/** 安卓打包：对齐 Qt5 AndroidBuildPage，走 /api/android-build。SDK 任务无假停止。 */
import { useEffect, useMemo, useState } from 'react';
import { Button, Checkbox, Form, Input, Progress } from 'antd';

import { request } from '../api';
import {
  ANDROID_COPY,
  androidAppFieldsReady,
  androidConfigPayload,
  androidCopy,
  androidJobCancellable,
  androidOwnerProjectKey,
  androidSdkReady,
  androidStatusPath,
  appendArchiveSource,
  defaultAndroidForm,
  formatAndroidOutputs,
  sameAndroidPath,
} from '../androidBuildView.mjs';
import { useT } from '../i18n';
import type { AppState } from '../useAppState';
import { Banner, Dialog, SettingsGroup } from '../ui';
import {
  toolStatusText,
  useProjectToolJob,
  type ToolJob,
  type ToolResultBase,
} from './projectToolJob';

interface AndroidOutput {
  name?: string;
  path?: string;
  mtime?: number;
}

interface AndroidResult extends ToolResultBase {
  success?: boolean;
  open_bin?: boolean;
  rapt_bin?: string;
  outputs?: AndroidOutput[];
  output_names?: string[];
  new_output_names?: string[];
  outputs_include_history?: boolean;
  archive_path?: string;
  backup_path?: string;
  packed_count?: number;
  removed?: string[];
  skipped?: string[];
  failed?: string[];
  logs?: string[];
  cancellable?: boolean;
}

interface AndroidConfig {
  sdk_path?: string;
  app_name?: string;
  package_name?: string;
  version?: string;
  archive_source_dir?: string;
  shell_backup_enable?: boolean;
  shell_remove_dirs?: string;
  default_shell_remove_dirs?: string;
  dname?: string;
  update_always?: boolean;
  update_icons?: boolean;
}

interface AndroidStatus {
  project_key?: string;
  project_root?: string;
  owner_project_key?: string;
  owner_project_root?: string;
  game_dir?: string;
  keystore_exists?: boolean;
  rapt_bin?: string;
  rapt_bin_exists?: boolean;
  outputs?: AndroidOutput[];
  config?: AndroidConfig;
  job?: ToolJob<AndroidResult> | null;
  cancellable?: boolean;
}

type ConfirmKind = 'build' | 'shell' | null;

const KINDS = [
  'android_check_env',
  'android_install_sdk',
  'android_generate_keys',
  'android_build',
  'android_shell',
] as const;

export function AndroidBuildPage(props: { state: AppState }) {
  const { state } = props;
  const t = useT();
  const uiLang = state.bootLanguage === 'EN' ? 'EN' : 'ZH';
  const copy = (key: keyof typeof ANDROID_COPY) => androidCopy(ANDROID_COPY[key], uiLang);
  const [form, setForm] = useState(() => defaultAndroidForm());
  const [projectPath, setProjectPath] = useState('');
  const [confirm, setConfirm] = useState<ConfirmKind>(null);
  const [localError, setLocalError] = useState('');
  const [detectMsg, setDetectMsg] = useState('');

  // 手动目标 B 进入 statusPath，驱动 late 响应与 canonical 失效
  const statusPath = useMemo(() => androidStatusPath(projectPath), [projectPath]);
  const suite = useProjectToolJob<AndroidResult, AndroidStatus>(state, statusPath, KINDS);
  const { status, keyReady, job, result, active, error, busy } = suite;
  const ownerKey = androidOwnerProjectKey(status, suite.currentKey() || '');

  const engineBusy = state.translation.engine_status !== 'IDLE'
    || state.translation.stop_barrier
    || state.translation.single_tasks;
  const hasProject = Boolean(state.project?.renpy_project_path);
  const writeBlocked = busy || engineBusy || !keyReady || state.link !== 'open' || !hasProject;
  const fieldsReady = androidAppFieldsReady(form);
  const sdkReady = androidSdkReady(form);
  const actionBlocked = writeBlocked || !sdkReady;
  const cancellable = androidJobCancellable(job);

  useEffect(() => {
    setProjectPath(String(state.project?.renpy_project_path ?? ''));
    setConfirm(null);
    setLocalError('');
    setDetectMsg('');
  }, [state.project?.renpy_project_path]);

  useEffect(() => {
    if (!status?.config) return;
    setForm(defaultAndroidForm(status.config));
    // 仅在路径尚未手动改写时同步 status 根，避免冲掉手动 B
    if (status.project_root && !projectPath.trim()) {
      setProjectPath(status.project_root);
    }
  }, [status?.config, status?.project_root, suite.identity]);

  // 构建成功后自动打开 rapt/bin（对齐 Qt）
  useEffect(() => {
    if (!result?.open_bin || job?.status !== 'done') return;
    const path = result.rapt_bin || status?.rapt_bin;
    if (path) void window.renpy?.openPath?.(path);
  }, [job?.id, job?.status, result?.open_bin, result?.rapt_bin, status?.rapt_bin]);

  function patchForm(partial: Partial<typeof form>) {
    setForm((prev) => ({ ...prev, ...partial }));
  }

  async function pickSdk() {
    const context = suite.identityRef.current;
    const next = await window.renpy?.pickFolder?.(form.sdkPath || undefined);
    if (next && context === suite.identityRef.current) patchForm({ sdkPath: next });
  }

  async function pickProject() {
    const context = suite.identityRef.current;
    const next = await window.renpy?.pickFolder?.(projectPath || undefined);
    if (next && context === suite.identityRef.current) setProjectPath(next);
  }

  async function addArchiveFolder() {
    const context = suite.identityRef.current;
    const next = await window.renpy?.pickFolder?.(undefined);
    if (next && context === suite.identityRef.current) {
      patchForm({ archiveSourceDir: appendArchiveSource(form.archiveSourceDir, next) });
    }
  }

  async function runDetect(target: 'archive' | 'remove') {
    if (actionBlocked) return;
    const context = suite.identityRef.current;
    const pathAtStart = projectPath;
    setDetectMsg('');
    setLocalError('');
    try {
      const payload = await request<{
        value?: string;
        message?: string;
        cleared?: boolean;
        count?: number;
        project_root?: string;
      }>('/api/android-build/detect', {
        method: 'POST',
        body: JSON.stringify({
          // owner A + 手动 project_path B（与 Qt/API 角色一致）
          project_key: ownerKey || suite.currentKey() || '',
          project_path: pathAtStart,
          hints: form.shellRemoveDirs,
          target,
          current: target === 'archive' ? form.archiveSourceDir : form.shellRemoveDirs,
          replace: true,
        }),
      });
      // late：切项目/改路径后丢弃响应，避免污染新目标表单
      if (context !== suite.identityRef.current || !sameAndroidPath(pathAtStart, projectPath)) {
        return;
      }
      if (target === 'archive') patchForm({ archiveSourceDir: String(payload.value || '') });
      else patchForm({ shellRemoveDirs: String(payload.value || '') });
      setDetectMsg(payload.message || '');
    } catch (failure) {
      if (context !== suite.identityRef.current || !sameAndroidPath(pathAtStart, projectPath)) {
        return;
      }
      setLocalError(failure instanceof Error ? failure.message : String(failure));
    }
  }

  function payloadBase() {
    return androidConfigPayload(form, projectPath);
  }

  function envPayload(extra: Record<string, unknown> = {}) {
    return {
      project_path: projectPath,
      sdk_path: form.sdkPath,
      ...extra,
    };
  }

  function writeJson() {
    if (!fieldsReady) {
      setLocalError(copy('fillRequired'));
      return;
    }
    const key = ownerKey || suite.currentKey();
    if (!key || writeBlocked) return;
    const context = suite.identityRef.current;
    const pathAtStart = projectPath;
    setLocalError('');
    // 同步写入，不走 Job；对齐 Qt 即时写 android.json
    void request<{ message?: string }>('/api/android-build/write-json', {
      method: 'POST',
      body: JSON.stringify({ ...payloadBase(), project_key: key, persist: true }),
    }).then((payload) => {
      if (context !== suite.identityRef.current || !sameAndroidPath(pathAtStart, projectPath)) {
        return undefined;
      }
      setDetectMsg(payload.message || copy('writeJson'));
      return state.reloadTranslation();
    }).catch((failure) => {
      if (context !== suite.identityRef.current || !sameAndroidPath(pathAtStart, projectPath)) {
        return;
      }
      setLocalError(failure instanceof Error ? failure.message : String(failure));
    });
  }

  function startCheckEnv() {
    void suite.submit('/api/android-build/check-env', envPayload());
  }

  function startInstallSdk() {
    void suite.submit('/api/android-build/install-sdk', envPayload());
  }

  function startGenerateKeys() {
    void suite.submit('/api/android-build/generate-keys', envPayload({ dname: form.dname }));
  }

  function startBuild() {
    void suite.submit('/api/android-build/build', { ...payloadBase(), confirm: true });
  }

  function startShell() {
    void suite.submit('/api/android-build/make-shell', {
      project_path: projectPath,
      archive_source_dir: form.archiveSourceDir,
      shell_remove_dirs: form.shellRemoveDirs,
      shell_backup_enable: form.shellBackupEnable,
      sdk_path: form.sdkPath,
      app_name: form.appName,
      package_name: form.packageName,
      version: form.version,
      dname: form.dname,
      update_always: form.updateAlways,
      update_icons: form.updateIcons,
      confirm: true,
    });
  }

  async function openBin() {
    const context = suite.identityRef.current;
    setLocalError('');
    try {
      const payload = await request<{ path?: string }>('/api/android-build/open-bin', {
        method: 'POST',
        body: JSON.stringify({
          project_key: ownerKey || suite.currentKey() || '',
          project_path: projectPath,
          sdk_path: form.sdkPath,
        }),
      });
      if (context !== suite.identityRef.current) return;
      if (payload.path) await window.renpy?.openPath?.(payload.path);
    } catch (failure) {
      if (context !== suite.identityRef.current) return;
      setLocalError(failure instanceof Error ? failure.message : String(failure));
    }
  }

  const statusText = toolStatusText(t, suite, copy('idle'));
  const statusTone = active || suite.checking
    ? 'info'
    : job?.status === 'done'
      ? (result?.partial ? 'warning' : 'success')
      : job?.status === 'failed'
        ? (result?.written || result?.partial ? 'warning' : 'error')
        : 'info';
  const logs = result?.logs?.length ? result.logs : [];
  const outputNames = formatAndroidOutputs(result?.outputs || status?.outputs || []);
  const newNames = result?.new_output_names || [];

  return (
    <div className="rb-asset-page rb-page-scroll" data-rb-page="android-build">
      {error ? <Banner tone="error">{error}</Banner> : null}
      {localError ? <Banner tone="error">{localError}</Banner> : null}
      {!hasProject ? <Banner tone="warning">{copy('needsProject')}</Banner> : null}
      {detectMsg ? <Banner tone="info">{detectMsg}</Banner> : null}
      <Banner tone={statusTone}>{statusText}</Banner>
      {hasProject && status && !status.keystore_exists ? (
        <Banner tone="warning">{copy('keystoreMissing')}</Banner>
      ) : null}
      {active ? <Progress percent={0} status="active" aria-label={statusText} /> : null}

      <SettingsGroup title={copy('paths')} description={copy('pathsNote')}>
        <Form.Item label={copy('sdk')} style={{ marginBottom: 12 }}>
          <div className="rb-tool-actions" style={{ display: 'flex', gap: 8 }}>
            <Input
              value={form.sdkPath}
              onChange={(event) => patchForm({ sdkPath: event.target.value })}
              disabled={busy || !hasProject}
              data-rb-android-sdk="1"
            />
            <Button onClick={() => void pickSdk()} disabled={busy || !hasProject}>{copy('browse')}</Button>
          </div>
        </Form.Item>
        <Form.Item label={copy('project')} style={{ marginBottom: 0 }}>
          <div className="rb-tool-actions" style={{ display: 'flex', gap: 8 }}>
            <Input
              value={projectPath}
              onChange={(event) => setProjectPath(event.target.value)}
              disabled={busy || !hasProject}
              data-rb-android-project="1"
            />
            <Button onClick={() => void pickProject()} disabled={busy || !hasProject}>{copy('browse')}</Button>
          </div>
        </Form.Item>
      </SettingsGroup>

      <SettingsGroup title={copy('config')} description={copy('iconsHint')}>
        <Form.Item label={copy('appName')} style={{ marginBottom: 12 }}>
          <Input
            value={form.appName}
            onChange={(event) => patchForm({ appName: event.target.value })}
            disabled={busy || !hasProject}
            data-rb-android-app-name="1"
          />
        </Form.Item>
        <Form.Item label={copy('packageName')} style={{ marginBottom: 12 }}>
          <Input
            value={form.packageName}
            onChange={(event) => patchForm({ packageName: event.target.value })}
            disabled={busy || !hasProject}
            data-rb-android-package="1"
          />
        </Form.Item>
        <Form.Item label={copy('version')} style={{ marginBottom: 12 }}>
          <Input
            value={form.version}
            onChange={(event) => patchForm({ version: event.target.value })}
            disabled={busy || !hasProject}
            data-rb-android-version="1"
          />
        </Form.Item>
        {/* 隐藏字段：保留配置，不展示为高级区 */}
        <input type="hidden" data-rb-android-dname="1" value={form.dname} readOnly />
        <input type="hidden" data-rb-android-update-always="1" value={form.updateAlways ? '1' : '0'} readOnly />
        <input type="hidden" data-rb-android-update-icons="1" value={form.updateIcons ? '1' : '0'} readOnly />
        <div className="rb-tool-actions">
          <Button type="primary" onClick={() => writeJson()} disabled={actionBlocked || !fieldsReady} data-rb-android-write-json="1">
            {copy('writeJson')}
          </Button>
        </div>
      </SettingsGroup>

      <SettingsGroup title={copy('env')}>
        <div className="rb-tool-actions">
          <Button onClick={() => startCheckEnv()} disabled={actionBlocked} data-rb-android-check-env="1">
            {copy('checkEnv')}
          </Button>
          <Button type="primary" onClick={() => startInstallSdk()} disabled={actionBlocked} data-rb-android-install-sdk="1">
            {copy('installSdk')}
          </Button>
          <Button onClick={() => startGenerateKeys()} disabled={actionBlocked} data-rb-android-generate-keys="1">
            {copy('generateKeys')}
          </Button>
        </div>
      </SettingsGroup>

      <SettingsGroup title={copy('shell')} description={copy('shellHint')}>
        <Form.Item label={copy('archiveFolders')} style={{ marginBottom: 12 }}>
          <div className="rb-tool-actions" style={{ display: 'flex', gap: 8 }}>
            <Input
              value={form.archiveSourceDir}
              onChange={(event) => patchForm({ archiveSourceDir: event.target.value })}
              placeholder={copy('archivePlaceholder')}
              disabled={busy || !hasProject}
              data-rb-android-archive-source="1"
            />
            <Button onClick={() => void addArchiveFolder()} disabled={busy || !hasProject}>{copy('add')}</Button>
            <Button onClick={() => void runDetect('archive')} disabled={actionBlocked} data-rb-android-detect-archive="1">
              {copy('detect')}
            </Button>
          </div>
        </Form.Item>
        <div data-rb-android-backup="1" data-rb-android-backup-on={form.shellBackupEnable ? '1' : '0'}>
          <Checkbox
            checked={form.shellBackupEnable}
            onChange={(event) => patchForm({ shellBackupEnable: event.target.checked })}
            disabled={busy || !hasProject}
          >
            {copy('backupZip')}
          </Checkbox>
        </div>
        <Form.Item label={copy('cleanupFolders')} style={{ marginTop: 12, marginBottom: 12 }}>
          <div className="rb-tool-actions" style={{ display: 'flex', gap: 8 }}>
            <Input
              value={form.shellRemoveDirs}
              onChange={(event) => patchForm({ shellRemoveDirs: event.target.value })}
              placeholder={copy('cleanupPlaceholder')}
              disabled={busy || !hasProject}
              data-rb-android-remove-dirs="1"
            />
            <Button onClick={() => void runDetect('remove')} disabled={actionBlocked} data-rb-android-detect-remove="1">
              {copy('detect')}
            </Button>
          </div>
        </Form.Item>
        <div className="rb-tool-actions">
          <Button type="primary" onClick={() => setConfirm('shell')} disabled={actionBlocked} data-rb-android-make-shell="1">
            {copy('makeShell')}
          </Button>
        </div>
        {result?.action === 'shell' && (result.archive_path || result.backup_path) ? (
          <div data-rb-android-shell-result="1" style={{ marginTop: 12 }}>
            <Banner tone={result.partial ? 'warning' : 'success'}>
              {copy('shellResult')}: {result.message || ''}
              {result.archive_path ? ` archive=${result.archive_path}` : ''}
              {result.backup_path ? ` backup=${result.backup_path}` : ''}
              {typeof result.packed_count === 'number' ? ` packed=${result.packed_count}` : ''}
              {result.removed?.length ? ` removed=${result.removed.join(',')}` : ''}
              {result.failed?.length ? ` failed=${result.failed.join(',')}` : ''}
            </Banner>
          </div>
        ) : null}
      </SettingsGroup>

      <SettingsGroup title={copy('build')} description={copy('buildHint')}>
        <div className="rb-tool-actions">
          <Button
            type="primary"
            onClick={() => setConfirm('build')}
            disabled={actionBlocked || !fieldsReady || !status?.keystore_exists}
            data-rb-android-build="1"
          >
            {copy('startBuild')}
          </Button>
          <Button onClick={() => void openBin()} disabled={actionBlocked || !status?.rapt_bin_exists} data-rb-android-open-bin="1">
            {copy('openBin')}
          </Button>
        </div>
        {outputNames.length ? (
          <p className="card-description" data-rb-android-outputs="1">
            {copy('outputs')}: {outputNames.join(', ')}
          </p>
        ) : null}
        {newNames.length ? (
          <p className="card-description" data-rb-android-new-outputs="1">
            {copy('newOutputs')}: {newNames.join(', ')}
          </p>
        ) : null}
      </SettingsGroup>

      {logs.length ? (
        <SettingsGroup title={copy('logs')}>
          <pre data-rb-android-logs="1" style={{ whiteSpace: 'pre-wrap', maxHeight: 240, overflow: 'auto' }}>
            {logs.join('\n')}
          </pre>
        </SettingsGroup>
      ) : null}

      {/* 不展示停止：SDK 进程无真取消 */}
      {cancellable ? null : null}

      {confirm === 'build' ? (
        <Dialog
          title={copy('startBuild')}
          confirmText={copy('startBuild')}
          onConfirm={() => {
            setConfirm(null);
            startBuild();
          }}
          onCancel={() => setConfirm(null)}
        >
          <p>{copy('confirmBuild')}</p>
        </Dialog>
      ) : null}
      {confirm === 'shell' ? (
        <Dialog
          title={copy('makeShell')}
          confirmText={copy('makeShell')}
          onConfirm={() => {
            setConfirm(null);
            startShell();
          }}
          onCancel={() => setConfirm(null)}
        >
          <p>{copy('confirmShell')}</p>
        </Dialog>
      ) : null}
    </div>
  );
}
