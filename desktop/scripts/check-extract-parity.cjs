/**
 * JSON / 抽取到 TL 受控 UI 验收（独立 user-data-dir，避免与其它 Electron 缓存竞争）。
 *
 * 运行（pwsh）：
 *   $env:RENPYBOX_UI_URL='http://127.0.0.1:5179'
 *   $env:RENPYBOX_UI_CAPTURE_DIR="$env:TEMP\renpybox-qt5-parity\extract-final-cli"
 *   $profile = Join-Path $env:TEMP ("renpybox-extract-final-cli-" + [guid]::NewGuid().ToString('N'))
 *   cd desktop
 *   Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue
 *   .\node_modules\.bin\electron.cmd --user-data-dir=$profile scripts/check-extract-parity.cjs
 *
 * mock HTTP/WS，不触真实游戏或付费 API。
 * 真实点击须等按钮 enabled 且 submit（含 reloadTranslation）结束后再点下一步。
 */
if (process.type !== 'browser') throw new Error('请使用 Electron 主进程运行，并先清除 ELECTRON_RUN_AS_NODE。');

const { app, BrowserWindow } = require('electron');
const fs = require('node:fs');
const path = require('node:path');

const out = process.env.RENPYBOX_UI_CAPTURE_DIR || path.join(require('node:os').tmpdir(), 'renpybox-qt5-parity', 'new-ui-extract');
const logPath = path.join(out, 'extract-parity.log');
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

  const BOUND_KEY = 'c:\\ui-check|chinese';
  const f = window.__uiFixture = {
    values,
    sockets: [],
    writes: [],
    reads: [],
    unbound: false,
    engineStatus: 'IDLE',
    progress: { line: 0, total_line: 0, time: 0, total_output_tokens: 0 },
    progressSource: 'none',
    toolProjectKey: BOUND_KEY,
    toolSerial: 0,
    // 按目标 canonical key 存最近任务（对齐真 API 独立目标身份）
    jsonJobsByKey: {},
    tlJobsByKey: {},
    postModes: {},
    extractStatus: {
      has_existing_tl: true,
      incremental_dir_exists: true,
      suspicious_backup_available: true,
      suspicious_manifests: [{ path: 'C:/ui-check/game/tl/chinese/_filtered_suspicious/t1/restore_manifest.csv' }],
      rule_mode: 'builtin',
      options: {
        use_official: true,
        use_custom: true,
        supplement_mode: 'precise',
        skip_hook_files: true,
        filter_suspicious_bool_expr: true,
        auto_merge_cleanup: true,
      },
    },
    jsonStatus: {
      default_game_file: 'C:/ui-check/game.exe',
      project_root: 'C:/ui-check',
      game_dir: 'C:/ui-check/game',
      language: 'chinese',
      tl_dir: 'C:/ui-check/game/tl/chinese',
    },
  };

  window.confirm = () => true;
  const response = (data) => new Response(JSON.stringify(data), { status: 200, headers: { 'Content-Type': 'application/json' } });

  /** 对齐 RenpyProjectPaths：文件→父目录；…/game→项目根；键为 normcase 根|language */
  const resolveProjectRoot = (raw) => {
    let text = String(raw || '').trim().replace(/\\/g, '/').replace(/\/+$/, '');
    if (!text) return '';
    const base = text.split('/').pop() || '';
    if (/\.(exe|py|rpy)$/i.test(base)) text = text.replace(/\/[^/]+$/, '');
    if (text.toLowerCase().endsWith('/game')) text = text.slice(0, -5);
    return text.replace(/\/+$/, '');
  };

  const targetKey = (raw, language = 'chinese') => {
    const root = resolveProjectRoot(raw);
    if (!root) return '';
    // Windows normcase ≈ 小写 + 反斜杠，与后端 c:\\ui-check|chinese 形态一致
    const norm = root.replace(/\//g, '\\').toLowerCase();
    return `${norm}|${String(language || 'chinese').trim().toLowerCase() || 'chinese'}`;
  };

  const projectPayload = () => {
    if (f.unbound) {
      return { renpy_project_path: '', renpy_game_folder: '', renpy_tl_folder: '' };
    }
    return {
      renpy_project_path: 'C:/ui-check',
      renpy_game_folder: 'C:/ui-check/game',
      renpy_tl_folder: values.input_folder,
    };
  };

  const mkJob = (kind, body, message = '模拟完成', overrides = {}) => {
    const id = 'extract-parity-' + (f.toolSerial += 1);
    const lang = String(body.language || 'chinese');
    const rawTarget = body.game_file || body.game_dir || '';
    const key = rawTarget
      ? targetKey(rawTarget, lang)
      : String(body.project_key || (f.unbound ? '' : f.toolProjectKey));
    const job = {
      id,
      kind,
      status: 'done',
      total: 1,
      done: 1,
      progress: 1,
      error: null,
      cancel_requested: false,
      created_at: Date.now() / 1000,
      updated_at: Date.now() / 1000,
      result: {
        project_key: key,
        message,
        worker_active: false,
        action: kind.includes('preview') ? 'preview'
          : kind.includes('import') ? 'import_apply'
            : kind.includes('merge') ? 'merge'
              : kind.includes('restore') ? 'restore'
                : kind.includes('extract_to_tl') ? 'extract'
                  : kind,
        written: kind !== 'extract_json_preview',
        success: true,
        partial: false,
        incremental_dir: kind === 'extract_to_tl' ? 'C:/ui-check/game/tl/chinese_new' : '',
        language: lang,
      },
    };
    Object.assign(job, overrides);
    if (overrides.result) job.result = { ...job.result, ...overrides.result };
    return job;
  };

  const applyPostMode = (pathname, job, body) => {
    const mode = f.postModes[pathname] || 'default';
    if (mode === 'running') {
      job.status = 'running';
      job.done = 40;
      job.total = 100;
      job.progress = 0.4;
      job.cancel_requested = false;
      job.result.worker_active = true;
      job.result.written = false;
      job.result.success = false;
      job.result.partial = false;
      job.result.message = '任务进行中（fixture running）';
      return job;
    }
    if (mode === 'fail_partial') {
      job.status = 'failed';
      job.error = 'RuntimeError: fixture partial failure';
      job.result.worker_active = false;
      job.result.written = true;
      job.result.success = false;
      job.result.partial = true;
      job.result.written_files = [
        resolveProjectRoot(body.game_file || body.game_dir || 'C:/ui-check') + '/game/tl/chinese/a.rpy',
      ];
      job.result.message = '部分写入后失败（fixture）';
      return job;
    }
    if (mode === 'done_success_false') {
      job.status = 'done';
      job.result.worker_active = false;
      job.result.written = false;
      job.result.success = false;
      job.result.partial = false;
      job.result.message = '业务未完成（fixture done success=false）';
      return job;
    }
    return job;
  };

  const storeJob = (family, job) => {
    const key = String(job?.result?.project_key || '');
    if (!key) return;
    if (family === 'json') f.jsonJobsByKey[key] = job;
    else f.tlJobsByKey[key] = job;
  };

  const statusForJson = (url) => {
    const u = new URL(String(url), location.href);
    const lang = u.searchParams.get('language') || 'chinese';
    const gameFile = (u.searchParams.get('game_file') || '').trim();
    const owner = f.unbound ? '' : f.toolProjectKey;
    if (gameFile) {
      const key = targetKey(gameFile, lang);
      const root = resolveProjectRoot(gameFile);
      return {
        project_key: key,
        owner_project_key: owner,
        project_root: root,
        game_dir: root ? root + '/game' : '',
        language: lang,
        tl_dir: root ? root + '/game/tl/' + lang : '',
        default_game_file: gameFile,
        job: f.jsonJobsByKey[key] || null,
      };
    }
    if (f.unbound) {
      return {
        project_key: '',
        owner_project_key: '',
        project_root: '',
        game_dir: '',
        language: lang,
        tl_dir: '',
        default_game_file: '',
        job: null,
      };
    }
    return {
      project_key: f.toolProjectKey,
      owner_project_key: f.toolProjectKey,
      ...f.jsonStatus,
      language: lang,
      job: f.jsonJobsByKey[f.toolProjectKey] || null,
    };
  };

  const statusForTl = (url) => {
    const u = new URL(String(url), location.href);
    const lang = u.searchParams.get('language') || 'chinese';
    const gameDir = (u.searchParams.get('game_dir') || '').trim();
    const owner = f.unbound ? '' : f.toolProjectKey;
    if (gameDir) {
      const key = targetKey(gameDir, lang);
      const root = resolveProjectRoot(gameDir);
      return {
        ...f.extractStatus,
        project_key: key,
        owner_project_key: owner,
        project_root: root,
        game_dir: root ? (root.toLowerCase().endsWith('game') ? root : root + '/game') : gameDir,
        language: lang,
        tl_dir: root + '/game/tl/' + lang,
        incremental_dir: root + '/game/tl/' + lang + '_new',
        job: f.tlJobsByKey[key] || null,
      };
    }
    if (f.unbound) {
      return {
        project_key: '',
        owner_project_key: '',
        project_root: '',
        game_dir: '',
        language: lang,
        tl_dir: '',
        incremental_dir: '',
        has_existing_tl: false,
        incremental_dir_exists: false,
        suspicious_backup_available: false,
        suspicious_manifests: [],
        options: f.extractStatus.options,
        rule_mode: 'builtin',
        job: null,
      };
    }
    return {
      project_key: f.toolProjectKey,
      owner_project_key: f.toolProjectKey,
      project_root: 'C:/ui-check',
      game_dir: 'C:/ui-check/game',
      language: lang,
      tl_dir: 'C:/ui-check/game/tl/' + lang,
      ...f.extractStatus,
      job: f.tlJobsByKey[f.toolProjectKey] || null,
    };
  };

  f.emitEvent = (event, data = {}) => {
    const payload = JSON.stringify({ type: 'event', event, data });
    let delivered = 0;
    for (const socket of f.sockets) {
      if (typeof socket.onmessage === 'function') {
        socket.onmessage({ data: payload });
        delivered += 1;
      }
    }
    return delivered;
  };

  const findJobById = (id) => {
    for (const job of Object.values(f.jsonJobsByKey)) if (job?.id === id) return job;
    for (const job of Object.values(f.tlJobsByKey)) if (job?.id === id) return job;
    return null;
  };

  const nativeFetch = fetch.bind(window);
  window.fetch = async (url, options = {}) => {
    const abs = new URL(String(url), location.href);
    const p = abs.pathname;
    const qs = abs.search;
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
    if ((p === '/api/extract-to-tl' || p.startsWith('/api/extract-to-tl?')) && method === 'GET') {
      return response(statusForTl(abs.href));
    }
    if (p.startsWith('/api/extract-to-tl/') && method === 'POST') {
      const kind = p.includes('merge') ? 'extract_to_tl_merge' : p.includes('restore') ? 'extract_to_tl_restore' : p.includes('open-path') ? 'extract_to_tl_open' : 'extract_to_tl';
      if (kind === 'extract_to_tl_open') return response({ ok: true, path: body.path, project_key: body.project_key || '' });
      let job = mkJob(kind, body);
      job = applyPostMode(p, job, body);
      storeJob('tl', job);
      return response({ job });
    }
    if (p.startsWith('/api/extract-to-tl/suspicious-backups')) {
      return response({
        manifests: f.extractStatus.suspicious_manifests || [],
        available: true,
        open_path: 'C:/ui-check/game/tl/chinese/_filtered_suspicious',
      });
    }
    if ((p === '/api/extract-json' || p.startsWith('/api/extract-json?')) && method === 'GET') {
      return response(statusForJson(abs.href));
    }
    if (p.startsWith('/api/extract-json/') && method === 'POST') {
      const kind = ({
        '/api/extract-json/preview': 'extract_json_preview',
        '/api/extract-json/export-json': 'extract_json_export',
        '/api/extract-json/import-apply': 'extract_json_import',
        '/api/extract-json/cleanup': 'extract_json_cleanup',
        '/api/extract-json/export-tl-json': 'extract_json_export_tl',
      })[p] || 'extract_json';
      let job = mkJob(kind, body);
      job.result.file_count = 1;
      job.result.entry_count = 2;
      job = applyPostMode(p, job, body);
      storeJob('json', job);
      return response({ job });
    }
    if (/^\/api\/jobs\/extract-parity-\d+\/cancel$/.test(p) && method === 'POST') {
      const id = p.split('/')[3];
      const job = findJobById(id);
      if (job) {
        job.status = 'cancelled';
        job.cancel_requested = true;
        job.result = {
          ...job.result,
          worker_active: false,
          success: false,
          partial: true,
          written: true,
          written_files: job.result.written_files?.length
            ? job.result.written_files
            : [(resolveProjectRoot(job.result.game_file || 'C:/manual-target') || 'C:/manual-target') + '/game/tl/chinese/a.rpy'],
          message: '任务已取消（已保留写入结果）',
        };
      }
      return response({ ok: true });
    }
    if (p === '/api/jobs') return response({ jobs: [] });
    // 其它工具箱入口可能顺带请求，给空成功以免打断导航
    if (p.startsWith('/api/')) return response({ ok: true, project_key: f.toolProjectKey });
    throw new Error('extract parity 未定义接口：' + method + ' ' + p + qs);
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
  const errors = [];
  win.webContents.on('console-message', (event, level, message) => {
    const severity = event.level ?? level;
    const value = event.message ?? message;
    const text = String(value ?? '');
    const antdDeprecation = text.includes('[antd:') && text.includes('deprecated');
    if ((severity === 'error' || severity >= 3) && !antdDeprecation) {
      errors.push(text);
      log('CONSOLE ' + text);
    }
  });

  await win.loadURL('about:blank');
  win.webContents.debugger.attach('1.3');
  await win.webContents.debugger.sendCommand('Page.enable');
  await win.webContents.debugger.sendCommand('Runtime.enable');
  await win.webContents.debugger.sendCommand('Page.addScriptToEvaluateOnNewDocument', { source: '(' + fixture.toString() + ')()' });
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

  for (let i = 0; i < 80; i++) {
    if (await js("!!document.querySelector('.translation-layout')")) break;
    await pause(100);
  }

  /** 失败时简短真实 DOM 诊断：disabled/rect/命中/writes，并截图 */
  const diagnoseButton = async (text, label) => {
    const normalized = text.replaceAll(' ', '');
    const probe = await js(`(()=>{
      const dialogs=[...document.querySelectorAll('[role=dialog]')].filter(e=>e.getBoundingClientRect().height>0);
      const scope=dialogs.at(-1)||document;
      const e=[...scope.querySelectorAll('button,[role=tab],[role=menuitem]')].find(b=>b.textContent.split(' ').join('')===${JSON.stringify(normalized)});
      const writes=(window.__uiFixture&&__uiFixture.writes)||[];
      if(!e) return {found:false,writesLen:writes.length,lastWrites:writes.slice(-3).map(w=>w.p)};
      const r=e.getBoundingClientRect();
      const x=r.left+r.width/2, y=r.top+r.height/2;
      const hit=document.elementFromPoint(x,y);
      const hitOk=!!hit&&(hit===e||e.contains(hit));
      const inView=r.width>1&&r.height>1&&x>=0&&y>=0&&x<=window.innerWidth&&y<=window.innerHeight;
      return {
        found:true,
        disabled:!!e.disabled,
        loading:e.classList.contains('ant-btn-loading'),
        rect:{x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)},
        center:{x:Math.round(x),y:Math.round(y)},
        inView,
        hitOk,
        hitTag:hit?hit.tagName:null,
        hitClass:hit?(hit.className||'').toString().slice(0,80):null,
        hitText:hit?(hit.textContent||'').replace(/\\s+/g,' ').trim().slice(0,48):null,
        writesLen:writes.length,
        lastWrites:writes.slice(-3).map(w=>w.p),
      };
    })()`);
    log('DIAG ' + label + ' btn=' + JSON.stringify(text) + ' ' + JSON.stringify(probe));
    try {
      const safe = String(label).replace(/[^\w\u4e00-\u9fff-]+/g, '_').slice(0, 48);
      await capture('fail-' + safe);
    } catch (err) {
      log('DIAG capture-failed ' + (err && err.message ? err.message : String(err)));
    }
  };

  const assert = async (expression, name) => {
    for (let attempt = 0; attempt < 40; attempt++) {
      if (await js(`Boolean(${expression})`)) {
        log('PASS ' + name);
        return;
      }
      await pause(120);
    }
    const writes = await js('(window.__uiFixture&&__uiFixture.writes||[]).slice(-5).map(w=>w.p)');
    log('DIAG assert-fail ' + name + ' recentWrites=' + JSON.stringify(writes));
    const writeBtn = String(name).match(/^提交写入:\s*(.+)$/);
    if (writeBtn) await diagnoseButton(writeBtn[1], 'assert-' + name);
    else {
      try { await capture('fail-assert'); } catch (_) { /* ignore */ }
    }
    throw new Error('FAIL ' + name);
  };

  /**
   * 等按钮真实可点：enabled、正尺寸、中心在 viewport、
   * elementFromPoint 命中自身/子节点，且 rect 连续两帧稳定（Collapse/滚动结束）。
   */
  const waitButtonInteractable = async (text, name = text) => {
    const normalized = text.replaceAll(' ', '');
    let last = null;
    let stable = 0;
    for (let attempt = 0; attempt < 100; attempt++) {
      const state = await js(`(()=>{
        const dialogs=[...document.querySelectorAll('[role=dialog]')].filter(e=>e.getBoundingClientRect().height>0);
        const scope=dialogs.at(-1)||document;
        const e=[...scope.querySelectorAll('button,[role=tab],[role=menuitem]')].find(b=>b.textContent.split(' ').join('')===${JSON.stringify(normalized)});
        if(!e || e.disabled || e.classList.contains('ant-btn-loading')) return null;
        e.scrollIntoView({block:'nearest', inline:'nearest'});
        const r=e.getBoundingClientRect();
        if(r.width<2 || r.height<2) return null;
        const x=r.left+r.width/2, y=r.top+r.height/2;
        if(x<0 || y<0 || x>window.innerWidth || y>window.innerHeight) return null;
        const hit=document.elementFromPoint(x,y);
        if(!hit || !(hit===e || e.contains(hit))) return null;
        return {x, y, l:r.left, t:r.top, w:r.width, h:r.height};
      })()`);
      if (state) {
        if (
          last
          && Math.abs(last.l - state.l) < 0.5
          && Math.abs(last.t - state.t) < 0.5
          && Math.abs(last.w - state.w) < 0.5
          && Math.abs(last.h - state.h) < 0.5
        ) {
          stable += 1;
          if (stable >= 2) return { x: state.x, y: state.y };
        } else {
          stable = 0;
          last = state;
        }
      } else {
        stable = 0;
        last = null;
      }
      await pause(50);
    }
    await diagnoseButton(text, 'interactable-' + name);
    throw new Error('FAIL 按钮不可交互: ' + name);
  };

  /** 兼容旧调用：enabled 且可命中 */
  const waitButtonEnabled = async (text, name = text) => {
    await waitButtonInteractable(text, name);
  };

  const click = async (text) => {
    await waitButtonInteractable(text);
    // 派发鼠标前再校验 enabled + 同中心命中，避免动画间隙误点
    const position = await js(`(()=>{
      const dialogs=[...document.querySelectorAll('[role=dialog]')].filter(e=>e.getBoundingClientRect().height>0);
      const scope=dialogs.at(-1)||document;
      const normalized=${JSON.stringify(text.replaceAll(' ', ''))};
      const e=[...scope.querySelectorAll('button,[role=tab],[role=menuitem]')].find(b=>b.textContent.split(' ').join('')===normalized);
      if(!e) return null;
      if(e.disabled || e.classList.contains('ant-btn-loading')) return null;
      const r=e.getBoundingClientRect();
      if(r.width<2 || r.height<2) return null;
      const x=r.left+r.width/2, y=r.top+r.height/2;
      if(x<0 || y<0 || x>window.innerWidth || y>window.innerHeight) return null;
      const hit=document.elementFromPoint(x,y);
      if(!hit || !(hit===e || e.contains(hit))) return null;
      return {x, y};
    })()`);
    if (!position) {
      await diagnoseButton(text, 'pre-click-' + text);
      throw new Error('FAIL 点击前目标失效: ' + text);
    }
    await win.webContents.debugger.sendCommand('Input.dispatchMouseEvent', { type: 'mousePressed', ...position, button: 'left', clickCount: 1 });
    await win.webContents.debugger.sendCommand('Input.dispatchMouseEvent', { type: 'mouseReleased', ...position, button: 'left', clickCount: 1 });
  };

  /**
   * 真实点击提交：点击前挂 MutationObserver 捕获 busy/disabled 闪帧，
   * 再等 writes；最后等可交互 idle（避免 POST 后误认点击前旧 enabled）。
   * 同时监视点击按钮与 idle 按钮文案（running 时「预览」会换成「取消」）。
   */
  const clickSubmit = async (text, writeExpr, idleButton = text) => {
    const before = await js('__uiFixture.writes.length');
    const clickNorm = text.replaceAll(' ', '');
    const idleNorm = idleButton.replaceAll(' ', '');
    await js(`(()=>{
      if(window.__rbBusyMo) try{window.__rbBusyMo.disconnect();}catch(_){}
      window.__rbBusySeen=false;
      const norms=new Set([${JSON.stringify(clickNorm)}, ${JSON.stringify(idleNorm)}]);
      const mark=()=>{
        const dialogs=[...document.querySelectorAll('[role=dialog]')].filter(e=>e.getBoundingClientRect().height>0);
        const scope=dialogs.at(-1)||document;
        for (const e of scope.querySelectorAll('button,[role=tab],[role=menuitem]')) {
          const t=(e.textContent||'').split(' ').join('');
          if(!norms.has(t)) continue;
          if(e.disabled||e.classList.contains('ant-btn-loading')) { window.__rbBusySeen=true; return; }
        }
      };
      mark();
      const mo=new MutationObserver(mark);
      mo.observe(document.body,{subtree:true,childList:true,attributes:true,attributeFilter:['disabled','class']});
      window.__rbBusyMo=mo;
      return true;
    })()`);
    await click(text);
    let sawBusy = false;
    let wrote = false;
    for (let attempt = 0; attempt < 100; attempt++) {
      const snap = await js(`(()=>{
        const writesOk=__uiFixture.writes.length>${before}&&(${writeExpr});
        const dialogs=[...document.querySelectorAll('[role=dialog]')].filter(e=>e.getBoundingClientRect().height>0);
        const scope=dialogs.at(-1)||document;
        const norms=new Set([${JSON.stringify(clickNorm)}, ${JSON.stringify(idleNorm)}]);
        let busyNow=false;
        for (const e of scope.querySelectorAll('button,[role=tab],[role=menuitem]')) {
          const t=(e.textContent||'').split(' ').join('');
          if(!norms.has(t)) continue;
          if(e.disabled||e.classList.contains('ant-btn-loading')) { busyNow=true; break; }
        }
        if(busyNow) window.__rbBusySeen=true;
        return {writesOk, busySeen:!!window.__rbBusySeen, busyNow};
      })()`);
      if (snap.busySeen) sawBusy = true;
      if (snap.writesOk) wrote = true;
      if (wrote && sawBusy) break;
      await pause(20);
    }
    await js(`(()=>{ if(window.__rbBusyMo) try{window.__rbBusyMo.disconnect();}catch(_){} window.__rbBusyMo=null; })()`);
    if (!wrote) {
      log('DIAG assert-fail 提交写入: ' + text + ' recentWrites=' + JSON.stringify(await js('__uiFixture.writes.slice(-5).map(w=>w.p)')));
      await diagnoseButton(text, 'assert-提交写入-' + text);
      throw new Error('FAIL 提交写入: ' + text);
    }
    if (!sawBusy) {
      await diagnoseButton(idleButton, 'submit-no-busy-' + idleButton);
      throw new Error('FAIL submit 未见 busy/disabled render: ' + idleButton);
    }
    log('PASS 提交写入: ' + text);
    await waitButtonInteractable(idleButton, 'submit 完成可再点: ' + idleButton);
  };

  const page = async (title) => {
    await js(`Array.from(document.querySelectorAll('.nav-item')).find(b=>b.title===${JSON.stringify(title)})?.click()`);
    await pause(200);
  };

  const input = async (selector, value) => {
    await js(`(()=>{
      const root=document.querySelector(${JSON.stringify(selector)});
      const e=root?.matches('input,textarea')?root:root?.querySelector('input,textarea');
      if(!e) throw new Error('缺少输入框 '+${JSON.stringify(selector)});
      const proto=e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto,'value').set.call(e,${JSON.stringify(value)});
      e.dispatchEvent(new Event('input',{bubbles:true}));
    })()`);
    await pause(80);
  };

  const setNthTextInput = async (pageSel, index, value) => {
    await js(`(()=>{
      const page=document.querySelector(${JSON.stringify(pageSel)});
      const inputs=[...page.querySelectorAll('input')].filter(e=>e.type!=='checkbox'&&e.type!=='radio');
      const e=inputs[${index}];
      if(!e) throw new Error('缺少第 ${index} 个输入 '+${JSON.stringify(pageSel)});
      const proto=HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto,'value').set.call(e,${JSON.stringify(value)});
      e.dispatchEvent(new Event('input',{bubbles:true}));
    })()`);
    await pause(100);
  };

  const capture = async (name) => {
    const result = await win.webContents.debugger.sendCommand('Page.captureScreenshot');
    fs.writeFileSync(path.join(out, name + '.png'), Buffer.from(result.data, 'base64'));
    log('CAPTURE ' + name + '.png');
  };

  const openToolbox = async () => {
    await page("Ren'Py 工具箱");
    await pause(180);
  };

  const openTool = async (title) => {
    await openToolbox();
    await input('.toolbox-search', title);
    await pause(160);
    await js('document.querySelector(".tool-card")?.click()');
    await pause(220);
  };

  const clearWrites = async () => {
    await js('__uiFixture.writes.length=0');
  };

  const setUnbound = async () => {
    await js(`(async()=>{
      __uiFixture.unbound=true;
      for (let i=0;i<50;i++){
        if (__uiFixture.sockets.some(s=>typeof s.onmessage==='function')) break;
        await new Promise(r=>setTimeout(r,40));
      }
      const delivered=__uiFixture.emitEvent('PROJECT_CHANGED', {});
      if (!delivered) throw new Error('WS onmessage 未就绪');
    })()`);
    await pause(450);
  };

  /**
   * 断言当前页 Banner 文案等于 fixture result.message，且所在 Alert 类型匹配；
   * 禁止仅凭页面上任意旧 warning 假阳性通过。
   */
  const assertMessageAlert = async (pageSel, message, tones, name) => {
    const allowed = (Array.isArray(tones) ? tones : [tones]).map((tone) => (
      tone === 'warning' ? 'ant-alert-warning' : tone === 'error' ? 'ant-alert-error' : 'ant-alert-success'
    ));
    await assert(`(()=>{
      const page=document.querySelector(${JSON.stringify(pageSel)});
      if(!page) return false;
      const msg=${JSON.stringify(message)};
      const nodes=[...page.querySelectorAll('.rb-banner-text')].filter(e=>(e.textContent||'')===msg || (e.textContent||'').includes(msg));
      if(!nodes.length) return false;
      return nodes.some(n=>{
        const alert=n.closest('.ant-alert');
        if(!alert || alert.classList.contains('ant-alert-success')) return false;
        return ${JSON.stringify(allowed)}.some(c=>alert.classList.contains(c));
      });
    })()`, name);
  };

  await assert("document.querySelector('.workspace-project').title==='C:/ui-check'", 'fixture 已绑定项目');

  // —— 抽取到 TL ——
  await openTool('翻译抽取到 TL');
  await assert("document.querySelector('[data-rb-page=extract-to-tl]')", '进入抽取到 TL');
  await clearWrites();
  await clickSubmit(
    '开始抽取',
    "__uiFixture.writes.some(w=>w.p==='/api/extract-to-tl/extract')",
    '开始抽取',
  );
  await assert("__uiFixture.writes.some(w=>w.p==='/api/extract-to-tl/extract')", '提交 extract');
  await js(`(()=>{
    const header=[...document.querySelectorAll('.ant-collapse-header')].find(h=>/高级|Advanced/.test(h.textContent||''));
    header?.click();
  })()`);
  // Collapse 展开动画：等合并按钮真实可命中（正尺寸/viewport/命中/rect 稳定），不用固定 sleep
  await waitButtonInteractable('立即合并增量', '高级面板合并按钮可交互');
  await clearWrites();
  await clickSubmit(
    '立即合并增量',
    "__uiFixture.writes.some(w=>w.p==='/api/extract-to-tl/merge-incremental')",
    '立即合并增量',
  );
  await assert("__uiFixture.writes.some(w=>w.p==='/api/extract-to-tl/merge-incremental')", '提交 merge');
  await clearWrites();
  await clickSubmit(
    '恢复勾选条目',
    "__uiFixture.writes.some(w=>w.p==='/api/extract-to-tl/restore-suspicious')",
    '恢复勾选条目',
  );
  await assert("__uiFixture.writes.some(w=>w.p==='/api/extract-to-tl/restore-suspicious')", '提交 restore');
  await capture('extract-to-tl-advanced');

  // —— JSON ——
  await openTool('文本提取 JSON');
  await assert("document.querySelector('[data-rb-page=extract-json]')", '进入文本提取 JSON');
  await clearWrites();
  await clickSubmit(
    '预览条目数',
    "__uiFixture.writes.some(w=>w.p==='/api/extract-json/preview'&&w.body.ensure_official===true)",
    '预览条目数',
  );
  await assert("__uiFixture.writes.some(w=>w.p==='/api/extract-json/preview'&&w.body.ensure_official===true)", '预览 ensure_official=true');
  await capture('extract-json-preview');

  // —— C: JSON import failed+partial → warning/error，非 success ——
  await js("__uiFixture.postModes['/api/extract-json/import-apply']='fail_partial'");
  await setNthTextInput('[data-rb-page=extract-json]', 3, 'C:/ui-check/translations.json');
  await clearWrites();
  await clickSubmit(
    '导入并应用',
    "__uiFixture.writes.some(w=>w.p==='/api/extract-json/import-apply')",
    '导入并应用',
  );
  await assertMessageAlert(
    '[data-rb-page=extract-json]',
    '部分写入后失败（fixture）',
    ['warning', 'error'],
    'JSON fail_partial 消息 Alert 为 warning/error',
  );
  await capture('extract-json-fail-partial');

  // —— C: TL restore failed+partial ——
  await openTool('翻译抽取到 TL');
  await js(`(()=>{
    const header=[...document.querySelectorAll('.ant-collapse-header')].find(h=>/高级|Advanced/.test(h.textContent||''));
    header?.click();
  })()`);
  await js("__uiFixture.postModes['/api/extract-to-tl/restore-suspicious']='fail_partial'");
  await waitButtonInteractable('恢复勾选条目', '高级面板恢复按钮可交互');
  await clearWrites();
  await clickSubmit(
    '恢复勾选条目',
    "__uiFixture.writes.some(w=>w.p==='/api/extract-to-tl/restore-suspicious')",
    '恢复勾选条目',
  );
  await assertMessageAlert(
    '[data-rb-page=extract-to-tl]',
    '部分写入后失败（fixture）',
    ['warning', 'error'],
    'TL fail_partial 消息 Alert 为 warning/error',
  );
  await capture('extract-to-tl-fail-partial');

  // —— 未绑定仍可打开两工具 ——
  await setUnbound();
  await openToolbox();
  await input('.toolbox-search', '翻译抽取到 TL');
  await assert('(()=>{const c=document.querySelector(".tool-card");return c&&!c.disabled;})()', '未绑定仍可点抽取到 TL');
  await js('document.querySelector(".tool-card")?.click()');
  await pause(220);
  await assert("document.querySelector('[data-rb-page=extract-to-tl]')", '未绑定可打开抽取到 TL');
  await capture('extract-to-tl-unbound');

  await openToolbox();
  await input('.toolbox-search', '文本提取 JSON');
  await assert('(()=>{const c=document.querySelector(".tool-card");return c&&!c.disabled;})()', '未绑定仍可点 JSON');
  await js('document.querySelector(".tool-card")?.click()');
  await pause(220);
  await assert("document.querySelector('[data-rb-page=extract-json]')", '未绑定可打开 JSON');
  await capture('extract-json-unbound');

  // —— A: 未绑定 manual 目标 + running 长任务 + 真实轮询保留取消 ——
  const manualGame = 'C:/manual-target/Demo.exe';
  const manualLang = 'chinese';
  await js("__uiFixture.postModes['/api/extract-json/preview']='running'");
  await js('__uiFixture.reads.length=0');
  await setNthTextInput('[data-rb-page=extract-json]', 0, manualGame);
  await setNthTextInput('[data-rb-page=extract-json]', 1, manualLang);
  // 等 statusPath 轮询带上 manual query（1.5s 周期）
  await assert(
    `__uiFixture.reads.some(r=>r.startsWith('/api/extract-json?')&&r.includes('game_file=')&&decodeURIComponent(r).includes('manual-target')&&r.includes('language=${manualLang}'))`,
    '未绑定 GET status 含 manual game_file/language',
  );
  await clearWrites();
  await waitButtonEnabled('预览条目数');
  await clickSubmit(
    '预览条目数',
    "__uiFixture.writes.some(w=>w.p==='/api/extract-json/preview'&&String(w.body.game_file||'').includes('manual-target'))",
    '取消任务',
  );
  await assert(
    "document.querySelector('[data-rb-page=extract-json] button') && [...document.querySelectorAll('[data-rb-page=extract-json] button')].some(b=>b.textContent.includes('取消')&&!b.disabled)",
    '长任务显示取消按钮',
  );
  // 至少再等一轮真实轮询（>1.5s），仍 running 且读 URL 含目标
  const readsBefore = await js('__uiFixture.reads.length');
  await assert(
    `__uiFixture.reads.length>${readsBefore}&&__uiFixture.reads.slice(${readsBefore}).some(r=>r.includes('/api/extract-json?')&&decodeURIComponent(r).includes('manual-target')&&r.includes('language=${manualLang}'))`,
    '定时轮询仍按 manual 目标读取 status',
  );
  await assert(
    "Object.values(__uiFixture.jsonJobsByKey).some(j=>j&&j.status==='running'&&j.result&&j.result.worker_active)",
    'fixture 目标 job 仍为 running',
  );
  // 真实 DOM：running 业务消息 + Progress + 可用取消（active 时 Banner 为 info）
  await assert(`(()=>{
    const page=document.querySelector('[data-rb-page=extract-json]');
    if(!page) return false;
    const msg='任务进行中（fixture running）';
    const hasMsg=[...page.querySelectorAll('.rb-banner-text')].some(e=>(e.textContent||'').includes(msg));
    const hasProgress=!!page.querySelector('.ant-progress,[aria-label="任务进行中…"]');
    const hasCancel=[...page.querySelectorAll('button')].some(b=>(b.textContent||'').includes('取消')&&!b.disabled);
    return hasMsg&&hasProgress&&hasCancel;
  })()`, 'DOM 仍显示 running 消息/Progress/取消');
  await capture('extract-json-unbound-running');

  // —— A 导航恢复：离开再重开 JSON，同 manual 目标由 GET 恢复 running，无新 preview POST ——
  await openToolbox();
  await input('.toolbox-search', '文本提取 JSON');
  await js('document.querySelector(".tool-card")?.click()');
  await pause(220);
  await assert("document.querySelector('[data-rb-page=extract-json]')", '导航重开 JSON 页');
  await clearWrites();
  const readsAtReopen = await js('__uiFixture.reads.length');
  await setNthTextInput('[data-rb-page=extract-json]', 0, manualGame);
  await setNthTextInput('[data-rb-page=extract-json]', 1, manualLang);
  await assert(
    `__uiFixture.reads.length>${readsAtReopen}&&__uiFixture.reads.slice(${readsAtReopen}).some(r=>{
      const d=decodeURIComponent(r);
      return r.includes('/api/extract-json?')&&d.includes('manual-target')&&r.includes('language=${manualLang}');
    })`,
    '重开后新 GET status 含同 manual 目标',
  );
  await assert(
    "Object.values(__uiFixture.jsonJobsByKey).some(j=>j&&j.status==='running'&&j.result&&j.result.worker_active)",
    '重开后 fixture 仍为同目标 running job',
  );
  await assert(`(()=>{
    const page=document.querySelector('[data-rb-page=extract-json]');
    if(!page) return false;
    const msg='任务进行中（fixture running）';
    const hasMsg=[...page.querySelectorAll('.rb-banner-text')].some(e=>(e.textContent||'').includes(msg));
    const hasCancel=[...page.querySelectorAll('button')].some(b=>(b.textContent||'').includes('取消')&&!b.disabled);
    return hasMsg&&hasCancel;
  })()`, '重开恢复后 DOM 仍 running/可取消');
  await assert(
    "!__uiFixture.writes.some(w=>w.p==='/api/extract-json/preview')",
    '重开恢复无新 preview POST',
  );
  await capture('extract-json-unbound-reopen-running');

  // —— B: 真实取消 → cancelled + 对应消息 warning；取消后必须出现新的目标 status GET ——
  const readsAtCancel = await js('__uiFixture.reads.length');
  await clearWrites();
  await click('取消任务');
  await assert(
    "__uiFixture.writes.some(w=>/^\\/api\\/jobs\\/extract-parity-\\d+\\/cancel$/.test(w.p))",
    '真实取消 POST',
  );
  await assert(
    "Object.values(__uiFixture.jsonJobsByKey).some(j=>j&&j.status==='cancelled'&&j.cancel_requested===true&&j.result&&j.result.success===false&&j.result.partial===true&&j.result.written===true&&Array.isArray(j.result.written_files)&&j.result.written_files.length&&j.result.worker_active===false)",
    '取消终态保留 written/partial 元数据',
  );
  await assert(
    `__uiFixture.reads.length>${readsAtCancel}&&__uiFixture.reads.slice(${readsAtCancel}).some(r=>{
      const d=decodeURIComponent(r);
      return r.includes('/api/extract-json?')&&d.includes('manual-target')&&r.includes('language=${manualLang}');
    })`,
    '取消后新 status GET 含当前 manual 目标',
  );
  await assertMessageAlert(
    '[data-rb-page=extract-json]',
    '任务已取消（已保留写入结果）',
    ['warning'],
    '取消消息 Alert 为 warning',
  );
  await capture('extract-json-unbound-cancelled');

  // 轻量 done+success=false：cleanup 场景（消息必须落到 warning，不能复用旧 cancel warning）
  await js("__uiFixture.postModes['/api/extract-json/cleanup']='done_success_false'");
  await js("__uiFixture.postModes['/api/extract-json/preview']='default'");
  await waitButtonEnabled('清理 TL 重复');
  await clearWrites();
  await clickSubmit(
    '清理 TL 重复',
    "__uiFixture.writes.some(w=>w.p==='/api/extract-json/cleanup')",
    '清理 TL 重复',
  );
  await assertMessageAlert(
    '[data-rb-page=extract-json]',
    '业务未完成（fixture done success=false）',
    ['warning'],
    'done success=false 消息 Alert 为 warning',
  );

  if (errors.length) throw new Error('控制台错误：' + JSON.stringify(errors));
  log('ALL EXTRACT PARITY CHECKS PASSED');
  win.destroy();
  app.quit();
}).catch((error) => {
  log(error.stack || String(error));
  app.exit(1);
});
