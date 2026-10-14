/**
 * 资源套件三页（结构/Emoji、批量修正、姓名提取）共用：
 * 从 /api/asset-suite/status 取后端 canonical project_key，本地项目身份变化后重新拉取，期间禁止写入；
 * 任务只接受本页 kind 且 project_key 与 canonical 一致的结果，避免把其它工具或旧项目的任务映射到本页。
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import { ApiError, cancelJob, request } from '../api';
import { useT } from '../i18n';
import type { JobSnapshot } from '../types';
import type { AppState } from '../useAppState';
import { Banner } from '../ui';

export interface AssetResultBase {
  project_key?: string;
  message?: string;
  worker_active?: boolean;
  operation?: string;
  warnings?: string[];
  success?: boolean;
  level?: string;
  partial?: boolean;
  backup_path?: string;
  backups?: string[];
}

export type AssetJob<R> = JobSnapshot & { cancel_requested?: boolean; result?: R | null };

export function assetJobResult<R>(job: AssetJob<R> | null): R | null {
  return job?.result && typeof job.result === 'object' ? job.result : null;
}

export function assetJobRunning<R extends AssetResultBase>(job: AssetJob<R> | null): boolean {
  return Boolean(job && (job.status === 'pending' || job.status === 'running' || assetJobResult(job)?.worker_active));
}

export const errorText = (error: unknown) => (error instanceof Error ? error.message : String(error));

export function useAssetSuiteJob<R extends AssetResultBase>(
  state: AppState,
  kinds: readonly string[],
  onFinished?: (job: AssetJob<R>, result: R | null) => void,
) {
  const values = state.settings?.values;
  const identity = JSON.stringify([
    state.project?.renpy_project_path, state.project?.renpy_game_folder, state.project?.renpy_tl_folder,
    values?.renpy_project_path, values?.renpy_game_folder, values?.renpy_tl_folder, values?.input_folder, values?.output_folder,
  ]);
  const identityRef = useRef(identity);
  identityRef.current = identity;
  const [canonical, setCanonical] = useState<{ identity: string; key: string } | null>(null);
  const canonicalRef = useRef(canonical);
  canonicalRef.current = canonical;
  const keyReady = canonical?.identity === identity;
  const [job, setJob] = useState<AssetJob<R> | null>(null);
  const [error, setError] = useState('');
  const [checking, setChecking] = useState(true);
  const [cancelling, setCancelling] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const pending = useRef(false);
  const revision = useRef(0);
  const completed = useRef('');
  const sequence = useRef(0);
  const finishedRef = useRef(onFinished);
  finishedRef.current = onFinished;
  const kindsKey = kinds.join('|');

  const accept = useCallback((next: AssetJob<R> | null, key: string): AssetJob<R> | null => {
    if (!next || !kindsKey.split('|').includes(next.kind)) return null;
    return assetJobResult(next)?.project_key === key ? next : null;
  }, [kindsKey]);

  useEffect(() => {
    sequence.current += 1;
    completed.current = '';
    pending.current = false;
    setSubmitting(false);
    setJob(null);
    setError('');
    setCancelling(false);
    setChecking(true);
    return () => { sequence.current += 1; };
  }, [identity]);

  useEffect(() => {
    if (state.link !== 'open') return;
    let alive = true;
    let timer = 0;
    const local = identity;
    const current = sequence.current;
    const poll = async () => {
      try {
        if (pending.current) return;
        const requestRevision = revision.current;
        const status = await request<{ job: AssetJob<R> | null; project_key: string }>('/api/asset-suite/status');
        if (!alive || local !== identityRef.current || current !== sequence.current || requestRevision !== revision.current || pending.current) return;
        const key = String(status.project_key ?? '');
        setCanonical((previous) => (previous?.identity === local && previous.key === key ? previous : { identity: local, key }));
        const next = accept(status.job, key);
        setJob(next);
        setChecking(false);
        if (!assetJobRunning(next)) setCancelling(false);
        if (next && !assetJobRunning(next) && completed.current !== next.id) {
          completed.current = next.id;
          finishedRef.current?.(next, assetJobResult(next));
          await state.reloadTranslation();
        }
      } catch (failure) {
        if (alive && local === identityRef.current && current === sequence.current) {
          setChecking(false);
          setError(errorText(failure));
        }
      } finally {
        if (alive) timer = window.setTimeout(() => void poll(), 1500);
      }
    };
    void poll();
    return () => { alive = false; window.clearTimeout(timer); };
  }, [identity, state.link, state.reloadTranslation, accept]);

  /** canonical key 尚未按当前本地身份拉取时返回 null，调用方必须放弃写入。 */
  const currentKey = useCallback((): string | null => {
    const value = canonicalRef.current;
    return value && value.identity === identityRef.current ? value.key : null;
  }, []);

  /** 409 表示后端项目已切换：作废 canonical，等下一次轮询重新拉取后才允许写入。 */
  const handleFailure = useCallback((failure: unknown, local: string, current: number) => {
    if (local !== identityRef.current || current !== sequence.current) return;
    if (failure instanceof ApiError && failure.status === 409) {
      canonicalRef.current = null;
      setCanonical(null);
    }
    setError(errorText(failure));
  }, []);

  const submit = useCallback(async (path: string, body: Record<string, unknown>): Promise<boolean> => {
    const key = currentKey();
    if (pending.current || key === null) return false;
    const local = identityRef.current;
    const current = sequence.current;
    pending.current = true;
    revision.current += 1;
    setSubmitting(true);
    setError('');
    try {
      const { job: next } = await request<{ job: AssetJob<R> }>(path, {
        method: 'POST',
        body: JSON.stringify({ ...body, project_key: key }),
      });
      if (local !== identityRef.current || current !== sequence.current) return false;
      setJob(accept(next, key));
      await state.reloadTranslation();
      return local === identityRef.current && current === sequence.current;
    } catch (failure) {
      handleFailure(failure, local, current);
      return false;
    } finally {
      if (local === identityRef.current && current === sequence.current) {
        pending.current = false;
        setSubmitting(false);
      }
    }
  }, [accept, currentKey, handleFailure, state.reloadTranslation]);

  const cancel = useCallback(async () => {
    const key = currentKey();
    if (!job || !assetJobRunning(job) || cancelling || key === null || assetJobResult(job)?.project_key !== key) return;
    const local = identityRef.current;
    const current = sequence.current;
    setCancelling(true);
    try {
      await cancelJob(job.id);
    } catch (failure) {
      if (local !== identityRef.current || current !== sequence.current) return;
      setCancelling(false);
      setError(errorText(failure));
    }
  }, [job, cancelling, currentKey]);

  const active = assetJobRunning(job);
  return {
    identity,
    identityRef,
    // 请求发起时保存序号；项目变化和卸载 cleanup 都会递增，使晚到结果失效。
    sequence,
    keyReady,
    currentKey,
    handleFailure,
    job,
    result: assetJobResult(job),
    active,
    checking,
    error,
    setError,
    cancelling,
    submitting,
    busy: active || cancelling || submitting,
    submit,
    cancel,
  };
}

export function assetStatusText<R extends AssetResultBase>(
  t: ReturnType<typeof useT>,
  view: { checking: boolean; active: boolean; cancelling: boolean; job: AssetJob<R> | null; result: R | null },
  idle: string,
): string {
  const { checking, active, cancelling, job, result } = view;
  if (checking) return t('asset_checking');
  if (active) return cancelling || job?.cancel_requested ? t('asset_cancelling') : (result?.message || t('asset_running'));
  if (job?.status === 'done') return result?.message || t('asset_done');
  if (job?.status === 'failed') return job.error || result?.message || t('asset_failed');
  if (job?.status === 'cancelled') return t('asset_cancelled');
  return idle;
}

/** 部分写入、警告与备份位置；三页统一展示。 */
export function AssetResultNotes(props: { result: AssetResultBase | null }) {
  const { result } = props;
  const t = useT();
  if (!result) return null;
  const backups = [...new Set([result.backup_path, ...(result.backups ?? [])].filter((path): path is string => Boolean(path)))];
  return (
    <>
      {result.partial ? <Banner tone="warning">{t('asset_partial')}</Banner> : null}
      {result.warnings?.length ? <Banner tone="warning">{result.warnings.join('\n')}</Banner> : null}
      {backups.map((path) => <p key={path} className="card-description rb-asset-backup">{t('asset_backup_path').replace('{path}', path)}</p>)}
    </>
  );
}
