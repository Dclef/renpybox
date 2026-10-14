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
import { useT } from '../i18n';
import type { AppState } from '../useAppState';
import { Banner, SettingsGroup } from '../ui';

export function HookSupplementPage(props: { state: AppState }) {
  const { state } = props;
  const t = useT();
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
        state.pushToast('success', t('hook_supplement_submitted'));
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
      <Banner tone="info">{t('hook_supplement_note')}</Banner>
      {!gate.canStart ? <Banner tone="warning">{gate.hint}</Banner> : null}
      {hintOut ? <Banner tone="info">{t('hook_supplement_output_hint').split('{path}').join(hintOut)}</Banner> : null}

      <SettingsGroup title={t('hook_supplement_group_title')}>
        <Form layout="horizontal">
          <Form.Item label={t('hook_supplement_project_dir')} style={{ marginBottom: 8 }}>
            <Input
              value={gamePath}
              disabled={busy || engineBusy}
              onChange={(e) => setGamePath(e.target.value)}
              placeholder={t('hook_supplement_project_dir_placeholder')}
            />
          </Form.Item>
          {window.renpy?.pickFolder ? (
            <div className="rb-tool-actions" style={{ marginBottom: 12 }}>
              <Button disabled={busy || engineBusy} onClick={() => void pickProject()}>{t('hook_supplement_select_project')}</Button>
            </div>
          ) : null}
          <Form.Item label={t('hook_supplement_tl_parent_label')} style={{ marginBottom: 8 }}>
            <Input
              value={tlParent}
              disabled={busy || engineBusy}
              onChange={(e) => setTlParent(e.target.value)}
              placeholder={t('hook_supplement_tl_parent_placeholder')}
            />
          </Form.Item>
          {window.renpy?.pickFolder ? (
            <div className="rb-tool-actions" style={{ marginBottom: 12 }}>
              <Button disabled={busy || engineBusy} onClick={() => void pickTlParent()}>{t('hook_supplement_select_tl_parent')}</Button>
            </div>
          ) : null}
          <Form.Item label={t('asset_language')} style={{ marginBottom: 12 }}>
            <Input
              value={tlName}
              disabled={busy || engineBusy}
              onChange={(e) => setTlName(e.target.value)}
            />
          </Form.Item>
          <Form.Item label={t('hook_supplement_source_language')} style={{ marginBottom: 12 }}>
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
          <Form.Item label={t('font_inject_language')} style={{ marginBottom: 0 }}>
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

      <SettingsGroup title={t('hook_supplement_group_start')}>
        <div className="rb-tool-actions">
          <Button type="primary" disabled={!gate.canStart || busy} loading={busy} onClick={() => void start(false)}>
            {t('hook_supplement_start')}</Button>
          <Button danger disabled={!translating || busy} onClick={() => void state.stopTranslation()}>
            {t('hook_supplement_stop')}</Button>
        </div>
        {(translating || progress.label) ? (
          <>
            <Progress percent={progress.percent} style={{ marginTop: 12 }} />
            <p className="card-description">{progress.label || t('hook_supplement_translating')}</p>
          </>
        ) : null}
      </SettingsGroup>

      {assetsMissing ? (
        <Banner tone="warning">
          {t('hook_supplement_assets_missing')}<Button type="link" onClick={() => void start(true)}>{t('hook_supplement_continue_anyway')}</Button>
        </Banner>
      ) : null}
    </div>
  );
}
