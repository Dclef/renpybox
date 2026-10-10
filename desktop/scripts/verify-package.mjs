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
console.log('[package] Bundled Python, original icon, private-file exclusions and newui updater configuration verified.');
