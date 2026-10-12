/** 文本提取 JSON：对齐 Qt ExtractTab，走 /api/extract-json。 */
import { useEffect, useMemo, useState } from 'react';
import { Button, Form, Input, Progress, Space } from 'antd';

import {
  exportJsonReady,
  extractJsonStatusPath,
  extractJsonStatusTone,
  formatPreviewSummary,
  importJsonReady,
  resolveGameFile,
} from '../extractJsonView.mjs';
import { useT } from '../i18n';
import type { AppState } from '../useAppState';
import { Banner, SettingsGroup } from '../ui';
import {
  toolStatusText,
  useProjectToolJob,
  type ToolJob,
  type ToolResultBase,
} from './projectToolJob';

interface JsonResult extends ToolResultBase {
  file_count?: number;
  entry_count?: number;
  skipped?: number;
  output_path?: string;
  tl_dir?: string;
  success?: boolean;
}

interface JsonStatus {
  project_key?: string;
  project_root?: string;
  game_dir?: string;
  language?: string;
  tl_dir?: string;
  default_game_file?: string;
  owner_project_key?: string;
  job?: ToolJob<JsonResult> | null;
}

const KINDS = [
  'extract_json_preview',
  'extract_json_export',
  'extract_json_import',
  'extract_json_cleanup',
  'extract_json_export_tl',
] as const;

export function ExtractJsonPage(props: { state: AppState }) {
  const { state } = props;
  const t = useT();
  const fallbackRoot = String(state.project?.renpy_project_path ?? '');
  const [language, setLanguage] = useState('chinese');
  const [gameFile, setGameFile] = useState('');
  const [outputPath, setOutputPath] = useState('');
  const [jsonPath, setJsonPath] = useState('');
  const [tlExportPath, setTlExportPath] = useState('');
  const statusPath = useMemo(
    () => extractJsonStatusPath({ gameFile, language, defaultRoot: fallbackRoot }),
    [gameFile, language, fallbackRoot],
  );
  const suite = useProjectToolJob<JsonResult, JsonStatus>(state, statusPath, KINDS);
  const { status, keyReady, job, result, active, error, cancelling, busy } = suite;

  const engineBusy = state.translation.engine_status !== 'IDLE' || state.translation.stop_barrier || state.translation.single_tasks;
  const writeBlocked = busy || engineBusy || !keyReady || state.link !== 'open';
  const defaultRoot = status?.default_game_file || status?.project_root || fallbackRoot;
  const resolvedGame = resolveGameFile(gameFile, defaultRoot);
  const canExport = exportJsonReady({ gameFile, outputPath, defaultRoot });
  const canImport = importJsonReady({ gameFile, jsonPath, defaultRoot });

  useEffect(() => {
    setLanguage('chinese');
    setGameFile(String(state.project?.renpy_project_path ?? ''));
    setOutputPath('');
    setJsonPath('');
    setTlExportPath('');
  }, [suite.identity, state.project?.renpy_project_path]);

  async function pickGameFile() {
    const context = suite.identityRef.current;
    const next = await window.renpy?.pickFile?.({
      filters: [{ name: 'Executable', extensions: ['exe'] }],
    });
    if (next && context === suite.identityRef.current) setGameFile(next);
  }

  async function pickOutput() {
    const context = suite.identityRef.current;
    const next = await window.renpy?.saveFile?.({
      defaultPath: outputPath || `${resolvedGame || 'export'}.json`,
      filters: [{ name: 'JSON', extensions: ['json'] }],
    });
    if (next && context === suite.identityRef.current) setOutputPath(next);
  }

  async function pickJson() {
    const context = suite.identityRef.current;
    const next = await window.renpy?.pickFile?.({
      filters: [{ name: 'JSON', extensions: ['json'] }],
    });
    if (next && context === suite.identityRef.current) setJsonPath(next);
  }

  async function pickTlExport() {
    const context = suite.identityRef.current;
    const next = await window.renpy?.saveFile?.({
      defaultPath: tlExportPath || `tl_${language || 'chinese'}.json`,
      filters: [{ name: 'JSON', extensions: ['json'] }],
    });
    if (next && context === suite.identityRef.current) setTlExportPath(next);
  }

  const statusText = toolStatusText(t, suite, t('extract_json_idle'));
  const statusTone = extractJsonStatusTone({
    active,
    checking: suite.checking,
    job,
    result,
  });
  const previewSummary = formatPreviewSummary(t('extract_json_preview_summary'), {
    fileCount: result?.file_count ?? 0,
    entryCount: result?.entry_count ?? 0,
  });

  return (
    <div className="rb-asset-page rb-page-scroll" data-rb-page="extract-json">
      {error ? <Banner tone="error">{error}</Banner> : null}
      {/* 本工具不要求绑定项目；未绑定时用手选游戏 EXE/目录即可 */}
      <Banner tone="info">{t('extract_json_intro')}</Banner>
      <Banner tone={statusTone}>{statusText}</Banner>
      {active ? <Progress percent={Math.min(100, 100 * (job?.progress || 0))} aria-label={t('tool_job_running')} /> : null}
      {active ? (
        <div className="rb-tool-actions">
          <Button onClick={() => void suite.cancel()} disabled={cancelling || Boolean(job?.cancel_requested)}>
            {t('tool_job_cancel')}
          </Button>
        </div>
      ) : null}

      <SettingsGroup title={t('extract_json_title')} description={t('extract_json_desc')}>
        <Form.Item label={t('extract_json_game_file')} style={{ marginBottom: 12 }}>
          <Space.Compact block>
            <Input value={gameFile} onChange={(e) => setGameFile(e.target.value)} style={{ flex: 1 }} />
            <Button onClick={() => void pickGameFile()} disabled={writeBlocked}>{t('extract_json_browse')}</Button>
          </Space.Compact>
        </Form.Item>
        <Form.Item label={t('extract_json_language')} style={{ marginBottom: 12 }}>
          <Input value={language} onChange={(e) => setLanguage(e.target.value)} placeholder="chinese" />
        </Form.Item>
        <div className="rb-tool-actions">
          <Button
            onClick={() => void suite.submit('/api/extract-json/preview', {
              game_file: resolvedGame,
              language: language.trim() || 'chinese',
              ensure_official: true,
            })}
            disabled={writeBlocked || !resolvedGame}
          >
            {t('extract_json_preview')}
          </Button>
        </div>
        {result?.action === 'preview' ? <p className="card-description">{previewSummary}</p> : null}
      </SettingsGroup>

      <SettingsGroup title={t('extract_json_export_title')} description={t('extract_json_export_desc')}>
        <Form.Item label={t('extract_json_output')} style={{ marginBottom: 12 }}>
          <Space.Compact block>
            <Input value={outputPath} onChange={(e) => setOutputPath(e.target.value)} style={{ flex: 1 }} />
            <Button onClick={() => void pickOutput()} disabled={writeBlocked}>{t('extract_json_browse')}</Button>
          </Space.Compact>
        </Form.Item>
        <Button
          type="primary"
          onClick={() => void suite.submit('/api/extract-json/export-json', {
            game_file: resolvedGame,
            language: language.trim() || 'chinese',
            output_path: outputPath.trim(),
            force_extract: true,
            include_metadata: true,
          })}
          disabled={writeBlocked || !canExport}
        >
          {t('extract_json_export_run')}
        </Button>
      </SettingsGroup>

      <SettingsGroup title={t('extract_json_import_title')} description={t('extract_json_import_desc')}>
        <Form.Item label={t('extract_json_json_path')} style={{ marginBottom: 12 }}>
          <Space.Compact block>
            <Input value={jsonPath} onChange={(e) => setJsonPath(e.target.value)} style={{ flex: 1 }} />
            <Button onClick={() => void pickJson()} disabled={writeBlocked}>{t('extract_json_browse')}</Button>
          </Space.Compact>
        </Form.Item>
        <div className="rb-tool-actions">
          <Button
            type="primary"
            onClick={() => void suite.submit('/api/extract-json/import-apply', {
              game_file: resolvedGame,
              language: language.trim() || 'chinese',
              json_path: jsonPath.trim(),
              backup: true,
            })}
            disabled={writeBlocked || !canImport}
          >
            {t('extract_json_import_run')}
          </Button>
          <Button
            onClick={() => void suite.submit('/api/extract-json/cleanup', {
              game_file: resolvedGame,
              language: language.trim() || 'chinese',
            })}
            disabled={writeBlocked || !resolvedGame}
          >
            {t('extract_json_cleanup')}
          </Button>
        </div>
      </SettingsGroup>

      <SettingsGroup title={t('extract_json_tl_export_title')} description={t('extract_json_tl_export_desc')}>
        <Form.Item label={t('extract_json_output')} style={{ marginBottom: 12 }}>
          <Space.Compact block>
            <Input value={tlExportPath} onChange={(e) => setTlExportPath(e.target.value)} style={{ flex: 1 }} />
            <Button onClick={() => void pickTlExport()} disabled={writeBlocked}>{t('extract_json_browse')}</Button>
          </Space.Compact>
        </Form.Item>
        <Button
          onClick={() => void suite.submit('/api/extract-json/export-tl-json', {
            game_file: resolvedGame,
            language: language.trim() || 'chinese',
            output_path: tlExportPath.trim(),
            include_metadata: true,
          })}
          disabled={writeBlocked || !resolvedGame || !tlExportPath.trim()}
        >
          {t('extract_json_tl_export_run')}
        </Button>
      </SettingsGroup>

      {result?.message && result.action !== 'preview' ? (
        <p className="card-description rb-asset-output">{result.message}</p>
      ) : null}
    </div>
  );
}
