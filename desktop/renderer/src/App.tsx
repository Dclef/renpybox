import { useEffect, useRef } from 'react';
import { useRowsSocket } from './useRowsSocket';
import { VirtualTable } from './VirtualTable';
import { getLongTasks, probeResponsiveness, resetLongTasks, sampleFps } from './perf';

declare global {
  interface Window {
    renpy?: { sidecar(): Promise<unknown>; platform: string; versions: Record<string, string> };
    /** perf-gate.js 无头验收用的自动化入口 */
    __renpy?: {
      ready: boolean;
      loadRows: (total?: number) => void;
      startJob: (total?: number, concurrency?: number) => void;
      metrics: () => Record<string, unknown>;
      scrollTo: (offset: number) => void;
    };
  }
}

type Verdict = 'ok' | 'bad' | '';

interface Live {
  fps: number;
  minFps: number;
  longTasks: number;
  maxBlockMs: number;
  connected: boolean;
  jobDone: number;
  jobTotal: number;
  jobRunning: boolean;
}

export default function App() {
  const { connected, rows, rowsStats, job, loadRows, startJob, cancelJob } = useRowsSocket();
  const cells = useRef<Record<string, HTMLSpanElement | null>>({});

  // 性能数据放可变对象 + 直接写 DOM，绝不进 state。
  // 早期版本每 500ms setState 一次，实测把滚动帧率从 60 打到 48——
  // 测量工具自己成了瓶颈，这是「UI 线程 16ms 预算」的第一课。
  const live = useRef<Live>({
    fps: 0,
    minFps: 0,
    longTasks: 0,
    maxBlockMs: 0,
    connected: false,
    jobDone: 0,
    jobTotal: 0,
    jobRunning: false,
  });

  const paint = () => {
    const c = cells.current;
    const put = (k: string, v: string, verdict: Verdict = '') => {
      const el = c[k];
      if (!el) return;
      if (el.textContent !== v) el.textContent = v;
      const cls = 'm-value' + (verdict ? ' ' + verdict : '');
      if (el.className !== cls) el.className = cls;
    };
    const L = live.current;
    put('sidecar', L.connected ? '已连接' : '未连接', L.connected ? 'ok' : 'bad');
    put('rows', String(rowsStats.received));
    put(
      'firstPaint',
      rowsStats.firstPaintMs ? `${Math.round(rowsStats.firstPaintMs)}ms` : '—',
      rowsStats.firstPaintMs ? (rowsStats.firstPaintMs < 300 ? 'ok' : 'bad') : '',
    );
    put('push', rowsStats.elapsedMs ? `${rowsStats.elapsedMs}ms` : '—');
    put('fps', `${L.fps}fps`, L.fps >= 55 ? 'ok' : 'bad');
    put('minFps', `${L.minFps}fps`, L.minFps >= 50 ? 'ok' : 'bad');
    put('longTasks', String(L.longTasks), L.longTasks === 0 ? 'ok' : 'bad');
    put('block', `${Math.round(L.maxBlockMs)}ms`, L.maxBlockMs < 50 ? 'ok' : 'bad');
    put('job', L.jobTotal ? `${L.jobDone}/${L.jobTotal}` : '—', L.jobRunning ? '' : 'ok');
  };

  useEffect(() => {
    resetLongTasks();
    const stop = sampleFps((fps) => {
      const L = live.current;
      L.fps = fps;
      L.minFps = L.minFps === 0 ? fps : Math.min(L.minFps, fps);
      const lt = getLongTasks();
      L.longTasks = lt.longTasks;
      L.maxBlockMs = lt.maxBlockMs;
      paint();
    });
    const timer = setInterval(paint, 250);
    return () => {
      stop();
      clearInterval(timer);
    };
  }, []);

  // 数据与任务状态变化时同步进 live，供无障碍文本与门禁读取
  useEffect(() => {
    const L = live.current;
    L.connected = connected;
    L.jobDone = job.done;
    L.jobTotal = job.total;
    L.jobRunning = job.running;
    paint();
  }, [connected, rowsStats.received, job.done, job.running]);

  const loadRef = useRef(loadRows);
  const jobRef = useRef(startJob);
  loadRef.current = loadRows;
  jobRef.current = startJob;

  // 自动化入口，供 perf-gate 无头驱动
  useEffect(() => {
    window.__renpy = {
      ready: true,
      loadRows: (total?: number) => loadRef.current(total),
      startJob: (total?: number, concurrency?: number) => jobRef.current(total, concurrency),
      scrollTo: (offset: number) => {
        const el = document.querySelector('.table-body') as HTMLElement | null;
        if (el) el.scrollTop = offset;
      },
      metrics: () => {
        const lt = getLongTasks();
        return {
          connected: live.current.connected,
          rowsReceived: rowsStats.received,
          rowsTotal: rowsStats.total,
          rowsDone: rowsStats.done,
          rowsElapsedMs: rowsStats.elapsedMs,
          firstPaintMs: rowsStats.firstPaintMs,
          fps: live.current.fps,
          minFps: live.current.minFps,
          jobDone: live.current.jobDone,
          jobTotal: live.current.jobTotal,
          jobRunning: live.current.jobRunning,
          longTasks: lt.longTasks,
          maxBlockMs: lt.maxBlockMs,
          domRows: document.querySelectorAll('.row-wrap').length,
        };
      },
    };
  }, [rowsStats]);

  useEffect(() => {
    probeResponsiveness(1500);
  }, [rowsStats.received]);

  return (
    <div className="app">
      <header className="bar">
        <div className="brand">RenpyBox · Electron 壳 spike（React 版）</div>
        <div className="actions">
          <button onClick={() => loadRows()}>加载 10 万行</button>
          <button onClick={() => startJob()}>启动高并发任务</button>
          <button onClick={cancelJob} disabled={!job.running}>
            取消任务
          </button>
        </div>
      </header>

      <section className="hud">
        <Metric label="sidecar" cell="sidecar" cells={cells} />
        <Metric label="已接收行" cell="rows" cells={cells} />
        <Metric label="首屏" cell="firstPaint" cells={cells} />
        <Metric label="推送耗时" cell="push" cells={cells} />
        <Metric label="帧率" cell="fps" cells={cells} />
        <Metric label="最低帧率" cell="minFps" cells={cells} />
        <Metric label="长任务" cell="longTasks" cells={cells} />
        <Metric label="最长阻塞" cell="block" cells={cells} />
        <Metric label="任务进度" cell="job" cells={cells} />
      </section>

      <VirtualTable rows={rows} />
    </div>
  );
}

function Metric({
  label,
  cell,
  cells,
}: {
  label: string;
  cell: string;
  cells: React.RefObject<Record<string, HTMLSpanElement | null>>;
}) {
  return (
    <div className="metric">
      <span className="m-label">{label}</span>
      <span className="m-value" ref={(el) => { cells.current[cell] = el; }}>
        —
      </span>
    </div>
  );
}