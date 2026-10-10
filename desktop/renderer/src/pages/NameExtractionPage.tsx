/** 姓名字段提取：扫描后本地审阅、可选 LLM 翻译译名，再导出 TXT/JSON。 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Button, ConfigProvider, Form, Input, Progress, Table, Typography } from 'antd';
import type { ThemeConfig } from 'antd';

import { cancelJob, request } from '../api';
import { useT } from '../i18n';
import type { AppState } from '../useAppState';
import { Banner, Dialog, SettingsGroup } from '../ui';
import {
  AssetResultNotes, assetJobResult, assetJobRunning, assetStatusText, errorText, useAssetSuiteJob,
  type AssetJob, type AssetResultBase,
} from './assetSuiteJob';

interface NameEntry {
  src: string;
  context?: string;
  dst?: string;
}

interface AssetResult extends AssetResultBase {
  path?: string;
  entries?: NameEntry[];
  count?: number;
  empty?: boolean;
}

/** 复用术语表 /api/lexicon/glossary/translate 的任务结果；results 索引对应提交时的 rows。 */
interface TranslateResult extends AssetResultBase {
  output_folder?: string;
  results?: Array<[number, string]>;
  row_snapshots?: Array<{ src?: string; dst?: string }>;
  failed_count?: number;
}

type TranslateJob = AssetJob<TranslateResult>;
type LexiconStatus = { job: TranslateJob | null; project_key: string; output_folder: string };

const KINDS = ['asset_names_extract'] as const;
// 与姓名提取 asset_names_extract 区分，/api/lexicon 里其它词库任务一律不认
const TRANSLATE_KIND = 'lexicon_translate';

// antd 运行时样式未分层，会压过 @layer app 中的 padding 覆盖，所以紧凑内边距用组件 token 设置
const NAME_TABLE_THEME: ThemeConfig = { components: { Table: { cellPaddingBlockSM: 4, cellPaddingInlineSM: 8 } } };
// Paragraph 渲染为 div，自带 margin-bottom: 1em，同样只能用行内样式清掉
const CONTEXT_STYLE = { margin: 0, paddingTop: 2, fontSize: 13, lineHeight: '20px' } as const;

async function downloadBlob(filename: string, content: string, mediaType: string) {
  const blob = new Blob([content], { type: mediaType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
  return filename;
}

/** 与后端 collect_glossary_translate_tasks 一致：译名为空或等于原文才需要翻译。 */
function needsTranslate(item: NameEntry): boolean {
  const src = item.src.trim();
  const dst = (item.dst ?? '').trim();
  return Boolean(src) && (!dst || dst === src);
}

function toTranslateRows(entries: NameEntry[]) {
  return entries.map((item) => ({ src: item.src, dst: item.dst ?? '' }));
}

/** 只接受当前项目、当前输出目录下的 LLM 翻译任务。 */
function acceptTranslate(next: TranslateJob | null, key: string, folder: string): TranslateJob | null {
  const result = assetJobResult(next);
  if (!next || next.kind !== TRANSLATE_KIND || !result) return null;
  return result.project_key === key && result.output_folder === folder ? next : null;
}

/** 任务提交时的行快照必须与当前草稿逐行一致，才允许手动应用恢复的旧结果。 */
function snapshotMatches(entries: NameEntry[], result: TranslateResult | null): boolean {
  const snapshots = result?.row_snapshots;
  return Boolean(snapshots && snapshots.length === entries.length
    && snapshots.every((row, index) => row.src === entries[index].src && (row.dst ?? '') === (entries[index].dst ?? '')));
}

/** 按结果索引填入译名；原文已变化、或已有非占位译文（含用户修改）的条目保持不动。 */
function fillTranslations(entries: NameEntry[], result: TranslateResult): { rows: NameEntry[]; applied: number } {
  const snapshots = result.row_snapshots ?? [];
  const rows = entries.slice();
  let applied = 0;
  for (const pair of result.results ?? []) {
    if (!Array.isArray(pair)) continue;
    const [index, dst] = pair;
    const row = rows[index];
    const text = typeof dst === 'string' ? dst.trim() : '';
    if (!row || !text || snapshots[index]?.src !== row.src || !needsTranslate(row)) continue;
    rows[index] = { ...row, dst: text };
    applied += 1;
  }
  return { rows, applied };
}

export function NameExtractionPage(props: { state: AppState }) {
  const { state } = props;
  const t = useT();
  const projectRoot = String(state.project?.renpy_project_path ?? '');
  const gameFolder = String(state.project?.renpy_game_folder ?? '');
  const [inputDir, setInputDir] = useState(gameFolder || projectRoot);
  const [entries, setEntries] = useState<NameEntry[]>([]);
  const entriesRef = useRef(entries);
  entriesRef.current = entries;
  const [exportFormat, setExportFormat] = useState<'txt' | 'json'>('txt');
  const [dialog, setDialog] = useState<'export' | 'translate' | 'apply' | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportMessage, setExportMessage] = useState('');
  // LLM 翻译任务：与姓名提取任务分开追踪，只自动应用本页启动的任务
  const [translateJob, setTranslateJob] = useState<TranslateJob | null>(null);
  const [translateSubmitting, setTranslateSubmitting] = useState(false);
  const [translateCancelling, setTranslateCancelling] = useState(false);
  const [appliedTranslate, setAppliedTranslate] = useState('');
  const translateOwner = useRef<{ id: string; identity: string; sequence: number; projectKey: string; outputFolder: string } | null>(null);
  const onFinished = useCallback((finished: AssetJob<AssetResult>, result: AssetResult | null) => {
    // 零结果不覆盖已有 draft
    if (finished.status === 'done' && result?.operation === 'names_extract' && !result.empty && result.entries?.length) {
      setEntries(result.entries.map((item) => ({ src: item.src, context: item.context, dst: item.dst || item.src })));
    }
  }, []);
  const suite = useAssetSuiteJob<AssetResult>(state, KINDS, onFinished);
  const { identity, identityRef, sequence, keyReady, currentKey, handleFailure, job, result, active, error, setError, cancelling } = suite;
  const translateActive = assetJobRunning(translateJob);
  const translateResult = assetJobResult(translateJob);
  const translateBusy = translateSubmitting || translateActive || translateCancelling;
  const busy = suite.busy || exporting || translateBusy;
  const engineBusy = state.translation.engine_status !== 'IDLE' || state.translation.stop_barrier || state.translation.single_tasks;
  const pendingTranslate = entries.filter(needsTranslate).length;
  const translateJobId = translateJob?.id ?? '';
  const translateEventStatus = state.jobs.find((item) => item.id === translateJobId)?.status;

  useEffect(() => {
    setInputDir(gameFolder || projectRoot);
  }, [gameFolder, projectRoot]);

  useEffect(() => {
    setDialog(null);
    setExportMessage('');
    setExporting(false);
    // 项目切换清空 draft；同项目任务恢复不在此清空
    setEntries([]);
    translateOwner.current = null;
    setTranslateJob(null);
    setTranslateSubmitting(false);
    setTranslateCancelling(false);
    setAppliedTranslate('');
  }, [identity]);

  /** 拉取 /api/lexicon，只在仍是同一任务时更新；项目切换或卸载后晚到的响应直接丢弃。 */
  const refreshTranslate = useCallback(async (id: string) => {
    const local = identityRef.current;
    const current = sequence.current;
    try {
      const status = await request<LexiconStatus>('/api/lexicon');
      if (local !== identityRef.current || current !== sequence.current) return;
      const key = currentKey();
      const next = key !== null && status.project_key === key ? acceptTranslate(status.job, key, status.output_folder) : null;
      if (!next || next.id !== id) return;
      setTranslateJob(next);
      if (!assetJobRunning(next)) setTranslateCancelling(false);
    } catch {
      // 轮询失败等下一轮
    }
  }, [identityRef, sequence, currentKey]);

  // 进入页面或项目身份就绪后恢复最近一次翻译任务：仅展示状态，结果需用户手动应用
  useEffect(() => {
    if (!keyReady || state.link !== 'open') return;
    let alive = true;
    const local = identityRef.current;
    const current = sequence.current;
    void request<LexiconStatus>('/api/lexicon').then((status) => {
      if (!alive || local !== identityRef.current || current !== sequence.current || translateOwner.current) return;
      const key = currentKey();
      if (key === null || status.project_key !== key) return;
      const next = acceptTranslate(status.job, key, status.output_folder);
      if (next) setTranslateJob((previous) => previous ?? next);
    }).catch(() => undefined);
    return () => { alive = false; };
  }, [keyReady, state.link, identityRef, sequence, currentKey]);

  useEffect(() => {
    if (!translateActive || !translateJobId || state.link !== 'open') return;
    const timer = window.setInterval(() => void refreshTranslate(translateJobId), 800);
    return () => window.clearInterval(timer);
  }, [translateActive, translateJobId, state.link, refreshTranslate]);

  // sidecar job 事件只带摘要，状态变化时立即拉一次完整结果
  useEffect(() => {
    if (translateJobId && translateEventStatus) void refreshTranslate(translateJobId);
  }, [translateJobId, translateEventStatus, refreshTranslate]);

  const applyTranslateResult = useCallback((finished: TranslateJob, data: TranslateResult) => {
    setAppliedTranslate(finished.id);
    const { rows, applied } = fillTranslations(entriesRef.current, data);
    if (applied) setEntries(rows);
    if (finished.status === 'cancelled' && !applied) {
      state.pushToast('info', t('asset_names_translate_cancelled'));
      return;
    }
    state.pushToast(applied ? 'success' : 'info', applied
      ? t('asset_names_translate_applied').replace('{count}', String(applied))
      : t('asset_names_translate_empty'));
  }, [state, t]);

  // 本页启动的任务结束后按归属校验再写回草稿；失败/取消不清空草稿
  useEffect(() => {
    const owner = translateOwner.current;
    if (!translateJob || assetJobRunning(translateJob) || !owner || owner.id !== translateJob.id) return;
    translateOwner.current = null;
    void state.reloadTranslation();
    if (owner.identity !== identityRef.current || owner.sequence !== sequence.current) return;
    const data = assetJobResult(translateJob);
    if (!data || data.project_key !== owner.projectKey || data.output_folder !== owner.outputFolder) return;
    if (translateJob.status === 'failed') {
      setAppliedTranslate(translateJob.id);
      setError(translateJob.error || data.message || t('asset_names_translate_failed'));
      return;
    }
    applyTranslateResult(translateJob, data);
  }, [translateJob, identityRef, sequence, state, setError, t, applyTranslateResult]);

  const pickDir = useCallback(async () => {
    const context = identityRef.current;
    const current = sequence.current;
    const next = await window.renpy?.pickFolder?.(inputDir || undefined);
    if (next && context === identityRef.current && current === sequence.current) setInputDir(next);
  }, [inputDir, identityRef, sequence]);

  function startExtract() {
    void suite.submit('/api/asset-suite/names/extract', { input_dir: inputDir });
  }

  async function startTranslate() {
    setDialog(null);
    const key = currentKey();
    if (key === null || busy || engineBusy || !entriesRef.current.some(needsTranslate)) return;
    const local = identityRef.current;
    const current = sequence.current;
    const rows = toTranslateRows(entriesRef.current);
    setTranslateSubmitting(true);
    setError('');
    try {
      // 与术语表一致：先取 /api/lexicon 的 canonical 身份，再带 project_key/output_folder 提交
      const status = await request<LexiconStatus>('/api/lexicon');
      if (local !== identityRef.current || current !== sequence.current) return;
      if (status.project_key !== key) {
        setError(t('asset_names_translate_project_changed'));
        return;
      }
      const { job: next } = await request<{ job: TranslateJob }>('/api/lexicon/glossary/translate', {
        method: 'POST',
        body: JSON.stringify({ mode: 'llm', confirm: true, rows, project_key: key, output_folder: status.output_folder }),
      });
      if (local !== identityRef.current || current !== sequence.current) return;
      const accepted = acceptTranslate(next, key, status.output_folder);
      if (!accepted) return;
      translateOwner.current = { id: accepted.id, identity: local, sequence: current, projectKey: key, outputFolder: status.output_folder };
      setTranslateJob(accepted);
      void state.reloadTranslation();
    } catch (failure) {
      handleFailure(failure, local, current);
    } finally {
      if (local === identityRef.current && current === sequence.current) setTranslateSubmitting(false);
    }
  }

  async function cancelTranslate() {
    if (!translateJob || !translateActive || translateCancelling || translateJob.cancel_requested) return;
    const id = translateJob.id;
    const local = identityRef.current;
    const current = sequence.current;
    setTranslateCancelling(true);
    try {
      await cancelJob(id);
      if (local === identityRef.current && current === sequence.current) void refreshTranslate(id);
    } catch (failure) {
      if (local !== identityRef.current || current !== sequence.current) return;
      setTranslateCancelling(false);
      setError(errorText(failure));
    }
  }

  // 恢复的旧任务（非本页本次启动）只有在行快照与当前草稿一致时才可由用户手动应用
  const canApplyRecovered = Boolean(
    translateJob && translateResult && !translateBusy && translateJob.status !== 'failed'
    && translateOwner.current?.id !== translateJob.id && appliedTranslate !== translateJob.id
    && translateResult.results?.length && snapshotMatches(entries, translateResult),
  );

  function applyRecovered() {
    setDialog(null);
    const key = currentKey();
    if (!canApplyRecovered || !translateJob || !translateResult || key === null || translateResult.project_key !== key) return;
    applyTranslateResult(translateJob, translateResult);
  }

  async function startExport() {
    setDialog(null);
    const key = currentKey();
    if (!entries.length || key === null) return;
    const local = identityRef.current;
    const current = sequence.current;
    setExporting(true);
    setError('');
    setExportMessage('');
    try {
      const defaultName = exportFormat === 'json' ? 'glossary_names.json' : 'glossary_names.txt';
      const picked = await window.renpy?.saveFile?.({
        defaultPath: defaultName,
        filters: exportFormat === 'json'
          ? [{ name: 'JSON', extensions: ['json'] }]
          : [{ name: 'Text', extensions: ['txt'] }],
      });
      if (local !== identityRef.current || current !== sequence.current) return;
      // JSON 内容为裸数组 {src,dst,info,comment,type}，与 Qt TableManager 术语表导入格式一致
      const payload = await request<{
        filename: string;
        media_type: string;
        content: string;
        count: number;
        message: string;
        path?: string;
        backup_path?: string;
      }>('/api/asset-suite/names/export', {
        method: 'POST',
        body: JSON.stringify({
          entries: entries.map((item) => ({ src: item.src, dst: item.dst || item.src, info: '角色姓名', comment: '角色姓名', type: '角色' })),
          format: exportFormat,
          output_file: picked || '',
          confirm_overwrite: Boolean(picked),
          project_key: key,
        }),
      });
      if (local !== identityRef.current || current !== sequence.current) return;
      const backup = payload.backup_path ? `\n${t('asset_backup_path').replace('{path}', payload.backup_path)}` : '';
      if (picked && payload.path) {
        setExportMessage(`${payload.message}\n${payload.path}${backup}`);
      } else {
        const saved = await downloadBlob(payload.filename, payload.content, payload.media_type);
        if (local !== identityRef.current || current !== sequence.current) return;
        setExportMessage(`${payload.message}\n${saved}`);
      }
    } catch (failure) {
      handleFailure(failure, local, current);
    } finally {
      if (local === identityRef.current && current === sequence.current) setExporting(false);
    }
  }

  const statusText = assetStatusText(t, suite, t('asset_names_idle'));

  return (
    <div className="rb-asset-page rb-page-scroll" data-rb-page="name-extraction">
      {error ? <Banner tone="error">{error}</Banner> : null}
      <Banner tone={result?.empty || result?.partial || result?.level === 'warning' ? 'warning' : result?.level === 'error' ? 'error' : 'info'}>{statusText}</Banner>
      {exportMessage ? <Banner tone="success">{exportMessage}</Banner> : null}
      {active ? <Progress percent={Math.min(100, 100 * (job?.progress || 0))} aria-label={t('asset_running')} /> : null}
      {active ? (
        <div className="rb-tool-actions">
          <Button className="rb-asset-cancel" onClick={() => void suite.cancel()} disabled={cancelling || Boolean(job?.cancel_requested)}>
            {t('asset_cancel')}
          </Button>
        </div>
      ) : null}
      <AssetResultNotes result={result} />

      <SettingsGroup title={t('asset_names_extract_title')} description={t('asset_names_extract_desc')}>
        <Form.Item className="rb-asset-input-dir" label={t('asset_names_input')} style={{ marginBottom: 0 }}>
          <Input value={inputDir} onChange={(event) => setInputDir(event.target.value)} disabled={busy} />
        </Form.Item>
        <div className="rb-tool-actions">
          <Button onClick={() => void pickDir()} disabled={busy}>{t('asset_pick_folder')}</Button>
          <Button type="primary" className="rb-asset-extract" onClick={startExtract} disabled={busy || engineBusy || !keyReady || !inputDir.trim() || state.link !== 'open'}>
            {t('asset_names_extract')}
          </Button>
        </div>
      </SettingsGroup>

      <SettingsGroup title={t('asset_names_export_title')} description={t('asset_names_export_desc')}>
        <p className="card-description">{t('asset_names_count').replace('{count}', String(entries.length))}</p>
        <div className="rb-tool-actions">
          <Button
            className="rb-asset-translate-names"
            onClick={() => setDialog('translate')}
            disabled={busy || engineBusy || !keyReady || !pendingTranslate || state.link !== 'open'}
          >
            {t('asset_names_translate_llm')}
          </Button>
          {translateActive ? (
            <Button className="rb-asset-cancel" onClick={() => void cancelTranslate()} disabled={translateCancelling || Boolean(translateJob?.cancel_requested)}>
              {t('asset_cancel')}
            </Button>
          ) : null}
          {canApplyRecovered ? (
            <Button onClick={() => setDialog('apply')} disabled={busy || state.link !== 'open'}>{t('asset_names_translate_apply')}</Button>
          ) : null}
        </div>
        {translateActive ? (
          <>
            <Banner tone="info">
              {translateCancelling || translateJob?.cancel_requested ? t('asset_names_translate_cancelling') : (translateResult?.message || t('asset_names_translate_running'))}
            </Banner>
            <Progress percent={Math.min(100, 100 * (translateJob?.progress || 0))} aria-label={t('asset_names_translate_running')} />
          </>
        ) : null}
        {translateJob && !translateActive && appliedTranslate === translateJob.id ? <AssetResultNotes result={translateResult} /> : null}
        <ConfigProvider theme={NAME_TABLE_THEME}>
          <Table
            className="rb-asset-name-list"
            size="small"
            tableLayout="fixed"
            // 固定列宽之和作为横向滚动下限，窄窗口横向滚动；纵向高度随窗口可用空间伸缩，最低 240px
            scroll={{ x: 760, y: 'max(240px, calc(100vh - 360px))' }}
            pagination={{ pageSize: 50, showSizeChanger: true, pageSizeOptions: [20, 50, 100, 200] }}
            rowKey={(row) => String(row.__i)}
            dataSource={entries.map((item, index) => ({ ...item, __i: index }))}
            columns={[
              {
                title: t('asset_names_src'),
                dataIndex: 'src',
                key: 'src',
                width: 180,
                render: (value: string) => <Input size="small" value={value} readOnly title={value} />,
              },
              {
                title: t('asset_names_dst'),
                dataIndex: 'dst',
                key: 'dst',
                width: 220,
                render: (_: string | undefined, item: NameEntry & { __i: number }) => (
                  <Input
                    size="small"
                    value={item.dst || item.src}
                    disabled={busy}
                    onChange={(event) => {
                      const value = event.target.value;
                      const absoluteIndex = item.__i;
                      setEntries((prev) => prev.map((row, rowIndex) => (rowIndex === absoluteIndex ? { ...row, dst: value } : row)));
                    }}
                  />
                ),
              },
              {
                title: t('asset_names_context'),
                dataIndex: 'context',
                key: 'context',
                width: 360,
                // 上下文默认最多 2 行，超出省略；展开/收起为可聚焦按钮，键盘可操作，不在单元格内出现滚动条
                render: (value: string | undefined) => (
                  <Typography.Paragraph
                    className="rb-asset-name-context"
                    style={CONTEXT_STYLE}
                    type="secondary"
                    ellipsis={value ? { rows: 2, expandable: 'collapsible' } : false}
                  >
                    {value || '—'}
                  </Typography.Paragraph>
                ),
              },
            ]}
          />
        </ConfigProvider>
        <div className="rb-tool-actions">
          <Button type={exportFormat === 'txt' ? 'primary' : 'default'} className="rb-asset-format-txt" onClick={() => setExportFormat('txt')} disabled={busy}>TXT</Button>
          <Button type={exportFormat === 'json' ? 'primary' : 'default'} className="rb-asset-format-json" onClick={() => setExportFormat('json')} disabled={busy}>JSON</Button>
          <Button type="primary" className="rb-asset-export-names" onClick={() => setDialog('export')} disabled={busy || !keyReady || !entries.length || state.link !== 'open'}>
            {t('asset_names_export')}
          </Button>
        </div>
      </SettingsGroup>

      {dialog === 'export' ? (
        <Dialog title={t('asset_names_export_confirm_title')} confirmText={t('asset_names_export')} cancelText={t('workbench_cancel')} onConfirm={() => void startExport()} onCancel={() => setDialog(null)}>
          <p>{t('asset_names_export_confirm').replace('{format}', exportFormat.toUpperCase())}</p>
        </Dialog>
      ) : null}
      {dialog === 'translate' ? (
        <Dialog title={t('asset_names_translate_confirm_title')} confirmText={t('asset_names_translate_llm')} cancelText={t('workbench_cancel')} onConfirm={() => void startTranslate()} onCancel={() => setDialog(null)}>
          <p>{t('asset_names_translate_confirm').replace('{count}', String(pendingTranslate))}</p>
        </Dialog>
      ) : null}
      {dialog === 'apply' ? (
        <Dialog title={t('asset_names_translate_apply_title')} confirmText={t('asset_names_translate_apply')} cancelText={t('workbench_cancel')} onConfirm={applyRecovered} onCancel={() => setDialog(null)}>
          <p>{t('asset_names_translate_apply_confirm')}</p>
        </Dialog>
      ) : null}
    </div>
  );
}
