/* ==========================================================================
   BOH — 策略页渲染
   结论：4:3:3 持有 + 阈值 ±15pp 触发再平衡（回测比选，见 backtest-result.json）。
   图：各策略净值曲线（对数刻度）；
   表：策略对比、阈值扫描、稳健性检验（自然年 / 滚动三年 / 牛熊分段）。
   ========================================================================== */

import { drawLogChart } from './render-logic.js';

// 曲线配色：选定阈值青绿加粗，其余中性
const CURVE_STYLE = {
  th15:    { cls: 'bt-sel', color: '#3fbf87' },   // 选定
  th5:     { cls: 'bt-t5', color: '#4aa8d8' },
  th10:    { cls: 'bt-t10', color: '#8a7fd6' },
  th20:    { cls: 'bt-t20', color: '#d98a3d' },
  daily:   { cls: 'bt-daily', color: '#6ba3c9' },
  weekly:  { cls: 'bt-weekly', color: '#c9a227' },
  buyhold: { cls: 'bt-bh', color: '#a8a29a' },
};
// 图里只放几条主要的，避免糊成一团
const CURVE_ORDER = ['th15', 'th5', 'th10', 'th20', 'buyhold'];

const fmtInt = v => Math.round(v).toLocaleString('en-US');
const fmtPct1 = v => `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`;

export function renderStrategy(cfg) {
  if (!cfg || !cfg.curve) return;
  const sel = cfg.selected || 'th15';
  const withFee = Object.fromEntries(cfg.results.filter(r => r.fee).map(r => [r.key, r]));

  const stamp = document.getElementById('bt-stamp');
  if (stamp) stamp.textContent = `${cfg.startDate} → ${cfg.endDate}`;

  // ---- 净值曲线 ----
  const svg = document.getElementById('bt-chart');
  if (svg) {
    drawLogChart(svg, cfg.curve.dates, CURVE_ORDER.map(k => ({
      values: cfg.curve.values[k],
      cls: CURVE_STYLE[k].cls,
      endColor: k === sel ? CURVE_STYLE[sel].color : 'var(--tx-3)',
    })), {
      endFormat: v => `${(v / 100).toFixed(1)}x`,
    });
  }

  // ---- 图例 ----
  const lg = document.getElementById('bt-legend');
  if (lg) {
    lg.innerHTML = CURVE_ORDER.map(k => {
      const r = withFee[k];
      if (!r) return '';
      const mult = (r.endValue / 100).toFixed(1);
      return `<span class="lg-item${k === sel ? ' is-sel' : ''}">
        <i class="lg-line" style="background:${CURVE_STYLE[k].color}"></i>${r.label} ${mult}x</span>`;
    }).join('');
  }

  // ---- 回测参数 ----
  const par = document.getElementById('bt-params');
  if (par) {
    const items = [
      ['回测区间', `${cfg.startDate} → ${cfg.endDate}`],
      ['长度', `约 ${cfg.years} 年 · ${fmtInt(cfg.days)} 个交易日`],
      ['回测标的', cfg.target
        ? `${cfg.pair[0]} ${Math.round(cfg.target.BNB * 100)}% + ${cfg.pair[1]} ${Math.round(cfg.target.OKB * 100)}%`
        : cfg.pair.join(' + ')],
      ['手续费', '单边 0.1%'],
      ['起始值', '100，按目标比例'],
    ];
    par.innerHTML = items.map(([k, v]) =>
      `<div class="bt-p"><span class="bt-p-k">${k}</span><span class="bt-p-v">${v}</span></div>`
    ).join('');
  }

  // ---- 主表：策略对比 ----
  const tb = document.getElementById('bt-table');
  if (tb) {
    const order = ['buyhold', 'daily', 'weekly', 'th5', 'th10', 'th15', 'th20'];
    const rows = order.map(k => {
      const r = withFee[k];
      if (!r) return '';
      const isSel = k === sel;
      return `
        <tr${isSel ? ' class="is-sel"' : ''}>
          <td>
            <span class="strat-name">${r.label}${isSel ? '<i class="strat-flag">选定</i>' : ''}</span>
            <span class="cell-sub">${r.rule}</span>
          </td>
          <td class="n">${fmtInt(r.rebalances)}</td>
          <td class="n"><span class="cell-num">${fmtInt(r.endValue)}</span></td>
          <td class="n"><span class="cell-num ${r.totalReturnPct >= 0 ? 'up' : 'down'}">${fmtPct1(r.totalReturnPct)}</span></td>
          <td class="n"><span class="cell-num down">${r.maxDrawdownPct.toFixed(1)}%</span></td>
          <td class="n">${r.feesPaid ? fmtInt(r.feesPaid) : '—'}</td>
        </tr>`;
    }).join('');

    tb.innerHTML = `
      <div class="tablewrap strat-wrap">
        <table class="grid-table strat-table">
          <caption class="sr-only">各再平衡策略的回测指标对比</caption>
          <thead>
            <tr>
              <th scope="col">策略</th>
              <th scope="col" class="n">调仓次数</th>
              <th scope="col" class="n">期末值</th>
              <th scope="col" class="n">总收益</th>
              <th scope="col" class="n">最大回撤</th>
              <th scope="col" class="n">手续费</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  // ---- 阈值扫描 ----
  const scanEl = document.getElementById('bt-scan');
  if (scanEl && cfg.scan) {
    const max = Math.max(...cfg.scan.map(s => s.endValue));
    const rows = cfg.scan.map(s => {
      const isSel = s.pp === cfg.selectedPp;
      const w = Math.max(4, (s.endValue / max) * 100);
      return `
        <tr${isSel ? ' class="is-sel"' : ''}>
          <td><span class="scan-pp">±${s.pp}pp${isSel ? '<i class="strat-flag">选定</i>' : ''}</span></td>
          <td class="scan-bar-cell"><span class="scan-bar" style="width:${w.toFixed(1)}%"></span></td>
          <td class="n"><span class="cell-num">${fmtInt(s.endValue)}</span></td>
          <td class="n">${s.cagrPct.toFixed(1)}%</td>
          <td class="n">${fmtInt(s.rebalances)}</td>
        </tr>`;
    }).join('');
    scanEl.innerHTML = `
      <div class="tablewrap strat-wrap">
        <table class="grid-table strat-table scan-table">
          <caption class="sr-only">不同阈值下的回测结果</caption>
          <thead>
            <tr>
              <th scope="col">阈值</th>
              <th scope="col" class="scan-bar-cell"></th>
              <th scope="col" class="n">期末值</th>
              <th scope="col" class="n">年化</th>
              <th scope="col" class="n">调仓</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  // ---- 稳健性检验 ----
  const rob = document.getElementById('bt-robust');
  if (rob && cfg.yearly && cfg.rolling) {
    const ths = cfg.thresholds || [5, 10, 15, 20];
    const head = ths.map(t => `<th scope="col" class="n">±${t}pp</th>`).join('');

    const rowFor = (row, label) => {
      const cells = ths.map(t => {
        const v = row.values[`th${t}`];
        const isBest = row.best === t;
        return `<td class="n"><span class="cell-num${isBest ? ' is-best' : ''}">${
          v == null ? '—' : Math.round(v).toLocaleString('en-US')}</span></td>`;
      }).join('');
      return `<tr><td>${label}</td>${cells}</tr>`;
    };

    const yearly = cfg.yearly.map(r => rowFor(r, `${r.year} 年`)).join('');
    const rolling = cfg.rolling.map(r => rowFor(r, `${r.start} 起`)).join('');
    const phases = cfg.phases.map(r => rowFor(r, r.label)).join('');

    const ch = cfg.champions || {};
    const tally = key => ths
      .map(t => `±${t}pp ${ch[key]?.[`th${t}`] ?? 0} 次`)
      .join(' · ');

    rob.innerHTML = `
      <div class="rob-block">
        <h3>自然年</h3>
        <div class="tablewrap strat-wrap">
          <table class="grid-table strat-table">
            <caption class="sr-only">各自然年不同阈值的期末值</caption>
            <thead><tr><th scope="col">年度</th>${head}</tr></thead>
            <tbody>${yearly}</tbody>
          </table>
        </div>
        <p class="rob-note">夺冠次数：${tally('yearly')}</p>
      </div>

      <div class="rob-block">
        <h3>滚动 3 年窗口</h3>
        <div class="tablewrap strat-wrap">
          <table class="grid-table strat-table">
            <caption class="sr-only">滚动三年窗口不同阈值的期末值</caption>
            <thead><tr><th scope="col">起点</th>${head}</tr></thead>
            <tbody>${rolling}</tbody>
          </table>
        </div>
        <p class="rob-note">夺冠次数：${tally('rolling')}</p>
      </div>

      <div class="rob-block">
        <h3>牛熊分段</h3>
        <div class="tablewrap strat-wrap">
          <table class="grid-table strat-table">
            <caption class="sr-only">牛市与熊市分段下不同阈值的表现</caption>
            <thead><tr><th scope="col">区间</th>${head}</tr></thead>
            <tbody>${phases}</tbody>
          </table>
        </div>
        <p class="rob-note">夺冠次数：${tally('phases')}</p>
      </div>

      <p class="rob-tip">每格加粗者为该行最优。同一个阈值在多数行都加粗，说明它不是运气。</p>`;
  }

  // ---- 同区间参照 ----
  const ref = document.getElementById('bt-refs');
  if (ref && cfg.references) {
    ref.innerHTML = cfg.references.map(x =>
      `<span class="bt-ref"><b>${x.label.split(' ')[0]}</b> ${x.multiple.toFixed(1)}x</span>`
    ).join('');
  }
}
