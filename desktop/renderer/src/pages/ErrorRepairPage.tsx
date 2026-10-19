/**
 * 脚本修复（原「错误修复」+「代码格式化」合一）：
 * 主按钮「扫描并修复」一次完成 分类扫描 → 修安全集 → 处理残留 tl/<lang>_new → 复扫；
 * 次级「仅扫描」只看问题分组；另有报告导出与深度 lint 卡片。结果按
 * 已自动修复 / 需人工处理 / 环境问题 三组展示，清单只取后端 manual_sample（≤10 条）。
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Checkbox, Form, Input, Progress, Space, Tag } from 'antd';

import { request } from '../api';
import {
  ERROR_REPAIR_DEFAULTS,
  buildEnvironmentFixBody,
  errorRepairOwnerProjectKey,
  errorRepairStatusPath,
  fixTone,
  formatRepairSummary,
  formatScanSummary,
  formatTypeBreakdown,
  repairTypeLabel,
  scanIsActionable,
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

interface RepairIssue {
  file: string;
  line: number;
  type: string;
  message?: string;
  fixable?: boolean;
}

interface RepairEnvIssue {
  kind?: string;
  type?: string;
  path: string;
  language?: string;
  message?: string;
  issue_count?: number;
  actions?: string[];
}

interface RepairEnvFix {
  path: string;
  action?: string;
  ok?: boolean;
  message?: string;
  backup?: string;
}

type EnvAction = 'merge' | 'move';

interface RepairResult extends ToolResultBase {
  folder?: string;
  success?: boolean;
  // 扫描
  report?: Record<string, Array<Record<string, unknown>>>;
  has_scan_report?: boolean;
  scanned_files?: number;
  total_files?: number;
  affected_files?: number;
  total_issues?: number;
  issues_by_type?: Record<string, number>;
  fixable_issues?: number;
  manual_issues?: number;
  environment_issues?: RepairEnvIssue[];
  manual_sample?: RepairIssue[];
  // 修复
  fixed_files?: number;
  fixed_items?: number;
  failed_files?: number;
  fixed_by_type?: Record<string, number>;
  environment_fixes?: RepairEnvFix[];
  /** 复扫未完成时为 null：剩余数量未知。 */
  remaining_issues?: number | null;
  remaining_by_type?: Record<string, number>;
  rescan_skipped?: boolean;
  // lint
  errors?: Array<Record<string, unknown>>;
  error_count?: number;
  lint_errors_path?: string;
}

interface RepairStatus {
  project_key?: string;
  folder?: string;
  owner_project_key?: string;
  has_scan_report?: boolean;
  owner_identity?: string[];
  job?: ToolJob<RepairResult> | null;
}

const KINDS = ['error_repair_scan', 'error_repair_fix', 'error_repair_lint'] as const;

type RepairOptions = typeof ERROR_REPAIR_DEFAULTS;

const COPY = {
  ZH: {
    folderTitle: '翻译目录',
    folderDesc: '选择 game/tl/<语言> 或包含生成 .rpy 的目录',
    folderLabel: '翻译目录',
    browse: '浏览',
    optionsTitle: '修复选项',
    optionsDesc: '默认只勾安全项；高级项可能误改文件，建议先备份再勾选。',
    groupFormat: '格式化',
    groupRepair: '修复',
    keepComments: '保留注释',
    keepCommentsHint: '注释始终保留，本项不可关闭。',
    fixIndent: 'Tab 转空格',
    fixIndentHint: '行首 Tab 按层级替换为 4 个空格。',
    fixTrailingSpaces: '移除行尾空格',
    fixTrailingHint: '删除行尾多余空白，不改动译文内容。',
    fixEmptyBlocks: '空翻译块',
    fixEmptyBlocksHint: '删除没有译文的 translate strings 块。',
    fixDuplicates: '重复译文',
    fixDuplicatesHint: '合并 old/new 相同或重复的条目。',
    fixDialogueQuotes: '对话引号未转义',
    fixDialogueQuotesHint: '为对话里的双引号补上反斜杠转义。',
    fixIndentLevel: '缩进层级',
    fixIndentLevelHint: '按父块回退缩进；嵌套语句较多时可能误改，建议先备份。',
    fixQuotes: '引号规范',
    fixQuotesHint: '把外层引号统一为 “ ”；可能改动原文标点，建议先备份。',
    advanced: '高级',
    scanFix: '扫描并修复',
    scanOnly: '仅扫描',
    exportReport: '导出报告',
    cancelTask: '取消任务',
    scanHelp: '扫描只读；「扫描并修复」会先分类，再修安全项、处理残留增量目录，最后复扫。',
    confirmTitle: '确认修复',
    confirmBody: '将按勾选项修改 .rpy，并在修改前为每个有改动的文件写 .bak 备份；检测到残留增量目录时会先把 tl/<语言> 与 tl/<语言>_new 打包备份到项目的 _renpybox_backup，再合并并删除增量目录。高级项（缩进层级、引号规范）可能误改，修复后请核对结果。继续？',
    scanTitle: '扫描结果',
    fixTitle: '修复结果',
    fixedGroup: '已自动修复',
    filesUnit: '个文件',
    itemsUnit: '处',
    failedUnit: '个文件失败',
    manualGroup: '需人工处理',
    envGroup: '环境问题（残留增量目录）',
    nothingFixed: '没有需要修改的内容。',
    manualCount: '{count} 条',
    envMerge: '合并到主目录',
    envMove: '移出游戏目录',
    envMerged: '已合并',
    envMoved: '已移出',
    envFailed: '处理失败',
    envNone: '没有残留增量目录。',
    envConfirmTitle: '确认处理环境问题',
    envConfirmMerge: '只处理这一个增量目录：先把 tl/<语言> 与 tl/<语言>_new 完整打包到项目的 _renpybox_backup（备份失败则不合并），再把译文合并进 tl/<语言> 并删除该增量目录。继续？',
    envConfirmMove: '只处理这一个增量目录：将其移动到项目的 _renpybox_backup（不删除文件），之后可手动检查。继续？',
    sampleMore: '另有 {count} 条，可导出报告查看。',
    copied: '已复制路径',
    copyFailed: '复制路径失败',
    copyPath: '点击复制路径',
    rescanSkipped: '修复或复扫未完成，剩余问题数量未知，请重新扫描。',
    remainingUnknown: '未知',
    idle: '空闲',
    lintTitle: '深度 Lint 检查',
    lintDesc: "调用 Ren'Py 内置 lint 命令进行深度语法检查",
    exeLabel: '游戏主程序',
    runLint: '执行 Lint 检查',
    exportFailed: '导出失败',
  },
  EN: {
    folderTitle: 'Translation Folder',
    folderDesc: 'Select game/tl/<language> or a folder with generated .rpy files',
    folderLabel: 'Translation Folder',
    browse: 'Browse',
    optionsTitle: 'Repair Options',
    optionsDesc: 'Only safe options are on by default. Advanced options may alter files unexpectedly; back up first.',
    groupFormat: 'Formatting',
    groupRepair: 'Repairs',
    keepComments: 'Keep comments',
    keepCommentsHint: 'Comments are always kept; this cannot be turned off.',
    fixIndent: 'Tabs to spaces',
    fixIndentHint: 'Replace leading tabs with 4 spaces per level.',
    fixTrailingSpaces: 'Trim trailing spaces',
    fixTrailingHint: 'Remove trailing whitespace without touching the text.',
    fixEmptyBlocks: 'Empty blocks',
    fixEmptyBlocksHint: 'Delete translate strings blocks that have no translation.',
    fixDuplicates: 'Duplicate strings',
    fixDuplicatesHint: 'Merge entries whose old and new text are identical or repeated.',
    fixDialogueQuotes: 'Unescaped dialogue quotes',
    fixDialogueQuotesHint: 'Escape double quotes inside dialogue.',
    fixIndentLevel: 'Indentation level',
    fixIndentLevelHint: 'Rewind indentation to the parent block; may misfire on deeply nested statements, back up first.',
    fixQuotes: 'Quote normalization',
    fixQuotesHint: 'Normalize outer quotes to “ ”; may change original punctuation, back up first.',
    advanced: 'Advanced',
    scanFix: 'Scan & repair',
    scanOnly: 'Scan only',
    exportReport: 'Export report',
    cancelTask: 'Cancel task',
    scanHelp: 'Scanning is read-only. "Scan & repair" classifies issues, fixes the safe set, handles leftover incremental folders, then rescans.',
    confirmTitle: 'Confirm repair',
    confirmBody: 'The selected repairs will modify .rpy files and write a .bak backup for every changed file first. Leftover incremental folders are merged after tl/<language> and tl/<language>_new are archived into the project\'s _renpybox_backup; the incremental folder is then removed. Advanced options (indentation level, quote normalization) may misfire; review the result afterward. Continue?',
    scanTitle: 'Scan result',
    fixTitle: 'Repair result',
    fixedGroup: 'Fixed automatically',
    filesUnit: 'file(s)',
    itemsUnit: 'change(s)',
    failedUnit: 'file(s) failed',
    manualGroup: 'Needs manual work',
    envGroup: 'Environment issues (leftover incremental folders)',
    nothingFixed: 'Nothing needed changes.',
    manualCount: '{count} issue(s)',
    envMerge: 'Merge into main folder',
    envMove: 'Move out of game folder',
    envMerged: 'Merged',
    envMoved: 'Moved',
    envFailed: 'Failed',
    envNone: 'No leftover incremental folders.',
    envConfirmTitle: 'Confirm environment fix',
    envConfirmMerge: 'Only this incremental folder is handled: tl/<language> and tl/<language>_new are first archived into the project\'s _renpybox_backup (no merge if the backup fails), then merged into tl/<language> and the incremental folder is removed. Continue?',
    envConfirmMove: 'Only this incremental folder is handled: it is moved into the project\'s _renpybox_backup (files are not deleted). Continue?',
    sampleMore: '{count} more issue(s); export the report to see all of them.',
    copied: 'Path copied',
    copyFailed: 'Could not copy the path',
    copyPath: 'Click to copy the path',
    rescanSkipped: 'The repair or rescan did not finish; remaining issues are unknown. Please scan again.',
    remainingUnknown: 'unknown',
    idle: 'Idle',
    lintTitle: 'Deep Lint Check',
    lintDesc: "Run Ren'Py's built-in lint command for a deeper syntax check",
    exeLabel: 'Game Executable',
    runLint: 'Run Lint Check',
    exportFailed: 'Export failed',
  },
} as const;

type Copy = { [Key in keyof typeof COPY.ZH]: string };
type Fill = (text: string, values: Record<string, string | number>) => string;

const fill: Fill = (text, values) =>
  Object.entries(values).reduce((acc, [key, value]) => acc.replace(`{${key}}`, String(value)), text);

/** 目录比较统一分隔符与大小写，避免同一目录因写法不同丢缓存。 */
function normalizeFolder(path: string): string {
  return String(path || '').replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase();
}

/** 清单里只显示末两段路径，完整路径放在 title 与复制内容里。 */
function shortPath(path: string): string {
  const parts = String(path || '').split(/[\\/]/).filter(Boolean);
  return parts.slice(-2).join('/') || String(path || '');
}

function advancedLabel(label: string, copy: Copy): string {
  return `${label}（${copy.advanced}）`;
}

/** 类型明细 chips：数据来自 issues_by_type / remaining_by_type，title 里给一行可读汇总。 */
function TypeChips(props: { counts?: Record<string, number>; lang: 'ZH' | 'EN' }) {
  const { counts, lang } = props;
  const rows = Object.entries(counts ?? {})
    .map(([type, count]) => ({ type, count: Number(count ?? 0) }))
    .filter((row) => Number.isFinite(row.count) && row.count > 0)
    .sort((left, right) => right.count - left.count);
  if (!rows.length) return null;
  return (
    <div title={formatTypeBreakdown(counts, lang)}>
      <Space size={[6, 6]} wrap>
        {rows.map((row) => (
          <Tag key={row.type}>{`${repairTypeLabel(row.type, lang)} ${row.count}`}</Tag>
        ))}
      </Space>
    </div>
  );
}

/** 需人工清单：最多 10 条，点文件行复制完整路径；不打开编辑器。 */
function IssueSample(props: {
  issues?: RepairIssue[];
  total: number;
  lang: 'ZH' | 'EN';
  uiCopy: Copy;
  onCopy: (issue: RepairIssue) => void;
}) {
  const { issues, total, lang, uiCopy, onCopy } = props;
  const items = Array.isArray(issues) ? issues : [];
  if (!items.length) return null;
  const more = total - items.length;
  return (
    <>
      <div className="rb-quality-items">
        {items.map((issue, index) => (
          <div
            key={`${issue.file}:${issue.line}:${index}`}
            style={{ display: 'flex', gap: 8, alignItems: 'baseline', minWidth: 0 }}
          >
            <Button
              type="link"
              size="small"
              style={{ padding: 0, height: 'auto', fontFamily: 'ui-monospace, monospace' }}
              title={`${uiCopy.copyPath}: ${issue.file}:${issue.line}`}
              onClick={() => onCopy(issue)}
            >
              {`${shortPath(issue.file)}:${issue.line}`}
            </Button>
            <span className="rb-setting-desc" style={{ minWidth: 0 }}>
              {issue.message || repairTypeLabel(issue.type, lang)}
            </span>
          </div>
        ))}
      </div>
      {more > 0 ? (
        <div className="rb-metric-note">{fill(uiCopy.sampleMore, { count: more })}</div>
      ) : null}
    </>
  );
}

function OptionItem(props: {
  label: string;
  hint: string;
  checked: boolean;
  disabled?: boolean;
  onChange?: (checked: boolean) => void;
}) {
  const { label, hint, checked, disabled, onChange } = props;
  return (
    <div style={{ flex: '1 1 100%', display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
      <Checkbox
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange?.(event.target.checked)}
      >
        {label}
      </Checkbox>
      <span className="rb-setting-desc">{hint}</span>
    </div>
  );
}

function OptionGroupLabel(props: { text: string }) {
  return <div className="rb-setting-title" style={{ flex: '1 1 100%' }}>{props.text}</div>;
}

function EnvironmentIssueCard(props: {
  issue: RepairEnvIssue;
  uiCopy: Copy;
  disabled: boolean;
  onAction: (action: EnvAction) => void;
}) {
  const { issue, uiCopy, disabled, onAction } = props;
  const actions = Array.isArray(issue.actions) ? issue.actions : ['merge', 'move'];
  return (
    <div className="rb-panel" style={{ display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 }}>
      <div className="rb-setting-title">
        {`${issue.language || issue.type || ''} · ${issue.issue_count ?? 0}`}
      </div>
      <div className="rb-setting-desc rb-path" title={issue.path}>{issue.path}</div>
      {issue.message ? <div className="rb-setting-desc">{issue.message}</div> : null}
      <div className="rb-tool-actions">
        {actions.includes('merge') ? (
          <Button size="small" type="primary" disabled={disabled} onClick={() => onAction('merge')}>
            {uiCopy.envMerge}
          </Button>
        ) : null}
        {actions.includes('move') ? (
          <Button size="small" disabled={disabled} onClick={() => onAction('move')}>
            {uiCopy.envMove}
          </Button>
        ) : null}
      </div>
    </div>
  );
}

function EnvironmentFixRow(props: { fix: RepairEnvFix; uiCopy: Copy }) {
  const { fix, uiCopy } = props;
  const moved = fix.action === 'move';
  const failed = fix.ok === false;
  const actionText = moved ? uiCopy.envMoved : uiCopy.envMerged;
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'baseline', flexWrap: 'wrap', minWidth: 0 }}>
      <Tag color={failed ? 'error' : 'success'}>{failed ? uiCopy.envFailed : actionText}</Tag>
      <span className="rb-setting-desc rb-path" title={fix.path} style={{ flex: 1, minWidth: 0 }}>
        {fix.path}
      </span>
      {fix.message ? <span className="rb-setting-desc">{fix.message}</span> : null}
    </div>
  );
}

export function ErrorRepairPage(props: { state: AppState }) {
  const { state } = props;
  const t = useT();
  const uiLang: 'ZH' | 'EN' = state.bootLanguage === 'EN' ? 'EN' : 'ZH';
  const uiCopy = COPY[uiLang];
  const [folder, setFolder] = useState('');
  const [gameExe, setGameExe] = useState('');
  const [options, setOptions] = useState<RepairOptions>({ ...ERROR_REPAIR_DEFAULTS });
  const [confirmFix, setConfirmFix] = useState(false);
  // 卡片操作只针对该卡片的残留目录；路径随请求下发，由后端对照本次扫描校验。
  const [envAction, setEnvAction] = useState<{ action: EnvAction; path: string } | null>(null);
  const [exportError, setExportError] = useState('');
  // 按目录身份保留上次成功扫描，失败不清
  const lastScanByFolder = useRef<Record<string, RepairResult>>({});

  const statusPath = useMemo(() => errorRepairStatusPath(folder), [folder]);
  const suite = useProjectToolJob<RepairResult, RepairStatus>(state, statusPath, KINDS, folder);
  const { keyReady, job, result, active, error, busy, status } = suite;
  const ownerKey = errorRepairOwnerProjectKey(status);
  const engineBusy = state.translation.engine_status !== 'IDLE'
    || state.translation.stop_barrier
    || state.translation.single_tasks;
  const blocked = busy || engineBusy || !keyReady || state.link !== 'open';
  const folderReady = Boolean(folder.trim());

  useEffect(() => {
    setFolder('');
    setGameExe('');
    setOptions({ ...ERROR_REPAIR_DEFAULTS });
    setConfirmFix(false);
    setEnvAction(null);
    setExportError('');
  }, [suite.identity]);

  // 扫描成功则按目录缓存；失败保留旧缓存
  useEffect(() => {
    if (job?.status !== 'done' || result?.action !== 'scan' || !result.folder) return;
    lastScanByFolder.current[normalizeFolder(result.folder)] = result;
  }, [job?.status, job?.id, result]);

  const done = job?.status === 'done';
  const fixView = done && result?.action === 'fix' ? result : null;
  const currentScan = done && result?.action === 'scan' ? result : null;
  const cachedScan = folder.trim() ? lastScanByFolder.current[normalizeFolder(folder)] : undefined;
  const scanView = fixView ? null : currentScan ?? cachedScan ?? null;
  const lintView = done && result?.action === 'lint' ? result : null;
  const canExport = Boolean(status?.has_scan_report);

  function setOption(key: keyof RepairOptions, value: boolean) {
    setOptions((previous) => Object.assign({}, previous, { [key]: value }));
  }

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
      const payload = await request<{ success: boolean; message?: string; output_path?: string }>(
        '/api/error-repair/export',
        { method: 'POST', body: JSON.stringify(body) },
      );
      if (!payload.success) setExportError(payload.message || uiCopy.exportFailed);
    } catch (failure) {
      setExportError(failure instanceof Error ? failure.message : String(failure));
    }
  }

  function scanOnly() {
    void suite.submit('/api/error-repair/scan', {
      folder,
      check_indent: options.fixIndent,
      check_indent_level: options.fixIndentLevel,
      owner_project_key: ownerKey,
    });
  }

  function runFix() {
    void suite.submit('/api/error-repair/fix', {
      folder,
      fix_indent: options.fixIndent,
      fix_trailing_spaces: options.fixTrailingSpaces,
      fix_empty_blocks: options.fixEmptyBlocks,
      fix_duplicates: options.fixDuplicates,
      fix_dialogue_quotes: options.fixDialogueQuotes,
      fix_indent_level: options.fixIndentLevel,
      fix_quotes: options.fixQuotes,
      fix_environment: true,
      confirm: true,
      owner_project_key: ownerKey,
    });
  }

  /** 只处理选中卡片的环境问题：fix_* 全关，fix_environment + environment_action + environment_path。 */
  function runEnvFix(action: EnvAction, path: string) {
    void suite.submit('/api/error-repair/fix', buildEnvironmentFixBody({ folder, action, path, ownerKey }));
  }

  function copyIssue(issue: RepairIssue) {
    void navigator.clipboard.writeText(`${issue.file}:${issue.line}`)
      .then(() => state.pushToast('success', uiCopy.copied))
      .catch(() => state.pushToast('warning', uiCopy.copyFailed));
  }

  const statusText = toolStatusText(t, suite, uiCopy.idle);
  const scanEnv: RepairEnvIssue[] = Array.isArray(scanView?.environment_issues)
    ? scanView.environment_issues
    : [];
  const envFixes: RepairEnvFix[] = Array.isArray(fixView?.environment_fixes)
    ? fixView.environment_fixes
    : [];

  return (
    <div className="rb-page-scroll">
      {error ? <Banner tone="error">{error}</Banner> : null}
      {exportError ? <Banner tone="error">{exportError}</Banner> : null}
      <Banner tone="info">{uiCopy.scanHelp}</Banner>
      <Banner
        tone={active ? 'info' : job?.status === 'failed' ? 'error' : job?.status === 'done' ? 'success' : 'info'}
      >
        {statusText}
      </Banner>
      {active ? <Progress percent={Math.round((job?.progress ?? 0) * 100)} status="active" /> : null}

      <SettingsGroup title={uiCopy.folderTitle} description={uiCopy.folderDesc}>
        <Form.Item label={uiCopy.folderLabel}>
          <Space.Compact block>
            <Input value={folder} onChange={(e) => setFolder(e.target.value)} disabled={blocked} />
            <Button onClick={() => void pickFolder()} disabled={blocked}>{uiCopy.browse}</Button>
          </Space.Compact>
        </Form.Item>
      </SettingsGroup>

      <SettingsGroup title={uiCopy.optionsTitle} description={uiCopy.optionsDesc}>
        <OptionGroupLabel text={uiCopy.groupFormat} />
        <OptionItem
          label={uiCopy.keepComments}
          hint={uiCopy.keepCommentsHint}
          checked
          disabled
        />
        <OptionItem
          label={uiCopy.fixIndent}
          hint={uiCopy.fixIndentHint}
          checked={options.fixIndent}
          disabled={blocked}
          onChange={(checked) => setOption('fixIndent', checked)}
        />
        <OptionItem
          label={uiCopy.fixTrailingSpaces}
          hint={uiCopy.fixTrailingHint}
          checked={options.fixTrailingSpaces}
          disabled={blocked}
          onChange={(checked) => setOption('fixTrailingSpaces', checked)}
        />
        <OptionGroupLabel text={uiCopy.groupRepair} />
        <OptionItem
          label={uiCopy.fixEmptyBlocks}
          hint={uiCopy.fixEmptyBlocksHint}
          checked={options.fixEmptyBlocks}
          disabled={blocked}
          onChange={(checked) => setOption('fixEmptyBlocks', checked)}
        />
        <OptionItem
          label={uiCopy.fixDuplicates}
          hint={uiCopy.fixDuplicatesHint}
          checked={options.fixDuplicates}
          disabled={blocked}
          onChange={(checked) => setOption('fixDuplicates', checked)}
        />
        <OptionItem
          label={uiCopy.fixDialogueQuotes}
          hint={uiCopy.fixDialogueQuotesHint}
          checked={options.fixDialogueQuotes}
          disabled={blocked}
          onChange={(checked) => setOption('fixDialogueQuotes', checked)}
        />
        <OptionItem
          label={advancedLabel(uiCopy.fixIndentLevel, uiCopy)}
          hint={uiCopy.fixIndentLevelHint}
          checked={options.fixIndentLevel}
          disabled={blocked}
          onChange={(checked) => setOption('fixIndentLevel', checked)}
        />
        <OptionItem
          label={advancedLabel(uiCopy.fixQuotes, uiCopy)}
          hint={uiCopy.fixQuotesHint}
          checked={options.fixQuotes}
          disabled={blocked}
          onChange={(checked) => setOption('fixQuotes', checked)}
        />
      </SettingsGroup>

      <div className="rb-tool-actions">
        <Button
          type="primary"
          loading={suite.submitting}
          disabled={blocked || !folderReady}
          onClick={() => setConfirmFix(true)}
        >
          {uiCopy.scanFix}
        </Button>
        <Button disabled={blocked || !folderReady} onClick={scanOnly}>{uiCopy.scanOnly}</Button>
        <Button disabled={blocked || !canExport} onClick={() => void exportReport()}>
          {uiCopy.exportReport}
        </Button>
        {active ? (
          <Button
            disabled={suite.cancelling || job?.cancel_requested}
            onClick={() => void suite.cancel()}
          >
            {uiCopy.cancelTask}
          </Button>
        ) : null}
      </div>

      {scanView ? (
        <SettingsGroup title={uiCopy.scanTitle}>
          <Banner tone={scanIsActionable(scanView) ? 'info' : 'success'}>
            {formatScanSummary(scanView, uiLang)}
          </Banner>
          <div style={{ flex: '1 1 100%', minWidth: 0 }}>
            <TypeChips counts={scanView.issues_by_type} lang={uiLang} />
          </div>
          {Number(scanView.manual_issues ?? 0) > 0 ? (
            <div style={{ flex: '1 1 100%', display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 }}>
              <div className="rb-setting-title">
                {`${uiCopy.manualGroup} · ${fill(uiCopy.manualCount, { count: scanView.manual_issues ?? 0 })}`}
              </div>
              <IssueSample
                issues={scanView.manual_sample}
                total={Number(scanView.manual_issues ?? 0)}
                lang={uiLang}
                uiCopy={uiCopy}
                onCopy={copyIssue}
              />
            </div>
          ) : null}
          {scanEnv.length > 0 ? (
            <div style={{ flex: '1 1 100%', display: 'flex', flexDirection: 'column', gap: 8, minWidth: 0 }}>
              <div className="rb-setting-title">{uiCopy.envGroup}</div>
              {scanEnv.map((issue) => (
                <EnvironmentIssueCard
                  key={`${issue.path}:${issue.language ?? ''}`}
                  issue={issue}
                  uiCopy={uiCopy}
                  disabled={blocked}
                  onAction={(action) => setEnvAction({ action, path: issue.path })}
                />
              ))}
            </div>
          ) : null}
        </SettingsGroup>
      ) : null}

      {fixView ? (
        <SettingsGroup title={uiCopy.fixTitle}>
          <Banner tone={fixTone(fixView)}>{formatRepairSummary(fixView, uiLang)}</Banner>
          <div style={{ flex: '1 1 100%', display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 }}>
            <div className="rb-setting-title">{uiCopy.fixedGroup}</div>
            <div
              className="rb-quality-summary"
              style={{
                gridTemplateColumns: `repeat(${Number(fixView.failed_files ?? 0) > 0 ? 3 : 2}, minmax(0, 1fr))`,
                margin: '4px 0',
              }}
            >
              <strong>{`${fixView.fixed_files ?? 0} ${uiCopy.filesUnit}`}</strong>
              <strong>{`${fixView.fixed_items ?? 0} ${uiCopy.itemsUnit}`}</strong>
              {Number(fixView.failed_files ?? 0) > 0
                ? <strong>{`${fixView.failed_files} ${uiCopy.failedUnit}`}</strong>
                : null}
            </div>
            {Number(fixView.fixed_items ?? 0) > 0 ? (
              <div className="rb-setting-desc">{formatTypeBreakdown(fixView.fixed_by_type, uiLang)}</div>
            ) : (
              <div className="rb-setting-desc">{uiCopy.nothingFixed}</div>
            )}
          </div>
          <div style={{ flex: '1 1 100%', display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 }}>
            <div className="rb-setting-title">
              {`${uiCopy.manualGroup} · ${fixView.rescan_skipped || fixView.remaining_issues == null
                ? uiCopy.remainingUnknown
                : fill(uiCopy.manualCount, { count: fixView.remaining_issues })}`}
            </div>
            {fixView.rescan_skipped ? (
              <div className="rb-metric-note">{uiCopy.rescanSkipped}</div>
            ) : null}
            <div style={{ minWidth: 0 }}>
              <TypeChips counts={fixView.remaining_by_type} lang={uiLang} />
            </div>
            <IssueSample
              issues={fixView.manual_sample}
              total={Number(fixView.remaining_issues ?? 0)}
              lang={uiLang}
              uiCopy={uiCopy}
              onCopy={copyIssue}
            />
          </div>
          <div style={{ flex: '1 1 100%', display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 }}>
            <div className="rb-setting-title">{uiCopy.envGroup}</div>
            {envFixes.length > 0
              ? envFixes.map((fix, index) => (
                <EnvironmentFixRow key={`${fix.path}:${index}`} fix={fix} uiCopy={uiCopy} />
              ))
              : <div className="rb-setting-desc">{uiCopy.envNone}</div>}
          </div>
        </SettingsGroup>
      ) : null}

      {lintView ? (
        <Banner tone="info">
          {uiLang === 'EN'
            ? `Lint: ${lintView.error_count ?? 0} issue(s)${lintView.lint_errors_path ? ` → ${lintView.lint_errors_path}` : ''}`
            : `Lint：${lintView.error_count ?? 0} 条${lintView.lint_errors_path ? ` → ${lintView.lint_errors_path}` : ''}`}
        </Banner>
      ) : null}

      <SettingsGroup title={uiCopy.lintTitle} description={uiCopy.lintDesc}>
        <Form.Item label={uiCopy.exeLabel}>
          <Space.Compact block>
            <Input value={gameExe} onChange={(e) => setGameExe(e.target.value)} disabled={blocked} />
            <Button onClick={() => void pickExe()} disabled={blocked}>{uiCopy.browse}</Button>
          </Space.Compact>
        </Form.Item>
        <Button
          disabled={blocked || !folderReady || !gameExe.trim()}
          onClick={() => void suite.submit('/api/error-repair/lint', {
            folder,
            game_exe: gameExe,
            owner_project_key: ownerKey,
          })}
        >
          {uiCopy.runLint}
        </Button>
      </SettingsGroup>

      {confirmFix ? (
        <Dialog
          title={uiCopy.confirmTitle}
          confirmText={uiCopy.scanFix}
          onConfirm={() => {
            setConfirmFix(false);
            runFix();
          }}
          onCancel={() => setConfirmFix(false)}
        >
          <p>{uiCopy.confirmBody}</p>
        </Dialog>
      ) : null}

      {envAction ? (
        <Dialog
          title={uiCopy.envConfirmTitle}
          onConfirm={() => {
            const { action, path } = envAction;
            setEnvAction(null);
            runEnvFix(action, path);
          }}
          onCancel={() => setEnvAction(null)}
        >
          <p>{envAction.action === 'move' ? uiCopy.envConfirmMove : uiCopy.envConfirmMerge}</p>
          <p className="rb-path">{envAction.path}</p>
        </Dialog>
      ) : null}
    </div>
  );
}
