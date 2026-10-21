/**
 * 项目设置页 —— 对齐 frontend/Project/ProjectPage.py 的实测几何。
 *
 * 实测（nav=256、页宽 1023）：
 *   头部 975x36 @ (24,24)：TitleLabel 18px + CaptionLabel 12px（间距 2）
 *   滚动区 975x669 @ (24,68)（头部底 60 之后 8px）
 *   恰好 6 张卡、每张 975x66、纵向节距 74（卡高 66 + 间距 8）
 *     卡内边距左 17、标题 fpx=14 @y=17、说明 fpx=12 @y=37、控件右侧垂直居中
 *     ComboBox 72x27 / PushButton 78x27 / SwitchButton 56x22
 *
 * 顺序同 renpybox/frontend/Project/ProjectPage.py:81-86。
 * 目录选择走主进程原生 dialog（`window.renpy.pickFolder`），对应原壳的
 * `QFileDialog.getExistingDirectory`；「打开」对应 `webbrowser.open`。
 *
 * 注意：真实 ProjectPage **没有「工程路径」卡片** —— 项目身份是选输入目录时
 * 由 `_sync_renpy_paths_from_selection()` 顺带绑定的，所以这里选完目录会调
 * `POST /api/project/resolve`（后端只在目录确实含 Ren'Py 结构时才认）。
 *
 * .rbox 工程文件只是输出缓存 + 白名单项目设置的快照：导入前必须先 inspect 并确认，
 * 导入替换当前输出缓存（后端留回滚备份），从不改写工程/输入/输出路径。
 * 自定义输出目录与工作台资料所在的规范输出目录不同时，后端还会同步并备份后者。
 * 旧 SQLite/JSON 缓存仍可直接使用。从旧数据创建 .rbox 只读取用户选中的目录，不改旧数据，也不替换当前缓存。
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { Button } from 'antd';

import { exportLegacyProjectFile, exportProjectFile, importProjectFile, inspectLegacyProjectCache, inspectProjectFile, resolveProject } from '../api';
import { useT } from '../i18n';
import { LANGUAGE_OPTIONS } from '../settingsSchema';
import type { LegacyProjectCacheDescription, ProjectFileDescription } from '../types';
import type { AppState } from '../useAppState';
import { Banner, Dialog, PageHeader, SelectInput, SettingCard, SettingsGroup, Switch } from '../ui';

const RBOX_FILTERS = [{ name: 'RenpyBox Project', extensions: ['rbox'] }];

type ProjectFileResult =
  | { kind: 'export'; path: string; itemCount: number; settings: number; source?: string }
  | { kind: 'import'; path: string; itemCount: number; backup: string; assetsOutput: string; assetsBackup: string; applied: number; ignored: number };

function withRboxSuffix(path: string): string {
  return /\.rbox$/i.test(path) ? path : `${path}.rbox`;
}

function parentFolder(target: string): string {
  const trimmed = target.replace(/[\\/]+$/, '');
  const parent = trimmed.replace(/[\\/][^\\/]+$/, '');
  return parent && parent !== trimmed ? parent : trimmed;
}

function formatTime(value: string): string {
  const time = Date.parse(value);
  return Number.isFinite(time) ? new Date(time).toLocaleString() : value || '—';
}

export function ProjectPage(props: { state: AppState; incomingFile?: string | null; onIncomingFileConsumed?: () => void }) {
  const { state, incomingFile, onIncomingFileConsumed } = props;
  const t = useT();
  const [inputFolder, setInputFolder] = useState('');
  const [outputFolder, setOutputFolder] = useState('');
  const [busy, setBusy] = useState(false);
  const [pendingImport, setPendingImport] = useState<ProjectFileDescription | null>(null);
  const [pendingLegacy, setPendingLegacy] = useState<LegacyProjectCacheDescription | null>(null);
  const [fileResult, setFileResult] = useState<ProjectFileResult | null>(null);
  const legacyFlight = useRef(false);

  // 语言下拉的选项文案在数据表里按 code 存，渲染时用 t() 换成当前界面语言。
  const languageOptions = LANGUAGE_OPTIONS.map((option) => ({ value: option.value, label: t(option.labelKey) }));

  const values = state.settings?.values;
  const sourceLanguage = String(values?.source_language ?? 'EN');
  const targetLanguage = String(values?.target_language ?? 'ZH');

  // 重新显示时刷新路径，避免沿用旧页面创建时的配置快照（对齐 showEvent）。
  useEffect(() => {
    if (!values) return;
    setInputFolder(String(values.input_folder ?? ''));
    setOutputFolder(String(values.output_folder ?? ''));
  }, [values]);

  /**
   * 选目录。原壳的 `_sync_renpy_paths_from_selection` 语义：
   * 只有目录本身带 Ren'Py 项目结构时才同步项目身份，否则仅保留为输入目录
   * —— 用户自建的翻译目录被当成项目根，会让 renpy_tl_folder 指向不存在的路径。
   */
  const pickFolder = useCallback(
    async (which: 'input' | 'output', current: string) => {
      const picked = await window.renpy?.pickFolder(current || undefined);
      if (!picked) return;
      setBusy(true);
      try {
        if (!await state.setSetting(which === 'input' ? 'input_folder' : 'output_folder', picked)) return;
        if (which === 'input') {
          try {
            await resolveProject(picked);
            await Promise.all([state.reloadProject(), state.reloadSettings(), state.reloadTranslation()]);
            state.pushToast('success', t('project_page_project_bound_toast'));
          } catch (error) {
            const message = error instanceof Error ? error.message : '';
            state.pushToast(
              'info',
              message || t('project_page_not_project_structure'),
            );
          }
        }
      } finally {
        setBusy(false);
      }
    },
    [state],
  );

  const pickProject = useCallback(async () => {
    const current = String(state.project?.renpy_project_path ?? inputFolder);
    const picked = await window.renpy?.pickFolder(current || undefined);
    if (!picked) return;
    setBusy(true);
    try {
      await resolveProject(picked);
      await Promise.all([state.reloadProject(), state.reloadSettings(), state.reloadTranslation()]);
      state.pushToast('success', t('project_page_project_bound_direct'));
    } catch (error) {
      state.pushToast('error', error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }, [inputFolder, state]);

  const openFolder = useCallback((target: string) => {
    if (!target) return;
    void window.renpy?.openPath(target);
  }, []);

  const projectRoot = String(state.project?.renpy_project_path ?? '');
  const gameFolder = String(state.project?.renpy_game_folder ?? '');
  const tlFolder = String(state.project?.renpy_tl_folder ?? '');
  const projectLabel = projectRoot.split(/[\\/]/).filter(Boolean).at(-1) || '';
  const engineBusy = state.translation.engine_status !== 'IDLE'
    || state.translation.stop_barrier
    || state.translation.single_tasks;
  const projectFileBlocked = busy || state.saving || engineBusy || !projectRoot || !window.renpy;

  const exportFile = useCallback(async () => {
    const picked = await window.renpy?.saveFile({ defaultPath: `${projectLabel || 'project'}.rbox`, filters: RBOX_FILTERS });
    if (!picked) return;
    const target = withRboxSuffix(picked);
    setBusy(true);
    try {
      const result = await exportProjectFile(target);
      setFileResult({ kind: 'export', path: result.info.path || target, itemCount: result.info.item_count, settings: result.settings.length });
      state.pushToast('success', t('project_file_export_success').replace('{path}', result.info.path || target));
    } catch (error) {
      state.pushToast('error', error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }, [projectLabel, state, t]);

  /** 打开 .rbox → 先 inspect，再弹确认框；「导入工程文件」按钮和双击文件都走这里。 */
  const beginImport = useCallback(async (path: string) => {
    setBusy(true);
    try {
      setPendingImport(await inspectProjectFile(path));
    } catch (error) {
      state.pushToast('error', error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }, [state]);

  const pickImportFile = useCallback(async () => {
    const picked = await window.renpy?.pickFile({ filters: RBOX_FILTERS });
    if (!picked) return;
    await beginImport(picked);
  }, [beginImport]);

  // 双击 .rbox / 启动参数带 .rbox：主进程推路径过来，直接进入导入确认。
  useEffect(() => {
    const file = String(incomingFile ?? '').trim();
    if (!file) return;
    onIncomingFileConsumed?.();
    void beginImport(file);
  }, [incomingFile, beginImport, onIncomingFileConsumed]);

  const confirmImport = useCallback(async (pending: ProjectFileDescription) => {
    setPendingImport(null);
    setBusy(true);
    try {
      const result = await importProjectFile(pending.info.path);
      await Promise.all([state.reloadProject(), state.reloadSettings(), state.reloadTranslation()]);
      setFileResult({
        kind: 'import',
        path: result.info.path || pending.info.path,
        itemCount: result.item_count,
        backup: result.backup_folder,
        assetsOutput: result.assets_output_folder,
        assetsBackup: result.assets_backup_folder,
        applied: result.applied_settings.length,
        ignored: result.ignored_settings.length,
      });
      state.pushToast(
        'success',
        result.assets_backup_folder
          ? t('project_file_import_success_assets')
            .replace('{backup}', result.backup_folder || '—')
            .replace('{assets_backup}', result.assets_backup_folder)
          : result.backup_folder
            ? t('project_file_import_success').replace('{backup}', result.backup_folder)
            : t('project_file_import_success_no_backup'),
      );
    } catch (error) {
      state.pushToast('error', error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }, [state, t]);

  const pickLegacyCache = useCallback(async () => {
    const picked = await window.renpy?.pickFolder(outputFolder || inputFolder || undefined);
    if (!picked) return;
    setBusy(true);
    try {
      setPendingLegacy(await inspectLegacyProjectCache(picked));
    } catch (error) {
      state.pushToast('error', error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }, [inputFolder, outputFolder, state]);

  const saveLegacyCache = useCallback(async (pending: LegacyProjectCacheDescription) => {
    if (legacyFlight.current) return;
    legacyFlight.current = true;
    setBusy(true);
    try {
      const picked = await window.renpy?.saveFile({ defaultPath: `${projectLabel || 'project'}-legacy.rbox`, filters: RBOX_FILTERS });
      if (!picked) return;
      const target = withRboxSuffix(picked);
      const result = await exportLegacyProjectFile(pending.cache_folder, target);
      setPendingLegacy(null);
      const path = result.info.path || target;
      setFileResult({
        kind: 'export',
        path,
        itemCount: result.info.item_count,
        settings: result.settings.length,
        source: result.source_output_folder,
      });
      state.pushToast('success', t('project_file_legacy_success').replace('{path}', path));
    } catch (error) {
      state.pushToast('error', error instanceof Error ? error.message : String(error));
    } finally {
      legacyFlight.current = false;
      setBusy(false);
    }
  }, [projectLabel, state, t]);

  const pendingRootMismatch = Boolean(
    pendingImport
    && pendingImport.info.project_root
    && pendingImport.current_project_root
    && !pendingImport.project_root_matches,
  );

  return (
    <div className="rb-page rb-page-narrow rb-project-page">
      <div className="rb-page-scroll">
        <PageHeader title={t('app_project_page')} description={t('project_page_header_description')} />
        {/* 已绑定的工程即“当前项目卡”，与接口管理的当前接口同样高亮 */}
        <section className="rb-panel rb-project-identity" data-active={Boolean(projectRoot)}>
          <div className="rb-identity-copy">
            <div className="rb-identity-kicker">{projectRoot ? t('project_page_bound_badge') : t('project_page_unbound_badge')}</div>
            <div className="rb-identity-name">{projectLabel || t('project_page_unbound_name')}</div>
            <p>
              {projectRoot
                ? t('project_page_bound_hint')
                : t('project_page_unbound_hint')}
            </p>
          </div>
          <Button disabled={busy} onClick={() => void pickProject()}>
            {projectRoot ? t('project_page_reselect') : t('project_page_select')}
          </Button>
          <dl className="rb-identity-paths">
            <div>
              <dt>{t('project_page_project_root')}</dt>
              <dd title={projectRoot || undefined}>{projectRoot || t('project_page_unbound')}</dd>
            </div>
            <div>
              <dt>game</dt>
              <dd title={gameFolder || undefined}>{gameFolder || '—'}</dd>
            </div>
            <div>
              <dt>tl</dt>
              <dd title={tlFolder || undefined}>{tlFolder || '—'}</dd>
            </div>
          </dl>
        </section>

        <div className="rb-project-file">
        <SettingsGroup
          title={t('project_file_title')}
          description={t('project_file_description')}
        >
          <Banner tone="info">{t('project_file_compatibility')}</Banner>
          <p className="rb-project-file-guide">{t('project_file_snapshot_hint')}</p>
          <p className="rb-project-file-guide">{t('project_file_legacy_steps')}</p>
          {!projectRoot ? <p className="rb-metric-note">{t('project_file_need_project')}</p> : null}
          {projectRoot && (state.saving || engineBusy) ? <p className="rb-metric-note">{t('project_file_busy')}</p> : null}
          <div className="rb-project-file-actions">
            <Button size="small" disabled={projectFileBlocked} onClick={() => void exportFile()}>{t('project_file_export')}</Button>
            <Button size="small" disabled={projectFileBlocked} onClick={() => void pickImportFile()}>{t('project_file_import')}</Button>
            <Button size="small" disabled={projectFileBlocked} onClick={() => void pickLegacyCache()}>{t('project_file_legacy_migrate')}</Button>
          </div>
          {fileResult ? (
            <dl className="rb-workbench-draft-fields">
              <div>
                <dt>{t(fileResult.kind === 'export' ? 'project_file_last_export' : 'project_file_last_import')}</dt>
                <dd>
                  <span className="rb-path" title={fileResult.path}>{fileResult.path}</span>
                  {fileResult.kind === 'export' && fileResult.source ? (
                    <>
                      {' '}
                      <Button type="link" size="small" onClick={() => openFolder(parentFolder(fileResult.path))}>{t('project_file_open_folder')}</Button>
                    </>
                  ) : null}
                </dd>
              </div>
              <div><dt>{t('project_file_item_count')}</dt><dd>{fileResult.itemCount}</dd></div>
              {fileResult.kind === 'export' && fileResult.source ? (
                <div><dt>{t('project_file_legacy_source')}</dt><dd className="rb-path" title={fileResult.source}>{fileResult.source}</dd></div>
              ) : null}
              {fileResult.kind === 'export' ? (
                <div>
                  <dt>{t('project_file_settings')}</dt>
                  <dd>{t('project_file_settings_exported').replace('{count}', String(fileResult.settings))}</dd>
                </div>
              ) : (
                <>
                  <div>
                    <dt>{t('project_file_settings')}</dt>
                    <dd>
                      {t('project_file_settings_imported')
                        .replace('{applied}', String(fileResult.applied))
                        .replace('{ignored}', String(fileResult.ignored))}
                    </dd>
                  </div>
                  <div>
                    <dt>{t('project_file_backup')}</dt>
                    <dd>
                      {fileResult.backup ? (
                        <>
                          <span className="rb-path" title={fileResult.backup}>{fileResult.backup}</span>{' '}
                          <Button type="link" size="small" onClick={() => openFolder(fileResult.backup)}>{t('setting_open')}</Button>
                        </>
                      ) : t('project_file_backup_none')}
                    </dd>
                  </div>
                  {fileResult.assetsOutput ? (
                    <div>
                      <dt>{t('project_file_assets_backup')}</dt>
                      <dd>
                        {fileResult.assetsBackup ? (
                          <>
                            <span className="rb-path" title={fileResult.assetsBackup}>{fileResult.assetsBackup}</span>{' '}
                            <Button type="link" size="small" onClick={() => openFolder(fileResult.assetsBackup)}>{t('setting_open')}</Button>
                          </>
                        ) : t('project_file_backup_none')}
                      </dd>
                    </div>
                  ) : null}
                </>
              )}
            </dl>
          ) : projectRoot ? (
            <p className="rb-metric-note">{t('project_file_empty')}</p>
          ) : null}
          {fileResult?.kind === 'export' && fileResult.source ? (
            <p className="rb-project-file-guide">{t('project_file_legacy_next')}</p>
          ) : null}
        </SettingsGroup>
        </div>
        <SettingsGroup>
          <SettingCard title={t('project_page_source_language_title')} description={t('project_page_source_language_content')}>
            <SelectInput
              label={t('project_page_source_language_title')}
              value={sourceLanguage}
              disabled={state.saving}
              options={languageOptions}
              onCommit={(next) => state.setSetting('source_language', next)}
            />
          </SettingCard>
          <SettingCard title={t('project_page_target_language_title')} description={t('project_page_target_language_content')}>
            <SelectInput
              label={t('project_page_target_language_title')}
              value={targetLanguage}
              disabled={state.saving}
              options={languageOptions}
              onCommit={(next) => state.setSetting('target_language', next)}
            />
          </SettingCard>
          <SettingCard title={t('project_page_input_folder_title')} description={<span className="rb-path" title={inputFolder || undefined}>{inputFolder || t('setting_input_folder_placeholder')}</span>}>
            <Button type="default" size="small" disabled={busy} onClick={() => void pickFolder('input', inputFolder)}>{t('setting_choose')}</Button>
            <Button type="default" size="small" disabled={!inputFolder} onClick={() => openFolder(inputFolder)}>{t('setting_open')}</Button>
          </SettingCard>
          <SettingCard title={t('project_page_output_folder_title')} description={<span className="rb-path" title={outputFolder || undefined}>{outputFolder || t('setting_output_folder_placeholder')}</span>}>
            <Button type="default" size="small" disabled={busy} onClick={() => void pickFolder('output', outputFolder)}>{t('setting_choose')}</Button>
            <Button type="default" size="small" disabled={!outputFolder} onClick={() => openFolder(outputFolder)}>{t('setting_open')}</Button>
          </SettingCard>
          <SettingCard title={t('project_page_output_folder_open_on_finish_title')} description={t('project_page_output_folder_open_on_finish_content')}>
            <Switch
              checked={values?.output_folder_open_on_finish === true}
              disabled={state.saving}
              label={t('project_page_output_folder_open_on_finish_title')}
              onChange={(next) => state.setSetting('output_folder_open_on_finish', next)}
            />
          </SettingCard>
          <SettingCard title={t('project_page_traditional_chinese_title')} description={t('project_page_traditional_chinese_content')}>
            <Switch
              checked={values?.traditional_chinese_enable === true}
              disabled={state.saving}
              label={t('project_page_traditional_chinese_title')}
              onChange={(next) => state.setSetting('traditional_chinese_enable', next)}
            />
          </SettingCard>
        </SettingsGroup>

      </div>

      {pendingLegacy ? (
        <Dialog
          title={t('project_file_legacy_title')}
          confirmText={t('project_file_legacy_confirm')}
          onCancel={() => { if (!busy) setPendingLegacy(null); }}
          onConfirm={busy ? undefined : () => void saveLegacyCache(pendingLegacy)}
        >
          <p>{t('project_file_legacy_body')}</p>
          <dl className="rb-workbench-draft-fields">
            <div><dt>{t('project_file_legacy_output')}</dt><dd>{pendingLegacy.output_folder || '—'}</dd></div>
            <div><dt>{t('project_file_legacy_cache')}</dt><dd>{pendingLegacy.cache_folder}</dd></div>
            <div><dt>{t('project_file_legacy_format')}</dt><dd>{t(pendingLegacy.cache_format === 'json' ? 'project_file_legacy_format_json' : 'project_file_legacy_format_sqlite')}</dd></div>
            <div><dt>{t('project_file_item_count')}</dt><dd>{pendingLegacy.item_count}</dd></div>
            <div><dt>{t('project_file_current_root')}</dt><dd>{pendingLegacy.current_project_root || '—'}</dd></div>
            <div><dt>{t('project_file_settings')}</dt><dd>{t('project_file_legacy_settings').replace('{count}', String(pendingLegacy.settings.length))}</dd></div>
          </dl>
        </Dialog>
      ) : null}

      {pendingImport ? (
        <Dialog
          title={t('project_file_import_title')}
          confirmText={t('project_file_import_confirm')}
          onCancel={() => setPendingImport(null)}
          onConfirm={busy ? undefined : () => void confirmImport(pendingImport)}
        >
          <p>{t('project_file_import_body')}</p>
          {pendingRootMismatch ? <Banner tone="warning">{t('project_file_root_mismatch')}</Banner> : null}
          <dl className="rb-workbench-draft-fields">
            <div><dt>{t('project_file_path')}</dt><dd>{pendingImport.info.path}</dd></div>
            <div><dt>{t('project_file_recorded_root')}</dt><dd>{pendingImport.info.project_root || '—'}</dd></div>
            <div><dt>{t('project_file_current_root')}</dt><dd>{pendingImport.current_project_root || '—'}</dd></div>
            <div><dt>{t('project_file_output_folder')}</dt><dd>{pendingImport.output_folder || '—'}</dd></div>
            <div><dt>{t('project_file_item_count')}</dt><dd>{pendingImport.info.item_count}</dd></div>
            <div><dt>{t('project_file_schema')}</dt><dd>{pendingImport.info.schema_version}</dd></div>
            <div><dt>{t('project_file_app_version')}</dt><dd>{pendingImport.info.app_version || '—'}</dd></div>
            <div><dt>{t('project_file_updated_at')}</dt><dd>{formatTime(pendingImport.info.updated_at)}</dd></div>
          </dl>
        </Dialog>
      ) : null}
    </div>
  );
}
