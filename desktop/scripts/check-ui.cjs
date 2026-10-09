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
  f.reads = []; f.confirmed = [];
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
    if (p === '/api/settings') { if (method === 'PATCH') Object.assign(values, body.values); return response({ values, masked: [] }); }
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
    if (p === '/api/project') return response({ renpy_project_path: 'C:/ui-check', renpy_game_folder: 'C:/ui-check/game', renpy_tl_folder: values.input_folder });
    if (p === '/api/translation/state') return response({ engine_status: 'IDLE', stop_barrier: false, single_tasks: false, request_id: 'fixture', run_id: 1, running: { running: 0, max: 4 }, progress: { line: 64, total_line: 100, time: 120, total_output_tokens: 4800, throughput: { schema_version: 1, elapsed_seconds: 120, output_tokens: 4800, effective_items_per_minute: 32 } }, active_output_folder: values.output_folder });
    if (p === '/api/settings/prompt-preview') return response({ base: '将对白翻译为自然中文，保留人物语气。', style: '语言克制。', fixed: '保持变量和输出协议。' });
    if (p === '/api/workbench') { if (method === 'PATCH') Object.assign(f.assets, body, { revision: f.assets.revision + 1 }); return response(f.assets); }
    if (p === '/api/workbench/glossary') { if (method === 'PATCH') Object.assign(f.glossary, body, { revision: f.glossary.revision + 1 }); return response(f.glossary); }
    if (p === '/api/proofreading') return response({ cache_token: 'fixture-cache', cache_folder: values.output_folder, total: 1, matched: 1, page: 1, limit: 50, files: ['chapter_01.rpy'], readonly: false, items: f.items });
    if (p === '/api/proofreading/item') { f.items[0].dst = body.dst; return response({ ok: true }); }
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
  const js = code => win.webContents.executeJavaScript(code);
  for (let i = 0; i < 50; i++) { if (await js("!!document.querySelector('.translation-layout')")) break; await pause(100); }
  const assert = async (expression, name) => { if (!await js(expression)) throw new Error('FAIL ' + name); log('PASS ' + name); };
  const click = async text => { await js(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()===${JSON.stringify(text)})?.click()`); await pause(120); };
  const page = async title => { await js(`Array.from(document.querySelectorAll('.nav-item')).find(b=>b.title===${JSON.stringify(title)})?.click()`); await pause(180); };
  const input = async (selector, value) => { await js(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});Object.getOwnPropertyDescriptor(e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype,'value').set.call(e,${JSON.stringify(value)});e.dispatchEvent(new Event('input',{bubbles:true}));})()`); await pause(80); };
  const capture = async name => { await js("document.querySelectorAll('.banner button').forEach(b=>{if(b.textContent.trim()==='知道了')b.click()})"); await js("document.querySelectorAll('[data-rb-toast] button[aria-label=\"知道了\"]').forEach(b=>b.click())"); await pause(240); const result = await win.webContents.debugger.sendCommand('Page.captureScreenshot'); fs.writeFileSync(path.join(out, name + '.png'), Buffer.from(result.data, 'base64')); };
  const SAMPLE_PAGES = [['翻译任务','translation'],['基础设置','basic'],['项目设置','project'],['术语表','glossary']];
  const captureSamples = async prefix => {
    for (const [title, key] of SAMPLE_PAGES) {
      await page(title);
      if (key === 'glossary') { await js("document.querySelector('.rb-term-row')?.click()"); await pause(160); }
      await capture(`${prefix}-${key}`);
    }
    await page('翻译任务');
  };
  const waitLayout = async () => { for (let i = 0; i < 50; i++) { if (await js("!!document.querySelector('.translation-layout')")) return; await pause(100); } };
  const setProgress = async progress => { await js(`__uiFixture.sockets.at(-1).onmessage({data:JSON.stringify({type:'event',event:'TRANSLATION_UPDATE',data:${JSON.stringify(progress)}})})`); await pause(100); };
  await assert("document.querySelector('.rb-progress-percent').textContent.includes('64.0%')", '翻译快照');
  await assert("document.querySelectorAll('.nav-group-label').length===4", '导航工作流分组');
  await assert("document.querySelector('.workspace-link').getAttribute('aria-label')==='后端已连接'", '全局连接状态');
  await assert("document.querySelector('.task-input').textContent.trim()===__uiFixture.values.input_folder && document.querySelector('.workspace-project').title==='C:/ui-check'", '项目身份与翻译输入目录分开展示');
  await assert("document.querySelector('.task-platform').textContent.includes('主翻译接口') && document.querySelector('.task-language-pair').textContent.includes('EN') && document.querySelector('.task-language-pair').textContent.includes('ZH')", '当前接口与语言上下文');
  await assert("document.querySelector('.task-state').textContent==='可继续'", '已暂停任务状态');
  await setProgress({line:100,total_line:100,failed_line_count:1});
  await assert("document.querySelector('.task-state').textContent==='可继续' && document.querySelector('.task-state').dataset.warning==='true'", '失败条目不误报完成');
  await setProgress({failed_line_count:0});
  await assert("document.querySelector('.task-state').textContent==='已完成'", '任务完成状态');
  await setProgress({line:0,total_line:0});
  await assert("document.querySelector('.task-state').textContent==='待开始' && !document.querySelector('.rb-failed-badge')", '空任务不显示虚假健康状态');
  await setProgress({line:64,total_line:100});
  await capture('new-ui-translation-dark');
  await captureSamples('p1-dark-1280');
  await js("document.querySelector('.task-input').click()"); await pause(180);
  await assert("document.querySelector('.content').dataset.page==='project' && document.querySelector('.content h1').textContent==='项目设置'", '输入目录快捷入口');
  await page('翻译任务'); await js("document.querySelector('.task-platform').click()"); await pause(180);
  await assert("document.querySelector('.content').dataset.page==='platform'", '翻译接口快捷入口');
  await page('接口管理'); await capture('new-ui-platform-dark');
  await click('新增接口'); await capture('new-ui-platform-editor-dark');
  await input('.platform-editor input', '自检接口'); await input('.platform-editor input[placeholder^=服务商]', 'story-model'); await input('.platform-editor input[type=url]', 'https://api.example.com/v1'); await click('保存接口');
  await assert("__uiFixture.values.platforms.some(p=>p.name==='自检接口')", '接口编辑表单提交');
  await assert("!('api_keys' in __uiFixture.writes.at(-1).body)", '空密钥不覆盖凭据');
  await page('角色 / 世界观工作台'); await click('世界观');
  await input('.workbench-form-grid input', '港湾来信 · 新篇'); await click('保存修改');
  await assert("__uiFixture.assets.worldbook.project_name==='港湾来信 · 新篇'", '世界观保存');
  await click('角色卡'); await capture('new-ui-characters-dark');
  await page('术语表'); await js("document.querySelector('.rb-term-row')?.click()"); await pause(120);
  await input('.rb-term-editor textarea', 'Harbor Town');
  await js("document.querySelector('.workspace-project').click()"); await pause(180);
  await assert("!!document.querySelector('[role=dialog]') && !!document.querySelector('.glossary-layout')", '切页保护编辑');
  await click('取消'); await click('保存到项目');
  await assert("__uiFixture.glossary.rows[0].src==='Harbor Town'", '词库提交');
  await page('平行校对台'); await click('艾丽丝，那封信今天早上到了。'); await pause(100);
  await input('#proofreading-draft', '艾丽丝，那封信今早到了。'); await click('保存译文');
  await assert("__uiFixture.items[0].dst==='艾丽丝，那封信今早到了。' && !document.querySelector('[role=dialog]')", '校对保存');
  await capture('new-ui-proofreading-dark');
  await page('翻译提示'); await click('查看当前提示词');
  await assert("document.querySelector('.prompt-preview-text').value.includes('自然中文')", '静态提示词预览');
  await js("document.querySelector('.dialog').dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))"); await pause(100);
  await assert("!document.querySelector('[role=dialog]')", 'Escape 关闭');
  await page("Ren'Py 工具箱"); await input('.toolbox-search', '术语');
  await assert("document.querySelectorAll('.tool-card').length===1", '工具搜索不重复');
  await js("document.querySelector('.tool-card').click()"); await pause(180);
  await assert("!!document.querySelector('.glossary-layout')", '工具词库入口');
  await page('Agent 助手');
  await assert("!!document.querySelector('.agent-composer textarea') && !document.querySelector('.agent-empty').textContent.includes('暂不可用')", 'Agent 工作区已替换占位页');
  await js("document.querySelector('.agent-suggestion').click(); const select=document.querySelector('[aria-label=\"Agent 思考等级\"]'); select.value='HIGH'; select.dispatchEvent(new Event('change',{bubbles:true}));"); await pause(100);
  await click('发送');
  await assert("__uiFixture.writes.at(-1).p==='/api/agent/message' && __uiFixture.writes.at(-1).body.thinking_level==='HIGH' && document.querySelectorAll('.agent-message').length===2", 'Agent 发送实际请求与思考覆盖项');
  await js("__uiFixture.agent.messages.at(-1).content='找到 2 个资源包。'; __uiFixture.agent.messages.at(-1).tools=[{name:'list_rpa_files',status:'done',message:'找到 2 个资源包'}]; __uiFixture.emitAgent();"); await pause(220);
  await assert("document.querySelector('.agent-message-body').textContent.includes('找到 2 个资源包') && !!document.querySelector('.agent-tool')", 'Agent 流式快照与工具反馈');
  await page('翻译任务'); await page('Agent 助手');
  await assert("document.querySelectorAll('.agent-message').length===2 && Array.from(document.querySelectorAll('button')).some(button=>button.textContent.trim()==='停止')", 'Agent 切页恢复正在运行的会话');
  await click('停止');
  await assert("__uiFixture.writes.at(-1).p==='/api/agent/stop' && document.querySelector('.agent-chat').textContent.includes('已停止')", 'Agent 停止请求');
  await click('新建会话'); await click('清空并新建');
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
  await js("document.querySelector('[title=\"切换主题\"]').click()"); await pause(200); await captureSamples('p1-light-1280'); await capture('new-ui-glossary-light');
  await page('Agent 助手'); await capture('new-ui-agent-light');
  await page('翻译任务'); await capture('new-ui-translation-light');
  const labels = ['翻译任务','平行校对台','项目设置','接口管理',"Ren'Py 工具箱",'术语表','禁翻表','称呼桥接','角色 / 世界观工作台','翻译提示','Agent 助手','基础设置','应用设置'];
  for (const [width,height] of [[680,800],[900,640],[1000,640],[1280,800],[1920,1080]]) {
    await win.webContents.debugger.sendCommand('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
    for (const title of labels) {
      await page(title);
      const data = await js(`({root:document.documentElement.scrollWidth>innerWidth,panels:Array.from(document.querySelectorAll('.content,.workspace-bar,.task-context,.settings-header,.workbench-header,.translation-footer,.rb-command-bar,.rb-sheet,.platform-toolbar,.agent-topbar,.agent-controls,.agent-composer,.agent-confirmation,.rb-titlebar')).filter(e=>e.scrollWidth>e.clientWidth+1).map(e=>e.className),controls:Array.from(document.querySelectorAll('button,input,select,textarea')).filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&(r.left<0||r.right>innerWidth+1)}).map(e=>e.getAttribute('aria-label')||e.textContent.trim())})`);
      log('LAYOUT '+width+' '+title+' '+JSON.stringify(data));
      if (data.root || data.panels.length || data.controls.length) throw new Error('布局越界：'+width+' '+title+' '+JSON.stringify(data));
    }
    await assert("document.querySelector('.sidebar-footer').getBoundingClientRect().bottom<=innerHeight", '侧栏底部入口可见 '+width);
    if (width === 1280) {
      await assert("(()=>{const e=document.querySelector('.sidebar-navigation');return !!e && e.scrollHeight<=e.clientHeight})()", '侧栏不需要滚动');
      await page('翻译任务');
      await assert("document.querySelector('.content h1').getBoundingClientRect().top<=64", '翻译标题起点');
    }
    if (width === 680) { await page('平行校对台'); await capture('new-ui-proofreading-680'); }
    if (width === 900) await captureSamples('p1-light-900');
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
  log('控制台错误：'+JSON.stringify(errors)); if (errors.length) throw new Error('控制台错误');
  log('ALL CHECKS PASSED'); win.destroy(); app.quit();
}).catch(error=>{log(error.stack || String(error));app.exit(1);});
