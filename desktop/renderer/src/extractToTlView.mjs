/**
 * 抽取到 TL 页纯函数：有效译文判断、增量路径、选项归一（对齐 Qt RenpyTranslationPage）。
 */

const IGNORED_NAMES = new Set([
  'replace_text_auto.rpy',
  'set_default_language_at_startup.rpy',
]);

/** 与后端 is_effective_tl_rpy / Qt 一致。 */
export function isEffectiveTlRpy(fileName) {
  const name = String(fileName ?? '').toLowerCase();
  if (!name.endsWith('.rpy')) return false;
  if (name.startsWith('miss_ready_replace')) return false;
  if (name.startsWith('hook_')) return false;
  if (IGNORED_NAMES.has(name)) return false;
  return true;
}

/** 有有效 tl/*.rpy 时走增量抽取。 */
export function shouldUseIncremental(fileNames) {
  if (!Array.isArray(fileNames)) return false;
  return fileNames.some((name) => isEffectiveTlRpy(name));
}

/**
 * 自定义规则强制关闭官方/补充；否则至少保留一种。
 * 无 EXE 且官方开启时关闭官方并回退补充。
 */
export function resolveExtractSwitches({
  useOfficial,
  useCustom,
  ruleMode = 'builtin',
  hasExe = true,
} = {}) {
  let official = Boolean(useOfficial);
  let custom = Boolean(useCustom);
  if (String(ruleMode) === 'custom') {
    return { useOfficial: false, useCustom: false, ruleMode: 'custom' };
  }
  if (!official && !custom) custom = true;
  if (official && !hasExe) {
    official = false;
    if (!custom) custom = true;
  }
  return { useOfficial: official, useCustom: custom, ruleMode: String(ruleMode || 'builtin') };
}

/** supplement_mode 仅 precise / aggressive。 */
export function normalizeSupplementMode(value) {
  const mode = String(value ?? 'precise').toLowerCase();
  return mode === 'aggressive' ? 'aggressive' : 'precise';
}

/** 可疑备份列表中的首选打开路径。 */
export function preferredSuspiciousOpenPath(status) {
  const manifests = Array.isArray(status?.suspicious_manifests) ? status.suspicious_manifests : [];
  if (manifests.length && manifests[0]?.path) return String(manifests[0].path);
  if (status?.open_path) return String(status.open_path);
  const tl = String(status?.tl_dir || '').trim();
  return tl ? `${tl.replace(/[\\/]+$/, '')}/_filtered_suspicious` : '';
}

/** 组装抽取到 TL 的 status URL；手选 game_dir 时按独立目标键轮询。 */
export function extractToTlStatusPath({ gameDir = '', language = 'chinese' } = {}) {
  const lang = String(language || 'chinese').trim() || 'chinese';
  const qs = new URLSearchParams({ language: lang });
  const dir = String(gameDir || '').trim();
  if (dir) qs.set('game_dir', dir);
  return `/api/extract-to-tl?${qs.toString()}`;
}

/** 终态 Banner：取消/部分写入/业务失败不用绿色成功。 */
export function extractToTlStatusTone({ active = false, checking = false, job = null, result = null } = {}) {
  if (active || checking) return 'info';
  const status = job?.status;
  const partial = Boolean(result?.partial);
  const failedBiz = result?.success === false;
  if (status === 'cancelled' || partial || (status === 'done' && failedBiz)) return 'warning';
  if (status === 'failed') return result?.written || partial ? 'warning' : 'error';
  if (status === 'done') return 'success';
  return 'info';
}
