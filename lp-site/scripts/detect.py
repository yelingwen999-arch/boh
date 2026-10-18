"""异动检测：对比本次抓取和上一版快照，产出 alerts.json。

设计原则：
  1. 只在**真的有事**时才产出警报。宁可少报，不要天天刷屏——刷屏的警报等于没有警报。
  2. 首次运行（没有历史快照）不报警，只记录基线。
  3. 每条警报都带「上次值 → 本次值」，看的人自己能判断严重程度。

用法（由 workflow 调用）：
    python detect.py                 # 检测并写 alerts.json
    python detect.py --state x.json  # 指定上一版快照路径
"""
import json
import os
import sys
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.normpath(os.path.join(HERE, "..", "public", "data"))
POOLS_PATH = os.path.join(DATA_DIR, "pools.json")
STATE_PATH = os.path.join(DATA_DIR, "prev_pools.json")
KNOWN_PATH = os.path.join(DATA_DIR, "known_pools.json")
ALERTS_PATH = os.path.join(DATA_DIR, "alerts.json")

# ---- 阈值：先按保守值起，观察几天再调 ----
APR_JUMP_PCT = 60          # APR 相对上次涨幅 ≥60% 触发（且绝对值有意义）
APR_ABS_MIN = 30           # APR 低于这个值不谈「飙升」，避免小池子噪音
APR_TOP_RANK = 5           # 新进 APR 前 N 名也报一次
TVL_SWING_PCT = 35         # TVL 变化 ≥35% 触发
TVL_ABS_MIN = 20000        # TVL 小于该值时 TVL 变化不算数（小池子抖动大）
VOL_DRY_PCT = -60          # 7 日量能相对 30 日掉 ≥60% 视为萎缩
MICRO_TVL = 50000          # 低于此 TVL 的池子进入警报时明确标注「微型」
SHARE_WARN_PCT = 5         # 按本金算的占比超过该值告警
CAP_DEFAULT = 10000        # 与前端默认本金一致
BASELINE_MIN_RATIO = 0.6   # 本次池子数低于上一版的 60% 就认为抓取不完整，不更新基线


def load(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def key_of(p):
    """池子唯一标识：链 + 地址。地址变了就是新池子。"""
    return f"{p.get('net')}|{str(p.get('addr', '')).lower()}"


def label(p):
    """人看的名字：SPCX / USDG · Robinhood · 0.05%"""
    net_names = {
        "robinhood": "Robinhood",
        "bsc": "BNB Chain",
        "base": "Base",
        "solana": "Solana",
    }
    net = net_names.get(p.get("net"), p.get("net"))
    fee = p.get("fee")
    fee_s = f"{fee}%" if fee is not None else "?"
    return f"{p.get('stock')}/{p.get('stable')} · {net} · {fee_s}"


def pct(a, b):
    """a 相对 b 的变化百分比；b 为 0 时返回 None。"""
    if not b:
        return None
    return (a - b) / b * 100


def fmt_usd(v):
    if v is None:
        return "–"
    if v >= 1e6:
        return f"${v/1e6:.2f}M"
    if v >= 1e3:
        return f"${v/1e3:.1f}K"
    return f"${v:.0f}"


def detect(cur, prev):
    """对比两版数据，返回警报列表。"""
    alerts = []

    if not prev or not prev.get("pools"):
        return alerts  # 没有基线，本次只记录，不报警

    cur_pools = {key_of(p): p for p in cur.get("pools", [])}
    prev_pools = {key_of(p): p for p in prev.get("pools", [])}

    # ---- 1. 新池上线 ----
    for k, p in cur_pools.items():
        if k in prev_pools:
            continue
        tvl = p.get("tvl") or 0
        # 太小的池子不算「上线」，只是数据里冒出来的垃圾
        if tvl < TVL_ABS_MIN:
            continue
        alerts.append(
            {
                "type": "new_pool",
                "level": "info",
                "title": f"新池上线 · {label(p)}",
                "detail": f"TVL {fmt_usd(tvl)} · APR30 {p.get('apr30', 0):.0f}%",
                "pool": key_of(p),
                "prev": None,
                "now": {
                    "tvl": tvl,
                    "apr30": p.get("apr30"),
                },
            }
        )

    # ---- 2. APR 飙升 ----
    for k, p in cur_pools.items():
        q = prev_pools.get(k)
        if not q:
            continue
        a_now = p.get("apr30") or 0
        a_prev = q.get("apr30") or 0
        if a_now < APR_ABS_MIN or a_prev <= 0:
            continue
        chg = pct(a_now, a_prev)
        if chg is not None and chg >= APR_JUMP_PCT:
            tvl = p.get("tvl") or 0
            micro = " ⚠️微型池" if tvl < MICRO_TVL else ""
            alerts.append(
                {
                    "type": "apr_jump",
                    "level": "warn" if tvl < MICRO_TVL else "info",
                    "title": f"APR 飙升 · {label(p)}{micro}",
                    "detail": (
                        f"{a_prev:.0f}% → {a_now:.0f}%（{chg:+.0f}%）"
                        f" · TVL {fmt_usd(tvl)}"
                    ),
                    "pool": k,
                    "prev": {"apr30": a_prev, "tvl": q.get("tvl")},
                    "now": {"apr30": a_now, "tvl": tvl},
                }
            )

    # ---- 3. 新进 APR 前 N ----
    def top_ranks(pools, n):
        ranked = sorted(
            [p for p in pools if (p.get("tvl") or 0) >= TVL_ABS_MIN],
            key=lambda x: -(x.get("apr30") or 0),
        )[:n]
        return {key_of(p): i + 1 for i, p in enumerate(ranked)}

    cur_top = top_ranks(cur.get("pools", []), APR_TOP_RANK)
    prev_top = top_ranks(prev.get("pools", []), APR_TOP_RANK)

    # 上一版里所有池子的 APR 名次（不限前 N），用来说明「从第几名上来的」
    def all_ranks(pools):
        ranked = sorted(
            [p for p in pools if (p.get("tvl") or 0) >= TVL_ABS_MIN],
            key=lambda x: -(x.get("apr30") or 0),
        )
        return {key_of(p): i + 1 for i, p in enumerate(ranked)}

    prev_rank_all = all_ranks(prev.get("pools", []))

    for k, rank in cur_top.items():
        if k in prev_top:
            continue
        if k not in prev_pools:
            continue  # 新池已经报过了，别重复
        p = cur_pools[k]
        was = prev_rank_all.get(k)
        move = f"上次第 {was} 名 → " if was else ""
        alerts.append(
            {
                "type": "top_rank",
                "level": "info",
                "title": f"新进 APR 前 {APR_TOP_RANK} · {label(p)}",
                "detail": f"{move}当前第 {rank} 名 · APR30 {p.get('apr30', 0):.0f}%",
                "pool": k,
                "prev": {"rank": was},
                "now": {"rank": rank, "apr30": p.get("apr30")},
            }
        )

    # ---- 4. TVL 异常 ----
    for k, p in cur_pools.items():
        q = prev_pools.get(k)
        if not q:
            continue
        t_now = p.get("tvl") or 0
        t_prev = q.get("tvl") or 0
        if t_prev < TVL_ABS_MIN or t_now < 0:
            continue
        chg = pct(t_now, t_prev)
        if chg is None or abs(chg) < TVL_SWING_PCT:
            continue
        down = chg < 0
        alerts.append(
            {
                "type": "tvl_swing",
                "level": "warn" if down else "info",
                "title": f"TVL {'骤降' if down else '暴涨'} · {label(p)}",
                "detail": f"{fmt_usd(t_prev)} → {fmt_usd(t_now)}（{chg:+.0f}%）",
                "pool": k,
                "prev": {"tvl": t_prev},
                "now": {"tvl": t_now},
            }
        )

    # ---- 5. 量能萎缩 ----
    for k, p in cur_pools.items():
        q = prev_pools.get(k)
        if not q:
            continue
        v7, v30 = p.get("v7") or 0, p.get("v30") or 0
        if v30 <= 0:
            continue
        ratio = v7 / v30
        # 只在「这次才掉下去」时报，避免同一个池子天天报
        q7, q30 = q.get("v7") or 0, q.get("v30") or 0
        prev_ratio = (q7 / q30) if q30 else 1
        if ratio * 100 <= 100 + VOL_DRY_PCT and prev_ratio * 100 > 100 + VOL_DRY_PCT:
            alerts.append(
                {
                    "type": "volume_dry",
                    "level": "warn",
                    "title": f"量能萎缩 · {label(p)}",
                    "detail": (
                        f"7 日均量 / 30 日均量 = {ratio*100:.0f}%"
                        f"（{fmt_usd(v7)} / {fmt_usd(v30)}）"
                    ),
                    "pool": k,
                    "prev": {"ratio": round(prev_ratio * 100, 1)},
                    "now": {"ratio": round(ratio * 100, 1)},
                }
            )

    # ---- 6. 占比恶化（按默认本金） ----
    # 判据：本次超线，且比上次更差（或上次不知情）。这样池子持续悬在线上
    # 但没变坏时不会天天刷屏，一旦继续恶化就会再提醒。
    for k, p in cur_pools.items():
        tvl = p.get("tvl") or 0
        if tvl < 5000:
            continue
        share = CAP_DEFAULT / (tvl + CAP_DEFAULT) * 100
        if share <= SHARE_WARN_PCT:
            continue
        q = prev_pools.get(k)
        t_prev = (q or {}).get("tvl") or 0
        prev_share = (CAP_DEFAULT / (t_prev + CAP_DEFAULT) * 100) if t_prev else 0
        # 上次已经超线、且这次没有更差 → 静默
        if prev_share > SHARE_WARN_PCT and share <= prev_share * 1.02:
            continue
        alerts.append(
            {
                "type": "share_risk",
                "level": "warn",
                "title": f"占比过高 · {label(p)}",
                "detail": (
                    f"按本金 ${CAP_DEFAULT:,.0f} 算，占池子 {share:.1f}%"
                    f"（TVL {fmt_usd(tvl)}）— 你即市场"
                ),
                "pool": k,
                "prev": {"share": round(prev_share, 2)},
                "now": {"share": round(share, 2)},
            }
        )

    # 严重度排序：warn 在前
    order = {"warn": 0, "info": 1}
    alerts.sort(key=lambda a: (order.get(a["level"], 2), a["type"]))
    return alerts


def main():
    cur = load(POOLS_PATH)
    if not cur or not cur.get("pools"):
        print("没有 pools.json，跳过检测")
        return 0

    prev = load(STATE_PATH)
    known = load(KNOWN_PATH)

    # 基线保护：如果本次结果比上一版少了太多池子，说明抓取中途出问题，
    # 不能拿它当新基线，否则下一轮会把一堆「消失的池子」误判成异常，
    # 等抓取恢复了又会把它们全报成「新池上线」。
    cur_n = len(cur.get("pools", []))
    prev_n = len(prev.get("pools", [])) if prev else 0
    if prev_n and cur_n < prev_n * BASELINE_MIN_RATIO:
        print(
            f"本次只有 {cur_n} 个池，上一版 {prev_n} 个，可能抓取不完整；"
            f"保留原基线，本轮不更新 prev_pools.json"
        )
        alerts = detect(cur, prev)   # 仍然对比并报告，但不覆盖基线
    else:
        alerts = detect(cur, prev)

    # ---- 过滤假「新池」 ----
    # 抓取本身有波动：受预算 / 限流影响，某个池子可能这轮没抓到、下轮又出现。
    # 只看「上一轮有没有」会把它误报成新池。所以维护一份「见过的池子」，
    # 只有从未出现过的才算真·新池。
    seen = set((known or {}).get("pools", []))
    filtered = []
    suppressed = 0
    for a in alerts:
        if a["type"] == "new_pool":
            pid = a["pool"]
            if pid in seen:
                suppressed += 1
                continue
            seen.add(pid)
        filtered.append(a)
    if suppressed:
        print(f"（{suppressed} 条「新池上线」是抓取波动导致的误报，已过滤）")
    alerts = filtered

    # 记录所有见过的池子（含本轮所有池，不只是报警过的）
    for p in cur.get("pools", []):
        seen.add(key_of(p))
    with open(KNOWN_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {"updated": cur.get("updated"), "pools": sorted(seen)},
            f,
            ensure_ascii=False,
            indent=1,
        )

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "baseline": bool(prev and prev.get("pools")),
        "prevUpdated": (prev or {}).get("updated"),
        "nowUpdated": cur.get("updated"),
        "n": len(alerts),
        "alerts": alerts,
    }

    with open(ALERTS_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    # 把本次数据存成下一轮的基线（仅在池子数量正常时）
    if not (prev_n and cur_n < prev_n * BASELINE_MIN_RATIO):
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False, indent=1)

    if not payload["baseline"]:
        print("首次运行：已建立基线，本轮不报警")
    else:
        print(f"检测完成：{len(alerts)} 条异动")

    for a in alerts:
        print(f"  [{a['level']}] {a['title']}  —  {a['detail']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
