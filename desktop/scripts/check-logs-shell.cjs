/**
 * 运行日志窗口（shell/welcome.html）的端到端自检：导出日志 / 打开日志。
 *
 * 壳窗口不依赖 sidecar，所以这里用注入的假 bridge 驱动真实页面脚本，
 * 只验证「按钮 → bridge 调用 → 状态文案」这条链路，避免真机上手点一遍。
 * 用法：desktop> node_modules\.bin\electron.cmd scripts\check-logs-shell.cjs
 */
const { app, BrowserWindow } = require('electron');
const path = require('node:path');

const PAGE = path.join(__dirname, '..', 'shell', 'welcome.html');
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
let failures = 0;

function log(line) {
  process.stdout.write(line + '\n');
}

function check(ok, name, extra) {
  if (ok) log('PASS ' + name);
  else {
    failures += 1;
    log('FAIL ' + name + (extra === undefined ? '' : ' -> ' + JSON.stringify(extra)));
  }
}

// 在页面脚本执行前注入假 bridge；extra 用来逐条改变返回值以覆盖分支。
function stub() {
  const calls = [];
  const state = { text: 'line 1\nline 2\n', truncated: false, exportResult: null, revealResult: null };
  window.__shellStub = { calls, state };
  window.shellBridge = {
    isShellWindow: true,
    logs: {
      read: async (source) => {
        calls.push({ name: 'read', args: [source] });
        return { text: state.text, truncated: state.truncated };
      },
      copy: async (value) => {
        calls.push({ name: 'copy', args: [value] });
        return true;
      },
      export: async (source, snapshot) => {
        calls.push({ name: 'export', args: [source, snapshot] });
        return state.exportResult || { canceled: false, written: true, path: 'C:/out/renpybox-app.log', bytes: snapshot.length };
      },
      reveal: async (source) => {
        calls.push({ name: 'reveal', args: [source] });
        return state.revealResult || { kind: 'file', path: 'C:/log/app.log' };
      },
    },
    close: () => calls.push({ name: 'close', args: [] }),
  };
}

async function main() {
  const win = new BrowserWindow({
    width: 900,
    height: 700,
    show: false,
    webPreferences: { offscreen: true, contextIsolation: true, sandbox: true },
  });
  const consoleErrors = [];
  win.webContents.on('console-message', (event, level, message) => {
    const severity = event.level ?? level;
    const value = event.message ?? message;
    if (severity === 'error' || severity >= 3) consoleErrors.push(value);
  });
  await win.loadURL('about:blank');
  win.webContents.debugger.attach('1.3');
  await win.webContents.debugger.sendCommand('Page.enable');
  await win.webContents.debugger.sendCommand('Runtime.enable');
  await win.webContents.debugger.sendCommand('Page.addScriptToEvaluateOnNewDocument', {
    source: '(' + stub.toString() + ')()',
  });
  await win.loadFile(PAGE);

  const js = (code) => win.webContents.executeJavaScript(`(async()=>{${code}})()`, true);
  const text = (selector) => js(`return document.querySelector(${JSON.stringify(selector)})?.textContent ?? null;`);
  const disabled = (selector) => js(`return Boolean(document.querySelector(${JSON.stringify(selector)})?.disabled);`);
  const calls = () => js('return window.__shellStub.calls;');
  const setState = (patch) => js(`Object.assign(window.__shellStub.state, ${JSON.stringify(patch)}); return true;`);

  for (let i = 0; i < 60; i += 1) {
    if ((await text('#status')) && (await disabled('#export')) === false) break;
    await pause(100);
  }
  check((await text('#status') || '').startsWith('已刷新'), '日志读取后显示刷新时间', await text('#status'));
  check((await disabled('#export')) === false, '日志有内容时导出按钮可用');
  check((await disabled('#copy')) === false, '日志有内容时复制按钮可用');
  check((await text('#log-output')) === 'line 1\nline 2\n', '日志正文按纯文本呈现', await text('#log-output'));

  await js("document.getElementById('reveal').click(); return true;");
  await pause(200);
  const revealCalls = (await calls()).filter((call) => call.name === 'reveal');
  check(revealCalls.length === 1 && revealCalls[0].args[0] === 'app', '打开日志按当前来源调用 bridge', revealCalls);
  check((await text('#status')) === '已在文件管理器中定位日志文件', '打开日志后给出定位反馈', await text('#status'));

  await setState({ revealResult: { kind: 'directory', path: 'C:/log' } });
  await js("document.getElementById('reveal').click(); return true;");
  await pause(200);
  check((await text('#status')) === '日志文件尚未生成，已打开日志目录', '文件缺失时退化为打开目录并有文案', await text('#status'));

  await js("document.getElementById('export').click(); return true;");
  await pause(250);
  const exportCalls = (await calls()).filter((call) => call.name === 'export');
  check(exportCalls.length === 1, '点击导出只触发一次 bridge 调用', exportCalls.length);
  check(exportCalls[0]?.args[0] === 'app', '导出带上当前来源', exportCalls[0]?.args);
  check(exportCalls[0]?.args[1] === 'line 1\nline 2\n', '导出带上界面当前文本作为兜底', exportCalls[0]?.args?.[1]);
  check((await text('#status') || '').startsWith('已导出日志 · C:/out/renpybox-app.log'), '导出成功回显路径', await text('#status'));

  await setState({ exportResult: { canceled: true } });
  await js("document.getElementById('export').click(); return true;");
  await pause(250);
  check((await text('#status')) === '已取消导出', '取消导出不报错', await text('#status'));

  await setState({ exportResult: { canceled: false, written: false, bytes: 0 } });
  await js("document.getElementById('export').click(); return true;");
  await pause(250);
  check((await text('#status')) === '日志还没有内容，暂无可导出的文件', '空日志导出给出解释', await text('#status'));

  // 切到「启动与更新」来源后再导出，应带上 desktop。
  await setState({ exportResult: null });
  await js("const select=document.getElementById('source'); select.value='desktop'; select.dispatchEvent(new Event('change')); return true;");
  await pause(300);
  await js("document.getElementById('export').click(); return true;");
  await pause(250);
  const afterSwitch = (await calls()).filter((call) => call.name === 'export');
  check(afterSwitch.at(-1)?.args[0] === 'desktop', '切换来源后导出跟随来源', afterSwitch.at(-1)?.args);

  const fatal = consoleErrors.filter((line) => !/rc-virtual-list/.test(line));
  check(fatal.length === 0, '壳页面没有控制台错误', fatal);
  win.destroy();
  log(failures === 0 ? 'ALL LOG SHELL CHECKS PASSED' : 'LOG SHELL CHECKS FAILED: ' + failures);
  app.exit(failures === 0 ? 0 : 1);
}

app.whenReady().then(main).catch((error) => {
  log('FATAL ' + (error && error.stack ? error.stack : error));
  app.exit(1);
});
