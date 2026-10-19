/* 本地预览：node scripts/serve.mjs  ->  http://127.0.0.1:5274
   只服务 dist/，与线上结构一致（含 /data/pools.json）。

   两个防呆设计（都来自实际踩过的坑）：
     1. dist/ 不存在时**自动构建**，而不是报错退出
     2. 每个请求都检查 dist/index.html 是否比源文件旧，旧了就自动重建
        —— 改完前端忘了 build 是这个项目最常犯的错 */
import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { resolve, dirname, extname, normalize, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const dist = resolve(root, 'dist');
const port = Number(process.env.PORT || 5274);

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
};

// 源文件：任何一个比 dist 新，就说明需要重建
const SOURCES = ['index.html', 'about.html'];

function build() {
  console.log('[serve] 构建 dist/ ...');
  execFileSync(process.execPath, [resolve(root, 'scripts', 'build.mjs')], {
    cwd: root,
    stdio: 'inherit',
  });
}

let lastBuild = 0;

/** dist 缺失或比源文件旧时重建，最多每 2 秒一次 */
async function ensureFresh() {
  const idx = join(dist, 'index.html');
  if (!existsSync(idx)) {
    if (Date.now() - lastBuild > 2000) { lastBuild = Date.now(); build(); }
    return;
  }
  const distTime = (await stat(idx)).mtimeMs;
  for (const s of SOURCES) {
    const src = join(root, s);
    if (!existsSync(src)) continue;
    const srcTime = (await stat(src)).mtimeMs;
    if (srcTime > distTime) {
      if (Date.now() - lastBuild > 2000) {
        lastBuild = Date.now();
        console.log(`[serve] ${s} 比 dist 新，自动重建`);
        build();
      }
      return;
    }
  }
}

// 启动时先确保 dist 可用
if (!existsSync(join(dist, 'index.html'))) build();

createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  let p = normalize(decodeURIComponent(url.pathname)).replace(/^([/\\])+/, '');
  if (p === '' || p === '.') p = 'index.html';

  // 页面/数据请求前先确认构建产物是最新的
  await ensureFresh();

  const file = resolve(dist, p);

  // 目录穿越防护
  if (!file.startsWith(dist)) {
    res.writeHead(403).end('forbidden');
    return;
  }

  try {
    const body = await readFile(file);
    res.writeHead(200, {
      'content-type': TYPES[extname(file)] || 'application/octet-stream',
      'cache-control': 'no-store',
    });
    res.end(body);
  } catch {
    res.writeHead(404, { 'content-type': 'text/plain; charset=utf-8' });
    res.end('404 ' + p);
  }
}).listen(port, '127.0.0.1', () => {
  console.log(`LP dashboard (static) -> http://127.0.0.1:${port}`);
});
