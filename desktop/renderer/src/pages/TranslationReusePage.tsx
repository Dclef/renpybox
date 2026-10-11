/** 更新翻译复用：预览只读 / 执行写入，对齐 Qt5 TranslationReusePage。 */
import { useEffect, useMemo, useState } from 'react';
import { Button, Form, Input, Progress } from 'antd';

import {
  formatReuseSummary,
  reuseOwnerProjectKey,
  reusePathsConflict,
  translationReuseStatusPath,
} from '../translationReuseView.mjs';
import { useT } from '../i18n';
import type { AppState } from '../useAppState';
import { Banner, Dialog, SettingsGroup } from '../ui';
import {
  toolStatusText,
  useProjectToolJob,
  type ToolJob,
  type ToolResultBase,
} from './projectToolJob';

interface ReuseResult extends ToolResultBase {
  reusable_entries?: number;
  conflicts?: number;
  already_reused?: number;
  unmatched_entries?: number;
  applied_entries?: number;
  hook_updated?: boolean;
  failed_files?: string[];
  source_dir?: string;
  target_dir?: string;
  success?: boolean;
}

interface ReuseStatus {
  project_key?: string;
  owner_project_key?: string;
  source_dir?: string;
  target_dir?: string;
  default_target_dir?: string;
  job?: ToolJob<ReuseResult> | null;
}

const KINDS = ['translation_reuse_preview', 'translation_reuse_execute'] as const;

const COPY = {
  ZH: {
    pathsTitle: '译文目录',
    source: '旧译文',
    target: '新译文',
    sourcePh: '旧版本 game/tl/<语言> 目录',
    targetPh: '新版本 game/tl/<语言> 目录',
    preview: '预览',
    execute: '执行复用',
    confirm: '将只填充目标中的空白/原文占位译文，冲突的人工译文保留；执行前会在 game 外自动备份。继续？',
    conflict: '旧译文与目标目录不能相同或互相包含。',
    browse: '浏览',
  },
  EN: {
    pathsTitle: 'Translation Folders',
    source: 'Previous Translation',
    target: 'New Translation',
    sourcePh: 'Previous game/tl/<language> folder',
    targetPh: 'New game/tl/<language> folder',
    preview: 'Preview',
    execute: 'Reuse Translations',
    confirm: 'Only empty or source-identical entries will be filled; conflicting human translations are kept. A backup outside game/ will be created. Continue?',
    conflict: 'Source and target folders must differ and must not nest.',
    browse: 'Browse',
  },
} as const;

export function TranslationReusePage(props: { state: AppState }) {
  const { state } = props;
  const t = useT();
  const uiLang = state.bootLanguage === 'EN' ? 'EN' : 'ZH';
  const copy = COPY[uiLang];
  const defaultTarget = String(state.project?.renpy_tl_folder ?? '');
  const [sourceDir, setSourceDir] = useState('');
  const [targetDir, setTargetDir] = useState(defaultTarget);
  const [confirmExec, setConfirmExec] = useState(false);

  const statusPath = useMemo(
    () => translationReuseStatusPath({ sourceDir, targetDir }),
    [sourceDir, targetDir],
  );
  const suite = useProjectToolJob<ReuseResult, ReuseStatus>(
    state,
    statusPath,
    KINDS,
    `${sourceDir}\0${targetDir}`,
  );
  const { keyReady, job, result, active, error, busy, status } = suite;
  const ownerKey = reuseOwnerProjectKey(status);
  const engineBusy = state.translation.engine_status !== 'IDLE' || state.translation.stop_barrier || state.translation.single_tasks;
  const blocked = busy || engineBusy || !keyReady || state.link !== 'open';
  const pathConflict = reusePathsConflict(sourceDir, targetDir);
  const ready = Boolean(sourceDir.trim() && targetDir.trim()) && !pathConflict;

  useEffect(() => {
    setSourceDir('');
    setTargetDir(String(state.project?.renpy_tl_folder ?? status?.default_target_dir ?? ''));
    setConfirmExec(false);
  }, [suite.identity]);

  async function pickSource() {
    const context = suite.identityRef.current;
    const next = await window.renpy?.pickFolder?.(sourceDir || undefined);
    if (next && context === suite.identityRef.current) setSourceDir(next);
  }

  async function pickTarget() {
    const context = suite.identityRef.current;
    const next = await window.renpy?.pickFolder?.(targetDir || undefined);
    if (next && context === suite.identityRef.current) setTargetDir(next);
  }

  const statusText = toolStatusText(t, suite, uiLang === 'EN' ? 'Not previewed' : '尚未预览');
  const summary = formatReuseSummary(
    result?.action === 'preview' || result?.action === 'execute' ? result : null,
    uiLang,
  );

  return (
    <div className="rb-page-scroll">
      {error ? <Banner tone="error">{error}</Banner> : null}
      {pathConflict ? <Banner tone="warning">{copy.conflict}</Banner> : null}
      <Banner tone={active ? 'info' : job?.status === 'failed' ? 'error' : job?.status === 'done' ? 'success' : 'info'}>
        {statusText}
      </Banner>
      {active ? <Progress percent={Math.round((job?.progress ?? 0) * 100)} status="active" /> : null}

      <SettingsGroup title={copy.pathsTitle}>
        <Form.Item label={copy.source}>
          <Input.Group compact style={{ display: 'flex' }}>
            <Input
              value={sourceDir}
              placeholder={copy.sourcePh}
              disabled={blocked}
              onChange={(e) => setSourceDir(e.target.value)}
            />
            <Button onClick={() => void pickSource()} disabled={blocked}>{copy.browse}</Button>
          </Input.Group>
        </Form.Item>
        <Form.Item label={copy.target}>
          <Input.Group compact style={{ display: 'flex' }}>
            <Input
              value={targetDir}
              placeholder={copy.targetPh}
              disabled={blocked}
              onChange={(e) => setTargetDir(e.target.value)}
            />
            <Button onClick={() => void pickTarget()} disabled={blocked}>{copy.browse}</Button>
          </Input.Group>
        </Form.Item>
      </SettingsGroup>

      <div className="rb-tool-actions">
        <Button
          disabled={blocked || !ready}
          onClick={() => void suite.submit('/api/translation-reuse/preview', {
            source_dir: sourceDir,
            target_dir: targetDir,
            owner_project_key: ownerKey,
          })}
        >
          {copy.preview}
        </Button>
        <Button type="primary" disabled={blocked || !ready} onClick={() => setConfirmExec(true)}>
          {copy.execute}
        </Button>
      </div>

      <Banner tone={result?.partial ? 'warning' : 'info'}>{summary}</Banner>

      {confirmExec ? (
        <Dialog
          title={copy.execute}
          onConfirm={() => {
            setConfirmExec(false);
            void suite.submit('/api/translation-reuse/execute', {
              source_dir: sourceDir,
              target_dir: targetDir,
              confirm: true,
              owner_project_key: ownerKey,
            });
          }}
          onCancel={() => setConfirmExec(false)}
        >
          <p>{copy.confirm}</p>
        </Dialog>
      ) : null}
    </div>
  );
}
