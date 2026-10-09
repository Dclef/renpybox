/** 接口管理：复用现有配置与密钥存储，编辑时只提交实际修改的接口字段。 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { Accordion, ActionIcon, Autocomplete, Button, Checkbox, Menu, Modal, Paper, NumberInput, Select, Textarea, TextInput } from '@mantine/core';
import { Cloud, Cpu, Languages, MoreHorizontal, Pencil, Plus, Send, Settings } from 'lucide-react';

import { useT } from '../i18n';
import { getTranslationState, request } from '../api';
import type { AppState } from '../useAppState';
import { Banner, Dialog, Empty, PageHeader, SettingsGroup } from '../ui';

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
  { key: 'local', title: '本地模型', description: '本机部署，延迟低', icon: Cpu },
  { key: 'machine', title: '传统机翻', description: '无需模型配置', icon: Languages },
  { key: 'online', title: '在线大模型', description: '官方与云端服务', icon: Cloud },
  { key: 'custom', title: '自定义接口', description: '兼容 OpenAI 等协议', icon: Settings },
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
  const t = useT();
  const [models, setModels] = useState<string[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);
  const modelRequest = useRef(0);
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
    modelRequest.current += 1;
    setModels([]);
    setLoadingModels(false);
    const next = makeEditor(platform);
    setEditor(next);
    setOriginal(next);
    window.requestAnimationFrame(() => editorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
  }
  function closeEditor() {
    if (!dirty || window.confirm('放弃尚未保存的接口修改？')) {
      modelRequest.current += 1;
      setLoadingModels(false);
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
  async function loadModels() {
    if (editor?.id == null) return;
    const id = ++modelRequest.current;
    setLoadingModels(true);
    try {
      const result = await request<{ models: string[] }>('/api/platforms/' + editor.id + '/models');
      if (id !== modelRequest.current) return;
      setModels(result.models);
      if (!result.models.length) state.pushToast('info', t('platform_models_empty'));
    } catch (error) {
      if (id === modelRequest.current) state.pushToast('error', error instanceof Error ? error.message : String(error));
    } finally {
      if (id === modelRequest.current) setLoadingModels(false);
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
      modelRequest.current += 1;
      setLoadingModels(false);
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
  const thinkingOptions = [['OFF', '关闭'], ['LOW', '低'], ['MEDIUM', '中'], ['HIGH', '高'], ['MAX', '最高']] as const;
  return (
    <div className="rb-page rb-platform">
      <PageHeader
        title="接口管理"
        description="配置翻译用的模型服务；当前启用的接口会用于翻译任务"
        actions={(
          <div className="platform-toolbar">
            <TextInput
              w={220}
              maw="100%"
              aria-label="搜索接口"
              placeholder="搜索名称或模型…"
              value={keyword}
              onChange={(event) => setKeyword(event.currentTarget.value)}
            />
            <Button leftSection={<Plus size={16} strokeWidth={1.75} />} disabled={disabled} onClick={() => openEditor()}>
              新增接口
            </Button>
          </div>
        )}
      />

      <div className="rb-platform-summary" data-active={Boolean(active)}>
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

      {testResult ? (
        <Banner tone={testResult.ok ? 'success' : 'warning'} onDismiss={() => setTestResult(null)}>
          {testResult.text}
        </Banner>
      ) : null}

      <div className="rb-platform-body">
        <div className="rb-platform-list">
          {groups.map((group) => {
            const Icon = group.icon;
            return (
              <SettingsGroup
                key={group.key}
                title={(
                  <span className="rb-platform-group-title">
                    <Icon size={16} strokeWidth={1.75} />
                    {group.title}
                  </span>
                )}
                description={group.description}
                actions={<span className="rb-platform-count">{group.items.length}</span>}
              >
                {group.items.map((platform) => {
                  const isActive = platform.id === activeId;
                  return (
                    <Paper withBorder radius="md" className="rb-platform-card" key={platform.id} data-active={isActive || undefined}
                      title={[platform.name, platform.model, platform.api_url].filter(Boolean).join(' · ')}
                      onDoubleClick={() => { if (!disabled) openEditor(platform); }}>
                      <div className="rb-platform-card-head">
                        <strong>{platform.name || '未命名接口'}</strong>
                        <div className="platform-row-actions">
                          <ActionIcon variant="subtle" color="gray" size={28} aria-label={t('platform_test')} title={t('platform_test')}
                            loading={testing === platform.id} disabled={disabled} onClick={() => void startTest(platform)}><Send size={15} /></ActionIcon>
                          <ActionIcon variant="subtle" color="gray" size={28} aria-label={t('platform_edit')} title={t('platform_edit')}
                            disabled={disabled} onClick={() => openEditor(platform)}><Pencil size={15} /></ActionIcon>
                          <Menu position="bottom-end" withinPortal>
                            <Menu.Target><ActionIcon variant="subtle" color="gray" size={28} aria-label={(platform.name || '') + '更多'} disabled={disabled}><MoreHorizontal size={16} /></ActionIcon></Menu.Target>
                            <Menu.Dropdown>
                              <Menu.Item disabled={disabled || isActive} onClick={() => void mutate('/api/platforms/' + platform.id + '/activate', 'POST')}>{isActive ? '已启用' : '启用'}</Menu.Item>
                              <Menu.Item disabled={disabled} onClick={() => openEditor(platform)}>{t('platform_edit')}</Menu.Item>
                              <Menu.Item disabled={disabled} onClick={() => { openEditor(platform); window.setTimeout(() => editorRef.current?.querySelector<HTMLButtonElement>('.mantine-Accordion-control')?.click(), 50); }}>{t('platform_parameters')}</Menu.Item>
                              <Menu.Divider />
                              <Menu.Item color="red" disabled={disabled} onClick={() => setDeleting(platform)}>删除</Menu.Item>
                            </Menu.Dropdown>
                          </Menu>
                        </div>
                      </div>
                      <div className="rb-platform-card-meta"><span className="rb-platform-badge">{platform.api_format || '—'}</span><span>{modelLabel(platform)}</span>{isActive && <i aria-label="使用中" title="使用中" />}</div>
                    </Paper>
                  );
                })}
              </SettingsGroup>
            );
          })}

          {groups.length === 0 ? (
            <Empty>{keyword ? '没有匹配的接口，试试其他名称或模型' : '还没有翻译接口，点击「新增接口」配置第一个服务'}</Empty>
          ) : null}

          {state.translation.engine_status !== 'IDLE' && testing === null ? (
            <Banner tone="info">任务正在执行，结束后可以修改或切换接口。</Banner>
          ) : null}
        </div>

        {editor ? (
          <Modal opened onClose={closeEditor} title={editor.id === null ? '新增接口' : '编辑接口'} size="lg" centered closeOnClickOutside={false}>
          <form
            ref={editorRef}
            className="platform-editor"
            onSubmit={(event) => {
              event.preventDefault();
              void saveEditor();
            }}
          >
            <div className="rb-platform-editor-head">
              <div>
                <h2>{editor.id === null ? '新增接口' : '编辑接口'}</h2>
                <span>{dirty ? '有未保存的修改' : '保存后即可用于翻译'}</span>
              </div>
              <Button type="button" variant="default" disabled={busy} onClick={closeEditor}>关闭</Button>
            </div>

            <TextInput
              label="接口名称"
              required
              maxLength={128}
              autoFocus
              value={editor.name}
              onChange={(event) => setEditor({ ...editor, name: event.currentTarget.value })}
              placeholder="例如：DeepSeek / Claude"
            />
            <Select
              label="分组"
              allowDeselect={false}
              value={editor.group}
              data={GROUPS.map((group) => ({ value: group.key, label: group.title }))}
              onChange={(value) => { if (value) setEditor({ ...editor, group: value }); }}
            />
            <Select
              label="接口协议"
              allowDeselect={false}
              value={editor.api_format}
              data={FORMATS}
              onChange={(value) => {
                if (!value) return;
                setEditor({
                  ...editor,
                  api_format: value,
                  ...(['GoogleFree', 'Bing'].includes(value) ? { group: 'machine' } : {}),
                });
              }}
            />
            {!machine ? (
              <>
                <Autocomplete label="模型名称" required maxLength={256} data={models}
                  value={editor.model} onChange={(model) => setEditor({ ...editor, model })}
                  placeholder="服务商提供的模型 ID" limit={50} />
                <Button type="button" variant="default" loading={loadingModels}
                  disabled={disabled || editor.id === null || editor.api_url !== original?.api_url || editor.api_format !== original?.api_format || !!editor.keys.trim() || editor.clearKeys}
                  onClick={() => void loadModels()}>{t('platform_load_models')}</Button>
                <span className="rb-metric-note">{t('platform_models_saved_hint')}</span>
              </>
            ) : null}
            {!machine ? (
              <TextInput
                label="接口地址"
                required
                type="url"
                maxLength={2048}
                value={editor.api_url}
                onChange={(event) => setEditor({ ...editor, api_url: event.currentTarget.value })}
                placeholder="https://api.example.com/v1"
              />
            ) : null}
            {!machine ? (
              <>
                <Textarea
                  label="API 密钥"
                  autosize
                  minRows={2}
                  value={editor.keys}
                  disabled={editor.clearKeys}
                  autoComplete="off"
                  spellCheck={false}
                  onChange={(event) => setEditor({ ...editor, keys: event.currentTarget.value })}
                  placeholder={editor.id === null ? '每行一把密钥；无需密钥可留空' : '留空保留原密钥；输入新密钥将替换原值'}
                />
                <p className="rb-platform-help">已有密钥不回显。支持多把密钥，每行一把。</p>
              </>
            ) : null}
            {!machine && editor.id !== null ? (
              <Checkbox
                checked={editor.clearKeys}
                label="清空此接口已保存的密钥"
                onChange={(event) => setEditor({ ...editor, clearKeys: event.currentTarget.checked })}
              />
            ) : null}
            {!machine && editor.api_format !== 'SakuraLLM' ? (
              <Select
                label="思考等级"
                allowDeselect={false}
                value={editor.thinking_level}
                data={thinkingOptions.map(([value, label]) => ({ value, label }))}
                onChange={(value) => { if (value) setEditor({ ...editor, thinking_level: value }); }}
              />
            ) : null}

            {!machine ? (
              <Accordion variant="contained">
                <Accordion.Item value="sampling">
                  <Accordion.Control>高级采样参数</Accordion.Control>
                  <Accordion.Panel>
                    <div className="rb-platform-params">
                      {PARAMETERS.map((parameter) => {
                        const enableKey = `${parameter.key}_custom_enable` as keyof Editor;
                        return (
                          <div className="rb-platform-param" key={parameter.key}>
                            <Checkbox
                              checked={Boolean(editor[enableKey])}
                              label={parameter.label}
                              onChange={(event) => setEditor({ ...editor, [enableKey]: event.currentTarget.checked })}
                            />
                            <NumberInput
                              step={0.01}
                              decimalScale={2}
                              min={parameter.min}
                              max={parameter.max}
                              disabled={!editor[enableKey]}
                              value={editor[parameter.key]}
                              onChange={(value) => setEditor({ ...editor, [parameter.key]: typeof value === 'number' ? value : 0 })}
                              aria-label={parameter.label}
                            />
                          </div>
                        );
                      })}
                    </div>
                  </Accordion.Panel>
                </Accordion.Item>
              </Accordion>
            ) : null}

            <div className="rb-platform-editor-footer">
              <Button type="button" variant="default" disabled={busy} onClick={closeEditor}>取消</Button>
              <Button type="submit" disabled={disabled || !editor.name.trim() || (editor.id !== null && !dirty)}>
                {busy ? '保存中…' : '保存接口'}
              </Button>
            </div>
          </form>
          </Modal>
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
