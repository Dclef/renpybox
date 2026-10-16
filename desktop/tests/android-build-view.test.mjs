import assert from 'node:assert/strict';
import test from 'node:test';

import {
  ANDROID_COPY,
  androidAppFieldsReady,
  androidConfigPayload,
  androidCopy,
  androidJobCancellable,
  androidOwnerProjectKey,
  androidSdkReady,
  androidStatusPath,
  appendArchiveSource,
  defaultAndroidForm,
  formatAndroidOutputs,
  formatPrefixPlan,
  formatPrefixResult,
  prefixRequestBody,
  sameAndroidPath,
} from '../renderer/src/androidBuildView.mjs';

test('默认表单对齐 Config/Qt', () => {
  const form = defaultAndroidForm();
  assert.equal(form.shellBackupEnable, true);
  assert.equal(form.updateAlways, true);
  assert.equal(form.updateIcons, true);
  assert.equal(form.dname, '');
  assert.equal(form.shellRemoveDirs, 'images,image,audio,video,videos,movies,script');
  assert.equal(form.archiveSourceDir, '');
});

test('statusPath 支持手动 project_path', () => {
  assert.equal(androidStatusPath(), '/api/android-build');
  assert.equal(
    androidStatusPath('C:/manual-b'),
    '/api/android-build?project_path=C%3A%2Fmanual-b',
  );
  assert.equal(
    androidOwnerProjectKey({ owner_project_key: 'ownerA', project_key: 'targetB' }, 'fallback'),
    'ownerA',
  );
  assert.equal(androidOwnerProjectKey({ project_key: 'targetB' }, 'fallback'), 'fallback');
  assert.equal(sameAndroidPath('C:\\Game\\A', 'C:/game/a'), true);
});

test('字段就绪与 SDK', () => {
  assert.equal(androidAppFieldsReady({ appName: 'A', packageName: 'p', version: '1' }), true);
  assert.equal(androidAppFieldsReady({ appName: '', packageName: 'p', version: '1' }), false);
  assert.equal(androidSdkReady({ sdkPath: 'C:/sdk' }), true);
  assert.equal(androidSdkReady({ sdkPath: '  ' }), false);
});

test('配置 payload 含隐藏字段', () => {
  const payload = androidConfigPayload({
    sdkPath: 'C:/sdk',
    appName: 'Demo',
    packageName: 'com.demo',
    version: '1.0',
    archiveSourceDir: 'images',
    shellBackupEnable: true,
    shellRemoveDirs: 'images',
    dname: 'CN=X',
    updateAlways: false,
    updateIcons: true,
  }, 'C:/game');
  assert.equal(payload.dname, 'CN=X');
  assert.equal(payload.update_always, false);
  assert.equal(payload.update_icons, true);
  assert.equal(payload.shell_backup_enable, true);
  assert.equal(payload.project_path, 'C:/game');
});

test('打包源添加去重', () => {
  assert.equal(appendArchiveSource('', 'C:/a'), 'C:/a');
  assert.equal(appendArchiveSource('C:/a', 'C:/b'), 'C:/a;C:/b');
  assert.equal(appendArchiveSource('C:/a;C:/b', 'C:/A'), 'C:/a;C:/b');
});

test('SDK 任务不可取消', () => {
  assert.equal(androidJobCancellable({ result: { cancellable: false } }), false);
  assert.equal(androidJobCancellable({ result: { cancellable: true } }), false);
  assert.equal(androidJobCancellable(null), false);
});

test('双语文案与产物格式化', () => {
  assert.equal(androidCopy(ANDROID_COPY.title, 'ZH'), '安卓打包');
  assert.equal(androidCopy(ANDROID_COPY.title, 'EN'), 'Android Build');
  assert.deepEqual(
    formatAndroidOutputs([{ name: 'a.apk' }, { name: 'b.apk' }, { name: 'c.apk' }, { name: 'd.apk' }], 3),
    ['a.apk', 'b.apk', 'c.apk'],
  );
});

test('prefixRequestBody 去空白与前缀回落', () => {
  assert.deepEqual(
    prefixRequestBody('  C:/assets/x-game  ', '  x-  ', 'strip', false),
    { directory: 'C:/assets/x-game', prefix: 'x-', action: 'strip', apply: false },
  );
  assert.deepEqual(
    prefixRequestBody('C:/game', '   ', 'restore', true),
    { directory: 'C:/game', prefix: 'x-', action: 'restore', apply: true },
  );
});

test('formatPrefixPlan / formatPrefixResult 中英文', () => {
  const base = { total: 12, files: 10, dirs: 2, renamed: 12, skipped: 0 };
  assert.equal(formatPrefixPlan(base, 'ZH'), '将重命名 12 个条目（文件 10 / 目录 2）');
  assert.equal(formatPrefixPlan(base, 'EN'), 'Rename 12 entries (10 files / 2 folders)');
  assert.equal(
    formatPrefixPlan({ ...base, skipped: 1 }, 'ZH'),
    '将重命名 12 个条目（文件 10 / 目录 2），跳过 1 个',
  );
  assert.equal(
    formatPrefixPlan({ ...base, skipped: 1 }, 'EN'),
    'Rename 12 entries (10 files / 2 folders), skip 1',
  );
  assert.equal(formatPrefixResult(base, 'ZH'), '已重命名 12 个条目（文件 10 / 目录 2）');
  assert.equal(formatPrefixResult(base, 'EN'), 'Renamed 12 entries (10 files / 2 folders)');
  assert.equal(
    formatPrefixResult({ ...base, skipped: 1, new_root: 'C:/assets/game' }, 'ZH'),
    '已重命名 12 个条目（文件 10 / 目录 2），跳过 1 个，根目录已改为 game',
  );
  assert.equal(
    formatPrefixResult({ ...base, skipped: 1, new_root: 'C:/assets/game' }, 'EN'),
    'Renamed 12 entries (10 files / 2 folders), skip 1, root folder renamed to game',
  );
});

test('ANDROID_COPY 新增 X- 前缀键双语齐全', () => {
  const keys = [
    'xPrefix', 'xPrefixHint', 'prefixDir', 'prefixDirPlaceholder', 'prefixLabel',
    'stripPrefix', 'restorePrefix', 'prefixNothing', 'prefixNeedDir',
    'confirmStrip', 'confirmRestore', 'prefixSamples',
  ];
  for (const key of keys) {
    assert.ok(ANDROID_COPY[key], key);
    assert.ok(ANDROID_COPY[key].ZH, `${key}.ZH`);
    assert.ok(ANDROID_COPY[key].EN, `${key}.EN`);
  }
});
