import { useCallback, useEffect, useRef, useState } from 'react';
import { Button, Select } from '@mantine/core';
import { Bot, Square } from 'lucide-react';
import * as api from '../api';
import { AgentMessageBody } from '../AgentMessageBody';
import type { AgentSnapshot, AgentThinkingLevel } from '../types';
import type { AppState } from '../useAppState';
import { Banner, Dialog } from '../ui';

const TOOL_NAMES: Record<string, string> = {
  set_project: '设置项目', get_project_info: '查询项目', inspect_translation_project: '检查翻译项目',
  list_rpa_files: '查找 RPA 资源包', scan_script_errors: '扫描脚本问题',
  unpack_rpa_files: '解包 RPA 资源', start_translation: '开始翻译',
  get_translation_status: '查询翻译状态', optimize_old_new_translations: '整理 old/new 译文',
};
const SUGGESTIONS = ['检查当前项目的翻译准备情况', '扫描脚本中可能存在的问题', '查看当前翻译进度和失败项'];
const DRAFT_KEY = 'renpybox.agent.draft';

function statusLabel(status?: string): string {
  if (status === 'running') return '处理中';
  if (status === 'cancelled') return '已停止';
  if (status === 'failed') return '执行失败';
  return '';
}

function toolStatusLabel(status: string): string {
  if (status === 'running') return '执行中';
  if (status === 'done') return '已完成';
  if (status === 'cancelled') return '已停止';
  return '未完成';
}

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
  const projectPath = String(state.project?.renpy_project_path ?? '');
  const projectName = projectPath.split(/[\\/]/).pop() || '未选择项目';
  const confirmation = session?.confirmation;
  const runStatus = !connected ? 'offline' : busy ? (session?.status === 'stopping' ? 'stopping' : 'busy') : 'idle';
  const runStatusText = runStatus === 'offline' ? '未连接' : runStatus === 'stopping' ? '停止中' : runStatus === 'busy' ? '处理中' : '就绪';

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
            <span className="agent-project-text" title={projectPath}>项目 · {projectName}</span>
          </div>
        </div>
        <div className="agent-controls">
          <label className="agent-select">
            <span>接口</span>
            <Select
              w={150}
              maw="100%"
              aria-label="Agent 接口"
              allowDeselect={false}
              value={platform ? String(platformId) : '-1'}
              disabled={!connected || busy || pending || state.saving}
              data={[{ value: '-1', label: '选择 Agent 接口' }, ...platforms.map(entry => ({ value: String(entry.id), label: entry.name || entry.model || `接口 ${entry.id}` }))]}
              onChange={value => { if (value != null) state.setSetting('agent_platform', Number(value)); }}
            />
          </label>
          <label className="agent-select">
            <span>思考</span>
            <Select
              w={120}
              maw="100%"
              aria-label="Agent 思考等级"
              allowDeselect={false}
              value={thinking}
              disabled={!connected || busy || pending || state.saving}
              data={([['OFF', '关闭'], ['LOW', '低'], ['MEDIUM', '中'], ['HIGH', '高'], ['MAX', '最高']] as const).map(([value, label]) => ({ value, label }))}
              onChange={value => { if (value != null) state.setSetting('agent_thinking_level', value); }}
            />
          </label>
          <div className="agent-control-actions">
            <Button variant="default" onClick={onOpenPlatforms}>管理接口</Button>
            <Button variant="default" disabled={!connected || !session || busy || pending || !session.messages.length} onClick={() => setResetDialog(true)}>新建会话</Button>
          </div>
        </div>
      </header>

      {loadError ? <Banner tone="error">加载 Agent 会话失败：{loadError} <Button variant="default" size="xs" onClick={() => setRetry(previous => previous + 1)}>重试</Button></Banner> : null}
      {actionError ? <Banner tone="error" onDismiss={() => setActionError('')}>{actionError}</Banner> : null}
      {connected && !platform ? <Banner tone="info">请选择支持工具调用的 OpenAI、Anthropic 或 Google 接口，不会改变翻译任务的接口设置。</Banner> : null}

      <div ref={chatRef} className="agent-chat" role="log" aria-label="Agent 对话" aria-live="off" onScroll={() => {
        const chat = chatRef.current;
        if (chat) followRef.current = chat.scrollHeight - chat.scrollTop - chat.clientHeight < 80;
      }}>
        {!session?.messages.length ? (
          <div className="agent-empty">
            <span className="agent-empty-icon" aria-hidden="true">
              <Bot size={28} strokeWidth={1.75} />
            </span>
            <h2>从当前项目开始</h2>
            <p>用自然语言检查项目、查询进度或调用现有工具。需要确认的操作会先显示执行范围。</p>
            <div className="agent-suggestions">
              {SUGGESTIONS.map(text => (
                <button
                  type="button"
                  key={text}
                  className="agent-suggestion"
                  disabled={busy}
                  onClick={() => { setDraft(text); inputRef.current?.focus(); }}
                >
                  <span className="agent-suggestion-text">{text}</span>
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
              {message.tools?.map((tool, index) => (
                <details className="agent-detail agent-tool" key={index} data-status={tool.status}>
                  <summary>
                    <span className="agent-tool-name">{TOOL_NAMES[tool.name] || tool.name}</span>
                    <span className="agent-tool-status">{toolStatusLabel(tool.status)}</span>
                  </summary>
                  {tool.message ? <p>{tool.message}</p> : null}
                  {tool.arguments ? <pre>{JSON.stringify(tool.arguments, null, 2)}</pre> : null}
                  {tool.data && Object.keys(tool.data).length ? <pre>{JSON.stringify(tool.data, null, 2)}</pre> : null}
                </details>
              ))}
              {message.role === 'assistant' ? <AgentMessageBody text={message.content} /> : <div className="agent-plain-text">{message.content}</div>}
              {message.status === 'running' && !message.content ? (
                <span className="agent-processing">
                  <span className="agent-processing-dots" aria-hidden="true"><i /><i /><i /></span>
                  {confirmation ? '等待你确认工具操作' : '正在处理请求…'}
                </span>
              ) : null}
              {message.error ? <div className="agent-message-error" role="status">{message.error}</div> : null}
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

      {confirmation ? (
        <section className="agent-confirmation" aria-label="工具执行确认">
          <div className="agent-confirmation-copy">
            <strong>执行前确认 · {TOOL_NAMES[confirmation.name] || confirmation.name}</strong>
            <p>请核对执行范围；拒绝或超时后不会执行此工具。已开始的写入操作不保证立即停止。</p>
          </div>
          <pre>{JSON.stringify({ arguments: confirmation.arguments, context: confirmation.data }, null, 2)}</pre>
          <div className="agent-confirmation-actions">
            <span>确认有效至 {new Date(confirmation.expires_at * 1000).toLocaleTimeString()}</span>
            <Button variant="default" disabled={!connected || pending} onClick={() => void perform(() => api.confirmAgentTool(confirmation.id, false))}>拒绝执行</Button>
            <Button disabled={!connected || pending} onClick={() => void perform(() => api.confirmAgentTool(confirmation.id, true))}>确认执行</Button>
          </div>
        </section>
      ) : null}

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
                : busy
                  ? '任务处理中；可以先编写下一条消息'
                  : 'Enter 发送 · Shift+Enter 换行'}
          </span>
          {busy ? (
            <Button variant="default" disabled={!connected || pending || session?.status === 'stopping'} onClick={() => void perform(api.stopAgent)}>
              <Square size={14} strokeWidth={1.75} />停止
            </Button>
          ) : (
            <Button type="submit" disabled={!canSend}>
              {pending ? '发送中…' : '发送'}
            </Button>
          )}
        </div>
      </form>

      {resetDialog ? (
        <Dialog
          title="新建 Agent 会话"
          confirmText="清空并新建"
          onCancel={() => setResetDialog(false)}
          onConfirm={() => {
            setResetDialog(false);
            void perform(api.resetAgent);
          }}
        >
          这会清空当前对话和模型上下文，不会删除项目文件。
        </Dialog>
      ) : null}
    </div>
  );
}
