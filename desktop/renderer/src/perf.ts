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

/** 持续采样帧率，返回停止函数。 */
export function sampleFps(onSample: (fps: number) => void, intervalMs = 500) {
  let frames = 0;
  let last = performance.now();
  let raf = 0;
  const loop = () => {
    frames += 1;
    const now = performance.now();
    if (now - last >= intervalMs) {
      onSample(Math.round((frames * 1000) / (now - last)));
      frames = 0;
      last = now;
    }
    raf = requestAnimationFrame(loop);
  };
  raf = requestAnimationFrame(loop);
  return () => cancelAnimationFrame(raf);
}