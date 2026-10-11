/* ==========================================================================
   BOH — 主题切换
   三种状态：light / dark / auto（跟随系统）。
   切换时写 localStorage 并更新 <html data-theme>；按钮文字显示当前状态。
   ========================================================================== */

const KEY = 'boh-theme';

export function resolve(pref) {
  if (pref === 'light' || pref === 'dark') return pref;
  return matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}

export function currentPref() {
  try {
    const v = localStorage.getItem(KEY);
    if (v === 'light' || v === 'dark' || v === 'auto') return v;
  } catch { /* 无隐私模式下的 localStorage，忽略 */ }
  return 'auto';
}

export function apply(pref) {
  const theme = resolve(pref);
  document.documentElement.setAttribute('data-theme', theme);
  document.querySelectorAll('[data-theme-toggle]').forEach(btn => {
    const label = pref === 'auto' ? `跟随系统 · ${theme === 'light' ? '日' : '夜'}` : (pref === 'light' ? '日间' : '夜间');
    btn.textContent = label;
    btn.setAttribute('aria-label', `显示模式：${label}。点击切换`);
    btn.title = `当前：${label}（点击切换日间 / 夜间 / 跟随系统）`;
    btn.dataset.pref = pref;
  });
  return theme;
}

export function cycle() {
  const order = ['auto', 'light', 'dark'];
  const next = order[(order.indexOf(currentPref()) + 1) % order.length];
  try { localStorage.setItem(KEY, next); } catch { /* 忽略 */ }
  apply(next);
  return next;
}

export function initTheme() {
  apply(currentPref());

  document.querySelectorAll('[data-theme-toggle]').forEach(btn => {
    btn.addEventListener('click', () => cycle());
  });

  // 自动模式下跟随系统变化
  matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => {
    if (currentPref() === 'auto') apply('auto');
  });
}
