<script setup lang="ts">
import { onMounted, onUnmounted, reactive, watch } from 'vue';
import VirtualTable from './VirtualTable.vue';
import { useRowsSocket } from './useRowsSocket';
import { getLongTasks, probeResponsiveness, resetLongTasks, sampleFps } from './perf';

const { connected, rows, rowsStats, job, loadRows, startJob, cancelJob } = useRowsSocket();

const cells = new Map<string, HTMLElement>();
const setCell = (key: string, el: Element | null) => {
  if (el) cells.set(key, el as HTMLElement);
};

const live = reactive({
  fps: 0,
  minFps: 0,
  longTasks: 0,
  maxBlockMs: 0,
});

const put = (k: string, v: string, verdict = '') => {
  const el = cells.get(k);
  if (!el) return;
  if (el.textContent !== v) el.textContent = v;
  const cls = 'm-value' + (verdict ? ' ' + verdict : '');
  if (el.className !== cls) el.className = cls;
};

const paint = () => {
  put('sidecar', connected.value ? '已连接' : '未连接', connected.value ? 'ok' : 'bad');
  put('rows', String(rowsStats.received));
  put(
    'firstPaint',
    rowsStats.firstPaintMs ? `${Math.round(rowsStats.firstPaintMs)}ms` : '—',
    rowsStats.firstPaintMs ? (rowsStats.firstPaintMs < 300 ? 'ok' : 'bad') : '',
  );
  put('push', rowsStats.elapsedMs ? `${rowsStats.elapsedMs}ms` : '—');
  put('fps', `${live.fps}fps`, live.fps >= 55 ? 'ok' : 'bad');
  put('minFps', `${live.minFps}fps`, live.minFps >= 50 ? 'ok' : 'bad');
  put('longTasks', String(live.longTasks), live.longTasks === 0 ? 'ok' : 'bad');
  put('block', `${Math.round(live.maxBlockMs)}ms`, live.maxBlockMs < 50 ? 'ok' : 'bad');
  put('job', job.total ? `${job.done}/${job.total}` : '—', job.running ? '' : 'ok');
};

let stopFps: (() => void) | null = null;
let timer = 0;

onMounted(() => {
  resetLongTasks();
  stopFps = sampleFps((fps) => {
    live.fps = fps;
    live.minFps = live.minFps === 0 ? fps : Math.min(live.minFps, fps);
    const lt = getLongTasks();
    live.longTasks = lt.longTasks;
    live.maxBlockMs = lt.maxBlockMs;
    paint();
  });
  timer = window.setInterval(paint, 250);

  (window as any).__renpy = {
    ready: true,
    loadRows: (total?: number) => loadRows(total),
    startJob: (total?: number, concurrency?: number) => startJob(total, concurrency),
    scrollTo: (offset: number) => {
      const el = document.querySelector('.table-body') as HTMLElement | null;
      if (el) el.scrollTop = offset;
    },
    metrics: () => {
      const lt = getLongTasks();
      return {
        connected: connected.value,
        rowsReceived: rowsStats.received,
        rowsTotal: rowsStats.total,
        rowsDone: rowsStats.done,
        rowsElapsedMs: rowsStats.elapsedMs,
        firstPaintMs: rowsStats.firstPaintMs,
        fps: live.fps,
        minFps: live.minFps,
        jobDone: job.done,
        jobTotal: job.total,
        jobRunning: job.running,
        longTasks: lt.longTasks,
        maxBlockMs: lt.maxBlockMs,
        domRows: document.querySelectorAll('.row-wrap').length,
      };
    },
  };
});

onUnmounted(() => {
  stopFps?.();
  clearInterval(timer);
});

watch(() => rowsStats.received, () => {
  paint();
  probeResponsiveness(1500);
});
</script>

<template>
  <div class="app">
    <header class="bar">
      <div class="brand">RenpyBox · Electron 壳 spike（Vue 对照版）</div>
      <div class="actions">
        <button @click="loadRows()">加载 10 万行</button>
        <button @click="startJob()">启动高并发任务</button>
        <button :disabled="!job.running" @click="cancelJob">取消任务</button>
      </div>
    </header>

    <section class="hud">
      <div class="metric"><span class="m-label">sidecar</span><span class="m-value" :ref="(el) => setCell('sidecar', el as Element)">—</span></div>
      <div class="metric"><span class="m-label">已接收行</span><span class="m-value" :ref="(el) => setCell('rows', el as Element)">—</span></div>
      <div class="metric"><span class="m-label">首屏</span><span class="m-value" :ref="(el) => setCell('firstPaint', el as Element)">—</span></div>
      <div class="metric"><span class="m-label">推送耗时</span><span class="m-value" :ref="(el) => setCell('push', el as Element)">—</span></div>
      <div class="metric"><span class="m-label">帧率</span><span class="m-value" :ref="(el) => setCell('fps', el as Element)">—</span></div>
      <div class="metric"><span class="m-label">最低帧率</span><span class="m-value" :ref="(el) => setCell('minFps', el as Element)">—</span></div>
      <div class="metric"><span class="m-label">长任务</span><span class="m-value" :ref="(el) => setCell('longTasks', el as Element)">—</span></div>
      <div class="metric"><span class="m-label">最长阻塞</span><span class="m-value" :ref="(el) => setCell('block', el as Element)">—</span></div>
      <div class="metric"><span class="m-label">任务进度</span><span class="m-value" :ref="(el) => setCell('job', el as Element)">—</span></div>
    </section>

    <VirtualTable :rows="rows" />
  </div>
</template>