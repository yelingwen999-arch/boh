/* ==========================================================================
   BOH — 实时报价
   静态站点的 JSON 是抓取时的快照，会越来越旧；这里在浏览器端直接从
   Gate.io 现货接口取实时价覆盖（该接口带 CORS 头，无需服务器）。

   用法：
     import { live } from './live-quote.js';
     await live.load();              // 先取快照（立即可渲染）
     live.subscribe(render);         // 有更新就回调（快照到位、实时价到位各一次）
     live.start();                   // 启动定时刷新（幂等）

   数据形态：live.order 币种顺序；live.quote[sym] = { price, change24h, live }
   live 为 true 表示这是实时价，false 表示仍是快照值。
   ========================================================================== */

const GATE = 'https://api.gateio.ws/api/v4/spot/tickers?currency_pair=';

// Gate.io 交易对；不在表里的币种不取实时价，沿用快照
const GATE_PAIRS = {
  BTC: 'BTC_USDT', ETH: 'ETH_USDT', SOL: 'SOL_USDT', BNB: 'BNB_USDT',
  XRP: 'XRP_USDT', HYPE: 'HYPE_USDT', OKB: 'OKB_USDT', ZEC: 'ZEC_USDT',
};

const REFRESH_MS = 60000;     // 实时价刷新间隔
const SNAP_FRESH_S = 60;      // 快照多久算不新鲜，加载时据此决定是否立刻取

const subs = new Set();
let started = false;
let timer = null;

const live = {
  order: [],
  quote: {},
  generatedAt: null,

  /** 订阅更新；返回取消订阅函数 */
  subscribe(fn) {
    subs.add(fn);
    return () => subs.delete(fn);
  },

  /** 取静态快照（保证首屏不空） */
  async load() {
    try {
      const res = await fetch('./data/market.json', { cache: 'no-store' });
      const market = await res.json();
      this.order = market.order || Object.keys(market.assets || {});
      for (const sym of this.order) {
        const a = market.assets?.[sym];
        if (a) this.quote[sym] = { price: a.price, change24h: a.change24h, live: false };
      }
      this.generatedAt = market.generatedAt || null;
      this._emit();
      return true;
    } catch (err) {
      console.error('[BOH] 行情快照加载失败', err);
      return false;
    }
  },

  /** 取实时价覆盖快照；失败则保持原值 */
  async refresh() {
    const syms = this.order.filter(s => GATE_PAIRS[s]);
    if (!syms.length) return false;
    // 接口不支持逗号分隔多交易对（会 400），只能逐个查，故并发发出
    const results = await Promise.all(syms.map(async sym => {
      try {
        const res = await fetch(GATE + GATE_PAIRS[sym], { cache: 'no-store' });
        if (!res.ok) return null;
        const rows = await res.json();
        const r = Array.isArray(rows) ? rows[0] : null;
        const price = r ? parseFloat(r.last) : NaN;
        if (!Number.isFinite(price)) return null;
        const pct = r ? parseFloat(r.change_percentage) : NaN;
        return [sym, {
          price,
          change24h: Number.isFinite(pct) ? pct : this.quote[sym]?.change24h,
          live: true,
        }];
      } catch {
        return null;
      }
    }));

    let hit = 0;
    for (const item of results) {
      if (!item) continue;
      this.quote[item[0]] = item[1];
      hit++;
    }
    if (hit) {
      this._emit();
      return true;
    }
    console.warn('[BOH] 实时行情未能取回，沿用快照');
    return false;
  },

  /** 启动刷新（幂等）：快照不新鲜先取一次，之后定时刷新 */
  async start() {
    if (started) return;
    started = true;

    const age = this.generatedAt ? Date.now() / 1000 - this.generatedAt : Infinity;
    if (age > SNAP_FRESH_S) await this.refresh();

    timer = setInterval(() => this.refresh(), REFRESH_MS);
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) this.refresh();   // 回到前台补一次
    });
  },

  _emit() {
    for (const fn of subs) {
      try { fn(this); } catch (err) { console.error('[BOH] 报价订阅回调出错', err); }
    }
  },
};

export { live };
