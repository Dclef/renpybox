/** 称呼桥接：把 Mr.[name] 这类「称呼 + 变量」交给翻译前处理。 */
import { useEffect, useState } from 'react';
import { Button, Checkbox, TextInput } from '@mantine/core';

import { request } from '../api';
import { useT } from '../i18n';
import type { AppState } from '../useAppState';
import { Banner, Empty } from '../ui';

function readTitles(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => typeof item === 'string' ? item : item && typeof item === 'object' && 'src' in item ? String(item.src ?? '') : '');
}

export function HonorificPage(props: { state: AppState; onDirtyChange?: (dirty: boolean) => void }) {
  const { state, onDirtyChange } = props;
  const t = useT();
  const [loadingDefaults, setLoadingDefaults] = useState(false);
  const [titles, setTitles] = useState<string[]>(() => readTitles(state.settings?.values.honorific_placeholder_titles));
  const [enabled, setEnabled] = useState(state.settings?.values.honorific_placeholder_bridge_enable !== false);
  const [dirty, setDirty] = useState(false);
  const locked = loadingDefaults || state.saving || state.translation.engine_status !== 'IDLE' || state.translation.stop_barrier || state.translation.single_tasks;

  useEffect(() => {
    if (dirty) return;
    setTitles(readTitles(state.settings?.values.honorific_placeholder_titles));
    setEnabled(state.settings?.values.honorific_placeholder_bridge_enable !== false);
  }, [dirty, state.settings?.values.honorific_placeholder_titles, state.settings?.values.honorific_placeholder_bridge_enable]);

  useEffect(() => {
    onDirtyChange?.(dirty);
    return () => onDirtyChange?.(false);
  }, [dirty, onDirtyChange]);

  const save = async () => {
    const cleaned = titles.map((title) => title.trim().toLowerCase()).filter(Boolean);
    if (!await state.saveSettings({ honorific_placeholder_titles: cleaned, honorific_placeholder_bridge_enable: enabled })) return;
    setTitles(cleaned);
    setDirty(false);
    state.pushToast('success', `已保存 ${cleaned.length} 个称呼词`);
  };

  return (
    <div className="rb-embedded">
      <div className="rb-toolbar">
        <div className="rb-sheet-summary">
          <strong>{titles.filter((title) => title.trim()).length} 个称呼词</strong>
          <span>{dirty ? '有未保存修改' : enabled ? '翻译前会自动桥接' : '当前未启用'}</span>
        </div>
        <Checkbox label="启用称呼变量桥接" checked={enabled} disabled={locked} onChange={(event) => { setEnabled(event.currentTarget.checked); setDirty(true); }} />
        <span className="rb-toolbar-spacer" />
        <Button variant="default" disabled={locked} onClick={() => { setTitles((previous) => ['', ...previous]); setDirty(true); }}>新增称呼词</Button>
        <Button variant="default" disabled={locked || !titles.length} onClick={() => {
          setTitles([...new Set(titles.map((title) => title.trim().toLowerCase()).filter(Boolean))]); setDirty(true);
        }}>{t('rules_deduplicate')}</Button>
        <Button variant="default" disabled={locked} onClick={async () => {
          if (dirty && !window.confirm(t('rules_reload_confirm'))) return;
          await state.reloadSettings(); setDirty(false);
        }}>{t('rules_reload')}</Button>
        <Button variant="default" disabled={locked} onClick={async () => {
          if (!window.confirm(t('rules_defaults_confirm'))) return;
          setLoadingDefaults(true);
          try { const result = await request<{ titles: string[] }>('/api/settings/honorific-defaults'); setTitles(result.titles); setDirty(true); }
          catch (error) { state.pushToast('error', error instanceof Error ? error.message : String(error)); }
          finally { setLoadingDefaults(false); }
        }}>{t('rules_defaults')}</Button>
        <Button color="red" variant="subtle" disabled={locked || !titles.length} onClick={() => {
          if (!window.confirm(t('rules_clear_confirm'))) return;
          setTitles([]); setEnabled(false); setDirty(true);
        }}>{t('rules_clear')}</Button>
        <Button disabled={locked || !dirty} onClick={save}>{state.saving ? '保存中…' : '保存'}</Button>
      </div>
      {locked && state.translation.engine_status !== 'IDLE' ? <Banner tone="info">任务执行期间只读，结束后再保存。</Banner> : null}
      {titles.length === 0 ? <Empty>还没有称呼词</Empty> : (
        <div className="rb-honorific-list">
          {titles.map((title, index) => (
            <div className="rb-honorific-row" key={index}>
              <span>{index + 1}</span>
              <TextInput aria-label={`称呼词 ${index + 1}`} placeholder="例如 mr" value={title} disabled={locked} onChange={(event) => {
                const value = event.currentTarget.value;
                setTitles((previous) => previous.map((item, i) => (i === index ? value : item)));
                setDirty(true);
              }} />
              <Button color="red" variant="subtle" size="xs" disabled={locked} onClick={() => { setTitles((previous) => previous.filter((_, i) => i !== index)); setDirty(true); }}>移除</Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
