/** 直接翻译 tl/*.rpy：对齐 Qt DirectRpyTranslatePage，经 /api/translation/start（mode=direct）。 */

import { useMemo, useState } from 'react';
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
import type { PageKey } from '../nav';
import type { AppState } from '../useAppState';
import { Banner, SettingsGroup, Switch } from '../ui';
import * as api from '../api';

export function DirectRpyTranslatePage(props: {
  state: AppState;
  onNavigate?: (page: PageKey) => void;
}) {
  const { state, onNavigate } = props;
  const values = state.settings?.values ?? {};
  const projectPath = String(state.project?.renpy_project_path ?? '');
  const boundTl = String(state.project?.renpy_tl_folder ?? values.renpy_tl_folder ?? '');
  const ownerKey = useMemo(
    () => toolboxOwnerKey(projectPath, toolboxTlLanguageName(boundTl)),
    [boundTl, projectPath],
  );

  // Qt 初值：游戏/显式 TL 为空，语言名 chinese；不强制绑定项目。
  const [gamePath, setGamePath] = useState('');
  const [tlParent, setTlParent] = useState('');
  const [tlName, setTlName] = useState('chinese');
  const [langChoice, setLangChoice] = useState(() => encodeLangChoice('ZH', false));
  const [backup, setBackup] = useState(false);
  const [autoWrite, setAutoWrite] = useState(true);
  const [busy, setBusy] = useState(false);
  const [assetsMissing, setAssetsMissing] = useState(false);

  const engineBusy =
    state.translation.engine_status !== 'IDLE'
    || state.translation.stop_barrier
    || state.translation.single_tasks;
  const translating = state.translation.engine_status === 'TRANSLATING';
  const progress = translationProgressView(state.translation.progress);

  const explicitTlParent = normalizePath(tlParent);
  const explicitTlName = (tlName || '').trim() || 'chinese';
  const explicitTlDir = explicitTlParent
    ? `${explicitTlParent.replace(/[/\\]+$/, '')}\\${explicitTlName}`
    : '';

  const gate = useMemo(
    () => toolboxStartGate({
      mode: 'direct',
      hasProject: Boolean(projectPath),
      linkOpen: state.link === 'open',
      engineBusy,
      tlDir: boundTl,
      gamePath,
      tlParent,
      tlName,
    }),
    [boundTl, engineBusy, gamePath, projectPath, state.link, tlParent, tlName],
  );

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

  const pickTlParent = async () => {
    const path = await window.renpy?.pickFolder?.(tlParent || boundTl || projectPath || undefined);
    if (path) setTlParent(path);
  };

  const start = async (preflightConfirmed = false) => {
    if (!gate.canStart || busy) return;
    if (explicitTlParent && !explicitTlName) {
      state.pushToast('warning', '已填写 tl 父目录时须同时指定语言目录名');
      return;
    }
    const { code, traditional } = decodeLangChoice(langChoice);
    setBusy(true);
    try {
      const payload: Record<string, unknown> = {
        mode: 'direct',
        project_key: ownerKey || undefined,
        target_language: code,
        traditional_chinese_enable: traditional,
        renpy_backup_original: backup,
        auto_write_back: autoWrite,
      };
      if (explicitTlParent) {
        payload.tl_parent = explicitTlParent;
        payload.tl_name = explicitTlName;
      } else {
        payload.game_path = gamePath || undefined;
        payload.tl_name = explicitTlName;
      }
      const response = await state.startTranslation('UNTRANSLATED', preflightConfirmed, {
        ...payload,
      } as Parameters<AppState['startTranslation']>[2]);
      if (!response.accepted && response.reason === 'ASSETS_MISSING') {
        setAssetsMissing(true);
      } else if (response.accepted) {
        setAssetsMissing(false);
        state.pushToast('success', '已提交直接翻译');
      }
    } catch (error) {
      state.pushToast('error', error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };

  const reinject = async () => {
    setBusy(true);
    try {
      if (explicitTlParent) {
        await api.reinjectTranslation({
          tl_parent: explicitTlParent,
          tl_name: explicitTlName,
          project_key: ownerKey || undefined,
        });
      } else if (normalizePath(gamePath)) {
        await api.reinjectTranslation({
          game_path: normalizePath(gamePath),
          tl_name: explicitTlName,
          project_key: ownerKey || undefined,
        });
      } else if (normalizePath(boundTl)) {
        await api.reinjectTranslation({
          output_folder: normalizePath(boundTl),
          project_key: ownerKey || undefined,
        });
      } else {
        state.pushToast('warning', '请先指定 tl 目录');
        return;
      }
      state.pushToast('success', '已请求手动写回缓存译文');
    } catch (error) {
      state.pushToast('error', error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rb-page" data-rb-page="direct-rpy-translate">
      <Banner tone="info">{translationModeSummary('direct')}</Banner>
      {!gate.canStart ? <Banner tone="warning">{gate.hint}</Banner> : null}
      {explicitTlParent ? (
        <Banner tone="info">{`显式 TL 目录：${explicitTlDir}（tl 父目录 + 语言名，不再走 game/tl 自动查找）`}</Banner>
      ) : null}

      <SettingsGroup title="路径与语言" description="可直接选游戏/EXE，或显式指定 tl 父目录 + 语言文件夹名；不必事先绑定项目。">
        <Form layout="vertical">
          <Form.Item label="游戏 EXE / 项目目录" style={{ marginBottom: 8 }}>
            <Input
              value={gamePath}
              disabled={busy || engineBusy}
              onChange={(e) => setGamePath(e.target.value)}
              placeholder="选择 .exe 或项目根目录"
            />
          </Form.Item>
          {window.renpy?.pickFolder || window.renpy?.pickFile ? (
            <div className="rb-tool-actions" style={{ marginBottom: 12 }}>
              <Button disabled={busy || engineBusy} onClick={() => void pickGame()}>选择游戏</Button>
            </div>
          ) : null}
          <Form.Item label="tl 父目录（可选）" style={{ marginBottom: 8 }}>
            <Input
              value={tlParent}
              disabled={busy || engineBusy}
              onChange={(e) => setTlParent(e.target.value)}
              placeholder="默认使用 game/tl"
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
              placeholder="chinese"
            />
          </Form.Item>
          <Form.Item label="目标语言" style={{ marginBottom: 0 }}>
            <Select
              value={langChoice}
              disabled={busy || engineBusy}
              options={TOOLBOX_LANG_OPTIONS.map((item) => ({
                value: encodeLangChoice(item.value, item.traditional),
                label: item.label,
              }))}
              onChange={setLangChoice}
              style={{ width: '100%' }}
            />
          </Form.Item>
        </Form>
      </SettingsGroup>

      <SettingsGroup title="写入选项">
        <Form layout="vertical">
          <Form.Item label="写入前备份 .bak" style={{ marginBottom: 12 }}>
            <Switch label="写入前备份 .bak" checked={backup} disabled={busy || engineBusy} onChange={setBackup} />
          </Form.Item>
          <Form.Item label="自动写回文件" style={{ marginBottom: 0 }}>
            <Switch label="自动写回文件" checked={autoWrite} disabled={busy || engineBusy} onChange={setAutoWrite} />
          </Form.Item>
        </Form>
      </SettingsGroup>

      <SettingsGroup title="开始翻译">
        <div className="rb-tool-actions">
          <Button type="primary" disabled={!gate.canStart || busy} loading={busy} onClick={() => void start(false)}>
            开始翻译
          </Button>
          <Button danger disabled={!translating || busy} onClick={() => void state.stopTranslation()}>
            停止
          </Button>
          <Button disabled={busy || engineBusy} onClick={() => void reinject()}>
            手动写回
          </Button>
          {onNavigate ? (
            <Button disabled={busy} onClick={() => onNavigate('rpy-extraction')}>
              RPY 抽取设置
            </Button>
          ) : null}
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
