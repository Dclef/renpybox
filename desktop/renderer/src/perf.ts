/** 性能采样：帧率 + 长任务。用于 M0 门槛「不卡」的量化验收。 */

let longTasks = 0;
let maxBlockMs = 0;

if (typeof PerformanceObserver !== 'undefined') {
  try {
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        longTasks += 1;
        maxBlockMs = Math.max(maxBlockMs, entry.duration);
      }
    }).observe({ entryTypes: ['longtask'] });
  } catch {
    /* Chromium 不支持 longtask 时忽略 */
  }
}

export function getLongTasks() {
  return { longTasks, maxBlockMs };
}

export function resetLongTasks() {
  longTasks = 0;
  maxBlockMs = 0;
}

/**
 * 主线程 responsiveness 探针：
 * 反复用 setTimeout(0) 测实际间隔，间隔越长说明主线程越忙。
 * 比单点测 FPS 更能反映「输入有没有被响应」。
 */
export function probeResponsiveness(durationMs = 2000): Promise<{ avgLag: number; maxLag: number }> {
  return new Promise((resolve) => {
    const samples: number[] = [];
    const start = performance.now();
    let last = performance.now();
    const tick = () => {
      const now = performance.now();
      samples.push(now - last);
      last = now;
      if (now - start < durationMs) setTimeout(tick, 0);
      else {
        const usable = samples.slice(1);
        resolve({
          avgLag: usable.reduce((a, b) => a + b, 0) / Math.max(1, usable.length),
          maxLag: Math.max(...usable, 0),
        });
      }
    };
    setTimeout(tick, 0);
  });
}

/**
 * 帧间隔统计。
 *
 * 「最低帧率」对偶发抖动太敏感：任意一帧的 GC / 调度延迟都会把它拉低，
 * 但主线程其实没卡。所以卡不卡看两件事 —— 平均帧率 + 掉帧占比（间隔 > 24ms）。
 * 最低帧率仍然记录，只作为参考。
 */
const FRAME_DROP_MS = 24;
const frameIntervals: number[] = [];
let worstFps = Infinity;
let skipFirstFrame = true;

function recordFrame(dt: number) {
  // 第一帧没有参考意义（间隔包含启动开销），单独用标记跳过。
  // 注意不能用 frameIntervals.length === 0 判断——那样第一帧永远进不去，
  // 数组会一直是空的，平均帧率算出来恒为 0。
  if (skipFirstFrame) {
    skipFirstFrame = false;
    return;
  }

  frameIntervals.push(dt);
  if (frameIntervals.length > 600) frameIntervals.shift();
  const fps = 1000 / dt;
  if (fps < worstFps) worstFps = fps;
}

export function resetFrameStats() {
  frameIntervals.length = 0;
  worstFps = Infinity;
  skipFirstFrame = true;
}

export function frameStats() {
  if (frameIntervals.length === 0) {
    return { avgFps: 0, minFps: 0, droppedRatio: 1, frames: 0 };
  }
  const mean = frameIntervals.reduce((a, b) => a + b, 0) / frameIntervals.length;
  const dropped = frameIntervals.filter((dt) => dt > FRAME_DROP_MS).length;
  return {
    avgFps: Math.round(1000 / mean),
    minFps: Math.round(worstFps),
    droppedRatio: dropped / frameIntervals.length,
    frames: frameIntervals.length,
  };
}

/** 持续采样帧率，返回停止函数。 */
export function sampleFps(onSample: (fps: number) => void, intervalMs = 500) {
  let frames = 0;
  let last = performance.now();
  let windowStart = last;
  let raf = 0;

  const loop = () => {
    const now = performance.now();
    recordFrame(now - last);
    last = now;
    frames += 1;

    if (now - windowStart >= intervalMs) {
      onSample(Math.round((frames * 1000) / (now - windowStart)));
      frames = 0;
      windowStart = now;
    }
    raf = requestAnimationFrame(loop);
  };

  raf = requestAnimationFrame(loop);
  return () => cancelAnimationFrame(raf);
}