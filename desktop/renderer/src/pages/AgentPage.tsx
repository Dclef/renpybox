import { useCallback, useEffect, useRef, useState } from 'react';
import { Button, Checkbox, Popover, Select } from 'antd';
import { ArrowDown, Bot, Plus, RefreshCw, Settings, Square } from 'lucide-react';
import * as api from '../api';
import { AgentMessageBody } from '../AgentMessageBody';
import { languageFromTlPath, toolStatusInfo } from '../agentView.mjs';
import type { AgentSnapshot, AgentThinkingLevel } from '../types';
import type { AppState } from '../useAppState';
import { Banner, Dialog } from '../ui';

// 工具中文名与 Qt5 LocalizerZH.agent_page_tool_* 保持一致。
const TOOL_NAMES: Record<string, string> = {
  set_project: '设定项目', get_project_info: '读取项目信息', inspect_translation_project: '检查项目翻译状态',
  list_rpa_files: '查找 RPA 文件', scan_script_errors: '扫描译文脚本错误',
  unpack_rpa_files: '解包 RPA 文件', optimize_old_new_translations: '生成补充兜底补丁',
};
// 空会话快捷任务，与 Qt5 AgentEmptyState 的四张建议卡一致；点击只填入草稿，不直接发送。
const SUGGESTIONS = [
  { text: '检查项目并告诉我下一步', description: '汇总解包、翻译、资产与质量状态' },
  { text: '列出项目中的 RPA 文件', description: '列出 game 目录中的 RPA 归档文件' },
  { text: '扫描译文脚本错误', description: '扫描当前语言翻译目录中的生成 .rpy，不修改任何文件' },
  { text: '优化未生效的 old/new 译文', description: '翻译完成后生成运行时替换补丁' },
];
const DRAFT_KEY = 'renpybox.agent.draft';
// 与 Qt5 AUTO_FOLLOW_THRESHOLD 一致：离底部超过该距离视为用户在回看历史。
const FOLLOW_THRESHOLD = 80;

type AgentConfirmation = NonNullable<AgentSnapshot['confirmation']>;

/** 把服务端可信上下文整理成可读的确认摘要；未知工具只给通用提示，原始参数另行折叠展示。 */
function confirmationSummary(confirmation: AgentConfirmation): { title: string; facts: [string, string][]; note: string } {
  const data = confirmation.data ?? {};
  const text = (key: string) => String(data[key] ?? '');
  const count = (key: string) => String(Number(data[key] ?? 0) || 0);
  if (confirmation.name === 'unpack_rpa_files') {
    return {
      title: '确认解包 RPA',
      facts: [['RPA 文件', `${count('count')} 个`], ['game 目录', text('game_dir')]],
      note: '解包结果会直接写入 game 目录，并可能覆盖同名文件；原 RPA 文件会保留。',
    };
  }
  if (confirmation.name === 'optimize_old_new_translations') {
    return {
      title: '确认生成补充翻译兜底',
      facts: [
        ['语言目录', text('tl_dir')],
        ['补充抽取译文', `${count('old_new_count')} 条`],
        ['独立补漏译文', `${count('supplement_count')} 条`],
        ['最终替换', `${count('total_count')} 条`],
        ['跳过冲突原文', `${count('conflict_count')} 条`],
        ['输出文件', text('output_path')],
      ],
      note: '将按原文从长到短生成运行时替换代码；若已有自动补全 Hook，会先备份再覆盖。',
    };
  }
  return {
    title: `执行前确认 · ${TOOL_NAMES[confirmation.name] || confirmation.name}`,
    facts: [],
    note: `Agent 即将执行「${TOOL_NAMES[confirmation.name] || confirmation.name}」，请核对执行范围。`,
  };
}

function formatRemaining(seconds: number): string {
  const total = Math.max(0, Math.ceil(seconds));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
}

function statusLabel(status?: string): string {
  if (status === 'running') return '处理中';
  if (status === 'cancelled') return '已停止';
  if (status === 'failed') return '执行失败';
  return '';
}

const hasKeys = (value?: Record<string, unknown>) => Boolean(value && Object.keys(value).length);

export function AgentPage(props: { state: AppState; onOpenPlatforms: () => void }) {
  const { state, onOpenPlatforms } = props;
  const [session, setSession] = useState<AgentSnapshot | null>(null);
  const [draft, setDraft] = useState(() => {
    try { return sessionStorage.getItem(DRAFT_KEY) ?? ''; } catch { return ''; }
  });
  const [pending, setPending] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [actionError, setActionError] = useState('');
  const [retry, setRetry] = useState(0);
  const [resetDialog, setResetDialog] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [showLatest, setShowLatest] = useState(false);
  const [dontAskUnpack, setDontAskUnpack] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const autoConfirmedRef = useRef('');
  // 运行中点「新建任务」：先停止，等会话回到 idle 再清空（对齐 Qt5 _reset_after_worker）。
  const resetAfterStopRef = useRef(false);
  const chatRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const followRef = useRef(true);
  const mountedRef = useRef(true);
  const latest = useRef(session);
  latest.current = session;
  useEffect(() => {
    try {
      if (draft) sessionStorage.setItem(DRAFT_KEY, draft);
      else sessionStorage.removeItem(DRAFT_KEY);
    } catch {}
  }, [draft]);
  const accept = useCallback((next: AgentSnapshot) => {
    setSession(previous => previous && previous.session_id === next.session_id && previous.revision > next.revision ? previous : next);
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  useEffect(() => {
    if (state.link !== 'open') return;
    let disposed = false;
    let fetching = false;
    let scheduled: number | undefined;
    const refresh = async () => {
      if (disposed || fetching) return;
      fetching = true;
      try {
        const next = await api.getAgentSession();
        if (!disposed) { accept(next); setLoadError(''); }
      } catch (error) {
        if (!disposed) setLoadError(error instanceof Error ? error.message : String(error));
      } finally { fetching = false; }
    };
    void refresh();
    const unsubscribe = state.subscribe(event => {
      if (event.event !== 'AGENT_UPDATE' || scheduled !== undefined) return;
      scheduled = window.setTimeout(() => { scheduled = undefined; void refresh(); }, 80);
    });
    const interval = window.setInterval(() => {
      if (!latest.current || latest.current.status !== 'idle') void refresh();
    }, 1500);
    return () => {
      disposed = true;
      unsubscribe();
      window.clearInterval(interval);
      if (scheduled !== undefined) window.clearTimeout(scheduled);
    };
  }, [state.link, state.subscribe, retry, accept]);

  useEffect(() => {
    if (followRef.current && chatRef.current) chatRef.current.scrollTop = chatRef.current.scrollHeight;
  }, [session?.revision]);

  const scrollToLatest = () => {
    const chat = chatRef.current;
    followRef.current = true;
    setShowLatest(false);
    if (chat) chat.scrollTop = chat.scrollHeight;
  };

  useEffect(() => {
    if (session?.status !== 'idle' || !session.run_id) return;
    void Promise.all([state.reloadSettings(), state.reloadProject(), state.reloadTranslation()]).catch(() => {});
  }, [session?.status, session?.run_id, state.reloadSettings, state.reloadProject, state.reloadTranslation]);

  const perform = async (operation: () => Promise<AgentSnapshot>): Promise<boolean> => {
    setPending(true);
    setActionError('');
    try {
      const next = await operation();
      if (mountedRef.current) accept(next);
      return true;
    } catch (error) {
      if (mountedRef.current) setActionError(error instanceof Error ? error.message : String(error));
      return false;
    } finally {
      if (mountedRef.current) setPending(false);
    }
  };
  const connected = state.link === 'open';
  const busy = session !== null && session.status !== 'idle';
  const values = state.settings?.values ?? {};
  const platforms = (Array.isArray(values.platforms) ? values.platforms as { id: number; name?: string; model?: string; api_format?: string }[] : [])
    .filter(entry => ['openai', 'anthropic', 'google'].includes(String(entry.api_format ?? '').toLowerCase()));
  const thinkingValue = String(values.agent_thinking_level ?? 'OFF').toUpperCase();
  const thinking = (['OFF', 'LOW', 'MEDIUM', 'HIGH', 'MAX'].includes(thinkingValue) ? thinkingValue : 'OFF') as AgentThinkingLevel;
  const platformId = Number(values.agent_platform ?? -1);
  const platform = platforms.find(entry => entry.id === platformId);
  const canSend = connected && session !== null && !loadError && !!platform && !busy && !pending && !state.saving && !!draft.trim();
  const send = async () => {
    if (!canSend) return;
    followRef.current = true;
    const sent = await perform(() => api.sendAgentMessage(draft.trim(), thinking));
    if (sent && mountedRef.current) { setDraft(''); inputRef.current?.focus(); }
  };
  useEffect(() => {
    if (!resetAfterStopRef.current || session?.status !== 'idle' || !connected) return;
    resetAfterStopRef.current = false;
    void perform(api.resetAgent);
  }, [session?.status, connected]);

  const startNewTask = () => {
    setResetDialog(false);
    if (!busy) { void perform(api.resetAgent); return; }
    resetAfterStopRef.current = true;
    if (session?.status === 'stopping') return;
    void perform(api.stopAgent).then(stopped => { if (!stopped) resetAfterStopRef.current = false; });
  };

  const projectPath = String(state.project?.renpy_project_path ?? '');
  const projectName = projectPath.split(/[\\/]/).filter(Boolean).at(-1) || '未设置项目';
  // 对齐 Qt5 项目胶囊「项目名 · 语言」；语言取翻译目录 game/tl/<语言>。
  const projectLanguage = languageFromTlPath(state.project?.renpy_tl_folder);
  const projectLabel = projectPath && projectLanguage ? `${projectName} · ${projectLanguage}` : projectName;
  const confirmation = session?.confirmation;
  const runStatus = !connected ? 'offline' : busy ? (session?.status === 'stopping' ? 'stopping' : 'busy') : 'idle';
  const runStatusText = runStatus === 'offline' ? '未连接' : runStatus === 'stopping' ? '停止中' : runStatus === 'busy' ? '处理中' : '就绪';
  // agent_unpack_auto_confirm 与 Qt5 共用：勾选「不再询问」后解包确认由页面自动放行。
  const unpackAutoConfirm = values.agent_unpack_auto_confirm === true;
  const autoApprove = confirmation?.name === 'unpack_rpa_files' && unpackAutoConfirm;
  const remaining = confirmation ? confirmation.expires_at - now / 1000 : 0;
  const expired = Boolean(confirmation) && remaining <= 0;

  useEffect(() => {
    setDontAskUnpack(false);
    if (!confirmation) return;
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [confirmation?.id]);

  useEffect(() => {
    // 每个确认只自动放行一次；失败后保留确认区，交给用户手动处理。
    if (!confirmation || !autoApprove || !connected || autoConfirmedRef.current === confirmation.id) return;
    autoConfirmedRef.current = confirmation.id;
    void perform(() => api.confirmAgentTool(confirmation.id, true));
  }, [confirmation?.id, autoApprove, connected]);

  const resolveConfirmation = async (target: AgentConfirmation, approved: boolean) => {
    const done = await perform(() => api.confirmAgentTool(target.id, approved));
    if (done && approved && target.name === 'unpack_rpa_files' && dontAskUnpack) {
      void state.setSetting('agent_unpack_auto_confirm', true);
    }
  };

  const refreshPlatforms = async () => {
    setRefreshing(true);
    try {
      await state.reloadSettings();
      if (mountedRef.current) state.pushToast('success', 'Agent 接口列表已刷新');
    } catch (error) {
      if (mountedRef.current) setActionError(`刷新接口列表失败：${error instanceof Error ? error.message : String(error)}`);
    } finally {
      if (mountedRef.current) setRefreshing(false);
    }
  };

  const settingsPanel = (
    <div className="agent-settings-panel">
      <Button block icon={<RefreshCw size={14} strokeWidth={1.75} />} loading={refreshing} disabled={!connected} onClick={() => void refreshPlatforms()}>
        刷新接口列表
      </Button>
      <Button block onClick={() => { setSettingsOpen(false); onOpenPlatforms(); }}>管理接口</Button>
      <Checkbox
        checked={!unpackAutoConfirm}
        disabled={!connected || state.saving}
        onChange={event => { void state.setSetting('agent_unpack_auto_confirm', !event.target.checked); }}
      >
        解包 RPA 前确认
      </Checkbox>
    </div>
  );

  return (
    <div className="agent-workspace">
      <header className="agent-topbar">
        <div className="agent-identity">
          <span className="agent-avatar" aria-hidden="true">
            <Bot size={18} strokeWidth={1.75} />
          </span>
          <div className="agent-heading">
            <div className="agent-title-row">
              <h1 className="agent-title">Agent 助手</h1>
              <span className="agent-status" data-state={runStatus}>{runStatusText}</span>
            </div>
            <span
              className="agent-project-pill"
              data-state={projectPath ? 'ready' : 'unset'}
              title={projectPath || '尚未设置项目，请先在项目页选择 Ren\'Py 游戏目录'}
            >
              <span className="agent-project-dot" aria-hidden="true" />
              <span className="agent-project-label">{projectLabel}</span>
            </span>
          </div>
        </div>
        <div className="agent-controls">
          <label className="agent-select">
            <span>接口</span>
            <Select
              style={{ width: 190, maxWidth: '100%' }}
              popupMatchSelectWidth={false}
              aria-label="Agent 接口"
              allowClear={false}
              value={platform ? String(platformId) : '-1'}
              disabled={!connected || busy || pending || state.saving}
              // 与 Qt5 下拉一致显示「名称 [格式]」，便于区分同名模型的不同协议。
              options={[{ value: '-1', label: '选择 Agent 接口' }, ...platforms.map(entry => ({ value: String(entry.id), label: `${entry.name || entry.model || `接口 ${entry.id}`} [${entry.api_format}]` }))]}
              onChange={value => {
                void state.setSetting('agent_platform', Number(value)).then(saved => {
                  if (saved && session?.messages.length) {
                    state.pushToast('info', '已切换 Agent 接口，当前会话上下文仍属于原接口；如需全新上下文请点击「新建任务」。');
                  }
                });
              }}
            />
          </label>
          <label className="agent-select">
            <span>思考</span>
            <Select
              style={{ width: 120, maxWidth: '100%' }}
              aria-label="Agent 思考等级"
              allowClear={false}
              value={thinking}
              disabled={!connected || busy || pending || state.saving}
              options={([['OFF', '关闭'], ['LOW', '低'], ['MEDIUM', '中'], ['HIGH', '高'], ['MAX', '最高']] as const).map(([value, label]) => ({ value, label }))}
              onChange={value => { state.setSetting('agent_thinking_level', value); }}
            />
          </label>
          <div className="agent-control-actions">
            <Popover
              trigger="click"
              placement="bottomRight"
              title="Agent 设置"
              content={settingsPanel}
              open={settingsOpen}
              onOpenChange={setSettingsOpen}
            >
              <Button type="text" aria-label="Agent 设置" title="Agent 设置" icon={<Settings size={16} strokeWidth={1.75} />} />
            </Popover>
            <Button
              type="primary"
              icon={<Plus size={14} strokeWidth={1.75} />}
              disabled={!connected || !session || pending || session.status === 'stopping' || !session.messages.length}
              onClick={() => setResetDialog(true)}
            >
              新建任务
            </Button>
          </div>
        </div>
      </header>

      {loadError ? <Banner tone="error">加载 Agent 会话失败：{loadError} <Button type="default" size="small" onClick={() => setRetry(previous => previous + 1)}>重试</Button></Banner> : null}
      {actionError ? <Banner tone="error" onDismiss={() => setActionError('')}>{actionError}</Banner> : null}
      {connected && !platform ? (
        <Banner tone="info">
          请选择支持工具调用的 OpenAI、Anthropic 或 Google 接口，不会改变翻译任务的接口设置。
          <Button type="link" size="small" onClick={onOpenPlatforms}>管理接口</Button>
        </Banner>
      ) : null}

      <div className="agent-chat-frame">
        <div ref={chatRef} className="agent-chat" role="log" aria-label="Agent 对话" aria-live="off" onScroll={() => {
          const chat = chatRef.current;
          if (!chat) return;
          followRef.current = chat.scrollHeight - chat.scrollTop - chat.clientHeight < FOLLOW_THRESHOLD;
          setShowLatest(!followRef.current);
        }}>
          {!session?.messages.length ? (
            <div className="agent-empty">
              <span className="agent-empty-icon" aria-hidden="true">
                <Bot size={28} strokeWidth={1.75} />
              </span>
              <h2>从当前项目开始</h2>
              <p>用自然语言检查项目、查询进度或调用现有工具。需要确认的操作会先显示执行范围。</p>
              {!projectPath ? <p className="agent-empty-hint">尚未设置项目：可先在项目页选择 Ren'Py 游戏目录，或在消息中告诉 Agent 项目路径。</p> : null}
              <div className="agent-suggestions">
                {SUGGESTIONS.map(item => (
                  <button
                    type="button"
                    key={item.text}
                    className="agent-suggestion"
                    title={item.description}
                    disabled={busy}
                    onClick={() => {
                      setDraft(item.text);
                      // 与 Qt5 一致：填入后聚焦并全选，便于直接发送或改写。
                      requestAnimationFrame(() => { inputRef.current?.focus(); inputRef.current?.select(); });
                    }}
                  >
                    <span className="agent-suggestion-copy">
                      <span className="agent-suggestion-text">{item.text}</span>
                      <span className="agent-suggestion-desc">{item.description}</span>
                    </span>
                    <span className="agent-suggestion-arrow" aria-hidden="true">↗</span>
                  </button>
                ))}
              </div>
            </div>
          ) : session.messages.map(message => {
            const label = statusLabel(message.status);
            return (
              <article className="agent-message" data-role={message.role} data-status={message.status} key={message.id}>
                <div className="agent-message-meta">
                  <strong>{message.role === 'user' ? '你' : 'Agent'}</strong>
                  {label ? <span className="agent-message-status" data-status={message.status}>{label}</span> : null}
                </div>
                {message.reasoning ? (
                  <details className="agent-detail">
                    <summary>思考过程</summary>
                    <div className="agent-plain-text">{message.reasoning}</div>
                  </details>
                ) : null}
                {message.tools?.map((tool, index) => {
                  const info = toolStatusInfo(tool);
                  return (
                    // 失败时默认展开，让错误原因直接可见；其余状态折叠，点击查看参数和结果。
                    <details className="agent-detail agent-tool" key={index} data-status={info.tone} open={info.tone === 'failed'}>
                      <summary>
                        <span className="agent-tool-name" title={tool.name}>{TOOL_NAMES[tool.name] || tool.name}</span>
                        <span className="agent-tool-status">{info.label}</span>
                      </summary>
                      {tool.message ? <p className="agent-tool-message">{tool.message}</p> : null}
                      {!tool.message && tool.status === 'running' ? <p className="agent-tool-message">正在执行，完成后在此显示结果…</p> : null}
                      {hasKeys(tool.arguments) ? (
                        <>
                          <span className="agent-tool-label">调用参数</span>
                          <pre>{JSON.stringify(tool.arguments, null, 2)}</pre>
                        </>
                      ) : null}
                      {hasKeys(tool.data) ? (
                        <>
                          <span className="agent-tool-label">执行结果</span>
                          <pre>{JSON.stringify(tool.data, null, 2)}</pre>
                        </>
                      ) : null}
                    </details>
                  );
                })}
                {message.role === 'assistant' ? <AgentMessageBody text={message.content} /> : <div className="agent-plain-text">{message.content}</div>}
                {message.status === 'running' && !message.content ? (
                  <span className="agent-processing">
                    <span className="agent-processing-dots" aria-hidden="true"><i /><i /><i /></span>
                    {confirmation ? '等待你确认工具操作' : '正在处理请求…'}
                  </span>
                ) : null}
                {/* 主动停止/拒绝属于正常结束（Qt5 不追加错误条），用中性色提示，失败才用错误色。 */}
                {message.error ? <div className="agent-message-error" role="status" data-tone={message.status === 'cancelled' ? 'cancelled' : 'failed'}>{message.error}</div> : null}
                {message.role === 'assistant' && message.content ? (
                  <button
                    type="button"
                    className="agent-copy"
                    onClick={() => {
                      void navigator.clipboard.writeText(message.content)
                        .then(() => state.pushToast('success', '回复已复制'))
                        .catch(() => state.pushToast('error', '无法访问剪贴板，请手动复制'));
                    }}
                  >
                    复制回复
                  </button>
                ) : null}
              </article>
            );
          })}
        </div>
        {showLatest && session?.messages.length ? (
          <Button
            className="agent-scroll-latest"
            shape="circle"
            aria-label="回到最新消息"
            title="回到最新消息"
            icon={<ArrowDown size={16} strokeWidth={1.75} />}
            onClick={scrollToLatest}
          />
        ) : null}
      </div>

      {confirmation ? (() => {
        const summary = confirmationSummary(confirmation);
        const locked = !connected || pending;
        return (
          <section className="agent-confirmation" aria-label="工具执行确认">
            <div className="agent-confirmation-copy">
              <strong>{summary.title}</strong>
              <p>{summary.note}拒绝或超时后不会执行此工具；已开始的写入操作不保证立即停止。</p>
            </div>
            {summary.facts.length ? (
              <dl className="agent-confirmation-facts">
                {summary.facts.map(([label, value]) => (
                  <div key={label}>
                    <dt>{label}</dt>
                    <dd title={value}>{value || '—'}</dd>
                  </div>
                ))}
              </dl>
            ) : null}
            <details className="agent-detail" open={!summary.facts.length}>
              <summary>执行参数</summary>
              <pre>{JSON.stringify({ arguments: confirmation.arguments, context: confirmation.data }, null, 2)}</pre>
            </details>
            <div className="agent-confirmation-actions">
              {confirmation.name === 'unpack_rpa_files' ? (
                <Checkbox checked={dontAskUnpack} disabled={locked || autoApprove} onChange={event => setDontAskUnpack(event.target.checked)}>
                  以后自动解包，不再询问
                </Checkbox>
              ) : null}
              <span role="timer" aria-live="off">
                {autoApprove && pending ? '已开启自动解包，正在确认…' : expired ? '确认已超时' : `剩余 ${formatRemaining(remaining)}`}
              </span>
              <Button type="default" disabled={locked || expired} onClick={() => void resolveConfirmation(confirmation, false)}>拒绝执行</Button>
              <Button type="primary" disabled={locked || expired} onClick={() => void resolveConfirmation(confirmation, true)}>确认执行</Button>
            </div>
          </section>
        );
      })() : null}

      <form className="agent-composer" onSubmit={event => { event.preventDefault(); void send(); }}>
        <textarea
          ref={inputRef}
          aria-label="给 Agent 的消息"
          placeholder="描述你希望检查或处理的内容…"
          value={draft}
          maxLength={16000}
          rows={3}
          onChange={event => setDraft(event.target.value)}
          onKeyDown={event => {
            if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) {
              event.preventDefault();
              void send();
            }
          }}
        />
        <div className="agent-composer-footer">
          <span role="status">
            {!connected
              ? '后端未连接，草稿会保留'
              : session?.status === 'stopping'
                ? '正在停止，请等待当前操作返回'
                : confirmation
                  ? '等待确认工具操作，请在上方确认或拒绝'
                  : busy
                    ? '任务处理中；可以先编写下一条消息'
                    : !platform
                      ? '请先在右上角选择 Agent 接口'
                      : 'Enter 发送 · Shift+Enter 换行'}
          </span>
          {busy ? (
            <Button type="default" disabled={!connected || pending || session?.status === 'stopping'} onClick={() => void perform(api.stopAgent)} icon={<Square size={14} strokeWidth={1.75} />}>
              停止
            </Button>
          ) : (
            <Button htmlType="submit" disabled={!canSend}>
              {pending ? '发送中…' : '发送'}
            </Button>
          )}
        </div>
      </form>

      {resetDialog ? (
        <Dialog
          title="新建 Agent 任务"
          confirmText="清空并新建"
          onCancel={() => setResetDialog(false)}
          onConfirm={startNewTask}
        >
          {busy ? '当前任务会先停止，停止完成后清空对话和模型上下文；' : '这会清空当前对话和模型上下文，'}不会删除项目文件。
        </Dialog>
      ) : null}
    </div>
  );
}
