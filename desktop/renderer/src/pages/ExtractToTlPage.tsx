/** 抽取到 TL：对齐 Qt RenpyTranslationPage，走 /api/extract-to-tl。 */
import { useEffect, useMemo, useState } from 'react';
import { Button, Checkbox, Collapse, Form, Input, Progress, Select, Space } from 'antd';

import { request } from '../api';
import {
  extractToTlStatusPath,
  extractToTlStatusTone,
  preferredSuspiciousOpenPath,
  resolveExtractSwitches,
} from '../extractToTlView.mjs';
import { useT } from '../i18n';
import type { AppState } from '../useAppState';
import { Banner, SettingsGroup } from '../ui';
import {
  toolStatusText,
  useProjectToolJob,
  type ToolJob,
  type ToolResultBase,
} from './projectToolJob';

interface ExtractResult extends ToolResultBase {
  incremental?: boolean;
  merge?: { success?: boolean; message?: string } | null;
  tl_dir?: string;
  incremental_dir?: string;
  preserved_count?: number;
  new_strings?: number;
  success?: boolean;
}

interface ExtractStatus {
  project_key?: string;
  project_root?: string;
  game_dir?: string;
  language?: string;
  tl_dir?: string;
  incremental_dir?: string;
  has_existing_tl?: boolean;
  incremental_dir_exists?: boolean;
  suspicious_backup_available?: boolean;
  suspicious_manifests?: Array<{ path?: string; mtime?: number }>;
  rule_mode?: string;
  options?: {
    use_official?: boolean;
    use_custom?: boolean;
    supplement_mode?: string;
    skip_hook_files?: boolean;
    filter_suspicious_bool_expr?: boolean;
    auto_merge_cleanup?: boolean;
  };
  job?: ToolJob<ExtractResult> | null;
}

const KINDS = ['extract_to_tl', 'extract_to_tl_merge', 'extract_to_tl_restore'] as const;

export function ExtractToTlPage(props: { state: AppState }) {
  const { state } = props;
  const t = useT();
  const [language, setLanguage] = useState('chinese');
  const [gameDir, setGameDir] = useState('');
  const [exePath, setExePath] = useState('');
  const [useOfficial, setUseOfficial] = useState(true);
  const [useCustom, setUseCustom] = useState(true);
  const [supplementMode, setSupplementMode] = useState<'precise' | 'aggressive'>('precise');
  const [skipHooks, setSkipHooks] = useState(true);
  const [filterSuspicious, setFilterSuspicious] = useState(true);
  const [autoMerge, setAutoMerge] = useState(true);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const statusPath = useMemo(
    () => extractToTlStatusPath({ gameDir, language }),
    [gameDir, language],
  );
  const suite = useProjectToolJob<ExtractResult, ExtractStatus>(state, statusPath, KINDS);
  const { status, keyReady, job, result, active, error, cancelling, busy } = suite;

  const engineBusy = state.translation.engine_status !== 'IDLE' || state.translation.stop_barrier || state.translation.single_tasks;
  const writeBlocked = busy || engineBusy || !keyReady || state.link !== 'open';
  const hasTarget = Boolean(gameDir.trim() || status?.project_root || state.project?.renpy_project_path);
  const ruleMode = status?.rule_mode || 'builtin';
  const switches = resolveExtractSwitches({
    useOfficial,
    useCustom,
    ruleMode,
    // 未指定 EXE 时仍交给后端 auto_find；这里仅表示用户是否已手选
    hasExe: Boolean(exePath.trim()) || useOfficial,
  });
  const canMerge = Boolean(status?.incremental_dir_exists || result?.incremental_dir);
  const canRestore = Boolean(status?.suspicious_backup_available || status?.suspicious_manifests?.length);

  useEffect(() => {
    setLanguage('chinese');
    setGameDir(String(state.project?.renpy_game_folder ?? ''));
    setExePath('');
    setUseOfficial(true);
    setUseCustom(true);
    setSupplementMode('precise');
    setSkipHooks(true);
    setFilterSuspicious(true);
    setAutoMerge(true);
    setAdvancedOpen(false);
  }, [suite.identity, state.project?.renpy_game_folder]);

  async function pickGameDir() {
    const context = suite.identityRef.current;
    const next = await window.renpy?.pickFolder?.(gameDir || undefined);
    if (next && context === suite.identityRef.current) setGameDir(next);
  }

  async function pickExe() {
    const context = suite.identityRef.current;
    const next = await window.renpy?.pickFile?.({
      filters: [{ name: 'Executable', extensions: ['exe', 'py'] }],
    });
    if (next && context === suite.identityRef.current) setExePath(next);
  }

  function startExtract() {
    void suite.submit('/api/extract-to-tl/extract', {
      game_dir: gameDir,
      exe_path: exePath,
      language: language.trim() || 'chinese',
      use_official: switches.useOfficial,
      use_custom: switches.useCustom,
      supplement_mode: supplementMode,
      skip_hook_files: skipHooks,
      filter_suspicious_bool_expr: filterSuspicious,
      auto_merge_cleanup: autoMerge,
    });
  }

  function startMerge() {
    void suite.submit('/api/extract-to-tl/merge-incremental', {
      game_dir: gameDir,
      language: language.trim() || 'chinese',
    });
  }

  function startRestore() {
    void suite.submit('/api/extract-to-tl/restore-suspicious', {
      game_dir: gameDir,
      language: language.trim() || 'chinese',
      manifest_path: status?.suspicious_manifests?.[0]?.path || '',
    });
  }

  async function openSuspicious() {
    const key = suite.currentKey();
    // 未绑定项目时 key 可为 ""；有手选 game_dir 即可继续
    if (key === null) return;
    try {
      const lang = language.trim() || 'chinese';
      const qs = new URLSearchParams({ language: lang });
      if (gameDir.trim()) qs.set('game_dir', gameDir.trim());
      const listed = await request<{
        open_path?: string;
        manifests?: Array<{ path?: string }>;
        available?: boolean;
      }>(`/api/extract-to-tl/suspicious-backups?${qs.toString()}`);
      const target = listed.manifests?.[0]?.path || listed.open_path || preferredSuspiciousOpenPath(status);
      if (!target) {
        state.pushToast('warning', t('extract_tl_no_backup'));
        return;
      }
      const opened = await request<{ path?: string; ok?: boolean }>(
        '/api/extract-to-tl/open-path',
        {
          method: 'POST',
          body: JSON.stringify({
            project_key: key,
            game_dir: gameDir,
            path: target,
          }),
        },
      );
      if (opened.path) await window.renpy?.openPath?.(opened.path);
    } catch (failure) {
      state.pushToast('error', failure instanceof Error ? failure.message : String(failure));
    }
  }

  const statusText = toolStatusText(t, suite, t('extract_tl_idle'));
  const statusTone = extractToTlStatusTone({
    active,
    checking: suite.checking,
    job,
    result,
  });

  return (
    <div className="rb-asset-page rb-page-scroll" data-rb-page="extract-to-tl">
      {error ? <Banner tone="error">{error}</Banner> : null}
      {/* 本工具不要求绑定项目；未绑定时用手选 game_dir 即可 */}
      <Banner tone="info">{t('extract_tl_intro')}</Banner>
      <Banner tone={statusTone}>{statusText}</Banner>
      {active ? <Progress percent={Math.min(100, 100 * (job?.progress || 0))} aria-label={t('tool_job_running')} /> : null}
      {active ? (
        <div className="rb-tool-actions">
          <Button onClick={() => void suite.cancel()} disabled={cancelling || Boolean(job?.cancel_requested)}>
            {t('tool_job_cancel')}
          </Button>
        </div>
      ) : null}

      <SettingsGroup title={t('extract_tl_title')} description={t('extract_tl_desc')}>
        <Form.Item label={t('extract_tl_game_dir')} style={{ marginBottom: 12 }}>
          <Space.Compact block>
            <Input value={gameDir} onChange={(e) => setGameDir(e.target.value)} style={{ flex: 1 }} />
            <Button onClick={() => void pickGameDir()} disabled={writeBlocked}>{t('extract_tl_browse')}</Button>
          </Space.Compact>
        </Form.Item>
        <Form.Item label={t('extract_tl_language')} style={{ marginBottom: 12 }}>
          <Input value={language} onChange={(e) => setLanguage(e.target.value)} placeholder="chinese" />
        </Form.Item>
        <p className="card-description">
          {status?.has_existing_tl ? t('extract_tl_has_existing') : t('extract_tl_no_existing')}
          {status?.incremental_dir_exists ? ` · ${t('extract_tl_incremental_ready')}` : ''}
        </p>
        <div className="rb-tool-actions">
          <Button type="primary" onClick={startExtract} disabled={writeBlocked}>
            {t('extract_tl_run')}
          </Button>
        </div>
      </SettingsGroup>

      <Collapse
        activeKey={advancedOpen ? ['adv'] : []}
        onChange={(keys) => setAdvancedOpen(Array.isArray(keys) ? keys.includes('adv') : keys === 'adv')}
        items={[{
          key: 'adv',
          label: t('extract_tl_advanced'),
          children: (
            <>
              <Checkbox checked={useOfficial} onChange={(e) => setUseOfficial(e.target.checked)} disabled={ruleMode === 'custom'}>
                {t('extract_tl_official')}
              </Checkbox>
              <Checkbox checked={useCustom} onChange={(e) => setUseCustom(e.target.checked)} disabled={ruleMode === 'custom'} style={{ marginLeft: 12 }}>
                {t('extract_tl_custom')}
              </Checkbox>
              {ruleMode === 'custom' ? <p className="card-description">{t('extract_tl_custom_rule')}</p> : null}
              <Form.Item label={t('extract_tl_supplement_mode')} style={{ marginBottom: 12, marginTop: 12 }}>
                <Select
                  value={supplementMode}
                  onChange={(value) => setSupplementMode(value)}
                  options={[
                    { value: 'precise', label: t('extract_tl_mode_precise') },
                    { value: 'aggressive', label: t('extract_tl_mode_aggressive') },
                  ]}
                  style={{ width: 220 }}
                />
              </Form.Item>
              <Form.Item label={t('extract_tl_exe')} style={{ marginBottom: 12 }}>
                <Space.Compact block>
                  <Input value={exePath} onChange={(e) => setExePath(e.target.value)} disabled={!useOfficial} style={{ flex: 1 }} placeholder={t('extract_tl_exe_hint')} />
                  <Button onClick={() => void pickExe()} disabled={writeBlocked || !useOfficial}>{t('extract_tl_browse')}</Button>
                </Space.Compact>
              </Form.Item>
              <Checkbox checked={skipHooks} onChange={(e) => setSkipHooks(e.target.checked)}>
                {t('extract_tl_skip_hooks')}
              </Checkbox>
              <br />
              <Checkbox checked={filterSuspicious} onChange={(e) => setFilterSuspicious(e.target.checked)}>
                {t('extract_tl_filter_suspicious')}
              </Checkbox>
              <br />
              <Checkbox checked={autoMerge} onChange={(e) => setAutoMerge(e.target.checked)}>
                {t('extract_tl_auto_merge')}
              </Checkbox>
              <div className="rb-tool-actions" style={{ marginTop: 12 }}>
                <Button onClick={startMerge} disabled={writeBlocked || !canMerge}>
                  {t('extract_tl_merge_now')}
                </Button>
                <Button onClick={() => void openSuspicious()} disabled={!keyReady || !hasTarget}>
                  {t('extract_tl_open_backup')}
                </Button>
                <Button onClick={startRestore} disabled={writeBlocked || !canRestore}>
                  {t('extract_tl_restore')}
                </Button>
              </div>
            </>
          ),
        }]}
      />

      {result?.message ? <p className="card-description rb-asset-output">{result.message}</p> : null}
      {result?.merge?.message ? <p className="card-description">{result.merge.message}</p> : null}
    </div>
  );
}
