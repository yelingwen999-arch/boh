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
GT_GAP = 2.2            # GeckoTerminal 免费额度 30 req/min，留余量
RETRY_429_S = 12        # 被限流后等多久再重试（不宜太长，否则预算被吃掉）
BUDGET_S = int(os.environ.get("FETCH_BUDGET_S", "1500"))
SCAN_RESERVE_S = int(os.environ.get("FETCH_SCAN_RESERVE_S", "420"))
MIN_POOLS = 5           # 少于这个数量视为本轮抓取失败，不覆盖线上
MAX_POOLS = 24          # 补全阶段最多处理多少个（按 24h 量降序取前 N）
CHAINS = {"solana", "bsc", "base", "robinhood"}
STABLES = {"USDG", "USDC", "USDT", "FRXUSD", "AUSD"}

TICKERS = [
    "SPCX", "NVDA", "TSLA", "MSTR", "SPY", "QQQ", "AAPL", "SNDK", "SKHY",
    "KORU", "NBIS", "CRCL", "HOOD", "COIN", "GME", "INTC", "MU", "AMZN",
    "GOOGL", "META", "MSFT", "PLTR", "TSM", "AVGO", "AMD", "NFLX", "GLD",
    "DJT", "AMC", "IREN", "AAOI", "CRWV", "WDC", "MRVL", "ARM", "GLXY",
    "SOXL", "TQQQ", "MUB", "BABA", "QCOM", "ORCL", "HIMS", "QNT", "GLW",
    "SMCI", "APP",
]

# 合法标的：只能是「搜索用的 ticker」本身，或它的 bStocks 版本（NVDAB / SPCXB…）。
# 不能用宽松正则：会被 cbBTC / wstETH / WBTC 这类非股票代币误匹配。
VALID_STOCKS = set(TICKERS) | {t + "B" for t in TICKERS}

T0 = time.time()


def budget_left():
    return BUDGET_S - (time.time() - T0)


def scan_budget_left():
    """扫描阶段的截止点：给补全阶段留出至少 SCAN_RESERVE_S。"""
    return budget_left() - SCAN_RESERVE_S


def get(url, timeout=25, retries=3):
    """带限流退避的 GET。

    GeckoTerminal 的免费额度对 onchain 端点限得很紧，连打几次就会 429。
    429 时只等 RETRY_429_S（而不是 30s），并且不占用重试次数——否则一次
    限流就会把一个池子的两个请求都烧掉，补全阶段直接空转。
    """
    attempt = 0
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
                # 限流不算失败尝试，等一会儿再打同一个请求
                time.sleep(RETRY_429_S)
                attempt += 1
                continue
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


def gt_daily(net, addr):
    """返回 (成交量 list, 收盘价 list)，都按时间正序（最新在后）。

    OHLCV 每行是 [ts, open, high, low, close, volume]，一次请求两样都拿到，
    不用为价格多发一次 —— GeckoTerminal 的额度很紧。
    """
    d = get(
        f"https://api.geckoterminal.com/api/v2/networks/{net}/pools/{addr}"
        f"/ohlcv/day?aggregate=1&limit=30&currency=usd"
    )
    rows = None
    if d and "data" in d:
        rows = d["data"].get("attributes", {}).get("ohlcv_list")
    if not rows:
        return [], []
    rows = list(reversed(rows))          # API 是倒序（最新在前），翻成正序
    vols = [float(b[5]) for b in rows if b[5]]
    closes = [float(b[4]) for b in rows if b[4]]
    return vols, closes


def scan_stock_pools():
    """在四条链上搜「股票代币 / 稳定币」交易对。

    扫描阶段按 ticker 逐个搜，每轮约 2.2s 限速；扫描只占用预算到
    scan_budget_left() 归零为止，剩下的时间全部留给补全阶段。
    """
    found = {}
    for t in TICKERS:
        if scan_budget_left() < 0:
            print(
                f"  · 扫描阶段预算用尽，停止搜索（已扫 {len(found)} 个候选）",
                flush=True,
            )
            break
        d = get(f"https://api.geckoterminal.com/api/v2/search/pools?query={t}&limit=25")
        time.sleep(GT_GAP)
        if not d:
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
            if b_tok in STABLES and q_tok in STABLES:
                continue
            if b_tok in STABLES:
                stock, stable = q_tok, b_tok
            elif q_tok in STABLES:
                stock, stable = b_tok, q_tok
            else:
                continue
            if stock not in VALID_STOCKS:
                continue
            vol = float((a.get("volume_usd") or {}).get("h24") or 0)
            key = pid.lower()
            if key not in found or vol > found[key]["vol"]:
                found[key] = {
                    "net": net,
                    "addr": pid.split("_", 1)[1],
                    "name": name,
                    "stock": stock,
                    "stable": stable,
                    "vol": vol,
                }
    return [r for r in found.values() if r["vol"] >= 100_000]


def enrich(pool):
    """补 TVL / 费率 / 30 天量能 / 收益口径，以及两个代币合约（组池链接要用）。

    每个池子只发两个请求：详情 + OHLCV。OHLCV 拿不到就用搜索阶段已有的
    24h 量兜底（此时 v7 = v30 = 24h 量，前端会显示 ndays 偏小）。
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
        m = re.search(r"(\d+(?:\.\d+)?)\s*%", pool["name"])
        fee = float(m.group(1)) if m else None

    # 两个代币合约：PancakeSwap 的 /add/<A>/<B> 必须用合约地址，不能用链名
    tok_a = tok_b = None
    try:
        rel = d["data"].get("relationships", {})
        tok_a = rel["base_token"]["data"]["id"].split("_", 1)[1]
        tok_b = rel["quote_token"]["data"]["id"].split("_", 1)[1]
    except Exception:
        pass

    vol24 = float((a.get("volume_usd") or {}).get("h24") or 0) or pool["vol"]

    time.sleep(GT_GAP)          # 两个请求之间限速，避免 429
    vols, closes = gt_daily(pool["net"], pool["addr"])

    if not tvl or fee is None:
        return None

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
    day7 = v7 * fee / 100 * share
    apr7 = day7 * 365 / CAP * 100
    apr30 = v30 * fee / 100 * share * 365 / CAP * 100

    # ---- 标的本身的价格走势 ----
    # 手续费再高，标的在跌也是白搭。存下收盘价序列和几个关键涨跌幅。
    px = {
        "last": closes[-1] if closes else None,
        "chg1d": None,
        "chg7d": None,
        "chg30d": None,
        "series": closes[-30:],
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
        "stock": pool["stock"],
        "stable": pool["stable"],
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
        "tok_b": tok_b,
    }


def main():
    print(f"开始抓取  {datetime.now(timezone.utc).isoformat(timespec='seconds')}", flush=True)
    print(
        f"预算 {BUDGET_S}s（扫描阶段预留 {SCAN_RESERVE_S}s 给补全）", flush=True
    )

    candidates = scan_stock_pools()
    candidates.sort(key=lambda r: -r["vol"])
    print(
        f"扫描结束：候选池 {len(candidates)} 个（24h 量 ≥ $100k），"
        f"取前 {min(len(candidates), MAX_POOLS)} 个补全；剩余预算 {budget_left():.0f}s",
        flush=True,
    )

    rows = []
    for p in candidates[:MAX_POOLS]:
        if budget_left() < 60:
            print(f"  · 预算用尽，停止补全（已完成 {len(rows)} 个）", flush=True)
            break
        r = enrich(p)
        if r:
            rows.append(r)
            print(f"  ok {r['name']:<34} APR30 {r['apr30']:7.0f}%", flush=True)

    if len(rows) < MIN_POOLS:
        print(
            f"抓取结果过少（{len(rows)} < {MIN_POOLS}），保留上一版 pools.json 不覆盖",
            flush=True,
        )
        return 1

    rows.sort(key=lambda r: -r["apr30"])
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
