/** 禁翻表：原文在翻译时逐字符保留，数据写入配置 text_preserve_data。 */
import { useEffect, useState } from 'react';
import { Button, Checkbox, Textarea, TextInput } from '@mantine/core';

import { DataSheet } from '../components/DataSheet';
import type { AppState } from '../useAppState';
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
  const [selected, setSelected] = useState<number | null>(null);
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
  const selectedRow = selected != null ? rows[selected] : undefined;

  const save = () => {
    const cleaned = rows.map((row) => ({ src: row.src.trim(), comment: row.comment.trim() })).filter((row) => row.src);
    const nextEnabled = cleaned.length > 0 ? true : enabled;
    state.setSetting('text_preserve_data', cleaned);
    state.setSetting('text_preserve_enable', nextEnabled);
    setRows(cleaned);
    setEnabled(nextEnabled);
    setSelected(null);
    setDirty(false);
    state.pushToast('success', `已保存 ${cleaned.length} 条禁翻规则`);
  };

  const patch = (index: number, next: Partial<PreserveRow>) => {
    setRows((previous) => previous.map((item, i) => (i === index ? { ...item, ...next } : item)));
    setDirty(true);
  };

  return (
    <div className="rb-embedded">
      <div className="rb-toolbar">
        <div className="rb-sheet-summary">
          <strong>{rows.length} 条规则</strong>
          <span>{dirty ? '有未保存修改' : enabled ? '翻译时会套用' : '当前未启用'}</span>
        </div>
        <span className="rb-toolbar-spacer" />
        <Button variant="default" disabled={locked} onClick={() => { setRows((previous) => [{ src: '', comment: '' }, ...previous]); setQuery(''); setSelected(0); setDirty(true); }}>新增规则</Button>
        <Button disabled={locked || !dirty} onClick={save}>{state.saving ? '保存中…' : '保存'}</Button>
      </div>
      <div className="rb-toolbar">
        <TextInput w={280} aria-label="搜索禁翻规则" placeholder="搜索原文或备注" value={query} onChange={(event) => setQuery(event.currentTarget.value)} />
        <Checkbox label="翻译时启用禁翻表" checked={enabled} disabled={locked} onChange={(event) => { setEnabled(event.currentTarget.checked); setDirty(true); }} />
      </div>
      {locked && state.translation.engine_status !== 'IDLE' ? <Banner tone="info">任务执行期间只读，结束后再保存。</Banner> : null}
      <DataSheet
        rows={visible}
        getKey={(entry) => String(entry.index)}
        selectedKey={selected == null ? null : String(selected)}
        onSelect={(key) => setSelected(key == null ? null : Number(key))}
        emptyText={query ? '没有匹配的规则' : '还没有禁翻规则'}
        columns={[
          { key: 'src', title: '原文', render: ({ row }) => <span>{row.src}</span> },
          { key: 'comment', title: '备注', render: ({ row }) => <span>{row.comment}</span> },
        ]}
        editorClassName="rb-term-editor"
        editor={selectedRow && selected != null ? (
          <>
            <header>
              <h2>禁翻规则 {selected + 1}</h2>
              <Button variant="default" size="xs" onClick={() => setSelected(null)}>完成</Button>
            </header>
            <Textarea autosize aria-label={`禁翻规则 ${selected + 1} 原文`} disabled={locked} value={selectedRow.src} onChange={(event) => patch(selected, { src: event.currentTarget.value })} />
            <TextInput aria-label={`禁翻规则 ${selected + 1} 备注`} placeholder="备注（可选）" disabled={locked} value={selectedRow.comment} onChange={(event) => patch(selected, { comment: event.currentTarget.value })} />
            <Button color="red" variant="subtle" disabled={locked} onClick={() => { setRows((previous) => previous.filter((_, i) => i !== selected)); setSelected(null); setDirty(true); }}>移除</Button>
          </>
        ) : null}
      />
    </div>
  );
}
