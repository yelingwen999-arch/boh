/* ==========================================================================
   BOH — 全站顶栏
   行情带 + 导航 + 语言 + 显示模式，各页共用同一份标记与逻辑，
   避免切换页面时顶栏「跳一下」。

   行情带的价格由 live-quote 提供：先渲染静态快照，随后被实时价覆盖。
   ========================================================================== */

import { initTheme } from './theme.js';
import { icon } from './icons.js';
import { live } from './live-quote.js';

const ZERO = '—';

const fmtUsd = v =>
  v == null ? ZERO : '$' + v.toLocaleString('en-US', {
    minimumFractionDigits: v >= 1000 ? 0 : 2,
    maximumFractionDigits: v >= 1000 ? 0 : v >= 10 ? 2 : 4,
  });

const fmtPct = (v, d = 2) =>
  v == null ? ZERO : `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(d)}%`;

const cls = v => (v == null ? 'flat' : v > 0 ? 'up' : v < 0 ? 'down' : 'flat');

let trackEl = null;
let bound = false;

/** 渲染行情带（两份，配合 CSS -50% 位移无缝滚动） */
function renderTicker() {
  if (!trackEl) return;
  const items = live.order.map(sym => {
    const q = live.quote[sym];
    if (!q) return '';
    return `<span class="tk">
      ${icon(sym, 'sm')}
      <span class="tk-code">${sym}</span>
      <span class="tk-price">${fmtUsd(q.price)}</span>
      <span class="${cls(q.change24h)}">${fmtPct(q.change24h)}</span>
    </span>`;
  }).join('');
  const next = items + items;
  if (trackEl.innerHTML !== next) trackEl.innerHTML = next;
}

/**
 * 初始化顶栏。可重复调用（客户端切页后会再调一次）。
 * @param {string} activePage 'dash' | 'strategy' | 'history'，用于标记当前导航项
 */
export async function initChrome(activePage = '') {
  initTheme();

  if (activePage) {
    document.querySelectorAll('[data-nav]').forEach(a => {
      a.toggleAttribute('aria-current', a.getAttribute('data-nav') === activePage);
    });
  }

  trackEl = document.getElementById('ticker');
  if (!trackEl) return;

  if (!bound) {
    bound = true;
    live.subscribe(renderTicker);   // 快照到位、实时价到位都会触发
  }

  await live.load();                // 先渲染快照，首屏不空
  await live.start();               // 再取实时价并启动定时刷新
}
