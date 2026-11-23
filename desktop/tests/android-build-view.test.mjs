import assert from 'node:assert/strict';
import test from 'node:test';

import {
  ANDROID_COPY,
  androidAppFieldsReady,
  androidConfigPayload,
  androidCopy,
  androidDraftHasContent,
  androidDraftKey,
  androidFormIdentityKey,
  androidJobCancellable,
  parseAndroidDraftBundle,
  restoreAndroidDraft,
  serializeAndroidDraft,
  androidOwnerProjectKey,
  androidSdkReady,
  androidStatusPath,
  appendArchiveSource,
  defaultAndroidForm,
  formatAndroidOutputs,
  formatPrefixPlan,
  formatPrefixResult,
  mergeAndroidForm,
  prefixRequestBody,
  sameAndroidPath,
  shouldHydrateAndroidForm,
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

test('水合：用户 dirty（刚选 SDK）时空 config 不能冲掉 sdkPath', () => {
  const current = {
    ...defaultAndroidForm(),
    sdkPath: 'D:/renpy-8.5.3-sdk',
  };
  const emptyConfig = { sdk_path: '', app_name: '', package_name: '', version: '' };
  assert.equal(shouldHydrateAndroidForm({ hydrated: true, dirty: true }), false);
  assert.equal(shouldHydrateAndroidForm({ hydrated: false, dirty: true }), false);
  const merged = mergeAndroidForm(current, emptyConfig, { hydrated: false, dirty: true });
  assert.equal(merged.sdkPath, 'D:/renpy-8.5.3-sdk');
  assert.strictEqual(merged, current);
});

test('水合：同一身份已水合后轮询新 config 对象不再重置表单', () => {
  const current = defaultAndroidForm({
    sdk_path: 'D:/sdk',
    app_name: 'Demo',
    package_name: 'com.demo',
    version: '1.0',
  });
  // 内容相同但引用不同的轮询 payload
  const polled = {
    sdk_path: 'D:/sdk',
    app_name: 'Demo',
    package_name: 'com.demo',
    version: '1.0',
  };
  assert.equal(shouldHydrateAndroidForm({ hydrated: true, dirty: false }), false);
  const merged = mergeAndroidForm(current, polled, { hydrated: true, dirty: false });
  assert.strictEqual(merged, current);
  assert.equal(merged.appName, 'Demo');
});

test('水合：身份变化后允许重新水合并载入新 config', () => {
  const keyA = androidFormIdentityKey('/api/android-build?project_path=A', 'id-1');
  const keyB = androidFormIdentityKey('/api/android-build?project_path=B', 'id-2');
  assert.notEqual(keyA, keyB);

  const stale = defaultAndroidForm({ sdk_path: 'D:/old-sdk', app_name: 'Old' });
  // 身份变化：调用方重置 hydrated/dirty 后再 merge
  const nextConfig = {
    sdk_path: 'D:/new-sdk',
    app_name: 'NewApp',
    package_name: 'com.new',
    version: '2.0',
  };
  assert.equal(shouldHydrateAndroidForm({ hydrated: false, dirty: false }), true);
  const merged = mergeAndroidForm(stale, nextConfig, { hydrated: false, dirty: false });
  assert.notStrictEqual(merged, stale);
  assert.equal(merged.sdkPath, 'D:/new-sdk');
  assert.equal(merged.appName, 'NewApp');
  assert.equal(merged.packageName, 'com.new');
  assert.equal(merged.version, '2.0');
});

test('水合：未 dirty 且未水合时从 config 正常载入', () => {
  const empty = defaultAndroidForm();
  const config = {
    sdk_path: 'C:/renpy-sdk',
    app_name: 'Game',
    package_name: 'com.game',
    version: '0.1',
    archive_source_dir: 'images',
  };
  assert.equal(shouldHydrateAndroidForm({ hydrated: false, dirty: false }), true);
  const merged = mergeAndroidForm(empty, config, { hydrated: false, dirty: false });
  assert.equal(merged.sdkPath, 'C:/renpy-sdk');
  assert.equal(merged.appName, 'Game');
  assert.equal(merged.packageName, 'com.game');
  assert.equal(merged.version, '0.1');
  assert.equal(merged.archiveSourceDir, 'images');
});

test('androidDraftKey：空项目稳定、不同项目键不同', () => {
  const empty = androidDraftKey('');
  const empty2 = androidDraftKey('   ');
  assert.equal(empty, empty2);
  assert.ok(empty.startsWith('renpybox.android.draft.'));
  assert.notEqual(androidDraftKey('C:/Game/A'), androidDraftKey('C:/Game/B'));
  assert.equal(androidDraftKey('C:\\Game\\A'), androidDraftKey('c:/game/a'));
});

test('草稿序列化往返与 prefix 字段', () => {
  const form = { ...defaultAndroidForm(), sdkPath: 'D:/sdk/', appName: 'Demo' };
  const raw = serializeAndroidDraft(form, { prefixDir: 'C:/assets/x-game', prefixText: 'y-' });
  const bundle = parseAndroidDraftBundle(raw);
  assert.equal(bundle.form.sdkPath, 'D:/sdk/');
  assert.equal(bundle.form.appName, 'Demo');
  assert.equal(bundle.prefixDir, 'C:/assets/x-game');
  assert.equal(bundle.prefixText, 'y-');
  assert.equal(restoreAndroidDraft(raw).sdkPath, 'D:/sdk/');
});

test('restoreAndroidDraft：解析失败回落默认', () => {
  const form = restoreAndroidDraft('{not-json');
  assert.deepEqual(form, defaultAndroidForm());
  const nested = restoreAndroidDraft(JSON.stringify({ v: 1, form: null }));
  assert.deepEqual(nested, defaultAndroidForm());
});

test('restoreAndroidDraft：缺字段与类型错误回落', () => {
  const raw = JSON.stringify({
    v: 1,
    form: { sdkPath: 'https://ok/', appName: 42, shellBackupEnable: 'no' },
    prefixDir: 99,
  });
  const bundle = parseAndroidDraftBundle(raw);
  assert.equal(bundle.form.sdkPath, 'https://ok/');
  assert.equal(bundle.form.appName, '42');
  assert.equal(bundle.form.shellBackupEnable, true);
  assert.equal(bundle.prefixDir, '99');
});

test('androidDraftHasContent 识别非默认表单与前缀', () => {
  assert.equal(androidDraftHasContent(defaultAndroidForm()), false);
  assert.equal(androidDraftHasContent({ ...defaultAndroidForm(), sdkPath: 'C:/sdk/' }), true);
  assert.equal(androidDraftHasContent(defaultAndroidForm(), { prefixDir: 'C:/x' }), true);
});
