/**
 * 界面全量巡查（bug 排查用，不是几何/对齐门禁）：
 * 逐页打开侧栏所有入口 + 工具箱全部工具，收集
 *   - 渲染异常（空页、页头缺失、原始值泄漏 undefined/NaN/[object Object]、图片加载失败、重复 id）
 *   - 控制台 error / window.onerror / unhandledrejection
 * 发现异常就截图并记录，最后汇总；有任何异常退出码 1。
 *
 * 用法（cwd=desktop）：
 *   $env:ELECTRON_RUN_AS_NODE=$null
 *   $env:RENPYBOX_UI_URL='http://127.0.0.1:5179'
 *   $env:RENPYBOX_UI_CAPTURE_DIR='<输出目录>'
 *   $env:RENPYBOX_UI_THEME='LIGHT'   # 或 DARK
 *   cmd /c "node_modules\.bin\electron.cmd" scripts/check-crawl.cjs
 */
const { app, BrowserWindow } = require('electron');
const fs = require('fs');
const os = require('os');
const path = require('path');

app.disableHardwareAcceleration();
app.setPath('userData', path.join(os.tmpdir(), 'renpybox-crawl-profile-' + Date.now()));

const out = process.env.RENPYBOX_UI_CAPTURE_DIR || path.join(process.cwd(), 'docs', 'internal', 'crawl');
fs.mkdirSync(out, { recursive: true });
const logFile = path.join(out, 'crawl.log');
function log(line) {
  console.log(line);
  fs.appendFileSync(logFile, line + '\n');
}
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function fixture() {
  const values = {
    theme: '__RB_UI_THEME__',
    app_language: 'ZH',
    source_language: 'EN',
    target_language: 'ZH',
    input_folder: 'C:/ui-check/game/tl/chinese',
    output_folder: 'C:/ui-check/output',
    expert_mode: false,
    activate_platform: 0,
    agent_platform: 0,
    translation_output_protocol: 'STRUCTURED',
    platforms: [
      { id: 0, name: '主翻译接口', group: 'online', model: 'story-model', api_format: 'OpenAI', api_url: 'https://api.example.com/v1', api_key: '***' },
    ],
  };

  const f = (window.__uiFixture = {
    values,
    sockets: [],
    writes: [],
    reads: [],
    unbound: false,
    engineStatus: 'IDLE',
    progress: { line: 0, total_line: 0, time: 0, total_output_tokens: 0 },
    windowErrors: [],
    rejections: [],
  });

  window.addEventListener('error', (event) =>
    f.windowErrors.push({ message: String(event.message || event.error), stack: event.error && event.error.stack ? String(event.error.stack) : '' }),
  );
  window.addEventListener('unhandledrejection', (event) => {
    const reason = event.reason;
    f.rejections.push(String((reason && (reason.stack || reason.message)) || reason));
  });
  window.confirm = () => true;
  window.alert = () => {};

  const response = (data) =>
    new Response(JSON.stringify(data), { status: 200, headers: { 'Content-Type': 'application/json' } });

  const projectPayload = () =>
    f.unbound
      ? { renpy_project_path: '', renpy_game_folder: '', renpy_tl_folder: '' }
      : { renpy_project_path: 'C:/ui-check', renpy_game_folder: 'C:/ui-check/game', renpy_tl_folder: values.input_folder };

  f.emit = (event, data) => {
    const socket = f.sockets.at(-1);
    if (socket && typeof socket.onmessage === 'function') {
      socket.onmessage({ data: JSON.stringify({ type: 'event', event, data }) });
    }
  };

  const nativeFetch = fetch.bind(window);
  window.fetch = async (url, options = {}) => {
    const parsed = new URL(String(url), location.href);
    const p = parsed.pathname;
    if (p !== '/health' && !p.startsWith('/api/')) return nativeFetch(url, options);
    const method = options.method || 'GET';
    if (method === 'GET') f.reads.push(p + parsed.search);
    else f.writes.push({ p, method, body: options.body ? JSON.parse(options.body) : {} });

    if (p === '/health') return response({ ok: true, app_version: 'v0.8.1', mode: 'api', pid: 0 });
    if (p === '/api/version') return response({ app_version: 'v0.8.1', api_version: '1' });
    if (p === '/api/update') return response({ status: 'idle' });
    if (p === '/api/settings') {
      if (method === 'PATCH') Object.assign(values, JSON.parse(options.body || '{}').values || {});
      return response({ values, masked: [] });
    }
    if (p === '/api/settings/honorific-defaults') return response({ titles: ['mr', 'mrs', 'doctor'] });
    if (p === '/api/project') return response(projectPayload());
    if (p === '/api/project/validate') return response({ ok: true, valid: true, renpy_project_path: 'C:/ui-check', message: '' });
    if (p === '/api/platforms') return response({ values, masked: [] });
    if (/^\/api\/platforms\/\d+\/models$/.test(p)) return response({ models: ['available-model', 'story-model'] });
    if (p === '/api/jobs') return response({ jobs: [] });
    if (p === '/api/translation/state') {
      // 形状对齐 api/routes/translation.py:1076-1087 的 TranslationStateResponse
      return response({
        project_key: 'c:\\ui-check',
        engine_status: f.engineStatus,
        stop_barrier: false,
        single_tasks: false,
        request_id: '',
        run_id: 0,
        running: { running: 0, max: 4 },
        progress: { ...f.progress, status: 'UNTRANSLATED' },
        active_output_folder: values.output_folder,
        progress_source: 'none',
        progress_error: '',
      });
    }
    if (p === '/api/agent') return response({ status: 'idle', messages: [], confirmation: null });
    if (p === '/api/rpy-extraction') {
      return response({
        project_key: 'c:\\ui-check',
        path: 'C:/ui-check',
        category: 'source',
        language: 'chinese',
        job: null,
        applied_mode: 'builtin',
        applied_name: '未选择自定义方案',
        mode_labels: { builtin: '只用内置', combined: '内置＋自定义', custom: '仅自定义' },
        profiles: [],
        profile_docs: [],
        summary: '当前已生效：只用内置 · 未选择自定义方案',
        scan: { has_scan: false, completed: false, error: '', candidates: [], candidate_total: 0, page: 1, page_size: 200, page_count: 1 },
        new_rule_template: { id: 'tpl', name: '规则', enabled: true, include_globs: ['*.rpy'], pattern: '\\bcall\\b', flags: [], text_group: 'text', note: '', positive_samples: [], negative_samples: [] },
      });
    }
    // 其它接口给空壳，避免巡查被未覆盖接口打断
    return response({});
  };

  const NativeSocket = WebSocket;
  window.WebSocket = class {
    constructor(url) {
      if (!String(url).endsWith('/ws')) return new NativeSocket(url);
      this.readyState = 1;
      this.onopen = null;
      this.onmessage = null;
      this.onclose = null;
      this.onerror = null;
      f.sockets.push(this);
      setTimeout(() => {
        if (typeof this.onopen === 'function') this.onopen({});
      }, 0);
    }
    send() {}
    close() {
      this.readyState = 3;
      if (typeof this.onclose === 'function') this.onclose({});
    }
  };
}

app.whenReady().then(async () => {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    show: false,
    frame: false,
    webPreferences: { offscreen: true, sandbox: true, contextIsolation: true },
  });
  const consoleErrors = [];
  win.webContents.on('console-message', (event, level, message) => {
    const severity = event.level ?? level;
    const value = event.message ?? message;
    if (severity !== 'error' && !(severity >= 3)) return;
    if (/rc-virtual-list` reach the max limitation/.test(value)) return; // antd 虚拟列表内部提示
    consoleErrors.push(value);
    log('CONSOLE ' + value);
  });

  await win.loadURL('about:blank');
  win.webContents.debugger.attach('1.3');
  await win.webContents.debugger.sendCommand('Page.enable');
  await win.webContents.debugger.sendCommand('Runtime.enable');
  const theme = process.env.RENPYBOX_UI_THEME || 'LIGHT';
  await win.webContents.debugger.sendCommand('Page.addScriptToEvaluateOnNewDocument', {
    source: '(' + fixture.toString().replace("'__RB_UI_THEME__'", JSON.stringify(theme)) + ')()',
  });
  await win.loadURL(process.env.RENPYBOX_UI_URL || 'http://127.0.0.1:5179');

  const js = async (code) => {
    const result = await win.webContents.debugger.sendCommand('Runtime.evaluate', {
      expression: `(async()=>{const value=await (0,eval)(${JSON.stringify(code)});return typeof value==='function'||value instanceof Node?undefined:value;})()`,
      awaitPromise: true,
      returnByValue: true,
    });
    if (result.exceptionDetails) {
      throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
    }
    return result.result.value;
  };
  const shot = async (name) => {
    const result = await win.webContents.debugger.sendCommand('Page.captureScreenshot');
    fs.writeFileSync(path.join(out, name + '.png'), Buffer.from(result.data, 'base64'));
  };
  /** 设 RENPYBOX_CRAWL_CAPTURE_ALL=1 时每页都截图（默认只截异常页）。 */
  const captureAll = process.env.RENPYBOX_CRAWL_CAPTURE_ALL === '1';
  const safeName = (label) => label.replace(/[^\w\u4e00-\u9fa5-]+/g, '_');
  const clickAt = async (selector) => {
    const position = await js(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});if(!e)throw new Error('缺少元素 '+${JSON.stringify(selector)});e.scrollIntoView({block:'nearest'});const r=e.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2};})()`);
    await win.webContents.debugger.sendCommand('Input.dispatchMouseEvent', { type: 'mousePressed', ...position, button: 'left', clickCount: 1 });
    await win.webContents.debugger.sendCommand('Input.dispatchMouseEvent', { type: 'mouseReleased', ...position, button: 'left', clickCount: 1 });
    await pause(220);
  };
  const input = async (selector, value) => {
    await js(`(()=>{const root=document.querySelector(${JSON.stringify(selector)});const e=root?.matches('input,textarea')?root:root?.querySelector('input,textarea');if(!e)throw new Error('缺少输入框 '+${JSON.stringify(selector)});Object.getOwnPropertyDescriptor(e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype,'value').set.call(e,${JSON.stringify(value)});e.dispatchEvent(new Event('input',{bubbles:true}));})()`);
    await pause(80);
  };

  const anomalies = [];
  const crashes = [];
  let seenWindowErrors = 0;
  let seenUncaught = 0;
  const waitBoot = async () => {
    for (let i = 0; i < 80; i++) {
      if (await js("!!document.querySelector('.translation-layout') || !!document.querySelector('.rb-shell')")) break;
      await pause(100);
    }
    await pause(400);
  };
  const reloadApp = async () => {
    await win.reload();
    await waitBoot();
  };
  /** 页面崩溃会导致后续所有探针连锁失败，所以检测到就记录栈并重载，保证每条异常都能单独归因。 */
  const detectCrash = async (label) => {
    const safe = label.replace(/[^\w\u4e00-\u9fa5-]+/g, '_');
    const windowErrors = await js('__uiFixture.windowErrors.slice()');
    const uncaught = consoleErrors.filter((value) => /Uncaught/.test(value));
    const freshWindow = windowErrors.slice(seenWindowErrors);
    const freshUncaught = uncaught.slice(seenUncaught);
    if (!freshWindow.length && !freshUncaught.length) return false;
    for (const item of freshWindow) {
      const line = `CRASH [${label}] ${item.message}`;
      crashes.push(line);
      log(line);
      if (item.stack) log('CRASH_STACK ' + item.stack.split('\n').slice(0, 6).join(' | '));
    }
    for (const item of freshUncaught) {
      const line = `CRASH_CONSOLE [${label}] ${item}`;
      crashes.push(line);
      log(line);
    }
    seenWindowErrors = windowErrors.length;
    seenUncaught = uncaught.length;
    await shot('crash-' + safe);
    await reloadApp();
    return true;
  };
  const report = async (label, extra = '') => {
    const state = await js(`(()=>{
      const content = document.querySelector('.content');
      const text = (content?.innerText || '');
      const ids = [...document.querySelectorAll('[id]')].map(e => e.id);
      const duplicated = [...new Set(ids.filter((id, index) => ids.indexOf(id) !== index))];
      const broken = [...document.querySelectorAll('img[src]')].filter(img => img.complete && img.naturalWidth === 0).map(img => img.getAttribute('src'));
      return {
        page: content?.dataset.page || '',
        header: (content?.querySelector('h1')?.textContent || '').trim(),
        height: content?.scrollHeight || 0,
        boundary: !!document.querySelector('[data-rb-error-boundary]'),
        text: text.slice(0, 6000),
        duplicated,
        broken,
      };
    })()`);
    const found = [];
    if (!state.page) found.push('内容根缺失或缺少 data-page');
    if (!state.header) found.push('页头 h1 为空');
    if (state.boundary) found.push('ErrorBoundary 兜底被触发（该页渲染期抛错）');
    if (state.height > 0 && state.height < 60) found.push('页面高度异常（' + state.height + 'px）');
    if (/(^|[\s，。:：>（(])(undefined|NaN|Infinity|\[object Object\]|Invalid Date)([\s，。:：<）)]|$)/.test(state.text)) {
      const hit = state.text.match(/.{0,40}(undefined|NaN|Infinity|\[object Object\]|Invalid Date).{0,40}/);
      found.push('原始值泄漏：' + String(hit && hit[0]).replace(/\s+/g, ' ').trim());
    }
    if (state.duplicated.length) found.push('重复 DOM id：' + state.duplicated.slice(0, 4).join(','));
    if (state.broken.length) found.push('图片加载失败：' + state.broken.slice(0, 3).join(','));
    for (const message of found) {
      const line = `ANOMALY [${label}] ${message} ${extra}`;
      anomalies.push(line);
      log(line);
      await shot('anomaly-' + safeName(label));
    }
    if (captureAll) await shot(safeName(label) || 'page');
    return found.length === 0;
  };

  await waitBoot();

  const navTitles = await js("Array.from(document.querySelectorAll('.nav-item')).map(b => b.title).filter(Boolean)");
  const openNav = async (title) => {
    await js(`Array.from(document.querySelectorAll('.nav-item')).find(b => b.title === ${JSON.stringify(title)})?.click()`);
    await pause(420);
  };
  const openTool = async (title) => {
    await openNav("Ren'Py 工具箱");
    await input('.toolbox-search', title);
    const ok = await js(`(()=>{const card=document.querySelector('.tool-card');if(!card)return 'no-card';if(card.disabled)return 'disabled';card.click();return 'ok';})()`);
    await pause(420);
    return ok;
  };

  log(`=== 巡查开始 theme=${theme} 侧栏入口=${navTitles.length} ===`);
  const passed = [];
  await report('boot');
  let lastPageKey = await js("document.querySelector('.content')?.dataset.page || ''");
  for (const title of navTitles) {
    await openNav(title);
    const pageKey = await js("document.querySelector('.content')?.dataset.page || ''");
    if (pageKey && pageKey === lastPageKey) {
      log(`SKIP [page:${title}] 点击后未切换页面（不是页面入口）`);
      continue;
    }
    lastPageKey = pageKey;
    if (await report('page:' + title)) passed.push('page:' + title);
    await detectCrash('page:' + title);
  }

  await openNav("Ren'Py 工具箱");
  const toolTitles = await js("Array.from(document.querySelectorAll('.tool-card .rb-tool-title')).map(e => e.textContent.trim())");
  log(`=== 工具卡片=${toolTitles.length} ===`);
  for (const title of toolTitles) {
    const state = await openTool(title);
    if (state === 'disabled') {
      log(`SKIP [tool:${title}] 卡片禁用（需先选择游戏目录）`);
      continue;
    }
    if (state === 'no-card') {
      log(`ANOMALY [tool:${title}] 搜索后没有工具卡片`);
      anomalies.push('tool:' + title + ' 无卡片');
      continue;
    }
    if (await report('tool:' + title)) passed.push('tool:' + title);
    await detectCrash('tool:' + title);
  }

  // 空项目状态再走一遍侧栏（很多 bug 只在空状态出现）
  log('=== 切换为空项目再走一遍侧栏 ===');
  await js("__uiFixture.unbound = true; __uiFixture.emit('PROJECT_CHANGED', {});");
  await pause(600);
  for (const title of navTitles) {
    await openNav(title);
    if (await report('unbound:' + title)) passed.push('unbound:' + title);
    await detectCrash('unbound:' + title);
  }

  const windowErrors = await js('__uiFixture.windowErrors');
  const rejections = await js('__uiFixture.rejections');
  log(`=== 结果：通过 ${passed.length} 项；渲染异常 ${anomalies.length}；崩溃 ${crashes.length}；控制台错误 ${consoleErrors.length}；未处理 rejection ${rejections.length} ===`);
  for (const item of windowErrors) log('WINDOW_ERROR ' + item);
  for (const item of rejections) log('UNHANDLED_REJECTION ' + item);
  if (anomalies.length === 0 && crashes.length === 0 && consoleErrors.length === 0 && rejections.length === 0) {
    log('ALL CRAWL CHECKS PASSED');
    app.exit(0);
  } else {
    log('CRAWL FOUND ISSUES');
    app.exit(1);
  }
});
