// Agent 页的纯展示逻辑：不依赖 React，便于 node:test 直接覆盖。

/**
 * 工具卡片状态文案。后端拒绝/超时/项目变化都会落成 failed，
 * 这里按 code 区分，避免用户把「已拒绝」误读成执行出错。
 */
export function toolStatusInfo(tool) {
  const status = tool?.status;
  const code = String(tool?.code ?? '');
  if (status === 'running') return { label: '执行中', tone: 'running' };
  if (status === 'done') return { label: '已完成', tone: 'done' };
  if (status === 'cancelled' || code === 'USER_CANCELLED') return { label: '已取消', tone: 'cancelled' };
  if (code === 'CONFIRMATION_TIMEOUT') return { label: '确认超时', tone: 'cancelled' };
  if (code === 'CONFIRMATION_STALE') return { label: '项目已变化', tone: 'cancelled' };
  return { label: '失败', tone: 'failed' };
}

/** 对齐 ProjectPaths._language_from_tl_path：取最近的 tl/<语言> 目录名，路径不含 tl 时返回空串。 */
export function languageFromTlPath(path) {
  const parts = String(path ?? '').split(/[\\/]/).filter(Boolean);
  for (let index = parts.length - 2; index >= 0; index -= 1) {
    if (parts[index].toLowerCase() === 'tl') return parts[index + 1];
  }
  return '';
}

/**
 * Agent 能用哪种接口格式。
 *
 * 传统机翻格式（GoogleFree / Bing）没有工具调用能力，选中它们只会在真正发
 * 请求时失败，所以这里显式排除——不是「没写进白名单」，而是「明确不能选」。
 */
export const AGENT_API_FORMATS = Object.freeze(['OpenAI', 'Anthropic', 'Google']);
export const MACHINE_API_FORMATS = Object.freeze(['GoogleFree', 'Bing']);

export function isMachineApiFormat(apiFormat) {
  const value = String(apiFormat ?? '').trim();
  return MACHINE_API_FORMATS.some((item) => item.toLowerCase() === value.toLowerCase());
}

export function isAgentPlatform(platform) {
  const value = String(platform?.api_format ?? '').trim();
  if (!value) return false;
  if (isMachineApiFormat(value)) return false;
  return AGENT_API_FORMATS.some((item) => item.toLowerCase() === value.toLowerCase());
}

/** Agent 页接口下拉的可选项：只留支持工具调用的格式。 */
export function selectableAgentPlatforms(platforms) {
  if (!Array.isArray(platforms)) return [];
  return platforms.filter(isAgentPlatform);
}

/** 一条龙编排的阶段顺序，与后端 stage 取值对齐。 */
export const PIPELINE_STAGES = Object.freeze(['detect', 'unpack', 'decompile', 'extract', 'translate', 'apply', 'fallback', 'done']);

/** 阶段值对应的 i18n key；空串和未知阶段不展示。 */
export function stageKey(stage) {
  const value = String(stage ?? '');
  return PIPELINE_STAGES.includes(value) ? `agent_page_stage_${value}` : '';
}

function compactCount(value, divisor, suffix) {
  const scaled = Math.round((value / divisor) * 10) / 10;
  const text = Number.isInteger(scaled) ? String(scaled) : scaled.toFixed(1);
  return `${text}${suffix}`;
}

/** 把 token 数压成 200K / 1.5K / 1M；0 和非法值不展示。 */
export function formatTokenCount(n) {
  if (typeof n !== 'number' || !Number.isFinite(n) || n <= 0) return '';
  if (n >= 1_000_000) return compactCount(n, 1_000_000, 'M');
  if (n >= 1_000) return compactCount(n, 1_000, 'K');
  const rounded = Math.round(n * 10) / 10;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

/** 设置里的预算行：上下文窗口与最大轮数，缺哪项哪项为空。 */
export function budgetParts(budget) {
  const iterations = budget?.max_iterations;
  return {
    context: formatTokenCount(budget?.context_window),
    iterations: typeof iterations === 'number' && Number.isFinite(iterations) && iterations > 0 ? String(iterations) : '',
  };
}

function positiveNumber(value) {
  return typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : 0;
}

/**
 * 底部状态栏数据：轮次/步数、吞吐、累计 token、缓存命中率、上下文占比。
 *
 * 每一项都单独给值：供应商不回 usage 时这些字段是 0 或 null，
 * 由界面按需拼装，避免「没有数据却显示 0%」。
 */
export function metricsParts(metrics) {
  const empty = {
    rounds: 0,
    steps: 0,
    tokensPerSecond: 0,
    totalTokens: '',
    cacheHitPercent: null,
    contextPercent: 0,
    hasData: false,
  };
  if (!metrics || typeof metrics !== 'object') return empty;

  const rounds = positiveNumber(metrics.iterations);
  const steps = positiveNumber(metrics.steps);
  const tokensPerSecond = positiveNumber(metrics.tokens_per_second);
  const totalTokens = formatTokenCount(positiveNumber(metrics.total_tokens));
  const hitRate = typeof metrics.cache_hit_rate === 'number' && Number.isFinite(metrics.cache_hit_rate)
    ? Math.max(0, Math.min(1, metrics.cache_hit_rate))
    : null;
  const contextPercent = positiveNumber(metrics.context_percent);

  return {
    rounds,
    steps,
    tokensPerSecond,
    totalTokens,
    cacheHitPercent: hitRate === null ? null : Math.round(hitRate * 100),
    contextPercent: contextPercent > 0 ? Math.round(contextPercent * 100) : 0,
    hasData: rounds > 0 || Boolean(totalTokens) || contextPercent > 0,
  };
}
