/** 平行校对台：分页读取真实缓存，保存前由服务端检查项目和译文版本。 */
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Button, Checkbox, Dropdown, Input, InputNumber, Modal, Progress, Select, Space, Spin, Table, Tooltip } from 'antd';
import type { ColumnsType, TableRef } from 'antd/es/table';
import type { MenuProps } from 'antd';
import { request } from '../api';
import { focusTableRow } from '../components/tableFocus';
import type { AppState } from '../useAppState';
import { MoreHorizontal, AlertTriangle, ChevronDown, ChevronUp, Copy, Info, Pencil, RotateCcw } from 'lucide-react';
import type { MouseEvent, KeyboardEvent } from 'react';
import { Banner, Dialog, PageHeader } from '../ui';
import { useT } from '../i18n';
import {
  NO_WARNING, collectGlossaryTerms, collectWarnings, compilePattern, exportFilename, exportText,
  filterRows, matchRowIndices, pageSlice, replaceImpact, stepMatch,
} from '../proofreadingView.mjs';

interface GlossaryTerm {
  key: string;
  src: string;
  dst: string;
  label: string;
}

interface ProofreadingRow {
  id: number;
  version: string;
  src: string;
  dst: string;
  status: string;
  file_path: string;
  row: number;
  warnings?: string[];
  glossary_terms?: { src?: string; dst?: string }[];
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
  const [searchRegex, setSearchRegex] = useState(false);
  const [matchIndex, setMatchIndex] = useState(-1);
  const [status, setStatus] = useState('');
  const [file, setFile] = useState('');
  const [filterStatus, setFilterStatus] = useState<string[]>([]);
  const [filterFiles, setFilterFiles] = useState<string[]>([]);
  const [filterWarnings, setFilterWarnings] = useState<string[]>([]);
  const [filterTerms, setFilterTerms] = useState<string[]>([]);
  const [exportRowsState, setExportRowsState] = useState<{ filename: string; text: string; count: number; truncated: boolean } | null>(null);
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
  const [replaceRegex, setReplaceRegex] = useState(false);
  const [replaceScope, setReplaceScope] = useState<'selected' | 'page' | 'all'>('page');
  const [replacePlan, setReplacePlan] = useState<{ rows: { id: number; version: string; dst: string }[]; matchCount: number } | null>(null);
  const [replaceBusy, setReplaceBusy] = useState('');
  const [reportSelection, setReportSelection] = useState<Set<number>>(new Set());
  const [scrollY, setScrollY] = useState(200);
  const [scrollX, setScrollX] = useState(900);
  const requestId = useRef(0);
  const projectRef = useRef('');
  const matchIndexRef = useRef(-1);
  const dirtyRef = useRef(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const tableRef = useRef<TableRef>(null);
  const cancelFocus = useRef<(() => void) | null>(null);
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
    setMatchIndex(-1);
    setPage(1);
    setFile('');
    setStatus('');
    setFilterStatus([]);
    setFilterFiles([]);
    setFilterWarnings([]);
    setFilterTerms([]);
    setExportRowsState(null);
    setReplacePlan(null);
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
    setReplacePlan(null);
    setReplaceBusy('');
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

  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const measure = () => {
      const header = el.querySelector('.ant-table-header') as HTMLElement | null;
      const headerH = header?.offsetHeight ?? 36;
      // 下限与 .rb-proof-table-scroll 的 CSS min-height 一致，避免低窗口下两层最低高度冲突而裁切
      setScrollY(Math.max(48, el.clientHeight - headerH - 2));
      setScrollX(Math.max(620, el.clientWidth - 2));
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useLayoutEffect(() => {
    tableRef.current?.scrollTo({ top: 0 });
  }, [page, limit, search, status, file, onlyIssues, warning, filterStatus, filterFiles, filterTerms]);

  useEffect(() => () => cancelFocus.current?.(), []);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => setContextMenu(null);
    el.addEventListener('scroll', onScroll, true);
    return () => el.removeEventListener('scroll', onScroll, true);
  }, []);

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

  const replaceRows = async (plan: { rows: { id: number; version: string; dst: string }[]; matchCount: number }) => {
    if (!replaceSnapshot || !find || saving || readonly || !plan.rows.length) return;
    const identity = projectRef.current;
    const token = replaceSnapshot.cache_token;
    setSaving(true);
    setReplaceBusy('');
    let changed = 0;
    try {
      // 后端 /api/proofreading/replace 只接受纯文本；正则与影响范围在渲染端算好后逐行走 /item 落盘。
      for (const row of plan.rows) {
        setReplaceBusy(String(changed + 1) + '/' + String(plan.rows.length));
        await request('/api/proofreading/item', {
          method: 'PATCH', body: JSON.stringify({ cache_token: token, row: { id: row.id, version: row.version }, dst: row.dst }),
        });
        changed += 1;
        if (identity !== projectRef.current) return;
      }
      setReplaceOpen(false);
      setReplacePlan(null);
      state.pushToast('success', t('proofreading_batch_replace_summary').replace('{count}', String(changed)));
      reload();
    } catch (failure) {
      if (identity === projectRef.current) {
        state.pushToast('error', failure instanceof Error ? failure.message : String(failure));
        if (changed) reload();
      }
    } finally {
      setReplaceBusy('');
      setSaving(false);
    }
  };

  const previewReplace = async () => {
    if (!replaceOpen || saving || readonly || !find) return;
    const compiled = compilePattern(find, { regex: replaceRegex, caseSensitive });
    if (!compiled.ok) { setReplacePlan(null); return; }
    try {
      let candidates = items;
      if (replaceScope === 'selected') candidates = items.filter((row) => selected.has(row.id));
      else if (replaceScope === 'all') candidates = items;
      const impact = replaceImpact(candidates, find, replacement, { regex: replaceRegex, caseSensitive });
      setReplacePlan({ rows: impact.rows.map((row) => ({ id: row.id, version: row.version, dst: row.after })), matchCount: impact.matchCount });
    } catch (failure) {
      state.pushToast('error', failure instanceof Error ? failure.message : String(failure));
    }
  };

  /** 「全部结果」作用域或已载入行数不足一页时，先按当前筛选拉回整批命中行再算影响范围。 */
  const previewReplaceAll = async () => {
    if (!replaceOpen || saving || readonly || !find || !replaceSnapshot) return;
    if (!compilePattern(find, { regex: replaceRegex, caseSensitive }).ok) return;
    setSaving(true);
    try {
      const loaded = await loadAllRows();
      const candidates = replaceScope === 'selected' ? loaded.rows.filter((row) => selected.has(row.id)) : loaded.rows;
      const impact = replaceImpact(candidates, find, replacement, { regex: replaceRegex, caseSensitive });
      setReplacePlan({ rows: impact.rows.map((row) => ({ id: row.id, version: row.version, dst: row.after })), matchCount: impact.matchCount });
      if (!impact.rows.length) state.pushToast('info', t('proofreading_batch_replace_summary_none'));
    } catch (failure) {
      state.pushToast('error', failure instanceof Error ? failure.message : String(failure));
    } finally {
      setSaving(false);
    }
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

  // 筛选维度（状态 / 文件 / 问题类型 / 术语表）在已载入的结果上求值，对齐 FilterDialog 的客户端筛选口径。
  const filterActive = Boolean(filterStatus.length || filterFiles.length || filterWarnings.length || filterTerms.length);
  const filteredItems = useMemo(
    () => filterRows(items, { statuses: filterStatus, files: filterFiles, warnings: filterWarnings, terms: filterTerms }),
    [items, filterStatus, filterFiles, filterWarnings, filterTerms],
  );
  const clientPage = filterActive ? pageSlice(filteredItems, page, limit) : null;
  const visibleItems = clientPage ? clientPage.items : filteredItems;
  const termOptions = useMemo(() => collectGlossaryTerms(items), [items]);
  const availableWarnings = useMemo(() => collectWarnings(items), [items]);
  const warningOptions = useMemo(() => [
    { value: '', label: '全部问题类型' },
    ...(availableWarnings.length ? availableWarnings : Object.keys(WARNING_LABELS)).map((value) => ({ value, label: WARNING_LABELS[value] ?? value })),
  ], [availableWarnings]);
  /** 客户端「问题类型」多选：与 Qt5 FilterDialog 的问题类型区一致，含「无警告」占位。 */
  const warningFilterOptions = useMemo(() => {
    const values = availableWarnings.length ? availableWarnings : [...Object.keys(WARNING_LABELS), NO_WARNING];
    return values.map((value) => ({ value, label: value === NO_WARNING ? t('proofreading_filter_no_warning') : WARNING_LABELS[value] ?? value }));
  }, [availableWarnings, t]);

  // 正则搜索：非法正则只提示，不影响列表；搜索永远只作用于当前筛选结果。
  const searchPattern = compilePattern(search, { regex: searchRegex });
  const searchError = searchPattern.ok ? '' : searchPattern.error;
  const matches = useMemo(
    () => (searchError || !search ? [] : matchRowIndices(filteredItems, search, { regex: searchRegex })),
    [filteredItems, search, searchRegex, searchError],
  );
  const matchedRows = matches.map((index) => filteredItems[index]).filter(Boolean);
  /** 批量替换对话框里的实时状态：非法正则不允许继续，影响范围由 previewReplace 计算。 */
  const planPreview = compilePattern(find, { regex: replaceRegex, caseSensitive });
  const needPreviewAll = Boolean(find) && planPreview.ok && (replaceScope === 'all' || items.length >= 100);
  const waitingForAll = needPreviewAll && !replacePlan;

  /** 批量替换的「全部结果」作用域与筛选导出共用：按后端分页上限拉回全部命中行。 */
  const loadAllRows = async () => {
    if (!data) return { rows: items, truncated: false };
    const params = new URLSearchParams({
      page: '1', limit: '100', query: search, status, file_path: file, only_issues: 'false', warning,
      incremental: 'true',
    });
    const result = await request<ProofreadingData>('/api/proofreading?' + params);
    return { rows: result.items ?? [], truncated: (result.matched ?? 0) > (result.items ?? []).length };
  };

  const focusMatch = (row: ProofreadingRow) => {
    setActive(row.id);
    setSelected(new Set([row.id]));
    setPage(Math.floor(filteredItems.indexOf(row) / Math.max(1, limit)) + 1);
    window.requestAnimationFrame(() => {
      cancelFocus.current?.();
      cancelFocus.current = focusTableRow(tableRef, String(row.id), (target) => target.focus());
    });
  };
  const stepSearchMatch = (delta: number) => {
    if (searchError || !matches.length) return;
    const next = stepMatch(matchIndex, matches.length, delta);
    if (next < 0) return;
    matchIndexRef.current = next;
    setMatchIndex(next);
    focusMatch(matchedRows[next]);
  };

  const closeReplace = () => {
    if (saving) return;
    setReplaceOpen(false);
    setReplacePlan(null);
    setReplaceBusy('');
  };
  const copyFilteredExport = async () => {
    if (!exportRowsState) return;
    await copyText(exportRowsState.text);
    state.pushToast('success', t('proofreading_filter_export_copied'));
    setExportRowsState(null);
  };
  /** 导出筛选结果：按当前服务端筛选拉回整批命中行，再套用客户端筛选维度，对齐 FilterDialog 的导出报告。 */
  const exportFilteredRows = async () => {
    if (saving || loading) return;
    setSaving(true);
    try {
      const loaded = await loadAllRows();
      const warnings = filterWarnings.length ? filterWarnings : (warning ? [warning] : []);
      const rows = filterRows(loaded.rows, { statuses: filterStatus, files: filterFiles, terms: filterTerms, warnings });
      if (!rows.length) {
        state.pushToast('info', t('proofreading_filter_export_empty'));
        return;
      }
      setExportRowsState({ filename: exportFilename(), text: exportText(rows), count: rows.length, truncated: loaded.truncated });
    } catch (failure) {
      state.pushToast('error', failure instanceof Error ? failure.message : String(failure));
    } finally {
      setSaving(false);
    }
  };
  const applyFilter = (next: { statuses?: string[]; files?: string[]; warnings?: string[]; terms?: string[] }) => {
    if (next.statuses) setFilterStatus(next.statuses);
    if (next.files) setFilterFiles(next.files);
    if (next.warnings) setFilterWarnings(next.warnings);
    if (next.terms) setFilterTerms(next.terms);
    setPage(1);
  };

  useEffect(() => {
    matchIndexRef.current = -1;
    setMatchIndex(-1);
  }, [search, searchRegex, filterStatus, filterFiles, filterWarnings, filterTerms, page, limit]);

  useEffect(() => {
    if (!filterActive || !clientPage || clientPage.page === page) return;
    setPage(clientPage.page);
  }, [filterActive, clientPage, page]);

  useEffect(() => {
    if (!replaceOpen || saving) return;
    if (!find || !planPreview.ok) { setReplacePlan(null); return; }
    if (replaceScope === 'all' || items.length >= 100) { setReplacePlan(null); return; }
    void previewReplace();
  }, [replaceOpen, find, replacement, replaceRegex, caseSensitive, replaceScope, items, planPreview.ok, saving]);
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
      const from = visibleItems.findIndex((item) => item.id === selectionAnchor.current);
      const to = visibleItems.findIndex((item) => item.id === row.id);
      if (from >= 0) setSelected(new Set(visibleItems.slice(Math.min(from, to), Math.max(from, to) + 1).map((item) => item.id)));
    } else {
      if (event.ctrlKey || event.metaKey) toggle(row.id); else setSelected(new Set([row.id]));
      selectionAnchor.current = row.id;
    }
    setActive(row.id);
  };
  const focusRow = (id: number) => {
    cancelFocus.current?.();
    cancelFocus.current = focusTableRow(tableRef, String(id), (row) => row.focus());
  };
  const rowKeyDown = (event: KeyboardEvent<HTMLElement>, row: ProofreadingRow) => {
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
        focusRow(items[index].id);
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

  const contextMenuItems = (row: ProofreadingRow): MenuProps['items'] => {
    const multi = selected.has(row.id) && selected.size > 1;
    const targetRows = selected.has(row.id) ? items.filter((item) => selected.has(item.id)) : [row];
    return [
      {
        key: 'retranslate',
        label: '重新翻译' + (multi ? '所选行' : ''),
        disabled: mutationDisabled,
        onClick: () => confirmSelection('retranslate', targetRows),
      },
      {
        key: 'edit',
        icon: <Pencil size={14} />,
        label: '编辑译文',
        disabled: mutationDisabled,
        onClick: () => openEdit(row),
      },
      {
        key: 'copy-src',
        icon: <Copy size={14} />,
        label: '复制原文',
        onClick: () => void copyText(row.src),
      },
      {
        key: 'copy-dst',
        icon: <Copy size={14} />,
        label: '复制译文',
        onClick: () => void copyText(row.dst),
      },
      {
        key: 'copy-pairs',
        label: '复制双语对照',
        onClick: () => copyPairs(targetRows),
      },
      { type: 'divider' },
      ...(row.warnings?.includes('RETRY_THRESHOLD') ? [{
        key: 'confirm',
        label: '确认译文无误',
        disabled: mutationDisabled,
        onClick: () => confirmSelection('confirm', targetRows),
      }] : []),
      {
        key: 'reset',
        danger: true,
        icon: <RotateCcw size={14} />,
        label: '重置此行译文',
        disabled: mutationDisabled,
        onClick: () => confirmSelection('reset', [row]),
      },
      {
        key: 'locate',
        label: '定位译文',
        onClick: () => void locateRow(row),
      },
      {
        key: 'path',
        type: 'group',
        label: (row.file_path || '未分类') + (row.row ? ':' + row.row : ''),
      },
    ];
  };

  const columns: ColumnsType<ProofreadingRow> = [
    {
      title: '#',
      key: 'index',
      width: 46,
      className: 'rb-proof-index',
      render: (_value, row) => <span title={row.file_path + ':' + row.row}>{row.id + 1}</span>,
    },
    {
      title: '原文',
      key: 'src',
      width: Math.max(180, Math.floor((scrollX - 228) / 2)),
      className: 'rb-proof-cell-wrap',
      onCell: (row) => ({ onDoubleClick: () => openEdit(row) }),
      render: (_value, row) => row.src,
    },
    {
      title: '译文',
      key: 'dst',
      width: Math.max(180, Math.floor((scrollX - 228) / 2)),
      className: 'rb-proof-cell-wrap',
      onCell: (row) => ({ onDoubleClick: () => openEdit(row) }),
      render: (_value, row) => <span className="rb-proof-target">{row.dst || '（空译文）'}</span>,
    },
    {
      title: '状态',
      key: 'status',
      width: 100,
      render: (_value, row) => (
        <>
          <span className="rb-proof-status" data-status={row.status}>{STATUS_LABELS[row.status] ?? row.status}</span>
          {!!row.warnings?.length && (
            <span className="rb-proof-warning" title={row.warnings.map((value) => WARNING_LABELS[value] ?? value).join('、')}>
              <AlertTriangle size={13} />{row.warnings.length} 项问题
            </span>
          )}
        </>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 48,
      onCell: () => ({ onClick: (event) => event.stopPropagation() }),
      render: (_value, row) => (
        <Button
          type="text"
          size="small"
          aria-label={'第 ' + (row.id + 1) + ' 行操作'}
          icon={<MoreHorizontal size={16} />}
          onClick={(event) => {
            const rect = event.currentTarget.getBoundingClientRect();
            setContextMenu({ row, x: rect.left, y: rect.bottom });
          }}
        />
      ),
    },
  ];

  const actions = (
    <>
      <Button size="small" disabled={loading || saving || dirty} onClick={reload}>刷新译文</Button>
      <Button size="small" disabled={mutationDisabled || !data?.total} onClick={() => { if (data) setExportConfirm({ cache_token: data.cache_token, project: projectIdentity }); }}>导出译文</Button>
      <Button size="small" disabled={mutationDisabled || !items.length} onClick={() => { if (data) { setReplaceSnapshot({ cache_token: data.cache_token, rows: selected.size ? items.filter((row) => selected.has(row.id)) : items }); setReplaceOpen(true); } }}>批量替换</Button>
      <Button size="small" disabled={mutationDisabled || !selected.size} onClick={() => confirmSelection('retranslate')}>重译选中行</Button>
      {retranslateRunning && <Button size="small" danger disabled={retranslate.state === 'CANCELLING'} onClick={() => void cancelRetranslate()}>取消重译</Button>}
      <Button size="small" disabled={mutationDisabled || !selected.size} onClick={() => confirmSelection('reset')}>重置选中译文</Button>
      <Button size="small" disabled={loading || !data} onClick={() => void showReport()}>质量报告</Button>
      {(['proofread', 'polish'] as const).map((task) => (
        <Button size="small" key={task} disabled={mutationDisabled || !selected.size}
          onClick={() => {
            const rows = items.filter((row) => selected.has(row.id));
            if (data) setQualityConfirm({ task, cache_token: data.cache_token, ids: rows.map((row) => row.id), rows, project: projectIdentity });
          }}>
          {t(task === 'polish' ? 'polish_action' : 'proofread_action')}
        </Button>
      ))}
      {qualityRunning && <Button size="small" danger disabled={cancelling} onClick={() => void cancelQuality()}>{t('quality_cancel')}</Button>}
    </>
  );

  const qualityPercent = data?.quality_reports?.at(-1)?.total_count
    ? 100 * (data.quality_reports.at(-1)?.completed_count ?? 0) / (data.quality_reports.at(-1)?.total_count ?? 1)
    : 0;

  return (
    <div className={embedded ? 'proofreading-page rb-embedded' : 'proofreading-page rb-page'}>
      <div className="rb-page-scroll">
        {!embedded && (
          <PageHeader
            title="平行校对台"
            description="原文与译文并排阅读，让每一句更准确、更自然。"
          />
        )}
        <div className="rb-proofreading-actions">{actions}</div>
        {readonly && <Banner tone="info">当前任务正在运行，译文可阅读；任务结束后可以编辑和保存。</Banner>}
        {qualityRunning && <div className="rb-proofreading-task"><Progress percent={qualityPercent} showInfo={false} size="small" /><span>{t(cancelling ? 'quality_cancelling' : 'quality_running')}</span></div>}
        {retranslate.state !== 'IDLE' && <div className="rb-proofreading-task">重译：{retranslate.done ?? 0} / {retranslate.total ?? 0} · 已保存 {retranslate.updated ?? 0} · 失败 {retranslate.failed ?? 0} · {retranslateRunning ? retranslate.state === 'CANCELLING' ? '等待已发出的请求结束…' : '处理中…' : retranslate.state === 'FAILED' ? '失败：' + retranslate.error : retranslate.state === 'CANCELLED' ? '已取消' : '已完成'}</div>}
        {error && <Banner tone="warning">{error}</Banner>}
        <form className="proofreading-filters" onSubmit={(event) => { event.preventDefault(); setPage(1); setSearch(query.trim()); }}>
          <div className="rb-proof-search-row">
          <Space.Compact className="rb-proof-search">
            <Input
              aria-label="搜索原文或译文"
              placeholder="搜索原文、译文或文件…"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault();
                  const keyword = query.trim();
                  if (keyword !== search) { setPage(1); setSearch(keyword); return; }
                  stepSearchMatch(event.shiftKey ? -1 : 1);
                }
              }}
            />
            <Tooltip title={t('proofreading_match_prev')}>
              <Button
                aria-label={t('proofreading_match_prev')}
                disabled={loading || !!searchError || !matches.length}
                icon={<ChevronUp size={14} />}
                onClick={() => stepSearchMatch(-1)}
              />
            </Tooltip>
            <Tooltip title={t('proofreading_match_next')}>
              <Button
                aria-label={t('proofreading_match_next')}
                disabled={loading || !!searchError || !matches.length}
                icon={<ChevronDown size={14} />}
                onClick={() => stepSearchMatch(1)}
              />
            </Tooltip>
          </Space.Compact>
          <Button htmlType="submit" disabled={loading}>搜索</Button>
          <Checkbox checked={searchRegex} onChange={(event) => setSearchRegex(event.target.checked)}>{t('proofreading_regex_toggle')}</Checkbox>
          <Checkbox checked={onlyIssues} onChange={(event) => { setOnlyIssues(event.target.checked); setPage(1); }}>仅看问题</Checkbox>
          <Select
            aria-label="问题类型"
            value={warning}
            options={warningOptions}
            onChange={(value) => { setWarning(value ?? ''); setPage(1); }}
            style={{ width: 160 }}
          />
          </div>
          {(search || searchError) && (
          <span className="rb-metric-note" aria-live="polite">
            {searchError ? t('proofreading_regex_invalid').replace('{error}', searchError)
              : !search ? ''
                : matches.length ? t('proofreading_match_counter').replace('{current}', String(matchIndex >= 0 ? matchIndex + 1 : 1)).replace('{total}', String(matches.length))
                  : t('proofreading_match_none')}
          </span>
          )}
          <details className="rb-proof-filter-details">
          <summary>更多筛选{filterActive ? ' · 已启用' : ''}</summary>
          <div className="proofreading-filter-row">
          <Select
            mode="multiple"
            aria-label={t('proofreading_filter_statuses')}
            placeholder={t('proofreading_filter_statuses_placeholder')}
            maxTagCount="responsive"
            value={filterStatus}
            options={Object.entries(STATUS_LABELS).map(([value, label]) => ({ value, label }))}
            onChange={(values) => applyFilter({ statuses: values })}
          />
          <Select
            mode="multiple"
            aria-label={t('proofreading_filter_files')}
            placeholder={t('proofreading_filter_files_placeholder')}
            maxTagCount="responsive"
            value={filterFiles}
            options={(data?.files ?? []).map((path) => ({ value: path, label: path || '未分类' }))}
            onChange={(values) => applyFilter({ files: values })}
          />
          <Select
            mode="multiple"
            aria-label={t('proofreading_filter_warnings')}
            placeholder={t('proofreading_filter_warnings_placeholder')}
            maxTagCount="responsive"
            value={filterWarnings}
            options={warningFilterOptions}
            onChange={(values) => applyFilter({ warnings: values })}
          />
          <Select
            mode="multiple"
            aria-label={t('proofreading_filter_terms')}
            placeholder={t('proofreading_filter_terms_placeholder')}
            maxTagCount="responsive"
            value={filterTerms}
            options={termOptions.map((term: GlossaryTerm) => ({ value: term.key, label: term.label }))}
            onChange={(values) => applyFilter({ terms: values })}
          />
          {termOptions.length ? null : (
            <Tooltip title={t('proofreading_filter_terms_empty')}>
              <span className="rb-proof-filter-hint" aria-label={t('proofreading_filter_terms_empty')}><Info size={14} /></span>
            </Tooltip>
          )}
          {(termOptions.length || filterActive) ? (
            <span className="rb-tool-actions">
              <Button type="link" size="small" onClick={() => applyFilter({ terms: termOptions.map((term: GlossaryTerm) => term.key) })}>{t('proofreading_filter_select_all')}</Button>
              <Button type="link" size="small" disabled={!filterActive} onClick={() => applyFilter({ statuses: [], files: [], warnings: [], terms: [] })}>{t('proofreading_filter_clear')}</Button>
            </span>
          ) : null}
          </div>
          <p className="rb-proof-filter-scope">{t('proofreading_filter_scope_note')}</p>
          </details>
        </form>
        <div className="rb-proofreading-selection">
          {filterActive && <Tooltip title={t('proofreading_filter_scope_note')}><span className="rb-proof-filter-hint" aria-hidden="true">筛选已生效</span></Tooltip>}
          <Button type="link" size="small" disabled={!selected.size} onClick={() => copyPairs(items.filter((row) => selected.has(row.id)))}>{t('proofreading_copy_pairs')}</Button>
          <Button type="link" size="small" disabled={saving || loading || !data?.total} onClick={() => void exportFilteredRows()}>{t('proofreading_filter_export')}</Button>
          <span className="rb-proof-filter-hint">{t('proofreading_select_hint')}</span>
        </div>
        {loading && <div className="rb-proof-loading" role="status" aria-live="polite">
          <Spin size="small" />
          <span>{onlyIssues || warning ? t('proofreading_checking').replace('{checked}', (data?.checked ?? 0).toLocaleString()).replace('{total}', (data?.check_total ?? 0).toLocaleString()) : t('proofreading_loading')}</span>
        </div>}
        <div className="rb-proof-table-scroll" ref={scrollRef} aria-busy={loading}>
          <Table<ProofreadingRow>
            ref={tableRef}
            className="rb-proof-table"
            size="small"
            bordered
            tableLayout="fixed"
            rowKey="id"
            columns={columns}
            dataSource={visibleItems}
            pagination={false}
            loading={false}
            virtual={true}
            scroll={{ x: scrollX, y: scrollY }}
            locale={{
              emptyText: (
                <div className="rb-proof-empty" style={{ minHeight: Math.max(80, scrollY - 32) }}>
                  {loading ? t('proofreading_loading') : data ? t('proofreading_empty_filtered') : t('proofreading_empty_before')}
                </div>
              ),
            }}
            rowClassName={() => 'rb-proofreading-row'}
            rowSelection={{
              columnWidth: 34,
              selectedRowKeys: Array.from(selected),
              onChange: (keys) => setSelected(new Set(keys.map(Number))),
              onSelect: (record) => {
                setActive(record.id);
                selectionAnchor.current = record.id;
              },
              getCheckboxProps: () => ({ disabled: loading || saving, 'aria-label': '选择行' }),
            }}
            onRow={(row) => ({
              'data-selected': selected.has(row.id) ? 'true' : undefined,
              'aria-selected': selected.has(row.id),
              tabIndex: 0,
              onClick: (event) => {
                selectRow(row, event);
                (event.currentTarget as HTMLElement).focus();
              },
              onKeyDown: (event) => rowKeyDown(event, row),
              onContextMenu: (event) => {
                event.preventDefault();
                if (!selected.has(row.id)) selectRow(row, event);
                setContextMenu({ row, x: event.clientX, y: event.clientY });
              },
            })}
          />
        </div>
        <footer className="proofreading-pagination">
          <span>{data ? `${(filterActive ? filteredItems.length : data.matched ?? 0).toLocaleString()}${data.scan_complete === false ? '＋' : ''} 条符合条件 · 共 ${(data.total ?? 0).toLocaleString()} 条` : '原译对照'}{filterActive ? ` · 已筛选 ${visibleItems.length} / ${items.length} 行（本页）` : ''}{selected.size ? ` · 已选 ${selected.size} 条` : ''}</span>
          <div className="proofreading-toolbar">
            <Select
              aria-label="每页条数"
              size="small"
              style={{ width: 100 }}
              value={String(limit)}
              options={['25', '50', '100'].map((value) => ({ value, label: value + ' 条 / 页' }))}
              onChange={(value) => { setLimit(Number(value)); setPage(1); }}
            />
            <InputNumber
              aria-label="跳转页码"
              size="small"
              style={{ width: 64 }}
              min={1}
              max={filterActive ? (clientPage?.pages ?? 1) : Math.max(1, Math.ceil((data?.matched ?? 0) / limit))}
              value={page}
              onChange={(value) => { if (typeof value === 'number') setPage(value); }}
            />
            <Button size="small" disabled={loading || page <= 1} onClick={() => setPage((value) => value - 1)}>上一页</Button>
            <span>{filterActive ? (clientPage?.page ?? 1) : data?.page ?? 1} / {filterActive ? (clientPage?.pages ?? 1) : Math.max(1, Math.ceil((data?.matched ?? 0) / limit))}</span>
            <Button
              size="small"
              disabled={loading || !data || (filterActive ? (clientPage?.page ?? 1) >= (clientPage?.pages ?? 1) : page * limit >= data.matched)}
              onClick={() => setPage((value) => value + 1)}
            >
              下一页
            </Button>
          </div>
        </footer>
        <div className="rb-proofreading-location" title={activeRow?.file_path}>
          {activeRow ? activeRow.file_path + ':' + activeRow.row : '选择行后显示文件与行号'}
          <span>编辑确认后自动保存缓存；导出译文才会写入文件。</span>
        </div>
      </div>
      {contextMenu && (
        <Dropdown
          key={contextMenu.x + ':' + contextMenu.y + ':' + contextMenu.row.id}
          open
          onOpenChange={(opened) => { if (!opened) setContextMenu(null); }}
          menu={{ items: contextMenuItems(contextMenu.row), onClick: () => setContextMenu(null) }}
          placement="bottomLeft"
          autoAdjustOverflow
          getPopupContainer={() => document.body}
        >
          <span style={{ position: 'fixed', left: contextMenu.x, top: contextMenu.y, width: 1, height: 1 }} />
        </Dropdown>
      )}
      {locationOpen && (
        <Modal open onCancel={() => setLocationOpen(false)} title="定位译文" width={900} footer={null}>
          {locationError ? <Banner tone="warning">{locationError}</Banner> : !location ? <p>正在读取目标行…</p> : <>
            <p className="rb-proofreading-location">{location.path}:{location.row}</p>
            <Button size="small" onClick={() => void copyText(location.path)}>复制文件路径</Button>
            <pre className="rb-proof-context">{location.lines.map((line) => <div key={line.number} data-target={line.number === location.row}>{String(line.number).padStart(6)}  {line.text}</div>)}</pre>
          </>}
        </Modal>
      )}
      {edit && (
        <Modal
          open
          onCancel={closeEdit}
          title="编辑译文"
          width={960}
          centered
          classNames={{ body: 'rb-proof-editor' }}
          footer={
            <div className="rb-dialog-actions">
              <Button onClick={closeEdit}>取消</Button>
              <Button type="primary" disabled={saving || readonly || !dirty || editProjectChanged} onClick={() => void saveEdit()}>保存译文</Button>
            </div>
          }
        >
          <div
            onKeyDown={(event: KeyboardEvent<HTMLDivElement>) => {
              if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
                event.preventDefault();
                void saveEdit();
              }
            }}
          >
            {editProjectChanged && <Banner tone="warning">项目已切换，未保存的译文已保留。请复制译文后关闭编辑。</Banner>}
            <p className="rb-metric-note">{edit.file_path}:{edit.row} · Ctrl + Enter 保存</p>
            <div className="rb-proof-bilingual-editor">
              <label>
                <span>原文</span>
                <Input.TextArea readOnly value={edit.src} autoSize={{ minRows: 10, maxRows: 16 }} />
              </label>
              <label>
                <span>译文</span>
                <Input.TextArea
                  id="proofreading-draft"
                  value={draft}
                  disabled={saving || readonly}
                  autoSize={{ minRows: 10, maxRows: 16 }}
                  onChange={(event) => setDraft(event.target.value)}
                />
              </label>
            </div>
          </div>
        </Modal>
      )}
      {selectionConfirm && <Dialog title={selectionConfirm.action === 'retranslate' ? '重新翻译' : selectionConfirm.action === 'reset' ? '重置选中译文' : '确认译文无误'} confirmText={selectionConfirm.action === 'retranslate' ? '开始重译' : '确认并保存'} onCancel={() => { if (!saving) setSelectionConfirm(null); }} onConfirm={mutationDisabled || selectionConfirm.project !== projectIdentity ? undefined : () => void applySelection()}>
        <p>{selectionConfirm.action === 'retranslate' ? '使用当前翻译接口重新处理选中行，会消耗额度；失败行保留原译文。' : selectionConfirm.action === 'reset' ? '将清空选中行的译文、重试记录，并设为待翻译。' : '保留已有译文，清除重试次数和对应失败记录。'}共 {selectionConfirm.rows.length} 条，成功后保存到缓存。</p>
      </Dialog>}
      {exportConfirm && <Dialog title="导出译文" confirmText="写入译文文件" onCancel={() => { if (!saving) setExportConfirm(null); }} onConfirm={mutationDisabled || exportConfirm.project !== projectIdentity ? undefined : () => void exportRows()}>
        <p>将当前缓存中的全部译文按原文件格式写入输出目录，可能覆盖已有译文文件。当前筛选不会限制导出范围。</p>
        <p>{data?.cache_folder}</p>
      </Dialog>}
      {exportRowsState && (
        <Dialog
          title={t('proofreading_filter_export')}
          confirmText="复制到剪贴板"
          onCancel={() => setExportRowsState(null)}
          onConfirm={() => void copyFilteredExport()}
        >
          <p>{t('proofreading_filter_export_confirm').replace('{count}', String(exportRowsState.count))}</p>
          {exportRowsState.truncated && <Banner tone="info">{t('proofreading_filter_export_truncated').replace('{loaded}', String(exportRowsState.count)).replace('{limit}', '100').replace('{total}', String(data?.matched ?? exportRowsState.count))}</Banner>}
          <p className="rb-metric-note">{t('proofreading_filter_export_copied')}{exportRowsState.filename}</p>
          <Input.TextArea readOnly value={exportRowsState.text} autoSize={{ minRows: 6, maxRows: 12 }} />
        </Dialog>
      )}
      {reportOpen && (
        <Modal open onCancel={() => setReportOpen(false)} title="质量报告" width={720} footer={null}>
          {reportError ? <Banner tone="warning">{reportError}</Banner> : !report ? <p>正在读取报告…</p> : <>
            <div className="rb-quality-summary">
              <strong>失败 {report.failed_count}</strong>
              <strong>回退 {report.fallback_count}</strong>
              <strong>对齐异常 {report.line_mismatch_count}</strong>
            </div>
            <p>{Object.entries(report.error_type_counts).map(([key, count]) => key + ': ' + count).join(' · ') || '没有记录到翻译失败原因。'}</p>
            {report.item_references.length ? <div className="rb-quality-items">{report.item_references.map((row) => (
              <Checkbox
                key={row.item_index}
                checked={reportSelection.has(row.item_index)}
                onChange={() => setReportSelection((previous) => {
                  const next = new Set(previous);
                  if (next.has(row.item_index)) next.delete(row.item_index); else next.add(row.item_index);
                  return next;
                })}
              >
                {`#${row.item_index + 1} ${row.reference} · ${row.error_types.join('、')} · ${row.source_preview}`}
              </Checkbox>
            ))}</div> : <p>没有需要处理的条目。</p>}
            <Button size="small" disabled={!reportSelection.size || qualityRunning || readonly || !data?.cache_token} onClick={() => {
              if (!data) return;
              setQualityConfirm({ task: 'proofread', cache_token: data.cache_token, ids: [...reportSelection], project: projectIdentity });
              setReportOpen(false);
            }}>对选中项执行 AI 校对</Button>
          </>}
          {(data?.quality_reports ?? []).map((report) => (
            <details className="rb-quality-report" key={report.task_type}>
              <summary>AI 处理记录 · {t(report.task_type === 'POLISHER' ? 'polish_action' : 'proofread_action')} · {t(report.state === 'COMPLETED' ? 'quality_completed' : report.state === 'FAILED' ? 'quality_failed' : report.state === 'CANCELLED' ? 'quality_cancelled' : 'quality_running')}</summary>
              <p>{t('quality_summary').replace('{completed}', String(report.completed_count)).replace('{total}', String(report.total_count)).replace('{updated}', String(report.updated_count)).replace('{failed}', String(report.failed_count)).replace('{skipped}', String(report.skipped_count))}</p>
              <Progress percent={report.total_count > 0 ? 100 * report.completed_count / report.total_count : 0} showInfo={false} size="small" />
              {report.error_message && <Banner tone="warning">{report.error_message}</Banner>}
              {!!report.failures?.length && <ul>{report.failures.map((failure, index) => <li key={index}>#{failure.item_index + 1} · {failure.reason}</li>)}</ul>}
            </details>
          ))}
        </Modal>
      )}
      {qualityConfirm && (
        <Dialog title={t(qualityConfirm.task === 'polish' ? 'polish_action' : 'proofread_action')} confirmText={t('quality_confirm')}
          onCancel={() => { if (!saving) setQualityConfirm(null); }}
          onConfirm={saving || readonly || dirty || qualityConfirm.project !== projectIdentity ? undefined : () => void startQuality()}>
          <p>{t('quality_confirm_hint').replace('{count}', String(qualityConfirm.ids.length))}</p>
        </Dialog>
      )}
      {replaceOpen && (
        <Dialog
          title="批量替换译文"
          confirmText={replacePlan ? '替换并保存' : needPreviewAll ? '预览全部结果' : '替换并保存'}
          onCancel={closeReplace}
          onConfirm={!find || saving || readonly || !planPreview.ok ? undefined
            : needPreviewAll && !replacePlan ? () => void previewReplaceAll()
              : replacePlan?.rows.length ? () => void replaceRows(replacePlan) : undefined}
        >
          <p>
            作用范围：{replaceScope === 'selected' ? t('proofreading_batch_replace_scope_selected').replace('{count}', String(selected.size))
              : replaceScope === 'page' ? t('proofreading_batch_replace_scope_page').replace('{count}', String(items.length))
                : t('proofreading_batch_replace_scope_all').replace('{count}', String(data?.matched ?? items.length))}
            {replaceScope === 'all' ? '（先按当前筛选拉回全部命中行）' : ''}
          </p>
          <div className="proofreading-replacement-grid">
            <label>
              <span>查找</span>
              <Input value={find} disabled={saving} placeholder="需要替换的内容" onChange={(event) => { setFind(event.target.value); setReplacePlan(null); }} />
            </label>
            <label>
              <span>替换为</span>
              <Input value={replacement} disabled={saving} placeholder="留空可删除匹配内容" onChange={(event) => { setReplacement(event.target.value); setReplacePlan(null); }} />
            </label>
          </div>
          <Checkbox checked={caseSensitive} disabled={saving} onChange={(event) => { setCaseSensitive(event.target.checked); setReplacePlan(null); }}>区分大小写</Checkbox>
          <Checkbox checked={replaceRegex} disabled={saving} onChange={(event) => { setReplaceRegex(event.target.checked); setReplacePlan(null); }}>{t('proofreading_batch_replace_regex')}</Checkbox>
          <label className="proofreading-scope">
            <span>{t('proofreading_batch_replace_scope')}</span>
            <Select
              aria-label={t('proofreading_batch_replace_scope')}
              value={replaceScope}
              disabled={saving}
              onChange={(value) => { setReplaceScope(value ?? 'page'); setReplacePlan(null); }}
              options={[
                ...(selected.size ? [{ value: 'selected', label: t('proofreading_batch_replace_scope_selected').replace('{count}', String(selected.size)) }] : []),
                { value: 'page', label: t('proofreading_batch_replace_scope_page').replace('{count}', String(items.length)) },
                { value: 'all', label: t('proofreading_batch_replace_scope_all').replace('{count}', String(data?.matched ?? items.length)) },
              ]}
            />
          </label>
          {find && !planPreview.ok && <Banner tone="warning">{t('proofreading_batch_replace_regex_invalid').replace('{error}', String(planPreview.error ?? ''))}</Banner>}
          {waitingForAll && <p className="rb-metric-note">{t('proofreading_batch_replace_impact_hint')}</p>}
          {replacePlan && <p className="rb-metric-note">{replacePlan.rows.length ? t('proofreading_batch_replace_impact').replace('{rows}', String(replacePlan.rows.length)).replace('{matches}', String(replacePlan.matchCount)) : t('proofreading_batch_replace_impact_none')}</p>}
          {saving && <p>{replaceBusy ? '正在保存 ' + replaceBusy + ' …' : '正在计算影响范围…'}</p>}
          <p className="rb-metric-note">{t('proofreading_batch_replace_regex_tip')}</p>
        </Dialog>
      )}
    </div>
  );
}
