/** Capture README desktop screenshots from the built React UI (isolated HTTP/WS fixture). */
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

const output = path.resolve(__dirname, '../../docs/screenshots');
fs.mkdirSync(output, { recursive: true });
app.setPath('userData', fs.mkdtempSync(path.join(os.tmpdir(), 'renpybox-readme-capture-')));

const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const watchdog = setTimeout(() => { console.error('README capture timed out'); app.exit(2); }, 120000);
const UPSTREAM_CONSOLE_WARNINGS = [/rc-virtual-list` reach the max limitation/];

const scenarios = [
  { file: 'desktop-translation-zh.png', theme: 'DARK', lang: 'ZH', width: 1600, height: 1000, page: 'translation' },
  { file: 'desktop-translation-en.png', theme: 'DARK', lang: 'EN', width: 1600, height: 1000, page: 'translation' },
  { file: 'desktop-toolbox-zh.png', theme: 'LIGHT', lang: 'ZH', width: 1600, height: 1120, page: 'toolbox' },
  { file: 'desktop-toolbox-en.png', theme: 'LIGHT', lang: 'EN', width: 1600, height: 1120, page: 'toolbox' },
  { file: 'desktop-proofreading-zh.png', theme: 'DARK', lang: 'ZH', width: 1600, height: 1000, page: 'proofreading' },
  { file: 'desktop-workbench-zh.png', theme: 'LIGHT', lang: 'ZH', width: 1600, height: 1000, page: 'workbench' },
];

function configure(scenario) {
  const f = window.__uiFixture;
  const values = f.values;
  values.theme = scenario.theme;
  values.app_language = scenario.lang;
  values.source_language = 'EN';
  values.target_language = 'ZH';
  values.input_folder = 'C:/Games/HarborLetters/game/tl/chinese';
  values.output_folder = 'C:/Games/HarborLetters/output';
  values.expert_mode = true;
  values.activate_platform = 0;
  values.platforms = scenario.lang === 'EN'
    ? [
        { id: 0, name: 'Primary API', group: 'online', model: 'story-model', api_format: 'OpenAI', api_url: 'https://api.example.com/v1', api_key: '***' },
        { id: 1, name: 'Local Sakura', group: 'local', model: 'sakura', api_format: 'SakuraLLM', api_url: 'http://localhost:8080/v1', api_key: '***' },
      ]
    : [
        { id: 0, name: '主翻译接口', group: 'online', model: 'story-model', api_format: 'OpenAI', api_url: 'https://api.example.com/v1', api_key: '***' },
        { id: 1, name: '本地翻译模型', group: 'local', model: 'sakura', api_format: 'SakuraLLM', api_url: 'http://localhost:8080/v1', api_key: '***' },
      ];
  f.assetProjectRoot = 'C:/Games/HarborLetters';
  f.assetProjectKey = 'c:\\games\\harborletters|chinese';
  f.engineStatus = 'IDLE';
  f.items = [
    { id: 0, version: 'v1', src: 'Alice, the letter arrived this morning.', dst: '艾丽丝，那封信今天早上到了。', status: 'TRANSLATED', file_path: 'script.rpy', row: 42 },
    { id: 1, version: 'v1', src: 'I left it on the kitchen table, by the window.', dst: '我把它放在厨房窗边的桌上了。', status: 'TRANSLATED', file_path: 'script.rpy', row: 48 },
    { id: 2, version: 'v1', src: 'The handwriting looks familiar… almost like yours.', dst: '字迹有些眼熟……几乎就像你的。', status: 'TRANSLATED', file_path: 'script.rpy', row: 55 },
    { id: 3, version: 'v1', src: 'Meet me at the harbor before the tide turns.', dst: '趁潮水还没涨起来，到港湾来见我。', status: 'TRANSLATED', file_path: 'chapter_02.rpy', row: 18 },
    { id: 4, version: 'v1', src: 'If you are late, I will wait by the lighthouse.', dst: '要是你来迟了，我会在灯塔旁等你。', status: 'TRANSLATED', file_path: 'chapter_02.rpy', row: 24 },
    { id: 5, version: 'v1', src: 'Some letters are meant to be opened twice.', dst: '有些信，本来就该被拆开两次。', status: 'TRANSLATED', file_path: 'chapter_02.rpy', row: 31 },
  ];
  f.progress = {
    line: 128, total_line: 200, time: 240, total_output_tokens: 9600, status: 'TRANSLATING',
    throughput: { schema_version: 1, elapsed_seconds: 240, output_tokens: 9600, effective_items_per_minute: 32 },
    recent_items: [
      { time: '14:02:18', src: 'Alice, the letter arrived this morning.', dst: '艾丽丝，那封信今天早上到了。' },
      { time: '14:02:21', src: 'I left it on the kitchen table, by the window.', dst: '我把它放在厨房窗边的桌上了。' },
      { time: '14:02:25', src: 'Meet me at the harbor before the tide turns.', dst: '趁潮水还没涨起来，到港湾来见我。' },
      { time: '14:02:28', src: 'If you are late, I will wait by the lighthouse.', dst: '要是你来迟了，我会在灯塔旁等你。' },
    ],
  };
  f.progressSource = 'cache';
  f.assets.storage_key = 'harbor-letters';
  f.assets.revision = 1;
  f.assets.worldbook = {
    project_name: '港湾来信',
    genre: '日常 / 悬疑',
    setting_summary: '一座靠海的小镇，一封迟到的信。人物的语气平静而克制。',
    tone_style: '自然口语，保留人物之间的距离感',
    era_background: '当代海边小镇，灯塔与旧邮局仍在运转',
    narrative_rules: '对白简洁，不点破所有秘密',
    format_rules: '',
    spoiler_notes: '',
    reference_notes: 'Harbor Letters · 港湾来信',
  };
  f.assets.characters = [
    {
      id: 'alice', name: 'Alice', name_translation: '艾丽丝', aliases: ['A.'], match_keywords: ['Alice', '艾丽丝'],
      identity: '港口小镇的居民，收到一封迟到的信', personality: '温和、克制', speech_style: '简短自然',
      relationship_notes: '与灯塔管理员相识多年', prompt_notes: '保持平静语气', sample_lines: ['那封信今天早上到了。'], enabled: true, is_primary: true,
    },
    {
      id: 'keeper', name: 'Keeper', name_translation: '灯塔管理员', aliases: ['Bob'], match_keywords: ['Keeper', '灯塔'],
      identity: '灯塔管理员', personality: '寡言、可靠', speech_style: '短句，偶尔留下未说完的话',
      relationship_notes: '守着港湾的潮汐时刻表', prompt_notes: '语气沉稳', sample_lines: ['潮水转之前到港湾来。'], enabled: true, is_primary: false,
    },
  ];
  f.assets.worldbook_enabled = true;
  f.assets.characters_enabled = true;
  f.assets.worldbook_draft = {};
  f.assets.character_drafts = [];
  f.glossary.storage_key = 'harbor-letters';
  f.glossary.rows = [
    { src: 'Harbor', dst: '港湾', info: '地名', candidate: false, record_id: 'h1' },
    { src: 'Sealed Letter', dst: '封缄的信', info: '关键道具', candidate: false, record_id: 'h2' },
  ];
  f.glossary.candidate_ids = [];
  f.workbenchJob = null;
  f.qualityReports = [];
  localStorage.setItem('renpybox.theme', scenario.theme);
}

app.on('window-all-closed', () => {});
app.whenReady().then(async () => {
  for (const scenario of scenarios) {
    console.log('CAPTURE ' + scenario.file);
    const win = new BrowserWindow({
      width: scenario.width, height: scenario.height, show: false, frame: false,
      webPreferences: { offscreen: true, backgroundThrottling: false, sandbox: true, contextIsolation: true },
    });
    const errors = [];
    win.webContents.on('console-message', (event) => {
      if (event.level !== 'error') return;
      if (UPSTREAM_CONSOLE_WARNINGS.some(pattern => pattern.test(event.message))) return;
      errors.push(event.message);
    });
    await win.loadURL('about:blank');
    win.webContents.debugger.attach('1.3');
    await win.webContents.debugger.sendCommand('Page.enable');
    await win.webContents.debugger.sendCommand('Emulation.setDeviceMetricsOverride', {
      width: scenario.width,
      height: scenario.height,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await win.webContents.debugger.sendCommand('Emulation.setEmulatedMedia', {
      features: [{ name: 'prefers-reduced-motion', value: 'reduce' }],
    });
    await win.webContents.debugger.sendCommand('Page.addScriptToEvaluateOnNewDocument', {
      source: `(${fixture})(); (${configure.toString()})(${JSON.stringify(scenario)});`,
    });
    win.setContentSize(scenario.width, scenario.height);
    await win.loadFile(path.join(__dirname, '../dist/index.html'));

    const js = code => win.webContents.executeJavaScript(code);
    const waitFor = async (code, label = code) => {
      for (let i = 0; i < 100; i++) {
        if (await js(code)) return;
        await pause(50);
      }
      throw new Error(`${scenario.file}: timeout: ${label}`);
    };
    const page = async title => {
      await js(`Array.from(document.querySelectorAll('.nav-item')).find(b=>b.title===${JSON.stringify(title)})?.click()`);
      await pause(200);
    };
    const dismiss = async () => {
      await js(`document.querySelectorAll('.banner button').forEach(b=>{if(/知道了|Dismiss|Got it/i.test(b.textContent))b.click()})`);
      await js(`document.querySelectorAll('[data-rb-toast] button').forEach(b=>b.click())`);
      await pause(120);
    };

    await waitFor("!!document.querySelector('.translation-layout') || !!document.querySelector('.rb-nav-item')", 'shell ready');
    await waitFor("document.documentElement.dataset.theme===" + JSON.stringify(scenario.theme), 'theme');
    await pause(400);

    if (scenario.page === 'translation') {
      const title = scenario.lang === 'EN' ? 'Translation Task' : '翻译任务';
      await page(title);
      await waitFor("!!document.querySelector('.translation-layout') && document.querySelector('.rb-progress-percent')", 'translation ready');
      await waitFor("document.querySelector('.workspace-project')?.textContent.includes('HarborLetters')", 'project name');
      await waitFor("Number(document.querySelectorAll('.feed-card .ant-table-row').length) >= 1 || document.body.textContent.includes('艾丽丝')", 'feed rows');
    } else if (scenario.page === 'toolbox') {
      const title = scenario.lang === 'EN' ? "Ren'Py Toolbox" : "Ren'Py 工具箱";
      await page(title);
      await waitFor("document.querySelectorAll('.tool-card').length === 27", '27 tools');
    } else if (scenario.page === 'proofreading') {
      await page("Ren'Py 工具箱");
      await waitFor("!!document.querySelector('.rb-toolbox')", 'toolbox');
      await js(`(()=>{const input=document.querySelector('.toolbox-search input, input.toolbox-search');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,'检查与润色');input.dispatchEvent(new Event('input',{bubbles:true}));})()`);
      await waitFor("document.querySelectorAll('.tool-card').length >= 1", 'proof tool');
      await js("document.querySelector('.tool-card')?.click()");
      await waitFor("!!document.querySelector('.proofreading-page,.rb-proof-table') && document.querySelectorAll('.rb-proofreading-row,.ant-table-row').length >= 4", 'proof rows');
    } else if (scenario.page === 'workbench') {
      await page('角色 / 世界观工作台');
      await waitFor("!!document.querySelector('.rb-workbench-summary') && document.body.textContent.includes('港湾来信')", 'workbench');
      await waitFor("document.querySelector('.rb-workbench-stats')?.textContent.includes('2')", 'two characters');
    }

    await dismiss();
    await js('document.fonts ? document.fonts.ready : true');
    await pause(500);

    const forbidden = await js(`(()=>{
      const text = document.body.innerText || '';
      const hits = ['ui-check','fixture','Saved source','测试词','自检'].filter(word => text.includes(word));
      const toasts = [...document.querySelectorAll('[data-rb-toast]')].map(e => e.textContent.trim()).filter(Boolean);
      const errorToasts = toasts.filter(t => /失败|错误|error|failed/i.test(t));
      return { hits, errorToasts, toasts };
    })()`);
    assert.deepEqual(forbidden.hits, [], `${scenario.file}: forbidden demo words`);
    assert.deepEqual(forbidden.errorToasts, [], `${scenario.file}: error toasts`);
    assert.deepEqual(errors, [], `${scenario.file}: renderer errors`);

    const shot = await win.webContents.debugger.sendCommand('Page.captureScreenshot', {
      format: 'png',
      captureBeyondViewport: false,
      fromSurface: true,
      clip: { x: 0, y: 0, width: scenario.width, height: scenario.height, scale: 1 },
    });
    const png = Buffer.from(shot.data, 'base64');
    fs.writeFileSync(path.join(output, scenario.file), png);
    console.log(`WROTE ${scenario.file} (${scenario.width}x${scenario.height}, ${png.length} bytes)`);
    win.destroy();
  }
  clearTimeout(watchdog);
  console.log('ALL README SCREENSHOTS CAPTURED');
  app.exit(0);
}).catch(error => {
  console.error(error);
  clearTimeout(watchdog);
  app.exit(1);
});
