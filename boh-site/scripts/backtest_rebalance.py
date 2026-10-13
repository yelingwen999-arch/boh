"""BNB + OKB 双币等权组合的历史自平衡回测。

目的：用历史数据定最终采用哪种再平衡策略（用户要求：HYPE 是新币，先只回测 OKB 与 BNB）。

数据源：DefiLlama Coins API（免费、无需 key）
  https://coins.llama.fi/chart/{id}?start=UNIX&span=N&period=1d
  单次 span 上限 500 点，故按天分页拼接。

回测对象（同一区间：从两币都有日线数据的交集开始）：
  1. 不调仓 B&H        初始 50/50 后任其漂移
  2. 每日再平衡        每个交易日拉回 50/50
  3. 每周再平衡        每周一次拉回
  4. 阈值 ±5pp         偏离超过 5 个百分点才拉回
  5. 阈值 ±10pp        同上，阈值更宽

费用：单边按成交额收 0.1%（Binance/OKX/Gate 现货默认档），
      同时输出免手续费版本，以看清费用侵蚀。

产出：打印表格 + 写出 backtest-result.json（供页面后续使用）。
"""

import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "public" / "data" / "backtest-result.json"

IDS = {
    "BNB": "coingecko:binancecoin",
    "OKB": "coingecko:okb",
    "BTC": "coingecko:bitcoin",
}
FEE = 0.001            # 单边 0.1%
DAY = 86400
UA = {"User-Agent": "Mozilla/5.0 (compatible; boh-prototype/0.1)"}


def get(url: str):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_daily(coin_id: str, start: int) -> list:
    """分页抓日线，按天去重排序，直到追上当下。

    注意：早期数据可能稀疏（单页返回少于 span 个点），所以不能用
    "返回数 < span 就停"判断结束——只认"追上当下"或"一页空了"。
    """
    merged = {}
    s = start
    while True:
        url = f"https://coins.llama.fi/chart/{coin_id}?start={s}&span=500&period=1d"
        pts = get(url).get("coins", {}).get(coin_id, {}).get("prices", [])
        if not pts:
            break
        for p in pts:
            merged[int(p["timestamp"]) // DAY] = float(p["price"])
        last = max(int(p["timestamp"]) for p in pts)
        if last > time.time() - 2 * DAY:
            break
        s = last + DAY
        time.sleep(0.35)
    return sorted(merged.items())   # [(day_index, price)]


def align(series_list):
    """把多条日线序列按天对齐，只留交集。"""
    sets = [set(d for d, _ in s) for s in series_list]
    common = set.intersection(*sets)
    days = sorted(common)
    lookup = [{d: p for d, p in s} for s in series_list]
    return days, [[lk[d] for d in days] for lk in lookup]


# ---------------- 回测引擎 ----------------

def rebalance(v, w, target):
    """按目标权重调仓，返回 (新组合值, 调仓笔费)。v: 各资产市值, w: 各资产数量, target: 目标权重。"""
    total = sum(v)
    traded = sum(abs(x - t) * total for x, t in zip(
        [vi / total for vi in v], target))
    fee = traded * FEE
    return total - fee, fee


def run(prices, strategy, fee_on=True, target=(0.5, 0.5)):
    """prices: [[p0...],[p1...]] 每步已按 day 对齐。
    返回 (期末值, 最大回撤, 调仓次数, 累计费用, 净值序列)。"""
    n = len(prices[0])
    # 初始：按目标权重配置，总值从 100 起（便于直接读百分比）
    w = [100.0 * t / prices[i][0] for i, t in enumerate(target)]
    v = [w[i] * prices[i][0] for i in range(len(prices))]
    days = 0
    fees = 0.0
    rebalances = 0
    nav = []
    peak = 0.0              # 不能用 inf：max(inf, x) 恒为 inf，回撤会被算成 -100%
    maxdd = 0.0

    for d in range(n):
        v = [w[i] * prices[i][d] for i in range(len(prices))]
        total = sum(v)
        peak = max(peak, total)
        maxdd = min(maxdd, total / peak - 1)
        nav.append(total)
        days += 1

        # 触发判断（从第 2 天开始）
        if d == 0:
            continue
        cur = [vi / total for vi in v]
        if strategy == "buyhold":
            continue
        elif strategy == "daily":
            trig = True
        elif strategy == "weekly":
            trig = (days % 7 == 0)
        elif strategy.startswith("th"):   # th5 / th10
            pp = float(strategy[2:]) / 100
            trig = any(abs(c - t) > pp for c, t in zip(cur, target))
        else:
            trig = False
        if trig:
            total2, fee = rebalance(v, w, target)
            if fee_on:
                fees += fee
                total2 = total - fee
            else:
                fee = 0.0
                total2 = total
            rebalances += 1
            w = [total2 * t / prices[i][d] for i, t in enumerate(target)]
            v = [w[i] * prices[i][d] for i in range(len(prices))]
    return sum(v), maxdd, rebalances, fees, nav


def main():
    print("fetching BNB daily ...")
    bnb = fetch_daily(IDS["BNB"], 1498867200)      # 2017-07-01
    print(f"  {len(bnb)} days  {bnb[0][0]} -> {bnb[-1][0]}")
    print("fetching OKB daily ...")
    okb = fetch_daily(IDS["OKB"], 1525132800)      # 2018-05-01
    print(f"  {len(okb)} days  {okb[0][0]} -> {okb[-1][0]}")
    print("fetching BTC daily (benchmark) ...")
    btc = fetch_daily(IDS["BTC"], 1498867200)
    print(f"  {len(btc)} days")

    days, (p_bnb, p_okb, p_btc) = align([bnb, okb, btc])
    n = len(days)
    print(f"aligned: {n} days  {days[0]} -> {days[-1]}")
    start_ts, end_ts = days[0] * DAY, days[-1] * DAY

    import datetime as dt
    d0 = dt.datetime.fromtimestamp(start_ts, dt.timezone.utc).strftime("%Y-%m-%d")
    d1 = dt.datetime.fromtimestamp(end_ts, dt.timezone.utc).strftime("%Y-%m-%d")
    years = (end_ts - start_ts) / (365.25 * DAY)

    prices_pair = [p_bnb, p_okb]
    # 产品目标权重 4:3:3（BNB 40 / OKB 30 / HYPE 30，多给 BNB 的一份是压舱石）。
    # 回测只含双币：剔除 HYPE 后按比例换算 BNB 40/70≈57%、OKB 30/70≈43%。
    TARGET = (0.57, 0.43)
    strategies = [
        ("buyhold", "不调仓", "初始按目标比例，此后不再动作"),
        ("daily", "每日再平衡", "每个交易日拉回目标比例"),
        ("weekly", "每周再平衡", "每 7 天拉回目标比例"),
        ("th5", "阈值 ±5pp", "偏离目标超过 5 个百分点才拉回"),
        ("th10", "阈值 ±10pp", "偏离目标超过 10 个百分点才拉回"),
    ]

    results = []
    curves = {}
    for fee_on in (True, False):
        tag = "含费 0.1%" if fee_on else "免手续费"
        print(f"\n=== {tag} ===")
        print(f"{'策略':<16s} {'期末净值':>12s} {'总收益':>10s} {'CAGR':>8s} "
              f"{'最大回撤':>9s} {'调仓次数':>8s} {'费用合计':>11s}")
        for key, label, rule in strategies:
            end, mdd, cnt, fees, nav = run(prices_pair, key, fee_on, target=TARGET)
            cagr = (end / 100) ** (1 / years) - 1
            if fee_on:
                # 净值曲线按周采样（给页面画图用，体积可控），并保证末点在内
                idxs = list(range(0, len(nav), 7))
                if idxs[-1] != len(nav) - 1:
                    idxs.append(len(nav) - 1)
                curves[key] = [round(nav[i], 1) for i in idxs]
                curve_days = [days[i] for i in idxs]
            print(f"{label:<16s} {end:12.1f} {(end/100-1)*100:9.1f}% "
                  f"{cagr*100:7.2f}% {mdd*100:8.1f}% {cnt:8d} {fees:11.2f}")
            results.append({
                "fee": fee_on, "key": key, "label": label, "rule": rule,
                "endValue": round(end, 2),
                "totalReturnPct": round((end / 100 - 1) * 100, 2),
                "cagrPct": round(cagr * 100, 2),
                "maxDrawdownPct": round(mdd * 100, 2),
                "rebalances": cnt, "feesPaid": round(fees, 2),
            })

    # 单币与 BTC 参照（免手续费，同一区间）
    print("\n=== 同区间参照（免手续费，均从 100 起） ===")
    refs = [
        ("BNB 买入持有", p_bnb[-1] / p_bnb[0]),
        ("OKB 买入持有", p_okb[-1] / p_okb[0]),
        ("BTC 买入持有", p_btc[-1] / p_btc[0]),
    ]
    ref_out = []
    for label, m in refs:
        print(f"  {label:<16s} {m:8.2f}x")
        ref_out.append({"label": label, "multiple": round(m, 3)})

    # 费用敏感性：免手续费下策略差异 vs 含费差异（看清成本）
    print("\n=== 关键对比（含费 0.1%） ===")
    with_fee = {r["key"]: r for r in results if r["fee"]}
    bh = with_fee["buyhold"]["endValue"]
    for key in ("daily", "weekly", "th5", "th10"):
        w = with_fee[key]
        print(f"  {w['label']:<14s} 期末 {w['endValue']:9.1f}  "
              f"vs 不调仓 {w['endValue']-bh:+9.1f}  费用 {w['feesPaid']:.1f}")

    payload = {
        "generatedAt": int(time.time()),
        "source": "DefiLlama Coins API (coins.llama.fi), daily",
        "pair": ["BNB", "OKB"],
        "weighting": "57 : 43（产品 4:3:3 剔除 HYPE 后的双币换算）",
        "target": {"BNB": 0.57, "OKB": 0.43},
        "productWeights": {"BNB": 0.4, "OKB": 0.3, "HYPE": 0.3},
        "start": start_ts, "end": end_ts, "startDate": d0, "endDate": d1,
        "days": n, "years": round(years, 2), "feeRate": "0.1% per side",
        "results": results, "references": ref_out,
        # 按周采样的净值曲线（首值=100），供策略页画图
        "curve": {
            "dates": [d * DAY for d in curve_days],
            "values": curves,        # key -> [nav...]
        },
        # 最终选定的策略（回测结论）
        "selected": "th5",
    }
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(OUT)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
