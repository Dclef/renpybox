/**
 * Direct / Source / HOOK / Supplement 受控 UI 验收（modes 范围）。
 *
 * 运行：
 *   清除 ELECTRON_RUN_AS_NODE
 *   UI_URL=http://127.0.0.1:5179
 *   RENPYBOX_UI_CAPTURE_DIR=%TEMP%\\renpybox-qt5-parity\\new-ui-modes
 *   cd desktop && npx electron scripts/check-modes-parity.cjs
 *
 * 独立 --user-data-dir（app.setPath userData）防 cache 竞争；不触发真实游戏/收费 API。
 * fixture 在文档加载前注入（CDP），与 check-translation-parity 同口径。
 */
if (process.type !== 'browser') throw new Error('请使用 Electron 主进程运行，并先清除 ELECTRON_RUN_AS_NODE。');

const { app, BrowserWindow } = require('electron');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const out = process.env.RENPYBOX_UI_CAPTURE_DIR
  || path.join(os.tmpdir(), 'renpybox-qt5-parity', 'new-ui-modes');
const profileDir = path.join(os.tmpdir(), 'renpybox-modes-parity-profile-' + Date.now());
const logPath = path.join(out, 'modes-parity.log');
const pause = (ms) => new Promise((r) => setTimeout(r, ms));
const log = (value) => fs.appendFileSync(logPath, value + '\n');

fs.mkdirSync(out, { recursive: true });
fs.mkdirSync(profileDir, { recursive: true });
fs.writeFileSync(logPath, '');
app.setPath('userData', profileDir);

/** 与 renderer/src/tools.ts translate 组一致 */
const TRANSLATE_TOOLS = [
  { key: 'rpy_extraction_settings', title: 'RPY 抽取设置', page: 'rpy-extraction', requiresProject: false, primary: '应用设置', api: '/api/rpy-extraction/select' },
  { key: 'extract_to_tl', title: '翻译抽取到 TL', page: 'extract-to-tl', requiresProject: false, primary: '开始抽取', api: '/api/extract-to-tl/extract' },
  { key: 'direct_rpy_translate', title: '直接翻译 RPY', page: 'direct-rpy-translate', requiresProject: false, primary: '开始翻译', api: '/api/translation/start' },
  { key: 'hook_translate', title: 'HOOK 翻译', page: 'hook-translate', requiresProject: true, primary: '开始 HOOK 翻译', api: '/api/hook-translate/start' },
  { key: 'source_translate', title: '源码翻译', page: 'source-translate', requiresProject: true, primary: '开始翻译', api: '/api/translation/start' },
  { key: 'hook_supplement', title: '补全翻译', page: 'hook-supplement', requiresProject: true, primary: '开始补全翻译', api: '/api/translation/start' },
  { key: 'extract_json', title: '文本提取 JSON', page: 'extract-json', requiresProject: false, primary: '预览条目数', api: '/api/extract-json/preview' },
];

const PROJECT_REQUIRED = TRANSLATE_TOOLS.filter((t) => t.requiresProject).map((t) => t.title);
const PROJECT_OPTIONAL = TRANSLATE_TOOLS.filter((t) => !t.requiresProject).map((t) => t.title);

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
    toolProjectKey: 'c:\\ui-check|chinese',
    toolSerial: 0,
    toolJobs: {},
    rpyStatus: {
      applied_mode: 'builtin',
      applied_profile_id: null,
      applied_name: '内置',
      mode_labels: { builtin: '只用内置', combined: '内置＋自定义', custom: '仅自定义' },
      profiles: [],
      profile_docs: [],
      summary: '当前已生效：只用内置',
      no_profile_label: '未选择自定义方案',
    },
    extractStatus: {
      has_existing_tl: false,
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
    hookJob: null,
    /** 为 true 时 HOOK stop 返回 409，用于验证不得 fallback 全局 translation/stop */
    hookStopConflict: false,
    /** 与 /api/translation/state 对齐的本轮 request/run（HOOK 推进后写入） */
    translationRequestId: 'fixture',
    translationRunId: 0,
    /** 可释放 gate：抽取完成→翻译运行 的回调，由测试显式 release，禁止盲延时 */
    _hookFinishExtract: null,
  };

  /** 受控推进：抽取完成 → engine TRANSLATING + request/run=7 */
  f.releaseHookToTranslating = () => {
    const finish = f._hookFinishExtract;
    if (typeof finish !== 'function') {
      throw new Error('HOOK gate：无待推进的抽取任务');
    }
    f._hookFinishExtract = null;
    finish();
  };

  /** 终态清理：回到 IDLE，便于再次点击 Start / 后续窄屏门禁 */
  f.releaseHookToIdle = () => {
    f._hookFinishExtract = null;
    f.engineStatus = 'IDLE';
    f.translationRequestId = 'fixture';
    f.translationRunId = 0;
    f.hookStopConflict = false;
    f.emitEvent('TRANSLATION_DONE', {});
  };

  window.confirm = () => true;
  const response = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });

  const projectPayload = () => {
    if (f.unbound) {
      return { renpy_project_path: '', renpy_game_folder: '', renpy_tl_folder: '' };
    }
    const root = 'C:/ui-check';
    return {
      renpy_project_path: root,
      renpy_game_folder: root + '/game',
      renpy_tl_folder: values.input_folder,
    };
  };

  const mkJob = (kind, body, message = '模拟完成') => {
    const id = 'parity-task-' + (f.toolSerial += 1);
    const key = String(body.project_key || f.toolProjectKey);
    return {
      id,
      kind,
      status: 'done',
      total: 1,
      done: 1,
      progress: 1,
      error: null,
      created_at: Date.now() / 1000,
      updated_at: Date.now() / 1000,
      result: { project_key: key, message, worker_active: false, action: kind },
    };
  };

  const toolStatus = (extra = {}) => ({
    project_key: f.toolProjectKey,
    project_root: 'C:/ui-check',
    game_dir: 'C:/ui-check/game',
    language: 'chinese',
    tl_dir: 'C:/ui-check/game/tl/chinese',
    job: null,
    ...extra,
  });

  const nativeFetch = fetch.bind(window);
  window.fetch = async (url, options = {}) => {
    const parsed = new URL(String(url), location.href);
    const p = parsed.pathname;
    const qs = parsed.search;
    // query 供 stop 等断言核对真实请求参数（非伪造）
    const query = Object.fromEntries(parsed.searchParams.entries());
    if (p !== '/health' && !p.startsWith('/api/')) return nativeFetch(url, options);
    const method = options.method || 'GET';
    const body = options.body ? JSON.parse(options.body) : {};
    if (method !== 'GET') f.writes.push({ p, method, body, query });
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
        request_id: f.translationRequestId,
        run_id: f.translationRunId,
        running: { running: 0, max: 4 },
        progress: f.progress,
        progress_source: f.progressSource,
        progress_error: '',
        active_output_folder: values.output_folder,
      });
    }
    if (p === '/api/translation/start' && method === 'POST') {
      if (body.mode === 'source' && (body.renpy_backup_original || body.external_backup_dir)) {
        const job = mkJob('source_prebackup', body, '正在备份源码…');
        job.status = 'running';
        job.result.stage = 'backing_up';
        job.result.worker_active = true;
        job.result.translation_started = false;
        f.toolJobs.source_prebackup = job;
        setTimeout(() => {
          job.status = 'done';
          job.done = 1;
          job.progress = 1;
          job.result.worker_active = false;
          job.result.translation_started = true;
          job.result.stage = 'translating';
          job.result.message = '备份完成，翻译已启动';
          f.emitEvent('TRANSLATION_START_RESULT', { accepted: true, request_id: body.request_id || '', run_id: 3 });
        }, 180);
        return response({ accepted: true, reason: 'STARTED', stage: 'backing_up', request_id: body.request_id || job.id, job });
      }
      return response({ accepted: true, reason: 'STARTED', stage: 'translating', detail: 'modes mock', request_id: body.request_id || 'modes' });
    }
    if (p === '/api/translation/stop' && method === 'POST') return response({ ok: true, status: 'STOPPING' });
    if (p === '/api/translation/reinject' && method === 'POST') {
      return response({
        ok: true,
        output_folder: body.output_folder || (body.tl_parent ? `${body.tl_parent}/${body.tl_name || 'chinese'}` : ''),
      });
    }
    if (/^\/api\/jobs\/parity-task-/.test(p) && method === 'GET') {
      const id = p.split('/')[3];
      const job = Object.values(f.toolJobs).find((j) => j.id === id) || f.hookJob;
      return response(job || { id, status: 'done', result: {} });
    }
    if (p === '/api/hook-translate/status') {
      return response({ project_key: f.toolProjectKey, job: f.hookJob });
    }
    if (p === '/api/hook-translate/start' && method === 'POST') {
      f.hookJob = mkJob('hook_translate', body, '正在准备运行时 HOOK 抽取…');
      f.hookJob.status = 'running';
      f.hookJob.result.translation_started = false;
      f.hookJob.result.stage = 'extracting';
      f.hookJob.result.worker_active = true;
      f.hookJob.result.request_id = body.request_id || f.hookJob.id;
      const requestId = f.hookJob.result.request_id;
      // gated worker：保持抽取运行态，直至测试调用 releaseHookToTranslating
      f._hookFinishExtract = () => {
        if (!f.hookJob) return;
        f.hookJob.status = 'done';
        f.hookJob.done = 1;
        f.hookJob.progress = 1;
        f.hookJob.result.worker_active = false;
        f.hookJob.result.translation_started = true;
        f.hookJob.result.translation_run_id = 7;
        f.hookJob.result.stage = 'translating';
        f.hookJob.result.message = '运行时抽取完成，翻译已启动';
        f.hookJob.result.tl_dir = 'C:/ui-check/game/tl/chinese';
        f.translationRequestId = requestId;
        f.translationRunId = 7;
        f.engineStatus = 'TRANSLATING';
        f.emitEvent('TRANSLATION_START_RESULT', { accepted: true, request_id: requestId, run_id: 7 });
      };
      return response({ accepted: true, reason: 'STARTED', request_id: requestId, job: f.hookJob });
    }
    if (p === '/api/hook-translate/stop' && method === 'POST') {
      if (f.hookStopConflict) {
        // 校验真实 stop 查询与本轮 HOOK owner/request/run 一致后再返回 409
        const expectedOwner = String(f.hookJob?.result?.project_key || f.toolProjectKey);
        const expectedReq = String(f.hookJob?.result?.request_id || '');
        const expectedRun = String(f.hookJob?.result?.translation_run_id || 0);
        if (query.project_key !== expectedOwner) {
          throw new Error('HOOK stop owner 不匹配: ' + query.project_key + ' != ' + expectedOwner);
        }
        if (query.request_id !== expectedReq) {
          throw new Error('HOOK stop request_id 不匹配: ' + query.request_id + ' != ' + expectedReq);
        }
        if (query.run_id !== expectedRun) {
          throw new Error('HOOK stop run_id 不匹配: ' + query.run_id + ' != ' + expectedRun);
        }
        return response({ detail: '当前没有可停止的 HOOK 抽取或翻译任务' }, 409);
      }
      if (f.hookJob) f.hookJob.status = 'cancelled';
      return response({ ok: true, stage: 'extracting', job_id: f.hookJob?.id });
    }
    if (p === '/api/extract-to-tl' && method === 'GET') {
      return response(toolStatus({ ...f.extractStatus, job: f.toolJobs.extract_to_tl || null }));
    }
    if (p.startsWith('/api/extract-to-tl/') && method === 'POST') {
      const kind = p.includes('merge') ? 'extract_to_tl_merge' : p.includes('restore') ? 'extract_to_tl_restore' : 'extract_to_tl';
      const job = mkJob(kind, body);
      f.toolJobs.extract_to_tl = job;
      return response({ job });
    }
    if (p.startsWith('/api/extract-to-tl/suspicious-backups')) {
      return response({ manifests: [], available: false });
    }
    if (p === '/api/extract-json' && method === 'GET') {
      return response(toolStatus({ ...f.jsonStatus, job: f.toolJobs.extract_json || null }));
    }
    if (p.startsWith('/api/extract-json/') && method === 'POST') {
      const kind = ({
        '/api/extract-json/preview': 'extract_json_preview',
        '/api/extract-json/export-json': 'extract_json_export',
        '/api/extract-json/import-apply': 'extract_json_import',
        '/api/extract-json/cleanup': 'extract_json_cleanup',
        '/api/extract-json/export-tl-json': 'extract_json_export_tl',
      })[p] || 'extract_json';
      const job = mkJob(kind, body);
      job.result.file_count = 1;
      job.result.entry_count = 2;
      f.toolJobs.extract_json = job;
      return response({ job });
    }
    if (p === '/api/rpy-extraction' && method === 'GET') {
      return response(toolStatus({ ...f.rpyStatus, path: 'C:/ui-check', category: 'source', job: f.toolJobs.rpy || null }));
    }
    if (p.startsWith('/api/rpy-extraction/') && method === 'POST') {
      if (p === '/api/rpy-extraction/select') {
        f.rpyStatus.applied_mode = body.mode || 'builtin';
        f.rpyStatus.applied_profile_id = body.profile_id ?? null;
        f.rpyStatus.applied_name = body.mode === 'builtin' ? '内置' : '自定义';
        f.rpyStatus.summary = 'parity applied';
        return response(toolStatus({
          ...f.rpyStatus,
          applied_mode: f.rpyStatus.applied_mode,
          applied_profile_id: f.rpyStatus.applied_profile_id,
          applied_name: f.rpyStatus.applied_name,
        }));
      }
      if (p === '/api/rpy-extraction/preview' || p === '/api/rpy-extraction/preview/continue') {
        const job = mkJob('rpy_extraction_preview', body);
        f.toolJobs.rpy = job;
        return response({ job });
      }
      if (p === '/api/rpy-extraction/profiles') {
        const category = body.category || 'source';
        const editor = body.starter
          ? f.starterProfile(category)
          : {
            id: 'profile-parity-empty',
            name: '当前游戏补充规则',
            note: '',
            category,
            rules: [],
          };
        return response(toolStatus({
          ...f.rpyStatus,
          editor_profile: editor,
        }));
      }
      return response(toolStatus(f.rpyStatus));
    }
    if (/^\/api\/jobs\/parity-task-\d+\/cancel$/.test(p)) {
      const job = Object.values(f.toolJobs).find((j) => j.id === p.split('/')[3]) || f.hookJob;
      if (job) job.cancel_requested = true;
      return response(job || { ok: true });
    }
    if (p === '/api/jobs') return response({ jobs: [] });

    throw new Error('parity 自检未定义接口：' + method + ' ' + p + qs);
  };

  const starterRule = (id, name, pattern, example) => ({
    id,
    name,
    enabled: true,
    include_globs: ['*.rpy', '**/*.rpy'],
    pattern,
    flags: [],
    text_group: 'text',
    note: '',
    positive_samples: [example],
    negative_samples: ['jump next_label'],
  });

  f.starterProfile = (category = 'source') => ({
    id: 'profile-parity-starter',
    name: '常用 RPY 规则副本',
    note: '',
    category,
    rules: category === 'tl'
      ? [
        starterRule('rule-old', 'old/new 字符串', String.raw`^\s*old\s+(?P<text>"(?:\\.|[^"\\])*")\s*$`, 'old "Hello."'),
        starterRule('rule-dlg', '对白 / 旁白', String.raw`^\s*(?!(?:old|new)\b)(?:[a-zA-Z_]\w*\s+)?(?P<text>"(?:\\.|[^"\\])*")\s*$`, 'e "Hello."'),
      ]
      : [
        starterRule('rule-dlg', '对白 / 旁白', String.raw`^\s*(?:[a-zA-Z_]\w*\s+)?(?P<text>"(?:\\.|[^"\\])*")\s*$`, 'e "Hello."'),
        starterRule('rule-menu', '菜单选项', String.raw`^\s*(?P<text>"(?:\\.|[^"\\])*")\s*:\s*$`, '"Continue":'),
        starterRule('rule-ui', '界面文本', String.raw`^\s*(?:text|textbutton)\s+(?P<text>"(?:\\.|[^"\\])*")\s*$`, 'text "Hello."'),
      ],
  });

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
  await win.loadURL(process.env.UI_URL || process.env.RENPYBOX_UI_URL || 'http://127.0.0.1:5179');

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

  const assert = async (expression, name) => {
    for (let attempt = 0; attempt < 8; attempt++) {
      if (await js(`Boolean(${expression})`)) {
        log('PASS ' + name);
        return;
      }
      await pause(120);
    }
    log('FAIL CONTEXT ' + JSON.stringify(await js(`({
      page: document.querySelector('.content')?.dataset.page,
      toolPage: document.querySelector('[data-rb-page]')?.getAttribute('data-rb-page'),
      writes: __uiFixture.writes.slice(-4).map(w=>({p:w.p,method:w.method})),
      card: document.querySelector('.tool-card')?.outerHTML?.slice(0,200)
    })`)));
    throw new Error('FAIL ' + name);
  };

  const click = async (text) => {
    const position = await js(`(()=>{
      const dialogs=[...document.querySelectorAll('[role=dialog]')].filter(e=>e.getBoundingClientRect().height>0);
      const scope=dialogs.at(-1)||document;
      const normalized=${JSON.stringify(text.replaceAll(' ', ''))};
      const e=[...scope.querySelectorAll('button,[role=tab],[role=menuitem]')].find(b=>b.textContent.split(' ').join('')===normalized);
      if(!e) throw new Error('缺少操作 '+${JSON.stringify(text)});
      if(e.disabled) throw new Error('操作被禁用 '+${JSON.stringify(text)});
      e.scrollIntoView({block:'nearest'});
      const r=e.getBoundingClientRect();
      return {x:r.left+r.width/2,y:r.top+r.height/2};
    })()`);
    await win.webContents.debugger.sendCommand('Input.dispatchMouseEvent', { type: 'mousePressed', ...position, button: 'left', clickCount: 1 });
    await win.webContents.debugger.sendCommand('Input.dispatchMouseEvent', { type: 'mouseReleased', ...position, button: 'left', clickCount: 1 });
    await pause(220);
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

  const capture = async (name) => {
    const result = await win.webContents.debugger.sendCommand('Page.captureScreenshot');
    fs.writeFileSync(path.join(out, name + '.png'), Buffer.from(result.data, 'base64'));
  };

  const openToolbox = async () => {
    await page("Ren'Py 工具箱");
    await pause(180);
  };

  const searchTool = async (title) => {
    await input('.toolbox-search', title);
    await pause(160);
  };

  const openTool = async (title) => {
    await openToolbox();
    await searchTool(title);
    await js('document.querySelector(".tool-card")?.click()');
    await pause(220);
  };

  const clearWrites = async () => {
    await js('__uiFixture.writes.length=0');
  };

  const waitToolPage = async (pageKey) => {
    await assert(`document.querySelector('.content')?.dataset.page==='${pageKey}'`, '进入页面 ' + pageKey);
  };

  /** 条件等待按钮可点（不盲 pause）；覆盖 HOOK 800ms 轮询窗 */
  const waitButtonEnabled = async (text, name) => {
    const normalized = JSON.stringify(text.replaceAll(' ', ''));
    for (let attempt = 0; attempt < 40; attempt++) {
      const ok = await js(`([...document.querySelectorAll('button')].some(b=>b.textContent.split(' ').join('')===${normalized}&&!b.disabled))`);
      if (ok) {
        log('PASS ' + name);
        return;
      }
      await pause(100);
    }
    throw new Error('FAIL ' + name);
  };

  await assert("document.querySelector('.workspace-project').title==='C:/ui-check'", 'fixture 已绑定项目');

  // —— Direct ——
  await openTool('直接翻译 RPY');
  await waitToolPage('direct-rpy-translate');
  await assert("document.querySelector('[data-rb-page=direct-rpy-translate]')", 'Direct 页面挂载');
  await assert("document.querySelector('[aria-label=\"写入前备份 .bak\"]')?.getAttribute('aria-checked')==='false'", 'Direct 默认不备份');
  await assert("document.querySelector('[aria-label=\"自动写回文件\"]')?.getAttribute('aria-checked')==='true'", 'Direct 默认自动写回');
  await clearWrites();
  await click('开始翻译');
  await assert("__uiFixture.writes.some(w=>w.p==='/api/translation/start'&&w.body.mode==='direct'&&w.body.renpy_backup_original===false&&w.body.auto_write_back===true&&typeof w.body.project_key==='string')", 'Direct start 含 mode/owner');
  await clearWrites();
  await click('手动写回');
  await assert("__uiFixture.writes.some(w=>w.p==='/api/translation/reinject')", 'Direct 手动写回 reinject');
  await capture('direct-rpy-translate');

  // —— Source：输出只读 + 备份 job ——
  await openTool('源码翻译');
  await waitToolPage('source-translate');
  await assert("document.querySelector('[data-rb-page=source-translate] input[disabled]')", 'Source 输出只读/禁用');
  await assert("document.querySelector('[aria-label=\"自动备份 .bak\"]')?.getAttribute('aria-checked')==='false'", 'Source 默认不备份');
  await clearWrites();
  await click('开始翻译');
  await assert("__uiFixture.writes.some(w=>w.p==='/api/translation/start'&&w.body.mode==='source'&&!('output_folder' in w.body)&&typeof w.body.project_key==='string')", 'Source start 无手写 output');
  // 打开本地备份后应走 backing_up job
  await js(`(()=>{const sw=document.querySelector('[aria-label=\"自动备份 .bak\"]');if(sw&&sw.getAttribute('aria-checked')==='false')sw.click();})()`);
  await pause(120);
  await clearWrites();
  await click('开始翻译');
  await assert("__uiFixture.writes.some(w=>w.p==='/api/translation/start'&&w.body.mode==='source'&&w.body.renpy_backup_original===true)", 'Source 备份 start');
  await pause(400);
  await capture('source-translate');

  // —— Supplement：自定义 TL 父目录 ——
  await openTool('补全翻译');
  await waitToolPage('hook-supplement');
  await assert("document.querySelector('[data-rb-page=hook-supplement]')", 'Supplement 页面挂载');
  await clearWrites();
  await click('开始补全翻译');
  await assert("__uiFixture.writes.some(w=>w.p==='/api/translation/start'&&w.body.mode==='supplement'&&typeof w.body.project_key==='string')", 'Supplement start 含 owner');
  await capture('hook-supplement');

  // —— HOOK：两阶段 busy / START_RESULT（gated：显式推进抽取→翻译，再清 IDLE）——
  await openTool('HOOK 翻译');
  await waitToolPage('hook-translate');
  await assert("document.querySelector('[aria-label=\"增量补全（仅追加缺失项）\"]')", 'HOOK 增量开关');
  await clearWrites();
  await click('开始 HOOK 翻译');
  await assert("__uiFixture.writes.some(w=>w.p==='/api/hook-translate/start'&&w.body.renpy_backup_original===false&&typeof w.body.project_key==='string')", 'HOOK start 含 owner');
  await js('__uiFixture.releaseHookToTranslating()');
  await assert(
    "__uiFixture.engineStatus==='TRANSLATING'&&__uiFixture.hookJob?.result?.translation_started===true&&__uiFixture.translationRunId===7",
    'HOOK smoke 已进入翻译运行态',
  );
  await waitButtonEnabled('停止', 'HOOK smoke 停止已启用');
  // 与 409 段交接：必须回到 IDLE，否则第二次 Start 会被引擎忙门禁挡住
  await js('__uiFixture.releaseHookToIdle()');
  await assert("__uiFixture.engineStatus==='IDLE'", 'HOOK smoke 已回到 IDLE');
  await waitButtonEnabled('开始 HOOK 翻译', 'HOOK 可再次开始');
  await capture('hook-translate');

  // —— HOOK stop 409：翻译运行态真实点停止，mock 校验 owner/request/run 后 409，不得 fallback 全局 stop ——
  await js('__uiFixture.hookStopConflict=true');
  await clearWrites();
  await click('开始 HOOK 翻译');
  await assert("__uiFixture.writes.some(w=>w.p==='/api/hook-translate/start'&&typeof w.body.project_key==='string')", 'HOOK 409 轮 start 含 owner');
  await js('__uiFixture.releaseHookToTranslating()');
  await assert(
    "__uiFixture.engineStatus==='TRANSLATING'&&__uiFixture.hookJob?.result?.translation_run_id===7&&__uiFixture.translationRequestId===__uiFixture.hookJob.result.request_id",
    'HOOK 409 轮 request/run 已对齐',
  );
  await waitButtonEnabled('停止', 'HOOK 409 停止已启用');
  await clearWrites();
  await js('__uiFixture.reads.length=0');
  await click('停止');
  await assert(
    "__uiFixture.writes.some(w=>w.p==='/api/hook-translate/stop'&&w.query&&w.query.project_key&&w.query.request_id&&w.query.run_id==='7')",
    'HOOK stop 发起本页 stop（含 owner/request/run）',
  );
  log('EVIDENCE stop query ' + JSON.stringify(await js(`__uiFixture.writes.filter(w=>w.p==='/api/hook-translate/stop').map(w=>w.query)`)));
  await assert("!__uiFixture.writes.some(w=>w.p==='/api/translation/stop')", 'HOOK stop 409 不得 fallback 全局 stop');
  await assert(
    "__uiFixture.reads.some(r=>r.includes('/api/hook-translate/status'))||!!document.querySelector('[data-rb-toast][title*=\"当前没有可停止的 HOOK\"]')||document.body.textContent.includes('当前没有可停止的 HOOK 抽取或翻译任务')",
    'HOOK stop 409 文案/重读路径',
  );
  await js('__uiFixture.releaseHookToIdle()');
  await assert("__uiFixture.engineStatus==='IDLE'", 'HOOK 409 后已清理至 IDLE');

  // —— 窄屏烟雾 ——
  await win.webContents.debugger.sendCommand('Emulation.setDeviceMetricsOverride', {
    width: 680,
    height: 800,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await pause(200);
  await capture('hook-translate-narrow');
  await win.webContents.debugger.sendCommand('Emulation.clearDeviceMetricsOverride');

  // —— requiresProject 门禁（modes 三页）——
  await js(`(async()=>{
    __uiFixture.unbound=true;
    for (let i=0;i<50;i++){
      if (__uiFixture.sockets.some(s=>typeof s.onmessage==='function')) break;
      await new Promise(r=>setTimeout(r,40));
    }
    const delivered=__uiFixture.emitEvent('PROJECT_CHANGED', {});
    if (!delivered) throw new Error('WS onmessage 未就绪，无法投递 PROJECT_CHANGED');
  })()`);
  await pause(450);
  await openToolbox();
  for (const title of ['HOOK 翻译', '源码翻译', '补全翻译']) {
    await searchTool(title);
    await assert('(()=>{const c=document.querySelector(".tool-card");return c&&c.disabled;})()', '未绑定禁用 ' + title);
  }
  await searchTool('直接翻译 RPY');
  await assert('(()=>{const c=document.querySelector(".tool-card");return c&&!c.disabled;})()', 'Direct 未绑定仍可点');

  if (errors.length) throw new Error('控制台错误：' + JSON.stringify(errors));
  log('ALL MODES PARITY CHECKS PASSED');
  win.destroy();
  app.quit();
}).catch((error) => {
  log(error.stack || String(error));
  app.exit(1);
});
