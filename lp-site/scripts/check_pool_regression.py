"""校验这一轮抓到的池子数有没有异常缩水。

为什么需要这道检查（2026-10-20 事故）：
线上数据从 72 个池子掉到 21 个，页面照常打开、看起来正常，
但其实是残缺的。原因是 CI 里的 FETCH_BUDGET_S 给了 1500s（25 分钟），
而完整抓取要 40 分钟以上——预算烧完，脚本按设计停下来，把已经扫到的
一部分池子写进 pools.json，然后照样提交、覆盖掉上一版的完整数据。
它每小时跑一次，所以好数据会被反复覆盖成残缺数据。

check_yield_coverage.py 抓不到这个问题：它看的是「有 APY 的比例」，
21 个池里 14 个有 APY = 67%，远超 20% 的下限。缩水的维度是池子总数。

所以这里单独比「这一版 vs 上一版」的池子数：跌得太狠就让这一轮失败，
保留上一版。宁可数据旧一小时，也不要推一份缺胳膊少腿的上去。
"""

import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.normpath(os.path.join(HERE, "..", "public", "data", "pools.json"))
# git 里的路径（相对仓库根），用于取上一版
REPO_REL = "lp-site/public/data/pools.json"

# 允许的正常波动：三轮轮换会让池子组成变化，但总数不该塌。
# 低于上一版的 70% 就判定为「抓取没跑完」，而不是「市场真的少了这些池」。
MIN_RATIO = 0.70
# 池子本来就很少时不做比例判断（避免 3 -> 2 这种误杀）
MIN_BASE = 10


def count_of(doc):
    pools = (doc or {}).get("pools") or []
    return len(pools)


def previous_count():
    """读上一版（HEAD）的池子数；拿不到就返回 None（不做判断）。"""
    try:
        out = subprocess.run(
            ["git", "show", f"HEAD:{REPO_REL}"],
            cwd=os.path.dirname(os.path.dirname(HERE)),
            capture_output=True,
            check=False,
        )
    except OSError as e:
        print(f"跳过基线对比（git 不可用：{e}）")
        return None

    if out.returncode != 0 or not out.stdout:
        print("跳过基线对比（HEAD 里没有上一版 pools.json）")
        return None

    try:
        return count_of(json.loads(out.stdout.decode("utf-8")))
    except (ValueError, UnicodeDecodeError) as e:
        print(f"跳过基线对比（上一版解析失败：{e}）")
        return None


def main():
    if not os.path.exists(PATH):
        print(f"找不到 {PATH}", file=sys.stderr)
        return 1

    with open(PATH, encoding="utf-8") as f:
        cur_doc = json.load(f)
    cur = count_of(cur_doc)

    if cur == 0:
        print("这一版没有任何池子", file=sys.stderr)
        return 1

    prev = previous_count()
    print(f"池子数：这一版 {cur}" + (f"，上一版 {prev}" if prev is not None else "（无基线）"))

    if prev is None or prev < MIN_BASE:
        print("基线太小或不可用，本轮只记录不拦截")
        return 0

    ratio = cur / prev
    print(f"相对上一版：{ratio*100:.0f}%（下限 {MIN_RATIO*100:.0f}%）")

    if ratio < MIN_RATIO:
        print(
            f"池子数异常缩水（{cur} < 上一版 {prev} 的 {MIN_RATIO*100:.0f}%）。"
            f"抓取大概率在预算内没跑完，或被限流打断。"
            f"保留上一版数据，不提交这一版。",
            file=sys.stderr,
        )
        # 把按链分布打出来，方便判断是不是某条链整体失败了
        by_net = {}
        for p in cur_doc.get("pools") or []:
            net = p.get("net") or "?"
            by_net[net] = by_net.get(net, 0) + 1
        for net in sorted(by_net):
            print(f"  {net:<12} {by_net[net]}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
