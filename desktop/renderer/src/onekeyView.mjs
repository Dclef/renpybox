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
