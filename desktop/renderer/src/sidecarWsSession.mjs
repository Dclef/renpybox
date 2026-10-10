/**
 * sidecar WebSocket 会话（无 React / 无 TypeScript）。
 *
 * 每个会话自带 current socket，旧 socket 的 onclose 不会清掉新会话的引用。
 * StrictMode 的 mount→cleanup→remount 各自 dispose，互不踩踏。
 */

export const RECONNECT_BASE_MS = 500;
export const RECONNECT_MAX_MS = 10_000;

/**
 * @typedef {'connecting' | 'open' | 'closed'} WsStatus
 * @typedef {{
 *   readyState: number,
 *   close: () => void,
 *   onopen: ((ev?: unknown) => void) | null,
 *   onmessage: ((ev: { data: string }) => void) | null,
 *   onclose: (() => void) | null,
 *   onerror: (() => void) | null,
 * }} SidecarSocket
 * @typedef {{
 *   setTimeout: (fn: () => void, ms: number) => unknown,
 *   clearTimeout: (id: unknown) => void,
 * }} SidecarClock
 */

/**
 * @param {{
 *   url: string,
 *   createSocket: (url: string) => SidecarSocket,
 *   clock?: SidecarClock,
 *   reconnectBaseMs?: number,
 *   reconnectMaxMs?: number,
 *   onStatus?: (status: WsStatus) => void,
 *   onEvent?: (message: object) => void,
 *   onJob?: (message: object) => void,
 * }} options
 */
export function createSidecarWsSession(options) {
  const clock = options.clock ?? {
    setTimeout: (fn, ms) => setTimeout(fn, ms),
    clearTimeout: (id) => clearTimeout(id),
  };
  const baseMs = options.reconnectBaseMs ?? RECONNECT_BASE_MS;
  const maxMs = options.reconnectMaxMs ?? RECONNECT_MAX_MS;

  let disposed = false;
  let attempt = 0;
  /** @type {unknown} */
  let timer;
  /** @type {SidecarSocket | null} */
  let current = null;

  const connect = () => {
    timer = undefined;
    if (disposed) return;
    const socket = options.createSocket(options.url);
    current = socket;
    options.onStatus?.('connecting');

    socket.onopen = () => {
      // 已 dispose 或已被更新的会话忽略晚到的 open。
      if (disposed || current !== socket) return;
      attempt = 0;
      options.onStatus?.('open');
    };

    socket.onmessage = (raw) => {
      if (disposed || current !== socket) return;
      let message;
      try {
        message = JSON.parse(raw.data);
      } catch {
        return;
      }
      if (message?.type === 'event') {
        options.onEvent?.(message);
      } else if (message?.type === 'job') {
        options.onJob?.(message);
      }
    };

    socket.onclose = () => {
      // 只接纳当前连接的第一次关闭，旧回调不得重复安排重连。
      if (disposed || current !== socket) return;
      current = null;
      options.onStatus?.('closed');
      attempt += 1;
      const delay = Math.min(baseMs * 2 ** (attempt - 1), maxMs);
      timer = clock.setTimeout(connect, delay);
    };

    socket.onerror = () => {
      if (disposed || current !== socket) return;
      socket.close();
    };
  };

  // 首次连接延后一轮，让 StrictMode 的同步清理直接撤销建连。
  timer = clock.setTimeout(connect, 0);

  return {
    dispose() {
      disposed = true;
      if (timer !== undefined) {
        clock.clearTimeout(timer);
        timer = undefined;
      }
      const socket = current;
      current = null;
      // 摘掉回调再关闭，释放消息订阅并忽略晚到通知。
      if (socket) {
        socket.onopen = null;
        socket.onmessage = null;
        socket.onclose = null;
        socket.onerror = null;
        socket.close();
      }
    },
    /** @returns {SidecarSocket | null} */
    getSocket() {
      return current;
    },
    isDisposed() {
      return disposed;
    },
  };
}
