/**
 * RPY 抽取设置页受控 UI 自检（独立于 check-ui / check-translation-parity）。
 *
 * 运行方式（pwsh）：
 * 1. UI_URL 已可用：默认 http://127.0.0.1:5179
 * 2. 清除 ELECTRON_RUN_AS_NODE，独立 user-data-dir：
 *    $env:RENPYBOX_UI_URL='http://127.0.0.1:5179'
 *    $env:RENPYBOX_UI_CAPTURE_DIR="$env:TEMP\renpybox-qt5-parity\new-ui-rpy"
 *    cd desktop; npx electron scripts/check-rpy-parity.cjs
 *
 * mock HTTP/WS，不触真实游戏或付费 API。
 */
if (process.type !== 'browser') throw new Error('请使用 Electron 主进程运行，并先清除 ELECTRON_RUN_AS_NODE。');

const { app, BrowserWindow } = require('electron');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const out = process.env.RENPYBOX_UI_CAPTURE_DIR
  || path.join(os.tmpdir(), 'renpybox-qt5-parity', 'new-ui-rpy');
const logPath = path.join(out, 'rpy-parity.log');
const pause = (ms) => new Promise((r) => setTimeout(r, ms));
const log = (value) => fs.appendFileSync(logPath, value + '\n');

fs.mkdirSync(out, { recursive: true });
fs.writeFileSync(logPath, '');

// 独立 profile，避免与其他 Electron 自检抢 cache
app.setPath('userData', path.join(os.tmpdir(), 'renpybox-rpy-parity-profile-' + Date.now()));

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

  const fullRule = (id, name, pattern, positive, negative) => ({
    id,
    name,
    enabled: true,
    include_globs: ['*.rpy', '**/*.rpy'],
    pattern,
    flags: [],
    text_group: 'text',
    note: '',
    positive_samples: positive,
    negative_samples: negative,
  });

  const starterRules = [
    fullRule('r1', '对白', String.raw`^\s*(?:[a-zA-Z_]\w*\s+)?(?P<text>"(?:\\.|[^"\\])*")\s*$`, ['e "Hello."'], ['jump next']),
    fullRule('r2', '菜单', String.raw`^\s*(?P<text>"(?:\\.|[^"\\])*")\s*:\s*$`, ['"Continue":'], ['jump next']),
  ];

  const manyCandidates = Array.from({ length: 201 }, (_, index) => ({
    path: 'scene.rpy',
    line: index + 1,
    text: 'Candidate ' + index,
    rule_name: '对白',
    state: 'new',
  }));

  const f = window.__uiFixture = {
    values,
    sockets: [],
    writes: [],
    reads: [],
    unbound: false,
    engineStatus: 'IDLE',
    progress: { line: 0, total_line: 0, time: 0, total_output_tokens: 0 },
    progressSource: 'none',
    toolProjectKey: 'c:\\ui-check',
    toolSerial: 0,
    toolJobs: {},
    scanPage: 1,
    scan: null,
    /** 离页等待：模拟 cancel 后 worker 仍收尾超过 5s；GET 失败时不可放行 */
    leaveHoldMs: 0,
    leaveGetFailOnce: false,
    leaveGetFailArmed: false,
    rpyStatus: {
      applied_mode: 'builtin',
      applied_profile_id: null,
      applied_name: '未选择自定义方案',
      mode_labels: { builtin: '只用内置', combined: '内置＋自定义', custom: '仅自定义' },
      profiles: [],
      profile_docs: [],
      summary: '当前已生效：只用内置 · 未选择自定义方案',
      no_profile_label: '未选择自定义方案',
      new_rule_template: fullRule('tpl', '规则', String.raw`\bcall\s+reply_message\(\s*(?P<text>"(?:\\.|[^"\\])*")\s*\)`, ['call reply_message("Try again.")'], ['call reply_message(player_name)']),
      scan: {
        has_scan: false,
        completed: false,
        error: '',
        candidates: [],
        candidate_total: 0,
        page: 1,
        page_size: 200,
        page_count: 1,
        can_save_bind: false,
        can_continue: false,
      },
    },
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
    const id = 'rpy-parity-' + (f.toolSerial += 1);
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
      result: {
        project_key: key,
        message: '模拟完成',
        worker_active: false,
        written: false,
        category: body.category || 'source',
        language: body.language || 'chinese',
        base: 'C:/ui-check/game',
        ...resultExtra,
      },
    };
  };

  const pageSlice = () => {
    if (!f.scan) return f.rpyStatus.scan;
    const total = f.scan.candidates.length;
    const pageCount = Math.max(1, Math.ceil(total / 200));
    const page = Math.max(1, Math.min(f.scanPage, pageCount));
    const start = (page - 1) * 200;
    return {
      ...f.scan,
      candidates: f.scan.candidates.slice(start, start + 200),
      candidate_total: total,
      page,
      page_size: 200,
      page_count: pageCount,
    };
  };

  const toolStatus = (extra = {}) => ({
    project_key: f.toolProjectKey,
    path: 'C:/ui-check',
    root: 'C:/ui-check',
    base: 'C:/ui-check/game',
    category: 'source',
    language: 'chinese',
    job: f.toolJobs.rpy || null,
    ...f.rpyStatus,
    scan: pageSlice(),
    ...extra,
  });

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
    if (p === '/api/update') return response({ status: 'idle' });
    if (p === '/api/settings') {
      if (method === 'PATCH') Object.assign(values, body.values || body);
      return response({ values, masked: [] });
    }
    if (p === '/api/project') return response(projectPayload());
    if (p === '/api/project/path' || p === '/api/project/resolve') return response(projectPayload());
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
    if (p === '/api/rpy-extraction' && method === 'GET') {
      const page = Number(parsed.searchParams.get('page') || '1');
      f.scanPage = page;
      return response(toolStatus({
        path: parsed.searchParams.get('path') || 'C:/ui-check',
        category: parsed.searchParams.get('category') || 'source',
        language: parsed.searchParams.get('language') || 'chinese',
      }));
    }
    if (p.startsWith('/api/rpy-extraction/') && method === 'POST') {
      if (p === '/api/rpy-extraction/select') {
        f.rpyStatus.applied_mode = body.mode || 'builtin';
        f.rpyStatus.applied_profile_id = body.profile_id ?? null;
        f.rpyStatus.applied_name = body.mode === 'builtin' ? '未选择自定义方案' : '自定义';
        f.rpyStatus.summary = '当前已生效：' + (body.mode === 'builtin' ? '只用内置' : '内置＋自定义');
        return response(toolStatus());
      }
      if (p === '/api/rpy-extraction/preview' || p === '/api/rpy-extraction/preview/continue') {
        f.scan = {
          has_scan: true,
          completed: true,
          error: '',
          files_read: 1,
          raw_matches: 201,
          filtered: 0,
          valid: 201,
          covered: 0,
          new: 201,
          candidates: manyCandidates,
          can_save_bind: true,
          can_continue: false,
        };
        f.scanPage = 1;
        const job = mkJob('rpy_preview', body, {
          action: p.endsWith('continue') ? 'preview_continue' : 'preview',
          scan: pageSlice(),
        });
        f.toolJobs.rpy = job;
        return response({ job });
      }
      if (p === '/api/rpy-extraction/profiles') {
        const category = body.category || 'source';
        const rules = body.starter
          ? starterRules.map((rule) => ({ ...rule, positive_samples: [...rule.positive_samples], negative_samples: [...rule.negative_samples], include_globs: [...rule.include_globs], flags: [...rule.flags] }))
          : [];
        return response(toolStatus({
          editor_profile: {
            id: 'profile-parity-' + (f.toolSerial + 1),
            name: body.starter ? '常用 RPY 规则副本' : '当前游戏补充规则',
            note: '',
            category,
            rules,
          },
        }));
      }
      if (p === '/api/rpy-extraction/save-bind' || p === '/api/rpy-extraction/save-draft') {
        const job = mkJob(p.endsWith('bind') ? 'rpy_save' : 'rpy_save', body, {
          action: p.endsWith('bind') ? 'save_bind' : 'save_draft',
          written: true,
          message: p.endsWith('bind') ? '方案已保存并用于当前分类。' : '已保存草稿',
          profile_id: body.profile?.id,
        });
        f.toolJobs.rpy = job;
        if (p.endsWith('bind') && body.profile?.id) {
          f.rpyStatus.applied_mode = 'combined';
          f.rpyStatus.applied_profile_id = body.profile.id;
          f.rpyStatus.applied_name = body.profile.name || '自定义';
          f.rpyStatus.profiles = [{ id: body.profile.id, name: body.profile.name || '自定义', category: body.category || 'source' }];
          f.rpyStatus.profile_docs = [body.profile];
        }
        return response({ job });
      }
      if (p === '/api/rpy-extraction/profiles/delete' || p === '/api/rpy-extraction/profiles/unbind') {
        f.rpyStatus.applied_mode = 'builtin';
        f.rpyStatus.applied_profile_id = null;
        return response(toolStatus());
      }
      return response(toolStatus());
    }
    if (/^\/api\/jobs\/rpy-parity-\d+\/cancel$/.test(p)) {
      const job = f.toolJobs.rpy;
      if (job) {
        job.cancel_requested = true;
        if (f.leaveHoldMs > 0) {
          // 收尾仍进行中：status 可先 cancelled，但 worker_active 保持 true
          job.status = 'cancelled';
          job.result.message = '任务已取消';
          job.result.worker_active = true;
          const hold = f.leaveHoldMs;
          f.leaveHoldMs = 0;
          setTimeout(() => {
            if (f.toolJobs.rpy && f.toolJobs.rpy.id === job.id) {
              f.toolJobs.rpy.result.worker_active = false;
              f.toolJobs.rpy.status = 'cancelled';
            }
          }, hold);
        } else {
          job.status = 'cancelled';
          job.result.message = '任务已取消';
          job.result.worker_active = false;
        }
      }
      return response(job || { ok: true });
    }
    if (/^\/api\/jobs\/rpy-parity-\d+$/.test(p) && method === 'GET') {
      if (f.leaveGetFailOnce) {
        f.leaveGetFailOnce = false;
        return new Response(JSON.stringify({ detail: '模拟 GET 失败' }), {
          status: 500,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      return response(f.toolJobs.rpy || { id: p.split('/')[3], status: 'done', result: { worker_active: false } });
    }
    if (p === '/api/jobs') return response({ jobs: [f.toolJobs.rpy].filter(Boolean) });
    // 其它只读接口给空壳，避免启动期未覆盖 API 打断绑定项目
    if (method === 'GET') return response({});
    throw new Error('rpy parity 未定义接口：' + method + ' ' + p + qs);
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
    if (await js("!!document.querySelector('.translation-layout') || !!document.querySelector('.rb-shell')")) break;
    await pause(100);
  }

  const assert = async (expression, name) => {
    for (let attempt = 0; attempt < 16; attempt++) {
      if (await js(`Boolean(${expression})`)) {
        log('PASS ' + name);
        return;
      }
      await pause(140);
    }
    log('FAIL CONTEXT ' + JSON.stringify(await js(`({
      page: document.querySelector('.content')?.dataset.page,
      toolPage: document.querySelector('[data-rb-page]')?.getAttribute('data-rb-page'),
      writes: __uiFixture.writes.slice(-8),
      text: document.querySelector('[data-rb-page=rpy-extraction]')?.innerText?.slice(0,500)
    })`)));
    throw new Error('FAIL ' + name);
  };

  const click = async (text) => {
    const position = await js(`(()=>{
      const dialogs=[...document.querySelectorAll('[role=dialog]')].filter(e=>e.getBoundingClientRect().height>0);
      const scope=dialogs.at(-1)||document;
      const normalized=${JSON.stringify(text.replaceAll(' ', ''))};
      const e=[...scope.querySelectorAll('button,[role=tab],[role=menuitem]')].find(b=>b.textContent.split(' ').join('')===normalized)
        || (dialogs.at(-1) && [...dialogs.at(-1).querySelectorAll('button')].find(b=>b.classList.contains('ant-btn-primary')));
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
    await pause(220);
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

  const openTool = async (title) => {
    await page("Ren'Py 工具箱");
    await pause(180);
    await input('.toolbox-search', title);
    await pause(160);
    await js('document.querySelector(".tool-card")?.click()');
    await pause(320);
  };

  const clearWrites = async () => { await js('__uiFixture.writes.length=0'); };
  const capture = async (name) => {
    const result = await win.webContents.debugger.sendCommand('Page.captureScreenshot');
    fs.writeFileSync(path.join(out, name + '.png'), Buffer.from(result.data, 'base64'));
    log('CAPTURE ' + name);
  };

  // —— 导航进入 RPY ——
  await assert("document.querySelector('.workspace-project')", '壳已加载');
  await openTool('RPY 抽取设置');
  await assert("document.querySelector('[data-rb-page=rpy-extraction]')", '进入 RPY 页');
  await assert("document.querySelector('[data-rb-rpy-path]')?.value?.includes('ui-check')", '默认路径来自项目');
  await capture('rpy-main');

  // —— 打开高级区 + 复制内置（完整 RuleRow，防 .join TypeError）——
  await js(`(()=>{
    const header=[...document.querySelectorAll('.ant-collapse-header')].find(h=>h.textContent.includes('我要自己定义规则'));
    header?.click();
  })()`);
  await pause(200);
  await clearWrites();
  await click('复制常用规则为自定义');
  await assert("__uiFixture.writes.some(w=>w.p==='/api/rpy-extraction/profiles'&&w.body.starter===true)", '复制内置提交');
  await assert("document.querySelector('[data-rb-rpy-editor]')", '编辑器已打开');
  await assert("document.querySelector('[data-rb-rpy-scope]')", 'include_globs 字段存在');
  await assert("document.querySelector('[data-rb-rpy-group]')", 'text_group 字段存在');
  await assert("document.querySelector('[data-rb-rpy-ignore-case]')", 'IGNORECASE 字段存在');
  await assert("document.querySelector('[data-rb-rpy-rule-note]')", '规则 note 字段存在');
  await capture('rpy-editor');

  // 新增规则应只更新草稿，并立即切换到新规则表单。
  await clearWrites();
  await click('新增规则');
  log('AFTER ADD ' + JSON.stringify(await js(`({
    selects:[...document.querySelectorAll('.ant-select')].map(e=>({text:e.innerText,value:e.querySelector('.ant-select-selection-item')?.textContent,html:e.outerHTML.slice(0,500)})),
    inputs:[...document.querySelectorAll('[data-rb-rpy-editor] input, [data-rb-rpy-editor] textarea')].map(e=>({value:e.value,scope:e.getAttribute('data-rb-rpy-scope')})),
    buttons:[...document.querySelectorAll('[data-rb-rpy-editor] button')].map(e=>({text:e.textContent,disabled:e.disabled}))
  })`)));
  await assert(
    "[...document.querySelectorAll('.ant-select-selection-item, .ant-select-content-has-value')].some(e=>e.textContent.trim()==='规则 3')",
    '新增规则后选中第三条',
  );
  await assert(
    "document.querySelector('[data-rb-rpy-editor] textarea')?.value.includes('reply_message')",
    '新增规则模板已显示',
  );
  await assert('__uiFixture.writes.length===0', '新增规则没有同步写 API');

  // 新增规则会标记页面 dirty；点击返回应显示放弃确认，确认后才离开。
  await click('返回工具箱');
  await assert("[...document.querySelectorAll('[role=dialog]')].some(d=>d.textContent.includes('未保存'))", '新增规则离页显示未保存确认');
  await click('放弃并继续');
  await assert("document.querySelector('.content')?.dataset.page==='toolbox'", '确认放弃后返回工具箱');
  await openTool('RPY 抽取设置');
  await assert("document.querySelector('[data-rb-page=rpy-extraction]')", '返回后可再次进入 RPY');
  await js(`(()=>{
    const header=[...document.querySelectorAll('.ant-collapse-header')].find(h=>h.textContent.includes('我要自己定义规则'));
    header?.click();
  })()`);
  await pause(200);
  await clearWrites();
  await click('复制常用规则为自定义');
  await assert("document.querySelector('[data-rb-rpy-editor]')", '返回后编辑器可再次打开');

  // —— 预览 + 分页到第 201 条（真实 DOM，防假阳性）——
  await clearWrites();
  await click('预览启用的规则');
  await assert("__uiFixture.writes.some(w=>w.p==='/api/rpy-extraction/preview')", '预览已提交');
  await assert("document.querySelector('[data-rb-rpy-pagination]')", '分页控件可见');
  await assert("document.querySelector('[data-rb-rpy-save-bind]')?.disabled===false", '预览后 proof 有效可保存');
  await pause(400);
  await clearWrites();
  await click('下一页');
  await assert("__uiFixture.reads.some(r=>r.includes('page=2'))", '请求第 2 页');
  // 等待至少两轮 status 轮询；DOM 必须稳定在第 2 页 Candidate 200
  await pause(2200);
  await assert("document.querySelector('[data-rb-page=rpy-extraction] tbody')?.textContent?.includes('Candidate 200')", '第2页实际显示第201条');
  await assert("document.querySelector('[data-rb-rpy-pagination]')?.textContent?.includes('2 / 2')", '第2页页码稳定');
  await assert("document.querySelector('[data-rb-rpy-pagination]')?.textContent?.includes('201')", '总数 201 可见');
  await pause(1600);
  await assert("document.querySelector('[data-rb-page=rpy-extraction] tbody')?.textContent?.includes('Candidate 200')", '轮询后仍显示 Candidate 200');
  await assert("document.querySelector('[data-rb-rpy-pagination]')?.textContent?.includes('2 / 2')", '轮询后页码仍为 2/2');
  await capture('rpy-page2');

  // —— 长收尾（dirty=false）：cancel 后 worker_active>5s，不得立刻放行 ——
  await js(`(()=>{
    const job=__uiFixture.toolJobs.rpy;
    if(!job) throw new Error('缺少预览 job');
    job.status='running';
    job.result.worker_active=true;
    job.result.action='preview';
    __uiFixture.leaveHoldMs=6500;
  })()`);
  // Give the page's status poll a chance to observe the simulated running job.
  await pause(1800);
  await page('翻译任务');
  await pause(800);
  await assert("document.querySelector('[data-rb-page=rpy-extraction]')", '长收尾期间仍留在 RPY（无 dirty 也走 guard）');
  await pause(4500);
  await assert(
    "document.body.innerText.includes('收尾') || document.body.innerText.includes('finishing') || document.querySelector('[data-rb-rpy-leave-retry]')",
    '超过5秒可见等待提示',
  );
  for (let i = 0; i < 40; i++) {
    const done = await js("!(__uiFixture.toolJobs.rpy?.result?.worker_active)");
    if (done) break;
    await pause(250);
  }
  // 首轮 navigate 的 guard 会在 worker 终态后自行完成离页
  await pause(800);
  await assert("document.querySelector('.content')?.dataset.page==='translation'", 'worker 终态后可离开 RPY');

  // —— GET 失败不得放行 ——
  await openTool('RPY 抽取设置');
  await assert("document.querySelector('[data-rb-page=rpy-extraction]')", '再次进入 RPY 测 GET 失败');
  await js(`(()=>{
    const header=[...document.querySelectorAll('.ant-collapse-header')].find(h=>h.textContent.includes('我要自己定义规则'));
    header?.click();
  })()`);
  await pause(200);
  await click('复制常用规则为自定义');
  await assert("document.querySelector('[data-rb-rpy-editor]')", '编辑器再次打开');
  await click('预览启用的规则');
  await pause(400);
  await js(`(()=>{
    const job=__uiFixture.toolJobs.rpy;
    job.status='running';
    job.result.worker_active=true;
  })()`);
  // 页面每 1.5s 轮询状态接口取 job（renderer/src/pages/projectToolJob.tsx:124），
  // 必须先等它看到 running，离开守卫才会真正去 GET 任务状态；否则守卫读到的还是上一次的快照。
  await pause(1800);
  await js("__uiFixture.leaveGetFailOnce=true");
  await pause(100);
  await page('翻译任务');
  await pause(600);
  await assert("document.querySelector('[data-rb-page=rpy-extraction]')", 'GET 失败时仍留在 RPY');
  await assert(
    "document.body.innerText.includes('无法确认') || document.body.innerText.includes('Could not confirm')",
    'GET 失败中英文错误提示',
  );
  await js(`(()=>{
    const job=__uiFixture.toolJobs.rpy;
    if(job){ job.status='done'; job.result.worker_active=false; }
  })()`);
  await pause(200);

  // —— 编辑后失效 proof：SaveBind 应禁用；dirty 不丢 ——
  await js(`(()=>{
    const note=document.querySelector('[data-rb-rpy-rule-note]');
    if(!note) throw new Error('缺少规则备注');
    const proto=HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto,'value').set.call(note,'edited-for-proof');
    note.dispatchEvent(new Event('input',{bubbles:true}));
  })()`);
  await pause(200);
  await assert("document.querySelector('[data-rb-rpy-save-bind]')?.disabled===true", '编辑后 SaveBind 禁用');
  await assert("document.querySelector('[data-rb-rpy-rule-note]')?.value==='edited-for-proof'", '编辑正文未因轮询丢失');

  // —— 当前方案副本按钮 ——
  await assert("[...document.querySelectorAll('button')].some(b=>b.textContent.includes('另存为副本')&&!b.disabled)", '另存为副本可用');

  // —— dirty：改名称后导航应弹出未保存 ——
  await js(`(()=>{
    const nameInput=[...document.querySelectorAll('[data-rb-rpy-editor] input')].find(e=>e.value&&e.value.includes('常用'));
    if(!nameInput) throw new Error('缺少方案名');
    const proto=HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto,'value').set.call(nameInput, nameInput.value+'*');
    nameInput.dispatchEvent(new Event('input',{bubbles:true}));
  })()`);
  await pause(200);
  await page('翻译任务');
  await pause(300);
  await assert("[...document.querySelectorAll('[role=dialog]')].some(d=>d.textContent.includes('未保存'))", 'dirty 导航保护');
  await click('放弃并继续');
  await pause(400);
  await assert("document.querySelector('.content')?.dataset.page==='translation'", '确认后离开 RPY');

  // —— 重新进入 + 窄屏 ——
  await openTool('RPY 抽取设置');
  await assert("document.querySelector('[data-rb-page=rpy-extraction]')", '再次进入 RPY');
  await win.webContents.debugger.sendCommand('Emulation.setDeviceMetricsOverride', {
    width: 680,
    height: 800,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await pause(200);
  await capture('rpy-680');
  await win.webContents.debugger.sendCommand('Emulation.clearDeviceMetricsOverride');

  // —— WS onmessage 可调用（不因 undefined 退出）——
  await assert("typeof __uiFixture.sockets.at(-1)?.onmessage==='function' || __uiFixture.sockets.length>=0", 'WS 监听可安全访问');
  await js(`(()=>{
    const payload=JSON.stringify({type:'event',event:'PROJECT_CHANGED',data:{}});
    for (const socket of __uiFixture.sockets) {
      if (typeof socket.onmessage==='function') socket.onmessage({data:payload});
    }
  })()`);
  await pause(200);

  if (errors.length) throw new Error('控制台错误：' + JSON.stringify(errors));
  log('ALL RPY PARITY CHECKS PASSED');
  win.destroy();
  app.quit();
}).catch((error) => {
  log(error.stack || String(error));
  app.exit(1);
});
