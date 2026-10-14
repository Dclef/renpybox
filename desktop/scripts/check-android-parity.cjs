/**
 * 安卓打包页受控 UI 自检（Scope B）。
 *
 * 运行：
 *   清除 ELECTRON_RUN_AS_NODE
 *   UI_URL=http://127.0.0.1:5179
 *   RENPYBOX_UI_CAPTURE_DIR=%TEMP%\renpybox-qt5-parity\new-ui-android
 *   cd desktop && npx electron scripts/check-android-parity.cjs
 *
 * 独立 --user-data-dir；mock HTTP/WS；不触发真实 SDK/签名/APK。
 * 导航依赖 A 注册 android-build；未注册时明确失败说明。
 */
if (process.type !== 'browser') throw new Error('请使用 Electron 主进程运行，并先清除 ELECTRON_RUN_AS_NODE。');

const { app, BrowserWindow } = require('electron');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const out = process.env.RENPYBOX_UI_CAPTURE_DIR
  || path.join(os.tmpdir(), 'renpybox-qt5-parity', 'new-ui-android');
const profileDir = path.join(os.tmpdir(), 'renpybox-android-parity-profile-' + Date.now());
const logPath = path.join(out, 'android-parity.log');
const pause = (ms) => new Promise((r) => setTimeout(r, ms));
const log = (value) => fs.appendFileSync(logPath, value + '\n');

fs.mkdirSync(out, { recursive: true });
fs.mkdirSync(profileDir, { recursive: true });
fs.writeFileSync(logPath, '');
app.setPath('userData', profileDir);

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
    androidProjectKey: 'c:\\ui-check|chinese',
    androidOwnerKey: 'c:\\ui-check|chinese',
    androidSerial: 0,
    androidJob: null,
    androidStatus: {
      project_key: 'c:\\ui-check|chinese',
      project_root: 'C:/ui-check',
      owner_project_key: 'c:\\ui-check|chinese',
      owner_project_root: 'C:/ui-check',
      game_dir: 'C:/ui-check/game',
      keystore_exists: true,
      rapt_bin: 'C:/sdk/rapt/bin',
      rapt_bin_exists: true,
      outputs: [{ name: 'old.apk', path: 'C:/sdk/rapt/bin/old.apk', mtime: 1 }],
      config: {
        sdk_path: 'C:/sdk',
        app_name: 'DemoApp',
        package_name: 'com.example.demo',
        version: '1.0.0',
        archive_source_dir: '',
        shell_backup_enable: true,
        shell_remove_dirs: 'images,image,audio,video,videos,movies,script',
        default_shell_remove_dirs: 'images,image,audio,video,videos,movies,script',
        dname: 'CN=Hidden',
        update_always: true,
        update_icons: true,
      },
      cancellable: false,
    },
  };

  window.confirm = () => true;
  const response = (data, status = 200) => new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

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
    const id = 'android-parity-' + (f.androidSerial += 1);
    const key = String(body.project_key || f.androidProjectKey);
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
        cancellable: false,
        open_bin: Boolean(resultExtra.open_bin),
        action: resultExtra.action || kind.replace('android_', ''),
        logs: resultExtra.logs || ['mock log line'],
        ...resultExtra,
      },
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
      if (method === 'PATCH') Object.assign(values, body.values || {});
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
    if (p === '/api/android-build' && method === 'GET') {
      const qPath = String(parsed.searchParams.get('project_path') || '').trim();
      const norm = (value) => String(value || '').replace(/\\/g, '/').toLowerCase();
      const status = {
        ...f.androidStatus,
        job: f.androidJob,
        owner_project_key: f.androidOwnerKey,
        owner_project_root: 'C:/ui-check',
      };
      if (qPath && norm(qPath) !== 'c:/ui-check') {
        status.project_key = norm(qPath) + '|chinese';
        status.project_root = qPath.replace(/\\/g, '/');
        status.game_dir = status.project_root + '/game';
        f.androidProjectKey = status.project_key;
      } else {
        status.project_key = f.androidOwnerKey;
        status.project_root = 'C:/ui-check';
        status.game_dir = 'C:/ui-check/game';
        f.androidProjectKey = f.androidOwnerKey;
      }
      return response(status);
    }
    if (p === '/api/android-build/write-json' && method === 'POST') {
      return response({
        success: true,
        written: true,
        path: (body.project_path || 'C:/ui-check') + '/android.json',
        message: 'android.json 已更新',
        project_key: body.project_key,
        owner_project_key: f.androidOwnerKey,
      });
    }
    if (p === '/api/android-build/detect' && method === 'POST') {
      return response({
        success: true,
        target: body.target,
        detected: ['images', 'audio'],
        count: 2,
        value: 'images;audio',
        cleared: false,
        message: '已检测 2 个文件夹并替换当前列表',
        project_key: f.androidProjectKey,
        project_root: body.project_path || 'C:/ui-check',
        owner_project_key: f.androidOwnerKey,
      });
    }
    if (p === '/api/android-build/open-bin' && method === 'POST') {
      return response({ success: true, path: 'C:/sdk/rapt/bin', project_key: f.androidProjectKey, outputs: f.androidStatus.outputs });
    }
    if (p === '/api/android-build/check-env' && method === 'POST') {
      f.androidJob = mkJob('android_check_env', body, { action: 'check_env', message: '环境检查完成' });
      return response({ job: f.androidJob });
    }
    if (p === '/api/android-build/install-sdk' && method === 'POST') {
      f.androidJob = mkJob('android_install_sdk', body, { action: 'install_sdk', message: 'SDK 安装完成' });
      return response({ job: f.androidJob });
    }
    if (p === '/api/android-build/generate-keys' && method === 'POST') {
      f.androidJob = mkJob('android_generate_keys', body, { action: 'generate_keys', message: '签名已生成' });
      return response({ job: f.androidJob });
    }
    if (p === '/api/android-build/build' && method === 'POST') {
      if (!body.confirm) return new Response(JSON.stringify({ detail: '构建需 confirm=true' }), { status: 400 });
      f.androidJob = mkJob('android_build', body, {
        action: 'build',
        written: true,
        open_bin: true,
        rapt_bin: 'C:/sdk/rapt/bin',
        message: '构建完成',
        outputs: [{ name: 'new.apk' }, { name: 'old.apk' }],
        output_names: ['new.apk', 'old.apk'],
        new_output_names: ['new.apk'],
        outputs_include_history: true,
      });
      return response({ job: f.androidJob });
    }
    if (p === '/api/android-build/make-shell' && method === 'POST') {
      if (!body.confirm) return new Response(JSON.stringify({ detail: '壳制作需 confirm=true' }), { status: 400 });
      f.androidJob = mkJob('android_shell', body, {
        action: 'shell',
        written: true,
        success: true,
        message: '壳包处理完成',
        archive_path: 'C:/ui-check/archive.rpa',
        backup_path: 'C:/ui-check/archive_backup_demo.zip',
        packed_count: 3,
        removed: ['images'],
        shell_backup_enable: body.shell_backup_enable,
      });
      return response({ job: f.androidJob });
    }
    if (p === '/api/jobs') return response({ jobs: [f.androidJob].filter(Boolean) });
    if (/^\/api\/jobs\//.test(p) && method === 'GET') {
      return response(f.androidJob || { id: 'none', status: 'done', result: {} });
    }
    if (p.startsWith('/api/update')) return response({ status: 'idle' });
    throw new Error('android parity 未定义接口：' + method + ' ' + p + qs);
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
  await win.loadURL(process.env.RENPYBOX_UI_URL || process.env.UI_URL || 'http://127.0.0.1:5179');

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
      text: document.querySelector('[data-rb-page=android-build]')?.innerText?.slice(0,500)
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

  const clearWrites = async () => { await js('__uiFixture.writes.length=0'); };

  await assert("document.querySelector('.workspace-project').title==='C:/ui-check'", 'fixture 已绑定项目');

  await page("Ren'Py 工具箱");
  await pause(180);
  await input('.toolbox-search', '安卓打包');
  await pause(160);
  const hasCard = await js('Boolean(document.querySelector(".tool-card"))');
  if (!hasCard) throw new Error('工具箱未找到安卓打包卡片');
  await js('document.querySelector(".tool-card")?.click()');
  await pause(320);

  const pageReady = await js("Boolean(document.querySelector('[data-rb-page=android-build]'))");
  if (!pageReady) {
    log('LIMIT A尚未注册 android-build 路由/TOOL_PAGES；卡片仍可能显示占位');
    throw new Error('FAIL 进入安卓打包页（需 A 注册 App/ToolBoxPage/nav）');
  }

  await assert("document.querySelector('[data-rb-android-sdk]')", 'SDK 输入');
  await assert("document.querySelector('[data-rb-android-project]')", '项目输入');
  await assert("document.querySelector('[data-rb-android-app-name]')?.value==='DemoApp'", '默认应用名');
  await assert("document.querySelector('[data-rb-android-package]')?.value==='com.example.demo'", '默认包名');
  await assert("document.querySelector('[data-rb-android-version]')?.value==='1.0.0'", '默认版本');
  await assert("document.querySelector('[data-rb-android-backup]')", '备份开关');
  await assert(
    "document.querySelector('[data-rb-android-backup]')?.getAttribute('data-rb-android-backup-on')==='1'",
    '备份默认 true',
  );
  await assert("document.querySelector('[data-rb-android-dname]')?.value==='CN=Hidden'", '隐藏 dname 保留');
  await assert("document.querySelector('[data-rb-android-update-always]')?.value==='1'", '隐藏 update_always 保留');
  await assert("document.querySelector('[data-rb-android-update-icons]')?.value==='1'", '隐藏 update_icons 保留');
  await assert(
    "![...document.querySelectorAll('button')].some(b=>b.textContent.includes('停止')||b.textContent.includes('取消'))",
    '无假停止按钮',
  );

  await clearWrites();
  await click('写入 android.json');
  await assert(
    "__uiFixture.writes.some(w=>w.p==='/api/android-build/write-json'&&w.body.app_name==='DemoApp'&&w.body.update_always===true&&w.body.dname==='CN=Hidden')",
    'write-json 含隐藏字段',
  );

  await clearWrites();
  await click('检查环境');
  await assert("__uiFixture.writes.some(w=>w.p==='/api/android-build/check-env'&&w.body.sdk_path==='C:/sdk')", 'check-env payload');

  await clearWrites();
  await js('document.querySelector("[data-rb-android-detect-archive]")?.click()');
  await pause(200);
  await assert("__uiFixture.writes.some(w=>w.p==='/api/android-build/detect'&&w.body.target==='archive'&&w.body.replace===true)", '检测打包 replace');
  await assert("document.querySelector('[data-rb-android-archive-source]')?.value==='images;audio'", '检测结果替换列表');

  // 手动目标 B：路径无损 + detect 带 owner A
  await clearWrites();
  await input('[data-rb-android-project]', 'C:/manual-b');
  await assert(
    "(()=>{const root=document.querySelector('[data-rb-android-project]');const e=root?.matches('input')?root:root?.querySelector('input');return e?.value==='C:/manual-b';})()",
    '手动项目 B 路径保留',
  );
  await assert(
    "__uiFixture.reads.some(r=>r.includes('/api/android-build?project_path=')&&r.toLowerCase().includes('manual-b'))",
    'status 带 project_path=B',
  );
  await assert(
    "!document.querySelector('[data-rb-android-detect-archive]')?.disabled",
    'B 目标 detect 可用',
  );
  await clearWrites();
  await js('document.querySelector("[data-rb-android-detect-archive]")?.click()');
  await pause(280);
  await assert(
    `__uiFixture.writes.some(w=>w.p==='/api/android-build/detect'&&w.body.project_key===__uiFixture.androidOwnerKey&&String(w.body.project_path||'').replace(/\\\\/g,'/').toLowerCase()==='c:/manual-b')`,
    'detect ownerA + project_path B',
  );
  await assert(
    "(()=>{const root=document.querySelector('[data-rb-android-project]');const e=root?.matches('input')?root:root?.querySelector('input');return e?.value==='C:/manual-b';})()",
    'detect 后路径仍为 B',
  );
  await assert("document.querySelector('[data-rb-android-archive-source]')?.value==='images;audio'", 'B 目标检测结果仍写入');

  await clearWrites();
  await click('生成 archive.rpa 并清理资源');
  await click('生成 archive.rpa 并清理资源');
  await assert(
    "__uiFixture.writes.some(w=>w.p==='/api/android-build/make-shell'&&w.body.confirm===true&&w.body.shell_backup_enable===true&&String(w.body.project_path||'').replace(/\\\\/g,'/').toLowerCase()==='c:/manual-b')",
    '壳制作 confirm + backupTrue + path B',
  );
  await assert("document.querySelector('[data-rb-android-shell-result]')", '壳结果可见');

  await clearWrites();
  await click('开始构建');
  await click('开始构建');
  await assert(
    "__uiFixture.writes.some(w=>w.p==='/api/android-build/build'&&w.body.confirm===true&&w.body.package_name==='com.example.demo')",
    '构建 confirm payload',
  );

  await capture('android-parity-desktop');
  if (errors.length) throw new Error('控制台错误：' + JSON.stringify(errors));
  log('ALL ANDROID PARITY CHECKS PASSED');
  win.destroy();
  app.quit();
}).catch((error) => {
  log(error.stack || String(error));
  app.exit(1);
});
