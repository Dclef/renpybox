/** 一键翻译：准备抽取 → 跳转翻译页启停 → 确认应用译文。 */
import { useEffect, useRef, useState } from 'react';
import { Button, Checkbox, Form, Input, Progress, Radio, Select } from 'antd';

import { cancelJob, request } from '../api';
import { useT } from '../i18n';
import { isIncrementalOutput } from '../onekeyView.mjs';
import type { JobSnapshot } from '../types';
import type { AppState } from '../useAppState';
import { Banner, Dialog, SettingsGroup } from '../ui';

type ExtractMode = 'auto' | 'full' | 'incremental';
type SupplementMode = 'off' | 'precise' | 'aggressive';

interface OneKeyResult {
  project_key?: string;
  message?: string;
  worker_active?: boolean;
  stage?: string;
  incremental?: boolean;
  detect_status?: string;
  output_dir?: string;
  incremental_dir?: string;
  main_output_dir?: string;
  tl_dir?: string;
  language?: string;
  game_dir?: string;
  project_root?: string;
  payload?: Record<string, unknown>;
}

/** 后端按项目身份派生的写入范围，确认框只展示这些路径。 */
interface OneKeyLayout {
  tl_dir: string;
  incremental_dir: string;
  output_dir: string;
  incremental_output_dir: string;
  full_backup_pattern: string;
  ui_pack_dir: string;
}

interface DetectResult {
  status: string;
  message: string;
  project_key: string;
  existing_translation?: { exists: boolean; rpy_count: number; tl_dir: string };
  layout?: OneKeyLayout;
  auto_exe?: string | null;
  declined_count?: number;
  declined_path?: string;
}

type OneKeyJob = JobSnapshot & { cancel_requested?: boolean; result?: OneKeyResult | null };

function jobResult(job: OneKeyJob | null): OneKeyResult | null {
  return job?.result && typeof job.result === 'object' ? job.result : null;
}

function jobRunning(job: OneKeyJob | null): boolean {
  return Boolean(job && (job.status === 'pending' || job.status === 'running' || jobResult(job)?.worker_active));
}

const errorText = (error: unknown) => (error instanceof Error ? error.message : String(error));

const fill = (text: string, vars: Record<string, string | number>) =>
  Object.entries(vars).reduce((acc, [key, value]) => acc.split(`{${key}}`).join(String(value)), text);

export function OneKeyTranslatePage(props: {
  state: AppState;
  mode?: 'full' | 'apply';
  onOpenTranslation: () => void;
  onOpenWorkbench: () => void;
  onOpenGlossary: () => void;
  onOpenPreserve?: () => void;
}) {
  const { state, mode = 'full', onOpenTranslation, onOpenWorkbench, onOpenGlossary, onOpenPreserve } = props;
  const t = useT();
  const values = state.settings?.values ?? {};
  const projectRoot = String(state.project?.renpy_project_path ?? '');
  const tlFolder = String(state.project?.renpy_tl_folder ?? '');
  const defaultLanguage = tlFolder.split(/[\\/]/).filter(Boolean).at(-1) || 'chinese';
  const [gameDir, setGameDir] = useState(projectRoot);
  const [language, setLanguage] = useState(defaultLanguage);
  // 没有本次准备结果时按当前输出目录判断；完整流程准备完成后以任务结果为准
  const [incremental, setIncremental] = useState(() => isIncrementalOutput(values.output_folder));
  // 旧 Qt：检测到已有译文时默认增量；用户明确选择全量/增量后以用户选择为准
  const [extractMode, setExtractMode] = useState<ExtractMode>('auto');
  // 旧 Qt 一键流程总会尝试官方抽取（自动找 game.exe）；EXE 留空即交给后端自动识别
  const [officialExtract, setOfficialExtract] = useState(true);
  const [exePath, setExePath] = useState('');
  // 抽取选项在页面上可临时修改，开始准备时随请求落盘；未修改时沿用已保存配置
  const [supplementOverride, setSupplementOverride] = useState<SupplementMode | null>(null);
  const [injectOverride, setInjectOverride] = useState<boolean | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const pending = useRef(false);
  const completed = useRef('');
  const revision = useRef(0);
  const selectionEdited = useRef(false);
  const [detect, setDetect] = useState<DetectResult | null>(null);
  const [ready, setReady] = useState<OneKeyResult | null>(null);
  const [job, setJob] = useState<OneKeyJob | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [confirm, setConfirm] = useState<'prepare' | 'apply' | 'declined' | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [checking, setChecking] = useState(true);
  const projectKey = JSON.stringify([projectRoot, tlFolder, values.output_folder]);
  const projectRef = useRef(projectKey);
  const sequence = useRef(0);
  // 完整流程的增量标记由准备结果决定，不参与选择快照，避免回填结果时清掉 ready
  const selection = JSON.stringify([gameDir, language, mode === 'apply' ? incremental : null]);
  const selectionRef = useRef(selection);
  selectionRef.current = selection;
  projectRef.current = projectKey;
  const active = jobRunning(job);
  const busy = active || submitting;
  const engineBusy = state.translation.engine_status !== 'IDLE' || state.translation.stop_barrier || state.translation.single_tasks;

  const savedSupplement: SupplementMode = values.extract_use_custom === false || values.extract_supplement_mode === 'off'
    ? 'off'
    : values.extract_supplement_mode === 'aggressive' ? 'aggressive' : 'precise';
  const supplementMode = supplementOverride ?? savedSupplement;
  const injectUiPack = injectOverride ?? values.onekey_inject_base_box === true;
  const verifyUppercase = values.renpy_verify_uppercase_candidates !== false;
  const autoMergeCleanup = values.renpy_incremental_auto_merge_cleanup !== false;
  const extractConflict = !officialExtract && supplementMode === 'off';

  useEffect(() => {
    selectionEdited.current = false;
    setGameDir(projectRoot);
    setLanguage(defaultLanguage);
    setOfficialExtract(true);
    setExePath('');
  }, [projectRoot, defaultLanguage]);

  useEffect(() => {
    sequence.current += 1;
    // 设置晚于首帧加载或输出目录变化时重新推断，避免沿用空配置下的判断
    setIncremental(isIncrementalOutput(values.output_folder));
    setOfficialExtract(true);
    setExePath('');
    setExtractMode('auto');
    setSupplementOverride(null);
    setInjectOverride(null);
    setJob(null);
    setDetect(null);
    setReady(null);
    setError('');
    setNotice('');
    setConfirm(null);
    setCancelling(false);
    setChecking(true);
    return () => { sequence.current += 1; };
  }, [projectKey]);

  useEffect(() => {
    setDetect(null);
    setReady(null);
    setConfirm(null);
  }, [selection]);

  useEffect(() => {
    if (state.link !== 'open') return;
    let alive = true;
    let timer = 0;
    const key = projectKey;
    const current = sequence.current;
    const poll = async () => {
      try {
        if (pending.current) return;
        const requestRevision = revision.current;
        const { job: next } = await request<{ job: OneKeyJob | null }>('/api/onekey');
        if (!alive || key !== projectRef.current || current !== sequence.current || requestRevision !== revision.current || pending.current) return;
        setJob(next);
        setChecking(false);
        if (!jobRunning(next)) setCancelling(false);
        const result = jobResult(next);
        if (next?.status === 'done' && result?.stage === 'ready') {
          const path = gameDir.replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase();
          const matches = [result.project_root, result.game_dir].some(value => value?.replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase() === path);
          const followResult = mode === 'full' || !selectionEdited.current;
          if (matches && result.language === language && (followResult || Boolean(result.incremental) === incremental)) {
            if (followResult) setIncremental(Boolean(result.incremental));
            setReady(result);
          }
        }
        if (next && !jobRunning(next) && completed.current !== next.id) {
          completed.current = next.id;
          await Promise.all([state.reloadSettings(), state.reloadProject(), state.reloadTranslation()]);
        }
      } catch (failure) {
        if (alive && key === projectRef.current && current === sequence.current) {
          setChecking(false);
          setError(errorText(failure));
        }
      } finally {
        if (alive) timer = window.setTimeout(() => void poll(), 1500);
      }
    };
    void poll();
    return () => { alive = false; window.clearTimeout(timer); };
  }, [projectKey, state.link, mode, gameDir, language, incremental, state.reloadSettings, state.reloadProject, state.reloadTranslation]);

  async function runDetect(): Promise<DetectResult | null> {
    if (pending.current) return null;
    pending.current = true;
    revision.current += 1;
    setSubmitting(true);
    setError('');
    const expected = selectionRef.current;
    const context = projectRef.current;
    try {
      const next = await request<DetectResult>('/api/onekey/detect', {
        method: 'POST',
        body: JSON.stringify({ game_dir: gameDir, language, project_key: '' }),
      });
      if (expected !== selectionRef.current || context !== projectRef.current) return null;
      setDetect(next);
      return next;
    } catch (failure) {
      if (expected === selectionRef.current && context === projectRef.current) setError(errorText(failure));
      return null;
    } finally {
      pending.current = false;
      setSubmitting(false);
    }
  }

  /** 确认框必须展示后端派生的真实写入范围，缺少检测结果时先检测。 */
  async function openConfirm(kind: 'prepare' | 'apply' | 'declined') {
    if (kind === 'apply' && ready) { setConfirm(kind); return; }
    if (detect || await runDetect()) setConfirm(kind);
  }

  async function runPrepare() {
    if (pending.current) return;
    pending.current = true;
    revision.current += 1;
    setSubmitting(true);
    const context = projectRef.current;
    const expected = selectionRef.current;
    setConfirm(null);
    setError('');
    setNotice('');
    setReady(null);
    try {
      const { job: next } = await request<{ job: OneKeyJob }>('/api/onekey/prepare', {
        method: 'POST',
        body: JSON.stringify({
          game_dir: gameDir,
          language,
          mode: extractMode,
          confirm_write: true,
          official_extract: officialExtract,
          // 确认框里展示的 EXE 就是实际运行的 EXE；未勾选官方抽取时绝不传路径
          exe_path: officialExtract ? (exePath.trim() || detect?.auto_exe || null) : null,
          supplement_mode: supplementMode,
          inject_ui_pack: injectUiPack,
          project_key: detect?.project_key || '',
        }),
      });
      if (context !== projectRef.current || expected !== selectionRef.current) return;
      setJob(next);
      await Promise.all([state.reloadTranslation(), state.reloadSettings()]);
    } catch (failure) {
      if (context === projectRef.current && expected === selectionRef.current) setError(errorText(failure));
    } finally {
      pending.current = false;
      setSubmitting(false);
    }
  }

  async function runApply() {
    if (pending.current) return;
    pending.current = true;
    revision.current += 1;
    setSubmitting(true);
    const context = projectRef.current;
    const expected = selectionRef.current;
    setConfirm(null);
    setError('');
    setNotice('');
    try {
      const useIncremental = Boolean(ready?.incremental ?? incremental);
      const { job: next } = await request<{ job: OneKeyJob }>('/api/onekey/apply', {
        method: 'POST',
        body: JSON.stringify({
          game_dir: gameDir,
          language,
          incremental: useIncremental,
          confirm: true,
          incremental_output: useIncremental ? (ready?.output_dir || null) : null,
          incremental_target: useIncremental ? (ready?.incremental_dir || null) : null,
          main_output: ready?.main_output_dir || null,
          auto_merge_cleanup: useIncremental ? autoMergeCleanup : null,
          project_key: ready?.project_key || detect?.project_key || '',
        }),
      });
      if (context !== projectRef.current || expected !== selectionRef.current) return;
      setJob(next);
      await state.reloadTranslation();
    } catch (failure) {
      if (context === projectRef.current && expected === selectionRef.current) setError(errorText(failure));
    } finally {
      pending.current = false;
      setSubmitting(false);
    }
  }

  async function runClearDeclined() {
    if (pending.current) return;
    pending.current = true;
    setSubmitting(true);
    const context = projectRef.current;
    const expected = selectionRef.current;
    setConfirm(null);
    setError('');
    setNotice('');
    try {
      const { cleared } = await request<{ cleared: number }>('/api/onekey/declined/clear', {
        method: 'POST',
        body: JSON.stringify({ game_dir: gameDir, language, confirm: true, project_key: detect?.project_key || '' }),
      });
      if (context !== projectRef.current || expected !== selectionRef.current) return;
      setNotice(cleared ? fill(t('onekey_clear_declined_done'), { count: cleared }) : t('onekey_clear_declined_empty'));
      setDetect(prev => (prev ? { ...prev, declined_count: 0 } : prev));
    } catch (failure) {
      if (context === projectRef.current && expected === selectionRef.current) setError(errorText(failure));
    } finally {
      pending.current = false;
      setSubmitting(false);
    }
  }

  async function pickGame() {
    const context = projectRef.current;
    const path = await window.renpy?.pickFolder?.(gameDir || undefined);
    if (path && context === projectRef.current) { selectionEdited.current = true; setGameDir(path); }
  }

  async function pickExe() {
    const context = projectRef.current;
    const path = await window.renpy?.pickFile?.({
      defaultPath: exePath || gameDir || undefined,
      filters: [{ name: 'Executable', extensions: ['exe'] }],
    });
    if (path && context === projectRef.current) { setExePath(path); setOfficialExtract(true); }
  }

  async function onCancel() {
    if (!job || !active || cancelling) return;
    setCancelling(true);
    try {
      await cancelJob(job.id);
    } catch (failure) {
      setCancelling(false);
      setError(errorText(failure));
    }
  }

  const result = jobResult(job);
  const prepared = ready?.stage === 'ready';
  const applied = job?.status === 'done' && result?.stage === 'done';
  const missingGameDir = !gameDir.trim();
  const statusText = checking
    ? t('onekey_checking')
    : active
      ? (cancelling || job?.cancel_requested ? t('onekey_cancelling') : (result?.message || t('onekey_running')))
      : job?.status === 'failed'
        ? (job.error || result?.message || t('onekey_failed'))
        : job?.status === 'cancelled'
          ? (result?.stage === 'done' ? t('onekey_apply_finished_after_cancel') : t('onekey_cancelled'))
          : job?.status === 'done' && result?.stage === 'done'
            ? (result.message || t('archive_done'))
          : prepared
            ? (ready?.message || t('onekey_ready'))
            : detect
              ? detect.message
              : t('onekey_idle');

  const layout = detect?.layout;
  const existing = detect?.existing_translation;
  const willIncremental = Boolean(existing?.exists) && extractMode !== 'full';
  const chosenExe = officialExtract ? (exePath.trim() || detect?.auto_exe || '') : '';
  const supplementLabel = t(`onekey_supplement_${supplementMode}` as const);
  const modeText = !detect
    ? t('onekey_mode_unknown')
    : existing?.exists
      ? `${fill(t('onekey_existing_found'), { dir: existing.tl_dir, count: existing.rpy_count })} ${t(willIncremental ? 'onekey_mode_resolved_incremental' : 'onekey_mode_resolved_full')}`
      : t('onekey_existing_none');

  const applyIncremental = Boolean(ready?.incremental ?? incremental);
  const applyTl = ready?.tl_dir || layout?.tl_dir || '';
  const applyOutput = applyIncremental
    ? (ready?.output_dir || layout?.incremental_output_dir || '')
    : (ready?.output_dir || ready?.main_output_dir || layout?.output_dir || '');
  const applyStaging = ready?.incremental_dir || layout?.incremental_dir || '';

  const autoMergeCheckbox = (
    <Form.Item extra={t('onekey_auto_merge_cleanup_hint')} style={{ marginBottom: 0 }}>
      <Checkbox
        checked={autoMergeCleanup}
        onChange={(event) => void state.saveSettings({ renpy_incremental_auto_merge_cleanup: event.target.checked })}
        disabled={busy || state.link !== 'open'}
      >
        {t('onekey_auto_merge_cleanup')}
      </Checkbox>
    </Form.Item>
  );

  return (
    <div className="rb-onekey-page rb-page-scroll">
      {error ? <Banner tone="error">{error}</Banner> : null}
      {notice ? <Banner tone="success" onDismiss={() => setNotice('')}>{notice}</Banner> : null}
      <Banner tone={prepared ? 'success' : 'info'}>{statusText}</Banner>
      {mode === 'full' && (missingGameDir || !projectRoot) ? (
        <Banner tone="warning">
          {t(missingGameDir ? 'onekey_need_game_dir' : 'onekey_need_project')}
          {missingGameDir && window.renpy?.pickFolder ? (
            <Button onClick={() => void pickGame()} disabled={busy}>{t('archive_pick_folder')}</Button>
          ) : null}
        </Banner>
      ) : null}
      {active ? <Progress percent={Math.min(100, 100 * (job?.progress || 0))} aria-label={t('onekey_running')} /> : null}
      {active ? (
        <div className="rb-tool-actions">
          <Button onClick={() => void onCancel()} disabled={cancelling || Boolean(job?.cancel_requested)}>
            {t('onekey_cancel')}
          </Button>
        </div>
      ) : null}

      {mode === 'full' ? (
        <SettingsGroup title={t('onekey_prepare_title')} description={t('onekey_prepare_desc')}>
          <Form.Item label={t('onekey_game_dir')} style={{ marginBottom: 0 }}>
            <Input value={gameDir} onChange={(event) => { selectionEdited.current = true; setGameDir(event.target.value); }} disabled={busy} />
          </Form.Item>
          <Form.Item label={t('onekey_language')} style={{ marginBottom: 0 }}>
            <Input value={language} onChange={(event) => { selectionEdited.current = true; setLanguage(event.target.value); }} disabled={busy} />
          </Form.Item>
          <Form.Item label={t('onekey_mode_label')} extra={modeText} style={{ marginBottom: 0 }}>
            <Radio.Group value={extractMode} onChange={(event) => setExtractMode(event.target.value as ExtractMode)} disabled={busy}>
              <Radio value="auto">{t('onekey_mode_auto')}</Radio>
              <Radio value="incremental">{t('onekey_mode_incremental')}</Radio>
              <Radio value="full">{t('onekey_mode_full')}</Radio>
            </Radio.Group>
          </Form.Item>
          <Checkbox checked={officialExtract} onChange={(event) => setOfficialExtract(event.target.checked)} disabled={busy}>{t('onekey_official_extract')}</Checkbox>
          <Form.Item label={t('onekey_official_exe')} extra={t('onekey_official_hint')} style={{ marginBottom: 0 }}>
            <Input value={exePath} onChange={(event) => setExePath(event.target.value)} disabled={busy || !officialExtract} placeholder={detect?.auto_exe || undefined} />
          </Form.Item>
          {extractConflict ? <Banner tone="warning">{t('onekey_supplement_conflict')}</Banner> : null}
          <div className="rb-tool-actions">
            <Button onClick={() => void pickGame()} disabled={busy}>{t('archive_pick_folder')}</Button>
            <Button onClick={() => void pickExe()} disabled={busy}>{t('asset_pick_exe')}</Button>
            <Button onClick={() => void runDetect()} disabled={busy || !gameDir.trim() || state.link !== 'open'}>
              {t('onekey_detect')}
            </Button>
            <Button type="primary" onClick={() => void openConfirm('prepare')} disabled={busy || engineBusy || extractConflict || !gameDir.trim() || state.link !== 'open'}>
              {t('onekey_prepare')}
            </Button>
          </div>
          <p className="card-description">{t('onekey_no_auto_translate')}</p>
        </SettingsGroup>
      ) : null}

      {mode === 'full' ? (
        <SettingsGroup title={t('onekey_advanced_title')} description={t('onekey_advanced_desc')}>
          <Form.Item label={t('onekey_supplement_mode')} extra={t('onekey_supplement_hint')} style={{ marginBottom: 0 }}>
            <Select<SupplementMode>
              value={supplementMode}
              onChange={(value) => setSupplementOverride(value)}
              disabled={busy}
              style={{ maxWidth: 280 }}
              options={[
                { value: 'off', label: t('onekey_supplement_off') },
                { value: 'precise', label: t('onekey_supplement_precise') },
                { value: 'aggressive', label: t('onekey_supplement_aggressive') },
              ]}
            />
          </Form.Item>
          <Form.Item extra={t('onekey_inject_ui_pack_hint')} style={{ marginBottom: 0 }}>
            <Checkbox checked={injectUiPack} onChange={(event) => setInjectOverride(event.target.checked)} disabled={busy}>
              {t('onekey_inject_ui_pack')}
            </Checkbox>
          </Form.Item>
          <Form.Item extra={t('onekey_verify_uppercase_hint')} style={{ marginBottom: 0 }}>
            <Checkbox
              checked={verifyUppercase}
              onChange={(event) => void state.saveSettings({ renpy_verify_uppercase_candidates: event.target.checked })}
              disabled={state.link !== 'open'}
            >
              {t('onekey_verify_uppercase')}
            </Checkbox>
          </Form.Item>
          <div className="rb-tool-actions">
            <Button danger onClick={() => void openConfirm('declined')} disabled={busy || engineBusy || !gameDir.trim() || state.link !== 'open'}>
              {t('onekey_clear_declined')}
            </Button>
          </div>
          {detect ? <p className="card-description">{fill(t('onekey_clear_declined_count'), { count: detect.declined_count ?? 0 })}</p> : null}
        </SettingsGroup>
      ) : null}

      {mode === 'full' && prepared ? (
        <SettingsGroup title={t('onekey_translate_title')} description={t('onekey_translate_desc')}>
          <div className="rb-tool-actions">
            <Button type="primary" onClick={onOpenTranslation}>{t('onekey_next_translation')}</Button>
            <Button onClick={onOpenWorkbench}>{t('onekey_open_workbench')}</Button>
            <Button onClick={onOpenGlossary}>{t('onekey_open_glossary')}</Button>
            {onOpenPreserve ? <Button onClick={onOpenPreserve}>{t('onekey_open_preserve')}</Button> : null}
          </div>
          <p className="card-description">
            {t('onekey_paths_hint')
              .replace('{input}', String(values.input_folder ?? ready?.tl_dir ?? ''))
              .replace('{output}', String(values.output_folder ?? ready?.output_dir ?? ''))}
          </p>
        </SettingsGroup>
      ) : null}

      <SettingsGroup title={t('onekey_apply_title')} description={t('onekey_apply_desc')}>
        {mode === 'apply' ? (
          <>
            <Form.Item label={t('onekey_game_dir')} style={{ marginBottom: 0 }}>
              <Input value={gameDir} onChange={(event) => { selectionEdited.current = true; setGameDir(event.target.value); }} disabled={busy} />
            </Form.Item>
            <Form.Item label={t('onekey_language')} style={{ marginBottom: 0 }}>
              <Input value={language} onChange={(event) => { selectionEdited.current = true; setLanguage(event.target.value); }} disabled={busy} />
            </Form.Item>
            <Checkbox checked={incremental} onChange={(event) => { selectionEdited.current = true; setIncremental(event.target.checked); }} disabled={busy}>{t('onekey_incremental')}</Checkbox>
          </>
        ) : null}
        {autoMergeCheckbox}
        <div className="rb-tool-actions">
          <Button type="primary" onClick={() => void openConfirm('apply')} disabled={busy || engineBusy || !projectRoot || state.link !== 'open'}>
            {t('onekey_apply')}
          </Button>
          {mode === 'apply' && !applied ? (
            <Button onClick={onOpenTranslation}>{t('onekey_open_translation')}</Button>
          ) : null}
        </div>
        {applied ? (
          <div className="rb-tool-actions">
            <span className="card-description">{t('onekey_applied_next')}</span>
            <Button type="primary" onClick={onOpenTranslation}>{t('onekey_next_translation')}</Button>
            <Button onClick={onOpenWorkbench}>{t('onekey_open_workbench')}</Button>
          </div>
        ) : null}
      </SettingsGroup>

      {confirm === 'prepare' ? (
        <Dialog title={t('onekey_prepare_confirm_title')} confirmText={t('onekey_prepare')} cancelText={t('workbench_cancel')} onConfirm={() => void runPrepare()} onCancel={() => setConfirm(null)}>
          <p>{t('onekey_prepare_confirm')}</p>
          {layout ? (
            <p>{willIncremental
              ? fill(t('onekey_prepare_scope_incremental'), { tl: layout.tl_dir, staging: layout.incremental_dir, output: layout.incremental_output_dir })
              : fill(t('onekey_prepare_scope_full'), { tl: layout.tl_dir, backup: layout.full_backup_pattern, output: layout.output_dir })}</p>
          ) : null}
          <p>{!officialExtract
            ? t('onekey_prepare_confirm_no_official')
            : chosenExe ? t('onekey_prepare_confirm_exe').replace('{exe}', chosenExe)
              : detect ? t('onekey_prepare_confirm_no_exe') : t('onekey_prepare_confirm_auto')}</p>
          <p>{fill(t('onekey_prepare_scope_supplement'), { mode: supplementLabel })}</p>
          {injectUiPack && layout ? (
            <p>
              {fill(t('onekey_prepare_scope_ui_pack'), { dir: layout.ui_pack_dir })}
              {willIncremental ? ` ${t('onekey_prepare_scope_ui_pack_incremental')}` : ''}
            </p>
          ) : null}
          <p className="card-description">{gameDir}</p>
        </Dialog>
      ) : null}
      {confirm === 'apply' ? (
        <Dialog title={t('onekey_apply_confirm_title')} confirmText={t('onekey_apply')} cancelText={t('workbench_cancel')} onConfirm={() => void runApply()} onCancel={() => setConfirm(null)}>
          <p>{t('onekey_apply_confirm')}</p>
          {applyTl && applyOutput ? (
            <p>{applyIncremental
              ? fill(t('onekey_apply_confirm_incremental'), { output: applyOutput, tl: applyTl, staging: applyStaging })
              : fill(t('onekey_apply_confirm_full'), { output: applyOutput, tl: applyTl })}</p>
          ) : null}
          {applyIncremental ? <p>{t(autoMergeCleanup ? 'onekey_apply_confirm_cleanup_on' : 'onekey_apply_confirm_cleanup_off')}</p> : null}
        </Dialog>
      ) : null}
      {confirm === 'declined' ? (
        <Dialog title={t('onekey_clear_declined_title')} confirmText={t('onekey_clear_declined')} cancelText={t('workbench_cancel')} onConfirm={() => void runClearDeclined()} onCancel={() => setConfirm(null)}>
          <p>{fill(t('onekey_clear_declined_confirm'), { path: detect?.declined_path || '' })}</p>
          <p className="card-description">{fill(t('onekey_clear_declined_count'), { count: detect?.declined_count ?? 0 })}</p>
        </Dialog>
      ) : null}
    </div>
  );
}
