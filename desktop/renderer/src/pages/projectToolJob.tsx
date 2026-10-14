/**
 * 绑定项目工具页共用任务钩子（语言入口 / 默认语言 / 字体注入 / RPY 抽取等）：
 * 从 statusPath 取后端 canonical project_key，本地项目身份或页上下文变化后重新拉取，期间禁止写入；
 * 任务只接受本页 kind 且 project_key 与 canonical 一致的结果。
 * 使用带序列号与 pending 守卫的恢复轮询，避免与提交请求竞态。
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import { ApiError, cancelJob, request } from '../api';
import { useT } from '../i18n';
import type { JobSnapshot } from '../types';
import type { AppState } from '../useAppState';

export interface ToolResultBase {
  project_key?: string;
  message?: string;
  worker_active?: boolean;
  written?: boolean;
  partial?: boolean;
  language?: string | null;
  backup_path?: string;
  action?: string;
}

export type ToolJob<R> = JobSnapshot & { cancel_requested?: boolean; result?: R | null };

export function toolJobResult<R>(job: ToolJob<R> | null): R | null {
  return job?.result && typeof job.result === 'object' ? job.result : null;
}

export function toolJobRunning<R extends ToolResultBase>(job: ToolJob<R> | null): boolean {
  return Boolean(job && (job.status === 'pending' || job.status === 'running' || toolJobResult(job)?.worker_active));
}

export const toolErrorText = (error: unknown) => (error instanceof Error ? error.message : String(error));

export function useProjectToolJob<R extends ToolResultBase, S extends { project_key?: string; job?: ToolJob<R> | null; owner_identity?: string[] }>(
  state: AppState,
  statusPath: string,
  kinds: readonly string[],
  /** 页内 path/category/language 等；变化时使 canonical/job/轮询失效，但不触发页面把输入重置回全局默认 */
  contextKey: string = '',
) {
  const values = state.settings?.values;
  // 仅全局项目配置；页面应用此值决定是否重置本地输入，勿混入 path/category
  const projectIdentity = JSON.stringify([
    state.project?.renpy_project_path, state.project?.renpy_game_folder, state.project?.renpy_tl_folder,
    values?.renpy_project_path, values?.renpy_game_folder, values?.renpy_tl_folder, values?.input_folder, values?.output_folder,
  ]);
  // 工具上下文：含 statusPath（已带 query）与可选额外键，驱动轮询/canonical 失效
  const toolIdentity = JSON.stringify([projectIdentity, statusPath, contextKey]);
  const identityRef = useRef(toolIdentity);
  identityRef.current = toolIdentity;
  const [canonical, setCanonical] = useState<{ identity: string; key: string } | null>(null);
  const canonicalRef = useRef(canonical);
  canonicalRef.current = canonical;
  const keyReady = canonical?.identity === toolIdentity;
  const [status, setStatus] = useState<S | null>(null);
  const statusRef = useRef(status);
  statusRef.current = status;
  const [job, setJob] = useState<ToolJob<R> | null>(null);
  const [error, setError] = useState('');
  const [checking, setChecking] = useState(true);
  const [cancelling, setCancelling] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const pending = useRef(false);
  const revision = useRef(0);
  const completed = useRef('');
  const sequence = useRef(0);
  const kindsKey = kinds.join('|');

  const accept = useCallback((next: ToolJob<R> | null, key: string): ToolJob<R> | null => {
    if (!next || !kindsKey.split('|').includes(next.kind)) return null;
    return toolJobResult(next)?.project_key === key ? next : null;
  }, [kindsKey]);

  useEffect(() => {
    sequence.current += 1;
    completed.current = '';
    pending.current = false;
    setSubmitting(false);
    setJob(null);
    setStatus(null);
    setError('');
    setCancelling(false);
    setChecking(true);
    return () => { sequence.current += 1; };
  }, [toolIdentity]);

  useEffect(() => {
    if (state.link !== 'open') return;
    let alive = true;
    let timer = 0;
    const local = toolIdentity;
    const current = sequence.current;
    const poll = async () => {
      try {
        if (pending.current) return;
        const requestRevision = revision.current;
        const payload = await request<S>(statusPath);
        if (!alive || local !== identityRef.current || current !== sequence.current || requestRevision !== revision.current || pending.current) return;
        const key = String(payload.project_key ?? '');
        setCanonical((previous) => (previous?.identity === local && previous.key === key ? previous : { identity: local, key }));
        setStatus(payload);
        const next = accept(payload.job ?? null, key);
        setJob(next);
        // 成功轮询清除旧错误，避免切上下文后残留提示
        setError('');
        setChecking(false);
        if (!toolJobRunning(next)) setCancelling(false);
        if (next && !toolJobRunning(next) && completed.current !== next.id) {
          // 只读扫描也持有 TESTING；从后端确认释放，刷新失败则下轮重试。
          await state.reloadTranslation();
          if (alive && local === identityRef.current && current === sequence.current) {
            completed.current = next.id;
          }
        }
      } catch (failure) {
        if (alive && local === identityRef.current && current === sequence.current) {
          setChecking(false);
          setError(toolErrorText(failure));
        }
      } finally {
        if (alive) timer = window.setTimeout(() => void poll(), 1500);
      }
    };
    void poll();
    return () => { alive = false; window.clearTimeout(timer); };
  }, [toolIdentity, state.link, state.reloadTranslation, accept, statusPath]);

  const currentKey = useCallback((): string | null => {
    const value = canonicalRef.current;
    return value && value.identity === identityRef.current ? value.key : null;
  }, []);

  const handleFailure = useCallback((failure: unknown, local: string, current: number) => {
    if (local !== identityRef.current || current !== sequence.current) return;
    if (failure instanceof ApiError && failure.status === 409) {
      canonicalRef.current = null;
      setCanonical(null);
    }
    setError(toolErrorText(failure));
  }, []);

  const submit = useCallback(async (path: string, body: Record<string, unknown>): Promise<boolean> => {
    const key = currentKey();
    // keyReady 前为 null；未绑定项目时 canonical.key 可为 ""，仍允许提交
    if (pending.current || key === null) return false;
    const local = identityRef.current;
    const current = sequence.current;
    pending.current = true;
    revision.current += 1;
    setSubmitting(true);
    setError('');
    try {
      // C 页 status 含 owner_identity 时附带快照；body 已显式传入则不覆盖；其他工具无该字段不受影响
      const payload: Record<string, unknown> = { ...body, project_key: key };
      const snapshot = statusRef.current?.owner_identity;
      if (
        payload.owner_identity === undefined
        && Array.isArray(snapshot)
        && snapshot.every((item) => typeof item === 'string')
      ) {
        payload.owner_identity = snapshot;
      }
      const { job: next } = await request<{ job: ToolJob<R> }>(path, {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      if (local !== identityRef.current || current !== sequence.current) return false;
      // 未绑定启动后 job 可能带 target project_key；同步 canonical 以免 accept 丢弃
      const jobKey = String(toolJobResult(next)?.project_key || key);
      if (jobKey && jobKey !== key) {
        const updated = { identity: local, key: jobKey };
        canonicalRef.current = updated;
        setCanonical(updated);
      }
      setJob(accept(next, jobKey || key));
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
    if (!job || !toolJobRunning(job) || cancelling || key === null || toolJobResult(job)?.project_key !== key) return;
    const local = identityRef.current;
    const current = sequence.current;
    setCancelling(true);
    try {
      await cancelJob(job.id);
    } catch (failure) {
      if (local !== identityRef.current || current !== sequence.current) return;
      setCancelling(false);
      setError(toolErrorText(failure));
    }
  }, [job, cancelling, currentKey]);

  const active = toolJobRunning(job);
  return {
    /** 仅全局项目身份；页面应用此值重置本地输入，勿用 toolIdentity */
    identity: projectIdentity,
    identityRef,
    sequence,
    keyReady,
    currentKey,
    status,
    job,
    result: toolJobResult(job),
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

export function toolStatusText<R extends ToolResultBase>(
  t: ReturnType<typeof useT>,
  view: { checking: boolean; active: boolean; cancelling: boolean; job: ToolJob<R> | null; result: R | null },
  idle: string,
): string {
  const { checking, active, cancelling, job, result } = view;
  if (checking) return t('tool_job_checking');
  if (active) return cancelling || job?.cancel_requested ? t('tool_job_cancelling') : (result?.message || t('tool_job_running'));
  if (job?.status === 'done') return result?.message || t('tool_job_done');
  // 写入已发生时优先展示业务消息，避免「失败/取消」掩盖 written/partial
  if (job?.status === 'failed') {
    if (result?.written || result?.partial) return result?.message || job.error || t('tool_job_failed');
    return job.error || result?.message || t('tool_job_failed');
  }
  if (job?.status === 'cancelled') {
    if (result?.written || result?.partial) return result?.message || t('tool_job_cancelled');
    return t('tool_job_cancelled');
  }
  return idle;
}
