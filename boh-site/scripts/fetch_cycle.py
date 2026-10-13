"""拉取 BTC 与三个平台币的长周期周线，以及周期内的历史数据。

数据源：DefiLlama Coins API（免费、无需 key）
  https://coins.llama.fi/chart/{id}?start=UNIX&span=N&period=1w
  注意：单次 span 上限 500 点，因此要分页拼接才能覆盖完整历史。

产物：
  src/btc-cycle.json    BTC 全历史周线（用于四年周期图，需覆盖多个周期）
  src/compare.json      同区间内 BTC 与平台币篮子的对比（用于图二）
"""

import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "public" / "data"   # 网站读 public/data；此前误写 src

IDS = {
    "BTC": "coingecko:bitcoin",
    "BNB": "coingecko:binancecoin",
    "OKB": "coingecko:okb",
    "HYPE": "coingecko:hyperliquid",
}
BASKET = ["HYPE", "BNB", "OKB"]

# 分页边界：DefiLlama 单次最多 500 点。
# 两页必须互相覆盖且各自起点正确，否则中段会空洞（曾因此丢掉 2023–2024 整段）。
PAGE_STARTS = [1367107200, 1672531200]   # 2013-04-28, 2023-01-01
SPAN = 500
PERIOD = "1w"
CMP_START = 1733097600                    # 2024-12-02（HYPE 上市交易首周）
UA = {"User-Agent": "Mozilla/5.0 (compatible; boh-prototype/0.1)"}


def get(url: str):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_weekly_paged(coin_id: str) -> list:
    """分页抓取周线并按时间戳去重排序。"""
    merged = {}
    for start in PAGE_STARTS:
        url = f"https://coins.llama.fi/chart/{coin_id}?start={start}&span={SPAN}&period={PERIOD}"
        for p in get(url).get("coins", {}).get(coin_id, {}).get("prices", []):
            merged[int(p["timestamp"])] = float(p["price"])
        time.sleep(0.35)
    return sorted(merged.items())


def fetch_weekly(coin_id: str) -> list:
    """自 HYPE 上市交易首周起（用于平台币对比）。"""
    url = f"https://coins.llama.fi/chart/{coin_id}?start={CMP_START}&span=320&period={PERIOD}"
    out = get(url).get("coins", {}).get(coin_id, {}).get("prices", [])
    return [(int(p["timestamp"]), float(p["price"])) for p in out]


def align(hist: dict) -> tuple:
    """按周对齐（时间戳可能差几秒，按 7 天为界取整）。"""
    def by_week(points):
        d = {}
        for ts, price in points:
            wk = ts // 604800
            if wk not in d:
                d[wk] = (ts, price)
        return d

    per = {s: by_week(p) for s, p in hist.items()}
    common = None
    for d in per.values():
        keys = set(d.keys())
        common = keys if common is None else (common & keys)
    common = sorted(common)
    dates = [per["BTC"][w][0] for w in common]
    series = {s: [per[s][w][1] for w in common] for s in hist}
    return dates, series


def main() -> None:
    print("fetching BTC full history (paged) ...")
    btc_hist = fetch_weekly_paged(IDS["BTC"])
    print(f"  BTC {len(btc_hist)} weeks  {btc_hist[0][0]} -> {btc_hist[-1][0]}")

    print("fetching platform tokens (from 2021-11) ...")
    hist = {}
    for sym in BASKET:
        try:
            h = fetch_weekly(IDS[sym])
            hist[sym] = h
            print(f"  {sym:5s} {len(h)} weeks")
        except Exception as exc:  # noqa: BLE001
            print(f"  {sym:5s} FAILED: {exc}")
        time.sleep(0.4)

    # ---- 图一：BTC 全历史周期（用分页抓到的完整序列） ----
    btc_dates = [ts for ts, _ in btc_hist]
    btc_prices = [p for _, p in btc_hist]
    peak_i = max(range(len(btc_prices)), key=lambda i: btc_prices[i])
    cur = btc_prices[-1]
    peak = btc_prices[peak_i]
    print(f"BTC cycle: {len(btc_dates)} weeks  {btc_dates[0]} -> {btc_dates[-1]}")
    print(f"  peak  {btc_dates[peak_i]}  ${peak:,.0f}")
    print(f"  now   {btc_dates[-1]}  ${cur:,.0f}   drawdown {(cur/peak-1)*100:+.1f}%")

    # 周期顶底：用已确立的历史日期（市场事实），价格从实际序列取值。
    # 注意：这与"用算法猜极值"不同——这里只固定日期，价格全部来自真实数据。
    import datetime as dt

    def nearest_idx(y, m, d=15):
        target = dt.datetime(y, m, d, tzinfo=dt.timezone.utc).timestamp()
        return min(range(len(btc_dates)), key=lambda i: abs(btc_dates[i] - target))

    CYCLE_TURNS = [
        (2013, 11, 30, "high"),   # 2013 泡沫顶
        (2015, 1, 14, "low"),     # 2015 熊市底
        (2017, 12, 17, "high"),   # 2017 周期顶
        (2018, 12, 15, "low"),    # 2018 熊市底
        (2021, 11, 10, "high"),   # 2021 周期顶
        (2022, 11, 21, "low"),    # 2022 熊市底
        (2025, 10, 6, "high"),    # 2025 周期顶
    ]
    turns = [{"i": nearest_idx(y, m, d), "kind": k} for y, m, d, k in CYCLE_TURNS]

    print(f"  cycle turning points: {len(turns)}")
    for t in turns:
        print(f"    {btc_dates[t['i']]}  {t['kind']:4s}  ${btc_prices[t['i']]:,.0f}")

    # 周期区间：顶->底 为下行，底->顶 为上行
    periods = []
    for k in range(len(turns) - 1):
        t0, t1 = turns[k], turns[k + 1]
        periods.append({
            "from": btc_dates[t0["i"]], "to": btc_dates[t1["i"]],
            "fromPrice": btc_prices[t0["i"]], "toPrice": btc_prices[t1["i"]],
            "changePct": (btc_prices[t1["i"]] / btc_prices[t0["i"]] - 1) * 100,
            "kind": "bear" if t0["kind"] == "high" else "bull",
        })
    # 最后一段：最后一个转折点 -> 现在
    if turns:
        t0 = turns[-1]
        periods.append({
            "from": btc_dates[t0["i"]], "to": btc_dates[-1],
            "fromPrice": btc_prices[t0["i"]], "toPrice": btc_prices[-1],
            "changePct": (btc_prices[-1] / btc_prices[t0["i"]] - 1) * 100,
            "kind": "bear" if t0["kind"] == "high" else "bull",
        })

    print("  periods:")
    for p in periods:
        print(f"    {p['from']} -> {p['to']}  {p['kind']:4s}  {p['changePct']:+.1f}%")

    turning_points = [
        {"ts": btc_dates[t["i"]], "price": btc_prices[t["i"]], "kind": t["kind"]}
        for t in turns
    ]

    # 完整周期（顶部->顶部）的间隔，用来验证"四年一轮"这个说法
    highs = [t for t in turns if t["kind"] == "high"]
    cycle_gaps = []
    for k in range(len(highs) - 1):
        days = (btc_dates[highs[k + 1]["i"]] - btc_dates[highs[k]["i"]]) / 86400
        cycle_gaps.append({"from": btc_dates[highs[k]["i"]], "to": btc_dates[highs[k + 1]["i"]],
                           "days": days, "years": days / 365.25})
    for g in cycle_gaps:
        print(f"    cycle gap {g['days']:.0f} days = {g['years']:.2f} years")

    btc_cycle = {
        "generatedAt": int(time.time()),
        "source": "DefiLlama Coins API (coins.llama.fi), weekly",
        "unit": "USD",
        "dates": btc_dates,
        "prices": btc_prices,
        "peak": {"ts": btc_dates[peak_i], "price": peak},
        "current": {"ts": btc_dates[-1], "price": cur},
        "drawdownFromPeak": (cur / peak - 1) * 100,
        "turningPoints": turning_points,
        "periods": periods,
        "cycleGaps": cycle_gaps,
    }

    # ---- 图二：同区间平台币篮子 vs BTC（取交集，从 HYPE 上市那周算起） ----
    # 对比需要 BTC，所以把 BTC 的周线（截到同一时间范围）并入再对齐
    cmp_hist = dict(hist)
    cmp_hist["BTC"] = [(ts, p) for ts, p in btc_hist if ts >= CMP_START]
    dates, series = align(cmp_hist)
    print(f"aligned for comparison: {len(dates)} weeks  {dates[0]} -> {dates[-1]}")

    # ---- 图二：同区间平台币篮子 vs BTC ----
    base = {s: series[s][0] for s in BASKET}
    basket = [sum(series[s][i] / base[s] for s in BASKET) / len(BASKET) for i in range(len(dates))]
    btc_aligned = series["BTC"]
    btc_norm = [p / btc_aligned[0] * 100 for p in btc_aligned]
    basket_norm = [b * 100 for b in basket]
    vs = [basket_norm[i] / btc_norm[i] * 100 for i in range(len(dates))]

    compare = {
        "generatedAt": int(time.time()),
        "source": "DefiLlama Coins API (coins.llama.fi), weekly",
        "constituents": BASKET,
        "weighting": "equal",
        "dates": dates,
        "btc": btc_norm,
        "basket": basket_norm,
        "vsBtc": vs,
        "btcChange": btc_norm[-1] - 100,
        "basketChange": basket_norm[-1] - 100,
        "excess": (basket_norm[-1] - 100) - (btc_norm[-1] - 100),
    }
    print(f"  basket {compare['basketChange']:+.1f}%  BTC {compare['btcChange']:+.1f}%  excess {compare['excess']:+.1f}pp")

    for name, payload in (("btc-cycle.json", btc_cycle),):   # compare.json 已废弃，不再生成
        out = SRC / name
        tmp = out.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(out)
        print(f"  wrote {out}")


if __name__ == "__main__":
    main()
