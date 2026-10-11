/**
 * 翻译方式工具箱 UI 对等自检（7 款 translate 组工具）。
 *
 * 运行方式（与 check-ui.cjs 相同）：
 * 1. 在 desktop 目录启动 Vite：`npm run dev:renderer`
 * 2. 清除 ELECTRON_RUN_AS_NODE，以 Electron 主进程执行本脚本，例如：
 *    `cd desktop && npx electron scripts/check-translation-parity.cjs`
 * 3. 可选环境变量：
 *    - RENPYBOX_UI_URL（默认 http://127.0.0.1:5173）
 *    - RENPYBOX_UI_CAPTURE_DIR（截图与 translation-parity.log 输出目录，默认系统 tmp）
 *
 * 使用受控 fetch/WebSocket 快照，不触发真实游戏进程或付费翻译接口。
 */
if (process.type !== 'browser') throw new Error('请使用 Electron 主进程运行，并先清除 ELECTRON_RUN_AS_NODE。');

const { app, BrowserWindow } = require('electron');
const fs = require('node:fs');
const path = require('node:path');

const out = process.env.RENPYBOX_UI_CAPTURE_DIR || require('node:os').tmpdir();
const logPath = path.join(out, 'translation-parity.log');
const pause = (ms) => new Promise((r) => setTimeout(r, ms));
const log = (value) => fs.appendFileSync(logPath, value + '\n');

fs.mkdirSync(out, { recursive: true });
fs.writeFileSync(logPath, '');

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
  };

  window.confirm = () => true;
  const response = (data) => new Response(JSON.stringify(data), { status: 200, headers: { 'Content-Type': 'application/json' } });

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
    const p = new URL(String(url), location.href).pathname;
    const qs = new URL(String(url), location.href).search;
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
    if (p === '/api/translation/start' && method === 'POST') {
      return response({ accepted: true, reason: 'STARTED', detail: 'parity mock' });
    }
    if (p === '/api/translation/stop' && method === 'POST') return response({ ok: true, status: 'STOPPING' });
    if (p === '/api/translation/reinject' && method === 'POST') return response({ ok: true, output_folder: body.output_folder });
    if (p === '/api/hook-translate/status') {
      return response({ project_key: f.toolProjectKey, job: f.hookJob });
    }
    if (p === '/api/hook-translate/start' && method === 'POST') {
      f.hookJob = mkJob('hook_translate', body, 'HOOK 抽取已模拟完成');
      f.hookJob.result.translation_started = false;
      return response({ accepted: true, job: f.hookJob });
    }
    if (p === '/api/hook-translate/stop' && method === 'POST') {
      if (f.hookJob) f.hookJob.status = 'cancelled';
      return response({ ok: true, stage: 'extract', job_id: f.hookJob?.id });
    }
    // 与 extract-parity 一致：GET 识别 query；手动目标键与 job 按目标身份返回
    const extractTargetKey = (raw, language = 'chinese') => {
      let text = String(raw || '').trim().replace(/\\/g, '/').replace(/\/+$/, '');
      if (!text) return '';
      const base = text.split('/').pop() || '';
      if (/\.(exe|py|rpy)$/i.test(base)) text = text.replace(/\/[^/]+$/, '');
      if (text.toLowerCase().endsWith('/game')) text = text.slice(0, -5);
      const norm = text.replace(/\//g, '\\').toLowerCase();
      return `${norm}|${String(language || 'chinese').trim().toLowerCase() || 'chinese'}`;
    };
    if ((p === '/api/extract-to-tl' || p.startsWith('/api/extract-to-tl?')) && method === 'GET') {
      const u = new URL(String(url), location.href);
      const lang = u.searchParams.get('language') || 'chinese';
      const gameDir = (u.searchParams.get('game_dir') || '').trim();
      if (gameDir) {
        const key = extractTargetKey(gameDir, lang);
        return response(toolStatus({
          ...f.extractStatus,
          project_key: key,
          language: lang,
          job: (f.toolJobs.extract_to_tl?.result?.project_key === key) ? f.toolJobs.extract_to_tl : null,
        }));
      }
      if (f.unbound) {
        return response(toolStatus({ project_key: '', job: null, language: lang }));
      }
      return response(toolStatus({ ...f.extractStatus, job: f.toolJobs.extract_to_tl || null }));
    }
    if (p.startsWith('/api/extract-to-tl/') && method === 'POST') {
      const kind = p.includes('merge') ? 'extract_to_tl_merge' : p.includes('restore') ? 'extract_to_tl_restore' : 'extract_to_tl';
      const job = mkJob(kind, body);
      if (body.game_dir) job.result.project_key = extractTargetKey(body.game_dir, body.language || 'chinese');
      f.toolJobs.extract_to_tl = job;
      return response({ job });
    }
    if (p.startsWith('/api/extract-to-tl/suspicious-backups')) {
      return response({ manifests: [], available: false });
    }
    if ((p === '/api/extract-json' || p.startsWith('/api/extract-json?')) && method === 'GET') {
      const u = new URL(String(url), location.href);
      const lang = u.searchParams.get('language') || 'chinese';
      const gameFile = (u.searchParams.get('game_file') || '').trim();
      if (gameFile) {
        const key = extractTargetKey(gameFile, lang);
        return response(toolStatus({
          ...f.jsonStatus,
          project_key: key,
          language: lang,
          default_game_file: gameFile,
          job: (f.toolJobs.extract_json?.result?.project_key === key) ? f.toolJobs.extract_json : null,
        }));
      }
      if (f.unbound) {
        return response(toolStatus({ project_key: '', job: null, language: lang, default_game_file: '' }));
      }
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
      if (body.game_file) job.result.project_key = extractTargetKey(body.game_file, body.language || 'chinese');
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
  await win.loadURL(process.env.RENPYBOX_UI_URL || 'http://127.0.0.1:5173');

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

  // —— 已绑定项目：7 款工具可搜索打开 ——
  await assert("document.querySelector('.workspace-project').title==='C:/ui-check'", 'fixture 已绑定项目');
  for (const tool of TRANSLATE_TOOLS) {
    await openTool(tool.title);
    await waitToolPage(tool.page);
    log('OPEN ' + tool.key);
  }

  // —— 各页关键字段与主操作 API ——
  await openTool('直接翻译 RPY');
  await assert("document.querySelector('[aria-label=\"写入前备份 .bak\"]')?.getAttribute('aria-checked')==='false'", '直接翻译默认不备份');
  await assert("document.querySelector('input[placeholder=\"chinese\"]')", '直接翻译语言目录输入');
  await clearWrites();
  await click('开始翻译');
  await assert("__uiFixture.writes.some(w=>w.p==='/api/translation/start'&&w.body.mode==='direct'&&w.body.renpy_backup_original===false)", '直接翻译提交 start');

  await openTool('源码翻译');
  await assert("document.querySelector('[aria-label=\"自动备份 .bak\"]')?.getAttribute('aria-checked')==='false'", '源码翻译默认不备份');
  await clearWrites();
  await click('开始翻译');
  await assert("__uiFixture.writes.some(w=>w.p==='/api/translation/start'&&w.body.mode==='source')", '源码翻译提交 start');

  await openTool('补全翻译');
  await clearWrites();
  await click('开始补全翻译');
  await assert("__uiFixture.writes.some(w=>w.p==='/api/translation/start'&&w.body.mode==='supplement')", '补全翻译提交 start');

  await openTool('HOOK 翻译');
  await assert("document.querySelector('[aria-label=\"增量补全（仅追加缺失项）\"]')", 'HOOK 增量开关存在');
  await clearWrites();
  await click('开始 HOOK 翻译');
  await assert("__uiFixture.writes.some(w=>w.p==='/api/hook-translate/start'&&w.body.renpy_backup_original===false)", 'HOOK 提交 start');

  await openTool('翻译抽取到 TL');
  await assert("document.querySelector('[data-rb-page=extract-to-tl] input[placeholder=chinese]')", '抽取到 TL 语言字段');
  await clearWrites();
  await click('开始抽取');
  await assert("__uiFixture.writes.some(w=>w.p==='/api/extract-to-tl/extract')", '抽取到 TL 提交 extract');
  await js(`(()=>{
    const header=[...document.querySelectorAll('.ant-collapse-header')].find(h=>h.textContent.includes('高级')||h.textContent.includes('Advanced'));
    header?.click();
  })()`);
  await pause(200);
  await clearWrites();
  await click('立即合并增量');
  await assert("__uiFixture.writes.some(w=>w.p==='/api/extract-to-tl/merge-incremental'&&typeof w.body.game_dir==='string')", '抽取到 TL 高级合并带 game_dir');
  await capture('parity-extract-to-tl-advanced');

  await openTool('文本提取 JSON');
  await assert("document.querySelector('[data-rb-page=extract-json] input[placeholder=chinese]')", 'JSON 语言字段');
  await clearWrites();
  await click('预览条目数');
  await assert("__uiFixture.writes.some(w=>w.p==='/api/extract-json/preview'&&w.body.ensure_official===true)", 'JSON 预览 ensure_official=true');
  await capture('parity-extract-json-preview');

  await openTool('RPY 抽取设置');
  await assert("document.querySelector('[data-rb-page=rpy-extraction] input')", 'RPY 路径输入');
  await assert("document.querySelector('[data-rb-page=rpy-extraction] input')?.value?.includes('ui-check')", 'RPY 默认路径来自项目');
  await js(`(()=>{
    const header=[...document.querySelectorAll('.ant-collapse-header')].find(h=>h.textContent.includes('我要自己定义规则'));
    header?.click();
  })()`);
  await pause(200);
  await clearWrites();
  await click('复制常用规则为自定义');
  await assert("__uiFixture.writes.some(w=>w.p==='/api/rpy-extraction/profiles'&&w.body.starter===true)", 'RPY 复制内置规则提交');
  await assert("document.querySelector('[data-rb-page=rpy-extraction] textarea')", 'RPY 编辑器已打开且含规则样本输入');
  await capture('parity-rpy-extraction-editor');

  // —— 窄视口烟雾（停留在当前 RPY 页，避免折叠侧栏下无法切页）——
  await win.webContents.debugger.sendCommand('Emulation.setDeviceMetricsOverride', {
    width: 680,
    height: 800,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await pause(200);
  await capture('parity-rpy-extraction-680');
  await win.webContents.debugger.sendCommand('Emulation.clearDeviceMetricsOverride');
  await page("Ren'Py 工具箱");
  await pause(200);

  // —— 未绑定项目：requiresProject 门禁 ——
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

  for (const title of PROJECT_REQUIRED) {
    await searchTool(title);
    await assert('(()=>{const c=document.querySelector(".tool-card");return c&&c.disabled;})()', '未绑定禁用 ' + title);
  }
  for (const title of PROJECT_OPTIONAL.slice(0, 3)) {
    await searchTool(title);
    await assert('(()=>{const c=document.querySelector(".tool-card");return c&&!c.disabled;})()', '未绑定仍可点 ' + title);
  }

  await searchTool('翻译抽取到 TL');
  await js('document.querySelector(".tool-card")?.click()');
  await pause(200);
  await assert("document.querySelector('[data-rb-page=extract-to-tl]')", '未绑定可打开抽取到 TL');

  await openToolbox();
  await searchTool('HOOK 翻译');
  await assert('(()=>{const c=document.querySelector(".tool-card");return c&&c.disabled;})()', 'HOOK 卡片未绑定保持禁用');

  if (errors.length) throw new Error('控制台错误：' + JSON.stringify(errors));
  log('ALL TRANSLATION PARITY CHECKS PASSED');
  win.destroy();
  app.quit();
}).catch((error) => {
  log(error.stack || String(error));
  app.exit(1);
});
