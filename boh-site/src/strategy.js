/* BOH — 策略页入口：顶栏 + 路由 + 策略渲染 */

import { initChrome } from './chrome.js';
import { initRouter, currentPage } from './router.js';
import { renderStrategy } from './render-strategy.js';

initRouter();
initChrome(currentPage());

fetch('./data/backtest-result.json')
  .then(r => r.json())
  .then(renderStrategy)
  .catch(err => console.error('[BOH] 策略数据加载失败', err));
