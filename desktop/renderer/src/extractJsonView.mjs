/**
 * 文本提取 JSON 页纯函数：目标路径与导出就绪预检。
 */

/** 解析游戏 EXE / 项目根；空则回落 defaultRoot。 */
export function resolveGameFile(gameFile, defaultRoot = '') {
  const text = String(gameFile ?? '').trim();
  if (text) return text;
  return String(defaultRoot ?? '').trim();
}

/**
 * 组装 JSON 工具 status URL：带当前手动 game_file（或 defaultRoot）与 language，
 * 供未绑定长任务轮询按独立目标键取回 job。
 */
export function extractJsonStatusPath({ gameFile = '', language = 'chinese', defaultRoot = '' } = {}) {
  const lang = String(language || 'chinese').trim() || 'chinese';
  const game = resolveGameFile(gameFile, defaultRoot);
  const qs = new URLSearchParams({ language: lang });
  if (game) qs.set('game_file', game);
  return `/api/extract-json?${qs.toString()}`;
}

/** 终态 Banner：取消/部分写入/业务失败不用绿色成功。 */
export function extractJsonStatusTone({ active = false, checking = false, job = null, result = null } = {}) {
  if (active || checking) return 'info';
  const status = job?.status;
  const partial = Boolean(result?.partial);
  const failedBiz = result?.success === false;
  if (status === 'cancelled' || partial || (status === 'done' && failedBiz)) return 'warning';
  if (status === 'failed') return result?.written || partial ? 'warning' : 'error';
  if (status === 'done') return 'success';
  return 'info';
}

/** 导出 JSON：需要目标路径与输出文件。 */
export function exportJsonReady({ gameFile, outputPath, defaultRoot } = {}) {
  return Boolean(resolveGameFile(gameFile, defaultRoot) && String(outputPath ?? '').trim());
}

/** 导入：需要 JSON 路径与项目目标。 */
export function importJsonReady({ gameFile, jsonPath, defaultRoot } = {}) {
  return Boolean(resolveGameFile(gameFile, defaultRoot) && String(jsonPath ?? '').trim());
}

/** 预览摘要占位。 */
export function formatPreviewSummary(template, { fileCount = 0, entryCount = 0 } = {}) {
  return String(template || '')
    .replaceAll('{file_count}', String(fileCount))
    .replaceAll('{entry_count}', String(entryCount));
}
