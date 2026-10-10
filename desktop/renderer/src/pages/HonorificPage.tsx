/** 称呼桥接：两列表格内编辑，备注随配置持久化；对齐旧 Qt 工具栏语义。 */
import { useEffect, useRef, useState } from 'react';
import { Button, Checkbox, Input } from 'antd';
import { Plus, Search } from 'lucide-react';

import { request } from '../api';
import { DataSheet, type DataSheetEditTarget } from '../components/DataSheet';
import { useT } from '../i18n';
import type { AppState } from '../useAppState';
import { Banner, NextStepBar } from '../ui';

interface HonorificRow {
  id: string;
  src: string;
  comment: string;
}

function readRows(value: unknown, nextId: () => string): HonorificRow[] {
  if (!Array.isArray(value)) return [];
  const rows: HonorificRow[] = [];
  for (const item of value) {
    if (typeof item === 'string') {
      const src = item.trim();
      if (!src) continue;
      rows.push({ id: nextId(), src, comment: '' });
      continue;
    }
    if (!item || typeof item !== 'object') continue;
    const row = item as { src?: unknown; comment?: unknown };
    const src = String(row.src ?? '').trim();
    if (!src) continue;
    rows.push({ id: nextId(), src, comment: String(row.comment ?? '').trim() });
  }
  return rows;
}

function serializeRows(rows: HonorificRow[]): Array<string | { src: string; comment: string }> {
  const out: Array<string | { src: string; comment: string }> = [];
  for (const row of rows) {
    const src = row.src.trim().toLowerCase();
    if (!src) continue;
    const comment = row.comment.trim();
    out.push(comment ? { src, comment } : src);
  }
  return out;
}

export function HonorificPage(props: { state: AppState; onDirtyChange?: (dirty: boolean) => void; onNextStep?: () => void }) {
  const { state, onDirtyChange, onNextStep } = props;
  const t = useT();
  const idSeq = useRef(0);
  const nextId = () => `h-${++idSeq.current}`;
  const operation = useRef(0);
  const mounted = useRef(true);
  const [rows, setRows] = useState<HonorificRow[]>(() => readRows(state.settings?.values.honorific_placeholder_titles, nextId));
  // 单元格 blur 提交与紧随其后的保存点击在同一事件序列内，保存必须读同步引用而非渲染闭包
  const rowsRef = useRef(rows);
  rowsRef.current = rows;
  const [enabled, setEnabled] = useState(state.settings?.values.honorific_placeholder_bridge_enable !== false);
  const [dirty, setDirty] = useState(false);
  const [cellDirty, setCellDirty] = useState(false);
  const [query, setQuery] = useState('');
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [pageToken, setPageToken] = useState(0);
  const [editGeneration, setEditGeneration] = useState(0);
  const [editRequest, setEditRequest] = useState<DataSheetEditTarget | null>(null);
  const [busy, setBusy] = useState(false);
  const unsaved = dirty || cellDirty;
  const engineBusy = state.saving || state.translation.engine_status !== 'IDLE' || state.translation.stop_barrier || state.translation.single_tasks;
  const locked = busy || engineBusy;

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      operation.current += 1;
    };
  }, []);

  useEffect(() => {
    if (unsaved) return;
    setRows(readRows(state.settings?.values.honorific_placeholder_titles, nextId));
    setEnabled(state.settings?.values.honorific_placeholder_bridge_enable !== false);
    setEditGeneration((value) => value + 1);
  }, [unsaved, state.settings?.values.honorific_placeholder_titles, state.settings?.values.honorific_placeholder_bridge_enable]);

  useEffect(() => {
    onDirtyChange?.(unsaved);
    return () => onDirtyChange?.(false);
  }, [unsaved, onDirtyChange]);

  const visible = rows
    .map((row, index) => ({ row, index }))
    .filter(({ row }) => `${row.src} ${row.comment}`.toLowerCase().includes(query.toLowerCase()));

  const bumpStructure = () => setEditGeneration((value) => value + 1);

  const save = async () => {
    const id = ++operation.current;
    const payload = serializeRows(rowsRef.current);
    setBusy(true);
    try {
      const ok = await state.saveSettings({
        honorific_placeholder_titles: payload,
        honorific_placeholder_bridge_enable: enabled,
      });
      if (!mounted.current || id !== operation.current) return;
      if (!ok) return;
      setRows(readRows(payload, nextId));
      setDirty(false);
      setCellDirty(false);
      bumpStructure();
      state.pushToast('success', t('honorific_saved').replace('{count}', String(payload.length)));
    } finally {
      if (mounted.current && id === operation.current) setBusy(false);
    }
  };

  const reload = async () => {
    if (unsaved && !window.confirm(t('honorific_reload_confirm'))) return;
    const id = ++operation.current;
    setBusy(true);
    try {
      await state.reloadSettings();
      const latest = await request<{ values: Record<string, unknown> }>('/api/settings');
      if (!mounted.current || id !== operation.current) return;
      const loaded = readRows(latest.values.honorific_placeholder_titles, nextId);
      setRows(loaded);
      setEnabled(latest.values.honorific_placeholder_bridge_enable !== false);
      setDirty(false);
      setCellDirty(false);
      setSelectedKey(null);
      bumpStructure();
      state.pushToast('success', t('honorific_loaded').replace('{count}', String(loaded.length)));
    } catch (error) {
      if (mounted.current && id === operation.current) {
        state.pushToast('error', error instanceof Error ? error.message : String(error));
      }
    } finally {
      if (mounted.current && id === operation.current) setBusy(false);
    }
  };

  const loadDefaults = async () => {
    if (!window.confirm(t('honorific_defaults_confirm'))) return;
    const id = ++operation.current;
    setBusy(true);
    try {
      const result = await request<{ titles: string[] }>('/api/settings/honorific-defaults');
      if (!mounted.current || id !== operation.current) return;
      setRows(result.titles.map((src) => ({ id: nextId(), src, comment: '' })));
      setDirty(true);
      setCellDirty(false);
      setSelectedKey(null);
      setQuery('');
      setPageToken((value) => value + 1);
      bumpStructure();
      state.pushToast('success', t('honorific_defaults_loaded').replace('{count}', String(result.titles.length)));
    } catch (error) {
      if (mounted.current && id === operation.current) {
        state.pushToast('error', error instanceof Error ? error.message : String(error));
      }
    } finally {
      if (mounted.current && id === operation.current) setBusy(false);
    }
  };

  const addRow = () => {
    const row = { id: nextId(), src: '', comment: '' };
    setRows((previous) => [...previous, row]);
    setQuery('');
    setPageToken((value) => value + 1);
    setSelectedKey(row.id);
    setDirty(true);
    bumpStructure();
    setEditRequest({ rowKey: row.id, columnKey: 'src' });
  };

  const removeSelected = () => {
    if (!selectedKey) {
      state.pushToast('info', t('honorific_select_delete'));
      return;
    }
    setRows((previous) => previous.filter((row) => row.id !== selectedKey));
    setSelectedKey(null);
    setDirty(true);
    bumpStructure();
  };

  const deduplicate = () => {
    const seen = new Map<string, HonorificRow>();
    let removed = 0;
    for (const row of rows) {
      const key = row.src.trim().toLowerCase();
      if (!key) continue;
      const existing = seen.get(key);
      if (!existing) {
        seen.set(key, { ...row, src: key, comment: row.comment.trim() });
        continue;
      }
      removed += 1;
      if (row.comment.trim() && !existing.comment.trim()) {
        seen.set(key, { ...existing, comment: row.comment.trim() });
      }
    }
    setRows([...seen.values()]);
    setSelectedKey(null);
    setDirty(true);
    bumpStructure();
    state.pushToast(
      removed ? 'success' : 'info',
      removed
        ? t('honorific_dedupe_done').replace('{removed}', String(removed)).replace('{kept}', String(seen.size))
        : t('honorific_dedupe_none'),
    );
  };

  const clearAll = () => {
    if (!window.confirm(t('honorific_clear_confirm'))) return;
    setRows([]);
    setSelectedKey(null);
    setDirty(true);
    setCellDirty(false);
    bumpStructure();
    state.pushToast('success', t('honorific_cleared'));
  };

  const summary = unsaved
    ? t('honorific_dirty')
    : enabled
      ? t('honorific_status_on')
      : t('honorific_status_off');

  return (
    <div className="rb-embedded rb-lexicon">
      <div className="rb-lexicon-controls">
      {engineBusy && state.translation.engine_status !== 'IDLE' ? <Banner tone="info">{t('honorific_busy_readonly')}</Banner> : null}
      <div className="rb-toolbar">
        <div className="rb-sheet-summary">
          <strong>{t('honorific_count').replace('{count}', String(rows.filter((row) => row.src.trim()).length))}</strong>
          <span>{summary}</span>
        </div>
        <span className="rb-toolbar-spacer" />
        <Button disabled={locked} onClick={() => void reload()}>{t('rules_reload')}</Button>
        <Button disabled={locked} onClick={() => void loadDefaults()}>{t('rules_defaults')}</Button>
        <Button danger type="text" disabled={locked || !rows.length} onClick={clearAll}>{t('rules_clear')}</Button>
        <Button type="primary" disabled={locked || !unsaved} onClick={() => void save()}>{state.saving || busy ? t('honorific_saving') : t('honorific_save')}</Button>
      </div>
      <div className="rb-toolbar">
        <Button disabled={locked} icon={<Plus size={16} strokeWidth={1.75} />} onClick={addRow}>{t('honorific_add')}</Button>
        <Button disabled={locked || !selectedKey} onClick={removeSelected}>{t('honorific_delete')}</Button>
        <Button disabled={locked || !rows.length} onClick={deduplicate}>{t('rules_deduplicate')}</Button>
        <Checkbox
          checked={enabled}
          disabled={locked}
          onChange={(event) => { setEnabled(event.target.checked); setDirty(true); }}
        >{t('honorific_enable')}</Checkbox>
      </div>
      <div className="rb-toolbar">
        <Input
          style={{ width: 280 }}
          aria-label={t('honorific_search')}
          placeholder={t('honorific_search_placeholder')}
          value={query}
          prefix={<Search size={16} strokeWidth={1.75} />}
          onChange={(event) => { setQuery(event.target.value); setPageToken((value) => value + 1); }}
        />
        {!rows.length ? (
          <>
            <span className="rb-toolbar-spacer" />
            <span className="rb-sheet-summary"><span>{t('honorific_empty_hint')}</span></span>
          </>
        ) : null}
      </div>
      </div>
      <DataSheet
        rows={visible}
        getKey={(entry) => entry.row.id}
        selectedKey={selectedKey}
        onSelect={setSelectedKey}
        rowNumber={(entry) => entry.index + 1}
        emptyText={t('honorific_empty')}
        resetPageToken={pageToken}
        label={t('app_honorific_page')}
        readOnly={locked}
        editGeneration={editGeneration}
        onDraftChange={setCellDirty}
        getEditValue={(entry, editKey) => String(entry.row[editKey as keyof HonorificRow] ?? '')}
        onCommitEdit={(rowKey, editKey, value) => {
          const next = rowsRef.current.map((row) => (
            row.id === rowKey ? { ...row, [editKey]: value } : row
          ));
          rowsRef.current = next;
          setRows(next);
          setDirty(true);
        }}
        editRequest={editRequest}
        onEditRequestConsumed={() => setEditRequest(null)}
        columns={[
          { key: 'src', title: t('honorific_title'), width: '36%', editKey: 'src', render: ({ row }) => row.src || <span style={{ color: 'var(--rb-text-secondary)' }}>{t('honorific_placeholder_src')}</span> },
          { key: 'comment', title: t('sheet_note'), editKey: 'comment', render: ({ row }) => row.comment },
        ]}
      />
      {onNextStep ? <NextStepBar label={t('flow_next_onekey')} dirty={unsaved} onNext={onNextStep} /> : null}
    </div>
  );
}
