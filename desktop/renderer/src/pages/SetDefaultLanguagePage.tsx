/** 设置默认语言：复用 /api/language-tools/default；提交前校验 tl/<language> 存在。 */
import { useEffect, useMemo, useState } from 'react';
import { Button, Form, Input, Progress, Select } from 'antd';

import { defaultLanguagePathReady, resolveTargetLanguage } from '../languageToolsView.mjs';
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

const FALLBACK_LANGS = ['chinese', 'schinese', 'tchinese', 'japanese', 'korean', 'english'];
const KINDS = ['language_default'] as const;

export function SetDefaultLanguagePage(props: { state: AppState }) {
  const { state } = props;
  const t = useT();
  const [selected, setSelected] = useState('chinese');
  const [custom, setCustom] = useState('');
  const [confirm, setConfirm] = useState(false);
  const [localError, setLocalError] = useState('');
  const suite = useProjectToolJob<LanguageResult, LanguageStatus>(state, '/api/language-tools', KINDS);
  const { status, keyReady, job, result, active, error, cancelling, busy } = suite;
  const engineBusy = state.translation.engine_status !== 'IDLE' || state.translation.stop_barrier || state.translation.single_tasks;
  const hasProject = Boolean(state.project?.renpy_project_path);
  const languages = status?.languages?.length ? status.languages : FALLBACK_LANGS;
  const language = useMemo(() => resolveTargetLanguage(selected, custom, 'chinese'), [selected, custom]);
  const pathReady = defaultLanguagePathReady(language, status?.languages ?? []);
  const writeBlocked = busy || engineBusy || !keyReady || state.link !== 'open' || !hasProject || !language;

  const languagesKey = languages.join('\0');
  useEffect(() => {
    setConfirm(false);
    setLocalError('');
    setCustom('');
    if (languages.includes('chinese')) setSelected('chinese');
    else if (languages[0]) setSelected(languages[0]);
  }, [suite.identity]);

  useEffect(() => {
    if (status?.default_language && !custom && languages.includes(status.default_language)) {
      setSelected(status.default_language);
    }
  }, [status?.default_language, languagesKey, custom]);

  function askConfirm() {
    setLocalError('');
    if (!pathReady) {
      setLocalError(t('lang_default_missing_tl').replace('{language}', language));
      return;
    }
    setConfirm(true);
  }

  function start() {
    setConfirm(false);
    void suite.submit('/api/language-tools/default', { language, confirm: true });
  }

  const statusText = toolStatusText(t, suite, t('lang_default_idle'));
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
    <div className="rb-asset-page rb-page-scroll" data-rb-page="set-default-language">
      {error ? <Banner tone="error">{error}</Banner> : null}
      {localError ? <Banner tone="warning">{localError}</Banner> : null}
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

      <SettingsGroup title={t('lang_default_title')} description={t('lang_default_desc')}>
        <Form.Item label={t('lang_tools_project_root')} style={{ marginBottom: 12 }}>
          <Input value={status?.project_root || String(state.project?.renpy_project_path ?? '')} readOnly />
        </Form.Item>
        <Form.Item label={t('lang_default_language')} style={{ marginBottom: 12 }}>
          <Select
            options={languages.map((item) => ({ value: item, label: item }))}
            value={selected}
            onChange={(value) => setSelected(String(value || 'chinese'))}
            disabled={busy || !hasProject}
            allowClear={false}
          />
        </Form.Item>
        <Form.Item label={t('lang_default_custom')} style={{ marginBottom: 12 }}>
          <Input
            value={custom}
            onChange={(event) => setCustom(event.target.value)}
            placeholder={t('lang_default_custom_hint')}
            disabled={busy || !hasProject}
          />
        </Form.Item>
        <p className="card-description">
          {status?.default_language
            ? t('lang_default_current').replace('{language}', status.default_language)
            : t('lang_default_none')}
        </p>
        <div className="rb-tool-actions">
          <Button type="primary" onClick={askConfirm} disabled={writeBlocked}>
            {t('lang_default_run')}
          </Button>
        </div>
      </SettingsGroup>

      {result?.path ? <p className="card-description rb-asset-output">{result.path}</p> : null}

      {confirm ? (
        <Dialog
          title={t('lang_default_confirm_title')}
          confirmText={t('lang_default_run')}
          cancelText={t('workbench_cancel')}
          onConfirm={start}
          onCancel={() => setConfirm(false)}
        >
          <p>{t('lang_default_confirm').replace('{language}', language)}</p>
        </Dialog>
      ) : null}
    </div>
  );
}
