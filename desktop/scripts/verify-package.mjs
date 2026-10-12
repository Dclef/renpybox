import assert from 'node:assert/strict';
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const desktop = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const config = JSON.parse(readFileSync(path.join(desktop, 'package.json'), 'utf8'));
const packaged = path.join(desktop, 'release', 'win-unpacked', 'resources');
const hash = filename => createHash('sha256').update(readFileSync(filename)).digest('hex');
assert.match(config.version, /^[0-9]+[.][0-9]+[.][0-9]+-newui[.][0-9]+$/);
// 更新逻辑改为 desktop/main/updater.js 直接查 GitHub Releases API：不再需要 electron-builder
// 的 publish 配置，也不再生成 app-update.yml / blockmap / newui.yml。
assert.equal(config.build.publish, undefined, 'Desktop updates must not fall back to electron-builder publish metadata');
const dependencies = { ...config.dependencies, ...config.devDependencies };
assert(!('electron-updater' in dependencies), 'electron-updater must stay removed: the updater talks to the GitHub API directly');
assert(!('builder-util-runtime' in dependencies), 'builder-util-runtime was only used by electron-updater');
assert(!existsSync(path.join(packaged, 'app-update.yml')), 'Stale app-update.yml found inside the packaged resources');
// 安装包与免安装 zip 一次构建，两个产物共用同一个 win-unpacked。
assert.match(config.scripts['pack:win'], /--win nsis zip/, 'pack:win must build both nsis and the portable zip');
for (const file of ['app.asar', 'backend/RenpyBoxBackend.exe',
  'backend/_internal/resource/icon.ico', 'backend/build-manifest.json', 'renpybox/icon.ico']) {
  assert(existsSync(path.join(packaged, file)), `Missing packaged file: ${file}`);
}
const backendFiles = readdirSync(path.join(packaged, 'backend', '_internal'));
assert(backendFiles.some(name => /^python[0-9]+[.]dll$/.test(name)), 'Bundled Python DLL is missing');
assert.equal(hash(path.join(packaged, 'renpybox', 'icon.ico')), hash(path.join(desktop, '..', 'resource', 'icon.ico')));
const resources = path.join(packaged, 'backend', '_internal', 'resource');
const pending = [resources];
while (pending.length) {
  const folder = pending.pop();
  for (const entry of readdirSync(folder, { withFileTypes: true })) {
    const filename = path.join(folder, entry.name);
    if (entry.isDirectory()) pending.push(filename);
    else assert(!/^(config[.]json|secrets[.]json|credentials[.]json|[.]env(?:[.].*)?)$/i.test(entry.name),
      `Private configuration included: ${path.relative(resources, filename)}`);
  }
}
// 老的 electron-updater 产物不应再留在发布目录里误导用户
assert.equal(config.build.nsis.differentialPackage, false,
  'NSIS differentialPackage must stay false: blockmap assets are no longer published');
const releaseFiles = readdirSync(path.join(desktop, 'release'), { withFileTypes: true })
  .filter(entry => entry.isFile()).map(entry => entry.name);
for (const unwanted of releaseFiles.filter(name => name.endsWith('.blockmap') || name === 'newui.yml')) {
  assert.fail(`Remove stale update metadata from release/: ${unwanted}`);
}
console.log('[package] Bundled Python, original icon, private-file exclusions, direct GitHub update feed and portable zip verified.');
