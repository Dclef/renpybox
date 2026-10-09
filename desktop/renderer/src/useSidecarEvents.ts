/**
 * sidecar WebSocket 单连接。
 *
 * 设计约束（来自重构计划）：整个应用只允许一条 WS。多个 hook 各自建连会让
 * 每条事件被广播 N 次，十万行级别的进度推送会成倍放大。
 */

import { useEffect, useRef } from 'react';
import type { WsEventMessage, WsJobMessage, WsMessage } from './types';

export type WsStatus = 'connecting' | 'open' | 'closed';

type EventHandler = (message: WsEventMessage) => void;
type StatusHandler = (status: WsStatus) => void;
type JobHandler = (message: WsJobMessage) => void;

const RECONNECT_BASE_MS = 500;
const RECONNECT_MAX_MS = 10_000;

function socketUrl(): string {
  const { protocol, host } = window.location;
  // 打包版是 file:// 源，没有 host；此时 sidecar 固定在回环地址。
  if (protocol === 'file:' || !host) return 'ws://127.0.0.1:9712/ws';
  return `${protocol === 'https:' ? 'wss:' : 'ws:'}//${host}/ws`;
}

/**
 * 订阅 sidecar 事件流。
 *
 * 断线后自动重连，退避到 RECONNECT_MAX_MS 封顶。组件卸载或 handlers 变化时
 * 重新订阅同一条连接，不会额外开连接。
 */
export function useSidecarEvents(onEvent: EventHandler, onStatus?: StatusHandler, onJob?: JobHandler): void {
  const onEventRef = useRef(onEvent);
  const onStatusRef = useRef(onStatus);
  const onJobRef = useRef(onJob);
  const socketRef = useRef<WebSocket | null>(null);

  onEventRef.current = onEvent;
  onStatusRef.current = onStatus;
  onJobRef.current = onJob;

  useEffect(() => {
    let disposed = false;
    let attempt = 0;
    let timer: number | undefined;

    const connect = () => {
      if (disposed) return;
      const socket = new WebSocket(socketUrl());
      socketRef.current = socket;
      onStatusRef.current?.('connecting');

      socket.onopen = () => {
        attempt = 0;
        onStatusRef.current?.('open');
      };

      socket.onmessage = (raw: MessageEvent<string>) => {
        let message: WsMessage;
        try {
          message = JSON.parse(raw.data) as WsMessage;
        } catch {
          return;
        }
        if (message.type === 'event') {
          onEventRef.current(message as WsEventMessage);
        } else if (message.type === 'job') {
          onJobRef.current?.(message as WsJobMessage);
        }
      };

      socket.onclose = () => {
        socketRef.current = null;
        if (disposed) return;
        onStatusRef.current?.('closed');
        // 指数退避；sidecar 重启后自动接回，不让用户手动重开应用。
        attempt += 1;
        const delay = Math.min(RECONNECT_BASE_MS * 2 ** (attempt - 1), RECONNECT_MAX_MS);
        timer = window.setTimeout(connect, delay);
      };

      socket.onerror = () => socket.close();
    };

    connect();

    return () => {
      disposed = true;
      if (timer !== undefined) window.clearTimeout(timer);
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, []);
}

/**
 * 命令栏需要即时反馈时不要开第二条连接 —— 快照走 HTTP（api.ts 的
 * getTranslationState 等），事件流仍然只有上面那一条。
 */
