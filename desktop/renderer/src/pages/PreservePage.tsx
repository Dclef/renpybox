/** 禁翻表：单元格内联编辑，操作与旧 Qt TextPreservePage 对齐。 */
import { useEffect, useRef, useState } from 'react';
import { Button, Checkbox, Input } from 'antd';
import { Plus, Search } from 'lucide-react';

import { cancelJob, request } from '../api';
import { DataSheet, type DataSheetEditTarget } from '../components/DataSheet';
import type { JobSnapshot } from '../types';
import type { AppState } from '../useAppState';
import { useT } from '../i18n';
import { Banner, NextStepBar } from '../ui';

interface PreserveRow {
  src: string;
  comment: string;
  hits?: string;
}

interface LexiconJobResult {
  project_key?: string;
  message?: string;
  worker_active?: boolean;
  counts?: number[];
  counted_item_total?: number;
  kind?: string;
  rows?: PreserveRow[];
  enabled?: boolean;
  written?: boolean;
  output_folder?: string;
  snapshot_keys?: string[];
}

type LexiconJob = JobSnapshot & { cancel_requested?: boolean; result?: LexiconJobResult | null };

function readRows(value: unknown): PreserveRow[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => {
    if (typeof item === 'string') return { src: item, comment: '', hits: '' };
    if (!item || typeof item !== 'object') return { src: '', comment: '', hits: '' };
    const row = item as { src?: unknown; comment?: unknown; info?: unknown };
    return {
      src: String(row.src ?? ''),
      comment: String(row.comment ?? row.info ?? ''),
      hits: '',
    };
  });
}

function normalizeSrc(text: string): string {
  return text.trim().replace(/^["'“”‘’]+|["'“”‘’]+$/g, '').toLowerCase();
}

function jobRunning(job: LexiconJob | null): boolean {
  const result = job?.result && typeof job.result === 'object' ? job.result : null;
  return Boolean(job && (job.status === 'pending' || job.status === 'running' || result?.worker_active));
}

function downloadBase64(filename: string, contentBase64: string, mediaType: string) {
  const binary = atob(contentBase64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  const url = URL.createObjectURL(new Blob([bytes], { type: mediaType }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function fileToBase64(file: File): Promise<string> {
  const buffer = await file.arrayBuffer();
  let binary = '';
  const bytes = new Uint8Array(buffer);
  for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i]);
  return btoa(binary);
}

export function PreservePage(props: { state: AppState; onDirtyChange?: (dirty: boolean) => void; onNextStep?: () => void }) {
  const { state, onDirtyChange, onNextStep } = props;
  const t = useT();
  const stored = state.settings?.values.text_preserve_data;
  const [rows, setStoredRows] = useState<PreserveRow[]>(() => readRows(stored));
  const rowsRef = useRef(rows); rowsRef.current = rows;
  const generation = useRef(0);
  const [editGeneration, setEditGeneration] = useState(0);
  const [cellDirty, setCellDirty] = useState(false);
  const operation = useRef(0);
  const projectKey = JSON.stringify([state.project?.renpy_project_path, state.project?.renpy_tl_folder, state.settings?.values.renpy_project_path, state.settings?.values.renpy_game_folder, state.settings?.values.renpy_tl_folder, state.settings?.values.input_folder, state.settings?.values.output_folder]);
  const projectRef = useRef(projectKey); projectRef.current = projectKey;
  // 规则本身是全局设置；owner 只标记草稿在哪个项目身份下编辑，防止切换后晚到的旧草稿被保存进新项目
  const [ownerProject, setOwnerProject] = useState(projectKey);
  const stale = ownerProject !== projectKey;
  const [appliedJobId, setAppliedJobId] = useState('');
  const taskOwner = useRef<{ id: string; project: string; generation: number } | null>(null);
  const setRows = (next: PreserveRow[] | ((previous: PreserveRow[]) => PreserveRow[])) => {
    const value = typeof next === 'function' ? next(rowsRef.current) : next;
    rowsRef.current = value; generation.current += 1;
    setEditGeneration((value) => value + 1); setStoredRows(value);
  };
  const [enabled, setEnabled] = useState(state.settings?.values.text_preserve_enable === true);
  const [dirty, setDirty] = useState(false);
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<number | null>(null);
  const [pageToken, setPageToken] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [editRequest, setEditRequest] = useState<DataSheetEditTarget | null>(null);
  const [job, setJob] = useState<LexiconJob | null>(null);
  const excelInput = useRef<HTMLInputElement>(null);
  const completedJob = useRef('');
  const statsKeys = useRef<string[]>([]);
  const engineBusy = state.saving || state.translation.engine_status !== 'IDLE' || state.translation.stop_barrier || state.translation.single_tasks;
  const activeJob = jobRunning(job);
  const locked = busy || engineBusy || activeJob;
  // stale 期间只允许导出 Excel 与“加载设置”；加载按钮只看 locked，不被 stale 禁用
  const editLocked = locked || stale;

  useEffect(() => {
    // 有草稿（含 flush 回来的未 blur 文字）时不覆盖，owner 保持旧项目
    if (dirty || cellDirty) return;
    setRows(readRows(state.settings?.values.text_preserve_data));
    setEnabled(state.settings?.values.text_preserve_enable === true);
    setOwnerProject(projectKey);
  }, [dirty, cellDirty, projectKey, state.settings?.values.text_preserve_data, state.settings?.values.text_preserve_enable]);

  useEffect(() => {
    onDirtyChange?.(dirty || cellDirty);
    return () => onDirtyChange?.(false);
  }, [dirty, cellDirty, onDirtyChange]);

  useEffect(() => {
    let alive = true;
    operation.current += 1; taskOwner.current = null; setJob(null); setBusy(false);
    request<{ job: LexiconJob | null }>('/api/lexicon')
      .then(({ job: next }) => { if (alive) setJob(next); })
      .catch(() => undefined);
    return () => { alive = false; operation.current += 1; };
  }, [projectKey]);

  useEffect(() => {
    if (!activeJob || !job) return;
    let alive = true;
    const timer = window.setInterval(() => {
      void request<{ job: LexiconJob | null }>('/api/lexicon').then(({ job: next }) => {
        if (alive && next?.id === job.id) setJob(next);
      }).catch(() => undefined);
    }, 800);
    return () => { alive = false; window.clearInterval(timer); };
  }, [activeJob, job?.id]);

  useEffect(() => {
    if (!job || jobRunning(job) || completedJob.current === job.id) return;
    completedJob.current = job.id;
    const result = (job.result && typeof job.result === 'object' ? job.result : {}) as LexiconJobResult;
    const owner = taskOwner.current;
    void state.reloadTranslation();
    if (!owner || owner.id !== job.id || owner.project !== projectRef.current || owner.generation !== generation.current) return;
    setAppliedJobId(job.id);
    taskOwner.current = null;
    if (job.status === 'failed') { setError(job.error || result.message || '任务失败'); return; }
    if (job.kind === 'lexicon_preserve_rescan' && result.written && Array.isArray(result.rows)) {
      setRows(readRows(result.rows)); setEnabled(result.enabled === true); setDirty(false); setSelected(null);
      void state.reloadSettings(); state.pushToast('success', result.message || '重扫完成'); return;
    }
    if (job.status !== 'done' || job.kind !== 'lexicon_statistics' || result.kind !== 'preserve' || !Array.isArray(result.counts)) return;
    const currentKeys = rows.map((row) => normalizeSrc(row.src));
    if (!statsKeys.current.length || currentKeys.join('\0') !== statsKeys.current.join('\0')) {
      setRows((previous) => previous.map((row) => ({ ...row, hits: '' })));
      state.pushToast('info', '条目已变化，请重新统计命中');
      return;
    }
    setRows((previous) => previous.map((row, index) => ({
      ...row,
      hits: index < result.counts!.length ? String(Math.max(0, Number(result.counts![index]) || 0)) : '',
    })));
    state.pushToast('success', `已统计 ${result.counts.length} 条规则（缓存 ${result.counted_item_total ?? 0} 条）`);
  }, [job, rows, state]);

  const applyRecoveredJob = async () => {
    const result = job?.result;
    if (!job || editLocked || !result || result.output_folder !== state.settings?.values.output_folder) return;
    if (cellDirty) { setError('请先按 Enter 提交当前单元格，再应用任务结果。'); return; }
    const id = ++operation.current; const project = projectRef.current; const version = generation.current;
    setBusy(true);
    try {
      const identity = await request<{ project_key: string; output_folder: string }>('/api/lexicon');
      if (id !== operation.current || project !== projectRef.current || version !== generation.current) return;
      if (result.project_key !== identity.project_key || result.output_folder !== identity.output_folder) {
        setError('项目已变化，旧任务结果不会覆盖当前稿本。'); return;
      }
      if (job.kind === 'lexicon_statistics') {
        const keys = rowsRef.current.map((row) => normalizeSrc(row.src));
        if (result.kind !== 'preserve' || JSON.stringify(result.snapshot_keys) !== JSON.stringify(keys)) { setError('规则已变化，请重新统计。'); return; }
        statsKeys.current = keys;
      } else if (job.kind !== 'lexicon_preserve_rescan' || !result.written) return;
      if (!window.confirm('将这次任务结果载入当前禁翻表。继续？')) return;
      taskOwner.current = { id: job.id, project: projectRef.current, generation: generation.current };
      completedJob.current = ''; setJob({ ...job });
    } catch (e) {
      if (id === operation.current && project === projectRef.current) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (id === operation.current && project === projectRef.current) setBusy(false);
    }
  };

  const visible = rows
    .map((row, index) => ({ row, index }))
    .filter(({ row }) => `${row.src} ${row.comment}`.toLowerCase().includes(query.toLowerCase()));

  const save = async () => {
    if (editLocked) return;
    const id = ++operation.current; const project = projectRef.current;
    const cleaned = rowsRef.current.map((row) => ({ src: row.src.trim(), comment: row.comment.trim(), info: row.comment.trim() })).filter((row) => row.src);
    const nextEnabled = cleaned.length ? true : enabled;
    if (!await state.saveSettings({ text_preserve_data: cleaned, text_preserve_enable: nextEnabled })) return;
    if (id !== operation.current || project !== projectRef.current) return;
    setRows(cleaned.map((row) => ({ ...row, hits: '' })));
    setEnabled(nextEnabled);
    setSelected(null);
    setDirty(false);
    state.pushToast('success', `已保存 ${cleaned.length} 条禁翻规则`);
  };

  const reload = async () => {
    if ((dirty || cellDirty) && !window.confirm(t('rules_reload_confirm'))) return;
    const id = ++operation.current; const project = projectRef.current;
    setBusy(true);
    try {
      await state.reloadSettings();
      if (id !== operation.current || project !== projectRef.current) return;
      // 明确放弃旧草稿：dirty 清除后同步 effect 按最新设置重建行数据，owner 归当前项目
      setDirty(false);
      setOwnerProject(project);
      setSelected(null);
      setError('');
    } catch (e) { if (id === operation.current && project === projectRef.current) setError(String(e)); }
    finally { if (id === operation.current && project === projectRef.current) setBusy(false); }
  };

  const deduplicate = () => {
    if (editLocked) return;
    const unique = new Map<string, PreserveRow>();
    for (const row of rows) {
      const src = row.src.trim();
      if (!src) continue;
      const key = normalizeSrc(src);
      const previous = unique.get(key);
      unique.set(key, previous
        ? { ...previous, comment: row.comment.trim().length > previous.comment.length ? row.comment.trim() : previous.comment }
        : { src, comment: row.comment.trim(), hits: '' });
    }
    const removed = rows.filter((row) => row.src.trim()).length - unique.size;
    setRows([...unique.values()]);
    setSelected(null);
    setDirty(true);
    state.pushToast(removed ? 'success' : 'info', removed ? `已去除 ${removed} 条重复` : '没有重复条目');
  };

  const clearAll = async () => {
    if (editLocked || !window.confirm(t('lexicon_clear_confirm'))) return;
    const id = ++operation.current; const project = projectRef.current;
    if (!await state.saveSettings({ text_preserve_data: [], text_preserve_enable: false })) return;
    if (id !== operation.current || project !== projectRef.current) return;
    setRows([]);
    setEnabled(false);
    setSelected(null);
    setDirty(false);
    state.pushToast('success', '已清空禁翻表');
  };

  const addRow = () => {
    if (editLocked) return;
    const index = rows.length;
    setRows((previous) => [...previous, { src: '', comment: '', hits: '' }]);
    setQuery('');
    setSelected(index);
    setDirty(true);
    setEditRequest({ rowKey: String(index), columnKey: 'src' });
  };

  const removeSelected = () => {
    if (editLocked) return;
    if (selected == null) {
      state.pushToast('info', '请先选择要删除的条目');
      return;
    }
    setRows((previous) => previous.filter((_, i) => i !== selected));
    setSelected(null);
    setDirty(true);
  };

  const importExcel = async (file?: File) => {
    if (!file || editLocked) return;
    const id = ++operation.current; const project = projectRef.current; const version = generation.current;
    setBusy(true);
    try {
      if (file.size > 5 * 1024 * 1024) throw new Error('Excel 文件应小于 5 MB');
      const content_base64 = await fileToBase64(file);
      const result = await request<{ rows: PreserveRow[]; count: number }>('/api/lexicon/excel/import', {
        method: 'POST',
        body: JSON.stringify({ kind: 'preserve', content_base64, filename: file.name }),
      });
      if (id !== operation.current || project !== projectRef.current || version !== generation.current) return;
      setRows(result.rows.map((row) => ({ src: String(row.src ?? ''), comment: String(row.comment ?? ''), hits: '' })));
      setDirty(true);
      setSelected(null);
      setError('');
      state.pushToast('success', `已导入 ${result.count} 条（保存后生效）`);
    } catch (e) {
      if (id === operation.current && project === projectRef.current) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (id === operation.current && project === projectRef.current) setBusy(false);
      if (excelInput.current) excelInput.current.value = '';
    }
  };

  const exportExcel = async () => {
    if (!rows.length || locked) return;
    const id = ++operation.current; const project = projectRef.current; const version = generation.current;
    setBusy(true);
    try {
      const result = await request<{ filename: string; content_base64: string; media_type: string }>('/api/lexicon/excel/export', {
        method: 'POST',
        body: JSON.stringify({
          kind: 'preserve',
          rows: rows.map((row) => ({ src: row.src, comment: row.comment, info: row.comment })),
        }),
      });
      if (id !== operation.current || project !== projectRef.current || version !== generation.current) return;
      downloadBase64(result.filename, result.content_base64, result.media_type);
      state.pushToast('success', '已导出 Excel');
    } catch (e) {
      if (id === operation.current && project === projectRef.current) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (id === operation.current && project === projectRef.current) setBusy(false);
    }
  };

  const startJob = async (path: string, body: Record<string, unknown>) => {
    if (editLocked) return;
    if (cellDirty) { setError('请先按 Enter 提交当前单元格，再启动任务。'); return; }
    const id = ++operation.current; const project = projectRef.current; const version = generation.current;
    setBusy(true); setError('');
    try {
      const identity = await request<{ project_key: string; output_folder: string }>('/api/lexicon');
      if (id !== operation.current || project !== projectRef.current || version !== generation.current) return;
      const { job: next } = await request<{ job: LexiconJob }>(path, {
        method: 'POST', body: JSON.stringify({ ...body, project_key: identity.project_key, output_folder: identity.output_folder }),
      });
      if (id !== operation.current || project !== projectRef.current || version !== generation.current) return;
      taskOwner.current = { id: next.id, project, generation: version };
      completedJob.current = ''; setJob(next); void state.reloadTranslation();
    } catch (e) { if (id === operation.current && project === projectRef.current) setError(String(e)); }
    finally { if (id === operation.current && project === projectRef.current) setBusy(false); }
  };

  const onStatistics = () => {
    const payload = rowsRef.current.map((row) => ({ src: row.src, comment: row.comment }));
    statsKeys.current = payload.map((row) => normalizeSrc(row.src));
    void startJob('/api/lexicon/statistics', { kind: 'preserve', rows: payload });
  };

  const onRescan = () => {
    if (editLocked || !window.confirm(t('lexicon_rescan_variables_confirm'))) return;
    void startJob('/api/lexicon/preserve/rescan-variables', { confirm: true });
  };

  return (
    <div className="rb-embedded rb-lexicon">
      <div className="rb-lexicon-controls">
      {!activeJob && job && appliedJobId !== job.id && job.result?.output_folder === state.settings?.values.output_folder ? <Button disabled={editLocked} onClick={applyRecoveredJob}>应用任务结果</Button> : null}
      {error ? <Banner tone="error">{error}</Banner> : null}
      {stale ? <Banner tone="warning">项目已变更：当前草稿是在之前的项目下编辑的，不会保存到当前项目。可先导出 Excel，再点“加载设置”放弃草稿后继续编辑。</Banner> : null}
      {engineBusy && state.translation.engine_status !== 'IDLE' ? <Banner tone="info">任务执行期间只读，结束后再保存。</Banner> : null}
      <div className="rb-toolbar">
        <div className="rb-sheet-summary">
          <strong>{rows.length} 条规则</strong>
          <span>{dirty || cellDirty ? '有未保存修改' : enabled ? '翻译时会套用' : '当前未启用'}</span>
        </div>
        <span className="rb-toolbar-spacer" />
        <Button disabled={editLocked} onClick={() => excelInput.current?.click()}>{t('lexicon_import_excel')}</Button>
        <Button disabled={locked || !rows.length} onClick={() => void exportExcel()}>{t('lexicon_export_excel')}</Button>
        <Button disabled={locked} onClick={() => void reload()}>{t('lexicon_load_settings')}</Button>
        <Button type="primary" disabled={editLocked || !(dirty || cellDirty)} onClick={() => void save()}>{state.saving ? t('lexicon_busy') : t('lexicon_save_settings')}</Button>
      </div>
      <div className="rb-toolbar">
        <Button disabled={editLocked} icon={<Plus size={16} strokeWidth={1.75} />} onClick={addRow}>{t('lexicon_add')}</Button>
        <Button disabled={editLocked || selected == null} onClick={removeSelected}>{t('lexicon_delete_selected')}</Button>
        <Button disabled={editLocked || !rows.length} onClick={deduplicate}>{t('rules_deduplicate')}</Button>
        <Button danger type="text" disabled={editLocked || !rows.length} onClick={() => void clearAll()}>{t('lexicon_clear')}</Button>
        <Button disabled={editLocked || !rows.length} onClick={() => void onStatistics()}>{t('lexicon_count_hits')}</Button>
        <Button disabled={editLocked} onClick={() => void onRescan()}>{t('lexicon_rescan_variables')}</Button>
        {activeJob && job ? (
          <Button disabled={Boolean(job.cancel_requested)} onClick={() => void cancelJob(job.id)}>{t('lexicon_stop_scan')}</Button>
        ) : null}
      </div>
      <div className="rb-toolbar">
        <Input style={{ width: 280 }} aria-label={t('lexicon_search_preserve')} placeholder={t('lexicon_search_preserve_placeholder')} value={query} prefix={<Search size={16} strokeWidth={1.75} />} onChange={(event) => { setQuery(event.target.value); setPageToken((value) => value + 1); }} />
        <Checkbox checked={enabled} disabled={editLocked} onChange={(event) => { setEnabled(event.target.checked); setDirty(true); }}>{t('lexicon_enable_preserve')}</Checkbox>
      </div>
      </div>
      <input ref={excelInput} type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" hidden onChange={(e) => void importExcel(e.target.files?.[0])} />
      <DataSheet
        rows={visible}
        getKey={(entry) => String(entry.index)}
        selectedKey={selected == null ? null : String(selected)}
        onSelect={(key) => setSelected(key == null ? null : Number(key))}
        rowNumber={(entry) => entry.index + 1}
        emptyText={query ? '没有匹配的规则' : '还没有禁翻规则'}
        resetPageToken={pageToken}
        label={t('app_text_preserve_page')}
        readOnly={editLocked}
        editGeneration={editGeneration}
        flushKey={projectKey}
        onDraftChange={(value) => { setCellDirty(value); if (value) generation.current += 1; }}
        getEditValue={(entry, editKey) => String((entry.row as PreserveRow)[editKey as keyof PreserveRow] ?? '')}
        onCommitEdit={(rowKey, editKey, value, reason) => {
          // 项目切换时写锁可能同批变化；只把旧草稿留在本地 rowsRef，保存仍受 editLocked（含 stale）约束
          if (editLocked && reason !== 'project-change') return;
          const index = Number(rowKey);
          const nextRows = rowsRef.current.map((item, i) => {
            if (i !== index) return item;
            return { ...item, [editKey]: value, hits: editKey === 'src' ? '' : item.hits };
          });
          if (editKey === 'src') { nextRows.forEach((row) => { row.hits = ''; }); statsKeys.current = []; }
          rowsRef.current = nextRows; generation.current += 1; setStoredRows(nextRows); setDirty(true);
        }}
        editRequest={editRequest}
        onEditRequestConsumed={() => setEditRequest(null)}
        columns={[
          { key: 'src', title: t('sheet_src'), width: '46%', editKey: 'src', render: ({ row }) => row.src },
          { key: 'comment', title: t('sheet_note'), editKey: 'comment', render: ({ row }) => row.comment },
          { key: 'hits', title: t('sheet_hits'), width: '72px', render: ({ row }) => row.hits || '' },
        ]}
      />
      {onNextStep ? <NextStepBar label={t('flow_next_honorific')} dirty={dirty || cellDirty} onNext={onNextStep} /> : null}
    </div>
  );
}
