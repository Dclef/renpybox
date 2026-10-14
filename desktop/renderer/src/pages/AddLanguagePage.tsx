/** 添加语言入口：复用 /api/language-tools/entrance。 */
import { useEffect, useState } from 'react';
import { Button, Form, Input, Progress } from 'antd';

import { useT } from '../i18n';
import type { AppState } from '../useAppState';
import { Banner, Dialog, SettingsGroup } from '../ui';
import {
  toolStatusText,
  useProjectToolJob,
  type ToolJob,
  type ToolResultBase,
} from './projectToolJob';

interface LanguageResult extends ToolResultBase {
  path?: string;
  action?: string;
}

interface LanguageStatus {
  project_key?: string;
  project_root?: string;
  game_dir?: string;
  languages?: string[];
  entrance_exists?: boolean;
  default_script_exists?: boolean;
  default_language?: string | null;
  job?: ToolJob<LanguageResult> | null;
}

const KINDS = ['language_entrance'] as const;

export function AddLanguagePage(props: { state: AppState }) {
  const { state } = props;
  const t = useT();
  const [confirm, setConfirm] = useState(false);
  const suite = useProjectToolJob<LanguageResult, LanguageStatus>(state, '/api/language-tools', KINDS);
  const { status, keyReady, job, result, active, error, cancelling, busy } = suite;
  const engineBusy = state.translation.engine_status !== 'IDLE' || state.translation.stop_barrier || state.translation.single_tasks;
  const hasProject = Boolean(state.project?.renpy_project_path);
  const writeBlocked = busy || engineBusy || !keyReady || state.link !== 'open' || !hasProject;

  useEffect(() => {
    setConfirm(false);
  }, [suite.identity]);

  function start() {
    setConfirm(false);
    void suite.submit('/api/language-tools/entrance', { confirm: true });
  }

  const statusText = toolStatusText(t, suite, t('lang_entrance_idle'));
  const statusTone = active || suite.checking
    ? 'info'
    : job?.status === 'done'
      ? 'success'
      : job?.status === 'failed'
        ? 'error'
        : job?.status === 'cancelled'
          ? 'warning'
          : 'info';

  return (
    <div className="rb-asset-page rb-page-scroll" data-rb-page="add-language">
      {error ? <Banner tone="error">{error}</Banner> : null}
      {!hasProject ? <Banner tone="warning">{t('app_tool_needs_project')}</Banner> : null}
      <Banner tone={statusTone}>{statusText}</Banner>
      {active ? <Progress percent={Math.min(100, 100 * (job?.progress || 0))} aria-label={t('tool_job_running')} /> : null}
      {active ? (
        <div className="rb-tool-actions">
          <Button onClick={() => void suite.cancel()} disabled={cancelling || Boolean(job?.cancel_requested)}>
            {t('tool_job_cancel')}
          </Button>
        </div>
      ) : null}

      <SettingsGroup title={t('lang_entrance_title')} description={t('lang_entrance_desc')}>
        <Form.Item label={t('lang_tools_game_dir')} style={{ marginBottom: 12 }}>
          <Input value={status?.game_dir || String(state.project?.renpy_game_folder ?? '')} readOnly />
        </Form.Item>
        <p className="card-description">
          {status?.entrance_exists ? t('lang_entrance_exists') : t('lang_entrance_missing')}
        </p>
        <div className="rb-tool-actions">
          <Button type="primary" onClick={() => setConfirm(true)} disabled={writeBlocked}>
            {t('lang_entrance_run')}
          </Button>
        </div>
      </SettingsGroup>

      {result?.path ? <p className="card-description rb-asset-output">{result.path}</p> : null}

      {confirm ? (
        <Dialog
          title={t('lang_entrance_confirm_title')}
          confirmText={t('lang_entrance_run')}
          cancelText={t('workbench_cancel')}
          onConfirm={start}
          onCancel={() => setConfirm(false)}
        >
          <p>{t('lang_entrance_confirm')}</p>
          <p className="card-description">{status?.game_dir || ''}</p>
        </Dialog>
      ) : null}
    </div>
  );
}
