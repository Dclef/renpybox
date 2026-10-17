import assert from 'node:assert/strict';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { APP_DATA_DIR_NAME, LEGACY_APP_DATA_DIR_NAME, migrateLegacyProfile } from '../main/profile-migration.js';

function sandbox() {
  const root = mkdtempSync(path.join(tmpdir(), 'renpybox-profile-'));
  return { root, legacy: path.join(root, LEGACY_APP_DATA_DIR_NAME), target: path.join(root, APP_DATA_DIR_NAME) };
}

test('旧配置目录存在、新目录为空时复制一次', () => {
  const { root, legacy, target } = sandbox();
  mkdirSync(legacy, { recursive: true });
  writeFileSync(path.join(legacy, 'config.json'), '{"platforms":[1]}');
  writeFileSync(path.join(legacy, 'renpybox.db'), 'db');

  const logs = [];
  const result = migrateLegacyProfile({ appDataDir: root, logger: line => logs.push(line) });

  assert.equal(result.migrated, true);
  assert.equal(readFileSync(path.join(target, 'config.json'), 'utf8'), '{"platforms":[1]}');
  assert.equal(readFileSync(path.join(target, 'renpybox.db'), 'utf8'), 'db');
  assert.ok(logs.some(line => line.includes('迁移')));
  // 旧目录保留，允许用户回退
  assert.ok(existsSync(path.join(legacy, 'config.json')));
  rmSync(root, { recursive: true, force: true });
});

test('新目录已有配置时不覆盖', () => {
  const { root, legacy, target } = sandbox();
  mkdirSync(legacy, { recursive: true });
  writeFileSync(path.join(legacy, 'config.json'), 'old');
  mkdirSync(target, { recursive: true });
  writeFileSync(path.join(target, 'config.json'), 'new');

  const result = migrateLegacyProfile({ appDataDir: root });

  assert.equal(result.migrated, false);
  assert.equal(result.reason, 'target-exists');
  assert.equal(readFileSync(path.join(target, 'config.json'), 'utf8'), 'new');
  rmSync(root, { recursive: true, force: true });
});

test('没有旧目录时不动新目录', () => {
  const { root, target } = sandbox();
  const result = migrateLegacyProfile({ appDataDir: root });
  assert.equal(result.migrated, false);
  assert.equal(result.reason, 'absent');
  assert.equal(existsSync(target), false);
  rmSync(root, { recursive: true, force: true });
});

test('复制失败只记录日志，不阻塞启动', () => {
  const { root } = sandbox();
  const logs = [];
  const result = migrateLegacyProfile({
    appDataDir: root,
    logger: line => logs.push(line),
    fs: {
      existsSync: () => true,
      readdirSync: () => [],
      cpSync: () => { throw new Error('EPERM'); },
    },
  });
  assert.equal(result.migrated, false);
  assert.equal(result.reason, 'failed');
  assert.ok(logs.some(line => line.includes('EPERM')));
  rmSync(root, { recursive: true, force: true });
});
