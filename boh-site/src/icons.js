/* ==========================================================================
   BOH — 币种图标
   使用 CoinGecko 的官方代币图标（与价格数据源同一体系），
   已下载到 public/icons/，避免外链失效与跨域问题。

   注意：OKB 的图标就是 OKX 的品牌标志——平台币没有独立于交易所的视觉标识。
   这与 BTC / BNB / HYPE 各有自己标志的情况不同，属于事实差异。
   ========================================================================== */

const FILE = {
  BTC: 'btc.png',
  ETH: 'eth.png',
  SOL: 'sol.png',
  BNB: 'bnb.png',
  XRP: 'xrp.png',
  HYPE: 'hype.jpg',
  OKB: 'okb.png',
  ZEC: 'zec.png',
};

/** 返回一个图标元素。size: 'sm' | 'lg' | '' */
export function icon(sym, size = '') {
  const src = FILE[sym];
  if (!src) return '';
  const cls = size ? `ic ${size.startsWith('ic-') ? size : 'ic-' + size}` : 'ic';
  return `<img class="${cls}" src="/icons/${src}" alt="" width="24" height="24" loading="lazy" decoding="async" />`;
}
