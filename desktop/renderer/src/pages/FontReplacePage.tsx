/** 字体注入：扫描 / 预置注入 / 一键替换，对齐 Qt5 FontReplacePage。 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Checkbox, Collapse, Form, Input, Progress, Select } from 'antd';

import {
  FONT_BROWSE_LABEL,
  FONT_DEFAULT_LANGUAGE_LABEL,
  FONT_DEFAULT_LANGUAGE_VALUE,
  FONT_GAME_DIR_EMPTY_LABEL,
  FONT_GAME_DIR_HINT,
  FONT_SCAN_NO_REFS_LABEL,
  FONT_SCAN_STALE_LABEL,
  fontCopy,
  fontDetectedPlaceholder,
  fontGameDirReady,
  fontToolsGamePathPayload,
  fontToolsStatusPath,
  fontWriteNeedsRescan,
  formatFontBackupSideEffect,
  formatFontRestoreHint,
  formatFontScanSummary,
  replaceFontsReady,
  resolveFontInjectLanguage,
} from '../fontReplaceView.mjs';
import { fontInjectLanguageReady } from '../languageToolsView.mjs';
import { useT } from '../i18n';
import type { AppState } from '../useAppState';
import { Banner, Dialog, SettingsGroup } from '../ui';
import {
  toolJobResult,
  toolStatusText,
  useProjectToolJob,
  type ToolJob,
  type ToolResultBase,
} from './projectToolJob';

interface FontResult extends ToolResultBase {
  base_box?: string;
  fonts_dir?: string;
  gui_hook?: boolean | null;
  font_refs?: string[];
  font_files?: string[];
  font_ref_count?: number;
  font_file_count?: number;
  lang_count?: number;
  replaced_files?: number;
  replaced_count?: number;
  backup_name?: string;
  failed_files?: string[];
  partial?: boolean;
  restored?: boolean;
}

interface FontStatus {
  project_key?: string;
  project_root?: string;
  game_dir?: string;
  languages?: string[];
  font_refs?: string[];
  font_files?: string[];
  font_ref_count?: number;
  font_file_count?: number;
  fonts_scanned?: boolean;
  scan_stale?: boolean;
  job?: ToolJob<FontResult> | null;
  last_write_job?: ToolJob<FontResult> | null;
}

const KINDS = ['font_scan', 'font_inject', 'font_replace'] as const;

export function FontReplacePage(props: { state: AppState }) {
  const { state } = props;
  const t = useT();
  const uiLang = state.bootLanguage === 'EN' ? 'EN' : 'ZH';
  const boundGame = String(state.project?.renpy_game_folder ?? '');
  const [gameDir, setGameDir] = useState(boundGame);
  const [selected, setSelected] = useState('chinese');
  const [custom, setCustom] = useState('');
  const [generateGui, setGenerateGui] = useState(false);
  const [customFont, setCustomFont] = useState('');
  const [replaceAll, setReplaceAll] = useState(false);
  const [selectedFont, setSelectedFont] = useState('');
  const [originalFont, setOriginalFont] = useState('');
  const [autoBackup, setAutoBackup] = useState(true);
  const [confirmInject, setConfirmInject] = useState(false);
  const [confirmReplace, setConfirmReplace] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const scannedIdentity = useRef('');
  const rescanAfterWrite = useRef('');
  const statusPath = useMemo(() => fontToolsStatusPath(gameDir), [gameDir]);
  const suite = useProjectToolJob<FontResult, FontStatus>(state, statusPath, KINDS);
  const { status, keyReady, job, result, active, error, cancelling, busy } = suite;
  const writeJob = status?.last_write_job ?? null;
  const writeResult = toolJobResult(writeJob);
  const engineBusy = state.translation.engine_status !== 'IDLE' || state.translation.stop_barrier || state.translation.single_tasks;
  const hasProject = Boolean(state.project?.renpy_project_path);
  const languages = status?.languages?.length ? status.languages : ['chinese'];
  const language = useMemo(
    () => resolveFontInjectLanguage(selected, custom, 'chinese'),
    [selected, custom],
  );
  const languageReady = fontInjectLanguageReady(language);
  const fontsScanned = Boolean(status?.fonts_scanned) && !status?.scan_stale;
  const scanResultFresh = result?.action === 'scan' && job?.status === 'done';
  const fontRefs = fontsScanned
    ? (status?.font_refs ?? [])
    : (scanResultFresh ? (result?.font_refs ?? []) : []);
  const fontFiles = fontsScanned
    ? (status?.font_files ?? [])
    : (scanResultFresh ? (result?.font_files ?? []) : []);
  const fontRefCount = fontsScanned
    ? (status?.font_ref_count ?? fontRefs.length)
    : (scanResultFresh ? (result?.font_ref_count ?? fontRefs.length) : 0);
  const fontFileCount = fontsScanned
    ? (status?.font_file_count ?? fontFiles.length)
    : (scanResultFresh ? (result?.font_file_count ?? fontFiles.length) : 0);
  const replaceReady = replaceFontsReady({
    replaceAll,
    selectedFont,
    originalFont,
    detected: fontRefs,
  });
  const gameDirReady = fontGameDirReady(gameDir);
  // 空目录禁止写入/扫描：绝不能静默回退绑定项目
  const writeBlocked = busy || engineBusy || !keyReady || state.link !== 'open' || !hasProject || !gameDirReady;
  const injectBlocked = writeBlocked || !languageReady;
  const replaceBlocked = writeBlocked || !replaceReady;
  const canCancel = active && (job?.kind === 'font_scan' || !result?.written);
  const languageOptions = useMemo(
    () => [
      { value: FONT_DEFAULT_LANGUAGE_VALUE, label: fontCopy(FONT_DEFAULT_LANGUAGE_LABEL, uiLang) },
      ...languages.map((item) => ({ value: item, label: item })),
    ],
    [languages, uiLang],
  );
  const detectedPlaceholder = fontDetectedPlaceholder(
    {
      fontsScanned: fontsScanned || Boolean(scanResultFresh),
      scanStale: Boolean(status?.scan_stale) && !scanResultFresh,
      fontRefCount,
    },
    {
      noRefs: fontCopy(FONT_SCAN_NO_REFS_LABEL, uiLang),
      notScanned: t('font_inject_not_scanned'),
    },
  );
  const pathPayload = useMemo(
    () => fontToolsGamePathPayload(gameDir, boundGame),
    [gameDir, boundGame],
  );
  const scanScope = `${suite.identity}\0${statusPath}`;

  useEffect(() => {
    // 仅 owner（全局项目）变化时重置手动目录，避免改目录循环刷回绑定路径
    setGameDir(String(state.project?.renpy_game_folder ?? ''));
    setConfirmInject(false);
    setConfirmReplace(false);
    setGenerateGui(false);
    setCustom('');
    setCustomFont('');
    setReplaceAll(false);
    setSelectedFont('');
    setOriginalFont('');
    setAutoBackup(true);
    setAdvancedOpen(false);
    scannedIdentity.current = '';
    rescanAfterWrite.current = '';
    if (languages.includes('chinese')) setSelected('chinese');
    else if (languages[0]) setSelected(languages[0]);
  }, [suite.identity]);

  const languagesKey = languages.join('\0');
  useEffect(() => {
    if (!custom && languages.includes('chinese')) setSelected('chinese');
  }, [languagesKey, custom]);

  // 绑定目录或手动目标变化后自动扫描；空目录禁止回退 bound；scope 含 statusPath
  useEffect(() => {
    if (!gameDirReady) {
      // 空目录不得扫描；清掉占位，否则恢复同一路径时 scannedIdentity===scanScope 会跳过自动扫描
      scannedIdentity.current = '';
      return;
    }
    if (!keyReady || !hasProject || state.link !== 'open' || busy || engineBusy) return;
    if (scannedIdentity.current === scanScope) return;
    scannedIdentity.current = scanScope;
    void suite.submit('/api/font-tools/scan', { ...pathPayload }).then((ok) => {
      if (ok) return;
      // pending 守卫丢弃时释放占位，避免永久跳过
      if (scannedIdentity.current === scanScope) scannedIdentity.current = '';
    });
  }, [keyReady, hasProject, state.link, scanScope, busy, engineBusy, suite.submit, pathPayload, gameDirReady]);

  // 注入/替换任意实际写入终态都作废旧 refs 并自动重扫；写报告由 last_write_job 保留
  // busy/pending 时不得提前占位：否则 submit 被守卫丢弃后永远不再重试，页面会卡在 scan_stale
  useEffect(() => {
    if (active || busy || !fontWriteNeedsRescan(job, result)) return;
    if (!job || rescanAfterWrite.current === job.id) return;
    if (!keyReady || !hasProject || state.link !== 'open' || engineBusy) return;
    if (!gameDirReady) return;
    const writeId = job.id;
    rescanAfterWrite.current = writeId;
    scannedIdentity.current = scanScope;
    void suite.submit('/api/font-tools/scan', { ...pathPayload }).then((ok) => {
      if (ok) return;
      // submit 被 pending/canonical 拒绝：释放占位，等 busy 结束后由本 effect 重试
      if (rescanAfterWrite.current === writeId) rescanAfterWrite.current = '';
      if (scannedIdentity.current === scanScope) scannedIdentity.current = '';
    });
  }, [
    active, busy, job?.id, job?.status, result?.action, result?.written,
    keyReady, hasProject, state.link, engineBusy, scanScope, suite.submit, pathPayload, gameDirReady,
  ]);

  const fontRefsKey = fontRefs.join('\0');
  useEffect(() => {
    if (!fontRefs.length) {
      setSelectedFont('');
      return;
    }
    setSelectedFont((previous) => (fontRefs.includes(previous) ? previous : fontRefs[0] || ''));
  }, [fontRefsKey]);

  async function pickGameDir() {
    const context = suite.identityRef.current;
    const next = await window.renpy?.pickFolder?.(gameDir || boundGame || undefined);
    if (next && context === suite.identityRef.current) setGameDir(next);
  }

  async function pickFont() {
    const context = suite.identityRef.current;
    const next = await window.renpy?.pickFile?.({
      filters: [{ name: 'Font', extensions: ['ttf', 'otf', 'ttc', 'otc'] }],
    });
    if (next && context === suite.identityRef.current) setCustomFont(next);
  }

  function startInject() {
    if (!fontGameDirReady(gameDir)) return;
    setConfirmInject(false);
    void suite.submit('/api/font-tools/inject', {
      ...pathPayload,
      language,
      generate_gui_hook: generateGui,
      custom_font: customFont,
      confirm: true,
    });
  }

  function startReplace() {
    if (!fontGameDirReady(gameDir)) return;
    setConfirmReplace(false);
    void suite.submit('/api/font-tools/replace', {
      ...pathPayload,
      replace_all: replaceAll,
      selected_font: selectedFont,
      original_font: originalFont,
      custom_font: customFont,
      create_backup: autoBackup,
      confirm: true,
    });
  }

  function rescan() {
    if (!fontGameDirReady(gameDir)) return;
    scannedIdentity.current = scanScope;
    void suite.submit('/api/font-tools/scan', { ...pathPayload });
  }

  const statusText = toolStatusText(t, suite, t('font_inject_idle'));
  const statusTone = active || suite.checking
    ? 'info'
    : job?.status === 'done'
      ? (result?.gui_hook === false || result?.partial ? 'warning' : 'success')
      : job?.status === 'failed'
        ? (result?.written || result?.partial ? 'warning' : 'error')
        : job?.status === 'cancelled'
          ? 'warning'
          : 'info';
  const scanSummary = formatFontScanSummary(t('font_inject_scan_summary'), {
    fontCount: fontRefCount,
    fontFileCount: fontFileCount,
    langCount: languages.length,
  });
  const reviewWrite = Boolean(
    writeResult
    && writeJob
    && (writeJob.status === 'done' || writeJob.status === 'failed')
    && (writeResult.action === 'inject' || writeResult.action === 'replace')
    && (writeResult.written || writeResult.partial || writeResult.backup_path || typeof writeResult.replaced_files === 'number'),
  );
  const writeTone = writeJob?.status === 'failed'
    ? (writeResult?.written || writeResult?.partial ? 'warning' : 'error')
    : (writeResult?.partial || writeResult?.gui_hook === false ? 'warning' : 'success');
  const showFailureSideEffects = Boolean(
    job?.status === 'failed' && (result?.written || result?.partial || result?.backup_path),
  );
  const restoreHint = formatFontRestoreHint(writeResult || result, uiLang);
  const backupSideEffect = formatFontBackupSideEffect(
    writeResult?.backup_path || result?.backup_path,
    uiLang,
  );

  return (
    <div className="rb-asset-page rb-page-scroll" data-rb-page="font-replace">
      {error && gameDirReady ? <Banner tone="error">{error}</Banner> : null}
      {!hasProject ? <Banner tone="warning">{t('app_tool_needs_project')}</Banner> : null}
      {hasProject && !gameDirReady ? (
        <div data-rb-font-game-empty="1">
          <Banner tone="warning">{fontCopy(FONT_GAME_DIR_EMPTY_LABEL, uiLang)}</Banner>
        </div>
      ) : null}
      <Banner tone="info">{t('font_inject_intro')}</Banner>
      <Banner tone={statusTone}>{statusText}</Banner>
      {showFailureSideEffects ? (
        <Banner tone="warning">
          {result?.written || result?.partial
            ? (result?.message || statusText)
            : statusText}
          {restoreHint ? ` ${restoreHint}` : ''}
          {backupSideEffect ? ` ${backupSideEffect}` : ''}
        </Banner>
      ) : null}
      {reviewWrite ? (
        <div data-rb-font-write-report="1">
          <Banner tone={writeTone}>
            {writeResult?.message || ''}
            {typeof writeResult?.replaced_files === 'number'
              ? ` ${t('font_inject_replace_result')
                .replace('{replaced_files}', String(writeResult.replaced_files))
                .replace('{replaced_count}', String(writeResult.replaced_count ?? 0))}`
              : ''}
            {writeResult?.failed_files?.length
              ? ` failed=${writeResult.failed_files.length}`
              : ''}
            {restoreHint && !showFailureSideEffects ? ` ${restoreHint}` : ''}
            {backupSideEffect && !showFailureSideEffects ? ` ${backupSideEffect}` : ''}
          </Banner>
        </div>
      ) : null}
      {hasProject ? <Banner tone="info">{scanSummary}</Banner> : null}
      {status?.scan_stale ? (
        <Banner tone="warning">{fontCopy(FONT_SCAN_STALE_LABEL, uiLang)}</Banner>
      ) : null}
      {active ? <Progress percent={Math.min(100, 100 * (job?.progress || 0))} aria-label={t('tool_job_running')} /> : null}
      {active && canCancel ? (
        <div className="rb-tool-actions">
          <Button onClick={() => void suite.cancel()} disabled={cancelling || Boolean(job?.cancel_requested)}>
            {t('tool_job_cancel')}
          </Button>
        </div>
      ) : null}

      <SettingsGroup title={t('font_inject_title')} description={t('font_inject_desc')}>
        <Form.Item label={t('lang_tools_game_dir')} style={{ marginBottom: 12 }}>
          <div className="rb-tool-actions" style={{ display: 'flex', gap: 8 }}>
            <Input
              value={gameDir}
              onChange={(event) => setGameDir(event.target.value)}
              placeholder={boundGame || fontCopy(FONT_GAME_DIR_HINT, uiLang)}
              disabled={busy || !hasProject}
              data-rb-font-game-dir="1"
            />
            <Button onClick={() => void pickGameDir()} disabled={busy || !hasProject}>
              {fontCopy(FONT_BROWSE_LABEL, uiLang)}
            </Button>
          </div>
          <p className="card-description">{fontCopy(FONT_GAME_DIR_HINT, uiLang)}</p>
        </Form.Item>
        <Form.Item label={t('font_inject_language')} style={{ marginBottom: 12 }}>
          <Select
            options={languageOptions}
            value={selected}
            onChange={(value) => setSelected(String(value ?? FONT_DEFAULT_LANGUAGE_VALUE))}
            disabled={busy || !hasProject}
            allowClear={false}
          />
        </Form.Item>
        <Form.Item label={t('font_inject_custom_language')} style={{ marginBottom: 12 }}>
          <Input
            value={custom}
            onChange={(event) => setCustom(event.target.value)}
            placeholder={t('font_inject_custom_language_hint')}
            disabled={busy || !hasProject}
          />
        </Form.Item>
        <p className="card-description">{t('font_inject_language_hint')}</p>
        <div className="rb-tool-actions">
          <Button type="primary" onClick={() => setConfirmInject(true)} disabled={injectBlocked}>
            {t('font_inject_run')}
          </Button>
          <Button onClick={() => void rescan()} disabled={writeBlocked}>
            {t('font_inject_rescan')}
          </Button>
        </div>
      </SettingsGroup>

      <Collapse
        activeKey={advancedOpen ? ['advanced'] : []}
        onChange={(keys) => setAdvancedOpen((Array.isArray(keys) ? keys : [keys]).map(String).includes('advanced'))}
        items={[{
          key: 'advanced',
          label: t('font_inject_advanced'),
          children: (
            <div>
              <p className="card-description">{t('font_inject_advanced_desc')}</p>
              <Form.Item label={t('font_inject_custom_font')} style={{ marginBottom: 12 }}>
                <Input
                  value={customFont}
                  onChange={(event) => setCustomFont(event.target.value)}
                  placeholder={t('font_inject_custom_font_hint')}
                  disabled={busy || !hasProject}
                />
              </Form.Item>
              <div className="rb-tool-actions">
                <Button onClick={() => void pickFont()} disabled={busy || !hasProject}>
                  {t('font_inject_pick_font')}
                </Button>
              </div>

              <Form.Item label={t('font_inject_detected_fonts')} style={{ marginBottom: 12 }}>
                <Select
                  className="rb-font-detected-select"
                  options={fontRefs.map((item) => ({ value: item, label: item }))}
                  value={fontRefs.length ? selectedFont || undefined : undefined}
                  onChange={(value) => setSelectedFont(String(value || ''))}
                  disabled={busy || !hasProject || !fontRefs.length || replaceAll}
                  placeholder={detectedPlaceholder}
                  allowClear={false}
                />
              </Form.Item>
              <p className="card-description">{t('font_inject_detected_hint')}</p>
              <p className="card-description" data-rb-font-refs-files="1">
                {t('font_inject_refs_files')
                  .replace('{font_count}', String(fontRefCount))
                  .replace('{font_file_count}', String(fontFileCount))}
              </p>
              {fontFiles.length ? (
                <p className="card-description rb-asset-output">{fontFiles.slice(0, 12).join(', ')}{fontFiles.length > 12 ? '…' : ''}</p>
              ) : null}

              <Checkbox
                checked={replaceAll}
                onChange={(event) => setReplaceAll(event.target.checked)}
                disabled={busy || !hasProject}
              >
                {t('font_inject_replace_all')}
              </Checkbox>
              <Form.Item label={t('font_inject_original_font')} style={{ marginBottom: 12, marginTop: 12 }}>
                <Input
                  value={originalFont}
                  onChange={(event) => setOriginalFont(event.target.value)}
                  placeholder={t('font_inject_original_font_hint')}
                  disabled={busy || !hasProject || replaceAll}
                />
              </Form.Item>

              <Checkbox
                checked={generateGui}
                onChange={(event) => setGenerateGui(event.target.checked)}
                disabled={busy || !hasProject}
              >
                {t('font_inject_gui_hook')}
              </Checkbox>
              <p className="card-description">{t('font_inject_gui_hook_hint')}</p>

              <Checkbox
                checked={autoBackup}
                onChange={(event) => setAutoBackup(event.target.checked)}
                disabled={busy || !hasProject}
              >
                {t('font_inject_auto_backup')}
              </Checkbox>

              <div className="rb-tool-actions" style={{ marginTop: 12 }}>
                <Button onClick={() => setConfirmReplace(true)} disabled={replaceBlocked}>
                  {t('font_inject_replace_run')}
                </Button>
              </div>
            </div>
          ),
        }]}
      />

      {writeResult?.base_box ? <p className="card-description rb-asset-output">{writeResult.base_box}</p> : null}
      {typeof writeResult?.replaced_files === 'number' ? (
        <p className="card-description rb-asset-output" data-rb-font-replace-result="1">
          {t('font_inject_replace_result')
            .replace('{replaced_files}', String(writeResult.replaced_files))
            .replace('{replaced_count}', String(writeResult.replaced_count ?? 0))}
        </p>
      ) : null}
      {writeResult?.backup_path ? (
        <p className="card-description rb-asset-backup" data-rb-font-backup="1">
          {formatFontBackupSideEffect(writeResult.backup_path, uiLang)}
        </p>
      ) : null}

      {confirmInject ? (
        <Dialog
          title={t('font_inject_confirm_title')}
          confirmText={t('font_inject_run')}
          cancelText={t('workbench_cancel')}
          onConfirm={startInject}
          onCancel={() => setConfirmInject(false)}
        >
          <p>{t('font_inject_confirm').replace('{language}', language)}</p>
          {generateGui ? <p className="card-description">{t('font_inject_confirm_gui')}</p> : null}
        </Dialog>
      ) : null}

      {confirmReplace ? (
        <Dialog
          title={t('font_inject_replace_confirm_title')}
          confirmText={t('font_inject_replace_run')}
          cancelText={t('workbench_cancel')}
          onConfirm={startReplace}
          onCancel={() => setConfirmReplace(false)}
        >
          <p>{t('font_inject_replace_confirm')}</p>
          {autoBackup ? <p className="card-description">{t('font_inject_auto_backup')}</p> : null}
        </Dialog>
      ) : null}
    </div>
  );
}
