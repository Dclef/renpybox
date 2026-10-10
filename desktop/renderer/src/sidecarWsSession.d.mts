export type SidecarWsStatus = 'connecting' | 'open' | 'closed';

export const RECONNECT_BASE_MS: number;
export const RECONNECT_MAX_MS: number;

export interface SidecarSocket {
  readyState: number;
  close: () => void;
  // 与浏览器 WebSocket 回调签名兼容（this/Event 差异用宽松函数类型吞掉）。
  onopen: ((...args: never[]) => void) | null;
  onmessage: ((...args: never[]) => void) | null;
  onclose: ((...args: never[]) => void) | null;
  onerror: ((...args: never[]) => void) | null;
}

export interface SidecarClock {
  setTimeout: (fn: () => void, ms: number) => unknown;
  clearTimeout: (id: unknown) => void;
}

export interface SidecarWsSession {
  dispose(): void;
  getSocket(): SidecarSocket | null;
  isDisposed(): boolean;
}

export function createSidecarWsSession(options: {
  url: string;
  createSocket: (url: string) => SidecarSocket;
  clock?: SidecarClock;
  reconnectBaseMs?: number;
  reconnectMaxMs?: number;
  onStatus?: (status: SidecarWsStatus) => void;
  onEvent?: (message: unknown) => void;
  onJob?: (message: unknown) => void;
}): SidecarWsSession;
