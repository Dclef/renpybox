/** 接口管理：复用现有配置与密钥存储，编辑时只提交实际修改的接口字段。 */

import { useEffect, useMemo, useRef, useState } from 'react';

import { getTranslationState, request } from '../api';
import type { AppState } from '../useAppState';
import { IconIot, IconRobot, IconSetting, IconSync } from '../icons';
import { Banner, Dialog, Empty } from '../ui';

interface PlatformEntry {
  id: number;
  name?: string;
  group?: string;
  model?: string;
  api_url?: string;
  api_format?: string;
  thinking?: { level?: string } | boolean;
  [key: string]: unknown;
}

interface Editor {
  id: number | null;
  name: string;
  group: string;
  api_format: string;
  api_url: string;
  model: string;
  thinking_level: string;
  keys: string;
  clearKeys: boolean;
  top_p: number;
  temperature: number;
  presence_penalty: number;
  frequency_penalty: number;
  top_p_custom_enable: boolean;
  temperature_custom_enable: boolean;
  presence_penalty_custom_enable: boolean;
  frequency_penalty_custom_enable: boolean;
}

const GROUPS = [
  { key: 'local', title: '本地模型', description: '本机部署，延迟低', icon: IconRobot },
  { key: 'machine', title: '传统机翻', description: '无需模型配置', icon: IconSync },
  { key: 'online', title: '在线大模型', description: '官方与云端服务', icon: IconIot },
  { key: 'custom', title: '自定义接口', description: '兼容 OpenAI 等协议', icon: IconSetting },
];
const FORMATS = ['OpenAI', 'Google', 'Anthropic', 'SakuraLLM', 'GoogleFree', 'Bing'];
const PARAMETERS = [
  { key: 'top_p', label: 'Top P', min: 0, max: 1 },
  { key: 'temperature', label: '温度', min: 0, max: 2 },
  { key: 'presence_penalty', label: '存在惩罚', min: -2, max: 2 },
  { key: 'frequency_penalty', label: '频率惩罚', min: -2, max: 2 },
] as const;

function inferGroup(platform: PlatformEntry): string {
  if (GROUPS.some((group) => group.key === platform.group)) return String(platform.group);
  if (['GoogleFree', 'Bing'].includes(String(platform.api_format))) return 'machine';
  if (platform.api_format === 'SakuraLLM' || /127\.0\.0\.1|localhost|0\.0\.0\.0|\[::1\]/i.test(String(platform.api_url))) return 'local';
  if (/^(自定义|custom)/i.test(String(platform.name))) return 'custom';
  return 'online';
}

function modelLabel(platform: PlatformEntry): string {
  if (!platform.model || platform.model === 'no_model_required') return '无需指定模型';
  return String(platform.model);
}

function makeEditor(platform?: PlatformEntry): Editor {
  return {
    id: platform?.id ?? null,
    name: String(platform?.name ?? ''),
    group: platform ? inferGroup(platform) : 'custom',
    api_format: String(platform?.api_format ?? 'OpenAI'),
    api_url: String(platform?.api_url ?? ''),
    model: String(platform?.model ?? ''),
    thinking_level: typeof platform?.thinking === 'object' ? platform.thinking.level ?? 'OFF' : platform?.thinking ? 'HIGH' : 'OFF',
    keys: '',
    clearKeys: false,
    top_p: Number(platform?.top_p ?? 0.95),
    temperature: Number(platform?.temperature ?? 0.95),
    presence_penalty: Number(platform?.presence_penalty ?? 0),
    frequency_penalty: Number(platform?.frequency_penalty ?? 0),
    top_p_custom_enable: platform?.top_p_custom_enable === true,
    temperature_custom_enable: platform?.temperature_custom_enable === true,
    presence_penalty_custom_enable: platform?.presence_penalty_custom_enable === true,
    frequency_penalty_custom_enable: platform?.frequency_penalty_custom_enable === true,
  };
}

export function PlatformPage(props: { state: AppState; onDirtyChange?: (dirty: boolean) => void }) {
  const { state, onDirtyChange } = props;
  const platforms = useMemo(
    () => (Array.isArray(state.settings?.values.platforms) ? (state.settings.values.platforms as PlatformEntry[]) : []),
    [state.settings?.values.platforms],
  );
  const activeId = Number(state.settings?.values.activate_platform ?? -1);
  const active = platforms.find((platform) => platform.id === activeId);
  const [keyword, setKeyword] = useState('');
  const [editor, setEditor] = useState<Editor | null>(null);
  const [original, setOriginal] = useState<Editor | null>(null);
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState<number | null>(null);
  const [deleting, setDeleting] = useState<PlatformEntry | null>(null);
  const [testResult, setTestResult] = useState<{ ok: boolean; text: string } | null>(null);
  const editorRef = useRef<HTMLFormElement>(null);
  const testPending = useRef(false);
  const dirty = editor !== null && JSON.stringify(editor) !== JSON.stringify(original);
  const disabled =
    busy ||
    state.saving ||
    state.translation.engine_status !== 'IDLE' ||
    state.translation.stop_barrier ||
    state.translation.single_tasks ||
    testing !== null;
  const groups = GROUPS.map((group) => ({
    ...group,
    items: platforms.filter(
      (platform) =>
        inferGroup(platform) === group.key &&
        `${platform.name} ${platform.model} ${platform.api_url}`.toLowerCase().includes(keyword.toLowerCase()),
    ),
  })).filter((group) => group.items.length > 0);

  useEffect(() => {
    onDirtyChange?.(dirty);
  }, [dirty, onDirtyChange]);
  useEffect(() => () => onDirtyChange?.(false), [onDirtyChange]);
  useEffect(
    () =>
      state.subscribe((event) => {
        if (event.event !== 'PLATFORM_TEST_DONE' || !testPending.current) return;
        const data = event.data as { result?: boolean; result_msg?: string };
        testPending.current = false;
        setTesting(null);
        setTestResult({ ok: data.result !== false, text: data.result_msg || '接口测试已完成' });
        void state.reloadTranslation();
      }),
    [state.subscribe, state.reloadTranslation],
  );
  useEffect(() => {
    if (testing === null) return;
    const timer = window.setInterval(() => {
      void getTranslationState()
        .then((snapshot) => {
          if (snapshot.engine_status === 'IDLE' && testPending.current) {
            testPending.current = false;
            setTesting(null);
            setTestResult({ ok: false, text: '接口测试已结束，未收到结果。请检查连接后重试。' });
          }
        })
        .catch(() => {
          testPending.current = false;
          setTesting(null);
          setTestResult({ ok: false, text: '后端连接已中断，请恢复连接后重试。' });
        });
    }, 2500);
    return () => window.clearInterval(timer);
  }, [testing]);

  function openEditor(platform?: PlatformEntry) {
    if (dirty && !window.confirm('有尚未保存的接口修改，是否放弃？')) return;
    const next = makeEditor(platform);
    setEditor(next);
    setOriginal(next);
    window.requestAnimationFrame(() => editorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
  }
  function closeEditor() {
    if (!dirty || window.confirm('放弃尚未保存的接口修改？')) {
      setEditor(null);
      setOriginal(null);
    }
  }
  async function mutate(path: string, method: string, body?: Record<string, unknown>): Promise<boolean> {
    setBusy(true);
    try {
      await request(path, { method, ...(body ? { body: JSON.stringify(body) } : {}) });
      await state.reloadSettings();
      return true;
    } catch (error) {
      state.pushToast('error', error instanceof Error ? error.message : String(error));
      return false;
    } finally {
      setBusy(false);
    }
  }
  async function saveEditor() {
    if (!editor || !editor.name.trim()) return;
    const { id, keys, clearKeys, ...fields } = editor;
    const payload: Record<string, unknown> = Object.fromEntries(
      Object.entries(fields).filter(([key, value]) => id === null || value !== original?.[key as keyof Editor]),
    );
    if (clearKeys) payload.api_keys = [];
    else if (keys.trim()) payload.api_keys = keys.split(/\r?\n/).map((key) => key.trim()).filter(Boolean);
    if (await mutate(`/api/platforms${id === null ? '' : `/${id}`}`, id === null ? 'POST' : 'PATCH', payload)) {
      setEditor(null);
      setOriginal(null);
      state.pushToast('success', id === null ? '接口已新增' : '接口已保存');
    }
  }
  async function startTest(platform: PlatformEntry) {
    testPending.current = true;
    setTesting(platform.id);
    setTestResult(null);
    try {
      await request(`/api/platforms/${platform.id}/test`, { method: 'POST' });
      await state.reloadTranslation();
    } catch (error) {
      testPending.current = false;
      setTesting(null);
      state.pushToast('error', error instanceof Error ? error.message : String(error));
    }
  }
  const machine = editor !== null && ['GoogleFree', 'Bing'].includes(editor.api_format);

  return (
    <div className="settings-layout platform-page">
      <header className="settings-header">
        <h1 className="settings-title">接口管理</h1>
        <p className="settings-subtitle">配置翻译用的模型服务；当前启用的接口会用于翻译任务</p>
      </header>

      <div className="settings-scroll platform-scroll">
        <div className="platform-toolbar">
          <div className="platform-summary" data-active={Boolean(active)}>
            <span className="platform-status" data-active={Boolean(active)} aria-hidden="true" />
            {active ? (
              <div className="platform-summary-copy">
                <strong>{active.name || '未命名接口'}</strong>
                <span>{modelLabel(active)} · 用于翻译</span>
              </div>
            ) : (
              <div className="platform-summary-copy">
                <strong>未启用接口</strong>
                <span>选择一个接口后开始翻译</span>
              </div>
            )}
          </div>
          <div className="platform-toolbar-actions">
            <input
              className="input platform-search"
              aria-label="搜索接口"
              placeholder="搜索名称或模型…"
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
            />
            <button type="button" className="btn btn-primary" disabled={disabled} onClick={() => openEditor()}>
              新增接口
            </button>
          </div>
        </div>

        {testResult ? (
          <Banner tone={testResult.ok ? 'success' : 'warning'} onDismiss={() => setTestResult(null)}>
            {testResult.text}
          </Banner>
        ) : null}

        {editor ? (
          <form
            ref={editorRef}
            className="platform-editor"
            onSubmit={(event) => {
              event.preventDefault();
              void saveEditor();
            }}
          >
            <div className="platform-editor-heading">
              <div>
                <h2>{editor.id === null ? '新增接口' : '编辑接口'}</h2>
                <span>{dirty ? '有未保存的修改' : '保存后即可用于翻译'}</span>
              </div>
              <button type="button" className="btn" disabled={busy} onClick={closeEditor}>
                关闭
              </button>
            </div>

            <div className="platform-editor-grid">
              <label className="platform-field">
                接口名称
                <input
                  className="input"
                  required
                  maxLength={128}
                  autoFocus
                  value={editor.name}
                  onChange={(event) => setEditor({ ...editor, name: event.target.value })}
                  placeholder="例如：DeepSeek / Claude"
                />
              </label>
              <label className="platform-field">
                分组
                <select className="select" value={editor.group} onChange={(event) => setEditor({ ...editor, group: event.target.value })}>
                  {GROUPS.map((group) => (
                    <option key={group.key} value={group.key}>
                      {group.title}
                    </option>
                  ))}
                </select>
              </label>
              <label className="platform-field">
                接口协议
                <select
                  className="select"
                  value={editor.api_format}
                  onChange={(event) =>
                    setEditor({
                      ...editor,
                      api_format: event.target.value,
                      ...(['GoogleFree', 'Bing'].includes(event.target.value) ? { group: 'machine' } : {}),
                    })
                  }
                >
                  {FORMATS.map((format) => (
                    <option key={format}>{format}</option>
                  ))}
                </select>
              </label>
              {!machine ? (
                <label className="platform-field">
                  模型名称
                  <input
                    className="input"
                    required
                    maxLength={256}
                    value={editor.model}
                    onChange={(event) => setEditor({ ...editor, model: event.target.value })}
                    placeholder="服务商提供的模型 ID"
                  />
                </label>
              ) : null}
              {!machine ? (
                <label className="platform-field platform-field-wide">
                  接口地址
                  <input
                    className="input"
                    required
                    type="url"
                    maxLength={2048}
                    value={editor.api_url}
                    onChange={(event) => setEditor({ ...editor, api_url: event.target.value })}
                    placeholder="https://api.example.com/v1"
                  />
                </label>
              ) : null}
              {!machine ? (
                <label className="platform-field platform-field-wide">
                  API 密钥
                  <textarea
                    className="textarea"
                    rows={2}
                    value={editor.keys}
                    disabled={editor.clearKeys}
                    autoComplete="off"
                    spellCheck={false}
                    onChange={(event) => setEditor({ ...editor, keys: event.target.value })}
                    placeholder={editor.id === null ? '每行一把密钥；无需密钥可留空' : '留空保留原密钥；输入新密钥将替换原值'}
                  />
                  <span className="platform-field-help">已有密钥不回显。支持多把密钥，每行一把。</span>
                </label>
              ) : null}
              {!machine && editor.id !== null ? (
                <label className="platform-field platform-field-wide platform-check">
                  <input type="checkbox" checked={editor.clearKeys} onChange={(event) => setEditor({ ...editor, clearKeys: event.target.checked })} />
                  清空此接口已保存的密钥
                </label>
              ) : null}
              {!machine && editor.api_format !== 'SakuraLLM' ? (
                <label className="platform-field">
                  思考等级
                  <select className="select" value={editor.thinking_level} onChange={(event) => setEditor({ ...editor, thinking_level: event.target.value })}>
                    {([['OFF', '关闭'], ['LOW', '低'], ['MEDIUM', '中'], ['HIGH', '高'], ['MAX', '最高']] as const).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
            </div>

            {!machine ? (
              <details className="platform-parameters">
                <summary>高级采样参数</summary>
                <div className="platform-editor-grid">
                  {PARAMETERS.map((parameter) => {
                    const enableKey = `${parameter.key}_custom_enable` as keyof Editor;
                    return (
                      <label className="platform-field" key={parameter.key}>
                        <span className="platform-check">
                          <input
                            type="checkbox"
                            checked={Boolean(editor[enableKey])}
                            onChange={(event) => setEditor({ ...editor, [enableKey]: event.target.checked })}
                          />
                          {parameter.label}
                        </span>
                        <input
                          className="input"
                          type="number"
                          step="0.01"
                          min={parameter.min}
                          max={parameter.max}
                          disabled={!editor[enableKey]}
                          value={editor[parameter.key]}
                          onChange={(event) => setEditor({ ...editor, [parameter.key]: Number(event.target.value) })}
                        />
                      </label>
                    );
                  })}
                </div>
              </details>
            ) : null}

            <div className="platform-editor-footer">
              <button type="button" className="btn" disabled={busy} onClick={closeEditor}>
                取消
              </button>
              <button type="submit" className="btn btn-primary" disabled={disabled || !editor.name.trim() || (editor.id !== null && !dirty)}>
                {busy ? '保存中…' : '保存接口'}
              </button>
            </div>
          </form>
        ) : null}

        {groups.map((group) => {
          const Icon = group.icon;
          return (
            <section className="platform-list" key={group.key}>
              <div className="platform-group-heading">
                <span className="platform-group-icon" aria-hidden="true">
                  <Icon size={16} />
                </span>
                <div className="platform-group-copy">
                  <h2>{group.title}</h2>
                  <p>{group.description}</p>
                </div>
                <span className="platform-group-count">{group.items.length}</span>
              </div>
              <div className="platform-rows">
                {group.items.map((platform) => {
                  const isActive = platform.id === activeId;
                  return (
                    <article className="platform-row" key={platform.id} data-active={isActive || undefined}>
                      <div className="platform-row-main">
                        <div className="platform-row-title">
                          <strong>{platform.name || '未命名接口'}</strong>
                          {isActive ? <span className="platform-active-label">使用中</span> : null}
                          <span className="platform-item-badge">{platform.api_format || '—'}</span>
                        </div>
                        <div className="platform-row-meta">
                          <span className="platform-row-model">{modelLabel(platform)}</span>
                          <span className="platform-row-url" title={platform.api_url}>
                            {platform.api_url || '无需配置地址'}
                          </span>
                        </div>
                      </div>
                      <div className="platform-row-actions">
                        <button className="btn" type="button" disabled={disabled} onClick={() => void startTest(platform)}>
                          {testing === platform.id ? '测试中…' : '测试'}
                        </button>
                        <button className="btn" type="button" disabled={disabled} onClick={() => openEditor(platform)}>
                          编辑
                        </button>
                        {isActive ? (
                          <button className="btn" type="button" disabled title="当前已在使用">
                            已启用
                          </button>
                        ) : (
                          <button
                            className="btn btn-primary"
                            type="button"
                            disabled={disabled}
                            onClick={() => void mutate(`/api/platforms/${platform.id}/activate`, 'POST')}
                          >
                            启用
                          </button>
                        )}
                        <button
                          className="btn btn-danger-text"
                          type="button"
                          disabled={disabled}
                          onClick={() => {
                            if (!dirty || window.confirm('删除接口会关闭编辑面板，是否放弃尚未保存的修改？')) setDeleting(platform);
                          }}
                        >
                          删除
                        </button>
                      </div>
                    </article>
                  );
                })}
              </div>
            </section>
          );
        })}

        {groups.length === 0 ? (
          <Empty>{keyword ? '没有匹配的接口，试试其他名称或模型' : '还没有翻译接口，点击「新增接口」配置第一个服务'}</Empty>
        ) : null}

        {state.translation.engine_status !== 'IDLE' && testing === null ? (
          <Banner tone="info">任务正在执行，结束后可以修改或切换接口。</Banner>
        ) : null}
      </div>

      {deleting ? (
        <Dialog
          title="删除接口"
          confirmText="删除"
          onCancel={() => setDeleting(null)}
          onConfirm={() => {
            if (busy) return;
            void mutate(`/api/platforms/${deleting.id}`, 'DELETE').then((ok) => {
              if (ok) {
                setEditor(null);
                setOriginal(null);
                setDeleting(null);
                state.pushToast('success', '接口已删除');
              }
            });
          }}
        >
          确定删除「{deleting.name}」？对应的密钥也会一并移除。
          {deleting.id === activeId ? ' 删除当前接口后，将自动使用列表中的第一个接口。' : ''}
        </Dialog>
      ) : null}
    </div>
  );
}
