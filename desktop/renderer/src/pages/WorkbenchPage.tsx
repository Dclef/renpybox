/** 项目资料工作台：手动编辑保存在项目资产仓库，提示词预览复用真实构造器。 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Button, Loader, Select, Tabs, Textarea, TextInput } from '@mantine/core';

import { cancelJob, request } from '../api';
import { useT, type TextKey } from '../i18n';
import type { JobSnapshot } from '../types';
import type { AppState } from '../useAppState';
import { Banner, Dialog, Empty, PageHeader, SettingsGroup, Switch } from '../ui';

interface CharacterCard {
  id: string;
  name: string;
  name_translation: string;
  aliases: string[];
  match_keywords: string[];
  identity: string;
  personality: string;
  speech_style: string;
  relationship_notes: string;
  prompt_notes: string;
  sample_lines: string[];
  enabled: boolean;
  is_primary: boolean;
}
interface EditableAssets {
  worldbook: Record<string, string>;
  characters: CharacterCard[];
  worldbook_enabled: boolean;
  characters_enabled: boolean;
}
interface WorkbenchSnapshot extends EditableAssets {
  storage_key: string;
  revision: number;
  worldbook_draft: Record<string, string>;
  character_drafts: CharacterCard[];
}
interface PromptPreview {
  matched_names: string[];
  world_context: string;
  character_context: string;
  context: string;
}

type AnalysisAction = 'scan' | 'all' | 'worldbook' | 'characters';
type AnalysisScope = 'current' | 'full';
interface AnalysisJob extends JobSnapshot { cancel_requested?: boolean }
interface AnalysisResult {
  storage_key: string;
  action: AnalysisAction;
  scope: AnalysisScope;
  message?: string;
  worker_active?: boolean;
  worldbook_fields?: number;
  character_count?: number;
}

function analysisResult(job: AnalysisJob | null): AnalysisResult | null {
  return job?.result && typeof job.result === 'object' ? job.result as AnalysisResult : null;
}
function analysisRunning(job: AnalysisJob | null): boolean {
  return Boolean(job && (job.status === 'pending' || job.status === 'running' || analysisResult(job)?.worker_active));
}

type TabKey = 'overview' | 'worldbook' | 'characters' | 'preview';
const TABS: { key: TabKey; label: string }[] = [
  { key: 'overview', label: '概览' }, { key: 'worldbook', label: '世界观' },
  { key: 'characters', label: '角色卡' }, { key: 'preview', label: '提示词预览' },
];
const WORLD_FIELDS = [
  ['project_name', '项目名称'], ['genre', '作品类型'], ['setting_summary', '背景摘要'],
  ['tone_style', '整体语气'], ['era_background', '时代与环境'], ['narrative_rules', '叙事规则'],
  ['format_rules', '格式规则'], ['spoiler_notes', '剧透备注'], ['reference_notes', '补充参考'],
] as const;
const CHARACTER_FIELDS = [
  ['name', '角色名称'], ['name_translation', '推荐译名'], ['identity', '身份与经历'],
  ['personality', '性格'], ['speech_style', '说话风格'], ['prompt_notes', '翻译提示'],
  ['aliases', '别名'], ['match_keywords', '匹配关键词'], ['relationship_notes', '关系备注'],
  ['sample_lines', '台词示例'],
] as const;
const LIST_FIELDS = new Set(['aliases', 'match_keywords', 'sample_lines']);

function editable(snapshot: WorkbenchSnapshot): EditableAssets {
  // 扩展世界观字段由后端保留，表单只编辑原工作台公开的九个字段。
  return {
    worldbook: Object.fromEntries(WORLD_FIELDS.map(([key]) => [key, String(snapshot.worldbook[key] ?? '')])),
    characters: structuredClone(snapshot.characters),
    worldbook_enabled: snapshot.worldbook_enabled,
    characters_enabled: snapshot.characters_enabled,
  };
}
const errorText = (error: unknown) => error instanceof Error ? error.message : String(error);

export function WorkbenchPage(props: { state: AppState; onDirtyChange?: (dirty: boolean) => void }) {
  const { state, onDirtyChange } = props;
  const t = useT();
  const [tab, setTab] = useState<TabKey>('overview');
  const [snapshot, setSnapshot] = useState<WorkbenchSnapshot | null>(null);
  const [draft, setDraft] = useState<EditableAssets | null>(null);
  const [selectedId, setSelectedId] = useState('');
  const [search, setSearch] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [confirm, setConfirm] = useState<'delete' | 'reload' | 'apply' | 'analysis' | null>(null);
  const [snapshotProjectKey, setSnapshotProjectKey] = useState('');
  const [analysisAction, setAnalysisAction] = useState<Exclude<AnalysisAction, 'scan'>>('all');
  const [analysisScope, setAnalysisScope] = useState<AnalysisScope>('current');
  const [analysisJob, setAnalysisJob] = useState<AnalysisJob | null>(null);
  const [analysisChecking, setAnalysisChecking] = useState(true);
  const [analysisError, setAnalysisError] = useState('');
  const [analysisPollError, setAnalysisPollError] = useState('');
  const [cancelling, setCancelling] = useState(false);
  const analysisSequence = useRef(0);
  const analysisJobRef = useRef<AnalysisJob | null>(null);
  const refreshedJob = useRef('');
  const snapshotRef = useRef<WorkbenchSnapshot | null>(null);
  const engineStatusRef = useRef(state.translation.engine_status);
  const busyRef = useRef(false);
  const [sample, setSample] = useState('');
  const [preview, setPreview] = useState<PromptPreview | null>(null);
  const sequence = useRef(0);
  const dirtyRef = useRef(false);
  const projectRef = useRef('');
  const projectKey = JSON.stringify([state.project?.renpy_project_path, state.project?.renpy_tl_folder,
    state.settings?.values.input_folder, state.settings?.values.output_folder]);
  projectRef.current = projectKey;
  const dirty = Boolean(snapshot && draft && JSON.stringify(editable(snapshot)) !== JSON.stringify(draft));
  dirtyRef.current = dirty;
  const hasDrafts = Boolean(snapshot && (Object.values(snapshot.worldbook_draft).some(Boolean) || snapshot.character_drafts.length));
  busyRef.current = busy || loading;
  snapshotRef.current = snapshot;
  analysisJobRef.current = analysisJob;
  engineStatusRef.current = state.translation.engine_status;
  const projectCurrent = snapshotProjectKey === projectKey;
  const analysisActive = analysisRunning(analysisJob);
  const cancellationRequested = analysisActive && (cancelling || analysisJob?.cancel_requested);
  const mutationBlocked = busy || loading || !projectCurrent || analysisActive;
  const canAnalyze = Boolean(snapshot && !mutationBlocked && !dirty && !analysisChecking
    && state.link === 'open' && state.translation.engine_status === 'IDLE'
    && !state.translation.stop_barrier && !state.translation.single_tasks);
  const visibleCharacters = draft?.characters.filter((card) =>
    [card.name, card.name_translation, ...card.aliases, ...card.match_keywords]
      .join(' ').toLocaleLowerCase().includes(search.trim().toLocaleLowerCase())) ?? [];
  const selected = draft?.characters.find((card) => card.id === selectedId);
  const worldCount = draft ? Object.values(draft.worldbook).filter((text) => text.trim()).length : 0;

  useEffect(() => { onDirtyChange?.(dirty); }, [dirty, onDirtyChange]);
  useEffect(() => () => { onDirtyChange?.(false); }, [onDirtyChange]);

  const adopt = useCallback((next: WorkbenchSnapshot) => {
    setSnapshot(next);
    setSnapshotProjectKey(projectRef.current);
    setDraft(editable(next));
    setSelectedId((current) => next.characters.some((card) => card.id === current) ? current : next.characters[0]?.id ?? '');
    setPreview(null);
    setError('');
  }, []);

  const reload = useCallback(async () => {
    const current = ++sequence.current;
    const key = projectRef.current;
    setLoading(true);
    setError('');
    try {
      const next = await request<WorkbenchSnapshot>('/api/workbench');
      if (current === sequence.current && key === projectRef.current) adopt(next);
    } catch (failure) {
      if (current === sequence.current && key === projectRef.current) setError(errorText(failure));
    } finally {
      if (current === sequence.current && key === projectRef.current) setLoading(false);
    }
  }, [adopt]);

  useEffect(() => {
    sequence.current += 1;
    analysisSequence.current += 1;
    analysisJobRef.current = null;
    refreshedJob.current = '';
    setAnalysisJob(null);
    setAnalysisChecking(true);
    setAnalysisError('');
    setAnalysisPollError('');
    setCancelling(false);
    setBusy(false);
    setLoading(false);
    setPreview(null);
    setConfirm(null);
    // 外部切换项目时保留手动编辑，用户可以先导出，再明确重新加载。
    if (dirtyRef.current) {
      setError('项目已变更，请先导出未保存的资料，再重新加载当前项目。');
    } else {
      setSnapshot(null);
      setDraft(null);
      void reload();
    }
    return () => { sequence.current += 1; analysisSequence.current += 1; };
  }, [reload, projectKey]);

  useEffect(() => {
    if (!snapshotProjectKey || snapshotProjectKey !== projectKey || state.link !== 'open') return;
    let alive = true;
    let timer: number;
    const key = projectKey;
    const poll = async () => {
      const current = analysisSequence.current;
      const operation = sequence.current;
      const valid = () => alive && key === projectRef.current && current === analysisSequence.current;
      try {
        const { job } = await request<{ job: AnalysisJob | null }>('/api/workbench/analysis');
        if (!valid()) return;
        const result = analysisResult(job);
        if (job && result?.storage_key !== snapshotRef.current?.storage_key) return;
        const wasActive = analysisRunning(analysisJobRef.current);
        analysisJobRef.current = job;
        setAnalysisJob(job);
        setAnalysisPollError('');
        setAnalysisChecking(false);
        if (!analysisRunning(job)) setCancelling(false);
        if (analysisRunning(job) || wasActive || (job && engineStatusRef.current !== 'IDLE')) {
          await state.reloadTranslation();
        }
        if (job?.status === 'done' && !analysisRunning(job) && !busyRef.current && refreshedJob.current !== job.id) {
          const next = await request<WorkbenchSnapshot>('/api/workbench');
          if (!valid() || busyRef.current || operation !== sequence.current || next.storage_key !== snapshotRef.current?.storage_key) return;
          const previous = snapshotRef.current;
          if (previous && JSON.stringify(editable(previous)) === JSON.stringify(editable(next))) {
            // 正式资料未被外部更新时，只刷新草稿和版本，保留手工输入。
            setSnapshot({ ...previous, revision: next.revision, worldbook_draft: next.worldbook_draft, character_drafts: next.character_drafts });
          } else if (!dirtyRef.current) {
            adopt(next);
          } else {
            setError(t('workbench_external_update'));
          }
          refreshedJob.current = job.id;
        }
      } catch (failure) {
        if (valid()) {
          setAnalysisChecking(false);
          setAnalysisPollError(errorText(failure));
        }
      } finally {
        if (alive) timer = window.setTimeout(() => void poll(), 1500);
      }
    };
    void poll();
    return () => { alive = false; window.clearTimeout(timer); };
  }, [adopt, projectKey, snapshotProjectKey, state.link, state.reloadTranslation, t]);

  async function startAnalysis(action: AnalysisAction) {
    setConfirm(null);
    if (!snapshot || !canAnalyze) return;
    const current = ++analysisSequence.current;
    const key = projectRef.current;
    const storageKey = snapshot.storage_key;
    setBusy(true);
    setAnalysisError('');
    try {
      const { job } = await request<{ job: AnalysisJob }>('/api/workbench/analysis', {
        method: 'POST', body: JSON.stringify({ storage_key: storageKey, revision: snapshot.revision, action, scope: analysisScope }),
      });
      if (current !== analysisSequence.current || key !== projectRef.current) return;
      analysisJobRef.current = job;
      setAnalysisJob(job);
      refreshedJob.current = '';
      setCancelling(false);
      await state.reloadTranslation();
    } catch (failure) {
      if (current === analysisSequence.current && key === projectRef.current) setAnalysisError(errorText(failure));
    } finally {
      if (current === analysisSequence.current && key === projectRef.current) {
        analysisSequence.current += 1;
        setBusy(false);
      }
    }
  }

  async function cancelAnalysis() {
    if (!analysisJob || !analysisActive || cancellationRequested || state.link !== 'open') return;
    const current = ++analysisSequence.current;
    const key = projectRef.current;
    setCancelling(true);
    setAnalysisError('');
    try {
      const job = await cancelJob(analysisJob.id);
      if (current !== analysisSequence.current || key !== projectRef.current) return;
      analysisJobRef.current = job;
      setAnalysisJob(job);
      if (!analysisRunning(job)) setCancelling(false);
      await state.reloadTranslation();
    } catch (failure) {
      if (current === analysisSequence.current && key === projectRef.current) {
        setCancelling(false);
        setAnalysisError(errorText(failure));
      }
    } finally {
      if (current === analysisSequence.current && key === projectRef.current) analysisSequence.current += 1;
    }
  }

  async function save() {
    if (!snapshot || !draft || mutationBlocked) return;
    if (draft.characters.some((card) => !card.name.trim())) {
      setError('请填写每张角色卡的名称后再保存。');
      return;
    }
    const current = ++sequence.current;
    const key = projectRef.current;
    setBusy(true);
    setError('');
    try {
      const next = await request<WorkbenchSnapshot>('/api/workbench', {
        method: 'PATCH', body: JSON.stringify({ storage_key: snapshot.storage_key, revision: snapshot.revision, ...draft }),
      });
      if (current === sequence.current && key === projectRef.current) {
        adopt(next);
        state.pushToast('success', '项目资料已保存');
      }
    } catch (failure) {
      if (current === sequence.current && key === projectRef.current) setError(errorText(failure));
    } finally { if (current === sequence.current && key === projectRef.current) setBusy(false); }
  }

  async function applyDrafts() {
    setConfirm(null);
    if (!snapshot || mutationBlocked || dirty) return;
    const current = ++sequence.current;
    const key = projectRef.current;
    setBusy(true);
    setError('');
    try {
      const next = await request<WorkbenchSnapshot>('/api/workbench/apply-drafts', {
        method: 'POST', body: JSON.stringify({ storage_key: snapshot.storage_key, revision: snapshot.revision }),
      });
      if (current === sequence.current && key === projectRef.current) {
        adopt(next);
        state.pushToast('success', '草稿已应用到正式项目资料');
      }
    } catch (failure) {
      if (current === sequence.current && key === projectRef.current) setError(errorText(failure));
    } finally { if (current === sequence.current && key === projectRef.current) setBusy(false); }
  }

  async function previewPrompt() {
    if (!snapshot || dirty || mutationBlocked) return;
    const current = ++sequence.current;
    const key = projectRef.current;
    setBusy(true);
    setError('');
    try {
      const next = await request<PromptPreview>('/api/workbench/preview', {
        method: 'POST', body: JSON.stringify({ storage_key: snapshot.storage_key, revision: snapshot.revision, sample }),
      });
      if (current === sequence.current && key === projectRef.current) setPreview(next);
    } catch (failure) {
      if (current === sequence.current && key === projectRef.current) setError(errorText(failure));
    } finally { if (current === sequence.current && key === projectRef.current) setBusy(false); }
  }

  function addCharacter() {
    if (!draft) return;
    const id = `character_${crypto.randomUUID()}`;
    const name = `新角色 ${draft.characters.length + 1}`;
    const card: CharacterCard = {
      id, name, name_translation: '', aliases: [], match_keywords: [name], identity: '',
      personality: '', speech_style: '', relationship_notes: '', prompt_notes: '', sample_lines: [],
      enabled: true, is_primary: false,
    };
    setDraft({ ...draft, characters: [...draft.characters, card] });
    setSelectedId(id);
    setSearch('');
    setTab('characters');
    setPreview(null);
  }

  function updateCharacter(key: keyof CharacterCard, value: unknown) {
    if (!draft || !selected) return;
    setDraft({ ...draft, characters: draft.characters.map((card) => card.id === selected.id ? { ...card, [key]: value } : card) });
    setPreview(null);
  }

  const jobResult = analysisResult(analysisJob);
  const analysisLabels = {
    scan: t('workbench_scan'), all: t('workbench_analysis_all'),
    worldbook: t('workbench_analysis_worldbook'), characters: t('workbench_analysis_characters'),
  };
  const scopeLabels = { current: t('workbench_scope_current'), full: t('workbench_scope_full') };
  const statusLabels = {
    pending: t('workbench_status_pending'), running: t('workbench_status_running'),
    done: t('workbench_status_done'), failed: t('workbench_status_failed'), cancelled: t('workbench_status_cancelled'),
  };
  const analysisHint = !projectCurrent ? t('workbench_project_changed')
    : dirty ? t('workbench_analysis_dirty')
    : state.link !== 'open' ? t('workbench_analysis_disconnected')
    : state.translation.engine_status !== 'IDLE' || state.translation.stop_barrier || state.translation.single_tasks
      ? t('workbench_analysis_engine_busy') : t('workbench_analysis_hint');
  const platforms = state.settings?.values.platforms;
  const activePlatform = Array.isArray(platforms)
    ? platforms.find((platform) => platform.id === Number(state.settings?.values.activate_platform ?? -1)) : undefined;

  function exportAssets() {
    if (!snapshot || !draft) return;
    const data = {
      schema_version: 1, worldbook: { ...snapshot.worldbook, ...draft.worldbook }, character_cards: draft.characters,
      worldbook_draft: snapshot.worldbook_draft, character_drafts: snapshot.character_drafts,
    };
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2) + '\n'], { type: 'application/json;charset=utf-8' }));
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'RenpyBox_Workbench.json';
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="rb-page rb-workbench">
      <PageHeader
        title="角色与世界观"
        description="维护当前项目的背景、角色资料与翻译上下文"
        actions={(
          <>
            <Button variant="default" disabled={!draft || busy || loading} onClick={exportAssets}>导出资料</Button>
            <Button variant="default" disabled={!hasDrafts || dirty || mutationBlocked} title={dirty ? '先保存手动编辑，再应用草稿' : undefined} onClick={() => setConfirm('apply')}>应用草稿</Button>
            <Button disabled={!dirty || mutationBlocked} onClick={() => void save()}>{busy ? '处理中…' : '保存修改'}</Button>
          </>
        )}
      />
      <p className="rb-workbench-status">
        <span>{loading ? '正在读取项目资料…' : dirty ? '有未保存的修改' : snapshot ? '项目资料已同步' : '等待选择项目'}</span>
        <span>{draft ? `世界观 ${worldCount} 项 · 角色 ${draft.characters.length} 位${dirty ? ' · 点击保存后用于后续翻译' : ''}` : '选择项目后，即可维护独立的背景与角色资料。'}</span>
      </p>
      {error ? (
        <Banner tone="error">
          {error}{' '}
          <Button variant="default" size="xs" disabled={busy || loading} onClick={() => dirty ? setConfirm('reload') : void reload()}>重新加载</Button>
        </Banner>
      ) : null}
      {analysisJob && projectCurrent ? (
        <div className="rb-workbench-analysis-status" role="status" aria-live="polite">
          <div>
            <strong>{analysisActive ? <Loader size="xs" aria-hidden /> : null}{cancellationRequested ? t('workbench_status_cancelling') : statusLabels[analysisJob.status]}</strong>
            <span>{jobResult ? analysisLabels[jobResult.action] : t('workbench_analysis_title')} · {jobResult ? scopeLabels[jobResult.scope] : scopeLabels[analysisScope]}</span>
            {analysisJob.error || jobResult?.message ? <p>{analysisJob.error || jobResult?.message}</p> : null}
            {analysisJob.status === 'done' && !analysisActive ? <p>{t('workbench_analysis_result').replace('{worldbook}', String(jobResult?.worldbook_fields ?? Object.values(snapshot?.worldbook_draft ?? {}).filter(Boolean).length)).replace('{characters}', String(jobResult?.character_count ?? snapshot?.character_drafts.length ?? 0))}</p> : null}
            {cancellationRequested ? <p>{t('workbench_cancel_hint')}</p> : null}
          </div>
          {analysisActive ? <Button variant="default" size="xs" disabled={cancellationRequested || state.link !== 'open'} onClick={() => void cancelAnalysis()}>{t('workbench_cancel_analysis')}</Button> : null}
        </div>
      ) : null}
      {analysisError || analysisPollError ? <Banner tone="error">{analysisError || analysisPollError}</Banner> : null}
      <Tabs className="rb-workbench-tabs" value={tab} onChange={(value) => { if (value) setTab(value as TabKey); }}>
        <Tabs.List>
          {TABS.map((item) => <Tabs.Tab key={item.key} value={item.key}>{item.label}</Tabs.Tab>)}
        </Tabs.List>
      </Tabs>
      <div className="rb-workbench-scroll">
        {!draft ? <Empty>{loading ? '正在加载…' : '项目资料暂不可用，请检查项目设置。'}</Empty> : tab === 'overview' ? (
          <>
            <div className="rb-workbench-summary">
              <div>
                <span className="rb-workbench-kicker">项目背景</span>
                <h2>{draft.worldbook.project_name || '项目背景尚未填写'}</h2>
                <p>{draft.worldbook.setting_summary || '填写背景、语气与人物关系，保存后用于下一次翻译。'}</p>
                <Button variant="default" onClick={() => setTab('worldbook')}>完善世界观</Button>
              </div>
              <div className="rb-workbench-stats">
                <div><strong>{worldCount}</strong><span>背景设定</span></div>
                <div><strong>{draft.characters.length}</strong><span>角色资料</span></div>
                <div><strong>{snapshot?.character_drafts.length ?? 0}</strong><span>待审核角色</span></div>
              </div>
            </div>
            <SettingsGroup title={t('workbench_analysis_title')} description={t('workbench_analysis_description')}>
              <div className="rb-workbench-analysis">
                <Select
                  label={t('workbench_analysis_scope')}
                  value={analysisScope}
                  allowDeselect={false}
                  data={Object.entries(scopeLabels).map(([value, label]) => ({ value, label }))}
                  disabled={busy || analysisActive}
                  onChange={(value) => { if (value) setAnalysisScope(value as AnalysisScope); }}
                />
                <Button variant="default" disabled={!canAnalyze} onClick={() => void startAnalysis('scan')}>{t('workbench_scan')}</Button>
                <Select
                  label={t('workbench_analysis_content')}
                  value={analysisAction}
                  allowDeselect={false}
                  data={(['all', 'worldbook', 'characters'] as const).map((value) => ({ value, label: analysisLabels[value] }))}
                  disabled={busy || analysisActive}
                  onChange={(value) => { if (value) setAnalysisAction(value as Exclude<AnalysisAction, 'scan'>); }}
                />
                <Button disabled={!canAnalyze} onClick={() => setConfirm('analysis')}>{t('workbench_generate')}</Button>
              </div>
              <p className="rb-workbench-analysis-hint">{analysisChecking && projectCurrent ? t('workbench_analysis_checking') : analysisHint}</p>
            </SettingsGroup>
            <SettingsGroup title="翻译上下文" description="世界观作为全局背景；角色卡根据原文中的名称、别名和关键词按需匹配。">
              <div className="rb-workbench-switch"><span>注入世界观</span><Switch checked={draft.worldbook_enabled} disabled={busy} label="注入世界观" onChange={(value) => { setDraft({ ...draft, worldbook_enabled: value }); setPreview(null); }} /></div>
              <div className="rb-workbench-switch"><span>注入角色卡</span><Switch checked={draft.characters_enabled} disabled={busy} label="注入角色卡" onChange={(value) => { setDraft({ ...draft, characters_enabled: value }); setPreview(null); }} /></div>
            </SettingsGroup>
            {hasDrafts ? (
              <SettingsGroup title={t('workbench_drafts_title')} description={t('workbench_drafts_description')}>
                <div className="rb-workbench-draft-review">
                  {Object.values(snapshot?.worldbook_draft ?? {}).some(Boolean) ? (
                    <section>
                      <h3>{t('workbench_draft_worldbook')}</h3>
                      <dl className="rb-workbench-draft-fields">
                        {WORLD_FIELDS.map(([key]) => snapshot?.worldbook_draft[key] ? (
                          <div key={key}><dt>{t('workbench_world_' + key as TextKey)}</dt><dd>{snapshot.worldbook_draft[key]}</dd></div>
                        ) : null)}
                      </dl>
                    </section>
                  ) : null}
                  {snapshot?.character_drafts.length ? (
                    <section>
                      <h3>{t('workbench_draft_characters')} · {snapshot.character_drafts.length}</h3>
                      {snapshot.character_drafts.map((card) => (
                        <details className="rb-workbench-draft-character" key={card.id}>
                          <summary><strong>{card.name || t('workbench_unnamed')}</strong><span>{card.name_translation || card.identity || t('workbench_draft_review_hint')}</span></summary>
                          <dl className="rb-workbench-draft-fields">
                            {CHARACTER_FIELDS.slice(1).map(([key]) => {
                              const value = Array.isArray(card[key]) ? (card[key] as string[]).filter(Boolean).join('\n') : String(card[key] ?? '');
                              return value ? <div key={key}><dt>{t('workbench_character_' + key as TextKey)}</dt><dd>{value}</dd></div> : null;
                            })}
                          </dl>
                        </details>
                      ))}
                    </section>
                  ) : null}
                  <div className="rb-workbench-preview-actions">
                    <span>{dirty ? t('workbench_analysis_dirty') : t('workbench_draft_apply_hint')}</span>
                    <Button disabled={dirty || mutationBlocked} onClick={() => setConfirm('apply')}>{t('workbench_apply_drafts')}</Button>
                  </div>
                </div>
              </SettingsGroup>
            ) : null}
          </>
        ) : tab === 'worldbook' ? (
          <SettingsGroup title="故事背景与翻译约定" description="内容保存在当前项目中。无需填写所有字段，优先记录背景摘要与整体语气。">
            <div className="workbench-form-grid">
              {WORLD_FIELDS.map(([key, label], index) => index < 2 ? (
                <TextInput
                  key={key}
                  className="workbench-field"
                  label={label}
                  value={draft.worldbook[key]}
                  disabled={busy}
                  onChange={(event) => { setDraft({ ...draft, worldbook: { ...draft.worldbook, [key]: event.currentTarget.value } }); setPreview(null); }}
                />
              ) : (
                <Textarea
                  key={key}
                  className="workbench-field workbench-field-wide"
                  label={label}
                  autosize
                  minRows={key === 'setting_summary' ? 4 : 3}
                  value={draft.worldbook[key]}
                  disabled={busy}
                  placeholder={key === 'spoiler_notes' ? '仅供译者理解，避免在译文中直接透露' : undefined}
                  onChange={(event) => { setDraft({ ...draft, worldbook: { ...draft.worldbook, [key]: event.currentTarget.value } }); setPreview(null); }}
                />
              ))}
            </div>
          </SettingsGroup>
        ) : tab === 'characters' ? (
          <div className="rb-workbench-characters">
            <aside className="rb-workbench-roster">
              <div className="rb-workbench-roster-head">
                <strong>角色资料 {draft.characters.length}</strong>
                <Button size="xs" variant="default" disabled={busy} onClick={addCharacter}>新增</Button>
              </div>
              <TextInput aria-label={t('workbench_search')} placeholder={t('workbench_search_placeholder')} value={search} onChange={(event) => setSearch(event.currentTarget.value)} />
              <div className="rb-workbench-roster-list">
                {visibleCharacters.map((card) => (
                  <button key={card.id} type="button" className="rb-workbench-character" aria-pressed={selectedId === card.id} onClick={() => setSelectedId(card.id)}>
                    <span>{(card.name || '?').slice(0, 2)}</span>
                    <span><strong>{card.name || '未命名角色'}</strong><small>{card.name_translation || (card.enabled ? '已启用' : '未启用')}</small></span>
                  </button>
                ))}
                {!draft.characters.length ? <Empty>新增第一位角色，记录身份与说话风格。</Empty> : !visibleCharacters.length ? (
                  <Empty><span>{t('workbench_search_empty')}</span><Button variant="subtle" size="xs" onClick={() => setSearch('')}>{t('workbench_clear_search')}</Button></Empty>
                ) : null}
              </div>
            </aside>
            {selected ? (
              <section className="rb-workbench-editor">
                <div className="rb-workbench-editor-head">
                  <div>
                    <h2>{selected.name || '未命名角色'}</h2>
                    <p>正式角色卡 · 保存后用于后续翻译</p>
                  </div>
                  <Button variant="default" disabled={busy} onClick={() => setConfirm('delete')}>删除角色</Button>
                </div>
                <div className="workbench-form-grid">
                  {CHARACTER_FIELDS.map(([key, label], index) => index < 2 ? (
                    <TextInput
                      key={key}
                      className="workbench-field"
                      label={label}
                      value={String(selected[key])}
                      disabled={busy}
                      onChange={(event) => updateCharacter(key, event.currentTarget.value)}
                    />
                  ) : (
                    <Textarea
                      key={key}
                      className="workbench-field workbench-field-wide"
                      label={label}
                      description={LIST_FIELDS.has(key) ? '每行一项' : undefined}
                      autosize
                      minRows={3}
                      value={Array.isArray(selected[key]) ? (selected[key] as string[]).join('\n') : String(selected[key])}
                      disabled={busy}
                      onChange={(event) => updateCharacter(key, LIST_FIELDS.has(key) ? event.currentTarget.value.split('\n') : event.currentTarget.value)}
                    />
                  ))}
                </div>
                <div className="rb-workbench-switch"><span>启用此角色</span><Switch checked={selected.enabled} label="启用此角色" disabled={busy} onChange={(value) => updateCharacter('enabled', value)} /></div>
                <div className="rb-workbench-switch"><span>主要角色（优先匹配）</span><Switch checked={selected.is_primary} label="主要角色" disabled={busy} onChange={(value) => updateCharacter('is_primary', value)} /></div>
              </section>
            ) : <Empty>选择一位角色，或新增角色资料。</Empty>}
          </div>
        ) : (
          <>
            <SettingsGroup title="试一段原文，检查上下文" description="检查已保存资料的角色命中和背景片段；预览不会调用 AI，也不会产生费用。">
              <Textarea
                label="原文样例"
                autosize
                minRows={5}
                value={sample}
                disabled={busy}
                placeholder="输入包含角色名或关键词的原文…"
                onChange={(event) => { setSample(event.currentTarget.value); setPreview(null); }}
              />
              <div className="rb-workbench-preview-actions">
                <span>{dirty ? '先保存修改，再查看最新上下文。' : '匹配遵循实际翻译规则。'}</span>
                <Button disabled={dirty || mutationBlocked} onClick={() => void previewPrompt()}>生成预览</Button>
              </div>
            </SettingsGroup>
            {preview ? (
              <SettingsGroup title={`命中角色：${preview.matched_names.join('、') || '无'}`}>
                <pre className="rb-workbench-preview">{preview.context || '未产生上下文。请检查资产开关、内容或匹配关键词。'}</pre>
              </SettingsGroup>
            ) : null}
          </>
        )}
      </div>
      {confirm === 'analysis' ? <Dialog title={t('workbench_confirm_analysis')} confirmText={t('workbench_confirm_generate')} cancelText={t('workbench_cancel')} onCancel={() => setConfirm(null)} onConfirm={() => void startAnalysis(analysisAction)}>
        <p>{t('workbench_analysis_cost')}</p>
        <dl className="rb-workbench-draft-fields">
          <div><dt>{t('workbench_analysis_platform')}</dt><dd>{String(activePlatform?.name || t('workbench_current_platform'))}</dd></div>
          <div><dt>{t('workbench_analysis_scope')}</dt><dd>{scopeLabels[analysisScope]}</dd></div>
          <div><dt>{t('workbench_analysis_content')}</dt><dd>{analysisLabels[analysisAction]}</dd></div>
        </dl>
        <p>{t('workbench_analysis_confirm_hint')}</p>
      </Dialog> : null}
      {confirm === 'delete' && selected ? <Dialog title="删除角色资料" confirmText="删除" onCancel={() => setConfirm(null)} onConfirm={() => { if (!draft) return; const cards = draft.characters.filter((card) => card.id !== selected.id); setDraft({ ...draft, characters: cards }); setSelectedId(cards[0]?.id ?? ''); setConfirm(null); setPreview(null); }}>删除「{selected.name}」？点击保存后，删除才会写入当前项目。</Dialog> : null}
      {confirm === 'reload' ? <Dialog title="重新加载项目资料" confirmText="丢弃并重新加载" onCancel={() => setConfirm(null)} onConfirm={() => { setConfirm(null); void reload(); }}>当前未保存的修改将被丢弃。</Dialog> : null}
      {confirm === 'apply' ? <Dialog title="应用已有草稿" confirmText="应用草稿" onCancel={() => setConfirm(null)} onConfirm={() => void applyDrafts()}>草稿将合并到正式世界观和角色资料中，并启用对应上下文。正式资料中的同名字段可能更新。</Dialog> : null}
    </div>
  );
}
