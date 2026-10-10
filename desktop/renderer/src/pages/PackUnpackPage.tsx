/** 解包 / 反编译 / 打包：复用 /api/archive 长任务，不删除源档。 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Button, Checkbox, Form, Input, Progress } from 'antd';

import { cancelJob, request } from '../api';
import { useT } from '../i18n';
import type { JobSnapshot } from '../types';
import type { AppState } from '../useAppState';
import { Banner, Dialog, SettingsGroup } from '../ui';

interface ArchiveResult {
  project_key?: string;
  message?: string;
  worker_active?: boolean;
  path?: string;
  outputs?: string[];
  success?: boolean;
  archives_removed?: boolean;
}

type ArchiveJob = JobSnapshot & { cancel_requested?: boolean; result?: ArchiveResult | null };
type ConfirmKind = 'unpack' | 'decompile' | 'pack' | 'cleanupTemp' | 'cleanupRpyc';

function jobResult(job: ArchiveJob | null): ArchiveResult | null {
  return job?.result && typeof job.result === 'object' ? job.result : null;
}

function jobRunning(job: ArchiveJob | null): boolean {
  return Boolean(job && (job.status === 'pending' || job.status === 'running' || jobResult(job)?.worker_active));
}

/** 仅用于展示：与 Qt5 一致推导为源目录同级的“源目录名.rpa”，实际路径由后端重新推导。 */
function derivePackOutput(source: string): string {
  const trimmed = source.trim().replace(/[\\/]+$/, '');
  const index = Math.max(trimmed.lastIndexOf('/'), trimmed.lastIndexOf('\\'));
  const name = trimmed.slice(index + 1);
  if (index < 0 || !name || name.endsWith(':')) return '';
  return `${trimmed.slice(0, index + 1)}${name}.rpa`;
}

/** 与 Qt 一致：相对文件名落在源目录同级；后端会按 sidecar 工作目录解析相对路径，故提交前补成绝对路径。 */
function resolvePackOutput(source: string, output: string): string {
  const value = output.trim();
  if (!value) return '';
  if (/^([a-zA-Z]:[\\/]|[\\/])/.test(value)) return value;
  const base = derivePackOutput(source);
  const index = Math.max(base.lastIndexOf('/'), base.lastIndexOf('\\'));
  return index < 0 ? value : `${base.slice(0, index + 1)}${value}`;
}

const errorText = (error: unknown) => (error instanceof Error ? error.message : String(error));

export function PackUnpackPage(props: { state: AppState }) {
  const { state } = props;
  const t = useT();
  const projectRoot = String(state.project?.renpy_project_path ?? '');
  const gameFolder = String(state.project?.renpy_game_folder ?? '');
  const [unpackPath, setUnpackPath] = useState(gameFolder || projectRoot);
  const [decompilePath, setDecompilePath] = useState(projectRoot || gameFolder);
  const [packSource, setPackSource] = useState(gameFolder);
  const [packOutput, setPackOutput] = useState('');
  const [direct, setDirect] = useState(true);
  const [scriptOnly, setScriptOnly] = useState(false);
  const [overwrite, setOverwrite] = useState(false);
  const [useUnren, setUseUnren] = useState(true);
  const [splitEnabled, setSplitEnabled] = useState(false);
  const [partSize, setPartSize] = useState('1G');
  const [job, setJob] = useState<ArchiveJob | null>(null);
  const [error, setError] = useState('');
  const [confirm, setConfirm] = useState<ConfirmKind | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [checking, setChecking] = useState(true);
  const projectKey = JSON.stringify([projectRoot, gameFolder]);
  const projectRef = useRef(projectKey);
  const pending = useRef(false);
  const revision = useRef(0);
  const completed = useRef('');
  const [submitting, setSubmitting] = useState(false);
  const sequence = useRef(0);
  projectRef.current = projectKey;
  const active = jobRunning(job);
  const engineBusy = state.translation.engine_status !== 'IDLE' || state.translation.stop_barrier || state.translation.single_tasks;
  const busy = active || cancelling || submitting;
  const startBlocked = busy || engineBusy || state.link !== 'open';
  const derivedOutput = derivePackOutput(packSource);

  useEffect(() => {
    setUnpackPath(gameFolder || projectRoot);
    setDecompilePath(projectRoot || gameFolder);
    setPackSource(gameFolder);
  }, [gameFolder, projectRoot]);

  useEffect(() => {
    sequence.current += 1;
    setJob(null);
    setError('');
    setConfirm(null);
    setCancelling(false);
    setChecking(true);
    return () => { sequence.current += 1; };
  }, [projectKey]);

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
        const { job: next } = await request<{ job: ArchiveJob | null }>('/api/archive');
        if (!alive || key !== projectRef.current || current !== sequence.current || requestRevision !== revision.current || pending.current) return;
        setJob(next);
        setChecking(false);
        if (!jobRunning(next)) setCancelling(false);
        if (next && !jobRunning(next) && completed.current !== next.id) {
          completed.current = next.id;
          await state.reloadTranslation();
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
  }, [projectKey, state.link, state.reloadTranslation]);

  const pickDir = useCallback(async (setter: (value: string) => void, current: string) => {
    const context = projectRef.current;
    const path = await window.renpy?.pickFolder?.(current || undefined);
    if (path && context === projectRef.current) setter(path);
  }, []);

  const pickSave = useCallback(async () => {
    const context = projectRef.current;
    const path = await window.renpy?.saveFile?.({
      defaultPath: packOutput || derivedOutput || 'archive.rpa',
      filters: [{ name: 'RPA', extensions: ['rpa'] }],
    });
    if (path && context === projectRef.current) setPackOutput(path);
  }, [packOutput, derivedOutput]);

  /** 统一提交 archive 长任务；同一时刻只允许一个请求在途。 */
  async function submit(endpoint: string, body: Record<string, unknown>) {
    if (pending.current) return;
    pending.current = true;
    revision.current += 1;
    setSubmitting(true);
    const context = projectRef.current;
    setError('');
    setConfirm(null);
    try {
      const { job: next } = await request<{ job: ArchiveJob }>(`/api/archive/${endpoint}`, {
        method: 'POST',
        body: JSON.stringify({ ...body, project_key: '' }),
      });
      if (context !== projectRef.current) return;
      setJob(next);
      await state.reloadTranslation();
    } catch (failure) {
      if (context === projectRef.current) setError(errorText(failure));
    } finally {
      pending.current = false;
      setSubmitting(false);
    }
  }

  const startUnpack = () => submit('unpack', { path: unpackPath, direct, script_only: scriptOnly });
  const startDecompile = () => submit('decompile', {
    path: decompilePath,
    overwrite,
    use_unren: useUnren,
    confirm_overwrite: overwrite,
  });
  // 输出留空时原样发送空串，由后端推导；未勾选分卷时发送 null。
  const startPack = () => submit('pack', {
    source_dir: packSource,
    output_file: resolvePackOutput(packSource, packOutput),
    max_part_size: splitEnabled ? partSize : null,
    confirm: true,
  });
  const startCleanupTemp = () => submit('cleanup-temp', { path: unpackPath });
  const startCleanupRpyc = () => submit('cleanup-rpyc', { path: decompilePath });

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
  const statusText = checking
    ? t('archive_checking')
    : active
      ? (cancelling || job?.cancel_requested ? t('archive_cancelling') : (result?.message || t('archive_running')))
      : job?.status === 'done'
        ? (result?.message || t('archive_done'))
        : job?.status === 'failed'
          ? (job.error || result?.message || t('archive_failed'))
          : job?.status === 'cancelled'
            ? t('archive_cancelled')
            : t('archive_idle');
  const statusTone = active || checking
    ? 'info'
    : job?.status === 'done'
      ? 'success'
      : job?.status === 'failed'
        ? 'error'
        : job?.status === 'cancelled'
          ? 'warning'
          : 'info';

  return (
    <div className="rb-archive-page rb-page-scroll">
      {error ? <Banner tone="error">{error}</Banner> : null}
      <Banner tone={statusTone}>{statusText}</Banner>
      {active ? <Progress percent={Math.min(100, 100 * (job?.progress || 0))} aria-label={t('archive_running')} /> : null}
      {active ? (
        <div className="rb-tool-actions">
          <Button onClick={() => void onCancel()} disabled={cancelling || Boolean(job?.cancel_requested)}>
            {t('archive_cancel')}
          </Button>
        </div>
      ) : null}

      {result?.outputs?.length ? <ul>{result.outputs.map(path => <li key={path} className="card-description">{path}</li>)}</ul> : null}

      <SettingsGroup title={t('archive_unpack_title')} description={t('archive_unpack_desc')}>
        <Form.Item label={t('archive_path')} style={{ marginBottom: 0 }}>
          <Input value={unpackPath} onChange={(event) => setUnpackPath(event.target.value)} disabled={busy} />
        </Form.Item>
        <div className="rb-tool-actions">
          <Button onClick={() => void pickDir(setUnpackPath, unpackPath)} disabled={busy}>{t('archive_pick_folder')}</Button>
          <Checkbox checked={direct} onChange={(event) => setDirect(event.target.checked)} disabled={busy}>{t('archive_direct')}</Checkbox>
          <Checkbox checked={scriptOnly} onChange={(event) => setScriptOnly(event.target.checked)} disabled={busy}>{t('archive_script_only')}</Checkbox>
          <Button type="primary" onClick={() => setConfirm('unpack')} disabled={startBlocked || !unpackPath.trim()}>{t('archive_unpack')}</Button>
          <Button danger onClick={() => setConfirm('cleanupTemp')} disabled={startBlocked || !unpackPath.trim()}>{t('archive_cleanup_temp')}</Button>
        </div>
        <p className="card-description">{t('archive_keep_rpa')}</p>
      </SettingsGroup>

      <SettingsGroup title={t('archive_decompile_title')} description={t('archive_decompile_desc')}>
        <Form.Item label={t('archive_path')} style={{ marginBottom: 0 }}>
          <Input value={decompilePath} onChange={(event) => setDecompilePath(event.target.value)} disabled={busy} />
        </Form.Item>
        <div className="rb-tool-actions">
          <Button onClick={() => void pickDir(setDecompilePath, decompilePath)} disabled={busy}>{t('archive_pick_folder')}</Button>
          <Checkbox checked={overwrite} onChange={(event) => setOverwrite(event.target.checked)} disabled={busy}>{t('archive_overwrite')}</Checkbox>
          <Checkbox checked={useUnren} onChange={(event) => setUseUnren(event.target.checked)} disabled={busy}>{t('archive_use_unren')}</Checkbox>
          <Button type="primary" onClick={() => (overwrite ? setConfirm('decompile') : void startDecompile())} disabled={startBlocked || !decompilePath.trim()}>
            {t('archive_decompile')}
          </Button>
          <Button danger onClick={() => setConfirm('cleanupRpyc')} disabled={startBlocked || !decompilePath.trim()}>{t('archive_cleanup_rpyc')}</Button>
        </div>
      </SettingsGroup>

      <SettingsGroup title={t('archive_pack_title')} description={t('archive_pack_desc')}>
        <Form.Item label={t('archive_source')} style={{ marginBottom: 0 }}>
          <Input value={packSource} onChange={(event) => setPackSource(event.target.value)} disabled={busy} />
        </Form.Item>
        <Form.Item
          label={t('archive_output')}
          extra={!packOutput.trim() && derivedOutput ? `${t('archive_output_auto')}${derivedOutput}` : undefined}
          style={{ marginBottom: 0 }}
        >
          <Input
            value={packOutput}
            placeholder={derivedOutput || t('archive_output_placeholder')}
            onChange={(event) => setPackOutput(event.target.value)}
            disabled={busy}
          />
        </Form.Item>
        <div className="rb-tool-actions">
          <Checkbox checked={splitEnabled} onChange={(event) => setSplitEnabled(event.target.checked)} disabled={busy}>{t('archive_split')}</Checkbox>
        </div>
        <Form.Item label={t('archive_part_size')} style={{ marginBottom: 0 }}>
          <Input value={partSize} placeholder={t('archive_part_size_placeholder')} onChange={(event) => setPartSize(event.target.value)} disabled={busy || !splitEnabled} maxLength={20} />
        </Form.Item>
        <div className="rb-tool-actions">
          <Button onClick={() => void pickDir(setPackSource, packSource)} disabled={busy}>{t('archive_pick_folder')}</Button>
          <Button onClick={() => void pickSave()} disabled={busy}>{t('archive_pick_output')}</Button>
          <Button
            type="primary"
            onClick={() => setConfirm('pack')}
            disabled={startBlocked || !packSource.trim() || (splitEnabled && !partSize.trim())}
          >
            {t('archive_pack')}
          </Button>
        </div>
      </SettingsGroup>

      {confirm === 'unpack' ? (
        <Dialog title={t('archive_unpack')} confirmText={t('archive_unpack')} cancelText={t('workbench_cancel')} onConfirm={() => void startUnpack()} onCancel={() => setConfirm(null)}>
          <p>{t('archive_unpack_confirm')}</p>
          <p className="card-description">{unpackPath}</p>
        </Dialog>
      ) : null}
      {confirm === 'decompile' ? (
        <Dialog title={t('archive_overwrite_confirm_title')} confirmText={t('archive_decompile')} cancelText={t('workbench_cancel')} onConfirm={() => void startDecompile()} onCancel={() => setConfirm(null)}>
          <p>{t('archive_overwrite_confirm')}</p>
        </Dialog>
      ) : null}
      {confirm === 'pack' ? (
        <Dialog title={t('archive_pack_confirm_title')} confirmText={t('archive_pack')} cancelText={t('workbench_cancel')} onConfirm={() => void startPack()} onCancel={() => setConfirm(null)}>
          <p>{t('archive_pack_confirm')}</p>
          <p className="card-description">{resolvePackOutput(packSource, packOutput) || derivedOutput}</p>
          {splitEnabled ? <p className="card-description">{t('archive_part_size')}：{partSize.trim()}</p> : null}
        </Dialog>
      ) : null}
      {confirm === 'cleanupTemp' ? (
        <Dialog title={t('archive_cleanup_temp_title')} confirmText={t('archive_cleanup_temp')} cancelText={t('workbench_cancel')} onConfirm={() => void startCleanupTemp()} onCancel={() => setConfirm(null)}>
          <p>{t('archive_cleanup_temp_confirm')}</p>
          <p className="card-description">{unpackPath}</p>
        </Dialog>
      ) : null}
      {confirm === 'cleanupRpyc' ? (
        <Dialog title={t('archive_cleanup_rpyc_title')} confirmText={t('archive_cleanup_rpyc')} cancelText={t('workbench_cancel')} onConfirm={() => void startCleanupRpyc()} onCancel={() => setConfirm(null)}>
          <p>{t('archive_cleanup_rpyc_confirm')}</p>
          <p className="card-description">{decompilePath}</p>
        </Dialog>
      ) : null}
    </div>
  );
}
