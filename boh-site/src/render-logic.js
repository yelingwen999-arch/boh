/* ==========================================================================
   BOH — 论证板块渲染
   两张图：BTC 四年周期、平台币篮子 vs BTC。
   视觉规则同全站：细线、无光效、颜色走语义变量。
   ========================================================================== */

const NS = 'http://www.w3.org/2000/svg';
const svgEl = (n, a = {}) => {
  const node = document.createElementNS(NS, n);
  for (const k in a) node.setAttribute(k, a[k]);
  return node;
};

const fmtDate = ts => {
  const d = new Date(ts * 1000);
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`;
};
const fmtShort = ts => {
  const d = new Date(ts * 1000);
  return `${d.getUTCFullYear()}/${String(d.getUTCMonth() + 1).padStart(2, '0')}`;
};
const fmtUsd0 = v => '$' + Math.round(v).toLocaleString('en-US');
const fmtPct = (v, d = 1) =>
  v == null ? '—' : `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(d)}%`;
const cls = v => (v == null ? 'flat' : v > 0 ? 'up' : v < 0 ? 'down' : 'flat');

/* ---------- 通用：对数坐标折线图 ------------------------------------------ */

function drawLogChart(svg, dates, series, opts = {}) {
  const W = svg.clientWidth || 1000;
  const H = svg.clientHeight || 340;
  // 窄屏收紧边距，否则绘图区只剩一小条，横轴标签会互相压住
  const narrow = W < 560;
  const M = narrow
    ? { t: 20, r: 52, b: 24, l: 38 }
    : { t: 22, r: 78, b: 26, l: 56 };
  const PW = W - M.l - M.r;
  const PH = H - M.t - M.b;
  const n = dates.length;

  const all = series.flatMap(s => s.values).filter(v => v > 0);
  let lo = Math.log10(Math.min(...all));
  let hi = Math.log10(Math.max(...all));
  const pad = (hi - lo || 1) * 0.07;
  lo -= pad; hi += pad;

  const X = i => M.l + (n === 1 ? PW / 2 : (i / (n - 1)) * PW);
  const Y = v => M.t + PH - ((Math.log10(Math.max(v, 1e-9)) - lo) / (hi - lo)) * PH;

  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  while (svg.firstChild) svg.removeChild(svg.firstChild);

  // 区间底色
  for (const band of opts.bands || []) {
    const i0 = Math.max(0, dates.findIndex(d => d >= band.from));
    let i1 = dates.findIndex(d => d > band.to);
    if (i1 < 0) i1 = n - 1;
    if (i0 < 0) continue;
    svg.appendChild(svgEl('rect', {
      x: X(i0), y: M.t, width: Math.max(1, X(i1) - X(i0)), height: PH,
      fill: band.kind === 'bear' ? 'var(--clay-soft)' : 'var(--brass-soft)',
    }));
  }

  // 网格 + 纵轴（对数刻度：每个数量级标一条）
  const loMag = Math.floor(lo), hiMag = Math.ceil(hi);
  for (let m = loMag; m <= hiMag; m++) {
    const v = 10 ** m;
    const yy = Y(v);
    if (yy < M.t - 1 || yy > M.t + PH + 1) continue;
    svg.appendChild(svgEl('line', { class: 'grid', x1: M.l, x2: M.l + PW, y1: yy, y2: yy }));
    const lb = svgEl('text', { class: 'axis', x: M.l - 8, y: yy + 4, 'text-anchor': 'end' });
    lb.textContent = v >= 1000 ? (v / 1000) + 'k' : String(v);
    svg.appendChild(lb);
  }

  // 折线
  const toPath = arr => arr.map((v, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)} ${Y(v).toFixed(1)}`).join(' ');
  for (const s of series) {
    svg.appendChild(svgEl('path', { class: s.cls, d: toPath(s.values) }));
  }

  // 关键点标注
  for (const p of opts.markers || []) {
    const i = dates.findIndex(d => d >= p.ts);
    if (i < 0) continue;
    const cx = X(i), cy = Y(series[0].values[i]);
    svg.appendChild(svgEl('circle', { cx, cy, r: 3, fill: p.color || 'var(--tx)' }));
    const tx = svgEl('text', {
      class: 'axis', x: cx + (p.dx ?? 7), y: cy + (p.dy ?? -8),
      'text-anchor': (p.dx ?? 0) < 0 ? 'end' : (cx > W - 180 ? 'end' : 'start'),
      fill: p.color || 'var(--tx)',
    });
    tx.textContent = p.label;
    svg.appendChild(tx);
  }

  // 终点值
  const lastS = series[0].values[n - 1];
  const lt = svgEl('text', {
    class: 'axis', x: X(n - 1) + 8, y: Y(lastS) + 4,
    'text-anchor': 'start', fill: series[0].endColor || 'var(--tx)',
  });
  lt.textContent = opts.endFormat ? opts.endFormat(lastS) : lastS.toFixed(1);
  svg.appendChild(lt);

  // 横轴：窄屏只标首尾两个，否则标签会互相压住
  const picks = narrow
    ? [0, n - 1]
    : [0, Math.floor(n / 3), Math.floor((2 * n) / 3), n - 1];
  picks.forEach((i, k) => {
    const t = svgEl('text', {
      class: 'axis', x: X(i), y: M.t + PH + 18,
      'text-anchor': k === 0 ? 'start' : k === picks.length - 1 ? 'end' : 'middle',
    });
    t.textContent = fmtShort(dates[i]);
    svg.appendChild(t);
  });
}

/* ---------- 图一：BTC 四年周期 -------------------------------------------- */

export function renderCycle(cfg) {
  const svg = document.getElementById('cycle-chart');
  if (!svg || !cfg) return;

  // 周期顶全部标注（这是"周期存在"的证据）；再补最近一个底
  const highs = (cfg.turningPoints || []).filter(t => t.kind === 'high');
  const lows = (cfg.turningPoints || []).filter(t => t.kind === 'low');
  const markers = highs.map(t => ({
    ts: t.ts, label: fmtUsd0(t.price), color: 'var(--clay)', dy: -11,
  }));
  if (lows.length) {
    const l = lows[lows.length - 1];
    markers.push({ ts: l.ts, label: `底 ${fmtUsd0(l.price)}`, color: 'var(--jade)', dy: 18 });
  }
  // 末点靠右：文字左移，避免与右侧的终点值标签叠在一起
  markers.push({
    ts: cfg.current.ts,
    label: `现在 ${fmtUsd0(cfg.current.price)}`,
    color: 'var(--tx)', dx: -34, dy: 20,
  });

  drawLogChart(svg, cfg.dates, [{ values: cfg.prices, cls: 'line-btc-main', endColor: 'var(--tx)' }], {
    bands: (cfg.periods || []).map(p => ({ from: p.from, to: p.to, kind: p.kind })),
    markers,
    endFormat: v => fmtUsd0(v),
  });

  const el = document.getElementById('cycle-facts');
  if (el) {
    const gaps = cfg.cycleGaps || [];
    const periods = cfg.periods || [];
    const bears = periods.filter(p => p.kind === 'bear');
    const bulls = periods.filter(p => p.kind === 'bull');
    const meanYears = gaps.length ? gaps.reduce((s, g) => s + g.years, 0) / gaps.length : null;

    // 时间轴：每段宽度 = 该阶段实际月数，涨绿跌红交替，周期一眼可见
    const monthsOf = p => (p.to - p.from) / 86400 / 30.44;
    const totalMonths = periods.reduce((s, p) => s + monthsOf(p), 0);

    // 按真实月数分配宽度，但给窄段一个下限（否则段内的数字放不下），
    // 设完下限后重新归一化，保证七段加起来正好 100%。
    const MIN_W = 13.5;
    let raw = periods.map(p => monthsOf(p) / totalMonths * 100);
    for (let guard = 0; guard < 12; guard++) {
      const fixed = raw.map(w => w < MIN_W);
      if (!fixed.some(Boolean)) break;
      const fixedSum = raw.reduce((s, w, i) => s + (fixed[i] ? MIN_W : 0), 0);
      const flexSum = raw.reduce((s, w, i) => s + (fixed[i] ? 0 : w), 0);
      const scale = flexSum > 0 ? (100 - fixedSum) / flexSum : 1;
      const next = raw.map((w, i) => (fixed[i] ? MIN_W : w * scale));
      if (next.every((w, i) => Math.abs(w - raw[i]) < 0.01)) { raw = next; break; }
      raw = next;
    }
    const widths = raw;

    // 坐标轴刻度：段边界 + 两端，共 n+1 个
    const ticks = periods.map(p => p.from).concat(periods[periods.length - 1].to);

    el.innerHTML = `
      <p class="boh-scroll-hint">← 左右滑动查看完整周期 →</p>
      <div class="boh-axis">
        <div class="boh-seg" role="img" aria-label="BTC 历次周期区间的时间轴">
          ${periods.map((p, i) => {
            const isUp = p.changePct > 0;
            const last = i === periods.length - 1;
            return `
              <div class="boh-seg-part ${isUp ? 'bull' : 'bear'}${last ? ' is-now' : ''}"
                   style="flex:0 0 ${widths[i].toFixed(2)}%">
                <span class="boh-seg-pct">${fmtPct(p.changePct, isUp && Math.abs(p.changePct) > 100 ? 0 : 1)}</span>
                <span class="boh-seg-months">${monthsOf(p).toFixed(0)} 个月</span>
              </div>
            `;
          }).join('')}
        </div>

        <div class="boh-rule" aria-hidden="true">
          <span class="boh-axis-arrow"></span>
          ${ticks.map((t, i) => {
            // 第 i 个刻度是第 i-1 段的终点：位置 = 前面各段宽度之和
            const pos = i === 0 ? 0 : widths.slice(0, i).reduce((s, w) => s + w, 0);
            const edge = i === 0 ? ' is-first' : (i === widths.length ? ' is-last' : '');
            return `<span class="boh-tick${edge}" style="left:${pos.toFixed(2)}%"></span>
                    <span class="boh-tick-label${edge}" style="left:${pos.toFixed(2)}%">${fmtDate(t).slice(0, 7)}</span>`;
          }).join('')}
        </div>
      </div>

      <div class="cycle-sum">
        <div>
          <span class="cs-k">周期长度</span>
          <span class="cs-v">${meanYears ? meanYears.toFixed(2) : '—'} <em>年</em></span>
          <span class="cs-n">${gaps.map(g => g.years.toFixed(2)).join(' / ')} 年</span>
        </div>
        <div>
          <span class="cs-k">每轮下行</span>
          <span class="cs-v down">${bears.map(b => fmtPct(b.changePct, 0)).join(' / ')}</span>
          <span class="cs-n">各 ${bears.map(b => monthsOf(b).toFixed(0)).join(' / ')} 个月</span>
        </div>
        <div>
          <span class="cs-k">每轮上行</span>
          <span class="cs-v up">${bulls.map(b => fmtPct(b.changePct, 0)).join(' / ')}</span>
          <span class="cs-n">各 ${bulls.map(b => monthsOf(b).toFixed(0)).join(' / ')} 个月</span>
        </div>
      </div>
    `;
  }
}

/* ---------- 图二：平台币篮子 vs BTC -------------------------------------- */

export function renderCompare(cfg) {
  const svg = document.getElementById('compare-chart');
  if (!svg || !cfg) return;

  drawLogChart(svg, cfg.dates, [
    { values: cfg.basket, cls: 'line-basket-main', endColor: 'var(--tx)' },
    { values: cfg.btc, cls: 'line-btc-ref', endColor: 'var(--tx-3)' },
    { values: cfg.vsBtc, cls: 'line-vs-ref', endColor: 'var(--brass)' },
  ], {
    endFormat: v => v.toFixed(0),
    markers: [
      { ts: cfg.dates[0], label: '起点 100', color: 'var(--tx-3)' },
      { ts: cfg.basketPeak.ts, label: `篮子峰值 ${cfg.basketPeak.value.toFixed(0)}`, color: 'var(--tx)', dy: -10 },
      { ts: cfg.btcPeak.ts, label: `BTC 峰值 ${cfg.btcPeak.value.toFixed(0)}`, color: 'var(--tx-3)' },
    ],
  });

  const el = document.getElementById('compare-facts');
  if (el) {
    const cells = [
      ['平台币篮子（等权）', fmtPct(cfg.basketChange), `${fmtDate(cfg.dates[0])} 至 ${fmtDate(cfg.dates[cfg.dates.length - 1])}`],
      ['BTC（同区间）', fmtPct(cfg.btcChange), '同为起点 100'],
      ['篮子相对 BTC 超额', `${fmtPct(cfg.excess)} 个百分点`, '累计涨幅之差'],
      ['距各自历史最高', `篮子 ${fmtPct(cfg.basketPeak.drawdown)} · BTC ${fmtPct(cfg.btcPeak.drawdown)}`, `全历史峰值 · 篮子 ${fmtDate(cfg.basketPeak.ts)} · BTC ${fmtDate(cfg.btcPeak.ts)}`],
    ];
    el.innerHTML = cells.map(([k, v, sub]) => `
      <div>
        <dt>${k}</dt>
        <dd class="${typeof v === 'string' && v.startsWith('+') ? 'up' : typeof v === 'string' && v.startsWith('−') ? 'down' : ''}">${v}<small>${sub}</small></dd>
      </div>
    `).join('');
  }
}

/* ---------- 分散的意义：同期各币表现 ------------------------------------ */

export function renderSpread(assets, dates) {
  const el = document.getElementById('spread-facts');
  if (!el) return;

  const items = ['BNB', 'OKB', 'HYPE'].map(s => {
    const a = assets[s];
    return { sym: s, chg: a.rolling?.['365'], vs: a.vsBtc?.['365'] };
  });

  // 其他部分（含"篮子 12 个月"那一格）由调用方从 data.json 填，避免口径不一致
  el.innerHTML = items.map(it => `
    <div>
      <dt>${it.sym} · 近 12 个月</dt>
      <dd class="${cls(it.chg)}">${fmtPct(it.chg)}
        <small>对 BTC ${fmtPct(it.vs)}</small>
      </dd>
    </div>
  `).join('');
}
