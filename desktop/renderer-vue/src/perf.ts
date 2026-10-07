/** 性能采样：与 React 版完全相同的实现，保证对比公平。 */

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
    /* 忽略 */
  }
}

export function getLongTasks() {
  return { longTasks, maxBlockMs };
}

export function resetLongTasks() {
  longTasks = 0;
  maxBlockMs = 0;
}

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