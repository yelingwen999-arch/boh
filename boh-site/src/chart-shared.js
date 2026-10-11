/* ==========================================================================
   BOH — 走势图（篮子 / BTC / 篮子对 BTC）
   首屏的迷你图和下方的大图共用这套逻辑，避免两份代码漂移。
   ========================================================================== */

const NS = 'http://www.w3.org/2000/svg';
const svgEl = (n, a = {}) => {
  const node = document.createElementNS(NS, n);
  for (const k in a) node.setAttribute(k, a[k]);
  return node;
};

export const LINE_COLOR = {
  basket: '#4aa8d8',
  btc: '#a8a29a',
  vs: '#d98a3d',
};

const fmtDate = ts => {
  const d = new Date(ts * 1000);
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`;
};

/** 从整段 chart 数据里截取指定天数，并归一到起点 100 */
export function sliceSeries(chart, days) {
  const c = chart;
  const n = c.dates.length;
  const from = Math.max(0, n - 1 - days);
  const rebase = arr => {
    const base = arr[from];
    return arr.slice(from).map(v => (v / base) * 100);
  };
  return {
    dates: c.dates.slice(from),
    basket: rebase(c.basket),
    btc: rebase(c.btc),
    vs: c.vsBtc.slice(from).map(v => (v / c.vsBtc[from]) * 100),
  };
}

/**
 * 画图。
 * opts.showVs   是否画「篮子 / BTC」那条线
 * opts.showXAxis 是否画横轴日期
 */
export function draw(
  svg,
  s,
  {
    showVs = true,
    showXAxis = true,
    onHover = null,
    endColors = null,
  } = {}
) {
  const W = svg.clientWidth || 1000;
  const H = svg.clientHeight || 300;
  const M = { t: 16, r: showXAxis ? 56 : 48, b: showXAxis ? 26 : 8, l: 48 };
  const PW = W - M.l - M.r;
  const PH = H - M.t - M.b;
  const n = s.dates.length;

  const all = [...s.basket, ...s.btc, ...(showVs ? s.vs : [])];
  let lo = Math.min(...all, 98);
  let hi = Math.max(...all, 102);
  const pad = (hi - lo || 1) * 0.09;
  lo -= pad; hi += pad;

  const X = i => M.l + (n === 1 ? PW / 2 : (i / (n - 1)) * PW);
  const Y = v => M.t + PH - ((v - lo) / (hi - lo)) * PH;

  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  while (svg.firstChild) svg.removeChild(svg.firstChild);

  // 横网格 + 纵轴
  for (let t = 0; t <= 4; t++) {
    const v = lo + ((hi - lo) * t) / 4;
    const yy = Y(v);
    svg.appendChild(svgEl('line', { class: 'grid', x1: M.l, x2: M.l + PW, y1: yy, y2: yy }));
    const lb = svgEl('text', { class: 'axis', x: M.l - 8, y: yy + 4, 'text-anchor': 'end' });
    lb.textContent = v.toFixed(0);
    svg.appendChild(lb);
  }

  // 100 基准线
  if (lo < 100 && hi > 100) {
    svg.appendChild(svgEl('line', { class: 'base100', x1: M.l, x2: M.l + PW, y1: Y(100), y2: Y(100) }));
  }

  const toPath = arr => arr.map((v, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)} ${Y(v).toFixed(1)}`).join(' ');

  if (showVs) svg.appendChild(svgEl('path', { class: 'line-vs-ref', d: toPath(s.vs) }));
  svg.appendChild(svgEl('path', { class: 'line-btc-ref', d: toPath(s.btc) }));
  svg.appendChild(svgEl('path', { class: 'line-basket-main', d: toPath(s.basket) }));

  // 终点标签
  const colors = endColors || { basket: LINE_COLOR.basket, btc: LINE_COLOR.btc };
  const lt = svgEl('text', {
    class: 'axis', x: X(n - 1) + 8, y: Y(s.basket[n - 1]) + 4,
    'text-anchor': 'start', fill: colors.basket, 'font-weight': '600',
  });
  lt.textContent = s.basket[n - 1].toFixed(1);
  svg.appendChild(lt);

  const lb2 = svgEl('text', {
    class: 'axis', x: X(n - 1) + 8, y: Y(s.btc[n - 1]) + 4,
    'text-anchor': 'start', fill: colors.btc,
  });
  lb2.textContent = s.btc[n - 1].toFixed(1);
  svg.appendChild(lb2);

  // 横轴
  if (showXAxis) {
    const picks = [0, Math.floor(n / 3), Math.floor((2 * n) / 3), n - 1];
    picks.forEach((i, k) => {
      const t = svgEl('text', {
        class: 'axis', x: X(i), y: M.t + PH + 18,
        'text-anchor': k === 0 ? 'start' : k === picks.length - 1 ? 'end' : 'middle',
      });
      t.textContent = fmtDate(s.dates[i]).slice(2);
      svg.appendChild(t);
    });
  }

  attachCrosshair(svg, s, { M, PW, PH, X, Y, n, onHover });
}

/** 悬停十字线：在数据上着色 + 回调外部读值面板 */
function attachCrosshair(svg, s, g) {
  const { n } = g;
  let cross = null;
  const clear = () => { if (cross) { cross.remove(); cross = null; } };

  const paint = i => {
    clear();
    cross = svgEl('g');
    cross.appendChild(svgEl('line', {
      class: 'cross', x1: g.X(i), x2: g.X(i), y1: g.M.t, y2: g.M.t + g.PH,
    }));
    for (const [arr, fill] of [
      [s.basket, LINE_COLOR.basket],
      [s.btc, LINE_COLOR.btc],
      [s.vs, LINE_COLOR.vs],
    ]) {
      if (arr) {
        cross.appendChild(svgEl('circle', { cx: g.X(i), cy: g.Y(arr[i]), r: 3.1, fill }));
      }
    }
    svg.appendChild(cross);
    if (g.onHover) g.onHover(i, s);
  };

  svg.onmousemove = ev => {
    const rect = svg.getBoundingClientRect();
    const px = ((ev.clientX - rect.left) / rect.width) * (svg.clientWidth || 1000);
    let i = Math.round(((px - g.M.l) / g.PW) * (n - 1));
    i = Math.max(0, Math.min(n - 1, i));
    paint(i);
  };
  svg.onmouseleave = () => paint(n - 1);
  paint(n - 1);
}

export { fmtDate };
