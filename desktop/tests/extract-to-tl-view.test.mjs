import assert from 'node:assert/strict';
import test from 'node:test';

import {
  extractToTlStatusPath,
  extractToTlStatusTone,
  isEffectiveTlRpy,
  normalizeSupplementMode,
  preferredSuspiciousOpenPath,
  resolveExtractSwitches,
  shouldUseIncremental,
} from '../renderer/src/extractToTlView.mjs';

test('有效 tl rpy 排除 hook / 自动替换 / 默认语言脚本', () => {
  assert.equal(isEffectiveTlRpy('strings.rpy'), true);
  assert.equal(isEffectiveTlRpy('hook_add.rpy'), false);
  assert.equal(isEffectiveTlRpy('miss_ready_replace_x.rpy'), false);
  assert.equal(isEffectiveTlRpy('replace_text_auto.rpy'), false);
  assert.equal(isEffectiveTlRpy('set_default_language_at_startup.rpy'), false);
});

test('仅有有效译文时启用增量', () => {
  assert.equal(shouldUseIncremental(['hook_x.rpy']), false);
  assert.equal(shouldUseIncremental(['hook_x.rpy', 'dialog.rpy']), true);
  assert.equal(shouldUseIncremental(null), false);
});

test('自定义规则强制关闭官方与补充；无 EXE 时官方回退', () => {
  assert.deepEqual(
    resolveExtractSwitches({ useOfficial: true, useCustom: true, ruleMode: 'custom' }),
    { useOfficial: false, useCustom: false, ruleMode: 'custom' },
  );
  assert.deepEqual(
    resolveExtractSwitches({ useOfficial: true, useCustom: false, hasExe: false }),
    { useOfficial: false, useCustom: true, ruleMode: 'builtin' },
  );
  assert.deepEqual(
    resolveExtractSwitches({ useOfficial: false, useCustom: false }),
    { useOfficial: false, useCustom: true, ruleMode: 'builtin' },
  );
});

test('补充模式归一与可疑备份打开路径', () => {
  assert.equal(normalizeSupplementMode('AGGRESSIVE'), 'aggressive');
  assert.equal(normalizeSupplementMode('other'), 'precise');
  assert.equal(
    preferredSuspiciousOpenPath({
      suspicious_manifests: [{ path: 'C:/g/tl/chinese/_filtered_suspicious/a/restore_manifest.csv' }],
    }),
    'C:/g/tl/chinese/_filtered_suspicious/a/restore_manifest.csv',
  );
  assert.equal(
    preferredSuspiciousOpenPath({ tl_dir: 'C:/g/tl/chinese' }),
    'C:/g/tl/chinese/_filtered_suspicious',
  );
});

test('TL statusPath 带 game_dir 与语言', () => {
  assert.equal(
    extractToTlStatusPath({ gameDir: 'D:/Other/game', language: 'chinese' }),
    '/api/extract-to-tl?language=chinese&game_dir=D%3A%2FOther%2Fgame',
  );
  assert.equal(
    extractToTlStatusPath({ gameDir: '', language: 'japanese' }),
    '/api/extract-to-tl?language=japanese',
  );
});

test('TL 终态色调：部分写入/失败不用绿色', () => {
  assert.equal(
    extractToTlStatusTone({ job: { status: 'done' }, result: { success: true } }),
    'success',
  );
  assert.equal(
    extractToTlStatusTone({ job: { status: 'cancelled' }, result: { partial: true } }),
    'warning',
  );
  assert.equal(
    extractToTlStatusTone({ job: { status: 'failed' }, result: { written: false } }),
    'error',
  );
});
