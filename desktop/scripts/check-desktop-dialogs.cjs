/** Exercise the actual React dialogs in a hidden Electron window, without a backend. */
const { app, BrowserWindow } = require('electron');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
app.setPath('userData', fs.mkdtempSync(path.join(os.tmpdir(), 'renpybox-dialogs-profile-')));

function fixture(markdown, appVersion) {
  const state = window.__dialogFixture = { markdown, confirmed: 0, closeListener: null, patches: [], failSave: false, proofRows: [] };
  window.renpy = {
    sidecarPort: 9712,
    appInfo: async () => ({ appVersion, packaged: false, icon: '', health: { ok: true } }),
    updater: {
      state: async () => ({ status: 'dev', packaged: false, releaseNotes: '' }),
      onState: () => () => {},
    },
    changelog: async () => state.markdown,
    onMaximizeChange: () => () => {},
    onCloseRequested: (callback) => { state.closeListener = callback; return () => { state.closeListener = null; }; },
    close: () => state.closeListener?.(),
    closeConfirmed: () => { state.confirmed += 1; },
    openLogs: async () => {},
    pickFile: async () => null,
    pickFolder: async () => null,
  };
  const values = state.values = { theme: 'LIGHT', app_language: 'ZH', platforms: [], expert_mode: true, target_language: 'ZH', translation_custom_prompts: { EN: 'Preserve this draft' } };
  window.fetch = async (url, options = {}) => {
    const parsed = new URL(String(url), location.href);
    const route = parsed.pathname;
    let payload = {};
    if (route === '/health' || route === '/api/health') payload = { ok: true, python_version: '3.10.11' };
    if (route === '/api/settings') {
      if (options.method === 'PATCH') {
        if (state.failSave) return new Response(JSON.stringify({ detail: 'Simulated save failure' }), { status: 500 });
        const patch = JSON.parse(options.body).values;
        state.patches.push(patch);
        Object.assign(values, patch);
      }
      payload = { values, masked: [] };
    }
    if (route === '/api/jobs') payload = { jobs: [] };
    if (route === '/api/version') payload = { app_version: appVersion };
    if (route === '/api/project') payload = { renpy_project_path: 'C:/ui-check', renpy_game_folder: 'C:/ui-check/game', renpy_tl_folder: 'C:/ui-check/game/tl/chinese' };
    if (route === '/api/proofreading') payload = { cache_token: 'fixture', cache_folder: '', total: state.proofRows.length, matched: state.proofRows.length, page: 1, limit: 50, files: ['story.rpy'], readonly: false, items: state.proofRows };
    if (route === '/api/proofreading/retranslate') payload = { state: 'IDLE' };
    if (route === '/api/rpy-extraction') payload = { project_key: 'c:\\ui-check', path: 'C:/ui-check', category: parsed.searchParams.get('category') || 'source', applied_mode: 'builtin', applied_profile_id: null, profiles: [], scan: {}, job: null };
    if (route === '/api/settings/prompt-preview') {
      const base = values.translation_prompt_mode === 'CUSTOM' ? values.translation_custom_prompts.ZH : '将{source_language}翻译为{target_language}。';
      const style = values.translation_style_id === 'CUSTOM' ? values.translation_custom_style : '';
      payload = parsed.searchParams.get('raw') === 'true' ? { base, style, language: 'ZH' }
        : { base: base.replace('{source_language}', '英文').replace('{target_language}', '中文'), style, fixed: '固定工程协议' };
    }
    if (route === '/api/translation/state') payload = {
      engine_status: 'IDLE', stop_barrier: false, single_tasks: false,
      running: { running: 0, max: 1 }, progress: {},
    };
    return new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } });
  };
  window.WebSocket = class {
    readyState = 1;
    constructor() { setTimeout(() => this.onopen?.({}), 0); }
    send() {}
    close() { this.readyState = 3; }
  };
}

const pause = (ms) => new Promise(resolve => setTimeout(resolve, ms));
const watchdog = setTimeout(() => { console.error('FAIL: renderer did not respond within 50 seconds'); app.exit(1); }, 50000);
app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: 1280, height: 800, show: false, webPreferences: { offscreen: true, backgroundThrottling: false, sandbox: true, contextIsolation: true } });
  const errors = [];
  win.webContents.on('console-message', (event) => {
    if (event.level === 'error') errors.push(event.message);
  });
  await win.loadURL('about:blank');
  win.webContents.debugger.attach('1.3');
  await win.webContents.debugger.sendCommand('Page.enable');
  const motion = process.argv.includes('--motion') ? 'no-preference' : 'reduce';
  await win.webContents.debugger.sendCommand('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: motion }] });
  const markdown = fs.readFileSync(path.join(__dirname, '../../CHANGELOG.md'), 'utf8');
  const version = JSON.parse(fs.readFileSync(path.join(__dirname, '../package.json'), 'utf8')).version;
  await win.webContents.debugger.sendCommand('Page.addScriptToEvaluateOnNewDocument', {
    source: `(${fixture.toString()})(${JSON.stringify(markdown)}, ${JSON.stringify(version)})`,
  });
  await win.loadFile(path.join(__dirname, '../dist/index.html'));
  const js = code => win.webContents.executeJavaScript(code, true);
  async function waitFor(expression) {
    for (let n = 0; n < 50; n += 1) {
      if (await js(expression)) return;
      await pause(100);
    }
    throw new Error(`Not ready: ${expression}; ${errors.join('\n')}`);
  }
  await waitFor("Boolean(document.querySelector('[aria-label=\"应用设置\"]'))");
  await js("document.querySelector('[aria-label=\"应用设置\"]').click()");
  await waitFor("[...document.querySelectorAll('button')].some(b => b.textContent === '查看更新日志')");
  // Use actual mouse input: a synthetic click skips Select's pointer handling.
  const selectRect = await js("document.querySelector('.ant-select').getBoundingClientRect().toJSON()");
  const point = { x: Math.round(selectRect.x + selectRect.width / 2), y: Math.round(selectRect.y + selectRect.height / 2) };
  win.webContents.sendInputEvent({ type: 'mouseDown', button: 'left', clickCount: 1, ...point });
  win.webContents.sendInputEvent({ type: 'mouseUp', button: 'left', clickCount: 1, ...point });
  await waitFor("document.querySelector('[aria-label=\"应用语言\"][role=combobox]')?.getAttribute('aria-expanded') === 'true'");
  await pause(400);
  const popupRect = await js("document.querySelector('.ant-select-dropdown:not(.ant-select-dropdown-hidden)').getBoundingClientRect().toJSON()");
  assert.ok(Math.abs(popupRect.left - selectRect.left) < 3, `Select popup must align to its control (${motion})`);
  assert.ok(popupRect.top >= selectRect.bottom && popupRect.top < selectRect.bottom + 12, `Select popup must stay inside the window (${motion})`);
  assert.match(await js("document.querySelector('.ant-select-dropdown').textContent"), /英文/);
  await js("[...document.querySelectorAll('.ant-select-item-option')].find(e => e.textContent === '英文').click()");
  await waitFor("document.querySelector('.ant-select').textContent.includes('英文') && window.__dialogFixture.values.app_language === 'EN'");
  assert.deepEqual(await js("window.__dialogFixture.patches.at(-1)"), { app_language: 'EN' });
  console.log('PASS: language dropdown opens beside its control and selection updates');
  // 改了需要重启的设置会弹重启确认；先点「稍后重启」关掉，否则会遮挡后面的用例。
  await waitFor("Boolean([...document.querySelectorAll('.ant-modal button')].find(b => b.textContent === '稍后重启'))");
  assert.match(await js("document.querySelector('.ant-modal').textContent"), /需要重启应用/);
  await js("[...document.querySelectorAll('.ant-modal button')].find(b => b.textContent === '稍后重启').click()");
  await waitFor("!document.querySelector('.ant-modal')");
  // 「稍后重启」= 放弃本次修改：下拉框和配置都要退回中文，否则用户看不出到底生效没有。
  await waitFor("document.querySelector('.ant-select').textContent.includes('中文') && window.__dialogFixture.values.app_language === 'ZH'");
  assert.deepEqual(await js("window.__dialogFixture.patches.at(-1)"), { app_language: 'ZH' });
  console.log('PASS: restart-required setting asks before restart and can be postponed');
  console.log('Opening changelog');
  await js("[...document.querySelectorAll('button')].find(b => b.textContent === '查看更新日志').click()");
  await waitFor("Boolean(document.querySelector('.update-changelog'))");
  assert.ok((await js("document.querySelector('.update-changelog').textContent")).includes(`v${version}`));
  assert.doesNotMatch(await js("document.querySelector('.update-changelog').textContent"), /发版时，请同步更新/);
  assert.ok(await js("Boolean(document.querySelector('.update-changelog h3'))"), 'Worker should render formatted headings, not silently fall back');
  await pause(400);
  assert.equal(await js("getComputedStyle(document.querySelector('.ant-modal')).opacity"), '1', `Dialog must be visible (${motion})`);
  assert.equal(await js("getComputedStyle(document.querySelector('.ant-modal-mask')).opacity"), '1', `Mask must not be an invisible click blocker (${motion})`);
  win.webContents.invalidate();
  await pause(100);
  const output = path.join(os.tmpdir(), 'renpybox-desktop-dialogs', motion);
  fs.mkdirSync(output, { recursive: true });
  fs.writeFileSync(path.join(output, 'changelog.png'), (await win.webContents.capturePage()).toPNG());
  const firstPage = await js("document.querySelector('.update-changelog').textContent");
  await js("document.querySelector('.ant-pagination-next').click()");
  await waitFor(`document.querySelector('.update-changelog').textContent !== ${JSON.stringify(firstPage)}`);
  await js("[...document.querySelectorAll('.ant-modal button')].find(b => b.textContent === '关闭').click()");
  await waitFor("!document.querySelector('.update-changelog')");
  console.log('PASS: real changelog opens and closes, renderer remains responsive');
  // Long malformed notes must not monopolize the window's event loop.
  await js("window.__dialogFixture.markdown = '['.repeat(100000); window.__dialogFixture.ticks = 0; window.__dialogFixture.timer = setInterval(() => window.__dialogFixture.ticks++, 10)");
  await js("[...document.querySelectorAll('button')].find(b => b.textContent === '查看更新日志').click()");
  await pause(200);
  assert.ok(await js('window.__dialogFixture.ticks >= 3'), 'Window event loop must keep responding during parsing');
  await js("[...document.querySelectorAll('.ant-modal button')].find(b => b.textContent === '关闭').click()");
  await waitFor("!document.querySelector('.ant-modal')");
  await js("window.__dialogFixture.NativeWorker = window.Worker; window.Worker = class { postMessage() {} terminate() {} }; void 0");
  await js("[...document.querySelectorAll('button')].find(b => b.textContent === '查看更新日志').click()");
  await waitFor("document.querySelector('.update-changelog')?.textContent.includes('已切换为纯文本')");
  await js("[...document.querySelectorAll('.ant-modal button')].find(b => b.textContent === '关闭').click(); clearInterval(window.__dialogFixture.timer); window.Worker = window.__dialogFixture.NativeWorker; void 0");
  await waitFor("!document.querySelector('.ant-modal')");
  console.log('PASS: malformed notes cannot block UI; closing cancels parsing and timeout falls back to text');
  if (!process.argv.includes('--changelog-only')) {
    await js("document.querySelector('.rb-titlebar-button-close').click()");
    await waitFor("document.querySelector('.ant-modal')?.textContent.includes('退出 RenpyBox')");
    await pause(400);
    assert.equal(await js("getComputedStyle(document.querySelector('.ant-modal')).opacity"), '1');
    const modalPosition = await js("(() => { const r = document.querySelector('.ant-modal').getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2, width: innerWidth, height: innerHeight }; })()");
    assert.ok(Math.abs(modalPosition.x - modalPosition.width / 2) < 2, 'Exit dialog must be horizontally centered');
    assert.ok(Math.abs(modalPosition.y - modalPosition.height / 2) < 2, 'Exit dialog must be vertically centered');
    win.webContents.invalidate();
    await pause(100);
    fs.writeFileSync(path.join(output, 'exit-confirm.png'), (await win.webContents.capturePage()).toPNG());
    assert.equal(await js('window.__dialogFixture.confirmed'), 0);
    await js("[...document.querySelectorAll('.ant-modal button')].find(b => b.textContent === '取消').click()");
    await waitFor("!document.querySelector('.ant-modal')");
    await js('window.__dialogFixture.closeListener()');
    await waitFor("Boolean(document.querySelector('.ant-modal'))");
    await js("[...document.querySelectorAll('.ant-modal button')].find(b => b.textContent === '退出').click()");
    await waitFor('window.__dialogFixture.confirmed === 1');
    console.log('PASS: titlebar/system close use Ant dialogs, cancel preserves window, confirm closes once');
  }
  if (process.argv.includes('--workflows')) {
    const clickText = async (text, scope = 'button') => {
      await js(`[...document.querySelectorAll(${JSON.stringify(scope)})].find(e => e.textContent.trim() === ${JSON.stringify(text)}).click()`);
    };
    const editText = async (value) => {
      await js(`(() => { const e = document.querySelector('[aria-label="提示词编辑内容"]'); Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(e, ${JSON.stringify(value)}); e.dispatchEvent(new Event('input', { bubbles: true })); })()`);
    };
    const capture = async (name) => {
      win.webContents.invalidate(); await pause(100);
      fs.writeFileSync(path.join(output, name + '.png'), (await win.webContents.capturePage()).toPNG());
    };
    await waitFor("!document.querySelector('.ant-modal')");
    await clickText('翻译提示', '.nav-item');
    await waitFor("[...document.querySelectorAll('button')].some(e => e.textContent === '编辑提示词')");
    await clickText('编辑提示词');
    await waitFor("Boolean(document.querySelector('[aria-label=\"提示词编辑内容\"]'))");
    assert.match(await js("document.querySelector('[aria-label=\"提示词编辑内容\"]').value"), /\{target_language\}/);
    const writesBefore = await js('window.__dialogFixture.patches.length');
    await editText('未保存的内容');
    assert.equal(await js('window.__dialogFixture.patches.length'), writesBefore, 'Typing must not autosave');
    await clickText('取消', '.ant-modal button');
    await waitFor("document.body.textContent.includes('放弃未保存的提示词？')");
    await clickText('放弃修改', '.ant-modal button');
    await waitFor("!document.querySelector('.ant-modal')");
    assert.equal(await js('window.__dialogFixture.patches.length'), writesBefore, 'Discard must not write settings');
    await clickText('编辑提示词');
    await waitFor("Boolean(document.querySelector('[aria-label=\"提示词编辑内容\"]'))");
    const editedBase = '将{source_language}翻译为{target_language}，保留人物语气。';
    await editText(editedBase);
    await clickText('写作风格', '.ant-modal [role=tab]');
    await editText('简洁自然，避免过度解释。');
    await capture('prompt-editor');
    await js('window.__dialogFixture.failSave = true');
    await clickText('保存并应用', '.ant-modal button');
    await waitFor("document.body.textContent.includes('Simulated save failure')");
    assert.equal(await js("document.querySelector('[aria-label=\"提示词编辑内容\"]').value"), '简洁自然，避免过度解释。', 'Save failure must retain the draft');
    await js('window.__dialogFixture.failSave = false');
    await clickText('保存并应用', '.ant-modal button');
    await waitFor("!document.querySelector('.ant-modal')");
    const saved = await js('window.__dialogFixture.patches.at(-1)');
    assert.equal(saved.translation_prompt_mode, 'CUSTOM');
    assert.equal(saved.translation_custom_prompts.ZH, editedBase);
    assert.equal(saved.translation_custom_prompts.EN, 'Preserve this draft');
    assert.equal(saved.translation_style_id, 'CUSTOM');
    await clickText('查看当前提示词');
    await waitFor("Boolean(document.querySelector('[aria-label=\"提示词预览内容\"]'))");
    assert.match(await js("document.querySelector('[aria-label=\"提示词预览内容\"]').value"), /保留人物语气/);
    await clickText('关闭', '.ant-modal button');
    await js("document.querySelectorAll('.rb-toasts .ant-alert-close-icon').forEach(e => e.click())");
    console.log('PASS: prompt editing preserves placeholders, cancels without writes, retains failed drafts and saves both sections');

    const openTool = async (title) => {
      await clickText("Ren'Py 工具箱", '.nav-item');
      await waitFor("Boolean(document.querySelector('.tool-card'))");
      await js(`[...document.querySelectorAll('.tool-card')].find(e => e.querySelector('.rb-tool-title')?.textContent === ${JSON.stringify(title)}).click()`);
    };
    await openTool('RPY 抽取设置');
    await waitFor("Boolean(document.querySelector('[data-rb-page=\"rpy-extraction\"] .ant-select'))");
    const categoryRect = await js("document.querySelector('[data-rb-page=\"rpy-extraction\"] .ant-select').getBoundingClientRect().toJSON()");
    const categoryPoint = { x: Math.round(categoryRect.x + 80), y: Math.round(categoryRect.y + categoryRect.height / 2) };
    win.webContents.sendInputEvent({ type: 'mouseDown', button: 'left', clickCount: 1, ...categoryPoint });
    win.webContents.sendInputEvent({ type: 'mouseUp', button: 'left', clickCount: 1, ...categoryPoint });
    await waitFor("Boolean(document.querySelector('.ant-select-dropdown:not(.ant-select-dropdown-hidden) [title=\"TL RPY（读 tl/<语言> 目录）\"]'))");
    await pause(300);
    const categoryPopup = await js("document.querySelector('.ant-select-dropdown:not(.ant-select-dropdown-hidden)').getBoundingClientRect().toJSON()");
    assert.ok(Math.abs(categoryPopup.left - categoryRect.left) < 3);
    assert.ok(categoryPopup.top >= categoryRect.bottom && categoryPopup.top < categoryRect.bottom + 12);
    await capture('rpy-category');
    await js("document.querySelector('.ant-select-dropdown:not(.ant-select-dropdown-hidden) [title=\"TL RPY（读 tl/<语言> 目录）\"]').click()");
    await waitFor("document.querySelector('[data-rb-page=\"rpy-extraction\"] .ant-select').textContent.includes('TL RPY')");
    console.log('PASS: RPY category dropdown opens in place and switches category');

    for (const width of [1280, 1024]) {
      win.setContentSize(width, 800);
      await openTool('直接翻译 RPY');
      await waitFor("Boolean(document.querySelector('.rb-direct-path'))");
      await pause(200);
      const pathsAligned = await js("[...document.querySelectorAll('.rb-direct-path')].every(e => Math.abs(e.querySelector('input').getBoundingClientRect().top - e.querySelector('button').getBoundingClientRect().top) < 2)");
      assert.equal(pathsAligned, true, `Path selectors must stay beside inputs at ${width}px`);
      await capture('direct-' + width);
      await openTool('检查与润色');
      await waitFor("Boolean(document.querySelector('.rb-proof-table')) && document.querySelector('.rb-proof-table-scroll').getAttribute('aria-busy') === 'false'");
      await pause(300);
      const alignment = await js("(() => { const heading = document.querySelector('.rb-page-header').getBoundingClientRect(); const actions = document.querySelector('.rb-proofreading-actions').getBoundingClientRect(); const search = document.querySelector('.rb-proof-search-row').getBoundingClientRect(); return { gap: actions.top - heading.bottom, left: actions.left - heading.left, searchLeft: search.left - actions.left, searchWidth: search.width, actionsWidth: actions.width }; })()");
      assert.ok(alignment.gap < 24 && Math.abs(alignment.left) < 5, `Proofreading toolbar must align with the page heading: ${JSON.stringify(alignment)}`);
      assert.ok(Math.abs(alignment.searchLeft) < 2 && Math.abs(alignment.searchWidth - alignment.actionsWidth) < 2, 'Search row must fill the workspace');
      const tableBounds = await js("(() => { const root = document.querySelector('.rb-proof-table-scroll'); const head = root.querySelector('.ant-table-header table'); return { width: root.clientWidth, header: head?.getBoundingClientRect().width }; })()");
      assert.ok(tableBounds.header <= tableBounds.width + 2, `Table should fit the available width: ${JSON.stringify(tableBounds)}`);
      await capture('proofreading-empty-' + width);
    }
    await js("window.__dialogFixture.proofRows = [{id:0,version:'one',src:'Hello, [player_name]!',dst:'你好，[player_name]！',status:'TRANSLATED',file_path:'story.rpy',row:4,warnings:[]}]");
    await clickText('刷新译文');
    await waitFor("document.querySelector('.rb-proof-table').textContent.includes('Hello, [player_name]!')");
    await capture('proofreading-rows');
    console.log('PASS: direct translation path rows align; empty and populated proofreading tables render at desktop widths');
  }
  assert.deepEqual(errors, []);
  console.log(`Screenshots: ${output}`);
  clearTimeout(watchdog);
  win.destroy();
  app.exit(0);
}).catch(error => { console.error(error); clearTimeout(watchdog); app.exit(1); });
