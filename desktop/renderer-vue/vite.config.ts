import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import path from 'node:path';

const SIDECAR_PORT = Number(process.env.RENPYBOX_SIDECAR_PORT || 9712);
const WEB_PORT = Number(process.env.RENPYBOX_WEB_PORT || 5274);

// 与 React 版共用同一个 sidecar，只换渲染层，用来隔离框架变量
export default defineConfig({
  root: path.resolve(import.meta.dirname),
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port: WEB_PORT,
    strictPort: true,
    proxy: {
      '/health': `http://127.0.0.1:${SIDECAR_PORT}`,
      '/ws': { target: `ws://127.0.0.1:${SIDECAR_PORT}`, ws: true },
    },
  },
  build: {
    outDir: path.resolve(import.meta.dirname, '..', 'dist-vue'),
    emptyOutDir: true,
  },
});