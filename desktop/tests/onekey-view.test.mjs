import assert from 'node:assert/strict';
import test from 'node:test';

import {
  canRetryPrepare,
  isIncrementalOutput,
  prepareFailureSummary,
  prepareStageSummaryLines,
} from '../renderer/src/onekeyView.mjs';

const labels = {
  detect: '检测完成',
  unpack: '解包完成：{count} 个，方法 {method}',
  decompile: '反编译完成：{method}',
  extract: '抽取完成',
};

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

test('阶段摘要仅在字段存在时输出解包与反编译明细', () => {
  assert.deepEqual(prepareStageSummaryLines(null, labels), []);
  assert.deepEqual(prepareStageSummaryLines({ skipped_extraction: true, detect_status: 'ready' }, labels), []);

  assert.deepEqual(
    prepareStageSummaryLines({ detect_status: 'need_decompile' }, labels),
    ['检测完成'],
  );
  assert.deepEqual(
    prepareStageSummaryLines({ detect_status: 'need_unpack' }, labels),
    ['检测完成'],
  );

  // error / empty / cancelled 不显示“检测完成”
  assert.deepEqual(prepareStageSummaryLines({ detect_status: 'error' }, labels), []);
  assert.deepEqual(prepareStageSummaryLines({ detect_status: 'empty' }, labels), []);
  assert.deepEqual(prepareStageSummaryLines({ detect_status: 'cancelled' }, labels), []);

  assert.deepEqual(
    prepareStageSummaryLines({
      detect_status: 'ready',
      unpack: { count: 2, method: 'direct' },
      decompile: { method: 'unrpyc' },
      extraction_success: true,
      stage: 'ready',
    }, labels),
    [
      '检测完成',
      '解包完成：2 个，方法 direct',
      '反编译完成：unrpyc',
      '抽取完成',
    ],
  );

  // 没有 unpack/decompile 字段时不渲染对应摘要
  assert.deepEqual(
    prepareStageSummaryLines({ detect_status: 'ready', stage: 'ready', extraction_success: true }, labels),
    ['检测完成', '抽取完成'],
  );
});

test('失败摘要只在 failed 时返回，取消不会当成失败', () => {
  assert.equal(prepareFailureSummary({ status: 'cancelled', error: 'x', message: 'y' }, '准备失败'), '');
  assert.equal(prepareFailureSummary({ status: 'failed', error: '解包失败' }, '准备失败'), '解包失败');
  assert.equal(prepareFailureSummary({ status: 'failed', message: '抽取失败' }, '准备失败'), '抽取失败');
  assert.equal(prepareFailureSummary({ status: 'failed' }, '准备失败'), '准备失败');
  // error 仅空白时回退到 message，再空才用 fallback
  assert.equal(prepareFailureSummary({ status: 'failed', error: '   ', message: '真实错误' }, '准备失败'), '真实错误');
  assert.equal(prepareFailureSummary({ status: 'failed', error: '\t', message: '  ' }, '准备失败'), '准备失败');
});

test('重新准备仅 full + 准备任务 failed + 非 active', () => {
  assert.equal(canRetryPrepare({ mode: 'full', status: 'failed', active: false, kind: 'onekey_prepare' }), true);
  assert.equal(canRetryPrepare({ mode: 'apply', status: 'failed', active: false, kind: 'onekey_prepare' }), false);
  assert.equal(canRetryPrepare({ mode: 'full', status: 'cancelled', active: false, kind: 'onekey_prepare' }), false);
  assert.equal(canRetryPrepare({ mode: 'full', status: 'failed', active: true, kind: 'onekey_prepare' }), false);
  assert.equal(canRetryPrepare({ mode: 'full', status: 'failed', active: false, kind: 'onekey_apply' }), false);
});
