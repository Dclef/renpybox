/** 错误修复：扫描 / 自动修复 / lint / 导出，对齐 Qt5 ErrorRepairPage。 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Checkbox, Form, Input, Progress } from 'antd';

import { request } from '../api';
import {
  ERROR_REPAIR_DEFAULTS,
  errorRepairOwnerProjectKey,
  errorRepairStatusPath,
  formatFixSummary,
  formatScanSummary,
} from '../errorRepairView.mjs';
import { useT } from '../i18n';
import type { AppState } from '../useAppState';
import { Banner, Dialog, SettingsGroup } from '../ui';
import {
  toolStatusText,
  useProjectToolJob,
  type ToolJob,
  type ToolResultBase,
} from './projectToolJob';

interface RepairResult extends ToolResultBase {
  report?: Record<string, Array<Record<string, unknown>>>;
  total_issues?: number;
  fixed_files?: number;
  fixed_items?: number;
  failed_files?: number;
  errors?: Array<Record<string, unknown>>;
  error_count?: number;
  lint_errors_path?: string;
  folder?: string;
  success?: boolean;
}

interface RepairStatus {
  project_key?: string;
  folder?: string;
  owner_project_key?: string;
  has_scan_report?: boolean;
  job?: ToolJob<RepairResult> | null;
}

const KINDS = ['error_repair_scan', 'error_repair_fix', 'error_repair_lint'] as const;

const COPY = {
  ZH: {
    folderTitle: '翻译目录',
    folderDesc: '选择 game/tl/<语言> 或包含生成 .rpy 的目录',
    folderLabel: '翻译目录',
    optionsTitle: '修复选项',
    fixIndent: '修复缩进问题（Tab 转空格）',
    fixIndentLevel: '修复缩进层级问题（按父块回退）',
    fixQuotes: '规范化外层中文引号',
    fixDialogue: '修复未转义引号（源码翻译）',
    lintTitle: '深度 Lint 检查',
    lintDesc: "调用 Ren'Py 内置 lint 命令进行深度语法检查",
    exeLabel: '游戏主程序',
    scan: '扫描错误',
    fix: '自动修复',
    export: '导出报告',
    runLint: '执行 Lint 检查',
    fixConfirm: '将直接修改选定翻译目录下的 .rpy，不会自动备份。继续？',
    noBackup: '共享实现不会自动备份。',
    browse: '浏览',
  },
  EN: {
    folderTitle: 'Translation Folder',
    folderDesc: 'Select game/tl/<language> or a folder with generated .rpy files',
    folderLabel: 'Translation Folder',
    optionsTitle: 'Repair Options',
    fixIndent: 'Fix Indentation (Convert Tabs to Spaces)',
    fixIndentLevel: 'Fix Indentation Levels (Follow Parent Blocks)',
    fixQuotes: 'Normalize Outer Chinese Quotation Marks',
    fixDialogue: 'Fix Unescaped Quotes (Source Translation)',
    lintTitle: 'Deep Lint Check',
    lintDesc: "Run Ren'Py's built-in lint command for a deeper syntax check",
    exeLabel: 'Game Executable',
    scan: 'Scan for Errors',
    fix: 'Repair Automatically',
    export: 'Export Report',
    runLint: 'Run Lint Check',
    fixConfirm: 'Files under the selected translation folder will be modified in place. No automatic backup. Continue?',
    noBackup: 'The shared repairer does not create backups.',
    browse: 'Browse',
  },
} as const;

export function ErrorRepairPage(props: { state: AppState }) {
  const { state } = props;
  const t = useT();
  const uiLang = state.bootLanguage === 'EN' ? 'EN' : 'ZH';
  const copy = COPY[uiLang];
  const [folder, setFolder] = useState('');
  const [gameExe, setGameExe] = useState('');
  const [fixIndent, setFixIndent] = useState(ERROR_REPAIR_DEFAULTS.fixIndent);
  const [fixIndentLevel, setFixIndentLevel] = useState(ERROR_REPAIR_DEFAULTS.fixIndentLevel);
  const [fixQuotes, setFixQuotes] = useState(ERROR_REPAIR_DEFAULTS.fixQuotes);
  const [fixDialogueQuotes, setFixDialogueQuotes] = useState(ERROR_REPAIR_DEFAULTS.fixDialogueQuotes);
  const [confirmFix, setConfirmFix] = useState(false);
  const [exportError, setExportError] = useState('');
  // 按目录身份保留上次成功扫描，失败不清
  const lastScanByFolder = useRef<Record<string, RepairResult>>({});

  const statusPath = useMemo(() => errorRepairStatusPath(folder), [folder]);
  const suite = useProjectToolJob<RepairResult, RepairStatus>(state, statusPath, KINDS, folder);
  const { keyReady, job, result, active, error, busy, status } = suite;
  const ownerKey = errorRepairOwnerProjectKey(status);
  const engineBusy = state.translation.engine_status !== 'IDLE' || state.translation.stop_barrier || state.translation.single_tasks;
  const blocked = busy || engineBusy || !keyReady || state.link !== 'open';
  const folderReady = Boolean(folder.trim());

  useEffect(() => {
    setFolder('');
    setGameExe('');
    setFixIndent(ERROR_REPAIR_DEFAULTS.fixIndent);
    setFixIndentLevel(ERROR_REPAIR_DEFAULTS.fixIndentLevel);
    setFixQuotes(ERROR_REPAIR_DEFAULTS.fixQuotes);
    setFixDialogueQuotes(ERROR_REPAIR_DEFAULTS.fixDialogueQuotes);
    setConfirmFix(false);
    setExportError('');
  }, [suite.identity]);

  // 扫描成功则按目录缓存；失败保留旧缓存
  useEffect(() => {
    if (job?.status !== 'done' || result?.action !== 'scan' || !result.folder) return;
    lastScanByFolder.current[result.folder] = result;
  }, [job?.status, job?.id, result]);

  const cachedScan = folder.trim()
    ? Object.values(lastScanByFolder.current).find((item) => {
      const a = String(item.folder || '').replace(/\\/g, '/').toLowerCase();
      const b = folder.trim().replace(/\\/g, '/').toLowerCase();
      return a === b || a.endsWith(`/tl`) && b.includes(a);
    })
    : undefined;
  const scanResult = (result?.action === 'scan' && job?.status === 'done' ? result : null)
    || (cachedScan && result?.action !== 'scan' ? cachedScan : null)
    || cachedScan
    || null;
  const canExport = Boolean(scanResult?.report !== undefined || status?.has_scan_report);

  async function pickFolder() {
    const context = suite.identityRef.current;
    const next = await window.renpy?.pickFolder?.(folder || undefined);
    if (next && context === suite.identityRef.current) setFolder(next);
  }

  async function pickExe() {
    const context = suite.identityRef.current;
    const next = await window.renpy?.pickFile?.({
      filters: [{ name: 'Executable', extensions: ['exe'] }],
    });
    if (next && context === suite.identityRef.current) setGameExe(next);
  }

  async function exportReport() {
    if (!folderReady || !canExport) return;
    const context = suite.identityRef.current;
    setExportError('');
    const path = await window.renpy?.saveFile?.({
      defaultPath: 'error_report.xlsx',
      filters: [{ name: 'Excel', extensions: ['xlsx'] }],
    });
    if (!path || context !== suite.identityRef.current) return;
    try {
      const body: Record<string, unknown> = {
        folder,
        output_path: path,
        project_key: suite.currentKey() || '',
        owner_project_key: ownerKey,
      };
      if (scanResult?.report) body.report = scanResult.report;
      const payload = await request<{ success: boolean; message?: string; output_path?: string }>(
        '/api/error-repair/export',
        { method: 'POST', body: JSON.stringify(body) },
      );
      if (!payload.success) setExportError(payload.message || (uiLang === 'EN' ? 'Export failed' : '导出失败'));
    } catch (failure) {
      setExportError(failure instanceof Error ? failure.message : String(failure));
    }
  }

  const statusText = toolStatusText(t, suite, uiLang === 'EN' ? 'Idle' : '空闲');

  return (
    <div className="rb-page-scroll">
      {error ? <Banner tone="error">{error}</Banner> : null}
      {exportError ? <Banner tone="error">{exportError}</Banner> : null}
      <Banner tone="info">{copy.noBackup}</Banner>
      <Banner tone={active ? 'info' : job?.status === 'failed' ? 'error' : job?.status === 'done' ? 'success' : 'info'}>
        {statusText}
      </Banner>
      {active ? <Progress percent={Math.round((job?.progress ?? 0) * 100)} status="active" /> : null}

      <SettingsGroup title={copy.folderTitle} description={copy.folderDesc}>
        <Form.Item label={copy.folderLabel}>
          <Input.Group compact style={{ display: 'flex' }}>
            <Input value={folder} onChange={(e) => setFolder(e.target.value)} disabled={blocked} />
            <Button onClick={() => void pickFolder()} disabled={blocked}>{copy.browse}</Button>
          </Input.Group>
        </Form.Item>
      </SettingsGroup>

      <SettingsGroup title={copy.optionsTitle}>
        <Checkbox checked={fixIndent} disabled={blocked} onChange={(e) => setFixIndent(e.target.checked)}>{copy.fixIndent}</Checkbox>
        <Checkbox checked={fixIndentLevel} disabled={blocked} onChange={(e) => setFixIndentLevel(e.target.checked)}>{copy.fixIndentLevel}</Checkbox>
        <Checkbox checked={fixQuotes} disabled={blocked} onChange={(e) => setFixQuotes(e.target.checked)}>{copy.fixQuotes}</Checkbox>
        <Checkbox checked={fixDialogueQuotes} disabled={blocked} onChange={(e) => setFixDialogueQuotes(e.target.checked)}>{copy.fixDialogue}</Checkbox>
      </SettingsGroup>

      <SettingsGroup title={copy.lintTitle} description={copy.lintDesc}>
        <Form.Item label={copy.exeLabel}>
          <Input.Group compact style={{ display: 'flex' }}>
            <Input value={gameExe} onChange={(e) => setGameExe(e.target.value)} disabled={blocked} />
            <Button onClick={() => void pickExe()} disabled={blocked}>{copy.browse}</Button>
          </Input.Group>
        </Form.Item>
        <Button
          disabled={blocked || !folderReady || !gameExe.trim()}
          onClick={() => void suite.submit('/api/error-repair/lint', {
            folder,
            game_exe: gameExe,
            owner_project_key: ownerKey,
          })}
        >
          {copy.runLint}
        </Button>
      </SettingsGroup>

      <div className="rb-tool-actions">
        <Button
          disabled={blocked || !folderReady}
          onClick={() => void suite.submit('/api/error-repair/scan', {
            folder,
            check_indent: fixIndent,
            check_indent_level: fixIndentLevel,
            owner_project_key: ownerKey,
          })}
        >
          {copy.scan}
        </Button>
        <Button type="primary" disabled={blocked || !folderReady} onClick={() => setConfirmFix(true)}>
          {copy.fix}
        </Button>
        <Button disabled={blocked || !canExport} onClick={() => void exportReport()}>
          {copy.export}
        </Button>
      </div>

      {scanResult?.action === 'scan' || scanResult?.report ? (
        <Banner tone="info">{formatScanSummary(scanResult, uiLang)}</Banner>
      ) : null}
      {result?.action === 'fix' && job?.status === 'done' ? (
        <Banner tone={result.partial ? 'warning' : 'success'}>{formatFixSummary(result, uiLang)}</Banner>
      ) : null}
      {result?.action === 'lint' && job?.status === 'done' ? (
        <Banner tone="info">
          {uiLang === 'EN'
            ? `Lint: ${result.error_count ?? 0} issue(s)${result.lint_errors_path ? ` → ${result.lint_errors_path}` : ''}`
            : `Lint：${result.error_count ?? 0} 条${result.lint_errors_path ? ` → ${result.lint_errors_path}` : ''}`}
        </Banner>
      ) : null}

      {confirmFix ? (
        <Dialog
          title={copy.fix}
          onConfirm={() => {
            setConfirmFix(false);
            void suite.submit('/api/error-repair/fix', {
              folder,
              fix_indent: fixIndent,
              fix_indent_level: fixIndentLevel,
              fix_quotes: fixQuotes,
              fix_dialogue_quotes: fixDialogueQuotes,
              confirm: true,
              owner_project_key: ownerKey,
            });
          }}
          onCancel={() => setConfirmFix(false)}
        >
          <p>{copy.fixConfirm}</p>
        </Dialog>
      ) : null}
    </div>
  );
}
