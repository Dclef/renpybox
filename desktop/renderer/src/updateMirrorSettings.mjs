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

/** 把镜像列表格式化成多行文本（parseMirrorList 的逆操作）。 */
export function formatMirrorList(list) {
  if (!Array.isArray(list)) return '';
  return list
    .filter((item) => typeof item === 'string')
    .map((item) => item.trim())
    .filter((item) => item !== '')
    .join('\n');
}
