import assert from 'node:assert/strict';
import test from 'node:test';

import {
  describeTokenEstimate,
  elapsedSeconds,
  hasTranslationCache,
  mergeProgressUpdate,
  mergeTranslationSnapshot,
  translationCommands,
} from '../renderer/src/translationView.mjs';

function snapshot(overrides = {}) {
  return {
    engine_status: 'IDLE',
    stop_barrier: false,
    single_tasks: false,
    request_id: '',
    run_id: 1,
    running: { running: 0, max: 16 },
    progress: {},
    active_output_folder: '',
    ...overrides,
  };
}

test('继续任务只在空闲且缓存项目可续跑时可用', () => {
  assert.equal(translationCommands(snapshot()).continueTask, false);
  assert.equal(translationCommands(snapshot({ progress: { status: 'TRANSLATED', line: 3, total_line: 3 } })).continueTask, false);

  const resumable = translationCommands(snapshot({ progress: { status: 'TRANSLATING', line: 1, total_line: 3 } }));
  assert.equal(resumable.continueTask, true);
  assert.equal(resumable.confirmRestart, true);

  assert.equal(translationCommands(snapshot({ stop_barrier: true, progress: { status: 'TRANSLATING' } })).continueTask, false);
  assert.equal(translationCommands(snapshot({ single_tasks: true, progress: { status: 'TRANSLATING' } })).continueTask, false);
  assert.equal(translationCommands(snapshot({ progress: { status: 'TRANSLATING' } }), { busy: true }).continueTask, false);
});

test('没有可续跑缓存时开始翻译不再要求「重置」确认', () => {
  const fresh = translationCommands(snapshot());
  assert.equal(fresh.start, true);
  assert.equal(fresh.confirmRestart, false);
});

test('写入译文：空闲需有缓存，翻译中在线导出，停止收尾与质量任务禁用', () => {
  assert.equal(translationCommands(snapshot()).exportFile, false);
  assert.equal(translationCommands(snapshot({ progress: { status: 'TRANSLATED' } })).exportFile, true);
  assert.equal(translationCommands(snapshot({ engine_status: 'TRANSLATING' })).exportFile, true);
  assert.equal(translationCommands(snapshot({ engine_status: 'STOPPING', progress: { line: 1 } })).exportFile, false);
  assert.equal(translationCommands(snapshot({ engine_status: 'TRANSLATING', stop_barrier: true })).exportFile, false);
  assert.equal(translationCommands(snapshot({ engine_status: 'QUALITY', progress: { line: 1 } })).exportFile, false);
});

test('停止与重翻失败项不会在错误状态下改写缓存', () => {
  assert.equal(translationCommands(snapshot({ engine_status: 'TRANSLATING' })).stop, true);
  assert.equal(translationCommands(snapshot({ engine_status: 'STOPPING' })).stop, false);
  assert.equal(translationCommands(snapshot({ engine_status: 'TRANSLATING', stop_barrier: true })).stop, false);

  assert.equal(translationCommands(snapshot()).retryFailed, false);
  assert.equal(translationCommands(snapshot({ progress: { status: 'TRANSLATED', total_line: 2 } })).retryFailed, true);
  assert.equal(translationCommands(snapshot({ engine_status: 'TRANSLATING', progress: { line: 1 } })).retryFailed, false);
  assert.equal(translationCommands(snapshot({ stop_barrier: true, progress: { line: 1 } })).retryFailed, false);
});

test('缓存数据判定对齐 Qt5 has_cache_data', () => {
  assert.equal(hasTranslationCache({}), false);
  assert.equal(hasTranslationCache({ status: 'UNTRANSLATED' }), false);
  assert.equal(hasTranslationCache({ status: 'TRANSLATING' }), true);
  assert.equal(hasTranslationCache({ total_line: 5 }), true);
});

test('带行数的进度事件清掉预处理阶段文案', () => {
  const preparing = mergeProgressUpdate({ line: 0 }, { phase: 'preparing', message: '预处理中…' });
  assert.equal(preparing.phase, 'preparing');
  const running = mergeProgressUpdate(preparing, { line: 2, total_line: 10 });
  assert.equal('phase' in running, false);
  assert.equal('message' in running, false);
  assert.equal(running.line, 2);
  const again = mergeProgressUpdate(running, { phase: 'preparing', message: '生成任务中…' });
  assert.equal(again.phase, 'preparing');
  assert.equal(again.line, 2);
});

test('快照在途期间收到 WS 进度时仍采用快照的引擎状态', () => {
  const previous = snapshot({ engine_status: 'TRANSLATING', progress: { line: 10, total_line: 10 } });
  const next = snapshot({ engine_status: 'IDLE', progress: { status: 'TRANSLATED', line: 9, total_line: 10 } });

  const merged = mergeTranslationSnapshot(previous, next, true);
  assert.equal(merged.engine_status, 'IDLE');
  assert.equal(merged.progress.status, 'TRANSLATED');
  assert.equal(merged.progress.line, 10);

  assert.equal(mergeTranslationSnapshot(previous, next, false), next);
});

test('已用时间：翻译中按 start_time 实时计算，空闲读取缓存 time', () => {
  assert.equal(elapsedSeconds({ start_time: 100, time: 5 }, 'TRANSLATING', 130_000), 30);
  assert.equal(elapsedSeconds({ start_time: 100, time: 5 }, 'IDLE', 130_000), 5);
  assert.equal(elapsedSeconds({}, 'TRANSLATING', 130_000), 0);
});

test('Token 估算文案：无待译条目时提示已完成，有费用时附带费用', () => {
  assert.match(describeTokenEstimate({ untranslated_count: 0 }).text, /所有条目已翻译完成/);
  const text = describeTokenEstimate({
    untranslated_count: 3,
    batch_count: 1,
    total_source_tokens: 1500,
    estimated_input_tokens: 2_500_000,
    estimated_output_tokens: 20,
    estimated_cost: 0.05,
  }).text;
  assert.match(text, /待翻译条目 3/);
  assert.match(text, /原文 Token ~1\.5K/);
  assert.match(text, /预估输入 Token ~2\.50M/);
  assert.match(text, /预估费用 \$0\.0500/);
});
