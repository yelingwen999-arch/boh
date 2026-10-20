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

/**
 * dist 缺失或比源文件旧时重建，最多每 2 秒一次。
 *
 * 注意：必须拿「同名产物」比，不能拿 dist/index.html 的时间去比所有源文件。
 * 早先的写法把所有源文件的 mtime 和 dist/index.html 比，只要 about.html 比
 * dist/index.html 新（很常见：改完 index 再改 about），条件就永远成立，
 * 于是每个请求都触发一次重建，日志里刷满「about.html 比 dist 新」。
 * 重建又会刷新 dist 的 mtime，看起来像在自愈，实际是死循环。
 */
async function ensureFresh() {
  if (!existsSync(join(dist, 'index.html'))) {
    if (Date.now() - lastBuild > 2000) { lastBuild = Date.now(); build(); }
    return;
  }
  for (const s of SOURCES) {
    const src = join(root, s);
    const out = join(dist, s);
    if (!existsSync(src)) continue;
    // 产物不存在，或源比它对应的产物新 → 需要重建
    if (!existsSync(out)) {
      if (Date.now() - lastBuild > 2000) {
        lastBuild = Date.now();
        console.log(`[serve] dist/${s} 缺失，自动重建`);
        build();
      }
      return;
    }
    const srcTime = (await stat(src)).mtimeMs;
    const outTime = (await stat(out)).mtimeMs;
    if (srcTime > outTime) {
      if (Date.now() - lastBuild > 2000) {
        lastBuild = Date.now();
        console.log(`[serve] ${s} 比 dist/${s} 新，自动重建`);
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
