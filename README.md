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
│   └── data/
│       └── pools.json    抓取结果（由 Actions 每日更新并提交）
└── scripts/
    ├── fetch_pools.py    抓取脚本（Python，仅标准库）
    ├── build.mjs         构建：复制到 dist/
    ├── serve.mjs         本地预览
    └── check-js.mjs      内联 JS 语法检查

boh-site/                 已下线（平台币篮子 BOH），保留源码备查
.github/workflows/
├── update-lp-data.yml    每日抓取 LP 数据
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
