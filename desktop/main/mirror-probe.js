/**
 * 更新镜像测速（纯 ESM，可注入 fetchImpl；不 import electron）。
 * 每个前缀对固定 GitHub Release 资产发 Range GET，并发测量延迟与速率。
 */

export const DEFAULT_PROBE_ASSET = 'https://github.com/dclef/renpybox/releases/download/v0.9.2/RenpyBox-0.9.2-x64.exe';
const PROBE_RANGE = 'bytes=0-262143';
const DEFAULT_TIMEOUT_MS = 8000;

/** 空前缀表示直连资产本身。 */
export function probeTargetUrl(prefix, assetUrl = DEFAULT_PROBE_ASSET) {
  const head = String(prefix ?? '');
  return head ? `${head}${assetUrl}` : assetUrl;
}

async function drainBody(response) {
  const body = response?.body;
  if (body && typeof body.getReader === 'function') {
    const reader = body.getReader();
    let bytes = 0;
    try {
      while (true) {
        const chunk = await reader.read();
        if (chunk.done) break;
        bytes += chunk.value?.byteLength || 0;
      }
    } finally {
      try { reader.releaseLock?.(); } catch { /* 读完即释放 */ }
    }
    return bytes;
  }
  if (typeof response?.arrayBuffer === 'function') {
    const buffer = await response.arrayBuffer();
    return buffer.byteLength;
  }
  try { await body?.cancel?.(); } catch { /* 无 body 时忽略 */ }
  return 0;
}

async function probeOne(prefix, { fetchImpl, assetUrl, timeoutMs, signal }) {
  const started = Date.now();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const onAbort = () => controller.abort();
  if (signal) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener('abort', onAbort, { once: true });
  }
  try {
    const response = await fetchImpl(probeTargetUrl(prefix, assetUrl), {
      method: 'GET',
      headers: { Range: PROBE_RANGE },
      signal: controller.signal,
    });
    const latencyMs = Math.max(0, Date.now() - started);
    if (response.status !== 200 && response.status !== 206) {
      try { await response.body?.cancel?.(); } catch { /* 丢弃错误响应体 */ }
      return { prefix: String(prefix ?? ''), latencyMs, bytesPerSec: 0, ok: false };
    }
    const bytes = await drainBody(response);
    const elapsed = Math.max(1, Date.now() - started);
    const ok = bytes > 0;
    return {
      prefix: String(prefix ?? ''),
      latencyMs,
      bytesPerSec: ok ? Math.round((bytes * 1000) / elapsed) : 0,
      ok,
    };
  } catch {
    return { prefix: String(prefix ?? ''), latencyMs: timeoutMs, bytesPerSec: 0, ok: false };
  } finally {
    clearTimeout(timer);
    if (signal) signal.removeEventListener('abort', onAbort);
  }
}

/** 并发探测全部前缀；单节点失败不影响其它节点。 */
export async function probeMirrors(prefixes, options = {}) {
  const list = Array.isArray(prefixes) ? prefixes : [];
  const fetchImpl = options.fetchImpl;
  if (typeof fetchImpl !== 'function') {
    throw new TypeError('fetchImpl required');
  }
  const assetUrl = options.assetUrl || DEFAULT_PROBE_ASSET;
  const timeoutMs = Number(options.timeoutMs) > 0 ? Number(options.timeoutMs) : DEFAULT_TIMEOUT_MS;
  return Promise.all(list.map((prefix) => probeOne(prefix, {
    fetchImpl,
    assetUrl,
    timeoutMs,
    signal: options.signal,
  })));
}
