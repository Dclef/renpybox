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
