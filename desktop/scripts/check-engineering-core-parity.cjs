/**
 * 工程核心：错误修复 / 译文复用 / 格式化 / 解包 + 全部 7 入口受控 UI 自检。
 *
 * 运行（pwsh，勿终止 Vite 5179）：
 *   $env:RENPYBOX_UI_URL='http://127.0.0.1:5179'
 *   $env:RENPYBOX_UI_CAPTURE_DIR="$env:TEMP\renpybox-qt5-parity\engineering-core"
 *   $profile = Join-Path $env:TEMP ("renpybox-eng-core-" + [guid]::NewGuid().ToString('N'))
 *   cd desktop
 *   Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue
 *   .\node_modules\.bin\electron.cmd --user-data-dir=$profile scripts/check-engineering-core-parity.cjs
 *
 * mock HTTP/WS；B/C 页面未完整落地时入口仍应可导航（无「原桌面版」占位文案）。
 */
if (process.type !== 'browser') throw new Error('请使用 Electron 主进程运行，并先清除 ELECTRON_RUN_AS_NODE。');

const { app, BrowserWindow } = require('electron');
const fs = require('node:fs');
const path = require('node:path');

const out = process.env.RENPYBOX_UI_CAPTURE_DIR || path.join(require('node:os').tmpdir(), 'renpybox-qt5-parity', 'engineering-core');
const logPath = path.join(out, 'engineering-core-parity.log');
const pause = (ms) => new Promise((r) => setTimeout(r, ms));
const log = (value) => fs.appendFileSync(logPath, value + '\n');

fs.mkdirSync(out, { recursive: true });
fs.writeFileSync(logPath, '');

function fixture() {
  const values = {
    theme: 'DARK',
    source_language: 'EN',
    target_language: 'ZH',
    input_folder: 'C:/ui-check/game/tl/chinese',
    output_folder: 'C:/ui-check/output',
    expert_mode: false,
    activate_platform: 0,
    agent_platform: 0,
    platforms: [{
      id: 0,
      name: '主翻译接口',
      group: 'online',
      model: 'story-model',
      api_format: 'OpenAI',
      api_url: 'https://api.example.com/v1',
      api_key: '***',
    }],
  };

  const f = window.__uiFixture = {
    values,
    sockets: [],
    writes: [],
    reads: [],
    unbound: false,
    engineStatus: 'IDLE',
    progress: { line: 0, total_line: 0, time: 0, total_output_tokens: 0 },
    progressSource: 'none',
    jobs: {},
    serial: 0,
  };

  window.confirm = () => true;
  const response = (data) => new Response(JSON.stringify(data), { status: 200, headers: { 'Content-Type': 'application/json' } });

  const mkJob = (kind, body, extra = {}) => {
    const id = 'eng-' + (f.serial += 1);
    const key = String(body.project_key || extra.project_key || 'c:\\ui-check|tool');
    return {
      id,
      kind,
      status: 'done',
      total: 100,
      done: 100,
      progress: 1,
      error: null,
      created_at: Date.now() / 1000,
      updated_at: Date.now() / 1000,
      result: {
        project_key: key,
        message: extra.message || '模拟完成',
        worker_active: false,
        written: Boolean(extra.written),
        action: extra.action || 'scan',
        ...extra,
      },
    };
  };

  const projectPayload = () => {
    if (f.unbound) return { renpy_project_path: '', renpy_game_folder: '', renpy_tl_folder: '' };
    return {
      renpy_project_path: 'C:/ui-check',
      renpy_game_folder: 'C:/ui-check/game',
      renpy_tl_folder: values.input_folder,
    };
  };

  const nativeFetch = fetch.bind(window);
  window.fetch = async (url, options = {}) => {
    const parsed = new URL(String(url), location.href);
    const p = parsed.pathname;
    const qs = parsed.search;
    if (p !== '/health' && !p.startsWith('/api/')) return nativeFetch(url, options);
    const method = options.method || 'GET';
    const body = options.body ? JSON.parse(options.body) : {};
    if (method !== 'GET') f.writes.push({ p, method, body });
    else f.reads.push(p + qs);

    if (p === '/health') return response({ ok: true, app_version: 'v0.8.1', mode: 'api', pid: 0 });
    if (p === '/api/version') return response({ app_version: 'v0.8.1', api_version: '1' });
    if (p === '/api/project') return response(projectPayload());
    if (p === '/api/settings') {
      if (method === 'PATCH') Object.assign(values, body.values);
      return response({ values, masked: [] });
    }
    if (p === '/api/translation/state') {
      return response({
        engine_status: f.engineStatus,
        stop_barrier: false,
        single_tasks: false,
        request_id: 'fixture',
        run_id: 0,
        running: { running: 0, max: 4 },
        progress: f.progress,
        progress_source: f.progressSource,
        progress_error: '',
        active_output_folder: values.output_folder,
      });
    }

    if (p === '/api/error-repair' && method === 'GET') {
      const folder = parsed.searchParams.get('folder') || '';
      const key = folder ? 'folder:' + folder.toLowerCase() : '';
      return response({
        project_key: key,
        folder,
        owner_project_key: f.unbound ? '' : 'c:\\ui-check|chinese',
        has_scan_report: Boolean(f.jobs.error_scan),
        job: f.jobs.error || null,
      });
    }
    if (p === '/api/error-repair/scan' && method === 'POST') {
      const job = mkJob('error_repair_scan', body, {
        action: 'scan', report: {}, total_issues: 0, folder: body.folder, message: '未发现问题',
      });
      f.jobs.error = job;
      f.jobs.error_scan = job;
      return response({ job });
    }
    if (p === '/api/error-repair/fix' && method === 'POST') {
      if (!body.confirm) return new Response(JSON.stringify({ detail: '需要 confirm' }), { status: 400 });
      const job = mkJob('error_repair_fix', body, {
        action: 'fix', written: true, fixed_files: 1, fixed_items: 2, failed_files: 0, message: '已修复 1 个文件、2 处',
      });
      f.jobs.error = job;
      return response({ job });
    }
    if (p === '/api/error-repair/lint' && method === 'POST') {
      const job = mkJob('error_repair_lint', body, {
        action: 'lint', errors: [], error_count: 0, message: 'Lint 未发现翻译目录相关问题',
      });
      f.jobs.error = job;
      return response({ job });
    }
    if (p === '/api/error-repair/export' && method === 'POST') {
      return response({ success: true, output_path: body.output_path, message: 'ok' });
    }

    if (p === '/api/translation-reuse' && method === 'GET') {
      const source = parsed.searchParams.get('source_dir') || '';
      const target = parsed.searchParams.get('target_dir') || values.input_folder;
      const key = source && target ? `reuse:${source}|${target}` : '';
      return response({
        project_key: key,
        owner_project_key: f.unbound ? '' : 'c:\\ui-check|chinese',
        source_dir: source,
        target_dir: target,
        default_target_dir: values.input_folder,
        job: f.jobs.reuse || null,
      });
    }
    if (p === '/api/translation-reuse/preview' && method === 'POST') {
      const job = mkJob('translation_reuse_preview', body, {
        action: 'preview', reusable_entries: 2, conflicts: 1, already_reused: 0, unmatched_entries: 0,
        failed_files: [], message: '可复用 2；冲突 1',
      });
      f.jobs.reuse = job;
      return response({ job });
    }
    if (p === '/api/translation-reuse/execute' && method === 'POST') {
      if (!body.confirm) return new Response(JSON.stringify({ detail: '需要 confirm' }), { status: 400 });
      const job = mkJob('translation_reuse_execute', body, {
        action: 'execute', written: true, applied_entries: 2, reusable_entries: 2, conflicts: 1,
        already_reused: 0, unmatched_entries: 0, hook_updated: false,
        backup_path: 'C:/ui-check/tl_backup_chinese_reuse_1', failed_files: [],
        message: '已写入 2 条',
      });
      f.jobs.reuse = job;
      return response({ job });
    }

    if (p === '/api/formatter' && method === 'GET') {
      const folder = parsed.searchParams.get('folder') || '';
      return response({
        project_key: folder ? 'fmt:' + folder.toLowerCase() : '',
        owner_project_key: f.unbound ? '' : 'c:\\ui-check|chinese',
        folder,
        job: f.jobs.formatter || null,
      });
    }
    if (p === '/api/formatter/format' && method === 'POST') {
      if (!body.confirm) return new Response(JSON.stringify({ detail: '需要 confirm' }), { status: 400 });
      const job = mkJob('formatter_format', body, {
        action: 'format', written: true, success_count: 3, failed_files: [], message: '成功处理 3 个 RPY',
      });
      f.jobs.formatter = job;
      return response({ job });
    }

    if (p === '/api/archive' && method === 'GET') {
      return response({ job: f.jobs.archive || null, project_key: 'archive' });
    }
    if (p.startsWith('/api/archive/') && method === 'POST') {
      const job = mkJob('archive_unpack', body, {
        action: 'unpack', path: body.path || body.source_dir, message: '解包完成', archives_removed: false,
      });
      f.jobs.archive = job;
      return response({ job });
    }

    // Android / HTML / MOD：B/C 完整后仍应有路由；此处给空成功以免打断导航
    if (p.startsWith('/api/android-build') || p.startsWith('/api/html-import') || p.startsWith('/api/game-mod')) {
      if (method === 'GET') {
        return response({ project_key: f.unbound ? '' : 'c:\\ui-check|chinese', job: null });
      }
      return response({ job: mkJob('stub', body, { action: 'stub' }) });
    }

    if (p.startsWith('/api/')) return response({ ok: true, project_key: 'c:\\ui-check|chinese', job: null });
    throw new Error('engineering parity 未定义接口：' + method + ' ' + p + qs);
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
      setTimeout(() => { if (typeof this.onopen === 'function') this.onopen({}); }, 0);
    }
    close() {
      this.readyState = 3;
      if (typeof this.onclose === 'function') this.onclose({});
    }
  };

  window.renpy = {
    appInfo: async () => ({ appVersion: 'v0.8.1', packaged: false }),
    pickFolder: async () => 'C:/ui-check/manual-tl',
    pickFile: async () => 'C:/ui-check/game.exe',
    saveFile: async () => 'C:/ui-check/error_report.xlsx',
    onMaximizeChange: () => () => {},
    minimize: () => {},
    maximize: () => {},
    close: () => {},
  };
}

app.whenReady().then(async () => {
  const win = new BrowserWindow({
    width: 1280,
    height: 900,
    show: false,
    frame: false,
    webPreferences: { offscreen: true, sandbox: true, contextIsolation: true },
  });
  const errors = [];
  win.webContents.on('console-message', (event, level, message) => {
    const severity = event.level ?? level;
    const value = event.message ?? message;
    const text = String(value ?? '');
    if ((severity === 'error' || severity >= 3) && !(text.includes('[antd:') && text.includes('deprecated'))) {
      errors.push(text);
      log('CONSOLE ' + text);
    }
  });

  await win.loadURL('about:blank');
  win.webContents.debugger.attach('1.3');
  await win.webContents.debugger.sendCommand('Page.enable');
  await win.webContents.debugger.sendCommand('Runtime.enable');
  await win.webContents.debugger.sendCommand('Page.addScriptToEvaluateOnNewDocument', {
    source: '(' + fixture.toString() + ')()',
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

  const capture = async (name) => {
    const shot = await win.webContents.capturePage();
    const file = path.join(out, name + '.png');
    fs.writeFileSync(file, shot.toPNG());
    log('SHOT ' + file);
  };

  for (let i = 0; i < 80; i++) {
    if (await js("!!document.querySelector('.translation-layout') || !!document.querySelector('.rb-shell') || !!document.body")) break;
    await pause(100);
  }

  const assert = async (expression, name) => {
    for (let attempt = 0; attempt < 50; attempt++) {
      if (await js(`Boolean(${expression})`)) {
        log('PASS ' + name);
        return;
      }
      await pause(100);
    }
    await capture('fail-' + name.replace(/[^\w\u4e00-\u9fff-]+/g, '_').slice(0, 40));
    throw new Error('FAIL ' + name);
  };

  const navPage = async (title) => {
    await js(`Array.from(document.querySelectorAll('.nav-item')).find(b=>b.title===${JSON.stringify(title)})?.click()`);
    await pause(220);
  };

  const openTool = async (query) => {
    await navPage("Ren'Py 工具箱");
    await pause(200);
    await js(`(()=>{
      const root=document.querySelector('.toolbox-search');
      const e=root?.matches('input')?root:root?.querySelector('input');
      if(!e) throw new Error('缺少工具箱搜索框');
      const proto=HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto,'value').set.call(e,${JSON.stringify(query)});
      e.dispatchEvent(new Event('input',{bubbles:true}));
    })()`);
    await pause(180);
    const ok = await js('!!document.querySelector(".tool-card")');
    if (!ok) throw new Error('未找到工具卡片: ' + query);
    await js('document.querySelector(".tool-card")?.click()');
    await pause(320);
  };

  await assert("document.querySelector('.workspace-project')", '壳已渲染');

  // --- 七入口均不应出现「原桌面版」占位 ---
  await navPage("Ren'Py 工具箱");
  await pause(250);
  await capture('toolbox-engineer');
  for (const query of ['错误修复', '更新翻译复用', '代码格式化', '安卓打包', '网页', '游戏模组', '解包']) {
    await js(`(()=>{
      const root=document.querySelector('.toolbox-search');
      const e=root?.matches('input')?root:root?.querySelector('input');
      const proto=HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto,'value').set.call(e,${JSON.stringify(query)});
      e.dispatchEvent(new Event('input',{bubbles:true}));
    })()`);
    await pause(120);
    const pending = await js(`([...document.querySelectorAll('.tool-card')].some(c=>(c.textContent||'').includes('原桌面版')))`);
    if (pending) throw new Error('仍有原桌面版占位: ' + query);
  }
  log('PASS 七入口无原桌面版占位');

  // --- 错误修复默认 ---
  await openTool('错误修复');
  await assert("document.body.innerText.includes('修复缩进') || document.body.innerText.includes('Fix Indentation')", '错误修复页打开');
  const repairChecks = await js(`([...document.querySelectorAll('.ant-checkbox-wrapper')].map(w=>({
    text:(w.textContent||'').trim().slice(0,40),
    checked:!!w.querySelector('.ant-checkbox-checked'),
  })))`);
  log('repairChecks ' + JSON.stringify(repairChecks));
  const indent = repairChecks.find((c) => /Tab|缩进问题（Tab/.test(c.text) && !/层级/.test(c.text));
  const level = repairChecks.find((c) => /层级|Indentation Levels/.test(c.text));
  const quotes = repairChecks.find((c) => /弯引号|Chinese Quotation|外层中文引号/.test(c.text));
  const dialogue = repairChecks.find((c) => /未转义|Unescaped/.test(c.text));
  if (!indent?.checked) throw new Error('fixIndent 默认应为 true');
  if (level?.checked) throw new Error('fixIndentLevel 默认应为 false');
  if (quotes?.checked) throw new Error('fixQuotes 默认应为 false');
  if (dialogue?.checked) throw new Error('fixDialogueQuotes 默认应为 false');
  log('PASS 错误修复四默认 true,false,false,false');
  await capture('error-repair');

  // 空项目仍可独立使用
  await js('window.__uiFixture.unbound = true');
  await pause(200);
  await assert("document.body.innerText.includes('翻译目录') || document.body.innerText.includes('Translation Folder')", '未绑定仍显示错误修复页');

  // --- 译文复用 ---
  await js('window.__uiFixture.unbound = false');
  await pause(200);
  await openTool('更新翻译复用');
  await assert("document.body.innerText.includes('预览') || document.body.innerText.includes('Preview')", '译文复用预览按钮');
  await assert("document.body.innerText.includes('执行复用') || document.body.innerText.includes('Reuse Translations')", '译文复用执行按钮');
  await capture('translation-reuse');

  // --- 格式化 ---
  await openTool('代码格式化');
  const fmtChecks = await js(`([...document.querySelectorAll('.ant-checkbox-wrapper')].map(w=>({
    text:(w.textContent||'').trim().slice(0,40),
    checked:!!w.querySelector('.ant-checkbox-checked'),
  })))`);
  log('fmtChecks ' + JSON.stringify(fmtChecks));
  if (fmtChecks.length < 3 || fmtChecks.some((c) => !c.checked)) throw new Error('格式化三选项默认应为 true');
  log('PASS 格式化三默认 true');
  await capture('formatter');

  // --- 解包 ---
  await openTool('解包');
  await assert("document.body.innerText.includes('解包') || document.body.innerText.includes('Unpack')", '解包页');
  await capture('pack-unpack');

  // --- 其余入口可导航 ---
  for (const title of ['安卓打包', '网页', '游戏模组']) {
    await openTool(title);
    await capture('nav-' + title.replace(/[^\w\u4e00-\u9fff-]+/g, '_'));
    log('PASS 导航 ' + title);
  }

  if (errors.length) throw new Error('console errors: ' + errors.slice(0, 3).join(' | '));
  log('OK engineering-core-parity');
  app.exit(0);
}).catch((err) => {
  log('FATAL ' + (err && err.stack ? err.stack : String(err)));
  app.exit(1);
});
