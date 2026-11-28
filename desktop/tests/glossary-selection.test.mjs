import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { parseSync, traverse } from '@babel/core';
import { transformSync as stripTypes } from 'esbuild';
const staged = process.env.GLOSSARY_SELECTION_CANDIDATE === '1';
const path = name => new URL(staged ? './.tmp/glossary-selection-' + name : '../renderer/src/' + name, import.meta.url);
const { readRowSelection, selectionContextChanged, selectActiveRow, selectCheckedRows, deleteCheckedRows, clearCheckedTranslations, glossarySelectionLabels } = await import(path('glossarySelection.mjs'));
const context = JSON.stringify(['project-a', '']);
const fixture = () => ['Help', 'History', 'Renpy', 'Mouse'].map((src, index) => ({ src, dst: 'translated-' + src, case_sensitive: index < 3, extra: { keep: index } }));

test('selection labels use the current boot language without changing the shared i18n context', () => {
  assert.equal(glossarySelectionLabels('EN').confirmCurrent, 'Confirm current row');
  assert.equal(glossarySelectionLabels('ZH').confirmCurrent, '确认当前行');
  assert.equal(glossarySelectionLabels(undefined).deleteSelected.replace('{count}', '3'), '删除所选（3）');
});

test('legacy number/null slot preserves only the active row and never implicitly checks it', () => {
  assert.deepEqual(readRowSelection(2, 4, context), { active: 2, checked: [], context });
  assert.deepEqual(readRowSelection(null, 4, context), { active: null, checked: [], context });
  const rows = fixture();
  assert.equal(deleteCheckedRows(rows, 2, context), rows);
});

test('checking Help History Renpy deletes exactly those three and retains Mouse and its metadata', () => {
  const rows = fixture();
  const original = structuredClone(rows);
  const selected = selectCheckedRows(null, ['0', '1', '2'], rows.length, context);
  const next = deleteCheckedRows(rows, selected, context);
  assert.deepEqual(next, [rows[3]]);
  assert.equal(next[0], rows[3]);
  assert.deepEqual(rows, original);
  assert.equal(selected.active, null);
});

test('case-sensitive flags alone do not mean rows are selected for deletion', () => {
  const rows = fixture();
  assert.equal(deleteCheckedRows(rows, null, context), rows);
  assert.deepEqual(readRowSelection(null, rows.length, context).checked, []);
});

test('active row changes preserve checked keys and do not expand a single-row operation', () => {
  const checks = selectCheckedRows(null, ['0', '2'], 4, context);
  const active = selectActiveRow(checks, '1', 4, context);
  assert.equal(active.active, 1);
  assert.deepEqual(active.checked, [0, 2]);
  assert.deepEqual(selectActiveRow(active, null, 4, context).checked, [0, 2]);
  assert.equal(checks.active, null);
});

test('a filtered History at visible position zero is deleted by original index one', () => {
  const rows = fixture();
  const matches = rows.map((row, index) => ({ row, index })).filter(entry => entry.row.src === 'History');
  const selected = selectCheckedRows(null, matches.map(entry => String(entry.index)), rows.length, context);
  assert.deepEqual(deleteCheckedRows(rows, selected, context).map(row => row.src), ['Help', 'Renpy', 'Mouse']);
});

test('page-one 25 keys plus row 30 delete exactly 26 while preserving the other second-page rows', () => {
  const rows = Array.from({ length: 30 }, (_, index) => ({ src: 'term-' + (index + 1) }));
  const firstPage = selectCheckedRows(null, Array.from({ length: 25 }, (_, index) => String(index)), 30, context);
  const crossPage = selectCheckedRows(firstPage, [...firstPage.checked.map(String), '29'], 30, context);
  assert.equal(crossPage.checked.length, 26);
  assert.deepEqual(deleteCheckedRows(rows, crossPage, context).map(row => row.src), ['term-26', 'term-27', 'term-28', 'term-29']);
  assert.deepEqual(selectCheckedRows(crossPage, ['29'], 30, context).checked, [29]);
});

test('source destination and case edits retain checkbox identities and untouched unsaved draft values', () => {
  const rows = fixture();
  const selected = selectCheckedRows(null, ['0', '2'], rows.length, context);
  const edited = rows.map((row, index) => index === 3 ? { ...row, src: 'Mouse edited', dst: 'unsaved translation', case_sensitive: true } : row);
  assert.deepEqual(readRowSelection(selected, edited.length, context).checked, [0, 2]);
  assert.deepEqual(deleteCheckedRows(edited, selected, context).map(row => row.src), ['History', 'Mouse edited']);
  assert.equal(deleteCheckedRows(edited, selected, context)[1].dst, 'unsaved translation');
});

test('search or project context changes clear selection and stale keys cannot delete new-context data', () => {
  const rows = fixture();
  const selected = selectCheckedRows(null, ['1'], rows.length, context);
  for (const nextContext of [JSON.stringify(['project-b', '']), JSON.stringify(['project-a', 'History'])]) {
    assert.equal(selectionContextChanged(selected, nextContext), true);
    assert.deepEqual(readRowSelection(selected, rows.length, nextContext), { active: null, checked: [], context: nextContext });
    assert.equal(deleteCheckedRows(rows, selected, nextContext), rows);
  }
  assert.deepEqual(readRowSelection(null, 3, context).checked, []);
});

test('invalid duplicate and out-of-range keys fail closed rather than coercing a different row', () => {
  const selected = selectCheckedRows(null, ['', '01', '1x', '1.0', -1, 5, NaN, Infinity, null, '1', 1, '3'], 4, context);
  assert.deepEqual(selected.checked, [1, 3]);
  assert.equal(readRowSelection(-1, 4, context).active, null);
  assert.equal(readRowSelection(10, 4, context).active, null);
});

const pageSource = readFileSync(path(staged ? 'GlossaryPage.tsx' : 'pages/GlossaryPage.tsx'), 'utf8');
const sheetSource = readFileSync(path(staged ? 'DataSheet.tsx' : 'components/DataSheet.tsx'), 'utf8');
const parsed = parseSync(pageSource, { babelrc: false, configFile: false, parserOpts: { plugins: ['typescript', 'jsx'] } });
function variable(name) {
  let found;
  traverse(parsed, { VariableDeclarator(p) { if (p.node.id.type === 'Identifier' && p.node.id.name === name) found = p.node.init; } });
  assert.ok(found, name + ' exists');
  return pageSource.slice(found.start, found.end);
}

test('checkbox wiring is local-only; structural setRows clears selection but inline edits preserve it', () => {
  const remove = variable('removeSelected');
  assert.match(remove, /deleteCheckedRows\(previous, selected, selectionContext\)/);
  assert.match(remove, /rowsRef\.current/);
  assert.doesNotMatch(remove, /request\(|save\(|fetch\(/);
  assert.match(variable('setRows'), /resetSelection = true/);
  assert.match(variable('setRows'), /if \(resetSelection\) setSelected\(null\)/);
  assert.doesNotMatch(variable('commitEdit'), /setSelected\(/);
  let checkboxWiring;
  traverse(parsed, { JSXAttribute(p) { if (p.node.name.name === 'rowSelection') checkboxWiring = pageSource.slice(p.node.start, p.node.end); } });
  assert.match(checkboxWiring, /selectCheckedRows/);
  assert.doesNotMatch(checkboxWiring, /setDirty|setRows|setStoredRows/);
  assert.match(variable('confirmSelected'), /rows\[selection\.active\]/);
  assert.doesNotMatch(variable('confirmSelected'), /selection\.checked/);
});

test('shared sheet multi-selection is opt-in, page-scoped, key-preserving, and isolated from row editing', () => {
  assert.match(sheetSource, /rowSelection\?:/);
  assert.match(sheetSource, /rowSelection=\{rowSelection \?/);
  assert.match(sheetSource, /preserveSelectedRowKeys: true/);
  assert.match(sheetSource, /dataSource=\{visible\}/);
  assert.match(sheetSource, /data-testid="sheet-page-select"/);
  assert.match(sheetSource, /getTitleCheckboxProps/);
  assert.match(sheetSource, /sheet-row-select-/);
  const controls = sheetSource.slice(sheetSource.indexOf('rowSelection={rowSelection ?'), sheetSource.indexOf('columns={tableColumns}'));
  assert.match(controls, /onClick=.*stopPropagation/);
  assert.match(controls, /onDoubleClick=.*stopPropagation/);
  assert.match(controls, /onKeyDown=.*stopPropagation/);
  assert.match(pageSource, /case_sensitive: checked, hits: '' \} : item\), false\)/);
});

test('case sensitivity has its own visible header and category content stays separate', () => {
  let columnNodes;
  traverse(parsed, { JSXAttribute(path) {
    if (path.node.name.name === 'columns') columnNodes = path.node.value.expression.elements;
  } });
  const property = (node, name) => node.properties.find(item => item.key.name === name)?.value;
  const column = key => columnNodes.find(node => property(node, 'key')?.value === key);
  const type = column('type');
  const sensitive = column('case_sensitive');
  assert.equal(property(type, 'width').value, '14%');
  assert.equal(property(sensitive, 'width').value, '9%');
  assert.equal(property(sensitive, 'title').arguments[0].value, 'lexicon_case_sensitive');
  assert.equal(property(sensitive, 'editKey'), undefined);
  const categorySource = pageSource.slice(type.start, type.end);
  const sensitiveSource = pageSource.slice(sensitive.start, sensitive.end);
  assert.match(categorySource, /displayType|lexicon_candidate/);
  assert.doesNotMatch(categorySource, /Checkbox|case_sensitive/);
  assert.match(sensitiveSource, /aria-label=\{t\('lexicon_case_sensitive'\)\}/);
  assert.match(sensitiveSource, /i === index/);
  assert.match(sensitiveSource, /case_sensitive: checked, hits: '' \} : item\), false\)/);
  assert.match(sensitiveSource, /onClick=.*stopPropagation/);
  assert.match(sensitiveSource, /onDoubleClick=.*stopPropagation/);
  assert.match(sensitiveSource, /onKeyDown=.*stopPropagation/);
});

function actualEffect(source, hook, dependency, bindings) {
  const ast = parseSync(source, { babelrc: false, configFile: false, parserOpts: { plugins: ['typescript', 'jsx'] } });
  let callback;
  traverse(ast, { CallExpression(path) {
    const { callee, arguments: args } = path.node;
    if (callee.type === 'Identifier' && callee.name === hook && args[1]?.type === 'ArrayExpression' && args[1].elements.length === 1 && args[1].elements[0]?.name === dependency) callback = source.slice(args[0].start, args[0].end);
  } });
  assert.ok(callback, hook + ' [' + dependency + '] exists');
  const code = stripTypes('module.exports = ' + callback + ';', { loader: 'ts', format: 'cjs' }).code;
  const module = { exports: null };
  new Function(...Object.keys(bindings), 'module', code)(...Object.values(bindings), module);
  return module.exports();
}

test('actual generation effect preserves legacy-ref migration and Fast Refresh but cancels true structural changes', () => {
  const pending = { target: { rowKey: '3', columnKey: 'src' }, value: 'Mouse edited', original: 'Mouse' };
  const editRef = { current: pending };
  const flushKeyRef = { current: 'project-a' };
  const calls = [];
  const run = editGeneration => actualEffect(sheetSource, 'useLayoutEffect', 'editGeneration', {
    editGeneration, editRef, flushKeyRef,
    setEditing: value => calls.push(['editing', value]),
    setDraft: value => calls.push(['draft', value]),
    onDraftChange: value => calls.push(['dirty', value]),
  });
  run(4);
  assert.equal(editRef.current, pending);
  assert.equal(flushKeyRef.lastEditGeneration, 4);
  run(4);
  assert.equal(editRef.current.value, 'Mouse edited');
  assert.deepEqual(calls, []);
  assert.equal(flushKeyRef.current, 'project-a');
  run(5);
  assert.equal(editRef.current, null);
  assert.deepEqual(calls, [['editing', null], ['draft', ''], ['dirty', false]]);
  assert.equal(flushKeyRef.current, 'project-a');
});

test('actual dirty-project effect clears only the false same-project error and never reloads unsaved rows', () => {
  const message = '项目已变更，请先导出未保存的词条，再重新载入当前项目。';
  const run = (ownerProject, projectKey, initialError) => {
    let error = initialError;
    let reloads = 0;
    actualEffect(pageSource, 'useEffect', 'projectKey', {
      ownerProject, projectKey, snapshot: null, operation: { current: 1 }, taskOwner: { current: null }, dirtyRef: { current: true },
      setJob() {}, setBusy() {}, clearScanWarning() {},
      setError: value => { error = typeof value === 'function' ? value(error) : value; },
      request: () => { reloads += 1; throw new Error('Must not reload a dirty draft'); },
      setSnapshot: () => { throw new Error('Must not replace a dirty snapshot'); },
    });
    assert.equal(reloads, 0);
    return error;
  };
  assert.equal(run('project-a', 'project-a', message), '');
  assert.equal(run('project-a', 'project-a', 'Other network error'), 'Other network error');
  assert.equal(run('project-a', 'project-b', ''), message);
});

test('actual same-project refresh preserves a clean snapshot and live task ownership before any reset', () => {
 const operation={current:7},live={id:'running-job',project:'project-a',generation:4},taskOwner={current:live};let error='Other network error';const forbidden=()=>{throw new Error('Must not reset or reload a live same-project task');};
 actualEffect(pageSource,'useEffect','projectKey',{snapshot:{rows:[]},ownerProject:'project-a',projectKey:'project-a',operation,taskOwner,dirtyRef:{current:false},setJob:forbidden,setBusy:forbidden,clearScanWarning:forbidden,setSnapshot:forbidden,request:forbidden,setError:value=>{error=typeof value==='function'?value(error):value;}});
 assert.equal(operation.current,7);assert.equal(taskOwner.current,live);assert.equal(error,'Other network error');
});

test('clearCheckedTranslations blanks dst only and leaves unchecked row objects in place', () => {
  const kept = { src: 'B', dst: '乙', type: '地', candidate: false, record_id: 'keep' };
  const rows = [
    { src: 'A', dst: '甲', type: '名', candidate: true, candidate_confirmed: false, record_id: 'r1', info: 'note', case_sensitive: true },
    kept,
    { src: 'C', dst: '', type: '空', candidate: true, record_id: 'r3' },
  ];
  const selected = selectCheckedRows(null, ['0'], rows.length, context);
  const outcome = clearCheckedTranslations(rows, selected, context);
  assert.equal(outcome.changed, 1);
  assert.equal(outcome.rows[0].dst, '');
  assert.equal(outcome.rows[0].src, 'A');
  assert.equal(outcome.rows[0].type, '名');
  assert.equal(outcome.rows[0].candidate, true);
  assert.equal(outcome.rows[0].candidate_confirmed, false);
  assert.equal(outcome.rows[0].record_id, 'r1');
  assert.equal(outcome.rows[0].info, 'note');
  assert.equal(outcome.rows[0].case_sensitive, true);
  assert.equal(outcome.rows[1], kept);
  assert.equal(kept.dst, '乙');
  assert.equal(rows[0].dst, '甲');
});

test('checked rows that already have an empty dst do not count as changed', () => {
  const rows = [{ src: 'A', dst: '' }, { src: 'B', dst: '  ' }];
  const outcome = clearCheckedTranslations(rows, selectCheckedRows(null, ['0'], rows.length, context), context);
  assert.equal(outcome.changed, 0);
  assert.equal(outcome.rows.length, rows.length);
  assert.equal(outcome.rows[0].dst, '');
  assert.notEqual(outcome.rows, rows);
});

test('no checked rows returns the original array and changes nothing', () => {
  const rows = [{ src: 'A', dst: '甲' }];
  const outcome = clearCheckedTranslations(rows, null, context);
  assert.equal(outcome.rows, rows);
  assert.equal(outcome.changed, 0);
});

test('clear-dst button and translate buttons use the shared selection without touching full-table exports', () => {
  assert.match(pageSource, /data-testid="glossary-clear-dst-selected"/);
  assert.match(variable('clearSelectedTranslations'), /clearCheckedTranslations\(rowsRef\.current, selected, selectionContext\)/);
  assert.doesNotMatch(variable('clearSelectedTranslations'), /request\(|save\(|fetch\(/);
  const buttonAt = (marker) => {
    const at = pageSource.indexOf(marker);
    return pageSource.slice(pageSource.lastIndexOf('<Button', at), pageSource.indexOf('</Button>', at));
  };
  for (const segment of [buttonAt("mode: 'llm'"), buttonAt("mode: 'fast'")]) {
    assert.match(segment, /translateTargets\(\)\.rows\.length === 0/);
    assert.match(segment, /targets\.rows\.map\(toApiRow\)/);
    assert.match(segment, /pendingTranslateIndices\.current = targets\.indices/);
    assert.doesNotMatch(segment, /rowsRef\.current\.map\(toApiRow\)/);
  }
  assert.match(variable('translateTargets'), /readRowSelection\(selected, rowsRef\.current\.length, selectionContext\)/);
  assert.match(pageSource, /rowsRef\.current\.map\(toApiRow\)/);
});
