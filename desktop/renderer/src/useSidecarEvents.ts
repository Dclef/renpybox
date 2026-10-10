/**
 * sidecar WebSocket 单连接。
 *
 * 设计约束（来自重构计划）：整个应用只允许一条 WS。多个 hook 各自建连会让
 * 每条事件被广播 N 次，十万行级别的进度推送会成倍放大。
 *
 * 连接生命周期在 sidecarWsSession.mjs：每个 effect 实例自带 current，
 * StrictMode cleanup 不会让旧 socket 的 onclose 清掉新连接。
 */

import { useEffect, useRef } from 'react';
import type { WsEventMessage, WsJobMessage } from './types';
import { createSidecarWsSession, type SidecarSocket } from './sidecarWsSession.mjs';

export type WsStatus = 'connecting' | 'open' | 'closed';

type EventHandler = (message: WsEventMessage) => void;
type StatusHandler = (status: WsStatus) => void;
type JobHandler = (message: WsJobMessage) => void;

function socketUrl(): string {
  const { protocol, host } = window.location;
  // 打包版是 file:// 源，没有 host；此时 sidecar 固定在回环地址。
  if (protocol === 'file:' || !host) return 'ws://127.0.0.1:9712/ws';
  return `${protocol === 'https:' ? 'wss:' : 'ws:'}//${host}/ws`;
}

/**
 * 订阅 sidecar 事件流。
 *
 * 断线后自动重连，退避到 10s 封顶。handlers 经 ref 更新，不因回调变化重连。
 * 组件卸载 dispose 当前会话；StrictMode 双挂载各自一条短命会话，稳定后只留一条。
 */
export function useSidecarEvents(onEvent: EventHandler, onStatus?: StatusHandler, onJob?: JobHandler): void {
  const onEventRef = useRef(onEvent);
  const onStatusRef = useRef(onStatus);
  const onJobRef = useRef(onJob);

  onEventRef.current = onEvent;
  onStatusRef.current = onStatus;
  onJobRef.current = onJob;

  useEffect(() => {
    const session = createSidecarWsSession({
      url: socketUrl(),
      createSocket: (url) => new WebSocket(url) as unknown as SidecarSocket,
      onStatus: (status) => onStatusRef.current?.(status),
      onEvent: (message) => onEventRef.current(message as unknown as WsEventMessage),
      onJob: (message) => onJobRef.current?.(message as unknown as WsJobMessage),
    });

    return () => {
      session.dispose();
    };
  }, []);
}

/**
 * 命令栏需要即时反馈时不要开第二条连接 —— 快照走 HTTP（api.ts 的
 * getTranslationState 等），事件流仍然只有上面那一条。
 */
