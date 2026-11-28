import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { classifyWarning, importMergeLabels, mergeImportedRows, normalizeImportRows } from '../renderer/src/glossaryImport.mjs';

const term = (src, extra = {}) => ({ src, dst: '', type: '', info: '', case_sensitive: false, regex: false, ...extra });

test('map and array forms normalize the same way; bad input returns an error and does not throw', () => {
  const fields = { dst: 'A', info: 'i', type: '名', case_sensitive: true, regex: true, comment: 'no' };
  const fromArray = normalizeImportRows([{ src: '甲', ...fields }, { src: '   ' }, { src: '乙', comment: 'c', case_sensitive: 'yes', regex: 1 }]);
  const fromMap = normalizeImportRows({ 甲: fields, '   ': 'x', 乙: { comment: 'c', case_sensitive: 'yes', regex: 1 } });
  assert.equal(fromArray.error, '');
  assert.deepEqual(fromArray.rows, fromMap.rows);
  assert.deepEqual(fromArray.rows, [
    { src: '甲', dst: 'A', type: '名', info: 'i', case_sensitive: true, regex: true },
    { src: '乙', dst: '', type: '', info: 'c', case_sensitive: false, regex: false },
  ]);
  assert.deepEqual(normalizeImportRows({ 甲: 'A' }).rows, normalizeImportRows([term('甲', { dst: 'A' })]).rows);
  assert.equal(normalizeImportRows([{ src: '甲', info: '', comment: 'c' }]).rows[0].info, '');
  for (const bad of [null, undefined, 1, 'x', true, [{ dst: 'a' }], { 甲: 1 }, [null]]) {
    assert.doesNotThrow(() => normalizeImportRows(bad));
    const out = normalizeImportRows(bad);
    assert.deepEqual(out.rows, []);
    assert.match(out.error, /数组|映射/);
  }
  assert.equal(importMergeLabels('EN').lexicon_import_keep, 'Keep existing (recommended)');
  assert.equal(importMergeLabels(null).lexicon_import_merge_title, '导入术语表');
});

test('keep leaves existing row objects untouched and appends new rows as non-candidates', () => {
  const old = { src: 'Chad', dst: '查德', info: '人工', type: '名', case_sensitive: true, regex: false, enabled: true, record_id: 'keep', candidate: true, hits: '3' };
  const rows = [old];
  const next = mergeImportedRows(rows, [{ src: 'Chad', dst: '新', info: '盖', candidate: true, record_id: 'no' }, { src: 'Amy', dst: '艾米', candidate: true, record_id: 'no' }], 'keep');
  assert.equal(next.rows[0], old);
  assert.equal(old.dst, '查德');
  assert.equal(old.candidate, true);
  assert.equal(next.added, 1);
  assert.equal(next.duplicate, 1);
  assert.equal(next.kept, 1);
  assert.equal(next.rows[1].candidate, false);
  assert.equal(next.rows[1].candidate_confirmed, false);
  assert.equal(next.rows[1].hits, '');
  assert.equal(next.rows[1].dst, '艾米');
  assert.equal(next.rows[1].record_id, undefined);
  assert.notEqual(next.rows, rows);
  const same = mergeImportedRows(rows, [{ src: 'Chad', dst: '新' }], 'keep');
  assert.equal(same.added, 0);
  assert.equal(same.rows, rows);
});

test('fill writes dst only when empty or equal to src, and info only when empty', () => {
  const blank = { src: 'A', dst: '', info: '', type: '', record_id: 'r', candidate: true };
  const filled = mergeImportedRows([blank], [{ src: 'A', dst: '译', info: '注', type: '名', case_sensitive: true, regex: true }], 'fill');
  assert.equal(filled.filled, 1);
  assert.equal(filled.rows[0].dst, '译');
  assert.equal(filled.rows[0].info, '注');
  assert.equal(filled.rows[0].type, '名');
  assert.equal(filled.rows[0].case_sensitive, true);
  assert.equal(filled.rows[0].record_id, 'r');
  assert.equal(filled.rows[0].candidate, true);
  assert.equal(blank.dst, '');
  const kept = { src: 'A', dst: '已有', info: '留', type: '旧' };
  const sibling = { src: 'B', dst: 'b' };
  const current = [kept, sibling];
  const partial = mergeImportedRows(current, [{ src: 'A', dst: '新', info: '盖', type: '新' }], 'fill');
  assert.equal(partial.rows[0].dst, '已有');
  assert.equal(partial.rows[0].info, '留');
  assert.equal(partial.rows[0].type, '旧');
  assert.equal(partial.filled, 0);
  assert.equal(partial.rows, current);
  assert.equal(partial.rows[0], kept);
  assert.equal(partial.rows[1], sibling);
  const copied = { src: 'A', dst: 'A', info: '留' };
  assert.equal(mergeImportedRows([copied], [{ src: 'A', dst: '译', info: '盖' }], 'fill').rows[0].dst, '译');
  assert.equal(mergeImportedRows([copied], [{ src: 'A', dst: '译', info: '盖' }], 'fill').rows[0].info, '留');
  assert.equal(mergeImportedRows([{ src: 'A', dst: ' A ' }], [{ src: 'A', dst: '译' }], 'fill').rows[0].dst, '译');
  assert.equal(mergeImportedRows([{ src: 'A', dst: 'a' }], [{ src: 'A', dst: '译' }], 'fill').rows[0].dst, 'a');
  const spaced = { src: 'A', dst: '有', info: '  ', type: '  ' };
  const notes = mergeImportedRows([spaced], [{ src: 'A', dst: '新', info: '注', type: '名' }], 'fill');
  assert.equal(notes.rows[0].dst, '有');
  assert.equal(notes.rows[0].info, '注');
  assert.equal(notes.rows[0].type, '名');
  const flagged = { src: 'A', dst: '有', case_sensitive: true, regex: true };
  const flagRows = [flagged];
  const flags = mergeImportedRows(flagRows, [{ src: 'A', dst: '新', case_sensitive: false, regex: false }], 'fill');
  assert.equal(flags.filled, 0);
  assert.equal(flags.rows, flagRows);
  assert.equal(flags.rows[0], flagged);
  const off = { src: 'A', dst: '有', case_sensitive: false };
  const on = mergeImportedRows([off], [{ src: 'A', case_sensitive: true, regex: true }], 'fill');
  assert.equal(on.filled, 1);
  assert.equal(on.rows[0].case_sensitive, true);
  assert.equal(on.rows[0].regex, true);
  assert.equal(on.rows[0].dst, '有');
  assert.equal(off.case_sensitive, false);
});

test('overwrite replaces the row in place and keeps neighbor references', () => {
  const a = { src: 'A', dst: 'a' };
  const b = { src: 'B', dst: 'b', info: 'old', type: 'old', case_sensitive: true, regex: true, record_id: 'id', candidate: true };
  const c = { src: 'C', dst: 'c' };
  const next = mergeImportedRows([a, b, c], [{ src: 'B', dst: 'new', info: 'n', type: 't', case_sensitive: false, regex: false }], 'overwrite');
  assert.equal(next.rows[0], a);
  assert.equal(next.rows[2], c);
  assert.equal(next.replaced, 1);
  assert.equal(next.rows.length, 3);
  assert.deepEqual(next.rows[1], { src: 'B', dst: 'new', type: 't', info: 'n', case_sensitive: false, regex: false, candidate: false, candidate_confirmed: false, hits: '' });
  assert.equal(b.record_id, 'id');
  assert.equal(b.dst, 'b');
});

test('incoming duplicates keep the first row and overwrite keeps the last', () => {
  const incoming = [{ src: 'New', dst: 'first', info: 'f' }, { src: ' new ', dst: 'last', info: 'l' }];
  assert.equal(mergeImportedRows([], incoming, 'keep').rows[0].dst, 'first');
  assert.equal(mergeImportedRows([], incoming, 'fill').rows[0].info, 'f');
  assert.equal(mergeImportedRows([], incoming, 'overwrite').rows[0].dst, 'last');
  assert.equal(mergeImportedRows([], incoming, 'overwrite').rows[0].info, 'l');
  const current = [{ src: 'New', dst: 'old', info: 'stay' }];
  assert.equal(mergeImportedRows(current, incoming, 'keep').rows[0], current[0]);
  assert.equal(mergeImportedRows(current, incoming, 'overwrite').rows[0].dst, 'last');
  assert.equal(mergeImportedRows(current, incoming, 'overwrite').duplicate, 1);
  assert.equal(mergeImportedRows([], [{ src: 'A', dst: '1' }, { src: 'A', dst: '2' }], 'keep').added, 1);
});

test('quote and space variants share the Chad key', () => {
  const row = { src: 'Chad', dst: '查德', info: 'n', case_sensitive: true, regex: false, record_id: 'id', candidate: false };
  const rows = [row];
  for (const src of [' Chad ', '"CHAD"', 'Chad']) {
    const next = mergeImportedRows(rows, [{ src, dst: 'x' }], 'keep');
    assert.equal(next.added, 0);
    assert.equal(next.duplicate, 1);
    assert.equal(next.rows, rows);
    assert.equal(next.rows[0], row);
    assert.equal(row.dst, '查德');
  }
  const both = mergeImportedRows(rows, [{ src: ' Chad ', dst: '1' }, { src: '"CHAD"', dst: '2' }], 'keep');
  assert.equal(both.duplicate, 1);
  assert.equal(both.added, 0);
  assert.equal(both.rows, rows);
});

test('applying the same file again adds nothing and returns the same array', () => {
  const base = [{ src: 'Chad', dst: '查德', info: 'n' }];
  const file = [{ src: 'Chad', dst: '其他' }, { src: 'Amy', dst: '艾米', info: 'a' }];
  const once = mergeImportedRows(base, file, 'keep');
  const twice = mergeImportedRows(once.rows, file, 'keep');
  assert.equal(twice.added, 0);
  assert.equal(twice.rows, once.rows);
  const filled = mergeImportedRows([{ src: 'A', dst: '' }], [{ src: 'A', dst: '译', info: 'i' }], 'fill');
  const filledAgain = mergeImportedRows(filled.rows, [{ src: 'A', dst: '译', info: 'i' }], 'fill');
  assert.equal(filledAgain.added, 0);
  assert.equal(filledAgain.filled, 0);
  assert.equal(filledAgain.rows, filled.rows);
  const replaced = mergeImportedRows([{ src: 'A', dst: 'a' }], [{ src: 'A', dst: 'b', info: 'n', type: 't', case_sensitive: true, regex: false }], 'overwrite');
  const replacedAgain = mergeImportedRows(replaced.rows, [{ src: 'A', dst: 'b', info: 'n', type: 't', case_sensitive: true, regex: false }], 'overwrite');
  assert.equal(replacedAgain.added, 0);
  assert.equal(replacedAgain.replaced, 0);
  assert.equal(replacedAgain.rows, replaced.rows);
});

test('glossary page import merges instead of replacing the sheet or appending raw json', () => {
  const source = readFileSync(new URL('../renderer/src/pages/GlossaryPage.tsx', import.meta.url), 'utf8');
  const excel = source.slice(source.indexOf('const importExcel'), source.indexOf('const exportExcel'));
  const json = source.slice(source.indexOf('const importJson'), source.indexOf('const exportJson'));
  const apply = source.slice(source.indexOf('const applyPendingImport'), source.indexOf('const addRow'));
  assert.match(excel, /normalizeImportRows/);
  assert.match(json, /normalizeImportRows/);
  assert.doesNotMatch(excel, /setRows/);
  assert.doesNotMatch(json, /setRows/);
  assert.doesNotMatch(source, /\[\.\.\.previous,\s*\.\.\.incoming\]/);
  assert.match(apply, /mergeImportedRows\(rowsRef\.current, pending\.incoming, importStrategy\)/);
  assert.match(apply, /operation\.current/);
  assert.match(apply, /projectRef\.current/);
  assert.match(apply, /generation\.current/);
  assert.match(apply, /cellDirty/);
  assert.match(source, /lexicon_import_merge_title/);
  assert.match(source, /useState<ImportStrategy>\('keep'\)/);
  assert.match(source, /role="radiogroup"/);
  assert.match(source, /rb-import-strategy/);
  assert.match(source, /data-selected/);
  assert.match(source, /lexicon_import_effect_keep/);
});

test('classifyWarning labels the failure and splits the first colon', () => {
  assert.deepEqual(classifyWarning('第 1 块未能取得结果：RateLimitError 429 rate limit'), {
    kind: 'rate', head: '第 1 块未能取得结果', detail: 'RateLimitError 429 rate limit',
  });
  assert.equal(classifyWarning('第 2 块：APITimeoutError 504 Read timed out').kind, 'timeout');
  assert.deepEqual(classifyWarning('head: detail'), { kind: 'other', head: 'head', detail: 'detail' });
  assert.equal(classifyWarning('connection reset by peer').kind, 'connection');
  assert.equal(classifyWarning('BadRequestError 400').kind, 'request');
  assert.equal(classifyWarning('任务已取消').kind, 'cancel');
  assert.equal(classifyWarning('Cancelled by user').kind, 'cancel');
  assert.deepEqual(classifyWarning('plain note'), { kind: 'other', head: '', detail: 'plain note' });
  assert.deepEqual(classifyWarning(null), { kind: 'other', head: '', detail: '' });
  assert.deepEqual(classifyWarning(undefined), { kind: 'other', head: '', detail: '' });
  assert.deepEqual(classifyWarning(12), { kind: 'other', head: '', detail: '12' });
});
