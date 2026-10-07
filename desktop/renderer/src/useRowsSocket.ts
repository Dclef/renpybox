import { useCallback, useEffect, useRef, useState } from 'react';
import type { JobStats, Row, RowsStats } from './types';

const WS_URL = `ws://${location.host}/ws`;
const BATCH = 500;
const TOTAL = 100_000;

/**
 * WebSocket 单连接客户端（对齐 DeepSeek 的 ws 方案）：
 * 数据流、任务进度、控制指令共用一条连接，REST 不参与流式。
 *
 * 反卡顿要点：收到的批次先进缓冲区，再由 requestAnimationFrame 统一 flush，
 * 绝不在每条消息到达时直接 setState。
 */
export function useRowsSocket() {
  const [rows, setRows] = useState<Row[]>([]);
  const [rowsStats, setRowsStats] = useState<RowsStats>({
    received: 0,
    total: 0,
    done: false,
    elapsedMs: null,
    firstPaintMs: null,
  });
  const [job, setJob] = useState<JobStats>({
    jobId: null,
    done: 0,
    total: 0,
    running: false,
    finished: false,
  });
  const [connected, setConnected] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const pendingRef = useRef<string[]>([]);
  const bufferRef = useRef<Row[]>([]);
  const rafRef = useRef(0);
  const firstPaintRef = useRef<number | null>(null);
  const loadStartRef = useRef<number>(0);
  const pendingTotalRef = useRef(0);

  const flush = useCallback(() => {
    rafRef.current = 0;
    const pending = bufferRef.current;
    if (pending.length === 0) return;
    bufferRef.current = [];

    // 首屏埋点：首批数据落地的瞬间
    if (firstPaintRef.current === null) {
      firstPaintRef.current = performance.now() - loadStartRef.current;
    }

    setRows((prev) => {
      const next = prev.concat(pending);
      setRowsStats((s) => ({ ...s, received: next.length, total: pendingTotalRef.current }));
      return next;
    });
  }, []);

  const schedule = useCallback(() => {
    if (rafRef.current === 0) rafRef.current = requestAnimationFrame(flush);
  }, [flush]);

  /** 连接未就绪时先排队，避免 CONNECTING 状态下 send 抛错 */
  const send = useCallback((msg: unknown) => {
    const payload = JSON.stringify(msg);
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(payload);
    else pendingRef.current.push(payload);
  }, []);

  useEffect(() => {
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      const queued = pendingRef.current;
      pendingRef.current = [];
      for (const payload of queued) ws.send(payload);
    };
    ws.onclose = () => setConnected(false);

    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data as string);
      switch (msg.type) {
        case 'rows': {
          const incoming = msg.rows as Row[];
          bufferRef.current.push(...incoming);
          pendingTotalRef.current = msg.total;
          schedule();
          break;
        }
        case 'rows_done': {
          setRowsStats((s) => ({
            ...s,
            done: true,
            total: msg.total,
            received: s.received,
            elapsedMs: msg.elapsed_ms,
            firstPaintMs: firstPaintRef.current,
          }));
          break;
        }
        case 'job_started':
          setJob({ jobId: msg.job_id, done: 0, total: 0, running: true, finished: false });
          break;
        case 'job_progress':
          setJob((j) => ({ ...j, done: msg.done, total: msg.total }));
          break;
        case 'job_done':
          setJob((j) => ({ ...j, done: msg.done, total: msg.total, running: false, finished: true }));
          break;
        case 'job_cancelled':
          setJob((j) => ({ ...j, running: false, finished: true }));
          break;
        default:
          break;
      }
    };

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      ws.close();
    };
  }, [schedule]);

  const loadRows = useCallback((total = TOTAL, batch = BATCH) => {
    bufferRef.current = [];
    firstPaintRef.current = null;
    loadStartRef.current = performance.now();
    setRows([]);
    setRowsStats({ received: 0, total, done: false, elapsedMs: null, firstPaintMs: null });
    send({ type: 'load_rows', total, batch });
  }, [send]);

  const startJob = useCallback((total = 800, concurrency = 8) => {
    setJob({ jobId: null, done: 0, total, running: true, finished: false });
    send({ type: 'start_job', total, concurrency });
  }, [send]);

  const cancelJob = useCallback(() => {
    send({ type: 'cancel_job', job_id: job.jobId });
  }, [job.jobId, send]);

  return { connected, rows, rowsStats, job, loadRows, startJob, cancelJob };
}