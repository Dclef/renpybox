/** 运行时 EXE HOOK 翻译：对齐 Qt HookTranslatePage，走 /api/hook-translate。 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Form, Input, Progress, Select } from 'antd';

import * as api from '../api';
import {
  decodeLangChoice,
  encodeLangChoice,
  normalizePath,
  toolboxOwnerKey,
  toolboxStartGate,
  toolboxTargetKeyFromGamePath,
  toolboxTlLanguageName,
  TOOLBOX_LANG_OPTIONS,
  translationModeSummary,
  translationProgressView,
} from '../toolboxTranslateView.mjs';
import type { AppState } from '../useAppState';
import { Banner, SettingsGroup, Switch } from '../ui';

export function HookTranslatePage(props: { state: AppState }) {
  const { state } = props;
  const values = state.settings?.values ?? {};
  const projectPath = String(state.project?.renpy_project_path ?? '');
  const tlFolder = String(state.project?.renpy_tl_folder ?? '');
  // owner = 当前绑定项目；手动 gamePath 可为另一目录。
  const ownerKey = useMemo(
    () => toolboxOwnerKey(projectPath, toolboxTlLanguageName(tlFolder)),
    [projectPath, tlFolder],
  );
  const projectIdentity = useMemo(
    () => JSON.stringify([
      state.project?.renpy_project_path,
      state.project?.renpy_game_folder,
      state.project?.renpy_tl_folder,
    ]),
    [state.project?.renpy_game_folder, state.project?.renpy_project_path, state.project?.renpy_tl_folder],
  );
  const projectIdentityRef = useRef(projectIdentity);
  projectIdentityRef.current = projectIdentity;
  const ownerKeyRef = useRef(ownerKey);
  ownerKeyRef.current = ownerKey;
  const pollGeneration = useRef(0);
  // 受理后冻结本次 job 的 owner/target/request；status/stop 始终用冻结键，不被全局 B 带偏。
  const jobOwnerKeyRef = useRef('');
  const jobTargetKeyRef = useRef('');
  const jobRequestIdRef = useRef('');
  // start HTTP 在途时的发起上下文；迟到响应不得在外部项目上重挂旧任务。
  const pendingLaunchRef = useRef<{
    identity: string;
    generation: number;
    ownerKey: string;
    targetKey: string;
  } | null>(null);

  const [gamePath, setGamePath] = useState(projectPath);
  const [tlName, setTlName] = useState(() => toolboxTlLanguageName(tlFolder) || 'chinese');
  const [sourceChoice, setSourceChoice] = useState('EN');
  const [targetChoice, setTargetChoice] = useState(() => {
    const code = String(values.target_language ?? 'ZH');
    return encodeLangChoice(code, Boolean(values.traditional_chinese_enable));
  });
  const [backup, setBackup] = useState(false);
  const [incremental, setIncremental] = useState(true);
  const [generateEmpty, setGenerateEmpty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [assetsMissing, setAssetsMissing] = useState(false);
  const [jobMessage, setJobMessage] = useState('');
  const [extracting, setExtracting] = useState(false);
  const [activeRequestId, setActiveRequestId] = useState('');
  const [translationRunId, setTranslationRunId] = useState(0);
  const [ownsTranslation, setOwnsTranslation] = useState(false);
  const [frozenOwnerKey, setFrozenOwnerKey] = useState('');

  const engineBusy =
    state.translation.engine_status !== 'IDLE'
    || state.translation.stop_barrier
    || state.translation.single_tasks;
  const translating = state.translation.engine_status === 'TRANSLATING';
  const progress = translationProgressView(state.translation.progress);
  const pageTranslating = translating && ownsTranslation
    && (!activeRequestId || state.translation.request_id === activeRequestId);
  const statusOwnerKey = frozenOwnerKey || ownerKey;

  const gate = useMemo(
    () => toolboxStartGate({
      mode: 'hook',
      hasProject: Boolean(projectPath),
      linkOpen: state.link === 'open',
      engineBusy: engineBusy && !extracting,
      gamePath,
    }),
    [engineBusy, extracting, gamePath, projectPath, state.link],
  );

  useEffect(() => {
    setGamePath(projectPath);
  }, [projectPath]);

  useEffect(() => {
    const frozenOwner = jobOwnerKeyRef.current;
    const frozenTarget = jobTargetKeyRef.current;
    const pending = pendingLaunchRef.current;
    // 自身成功落到本次 target（或仍停在原 owner）时，不清空、不 bump；外部切到无关项目才丢弃。
    if (
      jobRequestIdRef.current
      && frozenOwner
      && (ownerKey === frozenTarget || ownerKey === frozenOwner)
    ) {
      return;
    }
    // start 响应尚未返回时，允许落到发起时的 owner / 手动 target（自有 A→B）。
    if (pending && (ownerKey === pending.targetKey || ownerKey === pending.ownerKey)) {
      return;
    }
    pollGeneration.current += 1;
    pendingLaunchRef.current = null;
    setOwnsTranslation(false);
    setActiveRequestId('');
    setTranslationRunId(0);
    setFrozenOwnerKey('');
    setExtracting(false);
    setBusy(false);
    jobOwnerKeyRef.current = '';
    jobTargetKeyRef.current = '';
    jobRequestIdRef.current = '';
  }, [ownerKey, projectIdentity]);

  useEffect(() => {
    if (!extracting) return;
    let cancelled = false;
    const pollIdentity = projectIdentity;
    const pollGen = pollGeneration.current;
    const pollOwner = jobOwnerKeyRef.current || statusOwnerKey;
    const pollRequest = jobRequestIdRef.current || activeRequestId;
    const tick = async () => {
      try {
        const status = await api.getHookTranslateStatus(
          pollOwner || undefined,
          pollRequest || undefined,
        );
        if (cancelled) return;
        // 外部无关项目切换会 bump generation；自身 A→B 保留 generation 与冻结 owner。
        if (pollGen !== pollGeneration.current) return;
        if (
          pollIdentity !== projectIdentityRef.current
          && ownerKey !== jobTargetKeyRef.current
          && ownerKey !== jobOwnerKeyRef.current
        ) {
          return;
        }
        const job = status.job;
        if (!job) return;
        const result = (job.result || {}) as Record<string, unknown>;
        setJobMessage(String(result.message || ''));
        if (job.status === 'done' || job.status === 'failed' || job.status === 'cancelled') {
          setExtracting(false);
          setBusy(false);
          if (job.status === 'failed') {
            setOwnsTranslation(false);
            state.pushToast('error', String(result.message || job.error || 'HOOK 抽取失败'));
          } else if (job.status === 'cancelled') {
            setOwnsTranslation(false);
            const partial = Boolean(result.partial || (Array.isArray(result.written_files) && result.written_files.length));
            state.pushToast('warning', partial ? '已取消 HOOK 抽取（已有部分产物）' : '已取消 HOOK 抽取');
          } else if (result.translation_started) {
            setOwnsTranslation(true);
            setTranslationRunId(Number(result.translation_run_id || 0));
            state.pushToast('success', '抽取完成，翻译已启动');
          } else {
            setOwnsTranslation(false);
            state.pushToast('warning', String(result.message || '抽取完成，但翻译未启动'));
          }
        }
      } catch {
        /* 轮询失败忽略，下一轮再试 */
      }
    };
    void tick();
    const id = window.setInterval(() => void tick(), 800);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [activeRequestId, extracting, ownerKey, projectIdentity, state, statusOwnerKey]);

  const pickGame = async () => {
    const file = await window.renpy?.pickFile?.({
      filters: [{ name: 'Executable', extensions: ['exe'] }],
    });
    if (file) {
      setGamePath(file);
      return;
    }
    const folder = await window.renpy?.pickFolder?.(gamePath || projectPath || undefined);
    if (folder) setGamePath(folder);
  };

  const start = async (preflightConfirmed = false) => {
    if (!gate.canStart || busy) return;
    const source = decodeLangChoice(sourceChoice);
    const target = decodeLangChoice(targetChoice);
    const launchGamePath = normalizePath(gamePath);
    const launchTlName = tlName || 'chinese';
    // targetKey 必须与后端 from_path→project_key 一致：.exe/game 目录先归一到项目根。
    const launch = {
      identity: projectIdentity,
      generation: pollGeneration.current,
      ownerKey,
      targetKey: toolboxTargetKeyFromGamePath(launchGamePath, launchTlName),
    };
    pendingLaunchRef.current = launch;
    setBusy(true);

    /** 迟到响应：仅原发起身份，或自有落到 launch/accepted target 时有效；外部 C 丢弃。 */
    const launchContextStillValid = (acceptedTarget = '') => {
      if (pendingLaunchRef.current !== launch) return false;
      const currentOwner = ownerKeyRef.current;
      const targetKey = acceptedTarget || launch.targetKey;
      return (
        projectIdentityRef.current === launch.identity
        || currentOwner === launch.ownerKey
        || currentOwner === launch.targetKey
        || (Boolean(targetKey) && currentOwner === targetKey)
      );
    };

    try {
      const response = await api.startHookTranslate({
        game_path: launchGamePath,
        tl_name: launchTlName,
        source_language: source.code,
        target_language: target.code,
        traditional_chinese_enable: target.traditional,
        renpy_backup_original: backup,
        renpy_hook_incremental: incremental,
        generate_empty: generateEmpty,
        preflight_confirmed: preflightConfirmed,
        project_key: launch.ownerKey || undefined,
      });
      const result = (response.job?.result || {}) as Record<string, unknown>;
      const acceptedTarget = String(result.target_key || launch.targetKey || '');
      if (!launchContextStillValid(acceptedTarget)) {
        // 外部已切走：不重挂旧任务，也不清掉新项目上可能已有的 busy。
        if (pendingLaunchRef.current === launch) pendingLaunchRef.current = null;
        return;
      }
      if (!response.accepted && response.reason === 'ASSETS_MISSING') {
        setAssetsMissing(true);
        setBusy(false);
        pendingLaunchRef.current = null;
        return;
      }
      if (!response.accepted) {
        state.pushToast('warning', response.detail || '无法启动 HOOK 翻译');
        setBusy(false);
        pendingLaunchRef.current = null;
        return;
      }
      const frozenOwner = String(result.owner_key || result.project_key || launch.ownerKey || '');
      const frozenTarget = String(result.target_key || launch.targetKey || '');
      const requestId = String(response.request_id || result.request_id || '');
      jobOwnerKeyRef.current = frozenOwner;
      jobTargetKeyRef.current = frozenTarget;
      jobRequestIdRef.current = requestId;
      pendingLaunchRef.current = null;
      setFrozenOwnerKey(frozenOwner);
      setAssetsMissing(false);
      setActiveRequestId(requestId);
      setOwnsTranslation(false);
      setExtracting(true);
      setJobMessage('正在准备运行时 HOOK 抽取…');
    } catch (error) {
      if (!launchContextStillValid()) {
        if (pendingLaunchRef.current === launch) pendingLaunchRef.current = null;
        return;
      }
      setBusy(false);
      pendingLaunchRef.current = null;
      state.pushToast('error', error instanceof Error ? error.message : String(error));
    }
  };

  const stop = async () => {
    const stopOwner = jobOwnerKeyRef.current || frozenOwnerKey || ownerKey;
    const stopRequest = jobRequestIdRef.current || activeRequestId;
    try {
      await api.stopHookTranslate({
        projectKey: stopOwner || undefined,
        requestId: stopRequest || undefined,
        runId: translationRunId || undefined,
      });
    } catch (error) {
      // 409 = owner guard：不得 fallback 全局 stop，避免 WS 状态陈旧时停掉他人任务。
      if (error instanceof api.ApiError && error.status === 409) {
        try {
          const status = await api.getHookTranslateStatus(
            stopOwner || undefined,
            stopRequest || undefined,
          );
          const job = status.job;
          const result = (job?.result || {}) as Record<string, unknown>;
          if (!job || job.status === 'done' || job.status === 'failed' || job.status === 'cancelled') {
            setExtracting(false);
            setBusy(false);
          }
          if (!result.translation_started) {
            setOwnsTranslation(false);
          }
          setJobMessage(String(result.message || error.message || ''));
        } catch {
          /* 重读失败仍以 409 文案为准 */
        }
        state.pushToast('warning', error.message || '当前没有可停止的本页任务');
        return;
      }
      if (!extracting) {
        state.pushToast('error', error instanceof Error ? error.message : String(error));
      }
    }
  };

  return (
    <div className="rb-page" data-rb-page="hook-translate">
      <Banner tone="info">{translationModeSummary('hook')}</Banner>
      <Banner tone="info">这里是 EXE 运行时 HOOK，不是 replace_text 补全。补全请用「补全翻译」页。</Banner>
      {!gate.canStart && !extracting ? <Banner tone="warning">{gate.hint}</Banner> : null}

      <SettingsGroup title="目标与语言" description="注入临时 hook 启动 EXE 抽取，成功后才启动统一翻译引擎。">
        <Form layout="vertical">
          <Form.Item label="游戏 EXE / 项目目录" style={{ marginBottom: 8 }}>
            <Input
              value={gamePath}
              disabled={busy || extracting || pageTranslating}
              onChange={(e) => setGamePath(e.target.value)}
              placeholder="优先 .exe，也可选项目根目录"
            />
          </Form.Item>
          {window.renpy?.pickFolder || window.renpy?.pickFile ? (
            <div className="rb-tool-actions" style={{ marginBottom: 12 }}>
              <Button disabled={busy || extracting || pageTranslating} onClick={() => void pickGame()}>
                选择 EXE / 目录
              </Button>
            </div>
          ) : null}
          <Form.Item label="语言目录名" style={{ marginBottom: 12 }}>
            <Input
              value={tlName}
              disabled={busy || extracting || pageTranslating}
              onChange={(e) => setTlName(e.target.value)}
            />
          </Form.Item>
          <Form.Item label="源语言" style={{ marginBottom: 12 }}>
            <Select
              value={sourceChoice}
              disabled={busy || extracting || pageTranslating}
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
              disabled={busy || extracting || pageTranslating}
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

      <SettingsGroup title="抽取选项">
        <Form layout="vertical">
          <Form.Item label="写回前备份 .bak" style={{ marginBottom: 12 }}>
            <Switch label="写回前备份 .bak" checked={backup} disabled={busy || extracting || pageTranslating} onChange={setBackup} />
          </Form.Item>
          <Form.Item label="增量补全" style={{ marginBottom: 12 }}>
            <Switch
              label="增量补全（仅追加缺失项）"
              checked={incremental}
              disabled={busy || extracting || pageTranslating}
              onChange={setIncremental}
            />
          </Form.Item>
          <Form.Item label="生成空白译文" style={{ marginBottom: 0 }}>
            <Switch
              label="抽取时生成空白译文"
              checked={generateEmpty}
              disabled={busy || extracting || pageTranslating}
              onChange={setGenerateEmpty}
            />
          </Form.Item>
        </Form>
      </SettingsGroup>

      <SettingsGroup title="开始 HOOK 翻译">
        <div className="rb-tool-actions">
          <Button
            type="primary"
            disabled={!gate.canStart || busy || extracting}
            loading={busy || extracting}
            onClick={() => void start(false)}
          >
            开始 HOOK 翻译
          </Button>
          <Button danger disabled={!extracting && !pageTranslating} onClick={() => void stop()}>
            停止
          </Button>
        </div>
        {extracting ? (
          <>
            <Progress percent={0} status="active" style={{ marginTop: 12 }} />
            <p className="card-description">{jobMessage || '运行时抽取中…'}</p>
          </>
        ) : null}
        {pageTranslating || (ownsTranslation && progress.label) ? (
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
