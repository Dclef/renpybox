/** 平行校对台：分页读取真实缓存，保存前由服务端检查项目和译文版本。 */
import { useEffect, useRef, useState } from 'react';
import { request } from '../api';
import type { AppState } from '../useAppState';
import { ActionIcon, Button, Checkbox, Loader, Menu, Modal, NumberInput, Portal, Progress, Select, Table, Textarea, TextInput } from '@mantine/core';
import { MoreHorizontal, AlertTriangle, Copy, Pencil, RotateCcw } from 'lucide-react';
import type { MouseEvent, KeyboardEvent } from 'react';
import { Banner, Dialog, PageHeader } from '../ui';
import { useT } from '../i18n';

interface ProofreadingRow {
  id: number;
  version: string;
  src: string;
  dst: string;
  status: string;
  file_path: string;
  row: number;
  warnings?: string[];
}

interface QualityReport {
  task_type: string;
  state: string;
  total_count: number;
  completed_count: number;
  updated_count: number;
  failed_count: number;
  skipped_count: number;
  error_message?: string;
  failures?: { item_index: number; reason: string; attempts: number }[];
}

interface ProofreadingData {
  cache_token: string;
  cache_folder: string;
  total: number;
  matched: number;
  page: number;
  limit: number;
  files: string[];
  readonly: boolean;
  quality_reports?: QualityReport[];
  scan_complete?: boolean;
  checked?: number;
  check_total?: number;
  items: ProofreadingRow[];
}

const WARNING_LABELS: Record<string, string> = {
  KANA: '假名残留', HANGEUL: '韩文残留', TEXT_PRESERVE: '文本保护失效',
  SIMILARITY: '原译相似度过高', GLOSSARY: '术语未生效', RETRY_THRESHOLD: '重试次数达阈值',
};

interface TranslationReport {
  failed_count: number;
  fallback_count: number;
  line_mismatch_count: number;
  error_type_counts: Record<string, number>;
  item_references: { item_index: number; reference: string; source_preview: string; error_types: string[] }[];
}

const STATUS_LABELS: Record<string, string> = {
  UNTRANSLATED: '待翻译', TRANSLATED: '已翻译', POLISHED: '已润色',
  TRANSLATED_IN_PAST: '已有译文', EXCLUDED: '已排除', DUPLICATED: '重复',
};

export function ProofreadingPage({ state, onDirtyChange, embedded = false }: {
  state: AppState;
  onDirtyChange?: (dirty: boolean) => void;
  embedded?: boolean;
}) {
  const t = useT();
  const [qualityConfirm, setQualityConfirm] = useState<{ task: 'polish' | 'proofread'; cache_token: string; ids: number[]; rows?: ProofreadingRow[]; project: string } | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [data, setData] = useState<ProofreadingData | null>(null);
  const [query, setQuery] = useState('');
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [file, setFile] = useState('');
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(50);
  const [onlyIssues, setOnlyIssues] = useState(false);
  const [warning, setWarning] = useState('');
  const [active, setActive] = useState<number | null>(null);
  const selectionAnchor = useRef<number | null>(null);
  const [contextMenu, setContextMenu] = useState<{ row: ProofreadingRow; x: number; y: number } | null>(null);
  const [selectionConfirm, setSelectionConfirm] = useState<{ action: 'reset' | 'confirm' | 'retranslate'; cache_token: string; rows: ProofreadingRow[]; project: string } | null>(null);
  const [exportConfirm, setExportConfirm] = useState<{ cache_token: string; project: string } | null>(null);
  const [reportOpen, setReportOpen] = useState(false);
  const [report, setReport] = useState<TranslationReport | null>(null);
  const [reportError, setReportError] = useState('');
  const [retranslate, setRetranslate] = useState<{ state: string; total?: number; done?: number; updated?: number; failed?: number; error?: string }>({ state: 'IDLE' });
  const retranslateRunning = ['RUNNING', 'CANCELLING'].includes(retranslate.state);
  const [locationOpen, setLocationOpen] = useState(false);
  const [location, setLocation] = useState<{ path: string; row: number; lines: { number: number; text: string }[] } | null>(null);
  const [locationError, setLocationError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [edit, setEdit] = useState<(ProofreadingRow & { cache_token: string; project_identity: string }) | null>(null);
  const [draft, setDraft] = useState('');
  const [replaceOpen, setReplaceOpen] = useState(false);
  const [replaceSnapshot, setReplaceSnapshot] = useState<{ cache_token: string; rows: ProofreadingRow[] } | null>(null);
  const [find, setFind] = useState('');
  const [replacement, setReplacement] = useState('');
  const [caseSensitive, setCaseSensitive] = useState(true);
  const [reportSelection, setReportSelection] = useState<Set<number>>(new Set());
  const requestId = useRef(0);
  const projectRef = useRef('');
  const dirtyRef = useRef(false);
  const projectIdentity = JSON.stringify([
    state.project?.renpy_project_path, state.project?.renpy_game_folder, state.project?.renpy_tl_folder,
    state.settings?.values.input_folder, state.settings?.values.output_folder,
  ]);
  projectRef.current = projectIdentity;
  const editProjectChanged = Boolean(edit && edit.project_identity !== projectIdentity);
  const readonly = data?.readonly || retranslateRunning || state.translation.engine_status !== 'IDLE'
    || state.translation.stop_barrier || state.translation.single_tasks;
  const qualityTask = state.translation.progress.quality_task as Record<string, unknown> | undefined;
  const qualityRunning = state.translation.engine_status === 'QUALITY'
    || qualityTask?.state === 'RUNNING';
  const dirty = Boolean(edit && draft !== edit.dst);
  dirtyRef.current = dirty;

  useEffect(() => {
    onDirtyChange?.(dirty);
    return () => onDirtyChange?.(false);
  }, [dirty, onDirtyChange]);

  useEffect(() => {
    setData(null);
    setSelected(new Set());
    if (!dirtyRef.current) setEdit(null);
    setReplaceOpen(false);
    setQualityConfirm(null);
    setSelectionConfirm(null);
    setExportConfirm(null);
    setReportOpen(false);
    setReport(null);
    setActive(null);
    setContextMenu(null);
    setLocationOpen(false);
    setLocation(null);
    selectionAnchor.current = null;
    setPage(1);
    setFile('');
  }, [projectIdentity]);

  // 返回页面或重连时补取状态，避免漏掉质量任务事件后一直只读。
  useEffect(() => {
    if (state.ready && state.link === 'open') void state.reloadTranslation().catch(() => undefined);
  }, [state.ready, state.link, state.reloadTranslation]);

  useEffect(() => state.subscribe((event) => {
    if (['TRANSLATION_DONE', 'PROJECT_STATUS_CHECK_DONE'].includes(event.event)) {
      setRefresh((value) => value + 1);
    }
    if (event.event === 'TRANSLATION_UPDATE' && event.data.quality_task) {
      const report = event.data.quality_task as QualityReport;
      setData((current) => current ? { ...current, quality_reports: [...(current.quality_reports ?? []).filter((old) => old.task_type !== report.task_type), report] } : current);
      if (report.state !== 'RUNNING') setRefresh((value) => value + 1);
      void state.reloadTranslation().catch(() => undefined);
    }
  }), [state.subscribe, state.reloadTranslation]);

  useEffect(() => {
    if (!qualityRunning) { setCancelling(false); return; }
    const timer = window.setInterval(() => {
      void state.reloadTranslation().catch(() => undefined);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [qualityRunning, state.reloadTranslation]);

  useEffect(() => {
    if (!state.ready) return;
    const id = ++requestId.current;
    const controller = new AbortController();
    const params = new URLSearchParams({ page: String(page), limit: String(limit), query: search, status, file_path: file, only_issues: String(onlyIssues), warning });
    params.set('incremental', 'true');
    let timer: number | undefined;
    setLoading(true);
    setData(null);
    setError('');
    const load = async () => {
      try {
        const result = await request<ProofreadingData>('/api/proofreading?' + params, { signal: controller.signal });
        if (id !== requestId.current) return;
        setData(result);
        setSelected(new Set()); setActive(null); selectionAnchor.current = null;
        if (result.scan_complete === false) {
          timer = window.setTimeout(() => void load(), 80);
        } else {
          setLoading(false);
          if (result.page !== page) setPage(result.page);
        }
      } catch (failure) {
        if (id !== requestId.current) return;
        setLoading(false); setData(null);
        setError(failure instanceof Error ? failure.message : String(failure));
      }
    };
    void load();
    return () => { requestId.current += 1; controller.abort(); window.clearTimeout(timer); };

  }, [state.ready, projectIdentity, page, limit, search, status, file, onlyIssues, warning, refresh, state.translation.engine_status, state.translation.stop_barrier, state.translation.single_tasks]);

  useEffect(() => {
    if (!state.ready) return;
    let activeRequest = true;
    const poll = async () => {
      try {
        const result = await request<typeof retranslate>('/api/proofreading/retranslate');
        if (!activeRequest) return;
        setRetranslate(result);
        if (retranslateRunning && !['RUNNING', 'CANCELLING'].includes(result.state)) {
          setRefresh((value) => value + 1);
          void state.reloadTranslation().catch(() => undefined);
        }
      } catch (failure) {
        if (activeRequest) setError(failure instanceof Error ? failure.message : String(failure));
      }
    };
    void poll();
    const timer = retranslateRunning ? window.setInterval(() => void poll(), 1500) : undefined;
    return () => { activeRequest = false; window.clearInterval(timer); };
  }, [state.ready, state.link, retranslateRunning, state.reloadTranslation]);

  const reload = () => setRefresh((value) => value + 1);
  const closeEdit = () => {
    if (saving) return;
    if (dirty && !window.confirm('译文尚未保存，确定放弃这次编辑？')) return;
    setEdit(null);
  };

  const saveEdit = async () => {
    if (!data || !edit || saving || readonly || editProjectChanged) return;
    const identity = projectRef.current;
    setSaving(true);
    try {
      await request('/api/proofreading/item', {
        method: 'PATCH', body: JSON.stringify({
          cache_token: edit.cache_token, row: { id: edit.id, version: edit.version }, dst: draft,
        }),
      });
      if (identity !== projectRef.current) return;
      setEdit(null);
      state.pushToast('success', '译文已保存到当前项目缓存。');
      reload();
    } catch (failure) {
      state.pushToast('error', failure instanceof Error ? failure.message : String(failure));
    } finally { setSaving(false); }
  };

  const replaceRows = async () => {
    if (!replaceSnapshot || !find || saving || readonly) return;
    const targets = replaceSnapshot.rows;
    setSaving(true);
    try {
      const result = await request<{ changed: number }>('/api/proofreading/replace', {
        method: 'POST', body: JSON.stringify({
          cache_token: replaceSnapshot.cache_token,
          rows: targets.map((row) => ({ id: row.id, version: row.version })),
          find, replace: replacement, case_sensitive: caseSensitive,
        }),
      });
      setReplaceOpen(false);
      state.pushToast(result.changed ? 'success' : 'info', result.changed ? `已替换并保存 ${result.changed} 条译文。` : '没有匹配的译文，内容未改变。');
      reload();
    } catch (failure) {
      state.pushToast('error', failure instanceof Error ? failure.message : String(failure));
    } finally { setSaving(false); }
  };

  const startQuality = async () => {
    if (!qualityConfirm || readonly || saving || dirty || qualityConfirm.project !== projectRef.current) return;
    const snapshot = qualityConfirm;
    setSaving(true);
    try {
      const result = await request<{ accepted: number; skipped: number }>('/api/proofreading/quality', {
        method: 'POST', body: JSON.stringify({
          task: snapshot.task, cache_token: snapshot.cache_token,
          ids: snapshot.ids,
          ...(snapshot.rows ? { rows: snapshot.rows.map((row) => ({ id: row.id, version: row.version })) } : {}),
        }),
      });
      if (snapshot.project !== projectRef.current) return;
      setQualityConfirm(null);
      state.pushToast('success', t('quality_started').replace('{accepted}', String(result.accepted)).replace('{skipped}', String(result.skipped)));
      await state.reloadTranslation();
      reload();
    } catch (failure) {
      state.pushToast('error', failure instanceof Error ? failure.message : String(failure));
    } finally { setSaving(false); }
  };

  const cancelQuality = async () => {
    if (cancelling || !qualityRunning) return;
    setCancelling(true);
    try {
      await request('/api/proofreading/quality/cancel', { method: 'POST' });
      state.pushToast('info', t('quality_cancelling'));
      await state.reloadTranslation();
      reload();
    } catch (failure) {
      setCancelling(false);
      state.pushToast('error', failure instanceof Error ? failure.message : String(failure));
    }
  };

  const items = data?.items ?? [];
  const activeRow = items.find((row) => row.id === active);
  const toggle = (id: number) => {
    setSelected((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };
  const openEdit = (row: ProofreadingRow) => {
    if (readonly || loading || saving) return;
    if (edit?.id === row.id) return;
    if (dirty && !window.confirm('译文尚未保存，确定放弃这次编辑？')) return;
    setEdit({ ...row, cache_token: data?.cache_token ?? '', project_identity: projectIdentity });
    setDraft(row.dst);
  };

  const copyText = async (text: string) => {
    try { await navigator.clipboard.writeText(text); state.pushToast('success', '已复制到剪贴板。'); }
    catch (failure) { state.pushToast('error', '复制失败：' + String(failure)); }
  };
  const copyPairs = (rows: ProofreadingRow[]) => {
    const cell = (value: string) => /[\t\r\n"]/.test(value) ? '"' + value.replaceAll('"', '""') + '"' : value;
    void copyText(rows.map((row) => cell(row.src) + '\t' + cell(row.dst)).join('\r\n'));
  };
  const selectRow = (row: ProofreadingRow, event: MouseEvent | KeyboardEvent) => {
    if (event.shiftKey && selectionAnchor.current != null) {
      const from = items.findIndex((item) => item.id === selectionAnchor.current);
      const to = items.findIndex((item) => item.id === row.id);
      if (from >= 0) setSelected(new Set(items.slice(Math.min(from, to), Math.max(from, to) + 1).map((item) => item.id)));
    } else {
      if (event.ctrlKey || event.metaKey) toggle(row.id); else setSelected(new Set([row.id]));
      selectionAnchor.current = row.id;
    }
    setActive(row.id);
  };
  const rowKeyDown = (event: KeyboardEvent<HTMLTableRowElement>, row: ProofreadingRow) => {
    if (event.target !== event.currentTarget) return;
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'a') {
      event.preventDefault(); setSelected(new Set(items.map((item) => item.id))); return;
    }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'c' && !window.getSelection()?.toString()) {
      event.preventDefault(); copyPairs(items.filter((item) => selected.has(item.id))); return;
    }
    if (event.key === 'Enter' || event.key === 'F2') { event.preventDefault(); openEdit(row); return; }
    if (event.key === ' ') { event.preventDefault(); toggle(row.id); return; }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const index = items.indexOf(row) + (event.key === 'ArrowDown' ? 1 : -1);
      if (items[index]) {
        selectRow(items[index], event);
        (event.currentTarget.parentElement?.children[index] as HTMLElement)?.focus();
      }
    }
  };
  const confirmSelection = (action: 'reset' | 'confirm' | 'retranslate', rows = items.filter((row) => selected.has(row.id))) => {
    if (data && rows.length) setSelectionConfirm({ action, rows, cache_token: data.cache_token, project: projectIdentity });
  };
  const applySelection = async () => {
    if (!selectionConfirm || readonly || saving || dirty || selectionConfirm.project !== projectRef.current) return;
    const snapshot = selectionConfirm;
    setSaving(true);
    try {
      const result = await request<{ changed: number; state: string }>('/api/proofreading/' + snapshot.action, {
        method: 'POST', body: JSON.stringify({ cache_token: snapshot.cache_token, rows: snapshot.rows.map(({ id, version }) => ({ id, version })) }),
      });
      if (snapshot.project !== projectRef.current) return;
      setSelectionConfirm(null);
      if (snapshot.action === 'retranslate') {
        setRetranslate(result);
        state.pushToast('info', '重译任务已启动。');
        await state.reloadTranslation();
      } else { state.pushToast('success', '已保存 ' + result.changed + ' 条变更。'); reload(); }
    } catch (failure) { state.pushToast('error', failure instanceof Error ? failure.message : String(failure)); }
    finally { setSaving(false); }
  };
  const exportRows = async () => {
    if (!exportConfirm || readonly || saving || dirty || exportConfirm.project !== projectRef.current) return;
    setSaving(true);
    try {
      const result = await request<{ output_folder: string }>('/api/proofreading/export', {
        method: 'POST', body: JSON.stringify({ cache_token: exportConfirm.cache_token }),
      });
      setExportConfirm(null); state.pushToast('success', '译文已写入：' + result.output_folder);
    } catch (failure) { state.pushToast('error', failure instanceof Error ? failure.message : String(failure)); }
    finally { setSaving(false); }
  };
  const showReport = async () => {
    const identity = projectRef.current;
    setReportOpen(true); setReport(null); setReportError('');
    try {
      const result = await request<TranslationReport>('/api/proofreading/report');
      if (identity === projectRef.current) {
        setReport(result);
        setReportSelection(new Set(result.item_references.map((item) => item.item_index)));
      }
    } catch (failure) { if (identity === projectRef.current) setReportError(failure instanceof Error ? failure.message : String(failure)); }
  };
  const locateRow = async (row: ProofreadingRow) => {
    if (!data) return;
    const identity = projectRef.current;
    setLocationOpen(true); setLocation(null); setLocationError('');
    try {
      const result = await request<NonNullable<typeof location>>('/api/proofreading/locate', {
        method: 'POST', body: JSON.stringify({ cache_token: data.cache_token, rows: [{ id: row.id, version: row.version }] }),
      });
      if (identity === projectRef.current) setLocation(result);
    } catch (failure) { if (identity === projectRef.current) setLocationError(failure instanceof Error ? failure.message : String(failure)); }
  };
  const cancelRetranslate = async () => {
    try { setRetranslate(await request<typeof retranslate>('/api/proofreading/retranslate/cancel', { method: 'POST' })); }
    catch (failure) { state.pushToast('error', failure instanceof Error ? failure.message : String(failure)); }
  };
  const mutationDisabled = !state.ready || Boolean(readonly) || retranslateRunning || loading || saving || dirty;
  const actions = (
    <>
      <Button size="xs" variant="default" disabled={loading || saving || dirty} onClick={reload}>刷新译文</Button>
      <Button size="xs" variant="default" disabled={mutationDisabled || !data?.total} onClick={() => { if (data) setExportConfirm({ cache_token: data.cache_token, project: projectIdentity }); }}>导出译文</Button>
      <Button size="xs" variant="default" disabled={mutationDisabled || !items.length} onClick={() => { if (data) { setReplaceSnapshot({ cache_token: data.cache_token, rows: selected.size ? items.filter((row) => selected.has(row.id)) : items }); setReplaceOpen(true); } }}>批量替换</Button>
      <Button size="xs" variant="default" disabled={mutationDisabled || !selected.size} onClick={() => confirmSelection('retranslate')}>重译选中行</Button>
      {retranslateRunning && <Button size="xs" variant="light" color="red" disabled={retranslate.state === 'CANCELLING'} onClick={() => void cancelRetranslate()}>取消重译</Button>}
      <Button size="xs" variant="default" disabled={mutationDisabled || !selected.size} onClick={() => confirmSelection('reset')}>重置选中译文</Button>
      <Button size="xs" variant="default" disabled={loading || !data} onClick={() => void showReport()}>质量报告</Button>
      {(['proofread', 'polish'] as const).map((task) => (
        <Button size="xs" key={task} variant="default" disabled={mutationDisabled || !selected.size}
          onClick={() => {
            const rows = items.filter((row) => selected.has(row.id));
            if (data) setQualityConfirm({ task, cache_token: data.cache_token, ids: rows.map((row) => row.id), rows, project: projectIdentity });
          }}>
          {t(task === 'polish' ? 'polish_action' : 'proofread_action')}
        </Button>
      ))}
      {qualityRunning && <Button size="xs" color="red" variant="light" disabled={cancelling} onClick={() => void cancelQuality()}>{t('quality_cancel')}</Button>}
    </>
  );

  return (
    <div className={embedded ? 'proofreading-page rb-embedded' : 'proofreading-page rb-page'}>
      <div className="rb-page-scroll">
        {embedded ? <div className="rb-embedded-actions">{actions}</div> : (
          <PageHeader
            title="平行校对台"
            description="原文与译文并排阅读，让每一句更准确、更自然。"
            actions={actions}
          />
        )}
        {readonly && <Banner tone="info">当前任务正在运行，译文可阅读；任务结束后可以编辑和保存。</Banner>}
        {qualityRunning && <div className="rb-proofreading-task"><Progress value={data?.quality_reports?.at(-1)?.total_count ? 100 * (data.quality_reports.at(-1)?.completed_count ?? 0) / (data.quality_reports.at(-1)?.total_count ?? 1) : 0} /><span>{t(cancelling ? 'quality_cancelling' : 'quality_running')}</span></div>}
        {retranslate.state !== 'IDLE' && <div className="rb-proofreading-task">重译：{retranslate.done ?? 0} / {retranslate.total ?? 0} · 已保存 {retranslate.updated ?? 0} · 失败 {retranslate.failed ?? 0} · {retranslateRunning ? retranslate.state === 'CANCELLING' ? '等待已发出的请求结束…' : '处理中…' : retranslate.state === 'FAILED' ? '失败：' + retranslate.error : retranslate.state === 'CANCELLED' ? '已取消' : '已完成'}</div>}
        {error && <Banner tone="warning">{error}</Banner>}
        <form className="proofreading-filters" onSubmit={(event) => { event.preventDefault(); setPage(1); setSearch(query.trim()); }}>
          <TextInput aria-label="搜索原文或译文" placeholder="搜索原文、译文或文件…" value={query} onChange={(event) => setQuery(event.currentTarget.value)} />
          <Select aria-label="翻译状态" allowDeselect={false} value={status} data={[{ value: '', label: '全部状态' }, ...Object.entries(STATUS_LABELS).map(([value, label]) => ({ value, label }))]} onChange={(value) => { if (value != null) { setStatus(value); setPage(1); } }} />
          <Select aria-label="源文件" allowDeselect={false} value={file} data={[{ value: '', label: '全部文件' }, ...(data?.files ?? []).map((path) => ({ value: path, label: path || '未分类' }))]} onChange={(value) => { if (value != null) { setFile(value); setPage(1); } }} />
          <Button variant="default" type="submit" disabled={loading}>搜索</Button>
        </form>
        <div className="rb-proofreading-selection">
          <Checkbox label="仅看问题" checked={onlyIssues} onChange={(event) => { setOnlyIssues(event.currentTarget.checked); setPage(1); }} />
          <Select aria-label="问题类型" value={warning} allowDeselect={false} size="xs" data={[{ value: '', label: '全部问题类型' }, ...Object.entries(WARNING_LABELS).map(([value, label]) => ({ value, label }))]} onChange={(value) => { setWarning(value ?? ''); setPage(1); }} />
          <Button size="compact-xs" variant="subtle" disabled={!selected.size} onClick={() => copyPairs(items.filter((row) => selected.has(row.id)))}>复制所选双语</Button>
          <span className="rb-metric-note">单击选行 · Ctrl / Shift 多选 · 双击或 F2 编辑</span>
        </div>
        {loading && <div className="rb-proof-loading" role="status" aria-live="polite">
          <Loader size="xs" />
          <span>{onlyIssues || warning ? t('proofreading_checking').replace('{checked}', (data?.checked ?? 0).toLocaleString()).replace('{total}', (data?.check_total ?? 0).toLocaleString()) : t('proofreading_loading')}</span>
        </div>}
        <div className="rb-proof-table-scroll" aria-busy={loading} onScroll={() => setContextMenu(null)}>
          <Table className="rb-proof-table" aria-label="原译对照表" layout="fixed" stickyHeader withTableBorder withColumnBorders highlightOnHover horizontalSpacing="sm" verticalSpacing="xs">
            <colgroup><col style={{ width: 34 }} /><col style={{ width: 46 }} /><col /><col /><col style={{ width: 80 }} /><col style={{ width: 40 }} /></colgroup>
            <Table.Thead><Table.Tr>
              <Table.Th><Checkbox aria-label="全选当前页" checked={!!items.length && selected.size === items.length} indeterminate={selected.size > 0 && selected.size < items.length} disabled={loading || saving} onChange={(event) => setSelected(event.currentTarget.checked ? new Set(items.map((row) => row.id)) : new Set())} /></Table.Th>
              <Table.Th>#</Table.Th><Table.Th>原文</Table.Th><Table.Th>译文</Table.Th><Table.Th>状态</Table.Th><Table.Th>操作</Table.Th>
            </Table.Tr></Table.Thead>
            <Table.Tbody>
              {items.map((row) => (
                <Table.Tr key={row.id} className="rb-proofreading-row" data-selected={selected.has(row.id)} aria-selected={selected.has(row.id)} tabIndex={0}
                  onClick={(event) => { selectRow(row, event); event.currentTarget.focus(); }} onKeyDown={(event) => rowKeyDown(event, row)}
                  onContextMenu={(event) => { event.preventDefault(); if (!selected.has(row.id)) selectRow(row, event); setContextMenu({ row, x: event.clientX, y: event.clientY }); }}>
                  <Table.Td onClick={(event) => event.stopPropagation()}><Checkbox aria-label="选择行" checked={selected.has(row.id)} disabled={loading || saving} onChange={() => { toggle(row.id); setActive(row.id); selectionAnchor.current = row.id; }} /></Table.Td>
                  <Table.Td className="rb-proof-index" title={row.file_path + ':' + row.row}>{row.id + 1}</Table.Td>
                  <Table.Td onDoubleClick={() => openEdit(row)}>{row.src}</Table.Td>
                  <Table.Td onDoubleClick={() => openEdit(row)}><span className="rb-proof-target">{row.dst || '（空译文）'}</span></Table.Td>
                  <Table.Td><span className="rb-proof-status" data-status={row.status}>{STATUS_LABELS[row.status] ?? row.status}</span>
                    {!!row.warnings?.length && <span className="rb-proof-warning" title={row.warnings.map((value) => WARNING_LABELS[value] ?? value).join('、')}><AlertTriangle size={13} />{row.warnings.length} 项问题</span>}
                  </Table.Td>
                  <Table.Td onClick={(event) => event.stopPropagation()}>
                    <ActionIcon variant="subtle" aria-label={'第 ' + (row.id + 1) + ' 行操作'} onClick={(event) => {
                      const rect = event.currentTarget.getBoundingClientRect();
                      setContextMenu({ row, x: rect.left, y: rect.bottom });
                    }}><MoreHorizontal size={16} /></ActionIcon>
                  </Table.Td>
                </Table.Tr>
              ))}
              {!items.length && <Table.Tr><Table.Td colSpan={6} className="rb-proof-empty">{loading ? t('proofreading_loading') : data ? '没有符合筛选条件的译文。' : '先完成一次翻译，再来这里校对译文。'}</Table.Td></Table.Tr>}
            </Table.Tbody>
          </Table>
        </div>
        <footer className="proofreading-pagination">
          <span>{data ? `${data.matched.toLocaleString()}{data.scan_complete === false ? '＋' : ''} 条符合条件 · 共 ${data.total.toLocaleString()} 条` : '原译对照'}{selected.size ? ` · 已选 ${selected.size} 条` : ''}</span>
          <div className="proofreading-toolbar">
            <Select aria-label="每页条数" size="xs" w={100} allowDeselect={false} value={String(limit)} data={['25', '50', '100'].map((value) => ({ value, label: value + ' 条 / 页' }))} onChange={(value) => { setLimit(Number(value)); setPage(1); }} />
            <NumberInput aria-label="跳转页码" size="xs" w={64} min={1} max={Math.max(1, Math.ceil((data?.matched ?? 0) / limit))} value={page} allowDecimal={false} onChange={(value) => { if (typeof value === 'number') setPage(value); }} />
            <Button variant="default" size="xs" disabled={loading || page <= 1} onClick={() => setPage((value) => value - 1)}>上一页</Button>
            <span>{data?.page ?? 1} / {Math.max(1, Math.ceil((data?.matched ?? 0) / limit))}</span>
            <Button variant="default" size="xs" disabled={loading || !data || page * limit >= data.matched} onClick={() => setPage((value) => value + 1)}>下一页</Button>
          </div>
        </footer>
        <div className="rb-proofreading-location" title={activeRow?.file_path}>
          {activeRow ? activeRow.file_path + ':' + activeRow.row : '选择行后显示文件与行号'}
          <span>编辑确认后自动保存缓存；导出译文才会写入文件。</span>
        </div>
      </div>
      {contextMenu && <Portal><Menu key={contextMenu.x + ":" + contextMenu.y} opened onChange={(opened) => { if (!opened) setContextMenu(null); }} position="bottom-start" offset={0} withinPortal>
        <Menu.Target><span style={{ position: 'fixed', left: contextMenu.x, top: contextMenu.y, width: 1, height: 1 }} /></Menu.Target>
                      <Menu.Dropdown>
                        <Menu.Item disabled={mutationDisabled} onClick={() => confirmSelection('retranslate', selected.has(contextMenu.row.id) ? items.filter((item) => selected.has(item.id)) : [contextMenu.row])}>重新翻译{selected.has(contextMenu.row.id) && selected.size > 1 ? '所选行' : ''}</Menu.Item>
                        <Menu.Item leftSection={<Pencil size={14} />} disabled={mutationDisabled} onClick={() => openEdit(contextMenu.row)}>编辑译文</Menu.Item>
                        <Menu.Item leftSection={<Copy size={14} />} onClick={() => void copyText(contextMenu.row.src)}>复制原文</Menu.Item>
                        <Menu.Item leftSection={<Copy size={14} />} onClick={() => void copyText(contextMenu.row.dst)}>复制译文</Menu.Item>
                        <Menu.Item onClick={() => copyPairs(selected.has(contextMenu.row.id) ? items.filter((item) => selected.has(item.id)) : [contextMenu.row])}>复制双语对照</Menu.Item>
                        <Menu.Divider />
                        {contextMenu.row.warnings?.includes('RETRY_THRESHOLD') && <Menu.Item disabled={mutationDisabled} onClick={() => confirmSelection('confirm', selected.has(contextMenu.row.id) ? items.filter((item) => selected.has(item.id)) : [contextMenu.row])}>确认译文无误</Menu.Item>}
                        <Menu.Item color="red" leftSection={<RotateCcw size={14} />} disabled={mutationDisabled} onClick={() => confirmSelection('reset', [contextMenu.row])}>重置此行译文</Menu.Item>
                        <Menu.Item onClick={() => void locateRow(contextMenu.row)}>定位译文</Menu.Item>
                        <Menu.Label>{contextMenu.row.file_path || '未分类'}{contextMenu.row.row ? ':' + contextMenu.row.row : ''}</Menu.Label>
                      </Menu.Dropdown>
      </Menu></Portal>}
      {locationOpen && <Modal opened onClose={() => setLocationOpen(false)} title="定位译文" size={900}>
        {locationError ? <Banner tone="warning">{locationError}</Banner> : !location ? <p>正在读取目标行…</p> : <>
          <p className="rb-proofreading-location">{location.path}:{location.row}</p>
          <Button size="xs" variant="default" onClick={() => void copyText(location.path)}>复制文件路径</Button>
          <pre className="rb-proof-context">{location.lines.map((line) => <div key={line.number} data-target={line.number === location.row}>{String(line.number).padStart(6)}  {line.text}</div>)}</pre>
        </>}
      </Modal>}
      {edit && (
        <Modal opened onClose={closeEdit} title="编辑译文" size={960} centered classNames={{ content: 'rb-proof-editor' }}
          onKeyDown={(event) => { if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') { event.preventDefault(); void saveEdit(); } }}>
          {editProjectChanged && <Banner tone="warning">项目已切换，未保存的译文已保留。请复制译文后关闭编辑。</Banner>}
          <p className="rb-metric-note">{edit.file_path}:{edit.row} · Ctrl + Enter 保存</p>
          <div className="rb-proof-bilingual-editor">
            <Textarea label="原文" readOnly value={edit.src} autosize minRows={10} maxRows={16} />
            <Textarea id="proofreading-draft" label="译文" data-autofocus value={draft} disabled={saving || readonly} autosize minRows={10} maxRows={16} onChange={(event) => setDraft(event.currentTarget.value)} />
          </div>
          <div className="rb-dialog-actions"><Button variant="default" onClick={closeEdit}>取消</Button><Button disabled={saving || readonly || !dirty || editProjectChanged} onClick={() => void saveEdit()}>保存译文</Button></div>
        </Modal>
      )}
      {selectionConfirm && <Dialog title={selectionConfirm.action === 'retranslate' ? '重新翻译' : selectionConfirm.action === 'reset' ? '重置选中译文' : '确认译文无误'} confirmText={selectionConfirm.action === 'retranslate' ? '开始重译' : '确认并保存'} onCancel={() => { if (!saving) setSelectionConfirm(null); }} onConfirm={mutationDisabled || selectionConfirm.project !== projectIdentity ? undefined : () => void applySelection()}>
        <p>{selectionConfirm.action === 'retranslate' ? '使用当前翻译接口重新处理选中行，会消耗额度；失败行保留原译文。' : selectionConfirm.action === 'reset' ? '将清空选中行的译文、重试记录，并设为待翻译。' : '保留已有译文，清除重试次数和对应失败记录。'}共 {selectionConfirm.rows.length} 条，成功后保存到缓存。</p>
      </Dialog>}
      {exportConfirm && <Dialog title="导出译文" confirmText="写入译文文件" onCancel={() => { if (!saving) setExportConfirm(null); }} onConfirm={mutationDisabled || exportConfirm.project !== projectIdentity ? undefined : () => void exportRows()}>
        <p>将当前缓存中的全部译文按原文件格式写入输出目录，可能覆盖已有译文文件。当前筛选不会限制导出范围。</p>
        <p>{data?.cache_folder}</p>
      </Dialog>}
      {reportOpen && <Modal opened onClose={() => setReportOpen(false)} title="质量报告" size="lg">
        {reportError ? <Banner tone="warning">{reportError}</Banner> : !report ? <p>正在读取报告…</p> : <>
          <div className="rb-quality-summary">
            <strong>失败 {report.failed_count}</strong>
            <strong>回退 {report.fallback_count}</strong>
            <strong>对齐异常 {report.line_mismatch_count}</strong>
          </div>
          <p>{Object.entries(report.error_type_counts).map(([key, count]) => key + ': ' + count).join(' · ') || '没有记录到翻译失败原因。'}</p>
          {report.item_references.length ? <div className="rb-quality-items">{report.item_references.map((row) => (
            <Checkbox key={row.item_index} checked={reportSelection.has(row.item_index)}
              label={`#${row.item_index + 1} ${row.reference} · ${row.error_types.join('、')} · ${row.source_preview}`}
              onChange={() => setReportSelection((previous) => {
                const next = new Set(previous);
                if (next.has(row.item_index)) next.delete(row.item_index); else next.add(row.item_index);
                return next;
              })} />
          ))}</div> : <p>没有需要处理的条目。</p>}
          <Button size="xs" disabled={!reportSelection.size || qualityRunning || readonly || !data?.cache_token} onClick={() => {
            if (!data) return;
            setQualityConfirm({ task: 'proofread', cache_token: data.cache_token, ids: [...reportSelection], project: projectIdentity });
            setReportOpen(false);
          }}>对选中项执行 AI 校对</Button>
        </>}
        {(data?.quality_reports ?? []).map((report) => (
          <details className="rb-quality-report" key={report.task_type}>
            <summary>AI 处理记录 · {t(report.task_type === 'POLISHER' ? 'polish_action' : 'proofread_action')} · {t(report.state === 'COMPLETED' ? 'quality_completed' : report.state === 'FAILED' ? 'quality_failed' : report.state === 'CANCELLED' ? 'quality_cancelled' : 'quality_running')}</summary>
            <p>{t('quality_summary').replace('{completed}', String(report.completed_count)).replace('{total}', String(report.total_count)).replace('{updated}', String(report.updated_count)).replace('{failed}', String(report.failed_count)).replace('{skipped}', String(report.skipped_count))}</p>
            <Progress value={report.total_count > 0 ? 100 * report.completed_count / report.total_count : 0} />
            {report.error_message && <Banner tone="warning">{report.error_message}</Banner>}
            {!!report.failures?.length && <ul>{report.failures.map((failure, index) => <li key={index}>#{failure.item_index + 1} · {failure.reason}</li>)}</ul>}
          </details>
        ))}

      </Modal>}
      {qualityConfirm && (
        <Dialog title={t(qualityConfirm.task === 'polish' ? 'polish_action' : 'proofread_action')} confirmText={t('quality_confirm')}
          onCancel={() => { if (!saving) setQualityConfirm(null); }}
          onConfirm={saving || readonly || dirty || qualityConfirm.project !== projectIdentity ? undefined : () => void startQuality()}>
          <p>{t('quality_confirm_hint').replace('{count}', String(qualityConfirm.ids.length))}</p>
        </Dialog>
      )}
      {replaceOpen && (
        <Dialog title="批量替换译文" confirmText="替换并保存" onCancel={() => { if (!saving) setReplaceOpen(false); }} onConfirm={!find || saving || readonly ? undefined : () => void replaceRows()}>
          <p>对{selected.size ? `已选 ${selected.size} 条` : `当前页 ${replaceSnapshot?.rows.length ?? 0} 条`}译文执行纯文本替换，并立即保存。</p>
          <div className="proofreading-replacement-grid">
            <TextInput label="查找" value={find} disabled={saving} placeholder="需要替换的内容" onChange={(event) => setFind(event.currentTarget.value)} />
            <TextInput label="替换为" value={replacement} disabled={saving} placeholder="留空可删除匹配内容" onChange={(event) => setReplacement(event.currentTarget.value)} />
          </div>
          <Checkbox label="区分大小写" checked={caseSensitive} disabled={saving} onChange={(event) => setCaseSensitive(event.currentTarget.checked)} />
          {saving && <p>正在保存替换结果…</p>}
        </Dialog>
      )}
    </div>
  );
}
