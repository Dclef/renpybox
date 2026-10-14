/** 终极结构导出 + Emoji 助手：复用 /api/asset-suite。 */
import { useCallback, useEffect, useState } from 'react';
import { Button, Checkbox, Form, Input, Progress, Select } from 'antd';

import { useT } from '../i18n';
import type { AppState } from '../useAppState';
import { Banner, Dialog, SettingsGroup } from '../ui';
import { AssetResultNotes, assetStatusText, useAssetSuiteJob, type AssetResultBase } from './assetSuiteJob';

interface AssetResult extends AssetResultBase {
  path?: string;
  output_dir?: string;
  names_count?: number;
  others_count?: number;
  replace_count?: number;
  deleted_count?: number;
  emoji_replacements?: number;
  emoji_dir?: string;
  target_dir?: string;
  success_files?: number;
  failed_files?: number;
  changed_count?: number;
}

const KINDS = ['asset_structure', 'asset_emoji'] as const;

/** 仅用于确认框展示：与 Qt _resolve_project_root 一致，exe/py 取父目录、game 目录上提一级，再拼 translate_output。 */
function deriveStructureOutput(raw: string): string {
  const parts = raw.trim().replace(/[\\/]+$/, '').split(/[\\/]/);
  if (/\.(exe|py)$/i.test(parts.at(-1) ?? '')) parts.pop();
  if ((parts.at(-1) ?? '').toLowerCase() === 'game') parts.pop();
  if (!parts.filter(Boolean).length) return '';
  const sep = raw.includes('\\') ? '\\' : '/';
  return [...parts, 'translate_output'].join(sep);
}

export function MaSuitePage(props: { state: AppState }) {
  const { state } = props;
  const t = useT();
  const projectRoot = String(state.project?.renpy_project_path ?? '');
  const gameFolder = String(state.project?.renpy_game_folder ?? '');
  const [path, setPath] = useState(gameFolder || projectRoot);
  const [language, setLanguage] = useState('chinese');
  const [mode, setMode] = useState<'1' | '2' | '3'>('1');
  const [useOfficial, setUseOfficial] = useState(false);
  const [exePath, setExePath] = useState('');
  const [genEmoji, setGenEmoji] = useState(false);
  const [emojiDir, setEmojiDir] = useState('');
  const [confirm, setConfirm] = useState<'structure' | 'emoji-prepare' | 'emoji-restore' | null>(null);
  const suite = useAssetSuiteJob<AssetResult>(state, KINDS);
  const { identity, identityRef, keyReady, job, result, active, error, cancelling, busy } = suite;
  const engineBusy = state.translation.engine_status !== 'IDLE' || state.translation.stop_barrier || state.translation.single_tasks;
  const writeBlocked = busy || engineBusy || !keyReady || state.link !== 'open';

  useEffect(() => {
    setPath(gameFolder || projectRoot);
  }, [gameFolder, projectRoot]);

  useEffect(() => {
    setConfirm(null);
  }, [identity]);

  const pickDir = useCallback(async (setter: (value: string) => void, current: string) => {
    const context = identityRef.current;
    const next = await window.renpy?.pickFolder?.(current || undefined);
    if (next && context === identityRef.current) setter(next);
  }, [identityRef]);

  const pickFile = useCallback(async (setter: (value: string) => void) => {
    const context = identityRef.current;
    const next = await window.renpy?.pickFile?.({ filters: [{ name: 'Executable', extensions: ['exe', 'py'] }] });
    if (next && context === identityRef.current) setter(next);
  }, [identityRef]);

  function startStructure() {
    setConfirm(null);
    void suite.submit('/api/asset-suite/structure', {
      path,
      language,
      mode,
      use_official: useOfficial,
      exe_path: useOfficial ? exePath : '',
      gen_emoji: genEmoji,
      confirm_overwrite: true,
    });
  }

  function startEmoji(modeValue: 'prepare' | 'restore') {
    setConfirm(null);
    void suite.submit('/api/asset-suite/emoji', {
      path,
      target_dir: emojiDir,
      mode: modeValue,
      confirm: true,
    });
  }

  const statusText = assetStatusText(t, suite, t('asset_structure_idle'));

  return (
    <div className="rb-asset-page rb-page-scroll" data-rb-page="ma-suite">
      {error ? <Banner tone="error">{error}</Banner> : null}
      <Banner tone={result?.partial || result?.level === 'warning' ? 'warning' : result?.level === 'error' ? 'error' : 'info'}>{statusText}</Banner>
      {active ? <Progress percent={Math.min(100, 100 * (job?.progress || 0))} aria-label={t('asset_running')} /> : null}
      {active ? (
        <div className="rb-tool-actions">
          <Button className="rb-asset-cancel" onClick={() => void suite.cancel()} disabled={cancelling || Boolean(job?.cancel_requested)}>
            {t('asset_cancel')}
          </Button>
        </div>
      ) : null}

      {result?.output_dir ? <p className="card-description rb-asset-output">{result.output_dir}</p> : null}
      <AssetResultNotes result={result} />

      <SettingsGroup title={t('asset_structure_title')} description={t('asset_structure_desc')}>
        <Form.Item className="rb-asset-path" label={t('asset_game_path')} style={{ marginBottom: 0 }}>
          <Input value={path} onChange={(event) => setPath(event.target.value)} disabled={busy} />
        </Form.Item>
        <div className="rb-tool-actions">
          <Button className="rb-asset-pick-folder" onClick={() => void pickDir(setPath, path)} disabled={busy}>{t('asset_pick_folder')}</Button>
          <Button className="rb-asset-pick-exe" onClick={() => void pickFile(setPath)} disabled={busy}>{t('asset_pick_exe')}</Button>
        </div>
        <Form.Item className="rb-asset-language" label={t('asset_language')} style={{ marginBottom: 0 }}>
          <Input value={language} onChange={(event) => setLanguage(event.target.value)} disabled={busy} />
        </Form.Item>
        <Form.Item className="rb-asset-mode" label={t('asset_mode')} style={{ marginBottom: 0 }}>
          <Select
            options={[
              { value: '1', label: t('asset_mode_1') },
              { value: '2', label: t('asset_mode_2') },
              { value: '3', label: t('asset_mode_3') },
            ]}
            value={mode}
            onChange={(value) => setMode((value as '1' | '2' | '3') || '1')}
            disabled={busy}
            allowClear={false}
          />
        </Form.Item>
        <Checkbox className="rb-asset-official" checked={useOfficial} onChange={(event) => {
          const checked = event.target.checked;
          setUseOfficial(checked);
          if (!checked) setExePath('');
        }} disabled={busy}>{t('asset_use_official')}</Checkbox>
        <Form.Item className="rb-asset-exe" label={t('asset_official_exe')} style={{ marginBottom: 0 }}>
          <Input value={exePath} onChange={(event) => setExePath(event.target.value)} disabled={busy || !useOfficial} />
        </Form.Item>
        <div className="rb-tool-actions">
          {/* 与 Qt 一致：未勾选时也能选 EXE，选中后自动勾选官方抽取 */}
          <Button onClick={() => void pickFile((value) => { setExePath(value); setUseOfficial(true); })} disabled={busy}>{t('asset_pick_exe')}</Button>
        </div>
        <Checkbox className="rb-asset-gen-emoji" checked={genEmoji} onChange={(event) => setGenEmoji(event.target.checked)} disabled={busy}>{t('asset_gen_emoji')}</Checkbox>
        <div className="rb-tool-actions">
          <Button type="primary" className="rb-asset-run-structure" onClick={() => setConfirm('structure')} disabled={writeBlocked || !path.trim()}>
            {t('asset_run_structure')}
          </Button>
        </div>
      </SettingsGroup>

      <SettingsGroup title={t('asset_emoji_title')} description={t('asset_emoji_desc')}>
        <Form.Item className="rb-asset-emoji-dir" label={t('asset_emoji_target')} style={{ marginBottom: 0 }}>
          <Input value={emojiDir} onChange={(event) => setEmojiDir(event.target.value)} disabled={busy} />
        </Form.Item>
        <div className="rb-tool-actions">
          <Button onClick={() => void pickDir(setEmojiDir, emojiDir)} disabled={busy}>{t('asset_pick_folder')}</Button>
          <Button type="primary" className="rb-asset-emoji-prepare" onClick={() => setConfirm('emoji-prepare')} disabled={writeBlocked || !path.trim() || !emojiDir.trim()}>
            {t('asset_emoji_prepare')}
          </Button>
          <Button type="primary" className="rb-asset-emoji-restore" onClick={() => setConfirm('emoji-restore')} disabled={writeBlocked || !path.trim() || !emojiDir.trim()}>
            {t('asset_emoji_restore')}
          </Button>
        </div>
      </SettingsGroup>

      {confirm === 'structure' ? (
        <Dialog title={t('asset_structure_confirm_title')} confirmText={t('asset_run_structure')} cancelText={t('workbench_cancel')} onConfirm={startStructure} onCancel={() => setConfirm(null)}>
          <p>{t('asset_structure_confirm')}</p>
          <p className="card-description">{deriveStructureOutput(path) ? t('asset_structure_output').replace('{path}', deriveStructureOutput(path)) : path}</p>
        </Dialog>
      ) : null}
      {confirm === 'emoji-prepare' || confirm === 'emoji-restore' ? (
        <Dialog
          title={t('asset_emoji_confirm_title')}
          confirmText={confirm === 'emoji-prepare' ? t('asset_emoji_prepare') : t('asset_emoji_restore')}
          cancelText={t('workbench_cancel')}
          onConfirm={() => startEmoji(confirm === 'emoji-prepare' ? 'prepare' : 'restore')}
          onCancel={() => setConfirm(null)}
        >
          <p>{t('asset_emoji_confirm')}</p>
          <p className="card-description">{emojiDir}</p>
        </Dialog>
      ) : null}
    </div>
  );
}
