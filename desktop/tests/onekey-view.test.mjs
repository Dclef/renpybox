import assert from 'node:assert/strict';
import test from 'node:test';

import {
  canRetryPrepare,
  isIncrementalOutput,
  onekeyLexiconHasWarning,
  onekeyLexiconOptions,
  onekeyLexiconReport,
  onekeyLexiconReportOf,
  onekeyLexiconSummaryLines,
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

test('词库选项：术语默认关闭、禁翻沿用旧默认，页面覆盖优先', () => {
  assert.deepEqual(onekeyLexiconOptions(null), { prepare_glossary: false, prepare_lexicon: true });
  assert.deepEqual(onekeyLexiconOptions({}), { prepare_glossary: false, prepare_lexicon: true });
  assert.deepEqual(
    onekeyLexiconOptions({ onekey_prepare_lexicon: true }),
    { prepare_glossary: false, prepare_lexicon: true },
  );
  assert.deepEqual(
    onekeyLexiconOptions({ onekey_prepare_lexicon: false, onekey_prepare_glossary: true }),
    { prepare_glossary: true, prepare_lexicon: false },
  );
  assert.deepEqual(
    onekeyLexiconOptions({}, { prepareGlossary: true, prepareLexicon: false }),
    { prepare_glossary: true, prepare_lexicon: false },
  );
  assert.deepEqual(
    onekeyLexiconOptions({ onekey_prepare_glossary: true, onekey_prepare_lexicon: true }, { prepareGlossary: false, prepareLexicon: true }),
    { prepare_glossary: false, prepare_lexicon: true },
  );
  // 普通 prepare 与 skip_extraction 走同一个 helper，载荷一致
  assert.deepEqual(onekeyLexiconOptions({}, { prepareGlossary: true }), onekeyLexiconOptions({}, { prepareGlossary: true }));
});

test('词库报告提取：兼容 lexicon 嵌套、顶层平铺结构与缺失', () => {
  const report = { success: true, glossary: { status: 'completed' } };
  assert.equal(onekeyLexiconReport({ lexicon: report }), report);
  // B 也可能把词库报告平铺在结果顶层，需如实识别，不能返回 null
  assert.equal(onekeyLexiconReport(report), report);
  const top = { success: true, glossary: { status: 'skipped' }, warnings: [] };
  assert.equal(onekeyLexiconReport(top), top);
  assert.equal(onekeyLexiconReport(null), null);
  assert.equal(onekeyLexiconReport({ message: '准备完成', stage: 'ready' }), null);
});

test('后续 apply job 无 lexicon 时仍保留 ready 已有的词库报告/警告', () => {
  const ready = { lexicon: { success: true, glossary: { status: 'partial', message: '部分分块失败' } } };
  const applyResult = { stage: 'done', message: '应用完成' };
  assert.equal(onekeyLexiconReport(applyResult), null);
  const report = onekeyLexiconReportOf(applyResult, ready);
  assert.equal(report, ready.lexicon);
  assert.equal(onekeyLexiconHasWarning(report), true);
  assert.deepEqual(onekeyLexiconSummaryLines(report), ['部分分块失败']);
  // 当前结果自带 lexicon 时优先当前结果
  const fresh = { lexicon: { success: true, warnings: ['本次超时'] } };
  assert.equal(onekeyLexiconReportOf(fresh, ready), fresh.lexicon);
  assert.equal(onekeyLexiconReportOf(null, null), null);
});

test('partial/failed、整体失败与 warnings 都升级为警告，skipped 不升级', () => {
  assert.equal(onekeyLexiconHasWarning(null), false);
  assert.equal(onekeyLexiconHasWarning({ success: true, warnings: [] }), false);
  assert.equal(onekeyLexiconHasWarning({ glossary: { status: 'completed' }, preserve: { status: 'skipped' } }), false);
  assert.equal(onekeyLexiconHasWarning({ glossary: { status: 'partial' } }), true);
  assert.equal(onekeyLexiconHasWarning({ preserve: { status: 'failed' } }), true);
  assert.equal(onekeyLexiconHasWarning({ success: false }), true);
  assert.equal(onekeyLexiconHasWarning({ warnings: ['Agent 未配置'] }), true);
  assert.equal(onekeyLexiconHasWarning({ warnings: ['   '] }), false);
});

test('词库摘要保留分步 status/message，并补 warnings，跳过抽取结果不隐藏', () => {
  assert.deepEqual(onekeyLexiconSummaryLines(null), []);
  assert.deepEqual(
    onekeyLexiconSummaryLines({
      success: true,
      glossary: { status: 'partial', message: 'Agent 只完成了部分分块，已保留 3 条候选' },
      preserve: { status: 'completed', message: '禁翻表已更新 2 条' },
      warnings: ['第 2 块超时'],
    }),
    [
      'Agent 只完成了部分分块，已保留 3 条候选',
      '禁翻表已更新 2 条',
      '第 2 块超时',
    ],
  );
  assert.deepEqual(
    onekeyLexiconSummaryLines({ success: true, glossary: { status: 'skipped' }, preserve: { status: 'skipped' }, message: '已跳过词库准备' }),
    ['glossary: skipped', 'preserve: skipped'],
  );
  assert.deepEqual(
    onekeyLexiconSummaryLines({ success: true, message: '词库未变动' }),
    ['词库未变动'],
  );
  assert.deepEqual(onekeyLexiconSummaryLines({ success: false }), ['failed']);
  const skipped = { skipped_extraction: true, lexicon: { success: true, glossary: { status: 'completed', message: '已提取 5 条' } } };
  const lex = onekeyLexiconReport(skipped);
  assert.deepEqual(onekeyLexiconSummaryLines(lex), ['已提取 5 条']);
  assert.equal(onekeyLexiconHasWarning(lex), false);
});

test('重新准备仅 full + 准备任务 failed + 非 active', () => {
  assert.equal(canRetryPrepare({ mode: 'full', status: 'failed', active: false, kind: 'onekey_prepare' }), true);
  assert.equal(canRetryPrepare({ mode: 'apply', status: 'failed', active: false, kind: 'onekey_prepare' }), false);
  assert.equal(canRetryPrepare({ mode: 'full', status: 'cancelled', active: false, kind: 'onekey_prepare' }), false);
  assert.equal(canRetryPrepare({ mode: 'full', status: 'failed', active: true, kind: 'onekey_prepare' }), false);
  assert.equal(canRetryPrepare({ mode: 'full', status: 'failed', active: false, kind: 'onekey_apply' }), false);
});
