import assert from 'node:assert/strict';
import test from 'node:test';

import { shouldHydrateAndroidForm as shouldHydrateForm } from '../renderer/src/androidBuildView.mjs';

test('同身份未水合未 dirty 允许水合', () => {
  assert.equal(shouldHydrateForm({ hydrated: false, dirty: false }), true);
  assert.equal(shouldHydrateForm(), true);
});

test('已水合过不再水合', () => {
  assert.equal(shouldHydrateForm({ hydrated: true, dirty: false }), false);
});

test('用户 dirty 后不再水合', () => {
  assert.equal(shouldHydrateForm({ hydrated: false, dirty: true }), false);
  assert.equal(shouldHydrateForm({ hydrated: true, dirty: true }), false);
});

// 身份变化后 hook 会重置 hydrated/dirty；这里用纯 flags 表达「重置后回到可水合初态」的等价状态。
test('身份变化重置后回到可水合初态', () => {
  assert.equal(shouldHydrateForm({ hydrated: true, dirty: true }), false);
  assert.equal(shouldHydrateForm({ hydrated: false, dirty: false }), true);
});
