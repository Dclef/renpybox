import assert from 'node:assert/strict';
import path from 'node:path';
import test from 'node:test';
import {
  compareDesktopVersions,
  createDesktopUpdater,
  parseDesktopVersion,
  pickLatestRelease,
  selectInstallerAsset,
} from '../main/updater.js';

const tick = () => new Promise(setImmediate);
const installer = version => ({ name: `RenpyBox-NewUI-${version}-x64.exe`, size: 280000000, browser_download_url: `https://example.test/renpybox/renpybox-newui-${version}-x64.exe` });
const release = (version, { assets, draft = false, prerelease = true } = {}) => ({
  tag_name: `v${version}`,
  html_url: `https://github.com/example/renpybox/releases/tag/v${version}`,
  body: `notes for ${version}`,
  draft,
  prerelease,
  assets: assets ?? [installer(version)],
});

function fixture({
  packaged = true,
  currentVersion = '0.8.2-newui.1',
  releases = [],
  requestError = null,
  downloadError = null,
  launchError = null,
  holdDownload = false,
  beforeInstall = async () => {},
} = {}) {
  const requests = [];
  const downloads = [];
  const launches = [];
  const quits = [];
  const states = [];
  const downloadSignals = [];
  let releaseDownload = () => {};
  const gate = new Promise(resolve => { releaseDownload = resolve; });
  const updater = createDesktopUpdater({
    packaged,
    version: currentVersion,
    tempDir: path.join('tmp', 'renpybox-update'),
    broadcast: state => states.push(state),
    log: Object.assign(() => {}, { error: () => {} }),
    beforeInstall,
    quit: () => quits.push(true),
    requestJson: async (url) => {
      requests.push(url);
      if (requestError) throw requestError;
      return releases;
    },
    downloadFile: async (url, destination, options = {}) => {
      downloads.push({ url, destination });
      downloadSignals.push(options.signal);
      options.onProgress?.({ received: 100, total: 400 });
      if (holdDownload) await gate;
      if (options.signal?.aborted) throw Object.assign(new Error('The operation was aborted'), { name: 'AbortError' });
      options.onProgress?.({ received: 400, total: 400 });
      if (downloadError) throw downloadError;
      return { path: destination, size: 400, total: 400 };
    },
    launchInstaller: async (filePath) => {
      if (launchError) throw launchError;
      launches.push(filePath);
    },
  });
  return { updater, requests, downloads, launches, quits, states, signals: () => downloadSignals, release: () => releaseDownload() };
}

test('支持正式版与旧测试版；标签只提供版本号，是否桌面发布由安装包资产决定', () => {
  assert.equal(parseDesktopVersion('0.9.0').build, null);
  assert.deepEqual(parseDesktopVersion('RenpyBox_v0.9.0'), parseDesktopVersion('v0.9.0'));
  assert.equal(parseDesktopVersion('0.9.0-beta.1'), null);
  assert.equal(parseDesktopVersion('RenpyBox_NewUI_v0.9.0'), null);
  assert.equal(compareDesktopVersions('0.9.0', '0.9.0-newui.99'), 1);
  assert.equal(compareDesktopVersions('0.9.0-newui.99', '0.9.0'), -1);
  assert.equal(compareDesktopVersions('0.9.0', 'v0.9.0'), 0);
  assert.equal(compareDesktopVersions('0.10.0', '0.9.99'), 1);
  assert.equal(parseDesktopVersion('v0.8.2-newui.1').build, 1);
  assert.equal(parseDesktopVersion('0.8.2-newui.1').patch, 2);
  assert.equal(compareDesktopVersions('0.8.2-newui.2', '0.8.2-newui.1'), 1);
  assert.equal(compareDesktopVersions('0.8.2-newui.10', '0.8.2-newui.9'), 1);
  assert.equal(compareDesktopVersions('0.8.3-newui.1', '0.8.2-newui.99'), 1);
  assert.equal(compareDesktopVersions('0.8.2-newui.1', '0.8.2-newui.1'), 0);
  assert.equal(compareDesktopVersions('0.8.2-newui.1', 'v0.8.2-newui.1'), 0);
});

test('只认带桌面 Windows 安装包资产的发布', () => {
  const zipOnly = release('0.8.2-newui.9', { assets: [{ name: 'RenpyBox-NewUI-0.8.2-newui.9-x64.zip' }] });
  assert.equal(selectInstallerAsset(zipOnly), null);
  assert.equal(pickLatestRelease([zipOnly], '0.8.2-newui.1'), null);
  const qt = { ...release('0.9.0', { prerelease: false, assets: [{ name: 'RenpyBox_v0.9.0.zip' }] }), tag_name: 'RenpyBox_v0.9.0' };
  assert.equal(pickLatestRelease([qt], '0.8.2-newui.1'), null, 'Qt 发布不能被当作桌面更新');
  assert.equal(pickLatestRelease([release('0.9.0', { assets: qt.assets })], '0.8.2-newui.1'), null);
  // 同一标签只要带上与标签版本同名的安装包，就是桌面发布（0.9.0 起 Qt 与桌面共用 vX.Y.Z）。
  const unified = { ...release('0.9.0', { prerelease: false }), tag_name: 'RenpyBox_v0.9.0' };
  assert.equal(selectInstallerAsset(unified)?.name, 'RenpyBox-NewUI-0.9.0-x64.exe');
  assert.equal(pickLatestRelease([unified], '0.8.2-newui.1'), unified);
  // 安装包版本与标签不一致（旧包误传）时不得下载。
  const mismatched = { ...release('0.9.1', { prerelease: false, assets: [installer('0.9.0')] }) };
  assert.equal(selectInstallerAsset(mismatched), null);
  assert.equal(pickLatestRelease([mismatched], '0.8.2-newui.1'), null);
});

test('测试版能升级到正式版，正式版跳过预发布和草稿', async () => {
  const stable = release('0.9.0', { prerelease: false });
  assert.equal(pickLatestRelease([stable], '0.8.2-newui.2'), stable);
  assert.equal(pickLatestRelease([stable], '0.9.0'), null);
  const next = release('0.9.1', { prerelease: false });
  const f = fixture({ currentVersion: '0.9.0', releases: [
    stable, next, release('0.10.0-newui.1'), release('0.10.0', { prerelease: true }),
    release('0.11.0', { draft: true, prerelease: false }),
  ] });
  const offered = await f.updater.check();
  assert.equal(offered.version, '0.9.1');
  const done = await f.updater.download();
  assert.equal(done.status, 'downloaded');
  assert.equal(done.filePath, path.join('tmp', 'renpybox-update', 'RenpyBox-NewUI-0.9.1-x64.exe'));
});

test('开发模式不检查、不下载、不安装', async () => {
  const f = fixture({ packaged: false });
  assert.equal((await f.updater.check()).status, 'dev');
  assert.equal(f.requests.length, 0);
  await assert.rejects(f.updater.download(), /开发模式/);
  await assert.rejects(f.updater.install(), /开发模式/);
  assert.equal(f.launches.length, 0);
  assert.equal(f.quits.length, 0);
});

test('并发检查共用一次请求', async () => {
  const f = fixture({ releases: [release('0.8.2-newui.2')] });
  const [first, second] = await Promise.all([f.updater.check(), f.updater.check()]);
  assert.equal(f.requests.length, 1);
  assert.equal(first.status, 'available');
  assert.equal(second.status, 'available');
});

test('挑出比当前版本新的最新一条发布', async () => {
  const f = fixture({
    releases: [
      { ...release('0.8.3', { prerelease: false, assets: [{ name: 'RenpyBox_v0.8.3.zip', size: 227000000, browser_download_url: 'https://example.test/renpybox/RenpyBox_v0.8.3.zip' }] }), tag_name: 'RenpyBox_v0.8.3' },
      release('0.8.2-newui.1'),
      release('0.8.2-newui.2'),
      release('0.8.2-newui.9', { draft: true }),
      release('0.9.0-newui.1', { assets: [{ name: 'RenpyBox-NewUI-0.9.0-newui.1-x64.zip' }] }),
    ],
  });
  const state = await f.updater.check();
  assert.equal(state.status, 'available');
  assert.equal(state.version, '0.8.2-newui.2');
  assert.equal(state.releaseUrl, 'https://github.com/example/renpybox/releases/tag/v0.8.2-newui.2');
  assert.equal(state.releaseNotes, 'notes for 0.8.2-newui.2');
  assert.match(f.requests[0], /api[.]github[.]com\/repos\/dclef\/renpybox\/releases/);
});

test('已是最新时给出 latest 而不是错误', async () => {
  const f = fixture({ releases: [release('0.8.2-newui.1')] });
  assert.equal((await f.updater.check()).status, 'latest');
  const empty = fixture({ releases: [] });
  const state = await empty.updater.check();
  assert.equal(state.status, 'latest');
  assert.equal(state.error, '');
});

test('没有可用的桌面发布时给出可读文案', async () => {
  const notPublished = fixture({ requestError: Object.assign(new Error('仓库或版本不存在'), { kind: 'not-published' }) });
  const state = await notPublished.updater.check();
  assert.equal(state.status, 'error');
  assert.match(state.error, /尚未发布可用的桌面版本/);
  const limited = fixture({ requestError: Object.assign(new Error('GitHub 返回 403'), { kind: 'rate-limited' }) });
  assert.match((await limited.updater.check()).error, /频率限制/);
  const offline = fixture({ requestError: Object.assign(new Error('fetch failed'), { kind: 'network' }) });
  assert.match((await offline.updater.check()).error, /无法连接 GitHub：fetch failed/);
});

test('下载报告进度并在完成后进入 downloaded', async () => {
  const f = fixture({ releases: [release('0.8.2-newui.2')] });
  const offered = await f.updater.check();
  const downloading = f.updater.download();
  assert.equal(f.updater.state().status, 'downloading');
  const done = await downloading;
  assert.equal(done.status, 'downloaded');
  assert.equal(done.progress, 100);
  assert.equal(done.filePath, path.join('tmp', 'renpybox-update', 'RenpyBox-NewUI-0.8.2-newui.2-x64.exe'));
  assert.equal(f.downloads.length, 1);
  assert.equal(f.downloads[0].url, offered.assetUrl);
  assert.ok(f.states.some(state => state.status === 'downloading' && state.progress === 25), '进度应按已下载字节上报');
});

test('取消下载回到 available 且可重新下载', async () => {
  const f = fixture({ releases: [release('0.8.2-newui.2')], holdDownload: true });
  await f.updater.check();
  const downloading = f.updater.download();
  await tick();
  f.updater.cancel();
  assert.equal(f.signals()[0].aborted, true);
  f.release();
  const state = await downloading;
  assert.equal(state.status, 'available');
  assert.equal(state.progress, 0);
});

test('下载失败进入错误状态', async () => {
  const f = fixture({ releases: [release('0.8.2-newui.2')], downloadError: Object.assign(new Error('连接被重置'), { kind: 'download' }) });
  await f.updater.check();
  const state = await f.updater.download();
  assert.equal(state.status, 'error');
  assert.match(state.error, /下载更新失败：连接被重置/);
});

test('安装前先停后端，安装包启动后退出应用', async () => {
  let cleanupCalls = 0;
  const f = fixture({ releases: [release('0.8.2-newui.2')], beforeInstall: async () => { cleanupCalls += 1; } });
  await assert.rejects(f.updater.install(), /更新尚未下载完成/);
  await f.updater.check();
  await f.updater.download();
  const first = f.updater.install();
  const second = f.updater.install();
  await Promise.all([first, second]);
  assert.equal(cleanupCalls, 1, '重复点击只清一次后端');
  assert.deepEqual(f.launches, [path.join('tmp', 'renpybox-update', 'RenpyBox-NewUI-0.8.2-newui.2-x64.exe')]);
  assert.equal(f.quits.length, 1);
});

test('安装包启动失败时给出可读错误', async () => {
  const f = fixture({ releases: [release('0.8.2-newui.2')], launchError: new Error('EPERM') });
  await f.updater.check();
  await f.updater.download();
  const state = await f.updater.install();
  assert.equal(state.status, 'error');
  assert.match(state.error, /启动安装程序失败：EPERM/);
  assert.equal(f.quits.length, 0);
});
