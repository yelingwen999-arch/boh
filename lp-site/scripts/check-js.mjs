/* 提取 <script> 内联代码并做语法检查。

   教训：index.html 曾出现一处引号不匹配（单引号开、反引号闭），read 工具
   显示正常，只有 node --check 能抓到。改完 JS 一定要跑这个。

   用法：node scripts/check-js.mjs
*/
import { readFileSync, writeFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { tmpdir } from 'node:os';

const here = dirname(fileURLToPath(import.meta.url));
const files = ['index.html', 'about.html'];
let bad = 0;

for (const f of files) {
  const html = readFileSync(resolve(here, '..', f), 'utf8');
  const blocks = [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/gi)];
  if (!blocks.length) {
    console.log(f + ': 无内联 script');
    continue;
  }
  blocks.forEach((m, i) => {
    const before = html.slice(0, m.index);
    const lineNo = before.split('\n').length;
    const tmp = resolve(tmpdir(), 'chk_' + f.replace('.', '_') + '_' + i + '.mjs');
    writeFileSync(tmp, m[1], 'utf8');
    try {
      execFileSync(process.execPath, ['--check', tmp], { stdio: 'pipe' });
      console.log(f + ' [script ' + i + '] 语法 OK  (起始行 ' + lineNo + ')');
    } catch (e) {
      bad++;
      console.error(f + ' [script ' + i + '] 语法错误 (起始行 ' + lineNo + '):');
      console.error(String(e.stderr || e.message));
    }
  });
}

process.exit(bad ? 1 : 0);