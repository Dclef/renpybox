// 独立术语/人名扫描任务的展示决策：不依赖 React，便于 node:test 覆盖。

/**
 * 把一次扫描任务的后端结果翻译成 UI 动作。
 *
 * - written===false 表示后端没有落盘：零候选空 payload 或重复候选都不得覆盖
 *   现有 UI 草稿、快照或候选标记（A 的中间版曾出现 entries=[] 清空表格）；
 * - 模型部分失败 / coverage 不全 / warnings 必须持久展示为警告；
 * - 零候选成功（completed 且无警告）正常显示，不升级为警告；
 * - 取消不标脏、不写表格。
 */
export function glossaryScanOutcome(result, status, partialFallback = '') {
  const r = result && typeof result === 'object' ? result : {};
  const jobStatus = String(status ?? '').trim().toLowerCase();
  const warnings = (Array.isArray(r.warnings) ? r.warnings : [])
    .map((item) => String(item ?? '').trim())
    .filter(Boolean);
  const stepStatus = String(r.status ?? '').trim().toLowerCase();
  const partial =
    stepStatus === 'partial' ||
    stepStatus === 'failed' ||
    r.coverage_complete === false;
  const cancelled = jobStatus === 'cancelled';
  const entries = Array.isArray(r.entries) ? r.entries : null;
  // 只有明确 written===true 才把后端 rows 应用到 UI；false/缺省都保留当前草稿。
  const written = r.written === true;
  const applyRows = !cancelled && written && entries !== null;
  const applyIds = applyRows;
  const warningLines = [];
  if (partial) {
    const message = String(r.message ?? '').trim();
    warningLines.push(message || String(partialFallback || '').trim());
  }
  warningLines.push(...warnings);
  const warning = warningLines.join('\n');
  return {
    applyRows,
    applyIds,
    markDirty: applyRows,
    warning,
    hasWarning: Boolean(warning),
    cancelled,
    partial,
    zeroSuccess: !cancelled && !partial && !warning && !written && entries !== null && entries.length === 0,
  };
}

const MAX_ACTIVE_CHUNKS = 8;
const MAX_PREVIEW_CANDIDATES = 20;
const MAX_SOURCES = 3;
const WARNING_PREVIEW_LIMIT = 3;
const WARNING_COLLAPSE_THRESHOLD = 8;

const safeNonNegInt = (value) => {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : 0;
};
const safeNonNegNumber = (value) => {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : 0;
};
const safeText = (value, max = 200) => String(value ?? '').trim().slice(0, max);

/**
 * 把 0..1 的任务进度安全地转成 0..100 的整数百分比。
 * 0.14 / 14.000000000000002% 都必须得到 14；NaN/Infinity/缺值/越界全部安全。
 */
export function jobProgressPercent(fraction) {
  const value = Number(fraction);
  if (Number.isNaN(value)) return 0;
  if (!Number.isFinite(value)) return value > 0 ? 100 : 0;
  return Math.round(Math.min(1, Math.max(0, value)) * 100);
}

/** 模板填充；缺失值渲染为空串，不抛错。 */
export function fillTemplate(text, vars) {
  return String(text ?? '').replace(/\{([^{}]+)\}/g, (_match, key) => String(vars?.[key] ?? ''));
}

/** 秒数保留一位小数，负数/NaN/Infinity 归零。 */
export function formatSeconds(seconds) {
  return Math.round(safeNonNegNumber(seconds) * 10) / 10;
}

/** 旧 job 时间戳以秒计；只显示最近快照的已知耗时，不猜测未知开始时间。 */
export function jobElapsedSeconds(createdAt, updatedAt) {
  const start = Number(createdAt);
  const end = Number(updatedAt);
  if (!Number.isFinite(start) || !Number.isFinite(end) || start <= 0 || end < start) return null;
  return formatSeconds(end - start);
}

/**
 * 把后端 extraction_progress 规范化成只读展示模型。
 * 旧 job 无该字段（或不是对象）时返回 null，调用方回退到 message + 整数进度。
 * 不修改输入，也不产生 rows / candidate_ids / entries：候选预览绝不写回草稿。
 */
export function normalizeExtractionProgress(raw) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;
  if (!['phase', 'total_chunks', 'completed_chunks', 'active_chunks', 'candidate_count', 'candidates'].some((key) => key in raw)) return null;
  const activeRaw = Array.isArray(raw.active_chunks) ? raw.active_chunks : [];
  const activeChunks = activeRaw.slice(0, MAX_ACTIVE_CHUNKS).map((chunk, i) => {
    const item = chunk && typeof chunk === 'object' ? chunk : {};
    const sourcesRaw = Array.isArray(item.sources) ? item.sources : [];
    return {
      index: safeNonNegInt(item.index) || i + 1,
      sources: sourcesRaw.slice(0, MAX_SOURCES).map((s) => safeText(s, 160)).filter(Boolean),
      elapsedSeconds: safeNonNegNumber(item.elapsed_seconds),
    };
  });
  const candidatesRaw = Array.isArray(raw.candidates) ? raw.candidates : [];
  const candidates = candidatesRaw.slice(0, MAX_PREVIEW_CANDIDATES).map((candidate) => {
    const item = candidate && typeof candidate === 'object' ? candidate : {};
    return {
      src: safeText(item.src, 120),
      type: safeText(item.type, 60),
      evidence: safeText(item.evidence, 160),
      source: safeText(item.source, 160),
      line: safeNonNegInt(item.line),
    };
  }).filter((item) => item.src);
  return {
    phase: safeText(raw.phase, 40) || 'extracting',
    totalChunks: safeNonNegInt(raw.total_chunks),
    completedChunks: safeNonNegInt(raw.completed_chunks),
    successfulChunks: safeNonNegInt(raw.successful_chunks),
    failedChunks: safeNonNegInt(raw.failed_chunks),
    pendingChunks: safeNonNegInt(raw.pending_chunks),
    elapsedSeconds: safeNonNegNumber(raw.elapsed_seconds),
    activeChunks,
    candidateCount: safeNonNegInt(raw.candidate_count),
    candidates,
    candidatesTruncated: candidatesRaw.length > MAX_PREVIEW_CANDIDATES || safeNonNegInt(raw.candidate_count) > candidates.length,
  };
}

/**
 * 紧凑警告模型：默认折叠，全部明细仍保留在 items 里供受限滚动区访问。
 * 兼容两种来源：结构化 warnings 数组，或旧版把警告拼成多行文本。
 */
export function warningDigest(warnings, warningText = '') {
  const raw = Array.isArray(warnings) ? warnings : [];
  // 明细保留完整原因：通过布局限制高度，不截断或合并不同的长错误。
  const lines = raw.map((item) => String(item ?? '').trim()).filter(Boolean);
  const extra = String(warningText ?? '').split('\n').map((line) => line.trim()).filter(Boolean);
  const merged = [];
  const seen = new Set();
  for (const line of [...lines, ...extra]) {
    if (seen.has(line)) continue;
    seen.add(line);
    merged.push(line);
  }
  const total = merged.length;
  return {
    total,
    items: merged,
    preview: merged.slice(0, WARNING_PREVIEW_LIMIT),
    hasMore: total > WARNING_PREVIEW_LIMIT,
    collapsed: total > WARNING_COLLAPSE_THRESHOLD,
  };
}

/** 汇总行的纯数据（不产生文案），供组件用本地化模板填充。 */
export function warningHeadline(view, digest, result = {}) {
  const warningCount = digest?.total ?? 0;
  const r = result && typeof result === 'object' ? result : {};
  const reportedIncomplete = r.coverage_complete === false || r.status === 'partial' || r.status === 'failed';
  if (!view || view.totalChunks <= 0) {
    const total = safeNonNegInt(r.llm_chunks_planned ?? r.llm_chunks_total);
    return {
      hasChunkSummary: total > 0 && r.llm_chunks_success != null,
      successful: safeNonNegInt(r.llm_chunks_success), total,
      failed: safeNonNegInt(r.llm_chunks_failed), pending: safeNonNegInt(r.llm_chunks_pending),
      warningCount, coverageIncomplete: reportedIncomplete,
    };
  }
  return {
    hasChunkSummary: true,
    successful: view.successfulChunks,
    total: view.totalChunks,
    failed: view.failedChunks,
    pending: view.pendingChunks,
    warningCount,
    coverageIncomplete: reportedIncomplete || view.failedChunks > 0 || (view.phase === 'completed' && view.successfulChunks < view.totalChunks),
  };
}

const CHECKPOINT_SCAN_PATHS = new Set([
  '/api/lexicon/glossary/scan-candidates',
  '/api/lexicon/glossary/scan-characters',
]);
const CHECKPOINT_STATUSES = new Set(['new', 'resumed', 'complete', 'corrupt', 'incompatible', 'unavailable', 'superseded']);

export function isCheckpointScanPath(path) {
  return CHECKPOINT_SCAN_PATHS.has(path);
}

export function hasCheckpointResumeCapability(response) {
  return response?.extraction_capabilities?.checkpoint_resume === true;
}

/** Keep non-scan requests unchanged; strip optional flags when talking to an older API. */
export function checkpointScanRequestBody(path, body, capabilities, mode) {
  const original = body && typeof body === 'object' ? body : {};
  if (!isCheckpointScanPath(path)) return { ...original };
  const { resume: _resume, force: _force, ...legacy } = original;
  if (!hasCheckpointResumeCapability(capabilities)) return legacy;
  const force = mode === 'restart' || original.force === true;
  const resume = !force && (mode === 'resume' || original.resume !== false);
  return { ...legacy, resume, force };
}

/** Optional server facts only: never infer checkpoints from percent or candidate previews. */
export function checkpointFeedback(result) {
  const r = result && typeof result === 'object' ? result : {};
  const progress = r.extraction_progress && typeof r.extraction_progress === 'object' ? r.extraction_progress : {};
  const count = (value) => typeof value === 'number' && Number.isFinite(value) && value >= 0 ? Math.floor(value) : null;
  const status = String(progress.checkpoint_status ?? r.checkpoint_status ?? '');
  const knownStatus = CHECKPOINT_STATUSES.has(status) ? status : '';
  return {
    reusedChunks: count(progress.reused_chunks ?? r.reused_chunks),
    requestedChunks: count(progress.requested_chunks ?? r.requested_chunks),
    status: knownStatus,
    resumeAvailable: ['new', 'resumed'].includes(knownStatus) && (progress.resume_available ?? r.resume_available) === true,
  };
}

