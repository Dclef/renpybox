/** 补全翻译（replace_text）：对齐 Qt HookSupplementPage，经 /api/translation/start（mode=supplement）。 */

import { useEffect, useMemo, useState } from 'react';
import { Button, Form, Input, Progress, Select } from 'antd';

import {
  decodeLangChoice,
  encodeLangChoice,
  normalizePath,
  toolboxOwnerKey,
  toolboxStartGate,
  toolboxTlLanguageName,
  TOOLBOX_LANG_OPTIONS,
  translationModeSummary,
  translationProgressView,
} from '../toolboxTranslateView.mjs';
import type { AppState } from '../useAppState';
import { Banner, SettingsGroup } from '../ui';

export function HookSupplementPage(props: { state: AppState }) {
  const { state } = props;
  const values = state.settings?.values ?? {};
  const projectPath = String(state.project?.renpy_project_path ?? '');
  const gameFolder = String(state.project?.renpy_game_folder ?? '');
  const boundTl = String(state.project?.renpy_tl_folder ?? values.renpy_tl_folder ?? '');
  const ownerKey = useMemo(
    () => toolboxOwnerKey(projectPath || gameFolder, toolboxTlLanguageName(boundTl)),
    [boundTl, gameFolder, projectPath],
  );

  const [gamePath, setGamePath] = useState(projectPath || gameFolder);
  const [tlName, setTlName] = useState(() => toolboxTlLanguageName(boundTl) || 'chinese');
  // 同项目自定义 TL：保留绑定路径的父目录，避免 candidate 永远 from_path 丢掉。
  const [tlParent, setTlParent] = useState(() => {
    const tl = normalizePath(boundTl);
    if (!tl) return '';
    const sep = tl.lastIndexOf('\\');
    return sep >= 0 ? tl.slice(0, sep) : '';
  });
  const [sourceChoice, setSourceChoice] = useState('EN');
  const [targetChoice, setTargetChoice] = useState(() => {
    const code = String(values.target_language ?? 'ZH');
    return encodeLangChoice(code, Boolean(values.traditional_chinese_enable));
  });
  const [busy, setBusy] = useState(false);
  const [assetsMissing, setAssetsMissing] = useState(false);

  useEffect(() => {
    setGamePath(projectPath || gameFolder);
    const tl = normalizePath(boundTl);
    setTlName(toolboxTlLanguageName(boundTl) || 'chinese');
    if (tl) {
      const sep = tl.lastIndexOf('\\');
      setTlParent(sep >= 0 ? tl.slice(0, sep) : '');
    }
  }, [boundTl, gameFolder, projectPath]);

  const engineBusy =
    state.translation.engine_status !== 'IDLE'
    || state.translation.stop_barrier
    || state.translation.single_tasks;
  const translating = state.translation.engine_status === 'TRANSLATING';
  const progress = translationProgressView(state.translation.progress);

  const gate = useMemo(
    () => toolboxStartGate({
      mode: 'supplement',
      hasProject: Boolean(projectPath),
      linkOpen: state.link === 'open',
      engineBusy,
      gamePath,
    }),
    [engineBusy, gamePath, projectPath, state.link],
  );

  const pickProject = async () => {
    const path = await window.renpy?.pickFolder?.(gamePath || projectPath || undefined);
    if (path) setGamePath(path);
  };

  const pickTlParent = async () => {
    const path = await window.renpy?.pickFolder?.(tlParent || boundTl || projectPath || undefined);
    if (path) setTlParent(path);
  };

  const start = async (preflightConfirmed = false) => {
    if (!gate.canStart || busy) return;
    const source = decodeLangChoice(sourceChoice);
    const target = decodeLangChoice(targetChoice);
    setBusy(true);
    try {
      const response = await state.startTranslation('UNTRANSLATED', preflightConfirmed, {
        mode: 'supplement',
        project_key: ownerKey || undefined,
        game_path: normalizePath(gamePath),
        tl_name: tlName || 'chinese',
        tl_parent: normalizePath(tlParent) || undefined,
        source_language: source.code,
        target_language: target.code,
        traditional_chinese_enable: target.traditional,
      });
      if (!response.accepted && response.reason === 'ASSETS_MISSING') {
        setAssetsMissing(true);
      } else if (response.accepted) {
        setAssetsMissing(false);
        state.pushToast('success', '已提交补全翻译');
      }
    } catch (error) {
      state.pushToast('error', error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };

  const hintOut = normalizePath(tlParent)
    ? `${normalizePath(tlParent)}\\${tlName || 'chinese'}\\replace_text_auto.rpy`
    : gamePath
      ? `${normalizePath(gamePath)}\\game\\tl\\${tlName || 'chinese'}\\replace_text_auto.rpy`
      : '';

  return (
    <div className="rb-page" data-rb-page="hook-supplement">
      <Banner tone="info">{translationModeSummary('supplement')}</Banner>
      <Banner tone="info">本页只做 replace_text 补全，不是 EXE 运行时 HOOK。</Banner>
      {!gate.canStart ? <Banner tone="warning">{gate.hint}</Banner> : null}
      {hintOut ? <Banner tone="info">{`补全输出：${hintOut}`}</Banner> : null}

      <SettingsGroup title="项目与语言">
        <Form layout="horizontal">
          <Form.Item label="项目目录" style={{ marginBottom: 8 }}>
            <Input
              value={gamePath}
              disabled={busy || engineBusy}
              onChange={(e) => setGamePath(e.target.value)}
              placeholder="选择包含 game 目录的项目根目录"
            />
          </Form.Item>
          {window.renpy?.pickFolder ? (
            <div className="rb-tool-actions" style={{ marginBottom: 12 }}>
              <Button disabled={busy || engineBusy} onClick={() => void pickProject()}>选择项目</Button>
            </div>
          ) : null}
          <Form.Item label="自定义 tl 父目录（可选）" style={{ marginBottom: 8 }}>
            <Input
              value={tlParent}
              disabled={busy || engineBusy}
              onChange={(e) => setTlParent(e.target.value)}
              placeholder="默认 game/tl；同项目自定义 TL 可保留"
            />
          </Form.Item>
          {window.renpy?.pickFolder ? (
            <div className="rb-tool-actions" style={{ marginBottom: 12 }}>
              <Button disabled={busy || engineBusy} onClick={() => void pickTlParent()}>选择 tl 父目录</Button>
            </div>
          ) : null}
          <Form.Item label="语言目录名" style={{ marginBottom: 12 }}>
            <Input
              value={tlName}
              disabled={busy || engineBusy}
              onChange={(e) => setTlName(e.target.value)}
            />
          </Form.Item>
          <Form.Item label="源语言" style={{ marginBottom: 12 }}>
            <Select
              value={sourceChoice}
              disabled={busy || engineBusy}
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
              disabled={busy || engineBusy}
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

      <SettingsGroup title="开始补全翻译">
        <div className="rb-tool-actions">
          <Button type="primary" disabled={!gate.canStart || busy} loading={busy} onClick={() => void start(false)}>
            开始补全翻译
          </Button>
          <Button danger disabled={!translating || busy} onClick={() => void state.stopTranslation()}>
            停止
          </Button>
        </div>
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
