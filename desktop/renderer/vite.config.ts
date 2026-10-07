import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

const SIDECAR_PORT = Number(process.env.RENPYBOX_SIDECAR_PORT || 9712);
const WEB_PORT = Number(process.env.RENPYBOX_WEB_PORT || 5173);

export default defineConfig({
  root: path.resolve(import.meta.dirname),
  plugins: [react()],
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
    outDir: path.resolve(import.meta.dirname, '..', 'dist'),
    emptyOutDir: true,
  },
});