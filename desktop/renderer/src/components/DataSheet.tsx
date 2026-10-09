import { useEffect, useRef, type CSSProperties, type KeyboardEvent, type ReactNode } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { Checkbox } from '@mantine/core';

import { Empty } from '../ui';

export interface DataSheetColumn<T> {
  key: string;
  title: ReactNode;
  width?: string;
  render: (row: T) => ReactNode;
}

export function DataSheet<T>(props: {
  rows: T[];
  getKey: (row: T) => string;
  columns: DataSheetColumn<T>[];
  selectedKey: string | null;
  onSelect: (key: string | null) => void;
  rowClassName?: (row: T) => string;
  editor?: ReactNode;
  editorClassName?: string;
  emptyText: string;
  footer?: ReactNode;
  virtual?: boolean;
  rowHeight?: number;
  /** 变化时把列表滚回顶部。 */
  scrollTopToken?: number;
  selection?: { keys: Set<string>; onToggle: (key: string) => void; onToggleAll: (checked: boolean) => void; disabled?: boolean };
}) {
  const {
    rows, getKey, columns, selectedKey, onSelect, rowClassName, editor, editorClassName,
    emptyText, footer, virtual = true, rowHeight = 40, scrollTopToken = 0, selection,
  } = props;
  const listRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: virtual ? rows.length : 0,
    getScrollElement: () => listRef.current,
    estimateSize: () => rowHeight,
    overscan: 8,
  });
  const virtualizerRef = useRef(virtualizer);
  virtualizerRef.current = virtualizer;
  useEffect(() => {
    if (scrollTopToken > 0) virtualizerRef.current.scrollToOffset(0);
  }, [scrollTopToken]);

  const template = [
    ...(selection ? ['28px'] : []),
    ...columns.map((column) => column.width ?? 'minmax(0, 1fr)'),
  ].join(' ');
  const allChecked = selection != null && rows.length > 0 && rows.every((row) => selection.keys.has(getKey(row)));
  const grid = { display: 'grid', gridTemplateColumns: template } as const;

  const cells = (row: T) => {
    const key = getKey(row);
    return (
      <>
        {selection ? (
          <Checkbox
            checked={selection.keys.has(key)}
            disabled={selection.disabled}
            aria-label="选择行"
            onClick={(event) => event.stopPropagation()}
            onChange={() => selection.onToggle(key)}
          />
        ) : null}
        {columns.map((column) => <span key={column.key} className="rb-sheet-cell">{column.render(row)}</span>)}
      </>
    );
  };
  const rowProps = (row: T, style?: CSSProperties) => {
    const key = getKey(row);
    return {
      role: 'row' as const,
      tabIndex: 0,
      'data-selected': selectedKey === key ? 'true' : undefined,
      className: rowClassName?.(row),
      style: { ...grid, ...style },
      onClick: () => onSelect(key),
      onKeyDown: (event: KeyboardEvent) => { if (event.key === 'Enter') onSelect(key); },
    };
  };

  return (
    <div className="rb-sheet">
      <div className="rb-sheet-table" role="table">
        <div className="rb-sheet-head" role="row" style={grid}>
          {selection ? <Checkbox checked={allChecked} disabled={selection.disabled} aria-label="全选" onChange={(event) => selection.onToggleAll(event.currentTarget.checked)} /> : null}
          {columns.map((column) => <span key={column.key}>{column.title}</span>)}
        </div>
        <div className="rb-sheet-scroll" ref={listRef}>
          {rows.length === 0 ? <Empty>{emptyText}</Empty> : virtual ? (
            <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
              {virtualizer.getVirtualItems().map((item) => {
                const row = rows[item.index];
                if (!row) return null;
                return (
                  <div key={getKey(row)} {...rowProps(row, {
                    position: 'absolute', top: 0, left: 0, width: '100%', height: rowHeight,
                    transform: `translateY(${item.start}px)`,
                  })}>
                    {cells(row)}
                  </div>
                );
              })}
            </div>
          ) : rows.map((row) => (
            <div key={getKey(row)} {...rowProps(row, { minHeight: rowHeight })}>{cells(row)}</div>
          ))}
        </div>
        {footer != null ? <div className="rb-sheet-foot">{footer}</div> : null}
      </div>
      {editor ? <aside className={editorClassName}>{editor}</aside> : null}
    </div>
  );
}
