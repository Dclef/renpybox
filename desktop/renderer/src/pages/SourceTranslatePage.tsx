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
import type { JobSnapshot } from '../types';
import { Banner, SettingsGroup, Switch } from '../ui';

type InputKind = 'folder' | 'file';

const TXT = {
  backingUp: { zh: '正在备份源码…', en: 'Backing up source…' },
  backupDone: { zh: '备份完成，翻译已启动', en: 'Backup done, translation started' },
  backupCancelled: { zh: '已取消源码备份', en: 'Source backup cancelled' },
  backupFailed: { zh: '源码备份失败', en: 'Source backup failed' },
} as const;

export function SourceTranslatePage(props: {
  state: AppState;
  onNavigate?: (page: PageKey) => void;
}) {
  const { state, onNavigate } = props;
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

  useEffect(() => {
    if (!backingUp || !backupJobId) return;
    let cancelled = false;
    const gen = ++pollGen.current;
    const tick = async () => {
      try {
        const job = await api.getJob(backupJobId) as JobSnapshot;
        if (cancelled || gen !== pollGen.current) return;
        const result = (job.result || {}) as Record<string, unknown>;
        setBackupMessage(String(result.message || TXT.backingUp.zh));
        setBackupPercent(Math.round(100 * (Number(job.progress) || 0)));
        if (job.status === 'done' || job.status === 'failed' || job.status === 'cancelled') {
          setBackingUp(false);
          setBusy(false);
          setBackupJobId('');
          if (job.status === 'failed') {
            state.pushToast('error', String(result.message || job.error || TXT.backupFailed.zh));
          } else if (job.status === 'cancelled') {
            state.pushToast('warning', TXT.backupCancelled.zh);
          } else if (result.translation_started) {
            const warnings = Array.isArray(result.warnings) ? result.warnings.filter(Boolean) : [];
            state.pushToast(
              'success',
              warnings.length
                ? `${TXT.backupDone.zh}（${warnings.join('；')}）`
                : TXT.backupDone.zh,
            );
            await Promise.all([state.reloadSettings(), state.reloadTranslation()]);
          } else {
            state.pushToast('warning', String(result.message || '备份完成，但翻译未启动'));
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

  const start = async (preflightConfirmed = false) => {
    if (!gate.canStart || busy || backingUp) return;
    if (externalBackup && !normalizePath(externalBackupDir)) {
      state.pushToast('warning', '请选择外部备份目录');
      return;
    }
    const input = normalizePath(inputPath);
    const source = decodeLangChoice(sourceChoice);
    const target = decodeLangChoice(targetChoice);
    setBusy(true);
    try {
      const response = await state.startTranslation('UNTRANSLATED', preflightConfirmed, {
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
        return;
      }
      setAssetsMissing(false);
      if (response.stage === 'backing_up' && response.job?.id) {
        setBackingUp(true);
        setBackupJobId(response.job.id);
        setBackupMessage(TXT.backingUp.zh);
        setBackupPercent(0);
        return;
      }
      state.pushToast('success', '已提交源码翻译');
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

      <SettingsGroup title="路径与语言" description="输入可为 game 目录或单个 .rpy；输出目录由输入自动推导（与 Qt 一致，不可手改）。">
        <Form layout="vertical">
          <Form.Item label="输入类型" style={{ marginBottom: 12 }}>
            <Radio.Group
              value={inputKind}
              disabled={busy || backingUp || engineBusy}
              onChange={(event) => onInputKindChange(event.target.value as InputKind)}
              options={[
                { value: 'folder', label: 'game 目录' },
                { value: 'file', label: '单个 .rpy' },
              ]}
            />
          </Form.Item>
          <Form.Item label={inputKind === 'file' ? '输入文件' : '输入目录'} style={{ marginBottom: 8 }}>
            <Input
              value={inputPath}
              disabled={busy || backingUp || engineBusy}
              onChange={(event) => setInputPath(event.target.value)}
              placeholder={inputKind === 'file' ? '选择 .rpy 文件' : '选择 game 目录'}
            />
          </Form.Item>
          {window.renpy?.pickFolder || window.renpy?.pickFile ? (
            <div className="rb-tool-actions" style={{ marginBottom: 12 }}>
              <Button disabled={busy || backingUp || engineBusy} onClick={() => void pickInput()}>选择输入</Button>
            </div>
          ) : null}
          <Form.Item label="输出目录（自动）" style={{ marginBottom: 8 }}>
            <Input
              value={outputPath}
              readOnly
              disabled
              placeholder={
                inputKind === 'file'
                  ? '默认：输入同目录/<文件名>_source_out'
                  : '默认：输入父目录/<目录名>_source_out'
              }
            />
          </Form.Item>
          <Form.Item label="源语言" style={{ marginBottom: 12 }}>
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
          <Form.Item label="目标语言" style={{ marginBottom: 0 }}>
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

      <SettingsGroup title="备份选项">
        <Form layout="vertical">
          <Form.Item label="自动备份 .bak" style={{ marginBottom: 12 }}>
            <Switch label="自动备份 .bak" checked={backup} disabled={busy || backingUp || engineBusy} onChange={setBackup} />
          </Form.Item>
          <Form.Item label="备份源码到外部" style={{ marginBottom: 8 }}>
            <Switch
              label="备份源码到外部"
              checked={externalBackup}
              disabled={busy || backingUp || engineBusy}
              onChange={setExternalBackup}
            />
          </Form.Item>
          {externalBackup ? (
            <>
              <Form.Item label="外部备份目录" style={{ marginBottom: 8 }}>
                <Input
                  value={externalBackupDir}
                  disabled={busy || backingUp || engineBusy}
                  onChange={(e) => setExternalBackupDir(e.target.value)}
                  placeholder="选择备份目录"
                />
              </Form.Item>
              {window.renpy?.pickFolder ? (
                <div className="rb-tool-actions">
                  <Button disabled={busy || backingUp || engineBusy} onClick={() => void pickBackup()}>选择备份目录</Button>
                </div>
              ) : null}
            </>
          ) : null}
        </Form>
      </SettingsGroup>

      <SettingsGroup title="开始翻译">
        <div className="rb-tool-actions">
          <Button type="primary" disabled={!gate.canStart || busy || backingUp} loading={busy || backingUp} onClick={() => void start(false)}>
            开始翻译
          </Button>
          <Button danger disabled={!backingUp && !translating} onClick={() => void stop()}>
            停止
          </Button>
          {onNavigate ? (
            <Button disabled={busy || backingUp} onClick={() => onNavigate('rpy-extraction')}>
              RPY 抽取设置
            </Button>
          ) : null}
        </div>
        {backingUp ? (
          <>
            <Progress percent={backupPercent} status="active" style={{ marginTop: 12 }} />
            <p className="card-description">{backupMessage || TXT.backingUp.zh}</p>
          </>
        ) : null}
        {(translating || progress.label) ? (
          <>
            <Progress percent={progress.percent} style={{ marginTop: 12 }} />
            <p className="card-description">{progress.label || '翻译中…'}</p>
          </>
        ) : null}
      </SettingsGroup>

      {assetsMissing ? (
        <Banner tone="warning">
          当前项目没有可注入的角色卡、世界观或术语资产。
          <Button type="link" onClick={() => void start(true)}>仍然继续</Button>
        </Banner>
      ) : null}
    </div>
  );
}
