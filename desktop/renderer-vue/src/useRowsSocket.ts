import { onUnmounted, reactive, ref, shallowRef } from 'vue';

export interface Row {
  id: number;
  key: string;
  source: string;
  target: string;
  status: 'pending' | 'translated' | 'reviewed';
}

const WS_URL = `ws://${location.host}/ws`;
const BATCH = 500;
const TOTAL = 100_000;

/**
 * WebSocket 单连接客户端。逻辑与 React 版逐行对应：
 * 批次先进缓冲区，再由 requestAnimationFrame 统一 flush。
 */
export function useRowsSocket() {
  const rows = shallowRef<Row[]>([]);
  const connected = ref(false);
  const rowsStats = reactive({
    received: 0,
    total: 0,
    done: false,
    elapsedMs: null as number | null,
    firstPaintMs: null as number | null,
  });
  const job = reactive({ jobId: null as string | null, done: 0, total: 0, running: false, finished: false });

  const wsRef = { value: null as WebSocket | null };
  const pending: string[] = [];
  let buffer: Row[] = [];
  let rafId = 0;
  let firstPaint: number | null = null;
  let loadStart = 0;
  let pendingTotal = 0;

  const flush = () => {
    rafId = 0;
    if (buffer.length === 0) return;
    const pendingRows = buffer;
    buffer = [];
    if (firstPaint === null) firstPaint = performance.now() - loadStart;
    rows.value = rows.value.concat(pendingRows);
    rowsStats.received = rows.value.length;
    rowsStats.total = pendingTotal;
  };

  const schedule = () => {
    if (rafId === 0) rafId = requestAnimationFrame(flush);
  };

  const send = (msg: unknown) => {
    const payload = JSON.stringify(msg);
    const ws = wsRef.value;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(payload);
    else pending.push(payload);
  };

  const ws = new WebSocket(WS_URL);
  wsRef.value = ws;
  ws.onopen = () => {
    connected.value = true;
    const queued = pending.splice(0, pending.length);
    for (const p of queued) ws.send(p);
  };
  ws.onclose = () => {
    connected.value = false;
  };
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data as string);
    switch (msg.type) {
      case 'rows':
        buffer.push(...(msg.rows as Row[]));
        pendingTotal = msg.total;
        schedule();
        break;
      case 'rows_done':
        rowsStats.done = true;
        rowsStats.total = msg.total;
        rowsStats.elapsedMs = msg.elapsed_ms;
        rowsStats.firstPaintMs = firstPaint;
        break;
      case 'job_started':
        job.jobId = msg.job_id;
        job.done = 0;
        job.total = 0;
        job.running = true;
        job.finished = false;
        break;
      case 'job_progress':
        job.done = msg.done;
        job.total = msg.total;
        break;
      case 'job_done':
        job.done = msg.done;
        job.total = msg.total;
        job.running = false;
        job.finished = true;
        break;
      case 'job_cancelled':
        job.running = false;
        job.finished = true;
        break;
      default:
        break;
    }
  };

  onUnmounted(() => {
    if (rafId) cancelAnimationFrame(rafId);
    ws.close();
  });

  const loadRows = (total = TOTAL, batch = BATCH) => {
    buffer = [];
    firstPaint = null;
    loadStart = performance.now();
    rows.value = [];
    rowsStats.received = 0;
    rowsStats.total = total;
    rowsStats.done = false;
    rowsStats.elapsedMs = null;
    rowsStats.firstPaintMs = null;
    send({ type: 'load_rows', total, batch });
  };

  const startJob = (total = 800, concurrency = 8) => {
    job.jobId = null;
    job.done = 0;
    job.total = total;
    job.running = true;
    job.finished = false;
    send({ type: 'start_job', total, concurrency });
  };

  const cancelJob = () => send({ type: 'cancel_job', job_id: job.jobId });

  return { connected, rows, rowsStats, job, loadRows, startJob, cancelJob };
}