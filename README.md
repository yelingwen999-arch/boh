# BOH — 平台币篮子

以 BTC 为基准度量的平台币篮子。装的是 **BNB、OKB、HYPE** 三种平台类代币，等权持有。

**线上地址：<https://chasebig.xyz>**

> 由 Cloudflare Pages 自动部署，绑定 `chasebig.xyz`。
> 推送到 `main` 分支后会自动重新构建上线（约 1 分钟）。

---

## 目录结构

```
boh-site/                 网站源码
├── dash.html             总览页
├── history.html          平台史页
├── src/                  样式与脚本
│   ├── dash-v3.css       全站样式（唯一入口，@import ref.css）
│   ├── ref.css           基础样式与主题变量
│   ├── chrome.js         共用顶栏（行情带 + 导航 + 日夜切换）
│   ├── router.js         两页之间的无刷新切换
│   ├── theme.js          日夜主题
│   ├── icons.js          币种图标
│   ├── chart-shared.js   图表共用逻辑
│   ├── render-logic.js   周期时间轴
│   └── render-platform-history.js   平台币 vs BTC
├── public/
│   ├── _redirects        根目录代理到 /dash.html（状态码 200）
│   ├── data/             数据文件（构建时原样复制）
│   └── icons/            币种官方图标
└── scripts/              数据抓取脚本（Python）

BOH-框架.md               产品定义、投资论证、已定规则
meme币合规调研.md          合规调研
```

## 本地开发

```bash
cd boh-site
pnpm install
pnpm dev          # 开发服务器 http://127.0.0.1:5273
pnpm build        # 构建到 dist/
pnpm preview      # 预览构建产物
```

## 更新数据

```bash
cd boh-site/scripts
python fetch_data.py               # 行情与平台数据
python fetch_cycle.py              # BTC 全历史周线
python fetch_platform_history.py   # 三个平台币全历史
python fetch_market.py             # 行情带八个币
```

数据写入 `boh-site/public/data/`，提交后自动部署。

## 部署

Cloudflare Pages，连接本仓库：

| 配置 | 值 |
|---|---|
| Root directory | `boh-site` |
| Build command | `pnpm build` |
| Build output directory | `dist` |

生产分支：`main`。推送即自动上线。

| | |
|---|---|
| 线上地址 | https://chasebig.xyz |
| Pages 默认地址 | https://boh-aml.pages.dev |
| 仓库 | https://github.com/yelingwen999-arch/boh |
