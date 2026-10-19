"""美股代币 LP 看板 — 数据抓取（静态站版本）

从 FastAPI 版的 server.py 移植：去掉后台线程与 Web 服务，只保留抓取逻辑，
结果写成静态 JSON（lp-site/public/data/pools.json），由 GitHub Actions 定时
运行并提交，Cloudflare Pages 自动重新部署。

与 server.py 的差异：
  - 不再依赖 cache.json / 常驻进程；每次运行都是独立的一次抓取
  - 单次运行有总时长预算（默认 25 分钟），超预算就带着已有结果退出，
    避免 GitHub Actions 的 20 分钟超时把整轮结果丢掉
  - 抓取失败时**保留上一版 pools.json**，不用残缺数据覆盖线上

用法：
    cd lp-site/scripts
    python fetch_pools.py
"""
import json
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.normpath(os.path.join(HERE, "..", "public", "data", "pools.json"))

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}
CAP = 10_000.0          # 收益口径用的本金，与前端默认值一致
GT_GAP = 3.0            # GeckoTerminal 免费额度 30 req/min。2.2s 实测仍频繁 429，放到 3.0s
RETRY_429_S = 12        # 被限流后首次等待时长（之后递增，且不吃重试次数）
BUDGET_S = int(os.environ.get("FETCH_BUDGET_S", "1500"))
SCAN_RESERVE_S = int(os.environ.get("FETCH_SCAN_RESERVE_S", "420"))
MIN_POOLS = 5           # 少于这个数量视为本轮抓取失败，不覆盖线上
MAX_POOLS = 72          # 补全阶段上限（按 24h 量降序）。放宽是因为同一股票在几条链上都有池
PER_TICKER_MIN = 3      # 每个标的至少保留这么多池，避免小链被大池挤掉
HOURLY_TOP_N = 40       # 只给成交量前 N 的池抓小时线，省额度（K 线主要看大池）
HOURLY_LIMIT = 720      # 小时线根数（720 = 30 天，GeckoTerminal 一次上限）
MIN_VOL = 30_000        # 候选池的最低 24h 量。放宽到 30K，让小链上的池子也能进来
CHAINS = {"solana", "bsc", "base", "robinhood"}
STABLES = {"USDG", "USDC", "USDT", "FRXUSD", "AUSD"}

# 非稳定币的主流计价资产。这些池子不是「股票/稳定币」，而是
# 「股票/原生币」——做市时你同时在承担原生币的涨跌，风险和稳定币池不是一回事。
# 单独标出来，前端会显示不同的计价标签，不混在股票/稳定币里。
QUOTE_NATIVE = {
    "WBNB", "BNB", "WETH", "ETH", "SOL", "WSOL",
    "HYPE", "WHYPE", "USDH", "AVAX", "WAVAX", "MATIC", "ARB", "OP", "BGB",
}

# 扫描用的美股代码。
#
# ⚠ 加新代码前先确认它真的是股票，别和加密货币撞名。
# 踩过的坑：QNT（Quant 网络，总量 2.1 万亿枚）被当成美股收进来，
# 结果列表里出现一个 TVL $505M 但日成交只有 $34 万的「池子」——
# 那不是股票代币，是加密货币。同理要注意 APP / ARM / COIN 这类
# 和加密圈重名的代码，加之前先查一下合约的 total_supply 是否像股票。
TICKERS = [
    "SPCX", "NVDA", "TSLA", "MSTR", "SPY", "QQQ", "AAPL", "SNDK", "SKHY",
    "KORU", "NBIS", "CRCL", "HOOD", "COIN", "GME", "INTC", "MU", "AMZN",
    "GOOGL", "META", "MSFT", "PLTR", "TSM", "AVGO", "AMD", "NFLX", "GLD",
    "DJT", "AMC", "IREN", "AAOI", "CRWV", "WDC", "MRVL", "ARM", "GLXY",
    "SOXL", "TQQQ", "MUB", "BABA", "QCOM", "ORCL", "HIMS", "GLW",
    "SMCI", "APP",
]

# 合法标的的判定。
#
# 同一个股票在每条链上的代币符号不一样，后缀也不同：
#   BSC        SKHYB    (bStocks)
#   Base       SKHYc
#   Solana     SKHYx
#   Robinhood  SKHY     (无后缀)
# 所以不能只认「ticker」和「ticker+B」——那样 Base 和 Solana 的池子会被全部
# 过滤掉（实测 SKHY 在 Solana 有 12 个池，全被漏了）。
#
# 规则：去掉末尾的 b/c/x 之后，必须仍在已知 ticker 列表里。
# 这样既覆盖所有链的后缀，又不会把 cbBTC / WBTC 之类的非股票代币放进来
# （它们的词根 cbBTC / WBTC 不在 TICKERS 里）。
TICKER_SET = set(TICKERS)
SUFFIXES = ("", "B", "c", "x")


def is_valid_stock(symbol):
    s = str(symbol).strip().upper()
    if not s:
        return False
    for suf in SUFFIXES:
        if suf:
            if s.endswith(suf.upper()) and s[: -len(suf)] in TICKER_SET:
                return True
        elif s in TICKER_SET:
            return True
    return False


def canonical_ticker(symbol):
    """把各链的代币符号归一到同一个 ticker。

    SKHYB / SKHYc / SKHYx -> SKHY；NVDAx -> NVDA；SPCXB -> SPCX
    这样同一个股票在不同链上的池子能被前端聚合到一起。
    注意：SPCX 本身以 X 结尾，但它在 TICKER_SET 里，优先原样返回。
    """
    s = str(symbol).strip().upper()
    if s in TICKER_SET:
        return s
    for suf in ("B", "X", "C"):
        if s.endswith(suf) and s[:-1] in TICKER_SET:
            return s[:-1]
    return s

T0 = time.time()

# 扫描阶段请求失败的 ticker。为空说明本轮扫描完整，非空则数据可能缺链。
SCAN_FAILED = []


def budget_left():
    return BUDGET_S - (time.time() - T0)


def scan_budget_left():
    """扫描阶段的截止点：给补全阶段留出至少 SCAN_RESERVE_S。"""
    return budget_left() - SCAN_RESERVE_S


def get(url, timeout=25, retries=3, max_429=8):
    """带限流退避的 GET。

    GeckoTerminal 免费额度限得很紧，连打几次就 429。这里有两个关键约定：

    1. 429 **不消耗** retries——否则连续几次限流就把这个请求彻底放弃，
       调用方拿到 None 后静默跳过，最后数据里凭空少一整条链。
       （之前就踩过：SPCX / TSLA 的搜索结果整批丢失，Solana 的池一个都没进。）
    2. 429 的等待是递增的，且受预算约束。

    返回 None 表示「确实没有」（404）或重试用尽，调用方必须自己区分要不要报警。
    """
    attempt = 0
    n429 = 0
    while attempt < retries:
        if budget_left() < 25:
            return None
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code == 429:
                n429 += 1
                if n429 > max_429:
                    return None
                # 递增等待：12s, 15s, 18s ... 最多 12+6*4=36s
                wait = RETRY_429_S + 3 * (n429 - 1)
                time.sleep(min(wait, 40))
                continue          # 注意：不动 attempt
            attempt += 1
            if attempt >= retries:
                return None
            time.sleep(1.5 * attempt)
        except Exception:
            attempt += 1
            if attempt >= retries:
                return None
            time.sleep(1.5 * attempt)
    return None


def gt_pool(net, addr):
    return get(f"https://api.geckoterminal.com/api/v2/networks/{net}/pools/{addr}")


def gt_ohlcv(net, addr, timeframe="day", limit=30):
    """抓 OHLCV，返回正序（最新在后）的 K 线列表。

    每根是 {t, o, h, l, c, v}。OHLCV 一次请求就把开高低收和成交量都给了，
    所以日线和小时线各只需要一个请求。
    """
    d = get(
        f"https://api.geckoterminal.com/api/v2/networks/{net}/pools/{addr}"
        f"/ohlcv/{timeframe}?aggregate=1&limit={limit}&currency=usd"
    )
    rows = None
    if d and "data" in d:
        rows = d["data"].get("attributes", {}).get("ohlcv_list")
    if not rows:
        return []
    out = []
    for b in reversed(rows):        # API 是倒序（最新在前），翻成正序
        try:
            out.append({
                "t": int(b[0]),
                "o": float(b[1]),
                "h": float(b[2]),
                "l": float(b[3]),
                "c": float(b[4]),
                "v": float(b[5]),
            })
        except (TypeError, ValueError, IndexError):
            continue
    return out


def gt_daily(net, addr, limit=30):
    """兼容旧调用：返回 (成交量 list, 收盘价 list, 完整日线 list)。"""
    bars = gt_ohlcv(net, addr, "day", limit)
    vols = [b["v"] for b in bars if b["v"]]
    closes = [b["c"] for b in bars if b["c"]]
    return vols, closes, bars


def scan_stock_pools():
    """在四条链上搜「股票代币 / 稳定币」交易对。

    扫描阶段按 ticker 逐个搜，每轮约 2.2s 限速；扫描只占用预算到
    scan_budget_left() 归零为止，剩下的时间全部留给补全阶段。
    """
    found = {}
    failed = []          # 请求失败的 ticker，最后汇总报警
    for t in TICKERS:
        if scan_budget_left() < 0:
            print(
                f"  · 扫描阶段预算用尽，停止搜索（已扫 {len(found)} 个候选）",
                flush=True,
            )
            break
        d = get(f"https://api.geckoterminal.com/api/v2/search/pools?query={t}&limit=25")
        time.sleep(GT_GAP)
        if d is None:
            # 关键：不能静默跳过。请求失败意味着这个 ticker 在所有链上的池子
            # 都会缺席，且前端完全看不出来。记下来，结束时报警。
            failed.append(t)
            continue
        for p in (d.get("data") or []):
            pid = p["id"]
            net = pid.split("_")[0]
            if net not in CHAINS:
                continue
            a = p.get("attributes") or {}
            name = a.get("name") or ""
            parts = [x.strip().upper() for x in name.split("/")]
            if len(parts) != 2:
                continue
            # 池子名常带费率后缀，如 "SPCXB / USDT 0.25%"
            b_tok = parts[0].split()[0] if parts[0].split() else parts[0]
            q_tok = parts[1].split()[0] if parts[1].split() else parts[1]

            # 一边是股票代币，另一边必须是稳定币或主流原生币。
            # 两类池子风险不同，记下计价类型供前端区分。
            quote = None
            if b_tok in STABLES:
                stock, quote, qkind = q_tok, b_tok, "stable"
            elif q_tok in STABLES:
                stock, quote, qkind = b_tok, q_tok, "stable"
            elif b_tok in QUOTE_NATIVE:
                stock, quote, qkind = q_tok, b_tok, "native"
            elif q_tok in QUOTE_NATIVE:
                stock, quote, qkind = b_tok, q_tok, "native"
            else:
                continue    # 两边都不是计价资产（可能是股票对股票、或 meme 对 meme）

            if not is_valid_stock(stock):
                continue
            # 两个都是股票代币的话（NVDA/TSLA 之类）不收，口径完全不一样
            if is_valid_stock(quote):
                continue
            vol = float((a.get("volume_usd") or {}).get("h24") or 0)
            key = pid.lower()
            if key not in found or vol > found[key]["vol"]:
                found[key] = {
                    "net": net,
                    "addr": pid.split("_", 1)[1],
                    "name": name,
                    "stock": canonical_ticker(stock),   # 归一到统一 ticker
                    "token": stock,                     # 保留原始符号，用于显示
                    "quote": quote,
                    "qkind": qkind,
                    "vol": vol,
                }
    if failed:
        print(
            f"  ⚠ 有 {len(failed)} 个 ticker 请求失败，它们的池子本轮会缺席："
            f"{', '.join(failed)}",
            flush=True,
        )
    SCAN_FAILED.extend(failed)
    return found.values()


def enrich(pool, want_hourly=True):
    """补 TVL / 费率 / 30 天量能 / 收益口径，以及两个代币合约（组池链接要用）。

    每个池子发两个请求：详情 + 日线 OHLCV。want_hourly 时再加一个请求抓小时线。
    OHLCV 拿不到就用搜索阶段已有的 24h 量兜底（此时 v7 = v30 = 24h 量，
    前端会显示 ndays 偏小）。
    """
    d = gt_pool(pool["net"], pool["addr"])
    if not d or "data" not in d:
        return None
    a = d["data"].get("attributes") or {}

    tvl = float(a.get("reserve_in_usd") or 0)
    fee = a.get("pool_fee_percentage")
    try:
        fee = float(fee)
    except (TypeError, ValueError):
        fee = None
    if fee is None:
        # 池名有时带费率后缀（"SPCXB / USDT 0.25%"），但 Solana 的池名
        # 一般不带（"SKHY / USDC"），所以这里经常取不到。
        m = re.search(r"(\d+(?:\.\d+)?)\s*%", pool["name"])
        fee = float(m.group(1)) if m else None
    if fee is None:
        # 再试 API 的十进制度量字段：有些 DEX 只给 fee_tier（基点）
        for k in ("fee_tier", "pool_fee", "fee_bps"):
            v = a.get(k)
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue
            # 大于 1 的按基点处理（30 -> 0.30%），否则当作百分比
            fee = fv / 100 if fv > 1 else fv
            break

    # 两个代币合约：PancakeSwap 的 /add/<A>/<B> 必须用合约地址，不能用链名
    tok_a = tok_b = None
    dex_id = None
    try:
        rel = d["data"].get("relationships", {})
        tok_a = rel["base_token"]["data"]["id"].split("_", 1)[1]
        tok_b = rel["quote_token"]["data"]["id"].split("_", 1)[1]
    except Exception:
        pass
    try:
        # DEX 标识（raydium-clmm / orca / meteora ...）。费率未知时，
        # 前端至少能告诉用户去哪儿看真实的费率档。
        dex_id = (d["data"].get("relationships") or {})["dex"]["data"]["id"]
    except Exception:
        pass

    vol24 = float((a.get("volume_usd") or {}).get("h24") or 0) or pool["vol"]

    time.sleep(GT_GAP)          # 两个请求之间限速，避免 429
    # 日线要 30 天算均量；同时留 90 根给前端 K 线（池子通常没那么多天）
    vols, closes, day_bars = gt_daily(pool["net"], pool["addr"], limit=90)

    # TVL 拿不到就没法算占比，这个是真没法保留
    if not tvl:
        return None

    # 费率拿不到不再丢弃池子。Solana 上的 Raydium / Orca / Meteora 经常
    # 不返回 pool_fee_percentage，池名也不带后缀——之前这里直接 return None，
    # 结果整条 Solana 链的池子全部消失，看起来像「这条链没有」。
    # 现在保留池子，APR 记为 None，前端显示「费率未知」。
    fee_known = fee is not None

    # 小时线单独再发一个请求。额度紧，只给成交量靠前的池子抓——
    # 池子多起来以后（72 个），全抓会超预算。日线仍然每个池都有。
    hour_bars = []
    if want_hourly and budget_left() > 120:
        time.sleep(GT_GAP)
        hour_bars = gt_ohlcv(pool["net"], pool["addr"], "hour", HOURLY_LIMIT)

    # 没有日线时退回 24h 量：不假装有 7/30 天数据
    if len(vols) >= 10:
        v7 = statistics.mean(vols[-7:])
        v30 = statistics.mean(vols)
    elif len(vols) >= 3:
        v7 = statistics.mean(vols[-7:])
        v30 = v7
    else:
        v7 = v30 = vol24

    share = CAP / (tvl + CAP)
    if fee_known:
        day7 = v7 * fee / 100 * share
        apr7 = day7 * 365 / CAP * 100
        apr30 = v30 * fee / 100 * share * 365 / CAP * 100
    else:
        # 费率未知：日收入与 APR 都无法给出，留 None 让前端显式显示「未知」，
        # 不要用 0 假装算过。
        day7 = apr7 = apr30 = None

    # ---- 标的本身的价格走势 ----
    # 手续费再高，标的在跌也是白搭。存下收盘价序列和几个关键涨跌幅。
    px = {
        "last": closes[-1] if closes else None,
        "chg1d": None,
        "chg7d": None,
        "chg30d": None,
        "series": closes[-30:],
        # K 线：日线最多 90 根（池子实际只有几十天）、小时线 720 根（30 天）
        "k": {
            "d": day_bars,
            "h": hour_bars,
        },
    }
    if closes:
        if len(closes) >= 2:
            px["chg1d"] = (closes[-1] / closes[-2] - 1) * 100
        if len(closes) >= 8:
            px["chg7d"] = (closes[-1] / closes[-8] - 1) * 100
        if len(closes) >= 2:
            px["chg30d"] = (closes[-1] / closes[0] - 1) * 100

    return {
        "name": pool["name"],
        "stock": pool["stock"],          # 归一后的 ticker（NVDA / SKHY）
        "token": pool.get("token", pool["stock"]),  # 链上实际符号（NVDAx / SKHYB）
        # stable 字段保留给前端（表示计价资产），同时用 qkind 区分稳定币/原生币
        "stable": pool["quote"],
        "quote": pool["quote"],
        "qkind": pool["qkind"],
        "net": pool["net"],
        "addr": pool["addr"],
        "fee": fee,
        "tvl": tvl,
        "vol24": vol24,
        "v7": v7,
        "v30": v30,
        "ndays": len(vols),
        "share_pct": share * 100,
        "day7": day7,
        "apr7": apr7,
        "apr30": apr30,
        "spark": vols[-30:],
        "px": px,
        "tok_a": tok_a,
        "dex": dex_id,
        "tok_b": tok_b,
    }


def main():
    print(f"开始抓取  {datetime.now(timezone.utc).isoformat(timespec='seconds')}", flush=True)
    print(
        f"预算 {BUDGET_S}s（扫描阶段预留 {SCAN_RESERVE_S}s 给补全）", flush=True
    )

    # 只要 24h 量过 MIN_VOL 就保留。这里不再按链做取舍——
    # 同一个股票在不同链上的池子都要露出来，小链的池子可能正是最好的一块。
    all_c = [r for r in scan_stock_pools() if r["vol"] >= MIN_VOL]
    if not all_c:
        print("扫描没有结果", flush=True)
        return 1

    # 选取策略：分三层，从强到弱。
    #
    # 为什么要分层：只按全局成交量取前 N，Solana / 小标的的池子永远排不上
    # 选取分三层，从强到弱。
    #
    # 为什么要分层：只按全局成交量取前 N，Solana / 小链的池子永远排不上
    # （实测 221 个候选里 Solana 的池一个都没进）。
    # 为什么第 1 层要按链轮转：即使做了「标的×链」保底，如果仍按全局量遍历，
    # Robinhood 的大池会先把名额吃光，轮到 Solana 时已经没位置了。
    # 所以第 1 层让每条链轮流各取一个，保证四条链都有实际数据。
    all_c.sort(key=lambda r: -r["vol"])

    picked = []
    picked_ids = set()

    def take(r):
        if id(r) in picked_ids or len(picked) >= MAX_POOLS:
            return False
        picked.append(r)
        picked_ids.add(id(r))
        return True

    # 第 1 层：按链轮转，每条链各取一个（标的×链 不重复）
    queues = {}
    for net in CHAINS:
        queues[net] = [r for r in all_c if r["net"] == net]
    seen_sc = set()
    progressed = True
    while progressed and len(picked) < MAX_POOLS:
        progressed = False
        for net in CHAINS:                      # 固定顺序轮转，结果可复现
            q = queues.get(net) or []
            while q:
                r = q.pop(0)
                k = (r["stock"], net)
                if k in seen_sc:
                    continue
                if take(r):
                    seen_sc.add(k)
                    progressed = True
                break

    # 第 2 层：每个标的凑够 PER_TICKER_MIN（含第 1 层已选的）
    per = {}
    for r in picked:
        per[r["stock"]] = per.get(r["stock"], 0) + 1
    for r in all_c:
        if per.get(r["stock"], 0) >= PER_TICKER_MIN:
            continue
        if take(r):
            per[r["stock"]] = per.get(r["stock"], 0) + 1

    # 第 3 层：按量补满
    for r in all_c:
        if len(picked) >= MAX_POOLS:
            break
        take(r)

    picked.sort(key=lambda r: -r["vol"])
    candidates = picked[:MAX_POOLS]

    n_native = sum(1 for r in candidates if r.get("qkind") == "native")
    n_net = len({r["net"] for r in candidates})
    n_stock = len({r["stock"] for r in candidates})
    print(
        f"扫描结束：候选 {len(all_c)} 个池 / {len({r['stock'] for r in all_c})} 个标的，"
        f"补全 {len(candidates)} 个（覆盖 {n_stock} 标的 / {n_net} 条链，"
        f"原生币计价 {n_native} 个）；剩余预算 {budget_left():.0f}s",
        flush=True,
    )

    rows = []
    for i, p in enumerate(candidates[:MAX_POOLS]):
        if budget_left() < 60:
            print(f"  · 预算用尽，停止补全（已完成 {len(rows)} 个）", flush=True)
            break
        # 小时线只给量大的那批抓；candidates 已按成交量降序
        r = enrich(p, want_hourly=(i < HOURLY_TOP_N))
        if r:
            rows.append(r)
            mark = "" if i < HOURLY_TOP_N else "  (无小时线)"
            apr = f"{r['apr30']:7.0f}%" if r["apr30"] is not None else "   费率未知"
            print(f"  ok {r['name']:<34} APR30 {apr}{mark}", flush=True)

    if len(rows) < MIN_POOLS:
        print(
            f"抓取结果过少（{len(rows)} < {MIN_POOLS}），保留上一版 pools.json 不覆盖",
            flush=True,
        )
        return 1

    rows.sort(key=lambda r: -(r["apr30"] if r["apr30"] is not None else -1))
    state = {
        "pools": rows,
        "updated": datetime.now(timezone.utc)
        .astimezone()
        .isoformat(timespec="seconds"),
        "n": len(rows),
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    print(f"完成：{len(rows)} 个池 → {OUT_PATH}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
