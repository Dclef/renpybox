import assert from 'node:assert/strict';
import test from 'node:test';

import {
  advancedMustStayOpen,
  buildNewRule,
  canApplySelection,
  canContinuePreview,
  canSaveBind,
  categoryScopeKey,
  clampScanPage,
  cloneProfileDraft,
  formatPageLabel,
  formatSelectionSummary,
  isEditorDirty,
  isPageDirty,
  isSelectionDirty,
  modeNeedsProfile,
  RPY_PAGE_SIZE,
} from '../renderer/src/rpyExtractionView.mjs';

test('builtin 不需要方案，combined/custom 需要', () => {
  assert.equal(modeNeedsProfile('builtin'), false);
  assert.equal(modeNeedsProfile('combined'), true);
  assert.equal(modeNeedsProfile('custom'), true);
  assert.equal(advancedMustStayOpen('combined'), true);
  assert.equal(advancedMustStayOpen('builtin'), false);
});

test('未保存下拉与已生效分离', () => {
  const applied = { mode: 'builtin', profileId: null, name: '未选择自定义方案' };
  const pending = { mode: 'combined', profileId: 'abc', name: '我的方案' };
  assert.equal(isSelectionDirty(applied, pending), true);
  assert.equal(isSelectionDirty(applied, applied), false);
  const summary = formatSelectionSummary(applied, pending, {
    current: '当前已生效：{mode} · {name}',
    pending: '未保存：{mode} · {name}（点「应用设置」后生效）',
    modes: { builtin: '只用内置', combined: '内置＋自定义', custom: '仅自定义' },
    noProfile: '未选择自定义方案',
  });
  assert.match(summary, /未保存/);
  assert.match(summary, /内置＋自定义/);
  assert.match(formatSelectionSummary(applied, applied), /当前已生效/);
});

test('应用校验：非 builtin 无方案不可用；custom 需启用规则', () => {
  assert.equal(canApplySelection('builtin', null), true);
  assert.equal(canApplySelection('combined', null), false);
  assert.equal(canApplySelection('combined', 'id'), true);
  assert.equal(canApplySelection('custom', 'id', { rules: [{ enabled: false }] }), false);
  assert.equal(canApplySelection('custom', 'id', { rules: [{ enabled: true }] }), true);
});

test('预览状态与分类键；本地失效 scan 不可保存', () => {
  assert.equal(canSaveBind({ completed: true, error: '' }), true);
  assert.equal(canSaveBind({ has_scan: false, completed: true, error: '' }), false);
  assert.equal(canSaveBind({ completed: false, error: '' }), false);
  assert.equal(canContinuePreview({ completed: false, error: '' }), true);
  assert.equal(canContinuePreview({ completed: true, error: '' }), false);
  assert.equal(categoryScopeKey('tl'), 'tl');
  assert.equal(categoryScopeKey('source'), 'source');
});

test('分页 200：第 2 页可达第 201 条', () => {
  assert.equal(RPY_PAGE_SIZE, 200);
  assert.equal(clampScanPage(1, 201), 1);
  assert.equal(clampScanPage(2, 201), 2);
  assert.equal(clampScanPage(99, 201), 2);
  assert.equal(formatPageLabel(2, 201), '2 / 2');
});

test('编辑器 dirty 与页面 dirty', () => {
  const editor = { id: 'a', name: 'x', note: '', category: 'source', rules: [] };
  const baseline = JSON.stringify(editor);
  assert.equal(isEditorDirty(editor, baseline), false);
  assert.equal(isEditorDirty({ ...editor, name: 'y' }, baseline), true);
  assert.equal(isPageDirty(false, true), true);
  assert.equal(isPageDirty(true, false), true);
  assert.equal(isPageDirty(false, false), false);
});

test('TL 模板新增规则与 clone 新 id', () => {
  const tlTemplate = {
    pattern: String.raw`^\s*old\s+(?P<text>"(?:\\.|[^"\\])*")\s*$`,
    include_globs: ['*.rpy'],
    flags: [],
    text_group: 'text',
    note: '',
    positive_samples: ['old "Hello."'],
    negative_samples: ['jump next_label'],
  };
  const rule = buildNewRule(tlTemplate, 1);
  assert.match(rule.pattern, /old/);
  assert.equal(rule.enabled, true);
  assert.equal(rule.name, '规则 1');

  const profile = { id: 'old', name: '方案', note: '', category: 'tl', rules: [rule] };
  const cloned = cloneProfileDraft(profile, '（副本）');
  assert.ok(cloned);
  assert.notEqual(cloned.id, 'old');
  assert.match(cloned.name, /副本/);
});
