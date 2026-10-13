/* BOH — 平台史页入口。挂载由 router 调用（直接打开与客户端切页都走 renderPage）。 */

import { initChrome } from './chrome.js';
import { initRouter } from './router.js';

/** 挂载平台史页：顶栏（行情带 + 主题），正文本身是静态 HTML */
export async function renderPage() {
  await initChrome('history');
}

initRouter().catch(err => console.error('[BOH] 平台史页初始化失败', err));
