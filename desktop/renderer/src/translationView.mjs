// 翻译页的纯业务判定：不依赖 React，便于 node:test 直接覆盖。
// 口径对齐 frontend/TranslationPage.py 的 update_button_status / translation_update。

/** 可续跑的项目状态，对齐 Base.PROJECT_RESUMABLE_STATUSES。 */
const RESUMABLE_PROJECT_STATUS = 'TRANSLATING';

function toNumber(value) {
  const number = Number(value ?? 0);
  return Number.isFinite(number) ? number : 0;
}

/** 对齐 update_button_status 的 has_cache_data：缓存里有项目状态或行数才算有可用数据。 */
export function hasTranslationCache(progress) {
  const status = progress?.status;
  return status === 'TRANSLATING'
    || status === 'TRANSLATED'
    || toNumber(progress?.line) > 0
    || toNumber(progress?.total_line) > 0;
}

/**
 * 命令栏按钮可用性。
 *
 * - 继续任务：空闲且缓存项目状态为 TRANSLATING，否则后端会因找不到续跑缓存报错；
 * - 写入译文：空闲时需要有缓存，翻译中走在线导出，停止收尾/质量任务/测试期间禁用；
 * - 重翻失败项：只在空闲且有缓存时改写缓存，避免与运行中的翻译器并发写；
 * - 开始翻译：只有存在可续跑缓存时才需要「将重置未完成任务」确认。
 */
export function translationCommands(snapshot, options = {}) {
  const engineStatus = snapshot?.engine_status ?? 'IDLE';
  const stopBarrier = Boolean(snapshot?.stop_barrier);
  const progress = snapshot?.progress ?? {};
  const locked = Boolean(options.busy) || options.ready === false;
  const idle = engineStatus === 'IDLE' && !stopBarrier;
  const canStart = idle && !snapshot?.single_tasks;
  const resumable = canStart && progress.status === RESUMABLE_PROJECT_STATUS;
  const translating = engineStatus === 'TRANSLATING' && !stopBarrier;
  const cached = hasTranslationCache(progress);

  return {
    start: !locked && canStart,
    continueTask: !locked && resumable,
    stop: !locked && translating,
    exportFile: !locked && ((idle && cached) || translating),
    retryFailed: !locked && canStart && cached,
    confirmRestart: resumable,
  };
}

/**
 * 合并一条 TRANSLATION_UPDATE。
 *
 * 带行数的进度事件说明预处理已结束，必须清掉之前合并进来的 phase/message，
 * 否则整轮任务都会显示「正在准备」（对齐 translation_update 里的 indeterminate_hide）。
 */
export function mergeProgressUpdate(previous, update) {
  const merged = { ...(previous ?? {}), ...(update ?? {}) };
  const hasLine = update && ('line' in update || 'total_line' in update);
  if (hasLine && !('phase' in update)) {
    delete merged.phase;
    delete merged.message;
  }
  return merged;
}

/**
 * 应用 /state 快照。
 *
 * 引擎状态只有 HTTP 快照能给出，不能因为请求期间收到过 WS 进度就整份丢弃；
 * 否则任务结束后的最后一条 UPDATE 会让界面停在 TRANSLATING。
 * 请求期间到达的 WS 进度比快照新，覆盖在快照进度之上。
 */
export function mergeTranslationSnapshot(previous, next, progressChangedDuringRequest) {
  if (!progressChangedDuringRequest || !previous) return next;
  return { ...next, progress: { ...(next.progress ?? {}), ...(previous.progress ?? {}) } };
}

/** 已用秒数：翻译中按 start_time 实时计算，结束后使用缓存里的 time 快照（对齐 update_time）。 */
export function elapsedSeconds(progress, engineStatus, nowMs) {
  const startTime = toNumber(progress?.start_time);
  if (engineStatus === 'TRANSLATING' && startTime > 0) {
    return Math.max(0, nowMs / 1000 - startTime);
  }
  return Math.max(0, toNumber(progress?.time));
}

function formatTokens(value) {
  const number = Math.max(0, toNumber(value));
  if (number < 1000) return String(Math.round(number));
  if (number < 1_000_000) return `${(number / 1000).toFixed(1)}K`;
  return `${(number / 1_000_000).toFixed(2)}M`;
}

/** Token 估算结果文案，对齐 _on_token_estimate_done。 */
export function describeTokenEstimate(result) {
  if (!result || toNumber(result.untranslated_count) === 0) {
    return { tone: 'info', text: '所有条目已翻译完成，或当前没有待翻译内容。' };
  }
  const parts = [
    `待翻译条目 ${toNumber(result.untranslated_count)}`,
    `预估批次数 ${toNumber(result.batch_count)}`,
    `原文 Token ~${formatTokens(result.total_source_tokens)}`,
    `预估输入 Token ~${formatTokens(result.estimated_input_tokens)}`,
    `预估输出 Token ~${formatTokens(result.estimated_output_tokens)}`,
  ];
  const cost = toNumber(result.estimated_cost);
  if (cost > 0) parts.push(`预估费用 $${cost.toFixed(4)}`);
  return { tone: 'info', text: parts.join('，') };
}
