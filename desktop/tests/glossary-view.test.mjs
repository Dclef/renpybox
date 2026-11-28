import assert from 'node:assert/strict';
import test from 'node:test';

import {
  checkpointFeedback,
  checkpointScanRequestBody,
  hasCheckpointResumeCapability,
  isCheckpointScanPath,
  fillTemplate,
  formatSeconds,
  glossaryScanOutcome,
  jobProgressPercent,
  jobElapsedSeconds,
  normalizeExtractionProgress,
  warningDigest,
  warningHeadline,
} from '../renderer/src/glossaryView.mjs';

test('零候选且 written=false：不覆盖草稿、不标脏、无警告', () => {
  const outcome = glossaryScanOutcome(
    { status: 'completed', entries: [], candidate_ids: [], written: false, message: '未发现候选' },
    'done',
  );
  assert.equal(outcome.applyRows, false);
  assert.equal(outcome.applyIds, false);
  assert.equal(outcome.markDirty, false);
  assert.equal(outcome.hasWarning, false);
  assert.equal(outcome.zeroSuccess, true);
});

test('空 payload 里 entries 缺失时也不覆盖草稿', () => {
  const outcome = glossaryScanOutcome({ written: false }, 'done');
  assert.equal(outcome.applyRows, false);
  assert.equal(outcome.markDirty, false);
});

test('部分分块失败：持久警告，但结果仍可应用', () => {
  const outcome = glossaryScanOutcome(
    { status: 'partial', coverage_complete: false, entries: [{ src: 'A' }], written: true, message: '只完成部分分块' },
    'done',
  );
  assert.equal(outcome.applyRows, true);
  assert.equal(outcome.hasWarning, true);
  assert.match(outcome.warning, /只完成部分分块/);
  assert.equal(outcome.partial, true);
});

test('coverage_complete=false 与 warnings 都升级为持久警告', () => {
  const fallback = '部分分块未完成';
  const a = glossaryScanOutcome({ status: 'completed', coverage_complete: false, entries: [], written: true }, 'done', fallback);
  assert.equal(a.hasWarning, true);
  assert.equal(a.warning, fallback);
  const b = glossaryScanOutcome({ status: 'completed', entries: [], written: true, warnings: ['第 2 块超时', '  '] }, 'done');
  assert.equal(b.hasWarning, true);
  assert.match(b.warning, /第 2 块超时/);
  const c = glossaryScanOutcome({ status: 'failed', entries: [], written: false }, 'done', fallback);
  assert.equal(c.hasWarning, true);
});

test('零候选但成功落盘：正常显示，不升级警告', () => {
  const outcome = glossaryScanOutcome({ status: 'completed', entries: [], written: true, message: '未发现候选' }, 'done');
  assert.equal(outcome.hasWarning, false);
  assert.equal(outcome.zeroSuccess, false);
});

test('正常有候选落盘：应用 rows/ids 并标脏', () => {
  const outcome = glossaryScanOutcome(
    { status: 'completed', entries: [{ src: 'A' }], candidate_ids: ['x'], written: true },
    'done',
  );
  assert.equal(outcome.applyRows, true);
  assert.equal(outcome.applyIds, true);
  assert.equal(outcome.markDirty, true);
});

test('取消：不 setDirty、不写表格、不标脏', () => {
  const outcome = glossaryScanOutcome(
    { status: 'completed', entries: [{ src: 'A' }], written: true, extraction_progress: { total_chunks: 3 } },
    'cancelled',
  );
  assert.equal(outcome.cancelled, true);
  assert.equal(outcome.applyRows, false);
  assert.equal(outcome.applyIds, false);
  assert.equal(outcome.markDirty, false);
});

test('重复候选 written=false 且 entries 含现有行：不覆盖草稿、不丢候选标记', () => {
  const outcome = glossaryScanOutcome(
    { status: 'completed', entries: [{ src: 'A' }], candidate_ids: ['x'], written: false },
    'done',
  );
  assert.equal(outcome.applyRows, false);
  assert.equal(outcome.applyIds, false);
  assert.equal(outcome.markDirty, false);
});

test('partial 且无后端 message 时使用调用方传入的本地化文案，不内联固定中文', () => {
  const fallback = 'The Agent finished only some chunks';
  const withMessage = glossaryScanOutcome({ status: 'partial', entries: [], written: false }, 'done', fallback);
  assert.equal(withMessage.warning, fallback);
  const noFallback = glossaryScanOutcome({ status: 'partial', entries: [], written: false }, 'done');
  assert.equal(noFallback.warning, '');
  assert.equal(noFallback.hasWarning, false);
  assert.equal(noFallback.partial, true);
});

test('结果不是对象时安全降级', () => {
  const outcome = glossaryScanOutcome(null, 'done');
  assert.equal(outcome.applyRows, false);
  assert.equal(outcome.hasWarning, false);
});

test('百分比：0.14 与 14.000000000000002% 源值都取整为 14，无长小数', () => {
  assert.equal(jobProgressPercent(0.14), 14);
  assert.equal(jobProgressPercent(0.14000000000000002), 14);
  // 后端把 14.000000000000002 当成 0..1 小数或 0..100 数值都要安全
  assert.equal(jobProgressPercent(14.000000000000002 / 100), 14);
  assert.equal(jobProgressPercent(0), 0);
  assert.equal(jobProgressPercent(1), 100);
  assert.equal(jobProgressPercent(0.999), 100);
  assert.equal(jobProgressPercent(0.004), 0);
  assert.equal(jobProgressPercent(-0.5), 0);
  assert.equal(jobProgressPercent(2), 100);
  assert.equal(jobProgressPercent(1.5), 100);
});

test('百分比：NaN / Infinity / 旧 job 缺值 / 非数字都安全', () => {
  assert.equal(jobProgressPercent(NaN), 0);
  assert.equal(jobProgressPercent(Infinity), 100);
  assert.equal(jobProgressPercent(-Infinity), 0);
  assert.equal(jobProgressPercent(undefined), 0);
  assert.equal(jobProgressPercent(null), 0);
  assert.equal(jobProgressPercent('abc'), 0);
  assert.equal(jobProgressPercent('0.14'), 14);
  assert.equal(jobProgressPercent({}), 0);
});

test('模板填充与秒数格式化', () => {
  assert.equal(fillTemplate('块 {completed}/{total}', { completed: 5, total: 124 }), '块 5/124');
  assert.equal(fillTemplate('{a} {b}', { a: 1 }), '1 ');
  assert.equal(fillTemplate(null, {}), '');
  assert.equal(formatSeconds(3.14159), 3.1);
  assert.equal(formatSeconds(NaN), 0);
  assert.equal(formatSeconds(-2), 0);
  assert.equal(formatSeconds(Infinity), 0);
});

const progress124 = {
  phase: 'extracting',
  total_chunks: 124,
  completed_chunks: 124,
  successful_chunks: 5,
  failed_chunks: 119,
  pending_chunks: 0,
  elapsed_seconds: 63.44,
  active_chunks: [
    { index: 7, sources: ['game/script.rpy', 'game/chars.rpy'], elapsed_seconds: 4.2 },
  ],
  candidate_count: 9,
  candidates: [
    { src: '艾莉娅', type: '角色', evidence: 'define e = Character("艾莉娅")', source: 'game/chars.rpy', line: 12 },
    { src: 'Help', type: 'UI', evidence: 'textbutton _("Help")', source: 'game/screens.rpy', line: 3 },
  ],
};

test('124/5/119 场景：规范化摘要只保留有界活动分块与最多20项预览，不产生 rows/ids', () => {
  const view = normalizeExtractionProgress(progress124);
  assert.equal(view.totalChunks, 124);
  assert.equal(view.successfulChunks, 5);
  assert.equal(view.failedChunks, 119);
  assert.equal(view.candidateCount, 9);
  assert.equal(view.elapsedSeconds, 63.44);
  assert.equal(view.activeChunks.length, 1);
  assert.deepEqual(view.activeChunks[0].sources, ['game/script.rpy', 'game/chars.rpy']);
  assert.equal(view.activeChunks[0].reasoning, '');
  assert.equal(view.candidates.length, 2);
  assert.equal(view.candidates[0].src, '艾莉娅');
  assert.equal(view.candidates[0].line, 12);
  // 关键：预览绝不写回 rows / candidate_ids / entries
  assert.equal(view.entries, undefined);
  assert.equal(view.rows, undefined);
  assert.equal(view.candidate_ids, undefined);
  // 后端也会裁到 20 项；总候选数大于预览长度时应显示还有更多。
  assert.equal(view.candidatesTruncated, true);
});

test('规范化：active_chunks 与 candidates 有上限，sources 最多3项，长度截断', () => {
  const view = normalizeExtractionProgress({
    total_chunks: 200,
    active_chunks: Array.from({ length: 30 }, (_, i) => ({ index: i + 1, sources: ['a', 'b', 'c', 'd'], elapsed_seconds: i })),
    candidates: Array.from({ length: 40 }, (_, i) => ({ src: 'T' + i, evidence: 'x'.repeat(500) })),
  });
  assert.equal(view.activeChunks.length, 8);
  assert.equal(view.activeChunks[0].sources.length, 3);
  assert.equal(view.candidates.length, 20);
  assert.ok(view.candidates[0].evidence.length <= 160);
  assert.equal(view.candidatesTruncated, true);
});

test('无 details 的旧 payload：返回 null，调用方回退 message + 整数进度', () => {
  assert.equal(normalizeExtractionProgress(undefined), null);
  assert.equal(normalizeExtractionProgress(null), null);
  assert.equal(normalizeExtractionProgress('x'), null);
  assert.equal(normalizeExtractionProgress([]), null);
  assert.equal(normalizeExtractionProgress({}), null); // 空对象必须回退旧 job 展示
  const legacy = { message: '正在扫描', progress: 0.14 };
  assert.equal(normalizeExtractionProgress(legacy.extraction_progress), null);
  assert.equal(jobProgressPercent(legacy.progress), 14);
});

test('119 条警告：默认紧凑预览 + 折叠，全部明细仍可访问，不铺满界面', () => {
  const warnings = Array.from({ length: 119 }, (_, i) => `第 ${i + 1} 块超时`);
  const digest = warningDigest(warnings);
  assert.equal(digest.total, 119);
  assert.equal(digest.preview.length, 3);
  assert.equal(digest.items.length, 119);
  assert.equal(digest.hasMore, true);
  assert.equal(digest.collapsed, true);
  assert.equal(digest.items[118], '第 119 块超时');
});

test('警告 digest：合并多行 warningText、去重、空白过滤、无警告安全', () => {
  const digest = warningDigest(['A', '  ', 'B'], 'A\nC\n');
  assert.equal(digest.total, 3);
  assert.deepEqual(digest.items, ['A', 'B', 'C']);
  assert.equal(warningDigest([], '').total, 0);
  assert.equal(warningDigest(null).total, 0);
  const few = warningDigest(['x', 'y']);
  assert.equal(few.collapsed, false);
  assert.equal(few.hasMore, false);
});

test('124/5/119 汇总：5/124 成功、119 警告、覆盖未完成，completed 不伪称覆盖完整', () => {
  const view = normalizeExtractionProgress(progress124);
  const digest = warningDigest(progress124.failed_chunks ? Array.from({ length: 119 }, (_, i) => 'w' + i) : []);
  const head = warningHeadline(view, digest);
  assert.equal(head.hasChunkSummary, true);
  assert.equal(head.successful, 5);
  assert.equal(head.total, 124);
  assert.equal(head.failed, 119);
  assert.equal(head.warningCount, 119);
  assert.equal(head.coverageIncomplete, true);
  // completed phase 只是执行结束，coverageIncomplete 仍为 true
  const doneView = normalizeExtractionProgress({ ...progress124, phase: 'completed', pending_chunks: 0 });
  assert.equal(doneView.phase, 'completed');
  assert.equal(warningHeadline(doneView, digest).coverageIncomplete, true);
});

test('旧 job 无结构化字段：汇总不含块信息，但警告数量仍如实展示', () => {
  const head = warningHeadline(null, warningDigest(['timeout']));
  assert.equal(head.hasChunkSummary, false);
  assert.equal(head.warningCount, 1);
  assert.equal(head.coverageIncomplete, false);
});

test('取消与项目切换保护：结构化预览绝不触发 applyRows / applyIds / markDirty', () => {
  const cancelled = glossaryScanOutcome(
    { ...progress124, entries: [{ src: 'X' }], written: true },
    'cancelled',
  );
  assert.equal(cancelled.applyRows, false);
  assert.equal(cancelled.applyIds, false);
  assert.equal(cancelled.markDirty, false);
  // 项目切换后晚到的零候选结果同样不写草稿
  const late = glossaryScanOutcome({ entries: [], candidate_ids: [], written: false }, 'done');
  assert.equal(late.applyRows, false);
  assert.equal(late.applyIds, false);
});

test('极大有限进度值仍 clamp 到 100，不会乘法溢出变为 0', () => {
  assert.equal(jobProgressPercent(Number.MAX_VALUE), 100);
  assert.equal(jobProgressPercent(-Number.MAX_VALUE), 0);
});

test('旧 job 仅用已知秒级时间戳显示耗时，缺省和无效值不伪造', () => {
  assert.equal(jobElapsedSeconds(1000, 1023.44), 23.4);
  assert.equal(jobElapsedSeconds(1000, 1000), 0);
  for (const pair of [[undefined, 1000], [0, 1000], [1000, undefined], [Infinity, 1100], [1000, Infinity], [1000, 999]]) {
    assert.equal(jobElapsedSeconds(...pair), null);
  }
});

test('旧最终结果保持 5/124 成功摘要与 coverage_complete=false', () => {
  const head = warningHeadline(null, warningDigest(Array.from({ length: 119 }, (_, i) => 'warn-' + i)), {
    llm_chunks_total: 124, llm_chunks_success: 5, status: 'partial', coverage_complete: false,
  });
  assert.equal(head.hasChunkSummary, true);
  assert.equal(head.successful, 5);
  assert.equal(head.total, 124);
  assert.equal(head.warningCount, 119);
  assert.equal(head.coverageIncomplete, true);
  const planned = warningHeadline(null, null, { llm_chunks_planned: 140, llm_chunks_total: 124, llm_chunks_success: 5 });
  assert.equal(planned.total, 140);
});

test('进行中的待处理块不假报失败，执行结束但尚有未处理块必须提示覆盖未完成', () => {
  const running = normalizeExtractionProgress({ phase: 'extracting', total_chunks: 124, completed_chunks: 4, successful_chunks: 4, failed_chunks: 0, pending_chunks: 116 });
  assert.equal(warningHeadline(running).coverageIncomplete, false);
  assert.equal(warningHeadline({ ...running, phase: 'completed' }).coverageIncomplete, true);
  assert.equal(warningHeadline(running, null, { coverage_complete: false }).coverageIncomplete, true);
});

test('警告详细原因保留超过400字的尾部，不把同前缀的不同错误合并', () => {
  const prefix = 'long warning '.repeat(50);
  const warnings = [prefix + 'first', prefix + 'second'];
  assert.deepEqual(warningDigest(warnings).items, warnings);
  assert.equal(warningDigest(warnings).total, 2);
});

test('预览规范化不改变输入或生成可应用的正式 entries', () => {
  const raw = { phase: 'extracting', candidate_count: 30, candidates: Array.from({ length: 20 }, (_, i) => ({ src: 'entity' + i, type: 'name' })) };
  const before = structuredClone(raw);
  const preview = normalizeExtractionProgress(raw);
  assert.deepEqual(raw, before);
  assert.equal(preview.candidates.length, 20);
  assert.equal(preview.candidatesTruncated, true);
  const outcome = glossaryScanOutcome({ extraction_progress: raw }, 'running');
  assert.equal(outcome.applyRows, false);
  assert.equal(outcome.applyIds, false);
  assert.equal(outcome.markDirty, false);
});


test('checkpoint support is explicit capability only, never a JS version or old job counter', () => {
  for (const response of [null, {}, { job: { progress: 1, resume_available: true } }, { extraction_capabilities: { checkpoint_resume: 'true' } }]) assert.equal(hasCheckpointResumeCapability(response), false);
  assert.equal(hasCheckpointResumeCapability({ extraction_capabilities: { checkpoint_resume: true } }), true);
});

test('both scans default to resume; force wins; older APIs receive their original body', () => {
  const cap = { extraction_capabilities: { checkpoint_resume: true } };
  const body = { confirm: true, rows: [{ src: 'draft', dst: 'manual translation' }] };
  const before = structuredClone(body);
  for (const path of ['/api/lexicon/glossary/scan-candidates', '/api/lexicon/glossary/scan-characters']) {
    assert.equal(isCheckpointScanPath(path), true);
    assert.deepEqual(checkpointScanRequestBody(path, body, cap), { ...body, resume: true, force: false });
    assert.deepEqual(checkpointScanRequestBody(path, body, cap, 'restart'), { ...body, resume: false, force: true });
    assert.deepEqual(checkpointScanRequestBody(path, { ...body, resume: true, force: true }, cap, 'resume'), { ...body, resume: false, force: true });
    assert.deepEqual(checkpointScanRequestBody(path, { ...body, resume: true, force: false }, {}), body);
    assert.deepEqual(checkpointScanRequestBody(path, body, null), body);
  }
  assert.deepEqual(body, before);
  const other = { force: true, mode: 'llm' };
  assert.deepEqual(checkpointScanRequestBody('/api/lexicon/glossary/translate', other, {}), other);
});

test('checkpoint facts remain absent for legacy jobs and do not infer reusable chunks from previews', () => {
  assert.deepEqual(checkpointFeedback({ progress: 1, extraction_progress: { phase: 'extracting', completed_chunks: 8, successful_chunks: 8, candidates: [{ src: 'name' }] } }), {
    reusedChunks: null, requestedChunks: null, status: '', resumeAvailable: false,
  });
  assert.deepEqual(checkpointFeedback({ reused_chunks: 5, requested_chunks: 3, checkpoint_status: 'resumed', resume_available: true }), { reusedChunks: 5, requestedChunks: 3, status: 'resumed', resumeAvailable: true });
  const input = { phase: 'extracting', total_chunks: 12, completed_chunks: 7, successful_chunks: 7, reused_chunks: 5, requested_chunks: 3 };
  assert.equal(normalizeExtractionProgress(input).completedChunks, 7);
  assert.equal(normalizeExtractionProgress(input).successfulChunks, 7);
});

test('checkpoint status enumerations and invalid counts fail closed', () => {
  for (const status of ['complete', 'corrupt', 'incompatible', 'unavailable', 'superseded', 'unknown-new-server-value']) {
    const facts = checkpointFeedback({ checkpoint_status: status, resume_available: true, reused_chunks: NaN, requested_chunks: -1 });
    assert.equal(facts.resumeAvailable, false);
    assert.equal(facts.reusedChunks, null);
    assert.equal(facts.requestedChunks, null);
    assert.equal(facts.status, status.startsWith('unknown') ? '' : status);
  }
  assert.deepEqual(checkpointFeedback({ reused_chunks: 1, requested_chunks: 1, extraction_progress: { reused_chunks: 4, requested_chunks: 0, checkpoint_status: 'new', resume_available: false } }), { reusedChunks: 4, requestedChunks: 0, status: 'new', resumeAvailable: false });
});

test('failed glossary persistence keeps nested checkpoint facts and supports all-reused retry with zero requests', () => {
  const failedResult = { status: 'failed', written: false, extraction_progress: {
    phase: 'completed', total_chunks: 24, completed_chunks: 24, successful_chunks: 24,
    reused_chunks: 0, requested_chunks: 24, checkpoint_status: 'new', resume_available: true,
  } };
  const original = structuredClone(failedResult);
  assert.deepEqual(checkpointFeedback(failedResult), { reusedChunks: 0, requestedChunks: 24, status: 'new', resumeAvailable: true });
  assert.deepEqual(failedResult, original);
  const retry = { extraction_progress: {
    phase: 'aggregating', total_chunks: 24, completed_chunks: 24, successful_chunks: 24,
    reused_chunks: 24, requested_chunks: 0, checkpoint_status: 'resumed', resume_available: true,
  } };
  assert.deepEqual(checkpointFeedback(retry), { reusedChunks: 24, requestedChunks: 0, status: 'resumed', resumeAvailable: true });
  assert.equal(normalizeExtractionProgress(retry.extraction_progress).completedChunks, 24);
  assert.equal(normalizeExtractionProgress(retry.extraction_progress).successfulChunks, 24);
});


