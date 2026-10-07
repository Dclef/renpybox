import { memo, useRef } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import type { Row } from './types';

interface Props {
  rows: Row[];
}

/**
 * 十万级虚拟表格。三个关键点：
 * 1. 只渲染可视区（这是 Qt QTableWidget 做不到的）
 * 2. 动态行高测量：翻译文本行长不一，必须 measureElement
 * 3. 行组件 memo，避免父组件重渲时全表重绘
 */
const RowItem = memo(function RowItem({ row }: { row: Row }) {
  return (
    <div className="row">
      <span className="idx">{row.id}</span>
      <span className={`tag ${row.status}`}>{row.status}</span>
      <span className="text">{row.source}</span>
      <span className="text target">{row.target || '—'}</span>
    </div>
  );
});

export function VirtualTable({ rows }: Props) {
  const parentRef = useRef<HTMLDivElement>(null);

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 68,
    overscan: 8,
    getItemKey: (i) => rows[i]?.id ?? i,
  });

  return (
    <>
      <div className="table-head">
        <span>#</span>
        <span>状态</span>
        <span>原文</span>
        <span>译文</span>
      </div>
      <div className="table-body" ref={parentRef}>
        {rows.length === 0 ? (
          <div className="empty">点「加载 10 万行」开始</div>
        ) : (
          <div className="table-sizer" style={{ height: virtualizer.getTotalSize() }}>
            {virtualizer.getVirtualItems().map((item) => (
              <div
                key={item.key}
                className="row-wrap"
                style={{ transform: `translateY(${item.start}px)` }}
                data-index={item.index}
                ref={virtualizer.measureElement}
              >
                <RowItem row={rows[item.index]} />
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}