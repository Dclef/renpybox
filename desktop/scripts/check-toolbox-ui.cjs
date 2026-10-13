/** Toolbox rendering and navigation checks against the built React UI, with isolated HTTP/WS fixtures. */
const { app, BrowserWindow } = require('electron');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, 'check-ui.cjs'), 'utf8');
const start = source.indexOf('function fixture()');
const end = source.indexOf('\napp.whenReady()', start);
assert(start >= 0 && end > start, 'Shared UI fixture must be available');
const version = JSON.parse(fs.readFileSync(path.join(__dirname, '../package.json'), 'utf8')).version;
const fixture = source.slice(start, end).replaceAll("'v0.8.1'", JSON.stringify('v' + version));
const output = process.env.RENPYBOX_UI_CAPTURE_DIR || path.join(os.tmpdir(), 'renpybox-toolbox-ui');
fs.mkdirSync(output, { recursive: true });
app.setPath('userData', fs.mkdtempSync(path.join(os.tmpdir(), 'renpybox-toolbox-check-')));
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const watchdog = setTimeout(() => { console.error('Toolbox checks timed out'); app.exit(2); }, 60000);
const scenarios = [
  { name: 'light-1280', theme: 'LIGHT', lang: 'ZH', width: 1280, height: 800, bound: true },
  { name: 'dark-1280', theme: 'DARK', lang: 'ZH', width: 1280, height: 800, bound: true },
  { name: 'english-900', theme: 'DARK', lang: 'EN', width: 900, height: 640, bound: true },
  { name: 'unbound-900', theme: 'LIGHT', lang: 'ZH', width: 900, height: 640, bound: false },
  { name: 'english-1440', theme: 'LIGHT', lang: 'EN', width: 1440, height: 800, bound: true },
];
function configure({ theme, lang, bound }) {
  window.__uiFixture.values.theme = theme;
  window.__uiFixture.values.app_language = lang;
  localStorage.setItem('renpybox.theme', theme);
  if (!bound) {
    const previous = window.fetch;
    window.fetch = (url, options) => new URL(String(url), location.href).pathname === '/api/project'
      ? Promise.resolve(new Response(JSON.stringify({ renpy_project_path: '', renpy_game_folder: '', renpy_tl_folder: '' }), { headers: { 'Content-Type': 'application/json' } }))
      : previous(url, options);
  }
}
app.on('window-all-closed', () => {});
app.whenReady().then(async () => {
  for (const scenario of scenarios) {
    console.log(`CHECK ${scenario.name}`);
    const win = new BrowserWindow({ width: scenario.width, height: scenario.height, show: false, frame: false,
      webPreferences: { offscreen: true, backgroundThrottling: false, sandbox: true, contextIsolation: true } });
    const errors = [];
    win.webContents.on('console-message', (event) => {
      if (event.level === 'error') errors.push(event.message);
    });
    await win.loadURL('about:blank');
    win.webContents.debugger.attach('1.3');
    await win.webContents.debugger.sendCommand('Page.enable');
    await win.webContents.debugger.sendCommand('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] });
    await win.webContents.debugger.sendCommand('Page.addScriptToEvaluateOnNewDocument', {
      source: `(${fixture})(); (${configure.toString()})(${JSON.stringify(scenario)});`,
    });
    await win.loadFile(path.join(__dirname, '../dist/index.html'));
    const js = code => win.webContents.executeJavaScript(code);
    const waitFor = async (code) => {
      for (let i = 0; i < 80; i++) { if (await js(code)) return; await pause(50); }
      throw new Error(`${scenario.name}: timeout: ${code}`);
    };
    await waitFor("Boolean([...document.querySelectorAll('.rb-nav-item')].find(el=>/工具箱|Toolbox/.test(el.textContent)))");
    await js("[...document.querySelectorAll('.rb-nav-item')].find(el=>/工具箱|Toolbox/.test(el.textContent)).click()");
    await waitFor("document.querySelectorAll('.tool-card').length === 27");
    assert.equal(await js("document.querySelectorAll('.tool-card:disabled').length"), scenario.bound ? 0 : 8, 'Project requirements must remain unchanged');
    assert.equal(await js("document.documentElement.dataset.theme"), scenario.theme);
    assert(await js("getComputedStyle(document.documentElement).getPropertyValue('--rb-text-tertiary').trim().length > 0"), 'Auxiliary text color must resolve');
    if (scenario.lang === 'EN') assert.equal(await js("/[\\u3400-\\u9fff]/.test(document.querySelector('.rb-toolbox').innerText)"), false, 'English toolbox must not leak Chinese copy');
    const overflow = await js(`Array.from(document.querySelectorAll('.rb-toolbox,.rb-toolbox-categories,.tool-card,.tool-card-head')).filter(el=>el.scrollWidth>el.clientWidth+1).map(el=>el.className)`);
    assert.deepEqual(overflow, [], 'Toolbox must fit the window');
    await pause(120);
    fs.writeFileSync(path.join(output, scenario.name + '.png'), (await win.webContents.capturePage()).toPNG());
    for (const [group, count] of [['flow', 9], ['translate', 7], ['asset', 4], ['engineer', 7]]) {
      await js(`document.querySelector('[data-tool-group="${group}"]').click()`);
      await waitFor(`document.querySelectorAll('.tool-card').length === ${count}`);
    }
    await js("document.querySelector('.rb-toolbox-categories > button').click()");
    await waitFor("document.querySelectorAll('.tool-card').length === 27");
    const search = async value => {
      await js(`(()=>{const input=document.querySelector('.toolbox-search input, input.toolbox-search');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,${JSON.stringify(value)});input.dispatchEvent(new Event('input',{bubbles:true}));})()`);
    };
    await search(scenario.lang === 'EN' ? 'untranslated' : '字体');
    await waitFor("document.querySelectorAll('.tool-card').length === 1");
    assert.equal(await js("document.querySelector('.tool-card').dataset.toolKey"), scenario.lang === 'EN' ? 'text_preserve' : 'font_replace');
    await search('no-tool-matches-this-query');
    await waitFor("Boolean(document.querySelector('.rb-toolbox-empty button'))");
    await js("document.querySelector('.rb-toolbox-empty button').click()");
    await waitFor("document.querySelectorAll('.tool-card').length === 27");
    await js("document.querySelector('.rb-toolbox-categories > button').focus()");
    await win.webContents.debugger.sendCommand('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 });
    await win.webContents.debugger.sendCommand('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 });
    assert.equal(await js("document.activeElement.dataset.toolGroup"), 'flow', 'Categories must be keyboard reachable');
    if (!scenario.bound) {
      await js("document.querySelector('.rb-toolbox-project-hint button').click()");
      await waitFor("!document.querySelector('.rb-toolbox') && document.querySelector('.rb-page-title')?.textContent.includes('项目设置')");
    }
    assert.deepEqual(errors, [], 'No renderer errors');
    console.log(`PASS ${scenario.name}: 27 tools, project gates, categories, search, reset, keyboard and layout`);
    win.destroy();
  }
  clearTimeout(watchdog);
  console.log('ALL TOOLBOX UI CHECKS PASSED');
  app.exit(0);
}).catch(error => { console.error(error); clearTimeout(watchdog); app.exit(1); });
