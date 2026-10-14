// 解包/打包页的纯展示逻辑：不依赖 React，便于 node:test 直接覆盖。

/** Qt5 只有打包支持取消；解包、反编译和清理一旦开始就跑到结束。 */
export const CANCELLABLE_ARCHIVE_KINDS = ['archive_pack'];

export function archiveJobCancellable(job) {
  return Boolean(job && CANCELLABLE_ARCHIVE_KINDS.includes(job.kind));
}

function splitTail(path) {
  const trimmed = String(path ?? '').trim().replace(/[\\/]+$/, '');
  const index = Math.max(trimmed.lastIndexOf('/'), trimmed.lastIndexOf('\\'));
  return { trimmed, index, name: trimmed.slice(index + 1) };
}

/** 源目录本身是 game 时，留空输出会落到项目根的 game.rpa，Ren'Py 不会加载。 */
export function isGameFolder(source) {
  const { name } = splitTail(source);
  return name.toLowerCase() === 'game';
}

/** 仅用于展示：与 Qt5 一致推导为源目录同级的“源目录名.rpa”，实际路径由后端重新推导。 */
export function derivePackOutput(source) {
  const { trimmed, index, name } = splitTail(source);
  if (index < 0 || !name || name.endsWith(':') || isGameFolder(trimmed)) return '';
  return `${trimmed.slice(0, index + 1)}${name}.rpa`;
}

/** 与 Qt5 一致：相对文件名落在源目录同级；后端按 sidecar 工作目录解析相对路径，故提交前补成绝对路径。 */
export function resolvePackOutput(source, output) {
  const value = String(output ?? '').trim();
  if (!value) return '';
  if (/^([a-zA-Z]:[\\/]|[\\/])/.test(value)) return value;
  const { trimmed, index } = splitTail(source);
  return index < 0 ? value : `${trimmed.slice(0, index + 1)}${value}`;
}
