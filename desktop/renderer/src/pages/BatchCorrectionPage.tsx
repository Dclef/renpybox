/** 批量修正：生成 Excel 并原地注入译文。 */
import { useCallback, useEffect, useState } from 'react';
import { Button, Form, Input, Progress, Table } from 'antd';

import { useT } from '../i18n';
import type { AppState } from '../useAppState';
import { Banner, Dialog, SettingsGroup } from '../ui';
import { AssetResultNotes, assetStatusText, useAssetSuiteJob, type AssetJob, type AssetResultBase } from './assetSuiteJob';

interface AssetResult extends AssetResultBase {
  path?: string;
  workbook?: string;
  count?: number;
  applied_files?: number;
  applied_changes?: number;
  unmatched_preview?: Array<{ path: string; count: number; reason?: string }>;
}

const KINDS = ['asset_corrections_export', 'asset_corrections_apply'] as const;

export function BatchCorrectionPage(props: { state: AppState }) {
  const { state } = props;
  const t = useT();
  const gameFolder = String(state.project?.renpy_game_folder ?? '');
  const tlFolder = String(state.project?.renpy_tl_folder ?? '');
  const [inputDir, setInputDir] = useState('');
  const [outputDir, setOutputDir] = useState('');
  const [workbook, setWorkbook] = useState('');
  const [translationRoot, setTranslationRoot] = useState(tlFolder || gameFolder);
  const [confirm, setConfirm] = useState<'export' | 'apply' | null>(null);
  const onFinished = useCallback((_job: AssetJob<AssetResult>, result: AssetResult | null) => {
    if (result?.path && result.operation === 'corrections_export') setWorkbook(result.path);
  }, []);
  const suite = useAssetSuiteJob<AssetResult>(state, KINDS, onFinished);
  const { identity, identityRef, keyReady, job, result, active, error, cancelling, busy } = suite;
  const engineBusy = state.translation.engine_status !== 'IDLE' || state.translation.stop_barrier || state.translation.single_tasks;
  const writeBlocked = busy || engineBusy || !keyReady || state.link !== 'open';

  useEffect(() => {
    setTranslationRoot(tlFolder || gameFolder);
  }, [tlFolder, gameFolder]);

  useEffect(() => {
    setConfirm(null);
  }, [identity]);

  const pickDir = useCallback(async (setter: (value: string) => void, current: string) => {
    const context = identityRef.current;
    const next = await window.renpy?.pickFolder?.(current || undefined);
    if (next && context === identityRef.current) setter(next);
  }, [identityRef]);

  const pickWorkbook = useCallback(async () => {
    const context = identityRef.current;
    const path = await window.renpy?.pickFile?.({ filters: [{ name: 'Excel', extensions: ['xlsx'] }] });
    if (path && context === identityRef.current) setWorkbook(path);
  }, [identityRef]);

  function startExport() {
    setConfirm(null);
    void suite.submit('/api/asset-suite/corrections/export', {
      input_dir: inputDir,
      output_dir: outputDir,
      confirm_overwrite: true,
    });
  }

  function startApply() {
    setConfirm(null);
    void suite.submit('/api/asset-suite/corrections/apply', {
      workbook: workbook || `${outputDir.replace(/[\\/]+$/, '')}/批量修正.xlsx`,
      translation_root: translationRoot,
      confirm: true,
    });
  }

  const statusText = assetStatusText(t, suite, t('asset_batch_idle'));

  return (
    <div className="rb-asset-page rb-page-scroll" data-rb-page="batch-correction">
      {error ? <Banner tone="error">{error}</Banner> : null}
      <Banner tone={result?.partial || result?.level === 'warning' ? 'warning' : result?.level === 'error' ? 'error' : 'info'}>{statusText}</Banner>
      {active ? <Progress percent={Math.min(100, 100 * (job?.progress || 0))} aria-label={t('asset_running')} /> : null}
      {active ? (
        <div className="rb-tool-actions">
          <Button className="rb-asset-cancel" onClick={() => void suite.cancel()} disabled={cancelling || Boolean(job?.cancel_requested)}>
            {t('asset_cancel')}
          </Button>
        </div>
      ) : null}

      <AssetResultNotes result={result} />
      {result?.unmatched_preview?.length ? (
        <Table
          className="rb-asset-unmatched"
          size="small"
          pagination={{ pageSize: 20, showSizeChanger: true }}
          rowKey={(item) => `${item.path}-${item.reason}`}
          dataSource={result.unmatched_preview}
          columns={[
            { title: t('asset_unmatched_path'), dataIndex: 'path', key: 'path', ellipsis: true },
            { title: t('asset_unmatched_count'), dataIndex: 'count', key: 'count', width: 80 },
            { title: t('asset_unmatched_reason'), dataIndex: 'reason', key: 'reason', ellipsis: true },
          ]}
        />
      ) : null}

      <SettingsGroup title={t('asset_batch_export_title')} description={t('asset_batch_export_desc')}>
        <Form.Item className="rb-asset-input-dir" label={t('asset_batch_input')} style={{ marginBottom: 0 }}>
          <Input value={inputDir} onChange={(event) => setInputDir(event.target.value)} disabled={busy} />
        </Form.Item>
        <Form.Item className="rb-asset-output-dir" label={t('asset_batch_output')} style={{ marginBottom: 0 }}>
          <Input value={outputDir} onChange={(event) => setOutputDir(event.target.value)} disabled={busy} />
        </Form.Item>
        <div className="rb-tool-actions">
          <Button onClick={() => void pickDir(setInputDir, inputDir)} disabled={busy}>{t('asset_pick_folder')}</Button>
          <Button onClick={() => void pickDir(setOutputDir, outputDir)} disabled={busy}>{t('asset_pick_folder')}</Button>
          <Button type="primary" className="rb-asset-export" onClick={() => setConfirm('export')} disabled={writeBlocked || !inputDir.trim() || !outputDir.trim()}>
            {t('asset_batch_export')}
          </Button>
        </div>
        <p className="card-description">{t('asset_batch_edit_hint')}</p>
      </SettingsGroup>

      <SettingsGroup title={t('asset_batch_apply_title')} description={t('asset_batch_apply_desc')}>
        <Form.Item className="rb-asset-workbook" label={t('asset_batch_workbook')} style={{ marginBottom: 0 }}>
          <Input value={workbook} onChange={(event) => setWorkbook(event.target.value)} disabled={busy} />
        </Form.Item>
        <Form.Item className="rb-asset-translation-root" label={t('asset_batch_translation_root')} style={{ marginBottom: 0 }}>
          <Input value={translationRoot} onChange={(event) => setTranslationRoot(event.target.value)} disabled={busy} />
        </Form.Item>
        <div className="rb-tool-actions">
          <Button onClick={() => void pickWorkbook()} disabled={busy}>{t('asset_pick_file')}</Button>
          <Button onClick={() => void pickDir(setTranslationRoot, translationRoot)} disabled={busy}>{t('asset_pick_folder')}</Button>
          <Button type="primary" className="rb-asset-apply" onClick={() => setConfirm('apply')} disabled={writeBlocked || !(workbook.trim() || outputDir.trim()) || !translationRoot.trim()}>
            {t('asset_batch_apply')}
          </Button>
        </div>
        <p className="card-description">{t('asset_batch_inplace_hint')}</p>
      </SettingsGroup>

      {confirm === 'export' ? (
        <Dialog title={t('asset_batch_export_confirm_title')} confirmText={t('asset_batch_export')} cancelText={t('workbench_cancel')} onConfirm={startExport} onCancel={() => setConfirm(null)}>
          <p>{t('asset_batch_export_confirm')}</p>
        </Dialog>
      ) : null}
      {confirm === 'apply' ? (
        <Dialog title={t('asset_batch_apply_confirm_title')} confirmText={t('asset_batch_apply')} cancelText={t('workbench_cancel')} onConfirm={startApply} onCancel={() => setConfirm(null)}>
          <p>{t('asset_batch_apply_confirm')}</p>
          <p className="card-description">{translationRoot}</p>
        </Dialog>
      ) : null}
    </div>
  );
}
