/**
 * 翻译方式 owner 绑定 / HOOK 冻结任务 受控 UI 验收（modes-owner 范围）。
 *
 * 运行：
 *   清除 ELECTRON_RUN_AS_NODE
 *   UI_URL=http://127.0.0.1:5179
 *   RENPYBOX_UI_CAPTURE_DIR=%TEMP%\\renpybox-qt5-parity\\new-ui-modes-owner
 *   cd desktop && npx electron scripts/check-modes-owner-parity.cjs
 *
 * uniqueprofile；现有 Vite5179；无 build。不改 check-modes-parity.cjs。
 */
if (process.type !== 'browser') throw new Error('请使用 Electron 主进程运行，并先清除 ELECTRON_RUN_AS_NODE。');

const { app, BrowserWindow } = require('electron');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const out = process.env.RENPYBOX_UI_CAPTURE_DIR
  || path.join(os.tmpdir(), 'renpybox-qt5-parity', 'new-ui-modes-owner');
const profileDir = path.join(os.tmpdir(), 'renpybox-modes-owner-parity-profile-' + Date.now());
const logPath = path.join(out, 'modes-owner-parity.log');
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
    bindingRoot: "C:/ui-check",
    startResults: [],
    statusResults: [],
    stopResults: [],
    /** 为 true 时挂起 /hook-translate/start 的 HTTP 响应，直至 releaseHeldStart */
    holdStartResponse: false,
    releaseHeldStart: null,
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

  // 受控模拟真实 API：手动目标落盘后广播 PROJECT_CHANGED，并同步 /api/project。
  // 与 RenpyProjectPaths.from_path / 前端 toolboxProjectRootFromGamePath 对齐。
  f.projectRootFromGamePath = (raw) => {
    let p = String(raw || '').replaceAll('\\', '/').replace(/\/+$/, '');
    if (!p) return '';
    if (/\.(exe|py|rpy)$/i.test(p)) p = p.replace(/\/[^/]+$/, '');
    const parts = p.split('/').filter(Boolean);
    for (let i = parts.length - 1; i >= 0; i -= 1) {
      if (String(parts[i]).toLowerCase() !== 'tl') continue;
      const parent = parts.slice(0, i);
      if (parent.length && String(parent[parent.length - 1]).toLowerCase() === 'game') {
        return parent.slice(0, -1).join('/');
      }
      return parent.join('/');
    }
    if (parts.length && String(parts[parts.length - 1]).toLowerCase() === 'game') {
      parts.pop();
    }
    return parts.join('/');
  };
  f.ownerKey = () => f.bindingRoot.replaceAll('/', '\\').toLowerCase() + '|chinese';
  f.setBinding = (root) => {
    f.bindingRoot = f.projectRootFromGamePath(root).replace(/\/+$/, '') || String(root || '').replaceAll('\\', '/').replace(/\/+$/, '');
    values.renpy_project_path = f.bindingRoot;
    values.renpy_game_folder = f.bindingRoot + '/game';
    values.renpy_tl_folder = f.bindingRoot + '/game/tl/chinese';
    values.input_folder = values.renpy_tl_folder;
    values.output_folder = values.renpy_tl_folder;
  };
  f.setBinding(f.bindingRoot);
  window.confirm = () => true;
  const response = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });

  const projectPayload = () => {
    if (f.unbound) {
      return { renpy_project_path: '', renpy_game_folder: '', renpy_tl_folder: '' };
    }
    const root = f.bindingRoot;
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
      const owner = f.ownerKey();
      if (body.project_key && body.project_key !== owner) {
        f.startResults.push({ status: 409, requestOwner: body.project_key, liveOwner: owner });
        return response({ detail: '项目已切换，请重新加载后再操作' }, 409);
      }
      f.startResults.push({ status: 200, requestOwner: body.project_key, liveOwner: owner });
      if (body.mode === 'direct' || body.mode === 'supplement') {
        f.setBinding(String(body.game_path || f.bindingRoot));
        f.emitEvent('PROJECT_CHANGED', { project_root: f.bindingRoot });
        f.emitEvent('TRANSLATION_START', { request_id: body.request_id || 'owner-direct' });
      }
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
      const key = String(query.project_key || f.ownerKey());
      const req = String(query.request_id || '');
      const job = f.hookJob;
      const matching = job
        && (!key || key === String(job.result.owner_key || job.result.project_key))
        && (!req || req === String(job.result.request_id || ''));
      f.statusResults.push({ owner: key, request: req, job: matching ? job.id : null });
      return response({ project_key: key, job: matching ? job : null });
    }
    if (p === '/api/hook-translate/start' && method === 'POST') {
      f.hookJob = mkJob('hook_translate', body, '正在准备运行时 HOOK 抽取…');
      f.hookJob.result.owner_key = String(body.project_key || f.ownerKey());
      // target_key = from_path(game_path).project_key，不得把 .exe 路径直接当项目根。
      f.hookTarget = f.projectRootFromGamePath(body.game_path);
      f.hookJob.result.target_key = String(f.hookTarget).replaceAll('/', '\\').toLowerCase() + '|chinese';
      f.hookJob.status = 'running';
      f.hookJob.result.translation_started = false;
      f.hookJob.result.stage = 'extracting';
      f.hookJob.result.worker_active = true;
      f.hookJob.result.request_id = body.request_id || f.hookJob.id;
      const requestId = f.hookJob.result.request_id;
      // gated worker：保持抽取运行态，直至测试调用 releaseHookToTranslating
      f._hookFinishExtract = () => {
        if (!f.hookJob) return;
        f.setBinding(f.hookTarget);
        // 对齐真实 API：persist 成功后、START_RESULT 前广播 PROJECT_CHANGED。
        f.emitEvent('PROJECT_CHANGED', { project_root: f.bindingRoot });
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
      const startPayload = { accepted: true, reason: 'STARTED', request_id: requestId, job: f.hookJob };
      if (f.holdStartResponse) {
        return await new Promise((resolve) => {
          f.releaseHeldStart = () => resolve(response(startPayload));
        });
      }
      return response(startPayload);
    }
    if (p === '/api/hook-translate/stop' && method === 'POST') {
      const owner = String(f.hookJob?.result?.owner_key || f.hookJob?.result?.project_key || '');
      if (query.project_key && query.project_key !== owner) {
        f.stopResults.push({ status: 409, query, jobOwner: owner });
        return response({ detail: '当前没有可停止的 HOOK 抽取或翻译任务' }, 409);
      }
      f.stopResults.push({ status: 200, query, jobOwner: owner });
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

  await assert("document.querySelector('.workspace-project').title==='C:/ui-check'", '项目 A 已绑定');

  // —— Direct：手动 A→B，成功后全局 B，二次点击 owner B ——
  await openTool('直接翻译 RPY');
  await waitToolPage('direct-rpy-translate');
  await input('[data-rb-page=direct-rpy-translate] input', 'C:/ui-manual-B');
  await js('__uiFixture.reads.length=0');
  await clearWrites();
  await click('开始翻译');
  await assert("__uiFixture.bindingRoot==='C:/ui-manual-B'", 'Direct 首次持久化 B');
  await assert("document.querySelector('.workspace-project').title==='C:/ui-manual-B'", 'Direct 成功后界面全局项目 B');
  await assert("__uiFixture.reads.some(r=>r==='/api/project'||r.startsWith('/api/project?'))", 'Direct accepted 后 reloadProject');
  await waitButtonEnabled('开始翻译', 'Direct 第二次 start 可点');
  await clearWrites();
  await js('__uiFixture.startResults.length=0');
  await click('开始翻译');
  await assert("__uiFixture.startResults.at(-1).status===200", 'Direct 二次点击 owner B 受理');
  await assert("String(__uiFixture.startResults.at(-1).requestOwner).includes('ui-manual-b')", 'Direct 二次请求 owner 为 B');
  log('DIRECT_OWNER ' + JSON.stringify(await js(`({workspace:document.querySelector('.workspace-project').title,live:__uiFixture.bindingRoot,starts:__uiFixture.startResults})`)));
  await capture('owner-direct-bound');

  // —— Supplement 同链 ——
  await js("__uiFixture.setBinding('C:/ui-check');__uiFixture.emitEvent('PROJECT_CHANGED',{});");
  await assert("document.querySelector('.workspace-project').title==='C:/ui-check'", '重置项目 A');
  await openTool('补全翻译');
  await waitToolPage('hook-supplement');
  await input('[data-rb-page=hook-supplement] input', 'C:/ui-supp-B');
  await js('__uiFixture.reads.length=0;__uiFixture.startResults.length=0');
  await clearWrites();
  await click('开始补全翻译');
  await assert("document.querySelector('.workspace-project').title==='C:/ui-supp-B'", 'Supplement 成功后界面全局项目 B');
  await waitButtonEnabled('开始补全翻译', 'Supplement 第二次可点');
  await clearWrites();
  await js('__uiFixture.startResults.length=0');
  await click('开始补全翻译');
  await assert("__uiFixture.startResults.at(-1).status===200 && String(__uiFixture.startResults.at(-1).requestOwner).includes('ui-supp-b')", 'Supplement 二次 owner B');
  log('SUPPLEMENT_OWNER ' + JSON.stringify(await js(`({workspace:document.querySelector('.workspace-project').title,starts:__uiFixture.startResults})`)));
  await capture('owner-supplement-bound');

  // —— HOOK：PROJECT_CHANGED 先于 done，仍轮询原 owner A 并保留停止 ——
  await js("__uiFixture.releaseHookToIdle();__uiFixture.setBinding('C:/ui-check');__uiFixture.emitEvent('PROJECT_CHANGED',{});");
  await assert("document.querySelector('.workspace-project').title==='C:/ui-check'", 'HOOK 前重置 A');
  await openTool('HOOK 翻译');
  await waitToolPage('hook-translate');
  await input('[data-rb-page=hook-translate] input', 'C:/ui-hook-B');
  await js('__uiFixture.statusResults.length=0;__uiFixture.stopResults.length=0');
  await clearWrites();
  await click('开始 HOOK 翻译');
  await assert("__uiFixture.hookJob?.status==='running'", 'HOOK 抽取运行');
  await assert("String(__uiFixture.hookJob.result.owner_key).includes('ui-check')", 'HOOK job 冻结 owner A');
  await js('__uiFixture.releaseHookToTranslating()');
  await assert("document.querySelector('.workspace-project').title==='C:/ui-hook-B'", 'HOOK persist 后界面全局 B');
  await waitButtonEnabled('停止', 'HOOK 自身转换后停止仍可用');
  await pause(950);
  await assert("__uiFixture.statusResults.some(s=>String(s.owner).includes('ui-check')&&s.job)", 'HOOK 持续轮询原 owner A 且命中 job');
  await clearWrites();
  await js('__uiFixture.reads.length=0;__uiFixture.stopResults.length=0');
  await click('停止');
  await assert("__uiFixture.stopResults.at(-1)?.status===200", 'HOOK stop 原 owner 受理');
  await assert("__uiFixture.writes.some(w=>w.p==='/api/hook-translate/stop'&&w.query&&String(w.query.project_key).includes('ui-check')&&w.query.request_id&&w.query.run_id==='7')", 'HOOK stop POST 含原 owner+request+run');
  await assert("!__uiFixture.writes.some(w=>w.p==='/api/translation/stop')", 'HOOK stop 无全局 translation/stop');
  log('HOOK_OWNER_STOP ' + JSON.stringify(await js(`({workspace:document.querySelector('.workspace-project').title,status:__uiFixture.statusResults,stop:__uiFixture.stopResults,writes:__uiFixture.writes.filter(w=>w.p.includes('stop'))})`)));
  await capture('owner-hook-frozen-stop');

  // —— 下一任务必须用当前新 owner B ——
  await js('__uiFixture.releaseHookToIdle()');
  await waitButtonEnabled('开始 HOOK 翻译', 'HOOK 可再次开始');
  await clearWrites();
  await click('开始 HOOK 翻译');
  await assert("__uiFixture.writes.some(w=>w.p==='/api/hook-translate/start'&&String(w.body.project_key).includes('ui-hook-b'))", '下一 HOOK 任务 owner 为 B');
  await js('__uiFixture.releaseHookToIdle()');

  // —— 外部切到 C：旧任务不串回当前页 ——
  await js("__uiFixture.setBinding('C:/ui-check');__uiFixture.emitEvent('PROJECT_CHANGED',{});");
  await openTool('HOOK 翻译');
  await waitToolPage('hook-translate');
  await input('[data-rb-page=hook-translate] input', 'C:/ui-hook-ext-B');
  await click('开始 HOOK 翻译');
  await js('__uiFixture.releaseHookToTranslating()');
  await waitButtonEnabled('停止', '外部切换前停止可用');
  await js("__uiFixture.setBinding('C:/ui-ext-C');__uiFixture.emitEvent('PROJECT_CHANGED',{project_root:'C:/ui-ext-C'});");
  await assert("document.querySelector('.workspace-project').title==='C:/ui-ext-C'", '外部切换到 C');
  await pause(400);
  await assert("[...document.querySelectorAll('button')].some(b=>b.textContent==='停止'&&b.disabled)", '外部切 C 后旧停止禁用');
  await clearWrites();
  await assert("!__uiFixture.writes.some(w=>w.p==='/api/hook-translate/stop'||w.p==='/api/translation/stop')", '外部切 C 后无串项目 stop');
  log('HOOK_EXTERNAL_C ' + JSON.stringify(await js(`({workspace:document.querySelector('.workspace-project').title,stopDisabled:[...document.querySelectorAll('button')].find(b=>b.textContent==='停止')?.disabled,writes:__uiFixture.writes.slice(-3)})`)));
  await capture('owner-hook-external-c');

  // —— 迟到 start HTTP：外部切 C 后旧 accepted 不得重挂 A ——
  await js("__uiFixture.releaseHookToIdle();__uiFixture.holdStartResponse=false;__uiFixture.releaseHeldStart=null;__uiFixture.setBinding('C:/ui-check');__uiFixture.emitEvent('PROJECT_CHANGED',{});");
  await assert("document.querySelector('.workspace-project').title==='C:/ui-check'", 'late-C 前重置 A');
  await openTool('HOOK 翻译');
  await waitToolPage('hook-translate');
  await input('[data-rb-page=hook-translate] input', 'C:/late-owner-B');
  await js('__uiFixture.holdStartResponse=true;__uiFixture.statusResults.length=0;__uiFixture.reads.length=0');
  await clearWrites();
  await click('开始 HOOK 翻译');
  await assert("typeof __uiFixture.releaseHeldStart==='function'", '旧 A start 响应已真实 HTTP gate 挂起');
  await js("__uiFixture.setBinding('C:/external-C');__uiFixture.emitEvent('PROJECT_CHANGED',{})");
  await assert("document.querySelector('.workspace-project').title==='C:/external-C'", 'accepted 在途时外部切 C 完成');
  await js('__uiFixture.statusResults.length=0;__uiFixture.reads.length=0;__uiFixture.holdStartResponse=false;__uiFixture.releaseHeldStart()');
  await pause(1200);
  log('LATE_START_EXTERNAL_C ' + JSON.stringify(await js(`({workspace:document.querySelector('.workspace-project').title,job:__uiFixture.hookJob,status:__uiFixture.statusResults,reads:__uiFixture.reads,stopDisabled:[...document.querySelectorAll('button')].find(b=>b.textContent==='停止')?.disabled,extracting:!!document.querySelector('[data-rb-page=hook-translate] .ant-progress')})`)));
  await capture('owner-late-start-external-C');
  await assert("[...document.querySelectorAll('button')].some(b=>b.textContent==='停止'&&b.disabled)", '迟到 A accepted 没有在 C 重新挂旧任务');
  await assert("!__uiFixture.statusResults.some(s=>String(s.owner).includes('ui-check')&&s.job)", 'C 下没有重新轮询旧 A job');

  // —— 迟到 start HTTP：自身 persist 目标 B 先于响应，仍须受理并可停止 ——
  await js("__uiFixture.releaseHookToIdle();__uiFixture.holdStartResponse=false;__uiFixture.releaseHeldStart=null;__uiFixture.setBinding('C:/ui-check');__uiFixture.emitEvent('PROJECT_CHANGED',{});");
  await assert("document.querySelector('.workspace-project').title==='C:/ui-check'", 'late-B 前重置 A');
  await openTool('HOOK 翻译');
  await waitToolPage('hook-translate');
  await input('[data-rb-page=hook-translate] input', 'C:/late-persist-B');
  await js('__uiFixture.holdStartResponse=true;__uiFixture.statusResults.length=0;__uiFixture.stopResults.length=0');
  await clearWrites();
  await click('开始 HOOK 翻译');
  await assert("typeof __uiFixture.releaseHeldStart==='function'", '自有 B start 响应已 gate 挂起');
  // 模拟抽取侧 persist B 早于 HTTP accepted 返回
  await js("__uiFixture.setBinding('C:/late-persist-B');__uiFixture.emitEvent('PROJECT_CHANGED',{project_root:'C:/late-persist-B'})");
  await assert("document.querySelector('.workspace-project').title==='C:/late-persist-B'", 'accepted 在途时自身已落到 B');
  await js('__uiFixture.holdStartResponse=false;__uiFixture.releaseHeldStart()');
  await pause(400);
  await assert("__uiFixture.hookJob?.status==='running'", '迟到 accepted 在自有 B 上仍受理抽取');
  await waitButtonEnabled('停止', '自身 B 先于响应时停止仍可用');
  await pause(950);
  await assert("__uiFixture.statusResults.some(s=>String(s.owner).includes('ui-check')&&s.job)", '自有 B 仍按原 owner A 轮询');
  await js('__uiFixture.releaseHookToTranslating()');
  await waitButtonEnabled('停止', '自有 B 翻译态停止可用');
  await clearWrites();
  await js('__uiFixture.stopResults.length=0');
  await click('停止');
  await assert("__uiFixture.stopResults.at(-1)?.status===200", '自有 B 先于响应后 stop 原 owner 受理');
  await assert("__uiFixture.writes.some(w=>w.p==='/api/hook-translate/stop'&&w.query&&String(w.query.project_key).includes('ui-check')&&w.query.request_id&&w.query.run_id==='7')", '自有 B 场景 stop 含原 owner+request+run');
  log('LATE_START_OWN_B ' + JSON.stringify(await js(`({workspace:document.querySelector('.workspace-project').title,status:__uiFixture.statusResults,stop:__uiFixture.stopResults.at(-1)})`)));
  await capture('owner-late-start-own-B');
  await js('__uiFixture.releaseHookToIdle()');

  // —— 迟到 start HTTP：自身 EXE 目标 B（game.exe）persist 先于响应，仍须受理 ——
  await js("__uiFixture.releaseHookToIdle();__uiFixture.holdStartResponse=false;__uiFixture.releaseHeldStart=null;__uiFixture.setBinding('C:/ui-check');__uiFixture.emitEvent('PROJECT_CHANGED',{});");
  await assert("document.querySelector('.workspace-project').title==='C:/ui-check'", 'late-EXE 前重置 A');
  await openTool('HOOK 翻译');
  await waitToolPage('hook-translate');
  await input('[data-rb-page=hook-translate] input', 'C:/late-exe-B/game.exe');
  await js('__uiFixture.holdStartResponse=true;__uiFixture.statusResults.length=0;__uiFixture.stopResults.length=0');
  await clearWrites();
  await click('开始 HOOK 翻译');
  await assert("typeof __uiFixture.releaseHeldStart==='function'", '自身 EXE start 响应已 gate 挂起');
  await assert("__uiFixture.hookJob.result.target_key==='c:\\\\late-exe-b|chinese'", 'fixture target_key 已规范到项目根而非 exe');
  // persist 广播项目根 B（不是 game.exe 路径）
  await js("__uiFixture.setBinding('C:/late-exe-B');__uiFixture.emitEvent('PROJECT_CHANGED',{project_root:'C:/late-exe-B'})");
  await assert("document.querySelector('.workspace-project').title==='C:/late-exe-B'", 'accepted 在途时自身 EXE 已落到项目根 B');
  await js('__uiFixture.holdStartResponse=false;__uiFixture.releaseHeldStart()');
  await pause(400);
  await assert("__uiFixture.hookJob?.status==='running'", '迟到 accepted 在自身 EXE→B 上仍受理');
  await waitButtonEnabled('停止', '自身 EXE→B 停止仍可用');
  await pause(950);
  await assert("__uiFixture.statusResults.some(s=>String(s.owner).includes('ui-check')&&s.job)", '自身 EXE→B 仍按原 owner A 轮询');
  await js('__uiFixture.releaseHookToTranslating()');
  await waitButtonEnabled('停止', '自身 EXE→B 翻译态停止可用');
  await clearWrites();
  await js('__uiFixture.stopResults.length=0');
  await click('停止');
  await assert("__uiFixture.stopResults.at(-1)?.status===200", '自身 EXE→B stop 原 owner 受理');
  await assert("!__uiFixture.writes.some(w=>w.p==='/api/translation/stop')", '自身 EXE→B 无全局 stop');
  log('LATE_START_OWN_EXE ' + JSON.stringify(await js(`({workspace:document.querySelector('.workspace-project').title,target:__uiFixture.hookJob?.result?.target_key,status:__uiFixture.statusResults,stop:__uiFixture.stopResults.at(-1)})`)));
  await capture('owner-late-start-own-exe');
  await js('__uiFixture.releaseHookToIdle()');

  if (errors.length) throw new Error('控制台错误：' + JSON.stringify(errors));
  log('ALL MODES OWNER PARITY CHECKS PASSED');
  win.destroy();
  app.quit();
}).catch((error) => {
  log(error.stack || String(error));
  app.exit(1);
});
