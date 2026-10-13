import { defineConfig } from 'vite';
import { resolve } from 'node:path';

export default defineConfig({
  root: '.',
  // 相对路径：绑定到域名根目录或子目录都能正常加载资源
  base: './',

  build: {
    outDir: 'dist',
    emptyOutDir: true,
    // 两个页面各自作为入口，静态托管时都能直接访问。
    // 根目录由 public/_redirects 代理到 /dash.html（状态码 200，
    // 是就地渲染而非跳转），所以不需要单独的 index.html 跳转页。
    rollupOptions: {
      input: {
        dash: resolve(__dirname, 'dash.html'),
        strategy: resolve(__dirname, 'strategy.html'),
        history: resolve(__dirname, 'history.html'),
      },
    },
  },

  server: {
    port: 5273,
    host: '127.0.0.1',
    strictPort: true,
    watch: {
      // 排除编辑器 / 脚本的原子写入临时文件：Windows 下监听这些会 EBUSY 崩溃
      ignored: [
        '**/scripts/**',
        '**/*.py',
        '**/.*.tmpdir/**',
        '**/*.tmp',
        '**/.fetch_data*',
      ],
    },
  },
});
