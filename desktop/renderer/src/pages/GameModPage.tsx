/** 游戏模组注入：对齐 Qt5 GameModPage，走 /api/game-mod。 */
import { useEffect, useMemo, useState } from 'react';
import { Button, Form, Input, Progress } from 'antd';

import {
  MOD_COPY,
  gameModStatusPath,
  gameModStatusTone,
  gamePathReady,
  modCopy,
  modStatusLabel,
} from '../gameModView.mjs';
import { useT } from '../i18n';
import type { AppState } from '../useAppState';
import { Banner, Dialog, SettingsGroup } from '../ui';
import {
  toolStatusText,
  useProjectToolJob,
  type ToolJob,
  type ToolResultBase,
} from './projectToolJob';

interface ModResult extends ToolResultBase {
  key?: string;
  mods?: Record<string, boolean>;
  legacy_dumuqiao?: boolean;
  game_dir?: string;
  success?: boolean;
}

interface ModStatus {
  project_key?: string;
  game_dir?: string;
  mods?: Record<string, boolean>;
  legacy_dumuqiao?: boolean;
  legacy_files?: string[];
  owner_identity?: string[];
  error?: string;
  job?: ToolJob<ModResult> | null;
}

const KINDS = ['game_mod_install', 'game_mod_uninstall', 'game_mod_cleanup_legacy'] as const;

export function GameModPage(props: { state: AppState }) {
  const { state } = props;
  const i18n = useT();
  const uiLang = state.bootLanguage === 'EN' ? 'EN' : 'ZH';
  const t = (table: { ZH: string; EN: string }) => modCopy(table, uiLang);
  const [gamePath, setGamePath] = useState('');
  const [confirmInstall, setConfirmInstall] = useState<{ key: string; action: 'install' | 'uninstall' } | null>(null);
  const [confirmLegacy, setConfirmLegacy] = useState(false);

  const statusPath = useMemo(() => gameModStatusPath(gamePath), [gamePath]);
  const suite = useProjectToolJob<ModResult, ModStatus>(state, statusPath, KINDS);
  const { status, keyReady, job, result, active, error, cancelling, busy } = suite;
  const engineBusy = state.translation.engine_status !== 'IDLE' || state.translation.stop_barrier || state.translation.single_tasks;
  const blocked = busy || engineBusy || !keyReady || state.link !== 'open' || !gamePathReady(gamePath);
  const statusText = toolStatusText(i18n, suite, t(MOD_COPY.title));
  const statusTone = gameModStatusTone({
    active,
    checking: suite.checking,
    job,
    result,
  });
  const mods = status?.mods || result?.mods || {
    gallery_unlock: false,
    urm: false,
    simple_modifier: false,
  };
  const legacy = Boolean(status?.legacy_dumuqiao ?? result?.legacy_dumuqiao);

  useEffect(() => {
    setGamePath('');
    setConfirmInstall(null);
    setConfirmLegacy(false);
  }, [suite.identity]);

  async function pickGame() {
    const context = suite.identityRef.current;
    const next = await window.renpy?.pickFolder?.();
    if (next && context === suite.identityRef.current) setGamePath(next);
  }

  function runMod(action: 'install' | 'uninstall', key: string) {
    void suite.submit(`/api/game-mod/${action}`, {
      game_path: gamePath.trim(),
      key,
      confirm: true,
    });
  }

  return (
    <div className="rb-asset-page rb-page-scroll" data-rb-page="game-mod">
      <Banner tone="info">{t(MOD_COPY.intro)}</Banner>
      {error ? <Banner tone="error">{error}</Banner> : null}
      {status?.error ? <Banner tone="error">{status.error}</Banner> : null}
      <Banner tone={statusTone}>{statusText}</Banner>
      {active ? <Progress percent={Math.min(100, Math.round(((job?.done || 0) / Math.max(job?.total || 1, 1)) * 100))} /> : null}
      {active ? (
        <div className="rb-tool-actions">
          <Button onClick={() => void suite.cancel()} disabled={cancelling || Boolean(job?.cancel_requested)}>
            {i18n('tool_job_cancel')}
          </Button>
        </div>
      ) : null}

      <SettingsGroup title={t(MOD_COPY.gameDir)} description={t(MOD_COPY.gameHint)}>
        <Form.Item style={{ marginBottom: 12 }}>
          <Input.Group compact style={{ display: 'flex' }}>
            <Input
              value={gamePath}
              onChange={(event) => setGamePath(event.target.value)}
              style={{ flex: 1 }}
              disabled={busy || cancelling || engineBusy || state.link !== 'open'}
              placeholder={t(MOD_COPY.gameHint)}
            />
            <Button
              disabled={busy || cancelling || engineBusy || state.link !== 'open'}
              onClick={() => void pickGame()}
            >
              {t(MOD_COPY.browse)}
            </Button>
          </Input.Group>
        </Form.Item>
        {!gamePathReady(gamePath) ? (
          <p className="muted">
            {`${t(MOD_COPY.galleryTitle)}：${t(MOD_COPY.unknown)}`}
          </p>
        ) : (
          <>
            <p className="muted">{`${t(MOD_COPY.galleryTitle)}：${modStatusLabel(Boolean(mods.gallery_unlock), uiLang)}`}</p>
            <p className="muted">{`${t(MOD_COPY.urmTitle)}：${modStatusLabel(Boolean(mods.urm), uiLang)}`}</p>
            <p className="muted">{`${t(MOD_COPY.simpleTitle)}：${modStatusLabel(Boolean(mods.simple_modifier), uiLang)}`}</p>
          </>
        )}
        {legacy ? (
          <>
            <Banner tone="warning">{t(MOD_COPY.legacyWarn)}</Banner>
            <Button danger disabled={blocked} onClick={() => setConfirmLegacy(true)}>
              {t(MOD_COPY.legacyClean)}
            </Button>
          </>
        ) : null}
      </SettingsGroup>

      <SettingsGroup title={t(MOD_COPY.galleryTitle)} description={t(MOD_COPY.galleryDesc)}>
        <div className="rb-tool-actions">
          <Button type="primary" disabled={blocked} onClick={() => setConfirmInstall({ key: 'gallery_unlock', action: 'install' })}>
            {t(MOD_COPY.install)}
          </Button>
          <Button disabled={blocked} onClick={() => setConfirmInstall({ key: 'gallery_unlock', action: 'uninstall' })}>
            {t(MOD_COPY.uninstall)}
          </Button>
        </div>
      </SettingsGroup>

      <SettingsGroup title={t(MOD_COPY.urmTitle)} description={t(MOD_COPY.urmDesc)}>
        <div className="rb-tool-actions">
          <Button type="primary" disabled={blocked} onClick={() => setConfirmInstall({ key: 'urm', action: 'install' })}>
            {t(MOD_COPY.install)}
          </Button>
          <Button disabled={blocked} onClick={() => setConfirmInstall({ key: 'urm', action: 'uninstall' })}>
            {t(MOD_COPY.uninstall)}
          </Button>
        </div>
      </SettingsGroup>

      <SettingsGroup title={t(MOD_COPY.simpleTitle)} description={t(MOD_COPY.simpleDesc)}>
        <div className="rb-tool-actions">
          <Button type="primary" disabled={blocked} onClick={() => setConfirmInstall({ key: 'simple_modifier', action: 'install' })}>
            {t(MOD_COPY.install)}
          </Button>
          <Button disabled={blocked} onClick={() => setConfirmInstall({ key: 'simple_modifier', action: 'uninstall' })}>
            {t(MOD_COPY.uninstall)}
          </Button>
        </div>
      </SettingsGroup>

      {confirmInstall ? (
        <Dialog
          title={confirmInstall.action === 'install' ? t(MOD_COPY.install) : t(MOD_COPY.uninstall)}
          onCancel={() => setConfirmInstall(null)}
          onConfirm={() => {
            runMod(confirmInstall.action, confirmInstall.key);
            setConfirmInstall(null);
          }}
        >
          {confirmInstall.action === 'install' ? t(MOD_COPY.installConfirm) : t(MOD_COPY.uninstallConfirm)}
        </Dialog>
      ) : null}

      {confirmLegacy ? (
        <Dialog
          title={t(MOD_COPY.legacyClean)}
          onCancel={() => setConfirmLegacy(false)}
          onConfirm={() => {
            setConfirmLegacy(false);
            void suite.submit('/api/game-mod/cleanup-legacy', {
              game_path: gamePath.trim(),
              confirm: true,
            });
          }}
        >
          {t(MOD_COPY.legacyConfirm)}
        </Dialog>
      ) : null}
    </div>
  );
}

export default GameModPage;
