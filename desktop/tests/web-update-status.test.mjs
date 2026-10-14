/**
 * 网页端更新状态映射（对齐 Qt5 AppSettingsPage.refresh_update_ui）。
 *
 * 运行（pwsh）：
 *   cd desktop; node --test tests/web-update-status.test.mjs
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { resolveWebUpdateUi } from '../renderer/src/webUpdateStatus.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const settingsPage = fs.readFileSync(path.join(root, 'renderer/src/pages/SettingsPage.tsx'), 'utf8');
const appTsx = fs.readFileSync(path.join(root, 'renderer/src/App.tsx'), 'utf8');

function state(partial = {}) {
  return {
    status: 'NONE',
    latest: {},
    downloaded_size: 0,
    total_size: 0,
    error: '',
    new_version: false,
    can_install: false,
    ...partial,
  };
}

test('NONE 且无 latest：尚未检查', () => {
  const ui = resolveWebUpdateUi(state());
  assert.equal(ui.statusText, '尚未检查更新');
  assert.equal(ui.offerUpdate, false);
  assert.equal(ui.offerMigration, false);
  assert.equal(ui.showInstall, false);
});

test('检查中优先于其它状态文案', () => {
  const ui = resolveWebUpdateUi(state({ status: 'NEW_VERSION', latest: { tag_name: 'v1.2.3' }, new_version: true }), true);
  assert.equal(ui.statusText, '检查中…');
  assert.equal(ui.offerUpdate, true);
});

test('NEW_VERSION / NONE+new_version 提供下载操作', () => {
  const fresh = resolveWebUpdateUi(state({ status: 'NEW_VERSION', latest: { tag_name: 'v9.0.0' }, new_version: true }));
  assert.match(fresh.statusText, /发现新版本/);
  assert.equal(fresh.offerUpdate, true);
  assert.equal(fresh.offerMigration, false);

  const cached = resolveWebUpdateUi(state({ status: 'NONE', latest: { tag_name: 'v9.0.0' }, new_version: true }));
  assert.match(cached.statusText, /发现新版本/);
  assert.equal(cached.offerUpdate, true);
});

test('同版本 DESKTOP_AVAILABLE 提供迁移入口，不显示下载/安装/进度', () => {
  const ui = resolveWebUpdateUi(state({
    status: 'DESKTOP_AVAILABLE',
    latest: { tag_name: 'v0.9.0', delivery: 'desktop' },
    new_version: true,
    can_install: false,
  }));
  assert.match(ui.statusText, /桌面版/);
  assert.equal(ui.offerMigration, true);
  assert.equal(ui.offerUpdate, false);
  assert.equal(ui.showInstall, false);
  assert.equal(ui.showProgress, false);
  assert.equal(ui.showCancel, false);
});

test('UPDATING 不被 new_version / migration 盖住，显示进度与取消', () => {
  const ui = resolveWebUpdateUi(state({
    status: 'UPDATING',
    latest: { tag_name: 'v9.0.0', delivery: 'desktop' },
    new_version: true,
    downloaded_size: 12 * 1024 * 1024,
    total_size: 48 * 1024 * 1024,
  }));
  assert.match(ui.statusText, /正在下载/);
  assert.equal(ui.progress, 25);
  assert.equal(ui.offerUpdate, false);
  assert.equal(ui.offerMigration, false);
  assert.equal(ui.showProgress, true);
  assert.equal(ui.showCancel, true);
  assert.equal(ui.showInstall, false);
});

test('DOWNLOADED / can_install 显示安装，不显示下载', () => {
  const byStatus = resolveWebUpdateUi(state({
    status: 'DOWNLOADED',
    latest: { tag_name: 'v9.0.0' },
    new_version: true,
    can_install: true,
  }));
  assert.equal(byStatus.statusText, '下载完成，重启后生效');
  assert.equal(byStatus.offerUpdate, false);
  assert.equal(byStatus.offerMigration, false);
  assert.equal(byStatus.showInstall, true);

  const byFlag = resolveWebUpdateUi(state({ status: 'NONE', can_install: true, new_version: true, latest: { tag_name: 'v9.0.0' } }));
  assert.equal(byFlag.showInstall, true);
});

test('错误与已是最新', () => {
  assert.equal(resolveWebUpdateUi(state({ error: 'timeout' })).statusText, '检查更新失败，请重试');
  assert.equal(
    resolveWebUpdateUi(state({ latest: { tag_name: 'v0.8.1' }, new_version: false })).statusText,
    '已是最新版本',
  );
});

test('WebAboutCard offer/确认：legacy 确认后 downloadUpdate；migration 打开 release_url', () => {
  // 只抽 WebAboutCard 源码片段做静态契约，不镜像 React 状态机
  const start = settingsPage.indexOf('function WebAboutCard');
  assert.ok(start >= 0, '应存在 WebAboutCard');
  const web = settingsPage.slice(start, settingsPage.indexOf('function ProxyCard', start));
  assert.match(web, /t\('app_update_view_update'\)/);
  assert.match(web, /t\('app_desktop_update_action'\)/);
  assert.match(web, /t\('app_desktop_update_description'\)/);
  assert.doesNotMatch(web, /查看详情/);
  // legacy 确认走 downloadUpdate；migration 确认走 window.open(release_url) 后 return，不调自动更新 API
  assert.match(web, /if\s*\(\s*ui\.offerMigration\s*\)[\s\S]*?update\.release_url[\s\S]*?window\.open\([\s\S]*?return;[\s\S]*?api\.downloadUpdate/s);
  assert.match(web, /onCancel=\{\(\) => setDetailsOpen\(false\)\}/);
  assert.doesNotMatch(web, /offerMigration[\s\S]{0,80}api\.downloadUpdate/);
  assert.match(web, /<ChangelogView markdown=\{String\(update\.latest\?\.body/);
  // Dialog 在 ChangelogView 后展示包大小 / 发布日期（对齐 Qt metadata）
  assert.match(web, /rb-update-release-meta/);
  assert.match(web, /formatMegabytes/);
  assert.match(web, /published_at/);
  assert.doesNotMatch(web, /ui\.offerUpdate[\s\S]*?api\.downloadUpdate[\s\S]*?ui\.showCancel/);
});

test('WebAboutCard 不再承担启动自动检查，手动按钮只走 run(checkUpdate(true))', () => {
  const start = settingsPage.indexOf('function WebAboutCard');
  const web = settingsPage.slice(start, settingsPage.indexOf('function ProxyCard', start));
  assert.doesNotMatch(settingsPage, /webAboutAutoCheckFired/);
  assert.doesNotMatch(web, /api\.checkUpdate\(false\)/);
  assert.doesNotMatch(web, /3000/);
  assert.match(web, /onClick=\{\(\) => void run\(\(\) => api\.checkUpdate\(true\), \{ checking: true \}\)\}/);
});

test('App.tsx 根层网页端启动 3s 自动检查：仅网页端、manual=false、清 timer、防重复', () => {
  assert.match(appTsx, /import \* as api from '\.\/api';/);
  assert.match(appTsx, /^let webStartupUpdateCheckFired = false;/m);
  const start = appTsx.indexOf('if (window.renpy) return;');
  assert.ok(start >= 0, 'App 根层应存在 window.renpy guard（Electron 不触发）');
  const effect = appTsx.slice(start, appTsx.indexOf('}, []);', start));
  assert.match(effect, /if \(webStartupUpdateCheckFired\) return/);
  assert.match(effect, /webStartupUpdateCheckFired = true/);
  assert.match(effect, /setTimeout\([\s\S]*?,\s*3000\)/);
  assert.match(effect, /void api\.checkUpdate\(false\)\.catch/);
  assert.match(effect, /clearTimeout\(timer\)/);
});
