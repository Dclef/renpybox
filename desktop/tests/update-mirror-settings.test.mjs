/**
 * 更新镜像设置：解析/格式化纯函数契约。
 *
 * 运行（pwsh）：
 *   cd desktop; node --test tests/update-mirror-settings.test.mjs
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { parseMirrorList, formatMirrorList } from '../renderer/src/updateMirrorSettings.mjs';

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
