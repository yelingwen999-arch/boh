/* ==========================================================================
   BOH — 平台币历史对比图
   以 BNB 的历史周线为骨架（2017-09 至今），在同一张图上叠加 OKB 与 HYPE。
   每个平台币从各自首周归一到 100；BTC 从 BNB 首周归一。
   ========================================================================== */

import { icon } from './icons.js';

const NS = 'http://www.w3.org/2000/svg';const svgEl = (n, a = {}) => {
  const node = document.createElementNS(NS, n);
  for (const k in a) node.setAttribute(k, a[k]);
  return node;
};

const fmtDate = ts => {
  const d = new Date(ts * 1000);
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`;
};
const fmtYM = ts => {
  const d = new Date(ts * 1000);
  return `${d.getUTCFullYear()}/${String(d.getUTCMonth() + 1).padStart(2, '0')}`;
};
const fmtPct = (v, d = 1) =>
  v == null ? '—' : `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(d)}%`;
const fmtTimes = v => (v == null ? '—' : Math.round(v).toLocaleString('en-US') + ' 倍');

const SERIES_STYLE = {
  BNB: { cls: 'pl-bnb', color: '#5b9bd5' },
  OKB: { cls: 'pl-okb', color: '#e8913a' },
  HYPE: { cls: 'pl-hype', color: '#3fbf87' },
  BTC: { cls: 'pl-btc', color: '#8f8a80' },
};

export function renderPlatformHistory(cfg) {
  const svg = document.getElementById('pl-chart');
  if (!svg || !cfg) return;

  const W = svg.clientWidth || 1000;
  const H = svg.clientHeight || 380;
  const M = { t: 24, r: 78, b: 28, l: 64 };
  const PW = W - M.l - M.r;
  const PH = H - M.t - M.b;
  const dates = cfg.dates;
  const n = dates.length;

  // 起点对齐：四条线全部以"共同起点"为 100，便于直接比较。
  // 各币完整的生命周期倍数放在下面的表格里，图这里只管"同一起跑线之后谁领先"。
  const anchor = 'HYPE';                 // 三者中上市最晚的，作为共同起点
  const iAnchor = cfg.startIdx[anchor];
  const ANCHOR_LABEL = `共同起点 ${fmtYM(dates[iAnchor])} = 100`;

  const series = {};
  for (const s of ['BNB', 'OKB', 'HYPE', 'BTC']) {
    const raw = cfg.raw[s];
    const base = raw[iAnchor];
    series[s] = (base && base > 0)
      ? raw.map(v => (v == null || v <= 0) ? null : (v / base) * 100)
      : raw.map(() => null);
  }

  const all = [];
  for (const s in series) for (const v of series[s]) if (v != null && v > 0) all.push(v);

  let lo = Math.log10(Math.max(Math.min(...all), 1e-9));
  let hi = Math.log10(Math.max(...all));
  const pad = (hi - lo || 1) * 0.06;
  lo -= pad; hi += pad;

  const X = i => M.l + (i / (n - 1)) * PW;
  const Y = v => M.t + PH - ((Math.log10(Math.max(v, 1e-9)) - lo) / (hi - lo)) * PH;

  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  while (svg.firstChild) svg.removeChild(svg.firstChild);

  for (let m = Math.floor(lo); m <= Math.ceil(hi); m++) {
    const v = 10 ** m;
    const yy = Y(v);
    if (yy < M.t - 1 || yy > M.t + PH + 1) continue;
    svg.appendChild(svgEl('line', { class: 'grid', x1: M.l, x2: M.l + PW, y1: yy, y2: yy }));
    const lb = svgEl('text', { class: 'axis', x: M.l - 8, y: yy + 4, 'text-anchor': 'end' });
    lb.textContent = cfg.raw[anchor] && v >= 1e6 ? `${v / 1e6}m` : v >= 1e3 ? `${v / 1e3}k` : `${v}`;
    svg.appendChild(lb);
  }

  if (lo < 0 && hi > 0) {
    svg.appendChild(svgEl('line', { class: 'base100', x1: M.l, x2: M.l + PW, y1: Y(100), y2: Y(100) }));
    const tb = svgEl('text', { class: 'axis', x: M.l + PW + 6, y: Y(100) + 4, 'text-anchor': 'start' });
    tb.textContent = ANCHOR_LABEL;
    svg.appendChild(tb);
  }

  const toPath = arr => {
    let d = '', started = false;
    arr.forEach((v, i) => {
      if (v == null) return;
      d += `${started ? 'L' : 'M'}${X(i).toFixed(1)} ${Y(v).toFixed(1)}`;
      started = true;
    });
    return d;
  };
  for (const s of ['BTC', 'BNB', 'OKB', 'HYPE']) {
    svg.appendChild(svgEl('path', { class: SERIES_STYLE[s].cls, d: toPath(series[s]) }));
  }

  // 终点：标注倍数（相对共同起点）
  for (const s of ['BNB', 'OKB', 'HYPE', 'BTC']) {
    const arr = series[s];
    let lastIdx = -1;
    for (let i = arr.length - 1; i >= 0; i--) { if (arr[i] != null) { lastIdx = i; break; } }
    if (lastIdx < 0) continue;
    const mult = arr[lastIdx] / 100;
    const t = svgEl('text', {
      class: 'axis', x: X(lastIdx) + 7, y: Y(arr[lastIdx]) + 4,
      'text-anchor': 'start', fill: SERIES_STYLE[s].color, 'font-weight': '600',
    });
    t.textContent = `${s} ${mult >= 10 ? mult.toFixed(0) : mult.toFixed(2)}×`;
    svg.appendChild(t);
  }

  const picks = [0, Math.floor(n / 3), Math.floor((2 * n) / 3), n - 1];
  picks.forEach((i, k) => {
    const t = svgEl('text', {
      class: 'axis', x: X(i), y: M.t + PH + 18,
      'text-anchor': k === 0 ? 'start' : k === picks.length - 1 ? 'end' : 'middle',
    });
    t.textContent = fmtYM(dates[i]);
    svg.appendChild(t);
  });

  // 图例：官方图标 + 名称
  const lg = document.getElementById('pl-legend');
  if (lg) {
    lg.innerHTML = ['BNB', 'OKB', 'HYPE', 'BTC'].map(s =>
      `<span class="lg-item"><i class="lg-line" style="background:${SERIES_STYLE[s].color}"></i>${icon(s, 'sm')}${s}</span>`
    ).join('');
  }

  // 数据表：每个平台币自诞生起 vs BTC（全宽，与上面的图同宽）
  const el = document.getElementById('pl-facts');
  if (el && cfg.windows) {
    const rows = ['BNB', 'OKB', 'HYPE'].map(s => {
      const w = cfg.windows[s];
      if (!w) return '';
      const tMult = 1 + w.tokenChange / 100;
      const bMult = 1 + w.btcChange / 100;
      return `
        <tr>
          <td>
            <span class="pl-name">
              ${icon(s)}
              <span class="tok-code">${s}</span>
            </span>
            <span class="cell-sub">自 ${fmtDate(w.from)}</span>
          </td>
          <td class="n"><span class="cell-num up">${fmtTimes(tMult)}</span></td>
          <td class="n"><span class="cell-num">${fmtTimes(bMult)}</span></td>
          <td class="n"><span class="cell-num up">${fmtPct(w.excess, 0)}</span></td>
        </tr>`;
    }).join('');

    el.innerHTML = `
      <table class="grid-table pl-table">
        <caption class="sr-only">每个平台币自上市以来与 BTC 的对比</caption>
        <thead>
          <tr>
            <th scope="col">平台币</th>
            <th scope="col" class="n">自上市至今</th>
            <th scope="col" class="n">BTC 同期</th>
            <th scope="col" class="n">领先</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    `;
  }
}
