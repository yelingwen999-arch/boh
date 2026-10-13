/* BOH — 策略页入口。挂载由 router 调用（直接打开与客户端切页都走 renderPage）。 */

import { initChrome } from './chrome.js';
import { initRouter } from './router.js';
import { renderStrategy } from './render-strategy.js';

let CFG = null;

/** 挂载策略页：顶栏 + 回测数据（取一次）+ 渲染 */
export async function renderPage() {
  await initChrome('strategy');
  if (!CFG) {
    CFG = await fetch('./data/backtest-result.json').then(r => r.json());
  }
  renderStrategy(CFG);
}

initRouter().catch(err => console.error('[BOH] 策略页初始化失败', err));
