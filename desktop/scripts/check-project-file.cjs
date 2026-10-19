/** Hidden Electron check for the older-data → .rbox wizard. No live backend. */
const { app, BrowserWindow } = require('electron');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

app.setPath('userData', fs.mkdtempSync(path.join(os.tmpdir(), 'renpybox-project-file-')));

const OUTSIDE = 'E:/outside/old-output/cache';
const SAVE_PATH = 'E:/outside/saved/legacy';

function fixture() {
  const state = window.__projectFile = {
    inspects: [],
    exports: [],
    saveCalls: [],
    opened: [],
    saveMode: 'cancel',
    failExport: false,
    releaseSave: null,
  };
  window.renpy = {
    sidecarPort: 9712,
    appInfo: async () => ({ appVersion: '0.9.3', packaged: false, icon: '', health: { ok: true } }),
    updater: { state: async () => ({ status: 'dev', packaged: false, releaseNotes: '' }), onState: () => () => {} },
    changelog: async () => '',
    onMaximizeChange: () => () => {},
    onCloseRequested: () => () => {},
    openLogs: async () => {},
    pickFile: async () => null,
    pickFolder: async () => 'E:/outside/old-output/cache',
    saveFile: async (options) => {
      state.saveCalls.push(options);
      if (state.saveMode === 'cancel') return null;
      if (state.saveMode === 'wait') {
        await new Promise((resolve) => { state.releaseSave = resolve; });
      }
      return 'E:/outside/saved/legacy';
    },
    openPath: async (target) => { state.opened.push(target); return true; },
  };
  const values = {
    theme: 'LIGHT',
    app_language: 'ZH',
    platforms: [],
    source_language: 'EN',
    target_language: 'ZH',
    input_folder: 'C:/ui-check/game',
    output_folder: 'C:/ui-check/game/tl/chinese',
  };
  const translation = {
    engine_status: 'IDLE',
    stop_barrier: false,
    single_tasks: false,
    request_id: '',
    run_id: 0,
    running: { running: 0, max: 1 },
    progress: {},
    active_output_folder: '',
  };
  window.fetch = async (url, options = {}) => {
    const route = new URL(String(url), location.href).pathname;
    let payload = {};
    if (route === '/health' || route === '/api/health') payload = { ok: true, python_version: '3.10.11', app_version: '0.9.3', pid: 1, mode: 'dev' };
    if (route === '/api/settings') payload = { values, masked: [] };
    if (route === '/api/jobs') payload = { jobs: [] };
    if (route === '/api/version') payload = { app_version: '0.9.3', api_version: '1' };
    if (route === '/api/project') payload = { renpy_project_path: 'C:/ui-check', renpy_game_folder: 'C:/ui-check/game', renpy_tl_folder: 'C:/ui-check/game/tl/chinese', theme: 'LIGHT', app_language: 'ZH' };
    if (route === '/api/translation/state') payload = translation;
    if (route === '/api/project/file/legacy/inspect') {
      const body = JSON.parse(options.body);
      state.inspects.push(body);
      payload = {
        output_folder: 'E:/outside/old-output',
        cache_folder: body.folder,
        cache_format: 'sqlite',
        item_count: 42,
        current_project_root: 'C:/ui-check',
        settings: ['source_language', 'target_language'],
      };
    }
    if (route === '/api/project/file/legacy/export') {
      const body = JSON.parse(options.body);
      state.exports.push(body);
      if (state.failExport) {
        return new Response(JSON.stringify({ detail: '无法读取旧数据' }), { status: 500, headers: { 'Content-Type': 'application/json' } });
      }
      payload = {
        info: {
          path: body.path,
          schema_version: 1,
          app_version: '0.9.3',
          created_at: '',
          updated_at: '',
          project_root: 'C:/ui-check',
          item_count: 42,
          items_digest: '',
        },
        output_folder: 'C:/ui-check/game/tl/chinese',
        current_project_root: 'C:/ui-check',
        project_root_matches: true,
        settings: ['source_language', 'target_language'],
        source_output_folder: 'E:/outside/old-output',
      };
    }
    return new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } });
  };
  window.WebSocket = class {
    readyState = 1;
    constructor() { setTimeout(() => this.onopen?.({}), 0); }
    send() {}
    close() { this.readyState = 3; }
  };
}

const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const watchdog = setTimeout(() => { console.error('FAIL: renderer did not respond within 50 seconds'); app.exit(1); }, 50000);

app.whenReady().then(async () => {
  const win = new BrowserWindow({
    width: 1024,
    height: 768,
    show: false,
    webPreferences: { offscreen: true, backgroundThrottling: false, sandbox: true, contextIsolation: true },
  });
  const errors = [];
  win.webContents.on('console-message', (event) => {
    if (event.level === 'error') errors.push(event.message);
  });
  await win.loadURL('about:blank');
  await win.webContents.executeJavaScript(`(${fixture.toString()})()`, true);
  win.webContents.debugger.attach('1.3');
  await win.webContents.debugger.sendCommand('Page.enable');
  await win.webContents.debugger.sendCommand('Page.addScriptToEvaluateOnNewDocument', { source: `(${fixture.toString()})()` });
  await win.loadFile(path.join(__dirname, '../dist/index.html'));
  const js = (code) => win.webContents.executeJavaScript(code, true);
  async function waitFor(expression) {
    for (let n = 0; n < 80; n += 1) {
      if (await js(expression)) return;
      await pause(100);
    }
    throw new Error(`Not ready: ${expression}; ${errors.join('\n')}`);
  }
  const click = async (text, scope = 'button') => {
    const clicked = await js(`[...document.querySelectorAll(${JSON.stringify(scope)})].some((element) => { if (element.textContent.trim() !== ${JSON.stringify(text)}) return false; element.click(); return true; })`);
    assert.equal(clicked, true, `missing ${text}`);
  };
  const shot = async (name) => {
    win.webContents.invalidate();
    await pause(100);
    const output = path.join(os.tmpdir(), 'renpybox-project-file');
    fs.mkdirSync(output, { recursive: true });
    const file = path.join(output, name);
    fs.writeFileSync(file, (await win.webContents.capturePage()).toPNG());
    console.log(`SHOT: ${file}`);
  };

  try {
    await waitFor("Boolean([...document.querySelectorAll('.nav-item')].find((element) => element.textContent.trim() === '项目设置'))");
    await click('项目设置', '.nav-item');
    await waitFor("Boolean(document.querySelector('.rb-project-file-actions'))");
    const layout = await js(`(() => {
      const root = document.querySelector('.rb-project-file');
      const note = root.querySelector('.banner');
      const actions = root.querySelector('.rb-project-file-actions');
      const buttons = [...actions.querySelectorAll('button')].map((button) => {
        const rect = button.getBoundingClientRect();
        return { text: button.textContent.trim(), disabled: button.disabled, left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom };
      });
      return { noteTop: note.getBoundingClientRect().top, buttonTop: buttons[0].top, buttons, width: innerWidth };
    })()`);
    assert.ok(layout.noteTop < layout.buttonTop, 'compatibility notice must sit above the actions');
    assert.equal(layout.buttons.length, 3);
    for (const button of layout.buttons) {
      assert.equal(button.disabled, false, button.text);
      assert.ok(button.left >= 0 && button.right <= layout.width + 1, `${button.text} overflows at 1024`);
    }
    const legacy = layout.buttons.find((button) => button.text === '从旧版数据创建工程文件');
    assert.ok(legacy, 'legacy action must be visible');
    await js("document.querySelector('.rb-project-file').scrollIntoView({ block: 'center' })");
    await pause(50);
    await shot('project-file-1024.png');

    await click('从旧版数据创建工程文件');
    await waitFor(`document.querySelector('.ant-modal')?.textContent.includes(${JSON.stringify(OUTSIDE)})`);
    assert.equal(await js('window.__projectFile.exports.length'), 0, 'preview must not write');
    assert.deepEqual(await js('window.__projectFile.inspects'), [{ folder: OUTSIDE }]);
    const preview = await js("document.querySelector('.ant-modal').textContent");
    assert.match(preview, /E:\/outside\/old-output/);
    assert.match(preview, /42/);
    assert.match(preview, /C:\/ui-check/);
    assert.match(preview, /SQLite/);
    await shot('legacy-preview.png');

    await click('取消', '.ant-modal button');
    await waitFor("!document.querySelector('.ant-modal')");
    assert.equal(await js('window.__projectFile.exports.length'), 0);

    await click('从旧版数据创建工程文件');
    await waitFor("Boolean(document.querySelector('.ant-modal'))");
    await click('选择保存位置', '.ant-modal button');
    await waitFor("Boolean(document.querySelector('.ant-modal')) && window.__projectFile.saveCalls.length === 1");
    assert.equal(await js('window.__projectFile.exports.length'), 0, 'cancelling the save dialog must not export');
    assert.match(await js('window.__projectFile.saveCalls[0].defaultPath'), /-legacy\.rbox$/);

    await js("window.__projectFile.saveMode = 'wait'; window.__projectFile.failExport = true");
    await click('选择保存位置', '.ant-modal button');
    await waitFor("window.__projectFile.saveCalls.length === 2 && ![...document.querySelectorAll('.ant-modal button')].some((element) => element.textContent.trim() === '选择保存位置')");
    assert.equal(await js('window.__projectFile.exports.length'), 0, 'confirm must not export twice while the save dialog is open');
    await js('window.__projectFile.releaseSave()');
    await waitFor("document.body.textContent.includes('无法读取旧数据') && document.querySelector('.ant-modal')?.textContent.includes('E:/outside/old-output/cache')");
    assert.equal(await js('window.__projectFile.exports.length'), 1);

    await js("window.__projectFile.saveMode = 'path'; window.__projectFile.failExport = false");
    await click('选择保存位置', '.ant-modal button');
    await waitFor("!document.querySelector('.ant-modal') && document.body.textContent.includes('E:/outside/saved/legacy.rbox')");
    const exported = await js('window.__projectFile.exports.at(-1)');
    assert.equal(exported.folder, OUTSIDE);
    assert.equal(exported.path, `${SAVE_PATH}.rbox`);
    assert.match(await js('document.body.textContent'), /E:\/outside\/old-output/);
    await click('打开所在文件夹');
    assert.deepEqual(await js('window.__projectFile.opened'), ['E:/outside/saved']);
    await js("document.querySelector('.rb-project-file').scrollIntoView({ block: 'center' })");
    await pause(50);
    await shot('legacy-result.png');
    console.log('PASS: legacy project file wizard');

    const englishFixture = fixture.toString().replaceAll("app_language: 'ZH'", "app_language: 'EN'");
    await win.webContents.debugger.sendCommand('Page.addScriptToEvaluateOnNewDocument', { source: `(${englishFixture})()` });
    await win.loadFile(path.join(__dirname, '../dist/index.html'));
    await waitFor("Boolean([...document.querySelectorAll('.nav-item')].find(element => element.textContent.trim() === 'Project Settings'))");
    await click('Project Settings', '.nav-item');
    await waitFor("Boolean(document.querySelector('.rb-project-file-actions'))");
    const english = await js("document.querySelector('.rb-project-file').innerText");
    assert.match(english, /SQLite/);
    assert.match(english, /JSON/);
    assert.match(english, /manual snapshot/);
    assert.equal(/[\u3400-\u9fff]/.test(english), false, 'English project file copy must be complete');
    assert.deepEqual(await js("[...document.querySelectorAll('.rb-project-file,.rb-project-file-actions,.rb-project-file .rb-settings-body')].filter(element => element.scrollWidth > element.clientWidth + 1).map(element => element.className)"), [], 'English project file actions must fit 1024px');
    await click('Create Project File from Older Data');
    await waitFor("Boolean(document.querySelector('.ant-modal'))");
    assert.match(await js("document.querySelector('.ant-modal').textContent"), /settings from an older program are not read automatically/);
    assert.deepEqual(await js("[...document.querySelectorAll('.ant-modal-body')].filter(element => element.scrollWidth > element.clientWidth + 1).map(element => element.className)"), [], 'English preview must not overflow');
    await shot('legacy-preview-en-1024.png');
    assert.deepEqual(errors, [], 'renderer must not report errors');
    console.log('PASS: English compatibility, migration preview and 1024px layout');
    clearTimeout(watchdog);
    app.exit(0);
  } catch (error) {
    console.error(error);
    clearTimeout(watchdog);
    app.exit(1);
  }
}).catch((error) => {
  console.error(error);
  clearTimeout(watchdog);
  app.exit(1);
});
