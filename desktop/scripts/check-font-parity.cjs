/**
 * 字体注入页受控 UI 自检（不改动 check-ui / check-translation-parity）。
 *
 * 运行方式：
 * 1. 在 desktop 目录构建页面：`npm run build:renderer`
 * 2. 清除 ELECTRON_RUN_AS_NODE，以 Electron 主进程执行：
 *    `cd desktop && npx electron scripts/check-font-parity.cjs`
 * 3. 可选：RENPYBOX_UI_URL 指向开发服务器，RENPYBOX_UI_CAPTURE_DIR 保存证据
 *
 * mock HTTP/WS，不触真实游戏或付费 API。
 */
if (process.type !== 'browser') throw new Error('请使用 Electron 主进程运行，并先清除 ELECTRON_RUN_AS_NODE。');

const { app, BrowserWindow } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
app.setPath('userData', fs.mkdtempSync(path.join(require('node:os').tmpdir(), 'renpybox-font-profile-')));

const out = process.env.RENPYBOX_UI_CAPTURE_DIR || require('node:os').tmpdir();
const logPath = path.join(out, 'font-parity.log');
const pause = (ms) => new Promise((r) => setTimeout(r, ms));
const log = (value) => { fs.appendFileSync(logPath, value + '\n'); console.log(value); };

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
    fontProjectKey: 'c:\\ui-check|chinese',
    fontBoundKey: 'c:\\ui-check|chinese',
    fontManualKey: 'c:\\ui-check-manual|chinese',
    fontSerial: 0,
    fontJob: null,
    lastWriteJob: null,
    fontHoldScan: null,
    fontStatus: {
      project_key: 'c:\\ui-check|chinese',
      project_root: 'C:/ui-check',
      game_dir: 'C:/ui-check/game',
      languages: ['chinese', 'schinese'],
      font_refs: ['fonts/used.ttf', 'gui/DejaVu.ttf'],
      font_files: ['fonts/used.ttf', 'fonts/unused.otf'],
      font_ref_count: 2,
      font_file_count: 2,
      fonts_scanned: true,
      scan_stale: false,
    },
    lateScanTimer: null,
  };

  window.confirm = () => true;
  const response = (data) => new Response(JSON.stringify(data), { status: 200, headers: { 'Content-Type': 'application/json' } });

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

  const mkJob = (kind, body, resultExtra = {}) => {
    const id = 'font-parity-' + (f.fontSerial += 1);
    const key = String(body.project_key || f.fontProjectKey);
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
      result: {
        project_key: key,
        message: resultExtra.message || '模拟完成',
        worker_active: false,
        written: Boolean(resultExtra.written),
        partial: Boolean(resultExtra.partial),
        action: resultExtra.action || (kind === 'font_scan' ? 'scan' : kind === 'font_inject' ? 'inject' : 'replace'),
        ...resultExtra,
      },
    };
  };

  const statusFor = (searchParams) => {
    const gamePath = searchParams.get('game_path') || '';
    const manual = Boolean(gamePath && !gamePath.replace(/\\/g, '/').toLowerCase().includes('ui-check/game'));
    const key = manual ? f.fontManualKey : f.fontBoundKey;
    f.fontProjectKey = key;
    const base = {
      ...f.fontStatus,
      project_key: key,
      project_root: manual ? 'C:/ui-check-manual' : 'C:/ui-check',
      game_dir: manual ? 'C:/ui-check-manual/game' : (gamePath || 'C:/ui-check/game'),
      job: f.fontJob && f.fontJob.result?.project_key === key ? structuredClone(f.fontJob) : null,
      last_write_job: f.lastWriteJob && f.lastWriteJob.result?.project_key === key
        ? structuredClone(f.lastWriteJob)
        : null,
    };
    return base;
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
      if (f.translationFailuresRemaining > 0) {
        f.translationFailuresRemaining -= 1;
        f.translationFailures = (f.translationFailures || 0) + 1;
        return new Response(JSON.stringify({ detail: '模拟短暂状态读取失败' }), { status: 503 });
      }
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

    if (p === '/api/font-tools' && method === 'GET') {
      // 显式空 game_path → 400（与 API 一致，禁止静默 bound）
      if (parsed.searchParams.has('game_path') && !(parsed.searchParams.get('game_path') || '').trim()) {
        return new Response(JSON.stringify({ detail: '游戏目录不能为空' }), { status: 400 });
      }
      const payload = statusFor(parsed.searchParams);
      if (f.fontHoldScan) {
        const hold = f.fontHoldScan;
        f.fontHoldScan = null;
        return new Promise((resolve) => {
          f.releaseFontHold = () => resolve(response(payload));
          if (hold === 'auto') setTimeout(() => f.releaseFontHold?.(), 50);
        });
      }
      return response(payload);
    }

    if (p === '/api/font-tools/scan' && method === 'POST') {
      if (Object.prototype.hasOwnProperty.call(body, 'game_path') && !String(body.game_path || '').trim()) {
        return new Response(JSON.stringify({ detail: '游戏目录不能为空' }), { status: 400 });
      }
      if (body.project_key && body.project_key !== f.fontProjectKey && body.project_key !== f.fontBoundKey && body.project_key !== f.fontManualKey) {
        return new Response(JSON.stringify({ detail: '项目已切换，请重新加载后再操作' }), { status: 409 });
      }
      const key = String(body.project_key || f.fontProjectKey);
      f.fontProjectKey = key;
      const job = mkJob('font_scan', body, {
        action: 'scan',
        written: false,
        message: '扫描完成：检测到 2 个字体引用，发现 2 个字体文件，2 个翻译语言',
        font_refs: f.fontStatus.font_refs,
        font_files: f.fontStatus.font_files,
        font_ref_count: f.fontStatus.font_ref_count,
        font_file_count: f.fontStatus.font_file_count,
        languages: f.fontStatus.languages,
        lang_count: f.fontStatus.languages.length,
      });
      // 零引用扫描场景
      if (f.forceZeroScan) {
        job.result.font_refs = [];
        job.result.font_files = [];
        job.result.font_ref_count = 0;
        job.result.font_file_count = 0;
        job.result.message = '扫描完成：检测到 0 个字体引用，发现 0 个字体文件，2 个翻译语言';
        f.fontStatus.font_refs = [];
        f.fontStatus.font_files = [];
        f.fontStatus.font_ref_count = 0;
        f.fontStatus.font_file_count = 0;
      }
      f.fontStatus.fonts_scanned = true;
      f.fontStatus.scan_stale = false;
      f.fontJob = job;
      // 可控的真实生命周期：提交时持有 TESTING，工作线程退出后才释放。
      if (f.holdEngineScan) {
        f.holdEngineScan = false;
        job.status = 'running';
        job.done = 0;
        job.progress = 0;
        job.result.worker_active = true;
        f.engineStatus = 'TESTING';
        f.finishEngineScan = (status = 'done', emit = true) => {
          job.status = status;
          job.done = status === 'done' ? 1 : 0;
          job.progress = job.done;
          job.result.worker_active = false;
          f.engineStatus = 'IDLE';
          if (emit) f.sockets.forEach((socket) => socket.onmessage?.({ data: JSON.stringify({ type: 'job', job }) }));
        };
        return response({ job });
      }
      // 晚到结果：先返回 running，稍后变为 done（验证手动目标上下文）
      if (f.deferScanDone) {
        job.status = 'running';
        job.done = 0;
        job.progress = 0;
        job.result.worker_active = true;
        job.result.message = '扫描中';
        const deferred = structuredClone(job);
        setTimeout(() => {
          deferred.status = 'done';
          deferred.done = 1;
          deferred.progress = 1;
          deferred.result.worker_active = false;
          deferred.result.message = job.result.message;
          f.fontJob = deferred;
          f.sockets.forEach((socket) => socket.onmessage?.({ data: JSON.stringify({ type: 'job', job: deferred }) }));
        }, 120);
        f.deferScanDone = false;
        return response({ job });
      }
      return response({ job });
    }

    if (p === '/api/font-tools/inject' && method === 'POST') {
      if (!body.confirm) return new Response(JSON.stringify({ detail: '写入字体包需要 confirm=true' }), { status: 400 });
      if (Object.prototype.hasOwnProperty.call(body, 'game_path') && !String(body.game_path || '').trim()) {
        return new Response(JSON.stringify({ detail: '游戏目录不能为空' }), { status: 400 });
      }
      const job = mkJob('font_inject', body, {
        action: 'inject',
        written: true,
        message: '字体包已注入 tl/chinese。',
        language: body.language || 'chinese',
        backup_path: 'C:/ui-check/game/fonts_backup/inject_demo',
        base_box: 'C:/ui-check/game/tl/chinese/base_box',
        gui_hook: body.generate_gui_hook ? true : null,
      });
      f.fontJob = job;
      f.lastWriteJob = structuredClone(job);
      f.fontStatus.scan_stale = true;
      f.fontStatus.fonts_scanned = false;
      f.fontStatus.font_refs = [];
      f.fontStatus.font_ref_count = 0;
      return response({ job });
    }

    if (p === '/api/font-tools/replace' && method === 'POST') {
      if (!body.confirm) return new Response(JSON.stringify({ detail: '替换字体会修改脚本，需要 confirm=true' }), { status: 400 });
      if (Object.prototype.hasOwnProperty.call(body, 'game_path') && !String(body.game_path || '').trim()) {
        return new Response(JSON.stringify({ detail: '游戏目录不能为空' }), { status: 400 });
      }
      const partial = Boolean(f.forceReplacePartial);
      const job = mkJob('font_replace', body, {
        action: 'replace',
        written: true,
        partial,
        message: partial ? '部分文件写入失败' : '字体替换完成：修改 1 个文件，共 2 处',
        replaced_files: 1,
        replaced_count: 2,
        failed_files: partial ? ['extra.rpy'] : [],
        backup_path: body.create_backup === false ? null : 'C:/ui-check/game/fonts_backup/backup_demo',
        backup_name: body.create_backup === false ? '' : 'backup_demo',
      });
      f.fontJob = job;
      f.lastWriteJob = structuredClone(job);
      f.fontStatus.scan_stale = true;
      f.fontStatus.fonts_scanned = false;
      f.forceReplacePartial = false;
      return response({ job });
    }

    if (/^\/api\/jobs\/font-parity-\d+\/cancel$/.test(p)) {
      if (f.fontJob) {
        f.fontJob.cancel_requested = true;
        f.fontJob.result.message = '正在取消…';
      }
      return response(f.fontJob || { ok: true });
    }
    if (p === '/api/jobs') return response({ jobs: [f.fontJob].filter(Boolean) });

    throw new Error('font parity 未定义接口：' + method + ' ' + p + qs);
  };

  const NativeSocket = WebSocket;
  window.WebSocket = class {
    constructor(url) {
      if (!String(url).endsWith('/ws')) return new NativeSocket(url);
      this.readyState = 1;
      f.sockets.push(this);
      setTimeout(() => this.onopen?.({}), 0);
    }
    close() {
      this.readyState = 3;
      this.onclose?.({});
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
    if (severity === 'error' || severity >= 3) {
      errors.push(value);
      log('CONSOLE ' + value);
    }
  });

  await win.loadURL('about:blank');
  win.webContents.debugger.attach('1.3');
  await win.webContents.debugger.sendCommand('Page.enable');
  await win.webContents.debugger.sendCommand('Runtime.enable');
  await win.webContents.debugger.sendCommand('Page.addScriptToEvaluateOnNewDocument', {
    source: '(' + fixture.toString() + ')()',
  });
  if (process.env.RENPYBOX_UI_URL) await win.loadURL(process.env.RENPYBOX_UI_URL);
  else await win.loadFile(path.join(__dirname, '../dist/index.html'));

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
    for (let attempt = 0; attempt < 40; attempt++) {
      if (await js(`Boolean(${expression})`)) {
        log('PASS ' + name);
        return;
      }
      await pause(140);
    }
    log('FAIL CONTEXT ' + JSON.stringify(await js(`({
      page: document.querySelector('.content')?.dataset.page,
      toolPage: document.querySelector('[data-rb-page]')?.getAttribute('data-rb-page'),
      writes: __uiFixture.writes.slice(-6),
      text: document.querySelector('[data-rb-page=font-replace]')?.innerText?.slice(0,400)
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
    await win.webContents.debugger.sendCommand('Input.dispatchMouseEvent', {
      type: 'mousePressed', ...position, button: 'left', clickCount: 1,
    });
    await win.webContents.debugger.sendCommand('Input.dispatchMouseEvent', {
      type: 'mouseReleased', ...position, button: 'left', clickCount: 1,
    });
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
    await pause(100);
  };

  const capture = async (name) => {
    const result = await win.webContents.debugger.sendCommand('Page.captureScreenshot');
    fs.writeFileSync(path.join(out, name + '.png'), Buffer.from(result.data, 'base64'));
    log('CAPTURE ' + name);
  };

  const openFontPage = async () => {
    await page("Ren'Py 工具箱");
    await pause(180);
    await input('.toolbox-search', '字体注入');
    await pause(160);
    await js('document.querySelector(".tool-card")?.click()');
    await pause(280);
    await assert("document.querySelector('[data-rb-page=font-replace]')", '进入字体注入页');
  };

  const clearWrites = async () => {
    await js('__uiFixture.writes.length=0');
  };

  // —— 基础注入不自动扫描；显式扫描仍持有引擎并正常收尾 ——
  await assert("document.querySelector('.workspace-project').title==='C:/ui-check'", 'fixture 已绑定项目');
  await js('__uiFixture.holdEngineScan = true');
  await openFontPage();
  await assert("document.querySelector('[data-rb-font-game-dir]')", '游戏目录可编辑输入');
  await assert("!__uiFixture.writes.some(w=>w.p==='/api/font-tools/scan') && __uiFixture.engineStatus==='IDLE'", '打开基础注入页不触发扫描或占用引擎');
  await assert("[...document.querySelectorAll('button')].some(b=>b.textContent.replaceAll(' ','')==='一键注入字体' && !b.disabled)", '基础注入无需等待字体扫描');
  await click('重新扫描字体');
  await assert("__uiFixture.writes.some(w=>w.p==='/api/font-tools/scan')", '手动扫描已触发');
  await assert("__uiFixture.engineStatus==='TESTING' && [...document.querySelectorAll('button')].some(b=>b.textContent.replaceAll(' ','')==='一键注入字体' && b.disabled)", '扫描占用引擎时禁止写入');
  await js('__uiFixture.translationFailuresRemaining = 1; __uiFixture.finishEngineScan("done", false)');
  await assert("[...document.querySelectorAll('button')].some(b=>b.textContent.replaceAll(' ','')==='一键注入字体' && !b.disabled)", '只读扫描完成后恢复可操作状态');
  await assert('__uiFixture.translationFailures === 1', '终态状态读取短暂失败后自动重试');

  // 高级折叠 + 确认检测计数 + 打开字体下拉（同一次确保面板仍挂载）
  await js(`(()=>{
    const header=[...document.querySelectorAll('.ant-collapse-header')].find(e=>e.textContent.includes('高级选项'));
    if(!header) throw new Error('缺少高级选项');
    if(!document.querySelector('.ant-collapse-item-active')) header.click();
  })()`);
  await pause(220);
  await assert("document.querySelector('[data-rb-font-refs-files]')", '高级区显示 refs/files 计数');
  await assert(
    "document.querySelector('[data-rb-font-refs-files]')?.textContent?.includes('2')",
    '检测 refs/files 数为 2',
  );
  await assert("document.querySelector('.rb-font-detected-select')", '检测字体下拉已挂载');

  // 选择下拉实际 POST（替换）
  await clearWrites();
  const selectPos = await js(`(()=>{
    if(!document.querySelector('.ant-collapse-item-active')){
      [...document.querySelectorAll('.ant-collapse-header')].find(e=>e.textContent.includes('高级选项'))?.click();
    }
    const root=document.querySelector('.rb-font-detected-select');
    // antd 6: .ant-select-content；旧版: .ant-select-selector
    const selector=root?.querySelector('.ant-select-content, .ant-select-selector') || root;
    if(!selector) throw new Error('缺少字体下拉 .rb-font-detected-select');
    selector.scrollIntoView({block:'center'});
    const r=selector.getBoundingClientRect();
    return {x:r.left+r.width/2,y:r.top+r.height/2};
  })()`);
  await win.webContents.debugger.sendCommand('Input.dispatchMouseEvent', {
    type: 'mousePressed', ...selectPos, button: 'left', clickCount: 1,
  });
  await win.webContents.debugger.sendCommand('Input.dispatchMouseEvent', {
    type: 'mouseReleased', ...selectPos, button: 'left', clickCount: 1,
  });
  await pause(300);
  const optPos = await js(`(()=>{
    const opt=[...document.querySelectorAll('.ant-select-item-option')].find(e=>e.textContent.includes('gui/DejaVu.ttf'));
    if(!opt) throw new Error('缺少 DejaVu 选项:'+[...document.querySelectorAll('.ant-select-item-option')].map(e=>e.textContent.trim()).join('|'));
    opt.scrollIntoView({block:'nearest'});
    const r=opt.getBoundingClientRect();
    return {x:r.left+r.width/2,y:r.top+r.height/2};
  })()`);
  await win.webContents.debugger.sendCommand('Input.dispatchMouseEvent', {
    type: 'mousePressed', ...optPos, button: 'left', clickCount: 1,
  });
  await win.webContents.debugger.sendCommand('Input.dispatchMouseEvent', {
    type: 'mouseReleased', ...optPos, button: 'left', clickCount: 1,
  });
  await pause(200);
  await assert(
    "document.querySelector('.rb-font-detected-select')?.textContent?.includes('DejaVu')",
    '下拉已选中 DejaVu',
  );
  await click('一键替换字体');
  await click('一键替换字体'); // 确认对话框
  await assert(
    "__uiFixture.writes.some(w=>w.p==='/api/font-tools/replace'&&w.body.selected_font==='gui/DejaVu.ttf'&&w.body.create_backup===true&&w.body.replace_all===false)",
    '替换 POST：选中下拉 + backupTrue + replaceAllFalse',
  );
  await assert(
    "!__uiFixture.writes.some(w=>w.p==='/api/font-tools/replace'&&w.body.replace_all===true)",
    '替换未带 replace_all=true',
  );
  await assert("document.querySelector('[data-rb-font-write-report]')", '写入报告可见');
  await assert("document.querySelector('[data-rb-font-backup]')", '备份路径可见');

  // 写报告不被 autoScan 抹掉：模拟重扫后 last_write_job 仍在
  await clearWrites();
  await click('重新扫描字体');
  await assert("__uiFixture.writes.some(w=>w.p==='/api/font-tools/scan')", '手动重扫');
  await assert("document.querySelector('[data-rb-font-write-report]')", '重扫后写报告仍保留');
  await assert("document.querySelector('[data-rb-font-replace-result]')", '替换计数仍可见');

  // scan zero
  await js('__uiFixture.forceZeroScan=true');
  await clearWrites();
  await click('重新扫描字体');
  await pause(300);
  await assert(
    "document.querySelector('[data-rb-font-refs-files]')?.textContent?.includes('0')",
    '零引用扫描显示 0',
  );
  await js('__uiFixture.forceZeroScan=false; __uiFixture.fontStatus.font_refs=["fonts/used.ttf"]; __uiFixture.fontStatus.font_ref_count=1; __uiFixture.fontStatus.font_files=["fonts/used.ttf"]; __uiFixture.fontStatus.font_file_count=1;');

  // 手动 game 目标 + 上下文晚到结果
  await js('__uiFixture.deferScanDone=true');
  await clearWrites();
  await input('[data-rb-font-game-dir]', 'C:/ui-check-manual/game');
  await pause(400);
  await assert(
    "__uiFixture.writes.some(w=>w.p==='/api/font-tools/scan'&&String(w.body.game_path||'').includes('ui-check-manual'))",
    '手动目标 scan 带 game_path',
  );
  await assert(
    "__uiFixture.reads.some(r=>r.includes('game_path=')&&r.includes('ui-check-manual'))",
    'status GET 带手动 game_path',
  );
  await pause(250);
  await assert("document.querySelector('[data-rb-page=font-replace]')", '晚到扫描后页面仍稳定');

  // 失败 partial + 备份路径
  await input('[data-rb-font-game-dir]', 'C:/ui-check/game');
  await pause(350);
  await js('__uiFixture.forceReplacePartial=true; __uiFixture.fontStatus.font_refs=["fonts/used.ttf"]; __uiFixture.fontStatus.font_ref_count=1;');
  await js(`(()=>{
    const open=document.querySelector('.ant-collapse-item-active');
    if(!open){
      const btn=[...document.querySelectorAll('button,.ant-collapse-header')].find(e=>e.textContent.includes('高级选项'));
      btn?.click();
    }
  })()`);
  await pause(160);
  await clearWrites();
  await click('一键替换字体');
  await click('一键替换字体');
  await assert(
    "__uiFixture.writes.some(w=>w.p==='/api/font-tools/replace'&&w.body.create_backup===true)",
    'partial 替换已提交且 backupTrue',
  );
  await assert("document.querySelector('[data-rb-font-write-report]')", 'partial 写报告可见');
  await assert("document.querySelector('[data-rb-font-backup]')", 'partial 备份路径可见');

  // 注入默认：gui false（确认框路径）
  // 根因：partial 写入后 FontReplacePage 会自动 rescan；若此时 busy/pending，
  // suite.submit 会静默丢弃 inject。另 AntD Modal 挂载后 height 可能仍为 0，
  // 通用 click 会退回 document 再次点开按钮而不是点确认。须等空闲与可见 dialog。
  await assert(
    `[...document.querySelectorAll('button')].some(b=>{
      const t=b.textContent.split(' ').join('');
      return t==='一键注入字体'&&!b.disabled;
    }) && !(__uiFixture.fontJob && (__uiFixture.fontJob.status==='pending'||__uiFixture.fontJob.status==='running'||__uiFixture.fontJob.result?.worker_active))`,
    '注入前空闲且按钮可点',
  );
  await clearWrites();
  await click('一键注入字体');
  await assert(
    `[...document.querySelectorAll('[role=dialog]')].some(d=>{
      const r=d.getBoundingClientRect();
      if(r.height<=0||r.width<=0) return false;
      return [...d.querySelectorAll('button')].some(b=>{
        const t=b.textContent.split(' ').join('');
        return t==='一键注入字体'&&!b.disabled;
      });
    })`,
    '注入确认框可见且确认可点',
  );
  await click('一键注入字体');
  await assert(
    "__uiFixture.writes.some(w=>w.p==='/api/font-tools/inject'&&w.body.generate_gui_hook===false)",
    '注入默认 guiFalse',
  );

  // 空 game 输入：禁用写操作、提示可见、无静默 bound inject/replace/scan
  await clearWrites();
  await js('__uiFixture.reads.length=0');
  await input('[data-rb-font-game-dir]', '');
  await pause(450);
  await assert("document.querySelector('[data-rb-font-game-empty]')", '空目录提示可见');
  await assert(
    "document.querySelector('[data-rb-font-game-empty]')?.textContent?.includes('请先选择')||document.querySelector('[data-rb-font-game-empty]')?.textContent?.includes('Select the game')",
    '空目录中英提示文案',
  );
  await assert(
    "[...document.querySelectorAll('button')].some(b=>b.textContent.includes('一键注入')&&b.disabled)",
    '空目录禁用注入',
  );
  await assert(
    "[...document.querySelectorAll('button')].some(b=>b.textContent.includes('重新扫描')&&b.disabled)",
    '空目录禁用重扫',
  );
  await js(`(()=>{
    const open=document.querySelector('.ant-collapse-item-active');
    if(!open){
      [...document.querySelectorAll('.ant-collapse-header')].find(e=>e.textContent.includes('高级选项'))?.click();
    }
  })()`);
  await pause(160);
  await assert(
    "[...document.querySelectorAll('button')].some(b=>b.textContent.includes('一键替换')&&b.disabled)",
    '空目录禁用替换',
  );
  await assert(
    "!__uiFixture.writes.some(w=>w.p==='/api/font-tools/inject'||w.p==='/api/font-tools/replace')",
    '空目录无 inject/replace 请求',
  );
  await assert(
    "!__uiFixture.writes.some(w=>w.p==='/api/font-tools/scan')",
    '空目录无自动/手动 scan bound',
  );
  // 恢复有效路径后可重新扫描
  await clearWrites();
  await input('[data-rb-font-game-dir]', 'C:/ui-check/game');
  await pause(500);
  await assert("__uiFixture.writes.some(w=>w.p==='/api/font-tools/scan')", '恢复路径后可扫描');
  await assert("!document.querySelector('[data-rb-font-game-empty]')", '恢复后空目录提示消失');

  // 扫描中离开工具页：由应用级同步收尾，不能依赖已卸载的页面 hook。
  for (const outcome of ['done', 'failed', 'cancelled']) {
    await page('翻译任务');
    await js('__uiFixture.holdEngineScan = true');
    await openFontPage();
    await click('重新扫描字体');
    await assert("__uiFixture.engineStatus==='TESTING' && __uiFixture.fontJob?.status==='running'", `${outcome}：扫描正在运行`);
    await page('翻译任务');
    await assert("[...document.querySelectorAll('button')].some(b=>b.textContent.replaceAll(' ','')==='开始翻译' && b.disabled)", `${outcome}：运行期间全局禁用`);
    await js(`__uiFixture.translationFailuresRemaining = 1; __uiFixture.finishEngineScan(${JSON.stringify(outcome)}, ${outcome !== 'cancelled'})`);
    await assert("[...document.querySelectorAll('button')].some(b=>b.textContent.replaceAll(' ','')==='开始翻译' && !b.disabled)", `${outcome}：离开页面后恢复全局操作`);
  }
  await openFontPage();
  await assert("[...document.querySelectorAll('button')].some(b=>b.textContent.replaceAll(' ','')==='一键注入字体' && !b.disabled)", '返回字体页仍可注入');
  // 基础注入后首次展开高级区：首次扫描与写后重扫必须合并成一个请求。
  await js('__uiFixture.holdEngineScan = false');
  await clearWrites();
  await click('一键注入字体');
  await assert(
    `[...document.querySelectorAll('[role=dialog]')].some(d=>d.getBoundingClientRect().height>0)`,
    '基础注入确认框已打开',
  );
  await click('一键注入字体');
  await assert("__uiFixture.writes.some(w=>w.p==='/api/font-tools/inject')", '基础注入已提交');
  await pause(1700);
  await assert("!__uiFixture.writes.some(w=>w.p==='/api/font-tools/scan')", '基础注入完成后不自动扫描');
  await clearWrites();
  await js(`document.querySelector('.ant-collapse-header')?.click()`);
  await assert("__uiFixture.writes.some(w=>w.p==='/api/font-tools/scan')", '注入后首次展开高级区触发扫描');
  await pause(1700);
  await assert("__uiFixture.writes.filter(w=>w.p==='/api/font-tools/scan').length===1", '首次扫描与写后重扫合并为一次请求');
  await assert("document.querySelector('[data-rb-font-write-report]')", '合并扫描后注入报告仍保留');
  await capture('font-parity-desktop');

  // 窄屏
  await win.webContents.debugger.sendCommand('Emulation.setDeviceMetricsOverride', {
    width: 680,
    height: 800,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await capture('font-parity-680');
  await win.webContents.debugger.sendCommand('Emulation.clearDeviceMetricsOverride');

  if (errors.length) throw new Error('控制台错误：' + JSON.stringify(errors));
  log('ALL FONT PARITY CHECKS PASSED');
  win.destroy();
  app.quit();
}).catch((error) => {
  log(error.stack || String(error));
  app.exit(1);
});
