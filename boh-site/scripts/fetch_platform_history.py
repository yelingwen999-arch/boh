"""拉取 BNB / OKB / HYPE / BTC 的完整历史，用于"平台币自诞生即领先 BTC"这张图。

要点：BNB 是三者中历史最长的（2017-07），以它为骨架。
每个平台币各自从"首周"归一到 100，BTC 从 BNB 首周归一。
对比的每个平台币窗口都单独计算，避免用一个共同起点掩盖各自的起点。

产物：src/platform-history.json
"""

import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "public" / "data" / "platform-history.json"

IDS = {
    "BTC": "coingecko:bitcoin",
    "BNB": "coingecko:binancecoin",
    "OKB": "coingecko:okb",
    "HYPE": "coingecko:hyperliquid",
}
# BNB 从 2017-07 起；两页拼接（单次 span 上限 500）
PAGE_STARTS = [1498867200, 1698796800]   # 2017-07-01, 2023-11-01
SPAN = 500
PERIOD = "1w"
UA = {"User-Agent": "Mozilla/5.0 (compatible; boh-prototype/0.1)"}


def get(url: str):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_weekly_paged(coin_id: str) -> list:
    merged = {}
    for start in PAGE_STARTS:
        url = f"https://coins.llama.fi/chart/{coin_id}?start={start}&span={SPAN}&period={PERIOD}"
        for p in get(url).get("coins", {}).get(coin_id, {}).get("prices", []):
            merged[int(p["timestamp"])] = float(p["price"])
        time.sleep(0.35)
    return sorted(merged.items())


def by_day(points: list) -> dict:
    out = {}
    for ts, price in points:
        wk = ts // 604800
        if wk not in out:
            out[wk] = (ts, price)
    return out


def main() -> None:
    print("fetching full history ...")
    raw = {}
    for sym, cid in IDS.items():
        try:
            h = fetch_weekly_paged(cid)
            raw[sym] = by_day(h)
            first = min(raw[sym].values(), key=lambda v: v[0])
            print(f"  {sym:5s} {len(raw[sym])} weeks  from {first[0]}")
        except Exception as exc:  # noqa: BLE001
            print(f"  {sym:5s} FAILED: {exc}")
        time.sleep(0.35)

    if len(raw) != len(IDS):
        raise SystemExit("history incomplete")

    # 以 BNB 的周序列作为骨架
    spine = sorted(raw["BNB"].keys())
    dates = [raw["BNB"][w][0] for w in spine]

    bnb = [raw["BNB"][w][1] for w in spine]

    # BTC：从 BNB 首周开始（找不到就取最接近的周）
    btc_map = raw["BTC"]
    btc_first_key = min(btc_map.keys(), key=lambda w: abs(w - spine[0]))
    btc = [btc_map.get(w, (None, None))[1] for w in spine]
    # 补齐缺失（用前值填充）
    last = None
    for i in range(len(btc)):
        if btc[i] is None:
            btc[i] = last
        else:
            last = btc[i]

    okb = [raw["OKB"].get(w, (None, None))[1] for w in spine]
    hy = [raw["HYPE"].get(w, (None, None))[1] for w in spine]

    def first_valid(arr):
        return next((i for i, v in enumerate(arr) if v is not None), None)

    def norm(arr, i0):
        base = arr[i0]
        return [None if v is None else v / base * 100 for v in arr]

    i_bnb = first_valid(bnb)
    i_okb = first_valid(okb)
    i_hype = first_valid(hy)
    i_btc = first_valid(btc)

    def changed(arr, i0):
        if i0 is None:
            return None
        base = arr[i0]
        cur = next((v for v in reversed(arr) if v is not None), None)
        return None if (base is None or cur is None) else (cur / base - 1) * 100

    payload = {
        "generatedAt": int(time.time()),
        "source": "DefiLlama Coins API (coins.llama.fi), weekly",
        "dates": dates,
        # 原始价格序列（对齐到 BNB 的周骨架，缺失为 null）
        "raw": {"BNB": bnb, "OKB": okb, "HYPE": hy, "BTC": btc},
        # 归一序列（各自首周 = 100），供表格用
        "series": {
            "BNB": norm(bnb, i_bnb),
            "OKB": norm(okb, i_okb),
            "HYPE": norm(hy, i_hype),
            "BTC": norm(btc, i_btc),
        },
        "startIdx": {"BNB": i_bnb, "OKB": i_okb, "HYPE": i_hype, "BTC": i_btc},
        "changes": {s: changed(a, i) for s, (a, i) in {
            "BNB": (bnb, i_bnb), "OKB": (okb, i_okb),
            "HYPE": (hy, i_hype), "BTC_from_bnb": (btc, i_btc),
        }.items()},
        "rawLast": {"BNB": bnb[-1], "OKB": okb[-1], "HYPE": hy[-1], "BTC": btc[-1]},
    }

    # 每个平台币窗口内 BTC 的同期涨幅
    windows = {}
    for s, i0 in (("BNB", i_bnb), ("OKB", i_okb), ("HYPE", i_hype)):
        arrs = {"BNB": bnb, "OKB": okb, "HYPE": hy}[s]
        btcs = btc
        if i0 is None:
            continue
        b0 = btcs[i0]
        # 该币最后一个有效位置
        last_i = max(i for i, v in enumerate(arrs) if v is not None)
        windows[s] = {
            "from": dates[i0],
            "to": dates[last_i],
            "tokenChange": (arrs[last_i] / arrs[i0] - 1) * 100,
            "btcChange": (btcs[last_i] / b0 - 1) * 100 if b0 else None,
        }
        windows[s]["excess"] = windows[s]["tokenChange"] - windows[s]["btcChange"]
    payload["windows"] = windows

    print()
    for s, w in windows.items():
        print(f"  {s:5s} 自 {w['from']}  {w['tokenChange']:+9.1f}%  "
              f"BTC 同期 {w['btcChange']:+8.1f}%  超额 {w['excess']:+8.1f}pp")

    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(OUT)
    print(f"\nwrote {OUT}  ({len(dates)} weeks)")


if __name__ == "__main__":
    main()
