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
  translationProgressView,
} from '../toolboxTranslateView.mjs';
import type { PageKey } from '../nav';
import type { AppState } from '../useAppState';
import { Banner, SettingsGroup, Switch } from '../ui';
import { useT } from '../i18n';
import * as api from '../api';

export function DirectRpyTranslatePage(props: {
  state: AppState;
  onNavigate?: (page: PageKey) => void;
}) {
  const { state, onNavigate } = props;
  const t = useT();
  const values = state.settings?.values ?? {};
  const projectPath = String(state.project?.renpy_project_path ?? '');
  const boundTl = String(state.project?.renpy_tl_folder ?? values.renpy_tl_folder ?? '');
  const ownerKey = useMemo(
    () => toolboxOwnerKey(projectPath, toolboxTlLanguageName(boundTl)),
    [boundTl, projectPath],
  );

  // Qt 初值：游戏/显式 TL 为空，语言名 chinese；不强制绑定项目。绑定工程时把工程路径填好，用户仍可改成别的目录。
  const defaultTlParent = useMemo(() => {
    const tl = normalizePath(boundTl);
    const cut = tl.lastIndexOf('\\');
    return cut > 2 ? tl.slice(0, cut) : '';
  }, [boundTl]);

  const [gamePath, setGamePath] = useState(projectPath);
  const [tlParent, setTlParent] = useState(defaultTlParent);
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
      state.pushToast('warning', t('direct_rpy_tl_parent_required_pair'));
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
        state.pushToast('success', t('direct_rpy_submitted'));
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
        state.pushToast('warning', t('direct_rpy_need_tl'));
        return;
      }
      state.pushToast('success', t('direct_rpy_cache_writeback_requested'));
    } catch (error) {
      state.pushToast('error', error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rb-page" data-rb-page="direct-rpy-translate">
      <Banner tone="info">{t('direct_rpy_note')}</Banner>
      {!gate.canStart ? <Banner tone="warning">{gate.hint}</Banner> : null}
      {explicitTlParent ? (
        <Banner tone="info">{`显式 TL 目录：${explicitTlDir}（tl 父目录 + 语言名，不再走 game/tl 自动查找）`}</Banner>
      ) : null}

      <SettingsGroup title={t('direct_rpy_paths_description')} description={t('direct_rpy_paths_description')}>
        <Form layout="horizontal" labelCol={{ flex: '160px' }} wrapperCol={{ flex: 1 }} labelAlign="left" colon={false}>
          <Form.Item label={t('direct_rpy_game_label')} style={{ marginBottom: 12 }}>
            <div className="rb-direct-path">
            <Input
              aria-label={t('direct_rpy_game_label')}
              value={gamePath}
              disabled={busy || engineBusy}
              onChange={(e) => setGamePath(e.target.value)}
              placeholder={t('direct_rpy_game_placeholder')}
            />
            {window.renpy?.pickFolder || window.renpy?.pickFile ? (
              <Button disabled={busy || engineBusy} onClick={() => void pickGame()}>{t('direct_rpy_pick_game')}</Button>
            ) : null}
            </div>
          </Form.Item>
          <Form.Item label={t('direct_rpy_tl_parent_optional')} style={{ marginBottom: 12 }}>
            <div className="rb-direct-path">
            <Input
              aria-label={t('direct_rpy_tl_parent_label')}
              value={tlParent}
              disabled={busy || engineBusy}
              onChange={(e) => setTlParent(e.target.value)}
              placeholder={t('direct_rpy_tl_parent_placeholder')}
            />
            {window.renpy?.pickFolder ? (
              <Button disabled={busy || engineBusy} onClick={() => void pickTlParent()}>{t('archive_pick_folder')}</Button>
            ) : null}
            </div>
          </Form.Item>
          <Form.Item label={t('asset_source_tl_label')} style={{ marginBottom: 12 }}>
            <Input
              aria-label={t('asset_source_tl_label')}
              value={tlName}
              disabled={busy || engineBusy}
              onChange={(e) => setTlName(e.target.value)}
              placeholder="chinese"
            />
          </Form.Item>
          <Form.Item label={t('font_inject_language')} style={{ marginBottom: 0 }}>
            <Select
              aria-label={t('font_inject_language')}
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

      <SettingsGroup title={t('direct_rpy_write_options')}>
        <div className="rb-direct-options">
          <label>
            <span>{t('direct_rpy_backup_label')}</span>
            <Switch label={t('direct_rpy_backup_label')} checked={backup} disabled={busy || engineBusy} onChange={setBackup} />
          </label>
          <label>
            <span>{t('direct_rpy_write_back')}</span>
            <Switch label={t('direct_rpy_write_back')} checked={autoWrite} disabled={busy || engineBusy} onChange={setAutoWrite} />
          </label>
        </div>
      </SettingsGroup>

      <div className="rb-direct-footer">
        <div className="rb-tool-actions">
          <Button type="primary" disabled={!gate.canStart || busy} loading={busy} onClick={() => void start(false)}>
            {t('direct_rpy_start')}</Button>
          <Button danger disabled={!translating || busy} onClick={() => void state.stopTranslation()}>
            {t('direct_rpy_stop')}</Button>
          <Button disabled={busy || engineBusy} onClick={() => void reinject()}>
            {t('direct_rpy_manual_write_back')}</Button>
          {onNavigate ? (
            <Button disabled={busy} onClick={() => onNavigate('rpy-extraction')}>
              {t('rpy_extraction_settings')}</Button>
          ) : null}
        </div>
        {(translating || progress.label) ? (
          <>
            <Progress percent={progress.percent} style={{ marginTop: 12 }} />
            <p className="card-description">{progress.label || t('hook_supplement_translating')}</p>
          </>
        ) : null}
      </div>

      {assetsMissing ? (
        <Banner tone="warning">
          {t('hook_supplement_assets_missing')}<Button type="link" onClick={() => void start(true)}>{t('hook_supplement_continue_anyway')}</Button>
        </Banner>
      ) : null}
    </div>
  );
}
