// 一键翻译页的纯展示逻辑：不依赖 React，便于 node:test 直接覆盖。

/**
 * 没有本次准备结果时，应用译文是否按增量处理。
 * 对齐 Qt5：只有当前翻译输出指向 <lang>_new 增量目录时才走增量合并，
 * 否则按全量覆盖主 TL，不能默认增量去合并可能过期的暂存目录。
 */
export function isIncrementalOutput(outputFolder) {
  return /_new[\\/]?$/.test(String(outputFolder ?? '').trim());
}

const fillTemplate = (text, vars) =>
  Object.entries(vars).reduce((acc, [key, value]) => acc.split(`{${key}}`).join(String(value)), String(text ?? ''));

/**
 * 仅 full 模式、准备任务失败、且无进行中任务时可重新准备。
 * 取消状态与应用任务失败都不显示重试。
 */
export function canRetryPrepare({ mode, status, active, kind } = {}) {
  return mode === 'full' && status === 'failed' && !active && kind === 'onekey_prepare';
}

/**
 * 准备失败摘要：仅 status === failed 时返回错误文案，取消不会命中。
 * 先 trim error；空串再 trim message；都空才用 fallback。
 */
export function prepareFailureSummary({ status, error, message } = {}, fallback = '') {
  if (status !== 'failed') return '';
  const err = String(error ?? '').trim();
  if (err) return err;
  const msg = String(message ?? '').trim();
  if (msg) return msg;
  return String(fallback || '');
}

/** 检测成功类状态才显示“检测完成”；error/empty/cancelled 等不显示。 */
const DETECT_DONE_STATUSES = new Set(['ready', 'need_unpack', 'need_decompile']);

/**
 * 从准备结果拼已完成阶段摘要行；缺失字段不输出。
 * labels: { detect, unpack, decompile, extract }
 * unpack/decompile 模板可含 {count}/{method}。
 */
/**
 * 一条龙准备请求的词库选项：两个开关独立，普通 prepare 与跳过抽取路径都传。
 * 术语提取（prepare_glossary）默认关闭，避免旧配置里的 True 静默开启付费 Agent；
 * 禁翻准备（prepare_lexicon）沿用 onekey_prepare_lexicon !== false 的旧默认。
 * 页面临时 override 优先于已保存配置。
 */
export function onekeyLexiconOptions(values, overrides = {}) {
  const config = values && typeof values === 'object' ? values : {};
  const pick = (override, fallback) => (override == null ? fallback : Boolean(override));
  return {
    prepare_glossary: pick(
      overrides.prepareGlossary,
      config.onekey_prepare_glossary === true,
    ),
    prepare_lexicon: pick(
      overrides.prepareLexicon,
      config.onekey_prepare_lexicon !== false,
    ),
  };
}

/** 从准备结果里取词库报告；缺字段或旧结构时返回 null。 */
export function onekeyLexiconReport(result) {
  const source = result && typeof result === 'object' ? result : null;
  if (!source) return null;
  if (source.lexicon && typeof source.lexicon === 'object') return source.lexicon;
  // 兼容后端把词库报告平铺在结果顶层（success/message/glossary/preserve/warnings）
  const flattened = source.success === false
    || Array.isArray(source.warnings)
    || (source.glossary && typeof source.glossary === 'object')
    || (source.preserve && typeof source.preserve === 'object');
  return flattened ? source : null;
}

/**
 * 取当前任务结果与最近 ready 结果里第一份真实词库报告。
 * 后续 apply job 的 result 非 null 但不含 lexicon 时，不能因此隐藏 ready 已有的报告/警告。
 */
export function onekeyLexiconReportOf(...results) {
  for (const result of results) {
    const report = onekeyLexiconReport(result);
    if (report) return report;
  }
  return null;
}

const stringList = (value) =>
  Array.isArray(value) ? value.map((item) => String(item ?? '').trim()).filter(Boolean) : [];

/** 词库步骤是否应升级为警告：partial/failed、整体失败或有 warnings。 */
export function onekeyLexiconHasWarning(report) {
  if (!report || typeof report !== 'object') return false;
  if (report.success === false) return true;
  if (stringList(report.warnings).length) return true;
  return ['glossary', 'preserve'].some((key) => {
    const step = report[key];
    if (!step || typeof step !== 'object') return false;
    return step.status === 'partial' || step.status === 'failed';
  });
}

/**
 * 词库步骤展示行：优先用后端 status/message，兼容旧的 glossary/preserve 摘要结构。
 * 不把 partial/failed 伪装成成功；skipped 也如实展示。
 */
export function onekeyLexiconSummaryLines(report) {
  if (!report || typeof report !== 'object') return [];
  const lines = [];
  for (const key of ['glossary', 'preserve']) {
    const step = report[key];
    if (step && typeof step === 'object') {
      const message = String(step.message ?? '').trim();
      const status = String(step.status ?? '').trim();
      if (message) lines.push(message);
      else if (status) lines.push(`${key}: ${status}`);
    }
  }
  if (!lines.length) {
    const message = String(report.message ?? '').trim();
    if (message) lines.push(message);
  }
  // success === false 但没有分步信息时，至少给出整体失败提示
  if (!lines.length && report.success === false) lines.push('failed');
  for (const warning of stringList(report.warnings)) lines.push(warning);
  return lines;
}

export function prepareStageSummaryLines(result, labels = {}, fill = fillTemplate) {
  if (!result || typeof result !== 'object') return [];
  // 跳过抽取时没有检测/解包/反编译过程，避免误显示“检测完成”
  if (result.skipped_extraction) return [];

  const lines = [];
  const detectStatus = result.detect_status != null ? String(result.detect_status) : '';
  if (DETECT_DONE_STATUSES.has(detectStatus) && labels.detect) {
    lines.push(labels.detect);
  }

  const unpack = result.unpack;
  if (unpack && typeof unpack === 'object' && labels.unpack) {
    const hasCount = unpack.count != null && unpack.count !== '';
    const method = unpack.method != null ? String(unpack.method).trim() : '';
    if (hasCount || method) {
      lines.push(fill(labels.unpack, {
        count: hasCount ? unpack.count : '—',
        method: method || '—',
      }));
    }
  }

  const decompile = result.decompile;
  if (decompile && typeof decompile === 'object' && labels.decompile) {
    const method = decompile.method != null ? String(decompile.method).trim() : '';
    if (method) {
      lines.push(fill(labels.decompile, { method }));
    }
  }

  // 抽取成功或已进入路径配置/就绪时，显示抽取完成
  if (
    labels.extract
    && (result.extraction_success === true || result.stage === 'paths' || result.stage === 'ready')
  ) {
    lines.push(labels.extract);
  }

  return lines;
}
