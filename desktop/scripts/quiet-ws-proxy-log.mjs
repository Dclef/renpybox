/**
 * Vite6 自带 proxyReqWs 会给 downstream socket error 打整段 stack。
 * 浏览器正常关闭（尤其 Windows）常见 ECONNABORTED / EPIPE / ECONNRESET，
 * 属于「客户端已断」而非 sidecar 挂了。仅窄化这类 ws proxy socket 日志。
 */

const QUIET_CODES = new Set(['ECONNABORTED', 'EPIPE', 'ECONNRESET']);

/**
 * @param {unknown} msg
 * @param {{ code?: string } | undefined | null} err
 * @returns {boolean}
 */
export function shouldQuietWsProxySocketError(msg, err) {
  const code = err && typeof err === 'object' ? err.code : undefined;
  if (!code || !QUIET_CODES.has(code)) return false;
  const text = String(msg ?? '');
  // 只压「ws proxy socket error」（浏览器侧 socket）；保留 ws proxy error / ECONNREFUSED。
  return text.includes('ws proxy socket error');
}

/**
 * @param {unknown} msg
 * @param {{ code?: string } | undefined | null} err
 * @returns {string}
 */
export function quietWsProxySocketNote(msg, err) {
  const code = err && typeof err === 'object' && err.code ? err.code : 'unknown';
  return `WS 代理：浏览器已关闭连接（${code}，可忽略）`;
}
