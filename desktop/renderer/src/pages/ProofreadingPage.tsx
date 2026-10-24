/** 平行校对台：分页读取真实缓存，保存前由服务端检查项目和译文版本。 */
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Button, Checkbox, Dropdown, Input, InputNumber, Modal, Progress, Select, Space, Spin, Table, Tag, Tooltip } from 'antd';
import type { ColumnsType, TableRef } from 'antd/es/table';
import type { MenuProps } from 'antd';
import { request, apiBase } from '../api';
import { focusTableRow } from '../components/tableFocus';
import type { AppState } from '../useAppState';
import { MoreHorizontal, AlertTriangle, ChevronDown, ChevronLeft, ChevronRight, ChevronUp, Copy, Info, Pencil, RotateCcw } from 'lucide-react';
import type { MouseEvent, KeyboardEvent } from 'react';
import { Banner, Dialog, PageHeader } from '../ui';
import { useT } from '../i18n';
import {
  NO_WARNING, collectGlossaryTerms, compilePattern, exportFilename, exportText,
  matchRowIndices, replaceImpact, stepMatch,
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
  /** 本页暂存、尚未写入缓存的译文（覆盖服务端 dst 显示）。 */
  staged?: boolean;
}

/** 一个图片/视频落地结果：relative 是 game/ 下的相对路径。 */
interface SceneAsset {
  kind: 'image' | 'video' | 'none';
  relative: string;
  note: string;
}

interface SceneLayer extends SceneAsset {
  tag: string;
}

/** 一行台词对应的画面。reason 非空表示静态还原失败。 */
interface SceneStage {
  file: string;
  line: number;
  scene_line: number;
  scene_tag: string;
  background: SceneAsset | null;
  layers: SceneLayer[];
  reason: string;
}

interface SceneInfo {
  ok: boolean;
  source: { file: string; line: number; label: string };
  speaker: { src: string; dst: string };
  stage: SceneStage | null;
  reason: string;
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

/** 批量保存时每次请求最多带多少行，与后端 BatchEditRequest 的上限一致。 */
const BATCH_CHUNK = 100;

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
  const locationBoxRef = useRef<HTMLPreElement | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [edit, setEdit] = useState<(ProofreadingRow & { cache_token: string; project_identity: string }) | null>(null);
  const [discardEdit, setDiscardEdit] = useState<null | { action: 'close' } | { action: 'open'; row: ProofreadingRow }>(null);
  const [draft, setDraft] = useState('');
  // 「编辑译文」里的画面：打开某一行时按源脚本静态还原一次，改译文不重查。
  const [scene, setScene] = useState<SceneInfo | null>(null);
  const [sceneLoading, setSceneLoading] = useState(false);
  const [sceneError, setSceneError] = useState('');
  // 画面里的台词条显示什么：译文（默认）/ 原文 / 双语对照
  const [overlayMode, setOverlayMode] = useState<'dst' | 'src' | 'both'>('dst');
  /**
   * 已暂存、尚未写入缓存的译文：id → {version, dst}。
   * 改多行只写一次缓存，也只让服务端重新检查一次问题项。
   */
  const [pending, setPending] = useState<Record<number, { version: string; dst: string }>>({});
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
  const filterSignature = useRef('');
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
  // 编辑框里还没暂存的改动 vs. 页面级未保存（含已暂存、待写入缓存的行）
  const draftDirty = Boolean(edit && draft !== edit.dst);
  const pendingCount = Object.keys(pending).length;
  const dirty = draftDirty || pendingCount > 0;
  dirtyRef.current = dirty;

  useEffect(() => {
    onDirtyChange?.(dirty);
    return () => onDirtyChange?.(false);
  }, [dirty, onDirtyChange]);

  useEffect(() => {
    setData(null);
    filterSignature.current = '';
    setSelected(new Set());
    setPending({});
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
    // 更多筛选由服务端对整份缓存求值，这里只负责把多选值按重复参数传过去。
    filterStatus.forEach((value) => params.append('statuses', value));
    filterFiles.forEach((value) => params.append('files', value));
    filterWarnings.forEach((value) => params.append('warnings', value));
    filterTerms.forEach((value) => params.append('terms', value));
    params.set('incremental', 'true');
    const signature = params.toString();
    let timer: number | undefined;
    setLoading(true);
    // 不清空已有表格：润色/校对运行期间每 2 秒都会刷新一次，清空会让
    // 「已检查 N 条」闪回「正在载入翻译缓存」，也会把用户的选择清掉。
    setError('');
    setReplacePlan(null);
    setReplaceBusy('');
    const load = async () => {
      try {
        const result = await request<ProofreadingData>('/api/proofreading?' + params, { signal: controller.signal });
        if (id !== requestId.current) return;
        setData(result);
        // 只有筛选条件变化才重置选择；润色/校对期间的后台轮询不能把用户
        // 正在勾选的行清掉。
        if (filterSignature.current !== signature) {
          filterSignature.current = signature;
          setSelected(new Set()); setActive(null); selectionAnchor.current = null;
        }
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

  }, [state.ready, projectIdentity, page, limit, search, status, file, onlyIssues, warning, filterStatus, filterFiles, filterWarnings, filterTerms, refresh, state.translation.engine_status, state.translation.stop_barrier, state.translation.single_tasks]);

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
    if (draftDirty) { setDiscardEdit({ action: 'close' }); return; }
    setEdit(null);
  };

  /** 「保存」只暂存到本页：改多少行都不用等，稍后一次写入缓存。 */
  const stageEdit = () => {
    if (!data || !edit || saving || readonly || editProjectChanged) return;
    const { id, version, dst: editing } = edit;
    const nextDraft = draft;
    // 与磁盘上的译文比较：改回原样就把这一行从暂存里摘掉，不留「待保存」标记。
    const serverDst = data.items.find((row) => row.id === id)?.dst ?? editing;
    setPending((previous) => {
      const next = { ...previous };
      if (nextDraft === serverDst) delete next[id];
      else next[id] = { version, dst: nextDraft };
      return next;
    });
    setEdit(null);
    if (nextDraft === serverDst) state.pushToast('info', '已还原为缓存中的译文。');
    else state.pushToast('success', '译文已暂存，点「保存修改」统一写入缓存。');
  };

  /**
   * 编辑弹窗里的「上一个 / 下一个」：有草稿先按暂存规则收进 pending，再切相邻行，
   * 这样连续改多行不用每次点暂存、关窗、再点下一行。
   */
  const stepEdit = (delta: number) => {
    if (!edit || saving || readonly || editProjectChanged) return;
    const index = items.findIndex((row) => row.id === edit.id);
    if (index < 0) return;
    const target = items[index + delta];
    if (!target) {
      state.pushToast('info', delta > 0 ? '已经是最后一条了。' : '已经是第一条了。');
      return;
    }
    if (draftDirty && data) {
      const { id, version } = edit;
      const nextDraft = draft;
      const serverDst = data.items.find((row) => row.id === id)?.dst ?? edit.dst;
      setPending((previous) => {
        const next = { ...previous };
        if (nextDraft === serverDst) delete next[id];
        else next[id] = { version, dst: nextDraft };
        return next;
      });
    }
    setEdit({ ...target, cache_token: data?.cache_token ?? '', project_identity: projectIdentity });
    setDraft(target.dst);
    setDiscardEdit(null);
  };

  /** 一次写入全部暂存译文：只落盘一次，也只重新检查一次问题项。 */
  const savePending = async () => {    if (!data || !pendingCount || saving || readonly) return;
    const identity = projectRef.current;
    const rows = Object.entries(pending).map(([id, entry]) => ({
      id: Number(id), version: entry.version, dst: entry.dst,
    }));
    setSaving(true);
    try {
      const result = await request<{ changed: number }>('/api/proofreading/items', {
        method: 'PATCH', body: JSON.stringify({ cache_token: data.cache_token, rows }),
      });
      if (identity !== projectRef.current) return;
      setPending({});
      state.pushToast('success', '已保存 ' + result.changed + ' 条译文，只重新检查这些行的问题项。');
      reload();
    } catch (failure) {
      state.pushToast('error', failure instanceof Error ? failure.message : String(failure));
    } finally { setSaving(false); }
  };

  const discardPending = () => {
    if (!pendingCount || saving) return;
    setPending({});
    state.pushToast('info', '已放弃暂存的译文修改。');
  };

  const replaceRows = async (plan: { rows: { id: number; version: string; dst: string }[]; matchCount: number }) => {
    if (!replaceSnapshot || !find || saving || readonly || !plan.rows.length) return;
    const identity = projectRef.current;
    const token = replaceSnapshot.cache_token;
    setSaving(true);
    setReplaceBusy('');
    let changed = 0;
    try {
      // 逐块调用批量保存：一次请求写一整块，避免每行都重写一次缓存。
      for (let start = 0; start < plan.rows.length; start += BATCH_CHUNK) {
        const chunk = plan.rows.slice(start, start + BATCH_CHUNK);
        setReplaceBusy(String(start + chunk.length) + '/' + String(plan.rows.length));
        const result = await request<{ changed: number }>('/api/proofreading/items', {
          method: 'PATCH', body: JSON.stringify({ cache_token: token, rows: chunk }),
        });
        changed += Number(result.changed ?? 0);
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

  // 列表显示叠加本页暂存的译文，用户改完能看到结果，但还没写进缓存。
  const items = useMemo(() => (data?.items ?? []).map((row) => {
    const staged = pending[row.id];
    if (!staged || staged.dst === row.dst) return row;
    return { ...row, dst: staged.dst, staged: true };
  }), [data, pending]);
  const activeRow = items.find((row) => row.id === active);

  // 筛选维度（状态 / 文件 / 问题类型 / 术语表）全部由服务端对整份缓存求值，
  // 分页、匹配数与扫描进度都以服务端返回为准，前端不再只筛当前页。
  const filterActive = Boolean(filterStatus.length || filterFiles.length || filterWarnings.length || filterTerms.length);
  const scanFilter = onlyIssues || Boolean(warning) || filterWarnings.length > 0 || filterTerms.length > 0;
  const pageCount = Math.max(1, Math.ceil((data?.matched ?? 0) / limit));
  const termOptions = useMemo(() => collectGlossaryTerms(items), [items]);
  /** 已选术语可能不在当前页带来的选项里，用 key 兜底显示，避免多选标签丢失。 */
  const termSelectOptions = useMemo(() => {
    const options = termOptions.map((term) => ({ value: term.key, label: term.label }));
    const known = new Set(options.map((option) => option.value));
    filterTerms.filter((key) => !known.has(key)).forEach((key) => {
      options.push({ value: key, label: key.split('\u0000').join(' -> ') });
    });
    return options;
  }, [termOptions, filterTerms]);
  const warningOptions = useMemo(() => [
    { value: '', label: '全部问题类型' },
    ...Object.keys(WARNING_LABELS).map((value) => ({ value, label: WARNING_LABELS[value] ?? value })),
  ], []);
  /** 「问题类型」多选：完整列出检查类型，含「无警告」占位；选项不再依赖当前页碰巧出现的问题。 */
  const warningFilterOptions = useMemo(
    () => [...Object.keys(WARNING_LABELS), NO_WARNING].map((value) => ({ value, label: value === NO_WARNING ? t('proofreading_filter_no_warning') : WARNING_LABELS[value] ?? value })),
    [t],
  );

  // 正则搜索：非法正则只提示，不影响列表；搜索永远只作用于当前筛选结果。
  const searchPattern = compilePattern(search, { regex: searchRegex });
  const searchError = searchPattern.ok ? '' : searchPattern.error;
  const matches = useMemo(
    () => (searchError || !search ? [] : matchRowIndices(items, search, { regex: searchRegex })),
    [items, search, searchRegex, searchError],
  );
  const matchedRows = matches.map((index) => items[index]).filter(Boolean);
  /** 批量替换对话框里的实时状态：非法正则不允许继续，影响范围由 previewReplace 计算。 */
  const planPreview = compilePattern(find, { regex: replaceRegex, caseSensitive });
  const needPreviewAll = Boolean(find) && planPreview.ok && (replaceScope === 'all' || items.length >= 100);
  const waitingForAll = needPreviewAll && !replacePlan;

  /** 批量替换的「全部结果」作用域与筛选导出共用：按当前服务端筛选拉回全部命中行。 */
  const loadAllRows = async () => {
    if (!data) return { rows: items, truncated: false };
    const params = new URLSearchParams({
      page: '1', limit: '100', query: search, status, file_path: file,
      only_issues: String(onlyIssues), warning, incremental: 'true',
    });
    filterStatus.forEach((value) => params.append('statuses', value));
    filterFiles.forEach((value) => params.append('files', value));
    filterWarnings.forEach((value) => params.append('warnings', value));
    filterTerms.forEach((value) => params.append('terms', value));
    let result = await request<ProofreadingData>('/api/proofreading?' + params);
    // 问题类型/术语筛选要先扫完整份缓存；轮询到 scan_complete 再取结果，避免只拿到前几行。
    while (result.scan_complete === false) {
      await new Promise((resolve) => window.setTimeout(resolve, 80));
      result = await request<ProofreadingData>('/api/proofreading?' + params);
    }
    return { rows: result.items ?? [], truncated: (result.matched ?? 0) > (result.items ?? []).length };
  };

  const focusMatch = (row: ProofreadingRow) => {
    setActive(row.id);
    setSelected(new Set([row.id]));
    // 搜索只在当前页命中的行里跳转，不需要再切服务端分页。
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
  /** 导出筛选结果：服务端已对整份缓存套用全部筛选维度，这里只负责拉回命中的行。 */
  const exportFilteredRows = async () => {
    if (saving || loading) return;
    setSaving(true);
    try {
      const loaded = await loadAllRows();
      if (!loaded.rows.length) {
        state.pushToast('info', t('proofreading_filter_export_empty'));
        return;
      }
      setExportRowsState({ filename: exportFilename(), text: exportText(loaded.rows), count: loaded.rows.length, truncated: loaded.truncated });
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
    // 只有编辑框里没暂存的改动才算「会丢」；已暂存的行可以随时继续改。
    if (draftDirty) { setDiscardEdit({ action: 'open', row }); return; }
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
  // 定位译文：算出目标所在的整条 translate 块，便于整块淡高亮。
  const locationBlock = useMemo(() => {
    if (!location) return null;
    const lines = location.lines;
    const head = (text: string) => /^translate\s/.test(text);
    const index = lines.findIndex((line) => line.number === location.row);
    if (index < 0) return null;
    let start = index;
    while (start > 0 && !head(lines[start].text)) start -= 1;
    if (!head(lines[start].text)) start = index;
    let end = index;
    while (end < lines.length - 1 && !head(lines[end + 1].text)) end += 1;
    return { start: lines[start].number, end: lines[end].number };
  }, [location]);
  // 打开即把目标行滚到可视区中间——否则 ±20 行里目标行常常落在折叠线以下。
  useLayoutEffect(() => {
    const box = locationBoxRef.current;
    if (!box || !location) return;
    const target = box.querySelector<HTMLElement>('[data-target="true"]');
    if (!target) return;
    box.scrollTop = Math.max(0, target.offsetTop - (box.clientHeight - target.offsetHeight) / 2);
  }, [location]);
  // 编辑译文弹窗里的画面：只在这一行变化时查一次，改文本不重查。
  useEffect(() => {
    if (!edit) {
      setScene(null);
      setSceneError('');
      setSceneLoading(false);
      return;
    }
    const identity = projectRef.current;
    setScene(null);
    setSceneError('');
    setSceneLoading(true);
    void (async () => {
      try {
        const result = await request<SceneInfo>('/api/proofreading/scene', {
          method: 'POST',
          body: JSON.stringify({
            cache_token: edit.cache_token,
            row: { id: edit.id, version: edit.version },
          }),
        });
        if (identity === projectRef.current) setScene(result);
      } catch (failure) {
        if (identity === projectRef.current) {
          setSceneError(failure instanceof Error ? failure.message : String(failure));
        }
      } finally {
        if (identity === projectRef.current) setSceneLoading(false);
      }
    })();
  }, [edit?.id, edit?.version, edit?.cache_token]);
  /** game/ 下的相对路径 → 后端可直接吐的地址；打包后窗口是 file:// 源，必须走绝对地址。 */
  const assetUrl = (relative: string) => `${apiBase()}/api/proofreading/asset?path=${encodeURIComponent(relative)}`;
  const sceneBackground = scene?.stage?.background ?? null;
  const sceneUsable = Boolean(sceneBackground?.relative);
  // 画面里的台词条：说话人优先用译名，正文直接用正在编辑的 draft，边改边看。
  const overlayName = scene?.speaker.dst || scene?.speaker.src || '';
  const overlayDst = draft || edit?.dst || '';
  const cancelRetranslate = async () => {
    try { setRetranslate(await request<typeof retranslate>('/api/proofreading/retranslate/cancel', { method: 'POST' })); }
    catch (failure) { state.pushToast('error', failure instanceof Error ? failure.message : String(failure)); }
  };
  const mutationDisabled = !state.ready || Boolean(readonly) || retranslateRunning || loading || saving || dirty;
  // 「编辑译文」不受暂存影响：暂存就是为了连续改多行，改完再一次保存。
  const editDisabled = !state.ready || Boolean(readonly) || loading || saving;
  // 只对「选中行里当前还有问题标记」的批次点亮确认入口，避免整页误点。
  const confirmableSelected = items.some((row) => selected.has(row.id) && Boolean(row.warnings?.length));

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
        disabled: editDisabled,
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
      {
        key: 'confirm',
        label: '确认译文无误',
        disabled: mutationDisabled,
        onClick: () => confirmSelection('confirm', targetRows),
      },
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
      render: (_value, row) => (
        <>
          <span className="rb-proof-target">{row.dst || '（空译文）'}</span>
          {row.staged ? <Tag className="rb-proof-staged" color="gold">待保存</Tag> : null}
        </>
      ),
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
      {pendingCount > 0 && (
        <>
          <Button size="small" type="primary" loading={saving} disabled={readonly} onClick={() => void savePending()}>
            {'保存修改（' + pendingCount + ' 行）'}
          </Button>
          <Button size="small" disabled={saving} onClick={discardPending}>放弃暂存</Button>
        </>
      )}
      <Button size="small" disabled={loading || saving || dirty} onClick={reload}>刷新译文</Button>
      <Button size="small" disabled={mutationDisabled || !data?.total} onClick={() => { if (data) setExportConfirm({ cache_token: data.cache_token, project: projectIdentity }); }}>导出译文</Button>
      <Button size="small" disabled={mutationDisabled || !items.length} onClick={() => { if (data) { setReplaceSnapshot({ cache_token: data.cache_token, rows: selected.size ? items.filter((row) => selected.has(row.id)) : items }); setReplaceOpen(true); } }}>批量替换</Button>
      <Button size="small" disabled={mutationDisabled || !selected.size} onClick={() => confirmSelection('retranslate')}>重译选中行</Button>
      {retranslateRunning && <Button size="small" danger disabled={retranslate.state === 'CANCELLING'} onClick={() => void cancelRetranslate()}>取消重译</Button>}
      <Button size="small" disabled={mutationDisabled || !selected.size} onClick={() => confirmSelection('reset')}>重置选中译文</Button>
      <Button size="small" disabled={mutationDisabled || !confirmableSelected} onClick={() => confirmSelection('confirm')}>确认选中无误</Button>
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

  // 「上一个 / 下一个」按当前筛选后的顺序走，序号对得上用户在表里看到的位置。
  const editIndex = edit ? items.findIndex((row) => row.id === edit.id) : -1;
  const editHasPrev = editIndex > 0;
  const editHasNext = editIndex >= 0 && editIndex < items.length - 1;
  const editPosition = editIndex >= 0 ? `${editIndex + 1} / ${items.length}` : '';

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
        {pendingCount > 0 && (
          <Banner tone="info">
            {'已暂存 ' + pendingCount + ' 行译文。可以继续改其它行，最后点「保存修改」一次写入缓存——问题项也只重新检查一次。'}
          </Banner>
        )}
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
          <summary>
             {t('proofreading_more_filters')}
             {filterActive ? <span className="rb-proof-filter-count">{t('proofreading_filters_active').replace('{count}', String(filterStatus.length + filterFiles.length + filterWarnings.length + filterTerms.length))}</span> : null}
           </summary>
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
            options={termSelectOptions}
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
          <span>{scanFilter ? t('proofreading_checking').replace('{checked}', (data?.checked ?? 0).toLocaleString()).replace('{total}', (data?.check_total ?? 0).toLocaleString()) : t('proofreading_loading')}</span>
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
            dataSource={items}
            pagination={false}
            loading={false}
            virtual={true}
            scroll={{ x: scrollX, y: scrollY }}
            locale={{
              emptyText: (
                <div className="rb-proof-empty" style={{ minHeight: Math.max(80, scrollY - 32) }}>
                  {loading ? t('proofreading_loading') : data && data.total > 0 ? t('proofreading_empty_filtered') : t('proofreading_empty_before')}
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
          <span>{data ? `${(data.matched ?? 0).toLocaleString()}${data.scan_complete === false ? '＋' : ''} 条符合条件 · 共 ${(data.total ?? 0).toLocaleString()} 条` : '原译对照'}{selected.size ? ` · 已选 ${selected.size} 条` : ''}</span>
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
              max={pageCount}
              value={page}
              onChange={(value) => { if (typeof value === 'number') setPage(value); }}
            />
            <Button size="small" disabled={loading || page <= 1} onClick={() => setPage((value) => value - 1)}>上一页</Button>
            <span>{data?.page ?? page} / {pageCount}</span>
            <Button
              size="small"
              disabled={loading || !data || (data.page ?? page) >= pageCount}
              onClick={() => setPage((value) => value + 1)}
            >
              下一页
            </Button>
          </div>
        </footer>
        <div className="rb-proofreading-location" title={activeRow?.file_path}>
          {activeRow ? activeRow.file_path + ':' + activeRow.row : '选择行后显示文件与行号'}
          <span>点「保存修改」才写入缓存；导出译文才会写入文件。</span>
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
            <div className="rb-locate-head">
              <span className="rb-locate-path" title={location.path}>{location.path}</span>
              <span className="rb-locate-row">第 {location.row} 行</span>
              <Button size="small" onClick={() => void copyText(location.path)}>复制文件路径</Button>
            </div>
            <pre className="rb-proof-context" ref={locationBoxRef}>
              {location.lines.map((line) => {
                const inBlock = Boolean(locationBlock && line.number >= locationBlock.start && line.number <= locationBlock.end);
                return (
                  <div key={line.number} data-target={line.number === location.row} data-block={inBlock}>
                    {String(line.number).padStart(6)}  {line.text}
                  </div>
                );
              })}
            </pre>
          </>}
        </Modal>
      )}
      {edit && (
        <Modal
          open
          onCancel={closeEdit}
          title="编辑译文"
          width={1240}
          centered
          classNames={{ body: 'rb-proof-editor' }}
          footer={
            <div className="rb-dialog-actions">
              <div className="rb-proof-editor-step">
                <Button icon={<ChevronLeft size={14} />} disabled={saving || !editHasPrev} onClick={() => stepEdit(-1)}>上一个</Button>
                <Button disabled={saving || !editHasNext} onClick={() => stepEdit(1)}>下一个 <ChevronRight size={14} /></Button>
                <span className="rb-metric-note">{editPosition}</span>
              </div>
              <Button onClick={closeEdit}>取消</Button>
              <Button type="primary" disabled={saving || readonly || !draftDirty || editProjectChanged} onClick={stageEdit}>暂存译文</Button>
            </div>
          }
        >
          <div
            onKeyDown={(event: KeyboardEvent<HTMLDivElement>) => {
              if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
                event.preventDefault();
                stageEdit();
              }
            }}
          >
            {editProjectChanged && <Banner tone="warning">项目已切换，未保存的译文已保留。请复制译文后关闭编辑。</Banner>}
            <p className="rb-metric-note">{edit.file_path}:{edit.row} · Ctrl + Enter 暂存（暂存只记在本页，回列表点「保存修改」才写入缓存）</p>
            {!sceneUsable && (
              <p className="rb-proof-scene-hint" data-tone={sceneError ? 'error' : 'muted'}>
                {sceneLoading ? <Spin size="small" /> : null}
                {sceneError
                  || (sceneLoading ? '正在还原这句的画面…' : (scene?.reason || '这句没有画面信息。'))}
              </p>
            )}
            <div className={sceneUsable ? 'rb-proof-bilingual-editor is-split' : 'rb-proof-bilingual-editor'}>
              {sceneUsable && (
                <figure className="rb-proof-scene">
                  <div className="rb-proof-scene-media">
                    {sceneBackground!.kind === 'video' ? (
                      <video src={assetUrl(sceneBackground!.relative)} muted loop autoPlay playsInline />
                    ) : (
                      <img src={assetUrl(sceneBackground!.relative)} alt={scene?.stage?.scene_tag || '画面'} />
                    )}
                    {scene?.stage?.scene_tag ? <span className="rb-proof-scene-tag">{scene.stage.scene_tag}</span> : null}
                    <div className="rb-proof-scene-modes" role="group" aria-label="画面台词显示">
                      {([['dst', '译文'], ['src', '原文'], ['both', '双语']] as const).map(([mode, label]) => (
                        <button
                          key={mode}
                          type="button"
                          data-on={overlayMode === mode}
                          onClick={() => setOverlayMode(mode)}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                    <div className="rb-proof-scene-dialog">
                      {overlayName ? <span className="rb-proof-scene-dialog-name">{overlayName}</span> : null}
                      {overlayMode !== 'dst' && (
                        <p className="rb-proof-scene-dialog-text is-src" title={edit.src}>{edit.src}</p>
                      )}
                      {overlayMode !== 'src' && (
                        <p className="rb-proof-scene-dialog-text" title={overlayDst}>{overlayDst || '（这句还没有译文）'}</p>
                      )}
                    </div>
                  </div>
                  {(scene?.stage?.layers.length ?? 0) > 0 && (
                    <div className="rb-proof-scene-layers">
                      {scene!.stage!.layers.map((layer) => (
                        <img key={layer.tag} src={assetUrl(layer.relative)} alt={layer.tag} title={layer.tag} />
                      ))}
                    </div>
                  )}
                  <figcaption className="rb-metric-note rb-proof-scene-note">
                    <Tooltip title="画面是按源脚本里的 scene/show 静态推出来的，没有启动游戏。转场与 ATL 动画的中间态、按剧情变量走的分支、以及脚本里动态设定的画面，实际游戏里可能不是这个样子。">
                      <span className="rb-proof-scene-caution">
                        <AlertTriangle size={12} />
                        静态还原，非游戏实际画面
                      </span>
                    </Tooltip>
                    <span className="rb-proof-scene-source">
                      game/{scene?.source.file}:{scene?.source.line} · {sceneBackground!.note}
                    </span>
                  </figcaption>
                </figure>
              )}
              <label>
                <span>原文</span>
                <Input.TextArea readOnly value={edit.src} autoSize={{ minRows: sceneUsable ? 7 : 10, maxRows: 16 }} />
              </label>
              <label>
                <span>译文</span>
                <Input.TextArea
                  id="proofreading-draft"
                  value={draft}
                  disabled={saving || readonly}
                  autoSize={{ minRows: sceneUsable ? 7 : 10, maxRows: 16 }}
                  onChange={(event) => setDraft(event.target.value)}
                />
              </label>
            </div>
          </div>
        </Modal>
      )}
      {discardEdit ? (
        <Dialog title={t('proofreading_discard_title')} onCancel={() => setDiscardEdit(null)} onConfirm={() => {
          const discarded = discardEdit;
          setDiscardEdit(null);
          if (discarded.action === 'close') {
            setEdit(null);
            return;
          }
          setEdit({ ...discarded.row, cache_token: data?.cache_token ?? '', project_identity: projectIdentity });
          setDraft(discarded.row.dst);
        }}>
          {t('proofreading_discard_body')}
        </Dialog>
      ) : null}
      {selectionConfirm && <Dialog title={selectionConfirm.action === 'retranslate' ? '重新翻译' : selectionConfirm.action === 'reset' ? '重置选中译文' : '确认译文无误'} confirmText={selectionConfirm.action === 'retranslate' ? '开始重译' : '确认并保存'} onCancel={() => { if (!saving) setSelectionConfirm(null); }} onConfirm={mutationDisabled || selectionConfirm.project !== projectIdentity ? undefined : () => void applySelection()}>
        <p>{selectionConfirm.action === 'retranslate' ? '使用当前翻译接口重新处理选中行，会消耗额度；失败行保留原译文。' : selectionConfirm.action === 'reset' ? '将清空选中行的译文、重试记录，并设为待翻译。' : '保留已有译文，清除重试次数与当前查出的问题标记；译文若再修改，确认会自动失效。'}共 {selectionConfirm.rows.length} 条，成功后保存到缓存。</p>
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
