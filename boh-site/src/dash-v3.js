/* ==========================================================================
   BOH — 总览页交互
   这是一个营销页：只呈现结论与数据，不展示数据来源、缺口说明与内部术语。
   数据来源记录在仓库的 scripts/ 与数据文件里，不在页面上暴露。
   ========================================================================== */

import { renderCycle, renderSpread } from './render-logic.js';
import { renderPlatformHistory } from './render-platform-history.js';
import { initChrome } from './chrome.js';
import { icon } from './icons.js';
import { initRouter } from './router.js';
import { draw, sliceSeries, LINE_COLOR } from './chart-shared.js';

const ZERO = '—';
const ASSET_META = {
  BTC: { name: 'Bitcoin' },
  HYPE: { name: 'Hyperliquid' },
  BNB: { name: 'BNB Chain' },
  OKB: { name: 'OKX' },
};
const ORDER = ['BNB', 'OKB', 'HYPE'];

let DATA = null;
let RANGE = 365;

/* ---------- 工具 ---------------------------------------------------------- */

const fmtPct = (v, d = 2) =>
  v == null ? ZERO : `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(d)}%`;
const cls = v => (v == null ? 'flat' : v > 0 ? 'up' : v < 0 ? 'down' : 'flat');
const fmtUsd = v =>
  v == null ? ZERO : '$' + v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmtBig = v => {
  if (v == null) return ZERO;
  if (v >= 1e9) return '$' + (v / 1e9).toFixed(2) + 'B';
  if (v >= 1e6) return '$' + (v / 1e6).toFixed(1) + 'M';
  if (v >= 1e3) return '$' + (v / 1e3).toFixed(1) + 'K';
  return '$' + v.toFixed(0);
};
const fmtDate = ts => {
  const d = new Date(ts * 1000);
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`;
};

/* ---------- 行情带由共用顶栏模块负责（chrome.js） ---------- */

/* ---------- 行情快照 ------------------------------------------------------ */

function renderSnapshot() {
  document.getElementById('snap').innerHTML = ['BTC', ...ORDER].map(sym => {
    const a = DATA.assets[sym];
    const isBtc = sym === 'BTC';
    const v365 = isBtc ? null : (a.vsBtc?.['365'] ?? null);
    return `
      <div class="snap-cell">
        <div class="snap-top">
          ${icon(sym)}
          <span class="snap-code">${sym}</span>
          <span class="snap-name">${ASSET_META[sym].name}</span>
        </div>
        <span class="snap-price">${fmtUsd(a.price)}</span>
        <span class="snap-chg ${cls(a.change24h)}">${fmtPct(a.change24h)} <span style="color:var(--tx-3)">24h</span></span>
        <div class="snap-row">
          <span>12月 ${fmtPct(a.rolling?.['365'], 1)}</span>
          ${isBtc ? '<span>基准</span>' : `<span class="${cls(v365)}">对BTC ${fmtPct(v365, 1)}</span>`}
        </div>
      </div>
    `;
  }).join('');
}

/* ---------- 核心指标卡 ---------------------------------------------------- */

function renderKeycard(range) {
  const m = DATA.basket.metrics[String(range)];
  if (!m) return;

  const node = document.getElementById('keynum');
  node.textContent = fmtPct(m.vsBtcCum, 1);
  node.className = `keynum ${cls(m.vsBtcCum)}`;

  document.getElementById('keyunit').textContent = '个百分点 · 累计超额';

  const mb = document.getElementById('mk-basket');
  mb.textContent = fmtPct(m.abs, 2);
  mb.className = `kg-value num ${cls(m.abs)}`;

  const mt = document.getElementById('mk-btc');
  mt.textContent = fmtPct(m.btc, 2);
  mt.className = `kg-value num ${cls(m.btc)}`;

  const nav = document.getElementById('mk-nav');
  nav.textContent = (100 + (m.vsBtcCum ?? 0)).toFixed(1);
  nav.className = `kg-value num ${cls(m.vsBtcCum)}`;

  const days = range === 365 ? '近 12 个月' : `近 ${range} 天`;
  document.getElementById('keycard-foot').textContent =
    `${days} · 4:3:3 篮子 · 篮子按实际成交价折算份额`;
}

/* ---------- 走势图（首屏） ------------------------------------------------ */

function renderNavLegend() {
  const el = document.getElementById('nav-legend');
  if (!el) return;
  el.innerHTML =
    `<span class="lg-item"><i class="lg-line" style="background:${LINE_COLOR.basket}"></i>篮子涨跌</span>` +
    `<span class="lg-item"><i class="lg-line" style="background:${LINE_COLOR.btc}"></i>BTC</span>` +
    `<span class="lg-item"><i class="lg-line" style="background:${LINE_COLOR.vs}"></i>篮子 / BTC</span>`;
}

function drawChart() {
  const svg = document.getElementById('chart');   // 每次现取：客户端切页后 DOM 是新的
  if (!DATA || !svg) return;
  const s = sliceSeries(DATA.chart, RANGE);
  draw(svg, s, {
    showVs: true,
    showXAxis: false,
    onHover: (i, ser) => {
      document.getElementById('ro-date').textContent = fmtDate(ser.dates[i]);
      document.getElementById('ro-basket').textContent = ser.basket[i].toFixed(1);
      document.getElementById('ro-btc').textContent = ser.btc[i].toFixed(1);
      document.getElementById('ro-vs').textContent = ser.vs[i].toFixed(1);
    },
  });
}

/* ---------- 分散板块：补上「4:3:3 篮子」那一格（数字取自 data.json） --------- */

function appendBasketSpreadCell() {
  const el = document.getElementById('spread-facts');
  if (!el) return;
  const m = DATA.basket.metrics['365'];
  const div = document.createElement('div');
  div.innerHTML =
    `<dt>4:3:3 篮子 · 近 12 个月</dt>` +
    `<dd class="${cls(m.abs)}">${fmtPct(m.abs)}` +
    `<small>BTC 同期 ${fmtPct(m.btc)}</small></dd>`;
  el.appendChild(div);
}

/* ---------- 篮子构成表 ---------------------------------------------------- */
function renderHoldings() {
  document.getElementById('holdings').innerHTML = ORDER.map(sym => {
    const a = DATA.assets[sym];
    const sup = DATA.supplementary[sym];
    // 没有就不显示，不写"未查到"
    const apyCell = sup.stakeApy == null
      ? `<td class="n"></td>`
      : `<td class="n"><span class="cell-num">${sup.stakeApy.toFixed(2)}%</span></td>`;

    return `
      <tr>
        <td>
          <span class="tok">
            <span class="tok-line">${icon(sym)}<span class="tok-code">${sym}</span></span>
            <span class="tok-name">${ASSET_META[sym].name}</span>
          </span>
        </td>
        <td class="n"><span class="cell-num">${fmtUsd(a.price)}</span></td>
        <td class="n"><span class="cell-num ${cls(a.change24h)}">${fmtPct(a.change24h)}</span></td>
        <td class="n"><span class="cell-num ${cls(a.rolling?.['30'])}">${fmtPct(a.rolling?.['30'], 1)}</span></td>
        <td class="n"><span class="cell-num ${cls(a.rolling?.['365'])}">${fmtPct(a.rolling?.['365'], 1)}</span></td>
        <td class="n"><span class="cell-num ${cls(a.vsBtc?.['365'])}">${fmtPct(a.vsBtc?.['365'], 1)}</span></td>
        ${apyCell}
        <td class="n"><span class="cell-num">${fmtBig(sup.mcap)}</span></td>
        <td><span class="cell-sub" style="display:inline">${sup.buyback ? sup.buybackNote : ''}</span></td>
      </tr>
    `;
  }).join('');
}

/* ---------- 平台信息 ------------------------------------------------------ */

function renderPlatforms() {
  document.getElementById('plat-grid').innerHTML = ORDER.map(sym => {
    const a = DATA.assets[sym];
    const sup = DATA.supplementary[sym];
    const f = sup.feeRevenue;

    const metric = (k, v) =>
      `<div class="plat-metric"><span class="pm-k">${k}</span><span class="pm-v">${v}</span></div>`;

    // 只显示取到的数字，没有的就不列
    const metrics = [];
    if (sup.mcap) metrics.push(metric('市值', fmtBig(sup.mcap)));
    if (f) metrics.push(metric('平台费用 · 24h', fmtBig(f.day)));
    if (a.quoteVolume24h) metrics.push(metric('现货成交 · 24h', fmtBig(a.quoteVolume24h)));
    if (sup.stakeApy != null) metrics.push(metric('质押年化', sup.stakeApy.toFixed(2) + '%'));
    if (sup.stakeRatio != null) metrics.push(metric('质押率', sup.stakeRatio.toFixed(2) + '%'));
    if (sup.ath) metrics.push(metric('历史最高', `$${sup.ath.toLocaleString('en-US')}`));
    if (sup.validatorCount != null) {
      metrics.push(metric('验证者', sup.validatorTotal
        ? `${sup.validatorCount} / ${sup.validatorTotal}`
        : String(sup.validatorCount)));
    }
    metrics.push(metric('12 个月', fmtPct(a.rolling?.['365'], 1)));

    const events = (sup.events || []).slice(0, 3).map(ev => `
      <li>
        <span class="ev-date">${ev.date}</span>
        <span class="ev-body">${ev.text}</span>
      </li>
    `).join('');

    const why = f
      ? `平台费用可在链上核对：近 12 个月 ${fmtBig(f.year)}，累计 ${fmtBig(f.allTime)}。`
      : `平台自身的手续费收入未公开，靠平台规模与回购支撑。`;

    return `
      <article class="plat-card">
        <div class="plat-head">
          <span class="plat-id">
            <span class="plat-title">${icon(sym, 'ic-lg')}<span class="plat-code">${sym}</span></span>
            <span class="plat-name">${ASSET_META[sym].name} · ${sup.chain}</span>
          </span>
          <span class="plat-price">
            <span class="plat-price-v">${fmtUsd(a.price)}</span>
            <span class="plat-price-c ${cls(a.change24h)}">${fmtPct(a.change24h)} 24h</span>
          </span>
        </div>

        <div class="plat-metrics">${metrics.join('')}</div>

        <div class="plat-block">
          <h4>收入与回购</h4>
          <p>${why}${sup.buyback ? ' ' + sup.buybackNote + '。' : ''}</p>
        </div>

        ${events ? `<div class="plat-block"><h4>近期动态</h4><ul class="plat-events">${events}</ul></div>` : ''}
      </article>
    `;
  }).join('');
}

/* ---------- 页脚 ---------------------------------------------------------- */

function renderStamp() {
  // 营销页不展示数据来源与抓取时间，这里不做任何页脚标注
}

/* ---------- 区间切换 ------------------------------------------------------ */

function bindRanges() {
  document.querySelectorAll('.ranges button').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.ranges button').forEach(b => {
        b.classList.remove('is-on');
        b.setAttribute('aria-pressed', 'false');
      });
      btn.classList.add('is-on');
      btn.setAttribute('aria-pressed', 'true');
      RANGE = Number(btn.dataset.range);
      renderKeycard(RANGE);
      drawChart();
    });
  });
}

/* ---------- 启动 ---------------------------------------------------------- */

let resizeTimer = null;
window.addEventListener('resize', () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => drawChart(), 140);
});

/* ---------- 诊断：访问 ?debug=1 时在页面上打印图表真实状态 ---------- */

function diagnose() {
  const rows = [];
  for (const id of ['chart', 'cycle-chart', 'pl-chart']) {
    const el = document.getElementById(id);
    if (!el) { rows.push(`${id}: 元素不存在`); continue; }
    const paths = el.querySelectorAll('path');
    const cs = getComputedStyle(el);
    const box = el.getBoundingClientRect();
    let strokes = [];
    paths.forEach(p => {
      const s = getComputedStyle(p);
      strokes.push(s.stroke);
    });
    rows.push(
      `${id}: 子元素=${el.childElementCount} path=${paths.length} ` +
      `viewBox="${el.getAttribute('viewBox')}" ` +
      `尺寸=${Math.round(box.width)}x${Math.round(box.height)} ` +
      `clientWH=${el.clientWidth}x${el.clientHeight} ` +
      `display=${cs.display} visibility=${cs.visibility} opacity=${cs.opacity}`
    );
    if (strokes.length) rows.push(`    stroke: ${[...new Set(strokes)].join(' | ')}`);
  }
  // 数据条是否渲染
  for (const id of ['cycle-facts', 'pl-facts', 'plat-grid', 'holdings']) {
    const el = document.getElementById(id);
    rows.push(`${id}: ${el ? (el.childElementCount + ' 个子元素, ' + el.innerHTML.length + ' 字符') : '不存在'}`);
  }
  const panel = document.createElement('pre');
  panel.style.cssText =
    'position:fixed;left:0;right:0;bottom:0;z-index:99;max-height:45vh;overflow:auto;' +
    'margin:0;padding:.8rem 1rem;background:#0b0e13;color:#9fe8c6;' +
    'font:12px/1.7 ui-monospace,monospace;white-space:pre-wrap;border-top:2px solid #35d6f0';
  panel.textContent = rows.join('\n');
  document.body.appendChild(panel);
}

let CYCLE = null;
let PLAT_HIST = null;

/** 渲染总览页的所有板块。每一步独立保护，任何一个失败不影响其余。 */
function renderAll() {
  const steps = [
    ['snapshot', renderSnapshot],
    ['keycard', () => renderKeycard(RANGE)],
    ['chart', drawChart],          // 首屏图先画，不依赖下面几块
    ['ranges', bindRanges],
    ['navLegend', renderNavLegend],
    ['cycle', () => renderCycle(CYCLE)],
    ['platformHistory', () => renderPlatformHistory(PLAT_HIST)],
    ['spread', () => renderSpread(DATA.assets, DATA.chart.dates)],
    ['basketCell', appendBasketSpreadCell],
    ['platforms', renderPlatforms],
    ['holdings', renderHoldings],
    ['stamp', renderStamp],
  ];

  const failed = [];
  for (const [name, fn] of steps) {
    try {
      fn();
    } catch (err) {
      failed.push(name);
      console.error(`[BOH] 渲染失败: ${name}`, err);
    }
  }
  return failed;
}

/** 画一遍总览页所有板块（首次挂载与切页回来都走这里） */
async function render() {
  const failed = renderAll();
  if (failed.length) {
    const bar = document.createElement('div');
    bar.style.cssText =
      'position:fixed;left:0;right:0;bottom:0;z-index:99;padding:.6rem 1rem;' +
      'background:#b04a2c;color:#fff;font:12px/1.6 ui-monospace,monospace';
    bar.textContent = '以下板块渲染失败：' + failed.join('、') + '（详见控制台）';
    document.body.appendChild(bar);
  }
  if (new URLSearchParams(location.search).has('debug')) diagnose();
}

/**
 * 挂载总览页。直接打开页面与客户端切页都由 router 调用这里。
 * 数据只取一次，切页回来时只重画 DOM。
 */
export async function renderPage() {
  await initChrome('dash');

  if (!DATA) {
    const [main, cycle, platHist] = await Promise.all([
      fetch('./data/data.json').then(r => r.json()),
      fetch('./data/btc-cycle.json').then(r => r.json()).catch(() => null),
      fetch('./data/platform-history.json').then(r => r.json()).catch(() => null),
    ]);
    DATA = main;
    CYCLE = cycle;
    PLAT_HIST = platHist;
  }

  await render();
}

initRouter().catch(err => {
  console.error(err);
  // 把错误直接显示在页面上，避免"图没数据但不知道原因"
  const bar = document.createElement('div');
  bar.style.cssText =
    'position:fixed;left:0;right:0;bottom:0;z-index:99;padding:.75rem 1rem;' +
    'background:#b04a2c;color:#fff;font:13px/1.6 ui-monospace,monospace;white-space:pre-wrap';
  bar.textContent = '页面初始化失败：' + (err && err.message ? err.message : String(err)) +
    (err && err.stack ? '\n' + err.stack.split('\n').slice(1, 4).join('\n') : '');
  document.body.appendChild(bar);
});
