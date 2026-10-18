/* 构建：把静态文件复制到 dist/。
   Cloudflare Pages 的 Build command 跑 `node scripts/build.mjs`，
   输出目录 dist。这里不压缩、不打包 —— 两个 HTML 页面直接就是成品。 */
import { cp, rm, mkdir } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const dist = resolve(root, 'dist');

await rm(dist, { recursive: true, force: true });
await mkdir(dist, { recursive: true });

const files = ['index.html', 'about.html'];
for (const f of files) {
  const src = resolve(root, f);
  if (!existsSync(src)) throw new Error(`缺少页面文件：${f}`);
  await cp(src, resolve(dist, f));
}

const publicDir = resolve(root, 'public');
if (existsSync(publicDir)) {
  await cp(publicDir, dist, { recursive: true });
}

// 数据文件必须存在，否则线上会是一个空看板
if (!existsSync(resolve(dist, 'data', 'pools.json'))) {
  throw new Error('缺少 public/data/pools.json —— 请先运行 scripts/fetch_pools.py');
}

console.log('build ok ->', dist);
