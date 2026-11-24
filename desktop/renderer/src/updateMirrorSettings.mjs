/**
 * 更新镜像列表的纯函数（可被 node --test 直接导入，不依赖 React）。
 *
 * 用户在设置页「更新镜像」里一行填一个镜像前缀；空列表表示使用内置默认镜像。
 */

/**
 * 解析多行镜像列表。
 *
 * 规则：空行忽略；每行必须以 http:// 或 https:// 开头、以 / 结尾；重复项去重（保留首次出现）。
 * 返回 { values, errors }：values 是规范化后的列表，errors 是原样保留的非法行。
 */
export function parseMirrorList(text) {
  const values = [];
  const errors = [];
  const seen = new Set();
  for (const raw of String(text ?? '').split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) continue;
    const lower = line.toLowerCase();
    const okPrefix = lower.startsWith('http://') || lower.startsWith('https://');
    const okSuffix = line.endsWith('/');
    if (!okPrefix || !okSuffix) {
      errors.push(line);
      continue;
    }
    if (seen.has(line)) continue;
    seen.add(line);
    values.push(line);
  }
  return { values, errors };
}

// 内置默认镜像展示用副本：与 desktop/main/updater-mirror.js 的 GITHUB_DOWNLOAD_MIRRORS 保持一致（update-mirror-settings.test.mjs 有防漂移断言）。
export const BUILTIN_MIRRORS = Object.freeze([
  'https://fastgit.cc/',
  'https://cors.isteed.cc/',
]);

/** 内置默认镜像的多行展示文本（设置页空态只读展示用）。 */
export function builtinMirrorText() {
  return BUILTIN_MIRRORS.join('\n');
}

/** 配置值为空（或非列表）即表示使用内置默认镜像。 */
export function isUsingBuiltinMirrors(list) {
  return formatMirrorList(list) === '';
}

/** 把镜像列表格式化成多行文本（parseMirrorList 的逆操作）。 */
export function formatMirrorList(list) {
  if (!Array.isArray(list)) return '';
  return list
    .filter((item) => typeof item === 'string')
    .map((item) => item.trim())
    .filter((item) => item !== '')
    .join('\n');
}

// 下拉可勾选的预设镜像：内置两条实测可用 + 两条常见备用（须包含全部 BUILTIN_MIRRORS）
export const MIRROR_PRESETS = Object.freeze([
  ...BUILTIN_MIRRORS,
  'https://ghproxy.net/',
  'https://gh-proxy.com/',
]);

/** 从配置值读出有序镜像数组（与 formatMirrorList + parseMirrorList 一致）。 */
export function mirrorValuesFromSetting(value) {
  return parseMirrorList(formatMirrorList(value)).values;
}

/**
 * Select 多选 onChange：保留已在列表中的相对顺序，新勾选项按出现顺序追加到末尾。
 */
export function reconcileMirrorSelection(ordered, selected) {
  const pick = new Set(selected);
  const kept = ordered.filter((item) => pick.has(item));
  const keptSet = new Set(kept);
  const appended = selected.filter((item) => !keptSet.has(item));
  return [...kept, ...appended];
}

/**
 * 自定义输入追加一条/多行镜像：复用 parseMirrorList 校验，非法不改 values 并返回 errors。
 */
export function addCustomMirror(values, raw) {
  const base = Array.isArray(values) ? [...values] : [];
  const text = String(raw ?? '').trim();
  if (!text) return { values: base, errors: [] };
  const { values: parsed, errors } = parseMirrorList(text);
  if (errors.length > 0) return { values: base, errors };
  const seen = new Set(base);
  const next = [...base];
  for (const item of parsed) {
    if (!seen.has(item)) {
      seen.add(item);
      next.push(item);
    }
  }
  return { values: next, errors: [] };
}

/**
 * 测速结果排序：可用优先，速率降序，同速按延迟升序；仅第一名且可用时 fastest。
 * 不可用保留在末尾，供界面展示，不参与「最快」。
 */
export function rankMirrorResults(results) {
  const list = (Array.isArray(results) ? results : []).map((item) => ({
    prefix: String(item?.prefix ?? ''),
    latencyMs: Number.isFinite(Number(item?.latencyMs)) ? Number(item.latencyMs) : 0,
    bytesPerSec: Number.isFinite(Number(item?.bytesPerSec)) ? Number(item.bytesPerSec) : 0,
    ok: Boolean(item?.ok),
    fastest: false,
  }));
  list.sort((left, right) => {
    if (left.ok !== right.ok) return left.ok ? -1 : 1;
    if (right.bytesPerSec !== left.bytesPerSec) return right.bytesPerSec - left.bytesPerSec;
    return left.latencyMs - right.latencyMs;
  });
  if (list.length > 0 && list[0].ok) list[0].fastest = true;
  return list;
}

/** 自动保存用的前缀顺序：只留最快的两条可用非空前缀（直连空前缀不写入配置）。 */
export function speedOrderedMirrors(results) {
  return rankMirrorResults(results)
    .filter((item) => item.ok && item.prefix)
    .slice(0, 2)
    .map((item) => item.prefix);
}

/** 测速候选：当前列表为空则用预设，并始终追加直连空前缀，去重。 */
export function mirrorProbeCandidates(ordered) {
  const base = Array.isArray(ordered) && ordered.length > 0 ? ordered : [...MIRROR_PRESETS];
  const seen = new Set();
  const next = [];
  for (const item of [...base, '']) {
    const key = String(item ?? '');
    if (seen.has(key)) continue;
    seen.add(key);
    next.push(key);
  }
  return next;
}
