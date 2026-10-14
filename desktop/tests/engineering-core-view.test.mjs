/** 工程核心三页 view 纯函数自检 */
import test from 'node:test';
import assert from 'node:assert/strict';

import {
  ERROR_REPAIR_DEFAULTS,
  errorRepairOwnerProjectKey,
  errorRepairStatusPath,
  formatFixSummary,
  formatScanSummary,
} from '../renderer/src/errorRepairView.mjs';
import {
  formatReuseSummary,
  reuseOwnerProjectKey,
  reusePathsConflict,
  translationReuseStatusPath,
} from '../renderer/src/translationReuseView.mjs';
import {
  FORMATTER_DEFAULTS,
  formatFormatterSummary,
  formatterOwnerProjectKey,
  formatterStatusPath,
} from '../renderer/src/formatterView.mjs';

test('error repair defaults match Qt', () => {
  assert.equal(ERROR_REPAIR_DEFAULTS.fixIndent, true);
  assert.equal(ERROR_REPAIR_DEFAULTS.fixIndentLevel, false);
  assert.equal(ERROR_REPAIR_DEFAULTS.fixQuotes, false);
  assert.equal(ERROR_REPAIR_DEFAULTS.fixDialogueQuotes, false);
  assert.equal(ERROR_REPAIR_DEFAULTS.fixEmptyBlocks, false);
});

test('error repair status path encodes folder', () => {
  assert.equal(errorRepairStatusPath(''), '/api/error-repair');
  assert.match(errorRepairStatusPath('C:/tl/chinese'), /folder=/);
});

test('scan/fix summaries', () => {
  assert.match(formatScanSummary({ total_issues: 0, report: {} }, 'ZH'), /0/);
  assert.equal(formatScanSummary({ total_issues: 100000, affected_files: 42 }, 'ZH'), '发现 100000 个问题（42 个文件）');
  assert.match(formatFixSummary({ fixed_files: 1, fixed_items: 2, failed_files: 1 }, 'ZH'), /失败/);
});

test('reuse path conflict detects nest and same', () => {
  assert.equal(reusePathsConflict('C:/a', 'C:/a'), true);
  assert.equal(reusePathsConflict('C:/a', 'C:/a/b'), true);
  assert.equal(reusePathsConflict('C:/a/b', 'C:/a'), true);
  assert.equal(reusePathsConflict('C:/a', 'C:/b'), false);
  assert.match(translationReuseStatusPath({ sourceDir: 'S', targetDir: 'T' }), /source_dir=/);
  assert.match(formatReuseSummary({ reusable_entries: 1, conflicts: 0, already_reused: 0, unmatched_entries: 0 }, 'ZH'), /可复用/);
});

test('formatter defaults and success wording', () => {
  assert.equal(FORMATTER_DEFAULTS.preserveComments, true);
  assert.equal(FORMATTER_DEFAULTS.fixIndent, true);
  assert.equal(FORMATTER_DEFAULTS.removeTrailing, true);
  assert.match(formatFormatterSummary({ success_count: 3, failed_files: [] }, 'ZH'), /成功处理 3/);
  assert.equal(formatterStatusPath('D:/x').includes('folder='), true);
});

test('owner snapshot helpers prefer status.owner_project_key', () => {
  assert.equal(errorRepairOwnerProjectKey({ owner_project_key: 'a|zh' }), 'a|zh');
  assert.equal(errorRepairOwnerProjectKey({ owner_project_key: '' }), '');
  assert.equal(formatterOwnerProjectKey({ owner_project_key: 'b|zh' }), 'b|zh');
  assert.equal(reuseOwnerProjectKey(null), '');
  assert.equal(reuseOwnerProjectKey({ owner_project_key: 'c|zh' }), 'c|zh');
});
