# chasebig.xyz

美股代币（tokenized equity）流动性看板。

**线上：<https://chasebig.xyz>**

> Cloudflare Pages 自动部署。推送到 `main` 后约 1 分钟重新构建上线。
> Pages 默认地址：<https://boh-aml.pages.dev>

---

## 这是什么

一张只做信息汇总的看板，扫描 Solana、BNB Chain、Base、Robinhood Chain 四条链上
**美股代币 / 稳定币**构成的流动性池，展示 TVL、24h 成交量、费率、APR 与几项客观预警。

**不做的事**：不代客理财、不托管资产、不发行产品、不给收益承诺、不构成投资建议。
口径与免责声明见站内 `/about.html`。

---

## 目录结构

```
lp-site/                  主站（美股代币 LP 看板）
├── index.html            看板首页
├── about.html            口径与声明
├── package.json
├── public/
│   ├── _redirects        Cloudflare Pages 重定向规则
│   ├── favicon.svg
│   └── data/
│       ├── pools.json        当前快照（前端读）
│       ├── prev_pools.json   上一版快照（异动对比基线）
│       └── alerts.json       本轮异动（前端读）
└── scripts/
    ├── fetch_pools.py    抓取脚本（Python，仅标准库）
    ├── detect.py         异动检测：对比两版快照产出 alerts.json
    ├── notify.py         推送：Telegram / 邮件（未配置则静默跳过）
    ├── build.mjs         构建：复制到 dist/
    ├── serve.mjs         本地预览
    └── check-js.mjs      内联 JS 语法检查

boh-site/                 已下线（平台币篮子 BOH），保留源码备查
.github/workflows/
├── update-lp-data.yml    LP 看板监控：每小时抓取 → 检测 → 推送
└── update-data.yml       BOH 的数据任务（已停用，见下）
```

---

## Cloudflare Pages 配置

| 配置 | 值 |
|---|---|
| Root directory | `lp-site` |
| Build command | `node scripts/build.mjs` |
| Build output directory | `dist` |
| 生产分支 | `main` |

站点是纯静态的：没有服务端进程，没有常驻后台线程。数据由 Actions 抓取后
写成 `public/data/pools.json`，跟着代码一起部署。

---

## 更新数据

```bash
cd lp-site/scripts
python fetch_pools.py
```

数据写入 `lp-site/public/data/pools.json`，提交后自动部署。

抓取脚本的两个关键行为：

- **总预算**（默认 1500 秒，可用 `FETCH_BUDGET_S` 覆盖）到期就带着已有结果退出，
  不会让 GitHub Actions 打到 30 分钟超时、把整轮结果丢掉。
- **结果少于 5 个池**时视为本轮失败，**保留上一版 `pools.json` 不覆盖**，
  线上不会因为一次抓取异常变成空看板。

GeckoTerminal 免费额度对 onchain 端点限得很紧（30 req/min），脚本在请求之间
限速 2.2 秒，遇到 429 会等待后重试。

---

## 持续监控与异动警报

`update-lp-data.yml` 每小时跑一次：**抓取 → 对比上一版 → 有异动就推送**。

### 盯什么

`detect.py` 对比本次和上一版 `pools.json`，以下情况会产生警报：

| 类型 | 触发条件 | 阈值 |
|---|---|---|
| `apr_jump` | APR 相对上一版上涨 | ≥ 60%，且当前 APR ≥ 30% |
| `new_pool` | 出现上一版没有的池子 | TVL ≥ $20K |
| `top_rank` | 新进 APR 前 5 名 | — |
| `tvl_swing` | TVL 涨跌 | ≥ 35%，且上次 TVL ≥ $20K |
| `volume_dry` | 7 日均量 / 30 日均量跌破 60%（只在「这次才跌破」时报） | — |
| `share_risk` | 按 $10K 本金算占比 > 5%（只在恶化时报） | — |

阈值都在 `detect.py` 顶部常量里，要调直接改。

**设计取舍**：宁可少报，不要天天刷屏。刷屏的警报三天后就会被静音，
然后真正的警报也收不到。所以多数规则只在「状态刚发生变化」时触发一次。

### 推送配置（可跳过，不影响数据更新）

不配也能用——异动会写进 `alerts.json`，看板顶部会出现「本轮异动」。
想收到主动推送，去仓库 **Settings → Secrets and variables → Actions** 加：

**Telegram**（推荐，最快最省事）

| Secret | 值 |
|---|---|
| `TELEGRAM_BOT_TOKEN` | 找 @BotFather 创建 bot 后拿到的 token |
| `TELEGRAM_CHAT_ID` | 给 bot 发条消息，然后访问 `https://api.telegram.org/bot<TOKEN>/getUpdates` 里的 `chat.id` |

**邮件**（可选）

| Secret | 值 |
|---|---|
| `SMTP_HOST` | 如 `smtp.qq.com` |
| `SMTP_PORT` | `465`（SSL）或 `587`（STARTTLS） |
| `SMTP_USER` | 发件邮箱 |
| `SMTP_PASS` | 邮箱**授权码**，不是登录密码 |
| `MAIL_TO` | 收件邮箱 |

配置完验证：Actions → 「LP 看板监控」→ Run workflow →
勾上 **`notify_test`** 只发一条测试消息，不跑抓取。

```bash
# 本地也能自测
cd lp-site/scripts
python notify.py --test        # 发测试消息
python detect.py               # 跑一次检测，看输出
```

### 数据文件

| 文件 | 用途 |
|---|---|
| `public/data/pools.json` | 当前快照，前端读这个 |
| `public/data/prev_pools.json` | 上一版快照，`detect.py` 用来对比 |
| `public/data/alerts.json` | 本轮异动，前端读这个 |

三个文件都会被提交，所以历史和基线都在 git 里，可回溯。

---

## 本地预览

```bash
cd lp-site
node scripts/build.mjs
node scripts/serve.mjs        # http://127.0.0.1:5274
```

改完 JS 记得跑一次语法检查——`index.html` / `about.html` 的脚本是内联的，
一个引号错位就会整页白屏，而普通阅读看不出来：

```bash
node scripts/check-js.mjs
```

---

## 关于 boh-site

`boh-site/` 是此前的「BOH 平台币篮子」站点，**已下线**。
`/dash`、`/strategy`、`/history` 现在统一 302 到看板首页（见 `lp-site/public/_redirects`）。

源码保留在这个仓库里，方便以后查阅或复用；`update-data.yml` 也留着但不再参与部署
——它只写 `boh-site/public/data/`，不影响线上站点。
