"""BNB + OKB 双币组合的历史自平衡回测。

目的：用历史数据定最终采用哪种再平衡策略与阈值。
（HYPE 仅约两年历史，不足以回测；本脚本只含 BNB 与 OKB。）

数据源：DefiLlama Coins API（免费、无需 key），日线分页拼接。

回测对象（同一区间：两币都有日线数据的交集）：
  不调仓 / 每日 / 每周 / 阈值 ±5·±10·±15·±20pp，含手续费与免手续费两版
另做三组检验，用于判断阈值差异是信号还是噪音：
  阈值扫描、自然年与滚动三年窗口、牛熊分段

费用：单边按成交额 0.1%（交易所现货默认档）。

产物：public/data/backtest-result.json（供策略页直接渲染）
"""

import json
import sys
import time
import urllib.request
import datetime as dt
from pathlib import Path

# Windows 控制台默认 GBK，打印中文与 ± 会抛 UnicodeEncodeError；统一按 UTF-8 输出
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

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

# 产品目标权重 4:3:3（BNB 40 / OKB 30 / HYPE 30，多给 BNB 的一份是压舱石）。
# 回测只含双币：剔除 HYPE 后按比例换算 BNB 40/70≈57%、OKB 30/70≈43%。
TARGET = (0.57, 0.43)

# 对照用的阈值列表（页面表格与图都取自这里）
THRESHOLDS = [5, 10, 15, 20]
SCAN_PP = [3, 5, 7, 10, 15, 20, 30]
SELECTED = "th15"


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
    """按目标权重调仓，返回 (调仓后总值, 本次费用)。"""
    total = sum(v)
    traded = sum(abs(x - t) * total for x, t in zip([vi / total for vi in v], target))
    return total - traded * FEE, traded * FEE


def run(prices, strategy, fee_on=True, target=TARGET):
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

        if d == 0:
            continue
        cur = [vi / total for vi in v]
        if strategy == "buyhold":
            continue
        elif strategy == "daily":
            trig = True
        elif strategy == "weekly":
            trig = (days % 7 == 0)
        elif strategy.startswith("th"):
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
                total2 = total
            rebalances += 1
            w = [total2 * t / prices[i][d] for i, t in enumerate(target)]
            v = [w[i] * prices[i][d] for i in range(len(prices))]
    return sum(v), maxdd, rebalances, fees, nav


def slice_prices(P, a, b):
    return [[arr[i] for i in range(a, b)] for arr in P]


def year_bounds(days):
    """按自然年切分（UTC）。"""
    out = []
    cy = dt.datetime.fromtimestamp(days[0] * DAY, dt.timezone.utc).year
    si = 0
    for i, d in enumerate(days):
        y = dt.datetime.fromtimestamp(d * DAY, dt.timezone.utc).year
        if y != cy:
            out.append((si, i, cy))
            si, cy = i, y
    out.append((si, len(days), cy))
    return out


def main():
    print("fetching BNB daily ...")
    bnb = fetch_daily(IDS["BNB"], 1498867200)      # 2017-07-01
    print(f"  {len(bnb)} days")
    print("fetching OKB daily ...")
    okb = fetch_daily(IDS["OKB"], 1525132800)      # 2018-05-01
    print(f"  {len(okb)} days")
    print("fetching BTC daily (benchmark) ...")
    btc = fetch_daily(IDS["BTC"], 1498867200)
    print(f"  {len(btc)} days")

    days, (p_bnb, p_okb, p_btc) = align([bnb, okb, btc])
    n = len(days)
    start_ts, end_ts = days[0] * DAY, days[-1] * DAY
    d0 = dt.datetime.fromtimestamp(start_ts, dt.timezone.utc).strftime("%Y-%m-%d")
    d1 = dt.datetime.fromtimestamp(end_ts, dt.timezone.utc).strftime("%Y-%m-%d")
    years = (end_ts - start_ts) / (365.25 * DAY)
    print(f"aligned: {n} days  {d0} -> {d1}  ({years:.2f} 年)")

    P = [p_bnb, p_okb]
    strategies = [
        ("buyhold", "不调仓", "初始按目标比例，此后不再动作"),
        ("daily", "每日再平衡", "每个交易日拉回目标比例"),
        ("weekly", "每周再平衡", "每 7 天拉回目标比例"),
    ] + [(f"th{t}", f"阈值 ±{t}pp", f"偏离目标超过 {t} 个百分点才拉回") for t in THRESHOLDS]

    # ---------- 主表：各策略（含费 / 免手续费） ----------
    results = []
    curves = {}
    curve_days = None
    for fee_on in (True, False):
        print(f"\n=== {'含费 0.1%' if fee_on else '免手续费'} ===")
        print(f"{'策略':<16s} {'期末值':>11s} {'总收益':>11s} {'年化':>8s} "
              f"{'最大回撤':>9s} {'调仓':>7s} {'费用':>9s}")
        for key, label, rule in strategies:
            end, mdd, cnt, fees, nav = run(P, key, fee_on)
            cagr = (end / 100) ** (1 / years) - 1
            if fee_on:
                idxs = list(range(0, len(nav), 7))
                if idxs[-1] != len(nav) - 1:
                    idxs.append(len(nav) - 1)
                curves[key] = [round(nav[i], 1) for i in idxs]
                curve_days = [days[i] for i in idxs]
            print(f"{label:<16s} {end:11.1f} {(end/100-1)*100:10.1f}% "
                  f"{cagr*100:7.2f}% {mdd*100:8.1f}% {cnt:7d} {fees:9.2f}")
            results.append({
                "fee": fee_on, "key": key, "label": label, "rule": rule,
                "endValue": round(end, 2),
                "totalReturnPct": round((end / 100 - 1) * 100, 2),
                "cagrPct": round(cagr * 100, 2),
                "maxDrawdownPct": round(mdd * 100, 2),
                "rebalances": cnt, "feesPaid": round(fees, 2),
            })

    # ---------- 阈值扫描 ----------
    print("\n=== 阈值扫描 ===")
    scan = []
    print(f"{'阈值':>8s} {'期末值':>11s} {'年化':>8s} {'调仓':>7s} {'费用':>8s}")
    for pp in SCAN_PP:
        end, mdd, cnt, fees, _ = run(P, f"th{pp}", True)
        cagr = (end / 100) ** (1 / years) - 1
        scan.append({
            "pp": pp, "endValue": round(end, 2),
            "totalReturnPct": round((end / 100 - 1) * 100, 2),
            "cagrPct": round(cagr * 100, 2),
            "maxDrawdownPct": round(mdd * 100, 2),
            "rebalances": cnt, "feesPaid": round(fees, 2),
        })
        print(f"{'±' + str(pp) + 'pp':>8s} {end:11.1f} {cagr*100:7.2f}% {cnt:7d} {fees:8.2f}")
    print(f"  不调仓作为参照：{run(P, 'buyhold', True)[0]:.0f}")

    # ---------- 稳健性：自然年 ----------
    print("\n=== 自然年（各阈值当年期末值，从 100 起）===")
    yearly = []
    head = " ".join(f"{'±' + str(t) + 'pp':>10s}" for t in THRESHOLDS)
    print(f"{'年份':>6s} {head} {'最优':>8s}")
    for a, b, year in year_bounds(days):
        if b - a < 60:
            continue
        vals = {f"th{t}": round(run(slice_prices(P, a, b), f"th{t}", True)[0], 1) for t in THRESHOLDS}
        best = max(vals, key=vals.get).replace("th", "")
        yearly.append({"year": year, "values": vals, "best": int(best)})
        print(f"{year:>6d} " + " ".join(f"{vals['th' + str(t)]:10.1f}" for t in THRESHOLDS)
              + f" {'±' + best + 'pp':>8s}")

    # ---------- 稳健性：滚动三年 ----------
    print("\n=== 滚动 3 年窗口 ===")
    rolling = []
    w3 = int(3 * 365.25)
    s = 0
    print(f"{'起点':>12s} {head} {'最优':>8s}")
    while s + w3 <= n:
        vals = {f"th{t}": round(run(slice_prices(P, s, s + w3), f"th{t}", True)[0], 1)
                for t in THRESHOLDS}
        best = max(vals, key=vals.get).replace("th", "")
        rolling.append({
            "start": dt.datetime.fromtimestamp(days[s] * DAY, dt.timezone.utc).strftime("%Y-%m-%d"),
            "values": vals, "best": int(best),
        })
        print(f"{rolling[-1]['start']:>12s} "
              + " ".join(f"{vals['th' + str(t)]:10.1f}" for t in THRESHOLDS)
              + f" {'±' + best + 'pp':>8s}")
        s += 365

    # ---------- 牛熊分段 ----------
    print("\n=== 牛熊分段 ===")
    spans = [
        ("2018 熊市", "2018-01-01", "2019-01-31"),
        ("2019-2020 上行", "2019-02-01", "2021-04-30"),
        ("2021-2022 熊市", "2021-11-01", "2022-12-31"),
        ("2023-2024 上行", "2023-01-01", "2024-12-31"),
        ("2025-10 至今", "2025-10-01", None),
    ]
    phases = []
    print(f"{'区间':>18s} {head} {'不调仓':>9s} {'最优':>8s}")
    for label, s0, s1 in spans:
        t0 = dt.datetime.strptime(s0, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp()
        a = next((i for i, x in enumerate(days) if x * DAY >= t0), None)
        if a is None:
            continue
        if s1:
            t1 = dt.datetime.strptime(s1, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp()
            b = next((i for i, x in enumerate(days) if x * DAY > t1), n)
        else:
            b = n
        if b - a < 30:
            continue
        vals = {f"th{t}": round(run(slice_prices(P, a, b), f"th{t}", True)[0], 1)
                for t in THRESHOLDS}
        bh = round(run(slice_prices(P, a, b), "buyhold", True)[0], 1)
        best = max(vals, key=vals.get).replace("th", "")
        phases.append({"label": label, "values": vals, "buyhold": bh, "best": int(best)})
        print(f"{label:>18s} " + " ".join(f"{vals['th' + str(t)]:10.1f}" for t in THRESHOLDS)
              + f" {bh:9.1f} {'±' + best + 'pp':>8s}")

    # ---------- 单币与 BTC 参照 ----------
    print("\n=== 同区间参照（均从 100 起） ===")
    refs = [
        ("BNB 买入持有", p_bnb[-1] / p_bnb[0]),
        ("OKB 买入持有", p_okb[-1] / p_okb[0]),
        ("BTC 买入持有", p_btc[-1] / p_btc[0]),
    ]
    ref_out = []
    for label, m in refs:
        print(f"  {label:<16s} {m:8.2f}x")
        ref_out.append({"label": label, "multiple": round(m, 3)})

    # ---------- 夺冠统计（页面结论用） ----------
    def tally(rows):
        t = {f"th{n}": 0 for n in THRESHOLDS}
        for row in rows:
            t[f"th{row['best']}"] += 1
        return t
    champions = {
        "yearly": tally(yearly),
        "rolling": tally(rolling),
        "phases": tally(phases),
    }
    print(f"\n夺冠次数：{champions}")

    payload = {
        "generatedAt": int(time.time()),
        "source": "DefiLlama Coins API (coins.llama.fi), daily",
        "pair": ["BNB", "OKB"],
        "weighting": "57 : 43（产品 4:3:3 剔除 HYPE 后的双币换算）",
        "target": {"BNB": TARGET[0], "OKB": TARGET[1]},
        "productWeights": {"BNB": 0.4, "OKB": 0.3, "HYPE": 0.3},
        "start": start_ts, "end": end_ts, "startDate": d0, "endDate": d1,
        "days": n, "years": round(years, 2), "feeRate": "0.1% per side",
        "results": results, "references": ref_out,
        "curve": {"dates": [d * DAY for d in curve_days], "values": curves},
        "selected": SELECTED,
        "selectedPp": int(SELECTED[2:]),
        "thresholds": THRESHOLDS,
        "scan": scan,
        "yearly": yearly,
        "rolling": rolling,
        "phases": phases,
        "champions": champions,
    }
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(OUT)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
