"""校验这一轮的官方收益率覆盖率。

为什么需要这道检查：
收益率全部来自 DefiLlama。如果它挂了、限流了、或者匹配逻辑改坏了，
抓取脚本不会报错——它只是把每个池的 apr 都写成 None，页面会整片
显示「官方未收录」。那种输出推上线比没有数据更糟：看板看起来正常，
但没有任何收益信息。

所以：覆盖率低于阈值就让这一轮失败，保留上一版数据。
"""

import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.normpath(os.path.join(HERE, "..", "public", "data", "pools.json"))

# 实测覆盖率约 47%（72 个池里 34 个有官方数据）。
# 取 20% 作为下限：明显低于这个说明整条数据链路出了问题，
# 而不是「今天恰好没有新池被收录」。
MIN_RATIO = 0.20
MIN_ABS = 5


def main():
    if not os.path.exists(PATH):
        print(f"找不到 {PATH}", file=sys.stderr)
        return 1

    with open(PATH, encoding="utf-8") as f:
        d = json.load(f)

    pools = d.get("pools") or []
    total = len(pools)
    covered = sum(1 for p in pools if p.get("apr") is not None)

    if total == 0:
        print("数据里没有池子", file=sys.stderr)
        return 1

    ratio = covered / total
    print(f"官方收益率覆盖：{covered}/{total}（{ratio*100:.0f}%）")

    # 顺便报一下按链的分布，出问题时好定位
    by_net = {}
    for p in pools:
        net = p.get("net") or "?"
        t = by_net.setdefault(net, [0, 0])
        t[1] += 1
        if p.get("apr") is not None:
            t[0] += 1
    for net in sorted(by_net):
        ok, n = by_net[net]
        print(f"  {net:<12} {ok}/{n}")

    need = max(MIN_ABS, int(total * MIN_RATIO))
    if covered < need:
        print(
            f"覆盖率过低（{covered} < {need}），疑似 DefiLlama 不可用或匹配逻辑出错。"
            f"保留上一版数据。",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
