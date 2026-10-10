/** 翻译提示：模式、风格和自定义提示词，预览走真实构造结果。 */

import { useMemo, useState } from 'react';
import { Button, Input, Tabs } from 'antd';
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

function PromptEditor(props: {
  title: string;
  description: string;
  placeholder: string;
  value: string;
  disabled: boolean;
  onChange: (next: string) => void;
}) {
  const { title, description, placeholder, value, disabled, onChange } = props;
  return (
    <SettingsGroup title={title} description={description}>
      <Input.TextArea
        aria-label={title}
        placeholder={placeholder}
        value={value}
        disabled={disabled}
        autoSize={{ minRows: 6 }}
        onChange={(event) => onChange(event.target.value)}
      />
    </SettingsGroup>
  );
}

export function CustomPromptPage(props: { state: AppState; embedded?: boolean }) {
  const { state, embedded = false } = props;
  const [preview, setPreview] = useState<Record<string, string> | null>(null);
  const [previewTab, setPreviewTab] = useState('base');
  const [loadingPreview, setLoadingPreview] = useState(false);
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
  const customStyle = String(values?.translation_custom_style ?? '');

  const visiblePrompts = mode === 'CUSTOM';
  const visibleCustomStyle = styleId === 'CUSTOM';

  const setPrompt = (language: string, text: string) => {
    state.setSetting('translation_custom_prompts', { ...prompts, [language]: text });
  };

  return (
    <div className={embedded ? 'rb-embedded' : 'rb-page rb-page-narrow'}>
      <div className="rb-page-scroll">
        {embedded ? null : <PageHeader title="翻译提示" description="配置翻译提示词模式、风格和预览内容" />}
        <SettingsGroup
          title="基础提示模式"
          description="每次只使用一种基础模式；自定义模式仅替换基础提示词，固定工程协议仍会生效"
          actions={(
            <SelectInput
              label="基础提示模式"
              value={mode}
              options={PROMPT_MODE_OPTIONS}
              disabled={state.saving}
              onCommit={(next) => state.setSetting('translation_prompt_mode', next)}
            />
          )}
        />
        {visiblePrompts ? (
          <PromptEditor
            title="中文基础提示词"
            description="目标语言为中文时使用，完整替换所选基础提示模式"
            placeholder="输入中文基础提示词"
            value={prompts.ZH ?? ''}
            disabled={state.saving}
            onChange={(next) => setPrompt('ZH', next)}
          />
        ) : null}
        {visiblePrompts ? (
          <PromptEditor
            title="英文基础提示词"
            description="目标语言为非中文时使用，完整替换所选基础提示模式"
            placeholder="输入英文基础提示词"
            value={prompts.EN ?? ''}
            disabled={state.saving}
            onChange={(next) => setPrompt('EN', next)}
          />
        ) : null}
        <SettingsGroup
          title="写作风格"
          description="独立追加到基础提示词，可与任意基础模式组合"
          actions={(
            <SelectInput
              label="写作风格"
              value={styleId}
              options={WRITING_STYLE_OPTIONS}
              disabled={state.saving}
              onCommit={(next) => state.setSetting('translation_style_id', next)}
            />
          )}
        />
        {visibleCustomStyle ? (
          <PromptEditor
            title="自定义写作风格"
            description="作为独立风格要求完整追加，不会替换基础提示词"
            placeholder="输入自定义写作风格要求"
            value={customStyle}
            disabled={state.saving}
            onChange={(next) => state.setSetting('translation_custom_style', next)}
          />
        ) : null}
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
          提示词模式与写作风格会立即写入配置并在下一轮翻译生效。自定义提示词内容较长的，
          可以使用「查看当前提示词」检查基础提示、风格与固定协议。
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
            autoSize={{ minRows: 8 }}
            value={preview[previewTab] || '当前部分为空'}
          />
          <Button
            type="default"
            onClick={() => void navigator.clipboard.writeText(preview[previewTab] || '').then(() => state.pushToast('success', '已复制提示词')).catch(() => state.pushToast('warning', '复制失败，请选中文本后手动复制'))}
          >
            复制当前部分
          </Button>
        </Dialog>
      ) : null}
    </div>
  );
}
