/**
 * 工具详情页布局受控截图：ErrorRepair / Formatter / Android / HTML。
 *
 * 运行（pwsh，勿终止已有 Vite；本脚本要求 5179）：
 *   $env:RENPYBOX_UI_URL='http://127.0.0.1:5179'
 *   $env:RENPYBOX_UI_CAPTURE_DIR="$env:TEMP\renpybox-qt5-parity\tool-layout"
 *   $profile = Join-Path $env:TEMP ("renpybox-tool-layout-" + [guid]::NewGuid().ToString('N'))
 *   cd desktop
 *   Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue
 *   .\node_modules\.bin\electron.cmd --user-data-dir=$profile scripts/check-tool-layout.cjs
 *
 * 额外静态检查：node --test tests/tool-page-layout.test.mjs
 */
if (process.type !== 'browser') throw new Error('请使用 Electron 主进程运行，并先清除 ELECTRON_RUN_AS_NODE。');

const { app, BrowserWindow } = require('electron');
const fs = require('node:fs');
const path = require('node:path');

const out = process.env.RENPYBOX_UI_CAPTURE_DIR
  || path.join(require('node:os').tmpdir(), 'renpybox-qt5-parity', 'tool-layout');
const logPath = path.join(out, 'tool-layout.log');
const pause = (ms) => new Promise((r) => setTimeout(r, ms));
const log = (value) => fs.appendFileSync(logPath, value + '\n');

fs.mkdirSync(out, { recursive: true });
fs.writeFileSync(logPath, '');

function fixture() {
  const values = {
    theme: 'LIGHT',
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
    const method = String(options.method || 'GET').toUpperCase();
    let body = {};
    try { body = options.body ? JSON.parse(String(options.body)) : {}; } catch { body = {}; }
    f.reads.push({ p, method });
    if (method !== 'GET') f.writes.push({ p, body });

    if (p === '/health' || p === '/api/health') return response({ ok: true, app_version: 'ui-check', mode: 'api', pid: 0 });
    if (p === '/api/version') return response({ app_version: 'ui-check', api_version: '1' });
    if (p === '/api/project') return response(projectPayload());
    if (p === '/api/settings') {
      if (method === 'PATCH') Object.assign(values, body.values || body || {});
      return response({ values, masked: [] });
    }
    if (p === '/api/translation/state' || p === '/api/translation/status') {
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
    if (p.startsWith('/api/error-repair')) return response({ project_key: 'c:\\ui-check|tool', folder: '', job: null });
    if (p.startsWith('/api/formatter')) return response({ project_key: 'c:\\ui-check|tool', folder: '', job: null });
    if (p.startsWith('/api/android-build')) {
      return response({
        project_key: 'c:\\ui-check|tool',
        sdk_path: '',
        project_path: 'C:/ui-check',
        app_name: 'DemoApp',
        package_name: 'com.example.demo',
        version_name: '1.0.0',
        dname: 'CN=Hidden',
        update_always: true,
        update_icons: true,
        keystore_exists: true,
        defaults: {
          app_name: 'DemoApp',
          package_name: 'com.example.demo',
          version_name: '1.0.0',
          dname: 'CN=Hidden',
          update_always: true,
          update_icons: true,
        },
        job: null,
      });
    }
    if (p.startsWith('/api/html-import')) return response({ project_key: 'c:\\ui-check|tool', job: null });
    if (p.startsWith('/api/')) return response({ ok: true });
    return nativeFetch(url, options);
  };

  class FakeWS {
    constructor(url) {
      this.url = String(url);
      this.readyState = 1;
      this.onopen = null;
      this.onmessage = null;
      this.onclose = null;
      this.onerror = null;
      f.sockets.push(this);
      queueMicrotask(() => this.onopen && this.onopen({}));
    }
    send() {}
    close() { this.readyState = 3; if (this.onclose) this.onclose({}); }
  }
  window.WebSocket = FakeWS;
}

app.whenReady().then(async () => {
  const uiUrl = process.env.RENPYBOX_UI_URL || process.env.UI_URL || 'http://127.0.0.1:5179';
  log('UI_URL ' + uiUrl);
  log('OUT ' + out);

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
    const value = String(event.message ?? message ?? '');
    // antd 弃用警告不是布局回归；业务页 Input.Group 不在本脚本修改范围
    if (/\[antd:/.test(value) && /deprecated/i.test(value)) {
      log('CONSOLE-IGNORE ' + value);
      return;
    }
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
  await win.loadURL(uiUrl);

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
    if (await js("!!document.querySelector('.rb-shell') || !!document.body")) break;
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

  const openTool = async (query) => {
    await js(`Array.from(document.querySelectorAll('.nav-item')).find(b=>b.title==="Ren'Py 工具箱")?.click()`);
    await pause(220);
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
    await pause(360);
  };

  /** 量测详情页：外边距、SettingsGroup body padding、滚动 gap */
  const measureLayout = async (label) => {
    const metrics = await js(`(()=>{
      const page=document.querySelector('.rb-tool-page');
      const panel=document.querySelector('.rb-tool-panel');
      const scroll=document.querySelector('.rb-tool-panel .rb-page-scroll');
      const group=document.querySelector('.rb-settings-group');
      const body=document.querySelector('.rb-settings-body');
      if(!page||!scroll||!group||!body) return null;
      const ps=getComputedStyle(page);
      const ss=getComputedStyle(scroll);
      const bs=getComputedStyle(body);
      const pr=page.getBoundingClientRect();
      const gr=group.getBoundingClientRect();
      const boxes=[...document.querySelectorAll('.rb-settings-body > .ant-checkbox-wrapper')].slice(0,4).map(el=>{
        const r=el.getBoundingClientRect();
        return { top: Math.round(r.top), left: Math.round(r.left), width: Math.round(r.width) };
      });
      return {
        pagePadLeft: parseFloat(ps.paddingLeft),
        pagePadRight: parseFloat(ps.paddingRight),
        scrollPadLeft: parseFloat(ss.paddingLeft),
        scrollPadBottom: parseFloat(ss.paddingBottom),
        scrollGap: parseFloat(ss.gap) || parseFloat(ss.rowGap) || 0,
        bodyPad: parseFloat(bs.paddingLeft),
        bodyFlexWrap: bs.flexWrap,
        groupInsetLeft: gr.left - pr.left,
        hasPanel: !!panel,
        bannerFlex: (()=>{
          const b=scroll.querySelector(':scope > .banner');
          return b ? getComputedStyle(b).flexGrow : null;
        })(),
        scrollWidth: scroll.clientWidth,
        bannerWidth: (()=>{
          const b=scroll.querySelector(':scope > .banner');
          return b ? b.getBoundingClientRect().width : null;
        })(),
        checkboxes: boxes,
      };
    })()`);
    log('METRICS ' + label + ' ' + JSON.stringify(metrics));
    if (!metrics) throw new Error('缺少布局节点: ' + label);
    if (!(metrics.pagePadLeft >= 16 && metrics.pagePadRight >= 16)) {
      throw new Error(label + ' 详情页左右 padding 不足: ' + JSON.stringify(metrics));
    }
    if (!(metrics.scrollPadLeft >= 3.5 && metrics.scrollPadBottom >= 15.5)) {
      throw new Error(label + ' 滚动页 padding 应为 0 4px 16px: ' + JSON.stringify(metrics));
    }
    if (!(metrics.groupInsetLeft >= 16)) {
      throw new Error(label + ' 卡片相对页边 inset 不足: ' + JSON.stringify(metrics));
    }
    if (!(metrics.bodyPad >= 15.5) || metrics.bodyFlexWrap !== 'wrap') {
      throw new Error(label + ' SettingsGroup body 应为 padding 16px + wrap: ' + JSON.stringify(metrics));
    }
    if (!(metrics.scrollGap >= 11.5)) {
      throw new Error(label + ' 滚动页 gap 应约 12px: ' + JSON.stringify(metrics));
    }
    if (metrics.bannerFlex != null && Number(metrics.bannerFlex) !== 0) {
      throw new Error(label + ' Banner 不应 flex-grow: ' + JSON.stringify(metrics));
    }
    // 短状态条不应贴满滚动区宽度（允许长文案接近满宽）
    if (metrics.bannerWidth != null && metrics.scrollWidth > 0 && metrics.bannerWidth > metrics.scrollWidth - 8) {
      const textLen = await js(`(document.querySelector('.rb-tool-panel > .rb-page-scroll > .banner')?.innerText||'').trim().length`);
      if (textLen > 0 && textLen < 24) {
        throw new Error(label + ' 短 Banner 不应撑满滚动区: ' + JSON.stringify({ ...metrics, textLen }));
      }
    }
    // checkbox 应纵向排列（相邻 top 不同），不能挤在同一行
    if (metrics.checkboxes && metrics.checkboxes.length >= 2) {
      const sameRow = metrics.checkboxes.every((c) => c.top === metrics.checkboxes[0].top);
      if (sameRow) throw new Error(label + ' checkbox 横向挤成一排: ' + JSON.stringify(metrics.checkboxes));
    }
    log('PASS layout ' + label);
    return metrics;
  };

  await assert("document.querySelector('.rb-shell')", '壳已渲染');
  await assert(
    "document.querySelector('.workspace-project')?.title==='C:/ui-check'",
    'fixture 已绑定项目',
  );

  // --- ErrorRepair ---
  await openTool('错误修复');
  await assert(
    "document.body.innerText.includes('修复缩进') || document.body.innerText.includes('Fix Indentation')",
    '错误修复页打开',
  );
  await assert("document.querySelector('[data-rb-tool-frame]')", 'ToolPageFrame 标记');
  await measureLayout('error-repair');
  await capture('ErrorRepairPage');

  // --- Formatter ---
  await openTool('代码格式化');
  await assert(
    "document.body.innerText.includes('格式化') || document.body.innerText.includes('Format')",
    '格式化页打开',
  );
  await measureLayout('formatter');
  await capture('FormatterPage');

  // --- Android（需项目；blocked 时只报告） ---
  await openTool('安卓打包');
  const androidReady = await js("Boolean(document.querySelector('[data-rb-page=android-build]'))");
  const androidBlocked = await js("Boolean(document.querySelector('.rb-tool-page') && !document.querySelector('.rb-tool-panel'))");
  const androidText = await js("(document.querySelector('.rb-tool-page')?.innerText||'').slice(0,240)");
  log('ANDROID ready=' + androidReady + ' blocked=' + androidBlocked + ' text=' + JSON.stringify(androidText));
  if (androidReady) {
    await measureLayout('android-build');
    await capture('AndroidBuildPage');
    log('PASS android');
  } else if (androidBlocked) {
    await capture('AndroidBuildPage-blocked');
    log('LIMIT Android 被 ToolPageFrame 项目依赖阻塞，仅报告');
  } else {
    await capture('AndroidBuildPage-unknown');
    throw new Error('FAIL 进入安卓打包页: ' + androidText);
  }

  // --- HTML（类型/项目阻塞只报告，不硬失败） ---
  await openTool('网页');
  const htmlReady = await js("Boolean(document.querySelector('[data-rb-page=html-import]'))");
  const htmlBlocked = await js("Boolean(document.querySelector('.rb-tool-page') && !document.querySelector('.rb-tool-panel'))");
  const htmlText = await js("(document.querySelector('.rb-tool-page')?.innerText||'').slice(0,240)");
  log('HTML ready=' + htmlReady + ' blocked=' + htmlBlocked + ' text=' + JSON.stringify(htmlText));
  if (htmlReady) {
    await measureLayout('html-import');
    await capture('HtmlImportPage');
    log('PASS html-import');
  } else if (htmlBlocked) {
    await capture('HtmlImportPage-blocked');
    log('LIMIT HTML 当前被项目依赖阻塞（ToolPageFrame blocked），仅报告不失败');
  } else {
    await capture('HtmlImportPage-unknown');
    log('LIMIT HTML 页未就绪，仅报告: ' + htmlText);
  }

  // 窄屏可读性：四页各截一张
  await win.setSize(720, 800);
  for (const item of [
    ['错误修复', 'ErrorRepairPage-narrow', 'error-repair-narrow'],
    ['代码格式化', 'FormatterPage-narrow', 'formatter-narrow'],
    ['安卓打包', 'AndroidBuildPage-narrow', 'android-narrow'],
    ['网页', 'HtmlImportPage-narrow', 'html-narrow'],
  ]) {
    const [query, shot, label] = item;
    await openTool(query);
    await pause(200);
    const ready = await js("Boolean(document.querySelector('.rb-tool-panel .rb-page-scroll .rb-settings-body'))");
    if (ready) {
      await measureLayout(label);
      await capture(shot);
    } else {
      await capture(shot + '-blocked');
      log('LIMIT narrow blocked ' + label);
    }
  }
  await win.setSize(1280, 800);

  if (errors.length) throw new Error('console errors: ' + errors.slice(0, 3).join(' | '));
  log('OK tool-layout');
  app.exit(0);
}).catch((err) => {
  log('FATAL ' + (err && err.stack ? err.stack : String(err)));
  app.exit(1);
});
