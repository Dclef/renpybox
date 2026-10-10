import assert from 'node:assert/strict';
import test from 'node:test';

import { isIncrementalOutput } from '../renderer/src/onekeyView.mjs';

test('只有输出目录指向 <lang>_new 时应用译文才默认增量', () => {
  assert.equal(isIncrementalOutput('D:/game/RenpyBox_Translation/chinese_new'), true);
  assert.equal(isIncrementalOutput('D:\\game\\RenpyBox_Translation\\chinese_new\\'), true);
  assert.equal(isIncrementalOutput('D:/game/RenpyBox_Translation/chinese'), false);
  assert.equal(isIncrementalOutput('D:/game/chinese_new_backup'), false);
});

test('设置尚未加载或为空时按全量处理', () => {
  assert.equal(isIncrementalOutput(undefined), false);
  assert.equal(isIncrementalOutput(null), false);
  assert.equal(isIncrementalOutput(''), false);
});
