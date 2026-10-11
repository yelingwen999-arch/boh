/* ==========================================================================
   BOH — 全站顶栏
   行情带 + 导航 + 语言 + 显示模式，两个页面共用同一份标记与逻辑，
   避免切换页面时顶栏「跳一下」。
   ========================================================================== */

import { initTheme } from './theme.js';
import { icon } from './icons.js';

const ZERO = '—';

const fmtUsd = v =>
  v == null ? ZERO : '$' + v.toLocaleString('en-US', {
    minimumFractionDigits: v >= 1000 ? 0 : 2,
    maximumFractionDigits: v >= 1000 ? 0 : v >= 10 ? 2 : 4,
  });

const fmtPct = (v, d = 2) =>
  v == null ? ZERO : `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(d)}%`;

const cls = v => (v == null ? 'flat' : v > 0 ? 'up' : v < 0 ? 'down' : 'flat');

/**
 * 初始化顶栏。可重复调用（客户端切页后会再调一次）。
 * @param {string} activePage 'dash' | 'history'，用于标记当前导航项
 */
export async function initChrome(activePage = '') {
  // 主题先定，避免首屏闪白。initTheme 自带防重复绑定。
  initTheme();

  // 标记当前页
  if (activePage) {
    document.querySelectorAll('[data-nav]').forEach(a => {
      a.toggleAttribute('aria-current', a.getAttribute('data-nav') === activePage);
    });
  }

  // 行情带：已填过就只刷新数字，避免滚动位置被重置
  const track = document.getElementById('ticker');
  if (track) {
    try {
      const res = await fetch('./data/market.json');
      const market = await res.json();
      const syms = market.order || [];
      const items = syms.map(sym => {
        const a = market.assets[sym];
        if (!a) return '';
        return `<span class="tk">
          ${icon(sym, 'sm')}
          <span class="tk-code">${sym}</span>
          <span class="tk-price">${fmtUsd(a.price)}</span>
          <span class="${cls(a.change24h)}">${fmtPct(a.change24h)}</span>
        </span>`;
      }).join('');

      const next = items + items;   // 两份，配合 CSS -50% 位移无缝滚动
      if (track.innerHTML !== next) track.innerHTML = next;
    } catch (err) {
      console.error('[BOH] 行情带加载失败', err);
    }
  }
}
