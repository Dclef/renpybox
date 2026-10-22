/** 源码翻译 game/*.rpy：对齐 Qt SourceTranslatePage，经 /api/translation/start（mode=source）。 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Form, Input, Progress, Radio, Select } from 'antd';

import * as api from '../api';
import {
  decodeLangChoice,
  defaultSourceFileOutputDir,
  defaultSourceOutputDir,
  encodeLangChoice,
  normalizePath,
  sourceResumeView,
  toolboxOwnerKey,
  toolboxStartGate,
  toolboxTlLanguageName,
  TOOLBOX_LANG_OPTIONS,
  translationModeSummary,
  translationProgressView,
  validateSourceLayout,
} from '../toolboxTranslateView.mjs';
import type { PageKey } from '../nav';
import type { AppState } from '../useAppState';
import type { JobSnapshot, TranslationResumableInfo } from '../types';
import { Banner, Dialog, SettingsGroup, Switch } from '../ui';
import { useT } from '../i18n';

type InputKind = 'folder' | 'file';

// 进度/结果提示的文案键（模块级常量，避免进入 useEffect 依赖）
const TXT = {
  backingUp: 'source_translate_backing_up',
  backupDone: 'source_translate_backup_done_started',
  backupCancelled: 'source_translate_backup_cancelled',
  backupFailed: 'source_translate_backup_failed',
} as const;

export function SourceTranslatePage(props: {
  state: AppState;
  onNavigate?: (page: PageKey) => void;
}) {
  const { state, onNavigate } = props;
  const t = useT();
  const values = state.settings?.values ?? {};
  const projectPath = String(state.project?.renpy_project_path ?? '');
  const gameFolder = String(state.project?.renpy_game_folder ?? '');
  const tlFolder = String(state.project?.renpy_tl_folder ?? '');
  const ownerKey = useMemo(
    () => toolboxOwnerKey(projectPath, toolboxTlLanguageName(tlFolder)),
    [projectPath, tlFolder],
  );

  const [inputKind, setInputKind] = useState<InputKind>('folder');
  const [inputPath, setInputPath] = useState(gameFolder);
  const [sourceChoice, setSourceChoice] = useState('EN');
  const [targetChoice, setTargetChoice] = useState(() => {
    const code = String(values.target_language ?? 'ZH');
    return encodeLangChoice(code, Boolean(values.traditional_chinese_enable));
  });
  const [backup, setBackup] = useState(false);
  const [externalBackup, setExternalBackup] = useState(false);
  const [externalBackupDir, setExternalBackupDir] = useState('');
  const [busy, setBusy] = useState(false);
  const [backingUp, setBackingUp] = useState(false);
  const [backupMessage, setBackupMessage] = useState('');
  const [backupPercent, setBackupPercent] = useState(0);
  const [backupJobId, setBackupJobId] = useState('');
  const [assetsMissing, setAssetsMissing] = useState(false);
  const [resumeInfo, setResumeInfo] = useState<TranslationResumableInfo | null>(null);
  const [confirmRestart, setConfirmRestart] = useState(false);
  const pollGen = useRef(0);

  useEffect(() => {
    setInputKind('folder');
    setInputPath(gameFolder);
  }, [gameFolder]);

  const outputPath = useMemo(() => {
    if (inputKind === 'file') {
      return defaultSourceFileOutputDir(inputPath);
    }
    return defaultSourceOutputDir(inputPath);
  }, [inputKind, inputPath]);

  const engineBusy =
    state.translation.engine_status !== 'IDLE'
    || state.translation.stop_barrier
    || state.translation.single_tasks;
  const translating = state.translation.engine_status === 'TRANSLATING';
  const progress = translationProgressView(state.translation.progress);

  const layout = useMemo(
    () => validateSourceLayout(inputPath, outputPath),
    [inputPath, outputPath],
  );

  const gate = useMemo(
    () => toolboxStartGate({
      mode: 'source',
      hasProject: Boolean(projectPath),
      linkOpen: state.link === 'open',
      engineBusy: engineBusy && !backingUp,
      inputFolder: inputPath,
      outputFolder: outputPath,
    }),
    [backingUp, engineBusy, inputPath, outputPath, projectPath, state.link],
  );

  const resumeView = useMemo(() => sourceResumeView(resumeInfo), [resumeInfo]);

  // 输入变化、引擎回到空闲（停止/完成）时探测一次续跑缓存：
  // 有缓存时「开始」必须继续，不能重扫重翻。
  useEffect(() => {
    const input = normalizePath(inputPath);
    if (!input || !layout.ok) {
      // 输入无效/被清空：立刻丢掉旧探测结果，不能对错误目录显示「继续翻译」。
      setResumeInfo(null);
      return;
    }
    if (state.link !== 'open' || engineBusy || backingUp) return;
    // 先收起旧提示（换目录后旧缓存不作数），再防抖探测一次。
    setResumeInfo(null);
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void api
        .getSourceResumeInfo(input)
        .then((info) => {
          if (!cancelled) setResumeInfo(info.resumable ? info : null);
        })
        .catch(() => {
          if (!cancelled) setResumeInfo(null);
        });
    }, 300);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [backingUp, engineBusy, inputPath, layout.ok, state.link]);

  useEffect(() => {
    if (!backingUp || !backupJobId) return;
    let cancelled = false;
    const gen = ++pollGen.current;
    const tick = async () => {
      try {
        const job = await api.getJob(backupJobId) as JobSnapshot;
        if (cancelled || gen !== pollGen.current) return;
        const result = (job.result || {}) as Record<string, unknown>;
        setBackupMessage(String(result.message || t(TXT.backingUp)));
        setBackupPercent(Math.round(100 * (Number(job.progress) || 0)));
        if (job.status === 'done' || job.status === 'failed' || job.status === 'cancelled') {
          setBackingUp(false);
          setBusy(false);
          setBackupJobId('');
          if (job.status === 'failed') {
            state.pushToast('error', String(result.message || job.error || t(TXT.backupFailed)));
          } else if (job.status === 'cancelled') {
            state.pushToast('warning', t(TXT.backupCancelled));
          } else if (result.translation_started) {
            const warnings = Array.isArray(result.warnings) ? result.warnings.filter(Boolean) : [];
            state.pushToast(
              'success',
              warnings.length
                ? `${t(TXT.backupDone)}（${warnings.join('；')}）`
                : t(TXT.backupDone),
            );
            await Promise.all([state.reloadSettings(), state.reloadTranslation()]);
          } else {
            state.pushToast('warning', String(result.message || t('source_translate_backup_done_not_started')));
          }
        }
      } catch {
        /* 下一轮再试 */
      }
    };
    void tick();
    const id = window.setInterval(() => void tick(), 800);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [backupJobId, backingUp, state]);

  const onInputKindChange = (kind: InputKind) => {
    setInputKind(kind);
    if (kind === 'folder') {
      setInputPath(gameFolder);
      return;
    }
    setInputPath('');
  };

  const pickInput = async () => {
    if (inputKind === 'file') {
      const path = await window.renpy?.pickFile?.({
        filters: [{ name: 'Ren\'Py', extensions: ['rpy'] }],
      });
      if (path) {
        setInputPath(path);
      }
      return;
    }
    const path = await window.renpy?.pickFolder?.(inputPath || gameFolder || projectPath || undefined);
    if (path) {
      setInputPath(path);
    }
  };

  const pickBackup = async () => {
    const path = await window.renpy?.pickFolder?.(externalBackupDir || projectPath || undefined);
    if (path) setExternalBackupDir(path);
  };

  const start = async (preflightConfirmed = false, projectStatus: 'UNTRANSLATED' | 'TRANSLATING' = 'UNTRANSLATED') => {
    if (!gate.canStart || busy || backingUp) return;
    if (externalBackup && !normalizePath(externalBackupDir)) {
      state.pushToast('warning', t('source_translate_pick_backup_dir_first'));
      return;
    }
    const input = normalizePath(inputPath);
    const source = decodeLangChoice(sourceChoice);
    const target = decodeLangChoice(targetChoice);
    setBusy(true);
    try {
      const response = await state.startTranslation(projectStatus, preflightConfirmed, {
        mode: 'source',
        project_key: ownerKey || undefined,
        input_folder: input,
        source_language: source.code,
        target_language: target.code,
        traditional_chinese_enable: target.traditional,
        renpy_backup_original: backup,
        external_backup_dir: externalBackup ? externalBackupDir : undefined,
      });
      if (!response.accepted && response.reason === 'ASSETS_MISSING') {
        setAssetsMissing(true);
        setBusy(false);
        return;
      }
      if (!response.accepted) {
        setBusy(false);
        if (response.reason === 'NOT_RESUMABLE') {
          // 缓存刚好没了（被删/损坏）：退回「重新开始」，别把用户堵死。
          setResumeInfo(null);
        }
        return;
      }
      setAssetsMissing(false);
      if (response.stage === 'backing_up' && response.job?.id) {
        setBackingUp(true);
        setBackupJobId(response.job.id);
        setBackupMessage(t(TXT.backingUp));
        setBackupPercent(0);
        return;
      }
      state.pushToast('success', t(projectStatus === 'TRANSLATING' ? 'source_translate_resumed' : 'source_translate_submitted'));
      setBusy(false);
    } catch (error) {
      setBusy(false);
      state.pushToast('error', error instanceof Error ? error.message : String(error));
    }
  };

  const stop = async () => {
    try {
      if (backingUp && backupJobId) {
        await api.cancelJob(backupJobId);
        return;
      }
      if (translating) {
        await state.stopTranslation();
      }
    } catch (error) {
      state.pushToast('error', error instanceof Error ? error.message : String(error));
    }
  };

  return (
    <div className="rb-page" data-rb-page="source-translate">
      <Banner tone="info">{translationModeSummary('source')}</Banner>
      {!gate.canStart && !backingUp ? <Banner tone="warning">{gate.hint}</Banner> : null}
      {layout.ok && outputPath ? (
        <Banner tone="info">{`输出将写入：${normalizePath(outputPath)}`}</Banner>
      ) : null}
      {resumeView.canContinue && !translating && !backingUp ? (
        <Banner tone="info">{resumeView.hint}</Banner>
      ) : null}

      <SettingsGroup title={t('direct_rpy_paths_description')} description={t('source_translate_note')}>
        <Form layout="horizontal">
          <Form.Item label={t('source_translate_input_kind_label')} style={{ marginBottom: 12 }}>
            <Radio.Group
              value={inputKind}
              disabled={busy || backingUp || engineBusy}
              onChange={(event) => onInputKindChange(event.target.value as InputKind)}
              options={[
                { value: 'folder', label: t('lang_tools_game_dir') },
                { value: 'file', label: t('source_translate_input_kind_file') },
              ]}
            />
          </Form.Item>
          <Form.Item label={inputKind === 'file' ? t('source_translate_input_file') : t('asset_names_input')} style={{ marginBottom: 8 }}>
            <Input
              value={inputPath}
              disabled={busy || backingUp || engineBusy}
              onChange={(event) => setInputPath(event.target.value)}
              placeholder={inputKind === 'file' ? t('source_translate_pick_rpy') : t('source_translate_pick_game')}
            />
          </Form.Item>
          {window.renpy?.pickFolder || window.renpy?.pickFile ? (
            <div className="rb-tool-actions" style={{ marginBottom: 12 }}>
              <Button disabled={busy || backingUp || engineBusy} onClick={() => void pickInput()}>{t('source_translate_choose_input')}</Button>
            </div>
          ) : null}
          <Form.Item label={t('setting_output_dir_suffix')} style={{ marginBottom: 8 }}>
            <Input
              value={outputPath}
              readOnly
              disabled
              placeholder={
                inputKind === 'file'
                  ? t('source_translate_output_default_file')
                  : t('source_translate_output_default_dir')
              }
            />
          </Form.Item>
          <Form.Item label={t('source_translate_source_language')} style={{ marginBottom: 12 }}>
            <Select
              value={sourceChoice}
              disabled={busy || backingUp || engineBusy}
              options={TOOLBOX_LANG_OPTIONS.map((item) => ({
                value: encodeLangChoice(item.value, item.traditional),
                label: item.label,
              }))}
              onChange={setSourceChoice}
              style={{ width: '100%' }}
            />
          </Form.Item>
          <Form.Item label={t('font_inject_language')} style={{ marginBottom: 0 }}>
            <Select
              value={targetChoice}
              disabled={busy || backingUp || engineBusy}
              options={TOOLBOX_LANG_OPTIONS.map((item) => ({
                value: encodeLangChoice(item.value, item.traditional),
                label: item.label,
              }))}
              onChange={setTargetChoice}
              style={{ width: '100%' }}
            />
          </Form.Item>
        </Form>
      </SettingsGroup>

      <SettingsGroup title={t('source_translate_backup_options')}>
        <Form layout="horizontal">
          <Form.Item label={t('source_translate_auto_backup')} style={{ marginBottom: 12 }}>
            <Switch label={t('source_translate_auto_backup')} checked={backup} disabled={busy || backingUp || engineBusy} onChange={setBackup} />
          </Form.Item>
          <Form.Item label={t('source_translate_backup_external')} style={{ marginBottom: 8 }}>
            <Switch
              label={t('source_translate_backup_external')}
              checked={externalBackup}
              disabled={busy || backingUp || engineBusy}
              onChange={setExternalBackup}
            />
          </Form.Item>
          {externalBackup ? (
            <>
              <Form.Item label={t('source_translate_backup_dir')} style={{ marginBottom: 8 }}>
                <Input
                  value={externalBackupDir}
                  disabled={busy || backingUp || engineBusy}
                  onChange={(e) => setExternalBackupDir(e.target.value)}
                  placeholder={t('source_translate_pick_backup_dir')}
                />
              </Form.Item>
              {window.renpy?.pickFolder ? (
                <div className="rb-tool-actions">
                  <Button disabled={busy || backingUp || engineBusy} onClick={() => void pickBackup()}>{t('setting_choose')}</Button>
                </div>
              ) : null}
            </>
          ) : null}
        </Form>
      </SettingsGroup>

      <SettingsGroup title={t('source_translate_start')}>
        <div className="rb-tool-actions">
          <Button
            type="primary"
            disabled={!gate.canStart || busy || backingUp}
            loading={busy || backingUp}
            onClick={() => void start(false, resumeView.canContinue ? 'TRANSLATING' : 'UNTRANSLATED')}
          >
            {resumeView.canContinue ? t('source_translate_continue') : t('source_translate_start')}
          </Button>
          {resumeView.canContinue ? (
            <Button disabled={busy || backingUp} onClick={() => setConfirmRestart(true)}>
              {t('source_translate_restart')}
            </Button>
          ) : null}
          <Button danger disabled={!backingUp && !translating} onClick={() => void stop()}>
            {t('source_translate_stop')}</Button>
          {onNavigate ? (
            <Button disabled={busy || backingUp} onClick={() => onNavigate('rpy-extraction')}>
              {t('rpy_extraction_settings')}</Button>
          ) : null}
        </div>
        {backingUp ? (
          <>
            <Progress percent={backupPercent} status="active" style={{ marginTop: 12 }} />
            <p className="card-description">{backupMessage || t(TXT.backingUp)}</p>
          </>
        ) : null}
        {(translating || progress.label) ? (
          <>
            <Progress percent={progress.percent} style={{ marginTop: 12 }} />
            <p className="card-description">{progress.label || t('hook_supplement_translating')}</p>
          </>
        ) : null}
      </SettingsGroup>

      {assetsMissing ? (
        <Banner tone="warning">
          {t('hook_supplement_assets_missing')}<Button type="link" onClick={() => void start(true)}>{t('hook_supplement_continue_anyway')}</Button>
        </Banner>
      ) : null}

      {confirmRestart ? (
        <Dialog
          title={t('source_translate_restart_title')}
          onConfirm={() => {
            setConfirmRestart(false);
            void start(false, 'UNTRANSLATED');
          }}
          onCancel={() => setConfirmRestart(false)}
        >
          <p>{t('source_translate_restart_confirm')}</p>
        </Dialog>
      ) : null}
    </div>
  );
}
