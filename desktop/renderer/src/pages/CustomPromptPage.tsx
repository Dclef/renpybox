/** 翻译提示：模式、风格和自定义提示词，预览走真实构造结果。 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Input, Modal, Tabs } from 'antd';
import { request } from '../api';

import type { AppState } from '../useAppState';
import { Banner, Dialog, PageHeader, SelectInput, SettingsGroup } from '../ui';

const PROMPT_MODE_OPTIONS = [
  { value: 'COMMON', label: '通用（COMMON）' },
  { value: 'COT', label: '逐步推理（COT）' },
  { value: 'THINK', label: '深度思考（THINK）' },
  { value: 'LOCAL', label: '本地模型（LOCAL）' },
  { value: 'CUSTOM', label: '自定义（CUSTOM）' },
];

const WRITING_STYLE_OPTIONS = [
  { value: 'NONE', label: '无（NONE）' },
  { value: 'LITERARY', label: '文学化（LITERARY）' },
  { value: 'CLASSICAL', label: '古典文风（CLASSICAL）' },
  { value: 'R18', label: '成人内容（R18）' },
  { value: 'CUSTOM', label: '自定义（CUSTOM）' },
];

const PREVIEW_TABS = [
  { value: 'base', label: '基础提示' },
  { value: 'style', label: '写作风格' },
  { value: 'fixed', label: '固定协议' },
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
        throw new Error('后端尚未加载提示词编辑功能，请完整重启应用后重试。');
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
      if (!editor.base.trim()) { state.pushToast('warning', '基础提示词不能为空'); return; }
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
        state.pushToast('success', '提示词已保存，将在下一轮翻译生效');
      }
    } finally { saveInFlight.current = false; setSavingEditor(false); }
  };

  return (
    <div className={embedded ? 'rb-embedded' : 'rb-page rb-page-narrow'}>
      <div className="rb-page-scroll">
        {embedded ? null : <PageHeader title="翻译提示" description="配置翻译提示词模式、风格和预览内容" />}
        <SettingsGroup
          title="基础提示模式"
          description="每次只使用一种基础模式；自定义模式仅替换基础提示词，固定工程协议仍会生效"
          actions={(
            <>
            <SelectInput
              label="基础提示模式"
              value={mode}
              options={PROMPT_MODE_OPTIONS}
              disabled={state.saving}
              onCommit={(next) => state.setSetting('translation_prompt_mode', next)}
            />
            <Button disabled={state.saving || loadingEditor} onClick={() => void openEditor('base')}>编辑提示词</Button>
            </>
          )}
        />
        <SettingsGroup
          title="写作风格"
          description="独立追加到基础提示词，可与任意基础模式组合"
          actions={(
            <>
            <SelectInput
              label="写作风格"
              value={styleId}
              options={WRITING_STYLE_OPTIONS}
              disabled={state.saving}
              onCommit={(next) => state.setSetting('translation_style_id', next)}
            />
            <Button disabled={state.saving || loadingEditor} onClick={() => void openEditor('style')}>编辑风格</Button>
            </>
          )}
        />
        <SettingsGroup
          title="当前提示词"
          description="查看当前配置实际使用的静态提示词内容"
          actions={(
            <Button type="default" disabled={state.saving || loadingPreview} onClick={() => void loadPreview()}>
              {loadingPreview ? '读取中…' : '查看当前提示词'}
            </Button>
          )}
        />
        <Banner tone="info">
          编辑后点击“保存并应用”，修改的部分会切换为自定义模式，在下一轮翻译生效。可随时切回内置模式。
        </Banner>
      </div>
      {preview ? (
        <Dialog title="当前提示词" cancelText="关闭" onCancel={() => setPreview(null)}>
          <Tabs
            activeKey={previewTab}
            onChange={setPreviewTab}
            items={PREVIEW_TABS.map((tab) => ({ key: tab.value, label: tab.label }))}
            aria-label="提示词部分"
          />
          <Input.TextArea
            className="prompt-preview-text"
            aria-label="提示词预览内容"
            readOnly
            autoSize={{ minRows: 8, maxRows: 14 }}
            value={preview[previewTab] || '当前部分为空'}
          />
          <div className="rb-prompt-preview-actions">
          <Button
            type="default"
            onClick={() => void navigator.clipboard.writeText(preview[previewTab] || '').then(() => state.pushToast('success', '已复制提示词')).catch(() => state.pushToast('warning', '复制失败，请选中文本后手动复制'))}
          >
            复制当前部分
          </Button>
          {previewTab !== 'fixed' ? (
            <Button type="primary" disabled={state.saving || loadingEditor} onClick={() => void openEditor(previewTab as EditableSection)}>编辑当前部分</Button>
          ) : <span className="card-description">固定协议负责格式与占位符保护，由程序统一管理。</span>}
          </div>
        </Dialog>
      ) : null}
      {editor && (
        <Modal open centered width={800} title="编辑翻译提示词" onCancel={closeEditor} mask={{ closable: false }}
          closable={!savingEditor} keyboard={!savingEditor}
          footer={<>
            <Button disabled={savingEditor} onClick={closeEditor}>取消</Button>
            <Button type="primary" loading={savingEditor} disabled={!dirty || state.saving || editor.project !== project} onClick={() => void saveEditor()}>保存并应用</Button>
          </>}
        >
          {editor.project !== project && <Banner tone="warning">项目或目标语言已变化，请关闭后重新打开编辑。</Banner>}
          <Tabs activeKey={editorTab} onChange={(key) => setEditorTab(key as EditableSection)} items={[
            { key: 'base', label: `基础提示词（${editor.language === 'ZH' ? '中文' : '非中文'}）` },
            { key: 'style', label: '写作风格' },
          ]} />
          <Input.TextArea aria-label="提示词编辑内容" value={editor[editorTab]} disabled={savingEditor}
            autoSize={{ minRows: 10, maxRows: 18 }}
            onChange={(event) => setEditor({ ...editor, [editorTab]: event.target.value })}
          />
          <p className="rb-prompt-editor-help">{'{source_language} 和 {target_language} 会自动替换为当前翻译语言。'}</p>
        </Modal>
      )}
      {discardEditor && <Dialog title="放弃未保存的提示词？" cancelText="继续编辑" confirmText="放弃修改"
        onCancel={() => setDiscardEditor(false)} onConfirm={() => { setDiscardEditor(false); setEditor(null); }}
      >关闭后，本次编辑的内容将丢失。</Dialog>}
    </div>
  );
}
