import assert from 'node:assert/strict';
import test from 'node:test';

import {
  NO_WARNING,
  collectGlossaryTerms,
  collectWarnings,
  compilePattern,
  countMatches,
  exportFilename,
  exportText,
  filterRows,
  makeReplacer,
  matchRowIndices,
  pageSlice,
  replaceImpact,
  stepMatch,
} from '../renderer/src/proofreadingView.mjs';

function row(overrides = {}) {
  return {
    id: 0,
    version: 'v1',
    src: 'Hello',
    dst: '你好',
    status: 'TRANSLATED',
    file_path: 'chapter_01.rpy',
    row: 12,
    warnings: [],
    ...overrides,
  };
}

test('正则搜索：非法正则只给出可读错误，不抛异常', () => {
  const invalid = compilePattern('([', { regex: true });
  assert.equal(invalid.ok, false);
  assert.equal(typeof invalid.error, 'string');
  assert.ok(invalid.error.length > 0);

  const valid = compilePattern('^艾', { regex: true });
  assert.equal(valid.ok, true);
  assert.equal(valid.pattern.test('艾丽丝'), true);

  // 未开启正则时任何字符都是合法纯文本。
  assert.equal(compilePattern('([', { regex: false }).ok, true);
});

test('正则搜索固定忽略大小写，对齐 Qt5 re.IGNORECASE', () => {
  const compiled = compilePattern('^alice', { regex: true });
  assert.equal(compiled.pattern.test('ALICE 的信'), true);
});

test('匹配行下标：原文或译文任一命中即算一行，非法正则不返回匹配', () => {
  const rows = [
    row({ id: 0, src: 'Hello Alice', dst: '你好' }),
    row({ id: 1, src: 'Hello', dst: '你好 艾丽丝' }),
    row({ id: 2, src: 'Bye', dst: '再见' }),
  ];

  assert.deepEqual(matchRowIndices(rows, '艾丽丝'), [1]);
  assert.deepEqual(matchRowIndices(rows, 'hello'), [0, 1]);
  assert.deepEqual(matchRowIndices(rows, '^Hello$', { regex: true }), [1]);
  assert.deepEqual(matchRowIndices(rows, '^Hello', { regex: true }), [0, 1]);
  assert.deepEqual(matchRowIndices(rows, '(['), []);
  assert.deepEqual(matchRowIndices(rows, '([', { regex: true }), []);
  assert.deepEqual(matchRowIndices(rows, ''), []);
});

test('匹配跳转：越界回环，没有匹配时返回 -1', () => {
  assert.equal(stepMatch(0, 3, 1), 1);
  assert.equal(stepMatch(2, 3, 1), 0);
  assert.equal(stepMatch(0, 3, -1), 2);
  assert.equal(stepMatch(1, 3, -1), 0);
  assert.equal(stepMatch(-1, 0, 1), -1);
});

test('批量替换：四种组合与 Qt5 _on_batch_replace_clicked 一致', () => {
  assert.equal(makeReplacer('Alice', '艾丽丝', { caseSensitive: true })('Alice 和 Alice'), '艾丽丝 和 艾丽丝');
  assert.equal(makeReplacer('alice', '艾丽丝', { caseSensitive: true })('Alice'), 'Alice');
  assert.equal(makeReplacer('alice', '艾丽丝', { caseSensitive: false })('Alice 和 ALICE'), '艾丽丝 和 艾丽丝');

  // 纯文本替换不能把替换文本里的 $1 当反向引用。
  assert.equal(makeReplacer('Alice', '$1', { caseSensitive: true })('Alice'), '$1');
  assert.equal(makeReplacer('alice', '$1', { caseSensitive: false })('Alice'), '$1');
  assert.equal(makeReplacer('A', '$&', { caseSensitive: true })('A'), '$&');

  // 正则替换保留捕获组：JS 的 $1 与 Qt5/Python 的 \1、\g<1> 都接受。
  assert.equal(makeReplacer('(A)(l)', '$2$1', { regex: true, caseSensitive: true })('Alice'), 'lAice');
  assert.equal(makeReplacer('(A)(l)', '\\2\\1', { regex: true, caseSensitive: true })('Alice'), 'lAice');
  assert.equal(makeReplacer('(?<first>A)', '\\g<first>x', { regex: true, caseSensitive: true })('Alice'), 'Axlice');
  assert.equal(makeReplacer('A', '\\1', { regex: true, caseSensitive: true })('A'), '$1');
  assert.equal(makeReplacer('A', 'a$&b', { regex: true, caseSensitive: true })('A'), 'aAb');
  // 正则默认区分大小写（对齐 Qt5 未勾选时 flags=0）；勾掉才忽略大小写。
  assert.equal(makeReplacer('a', 'x', { regex: true })('aA'), 'xA');
  assert.equal(makeReplacer('a', 'x', { regex: true, caseSensitive: false })('aA'), 'xx');
});

test('影响范围：只统计真正会被改写的行，并给出命中次数', () => {
  const rows = [
    row({ id: 0, dst: 'Alice 与 Alice' }),
    row({ id: 1, dst: '无人' }),
    row({ id: 2, dst: 'Alice' }),
  ];

  const impact = replaceImpact(rows, 'Alice', '艾丽丝', { caseSensitive: true });
  assert.equal(impact.rows.length, 2);
  assert.equal(impact.matchCount, 3);
  assert.deepEqual(impact.rows.map((item) => item.id), [0, 2]);
  assert.equal(impact.rows[0].after, '艾丽丝 与 艾丽丝');

  assert.equal(replaceImpact(rows, 'Nobody', 'x', {}).rows.length, 0);
  assert.equal(replaceImpact(rows, '', 'x', {}).rows.length, 0);
});

test('影响范围：正则非法时不改写任何行', () => {
  const impact = replaceImpact([row({ dst: 'Alice' })], '([', 'x', { regex: true });
  assert.equal(impact.invalidRegex, true);
  assert.equal(impact.rows.length, 0);
  assert.equal(typeof impact.error, 'string');
});

test('命中次数与匹配口径一致', () => {
  assert.equal(countMatches('Alice Alice', 'Alice', { caseSensitive: true }), 2);
  assert.equal(countMatches('Alice alice', 'alice', { caseSensitive: false }), 2);
  assert.equal(countMatches('Alice', 'alice', { caseSensitive: true }), 0);
  assert.equal(countMatches('a1b22', '\\d+', { regex: true }), 2);
  assert.equal(countMatches('Alice', '([', { regex: true }), 0);
});

test('术语表列表只收集术语未生效行带来的词条', () => {
  const rows = [
    row({ warnings: ['GLOSSARY'], glossary_terms: [{ src: 'Alice', dst: '艾丽丝' }, { src: 'Town', dst: '小镇' }] }),
    row({ warnings: ['GLOSSARY'], glossary_terms: [{ src: 'Alice', dst: '艾丽丝' }] }),
    row({ warnings: ['KANA'], glossary_terms: [{ src: 'Noise', dst: '噪声' }] }),
  ];

  const terms = collectGlossaryTerms(rows);
  assert.deepEqual(terms.map((term) => term.label), ['Alice -> 艾丽丝', 'Town -> 小镇']);
  assert.deepEqual(collectGlossaryTerms([row()]), []);
});

test('问题类型列表：带出告警类型并补一个「没有问题」占位项', () => {
  assert.deepEqual(collectWarnings([row({ warnings: ['KANA'] }), row({ warnings: [] })]), ['KANA', NO_WARNING]);
  assert.deepEqual(collectWarnings([row({ warnings: ['KANA'] })]), ['KANA']);
  assert.deepEqual(collectWarnings([]), []);
});

test('客户端筛选：状态 / 文件 / 问题类型 / 术语表多选是「与」关系', () => {
  const rows = [
    row({ id: 0, status: 'TRANSLATED', file_path: 'a.rpy', dst: '艾丽丝 说', warnings: ['GLOSSARY'], glossary_terms: [{ src: 'Alice', dst: '艾丽丝' }] }),
    row({ id: 1, status: 'UNTRANSLATED', file_path: 'a.rpy', dst: '' }),
    row({ id: 2, status: 'TRANSLATED', file_path: 'b.rpy', dst: '小镇 说' }),
  ];

  assert.deepEqual(filterRows(rows, {}).map((item) => item.id), [0, 1, 2]);
  assert.deepEqual(filterRows(rows, { statuses: ['TRANSLATED'] }).map((item) => item.id), [0, 2]);
  assert.deepEqual(filterRows(rows, { files: ['a.rpy'] }).map((item) => item.id), [0, 1]);
  assert.deepEqual(filterRows(rows, { warnings: ['GLOSSARY'] }).map((item) => item.id), [0]);
  assert.deepEqual(filterRows(rows, { warnings: [NO_WARNING] }).map((item) => item.id), [1, 2]);
  assert.deepEqual(filterRows(rows, { terms: ['Alice\u0000艾丽丝'] }).map((item) => item.id), [0]);
  assert.deepEqual(filterRows(rows, { statuses: ['TRANSLATED'], files: ['a.rpy'] }).map((item) => item.id), [0]);
  assert.deepEqual(filterRows(rows, { terms: ['Alice\u0000艾丽丝'], files: ['b.rpy'] }), []);
  // 空数组等于「不限制这一维」，与 Qt5 的 None 口径一致。
  assert.deepEqual(filterRows(rows, { statuses: [], files: [] }).map((item) => item.id), [0, 1, 2]);
});

test('分页：筛选后页码越界回落到最后一页', () => {
  const rows = Array.from({ length: 5 }, (_, index) => row({ id: index }));
  const first = pageSlice(rows, 1, 2);
  assert.deepEqual(first.items.map((item) => item.id), [0, 1]);
  assert.equal(first.page, 1);
  assert.equal(first.pages, 3);

  const overflow = pageSlice(rows, 9, 2);
  assert.deepEqual(overflow.items.map((item) => item.id), [4]);
  assert.equal(overflow.page, 3);

  assert.deepEqual(pageSlice([], 1, 50).items, []);
  assert.equal(pageSlice([], 1, 50).pages, 1);
});

test('导出：字段与文件名对齐 Qt5 _export_filtered_items', () => {
  const rows = [row({ id: 0, warnings: ['KANA'], src: 'Alice', dst: '爱丽丝' })];
  const records = JSON.parse(exportText(rows));
  assert.deepEqual(records, [{
    file_path: 'chapter_01.rpy', status: 'TRANSLATED', warnings: ['KANA'], src: 'Alice', dst: '爱丽丝',
  }]);

  assert.equal(exportFilename(new Date(2026, 9, 12, 21, 5, 7)), 'proofreading_filter_report_20261012_210507.json');
});
