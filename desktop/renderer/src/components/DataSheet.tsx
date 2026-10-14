/** 术语表与禁翻表共用表格：本地分页，双击/F2 在单元格内编辑。 */
import { useLayoutEffect, useRef, useState, type KeyboardEvent, type MouseEvent, type ReactNode } from 'react';
import { Button, Input, Select, Table } from 'antd';
import type { ColumnsType, TableRef } from 'antd/es/table';
import type { TextAreaRef } from 'antd/es/input/TextArea';

import { useT } from '../i18n';
import { focusTableRow } from './tableFocus';

export interface DataSheetColumn<T> {
  key: string;
  title: ReactNode;
  width?: string;
  /** 可编辑字段名；缺省或空表示只读。 */
  editKey?: string;
  render: (row: T) => ReactNode;
}

export interface DataSheetEditTarget {
  rowKey: string;
  columnKey: string;
}

const PAGE_SIZES = [25, 50, 100];

export function DataSheet<T extends object>(props: {
  rows: T[];
  getKey: (row: T) => string;
  columns: DataSheetColumn<T>[];
  selectedKey: string | null;
  onSelect: (key: string | null) => void;
  /** 原始序号（从 1 计）。筛选和翻页后仍对应同一条数据。 */
  rowNumber: (row: T) => number;
  /** 读取单元格草稿文本；仅可编辑列需要。 */
  getEditValue?: (row: T, editKey: string) => string;
  /** 提交单元格编辑到草稿。 */
  /** reason 为 project-change 时是项目切换前保留旧草稿，父组件不应因写锁拒绝，只写回本地行数据。 */
  onCommitEdit?: (rowKey: string, editKey: string, value: string, reason?: 'project-change') => void;
  /** 只读时禁止进入编辑。 */
  readOnly?: boolean;
  /** 结构替换时撤销旧单元格，防止下标重排串写。 */
  editGeneration?: number;
  /** 变化时（如项目切换）先把未 blur 的单元格文字提交回当前行，再关闭编辑器。 */
  flushKey?: string;
  onDraftChange?: (dirty: boolean) => void;
  /** 外部请求开始编辑（例如新增后定位原文）。 */
  editRequest?: DataSheetEditTarget | null;
  onEditRequestConsumed?: () => void;
  emptyText: string;
  footer?: ReactNode;
  /** 变化时回到第一页（搜索、新增）。 */
  resetPageToken?: number;
  label: string;
}) {
  const t = useT();
  const {
    rows, getKey, columns, selectedKey, onSelect, rowNumber,
    getEditValue, onCommitEdit, readOnly = false, editGeneration = 0, flushKey = '', onDraftChange,
    editRequest, onEditRequestConsumed,
    emptyText, footer, resetPageToken = 0, label,
  } = props;
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [editing, setEditing] = useState<DataSheetEditTarget | null>(null);
  const [draft, setDraft] = useState('');
  const [scrollY, setScrollY] = useState(200);
  const [scrollX, setScrollX] = useState(720);
  const inputRef = useRef<TextAreaRef>(null);
  const tableRef = useRef<TableRef>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const editRef = useRef<{ target: DataSheetEditTarget; value: string; original: string } | null>(null);
  const flushKeyRef = useRef(flushKey);
  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize));
  const current = Math.min(page, pageCount);
  const visible = rows.slice((current - 1) * pageSize, current * pageSize);
  const editableColumns = columns.filter((column) => column.editKey);

  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const measure = () => {
      const header = el.querySelector('.ant-table-header') as HTMLElement | null;
      const headerH = header?.offsetHeight ?? 36;
      // 下限与 .rb-sheet-scroll 的 CSS min-height 一致，避免两层各自坚持不同最低高度而裁切
      setScrollY(Math.max(48, el.clientHeight - headerH - 2));
      // antd Table virtual 要求 scroll.x/y 均为 number
      setScrollX(Math.max(520, el.clientWidth));
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useLayoutEffect(() => {
    if (flushKeyRef.current === flushKey) return;
    flushKeyRef.current = flushKey;
    const edit = editRef.current;
    editRef.current = null;
    const column = edit ? columns.find((item) => item.key === edit.target.columnKey) : undefined;
    // 只读也要提交：草稿属于切换前的行数据，由父组件决定能否写回项目
    if (edit && column?.editKey && edit.value !== edit.original) onCommitEdit?.(edit.target.rowKey, column.editKey, edit.value, 'project-change');
    setEditing(null);
    setDraft('');
    onDraftChange?.(false);
  }, [flushKey]);

  useLayoutEffect(() => {
    editRef.current = null;
    setEditing(null);
    setDraft('');
    onDraftChange?.(false);
  }, [editGeneration]);

  useLayoutEffect(() => {
    tableRef.current?.scrollTo({ top: 0 });
  }, [current, resetPageToken]);

  useLayoutEffect(() => {
    setPage((value) => Math.min(value, pageCount));
  }, [pageCount]);
  useLayoutEffect(() => {
    setPage(1);
  }, [resetPageToken]);

  useLayoutEffect(() => {
    if (!editRequest || readOnly || !onCommitEdit || !getEditValue) return;
    const rowIndex = rows.findIndex((item) => getKey(item) === editRequest.rowKey);
    const row = rowIndex >= 0 ? rows[rowIndex] : undefined;
    const column = columns.find((item) => item.key === editRequest.columnKey && item.editKey);
    if (!row || !column?.editKey) {
      onEditRequestConsumed?.();
      return;
    }
    setPage(Math.floor(rowIndex / pageSize) + 1);
    onSelect(editRequest.rowKey);
    const value = getEditValue(row, column.editKey);
    editRef.current = { target: editRequest, value, original: value };
    setEditing(editRequest);
    setDraft(value);
    onEditRequestConsumed?.();
  }, [editRequest, readOnly, rows, columns, getKey, getEditValue, onCommitEdit, onSelect, onEditRequestConsumed, pageSize]);

  useLayoutEffect(() => {
    if (!editing) return;
    return focusTableRow(tableRef, editing.rowKey, (row) => {
      const textArea = inputRef.current?.resizableTextArea?.textArea;
      if (!textArea || !row.contains(textArea)) return false;
      inputRef.current?.focus({ cursor: 'all' });
      return true;
    });
  }, [editing]);

  const beginEdit = (rowKey: string, columnKey: string) => {
    if (readOnly || !onCommitEdit || !getEditValue) return;
    const row = rows.find((item) => getKey(item) === rowKey);
    const column = columns.find((item) => item.key === columnKey && item.editKey);
    if (!row || !column?.editKey) return;
    onSelect(rowKey);
    const value = getEditValue(row, column.editKey);
    editRef.current = { target: { rowKey, columnKey }, value, original: value };
    setEditing({ rowKey, columnKey });
    setDraft(value);
  };

  const cancelEdit = () => {
    editRef.current = null;
    onDraftChange?.(false);
    setEditing(null);
    setDraft('');
  };

  const commitEdit = (target?: DataSheetEditTarget) => {
    if (readOnly) return;
    const edit = editRef.current;
    if (!edit || (target && (target.rowKey !== edit.target.rowKey || target.columnKey !== edit.target.columnKey))) return;
    editRef.current = null;
    const column = columns.find((item) => item.key === edit.target.columnKey);
    if (!readOnly && column?.editKey && edit.value !== edit.original && onCommitEdit) {
      onCommitEdit(edit.target.rowKey, column.editKey, edit.value);
    }
    onDraftChange?.(false);
    setEditing(null);
    setDraft('');
  };

  const moveEdit = (delta: number) => {
    if (readOnly || !editing || !onCommitEdit || !getEditValue) return;
    const column = columns.find((item) => item.key === editing.columnKey);
    if (column?.editKey && editRef.current?.value !== editRef.current?.original) onCommitEdit(editing.rowKey, column.editKey, editRef.current?.value ?? draft);
    onDraftChange?.(false);

    const rowIndex = rows.findIndex((item) => getKey(item) === editing.rowKey);
    const colIndex = editableColumns.findIndex((item) => item.key === editing.columnKey);
    if (rowIndex < 0 || colIndex < 0 || editableColumns.length === 0) {
      cancelEdit();
      return;
    }
    let nextRow = rowIndex;
    let nextCol = colIndex + delta;
    if (nextCol >= editableColumns.length) {
      nextCol = 0;
      nextRow += 1;
    } else if (nextCol < 0) {
      nextCol = editableColumns.length - 1;
      nextRow -= 1;
    }
    if (nextRow < 0 || nextRow >= rows.length) {
      cancelEdit();
      return;
    }
    const nextRowKey = getKey(rows[nextRow]);
    const nextColumn = editableColumns[nextCol];
    const pageForRow = Math.floor(nextRow / pageSize) + 1;
    if (pageForRow !== current) setPage(pageForRow);
    onSelect(nextRowKey);
    const value = getEditValue(rows[nextRow], nextColumn.editKey!);
    editRef.current = { target: { rowKey: nextRowKey, columnKey: nextColumn.key }, value, original: value };
    setEditing({ rowKey: nextRowKey, columnKey: nextColumn.key });
    setDraft(value);
  };

  const onRowKey = (event: KeyboardEvent<HTMLElement>, key: string) => {
    if (editing) return;
    if (event.key === 'Enter') {
      event.preventDefault();
      onSelect(key);
    } else if (event.key === 'F2') {
      event.preventDefault();
      const first = editableColumns[0];
      if (first) beginEdit(key, first.key);
    }
  };

  const onEditorKey = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.nativeEvent.isComposing) return;
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      commitEdit();
    } else if (event.key === 'Escape') {
      event.preventDefault();
      cancelEdit();
    } else if (event.key === 'Tab') {
      event.preventDefault();
      moveEdit(event.shiftKey ? -1 : 1);
    }
  };

  const tableColumns: ColumnsType<T> = [
    {
      key: '__index',
      title: t('sheet_index'),
      width: 56,
      className: 'rb-proof-index',
      render: (_value, row) => rowNumber(row),
    },
    ...columns.map((column) => {
      const canEditCol = Boolean(column.editKey) && !readOnly && Boolean(onCommitEdit);
      return {
        key: column.key,
        title: column.title,
        width: column.width,
        className: canEditCol ? 'rb-sheet-cell-editable' : undefined,
        onCell: (row: T) => ({
          onDoubleClick: (event: MouseEvent) => {
            if (!canEditCol) return;
            event.stopPropagation();
            beginEdit(getKey(row), column.key);
          },
        }),
        render: (_value: unknown, row: T) => {
          const key = getKey(row);
          const isEditing = editing?.rowKey === key && editing.columnKey === column.key;
          if (isEditing) {
            return (
              <Input.TextArea
                ref={inputRef}
                className="rb-sheet-cell-editor"
                aria-label={`${t('sheet_edit_cell')} ${column.key}`}
                autoSize={{ minRows: 1, maxRows: 8 }}
                value={draft}
                disabled={readOnly}
                onChange={(event) => {
                  const value = event.target.value;
                  if (editRef.current) {
                    editRef.current.value = value;
                    onDraftChange?.(value !== editRef.current.original);
                  }
                  setDraft(value);
                }}
                onKeyDown={onEditorKey}
                onBlur={() => commitEdit({ rowKey: key, columnKey: column.key })}
              />
            );
          }
          return column.render(row);
        },
      };
    }),
  ];

  return (
    <div className="rb-sheet">
      <div className="rb-sheet-table">
        <div className="rb-sheet-scroll" ref={scrollRef} aria-label={label}>
          <Table<T>
            ref={tableRef}
            className="rb-proof-table"
            size="small"
            bordered
            tableLayout="fixed"
            rowKey={getKey}
            columns={tableColumns}
            dataSource={visible}
            pagination={false}
            virtual
            scroll={{ x: scrollX, y: scrollY }}
            locale={{ emptyText: <div className="rb-proof-empty">{emptyText}</div> }}
            rowClassName={() => 'rb-term-row'}
            onRow={(row) => {
              const key = getKey(row);
              const selected = selectedKey === key;
              return {
                'data-selected': selected ? 'true' : undefined,
                'aria-selected': selected,
                tabIndex: 0,
                onClick: () => { if (!editing) onSelect(key); },
                onKeyDown: (event) => onRowKey(event, key),
              };
            }}
          />
        </div>
        <footer className="rb-sheet-foot proofreading-pagination">
          <span>{footer != null && footer !== '' ? <>{footer} · </> : null}{current} / {pageCount}</span>
          <div className="proofreading-toolbar">
            <Select
              aria-label={t('sheet_page_size')}
              size="small"
              style={{ width: 118 }}
              allowClear={false}
              value={String(pageSize)}
              options={PAGE_SIZES.map((value) => ({
                value: String(value),
                label: t('sheet_per_page').replace('{count}', String(value)),
              }))}
              onChange={(value) => { setPageSize(Number(value)); setPage(1); }}
            />
            <Button size="small" disabled={current <= 1} onClick={() => setPage(current - 1)}>{t('sheet_prev')}</Button>
            <Button size="small" disabled={current >= pageCount} onClick={() => setPage(current + 1)}>{t('sheet_next')}</Button>
          </div>
        </footer>
      </div>
    </div>
  );
}
