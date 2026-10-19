/** 脚本修复 view 纯函数自检：扫描/修复摘句、类型明细、色调与默认选项。 */
import test from 'node:test';
import assert from 'node:assert/strict';

import {
  ERROR_REPAIR_DEFAULTS,
  REPAIR_TYPE_LABELS,
  buildEnvironmentFixBody,
  errorRepairOwnerProjectKey,
  errorRepairStatusPath,
  fixTone,
  formatRepairSummary,
  formatScanSummary,
  formatTypeBreakdown,
  repairTypeLabel,
  scanIsActionable,
} from '../renderer/src/errorRepairView.mjs';

test('默认只开安全项，高级项关闭', () => {
  assert.deepEqual(ERROR_REPAIR_DEFAULTS, {
    fixIndent: true,
    fixTrailingSpaces: true,
    fixEmptyBlocks: true,
    fixDuplicates: true,
    fixDialogueQuotes: true,
    fixIndentLevel: false,
    fixQuotes: false,
  });
});

test('状态路径编码目录', () => {
  assert.equal(errorRepairStatusPath(''), '/api/error-repair');
  assert.equal(errorRepairStatusPath('  '), '/api/error-repair');
  assert.equal(errorRepairStatusPath('C:/tl/chinese'), '/api/error-repair?folder=C%3A%2Ftl%2Fchinese');
});

test('扫描摘句：分组计数走新句式', () => {
  const result = {
    total_issues: 384,
    fixable_issues: 101,
    manual_issues: 283,
    environment_issues: [{ path: 'game/tl/chinese_new' }, { path: 'game/tl/english_new' }],
  };
  assert.equal(
    formatScanSummary(result, 'ZH'),
    '发现 384 个问题（可自动修复 101 个，需人工 283 个，环境问题 2 个）',
  );
  assert.equal(
    formatScanSummary(result, 'EN'),
    'Found 384 issue(s): 101 auto-fixable, 283 manual, 2 environment',
  );
});

test('扫描摘句：旧结果退回文件数句式', () => {
  assert.equal(
    formatScanSummary({ total_issues: 100000, affected_files: 42 }, 'ZH'),
    '发现 100000 个问题（42 个文件）',
  );
  assert.equal(
    formatScanSummary({ total_issues: 7, report: { 'a.rpy': [], 'b.rpy': [] } }, 'ZH'),
    '发现 7 个问题（2 个文件）',
  );
  assert.equal(formatScanSummary(null, 'ZH'), '尚未扫描');
  assert.equal(formatScanSummary(null, 'EN'), 'Not scanned');
});

test('修复摘句：文件/条数 + 环境处理 + 剩余人工', () => {
  const result = {
    fixed_files: 12,
    fixed_items: 101,
    failed_files: 1,
    environment_fixes: [{ ok: true }, { ok: false }],
    remaining_issues: 283,
  };
  assert.equal(
    formatRepairSummary(result, 'ZH'),
    '已修复 12 个文件、101 处；1 个文件失败；已处理 1 个环境问题；1 个环境问题处理失败；仍有 283 个问题需人工处理',
  );
  assert.match(formatRepairSummary(result, 'EN'), /^Fixed 12 file\(s\), 101 change\(s\)/);
  assert.match(formatRepairSummary(result, 'EN'), /283 issue\(s\) still need manual work$/);
});

test('修复摘句：未复扫时不谎报剩余数量', () => {
  const text = formatRepairSummary({ fixed_files: 0, fixed_items: 0, rescan_skipped: true }, 'ZH');
  assert.equal(text, '已修复 0 个文件、0 处；修复或复扫未完成，剩余问题数量未知');
  assert.doesNotMatch(text, /仍有/);
  assert.equal(formatRepairSummary(null, 'ZH'), '');
});

test('修复摘句：复扫未完成时 remaining_issues=null 显示为未知而不是 0', () => {
  const result = { fixed_files: 1, fixed_items: 2, remaining_issues: null, rescan_skipped: true };
  const zh = formatRepairSummary(result, 'ZH');
  assert.match(zh, /剩余问题数量未知$/);
  assert.doesNotMatch(zh, /仍有 0/);
  const en = formatRepairSummary(result, 'EN');
  assert.match(en, /remaining issues unknown$/);
  assert.doesNotMatch(en, /0 issue\(s\) still need/);
  // 即使旧字段缺失 rescan_skipped，null 也按未知处理。
  assert.match(formatRepairSummary({ remaining_issues: null }, 'ZH'), /未知$/);
  assert.equal(fixTone({ success: true, remaining_issues: null, rescan_skipped: true }), 'warning');
});

test('环境卡片请求体：只带所选目录，文件修复全关', () => {
  const body = buildEnvironmentFixBody({
    folder: 'C:/proj/game/tl/chinese',
    action: 'move',
    path: 'C:/proj/game/tl/japanese_new',
    ownerKey: 'proj|chinese',
  });
  assert.equal(body.environment_path, 'C:/proj/game/tl/japanese_new');
  assert.equal(body.environment_action, 'move');
  assert.equal(body.fix_environment, true);
  assert.equal(body.confirm, true);
  assert.equal(body.owner_project_key, 'proj|chinese');
  for (const key of [
    'fix_indent', 'fix_trailing_spaces', 'fix_empty_blocks', 'fix_duplicates',
    'fix_dialogue_quotes', 'fix_indent_level', 'fix_quotes',
  ]) {
    assert.equal(body[key], false, key);
  }
});

test('类型明细：计数降序、过滤零值、按语言连接', () => {
  const counts = { indent: 2, duplicate_old_new: 283, quotes: 0, empty_block: 7 };
  assert.equal(formatTypeBreakdown(counts, 'ZH'), '重复译文 283、空翻译块 7、缩进（Tab） 2');
  assert.equal(formatTypeBreakdown(counts, 'EN'), 'Duplicate strings 283, Empty blocks 7, Indentation (tabs) 2');
  assert.equal(formatTypeBreakdown({}, 'ZH'), '');
  assert.equal(formatTypeBreakdown(null, 'ZH'), '');
});

test('类型明细：同数按标签稳定排序', () => {
  assert.equal(
    formatTypeBreakdown({ quotes: 1, empty_block: 1 }, 'ZH'),
    '空翻译块 1、引号规范 1',
  );
});

test('类型标签：未登记类型原样返回', () => {
  assert.equal(repairTypeLabel('indent', 'ZH'), REPAIR_TYPE_LABELS.indent.ZH);
  assert.equal(repairTypeLabel('indent', 'EN'), 'Indentation (tabs)');
  assert.equal(repairTypeLabel('brand_new_type', 'ZH'), 'brand_new_type');
  assert.equal(repairTypeLabel(undefined, 'ZH'), '');
});

test('扫描结果是否可处理', () => {
  assert.equal(scanIsActionable(null), false);
  assert.equal(scanIsActionable({ total_issues: 0, fixable_issues: 0, manual_issues: 0, environment_issues: [] }), false);
  assert.equal(scanIsActionable({ total_issues: 3 }), true);
  assert.equal(scanIsActionable({ total_issues: 0, environment_issues: [{ path: 'x' }] }), true);
  assert.equal(scanIsActionable({ total_issues: 0, manual_sample: [{ file: 'a.rpy', line: 3 }] }), true);
});

test('修复色调：成功 / 有残留 / 失败', () => {
  assert.equal(fixTone({ success: true, fixed_items: 3 }), 'success');
  assert.equal(fixTone({ success: true, remaining_issues: 2 }), 'warning');
  assert.equal(fixTone({ success: true, failed_files: 1 }), 'warning');
  assert.equal(fixTone({ success: true, rescan_skipped: true }), 'warning');
  assert.equal(fixTone({ success: true, environment_fixes: [{ ok: false }] }), 'warning');
  assert.equal(fixTone({ success: false }), 'error');
  assert.equal(fixTone(null), 'error');
});

test('owner 快照优先取 status.owner_project_key', () => {
  assert.equal(errorRepairOwnerProjectKey({ owner_project_key: 'proj|chinese' }), 'proj|chinese');
  assert.equal(errorRepairOwnerProjectKey({ owner_project_key: '  proj|chinese  ' }), 'proj|chinese');
  assert.equal(errorRepairOwnerProjectKey({}), '');
  assert.equal(errorRepairOwnerProjectKey(null), '');
});
