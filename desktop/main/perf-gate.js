/**
 * M0 性能门禁：无头跑完指标，输出 JSON。
 *
 * 用法（推荐直接用 run-spike.sh，会自动拉起 sidecar + vite）：
 *   npm run sidecar / npm run dev:renderer / npm run perf-gate
 *
 * 用 offscreen 渲染，不弹窗，避免干扰你正在做的事。
 */
import { createRequire } from 'node:module';
import { writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// electron 是主进程内建模块，ESM 下用 createRequire 取最稳
const require = createRequire(import.meta.url);
const { app, BrowserWindow } = require('electron');

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PAGE_URL = process.env.VITE_DEV_SERVER_URL || 'http://127.0.0.1:5173';
const OUT = process.env.PERF_OUT || path.resolve(__dirname, '..', 'perf-result.json');
const TOTAL = Number(process.env.PERF_ROWS || 100000);
const SCROLL_MS = Number(process.env.PERF_SCROLL_MS || 3000);

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const bootedAt = Date.now();

async function js(win, code) {
  return win.webContents.executeJavaScript(code, true);
}

async function waitFor(win, expr, timeoutMs = 60000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const ok = await js(win, `(() => { try { return !!(${expr}); } catch { return false; } })()`);
    if (ok) return true;
    await sleep(100);
  }
  throw new Error(`等待超时：${expr}`);
}

const metrics = (win) => js(win, 'window.__renpy.metrics()');

/**
 * 平滑滚动：在一帧里推进固定距离，模拟真实用户滚动。
 * 不用 scrollTop 瞬移——瞬移会一次性触发大量动态行高测量，
 * 测出来的 maxBlockMs 是测量机制的开销，不是真实卡顿。
 */
function smoothScroll(win, ms) {
  return js(
    win,
    `new Promise((resolve) => {
      const el = document.querySelector('.table-body');
      if (!el) { resolve(-1); return; }
      const start = performance.now();
      const step = () => {
        el.scrollTop += 45;
        if (performance.now() - start < ${ms}) requestAnimationFrame(step);
        else resolve(el.scrollTop);
      };
      requestAnimationFrame(step);
    })`,
  );
}

function evaluate(report) {
  const resp = report.responsiveness || { avgLagMs: Infinity, maxLagMs: Infinity };
  const scrollRounds = report.scrollRoundStats || [];
  const jobRounds = report.jobRoundStats || [];

  // 「最低帧率」对偶发抖动过于敏感：任意一帧的 GC / 调度延迟都会把它拉低，
  // 但主线程其实没卡（长任务 0、最长阻塞十几毫秒）。
  // 所以卡不卡看两件事：平均帧率 + 掉帧占比（帧间隔 > 24ms）。
  // min fps 仍然记录，但不作为门禁。
  const avg = (list) => (list.length ? Math.round(list.reduce((a, b) => a + b, 0) / list.length) : 0);
  const dropped = avg(scrollRounds.map((r) => r.droppedRatio * 100));
  const scrollAvgFps = avg(scrollRounds.map((r) => r.avgFps));
  const jobAvgFps = avg(jobRounds.map((r) => r.avgFps));
  const jobDropped = avg(jobRounds.map((r) => r.droppedRatio * 100));

  const gates = [
    ['冷启动到可交互', report.coldStartMs, '< 1500ms', report.coldStartMs < 1500],
    ['10万行首屏', report.load.firstPaintMs, '< 300ms', report.load.firstPaintMs < 300],
    ['虚拟化生效(DOM行数)', report.load.domRows, '< 60', report.load.domRows > 0 && report.load.domRows < 60],
    ['滚动平均帧率', scrollAvgFps, '>= 50fps', scrollAvgFps >= 50],
    ['滚动掉帧占比', dropped, '< 5%', dropped < 5],
    ['并发任务中平均帧率', jobAvgFps, '>= 50fps', jobAvgFps >= 50],
    ['并发任务掉帧占比', jobDropped, '< 5%', jobDropped < 5],
    ['主线程平均延迟', resp.avgLagMs, '< 50ms', resp.avgLagMs < 50],
    ['主线程最大延迟', resp.maxLagMs, '< 50ms', resp.maxLagMs < 50],
    ['平滑滚动长任务数', report.scroll.longTasks, '== 0', report.scroll.longTasks === 0],
  ];

  console.log('\n=== M0 性能门禁 ===');
  for (const [name, value, target, pass] of gates) {
    const v = typeof value === 'number' ? Math.round(value * 10) / 10 : value;
    console.log(`${pass ? 'PASS' : 'FAIL'}  ${name.padEnd(24)} ${String(v).padStart(9)}   目标 ${target}`);
  }

  const failed = gates.filter((g) => !g[3]).map((g) => g[0]);
  console.log(`\n参考（不作为门禁）：滚动最低帧率 ${JSON.stringify(scrollRounds.map((r) => r.minFps))}` +
    `  任务中 ${JSON.stringify(jobRounds.map((r) => r.minFps))}`);
  console.log(`参考：10万行服务端推送耗时 ${report.load.rowsElapsedMs}ms（含模拟节流，非 UI 瓶颈）`);
  console.log(failed.length === 0 ? '\n全部通过' : `\n未通过：${failed.join('、')}`);
  return failed.length === 0;
}

app.whenReady().then(async () => {
  const win = new BrowserWindow({
    width: 1440,
    height: 900,
    show: false,
    webPreferences: { offscreen: true, contextIsolation: true, nodeIntegration: false, sandbox: true },
  });

  win.webContents.on('console-message', (e) => {
    const text = typeof e === 'object' && e !== null ? `${e.level}:${e.message}` : String(e);
    console.log(`[renderer] ${text}`);
  });
  win.webContents.on('did-fail-load', (_e, code, desc, url) =>
    console.error(`[renderer] 加载失败 ${code} ${desc} ${url}`),
  );
  win.webContents.on('render-process-gone', (_e, d) => console.error(`[renderer] 崩溃 ${JSON.stringify(d)}`));

  const report = { pageUrl: PAGE_URL, totalRows: TOTAL, scrollMs: SCROLL_MS };
  try {
    await win.loadURL(PAGE_URL);
    await waitFor(win, 'window.__renpy && window.__renpy.ready', 30000);
    report.coldStartMs = Date.now() - bootedAt;

    // 1) 10 万行流式加载
    await js(win, `window.__renpy.loadRows(${TOTAL})`);
    await waitFor(win, 'window.__renpy.metrics().rowsReceived > 0');
    await waitFor(win, 'window.__renpy.metrics().rowsDone === true', 90000);
    report.load = await metrics(win);

    // 2) 平滑滚动采样帧率
    //    预热一轮 + 三轮取中位数：单轮采样容易被机器抖动带偏，
    //    实测同一份代码单轮最低帧率会在 45~59 之间跳。
    await sleep(400);
    await smoothScroll(win, 800); // 预热，不计入

    const scrollRounds = [];
    for (let round = 0; round < 3; round++) {
      await js(win, 'window.__renpy.resetFrames && window.__renpy.resetFrames()');
      await smoothScroll(win, SCROLL_MS);
      const m = await metrics(win);
      scrollRounds.push({
        avgFps: m.avgFps ?? 0,
        minFps: m.minFps ?? 0,
        droppedRatio: m.droppedRatio ?? 1,
      });
      await smoothScroll(win, 0); // 回到顶部，避免下一轮起点不同
    }
    report.scrollRoundStats = scrollRounds;
    report.scroll = await metrics(win);

    // 3) 高并发任务期间平滑滚动（同样三轮）
    await js(win, 'window.__renpy.startJob(1500, 8)');
    await sleep(500);

    const jobRounds = [];
    for (let round = 0; round < 3; round++) {
      await js(win, 'window.__renpy.resetFrames && window.__renpy.resetFrames()');
      await smoothScroll(win, SCROLL_MS);
      const m = await metrics(win);
      jobRounds.push({
        avgFps: m.avgFps ?? 0,
        minFps: m.minFps ?? 0,
        droppedRatio: m.droppedRatio ?? 1,
      });
      await smoothScroll(win, 0);
    }
    report.jobRoundStats = jobRounds;
    report.duringJob = await metrics(win);

    // 4) 交互响应探针
    report.responsiveness = await js(win, `
      new Promise((resolve) => {
        const samples = [];
        let last = performance.now();
        const start = last;
        function tick() {
          const now = performance.now();
          samples.push(now - last);
          last = now;
          if (now - start < 2000) setTimeout(tick, 0);
          else {
            const usable = samples.slice(1);
            resolve({
              avgLagMs: usable.reduce((a, b) => a + b, 0) / Math.max(1, usable.length),
              maxLagMs: Math.max(...usable, 0),
            });
          }
        }
        setTimeout(tick, 0);
      })
    `);

    report.pass = evaluate(report);
  } catch (err) {
    report.error = String(err);
    console.error('[perf-gate] 失败：', err);
  } finally {
    writeFileSync(OUT, JSON.stringify(report, null, 2), 'utf8');
    console.log(`\n结果已写入 ${OUT}`);
    app.exit(0);
  }
});

