import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';
import {
  quietWsProxySocketNote,
  shouldQuietWsProxySocketError,
} from '../scripts/quiet-ws-proxy-log.mjs';

const SIDECAR_PORT = Number(process.env.RENPYBOX_SIDECAR_PORT || 9712);
const WEB_PORT = Number(process.env.RENPYBOX_WEB_PORT || 5173);

/** 窄化 Vite 默认「ws proxy socket error」堆栈：仅已关闭客户端连接。 */
function quietClosedWsProxySocket(): Plugin {
  return {
    name: 'quiet-closed-ws-proxy-socket',
    configureServer(server) {
      const original = server.config.logger.error.bind(server.config.logger);
      server.config.logger.error = (msg, options) => {
        const err = options && typeof options === 'object'
          ? (options as { error?: { code?: string } }).error
          : undefined;
        if (shouldQuietWsProxySocketError(msg, err ?? null)) {
          server.config.logger.info(quietWsProxySocketNote(msg, err ?? null), {
            timestamp: true,
          });
          return;
        }
        return original(msg, options);
      };
    },
  };
}

export default defineConfig(({ command }) => ({
  base: command === 'build' ? './' : '/',
  root: path.resolve(import.meta.dirname),
  plugins: [react(), quietClosedWsProxySocket()],
  server: {
    host: '127.0.0.1',
    port: WEB_PORT,
    strictPort: true,
    proxy: {
      '/health': `http://127.0.0.1:${SIDECAR_PORT}`,
      // 真实业务接口。开发时走 vite 代理；打包后 loadFile 源是 file://，
      // 请求要落到 api.ts 里算出的绝对地址。
      '/api': `http://127.0.0.1:${SIDECAR_PORT}`,
      '/ws': { target: `ws://127.0.0.1:${SIDECAR_PORT}`, ws: true },
    },
  },
  build: {
    outDir: path.resolve(import.meta.dirname, '..', 'dist'),
    emptyOutDir: true,
  },
}));
