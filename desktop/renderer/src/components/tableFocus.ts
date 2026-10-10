/** Ant 虚拟表格只挂载可视窗口内的行：先 scrollTo 目标，再等行真实挂载后聚焦。 */
import type { RefObject } from 'react';
import type { TableRef } from 'antd/es/table';

/**
 * focus 返回 false 表示目标子元素尚未就绪，继续逐帧等待。
 * 返回取消函数，供 effect 清理时调用。
 */
export function focusTableRow(
  table: RefObject<TableRef | null>,
  key: string,
  focus: (row: HTMLElement) => boolean | void,
): () => void {
  let frames = 0;
  let handle = 0;
  table.current?.scrollTo({ key, align: 'nearest' });
  const tick = () => {
    const row = table.current?.nativeElement?.querySelector<HTMLElement>(`[data-row-key="${CSS.escape(key)}"]`);
    if (row && focus(row) !== false) return;
    frames += 1;
    if (frames < 30) handle = requestAnimationFrame(tick);
  };
  handle = requestAnimationFrame(tick);
  return () => cancelAnimationFrame(handle);
}
