/** 禁翻表：原文在翻译时逐字符保留，数据写入配置 text_preserve_data。 */
import { useEffect, useState } from 'react';
import type { AppState } from '../useAppState';
import { Button, Input, Table } from 'antd';
import { Banner } from '../ui';

interface PreserveRow {
  src: string;
  comment: string;
}

function readRows(value: unknown): PreserveRow[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => {
    if (typeof item === 'string') return { src: item, comment: '' };
    const row = item as { src?: unknown; comment?: unknown; info?: unknown };
    return {
      src: String(row.src ?? ''),
      comment: String(row.comment ?? row.info ?? ''),
    };
  });
}

export function PreservePage(props: { state: AppState; onDirtyChange?: (dirty: boolean) => void }) {
  const { state, onDirtyChange } = props;
  const stored = state.settings?.values.text_preserve_data;
  const [rows, setRows] = useState<PreserveRow[]>(() => readRows(stored));
  const [enabled, setEnabled] = useState(state.settings?.values.text_preserve_enable === true);
  const [dirty, setDirty] = useState(false);
  const [query, setQuery] = useState('');
  const locked = state.saving || state.translation.engine_status !== 'IDLE' || state.translation.stop_barrier;

  useEffect(() => {
    if (dirty) return;
    setRows(readRows(state.settings?.values.text_preserve_data));
    setEnabled(state.settings?.values.text_preserve_enable === true);
  }, [dirty, state.settings?.values.text_preserve_data, state.settings?.values.text_preserve_enable]);

  useEffect(() => {
    onDirtyChange?.(dirty);
    return () => onDirtyChange?.(false);
  }, [dirty, onDirtyChange]);

  const visible = rows
    .map((row, index) => ({ row, index }))
    .filter(({ row }) => `${row.src} ${row.comment}`.toLowerCase().includes(query.toLowerCase()));

  const save = () => {
    const cleaned = rows.map((row) => ({ src: row.src.trim(), comment: row.comment.trim() })).filter((row) => row.src);
    const nextEnabled = cleaned.length > 0 ? true : enabled;
    state.setSetting('text_preserve_data', cleaned);
    state.setSetting('text_preserve_enable', nextEnabled);
    setRows(cleaned);
    setEnabled(nextEnabled);
    setDirty(false);
    state.pushToast('success', `已保存 ${cleaned.length} 条禁翻规则`);
  };

  return (
    <div className="settings-layout glossary-layout">
      <header className="settings-header">
        <h1 className="settings-title">禁翻表</h1>
        <p className="settings-subtitle">这些原文会在译文里原样保留，适合变量、代码和不应翻译的专名。</p>
      </header>
      <div className="settings-scroll glossary-scroll">
        <div className="workspace-toolbar">
          <div className="workspace-summary">
            <strong>{rows.length} 条规则</strong>
            <span>{dirty ? '有未保存修改' : enabled ? '翻译时会套用' : '当前未启用'}</span>
          </div>
          <div className="workspace-actions">
            <button type="button" className="btn btn-primary" disabled={locked || !dirty} onClick={save}>
              {state.saving ? '保存中…' : '保存'}
            </button>
          </div>
        </div>
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={enabled}
            disabled={locked}
            onChange={(event) => {
              setEnabled(event.target.checked);
              setDirty(true);
            }}
          />
          翻译时启用禁翻表
        </label>
        {locked && state.translation.engine_status !== 'IDLE' ? (
          <Banner tone="info">任务执行期间只读，结束后再保存。</Banner>
        ) : null}
        <div className="workspace-toolbar glossary-tools">
          <input
            type="text"
            aria-label="搜索禁翻规则"
            placeholder="搜索原文或备注"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <button
            type="button"
            className="btn"
            disabled={locked}
            onClick={() => {
              setRows((previous) => [{ src: '', comment: '' }, ...previous]);
              setQuery('');
              setDirty(true);
            }}
          >
            新增规则
          </button>
        </div>
        <Table
          className="data-sheet"
          size="small"
          bordered
          pagination={false}
          rowKey="index"
          dataSource={visible}
          locale={{ emptyText: query ? '没有匹配的规则' : '还没有禁翻规则' }}
          columns={[
            {
              title: '原文',
              render: (_, record) => (
                <Input.TextArea
                  aria-label={`禁翻规则 ${record.index + 1} 原文`}
                  autoSize={{ minRows: 1, maxRows: 4 }}
                  value={record.row.src}
                  disabled={locked}
                  onChange={(event) => {
                    const value = event.target.value;
                    setRows((previous) => previous.map((item, i) => (i === record.index ? { ...item, src: value } : item)));
                    setDirty(true);
                  }}
                />
              ),
            },
            {
              title: '备注',
              render: (_, record) => (
                <Input
                  aria-label={`禁翻规则 ${record.index + 1} 备注`}
                  placeholder="备注（可选）"
                  value={record.row.comment}
                  disabled={locked}
                  onChange={(event) => {
                    const value = event.target.value;
                    setRows((previous) => previous.map((item, i) => (i === record.index ? { ...item, comment: value } : item)));
                    setDirty(true);
                  }}
                />
              ),
            },
            {
              title: '操作',
              width: 88,
              render: (_, record) => (
                <Button
                  danger
                  type="link"
                  disabled={locked}
                  onClick={() => {
                    setRows((previous) => previous.filter((_, i) => i !== record.index));
                    setDirty(true);
                  }}
                >
                  移除
                </Button>
              ),
            },
          ]}
        />
      </div>
    </div>
  );
}
