import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { applyTranslate, mapSubsetResults, translateSnapshotsMatch, translateTargetRows } from '../renderer/src/glossaryTranslate.mjs';

const pageSource = readFileSync(new URL('../renderer/src/pages/GlossaryPage.tsx', import.meta.url), 'utf8');

test('translate targets keep original indexes and skip rows that already have a translation', () => {
  const rows = Array.from({ length: 10 }, (_, index) => ({ src: 's' + index, dst: '' }));
  rows[5].dst = '已有';
  rows[2].dst = 's2';
  rows[8].dst = '  ';
  const picked = translateTargetRows(rows, [2, 5, 8]);
  assert.deepEqual(picked.indices, [2, 8]);
  assert.deepEqual(picked.rows.map((row) => row.src), ['s2', 's8']);
  assert.equal(picked.rows[0], rows[2]);
  const all = translateTargetRows(rows, []);
  assert.deepEqual(all.indices, [0, 1, 2, 3, 4, 6, 7, 8, 9]);
});

test('subset result indexes map onto the full table and out-of-range indexes are dropped', () => {
  assert.deepEqual(mapSubsetResults([12, 13, 14, 15], [[0, '猛男'], [1, '红']]), [[12, '猛男'], [13, '红']]);
  assert.deepEqual(mapSubsetResults([12, 13], [[0, '甲'], [4, '越界'], [-1, '负']]), [[12, '甲']]);
  assert.deepEqual(mapSubsetResults([], [[0, '甲']]), []);
  assert.deepEqual(mapSubsetResults(undefined, [[0, '甲']]), []);
});

test('applyTranslate writes mapped rows and keeps the unmapped full-table behavior', () => {
  const rows = Array.from({ length: 16 }, (_, index) => ({ src: 's' + index, dst: index < 12 ? 'keep' + index : '', candidate: index === 12 }));
  const applied = applyTranslate(rows, [[0, '猛男'], [1, '红'], [9, '丢']], [12, 13, 14, 15]);
  assert.equal(applied.applied, 2);
  assert.equal(applied.rows[0].dst, 'keep0');
  assert.equal(applied.rows[12].dst, '猛男');
  assert.equal(applied.rows[12].candidate_confirmed, true);
  assert.equal(applied.rows[13].dst, '红');
  assert.equal(rows[12].dst, '');
  const legacy = applyTranslate([{ src: 'a', dst: '' }, { src: 'b', dst: '已译' }], [[0, '甲'], [1, '不应覆盖']]);
  assert.equal(legacy.applied, 1);
  assert.equal(legacy.rows[0].dst, '甲');
  assert.equal(legacy.rows[1].dst, '已译');
});

test('subset snapshots compare the indexed rows and a missing map still compares the whole table', () => {
  const rows = [{ src: 'a', dst: '' }, { src: 'b', dst: '已' }, { src: 'c', dst: '' }];
  assert.equal(translateSnapshotsMatch(rows, [{ src: 'c', dst: '' }], [2]), true);
  assert.equal(translateSnapshotsMatch(rows, [{ src: 'a', dst: '' }], [2]), false);
  assert.equal(translateSnapshotsMatch(rows, rows, undefined), true);
  assert.equal(translateSnapshotsMatch(rows, [{ src: 'c', dst: '' }], undefined), false);
});

test('translate results go through the stored index map', () => {
  const at = pageSource.indexOf("job.kind === 'lexicon_translate' && Array.isArray(result.results)");
  const block = pageSource.slice(at, at + 700);
  assert.match(block, /translateIndices/);
  assert.match(block, /applyTranslate\(previous, result\.results!, indices\)/);
  assert.doesNotMatch(block, /applyTranslate\(previous, result\.results!\)/);
});
