"""从 DefiLlama 取官方口径的 LP 收益率。

为什么不用「成交量 × 费率 ÷ TVL」自己算：
实测那个算法和 DApp 官方显示的数字差 0.02 倍到 11 倍，而且没有规律——
费率怎么分配、LP 集中在哪个价格区间、成交量归属哪一档，都不是
公开数据能还原的。与其给一个看起来精确但错得离谱的数字，不如用官方口径。

DefiLlama 的 /pools 接口返回每个池的：
  apyBase   手续费收益（对应 DApp 上的 Fee APR）
  apyReward 激励收益（AERO / CAKE 等代币奖励）
  apy       两者合计（对应 DApp 上显示的 APR）

匹配方式：链 + 两个代币的合约地址。比符号匹配可靠得多——
同一个股票在不同链上的符号不一样（SKHYB / SKHYc / SKHYx），
用地址就没有歧义。
"""

import json
import ssl
import time
import urllib.request

LLAMA_URL = "https://yields.llama.fi/pools"
UA = {"User-Agent": "Mozilla/5.0"}

# GeckoTerminal 的链 id -> DefiLlama 的链名
CHAIN_TO_LLAMA = {
    "base": "Base",
    "bsc": "BSC",
    "solana": "Solana",
    "robinhood": "Robinhood Chain",
}


def _fetch(url, timeout=90, retries=3):
    ctx = ssl.create_default_context()
    # 某些环境下 api.aerodrome.finance 会报 SSL EOF，这里统一关掉校验只用于
    # 公开只读接口；DefiLlama 本身是 HTTPS 直连。
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:          # noqa: BLE001
            last = e
            time.sleep(3 * (i + 1))
    print(f"  ⚠ DefiLlama 请求失败：{type(last).__name__}: {last}", flush=True)
    return None


def _token_key(tokens):
    """两个代币地址 -> 排序后的元组，作为匹配键。"""
    toks = [str(t).lower() for t in tokens if t]
    if len(toks) != 2:
        return None
    return tuple(sorted(toks))


def load_yields():
    """返回 {(链, (addrA, addrB)): [{apy, apyBase, apyReward, tvlUsd, ...}]}。

    载入失败时返回空 dict——调用方要把「没有官方数据」和「官方说 0%」区分开。
    """
    d = _fetch(LLAMA_URL)
    if not d or "data" not in d:
        return {}

    idx = {}
    for p in d["data"]:
        chain = p.get("chain")
        if chain not in CHAIN_TO_LLAMA.values():
            continue
        k = _token_key(p.get("underlyingTokens") or [])
        if not k:
            continue
        idx.setdefault((chain, k), []).append(
            {
                "project": p.get("project"),
                "symbol": p.get("symbol"),
                "poolMeta": p.get("poolMeta"),
                "apy": p.get("apy"),
                "apyBase": p.get("apyBase"),
                "apyReward": p.get("apyReward"),
                "tvlUsd": p.get("tvlUsd"),
                "stablecoin": p.get("stablecoin"),
                "ilRisk": p.get("ilRisk"),
                "apyMean30d": p.get("apyMean30d"),
                "apyPct1D": p.get("apyPct1D"),
                "apyPct7D": p.get("apyPct7D"),
                "volumeUsd1d": p.get("volumeUsd1d"),
                "outlier": p.get("outlier"),
                "underlyingTokens": p.get("underlyingTokens"),
            }
        )
    return idx


def match_yield(idx, net, tok_a, tok_b, tvl):
    """按链 + 合约地址找官方数据。

    同一个地址对可能对应多个条目（比如聚合器 beefy 包了同一个底层池），
    用 TVL 最接近的那个——它最可能是同一条流动性。
    """
    chain = CHAIN_TO_LLAMA.get(net)
    k = _token_key([tok_a, tok_b])
    if not chain or not k:
        return None
    cand = idx.get((chain, k))
    if not cand:
        return None
    tvl = tvl or 0
    best = min(cand, key=lambda x: abs((x.get("tvlUsd") or 0) - tvl))
    # TVL 差太多说明不是同一个池（可能只是共用同一个代币对）
    t = best.get("tvlUsd") or 0
    if tvl > 0 and t > 0:
        ratio = max(t, tvl) / min(t, tvl)
        if ratio > 5:
            return None
    return best
