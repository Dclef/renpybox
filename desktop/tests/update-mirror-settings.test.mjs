/**
 * 更新镜像设置：解析/格式化纯函数契约。
 *
 * 运行（pwsh）：
 *   cd desktop; node --test tests/update-mirror-settings.test.mjs
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  parseMirrorList,
  formatMirrorList,
  BUILTIN_MIRRORS,
  MIRROR_PRESETS,
  builtinMirrorText,
  isUsingBuiltinMirrors,
  mirrorValuesFromSetting,
  reconcileMirrorSelection,
  addCustomMirror,
  rankMirrorResults,
  speedOrderedMirrors,
  mirrorProbeCandidates,
} from '../renderer/src/updateMirrorSettings.mjs';
// 防漂移断言要对照主进程真相源；该文件是纯 ESM，无 Electron 依赖，可直接 import
import { GITHUB_DOWNLOAD_MIRRORS } from '../main/updater-mirror.js';

test('合法多行列表按顺序保留', () => {
  const { values, errors } = parseMirrorList(
    'https://fastgit.cc/\nhttps://cors.isteed.cc/\n',
  );
  assert.deepEqual(values, ['https://fastgit.cc/', 'https://cors.isteed.cc/']);
  assert.deepEqual(errors, []);
});

test('空行忽略', () => {
  const { values, errors } = parseMirrorList('\n  \nhttps://a.example/\n\n\nhttps://b.example/\n   \n');
  assert.deepEqual(values, ['https://a.example/', 'https://b.example/']);
  assert.deepEqual(errors, []);
});

test('重复项去重并保留首次出现顺序', () => {
  const { values } = parseMirrorList('https://b.example/\nhttps://a.example/\nhttps://b.example/');
  assert.deepEqual(values, ['https://b.example/', 'https://a.example/']);
});

test('缺协议被拒绝', () => {
  const { values, errors } = parseMirrorList('fastgit.cc/');
  assert.deepEqual(values, []);
  assert.deepEqual(errors, ['fastgit.cc/']);
});

test('缺尾斜杠被拒绝', () => {
  const { values, errors } = parseMirrorList('https://fastgit.cc');
  assert.deepEqual(values, []);
  assert.deepEqual(errors, ['https://fastgit.cc']);
});

test('非 http(s) 协议被拒绝', () => {
  const { values, errors } = parseMirrorList('ftp://a.example/\nfile:///tmp/');
  assert.deepEqual(values, []);
  assert.deepEqual(errors, ['ftp://a.example/', 'file:///tmp/']);
});

test('合法与非法混排：合法项照常返回，非法项单独报告', () => {
  const { values, errors } = parseMirrorList('https://ok.example/\nbad.example/\nhttp://ok2.example/');
  assert.deepEqual(values, ['https://ok.example/', 'http://ok2.example/']);
  assert.deepEqual(errors, ['bad.example/']);
});

test('空输入返回空数组（表示使用内置默认镜像）', () => {
  assert.deepEqual(parseMirrorList('').values, []);
  assert.deepEqual(parseMirrorList('   \n  \n').values, []);
  assert.deepEqual(parseMirrorList(undefined).values, []);
  assert.deepEqual(parseMirrorList(null).values, []);
});

test('formatMirrorList 与 parseMirrorList 往返一致', () => {
  const list = ['https://fastgit.cc/', 'https://cors.isteed.cc/'];
  const text = formatMirrorList(list);
  assert.equal(text, 'https://fastgit.cc/\nhttps://cors.isteed.cc/');
  assert.deepEqual(parseMirrorList(text).values, list);
  assert.equal(formatMirrorList(parseMirrorList(text).values), text);
});

test('formatMirrorList 对非列表/脏数据返回空串', () => {
  assert.equal(formatMirrorList(undefined), '');
  assert.equal(formatMirrorList(null), '');
  assert.equal(formatMirrorList([]), '');
  assert.equal(formatMirrorList([' ', 42, null, 'https://a.example/']), 'https://a.example/');
});

// 渲染层展示副本必须与主进程 GITHUB_DOWNLOAD_MIRRORS 完全一致，防止两份真相漂移
test('BUILTIN_MIRRORS 与主进程 GITHUB_DOWNLOAD_MIRRORS 深度相等', () => {
  assert.deepEqual([...BUILTIN_MIRRORS], [...GITHUB_DOWNLOAD_MIRRORS]);
  assert.ok(Object.isFrozen(BUILTIN_MIRRORS));
});

test('builtinMirrorText 按内置顺序输出多行文本', () => {
  assert.equal(builtinMirrorText(), 'https://fastgit.cc/\nhttps://cors.isteed.cc/');
  assert.deepEqual(parseMirrorList(builtinMirrorText()).values, [...GITHUB_DOWNLOAD_MIRRORS]);
});

test('isUsingBuiltinMirrors：空/脏数据视为使用内置默认，非空列表则不是', () => {
  assert.equal(isUsingBuiltinMirrors(undefined), true);
  assert.equal(isUsingBuiltinMirrors(null), true);
  assert.equal(isUsingBuiltinMirrors([]), true);
  assert.equal(isUsingBuiltinMirrors(['  ']), true);
  assert.equal(isUsingBuiltinMirrors(['https://a.example/']), false);
});

test('MIRROR_PRESETS 包含全部 BUILTIN_MIRRORS 且提供额外预设', () => {
  for (const mirror of BUILTIN_MIRRORS) {
    assert.ok(MIRROR_PRESETS.includes(mirror));
  }
  assert.ok(MIRROR_PRESETS.length > BUILTIN_MIRRORS.length);
  assert.equal(new Set(MIRROR_PRESETS).size, MIRROR_PRESETS.length);
  assert.ok(Object.isFrozen(MIRROR_PRESETS));
});

test('addCustomMirror：合法自定义追加到末尾', () => {
  const base = ['https://a.example/'];
  const { values, errors } = addCustomMirror(base, 'https://b.example/');
  assert.deepEqual(errors, []);
  assert.deepEqual(values, ['https://a.example/', 'https://b.example/']);
});

test('addCustomMirror：非法地址被拒且不改动原列表', () => {
  const base = ['https://a.example/'];
  const { values, errors } = addCustomMirror(base, 'bad.example/');
  assert.deepEqual(values, base);
  assert.deepEqual(errors, ['bad.example/']);
});

test('addCustomMirror：重复地址去重', () => {
  const base = ['https://a.example/'];
  const { values, errors } = addCustomMirror(base, 'https://a.example/\nhttps://b.example/');
  assert.deepEqual(errors, []);
  assert.deepEqual(values, ['https://a.example/', 'https://b.example/']);
});

test('reconcileMirrorSelection：保留既有顺序并把新勾选项追加到末尾', () => {
  const ordered = ['https://b.example/', 'https://a.example/'];
  // antd 可能返回乱序选中集
  const selected = ['https://a.example/', 'https://c.example/', 'https://b.example/'];
  assert.deepEqual(
    reconcileMirrorSelection(ordered, selected),
    ['https://b.example/', 'https://a.example/', 'https://c.example/'],
  );
});

test('恢复默认：空数组镜像语义与 mirrorValuesFromSetting 一致', () => {
  assert.deepEqual(mirrorValuesFromSetting([]), []);
  assert.equal(isUsingBuiltinMirrors([]), true);
  assert.deepEqual(mirrorValuesFromSetting(null), []);
  assert.deepEqual(mirrorValuesFromSetting(['https://x.example/']), ['https://x.example/']);
});

test('rankMirrorResults：快的排前，不可用排后，fastest 只给第一名', () => {
  const ranked = rankMirrorResults([
    { prefix: 'https://slow/', latencyMs: 40, bytesPerSec: 100, ok: true },
    { prefix: 'https://dead/', latencyMs: 8000, bytesPerSec: 0, ok: false },
    { prefix: 'https://fast/', latencyMs: 80, bytesPerSec: 900, ok: true },
  ]);
  assert.deepEqual(ranked.map((item) => item.prefix), ['https://fast/', 'https://slow/', 'https://dead/']);
  assert.equal(ranked[0].fastest, true);
  assert.equal(ranked.filter((item) => item.fastest).length, 1);
  assert.equal(ranked.at(-1).ok, false);
});

test('rankMirrorResults：同速率按延迟升序；空结果无 fastest', () => {
  const ranked = rankMirrorResults([
    { prefix: 'https://b/', latencyMs: 200, bytesPerSec: 500, ok: true },
    { prefix: 'https://a/', latencyMs: 50, bytesPerSec: 500, ok: true },
  ]);
  assert.deepEqual(ranked.map((item) => item.prefix), ['https://a/', 'https://b/']);
  assert.deepEqual(rankMirrorResults([]), []);
  assert.deepEqual(rankMirrorResults(null), []);
});

test('speedOrderedMirrors 只保留可用非空前缀；候选为空时用预设并加直连', () => {
  const ordered = speedOrderedMirrors([
    { prefix: '', latencyMs: 10, bytesPerSec: 9999, ok: true },
    { prefix: 'https://ok/', latencyMs: 30, bytesPerSec: 100, ok: true },
    { prefix: 'https://bad/', latencyMs: 1, bytesPerSec: 0, ok: false },
  ]);
  assert.deepEqual(ordered, ['https://ok/']);
  // 只保留最快的两条，多余的可用镜像不写入配置
  const many = speedOrderedMirrors([
    { prefix: 'https://a/', latencyMs: 5, bytesPerSec: 900, ok: true },
    { prefix: 'https://b/', latencyMs: 6, bytesPerSec: 800, ok: true },
    { prefix: 'https://c/', latencyMs: 7, bytesPerSec: 700, ok: true },
    { prefix: 'https://d/', latencyMs: 8, bytesPerSec: 600, ok: true },
    { prefix: 'https://bad/', latencyMs: 1, bytesPerSec: 0, ok: false },
  ]);
  assert.deepEqual(many, ['https://a/', 'https://b/']);
  const candidates = mirrorProbeCandidates([]);
  assert.equal(candidates.at(-1), '');
  assert.ok(candidates.includes(MIRROR_PRESETS[0]));
  assert.equal(new Set(candidates).size, candidates.length);
});
