# 本地看板维护速查

## 打开看板

```bash
cd E:\平台币计划\lp-site
node scripts/build.mjs      # 生成 dist/（预览服务只服务这个目录）
node scripts/serve.mjs      # http://127.0.0.1:5274
```

**改完任何前端文件都要重新 build**，否则页面 404。
预览服务启动时会检查 `dist/`，不存在会直接报错退出。

## 改完代码的检查顺序

```bash
node scripts/check-js.mjs   # 内联 JS 语法（引号错位会整页白屏，肉眼看不出来）
node scripts/build.mjs      # 构建
```

## 更新数据

```bash
cd scripts
python fetch_pools.py           # 抓取（约 15-25 分钟，有 25 分钟总预算）
python check_yield_coverage.py  # 校验官方收益率覆盖率
python detect.py                # 异动检测，写 alerts.json
```

## 收益率口径（重要）

**APY 来自 DefiLlama，不是自己算的。**

早期版本用 `成交量 × 费率 ÷ TVL` 推算 APR。实测和 DApp 官方页面的数字
差 **0.02 倍到 11 倍，且没有规律**——根本不能用。原因不止一个：费率里有多少
真正分给 LP、流动性集中在多窄的价格区间、成交量归属哪一档，公开数据还原不了。

现在 `yield_source.py` 按「链 + 两个代币的合约地址」去 DefiLlama 匹配：

- `apyBase` → 手续费收益
- `apyReward` → 激励收益（AERO / CAKE 等代币奖励）
- `apy` → 两者合计，就是 DApp 上显示的那个数

数据字段：`apr`（总）/ `apr_base`（手续费）/ `apr_reward`（激励）/ `apr_src`。
`apr_calc` 是旧算法的结果，**只作对照，不要拿来显示**。

匹配不上时 `apr` 为 `null`，页面显示「官方未收录」，**不会填一个猜的数字**。

覆盖率参考（2026-10 实测）：Base 92%、Solana 95%、BSC 15%、Robinhood 0%。
BSC 的 PancakeSwap v3 和 Robinhood 的 Uniswap 池 DefiLlama 收录得很少，
这是数据源的覆盖问题，不是匹配逻辑的问题。

## 常见问题

**页面打不开 / 404**
`dist/` 不存在。跑 `node scripts/build.mjs`。

**改了代码但页面没变**
`dist/` 是旧的。重新 build，然后强制刷新（Ctrl+F5）。

**抓取结果很少**
GeckoTerminal 限流。脚本会自动退避（429 不消耗重试次数），
结果少于 5 个池时不会覆盖线上数据。

**看到「⚠ 有 N 个 ticker 请求失败」**
这一轮的数据会缺掉那些 ticker 的所有池子（可能是整条链的池子都没进来）。
等几分钟重跑即可，**不要**把这一版当作完整数据。

**某条链一个池都没有**
先看上面那条告警。如果扫描很干净但某条链仍然为空，
检查 `scan_stock_pools()` 里 `CHAINS` 是否包含它，以及该链的池是否都被
`qkind` / 计价资产判定过滤掉了。

---

## 多链与标的口径

同一个股票在四条链上的代币符号不同：

| 链 | 符号 | 例子 |
|---|---|---|
| BNB Chain | 加 `B` | `SKHYB` |
| Base | 加 `c` | `SKHYc` |
| Solana | 加 `x` | `SKHYx` |
| Robinhood | 无后缀 | `SKHY` |

`canonical_ticker()` 会把它们归到同一个 ticker（`SKHY`），
前端就能把同一股票的多个链上池子聚在一起。
原始符号保留在 `token` 字段里，用于显示。

计价资产分两类：`qkind=stable`（USDT/USDC/USDG）和
`qkind=native`（WBNB/SOL/WETH）。原生币池会标「原生币」，
因为做市时你同时承担原生币涨跌，风险和稳定币池不同。

---

## 注意

- `dist/` 和 `__pycache__/` 都在 `.gitignore` 里，**不要删 dist 后再推代码** ——
  推代码不需要删它，删了本地就看不到页面了。
- 提交前只清理 `__pycache__`，`dist/` 留着。
- **抓取很慢**：72 个池约 15–25 分钟。`GT_GAP` 别调小，
  实测 2.2 秒会频繁 429 并静默丢数据。
