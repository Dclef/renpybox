/** 代码格式化：对齐 Qt5 FormatterPage（仅格式化，无预览/备份）。 */
import { useEffect, useMemo, useState } from 'react';
import { Button, Checkbox, Form, Input, Progress, Space } from 'antd';

import {
  FORMATTER_DEFAULTS,
  formatFormatterSummary,
  formatterOwnerProjectKey,
  formatterStatusPath,
} from '../formatterView.mjs';
import { useT } from '../i18n';
import type { AppState } from '../useAppState';
import { Banner, Dialog, SettingsGroup } from '../ui';
import {
  toolStatusText,
  useProjectToolJob,
  type ToolJob,
  type ToolResultBase,
} from './projectToolJob';

interface FormatResult extends ToolResultBase {
  success_count?: number;
  failed_files?: string[];
  total_files?: number;
  folder?: string;
  success?: boolean;
}

interface FormatStatus {
  project_key?: string;
  owner_project_key?: string;
  folder?: string;
  job?: ToolJob<FormatResult> | null;
}

const KINDS = ['formatter_format'] as const;

const COPY = {
  ZH: {
    folderTitle: '目录',
    folderDesc: '选择需要格式化的目录（递归处理 .rpy）',
    optionsTitle: '格式化选项',
    preserve: '保留注释（始终保留，不会删除）',
    fixIndent: '修复缩进（Tab 转空格）',
    trailing: '移除行尾空格',
    start: '开始格式化',
    confirm: '将直接改写目录下 .rpy，不会自动备份。继续？',
    browse: '浏览',
  },
  EN: {
    folderTitle: 'Folder',
    folderDesc: 'Select a folder to format (.rpy files recursively)',
    optionsTitle: 'Formatting Options',
    preserve: 'Preserve Comments (always kept; never deleted)',
    fixIndent: 'Fix Indentation (Convert Tabs to Spaces)',
    trailing: 'Remove Trailing Spaces',
    start: 'Start Formatting',
    confirm: 'Files will be modified in place with no automatic backup. Continue?',
    browse: 'Browse',
  },
} as const;

export function FormatterPage(props: { state: AppState }) {
  const { state } = props;
  const t = useT();
  const uiLang = state.bootLanguage === 'EN' ? 'EN' : 'ZH';
  const copy = COPY[uiLang];
  const [folder, setFolder] = useState('');
  const [preserveComments, setPreserveComments] = useState(FORMATTER_DEFAULTS.preserveComments);
  const [fixIndent, setFixIndent] = useState(FORMATTER_DEFAULTS.fixIndent);
  const [removeTrailing, setRemoveTrailing] = useState(FORMATTER_DEFAULTS.removeTrailing);
  const [confirmFormat, setConfirmFormat] = useState(false);

  const statusPath = useMemo(() => formatterStatusPath(folder), [folder]);
  const suite = useProjectToolJob<FormatResult, FormatStatus>(state, statusPath, KINDS, folder);
  const { keyReady, job, result, active, error, busy, status } = suite;
  const ownerKey = formatterOwnerProjectKey(status);
  const engineBusy = state.translation.engine_status !== 'IDLE' || state.translation.stop_barrier || state.translation.single_tasks;
  const blocked = busy || engineBusy || !keyReady || state.link !== 'open';
  const folderReady = Boolean(folder.trim());

  useEffect(() => {
    setFolder('');
    setPreserveComments(FORMATTER_DEFAULTS.preserveComments);
    setFixIndent(FORMATTER_DEFAULTS.fixIndent);
    setRemoveTrailing(FORMATTER_DEFAULTS.removeTrailing);
    setConfirmFormat(false);
  }, [suite.identity]);

  async function pickFolder() {
    const context = suite.identityRef.current;
    const next = await window.renpy?.pickFolder?.(folder || undefined);
    if (next && context === suite.identityRef.current) setFolder(next);
  }

  const statusText = toolStatusText(t, suite, uiLang === 'EN' ? 'Idle' : '空闲');

  return (
    <div className="rb-page-scroll">
      {error ? <Banner tone="error">{error}</Banner> : null}
      <Banner tone={active ? 'info' : job?.status === 'failed' ? 'error' : job?.status === 'done' ? 'success' : 'info'}>
        {statusText}
      </Banner>
      {active ? <Progress percent={Math.round((job?.progress ?? 0) * 100)} status="active" /> : null}

      <SettingsGroup title={copy.folderTitle} description={copy.folderDesc}>
        <Form.Item label={copy.folderTitle}>
          <Space.Compact block>
            <Input value={folder} disabled={blocked} onChange={(e) => setFolder(e.target.value)} />
            <Button onClick={() => void pickFolder()} disabled={blocked}>{copy.browse}</Button>
          </Space.Compact>
        </Form.Item>
      </SettingsGroup>

      <SettingsGroup title={copy.optionsTitle}>
        <Checkbox checked={preserveComments} disabled={blocked} onChange={(e) => setPreserveComments(e.target.checked)}>
          {copy.preserve}
        </Checkbox>
        <Checkbox checked={fixIndent} disabled={blocked} onChange={(e) => setFixIndent(e.target.checked)}>
          {copy.fixIndent}
        </Checkbox>
        <Checkbox checked={removeTrailing} disabled={blocked} onChange={(e) => setRemoveTrailing(e.target.checked)}>
          {copy.trailing}
        </Checkbox>
      </SettingsGroup>

      <div className="rb-tool-actions">
        <Button type="primary" disabled={blocked || !folderReady} onClick={() => setConfirmFormat(true)}>
          {copy.start}
        </Button>
      </div>

      {result?.action === 'format' && job?.status === 'done' ? (
        <Banner tone={result.partial ? 'warning' : 'success'}>
          {formatFormatterSummary(result, uiLang)}
        </Banner>
      ) : null}

      {confirmFormat ? (
        <Dialog
          title={copy.start}
          onConfirm={() => {
            setConfirmFormat(false);
            void suite.submit('/api/formatter/format', {
              folder,
              preserve_comments: preserveComments,
              fix_indent: fixIndent,
              remove_trailing: removeTrailing,
              confirm: true,
              owner_project_key: ownerKey,
            });
          }}
          onCancel={() => setConfirmFormat(false)}
        >
          <p>{copy.confirm}</p>
        </Dialog>
      ) : null}
    </div>
  );
}
