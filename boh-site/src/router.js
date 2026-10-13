/* ==========================================================================
   BOH — 两页之间的客户端切换
   只替换 <main> 里的内容，顶栏与行情带完全不动，
   避免整页跳转导致行情带滚动重置、页眉重绘。

   路径处理：本文件里不做任何硬编码前缀，一切基于当前页面 URL 解析，
   因此站点放在域名根目录或子目录都能正常工作。
   ========================================================================== */

const PAGE_FILES = ['dash', 'strategy', 'history'];   // 只比主干名，.html 后缀可有可无

/** 取当前页面所在目录，末尾带 /（如 / 或 /boh/） */
function pageDir() {
  return location.pathname.replace(/[^/]*$/, '');
}

/** 把站内链接解析成可比较的绝对 URL；非站内页面返回 null */
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

/** 把 <main> 换成目标页的内容 */
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

  // 导航高亮：按解析后的文件是否一致来判断
  const target = new URL(href, location.href).pathname;
  document.querySelectorAll('.head-nav a').forEach(a => {
    const u = resolvePage(a.getAttribute('href'));
    a.toggleAttribute('aria-current', !!u && u.pathname === target);
  });

  if (push) history.pushState({ boh: true }, '', href);

  window.dispatchEvent(new CustomEvent('boh:navigate', { detail: { url: href } }));
}

/** 拦截站内两个页面之间的链接点击与前进后退 */
export function initRouter() {
  document.addEventListener('click', ev => {
    const a = ev.target && ev.target.closest && ev.target.closest('a');
    if (!a) return;

    const href = a.getAttribute('href');
    if (!href) return;
    if (a.target === '_blank' || a.hasAttribute('download')) return;
    if (ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey || ev.button !== 0) return;

    const u = resolvePage(href);
    if (!u) return;                                   // 不是这两个页面，交给浏览器
    if (u.pathname === location.pathname) return;     // 已在该页

    ev.preventDefault();
    swapTo(href);
  });

  window.addEventListener('popstate', () => {
    const file = location.pathname.split('/').pop().replace(/\.html$/, '');
    if (PAGE_FILES.includes(file)) {
      swapTo(file + location.search, { push: false });
    }
  });
}

export { swapTo };

/** 当前页标识（用于导航高亮） */
export function currentPage() {
  return location.pathname.includes('history') ? 'history' : 'dash';
}
