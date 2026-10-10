/** UI 自检：HTTP/WS 使用受控快照，实际持久化另由 tests/api 临时项目验证。 */
if (process.type !== 'browser') throw new Error('请使用 Electron 主进程运行，并先清除 ELECTRON_RUN_AS_NODE。');
const { app, BrowserWindow } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const out = process.env.RENPYBOX_UI_CAPTURE_DIR || require('node:os').tmpdir();
const pause = ms => new Promise(r => setTimeout(r, ms));
const log = value => fs.appendFileSync(path.join(out, 'ui-check.log'), value + '\n');
fs.mkdirSync(out, { recursive: true });
fs.writeFileSync(path.join(out, 'ui-check.log'), '');
function fixture() {
  const character = (id, name) => ({ id, name, name_translation: '艾丽丝', aliases: [], match_keywords: [name], identity: '港口小镇的居民', personality: '温和', speech_style: '简短自然', relationship_notes: '', prompt_notes: '', sample_lines: [], enabled: true, is_primary: false });
  const values = { theme: 'DARK', source_language: 'EN', target_language: 'ZH', input_folder: 'C:/ui-check/game/tl/chinese', output_folder: 'C:/ui-check/output', expert_mode: true, activate_platform: 0, agent_platform: 0, platforms: [{ id: 0, name: '主翻译接口', group: 'online', model: 'story-model', api_format: 'OpenAI', api_url: 'https://api.example.com/v1', api_key: '***' }, { id: 1, name: '本地翻译模型', group: 'local', model: 'sakura', api_format: 'SakuraLLM', api_url: 'http://localhost:8080/v1', api_key: '***' }] };
  const worldbook = { project_name: '港湾来信', genre: '日常 / 悬疑', setting_summary: '一座靠海的小镇，一封迟到的信。人物的语气平静而克制。', tone_style: '自然口语，保留人物之间的距离感', era_background: '', narrative_rules: '', format_rules: '', spoiler_notes: '', reference_notes: '' };
  const f = window.__uiFixture = { values, sockets: [], writes: [], assets: { storage_key: 'fixture', revision: 1, worldbook, characters: [character('alice', 'Alice')], worldbook_enabled: true, characters_enabled: true, worldbook_draft: {}, character_drafts: [] }, glossary: { storage_key: 'fixture', revision: 1, enabled: true, candidate_ids: ['c1'], rows: [{ src: 'Harbor', dst: '港湾', info: '地名', candidate: false, record_id: 'f1' }, { src: 'Sealed Letter', dst: '封缄的信', info: '待审核', candidate: true, record_id: 'c1' }] }, items: [{ id: 0, version: 'v1', src: 'Alice, the letter arrived this morning.', dst: '艾丽丝，那封信今天早上到了。', status: 'TRANSLATED', file_path: 'chapter_01.rpy', row: 24 }] };
  const nativeFetch = fetch.bind(window);
  f.reads = []; f.confirmed = []; f.engineStatus = 'IDLE'; f.qualityReports = [];
  f.progress = { line: 64, total_line: 100, time: 120, total_output_tokens: 4800, throughput: { schema_version: 1, elapsed_seconds: 120, output_tokens: 4800, effective_items_per_minute: 32 }, recent_items: [{ src: 'Saved source', dst: '已保存的译文' }] };
  f.progressSource = 'cache'; window.confirm = () => true;
  f.emitQuality = report => { f.qualityReports = [report]; f.sockets.forEach(socket => socket.onmessage?.({ data: JSON.stringify({ type: 'event', event: 'TRANSLATION_UPDATE', data: { quality_task: report } }) })); };
  f.workbenchJob = null;
  f.archiveJob = null;
  f.onekeyJob = null;
  f.finishWorkbench = (status = 'done', message = '扫描到 1 位新角色') => {
    const job = f.workbenchJob;
    if (!job) throw new Error('没有待完成的工作台任务');
    job.status = status; job.updated_at += 1; job.result.message = message; job.result.worker_active = false;
    job.error = status === 'failed' ? message : null;
    if (status === 'done') {
      if (['scan', 'characters', 'all'].includes(job.result.action)) f.assets.character_drafts = [{ ...character('bob', 'Bob'), name_translation: '鲍勃', identity: '灯塔管理员', aliases: ['Keeper'] }];
      if (['worldbook', 'all'].includes(job.result.action)) f.assets.worldbook_draft = { setting_summary: '潮汐与灯塔构成故事背景。' };
      f.assets.revision += 1;
      job.result.worldbook_fields = Object.values(f.assets.worldbook_draft).filter(Boolean).length;
      job.result.character_count = f.assets.character_drafts.length;
    }
    f.engineStatus = 'IDLE';
    f.sockets.forEach(socket => socket.onmessage?.({ data: JSON.stringify({ type: 'job', job }) }));
  };
  f.finishLexicon = (result = {}, status = 'done') => {
    const job = f.lexiconJob;
    if (!job) throw new Error('没有词表任务');
    Object.assign(job.result, result, { worker_active: false });
    Object.assign(job, { status, updated_at: job.updated_at + 1, error: status === 'failed' ? result.message || '模拟失败' : null });
    if (status === 'done' && job.kind === 'lexicon_preserve_rescan') {
      values.text_preserve_data = result.rows; values.text_preserve_enable = result.enabled;
    }
    f.engineStatus = 'IDLE';
    f.sockets.forEach(socket => socket.onmessage?.({data: JSON.stringify({type:'job',job})}));
  };
  f.agent = { session_id: 'ui-agent', revision: 0, run_id: 0, status: 'idle', messages: [], confirmation: null };
  f.emitAgent = () => { f.agent.revision += 1; f.sockets.forEach(socket => socket.onmessage?.({ data: JSON.stringify({ type: 'event', event: 'AGENT_UPDATE', data: { revision: f.agent.revision } }) })); };
  const response = data => new Response(JSON.stringify(data), { status: 200, headers: { 'Content-Type': 'application/json' } });
  window.fetch = async (url, options = {}) => {
    const p = new URL(String(url), location.href).pathname;
    if (p !== '/health' && !p.startsWith('/api/')) return nativeFetch(url, options);
    const method = options.method || 'GET'; const body = options.body ? JSON.parse(options.body) : {};
    if (method !== 'GET') f.writes.push({ p, method, body });
    else f.reads.push(p);
    if (p === '/health') return response({ ok: true, app_version: 'v0.8.1', mode: 'api', pid: 0 });
    if (p === '/api/version') return response({ app_version: 'v0.8.1', api_version: '1' });
    if (p === '/api/platforms' && method === 'POST') { values.platforms.push({ ...body, id: values.platforms.length, api_key: '***' }); return response({ values, masked: [] }); }
    if (p === '/api/settings') { if (method === 'PATCH') { if (f.failSettings) return new Response(JSON.stringify({detail:'模拟落盘失败'}),{status:500}); Object.assign(values, body.values); } return response({ values, masked: [] }); }
    if (p === '/api/settings/honorific-defaults') return response({ titles: ['mr', 'mrs', 'doctor'] });
    if (/^\/api\/platforms\/\d+\/models$/.test(p)) return response({ models: ['available-model', 'story-model'] });
    if (p === '/api/agent') return response(f.agent);
    if (p === '/api/agent/message') {
      f.agent.run_id += 1; f.agent.status = 'running';
      f.agent.messages.push({ id: f.agent.run_id + '-user', role: 'user', content: body.message }, { id: f.agent.run_id + '-assistant', role: 'assistant', content: '正在检查项目…', reasoning: '读取项目结构。', tools: [], status: 'running', error: '' });
      f.emitAgent(); return response(f.agent);
    }
    if (p === '/api/agent/stop') { f.agent.status = 'idle'; f.agent.confirmation = null; f.agent.messages.at(-1).status = 'cancelled'; f.emitAgent(); return response(f.agent); }
    if (p === '/api/agent/reset') { f.agent.messages = []; f.agent.confirmation = null; f.agent.status = 'idle'; f.emitAgent(); return response(f.agent); }
    if (p === '/api/agent/confirm') {
      if (f.agent.confirmation?.id !== body.confirmation_id) return new Response(JSON.stringify({ detail: '确认已失效' }), { status: 409 });
      f.confirmed.push(body); f.agent.confirmation = null; f.agent.status = 'idle';
      Object.assign(f.agent.messages.at(-1), { content: body.approved ? '工具已完成。' : '', error: body.approved ? '' : '已拒绝执行工具。', status: body.approved ? 'done' : 'cancelled' });
      f.emitAgent(); return response(f.agent);
    }
// 项目响应支持下面的真实切项目场景。
if (p === '/api/project') {
  const root = f.assetProjectRoot || 'C:/ui-check';
  return response({ renpy_project_path: root, renpy_game_folder: root + '/game', renpy_tl_folder: values.input_folder });
}
if (p.startsWith('/api/asset-suite/')) {
  f.assetProjectKey ||= 'c:\\ui-check|chinese';
  f.finishAsset ||= (result = {}, status = 'done') => {
    const job = f.assetJob;
    if (!job) throw new Error('没有待完成的资源套件任务');
    Object.assign(job.result, result, { worker_active: false });
    Object.assign(job, { status, updated_at: job.updated_at + 1, done: 1, progress: 1, error: status === 'failed' ? result.message || '模拟失败' : null });
    if (status === 'cancelled') job.result.message = result.message || '任务已取消';
    f.engineStatus = 'IDLE';
    f.sockets.forEach(socket => socket.onmessage?.({ data: JSON.stringify({ type: 'job', job }) }));
  };
  if (p === '/api/asset-suite/status') {
    const snapshot = { project_key: f.assetProjectKey, job: f.assetJob?.result.project_key === f.assetProjectKey ? structuredClone(f.assetJob) : null };
    if (f.holdAssetStatus) {
      f.holdAssetStatus = false;
      return new Promise(resolve => { f.releaseAssetStatus = () => resolve(response(snapshot)); });
    }
    return response(snapshot);
  }
  // 后端允许空 key；下面的 UI 断言另外要求所有 POST 携带 canonical key。
  if (body.project_key && body.project_key !== f.assetProjectKey) {
    return new Response(JSON.stringify({ detail: '项目已切换，请重新加载后再操作' }), { status: 409 });
  }
  if (p === '/api/asset-suite/names/export') {
    const rows = body.entries.map(item => {
      const comment = item.comment || item.info || '角色姓名';
      return { src: item.src, dst: item.dst || item.src, info: comment, comment, type: item.type || '角色' };
    });
    const content = body.format === 'json' ? JSON.stringify(rows) : rows.map(row => row.src + ' -> ' + row.dst + ' #' + row.comment).join('\n');
    return response({ success: true, format: body.format, filename: 'glossary_names.' + body.format, media_type: body.format === 'json' ? 'application/json; charset=utf-8' : 'text/plain; charset=utf-8', content, content_base64: btoa(String.fromCharCode(...new TextEncoder().encode(content))), count: rows.length, path: body.output_file || '', backup_path: '', message: '已生成术语表（共 ' + rows.length + ' 个条目）' });
  }
  if (['/api/asset-suite/emoji', '/api/asset-suite/corrections/apply'].includes(p) && !body.confirm) {
    return new Response(JSON.stringify({ detail: '原地写入需要 confirm=true' }), { status: 400 });
  }
  const operation = ({
    '/api/asset-suite/structure': 'structure',
    '/api/asset-suite/emoji': 'emoji',
    '/api/asset-suite/corrections/export': 'corrections_export',
    '/api/asset-suite/corrections/apply': 'corrections_apply',
    '/api/asset-suite/names/extract': 'names_extract',
  })[p];
  if (!operation || method !== 'POST') throw new Error('未定义资源套件接口：' + method + ' ' + p);
  if (f.engineStatus !== 'IDLE') return new Response(JSON.stringify({ detail: '已有任务正在运行或收尾，请稍后再试' }), { status: 409 });
  f.engineStatus = 'TESTING';
  f.assetJob = { id: 'asset-task-' + (f.assetSerial = (f.assetSerial || 0) + 1), kind: 'asset_' + operation, status: 'running', total: 1, done: 0, progress: 0, error: null, created_at: Date.now() / 1000, updated_at: Date.now() / 1000, result: { project_key: f.assetProjectKey, operation, path: body.path || body.input_dir || body.translation_root, target_dir: body.target_dir, message: '资源套件任务进行中', worker_active: true } };
  return response({ job: f.assetJob });
}
if (/^\/api\/jobs\/asset-task-\d+\/cancel$/.test(p)) {
  f.assetJob.cancel_requested = true;
  f.assetJob.result.message = '正在取消，等待后台线程结束…';
  return response(f.assetJob);
}
if (p === '/api/jobs') return response({ jobs: [f.workbenchJob, f.archiveJob, f.onekeyJob, f.lexiconJob, f.assetJob].filter(Boolean) });
    if (p === '/api/translation/estimate') { if(!options.body) return new Response(JSON.stringify({detail:'Field required'}),{status:422}); return response({total_source_tokens:128,estimated_input_tokens:256,estimated_output_tokens:160,batch_count:2,untranslated_count:4}); }
    if (p === '/api/translation/state') return response({ engine_status: f.engineStatus, stop_barrier: false, single_tasks: false, request_id: 'fixture', run_id: 1, running: { running: 0, max: 4 }, progress: f.progress, progress_source: f.progressSource, progress_error: f.progressError || '', active_output_folder: values.output_folder });
    if (p === '/api/settings/prompt-preview') return response({ base: '将对白翻译为自然中文，保留人物语气。', style: '语言克制。', fixed: '保持变量和输出协议。' });
    if (p === '/api/workbench/analysis') {
      if (method === 'POST') {
        if (f.rejectWorkbench) return new Response(JSON.stringify({ detail: '项目资料已更新，请重新加载后再生成。' }), { status: 409 });
        f.engineStatus = 'TESTING';
        f.workbenchJob = { id: 'workbench-task', kind: 'workbench_analysis', status: 'running', total: 0, done: 0, progress: 0, error: null, created_at: Date.now() / 1000, updated_at: Date.now() / 1000, result: { storage_key: f.assets.storage_key, action: body.action, scope: body.scope, message: '正在读取项目语料', worker_active: true } };
      }
      return response({ job: f.workbenchJob?.result.storage_key === f.assets.storage_key ? f.workbenchJob : null });
    }
    if (p === '/api/jobs/workbench-task/cancel') { f.workbenchJob.result.message = '已请求取消，正在等待当前请求结束'; f.workbenchJob.cancel_requested = true; return response(f.workbenchJob); }
    if (p === '/api/workbench/apply-drafts') {
      Object.assign(f.assets.worldbook, f.assets.worldbook_draft);
      for (const card of f.assets.character_drafts) {
        const current = f.assets.characters.find(item => item.id === card.id);
        if (current) Object.assign(current, card); else f.assets.characters.push(card);
      }
      f.assets.worldbook_draft = {}; f.assets.character_drafts = []; f.assets.revision += 1;
      return response(f.assets);
    }
    if (p === '/api/workbench') {
      if (method === 'PATCH') {
        if (body.storage_key !== f.assets.storage_key || body.revision !== f.assets.revision) return new Response(JSON.stringify({ detail: '项目资料已更新，请重新加载后再保存。' }), { status: 409 });
        Object.assign(f.assets, body, { revision: f.assets.revision + 1 });
      }
      return response(f.assets);
    }
    if (p === '/api/workbench/glossary') { if (method === 'PATCH') Object.assign(f.glossary, body, { revision: f.glossary.revision + 1 }); return response(f.glossary); }
    if (p === '/api/lexicon') return response({ job: f.lexiconJob || null, project_key: 'ui-check|chinese', output_folder: values.output_folder });
    if (p === '/api/lexicon/excel/import') {
      const kind = body.kind;
      if (kind === 'glossary') return response({ rows: [{ src: 'Imported', dst: '导入', type: '地名', comment: 'excel' }], count: 1 });
      return response({ rows: [{ src: '[name]', comment: '变量' }], count: 1 });
    }
    if (p === '/api/lexicon/excel/export') return response({ filename: body.kind === 'glossary' ? 'glossary.xlsx' : 'text_preserve.xlsx', content_base64: btoa('PK'), media_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
    if (p === '/api/lexicon/glossary/classify') {
      return response({ rows: (body.rows || []).map(row => ({ ...row, type: row.type || '地名' })), ner_count: 0, kw_count: 1 });
    }
    if (['/api/lexicon/statistics', '/api/lexicon/glossary/scan-candidates', '/api/lexicon/glossary/scan-characters', '/api/lexicon/glossary/translate', '/api/lexicon/preserve/rescan-variables'].includes(p)) {
      f.engineStatus = 'TESTING';
      const kind = p.endsWith('statistics') ? 'lexicon_statistics' : p.endsWith('translate') ? 'lexicon_translate' : p.endsWith('scan-characters') ? 'lexicon_scan_characters' : p.endsWith('rescan-variables') ? 'lexicon_preserve_rescan' : 'lexicon_scan_candidates';
      f.lexiconJob = { id: 'lexicon-task-' + (f.lexiconSerial = (f.lexiconSerial || 0) + 1), kind, status: 'running', total: 1, done: 0, progress: 0, error: null, created_at: Date.now() / 1000, updated_at: Date.now() / 1000, result: { project_key: 'ui-check|chinese', output_folder: values.output_folder, kind: body.kind || kind, message: '进行中', worker_active: true } };
      f.lexiconInput = structuredClone(body);
      return response({ job: f.lexiconJob });
    }
    if (/^\/api\/jobs\/lexicon-task-\d+\/cancel$/.test(p)) { f.lexiconJob.cancel_requested = true; f.lexiconJob.result.message = '正在停止'; return response(f.lexiconJob); }
    if (p === '/api/proofreading/retranslate' && method === 'GET') return response(f.retranslate || { state: 'IDLE' });
    if (p === '/api/proofreading/retranslate') { f.retranslate = { state: 'RUNNING', total: body.rows.length, done: 0, updated: 0, failed: 0 }; return response(f.retranslate); }
    if (p === '/api/proofreading/retranslate/cancel') { f.retranslate.state = 'CANCELLING'; return response(f.retranslate); }
    if (p === '/api/proofreading/report') return response({ failed_count: 1, fallback_count: 2, line_mismatch_count: 1, error_type_counts: { FAIL_LINE_COUNT: 1 }, item_references: [{ item_index: 0, reference: 'chapter_01.rpy:24', source_preview: 'Hello', error_types: ['FAIL_LINE_COUNT'] }] });
    if (p === '/api/proofreading/locate') return response({ path: 'C:/ui-check/output/chapter_01.rpy', row: 24, lines: [{ number: 23, text: 'old "Hello"' }, { number: 24, text: 'new "你好"' }] });
    if (p === '/api/proofreading/export') return response({ ok: true, output_folder: values.output_folder });
    if (p === '/api/proofreading/reset') { body.rows.forEach(row => { f.items[row.id].dst = ''; f.items[row.id].status = 'UNTRANSLATED'; }); return response({ ok: true, changed: body.rows.length }); }
    if (p === '/api/proofreading' && f.issueDelay) await new Promise(resolve => setTimeout(resolve, 350));
    if (p === '/api/proofreading') return response({ cache_token: 'fixture-cache', cache_folder: values.output_folder, total: f.items.length, matched: f.items.length, page: 1, limit: 50, files: ['chapter_01.rpy'], readonly: f.engineStatus !== 'IDLE', quality_reports: f.qualityReports, items: f.items });
    if (p === '/api/proofreading/quality') {
      if (f.rejectQuality) return new Response(JSON.stringify({ detail: '译文或缓存条目已更新，请刷新后再编辑。' }), { status: 409 });
      f.engineStatus = 'QUALITY';
      f.emitQuality({ task_type: body.task === 'polish' ? 'POLISHER' : 'PROOFREADER', state: 'RUNNING', total_count: body.ids.length, completed_count: 0, updated_count: 0, failed_count: 0, skipped_count: 0 });
      return response({ ok: true, accepted: body.ids.length, skipped: 0 });
    }
    if (p === '/api/proofreading/quality/cancel') { f.engineStatus = 'IDLE'; f.emitQuality({ ...f.qualityReports[0], state: 'CANCELLED' }); return response({ ok: true }); }
    if (p === '/api/proofreading/item') { f.items[0].dst = body.dst; return response({ ok: true }); }
    if (p === '/api/archive') return response({ job: f.archiveJob });
    if (p === '/api/archive/unpack' || p === '/api/archive/decompile' || p === '/api/archive/pack') {
      f.engineStatus = 'TESTING';
      f.archiveJob = { id: 'archive-task', kind: p.split('/').pop() === 'pack' ? 'archive_pack' : (p.endsWith('unpack') ? 'archive_unpack' : 'archive_decompile'), status: 'running', total: 1, done: 0, progress: 0, error: null, created_at: Date.now() / 1000, updated_at: Date.now() / 1000, result: { project_key: 'C:/ui-check|chinese', message: '任务进行中', worker_active: true, path: body.path || body.source_dir || '', archives_removed: false } };
      return response({ job: f.archiveJob });
    }
    if (p === '/api/onekey') return response({ job: f.onekeyJob });
    if (p === '/api/onekey/detect') return response({ project_key: 'C:/ui-check|chinese', game_dir: 'C:/ui-check/game', project_root: 'C:/ui-check', language: body.language || 'chinese', status: 'ready', message: '已找到可抽取脚本' });
    if (p === '/api/onekey/prepare' || p === '/api/onekey/apply') {
      if (!body.confirm_write && !body.confirm) return new Response(JSON.stringify({ detail: '需要确认' }), { status: 400 });
      f.engineStatus = 'TESTING';
      f.onekeyJob = { id: 'onekey-task-' + f.writes.length, kind: p.endsWith('apply') ? 'onekey_apply' : 'onekey_prepare', status: 'running', total: 100, done: 10, progress: 0.1, error: null, created_at: Date.now() / 1000, updated_at: Date.now() / 1000, result: { project_key: 'C:/ui-check|chinese', project_root: 'C:/ui-check', game_dir: 'C:/ui-check/game', message: '准备中', worker_active: true, stage: p.endsWith('apply') ? 'apply' : 'extract', incremental: !!body.incremental, output_dir: values.output_folder, language: body.language || 'chinese' } };
      return response({ job: f.onekeyJob });
    }
    if (p === '/api/jobs/archive-task/cancel' || /^\/api\/jobs\/onekey-task-\d+\/cancel$/.test(p)) {
      const job = p.includes('archive') ? f.archiveJob : f.onekeyJob;
      if (job) { job.cancel_requested = true; job.result.message = '已请求取消'; }
      return response(job);
    }
    throw new Error('自检未定义接口：' + method + ' ' + p);
  };
  const NativeSocket = WebSocket;
  window.WebSocket = class {
    constructor(url) { if (!String(url).endsWith('/ws')) return new NativeSocket(url); this.readyState = 1; f.sockets.push(this); setTimeout(() => this.onopen?.({}), 0); }
    close() { this.readyState = 3; this.onclose?.({}); }
  };
}
app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: 1280, height: 800, show: false, frame: false, webPreferences: { offscreen: true, sandbox: true, contextIsolation: true } });
  const errors = [];
  win.webContents.on('console-message', (event, level, message) => { const severity = event.level ?? level; const value = event.message ?? message; if (severity === 'error' || severity >= 3) { errors.push(value); log('CONSOLE ' + value); } });
  await win.loadURL('about:blank'); win.webContents.debugger.attach('1.3');
  await win.webContents.debugger.sendCommand('Page.enable'); await win.webContents.debugger.sendCommand('Runtime.enable');
  await win.webContents.debugger.sendCommand('Page.addScriptToEvaluateOnNewDocument', { source: '(' + fixture.toString() + ')()' });
  await win.loadURL(process.env.RENPYBOX_UI_URL || 'http://127.0.0.1:5173');
  const js = async code => { const result=await win.webContents.debugger.sendCommand('Runtime.evaluate',{expression:`(async()=>{const value=await (0,eval)(${JSON.stringify(code)});return typeof value==='function'||value instanceof Node?undefined:value;})()`,awaitPromise:true,returnByValue:true}); if(result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description||result.exceptionDetails.text); return result.result.value; };
  for (let i = 0; i < 50; i++) { if (await js("!!document.querySelector('.translation-layout')")) break; await pause(100); }
  const assert = async (expression, name) => {
    for(let attempt=0;attempt<6;attempt++) { if(await js(`Boolean(${expression})`)) {log('PASS '+name);return;} await pause(100); }
    log('FAIL CONTEXT '+JSON.stringify(await js("({page:document.querySelector('.content')?.dataset.page,active:document.activeElement?.outerHTML?.slice(0,250),editors:[...document.querySelectorAll('.rb-sheet-cell-editor')].map(e=>[e.value,e.getAttribute('aria-label')]),writes:__uiFixture.writes.slice(-2).map(w=>({p:w.p,method:w.method})),dialogs:[...document.querySelectorAll('[role=dialog]')].map(e=>e.textContent),lastToasts:[...document.querySelectorAll('[data-rb-toast]')].map(e=>e.textContent)})")));
    throw new Error('FAIL '+name);
  };
  const click = async text => {
    const position = await js(`(()=>{const dialogs=[...document.querySelectorAll('[role=dialog]')].filter(e=>e.getBoundingClientRect().height>0);const scope=dialogs.at(-1)||document;const e=[...scope.querySelectorAll('button,[role=tab],[role=menuitem]')].find(b=>b.textContent.split(' ').join('')===${JSON.stringify(text.replaceAll(' ',''))});if(!e)throw new Error('缺少操作 '+${JSON.stringify(text)});if(e.disabled)throw new Error('操作被禁用 '+${JSON.stringify(text)});e.scrollIntoView({block:'nearest'});const r=e.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2};})()`);
    await win.webContents.debugger.sendCommand('Input.dispatchMouseEvent',{type:'mousePressed',...position,button:'left',clickCount:1});
    await win.webContents.debugger.sendCommand('Input.dispatchMouseEvent',{type:'mouseReleased',...position,button:'left',clickCount:1});
    await pause(220);
  };
  const page = async title => { await js(`Array.from(document.querySelectorAll('.nav-item')).find(b=>b.title===${JSON.stringify(title)})?.click()`); await pause(180); };
  const input = async (selector, value) => { await js(`(()=>{const root=document.querySelector(${JSON.stringify(selector)});const e=root?.matches('input,textarea')?root:root?.querySelector('input,textarea');if(!e)throw new Error('缺少输入框 '+${JSON.stringify(selector)});Object.getOwnPropertyDescriptor(e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype,'value').set.call(e,${JSON.stringify(value)});e.dispatchEvent(new Event('input',{bubbles:true}));})()`); await pause(80); };
  const capture = async name => { await js("document.querySelectorAll('.banner button').forEach(b=>{if(b.textContent.trim()==='知道了')b.click()})"); await js("document.querySelectorAll('[data-rb-toast] button[aria-label=\"知道了\"]').forEach(b=>b.click())"); await pause(240); const result = await win.webContents.debugger.sendCommand('Page.captureScreenshot'); fs.writeFileSync(path.join(out, name + '.png'), Buffer.from(result.data, 'base64')); };
  const openTool = async title => { await page("Ren'Py 工具箱"); await input('.toolbox-search', title); await js("document.querySelector('.tool-card')?.click()"); await pause(180); };
  const SAMPLE_PAGES = [['翻译任务','translation'],['基础设置','basic'],['项目设置','project'],['术语表','glossary']];
  const captureSamples = async prefix => {
    for (const [title, key] of SAMPLE_PAGES) {
      if (title === '基础设置') await page('基础设置');
      else if (title === '术语表') await openTool('术语表');
      else await page(title);
      if (key === 'glossary') { await js("document.querySelector('.rb-term-row')?.click()"); await pause(160); }
      await capture(`${prefix}-${key}`);
    }
    await page('翻译任务');
  };
  const capturePhase2A = async prefix => {
    await openTool('术语表');
    await js("document.querySelector('.rb-term-row')?.click()"); await pause(160);
    await capture(`${prefix}-glossary`);
    await openTool('禁翻表');
    await capture(`${prefix}-preserve`);
    await openTool('称呼桥接');
    await capture(`${prefix}-honorific`);
    await openTool('检查与润色');
    await js("document.querySelector('.rb-proof-target')?.dispatchEvent(new MouseEvent('dblclick',{bubbles:true}))"); await pause(160);
    await capture(`${prefix}-proofreading`);
    await js("Array.from(document.querySelectorAll('button,[role=tab]')).find(b=>b.textContent.trim()==='取消')?.click()"); await pause(80);
    await page('基础设置');
    await capture(`${prefix}-basic`);
    await page('翻译提示');
    await capture(`${prefix}-prompt`);
    await page('翻译任务');
  };
  const waitLayout = async () => { for (let i = 0; i < 50; i++) { if (await js("!!document.querySelector('.translation-layout')")) return; await pause(100); } };
  const setProgress = async progress => { await js(`__uiFixture.sockets.at(-1).onmessage({data:JSON.stringify({type:'event',event:'TRANSLATION_UPDATE',data:${JSON.stringify(progress)}})})`); await pause(100); };
  await assert("document.querySelector('.rb-progress-percent').textContent.includes('64%')", '翻译快照');
  await assert("document.querySelector('.feed-card').textContent.includes('已保存的译文') && document.body.textContent.includes('已恢复当前项目')", '启动恢复缓存流水');
  await js("__uiFixture.progress={}; __uiFixture.progressSource='none'; __uiFixture.values.output_folder='C:/other/output'; __uiFixture.sockets.at(-1).onmessage({data:JSON.stringify({type:'event',event:'PROJECT_CHANGED',data:{}})});"); await pause(250);
  await assert("document.querySelector('.rb-progress-percent').textContent.includes('0%') && !document.querySelector('.feed-card').textContent.includes('已保存的译文')", '切换空项目清除旧流水和统计');
  await js("__uiFixture.progress={line:64,total_line:100,time:120,total_output_tokens:4800}; __uiFixture.progressSource='cache'; __uiFixture.values.output_folder='C:/ui-check/output'; __uiFixture.sockets.at(-1).onmessage({data:JSON.stringify({type:'event',event:'PROJECT_CHANGED',data:{}})});"); await pause(250);
  await setProgress({ progress: { line: 65, total_line: 100 } });
  await assert("document.querySelector('.rb-progress-percent').textContent.includes('65%')", '兼容分区进度事件');
  await setProgress({line:64,total_line:100});
  await assert("document.querySelectorAll('.rb-nav-section').length===4 && document.querySelectorAll('.rb-nav .nav-item').length===9", '导航工作流分组');
  await js("__uiFixture.sockets.at(-1).onmessage({ data: JSON.stringify({ type: 'job', job: { id: 'smoke', kind: 'demo', status: 'running', total: 1, done: 0, progress: 0, error: null, created_at: 0, updated_at: 0 } }) });");
  await pause(120);
  await assert("!!document.querySelector('.rb-nav') && !!document.querySelector('.task-state')", 'job 消息不误入事件通道');
  await assert("document.querySelector('.workspace-link').getAttribute('aria-label')==='后端已连接'", '全局连接状态');
  await assert("document.querySelector('.task-input').textContent.trim()===__uiFixture.values.input_folder && document.querySelector('.workspace-project').title==='C:/ui-check'", '项目身份与翻译输入目录分开展示');
  await assert("document.querySelector('.task-platform').textContent.includes('主翻译接口') && document.querySelector('.task-language-pair').textContent.includes('EN') && document.querySelector('.task-language-pair').textContent.includes('ZH')", '当前接口与语言上下文');
  await assert("document.querySelector('.task-state').textContent==='可继续'", '已暂停任务状态');
  await setProgress({line:100,total_line:100,failed_line_count:1});
  await assert("document.querySelector('.task-state').textContent==='可继续' && document.querySelector('.task-state').dataset.warning==='true'", '失败条目不误报完成');
  await setProgress({failed_line_count:0});
  await assert("document.querySelector('.task-state').textContent==='已完成'", '任务完成状态');
  await setProgress({line:0,total_line:0});
  await assert("document.querySelector('.task-state').textContent==='待开始' && !document.querySelector('.rb-progress-meta .ant-tag')", '空任务不显示虚假健康状态');
  await setProgress({line:64,total_line:100});
  await assert("document.querySelectorAll('.rb-translation-summary .rb-panel').length===3 && !!document.querySelector('.ant-progress-circle') && document.querySelectorAll('.rb-throughput-stats > div').length===4", '旧版仪表盘分区及未知指标');
  await assert("document.querySelector('.rb-throughput-stats').textContent.includes('—')", '未知指标不伪装为零');
  await assert("(()=>{const e=document.querySelector('.translation-layout .banner');return e&&e.clientHeight>=e.scrollHeight-2})()", '缓存提示条不被压扁');
  await click('估算 Token');
  await assert("__uiFixture.writes.some(w=>w.p==='/api/translation/estimate'&&Object.keys(w.body).length===0)&&[...document.querySelectorAll('[data-rb-toast]')].some(e=>e.textContent.includes('原文 128 tokens'))", 'Token估算发送有效JSON且显示结果');
  await capture('new-ui-translation-dark');
  await captureSamples('p1-dark-1280');
  await capturePhase2A('p2a-dark-1280');
  await js("document.querySelector('.task-input').click()"); await pause(180);
  await assert("document.querySelector('.content').dataset.page==='project' && document.querySelector('.content h1').textContent==='项目设置'", '输入目录快捷入口');
  await page('翻译任务'); await js("document.querySelector('.task-platform').click()"); await pause(180);
  await assert("document.querySelector('.content').dataset.page==='platform'", '翻译接口快捷入口');
  await page('接口管理');
  await assert("(()=>{const e=document.querySelector('.rb-platform-card');const r=e.getBoundingClientRect();return r.width>=220&&r.height>=72&&document.querySelector('.rb-platform-list .rb-settings-group').getBoundingClientRect().height>140})()", 'Qt 分组卡片响应式布局且不挤压');
  await capture('new-ui-platform-dark');
  await click('新增接口'); await capture('new-ui-platform-editor-dark');
  await input('.platform-editor input', '自检接口'); await input('.platform-editor .ant-select-auto-complete input', 'story-model'); await input('.platform-editor input[type=url]', 'https://api.example.com/v1'); await click('保存接口');
  await assert("__uiFixture.values.platforms.some(p=>p.name==='自检接口')", '接口编辑表单提交');
  await assert("!('api_keys' in __uiFixture.writes.at(-1).body)", '空密钥不覆盖凭据');
  await js("document.querySelector('.platform-row-actions button[aria-label=\"编辑\"]').click()"); await pause(100);
  await click('读取模型列表');
  await js("document.querySelector('.platform-editor .ant-select-auto-complete input').focus()");
  await input('.platform-editor .ant-select-auto-complete input', 'available');
  log('MODEL CHECK ' + JSON.stringify(await js("({reads:__uiFixture.reads.slice(-6),list:document.querySelector('[role=listbox]')?.textContent, buttons:Array.from(document.querySelectorAll('.platform-editor button')).map(b=>[b.textContent,b.disabled])})")));
  await assert("Array.from(document.querySelectorAll('.ant-select-item-option')).some(e=>e.getBoundingClientRect().height>0&&e.textContent.includes('available-model')) && __uiFixture.reads.includes('/api/platforms/1/models')", '模型列表可读取并搜索');
  await js("Array.from(document.querySelectorAll('.ant-select-item-option')).find(e=>e.getBoundingClientRect().height>0&&e.textContent.trim()==='available-model').click()"); await pause(100);
  await assert("document.querySelector('.platform-editor .ant-select-auto-complete input').value==='available-model'", '选取模型填入草稿');
  await click('关闭');
  await js("__uiFixture.values.text_preserve_data=[{src:'Name',comment:'短'},{src:'name',comment:'完整备注'}]; __uiFixture.values.text_preserve_enable=false; __uiFixture.values.honorific_placeholder_titles=[{src:'Dr',comment:'旧版备注'},'dr']; __uiFixture.sockets.at(-1).onmessage({data:JSON.stringify({type:'event',event:'PROJECT_CHANGED',data:{}})});"); await pause(200);
  await openTool('禁翻表'); await click('去重');
  await js("__uiFixture.failSettings=true"); await click('保存设置');
  await assert("document.querySelector('.rb-sheet-summary').textContent.includes('有未保存修改') && __uiFixture.values.text_preserve_data.length===2", '禁翻规则保存失败保留草稿');
  await js("__uiFixture.failSettings=false"); await click('保存设置');
  await assert("__uiFixture.values.text_preserve_data.length===1 && __uiFixture.values.text_preserve_data[0].comment==='完整备注' && __uiFixture.values.text_preserve_enable===true && !document.querySelector('.rb-sheet-summary').textContent.includes('有未保存修改')", '禁翻去重保留备注并按 Qt 有条目时启用');
  await openTool('称呼桥接');
  await assert("document.querySelector('.rb-term-row').textContent.includes('Dr') && document.querySelector('.rb-term-row').textContent.includes('旧版备注')", '读取旧版对象格式称呼词');
  await click('去重'); await click('保存');
  await assert("__uiFixture.values.honorific_placeholder_titles.length===1 && __uiFixture.values.honorific_placeholder_titles[0].src==='dr' && __uiFixture.values.honorific_placeholder_titles[0].comment==='旧版备注'", '称呼去重按旧版小写规则保存');
  await click('恢复默认');
  await assert("document.querySelectorAll('.rb-term-row').length===3 && __uiFixture.values.honorific_placeholder_titles.length===1", '恢复引擎默认值只改草稿');
  await click('保存');
  await assert("__uiFixture.values.honorific_placeholder_titles.includes('doctor')", '确认保存默认称呼词');
  await js("document.querySelector('.rb-term-row').querySelectorAll('.ant-table-cell')[1].dispatchEvent(new MouseEvent('dblclick',{bubbles:true}))");await pause(100);
  await input('.rb-sheet-cell-editor','doctor-last字');await click('保存');
  await assert("__uiFixture.values.honorific_placeholder_titles[0]==='doctor-last字'",'称呼单元格未失焦直接保存包含最后一字');
  await click('恢复默认');await click('保存');
  await page('角色 / 世界观工作台'); await click('世界观');
  await input('.workbench-form-grid input', '港湾来信 · 新篇'); await click('保存修改');
  await assert("__uiFixture.assets.worldbook.project_name==='港湾来信 · 新篇'", '世界观保存');
  await click('概览');
  await assert("!!document.querySelector('.rb-workbench-analysis') && Array.from(document.querySelectorAll('button')).some(b=>b.textContent.trim()==='扫描角色' && !b.disabled)", '工作台提供扫描与生成入口');
  await click('世界观'); await input('.workbench-form-grid input', '未保存的工作台编辑'); await click('概览');
  await assert("Array.from(document.querySelectorAll('button')).filter(b=>['扫描角色','生成草稿'].includes(b.textContent.trim())).every(b=>b.disabled)", '未保存资料不能启动扫描或收费分析');
  await click('世界观'); await input('.workbench-form-grid input', '港湾来信 · 新篇'); await click('概览');
  await click('扫描角色');
  await assert("__uiFixture.writes.at(-1).p==='/api/workbench/analysis' && __uiFixture.writes.at(-1).body.action==='scan' && __uiFixture.writes.at(-1).body.storage_key==='fixture' && !document.querySelector('[role=dialog]')", '角色扫描携带项目版本且不请求AI确认');
  await page('翻译任务'); await page('角色 / 世界观工作台');
  await assert("document.querySelector('.rb-workbench-analysis-status').textContent.includes('正在读取项目语料')", '切页返回恢复正在执行的工作台任务');
  await js("__uiFixture.finishWorkbench()"); await pause(1900);
  await assert("document.querySelector('.rb-workbench-draft-review').textContent.includes('灯塔管理员') && __uiFixture.assets.characters.length===1", '扫描结果可读审核且不自动应用正式角色');
  await capture('workbench-scan-drafts-dark');
  await click('应用草稿');
  await js("Array.from(document.querySelectorAll('[role=dialog] button')).find(b=>b.textContent.trim()==='应用草稿').click()"); await pause(180);
  await assert("__uiFixture.assets.characters.length===2 && !__uiFixture.assets.character_drafts.length", '确认后将审核草稿应用到正式资料');
  await click('角色卡'); await input('.rb-workbench-roster input', 'Keeper');
  await assert("document.querySelectorAll('.rb-workbench-character').length===1 && document.querySelector('.rb-workbench-character').textContent.includes('Bob')", '角色搜索覆盖别名');
  await input('.rb-workbench-roster input', '完全不匹配的角色');
  await assert("!document.querySelector('.rb-workbench-character') && document.querySelector('.rb-workbench-roster-list').textContent.trim().length>0", '角色搜索无结果时提供明确反馈');
  await input('.rb-workbench-roster input', ''); await click('概览');
  await js("__uiFixture.workbenchStarts = __uiFixture.writes.filter(w=>w.p==='/api/workbench/analysis').length");
  await click('生成草稿');
  await assert("document.querySelector('[role=dialog]').textContent.includes('Token') && __uiFixture.writes.filter(w=>w.p==='/api/workbench/analysis').length===__uiFixture.workbenchStarts", 'AI分析先确认费用与处理范围');
  await click('确认并生成');
  await assert("__uiFixture.workbenchJob.result.action==='all' && __uiFixture.workbenchJob.result.worker_active", '确认后启动世界观与角色生成');
  await click('取消任务');
  await assert("__uiFixture.workbenchJob.cancel_requested && Array.from(document.querySelectorAll('button,[role=tab]')).find(b=>b.textContent.trim()==='生成草稿').disabled", '取消等待后台真正结束');
  await page('翻译任务'); await page('角色 / 世界观工作台');
  await assert("document.querySelector('.rb-workbench-analysis-status').textContent.includes('正在取消')", '取消状态在离开并返回工作台后保留');
  await js("__uiFixture.finishWorkbench('cancelled', '已取消，未修改项目资料')"); await pause(1900);
  await assert("!__uiFixture.assets.character_drafts.length && document.querySelector('.rb-workbench-analysis-status').textContent.includes('取消')", '取消终态保留已有资料且不产生草稿');
  await click('生成草稿'); await click('确认并生成');
  await js("__uiFixture.finishWorkbench('failed', '模拟接口失败，原资料保持不变')"); await pause(1900);
  await assert("document.querySelector('.rb-workbench-analysis-status').textContent.includes('模拟接口失败') && __uiFixture.assets.characters.length===2", '分析失败显示真实原因并保留资料');
  await click('生成草稿'); await click('确认并生成');
  await js("__uiFixture.finishWorkbench('done', '生成 1 项世界观和 1 位角色草稿')"); await pause(1900);
  await assert("document.querySelector('.rb-workbench-draft-review').textContent.includes('潮汐与灯塔') && !__uiFixture.assets.worldbook.setting_summary.includes('潮汐与灯塔')", 'AI结果先进入草稿审核，不覆盖正式背景');
  await click('扫描角色'); await click('世界观'); await input('.workbench-form-grid input', '任务期间保留的编辑');
  await js("__uiFixture.finishWorkbench()"); await pause(1900);
  await assert("document.querySelector('.workbench-form-grid input').value==='任务期间保留的编辑' && !Array.from(document.querySelectorAll('button,[role=tab]')).find(b=>b.textContent.trim()==='保存修改').disabled", '后台草稿完成不覆盖手工编辑');
  await click('保存修改');
  await assert("__uiFixture.assets.worldbook.project_name==='任务期间保留的编辑'", '完成后使用新草稿版本保存手工资料');
  await input('.workbench-form-grid input', '港湾来信 · 新篇'); await click('保存修改'); await click('概览');

  await click('扫描角色'); await click('世界观'); await input('.workbench-form-grid input', '本地尚未保存的项目名');
  await js("__uiFixture.assets.worldbook.project_name='外部更新的项目名'; __uiFixture.finishWorkbench()"); await pause(1900);
  await assert("document.querySelector('.workbench-form-grid input').value==='本地尚未保存的项目名' && document.body.textContent.includes('正式资料已被其他操作更新')", '外部资料变化保留本地编辑并显示冲突');
  await click('保存修改');
  await assert("__uiFixture.assets.worldbook.project_name==='外部更新的项目名' && document.querySelector('.workbench-form-grid input').value==='本地尚未保存的项目名'", '外部更新后不提升旧编辑版本绕过冲突');
  await click('重新加载'); await click('丢弃并重新加载');
  await input('.workbench-form-grid input', '港湾来信 · 新篇'); await click('保存修改'); await click('概览');
  await js("document.querySelector('.rb-workbench-draft-review').scrollIntoView({block:'start'}); document.querySelector('.rb-workbench-draft-character summary')?.click()"); await pause(180);
  await capture('workbench-analysis-drafts-dark');
  await js("document.querySelector('[title=切换主题]').click()"); await pause(220); await capture('workbench-analysis-drafts-light');
  await js("document.querySelector('[title=切换主题]').click()"); await pause(220);

  await click('世界观'); await input('.workbench-form-grid input', '切项目前尚未保存的资料');
  await js("__uiFixture.savedWorkbench=structuredClone(__uiFixture.assets); __uiFixture.savedOutput=__uiFixture.values.output_folder; __uiFixture.values.output_folder='C:/other-project/output'; __uiFixture.assets={...structuredClone(__uiFixture.assets),storage_key:'other-fixture',revision:1,worldbook:{...__uiFixture.assets.worldbook,project_name:'另一项目'},character_drafts:[],worldbook_draft:{}}; __uiFixture.sockets.at(-1).onmessage({data:JSON.stringify({type:'event',event:'PROJECT_CHANGED',data:{}})});"); await pause(350);
  await assert("document.querySelector('.workbench-form-grid input').value==='切项目前尚未保存的资料' && Array.from(document.querySelectorAll('button,[role=tab]')).find(b=>b.textContent.trim()==='保存修改').disabled", '外部切项目保留旧编辑并阻止写入新项目');
  await click('概览');
  await assert("Array.from(document.querySelectorAll('button,[role=tab]')).find(b=>b.textContent.trim()==='扫描角色').disabled", '旧项目编辑未处理时不能扫描新项目');
  await click('重新加载'); await click('丢弃并重新加载');
  await assert("document.querySelector('.rb-workbench-summary h2').textContent==='另一项目' && !document.querySelector('.rb-workbench-analysis-status')", '明确重新加载后只展示新项目资料和任务');
  await js("__uiFixture.assets=__uiFixture.savedWorkbench; __uiFixture.values.output_folder=__uiFixture.savedOutput; __uiFixture.sockets.at(-1).onmessage({data:JSON.stringify({type:'event',event:'PROJECT_CHANGED',data:{}})});"); await pause(350);

  await click('角色卡'); await capture('new-ui-characters-dark');
  await openTool('术语表'); await js("document.querySelector('.rb-term-row')?.click()"); await pause(120);
  await js("Array.from(document.querySelectorAll('.rb-term-row')).find(row=>row.dataset.rowKey==='0').querySelectorAll('.ant-table-cell')[1].dispatchEvent(new MouseEvent('dblclick',{bubbles:true}))"); await pause(120);
  await input('.rb-sheet-cell-editor', 'Harbor Town');
  await js("document.activeElement.blur()"); await pause(80);
  await js("document.querySelector('.workspace-project').click()"); await pause(180);
  await assert("!!document.querySelector('[role=dialog]') && !!document.querySelector('.glossary-layout')", '切页保护编辑');
  await click('取消'); await click('保存到项目');
  await assert("__uiFixture.glossary.rows[0].src==='Harbor Town'", '词库提交');
  await js("__uiFixture.savedGlossary=structuredClone(__uiFixture.glossary); __uiFixture.glossary.rows=Array.from({length:51},(_,i)=>({src:i===0?'<img class=xss src=x> LONGTERM Row '+ 'x'.repeat(400):i===50?'TailTerm Row':'Term '+i+' Row',dst:'dst '+i,info:'',type:i===3?'角色':'',candidate:i===3,candidate_confirmed:false,record_id:'r'+i})); __uiFixture.glossary.candidate_ids=['r3'];");
  await click('重新载入'); await pause(300);
  await assert("(()=>{const table=document.querySelector('.rb-sheet .ant-table'); if(!table)return false; const heads=[...table.querySelectorAll('thead th')].map(c=>c.textContent.trim()); const row=table.querySelector('.rb-term-row'); const cell=row?.querySelectorAll('.ant-table-cell')[1]; return heads.some(h=>h==='原文')&&heads.some(h=>h==='类别')&&heads.some(h=>h==='命中数')&&cell?.textContent.includes('LONGTERM')&&cell.textContent.includes('<img')&&!table.querySelector('img')&&!document.querySelector('.rb-term-editor')&&getComputedStyle(cell).whiteSpace!=='nowrap'&&!!table.querySelector('.ant-table-tbody-virtual-holder');})()", '术语表使用Ant虚拟表且单元格编辑无侧栏');
  await js("(()=>{const row=document.querySelector('.rb-term-row'); row.focus(); row.dispatchEvent(new KeyboardEvent('keydown',{key:'F2',bubbles:true}));})()"); await pause(120);
  await assert("document.activeElement.closest('.rb-sheet-cell-editor') && document.activeElement.tagName==='TEXTAREA'", 'F2 进入单元格编辑');
  await js("document.activeElement.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));"); await pause(80);
  await js("Array.from(document.querySelectorAll('.rb-term-row')).find(row=>row.dataset.rowKey==='1').querySelectorAll('.ant-table-cell')[1].dispatchEvent(new MouseEvent('dblclick',{bubbles:true}))"); await pause(120);
  await assert("document.activeElement.closest('.rb-sheet-cell-editor') && Array.from(document.querySelectorAll('.rb-term-row')).find(row=>row.dataset.rowKey==='1').getAttribute('data-selected')==='true'", '双击进入对应单元格');
  await js("document.activeElement.dispatchEvent(new KeyboardEvent('keydown',{key:'Tab',bubbles:true}));"); await pause(200);
  await assert("document.activeElement.closest('.rb-sheet-cell-editor')", 'Tab 切到下一可编辑单元格');
  await js("document.activeElement.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));"); await pause(80);
  await js("(()=>{const row=Array.from(document.querySelectorAll('.rb-term-row')).find(row=>row.dataset.rowKey==='2'); row.focus(); row.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));})()"); await pause(80);
  await assert("Array.from(document.querySelectorAll('.rb-term-row')).find(row=>row.dataset.rowKey==='2').getAttribute('data-selected')==='true'", 'Enter 选择词条');
  await js("__uiFixture.engineStatus='TRANSLATING'; __uiFixture.sockets.at(-1).onmessage({data:JSON.stringify({type:'event',event:'TRANSLATION_START',data:{}})});"); await pause(400);
  await assert("document.body.textContent.includes('任务执行期间词库只读') && !document.querySelector('.rb-sheet-cell-editor') && Array.from(document.querySelectorAll('button,[role=tab]')).find(b=>b.textContent.trim()==='保存到项目').disabled && Array.from(document.querySelectorAll('button,[role=tab]')).find(b=>b.textContent.trim()==='新增').disabled", '术语表运行中只读');
  await js("__uiFixture.engineStatus='IDLE'; __uiFixture.sockets.at(-1).onmessage({data:JSON.stringify({type:'event',event:'TRANSLATION_DONE',data:{}})});"); await pause(400);
  await assert("Array.from(document.querySelectorAll('button,[role=tab]')).find(b=>b.textContent.trim()==='新增') && !Array.from(document.querySelectorAll('button,[role=tab]')).find(b=>b.textContent.trim()==='新增').disabled", '术语表结束后恢复编辑');
  await js("Array.from(document.querySelectorAll('.rb-term-row')).find(row=>row.dataset.rowKey==='3').click()"); await pause(80);
  await assert("Array.from(document.querySelectorAll('.rb-term-row')).find(row=>row.dataset.rowKey==='3').textContent.includes('候选') && !!Array.from(document.querySelectorAll('button,[role=tab]')).find(b=>b.textContent.trim()==='确认所选')", '候选词条可确认');
  await click('确认所选'); await pause(80);
  await js("Array.from(document.querySelectorAll('.rb-term-row')).find(row=>row.dataset.rowKey==='3').querySelectorAll('.ant-table-cell')[3].dispatchEvent(new MouseEvent('dblclick',{bubbles:true}))"); await pause(100);
  await input('.rb-sheet-cell-editor', '角色地名');
  await js("document.activeElement.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));"); await pause(80);
  await assert("Array.from(document.querySelectorAll('.rb-term-row')).find(row=>row.dataset.rowKey==='3').textContent.includes('角色地名')", '类别单元格可编辑');
  await click('下一页');
  await assert("(()=>{const rows=[...document.querySelectorAll('.rb-term-row')]; const foot=document.querySelector('.rb-sheet-foot').textContent; return rows.length===1 && rows[0].querySelector('.rb-proof-index').textContent.trim()==='51' && rows[0].textContent.includes('TailTerm') && foot.includes('2 / 2');})()", '超过五十行进入第二页');
  await input('[aria-label="搜索词条"]', 'Row');
  await assert("(()=>{const rows=[...document.querySelectorAll('.rb-term-row')]; const foot=document.querySelector('.rb-sheet-foot').textContent; return rows.length>0 && rows.length<=50 && rows[0].querySelector('.rb-proof-index').textContent.trim()==='1' && foot.includes('1 / 2');})()", '搜索后回到第一页且序号不变');
  await input('[aria-label="搜索词条"]', '');
  await click('下一页');
  await js("document.querySelector('.rb-term-row').querySelectorAll('.ant-table-cell')[1].dispatchEvent(new MouseEvent('dblclick',{bubbles:true}))"); await pause(120);
  await input('.rb-sheet-cell-editor', 'MappedTail');
  await js("document.activeElement.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));"); await pause(80);
  await click('保存到项目'); await pause(250);
  await assert("__uiFixture.glossary.rows[50].src==='MappedTail' && __uiFixture.glossary.rows[0].src.includes('LONGTERM') && __uiFixture.glossary.rows[3].candidate_confirmed===true && __uiFixture.glossary.rows[3].src==='Term 3 Row'", '编辑保存映射到原始序号');
  await click('新增'); await pause(120);
  await assert("document.querySelector('.rb-sheet-cell-editor') && document.querySelector('.rb-term-row[data-selected=\"true\"] .rb-proof-index').textContent.trim()==='52' && document.querySelector('.rb-sheet-foot').textContent.includes('2 / 2')", '新增词条追加到末页并定位原文');
  await js("document.activeElement.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));"); await pause(80);
  await click('删除所选'); await pause(80);
  if (await js("!Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='下一页').disabled")) await click('下一页');
  await js("document.querySelector('.rb-term-row').click()"); await pause(80);
  await click('删除所选'); await pause(80);
  await assert("document.querySelectorAll('.rb-term-row').length>0 && document.querySelectorAll('.rb-term-row').length<=50 && document.querySelector('.rb-sheet-foot').textContent.includes('1 / 1')", '删除末页后页码收敛');
  await assert("!!Array.from(document.querySelectorAll('button,[role=tab]')).find(b=>b.textContent.trim()==='导入 Excel') && !!Array.from(document.querySelectorAll('button,[role=tab]')).find(b=>b.textContent.trim()==='扫描术语候选') && !!Array.from(document.querySelectorAll('button,[role=tab]')).find(b=>b.textContent.trim()==='快速翻译')", '术语表旧 Qt 操作按钮齐备');
  await js("__uiFixture.glossary=structuredClone(__uiFixture.savedGlossary)");
  await click('重新载入'); await click('重新载入'); await pause(300);
  await assert("document.querySelectorAll('.rb-term-row').length===2 && !document.querySelector('.rb-sheet-summary').textContent.includes('有未保存修改')", '词库测试后恢复原词条');
await js("__uiFixture.lexGlossaryBase=structuredClone(__uiFixture.glossary); __uiFixture.lexOutputBase=__uiFixture.values.output_folder; __uiFixture.lexConfirmBase=window.confirm; __uiFixture.lexConfirmTexts=[]; __uiFixture.lexiconJob=null; __uiFixture.glossary.rows=[{src:'Harbor',dst:'港湾',info:'已有译文'},{src:'FastTerm',dst:'',info:''},{src:'LlmTerm',dst:'LlmTerm',info:''}]; __uiFixture.glossary.candidate_ids=[]");
await click('重新载入'); await pause(250);
await click('统计命中');
await assert("__uiFixture.lexiconInput.kind==='glossary' && __uiFixture.lexiconInput.rows.length===3 && __uiFixture.lexiconInput.output_folder===__uiFixture.values.output_folder && __uiFixture.lexiconInput.project_key==='ui-check|chinese'", '术语命中统计发送行快照与项目身份');
await js("__uiFixture.finishLexicon({kind:'glossary',counts:[8,2,1],counted_item_total:20,snapshot_keys:['Harbor|0','FastTerm|0','LlmTerm|0'],message:'已统计 3 条规则'})"); await pause(1100);
await assert("[...document.querySelectorAll('.rb-term-row')].map(row=>row.querySelectorAll('.ant-table-cell')[5].textContent.trim()).join(',')==='8,2,1'", '术语命中数显示于对应行');

const glossaryBeforeScan = await js("__uiFixture.writes.length");
await js("window.confirm=text=>{__uiFixture.lexConfirmTexts.push(text);return false}");
await click('扫描术语候选');
await assert(`__uiFixture.writes.length===${glossaryBeforeScan} && __uiFixture.lexConfirmTexts.at(-1).includes('未确认候选')`, '拒绝候选扫描确认时不提交');
await js("window.confirm=text=>{__uiFixture.lexConfirmTexts.push(text);return true}");
await click('扫描术语候选');
await assert("__uiFixture.lexiconInput.confirm===true && __uiFixture.lexiconInput.rows[0].dst==='港湾'", '候选扫描确认后发送当前草稿');
await js("__uiFixture.lexCandidateRows=[...structuredClone(__uiFixture.glossary.rows),{src:'DragonGlass',dst:'',type:'地名',info:'扫描候选',candidate:true,candidate_confirmed:false,record_id:'scan-c1'}]; __uiFixture.finishLexicon({entries:__uiFixture.lexCandidateRows,candidate_ids:['scan-c1'],count_map:{dragonglass:4},added:1,updated:0,written:true,message:'术语候选扫描完成'})"); await pause(1100);
await assert("document.querySelector('.rb-sheet-foot').textContent.includes('4 条') && document.querySelector('.rb-term-row[data-row-key=\"3\"]').textContent.includes('候选') && document.querySelector('.rb-sheet-summary').textContent.includes('有未保存修改') && __uiFixture.glossary.rows.length===3", '扫描候选进入草稿且不会自动保存正式词库');

for (const [label, mode, index, translated] of [['快速翻译','fast',1,'快速译名'],['LLM 翻译','llm',2,'模型译名']]) {
  await click(label);
  await assert(`__uiFixture.lexiconInput.mode===${JSON.stringify(mode)} && __uiFixture.lexiconInput.confirm===true`, label + '只在确认后提交');
  await js(`__uiFixture.finishLexicon({success:true,results:[[${index},${JSON.stringify(translated)}]],row_snapshots:__uiFixture.lexiconInput.rows,failed_count:0,message:'译名已完成'})`);
  await pause(1100);
  await assert(`document.querySelector('.rb-term-row[data-row-key=\"${index}\"]').querySelectorAll('.ant-table-cell')[2].textContent===${JSON.stringify(translated)} && document.querySelector('.rb-term-row[data-row-key=\"0\"]').querySelectorAll('.ant-table-cell')[2].textContent==='港湾'`, label + '填充目标并保留已有译文');
}
for (const label of ['快速翻译','LLM 翻译']) {
  await click(label);
  await js("__uiFixture.finishLexicon({success:false,results:[],failed_count:1,warnings:['模拟翻译失败'],message:'模拟翻译失败，原译保持'},'failed')"); await pause(1100);
  await assert("document.querySelector('.rb-term-row[data-row-key=\"0\"]').querySelectorAll('.ant-table-cell')[2].textContent==='港湾' && document.querySelector('.rb-term-row[data-row-key=\"1\"]').querySelectorAll('.ant-table-cell')[2].textContent==='快速译名' && document.querySelector('.rb-term-row[data-row-key=\"2\"]').querySelectorAll('.ant-table-cell')[2].textContent==='模型译名' && document.querySelector('.glossary-layout').textContent.includes('模拟翻译失败')", label + '失败保留全部原译并显示错误');
}
await click('扫描术语候选'); await click('停止');
await js("__uiFixture.lexiconJob.status='cancelled'"); await pause(1100);
await assert("__uiFixture.lexiconJob.cancel_requested && __uiFixture.lexiconJob.result.worker_active && [...document.querySelectorAll('button')].find(b=>b.textContent.replaceAll(' ','')==='保存到项目').disabled", '词库取消终态仍等待 worker 并保持只读');
await js("__uiFixture.finishLexicon({message:'已停止'},'cancelled')"); await pause(1100);
await assert("![...document.querySelectorAll('button')].find(b=>b.textContent.replaceAll(' ','')==='新增').disabled", '词库 worker 退出后恢复编辑');

// 恢复任务不属于本页启动的任务，必须显式确认后才应用。
await click('重新载入'); await click('重新载入'); await pause(250);
await js("__uiFixture.lexiconJob={...structuredClone(__uiFixture.lexiconJob),id:'lexicon-task-recovered',kind:'lexicon_scan_candidates',status:'done',cancel_requested:false,result:{project_key:'ui-check|chinese',output_folder:__uiFixture.values.output_folder,worker_active:false,entries:[...structuredClone(__uiFixture.glossary.rows),{src:'RecoveredOnly',dst:'',candidate:true,record_id:'recovered-c1'}],candidate_ids:['recovered-c1'],written:true,message:'恢复扫描完成'}}");
await openTool('术语表');
await assert("document.querySelectorAll('.rb-term-row').length===3 && !document.querySelector('.rb-sheet').textContent.includes('RecoveredOnly') && [...document.querySelectorAll('button')].some(b=>b.textContent==='应用任务结果')", '重开词库仅恢复任务状态不自动覆盖草稿');
await js("window.confirm=text=>{__uiFixture.lexConfirmTexts.push(text);return false}");
await click('应用任务结果');
await assert("document.querySelectorAll('.rb-term-row').length===3 && __uiFixture.lexConfirmTexts.at(-1).includes('草稿')", '拒绝恢复结果确认时保持稿本');
await js("window.confirm=text=>{__uiFixture.lexConfirmTexts.push(text);return true}");
await click('应用任务结果'); await pause(250);
await assert("document.querySelector('.rb-sheet-foot').textContent.includes('4 条') && document.querySelector('.rb-sheet').textContent.includes('RecoveredOnly') && ![...document.querySelectorAll('button')].some(b=>b.textContent==='应用任务结果')", '确认后应用恢复结果且只应用一次');
await js("document.querySelector('.rb-term-row[data-row-key=\"1\"]').querySelectorAll('.ant-table-cell')[2].dispatchEvent(new MouseEvent('dblclick',{bubbles:true}))"); await pause(120);
await input('.rb-sheet-cell-editor', '恢复后人工译名');
await js("document.activeElement.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}))"); await pause(1100);
await assert("document.querySelector('.rb-term-row[data-row-key=\"1\"]').querySelectorAll('.ant-table-cell')[2].textContent==='恢复后人工译名' && ![...document.querySelectorAll('button')].some(b=>b.textContent==='应用任务结果')", '恢复结果不会重复覆盖后续人工编辑');

// 40 条仍在第一页；新增的第 41 条在虚拟窗口外也必须自动挂载并聚焦。
await js("__uiFixture.lexiconJob=null; __uiFixture.glossary.rows=Array.from({length:40},(_,i)=>({src:'VirtualTerm '+i,dst:'译名 '+i,info:''})); __uiFixture.glossary.candidate_ids=[]");
await click('重新载入'); await click('重新载入'); await pause(250);
await assert("!document.querySelector('.rb-term-row[data-row-key=\"39\"]')", '四十条术语的末行处于未挂载窗口');
await click('新增'); await pause(200);
await assert("document.activeElement.classList.contains('rb-sheet-cell-editor') && document.activeElement.closest('.rb-term-row').dataset.rowKey==='40' && document.querySelector('.rb-sheet-foot').textContent.includes('1 / 1')", '同页新增离屏术语自动挂载并聚焦原文');
await js("document.activeElement.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true})); __uiFixture.glossary.rows=Array.from({length:50},(_,i)=>({src:'VirtualTerm '+i,dst:'译名 '+i,info:''}))");
await click('重新载入'); await click('重新载入'); await pause(250);
const glossaryTabSteps = await js("(()=>{const mounted=[...document.querySelectorAll('.rb-term-row')]; __uiFixture.tabTarget=Math.min(49,Number(mounted.at(-1).dataset.rowKey)+2); const row=mounted[0]; row.focus(); row.dispatchEvent(new KeyboardEvent('keydown',{key:'F2',bubbles:true})); __uiFixture.tabStart=Number(row.dataset.rowKey);return (__uiFixture.tabTarget-__uiFixture.tabStart)*4;})()");
await pause(120);
await assert("!document.querySelector('.rb-term-row[data-row-key=\"'+__uiFixture.tabTarget+'\"]')", 'Tab 目标在当前虚拟窗口外');
for (let step=0; step<glossaryTabSteps; step++) { await js("document.activeElement.dispatchEvent(new KeyboardEvent('keydown',{key:'Tab',bubbles:true}))"); await pause(50); }
await assert("document.activeElement.classList.contains('rb-sheet-cell-editor') && document.activeElement.closest('.rb-term-row').dataset.rowKey===String(__uiFixture.tabTarget) && document.activeElement.getAttribute('aria-label').endsWith(' src')", 'Tab 连续跨虚拟窗口后仍聚焦正确单元格');
await js("document.activeElement.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true})); __uiFixture.glossary=structuredClone(__uiFixture.lexGlossaryBase)");
await click('重新载入'); await pause(250);

// 未 blur 的旧稿与同批引擎写锁一起保留，但不准写入新项目。
await js("document.querySelector('.rb-term-row').querySelectorAll('.ant-table-cell')[1].dispatchEvent(new MouseEvent('dblclick',{bubbles:true}))"); await pause(120);
await input('.rb-sheet-cell-editor', 'GlossaryUnblurDraft');
const glossaryPatchBaseline = await js("__uiFixture.writes.filter(w=>w.p==='/api/workbench/glossary' && w.method==='PATCH').length");
await js("__uiFixture.values.output_folder='C:/other-project/output'; __uiFixture.engineStatus='TESTING'; __uiFixture.sockets.at(-1).onmessage({data:JSON.stringify({type:'event',event:'PROJECT_CHANGED',data:{}})})"); await pause(450);
await assert("document.querySelector('.rb-sheet').textContent.includes('GlossaryUnblurDraft') && !document.querySelector('.rb-sheet-cell-editor') && document.querySelector('.rb-sheet-summary').textContent.includes('有未保存修改') && [...document.querySelectorAll('button')].find(b=>b.textContent.replaceAll(' ','')==='保存到项目').disabled", '术语切项目与写锁同批变化保留未 blur 草稿');
await js("__uiFixture.engineStatus='IDLE'; __uiFixture.sockets.at(-1).onmessage({data:JSON.stringify({type:'event',event:'TRANSLATION_DONE',data:{}})})"); await pause(250);
await assert(`[...document.querySelectorAll('button')].find(b=>b.textContent.replaceAll(' ','')==='保存到项目').disabled && __uiFixture.writes.filter(w=>w.p==='/api/workbench/glossary' && w.method==='PATCH').length===${glossaryPatchBaseline}`, '引擎空闲后仍禁止旧术语草稿串写新项目');
await js("__uiFixture.values.output_folder=__uiFixture.lexOutputBase; __uiFixture.glossary=structuredClone(__uiFixture.lexGlossaryBase); __uiFixture.lexiconJob=null; __uiFixture.sockets.at(-1).onmessage({data:JSON.stringify({type:'event',event:'PROJECT_CHANGED',data:{}})})"); await pause(250);
await assert("document.querySelector('.rb-sheet').textContent.includes('GlossaryUnblurDraft')", '恢复 fixture 身份仍保留旧稿直到用户明确载入');
await click('重新载入'); await click('重新载入'); await pause(250);
await js("window.confirm=__uiFixture.lexConfirmBase");
await assert("document.querySelectorAll('.rb-term-row').length===__uiFixture.lexGlossaryBase.rows.length && !document.querySelector('.rb-sheet').textContent.includes('GlossaryUnblurDraft') && !document.querySelector('.rb-sheet-summary').textContent.includes('有未保存修改')", '术语场景恢复原 fixture 并明确重新载入');
  await js("__uiFixture.savedPreserveData=structuredClone(__uiFixture.values.text_preserve_data); __uiFixture.savedPreserveEnable=__uiFixture.values.text_preserve_enable; __uiFixture.values.text_preserve_data=Array.from({length:51},(_,i)=>({src:i===0?'<img class=xss src=x> KEEPLONG Rule '+ 'y'.repeat(400):i===50?'TailKeep Rule':'Keep '+i+' Rule',comment:''})); __uiFixture.values.text_preserve_enable=true; __uiFixture.sockets.at(-1).onmessage({data:JSON.stringify({type:'event',event:'PROJECT_CHANGED',data:{}})});");
  await pause(400);
  await openTool('禁翻表');
  await assert("(()=>{const table=document.querySelector('.rb-sheet .ant-table'); if(!table)return false;const heads=[...table.querySelectorAll('thead th')].map(c=>c.textContent.trim());const cell=table.querySelector('.rb-term-row')?.querySelectorAll('.ant-table-cell')[1];return heads.some(h=>h==='原文')&&heads.some(h=>h==='备注')&&heads.some(h=>h==='命中数')&&cell?.textContent.includes('KEEPLONG')&&cell.textContent.includes('<img')&&!table.querySelector('img')&&!document.querySelector('.rb-term-editor')&&getComputedStyle(cell).whiteSpace!=='nowrap';})()", '禁翻表使用Ant虚拟表且单元格编辑无侧栏');
  await click('下一页');
  await input('[aria-label="搜索禁翻规则"]', 'Rule');
  await assert("(()=>{const rows=[...document.querySelectorAll('.rb-term-row')]; return rows.length>0 && rows.length<=50 && rows[0].querySelector('.rb-proof-index').textContent.trim()==='1' && document.querySelector('.rb-sheet-foot').textContent.includes('1 / 2');})()", '禁翻搜索后回到第一页');
  await input('[aria-label="搜索禁翻规则"]', '');
  await click('下一页');
  await js("document.querySelector('.rb-term-row').querySelectorAll('.ant-table-cell')[1].dispatchEvent(new MouseEvent('dblclick',{bubbles:true}))"); await pause(120);
  await input('.rb-sheet-cell-editor', 'MappedKeep');
  await js("document.activeElement.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));"); await pause(80);
  await click('保存设置'); await pause(300);
  await assert("__uiFixture.values.text_preserve_data[50].src==='MappedKeep' && __uiFixture.values.text_preserve_data[0].src.includes('KEEPLONG') && __uiFixture.values.text_preserve_data.length===51", '禁翻编辑保存映射到原始序号');
  await click('新增'); await pause(120);
  await assert("document.querySelector('.rb-sheet-cell-editor') && document.querySelector('.rb-term-row[data-selected=\"true\"] .rb-proof-index').textContent.trim()==='52'", '新增禁翻规则追加到末页并定位原文');
  await js("document.activeElement.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));"); await pause(80);
  await click('删除所选'); await pause(80);
  if (await js("!Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='下一页').disabled")) await click('下一页');
  await js("document.querySelector('.rb-term-row').click()"); await pause(80);
  await click('删除所选'); await pause(80);
  await assert("document.querySelectorAll('.rb-term-row').length>0 && document.querySelectorAll('.rb-term-row').length<=50 && document.querySelector('.rb-sheet-foot').textContent.includes('1 / 1')", '禁翻删除末页后页码收敛');
  await assert("!!Array.from(document.querySelectorAll('button,[role=tab]')).find(b=>b.textContent.trim()==='导入 Excel') && !!Array.from(document.querySelectorAll('button,[role=tab]')).find(b=>b.textContent.trim()==='重新扫描变量') && !!Array.from(document.querySelectorAll('button,[role=tab]')).find(b=>b.textContent.trim()==='统计命中')", '禁翻表旧 Qt 操作按钮齐备');
  await js("__uiFixture.values.text_preserve_data=structuredClone(__uiFixture.savedPreserveData); __uiFixture.values.text_preserve_enable=__uiFixture.savedPreserveEnable;");
  await click('加载设置'); await pause(400);
  await assert("!document.querySelector('.rb-sheet-summary').textContent.includes('有未保存修改')", '禁翻测试后恢复原规则');
await js("__uiFixture.lexPreserveBase=structuredClone(__uiFixture.values.text_preserve_data); __uiFixture.lexPreserveEnableBase=__uiFixture.values.text_preserve_enable; __uiFixture.lexPreserveOutputBase=__uiFixture.values.output_folder; __uiFixture.lexPreserveConfirmBase=window.confirm; __uiFixture.lexPreserveConfirmTexts=[]; __uiFixture.lexiconJob=null; __uiFixture.values.text_preserve_data=[{src:'[name]',comment:'姓名变量'},{src:'[score]',comment:'分数变量'}]; __uiFixture.values.text_preserve_enable=true");
await click('加载设置'); await pause(250);
await click('统计命中');
await assert("__uiFixture.lexiconInput.kind==='preserve' && __uiFixture.lexiconInput.rows.length===2 && __uiFixture.lexiconInput.output_folder===__uiFixture.values.output_folder", '禁翻命中统计发送实际规则与项目输出身份');
await js("__uiFixture.finishLexicon({kind:'preserve',counts:[3,7],counted_item_total:20,snapshot_keys:['[name]','[score]'],message:'已统计 2 条规则'})"); await pause(1100);
await assert("[...document.querySelectorAll('.rb-term-row')].map(row=>row.querySelectorAll('.ant-table-cell')[3].textContent.trim()).join(',')==='3,7'", '禁翻命中数映射到原始行');
const preserveBeforeRescan = await js("__uiFixture.writes.length");
await js("window.confirm=text=>{__uiFixture.lexPreserveConfirmTexts.push(text);return false}");
await click('重新扫描变量');
await assert(`__uiFixture.writes.length===${preserveBeforeRescan} && __uiFixture.lexPreserveConfirmTexts.at(-1).includes('整表替换') && __uiFixture.values.text_preserve_data[0].src==='[name]'`, '禁翻重扫拒绝确认时不提交也不覆盖规则');
await js("window.confirm=text=>{__uiFixture.lexPreserveConfirmTexts.push(text);return true}");
await click('重新扫描变量');
await assert("__uiFixture.lexiconInput.confirm===true && __uiFixture.lexiconInput.project_key==='ui-check|chinese'", '确认禁翻重扫后提交身份与覆盖许可');
const preserveSettingsReads = await js("__uiFixture.reads.filter(p=>p==='/api/settings').length");
await js("__uiFixture.finishLexicon({written:true,rows:[{src:'[actor]',comment:'重新扫描变量'},{src:'[score]',comment:'重新扫描变量'}],enabled:true,message:'禁翻变量已重扫并保存'})"); await pause(1100);
await assert(`__uiFixture.values.text_preserve_data[0].src==='[actor]' && __uiFixture.values.text_preserve_enable===true && document.querySelector('.rb-sheet').textContent.includes('[actor]') && !document.querySelector('.rb-sheet-summary').textContent.includes('有未保存修改') && __uiFixture.reads.filter(p=>p==='/api/settings').length>${preserveSettingsReads}`, '禁翻重扫结果已持久化并重新载入设置');

await js("document.querySelector('.rb-term-row').querySelectorAll('.ant-table-cell')[1].dispatchEvent(new MouseEvent('dblclick',{bubbles:true}))"); await pause(120);
await input('.rb-sheet-cell-editor', '[PreserveUnblurDraft]');
const preservePatchBaseline = await js("__uiFixture.writes.filter(w=>w.p==='/api/settings' && w.method==='PATCH').length");
await js("__uiFixture.values.output_folder='C:/other-project/output'; __uiFixture.values.text_preserve_data=[{src:'[new_project]',comment:'外部项目规则'}]; __uiFixture.engineStatus='TESTING'; __uiFixture.lexiconJob=null; __uiFixture.sockets.at(-1).onmessage({data:JSON.stringify({type:'event',event:'PROJECT_CHANGED',data:{}})})"); await pause(450);
await assert("document.querySelector('.rb-sheet').textContent.includes('[PreserveUnblurDraft]') && !document.querySelector('.rb-sheet').textContent.includes('[new_project]') && !document.querySelector('.rb-sheet-cell-editor') && document.querySelector('.rb-sheet-summary').textContent.includes('有未保存修改') && [...document.querySelectorAll('button')].find(b=>b.textContent.replaceAll(' ','')==='保存设置').disabled", '禁翻切项目与 TESTING 同批变化保留未 blur 旧稿');
await js("__uiFixture.engineStatus='IDLE'; __uiFixture.sockets.at(-1).onmessage({data:JSON.stringify({type:'event',event:'TRANSLATION_DONE',data:{}})})"); await pause(250);
await assert(`[...document.querySelectorAll('button')].find(b=>b.textContent.replaceAll(' ','')==='保存设置').disabled && __uiFixture.values.text_preserve_data[0].src==='[new_project]' && __uiFixture.writes.filter(w=>w.p==='/api/settings' && w.method==='PATCH').length===${preservePatchBaseline}`, '引擎空闲后禁止旧禁翻草稿串写新项目设置');
await js("__uiFixture.values.output_folder=__uiFixture.lexPreserveOutputBase; __uiFixture.values.text_preserve_data=structuredClone(__uiFixture.lexPreserveBase); __uiFixture.values.text_preserve_enable=__uiFixture.lexPreserveEnableBase; __uiFixture.sockets.at(-1).onmessage({data:JSON.stringify({type:'event',event:'PROJECT_CHANGED',data:{}})})"); await pause(250);
await assert("document.querySelector('.rb-sheet').textContent.includes('[PreserveUnblurDraft]')", '恢复设置 fixture 后仍保留旧禁翻草稿直到明确载入');
await click('加载设置'); await pause(350);
await js("window.confirm=__uiFixture.lexPreserveConfirmBase");
await assert("!document.querySelector('.rb-sheet').textContent.includes('[PreserveUnblurDraft]') && !document.querySelector('.rb-sheet-summary').textContent.includes('有未保存修改') && document.querySelectorAll('.rb-term-row').length===__uiFixture.lexPreserveBase.length", '禁翻场景恢复原规则并明确加载设置');

// 校对页连续上下移动，必须让未挂载行持续接住焦点。
await js("__uiFixture.lexProofItemsBase=structuredClone(__uiFixture.items); __uiFixture.items=Array.from({length:50},(_,i)=>({...__uiFixture.lexProofItemsBase[0],id:i,version:'virtual-'+i,src:'Virtual proof '+i,dst:'虚拟译文 '+i,row:24+i}))");
await openTool('检查与润色');
await assert("!document.querySelector('.rb-proofreading-row[data-row-key=\"35\"]') && document.querySelectorAll('.rb-proofreading-row').length<50", '校对第五十条分页内存在未挂载的离屏行');
await js("document.querySelector('.rb-proofreading-row[data-row-key=\"0\"]').click()");
for (let step=0; step<35; step++) { await js("document.activeElement.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowDown',bubbles:true}))"); await pause(50); }
await assert("document.activeElement.classList.contains('rb-proofreading-row') && document.activeElement.dataset.rowKey==='35' && document.activeElement.dataset.selected==='true' && !document.querySelector('[role=dialog]')", '校对向下连续跨离屏行仍移动选中与焦点');
for (let step=0; step<35; step++) { await js("document.activeElement.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowUp',bubbles:true}))"); await pause(50); }
await assert("document.activeElement.classList.contains('rb-proofreading-row') && document.activeElement.dataset.rowKey==='0' && document.activeElement.dataset.selected==='true'", '校对向上连续跨离屏行回到首行');
await js("__uiFixture.items=structuredClone(__uiFixture.lexProofItemsBase)"); await click('刷新译文'); await pause(250);
await assert("document.querySelectorAll('.rb-proofreading-row').length===__uiFixture.lexProofItemsBase.length", '校对键盘场景明确刷新恢复原译文');
await openTool('禁翻表');
  await openTool('检查与润色'); await js("document.querySelector('.rb-proof-target').dispatchEvent(new MouseEvent('dblclick',{bubbles:true}))"); await pause(100);
  await input('#proofreading-draft', '艾丽丝，那封信今早到了。'); await click('保存译文');
  await assert("__uiFixture.items[0].dst==='艾丽丝，那封信今早到了。' && !document.querySelector('[role=dialog]') && !document.querySelector('#proofreading-draft')", '校对保存');
  await js("__uiFixture.issueDelay=true; document.querySelector('input[type=checkbox][aria-label=only-issues]')?.click()");
  await js("Array.from(document.querySelectorAll('label')).find(label=>label.textContent==='仅看问题')?.click()"); await pause(30);
  await assert("!!document.querySelector('.rb-proof-loading') && !document.querySelector('.rb-proofreading-row')", '问题筛选立即反馈且不展示旧结果');
  await pause(420); await js("__uiFixture.issueDelay=false");
  await assert("!document.querySelector('.rb-proof-loading') && !!document.querySelector('.rb-proofreading-row')", '问题检查结束后恢复表格');
  await assert("Array.from(document.querySelectorAll('button,[role=tab]')).find(b=>b.textContent.trim()==='AI 校对').disabled", '质量任务要求先选中译文');
  await js("document.querySelector('[aria-label=选择行]').click()"); await pause(100);
  await click('AI 校对'); await click('开始处理');
  await assert("__uiFixture.writes.some(w=>w.p==='/api/proofreading/quality' && w.body.task==='proofread' && w.body.ids.length===1 && w.body.ids[0]===0 && w.body.rows[0].version==='v1')", 'AI 校对发送选中范围和行版本');
  await assert("document.querySelector('.rb-proofreading-task').textContent.includes('处理') && !document.querySelector('#proofreading-draft')", '质量运行期间只读并显示报告');
  await click('取消质量任务'); await pause(200);
  await assert("!document.querySelector('.rb-proofreading-task') && __uiFixture.qualityReports[0].state === 'CANCELLED'", '质量取消后恢复编辑');
  await js("document.querySelector('[aria-label=选择行]').click()"); await pause(100);
  await click('AI 润色');
  await js("__uiFixture.rejectQuality = true"); await click('开始处理');
  await assert("!!document.querySelector('[role=dialog]') && __uiFixture.engineStatus==='IDLE' && document.body.textContent.includes('译文或缓存条目已更新')", '版本冲突保留确认并显示真实错误');
  await js("__uiFixture.rejectQuality = false"); await click('开始处理');
  await assert("__uiFixture.writes.some(w=>w.p==='/api/proofreading/quality' && w.body.task==='polish')", 'AI 润色使用独立任务类型');
  await js("__uiFixture.engineStatus='IDLE'; __uiFixture.emitQuality({...__uiFixture.qualityReports[0],state:'COMPLETED',completed_count:1,updated_count:1})"); await pause(300);
  await assert("!document.querySelector('.rb-proofreading-task') && __uiFixture.qualityReports[0].state === 'COMPLETED'", '质量完成刷新缓存并恢复编辑');
  await page('翻译任务'); await openTool('检查与润色');
  await click('质量报告');
  await assert("document.querySelector('.rb-quality-report').textContent.includes('已完成') && document.querySelector('[role=dialog]').textContent.includes('对齐异常 1')", '翻译质量与 AI 处理记录区分显示');
  await js("document.querySelector('[role=dialog]').dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))"); await pause(200);
  await js("__uiFixture.items.push({...__uiFixture.items[0],id:1,version:'v2',src:'Another line',dst:'另一行'})"); await click('刷新译文');
  await js("document.querySelector('.rb-proof-target').dispatchEvent(new MouseEvent('dblclick',{bubbles:true}))"); await pause(100);
  await input('#proofreading-draft', '尚未保存的编辑');
  await js("window.__originalConfirm = window.confirm; window.confirm = () => false; document.querySelectorAll('.rb-proof-target')[1].dispatchEvent(new MouseEvent('dblclick',{bubbles:true}))"); await pause(100);
  await assert("document.querySelector('#proofreading-draft').value==='尚未保存的编辑'", '切换编辑行保留未保存译文');
  await click('取消');
  await assert("document.querySelector('#proofreading-draft').value==='尚未保存的编辑'", '取消编辑保留未保存译文');
  await js("window.confirm = () => true; void 0"); await click('取消');
  await js("window.confirm = window.__originalConfirm; __uiFixture.items.pop()"); await click('刷新译文');
  await js("__uiFixture.items.push({...__uiFixture.items[0],id:1,version:'v2',src:'Two',dst:'第二行'},{...__uiFixture.items[0],id:2,version:'v3',src:'Three',dst:'第三行'})"); await click('刷新译文');
  await js("document.querySelector('.rb-proofreading-row').click()"); await pause(80);
  await assert("!document.querySelector('#proofreading-draft') && document.querySelectorAll('.rb-proofreading-row[data-selected=true]').length===1", '单击只选行不打开编辑');
  await assert("getComputedStyle(document.querySelector('.rb-proof-target')).borderTopWidth==='0px' && getComputedStyle(document.querySelector('.rb-proof-target')).paddingTop==='0px'", '译文没有按钮边框和内边距');
  await js("document.querySelectorAll('.rb-proofreading-row')[2].dispatchEvent(new MouseEvent('click',{bubbles:true,shiftKey:true}))"); await pause(80);
  await assert("document.querySelectorAll('.rb-proofreading-row[data-selected=true]').length===3", 'Shift 连选三行');
  await js("document.querySelectorAll('.rb-proofreading-row')[1].dispatchEvent(new MouseEvent('click',{bubbles:true,ctrlKey:true}))"); await pause(80);
  await assert("document.querySelectorAll('.rb-proofreading-row[data-selected=true]').length===2", 'Ctrl 取消单行选择');
  await js("document.querySelector('.rb-proofreading-row').dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,clientX:480,clientY:370}))"); await pause(180);
  await assert("(()=>{const r=document.querySelector('[role=menu]').getBoundingClientRect();return Math.abs(r.left-480)<25 && Math.abs(r.top-370)<25})()", '右键菜单靠近鼠标而非行尾');
  await assert("document.querySelector('[role=menu]').textContent.includes('重新翻译') && document.querySelector('[role=menu]').textContent.includes('定位译文')", '恢复旧版右键操作');
  await capture('proofreading-context-menu'); await click('定位译文');
  await assert("document.querySelector('.rb-proof-context [data-target=true]').textContent.includes('24')", '定位展示实际译文行');
  await js("document.querySelector('[role=dialog]').dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))"); await pause(200);
  await click('导出译文'); await click('写入译文文件');
  await assert("__uiFixture.writes.some(w=>w.p==='/api/proofreading/export' && w.body.cache_token==='fixture-cache')", '导出携带项目缓存身份');
  await js("document.querySelector('.rb-proofreading-row').focus();document.querySelector('.rb-proofreading-row').dispatchEvent(new KeyboardEvent('keydown',{key:'F2',bubbles:true}))"); await pause(100);
  await assert("!!document.querySelector('.rb-proof-bilingual-editor') && !document.querySelector('.rb-sheet-editor')", 'F2 打开双语对照弹窗');
  await capture('proofreading-bilingual-editor'); await click('取消');
  await js("document.querySelector('.rb-proofreading-row').dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,clientX:window.innerWidth-8,clientY:window.innerHeight-8}))"); await pause(180);
  await assert("(()=>{const r=document.querySelector('[role=menu]').getBoundingClientRect();return r.right<=window.innerWidth && r.bottom<=window.innerHeight && r.left>=0 && r.top>=0})()", '右键菜单在边缘自动避让');
  await js("document.querySelector('[role=menu]').dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))"); await pause(180);
  await js("document.querySelector('.rb-proofreading-row').click()"); await pause(80);
  await click('重译选中行'); await click('开始重译');
  await assert("__uiFixture.writes.some(w=>w.p==='/api/proofreading/retranslate' && w.body.rows.length===1 && w.body.rows[0].version==='v1')", '重译提交选中版本');
  await click('取消重译');
  await assert("__uiFixture.retranslate.state==='CANCELLING' && Array.from(document.querySelectorAll('button,[role=tab]')).find(b=>b.textContent.trim()==='重译选中行').disabled", '取消重译等待后台完成');
  await js("__uiFixture.retranslate={state:'CANCELLED',total:1,done:1,updated:1,failed:0}"); await pause(1900);
  await assert("!Array.from(document.querySelectorAll('button,[role=tab]')).find(b=>b.textContent.trim()==='导出译文').disabled", '重译终态恢复编辑');

  await js("__uiFixture.items.splice(1)"); await click('刷新译文');
  await capture('new-ui-proofreading-dark');
  await page('翻译提示'); await click('查看当前提示词');
  await assert("document.querySelector('.prompt-preview-text').value.includes('自然中文')", '静态提示词预览');
  await js("document.querySelector('.dialog').dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))"); await pause(100);
  await assert("!document.querySelector('[role=dialog]')", 'Escape 关闭');
  await page("Ren'Py 工具箱");
  await assert("document.querySelectorAll('.tool-card').length===27 && document.querySelectorAll('.rb-tool-availability').length===16", '工具箱明确标记未接入工具');
  await capture('new-ui-toolbox-dark');
  await input('.toolbox-search', '术语');
  await assert("document.querySelectorAll('.tool-card').length===1", '工具搜索不重复');
  await js("document.querySelector('.tool-card').click()"); await pause(180);
  await assert("!!document.querySelector('.glossary-layout')", '工具词库入口');
  await openTool('一键翻译');
  await assert("!!document.querySelector('.rb-onekey-page') && Array.from(document.querySelectorAll('button')).some(b=>b.textContent.trim()==='开始准备')", '一键翻译页可进入');
  await click('开始准备');
  await assert("!!document.querySelector('[role=dialog]') && document.querySelector('[role=dialog]').textContent.includes('不会自动启动翻译')", '一键准备先确认且不自动翻译');
  await click('开始准备');
  await assert("__uiFixture.writes.at(-1).p==='/api/onekey/prepare' && __uiFixture.writes.at(-1).body.confirm_write===true && __uiFixture.onekeyJob.result.worker_active", '一键准备启动协作任务');
  await click('取消任务');
  await assert("__uiFixture.onekeyJob.cancel_requested", '一键任务可取消');
  await page('翻译任务'); await openTool('一键翻译');
  await assert("document.querySelector('.rb-onekey-page').textContent.includes('正在取消') && Array.from(document.querySelectorAll('button,[role=tab]')).find(b=>b.textContent.trim()==='开始准备').disabled", '切页恢复取消中的准备任务并阻止重复启动');
  await js("__uiFixture.onekeyJob.status='cancelled'; __uiFixture.onekeyJob.result.worker_active=false; __uiFixture.engineStatus='IDLE';"); await pause(1700);
  await click('开始准备'); await click('开始准备');
  await js("__uiFixture.onekeyJob.cancel_requested=false; __uiFixture.onekeyJob.status='done'; __uiFixture.onekeyJob.result.worker_active=false; __uiFixture.onekeyJob.result.stage='ready'; __uiFixture.onekeyJob.result.message='准备完成'; __uiFixture.engineStatus='IDLE'; __uiFixture.sockets.at(-1).onmessage({data:JSON.stringify({type:'job',job:__uiFixture.onekeyJob})});"); await pause(1600);
  await assert("Array.from(document.querySelectorAll('button')).some(b=>b.textContent.trim()==='打开翻译页') && Array.from(document.querySelectorAll('button')).some(b=>b.textContent.trim()==='应用译文')", '准备完成后可返回翻译页并应用');
  await openTool('应用翻译到游戏');
  await assert("!!document.querySelector('.rb-onekey-page') && Array.from(document.querySelectorAll('button')).some(b=>b.textContent.trim()==='应用译文')", '应用译文复用一键应用阶段');
  await click('应用译文');
  await assert("document.querySelector('[role=dialog]').textContent.includes('将覆盖游戏 TL') && __uiFixture.onekeyJob.kind==='onekey_prepare'", '应用译文先确认覆盖范围');
  await click('应用译文');
  await assert("__uiFixture.onekeyJob.kind==='onekey_apply' && __uiFixture.writes.at(-1).body.confirm===true", '确认后才提交应用任务');
  await js("__uiFixture.onekeyJob.status='done'; __uiFixture.onekeyJob.result.worker_active=false; __uiFixture.onekeyJob.result.stage='done'; __uiFixture.onekeyJob.result.message='已应用 1 个文件'; __uiFixture.engineStatus='IDLE';"); await pause(1700);
  await assert("document.querySelector('.rb-onekey-page').textContent.includes('已应用 1 个文件')", '应用结束显示结果并恢复引擎状态');
  await openTool('解包/打包');
  await assert("!!document.querySelector('.rb-archive-page') && Array.from(document.querySelectorAll('button')).some(b=>b.textContent.trim()==='开始解包')", '解包页可进入');
  await click('开始解包');
  await assert("!!document.querySelector('[role=dialog]') && document.querySelector('[role=dialog]').textContent.includes('可能覆盖')", '解包前确认写入与覆盖');
  await click('开始解包');
  await assert("__uiFixture.writes.at(-1).p==='/api/archive/unpack' && __uiFixture.archiveJob.result.archives_removed===false", '解包任务保留源档');
  await click('取消任务');
  await assert("__uiFixture.archiveJob.cancel_requested && __uiFixture.archiveJob.result.worker_active", '解包取消等待后台线程退出');
  await js("__uiFixture.archiveJob.status='cancelled'; __uiFixture.archiveJob.result.worker_active=false; __uiFixture.engineStatus='IDLE';"); await pause(1700);
  await js("Array.from(document.querySelectorAll('label')).find(label=>label.textContent==='覆盖已有 .rpy')?.click()"); await pause(80);
  await click('开始反编译');
  await assert("!!document.querySelector('[role=dialog]')", '覆盖反编译需确认');
  await js("document.querySelector('.dialog')?.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))"); await pause(100);
  await capture('new-ui-archive-dark');
  await openTool('一键翻译');
  await capture('new-ui-onekey-dark');
await openTool('终极结构导出');
await assert("document.querySelector('[data-rb-page=ma-suite]') && __uiFixture.reads.includes('/api/asset-suite/status') && !document.querySelector('.rb-asset-run-structure').disabled", '结构工具入口与 canonical 状态恢复');
await input('.rb-asset-path', 'C:/ui-check/game');
await click('生成结构');
await assert("document.querySelector('[role=dialog]').textContent.includes('先备份') && !__uiFixture.writes.some(w=>w.p==='/api/asset-suite/structure')", '结构先确认覆盖范围');
await click('生成结构');
await assert("__uiFixture.writes.at(-1).p==='/api/asset-suite/structure' && __uiFixture.writes.at(-1).body.project_key===__uiFixture.assetProjectKey && __uiFixture.writes.at(-1).body.confirm_overwrite===true && document.querySelector('.rb-asset-path input').disabled", '结构 POST 携带 canonical key 与确认');
await js("__uiFixture.finishAsset({success:true,level:'success',operation:'structure',output_dir:'C:/ui-check/translate_output',names_count:1,others_count:2,replace_count:3,message:'结构导出完成：角色 1 / 其他 2 / 替换 3'})");
await pause(1900);
await assert("document.querySelector('.rb-asset-output').textContent.includes('C:/ui-check/translate_output') && document.querySelector('.rb-asset-page').textContent.includes('结构导出完成') && !document.querySelector('.rb-asset-path input').disabled", '结构完成显示真实输出并恢复输入');

await input('.rb-asset-emoji-dir', 'C:/ui-check/game/tl/chinese');
await click('译前准备');
await assert("document.querySelector('[role=dialog]').textContent.includes('备份整个目标目录') && __uiFixture.assetJob.kind==='asset_structure'", 'Emoji 原地替换先确认');
await click('译前准备');
await assert("__uiFixture.writes.at(-1).p==='/api/asset-suite/emoji' && __uiFixture.writes.at(-1).body.project_key===__uiFixture.assetProjectKey && __uiFixture.writes.at(-1).body.confirm===true && __uiFixture.writes.at(-1).body.mode==='prepare'", 'Emoji POST 身份与确认');
await click('取消任务');
await js("__uiFixture.assetJob.status='cancelled'");
await pause(1900);
await assert("__uiFixture.assetJob.cancel_requested && __uiFixture.assetJob.result.worker_active && document.querySelector('.rb-asset-path input').disabled && document.querySelector('.rb-asset-emoji-prepare').disabled && document.querySelector('.rb-asset-page').textContent.includes('等待后台线程结束')", 'Emoji 取消状态仍等待 worker 退出并保持只读');
await js("__uiFixture.finishAsset({backup_path:'C:/ui-check/emoji_backup',message:'任务已取消'},'cancelled')");
await pause(1900);
await assert("!document.querySelector('.rb-asset-path input').disabled && !document.querySelector('.rb-asset-cancel') && document.querySelector('.rb-asset-page').textContent.includes('任务已取消')", 'Emoji worker 退出后解除只读');

await openTool('批量修正');
await assert("!!document.querySelector('[data-rb-page=batch-correction]') && !document.querySelector('.rb-asset-page').textContent.includes('emoji_backup')", '批量修正入口拒绝其它工具任务结果');
await input('.rb-asset-input-dir', 'C:/ui-check/reports');
await input('.rb-asset-output-dir', 'C:/ui-check/corrections');
await click('生成修正数据');
await assert("document.querySelector('[role=dialog]').textContent.includes('批量修正.xlsx') && __uiFixture.assetJob.kind==='asset_emoji'", '校对导出先确认工作簿覆盖');
await click('生成修正数据');
await assert("__uiFixture.writes.at(-1).p==='/api/asset-suite/corrections/export' && __uiFixture.writes.at(-1).body.project_key===__uiFixture.assetProjectKey && __uiFixture.writes.at(-1).body.confirm_overwrite===true", '校对导出 POST 身份与确认');
await js("__uiFixture.finishAsset({success:true,operation:'corrections_export',path:'C:/ui-check/corrections/批量修正.xlsx',count:2,backup_path:'C:/ui-check/corrections/批量修正.xlsx.bak',warnings:[],message:'已生成修正数据文件（共 2 条）'})");
await pause(1900);
await assert("document.querySelector('.rb-asset-workbook input').value==='C:/ui-check/corrections/批量修正.xlsx'", '校对导出 path 回填真实 xlsx 工作簿');
await input('.rb-asset-translation-root', 'C:/ui-check/game/tl/chinese');
await click('注入修正');
await assert("document.querySelector('[role=dialog]').textContent.includes('原地修改') && __uiFixture.assetJob.kind==='asset_corrections_export'", '校对注入先确认原地写入');
await click('注入修正');
await assert("__uiFixture.writes.at(-1).p==='/api/asset-suite/corrections/apply' && __uiFixture.writes.at(-1).body.confirm===true && __uiFixture.writes.at(-1).body.project_key===__uiFixture.assetProjectKey && __uiFixture.writes.at(-1).body.workbook==='C:/ui-check/corrections/批量修正.xlsx'", '校对注入发送真实工作簿与身份');
await js("__uiFixture.finishAsset({success:true,level:'warning',operation:'corrections_apply',partial:true,applied_files:1,applied_changes:1,warnings:['未找到目标文件: missing.rpy'],unmatched_preview:[{path:'missing.rpy',count:1,reason:'文件不存在'}],backups:['C:/ui-check/game/tl/chinese/chapter_01.rpy.bak'],message:'部分完成：已更新 1 个文件，应用 1 处；1 个文件仍有未匹配项'})");
await pause(1900);
await assert("document.querySelector('.rb-asset-unmatched').textContent.includes('missing.rpy') && document.querySelector('.rb-asset-unmatched').textContent.includes('文件不存在') && document.querySelector('.rb-asset-page').textContent.includes('未找到目标文件: missing.rpy') && document.querySelector('.rb-asset-page').textContent.includes('chapter_01.rpy.bak')", '校对注入展示警告、未匹配条目及真实 backups');

await openTool('姓名提取');
await assert("!!document.querySelector('[data-rb-page=name-extraction]') && !document.querySelector('.rb-asset-unmatched')", '姓名提取入口拒绝校对任务结果');
await click('开始提取');
await assert("__uiFixture.writes.at(-1).p==='/api/asset-suite/names/extract' && __uiFixture.writes.at(-1).body.project_key===__uiFixture.assetProjectKey", '姓名提取 POST 携带 canonical key');
await js("__uiFixture.finishAsset({success:true,operation:'names_extract',entries:[{src:'Alice',context:'[从 chapter_01.rpy 提取]'}],count:1,empty:false,warnings:[],message:'找到 1 个角色姓名'})");
await pause(1900);
await assert("document.querySelector('.rb-asset-name-list .ant-table-tbody .ant-table-row td:first-child input').value==='Alice' && document.querySelector('.rb-asset-name-list .ant-table-tbody .ant-table-row td:first-child input').readOnly", '姓名结果进入真实 Ant Table 且原文只读');
await js("__uiFixture.nameRestore={root:__uiFixture.assetProjectRoot,key:__uiFixture.assetProjectKey,input:__uiFixture.values.input_folder,output:__uiFixture.values.output_folder,job:structuredClone(__uiFixture.assetJob)};__uiFixture.assetProjectRoot='C:/name-restore-other';__uiFixture.assetProjectKey='other|chinese';__uiFixture.values.input_folder='C:/name-restore-other/game/tl/chinese';__uiFixture.values.output_folder='C:/name-restore-other/output';__uiFixture.sockets.at(-1).onmessage({data:JSON.stringify({type:'event',event:'PROJECT_CHANGED',data:{}})})");
await pause(350);
await assert("!document.querySelector('.rb-asset-name-list .ant-table-row')", 'B 项目清空 A 姓名');
await js("Object.assign(__uiFixture,{assetProjectRoot:__uiFixture.nameRestore.root,assetProjectKey:__uiFixture.nameRestore.key,assetJob:__uiFixture.nameRestore.job});__uiFixture.values.input_folder=__uiFixture.nameRestore.input;__uiFixture.values.output_folder=__uiFixture.nameRestore.output;__uiFixture.sockets.at(-1).onmessage({data:JSON.stringify({type:'event',event:'PROJECT_CHANGED',data:{}})})");
await pause(1900);
await assert("document.querySelector('.rb-asset-name-list .ant-table-row td:first-child input')?.value==='Alice'", 'A→B→A 恢复同一个 done 姓名任务');
await input('.rb-asset-name-list .ant-table-row td:nth-child(2) input', '保留姓名编辑');
await click('开始提取');
await js("__uiFixture.finishAsset({operation:'names_extract',entries:[{src:'LateCancelledName',dst:'不应入稿'}],count:1,empty:false},'cancelled')");
await pause(1900);
await assert("document.querySelector('.rb-asset-name-list .ant-table-row td:first-child input')?.value==='Alice' && document.querySelector('.rb-asset-name-list .ant-table-row td:nth-child(2) input')?.value==='保留姓名编辑'", '取消终态非空 entries 不覆盖旧 draft');
await input('.rb-asset-name-list .ant-table-tbody .ant-table-row td:nth-child(2) input', '艾丽丝');
await click('JSON');
// 截获实际下载 Blob；不把模拟响应本身当作导出验证。
await js("__uiFixture.savedCreateObjectURL=URL.createObjectURL; __uiFixture.savedAnchorClick=HTMLAnchorElement.prototype.click; HTMLAnchorElement.prototype.click=function(){__uiFixture.namesDownloadFilename=this.download}; URL.createObjectURL=blob=>{void blob.text().then(text=>{__uiFixture.namesDownloaded=JSON.parse(text)});return __uiFixture.savedCreateObjectURL.call(URL,blob)};void 0");
await click('导出术语表');
await assert("document.querySelector('[role=dialog]').textContent.includes('JSON') && !__uiFixture.writes.some(w=>w.p==='/api/asset-suite/names/export')", '姓名 JSON 导出先确认');
await click('导出术语表');
await pause(200);
await assert("__uiFixture.writes.at(-1).p==='/api/asset-suite/names/export' && __uiFixture.writes.at(-1).body.project_key===__uiFixture.assetProjectKey && __uiFixture.writes.at(-1).body.entries[0].dst==='艾丽丝' && Array.isArray(__uiFixture.namesDownloaded) && __uiFixture.namesDownloaded.length===1 && __uiFixture.namesDownloaded[0].src==='Alice' && __uiFixture.namesDownloaded[0].dst==='艾丽丝' && __uiFixture.namesDownloaded[0].info==='角色姓名' && __uiFixture.namesDownloaded[0].type==='角色' && __uiFixture.namesDownloadFilename==='glossary_names.json' && document.querySelector('.rb-asset-page').textContent.includes('glossary_names.json')", '姓名编辑后的 dst 导出为 Qt 兼容裸数组');
await js("URL.createObjectURL=__uiFixture.savedCreateObjectURL; HTMLAnchorElement.prototype.click=__uiFixture.savedAnchorClick;void 0");
await assert("__uiFixture.writes.filter(w=>w.p.startsWith('/api/asset-suite/')).every(w=>w.body.project_key===__uiFixture.assetProjectKey)", '资源套件所有 POST 都携带后端 canonical key');

// 持有旧项目的一次 GET 完成快照，再切项目并释放，验证晚到结果不会写回。
await js("__uiFixture.holdAssetStatus=true");
await pause(1900);
await assert("typeof __uiFixture.releaseAssetStatus==='function'", '旧项目 GET 快照已在请求途中');
await js("__uiFixture.savedAssetContext={root:__uiFixture.assetProjectRoot,key:__uiFixture.assetProjectKey,input:__uiFixture.values.input_folder,output:__uiFixture.values.output_folder}; __uiFixture.assetProjectRoot='C:/other-project'; __uiFixture.assetProjectKey='c:'+String.fromCharCode(92)+'other-project|chinese'; __uiFixture.values.input_folder='C:/other-project/game/tl/chinese'; __uiFixture.values.output_folder='C:/other-project/output'; __uiFixture.sockets.at(-1).onmessage({data:JSON.stringify({type:'event',event:'PROJECT_CHANGED',data:{}})})");
await pause(350);
await js("__uiFixture.releaseAssetStatus()");
await pause(200);
await assert("document.querySelector('.rb-asset-input-dir input').value==='C:/other-project/game' && document.querySelector('.rb-asset-page').textContent.includes('当前 0 条姓名') && !document.querySelector('.rb-asset-name-list .ant-table-tbody .ant-table-row') && !document.querySelector('.rb-asset-page').textContent.includes('找到 1 个角色姓名') && !document.querySelector('.rb-asset-page').textContent.includes('glossary_names.json')", '切项目拒绝旧 GET 结果并清空旧姓名与导出反馈');
await js("Object.assign(__uiFixture,{assetProjectRoot:__uiFixture.savedAssetContext.root,assetProjectKey:__uiFixture.savedAssetContext.key,assetJob:null}); __uiFixture.values.input_folder=__uiFixture.savedAssetContext.input; __uiFixture.values.output_folder=__uiFixture.savedAssetContext.output; __uiFixture.sockets.at(-1).onmessage({data:JSON.stringify({type:'event',event:'PROJECT_CHANGED',data:{}})})");
await pause(350);
await openTool('姓名提取'); await click('开始提取'); await js("__uiFixture.finishAsset({success:true,operation:'names_extract',entries:[{src:'Alice',dst:'艾丽丝'}],count:1,empty:false,message:'姓名恢复完成'})"); await pause(1900);
await js("__uiFixture.oldNameFetch=window.fetch;__uiFixture.oldNameAnchor=HTMLAnchorElement.prototype.click;__uiFixture.lateNameDownloads=0;HTMLAnchorElement.prototype.click=function(){if(this.download)__uiFixture.lateNameDownloads++};window.fetch=async(resource,options)=>{const response=await __uiFixture.oldNameFetch(resource,options);const path=new URL(typeof resource==='string'?resource:resource.url,location.origin).pathname;if(path==='/api/asset-suite/names/export')return new Promise(resolve=>{__uiFixture.releaseNameExport=()=>resolve(response)});return response}");
await click('导出术语表'); await click('导出术语表');
await assert("typeof __uiFixture.releaseNameExport==='function'", '姓名导出响应正在途中');
await page('翻译任务');
await js("__uiFixture.releaseNameExport()");
await pause(200);
await assert("__uiFixture.lateNameDownloads===0 && !document.querySelector('[data-rb-page=name-extraction]')", '已卸载姓名页晚到导出不自动下载');
await js("window.fetch=__uiFixture.oldNameFetch;HTMLAnchorElement.prototype.click=__uiFixture.oldNameAnchor");
  await page('Agent 助手');
  await assert("!!document.querySelector('.agent-composer textarea') && !document.querySelector('.agent-empty').textContent.includes('暂不可用')", 'Agent 工作区已替换占位页');
  await js("document.querySelector('.agent-suggestion').click()"); await pause(80);
  await js("document.querySelector('[aria-label=\"Agent 思考等级\"]').click()"); await pause(120);
  await js("Array.from(document.querySelectorAll('.ant-select-item-option')).find(o=>o.textContent.trim()==='高')?.click()"); await pause(120);
  await click('发送');
  await assert("__uiFixture.writes.at(-1).p==='/api/agent/message' && __uiFixture.writes.at(-1).body.thinking_level==='HIGH' && document.querySelectorAll('.agent-message').length===2", 'Agent 发送实际请求与思考覆盖项');
  await js("__uiFixture.agent.messages.at(-1).content='找到 2 个资源包。'; __uiFixture.agent.messages.at(-1).tools=[{name:'list_rpa_files',status:'done',message:'找到 2 个资源包'}]; __uiFixture.emitAgent();"); await pause(220);
  await assert("document.querySelector('.agent-message-body').textContent.includes('找到 2 个资源包') && !!document.querySelector('.agent-tool')", 'Agent 流式快照与工具反馈');
  await page('翻译任务'); await page('Agent 助手');
  await assert("document.querySelectorAll('.agent-message').length===2 && Array.from(document.querySelectorAll('button')).some(button=>button.textContent.trim()==='停止')", 'Agent 切页恢复正在运行的会话');
  await click('停止');
  await assert("__uiFixture.writes.at(-1).p==='/api/agent/stop' && document.querySelector('.agent-chat').textContent.includes('已停止')", 'Agent 停止请求');
  await click('新建任务'); await click('清空并新建');
  await assert("__uiFixture.agent.messages.length===0 && !!document.querySelector('.agent-empty')", 'Agent 清空会话与上下文');
  await input('.agent-composer textarea', '解包当前项目'); await click('发送');
  await js("__uiFixture.agent.confirmation={id:'c'.repeat(32),name:'unpack_rpa_files',arguments:{},data:{game_dir:'C:/ui-check/game',count:2},expires_at:Date.now()/1000+120}; __uiFixture.emitAgent();"); await pause(220);
  await assert("document.querySelector('.agent-confirmation').textContent.includes('C:/ui-check/game') && __uiFixture.confirmed.length===0", 'Agent 写入前展示服务端范围且不自动批准');
  await capture('new-ui-agent-confirmation-dark');
  await click('拒绝执行');
  await assert("__uiFixture.confirmed.at(-1).approved===false && !document.querySelector('.agent-confirmation')", 'Agent 拒绝工具');
  await input('.agent-composer textarea', '确认解包当前项目'); await click('发送');
  await js("__uiFixture.agent.confirmation={id:'d'.repeat(32),name:'unpack_rpa_files',arguments:{},data:{game_dir:'C:/ui-check/game',count:2},expires_at:Date.now()/1000+120}; __uiFixture.emitAgent();"); await pause(220);
  await click('确认执行');
  await assert("__uiFixture.writes.at(-1).body.confirmation_id==='d'.repeat(32) && __uiFixture.confirmed.at(-1).approved===true", 'Agent 确认仅提交一次性标识');
  await js("__uiFixture.agent.messages.at(-1).content=['**检查完成**','',String.fromCharCode(96).repeat(3)+'renpy','<img src=invalid>',String.fromCharCode(96).repeat(3)].join(String.fromCharCode(10)); __uiFixture.emitAgent();"); await pause(220);
  await assert("!!document.querySelector('.agent-message-body strong') && !!document.querySelector('.agent-message-body pre code') && !document.querySelector('.agent-message-body img')", 'Agent 格式化消息不执行 HTML');
  await input('.agent-composer textarea', '断线时保留的草稿');
  const readsBeforeReconnect = await js("__uiFixture.reads.filter(path=>path==='/api/settings').length");
  await js("__uiFixture.sockets.at(-1).close()"); await pause(120);
  await assert("document.querySelector('.backend-notice').textContent.includes('npm run dev:web') && document.querySelector('.agent-composer textarea').value==='断线时保留的草稿' && document.querySelector('.agent-composer button[type=submit]').disabled", '断线说明与 Agent 草稿保护');
  await pause(800);
  await assert(`document.querySelector('.workspace-link').getAttribute('aria-label')==='后端已连接' && __uiFixture.reads.filter(path=>path==='/api/settings').length>${readsBeforeReconnect} && document.querySelector('.agent-composer textarea').value==='断线时保留的草稿'`, '后端重连后重新加载配置和会话');
  await input('.agent-composer textarea', '');
  await capture('new-ui-agent-dark');
  await js("document.querySelector('[title=\"切换主题\"]').click()"); await pause(200); await captureSamples('p1-light-1280'); await capturePhase2A('p2a-light-1280'); await capture('new-ui-glossary-light');
  await page('Agent 助手'); await capture('new-ui-agent-light');
  await page('翻译任务'); await capture('new-ui-translation-light');
  const labels = [['翻译任务'], ['Agent 助手'], ['项目设置'], ['接口管理'], ["Ren'Py 工具箱"], ['角色 / 世界观工作台'], ['基础设置'], ['专家设置'], ['翻译提示'], ['应用设置'], ['工具', '术语表'], ['工具', '禁翻表'], ['工具', '称呼桥接'], ['工具', '检查与润色'], ['工具', '一键翻译'], ['工具', '解包/打包'], ['工具', '应用翻译到游戏'], ['工具', '终极结构导出'], ['工具', '批量修正'], ['工具', '姓名提取']];
  for (const [width,height] of [[560,700],[680,800],[900,640],[1000,640],[1280,800],[1600,1000],[1920,1080]]) {
    await win.webContents.debugger.sendCommand('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
    for (const item of labels) {
      const title = item[0] === '工具' ? item[1] : item[0];
      if (item[0] === '工具') await openTool(item[1]); else await page(item[0]);
      const data = await js(`({root:document.documentElement.scrollWidth>innerWidth||document.documentElement.scrollHeight>innerHeight+1,panels:Array.from(document.querySelectorAll('.content,.workspace-bar,.task-context,.settings-header,.workbench-header,.translation-footer,.rb-command-bar,.rb-sheet,.platform-toolbar,.agent-topbar,.agent-controls,.agent-composer,.agent-confirmation,.rb-titlebar')).filter(e=>e.scrollWidth>e.clientWidth+1).map(e=>e.className),controls:Array.from(document.querySelectorAll('button,input,select,textarea')).filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&!e.closest('.ant-table')&&(r.left<0||r.right>innerWidth+1)}).map(e=>e.getAttribute('aria-label')||e.textContent.trim())})`);
      log('LAYOUT '+width+' '+title+' '+JSON.stringify(data));
      if (data.root || data.panels.length || data.controls.length) throw new Error('布局越界：'+width+' '+title+' '+JSON.stringify(data));
      await assert("document.querySelector('.sidebar-footer').getBoundingClientRect().bottom<=innerHeight+1", '侧栏页脚可见 '+width+' '+title);
      if (['检查与润色','术语表','禁翻表','称呼桥接'].includes(title)) {
        await assert("(()=>{const e=document.querySelector('.proofreading-pagination');const r=e?.getBoundingClientRect();return r&&r.height>0&&r.top>=38&&r.bottom<=innerHeight+1;})()", '表格分页完整可见 '+width+' '+title);
      }
      if (width === 680 && (title === '术语表' || title === '禁翻表')) {
        await js("document.querySelector('.rb-term-row')?.querySelectorAll('.ant-table-cell')[1]?.dispatchEvent(new MouseEvent('dblclick',{bubbles:true}))"); await pause(160);
        const fit = await js("(()=>{const sheet=document.querySelector('.rb-sheet'); const editor=document.querySelector('.rb-sheet-cell-editor'); const scroller=document.querySelector('.rb-sheet-scroll'); if(!sheet||!editor||!scroller) return 'missing'; if(document.querySelector('.rb-term-editor')) return 'sidebar-present'; const er=editor.getBoundingClientRect(); const sr=scroller.getBoundingClientRect(); const scrollStyle=getComputedStyle(scroller); const inside=er.left>=sr.left-1&&er.right<=sr.right+1; const contained=sheet.scrollWidth<=sheet.clientWidth+1; const tableScroll=scrollStyle.overflowX==='auto'||scrollStyle.overflowX==='scroll'||!!scroller.querySelector('.ant-table-tbody-virtual-holder'); if(inside&&contained&&tableScroll) return ''; return JSON.stringify({inside,contained,tableScroll,editorLeft:Math.round(er.left),scrollRight:Math.round(sr.right)});})()");
        if (fit) throw new Error('窄窗单元格编辑越界：'+title+' '+fit);
        await js("document.activeElement?.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))"); await pause(60);
      }
    }
    await assert("document.querySelector('.sidebar-footer').getBoundingClientRect().bottom<=innerHeight", '侧栏底部入口可见 '+width);
    if (width === 1280) {
      await assert("(()=>{const e=document.querySelector('.sidebar-navigation');return !!e && e.scrollHeight<=e.clientHeight})()", '侧栏不需要滚动');
      await page('翻译任务');
      await assert("document.querySelector('.content h1').getBoundingClientRect().top<=64", '翻译标题起点');
    }
    if (width === 680) { await openTool('检查与润色'); await capture('new-ui-proofreading-680'); }
    if (width === 900) {
      await assert("(()=>{const e=document.querySelector('.sidebar-navigation');return !!e && e.scrollHeight<=e.clientHeight})()", '窄窗口侧栏不需要滚动');
      await captureSamples('p1-light-900');
    }
  }
  for (const accent of ['indigo', 'teal']) {
    await js(`localStorage.setItem('renpybox.accent',${JSON.stringify(accent)})`);
    await win.webContents.reload();
    await waitLayout();
    await js("document.querySelector('[title=\"切换主题\"]').click()"); await pause(200);
    await page('翻译任务'); await capture(`p1-accent-${accent}-translation`);
    await page('基础设置'); await capture(`p1-accent-${accent}-basic`);
  }
  await js("localStorage.removeItem('renpybox.accent')");
  await win.webContents.reload();
  await waitLayout();
  await win.webContents.debugger.sendCommand('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});
  await page('翻译任务');
  await assert("getComputedStyle(document.querySelector('.translation-layout')).animationName==='none'", '尊重减少动态效果设置');
  if (process.env.RENPYBOX_UI_CAPTURE_ALL === '1') {
    await win.webContents.debugger.sendCommand('Emulation.clearDeviceMetricsOverride');
    win.setContentSize(1280, 800);
    const pages = [['翻译任务', 'translation'], ['Agent 助手', 'agent'], ['项目设置', 'project'], ['接口管理', 'platform'], ["Ren'Py 工具箱", 'toolbox'], ['角色 / 世界观工作台', 'workbench'], ['基础设置', 'basic'], ['专家设置', 'expert'], ['翻译提示', 'prompt'], ['应用设置', 'settings']];
    for (const scheme of ['dark', 'light']) {
      if (await js("document.documentElement.dataset.theme.toLowerCase()") !== scheme) { await js("document.querySelector('[title=切换主题]').click()"); await pause(200); }
      for (const [title, key] of pages) { await page(title); await capture('all-' + scheme + '-' + key); }
      for (const [title, key] of [['检查与润色', 'proofreading'], ['术语表', 'glossary'], ['禁翻表', 'preserve'], ['称呼桥接', 'honorific'], ['终极结构导出','ma-suite'], ['批量修正','batch-correction'], ['姓名提取','name-extraction']]) { await openTool(title); await capture('all-' + scheme + '-' + key); }
    }
  }
  log('控制台错误：'+JSON.stringify(errors)); if (errors.length) throw new Error('控制台错误');
  log('ALL CHECKS PASSED'); win.destroy(); app.quit();
}).catch(error=>{log(error.stack || String(error));app.exit(1);});
