/** 称呼桥接：把 Mr.[name] 这类「称呼 + 变量」交给翻译前处理。 */
import { useEffect, useState } from 'react';
import { Button, Checkbox, TextInput } from '@mantine/core';

import type { AppState } from '../useAppState';
import { Banner, Empty } from '../ui';

function readTitles(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => String(item ?? ''));
}

export function HonorificPage(props: { state: AppState; onDirtyChange?: (dirty: boolean) => void }) {
  const { state, onDirtyChange } = props;
  const [titles, setTitles] = useState<string[]>(() => readTitles(state.settings?.values.honorific_placeholder_titles));
  const [enabled, setEnabled] = useState(state.settings?.values.honorific_placeholder_bridge_enable !== false);
  const [dirty, setDirty] = useState(false);
  const locked = state.saving || state.translation.engine_status !== 'IDLE' || state.translation.stop_barrier;

  useEffect(() => {
    if (dirty) return;
    setTitles(readTitles(state.settings?.values.honorific_placeholder_titles));
    setEnabled(state.settings?.values.honorific_placeholder_bridge_enable !== false);
  }, [dirty, state.settings?.values.honorific_placeholder_titles, state.settings?.values.honorific_placeholder_bridge_enable]);

  useEffect(() => {
    onDirtyChange?.(dirty);
    return () => onDirtyChange?.(false);
  }, [dirty, onDirtyChange]);

  const save = () => {
    const cleaned = titles.map((title) => title.trim()).filter(Boolean);
    state.setSetting('honorific_placeholder_titles', cleaned);
    state.setSetting('honorific_placeholder_bridge_enable', enabled);
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
