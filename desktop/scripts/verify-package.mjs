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
assert.equal(config.build.publish.channel, 'newui');
assert.equal(config.build.publish.releaseType, 'prerelease');
// 免安装 zip 与安装包必须一起构建：app-update.yml 只在同一次构建里带 nsis 目标时才写入
// （app-builder-lib/out/publish/PublishManager.js 的 isSuitableWindowsTarget 只认 nsis），
// 两个产物共用同一个 win-unpacked，所以一起构建才能让 zip 也带上更新配置。
assert.match(config.scripts['pack:win'], /--win nsis zip/,
  'pack:win must build both nsis and zip so the portable zip carries app-update.yml');
for (const file of ['app.asar', 'app-update.yml', 'backend/RenpyBoxBackend.exe',
  'backend/_internal/resource/icon.ico', 'backend/build-manifest.json', 'renpybox/icon.ico']) {
  assert(existsSync(path.join(packaged, file)), `Missing packaged file: ${file}`);
}
const backendFiles = readdirSync(path.join(packaged, 'backend', '_internal'));
assert(backendFiles.some(name => /^python[0-9]+[.]dll$/.test(name)), 'Bundled Python DLL is missing');
assert.equal(hash(path.join(packaged, 'renpybox', 'icon.ico')), hash(path.join(desktop, '..', 'resource', 'icon.ico')));
const update = readFileSync(path.join(packaged, 'app-update.yml'), 'utf8');
assert.match(update, /provider:[ ]*github/);
assert.match(update, /channel:[ ]*newui/);
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
const metadata = path.join(desktop, 'release', 'newui.yml');
if (existsSync(metadata)) {
  const contents = readFileSync(metadata, 'utf8');
  assert(contents.includes(`version: ${config.version}`), 'Stale newui update metadata');
  assert(contents.includes(`RenpyBox-NewUI-${config.version}-x64.exe`), 'Update metadata points to a different artifact');
}
// 免安装 zip 里的更新配置：zip 的中央目录文件名是明文存储，直接扫字节即可确认
const zip = path.join(desktop, 'release', `RenpyBox-NewUI-${config.version}-x64.zip`);
if (existsSync(zip)) {
  assert(readFileSync(zip).includes(Buffer.from('resources/app-update.yml')),
    'Portable zip is missing resources/app-update.yml: build nsis and zip in the same electron-builder run');
}
console.log('[package] Bundled Python, original icon, private-file exclusions, newui updater configuration and portable zip update config verified.');
