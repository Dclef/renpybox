/** 术语表：单元格内联编辑，操作与旧 Qt LocalGlossaryPage 对齐。 */
import { useEffect, useRef, useState } from 'react';
import { Button, Checkbox, Dropdown, Input, Progress, Tag } from 'antd';
import { Check, Plus, Search } from 'lucide-react';

import { cancelJob, request } from '../api';
import { DataSheet, type DataSheetEditTarget } from '../components/DataSheet';
import { useT } from '../i18n';
import type { JobSnapshot } from '../types';
import type { AppState } from '../useAppState';
import { Banner, Dialog, NextStepBar, PageHeader } from '../ui';

interface TermRow {
  src: string;
  dst: string;
  info?: string;
  type?: string;
  regex?: boolean;
  case_sensitive?: boolean;
  record_id?: string;
  candidate?: boolean;
  candidate_confirmed?: boolean;
  enabled?: boolean;
  hits?: string;
  [key: string]: unknown;
}
interface GlossarySnapshot {
  storage_key: string;
  revision: number;
  rows: TermRow[];
  enabled: boolean;
  candidate_ids: string[];
}

interface LexiconJobResult {
  project_key?: string;
  message?: string;
  worker_active?: boolean;
  counts?: number[];
  counted_item_total?: number;
  snapshot_keys?: string[];
  kind?: string;
  entries?: TermRow[];
  added?: number;
  updated?: number;
  count_map?: Record<string, number>;
  candidate_ids?: string[];
  warnings?: string[];
  results?: Array<[number, string]>;
  ner_count?: number;
  kw_count?: number;
  output_folder?: string;
  row_snapshots?: TermRow[];
  written?: boolean;
  failed_count?: number;
}

type LexiconJob = JobSnapshot & { cancel_requested?: boolean; result?: LexiconJobResult | null };

function normalizeSrc(text: string): string {
  return text.replace(/\s+/g, ' ').trim().replace(/^["'“”‘’]+|["'“”‘’]+$/g, '').toLowerCase();
}

function displayType(row: TermRow): string {
  const type = String(row.type ?? '').trim();
  if (!row.candidate) return type;
  if (!type || type === '候选') return '候选';
  if (type.startsWith('候选')) return type;
  return `候选 / ${type}`;
}

function noteOf(row: TermRow): string {
  return String(row.info ?? row.comment ?? '');
}

function toApiRow(row: TermRow): TermRow {
  const comment = noteOf(row);
  return {
    ...row,
    src: row.src,
    dst: row.dst,
    type: String(row.type ?? ''),
    comment,
    info: comment,
    case_sensitive: row.case_sensitive === true,
    candidate: row.candidate === true,
    candidate_confirmed: row.candidate_confirmed === true,
    record_id: row.record_id ?? '',
  };
}

function mergeEntries(base: TermRow, incoming: TermRow): TermRow {
  const merged: TermRow = { ...base };
  const inDst = String(incoming.dst ?? '').trim();
  const baseDst = String(merged.dst ?? '').trim();
  const baseSrc = String(merged.src ?? '').trim();
  if (inDst && (!baseDst || (baseSrc && baseDst.toLowerCase() === baseSrc.toLowerCase()))) merged.dst = inDst;
  if (String(incoming.type ?? '').trim() && !String(merged.type ?? '').trim()) merged.type = incoming.type;
  const inComment = noteOf(incoming).trim();
  const baseComment = noteOf(merged).trim();
  if (inComment) {
    if (!baseComment || (inComment.length > baseComment.length && !baseComment.includes(inComment))) {
      merged.info = inComment;
    }
  }
  if (!String(merged.record_id ?? '') && incoming.record_id) {
    merged.record_id = incoming.record_id;
    merged.candidate = incoming.candidate;
    merged.candidate_confirmed = incoming.candidate_confirmed;
  }
  if (incoming.case_sensitive) merged.case_sensitive = true;
  if (incoming.regex) merged.regex = true;
  if (incoming.candidate_confirmed) merged.candidate_confirmed = true;
  return merged;
}

function applyTranslate(rows: TermRow[], results: Array<[number, string]>): { rows: TermRow[]; applied: number } {
  const next = rows.map((row) => ({ ...row }));
  let applied = 0;
  for (const [index, dst] of results) {
    if (index < 0 || index >= next.length) continue;
    const text = String(dst ?? '').trim();
    if (!text) continue;
    const src = String(next[index].src ?? '').trim();
    const current = String(next[index].dst ?? '').trim();
    if (current && current !== src) continue;
    next[index] = { ...next[index], dst: text, candidate_confirmed: next[index].candidate ? true : next[index].candidate_confirmed };
    applied += 1;
  }
  return { rows: next, applied };
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

export function GlossaryPage({ state, onDirtyChange, onNextStep, embedded = false }: { state: AppState; onDirtyChange?: (dirty: boolean) => void; onNextStep?: () => void; embedded?: boolean }) {
  const t = useT();
  const [snapshot, setSnapshot] = useState<GlossarySnapshot | null>(null);
  const [rows, setStoredRows] = useState<TermRow[]>([]);
  const rowsRef = useRef(rows);
  rowsRef.current = rows;
  const generation = useRef(0);
  const [editGeneration, setEditGeneration] = useState(0);
  const [cellDirty, setCellDirty] = useState(false);
  const [appliedJobId, setAppliedJobId] = useState('');
  const taskOwner = useRef<{ id: string; project: string; generation: number } | null>(null);
  const setRows = (next: TermRow[] | ((previous: TermRow[]) => TermRow[])) => {
    const value = typeof next === 'function' ? next(rowsRef.current) : next;
    rowsRef.current = value;
    generation.current += 1;
    setEditGeneration((value) => value + 1);
    setStoredRows(value);
  };
  const [enabled, setEnabled] = useState(false);
  const [dirty, setDirty] = useState(false);
  const dirtyRef = useRef(false);
  dirtyRef.current = dirty || cellDirty;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<number | null>(null);
  const [pageToken, setPageToken] = useState(0);
  const [confirmReload, setConfirmReload] = useState(false);
  const [editRequest, setEditRequest] = useState<DataSheetEditTarget | null>(null);
  const [job, setJob] = useState<LexiconJob | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const excelInput = useRef<HTMLInputElement>(null);
  const jsonInput = useRef<HTMLInputElement>(null);
  const operation = useRef(0);
  const projectRef = useRef('');
  const completedJob = useRef('');
  const statsKeys = useRef<string[]>([]);
  const projectKey = JSON.stringify([state.project?.renpy_project_path, state.project?.renpy_tl_folder, state.settings?.values.renpy_project_path, state.settings?.values.renpy_game_folder, state.settings?.values.renpy_tl_folder, state.settings?.values.input_folder, state.settings?.values.output_folder]);
  projectRef.current = projectKey;
  // 当前草稿所属项目；与 projectKey 不同则草稿只保留在本地供导出，禁止写入新项目
  const [ownerProject, setOwnerProject] = useState('');
  const stale = ownerProject !== projectKey;
  const engineBusy = state.translation.engine_status !== 'IDLE' || state.translation.stop_barrier || state.translation.single_tasks;
  const activeJob = jobRunning(job);
  const locked = busy || engineBusy || activeJob;
  const editLocked = locked || stale;

  useEffect(() => {
    onDirtyChange?.(dirty || cellDirty);
    return () => onDirtyChange?.(false);
  }, [dirty, cellDirty, onDirtyChange]);

  const apply = (next: GlossarySnapshot) => {
    const normalized = next.rows.map((row) => ({
      ...row,
      info: noteOf(row),
      type: String(row.type ?? ''),
      hits: '',
      candidate_confirmed: row.candidate ? row.candidate_confirmed === true : undefined,
    }));
    setSnapshot(next);
    setOwnerProject(projectRef.current);
    setRows(normalized);
    setEnabled(next.enabled);
    setDirty(false);
    setError('');
    setSelected(null);
    statsKeys.current = [];
  };

  const reload = async () => {
    const id = ++operation.current;
    const key = projectRef.current;
    setBusy(true);
    try {
      const next = await request<GlossarySnapshot>('/api/workbench/glossary');
      if (id === operation.current && key === projectRef.current) apply(next);
    } catch (e) {
      if (id === operation.current && key === projectRef.current) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (id === operation.current && key === projectRef.current) setBusy(false);
    }
  };

  useEffect(() => () => { operation.current += 1; }, []);

  useEffect(() => {
    operation.current += 1;
    taskOwner.current = null;
    setJob(null);
    setBusy(false);
    // DataSheet 已在 layout 阶段按 flushKey 把未 blur 的文字提交回 rowsRef，此处 dirtyRef 已包含它
    if (dirtyRef.current) {
      setError('项目已变更，请先导出未保存的词条，再重新载入当前项目。');
      return;
    }
    let alive = true;
    const id = ++operation.current;
    setBusy(true);
    setSnapshot(null);
    request<GlossarySnapshot>('/api/workbench/glossary')
      .then((next) => { if (alive && id === operation.current) apply(next); })
      .catch((e) => { if (alive && id === operation.current) setError(e instanceof Error ? e.message : String(e)); })
      .finally(() => { if (alive && id === operation.current) setBusy(false); });
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
        if (!alive) return;
        if (next?.id === job.id) setJob(next);
        if (!jobRunning(next)) setCancelling(false);
      }).catch(() => undefined);
    }, 800);
    return () => { alive = false; window.clearInterval(timer); };
  }, [activeJob, job?.id]);

  useEffect(() => {
    if (!job || jobRunning(job) || completedJob.current === job.id) return;
    completedJob.current = job.id;
    const result = (job.result && typeof job.result === 'object' ? job.result : {}) as LexiconJobResult;
    // 任务启动时记下的路径快照；项目已切换则丢弃晚到结果。
    const owner = taskOwner.current;
    void state.reloadTranslation();
    if (!owner || owner.id !== job.id || owner.project !== projectRef.current || owner.generation !== generation.current) return;
    setAppliedJobId(job.id);
    taskOwner.current = null;
    if (job.status === 'failed') { setError(job.error || result.message || '任务失败'); return; }
    if (job.status === 'cancelled' && !Array.isArray(result.results) && !result.written) return;
    if (job.kind === 'lexicon_statistics' && result.kind === 'glossary' && Array.isArray(result.counts)) {
      setRows((previous) => {
        const currentKeys = previous.map((row) => `${row.src.replace(/\s+/g, ' ').trim()}|${row.case_sensitive ? 1 : 0}`);
        if (!statsKeys.current.length || currentKeys.join('\0') !== statsKeys.current.join('\0')) {
          state.pushToast('info', '词条已变化，请重新统计命中');
          return previous.map((row) => ({ ...row, hits: '' }));
        }
        state.pushToast('success', `已统计 ${result.counts!.length} 条规则（缓存 ${result.counted_item_total ?? 0} 条）`);
        return previous.map((row, index) => ({
          ...row,
          hits: index < result.counts!.length ? String(Math.max(0, Number(result.counts![index]) || 0)) : '',
        }));
      });
    }
    if ((job.kind === 'lexicon_scan_candidates' || job.kind === 'lexicon_scan_characters') && Array.isArray(result.entries)) {
      setRows(result.entries.map((row) => ({
        ...row,
        info: noteOf(row),
        hits: result.count_map?.[normalizeSrc(String(row.src ?? ''))] != null
          ? String(result.count_map[normalizeSrc(String(row.src ?? ''))])
          : '',
      })));
      if (snapshot && Array.isArray(result.candidate_ids)) {
        setSnapshot({ ...snapshot, candidate_ids: result.candidate_ids, revision: Number((result as LexiconJobResult & { revision?: number }).revision ?? snapshot.revision) });
      }
      setDirty(true);
      state.pushToast('success', result.message || `新增 ${result.added ?? 0}，更新 ${result.updated ?? 0}`);
    }
    if (job.kind === 'lexicon_translate' && Array.isArray(result.results)) {
      setRows((previous) => {
        const applied = applyTranslate(previous, result.results!);
        state.pushToast(applied.applied ? 'success' : 'info', applied.applied ? `已填充 ${applied.applied} 条译文` : '翻译完成但无可写入结果');
        return applied.rows;
      });
      setDirty(true);
    }
  }, [job, snapshot, state]);

  const commitEdit = (rowKey: string, editKey: string, value: string, reason?: 'project-change') => {
    // 项目切换时写锁可能同批变化；旧草稿仍需留在 rowsRef 供导出，写回项目由 stale 保护拦截
    if (locked && reason !== 'project-change') return;
    const index = Number(rowKey);
    const nextRows = rowsRef.current.map((row, i) => {
      if (i !== index) return row;
      const next = { ...row, [editKey]: value };
      if (editKey === 'src') next.hits = '';
      if (row.candidate && ['src', 'dst', 'type', 'info'].includes(editKey)) next.candidate_confirmed = true;
      return next;
    });
    if (editKey === 'src') { nextRows.forEach((row) => { row.hits = ''; }); statsKeys.current = []; }
    rowsRef.current = nextRows;
    generation.current += 1;
    setStoredRows(nextRows);
    setDirty(true);
  };

  const save = async () => {
    if (!snapshot || editLocked) return;
    const id = ++operation.current;
    const key = projectRef.current;
    setBusy(true);
    setError('');
    try {
      const payloadRows = rowsRef.current.filter((row) => row.src.trim()).map(toApiRow);
      const next = await request<GlossarySnapshot>('/api/workbench/glossary', {
        method: 'PATCH',
        body: JSON.stringify({
          storage_key: snapshot.storage_key,
          revision: snapshot.revision,
          candidate_ids: snapshot.candidate_ids,
          rows: payloadRows,
          enabled: payloadRows.length ? true : enabled,
        }),
      });
      if (id !== operation.current || key !== projectRef.current) return;
      apply(next);
      state.pushToast('success', '词库已保存到当前项目');
    } catch (e) {
      if (id === operation.current && key === projectRef.current) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (id === operation.current && key === projectRef.current) setBusy(false);
    }
  };

  const importExcel = async (file?: File) => {
    if (!file || editLocked) return;
    const id = ++operation.current;
    const key = projectRef.current; const version = generation.current;
    setBusy(true);
    try {
      if (file.size > 5 * 1024 * 1024) throw new Error('Excel 文件应小于 5 MB');
      const content_base64 = await fileToBase64(file);
      const result = await request<{ rows: TermRow[]; count: number }>('/api/lexicon/excel/import', {
        method: 'POST',
        body: JSON.stringify({ kind: 'glossary', content_base64, filename: file.name }),
      });
      if (id !== operation.current || key !== projectRef.current || version !== generation.current) return;
      setRows(result.rows.map((row) => ({
        src: String(row.src ?? ''),
        dst: String(row.dst ?? ''),
        type: String(row.type ?? ''),
        info: String(row.comment ?? row.info ?? ''),
        candidate: false,
        hits: '',
      })));
      if (snapshot) setSnapshot({ ...snapshot, candidate_ids: [] });
      setDirty(true);
      setSelected(null);
      setError('');
      state.pushToast('success', `已导入 ${result.count} 个词条（保存后生效）`);
    } catch (e) {
      if (id === operation.current && key === projectRef.current) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (id === operation.current && key === projectRef.current) setBusy(false);
      if (excelInput.current) excelInput.current.value = '';
    }
  };

  const exportExcel = async () => {
    if (!rows.length || locked) return;
    const op = ++operation.current; const owner = projectRef.current; const version = generation.current;
    setBusy(true);
    try {
      const result = await request<{ filename: string; content_base64: string; media_type: string }>('/api/lexicon/excel/export', {
        method: 'POST',
        body: JSON.stringify({ kind: 'glossary', rows: rowsRef.current.map(toApiRow) }),
      });
      if (op !== operation.current || owner !== projectRef.current || version !== generation.current) return;
      downloadBase64(result.filename, result.content_base64, result.media_type);
      state.pushToast('success', '已导出 Excel');
    } catch (e) {
      if (op === operation.current && owner === projectRef.current) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (op === operation.current && owner === projectRef.current) setBusy(false);
    }
  };

  const importJson = async (file?: File) => {
    if (!file || editLocked) return;
    const op = ++operation.current; const owner = projectRef.current; const version = generation.current;
    setBusy(true);
    try {
      if (file.size > 5 * 1024 * 1024) throw new Error('JSON 文件应小于 5 MB');
      const data: unknown = JSON.parse((await file.text()).replace(/^\uFEFF/, ''));
      if (!Array.isArray(data) || data.some((row) => !row || typeof row !== 'object' || typeof (row as TermRow).src !== 'string' || typeof (row as TermRow).dst !== 'string')) {
        throw new Error('文件应为词条数组，每条至少包含字符串 src 和 dst。');
      }
      const incoming = (data as TermRow[]).map((row) => ({
        ...row,
        record_id: '',
        candidate: row.candidate === true,
        candidate_confirmed: false,
        info: noteOf(row),
        type: String(row.type ?? ''),
        hits: '',
      }));
      if (op !== operation.current || owner !== projectRef.current || version !== generation.current) return;
      setRows((previous) => [...previous, ...incoming]);
      setDirty(true);
      state.pushToast('info', `已导入 ${incoming.length} 个词条，保存后生效`);
    } catch (e) {
      if (op === operation.current && owner === projectRef.current) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (op === operation.current && owner === projectRef.current) setBusy(false);
      if (jsonInput.current) jsonInput.current.value = '';
    }
  };

  const exportJson = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(rows.map(toApiRow), null, 2)], { type: 'application/json;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'glossary.json';
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const addRow = () => {
    const index = rows.length;
    setRows((previous) => [...previous, { src: '', dst: '', type: '', info: '', candidate: false, case_sensitive: false, hits: '' }]);
    setSelected(index);
    setQuery('');
    setDirty(true);
    setEditRequest({ rowKey: String(index), columnKey: 'src' });
  };

  const removeSelected = () => {
    if (selected == null) {
      state.pushToast('info', '请先选择要删除的词条');
      return;
    }
    setRows((previous) => previous.filter((_, i) => i !== selected));
    setSelected(null);
    setDirty(true);
  };

  const confirmSelected = () => {
    if (selected == null) {
      state.pushToast('info', '请先选择候选词条');
      return;
    }
    const row = rows[selected];
    if (!row?.candidate || row.candidate_confirmed) {
      state.pushToast('info', '选中项不是待确认候选');
      return;
    }
    setRows((previous) => previous.map((item, i) => (i === selected ? { ...item, candidate_confirmed: true } : item)));
    setDirty(true);
    state.pushToast('success', '已确认候选，补充译文后保存到项目');
  };

  const dedupe = () => {
    const keyIndex = new Map<string, number>();
    const deduped: TermRow[] = [];
    for (const item of rows) {
      const key = normalizeSrc(item.src);
      if (!key) continue;
      const existing = keyIndex.get(key);
      if (existing == null) {
        keyIndex.set(key, deduped.length);
        deduped.push({ ...item });
      } else {
        deduped[existing] = mergeEntries(deduped[existing], item);
      }
    }
    const removed = rows.filter((row) => normalizeSrc(row.src)).length - deduped.length;
    setRows(deduped);
    setSelected(null);
    setDirty(true);
    state.pushToast(removed ? 'success' : 'info', removed ? `已去除 ${removed} 条重复` : '没有重复词条');
  };

  const clearAll = async () => {
    if (!snapshot || editLocked) return;
    if (!window.confirm(t('lexicon_clear_confirm'))) return;
    const id = ++operation.current;
    const key = projectRef.current;
    setBusy(true);
    try {
      const next = await request<GlossarySnapshot>('/api/workbench/glossary', {
        method: 'PATCH',
        body: JSON.stringify({
          storage_key: snapshot.storage_key,
          revision: snapshot.revision,
          candidate_ids: snapshot.candidate_ids,
          rows: [],
          enabled: false,
        }),
      });
      if (id !== operation.current || key !== projectRef.current) return;
      apply(next);
      state.pushToast('success', '已清空术语表');
    } catch (e) {
      if (id === operation.current && key === projectRef.current) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (id === operation.current && key === projectRef.current) setBusy(false);
    }
  };

  const startJob = async (path: string, body: Record<string, unknown>, confirmText?: string) => {
    if (editLocked) return;
    if (cellDirty) { setError('请先按 Enter 提交当前单元格，再启动任务。'); return; }
    if (confirmText && !window.confirm(confirmText)) return;
    const id = ++operation.current;
    const project = projectRef.current;
    const draft = generation.current;
    setBusy(true);
    setError('');
    try {
      const identity = await request<{ project_key: string; output_folder: string }>('/api/lexicon');
      if (id !== operation.current || project !== projectRef.current || draft !== generation.current) return;
      const { job: next } = await request<{ job: LexiconJob }>(path, {
        method: 'POST', body: JSON.stringify({ ...body, project_key: identity.project_key, output_folder: identity.output_folder }),
      });
      if (id !== operation.current || project !== projectRef.current || draft !== generation.current) return;
      taskOwner.current = { id: next.id, project, generation: draft };
      completedJob.current = '';
      setJob(next);
      void state.reloadTranslation();
    } catch (e) {
      if (id === operation.current && project === projectRef.current) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (id === operation.current && project === projectRef.current) setBusy(false);
    }
  };

  const onStatistics = () => {
    const payload = rows.map(toApiRow);
    statsKeys.current = payload.map((row) => `${String(row.src).replace(/\s+/g, ' ').trim()}|${row.case_sensitive ? 1 : 0}`);
    void startJob('/api/lexicon/statistics', {
      kind: 'glossary',
      rows: payload,
    });
  };

  const onClassify = async () => {
    if (editLocked) return;
    const op = ++operation.current; const owner = projectRef.current; const version = generation.current;
    setBusy(true);
    try {
      const result = await request<{ rows: TermRow[]; ner_count: number; kw_count: number }>('/api/lexicon/glossary/classify', {
        method: 'POST',
        body: JSON.stringify({ rows: rowsRef.current.map(toApiRow) }),
      });
      if (op !== operation.current || owner !== projectRef.current || version !== generation.current) return;
      setRows(result.rows.map((row, index) => ({ ...rows[index], ...row, info: noteOf(row), hits: rows[index]?.hits ?? '' })));
      setDirty(true);
      state.pushToast((result.ner_count || result.kw_count) ? 'success' : 'info', `NER ${result.ner_count} · 关键词 ${result.kw_count}`);
    } catch (e) {
      if (op === operation.current && owner === projectRef.current) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (op === operation.current && owner === projectRef.current) setBusy(false);
    }
  };

  const onScanCharacters = () => void startJob('/api/lexicon/glossary/scan-characters', {
    confirm: true, rows: rowsRef.current.map(toApiRow),
  }, '重新扫描会替换旧的自动角色候选，保留手工词条。继续？');

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
      if (job.kind === 'lexicon_translate' && (!result.row_snapshots || result.row_snapshots.length !== rowsRef.current.length || result.row_snapshots.some((row, index) => row.src !== rowsRef.current[index].src || row.dst !== rowsRef.current[index].dst))) {
        setError('词条已变化，请重新翻译；旧任务结果不会覆盖当前稿本。'); return;
      }
      if (job.kind === 'lexicon_statistics') {
        const keys = rowsRef.current.map((row) => `${row.src.replace(/\s+/g, ' ').trim()}|${row.case_sensitive ? 1 : 0}`);
        if (result.kind !== 'glossary' || JSON.stringify(result.snapshot_keys) !== JSON.stringify(keys)) { setError('词条已变化，请重新统计。'); return; }
        statsKeys.current = keys;
      }
      if (!window.confirm('将这次任务结果应用到当前词表草稿，之后保存才生效。继续？')) return;
      taskOwner.current = { id: job.id, project: projectRef.current, generation: generation.current };
      completedJob.current = ''; setJob({ ...job });
    } catch (e) {
      if (id === operation.current && project === projectRef.current) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (id === operation.current && project === projectRef.current) setBusy(false);
    }
  };

  const matched = rows
    .map((row, index) => ({ row, index }))
    .filter(({ row }) => `${row.src} ${row.dst} ${displayType(row)} ${noteOf(row)}`.toLowerCase().includes(query.toLowerCase()));
  const candidateCount = rows.filter((row) => row.candidate).length;
  const emptyText = busy ? '正在读取词库…' : query ? '没有匹配的词条' : '词库为空，新增或导入词条开始整理';
  const jobResult = job?.result && typeof job.result === 'object' ? job.result : null;

  return (
    <div className={embedded ? 'glossary-layout rb-embedded' : 'glossary-layout rb-page'}>
      <div className="rb-page-scroll rb-glossary">
        {embedded ? null : (
          <PageHeader
            title="术语表"
            description="当前项目的专有名词对照。双击或 F2 编辑单元格；保存后翻译优先采用这些译法，未确认候选不会写入正式词库。"
            actions={(
              <>
                <Button disabled={busy || activeJob} onClick={() => (dirty ? setConfirmReload(true) : void reload())}>{t('lexicon_reload')}</Button>
                <Button type="primary" disabled={!snapshot || editLocked || !(dirty || cellDirty)} onClick={() => void save()}>{busy ? t('lexicon_busy') : t('lexicon_save_project')}</Button>
              </>
            )}
          />
        )}
        <div className="rb-lexicon-controls">
        <div className="rb-sheet-summary">{rows.length} 个词条 · {candidateCount} 个候选 · {dirty || cellDirty ? '有未保存修改' : '已与项目同步'}</div>
        {error ? <Banner tone="error">{error}</Banner> : null}
        {engineBusy ? <Banner tone="info">任务执行期间词库只读，结束后可以保存。</Banner> : null}
        {!activeJob && job && appliedJobId !== job.id && job.result?.output_folder === state.settings?.values.output_folder ? <Button onClick={applyRecoveredJob}>应用任务结果</Button> : null}
        {activeJob ? (
          <>
            <Banner tone="info">{cancelling || job?.cancel_requested ? t('lexicon_cancelling') : (jobResult?.message || t('lexicon_job_running'))}</Banner>
            <Progress percent={Math.min(100, 100 * (job?.progress || 0))} aria-label={t('lexicon_job_running')} />
          </>
        ) : null}

        <div className="rb-toolbar">
          <Button disabled={editLocked || !snapshot} onClick={() => excelInput.current?.click()}>{t('lexicon_import_excel')}</Button>
          <Button disabled={locked || !rows.length} onClick={() => void exportExcel()}>{t('lexicon_export_excel')}</Button>
          {embedded ? (
            <>
              <Button disabled={busy || activeJob} onClick={() => (dirty ? setConfirmReload(true) : void reload())}>{t('lexicon_reload')}</Button>
              <Button type="primary" disabled={!snapshot || editLocked || !(dirty || cellDirty)} onClick={() => void save()}>{busy ? t('lexicon_busy') : t('lexicon_save_project')}</Button>
            </>
          ) : null}
          <Button disabled={editLocked || !rows.length} onClick={onStatistics}>{t('lexicon_count_hits')}</Button>
          <span className="rb-toolbar-spacer" />
          <Checkbox checked={enabled} disabled={editLocked || !snapshot} onChange={(event) => { setEnabled(event.target.checked); setDirty(true); }}>{t('lexicon_enable_glossary')}</Checkbox>
        </div>

        <div className="rb-toolbar">
          <Button disabled={editLocked || !snapshot} icon={<Plus size={16} strokeWidth={1.75} />} onClick={addRow}>{t('lexicon_add')}</Button>
          <Button disabled={editLocked || selected == null} onClick={confirmSelected}>{t('lexicon_confirm_selected')}</Button>
          <Button disabled={editLocked || selected == null} onClick={removeSelected}>{t('lexicon_delete_selected')}</Button>
          <Button disabled={editLocked || !rows.length} onClick={dedupe}>{t('lexicon_deduplicate')}</Button>
          <Button disabled={editLocked || !rows.length} onClick={onClassify}>{t('lexicon_auto_classify')}</Button>
          <Button danger type="text" disabled={editLocked || !snapshot} onClick={() => void clearAll()}>{t('lexicon_clear')}</Button>
        </div>

        <div className="rb-toolbar">
          <Button disabled={editLocked || !snapshot} onClick={() => void startJob('/api/lexicon/glossary/scan-candidates', {
            confirm: true,
            rows: rowsRef.current.map(toApiRow),
          }, t('lexicon_scan_candidates_confirm'))}>{t('lexicon_scan_candidates')}</Button>
          <Button disabled={!activeJob || cancelling || Boolean(job?.cancel_requested)} onClick={() => {
            if (!job) return;
            setCancelling(true);
            void cancelJob(job.id).catch((e) => setError(e instanceof Error ? e.message : String(e)));
          }}>{t('lexicon_stop_scan')}</Button>
          <Button disabled={editLocked || !snapshot} onClick={() => void onScanCharacters()}>{t('lexicon_scan_characters')}</Button>
          <Button disabled={editLocked || !rows.length} onClick={() => {
            const tasks = rowsRef.current.filter((row) => row.src.trim() && (!row.dst.trim() || row.dst.trim() === row.src.trim())).length;
            void startJob('/api/lexicon/glossary/translate', {
              mode: 'llm',
              rows: rowsRef.current.map(toApiRow),
              confirm: true,
            }, t('lexicon_translate_llm_confirm').replace('{count}', String(tasks)));
          }}>{t('lexicon_translate_llm')}</Button>
          <Button disabled={editLocked || !rows.length} onClick={() => {
            const tasks = rowsRef.current.filter((row) => row.src.trim() && (!row.dst.trim() || row.dst.trim() === row.src.trim())).length;
            void startJob('/api/lexicon/glossary/translate', {
              mode: 'fast',
              engine: 'bing',
              rows: rowsRef.current.map(toApiRow),
              confirm: true,
            }, t('lexicon_translate_fast_confirm').replace('{count}', String(tasks)));
          }}>{t('lexicon_translate_fast')}</Button>
          <Dropdown
            menu={{
              items: [
                { key: 'import-json', label: t('lexicon_import_json'), disabled: editLocked || !snapshot, onClick: () => jsonInput.current?.click() },
                { key: 'export-json', label: t('lexicon_export_json'), disabled: rows.length === 0, onClick: exportJson },
              ],
            }}
            trigger={['click']}
          >
            <Button>{t('lexicon_more')}</Button>
          </Dropdown>
        </div>

        <div className="rb-toolbar">
          <Input style={{ width: 280 }} aria-label={t('lexicon_search_glossary')} placeholder={t('lexicon_search_glossary_placeholder')} value={query} prefix={<Search size={16} strokeWidth={1.75} />} onChange={(event) => { setQuery(event.target.value); setPageToken((value) => value + 1); }} />
        </div>
        </div>

        <input ref={excelInput} type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" hidden onChange={(e) => void importExcel(e.target.files?.[0])} />
        <input ref={jsonInput} type="file" accept=".json,application/json" hidden onChange={(e) => void importJson(e.target.files?.[0])} />

        <DataSheet
          rows={matched}
          getKey={(entry) => String(entry.index)}
          selectedKey={selected == null ? null : String(selected)}
          onSelect={(key) => setSelected(key == null ? null : Number(key))}
          rowNumber={(entry) => entry.index + 1}
          emptyText={emptyText}
          footer={`${matched.length} 条`}
          resetPageToken={pageToken}
          label={t('app_glossary_page')}
          readOnly={editLocked}
          editGeneration={editGeneration}
          flushKey={projectKey}
          onDraftChange={(value) => { setCellDirty(value); if (value) generation.current += 1; }}
          getEditValue={(entry, editKey) => String((entry.row as TermRow)[editKey] ?? '')}
          onCommitEdit={commitEdit}
          editRequest={editRequest}
          onEditRequestConsumed={() => setEditRequest(null)}
          columns={[
            { key: 'src', title: t('sheet_src'), width: '22%', editKey: 'src', render: ({ row }) => row.src },
            { key: 'dst', title: t('sheet_dst'), width: '22%', editKey: 'dst', render: ({ row }) => row.dst },
            { key: 'type', title: t('sheet_category'), width: '14%', editKey: 'type', render: ({ row }) => (
              <span className="rb-term-marks">
                {displayType(row)}
                {row.candidate ? <Tag>{row.candidate_confirmed ? <Check size={12} strokeWidth={1.75} /> : null}{t('lexicon_candidate')}</Tag> : null}
                <Checkbox aria-label={t('lexicon_case_sensitive')} checked={row.case_sensitive === true} disabled={editLocked} onClick={(event) => event.stopPropagation()} onChange={(event) => {
                  const checked = event.target.checked;
                  setRows((previous) => previous.map((item) => item === row ? { ...item, case_sensitive: checked, hits: '' } : item));
                  setDirty(true);
                }} />
              </span>
            ) },
            { key: 'info', title: t('sheet_note'), editKey: 'info', render: ({ row }) => noteOf(row) },
            { key: 'hits', title: t('sheet_hits'), width: '72px', render: ({ row }) => row.hits || '' },
          ]}
        />
        {onNextStep ? <NextStepBar label={t('flow_next_preserve')} dirty={dirty || cellDirty} onNext={onNextStep} /> : null}
      </div>
      {confirmReload ? (
        <Dialog title={t('lexicon_reload_title')} confirmText={t('lexicon_reload')} onCancel={() => setConfirmReload(false)} onConfirm={() => { setConfirmReload(false); void reload(); }}>
          {t('lexicon_reload_body')}
        </Dialog>
      ) : null}
    </div>
  );
}
