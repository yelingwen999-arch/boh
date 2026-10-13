/* ==========================================================================
   BOH — 策略页渲染
   结论：4:3:3 + 阈值 ±5pp 触发再平衡（权重为风险机制，阈值经回测比选，见 backtest-result.json）。
   图：五条净值曲线（对数刻度），表：回测参数与各策略指标。
   ========================================================================== */

import { drawLogChart } from './render-logic.js';

// 策略曲线配色：选定的 ±5pp 用青绿加粗，其余用中性色
const CURVE_STYLE = {
  th5:      { cls: 'bt-th5', color: '#3fbf87' },   // 选定
  daily:    { cls: 'bt-daily', color: '#4aa8d8' },
  weekly:   { cls: 'bt-weekly', color: '#d98a3d' },
  th10:     { cls: 'bt-th10', color: '#8a7fd6' },
  buyhold:  { cls: 'bt-bh', color: '#a8a29a' },
};
const ORDER = ['th5', 'daily', 'weekly', 'th10', 'buyhold'];

const fmtInt = v => Math.round(v).toLocaleString('en-US');
const fmtPct1 = v => `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`;

export function renderStrategy(cfg) {
  if (!cfg || !cfg.curve) return;
  const byKey = Object.fromEntries(cfg.results.filter(r => r.fee).map(r => [r.key, r]));

  const stamp = document.getElementById('bt-stamp');
  if (stamp) stamp.textContent = `${cfg.startDate} → ${cfg.endDate}`;

  // ---- 净值曲线（对数刻度，th5 放第一：终点标签给选定策略）----
  const svg = document.getElementById('bt-chart');
  if (svg) {
    drawLogChart(svg, cfg.curve.dates, ORDER.map(k => ({
      values: cfg.curve.values[k],
      cls: CURVE_STYLE[k].cls,
      endColor: k === 'th5' ? CURVE_STYLE.th5.color : 'var(--tx-3)',
    })), {
      endFormat: v => `${(v / 100).toFixed(1)}x`,
    });
  }

  // ---- 图例：色标 + 策略名 + 期末倍数 ----
  const lg = document.getElementById('bt-legend');
  if (lg) {
    lg.innerHTML = ORDER.map(k => {
      const r = byKey[k];
      const mult = (r.endValue / 100).toFixed(1);
      return `<span class="lg-item${k === 'th5' ? ' is-sel' : ''}">
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

  // ---- 策略对比表 ----
  const tb = document.getElementById('bt-table');
  if (tb) {
    const rows = ORDER.map(k => {
      const r = byKey[k];
      const sel = k === cfg.selected;
      return `
        <tr${sel ? ' class="is-sel"' : ''}>
          <td>
            <span class="strat-name">${r.label}${sel ? '<i class="strat-flag">选定</i>' : ''}</span>
            <span class="cell-sub">${r.rule}</span>
          </td>
          <td class="n">${fmtInt(r.rebalances)}</td>
          <td class="n"><span class="cell-num">${fmtInt(r.endValue)}</span></td>
          <td class="n"><span class="cell-num up">${fmtPct1(r.totalReturnPct)}</span></td>
          <td class="n"><span class="cell-num down">${r.maxDrawdownPct.toFixed(1)}%</span></td>
          <td class="n">${r.feesPaid ? fmtInt(r.feesPaid) : '—'}</td>
        </tr>`;
    }).join('');

    tb.innerHTML = `
      <div class="tablewrap strat-wrap">
        <table class="grid-table strat-table">
          <caption class="sr-only">五种再平衡策略的回测指标对比</caption>
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

  // ---- 同区间参照 ----
  const ref = document.getElementById('bt-refs');
  if (ref && cfg.references) {
    ref.innerHTML = cfg.references.map(x =>
      `<span class="bt-ref"><b>${x.label.split(' ')[0]}</b> ${x.multiple.toFixed(1)}x</span>`
    ).join('');
  }
}
