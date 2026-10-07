/**
 * 翻译提示页 —— 对齐 frontend/Setting/CustomPromptPage.py 的实测几何。
 *
 * 实测（nav=256、页宽 1023）：
 *   页头   975x36  @ (24,24)：TitleLabel 18px「翻译提示」+ CaptionLabel 12px @ y=20
 *   滚动区 975x669 @ (24,68)
 *   `ComboBoxCard 975x66 @ (0,0)`   基础提示模式 + ComboBox 184x27 @ (774,19)
 *   `ComboBoxCard 975x66 @ (0,74)`  写作风格 + ComboBox 142x27 @ (816,19)
 *   `PushButtonCard 975x66 @ (0,148)` 当前提示词 + PushButton 148x27 @ (810,19)
 *   两张「基础提示词」GroupCard 与一张「自定义写作风格」GroupCard 默认隐藏（vis=False），
 *   只在模式选中 CUSTOM 时才出现 —— `CustomPromptPage.py:165-175` 的 refresh_conditional_visibility。
 *
 * 取值来源（`frontend/Setting/TranslationSettingsBinding.py`）：
 *   translation_prompt_mode ∈ COMMON / COT / THINK / LOCAL / CUSTOM
 *   translation_style_id    ∈ NONE / LITERARY / CLASSICAL / R18 / CUSTOM
 *   translation_custom_prompts 是 dict，键为 "ZH" / "EN"（`get_custom_prompt` / `set_custom_prompt`）
 *   translation_custom_style 是一个字符串
 */

import { useMemo, useState } from 'react';
import { request } from '../api';

import type { AppState } from '../useAppState';
import { Banner, Dialog, SettingCard } from '../ui';

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

function readPrompts(raw: unknown): Record<string, string> {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {};
  const out: Record<string, string> = {};
  Object.entries(raw as Record<string, unknown>).forEach(([key, value]) => {
    if (typeof value === 'string') out[key] = value;
  });
  return out;
}

/** 语言自定义提示词卡：默认隐藏，模式选到 CUSTOM 才出现。 */
function CustomPromptCard(props: {
  title: string;
  description: string;
  placeholder: string;
  value: string;
  disabled: boolean;
  onChange: (next: string) => void;
}) {
  const { title, description, placeholder, value, disabled, onChange } = props;
  return (
    <section className="group-card prompt-group-card">
      <div className="setting-card-text">
        <span className="setting-card-title">{title}</span>
        <span className="setting-card-description">{description}</span>
      </div>
      <textarea
        className="prompt-textarea"
        aria-label={title}
        placeholder={placeholder}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
      />
    </section>
  );
}

export function CustomPromptPage(props: { state: AppState }) {
  const { state } = props;
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

  /** 写自定义提示词：`set_custom_prompt` 语义是「只改这一门语言，其余保留」。 */
  const setPrompt = (language: string, text: string) => {
    state.setSetting('translation_custom_prompts', { ...prompts, [language]: text });
  };

  return (
    <div className="settings-layout">
      <header className="settings-header">
        <h1 className="settings-title">翻译提示</h1>
        <p className="settings-subtitle">配置翻译提示词模式、风格和预览内容</p>
      </header>

      <div className="settings-scroll">
        <div className="settings-card-list">
          <SettingCard
            title="基础提示模式"
            description="每次只使用一种基础模式；自定义模式仅替换基础提示词，固定工程协议仍会生效"
          >
            <select
              aria-label="基础提示模式"
              value={mode}
              disabled={state.saving}
              onChange={(event) => state.setSetting('translation_prompt_mode', event.target.value)}
            >
              {PROMPT_MODE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </SettingCard>

          {visiblePrompts ? (
            <CustomPromptCard
              title="中文基础提示词"
              description="目标语言为中文时使用，完整替换所选基础提示模式"
              placeholder="输入中文基础提示词"
              value={prompts.ZH ?? ''}
              disabled={state.saving}
              onChange={(next) => setPrompt('ZH', next)}
            />
          ) : null}

          {visiblePrompts ? (
            <CustomPromptCard
              title="英文基础提示词"
              description="目标语言为非中文时使用，完整替换所选基础提示模式"
              placeholder="输入英文基础提示词"
              value={prompts.EN ?? ''}
              disabled={state.saving}
              onChange={(next) => setPrompt('EN', next)}
            />
          ) : null}

          <SettingCard title="写作风格" description="独立追加到基础提示词，可与任意基础模式组合">
            <select
              aria-label="写作风格"
              value={styleId}
              disabled={state.saving}
              onChange={(event) => state.setSetting('translation_style_id', event.target.value)}
            >
              {WRITING_STYLE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </SettingCard>

          {visibleCustomStyle ? (
            <CustomPromptCard
              title="自定义写作风格"
              description="作为独立风格要求完整追加，不会替换基础提示词"
              placeholder="输入自定义写作风格要求"
              value={customStyle}
              disabled={state.saving}
              onChange={(next) => state.setSetting('translation_custom_style', next)}
            />
          ) : null}

          <SettingCard
            title="当前提示词"
            description="查看当前配置实际使用的静态提示词内容"
          >
            <button
              type="button"
              className="btn"
              style={{ width: 148 }}
              disabled={state.saving || loadingPreview}
              onClick={() => void loadPreview()}
            >
              {loadingPreview ? '读取中…' : '查看当前提示词'}
            </button>
          </SettingCard>

          <Banner tone="info">
            提示词模式与写作风格会立即写入配置并在下一轮翻译生效。自定义提示词内容较长的，
            可以使用「查看当前提示词」检查基础提示、风格与固定协议。
          </Banner>
        </div>
      </div>
      {preview ? (
        <Dialog title="当前提示词" cancelText="关闭" onCancel={() => setPreview(null)}>
          <div className="workbench-tabs" role="tablist" aria-label="提示词部分">
            {Object.entries({ base: '基础提示', style: '写作风格', fixed: '固定协议' }).map(([key, label]) => (
              <button key={key} role="tab" className="quiet-pill" aria-selected={previewTab === key} onClick={() => setPreviewTab(key)}>{label}</button>
            ))}
          </div>
          <textarea className="prompt-preview-text" aria-label="提示词预览内容" readOnly value={preview[previewTab] || '当前部分为空'} />
          <button className="btn" onClick={() => void navigator.clipboard.writeText(preview[previewTab] || '').then(() => state.pushToast('success', '已复制提示词')).catch(() => state.pushToast('warning', '复制失败，请选中文本后手动复制'))}>复制当前部分</button>
        </Dialog>
      ) : null}
    </div>
  );
}