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
python fetch_pools.py       # 抓取（约 6-15 分钟，有 25 分钟总预算）
python detect.py            # 异动检测，写 alerts.json
```

## 常见问题

**页面打不开 / 404**
`dist/` 不存在。跑 `node scripts/build.mjs`。

**改了代码但页面没变**
`dist/` 是旧的。重新 build，然后强制刷新（Ctrl+F5）。

**抓取结果很少**
GeckoTerminal 限流。脚本会自动退避，结果少于 5 个池时不会覆盖线上数据。

---

## 注意

- `dist/` 和 `__pycache__/` 都在 `.gitignore` 里，**不要删 dist 后再推代码** ——
  推代码不需要删它，删了本地就看不到页面了。
- 提交前只清理 `__pycache__`，`dist/` 留着。
