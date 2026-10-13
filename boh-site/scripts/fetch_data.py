"""拉取 HYPE / BNB / OKB / BTC 的数据，生成前端用的 JSON。

数据源（均免费、无需 key）：
  - DefiLlama Coins  https://coins.llama.fi   现价 + 日线历史
  - Gate.io           https://api.gateio.ws   24h 涨跌（行情接口）

产物：src/data.json
"""

import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "data.json"

IDS = {
    "BTC": "coingecko:bitcoin",
    "HYPE": "coingecko:hyperliquid",
    "BNB": "coingecko:binancecoin",
    "OKB": "coingecko:okb",
}

GATE_PAIRS = {
    "BTC": "BTC_USDT",
    "HYPE": "HYPE_USDT",
    "BNB": "BNB_USDT",
    "OKB": "OKB_USDT",
}

BASKET = ["HYPE", "BNB", "OKB"]
# 4:3:3 目标权重（BNB 最久经考验，多给的 10 个百分点是压舱石——风险机制，不是押注谁更强）
WEIGHTS = {"BNB": 0.4, "OKB": 0.3, "HYPE": 0.3}
BASE_TS = 1757000000
SPAN = 400
PERIOD = "1d"
UA = {"User-Agent": "Mozilla/5.0 (compatible; boh-prototype/0.1)"}


def post_json(url: str, payload: dict):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={**UA, "Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------- 平台实时数据（各平台官方接口） ----------

def fetch_hyperliquid_stats() -> dict:
    """Hyperliquid 官方统计。globalStats 未载于文档，但实测稳定可用。"""
    gs = post_json("https://api.hyperliquid.xyz/info", {"type": "globalStats"})
    ctx = post_json("https://api.hyperliquid.xyz/info", {"type": "metaAndAssetCtxs"})

    out = {
        "totalVolume": gs.get("totalVolume"),
        "dailyVolume": gs.get("dailyVolume"),
        "nUsers": gs.get("nUsers"),
        "openInterest": float(gs["oi"]) if gs.get("oi") else None,
    }

    # HYPE 的合约上下文
    names = ctx[0].get("universe", [])
    idx = next((i for i, u in enumerate(names) if u.get("name") == "HYPE"), None)
    if idx is not None:
        c = ctx[1][idx]
        out["hype"] = {
            "markPx": float(c["markPx"]) if c.get("markPx") else None,
            "oraclePx": float(c["oraclePx"]) if c.get("oraclePx") else None,
            "funding": float(c["funding"]) if c.get("funding") else None,
            "openInterest": float(c["openInterest"]) if c.get("openInterest") else None,
            "dayNtlVlm": float(c["dayNtlVlm"]) if c.get("dayNtlVlm") else None,
        }
    return out


def fetch_bnb_staking() -> dict:
    """BNB Chain 官方质押接口。"""
    raw = get("https://api.bnbchain.org/bnb-staking/v1/summary")
    s = raw.get("data", {}).get("summary", raw.get("data", {}))
    total = s.get("totalStaked")
    return {
        "activeValidators": s.get("activeValidators"),
        "totalValidators": s.get("totalValidators"),
        "maxApy": (s.get("maxApy") or 0) * 100 or None,
        "totalStaked": float(total) / 1e18 if total else None,
    }


def fetch_chain_tvl() -> dict:
    chains = get("https://api.llama.fi/v2/chains")
    want = {"BSC": "BNB Chain", "X Layer": "X Layer", "Hyperliquid L1": "Hyperliquid L1"}
    out = {}
    for c in chains:
        if c.get("name") in want:
            out[c["name"]] = c.get("tvl")
    return out


def fetch_dex_volumes() -> dict:
    q = "?excludeTotalDataChart=true&excludeTotalDataChartBreakdown=true"
    out = {}
    for key, slug in (("hyperliquid", "hyperliquid"), ("bsc", "bsc")):
        d = get(f"https://api.llama.fi/overview/dexs/{slug}{q}")
        out[key] = {
            "total24h": d.get("total24h"),
            "total7d": d.get("total7d"),
            "change1d": d.get("change_1d"),
            "change7d": d.get("change_7d"),
        }
    return out


def fetch_fees_full() -> dict:
    d = get("https://api.llama.fi/summary/fees/hyperliquid?dataType=dailyFees")
    return {
        "day": d.get("total24h"),
        "week": d.get("total7d"),
        "month": d.get("total30d"),
        "year": d.get("total1y"),
        "allTime": d.get("totalAllTime"),
        "change1d": d.get("change_1d"),
    }


def get(url: str):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8"))


def safe(label: str, fn):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        print(f"  {label} FAILED: {exc}")
        return None


def fetch_current() -> dict:
    raw = get("https://coins.llama.fi/prices/current/" + ",".join(IDS.values()))
    out = {}
    for sym, cid in IDS.items():
        node = raw.get("coins", {}).get(cid)
        if node:
            out[sym] = {"price": float(node["price"]), "ts": int(node["timestamp"])}
    return out


def fetch_chart(coin_id: str) -> list:
    url = f"https://coins.llama.fi/chart/{coin_id}?start={BASE_TS}&span={SPAN}&period={PERIOD}"
    series = get(url).get("coins", {}).get(coin_id, {}).get("prices", [])
    return [(int(p["timestamp"]), float(p["price"])) for p in series]


def fetch_gate_24h(pair: str):
    data = get(f"https://api.gateio.ws/api/v4/spot/tickers?currency_pair={pair}")
    if not data:
        return None
    t = data[0]
    return {
        "changePct": float(t["change_percentage"]),
        "high": float(t["high_24h"]),
        "low": float(t["low_24h"]),
        "quoteVolume": float(t.get("quote_volume") or 0),
    }


def align_by_day(hist: dict) -> tuple:
    """按 UTC 日对齐，返回 (dates, {sym: [prices]})。"""
    def by_day(points):
        out = {}
        for ts, price in points:
            day = ts // 86400
            if day not in out:
                out[day] = (ts, price)
        return out

    per_day = {sym: by_day(s) for sym, s in hist.items()}
    common = None
    for d in per_day.values():
        keys = set(d.keys())
        common = keys if common is None else (common & keys)
    common = sorted(common)
    dates = [per_day["BTC"][day][0] for day in common]
    series = {sym: [per_day[sym][day][1] for day in common] for sym in IDS}
    return dates, series


def rolling(series: list, dates: list, days: int):
    """返回 {changePct, fromTs}，起点取离 (末日 - days) 最近的一天。"""
    if not dates:
        return None
    end_ts = dates[-1]
    target = end_ts - days * 86400
    idx = min(range(len(dates)), key=lambda i: abs(dates[i] - target))
    base = series[idx]
    if not base:
        return None
    return {
        "changePct": (series[-1] / base - 1) * 100,
        "fromTs": dates[idx],
        "days": (end_ts - dates[idx]) / 86400,
    }


def main() -> None:
    print("current prices ...")
    current = safe("current", fetch_current) or {}
    for sym, v in current.items():
        print(f"  {sym:5s} ${v['price']:,.4f}")

    print("daily history ...")
    hist = {}
    for sym, cid in IDS.items():
        s = safe(sym, lambda cid=cid: fetch_chart(cid))
        if s:
            hist[sym] = s
            print(f"  {sym:5s} {len(s)} pts")

    if len(hist) != len(IDS):
        raise SystemExit("history incomplete, aborting")

    dates, series = align_by_day(hist)
    print(f"aligned: {len(dates)} days  {dates[0]} -> {dates[-1]}")

    print("24h from Gate.io ...")
    gate = {}
    for sym, pair in GATE_PAIRS.items():
        g = safe(sym, lambda p=pair: fetch_gate_24h(p))
        if g:
            gate[sym] = g
            print(f"  {sym:5s} {g['changePct']:+.2f}%")
        time.sleep(0.2)

    # BTC 各周期
    btc_roll = {d: rolling(series["BTC"], dates, d) for d in (30, 90, 365)}

    # 各资产相对 BTC 的超额
    assets = {}
    for sym in IDS:
        s = series[sym]
        r = {d: rolling(s, dates, d) for d in (30, 90, 365)}
        vs = {}
        for d, v in r.items():
            b = btc_roll[d]
            vs[str(d)] = None if (v is None or b is None) else v["changePct"] - b["changePct"]
        assets[sym] = {
            "price": current.get(sym, {}).get("price"),
            "change24h": (gate.get(sym) or {}).get("changePct"),
            "high24h": (gate.get(sym) or {}).get("high"),
            "low24h": (gate.get(sym) or {}).get("low"),
            "quoteVolume24h": (gate.get(sym) or {}).get("quoteVolume"),
            "change24hSource": "Gate.io",
            "rolling": {str(d): (r[d] or {}).get("changePct") for d in (30, 90, 365)},
            "vsBtc": vs,
        }

    # 篮子：4:3:3（每日再平衡），以 BTC 计价
    lens = len(dates)

    def approx_turnover(days: int = 365):
        """自建仓以来，调仓产生的累计换手率（4:3:3 再平衡的日均换手 × 天数）。"""
        from_idx = max(0, lens - days)
        base = {s: series[s][from_idx] for s in BASKET}
        weights = dict(WEIGHTS)
        total = 0.0
        for i in range(from_idx + 1, lens):
            vals = {s: series[s][i] / base[s] for s in BASKET}
            tot = sum(vals.values())
            cur_w = {s: vals[s] / tot for s in BASKET}
            total += sum(abs(cur_w[s] - weights[s]) for s in BASKET) / 2
            base = {s: series[s][i] for s in BASKET}
            weights = dict(WEIGHTS)
        return total

    # ---- 统一序列：以下所有数字都从这一条派生，避免口径不一致 ----
    CHART_DAYS = 365
    chart_from = max(0, lens - CHART_DAYS)
    chart_idx = list(range(chart_from, lens))

    basket_series = {}
    for sym in BASKET:
        base = series[sym][chart_from]
        basket_series[sym] = [series[sym][i] / base * 100 for i in chart_idx]

    btc_norm = [series["BTC"][i] / series["BTC"][chart_from] * 100 for i in chart_idx]

    # 4:3:3 篮子（每日再平衡）
    basket_norm = [
        sum(basket_series[s][k] * WEIGHTS[s] for s in BASKET)
        for k in range(len(chart_idx))
    ]

    # 篮子 / BTC 净值（起点 100）
    vs_btc = [basket_norm[k] / btc_norm[k] * 100 for k in range(len(chart_idx))]

    # 三个口径，分别命名，绝不混用：
    #   abs        = 篮子自身的涨跌（以 USDT 计）
    #   btc        = BTC 同期的涨跌
    #   vsBtcCum   = 累计跑赢：同期篮子涨幅 - BTC 涨幅（凡涨幅均为以起点为基准的累计值）
    def cum_change(arr: list, days: int):
        if len(arr) < 2:
            return None
        start = max(0, len(arr) - 1 - days)
        return (arr[-1] / arr[start] - 1) * 100

    metrics = {}
    for d in (30, 90, 365):
        babs = cum_change(basket_norm, d)
        cabs = cum_change(btc_norm, d)
        metrics[str(d)] = {
            "days": d,
            "abs": babs,
            "btc": cabs,
            "vsBtcCum": None if (babs is None or cabs is None) else babs - cabs,
        }

    print("  metrics:")
    for k, v in metrics.items():
        print(f"    {k:>4s}d  basket {v['abs']:+7.2f}%  BTC {v['btc']:+7.2f}%  vsBtcCum {v['vsBtcCum']:+7.2f}%")

    # 图表终点的累计超额，必须与 metrics['365'].vsBtcCum 一致
    cum_excess_end = (basket_norm[-1] - btc_norm[-1])
    print(f"    chart end cumulative excess = {cum_excess_end:+.2f}%")

    print("platform live data ...")
    hl_stats = safe("hyperliquid stats", fetch_hyperliquid_stats)
    if hl_stats:
        print(f"  HL 24h vol ${hl_stats['dailyVolume']:,.0f}  users {hl_stats['nUsers']:,}")
    bnb_staking = safe("bnb staking", fetch_bnb_staking)
    if bnb_staking:
        print(f"  BNB validators {bnb_staking['activeValidators']}/{bnb_staking['totalValidators']}"
              f"  maxApy {bnb_staking['maxApy']:.2f}%  staked {bnb_staking['totalStaked']:,.0f}")
    chain_tvl = safe("chain tvl", fetch_chain_tvl) or {}
    dex_vols = safe("dex volumes", fetch_dex_volumes) or {}
    fees_full = safe("hyperliquid fees", fetch_fees_full)
    if fees_full:
        print(f"  HL fees 24h ${fees_full['day']:,.0f}  1y ${fees_full['year']:,.0f}")

    payload = {
        "generatedAt": int(time.time()),
        "sources": {
            "prices": "DefiLlama Coins API (coins.llama.fi)",
            "change24h": "Gate.io spot tickers (api.gateio.ws)",
        },
        # 人工查证过的补充资料。凡查不到的一律 null，不填估算值。
        "supplementary": {
            "HYPE": {
                "chain": "Hyperliquid L1",
                "launch": "2024-11",
                "ath": 98.00,
                "athDate": "2026-09-23",
                "stakeApy": 2.24,
                "stakeApySource": "Staking Rewards",
                "stakeRatio": 46.28,
                "validatorCount": 27,
                "mcap": 28360000000,
                "mcapSource": "CoinLore",
                "buyback": True,
                "buybackNote": "手续费 97–99% 经 Assistance Fund 回购",
                "burned": "累计销毁逾 4,171 万枚（占总供应 4.17%）",
                "feeRevenue": fees_full,
                "feeRevenueSource": "DefiLlama Fees",
                "events": [
                    {"date": "2026-09-23", "text": "HYPE 创历史最高价 $98.00", "src": "Gate.io 日线"},
                    {"date": "2026-03-04", "text": "Assistance Fund 累计回购突破 10 亿美元，累计永久销毁 4,171 万枚 HYPE", "src": "ChainCatcher"},
                    {"date": "2026-06-30", "text": "累计协议收入突破 10 亿美元", "src": "ChainCatcher"},
                    {"date": "2025-10-13", "text": "HIP-3 激活：质押 50 万 HYPE 即可无许可创建自有永续市场", "src": "The Block"},
                ],
            },
            "BNB": {
                "chain": "BNB Smart Chain",
                "launch": "2017-07",
                "ath": 1375.7,
                "athDate": "2025-10-13",
                "stakeApy": (bnb_staking or {}).get("maxApy") or 1.09,
                "stakeApySource": "BNB Chain 官方质押 API" if bnb_staking else "BNB Chain 官方（原生质押）",
                "stakeRatio": None,
                "validatorCount": (bnb_staking or {}).get("activeValidators") or 45,
                "validatorTotal": (bnb_staking or {}).get("totalValidators") or 56,
                "totalStaked": (bnb_staking or {}).get("totalStaked"),
                "mcap": 103890000000,
                "mcapSource": "CoinLore（供应量口径偏旧，市值可能偏高）",
                "buyback": True,
                "buybackNote": "Auto-Burn 季度销毁 + BEP-95",
                "burned": "第 36 次销毁后剩余约 1.3317 亿枚（目标 1 亿枚）",
                "feeRevenue": None,
                "feeRevenueSource": None,
                "events": [
                    {"date": "2026-07-15", "text": "第 36 次销毁 1,615,827.795 BNB（约 9.32 亿美元），剩余总量约 1.3317 亿枚", "src": "ChainCatcher"},
                    {"date": "2026-04-16", "text": "第 35 次销毁 156.9 万枚 BNB（约 10.2 亿美元）", "src": "ChainCatcher"},
                    {"date": "2025-10-13", "text": "BNB 创历史最高 $1,375.7", "src": "Gate.io 日线"},
                    {"date": "2023-11-21", "text": "CZ 认罪并辞任 CEO；币安与 DOJ 等达成 43 亿美元和解，CZ 个人另罚 5,000 万美元", "src": "证券时报 / Yahoo Finance"},
                ],
            },
            "OKB": {
                "chain": "X Layer",
                "launch": "2019-04",
                "ath": 258.6,
                "athDate": "2025-08-22",
                "stakeApy": None,
                "stakeApySource": None,
                "stakeRatio": None,
                "validatorCount": None,
                "mcap": 2613000000,
                "mcapSource": "CoinLore",
                "buyback": True,
                "buybackNote": "2019-05 起共 28 次季度回购销毁；2020-02 销毁 7 亿枚未发行部分；2025-08 一次性销毁后永久固定 2,100 万枚，不再销毁",
                "burned": "一次性销毁 65,256,712.097 枚（占销毁前剩余总量的 75.7%）",
                "feeRevenue": None,
                "feeRevenueSource": None,
                "events": [
                    {"date": "2025-08-22", "text": "OKB 创下盘中历史最高 $258.6", "src": "ChainCatcher / Gate.io 周线"},
                    {"date": "2025-08-18", "text": "OKB 智能合约升级，移除增发与人工销毁功能，总发行量永久固定为 2,100 万枚", "src": "OKX 公告（转引 ChainCatcher）"},
                    {"date": "2025-08-13", "text": "OKX 公告代币经济模型优化：一次性销毁 65,256,712.097 枚 OKB；OKTChain 下线，OKT 按 7/13–8/12 均价兑换为 OKB", "src": "ChainCatcher / CoinPost"},
                    {"date": "2024-04-15", "text": "X Layer 公共主网上线（Polygon zkEVM 技术的以太坊 L2），OKB 为其唯一 Gas 及原生代币", "src": "The Block"},
                    {"date": "2020-10-16", "text": "OKEx 暂停提币，创始人徐明星被中国警方带走调查；约 5 周后于 11-27 恢复提币", "src": "Forbes / The Block"},
                    {"date": "2020-02-10", "text": "一次性销毁全部 7 亿枚未发行 OKB（原始计划总量 10 亿枚的 70%），总供应降至 3 亿枚", "src": "界面新闻"},
                ],
                "conflicts": [
                    "「占流通量 52%」这一广泛流传的说法无法与官方数字对上：65,256,712 ÷ 销毁前剩余 86,256,735.85 ≈ 75.7%，或占原始总发行量 3 亿枚的 21.75%，两个口径都能对上，52% 来源不明。",
                ],
            },
        },
        "assets": assets,
        # 各平台官方接口返回的实时数据。取不到的为 null。
        "platform": {
            "HYPE": {
                "source": "Hyperliquid 官方 API (api.hyperliquid.xyz/info, POST)",
                "stats": hl_stats,
                "dex24h": (dex_vols.get("hyperliquid") or {}).get("total24h"),
                "dex7d": (dex_vols.get("hyperliquid") or {}).get("total7d"),
                "dexChange1d": (dex_vols.get("hyperliquid") or {}).get("change1d"),
                "tvl": chain_tvl.get("Hyperliquid L1"),
            },
            "BNB": {
                "source": "BNB Chain 官方质押 API (api.bnbchain.org) + DefiLlama",
                "staking": bnb_staking,
                "dex24h": (dex_vols.get("bsc") or {}).get("total24h"),
                "dex7d": (dex_vols.get("bsc") or {}).get("total7d"),
                "dexChange1d": (dex_vols.get("bsc") or {}).get("change1d"),
                "tvl": chain_tvl.get("BSC"),
            },
            "OKB": {
                "source": "DefiLlama（OKX 官方接口在本机网络被拦截，无法接入）",
                "stats": None,
                "staking": None,
                "dex24h": None,
                "dex7d": None,
                "dexChange1d": None,
                "tvl": chain_tvl.get("X Layer"),
            },
        },
        "basket": {
            "constituents": BASKET,
            "weighting": "4:3:3",
            "windowDays": CHART_DAYS,
            "metrics": metrics,
            "approxTurnover365": approx_turnover(CHART_DAYS),
        },
        "chart": {
            "dates": [dates[i] for i in chart_idx],
            "basket": basket_norm,
            "btc": btc_norm,
            "vsBtc": vs_btc,
            "perAsset": basket_series,
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(OUT)
    print(f"\nwrote {OUT}  ({len(dates)} days, chart {len(chart_idx)} pts)")


if __name__ == "__main__":
    main()
