"""抓取顶部行情带需要的币种数据（价格 + 24h 涨跌）。

数据源：Gate.io spot tickers（免费、无需 key）
产物：src/market.json
"""

import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "market.json"

# 顺序即展示顺序
SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "HYPE", "OKB", "ZEC"]
UA = {"User-Agent": "Mozilla/5.0 (compatible; boh-prototype/0.1)"}


def fetch_ticker(pair: str):
    url = f"https://api.gateio.ws/api/v4/spot/tickers?currency_pair={pair}"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not data:
        return None
    t = data[0]
    return {
        "pair": pair,
        "price": float(t["last"]),
        "change24h": float(t["change_percentage"]),
        "high24h": float(t["high_24h"]),
        "low24h": float(t["low_24h"]),
        "quoteVolume24h": float(t.get("quote_volume") or 0),
    }


def main() -> None:
    out = {}
    for sym in SYMBOLS:
        pair = f"{sym}_USDT"
        try:
            d = fetch_ticker(pair)
            if d:
                out[sym] = d
                print(f"  {sym:5s} ${d['price']:>12,.4f}  {d['change24h']:+6.2f}%")
            else:
                print(f"  {sym:5s} 无数据")
        except Exception as exc:  # noqa: BLE001
            print(f"  {sym:5s} FAILED: {exc}")
        time.sleep(0.25)

    payload = {
        "generatedAt": int(time.time()),
        "source": "Gate.io spot tickers (api.gateio.ws)",
        "order": [s for s in SYMBOLS if s in out],
        "assets": out,
    }
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(OUT)
    print(f"\nwrote {OUT}  ({len(out)} symbols)")


if __name__ == "__main__":
    main()
