/* ==========================================================================
   BOH — 多页之间的客户端切换
   只替换 <main> 里的内容，顶栏与行情带完全不动，避免整页跳转导致
   行情带滚动重置、页眉重绘。

   关键设计：目标页的 <script> 不会被 DOMParser 执行，所以切换后由路由器
   用动态 import 挂载目标页入口模块，并调用其 renderPage()。

   路径处理：本文件里不做硬编码前缀，一切基于当前页面 URL 解析，
   站点放在域名根目录或子目录都能正常工作。
   ========================================================================== */

const PAGE_FILES = ['dash', 'strategy', 'history'];

// 各页入口模块：切页后由路由器挂载
const ENTRIES = {
  dash: () => import('./dash-v3.js'),
  strategy: () => import('./strategy.js'),
  history: () => import('./history.js'),
};

let bound = false;     // click / popstate 只绑一次
let mounted = null;    // 当前已挂载的页面

/** 取当前页面所在目录，末尾带 /（如 / 或 /boh/） */
function pageDir() {
  return location.pathname.replace(/[^/]*$/, '');
}

/** 把站内链接解析成可比较的绝对 URL；非这几个页面返回 null */
function resolvePage(rawHref) {
  let u;
  try {
    u = new URL(rawHref, location.href);
  } catch {
    return null;
  }
  if (u.origin !== location.origin) return null;
  if (u.pathname.replace(/[^/]*$/, '') !== pageDir()) return null;   // 必须同目录
  const file = u.pathname.slice(u.pathname.lastIndexOf('/') + 1).replace(/\.html$/, '');
  if (!PAGE_FILES.includes(file)) return null;
  return u;
}

/** 当前页标识（用于导航高亮与挂载） */
export function currentPage() {
  const base = location.pathname.split('/').pop().replace(/\.html$/, '');
  if (base === 'history' || base === 'strategy') return base;
  return 'dash';   // /、/dash、/index.html 都算总览
}

/** 挂载某个页面的入口模块（幂等：同一页面只挂一次） */
async function mount(file) {
  if (!ENTRIES[file] || mounted === file) return;
  mounted = file;
  const mod = await ENTRIES[file]();
  if (mod && typeof mod.renderPage === 'function') {
    await mod.renderPage();
  }
}

/** 把 <main> 换成目标页的内容，并挂载目标页入口 */
async function swapTo(href, { push = true } = {}) {
  const currentMain = document.getElementById('main');
  if (!currentMain) { location.href = href; return; }

  // fetch 用相对路径，兼容子目录部署
  const file = new URL(href, location.href).pathname.split('/').pop();
  const fetchUrl = file + new URL(href, location.href).search;

  let html;
  try {
    const res = await fetch(fetchUrl);
    if (!res.ok) throw new Error(String(res.status));
    html = await res.text();
  } catch {
    location.href = href;   // 取不到就直接跳转，保证可用
    return;
  }

  const doc = new DOMParser().parseFromString(html, 'text/html');
  const nextMain = doc.querySelector('main');
  if (!nextMain) { location.href = href; return; }

  if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
  currentMain.replaceWith(nextMain);

  const t = doc.querySelector('title');
  if (t) document.title = t.textContent;

  if (push) history.pushState({ boh: true }, '', href);

  await mount(file.replace(/\.html$/, '') || 'dash');
}

/** 拦截站内页面之间的链接点击与前进后退；入口页调用一次即可 */
export function initRouter() {
  if (!bound) {
    bound = true;

    document.addEventListener('click', ev => {
      const a = ev.target && ev.target.closest && ev.target.closest('a');
      if (!a) return;

      const href = a.getAttribute('href');
      if (!href) return;
      if (a.target === '_blank' || a.hasAttribute('download')) return;
      if (ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey || ev.button !== 0) return;

      const u = resolvePage(href);
      if (!u) return;                                   // 不是这几个页面，交给浏览器
      if (u.pathname === location.pathname) return;     // 已在该页

      ev.preventDefault();
      swapTo(href).catch(err => console.error('[BOH] 切页失败', err));
    });

    window.addEventListener('popstate', () => {
      const base = location.pathname.split('/').pop().replace(/\.html$/, '') || 'dash';
      if (PAGE_FILES.includes(base)) {
        swapTo(base + location.search, { push: false })
          .catch(err => console.error('[BOH] 切页失败', err));
      }
    });
  }

  // 直接打开页面时也由路由器挂载当前页入口
  return mount(currentPage());
}

export { swapTo };
