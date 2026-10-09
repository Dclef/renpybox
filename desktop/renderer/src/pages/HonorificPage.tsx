/** 称呼桥接：把 Mr.[name] 这类「称呼 + 变量」交给翻译前处理。 */
import { useEffect, useState } from 'react';
import type { AppState } from '../useAppState';
import { Button, Input, Table } from 'antd';
import { Banner } from '../ui';

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
    <div className="settings-layout glossary-layout">
      <header className="settings-header">
        <h1 className="settings-title">称呼桥接</h1>
        <p className="settings-subtitle">识别 Mr.[name]、Dr.[name] 这类称呼加变量，避免模型丢掉变量或把中文语序写乱。</p>
      </header>
      <div className="settings-scroll glossary-scroll">
        <div className="workspace-toolbar">
          <div className="workspace-summary">
            <strong>{titles.filter((title) => title.trim()).length} 个称呼词</strong>
            <span>{dirty ? '有未保存修改' : enabled ? '翻译前会自动桥接' : '当前未启用'}</span>
          </div>
          <button type="button" className="btn btn-primary" disabled={locked || !dirty} onClick={save}>
            {state.saving ? '保存中…' : '保存'}
          </button>
        </div>
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={enabled}
            disabled={locked}
            onChange={(event) => {
              setEnabled(event.target.checked);
              setDirty(true);
            }}
          />
          启用称呼变量桥接
        </label>
        {locked && state.translation.engine_status !== 'IDLE' ? (
          <Banner tone="info">任务执行期间只读，结束后再保存。</Banner>
        ) : null}
        <div className="workspace-actions">
          <button
            type="button"
            className="btn"
            disabled={locked}
            onClick={() => {
              setTitles((previous) => ['', ...previous]);
              setDirty(true);
            }}
          >
            新增称呼词
          </button>
        </div>
        <Table
          className="data-sheet"
          size="small"
          bordered
          pagination={false}
          rowKey="index"
          dataSource={titles.map((title, index) => ({ title, index }))}
          locale={{ emptyText: '还没有称呼词' }}
          columns={[
            { title: '序号', dataIndex: 'index', width: 72, render: (index: number) => index + 1 },
            {
              title: '称呼词',
              render: (_, record) => (
                <Input
                  aria-label={`称呼词 ${record.index + 1}`}
                  value={record.title}
                  disabled={locked}
                  placeholder="例如 mr"
                  onChange={(event) => {
                    const value = event.target.value;
                    setTitles((previous) => previous.map((item, i) => (i === record.index ? value : item)));
                    setDirty(true);
                  }}
                />
              ),
            },
            {
              title: '操作',
              width: 88,
              render: (_, record) => (
                <Button
                  danger
                  type="link"
                  disabled={locked}
                  onClick={() => {
                    setTitles((previous) => previous.filter((_, i) => i !== record.index));
                    setDirty(true);
                  }}
                >
                  移除
                </Button>
              ),
            },
          ]}
        />
      </div>
    </div>
  );
}
