/** 翻译提示：模式、风格和自定义提示词，预览走真实构造结果。 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Input, Modal, Tabs } from 'antd';
import { request } from '../api';

import type { AppState } from '../useAppState';
import { Banner, Dialog, PageHeader, SelectInput, SettingsGroup } from '../ui';
import { useT, type TextKey } from '../i18n';

// 文案取自 i18n，渲染时按当前界面语言解析，避免模块加载时就固定语言。
const PROMPT_MODE_OPTIONS: { value: string; labelKey: TextKey }[] = [
  { value: 'COMMON', labelKey: 'prompt_mode_common' },
  { value: 'COT', labelKey: 'prompt_mode_cot' },
  { value: 'THINK', labelKey: 'prompt_mode_think' },
  { value: 'LOCAL', labelKey: 'prompt_mode_local' },
  { value: 'CUSTOM', labelKey: 'prompt_mode_custom' },
];

const WRITING_STYLE_OPTIONS: { value: string; labelKey: TextKey }[] = [
  { value: 'NONE', labelKey: 'prompt_style_none' },
  { value: 'LITERARY', labelKey: 'prompt_style_literary' },
  { value: 'CLASSICAL', labelKey: 'prompt_style_classical' },
  { value: 'R18', labelKey: 'prompt_style_r18' },
  { value: 'CUSTOM', labelKey: 'prompt_mode_custom' },
];

const PREVIEW_TABS: { value: string; labelKey: TextKey }[] = [
  { value: 'base', labelKey: 'custom_prompt_preview_tab_base' },
  { value: 'style', labelKey: 'writing_style' },
  { value: 'fixed', labelKey: 'custom_prompt_preview_tab_fixed' },
];

function readPrompts(raw: unknown): Record<string, string> {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {};
  const out: Record<string, string> = {};
  Object.entries(raw as Record<string, unknown>).forEach(([key, value]) => {
    if (typeof value === 'string') out[key] = value;
  });
  return out;
}

type EditableSection = 'base' | 'style';
interface PromptDraft {
  base: string;
  style: string;
  language: string;
  initial: { base: string; style: string };
  project: string;
}

export function CustomPromptPage(props: { state: AppState; embedded?: boolean; onDirtyChange?: (dirty: boolean) => void }) {
  const { state, embedded = false, onDirtyChange } = props;
  const t = useT();
  const [preview, setPreview] = useState<Record<string, string> | null>(null);
  const [previewTab, setPreviewTab] = useState('base');
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [editor, setEditor] = useState<PromptDraft | null>(null);
  const [editorTab, setEditorTab] = useState<EditableSection>('base');
  const [loadingEditor, setLoadingEditor] = useState(false);
  const [savingEditor, setSavingEditor] = useState(false);
  const [discardEditor, setDiscardEditor] = useState(false);
  const saveInFlight = useRef(false);
  const project = JSON.stringify([state.project?.renpy_project_path, state.settings?.values.target_language]);
  const projectRef = useRef(project);
  projectRef.current = project;
  const dirty = Boolean(editor && (editor.base !== editor.initial.base || editor.style !== editor.initial.style));
  useEffect(() => {
    onDirtyChange?.(dirty);
    return () => onDirtyChange?.(false);
  }, [dirty, onDirtyChange]);
  const loadPreview = async () => {
    setLoadingPreview(true);
    try { setPreview(await request<Record<string, string>>('/api/settings/prompt-preview')); }
    catch (e) { state.pushToast('error', e instanceof Error ? e.message : String(e)); }
    finally { setLoadingPreview(false); }
  };
  const values = state.settings?.values;

  const mode = String(values?.translation_prompt_mode ?? 'COMMON').toUpperCase();
  const styleId = String(values?.translation_style_id ?? 'NONE').toUpperCase();
  const prompts = useMemo(() => readPrompts(values?.translation_custom_prompts), [
    values?.translation_custom_prompts,
  ]);
  const openEditor = async (section: EditableSection) => {
    const identity = projectRef.current;
    setLoadingEditor(true);
    try {
      const raw = await request<{ base: string; style: string; language: string }>('/api/settings/prompt-preview?raw=true');
      if (identity !== projectRef.current) return;
      if (!['ZH', 'EN'].includes(raw.language) || typeof raw.base !== 'string' || typeof raw.style !== 'string') {
        throw new Error(t('custom_prompt_editor_error_unavailable'));
      }
      setEditor({ ...raw, initial: { base: raw.base, style: raw.style }, project: identity });
      setEditorTab(section);
      setPreview(null);
    } catch (error) {
      state.pushToast('error', error instanceof Error ? error.message : String(error));
    } finally { setLoadingEditor(false); }
  };
  const closeEditor = () => {
    if (saveInFlight.current) return;
    if (dirty) setDiscardEditor(true);
    else setEditor(null);
  };
  const saveEditor = async () => {
    if (!editor || !dirty || saveInFlight.current || state.saving || editor.project !== projectRef.current) return;
    const patch: Record<string, unknown> = {};
    if (editor.base !== editor.initial.base) {
      if (!editor.base.trim()) { state.pushToast('warning', t('custom_prompt_empty_base_warning')); return; }
      patch.translation_prompt_mode = 'CUSTOM';
      patch.translation_custom_prompts = { ...prompts, [editor.language]: editor.base };
      const enabled = values?.translation_custom_prompt_enabled_languages;
      patch.translation_custom_prompt_enabled_languages = mode === 'CUSTOM'
        ? Array.isArray(enabled) ? [...new Set([...enabled, editor.language])] : null
        : [editor.language];
    }
    if (editor.style !== editor.initial.style) {
      patch.translation_style_id = editor.style.trim() ? 'CUSTOM' : 'NONE';
      patch.translation_custom_style = editor.style;
    }
    saveInFlight.current = true;
    setSavingEditor(true);
    try {
      if (await state.saveSettings(patch)) {
        setEditor(null);
        state.pushToast('success', t('custom_prompt_saved'));
      }
    } finally { saveInFlight.current = false; setSavingEditor(false); }
  };

  return (
    <div className={embedded ? 'rb-embedded' : 'rb-page rb-page-narrow'}>
      <div className="rb-page-scroll">
        {embedded ? null : <PageHeader title={t('app_custom_prompt_navigation_item')} description={t('custom_prompt_page_header_description')} />}
        <SettingsGroup
          title={t('basic_prompt_mode')}
          description={t('basic_prompt_mode_description')}
          actions={(
            <>
            <SelectInput
              label={t('basic_prompt_mode')}
              value={mode}
              options={PROMPT_MODE_OPTIONS.map((item) => ({ value: item.value, label: t(item.labelKey) }))}
              disabled={state.saving}
              onCommit={(next) => state.setSetting('translation_prompt_mode', next)}
            />
            <Button disabled={state.saving || loadingEditor} onClick={() => void openEditor('base')}>{t('edit_prompt')}</Button>
            </>
          )}
        />
        <SettingsGroup
          title={t('custom_prompt_preview_tab_style')}
          description={t('writing_style_description')}
          actions={(
            <>
            <SelectInput
              label={t('custom_prompt_editor_style_tab')}
              value={styleId}
              options={WRITING_STYLE_OPTIONS.map((item) => ({ value: item.value, label: t(item.labelKey) }))}
              disabled={state.saving}
              onCommit={(next) => state.setSetting('translation_style_id', next)}
            />
            <Button disabled={state.saving || loadingEditor} onClick={() => void openEditor('style')}>{t('edit_style')}</Button>
            </>
          )}
        />
        <SettingsGroup
          title={t('current_prompt')}
          description={t('current_prompt_description')}
          actions={(
            <Button type="default" disabled={state.saving || loadingPreview} onClick={() => void loadPreview()}>
              {loadingPreview ? t('app_read_state_loading') : t('view_current_prompt')}
            </Button>
          )}
        />
        <Banner tone="info">
          {t('custom_prompt_banner')}</Banner>
      </div>
      {preview ? (
        <Dialog title={t('current_prompt')} cancelText={t('app_close')} onCancel={() => setPreview(null)}>
          <Tabs
            activeKey={previewTab}
            onChange={setPreviewTab}
            items={PREVIEW_TABS.map((tab) => ({ key: tab.value, label: t(tab.labelKey) }))}
            aria-label={t('custom_prompt_preview_sections_label')}
          />
          <Input.TextArea
            className="prompt-preview-text"
            aria-label={t('custom_prompt_preview_label')}
            readOnly
            autoSize={{ minRows: 8, maxRows: 14 }}
            value={preview[previewTab] || t('custom_prompt_preview_empty')}
          />
          <div className="rb-prompt-preview-actions">
          <Button
            type="default"
            onClick={() => void navigator.clipboard.writeText(preview[previewTab] || '').then(() => state.pushToast('success', t('custom_prompt_preview_copied'))).catch(() => state.pushToast('warning', t('custom_prompt_preview_copy_failed')))}
          >
            {t('custom_prompt_copy_section')}</Button>
          {previewTab !== 'fixed' ? (
            <Button type="primary" disabled={state.saving || loadingEditor} onClick={() => void openEditor(previewTab as EditableSection)}>{t('custom_prompt_edit_section')}</Button>
          ) : <span className="card-description">{t('custom_prompt_fixed_note')}</span>}
          </div>
        </Dialog>
      ) : null}
      {editor && (
        <Modal open centered width={800} title={t('custom_prompt_editor_title')} onCancel={closeEditor} mask={{ closable: false }}
          closable={!savingEditor} keyboard={!savingEditor}
          footer={<>
            <Button disabled={savingEditor} onClick={closeEditor}>{t('exit_cancel')}</Button>
            <Button type="primary" loading={savingEditor} disabled={!dirty || state.saving || editor.project !== project} onClick={() => void saveEditor()}>{t('custom_prompt_save_and_apply')}</Button>
          </>}
        >
          {editor.project !== project && <Banner tone="warning">{t('custom_prompt_editor_project_changed')}</Banner>}
          <Tabs activeKey={editorTab} onChange={(key) => setEditorTab(key as EditableSection)} items={[
            { key: 'base', label: t('custom_prompt_editor_tab_base').split('{language}').join(editor.language === 'ZH' ? t('language_zh') : t('custom_prompt_editor_tab_non_zh')) },
            { key: 'style', label: t('custom_prompt_editor_style_tab') },
          ]} />
          <Input.TextArea aria-label={t('custom_prompt_editor_label')} value={editor[editorTab]} disabled={savingEditor}
            autoSize={{ minRows: 10, maxRows: 18 }}
            onChange={(event) => setEditor({ ...editor, [editorTab]: event.target.value })}
          />
          <p className="rb-prompt-editor-help">{t('custom_prompt_editor_help')}</p>
        </Modal>
      )}
      {discardEditor && <Dialog title={t('custom_prompt_discard_title')} cancelText={t('exit_continue_editing')} confirmText={t('custom_prompt_discard_confirm')}
        onCancel={() => setDiscardEditor(false)} onConfirm={() => { setDiscardEditor(false); setEditor(null); }}
      >{t('custom_prompt_discard_content')}</Dialog>}
    </div>
  );
}
