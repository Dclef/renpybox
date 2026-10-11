/** RPY 抽取设置：分类 / 方式应用 / 自定义方案编辑与预览，对齐 Qt5 RpyExtractionPage。 */
import { useCallback, useEffect, useMemo, useRef, useState, type MutableRefObject } from 'react';
import { Button, Checkbox, Collapse, Form, Input, Progress, Select, Table } from 'antd';

import { ApiError, cancelJob, request } from '../api';
import { useT } from '../i18n';
import {
  advancedMustStayOpen,
  buildNewRule,
  canApplySelection,
  canContinuePreview,
  canSaveBind,
  clampScanPage,
  cloneProfileDraft,
  formatPageLabel,
  formatSelectionSummary,
  isEditorDirty,
  isPageDirty,
  isSelectionDirty,
  modeNeedsProfile,
  RPY_PAGE_SIZE,
} from '../rpyExtractionView.mjs';
import type { AppState } from '../useAppState';
import { Banner, SettingsGroup } from '../ui';
import {
  toolErrorText,
  toolJobRunning,
  toolStatusText,
  useProjectToolJob,
  type ToolJob,
  type ToolResultBase,
} from './projectToolJob';

interface RuleRow {
  id: string;
  name: string;
  enabled: boolean;
  include_globs: string[];
  pattern: string;
  flags: string[];
  text_group: string | number;
  note: string;
  positive_samples: string[];
  negative_samples: string[];
}

interface ProfileDoc {
  id: string;
  name: string;
  note: string;
  category: string;
  rules: RuleRow[];
}

interface ProfileSummary {
  id: string;
  name: string;
  note?: string;
  category?: string;
  rule_count?: number;
  enabled_count?: number;
}

interface ScanInfo {
  has_scan?: boolean;
  completed?: boolean;
  error?: string;
  files_read?: number;
  raw_matches?: number;
  filtered?: number;
  valid?: number;
  covered?: number;
  new?: number;
  candidates?: Array<{
    path: string;
    line: number;
    text: string;
    rule_name?: string;
    state?: string;
  }>;
  candidate_total?: number;
  page?: number;
  page_size?: number;
  page_count?: number;
  can_save_bind?: boolean;
  can_continue?: boolean;
}

interface RpyResult extends ToolResultBase {
  category?: string;
  scan?: ScanInfo;
  profile_id?: string;
  action?: string;
  base?: string;
}

interface RpyStatus {
  project_key?: string;
  path?: string;
  root?: string;
  base?: string;
  category?: string;
  language?: string;
  mode?: string;
  applied_mode?: string;
  applied_profile_id?: string | null;
  applied_name?: string;
  profile?: ProfileDoc | null;
  profiles?: ProfileSummary[];
  profile_docs?: ProfileDoc[];
  new_rule_template?: RuleRow;
  summary?: string;
  mode_labels?: Record<string, string>;
  no_profile_label?: string;
  scan?: ScanInfo;
  dirty?: boolean;
  job?: ToolJob<RpyResult> | null;
  editor_profile?: ProfileDoc;
}

type Mode = 'builtin' | 'combined' | 'custom';

const KINDS = ['rpy_preview', 'rpy_save'] as const;

function emptyProfile(category: string): ProfileDoc {
  return {
    id: `${Date.now().toString(16)}${Math.random().toString(16).slice(2, 10)}`,
    name: '当前游戏补充规则',
    note: '',
    category,
    rules: [],
  };
}

function profileBaseline(doc: ProfileDoc | null): string {
  return doc ? JSON.stringify(doc) : '';
}

function cloneProfileDoc(doc: ProfileDoc): ProfileDoc {
  return {
    ...doc,
    rules: doc.rules.map((rule) => ({
      ...rule,
      include_globs: [...(rule.include_globs || [])],
      flags: [...(rule.flags || [])],
      positive_samples: [...(rule.positive_samples || [])],
      negative_samples: [...(rule.negative_samples || [])],
    })),
  };
}

export function RpyExtractionPage(props: {
  state: AppState;
  onDirtyChange?: (dirty: boolean) => void;
  leaveGuardRef?: MutableRefObject<(() => Promise<void>) | null>;
  leaveBlockedRef?: MutableRefObject<boolean>;
}) {
  const { state, onDirtyChange, leaveGuardRef, leaveBlockedRef } = props;
  const t = useT();
  const projectPath = String(state.project?.renpy_project_path || state.project?.renpy_game_folder || '');
  const [path, setPath] = useState(projectPath);
  const [category, setCategory] = useState<'source' | 'tl'>('source');
  const [language, setLanguage] = useState('chinese');
  const [scanPage, setScanPage] = useState(1);
  const [mode, setMode] = useState<Mode>('builtin');
  const [profileId, setProfileId] = useState<string | null>(null);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editor, setEditor] = useState<ProfileDoc | null>(null);
  const [editorBaseline, setEditorBaseline] = useState('');
  const [ruleIndex, setRuleIndex] = useState(0);
  const [localError, setLocalError] = useState('');
  const [mutating, setMutating] = useState(false);
  const [leaveWaiting, setLeaveWaiting] = useState(false);
  /** 编辑后本地失效 proof；null=已清，undefined=用服务端 */
  const [scanOverride, setScanOverride] = useState<ScanInfo | null | undefined>(undefined);
  const mutateSeq = useRef(0);
  const jobIdRef = useRef<string | null>(null);
  /** 已处理完的预览 job：同 job 恢复/翻页轮询不得把页码打回 1 */
  const handledPreviewJobRef = useRef<string | null>(null);
  /** 保存受理时冻结的正文；仅 done∧written 后写入 baseline */
  const pendingSaveRef = useRef<{
    action: 'save_bind' | 'save_draft';
    baseline: string;
    submitFingerprint: string;
    profileId: string;
    applyEditor: ProfileDoc | null;
  } | null>(null);
  // 已生效基线：apply 成功后立刻更新，避免等轮询时摘要误显示「未保存」
  const [applied, setApplied] = useState<{ mode: string; profileId: string | null; name: string }>({
    mode: 'builtin',
    profileId: null,
    name: '',
  });

  const statusPath = useMemo(() => {
    const params = new URLSearchParams({
      path: path || projectPath,
      category,
      language: language || 'chinese',
      page: String(Math.max(1, scanPage)),
    });
    return `/api/rpy-extraction?${params.toString()}`;
  }, [path, projectPath, category, language, scanPage]);

  const suite = useProjectToolJob<RpyResult, RpyStatus>(state, statusPath, KINDS);
  const { status, keyReady, job, result, error, cancelling, busy, currentKey } = suite;
  const engineBusy = state.translation.engine_status !== 'IDLE' || state.translation.stop_barrier || state.translation.single_tasks;
  const hasProject = Boolean(projectPath);
  const writeBlocked = busy || mutating || engineBusy || !keyReady || state.link !== 'open';

  useEffect(() => {
    jobIdRef.current = job?.id ?? null;
  }, [job?.id]);

  const modeLabels = status?.mode_labels || {
    builtin: t('rpy_rules_builtin'),
    combined: t('rpy_rules_combined'),
    custom: t('rpy_rules_custom'),
  };
  const noProfile = status?.no_profile_label || t('rpy_rules_no_profile');
  const profiles = status?.profiles || [];
  const appliedView = {
    mode: applied.mode || 'builtin',
    profileId: applied.profileId,
    name: applied.name || noProfile,
  };
  const pendingName = profiles.find((item) => item.id === profileId)?.name || noProfile;
  const pending = { mode, profileId, name: pendingName };
  const selectionDirty = isSelectionDirty(appliedView, pending);
  const editorDirty = isEditorDirty(editor, editorBaseline);
  const pageDirty = isPageDirty(selectionDirty, editorDirty);
  const summary = formatSelectionSummary(appliedView, pending, {
    current: t('rpy_rules_current'),
    pending: t('rpy_rules_pending'),
    modes: modeLabels,
    noProfile,
  });
  const needsProfile = modeNeedsProfile(mode);
  // 优先当前分页 status.scan；job.result.scan 是预览完成时的第 1 页快照，翻页后不可覆盖
  const serverScan = status?.scan
    ?? (result?.category === category ? result?.scan : null)
    ?? null;
  const scan = scanOverride === null ? null : (scanOverride ?? serverScan);
  const jobForCategory = result?.category === category ? job : null;
  const activeForCategory = toolJobRunning(jobForCategory);

  const cancelAndWait = useCallback(async () => {
    const id = jobIdRef.current;
    if (!id) {
      setLeaveWaiting(false);
      return;
    }
    try {
      await cancelJob(id);
    } catch {
      // 任务可能已结束；仍须确认终态
    }
    const started = Date.now();
    let sawWaiting = false;
    // 仅在明确 !toolJobRunning（含 worker_active=false）时放行；超时/网络失败抛错留在页
    for (;;) {
      try {
        const snap = await request<ToolJob<RpyResult>>(`/api/jobs/${id}`);
        if (!toolJobRunning(snap)) {
          setLeaveWaiting(false);
          return;
        }
      } catch {
        setLeaveWaiting(false);
        setLocalError(t('rpy_rules_leave_wait_failed'));
        throw new Error(t('rpy_rules_leave_wait_failed'));
      }
      const elapsed = Date.now() - started;
      if (elapsed >= 5000 && !sawWaiting) {
        sawWaiting = true;
        setLeaveWaiting(true);
        setLocalError(t('rpy_rules_leave_waiting'));
      }
      if (elapsed >= 120000) {
        setLeaveWaiting(false);
        setLocalError(t('rpy_rules_leave_wait_failed'));
        throw new Error(t('rpy_rules_leave_wait_failed'));
      }
      await new Promise((resolve) => window.setTimeout(resolve, 50));
    }
  }, [t]);

  useEffect(() => {
    if (!leaveGuardRef) return;
    leaveGuardRef.current = cancelAndWait;
    return () => {
      leaveGuardRef.current = null;
    };
  }, [leaveGuardRef, cancelAndWait]);

  useEffect(() => {
    if (!leaveBlockedRef) return;
    leaveBlockedRef.current = activeForCategory || leaveWaiting;
    return () => {
      leaveBlockedRef.current = false;
    };
  }, [leaveBlockedRef, activeForCategory, leaveWaiting]);

  useEffect(() => {
    onDirtyChange?.(pageDirty);
    return () => onDirtyChange?.(false);
  }, [pageDirty, onDirtyChange]);

  // 项目身份变化：取消旧任务并重置本地态，禁止旧结果回写新页
  useEffect(() => {
    const previousId = jobIdRef.current;
    if (previousId) {
      void cancelJob(previousId).catch(() => undefined);
    }
    handledPreviewJobRef.current = null;
    pendingSaveRef.current = null;
    setPath(projectPath);
    setCategory('source');
    setLanguage('chinese');
    setScanPage(1);
    setMode('builtin');
    setProfileId(null);
    setApplied({ mode: 'builtin', profileId: null, name: '' });
    setAdvancedOpen(false);
    setEditorOpen(false);
    setEditor(null);
    setEditorBaseline('');
    setScanOverride(undefined);
    setLocalError('');
    setLeaveWaiting(false);
  }, [suite.identity, projectPath]);

  useEffect(() => {
    if (!status) return;
    const nextApplied = {
      mode: status.applied_mode || 'builtin',
      profileId: status.applied_profile_id ?? null,
      name: status.applied_name || noProfile,
    };
    setApplied(nextApplied);
    setMode((nextApplied.mode as Mode) || 'builtin');
    setProfileId(nextApplied.profileId);
  }, [status?.project_key, status?.category, status?.applied_mode, status?.applied_profile_id, status?.applied_name, noProfile]);

  useEffect(() => {
    if (advancedMustStayOpen(mode)) setAdvancedOpen(true);
  }, [mode]);

  // 新预览/续扫真正完成才重置第 1 页；同 job 恢复与翻页轮询不得重置
  useEffect(() => {
    if (!job?.id || toolJobRunning(job)) return;
    if (result?.action !== 'preview' && result?.action !== 'preview_continue') return;
    if (handledPreviewJobRef.current === job.id) return;
    handledPreviewJobRef.current = job.id;
    setScanOverride(undefined);
    setScanPage(1);
  }, [job?.id, job?.status, result?.action, result?.worker_active]);

  // 仅对应 job done 且 written=true 后更新保存基线；失败/取消保持 dirty
  useEffect(() => {
    const pending = pendingSaveRef.current;
    if (!pending || !job?.id) return;
    if (toolJobRunning(job)) return;
    if (result?.action !== pending.action) return;
    if (job.status === 'done' && result?.written === true) {
      setProfileId(pending.profileId);
      setEditor((current) => {
        // 用户在保存收尾期间又改了正文：只更新 baseline，保留其编辑（仍 dirty）
        if (current && pending.applyEditor && profileBaseline(current) === pending.submitFingerprint) {
          return pending.applyEditor;
        }
        return current;
      });
      setEditorBaseline(pending.baseline);
      setScanOverride(undefined);
      pendingSaveRef.current = null;
      return;
    }
    if (job.status === 'failed' || job.status === 'cancelled') {
      pendingSaveRef.current = null;
    }
  }, [job?.id, job?.status, result?.action, result?.written, result?.worker_active]);

  const ctx = useCallback(() => ({
    path: path || projectPath,
    category,
    language: language || 'chinese',
  }), [path, projectPath, category, language]);

  function confirmDiscard(): boolean {
    if (!pageDirty) return true;
    return window.confirm(t('game_rules_discard'));
  }

  function openEditorDoc(doc: ProfileDoc) {
    const copy = { ...doc, rules: doc.rules.map((rule) => ({
      ...rule,
      include_globs: [...(rule.include_globs || [])],
      flags: [...(rule.flags || [])],
      positive_samples: [...(rule.positive_samples || [])],
      negative_samples: [...(rule.negative_samples || [])],
    })) };
    setEditor(copy);
    setEditorBaseline(profileBaseline(copy));
    setRuleIndex(0);
    setEditorOpen(true);
    setAdvancedOpen(true);
    setScanOverride(undefined);
  }

  function touchEditor(next: ProfileDoc) {
    setEditor(next);
    setScanOverride(null);
  }

  async function mutate(pathUrl: string, body: Record<string, unknown>) {
    const key = currentKey();
    if (!key) return null;
    const local = suite.identityRef.current;
    const current = suite.sequence.current;
    const seq = (mutateSeq.current += 1);
    setMutating(true);
    setLocalError('');
    try {
      const next = await request<RpyStatus>(pathUrl, {
        method: 'POST',
        body: JSON.stringify({ ...body, ...ctx(), project_key: key }),
      });
      // 晚到响应：上下文已变则丢弃，且不解新 mutation 锁
      if (local !== suite.identityRef.current || current !== suite.sequence.current || seq !== mutateSeq.current) {
        return null;
      }
      return next;
    } catch (failure) {
      if (local === suite.identityRef.current && current === suite.sequence.current && seq === mutateSeq.current) {
        setLocalError(toolErrorText(failure));
      }
      if (failure instanceof ApiError && failure.status === 409) {
        // 交由轮询恢复 canonical
      }
      return null;
    } finally {
      if (local === suite.identityRef.current && current === suite.sequence.current && seq === mutateSeq.current) {
        setMutating(false);
      }
    }
  }

  async function applySelection() {
    if (!canApplySelection(mode, profileId)) {
      setLocalError(t('rpy_rules_apply_need_profile'));
      return;
    }
    const next = await mutate('/api/rpy-extraction/select', {
      mode,
      profile_id: mode === 'builtin' ? null : profileId,
    });
    if (next) {
      const nextApplied = {
        mode: next.applied_mode || 'builtin',
        profileId: next.applied_profile_id ?? null,
        name: next.applied_name || noProfile,
      };
      setApplied(nextApplied);
      setMode((nextApplied.mode as Mode) || 'builtin');
      setProfileId(nextApplied.profileId);
    }
  }

  async function openEditor(options?: { starter?: boolean; fresh?: boolean; clone?: boolean }) {
    if (options?.clone) {
      if (!editor) return;
      const cloned = cloneProfileDraft(editor, t('game_rules_copy_suffix'));
      if (!cloned) return;
      openEditorDoc(cloned as ProfileDoc);
      setEditorBaseline(''); // 副本视为未保存草稿
      setScanOverride(null);
      return;
    }
    if (options?.starter) {
      const next = await mutate('/api/rpy-extraction/profiles', { starter: true });
      if (next?.editor_profile) openEditorDoc(next.editor_profile);
      return;
    }
    if (options?.fresh) {
      // 新建仅草稿：API 不落盘
      const next = await mutate('/api/rpy-extraction/profiles', {});
      if (next?.editor_profile) {
        openEditorDoc(next.editor_profile);
        setEditorBaseline(''); // 未保存
      }
      return;
    }
    const docs = status?.profile_docs || [];
    const existing = (profileId && docs.find((item) => item.id === profileId))
      || (status?.profile && status.profile.id === profileId ? status.profile : null)
      || (!profileId ? emptyProfile(category) : null);
    if (!existing) {
      setLocalError(t('rpy_rules_apply_need_profile'));
      return;
    }
    openEditorDoc(existing);
  }

  function updateRule(patch: Partial<RuleRow>) {
    if (!editor || ruleIndex < 0 || ruleIndex >= editor.rules.length) return;
    touchEditor({
      ...editor,
      rules: editor.rules.map((rule, index) => (index === ruleIndex ? { ...rule, ...patch } : rule)),
    });
  }

  function addRule() {
    if (!editor) return;
    const rule = buildNewRule(status?.new_rule_template, editor.rules.length + 1) as RuleRow;
    touchEditor({ ...editor, rules: [...editor.rules, rule] });
    setRuleIndex(editor.rules.length);
  }

  function removeRule() {
    if (!editor || ruleIndex < 0) return;
    const rules = editor.rules.filter((_, index) => index !== ruleIndex);
    touchEditor({ ...editor, rules });
    setRuleIndex(Math.max(0, ruleIndex - 1));
  }

  async function runPreview() {
    if (!editor) return;
    setScanPage(1);
    await suite.submit('/api/rpy-extraction/preview', { ...ctx(), profile: editor });
  }

  async function runContinue() {
    if (!editor) return;
    await suite.submit('/api/rpy-extraction/preview/continue', { ...ctx(), profile: editor });
  }

  async function runSaveDraft() {
    if (!editor) return;
    // 服务端会强制全部 enabled=false；冻结与服务器一致的正文，仅 written 后落 baseline
    const submitFingerprint = profileBaseline(editor);
    const savedDoc: ProfileDoc = {
      ...cloneProfileDoc(editor),
      rules: editor.rules.map((rule) => ({ ...rule, enabled: false })),
    };
    pendingSaveRef.current = {
      action: 'save_draft',
      baseline: profileBaseline(savedDoc),
      submitFingerprint,
      profileId: editor.id,
      applyEditor: savedDoc,
    };
    const ok = await suite.submit('/api/rpy-extraction/save-draft', { ...ctx(), profile: editor });
    if (!ok) pendingSaveRef.current = null;
  }

  async function runSaveBind() {
    if (!editor) return;
    const frozen = cloneProfileDoc(editor);
    const fingerprint = profileBaseline(frozen);
    pendingSaveRef.current = {
      action: 'save_bind',
      baseline: fingerprint,
      submitFingerprint: fingerprint,
      profileId: editor.id,
      applyEditor: null,
    };
    const ok = await suite.submit('/api/rpy-extraction/save-bind', { ...ctx(), profile: editor });
    if (!ok) pendingSaveRef.current = null;
  }

  async function runDelete() {
    if (!editor?.id) return;
    const next = await mutate('/api/rpy-extraction/profiles/delete', { profile_id: editor.id });
    if (next) {
      const nextApplied = {
        mode: next.applied_mode || 'builtin',
        profileId: next.applied_profile_id ?? null,
        name: next.applied_name || noProfile,
      };
      setApplied(nextApplied);
      setEditor(null);
      setEditorBaseline('');
      setEditorOpen(false);
      setProfileId(nextApplied.profileId);
      setMode((nextApplied.mode as Mode) || 'builtin');
      setScanOverride(undefined);
    }
  }

  async function runUnbind() {
    if (!confirmDiscard()) return;
    const next = await mutate('/api/rpy-extraction/profiles/unbind', {});
    if (next) {
      const nextApplied = {
        mode: next.applied_mode || 'builtin',
        profileId: next.applied_profile_id ?? null,
        name: next.applied_name || noProfile,
      };
      setApplied(nextApplied);
      setMode((nextApplied.mode as Mode) || 'builtin');
      setProfileId(nextApplied.profileId);
    }
  }

  const displayError = localError || error;
  const statusText = toolStatusText(t, {
    ...suite,
    job: jobForCategory,
    result: result?.category === category ? result : null,
    active: activeForCategory,
  }, t('rpy_rules_idle'));
  const statusTone = activeForCategory || suite.checking
    ? 'info'
    : jobForCategory?.status === 'done'
      ? 'success'
      : jobForCategory?.status === 'failed'
        ? 'error'
        : jobForCategory?.status === 'cancelled'
          ? 'warning'
          : pageDirty
            ? 'warning'
            : 'info';
  const currentRule = editor && editor.rules[ruleIndex] ? editor.rules[ruleIndex] : null;
  const modeHelp = mode === 'combined'
    ? t('rpy_rules_combined_help')
    : mode === 'custom'
      ? t('rpy_rules_custom_help')
      : t('rpy_rules_builtin_help');
  const totalCandidates = scan?.candidate_total || 0;
  const pageCount = Math.max(1, scan?.page_count || Math.ceil(totalCandidates / RPY_PAGE_SIZE) || 1);
  const currentPage = clampScanPage(scan?.page || scanPage, totalCandidates, scan?.page_size || RPY_PAGE_SIZE);

  return (
    <div className="rb-asset-page rb-page-scroll" data-rb-page="rpy-extraction">
      {displayError ? <Banner tone="error">{displayError}</Banner> : null}
      {/* 本工具不要求绑定项目；未绑定时可手填扫描路径 */}
      {!hasProject && !path.trim() ? <Banner tone="info">{t('rpy_rules_need_path')}</Banner> : null}
      <Banner tone="info">{t('rpy_rules_intro')}</Banner>
      <Banner tone={statusTone}>{statusText}</Banner>
      {leaveWaiting ? (
        <Banner tone="warning">
          {t('rpy_rules_leave_waiting')}
          <div className="rb-tool-actions" style={{ marginTop: 8 }}>
            <Button onClick={() => void cancelAndWait().catch(() => undefined)} data-rb-rpy-leave-retry>
              {t('rpy_rules_leave_retry_cancel')}
            </Button>
          </div>
        </Banner>
      ) : null}
      {activeForCategory ? <Progress percent={Math.min(100, 100 * (jobForCategory?.progress || 0))} aria-label={t('tool_job_running')} /> : null}
      {activeForCategory ? (
        <div className="rb-tool-actions">
          <Button onClick={() => void suite.cancel()} disabled={cancelling || Boolean(jobForCategory?.cancel_requested)}>
            {t('tool_job_cancel')}
          </Button>
        </div>
      ) : null}

      <SettingsGroup title={t('rpy_rules_title')} description={t('rpy_rules_beginner_steps')}>
        <Form.Item label={t('rpy_rules_path')} style={{ marginBottom: 12 }}>
          <Input
            value={path}
            onChange={(event) => {
              const value = event.target.value;
              if (value !== path && pageDirty && !confirmDiscard()) return;
              setPath(value);
              setScanOverride(null);
              setScanPage(1);
            }}
            placeholder={t('rpy_rules_path')}
            disabled={busy || mutating}
            data-rb-rpy-path
          />
        </Form.Item>
        <Form.Item label={t('rpy_rules_category')} style={{ marginBottom: 12 }}>
          <Select
            value={category}
            options={[
              { value: 'source', label: t('rpy_rules_source') },
              { value: 'tl', label: t('rpy_rules_tl') },
            ]}
            onChange={(value) => {
              if (value !== category && pageDirty && !confirmDiscard()) return;
              setCategory(value as 'source' | 'tl');
              setEditor(null);
              setEditorBaseline('');
              setEditorOpen(false);
              setScanOverride(undefined);
              setScanPage(1);
            }}
            disabled={busy || mutating}
          />
        </Form.Item>
        <p className="card-description">
          {category === 'tl' ? t('rpy_rules_tl_scope') : t('rpy_rules_source_scope')}
        </p>
        <Form.Item label={t('rpy_rules_language')} style={{ marginBottom: 12 }}>
          <Input
            value={language}
            onChange={(event) => {
              const value = event.target.value;
              if (value !== language && pageDirty && !confirmDiscard()) return;
              setLanguage(value);
              setScanOverride(null);
              setScanPage(1);
            }}
            disabled={busy || mutating}
            data-rb-rpy-language
          />
        </Form.Item>
        <Form.Item label={t('rpy_rules_method')} style={{ marginBottom: 12 }}>
          <Select
            value={mode}
            options={[
              { value: 'builtin', label: t('rpy_rules_builtin_simple') },
              { value: 'combined', label: t('rpy_rules_combined_simple') },
              { value: 'custom', label: t('rpy_rules_custom_simple') },
            ]}
            onChange={(value) => setMode(value as Mode)}
            disabled={writeBlocked}
          />
        </Form.Item>
        <p className="card-description">{modeHelp}</p>
        {needsProfile ? (
          <Form.Item label={t('rpy_rules_profile')} style={{ marginBottom: 12 }}>
            <Select
              allowClear
              value={profileId || undefined}
              placeholder={noProfile}
              options={profiles.map((item) => ({ value: item.id, label: item.name || item.id }))}
              onChange={(value) => setProfileId(value ? String(value) : null)}
              disabled={writeBlocked}
            />
          </Form.Item>
        ) : null}
        <p className="card-description" data-rb-rpy-summary>{summary}</p>
        <div className="rb-tool-actions">
          <Button type="primary" onClick={() => void applySelection()} disabled={writeBlocked || !selectionDirty}>
            {t('rpy_rules_apply')}
          </Button>
        </div>
      </SettingsGroup>

      <Collapse
        activeKey={advancedOpen ? ['advanced'] : []}
        onChange={(keys) => {
          const open = (Array.isArray(keys) ? keys : [keys]).map(String).includes('advanced');
          if (!open && advancedMustStayOpen(mode)) {
            setAdvancedOpen(true);
            return;
          }
          setAdvancedOpen(open);
        }}
        items={[{
          key: 'advanced',
          label: t('rpy_rules_advanced_toggle'),
          children: (
            <div>
              <div className="rb-tool-actions">
                <Button onClick={() => void openEditor()} disabled={writeBlocked}>
                  {t('rpy_rules_edit')}
                </Button>
                <Button onClick={() => void openEditor({ starter: true })} disabled={writeBlocked} data-rb-rpy-copy-builtin>
                  {t('rpy_rules_copy_builtin')}
                </Button>
                <Button onClick={() => void openEditor({ fresh: true })} disabled={writeBlocked}>
                  {t('game_rules_new_profile')}
                </Button>
                <Button onClick={() => void openEditor({ clone: true })} disabled={writeBlocked || !editor}>
                  {t('game_rules_clone')}
                </Button>
                <Button onClick={() => void runUnbind()} disabled={writeBlocked}>
                  {t('game_rules_unbind')}
                </Button>
              </div>

              {editorOpen && editor ? (
                <div style={{ marginTop: 16 }} data-rb-rpy-editor>
                  <Form.Item label={t('game_rules_profile_name')} style={{ marginBottom: 12 }}>
                    <Input
                      value={editor.name}
                      onChange={(event) => touchEditor({ ...editor, name: event.target.value })}
                      disabled={writeBlocked}
                    />
                  </Form.Item>
                  <Form.Item label={t('game_rules_note')} style={{ marginBottom: 12 }}>
                    <Input
                      value={editor.note}
                      onChange={(event) => touchEditor({ ...editor, note: event.target.value })}
                      disabled={writeBlocked}
                    />
                  </Form.Item>
                  <Form.Item label={t('rpy_rules_profile')} style={{ marginBottom: 12 }}>
                    <Select
                      value={editor.rules.length ? ruleIndex : undefined}
                      options={editor.rules.map((rule, index) => ({ value: index, label: rule.name || `规则 ${index + 1}` }))}
                      onChange={(value) => setRuleIndex(Number(value))}
                      disabled={writeBlocked || !editor.rules.length}
                    />
                  </Form.Item>
                  <div className="rb-tool-actions">
                    <Button onClick={addRule} disabled={writeBlocked}>{t('game_rules_add_rule')}</Button>
                    <Button onClick={removeRule} disabled={writeBlocked || !currentRule}>{t('game_rules_remove_rule')}</Button>
                    <Button danger onClick={() => void runDelete()} disabled={writeBlocked}>{t('game_rules_delete_profile')}</Button>
                  </div>
                  {currentRule ? (
                    <>
                      <Form.Item style={{ marginBottom: 12 }}>
                        <Checkbox
                          checked={currentRule.enabled}
                          onChange={(event) => updateRule({ enabled: event.target.checked })}
                          disabled={writeBlocked}
                        >
                          {t('game_rules_enabled')}
                        </Checkbox>
                      </Form.Item>
                      <Form.Item label={t('game_rules_rule_name')} style={{ marginBottom: 12 }}>
                        <Input
                          value={currentRule.name}
                          onChange={(event) => updateRule({ name: event.target.value })}
                          disabled={writeBlocked}
                        />
                      </Form.Item>
                      <Form.Item label={t('game_rules_pattern')} style={{ marginBottom: 12 }}>
                        <Input.TextArea
                          value={currentRule.pattern}
                          onChange={(event) => updateRule({ pattern: event.target.value })}
                          autoSize={{ minRows: 2, maxRows: 6 }}
                          disabled={writeBlocked}
                        />
                      </Form.Item>
                      <Form.Item label={t('game_rules_scope')} style={{ marginBottom: 12 }}>
                        <Input
                          value={(currentRule.include_globs || []).join('; ')}
                          onChange={(event) => updateRule({
                            include_globs: event.target.value.split(';').map((item) => item.trim()).filter(Boolean),
                          })}
                          disabled={writeBlocked}
                          data-rb-rpy-scope
                        />
                      </Form.Item>
                      <Form.Item label={t('game_rules_group')} style={{ marginBottom: 12 }}>
                        <Input
                          value={String(currentRule.text_group ?? '')}
                          onChange={(event) => {
                            const raw = event.target.value.trim();
                            updateRule({ text_group: /^\d+$/.test(raw) ? Number(raw) : raw });
                          }}
                          disabled={writeBlocked}
                          data-rb-rpy-group
                        />
                      </Form.Item>
                      <Form.Item style={{ marginBottom: 12 }}>
                        <Checkbox
                          checked={(currentRule.flags || []).includes('IGNORECASE')}
                          onChange={(event) => updateRule({ flags: event.target.checked ? ['IGNORECASE'] : [] })}
                          disabled={writeBlocked}
                          data-rb-rpy-ignore-case
                        >
                          {t('game_rules_ignore_case')}
                        </Checkbox>
                      </Form.Item>
                      <Form.Item label={t('game_rules_rule_note')} style={{ marginBottom: 12 }}>
                        <Input
                          value={currentRule.note || ''}
                          onChange={(event) => updateRule({ note: event.target.value })}
                          disabled={writeBlocked}
                          data-rb-rpy-rule-note
                        />
                      </Form.Item>
                      <Form.Item label={t('game_rules_positive')} style={{ marginBottom: 12 }}>
                        <Input.TextArea
                          value={(currentRule.positive_samples || []).join('\n')}
                          onChange={(event) => updateRule({
                            positive_samples: event.target.value.split(/\r?\n/).filter((line) => line.length > 0),
                          })}
                          autoSize={{ minRows: 2, maxRows: 4 }}
                          disabled={writeBlocked}
                        />
                      </Form.Item>
                      <Form.Item label={t('game_rules_negative')} style={{ marginBottom: 12 }}>
                        <Input.TextArea
                          value={(currentRule.negative_samples || []).join('\n')}
                          onChange={(event) => updateRule({
                            negative_samples: event.target.value.split(/\r?\n/).filter((line) => line.length > 0),
                          })}
                          autoSize={{ minRows: 2, maxRows: 4 }}
                          disabled={writeBlocked}
                        />
                      </Form.Item>
                      <p className="card-description">{t('game_rules_literal_hint')}</p>
                    </>
                  ) : null}
                  <div className="rb-tool-actions">
                    <Button onClick={() => void runPreview()} disabled={writeBlocked || !editor.rules.length}>
                      {t('game_rules_preview')}
                    </Button>
                    <Button
                      onClick={() => void runContinue()}
                      disabled={writeBlocked || !canContinuePreview(scan)}
                    >
                      {t('game_rules_continue')}
                    </Button>
                    <Button onClick={() => void runSaveDraft()} disabled={writeBlocked}>
                      {t('game_rules_save_draft')}
                    </Button>
                    <Button
                      type="primary"
                      onClick={() => void runSaveBind()}
                      disabled={writeBlocked || !canSaveBind(scan)}
                      data-rb-rpy-save-bind
                    >
                      {t('game_rules_save_bind')}
                    </Button>
                  </div>
                  {scan?.has_scan ? (
                    <>
                      <p className="card-description">
                        {t('game_rules_stats')
                          .replaceAll('{files}', String(scan.files_read || 0))
                          .replaceAll('{raw}', String(scan.raw_matches || 0))
                          .replaceAll('{valid}', String(scan.valid || 0))
                          .replaceAll('{covered}', String(scan.covered || 0))
                          .replaceAll('{filtered}', String(scan.filtered || 0))
                          .replaceAll('{new}', String(scan.new || 0))}
                      </p>
                      <Table
                        size="small"
                        pagination={false}
                        rowKey={(row) => `${row.path}:${row.line}:${row.text}`}
                        dataSource={scan.candidates || []}
                        columns={[
                          { title: t('game_rules_source'), dataIndex: 'path', render: (value, row) => `${value}:${row.line}` },
                          { title: t('game_rules_text'), dataIndex: 'text' },
                          { title: t('game_rules_rule_name'), dataIndex: 'rule_name' },
                          { title: t('game_rules_state'), dataIndex: 'state' },
                        ]}
                      />
                      <div className="rb-tool-actions" data-rb-rpy-pagination>
                        <Button
                          onClick={() => setScanPage(Math.max(1, currentPage - 1))}
                          disabled={writeBlocked || currentPage <= 1}
                        >
                          {t('game_rules_previous')}
                        </Button>
                        <Button
                          onClick={() => setScanPage(Math.min(pageCount, currentPage + 1))}
                          disabled={writeBlocked || currentPage >= pageCount}
                        >
                          {t('game_rules_next')}
                        </Button>
                        <span className="card-description">
                          {t('game_rules_page')
                            .replaceAll('{page}', String(currentPage))
                            .replaceAll('{pages}', String(pageCount))
                            .replaceAll('{total}', String(totalCandidates))}
                          {' · '}
                          {formatPageLabel(currentPage, totalCandidates, scan.page_size || RPY_PAGE_SIZE)}
                        </span>
                      </div>
                    </>
                  ) : (
                    <p className="card-description">{t('game_rules_preview_needed')}</p>
                  )}
                </div>
              ) : null}
            </div>
          ),
        }]}
      />
    </div>
  );
}
