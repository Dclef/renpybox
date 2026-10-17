import { useCallback, useEffect, useRef, useState } from 'react';
import { Button, Checkbox, Popover, Select } from 'antd';
import { ArrowDown, Bot, Plus, RefreshCw, Settings, Square } from 'lucide-react';
import * as api from '../api';
import { AgentMessageBody } from '../AgentMessageBody';
import { languageFromTlPath, toolStatusInfo } from '../agentView.mjs';
import type { AgentSnapshot, AgentThinkingLevel } from '../types';
import type { AppState } from '../useAppState';
import { Banner, Dialog } from '../ui';
import { useT, type TextKey } from '../i18n';

// 工具中文名与 Qt5 LocalizerZH.agent_page_tool_* 保持一致。
const TOOL_NAMES: Record<string, TextKey> = {
  set_project: 'agent_page_tool_set_project', get_project_info: 'agent_page_tool_get_project_info', inspect_translation_project: 'agent_page_tool_inspect_translation_project',
  list_rpa_files: 'agent_page_tool_list_rpa_files', scan_script_errors: 'agent_page_tool_scan_script_errors',
  unpack_rpa_files: 'agent_page_tool_unpack_rpa_files', optimize_old_new_translations: 'agent_page_tool_optimize_old_new_translations',
  decompile_rpyc_files: 'agent_page_tool_decompile_rpyc_files', run_project_extraction: 'agent_page_tool_run_project_extraction',
  translation_status: 'agent_page_tool_translation_status', refresh_replace_fallback: 'agent_page_tool_refresh_replace_fallback',
};
// 空会话快捷任务，与 Qt5 AgentEmptyState 的四张建议卡一致；点击只填入草稿，不直接发送。
const SUGGESTIONS: { text: TextKey; description: TextKey }[] = [
  { text: 'agent_page_suggestion_project', description: 'agent_page_suggestion_project_desc' },
  { text: 'agent_page_suggestion_rpa', description: 'agent_page_suggestion_rpa_desc' },
  { text: 'agent_page_suggestion_errors', description: 'agent_page_suggestion_errors_desc' },
  { text: 'agent_page_suggestion_old_new', description: 'agent_page_suggestion_old_new_desc' },
];
const DRAFT_KEY = 'renpybox.agent.draft';
// 与 Qt5 AUTO_FOLLOW_THRESHOLD 一致：离底部超过该距离视为用户在回看历史。
const FOLLOW_THRESHOLD = 80;

type AgentConfirmation = NonNullable<AgentSnapshot['confirmation']>;

/** 把服务端可信上下文整理成可读的确认摘要；未知工具只给通用提示，原始参数另行折叠展示。 */
function confirmationSummary(t: (key: TextKey) => string, confirmation: AgentConfirmation): { title: string; facts: [string, string][]; note: string } {
  const data = confirmation.data ?? {};
  const text = (key: string) => String(data[key] ?? '');
  const count = (key: string) => String(Number(data[key] ?? 0) || 0);
  if (confirmation.name === 'unpack_rpa_files') {
    return {
      title: t('agent_page_confirmation_unpack_title'),
      facts: [[t('agent_page_unpack_rpa_file'), `${count('count')}${t('agent_page_unpack_unit')}`], [t('agent_page_unpack_game_dir'), text('game_dir')]],
      note: t('agent_page_unpack_note'),
    };
  }
  if (confirmation.name === 'optimize_old_new_translations') {
    return {
      title: t('agent_page_old_new_confirmation_title'),
      facts: [
        [t('agent_page_old_new_tl_dir'), text('tl_dir')],
        [t('agent_page_old_new_supplement'), `${count('old_new_count')}${t('agent_page_entry_unit')}`],
        [t('agent_page_old_new_independent'), `${count('supplement_count')}${t('agent_page_entry_unit')}`],
        [t('agent_page_old_new_total'), `${count('total_count')}${t('agent_page_entry_unit')}`],
        [t('agent_page_old_new_conflicts'), `${count('conflict_count')}${t('agent_page_entry_unit')}`],
        [t('agent_page_old_new_output'), text('output_path')],
      ],
      note: t('agent_page_old_new_note'),
    };
  }
  return {
    title: t('agent_page_confirmation_generic_title').replace('{tool}', TOOL_NAMES[confirmation.name] ? t(TOOL_NAMES[confirmation.name]) : confirmation.name),
    facts: [],
    note: t('agent_page_confirmation_generic').replace('{tool}', TOOL_NAMES[confirmation.name] ? t(TOOL_NAMES[confirmation.name]) : confirmation.name),
  };
}

function formatRemaining(seconds: number): string {
  const total = Math.max(0, Math.ceil(seconds));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
}

function statusLabel(t: (key: TextKey) => string, status?: string): string {
  if (status === 'running') return t('agent_page_tool_running');
  if (status === 'cancelled') return t('agent_page_cancelled');
  if (status === 'failed') return t('agent_page_failed');
  return '';
}

const hasKeys = (value?: Record<string, unknown>) => Boolean(value && Object.keys(value).length);

export function AgentPage(props: { state: AppState; onOpenPlatforms: () => void }) {
  const { state, onOpenPlatforms } = props;
  const t = useT();
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
  const projectName = projectPath.split(/[\\/]/).filter(Boolean).at(-1) || t('agent_page_project_unset');
  // 对齐 Qt5 项目胶囊「项目名 · 语言」；语言取翻译目录 game/tl/<语言>。
  const projectLanguage = languageFromTlPath(state.project?.renpy_tl_folder);
  const projectLabel = projectPath && projectLanguage ? `${projectName} · ${projectLanguage}` : projectName;
  const confirmation = session?.confirmation;
  const runStatus = !connected ? 'offline' : busy ? (session?.status === 'stopping' ? 'stopping' : 'busy') : 'idle';
  const runStatusText = runStatus === 'offline' ? t('agent_page_status_offline') : runStatus === 'stopping' ? t('agent_page_status_stopping') : runStatus === 'busy' ? t('agent_page_tool_running') : t('agent_page_status_ready');
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
      if (mountedRef.current) state.pushToast('success', t('agent_page_refresh_done'));
    } catch (error) {
      if (mountedRef.current) setActionError(`刷新接口列表失败：${error instanceof Error ? error.message : String(error)}`);
    } finally {
      if (mountedRef.current) setRefreshing(false);
    }
  };

  const settingsPanel = (
    <div className="agent-settings-panel">
      <Button block icon={<RefreshCw size={14} strokeWidth={1.75} />} loading={refreshing} disabled={!connected} onClick={() => void refreshPlatforms()}>
        {t('agent_page_settings_refresh')}</Button>
      <Button block onClick={() => { setSettingsOpen(false); onOpenPlatforms(); }}>{t('agent_page_manage_platforms')}</Button>
      <Checkbox
        checked={!unpackAutoConfirm}
        disabled={!connected || state.saving}
        onChange={event => { void state.setSetting('agent_unpack_auto_confirm', !event.target.checked); }}
      >
        {t('agent_page_settings_unpack_confirm')}</Checkbox>
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
              <h1 className="agent-title">{t('agent_page_title')}</h1>
              <span className="agent-status" data-state={runStatus}>{runStatusText}</span>
            </div>
            <span
              className="agent-project-pill"
              data-state={projectPath ? 'ready' : 'unset'}
              title={projectPath || t('agent_page_project_unset_hint')}
            >
              <span className="agent-project-dot" aria-hidden="true" />
              <span className="agent-project-label">{projectLabel}</span>
            </span>
          </div>
        </div>
        <div className="agent-controls">
          <label className="agent-select">
            <span>{t('agent_page_platform_short')}</span>
            <Select
              style={{ width: 190, maxWidth: '100%' }}
              popupMatchSelectWidth={false}
              aria-label={t('agent_page_platform')}
              allowClear={false}
              value={platform ? String(platformId) : '-1'}
              disabled={!connected || busy || pending || state.saving}
              // 与 Qt5 下拉一致显示「名称 [格式]」，便于区分同名模型的不同协议。
              options={[{ value: '-1', label: t('agent_page_platform_placeholder') }, ...platforms.map(entry => ({ value: String(entry.id), label: `${entry.name || entry.model || t('agent_page_platform_entry').replace('{id}', String(entry.id))} [${entry.api_format}]` }))]}
              onChange={value => {
                void state.setSetting('agent_platform', Number(value)).then(saved => {
                  if (saved && session?.messages.length) {
                    state.pushToast('info', t('agent_page_platform_switched'));
                  }
                });
              }}
            />
          </label>
          <label className="agent-select">
            <span>{t('agent_page_thinking')}</span>
            <Select
              style={{ width: 120, maxWidth: '100%' }}
              aria-label={t('agent_page_thinking_level')}
              allowClear={false}
              value={thinking}
              disabled={!connected || busy || pending || state.saving}
              options={([['OFF', t('agent_page_thinking_off')], ['LOW', t('agent_page_thinking_low')], ['MEDIUM', t('agent_page_thinking_medium')], ['HIGH', t('agent_page_thinking_high')], ['MAX', t('agent_page_thinking_max')]] as const).map(([value, label]) => ({ value, label }))}
              onChange={value => { state.setSetting('agent_thinking_level', value); }}
            />
          </label>
          <div className="agent-control-actions">
            <Popover
              trigger="click"
              placement="bottomRight"
              title={t('agent_page_settings_title')}
              content={settingsPanel}
              open={settingsOpen}
              onOpenChange={setSettingsOpen}
            >
              <Button type="text" aria-label={t('agent_page_settings_title')} title={t('agent_page_settings_title')} icon={<Settings size={16} strokeWidth={1.75} />} />
            </Popover>
            <Button
              type="primary"
              icon={<Plus size={14} strokeWidth={1.75} />}
              disabled={!connected || !session || pending || session.status === 'stopping' || !session.messages.length}
              onClick={() => setResetDialog(true)}
            >
              {t('agent_page_new_task')}</Button>
          </div>
        </div>
      </header>

      {loadError ? <Banner tone="error">{t('agent_page_load_failed')}{loadError} <Button type="default" size="small" onClick={() => setRetry(previous => previous + 1)}>{t('agent_page_retry')}</Button></Banner> : null}
      {actionError ? <Banner tone="error" onDismiss={() => setActionError('')}>{actionError}</Banner> : null}
      {connected && !platform ? (
        <Banner tone="info">
          {t('agent_page_platform_hint')}<Button type="link" size="small" onClick={onOpenPlatforms}>{t('agent_page_manage_platforms')}</Button>
        </Banner>
      ) : null}

      <div className="agent-chat-frame">
        <div ref={chatRef} className="agent-chat" role="log" aria-label={t('agent_page_chat')} aria-live="off" onScroll={() => {
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
              <h2>{t('agent_page_empty_title')}</h2>
              <p>{t('agent_page_empty_description')}</p>
              {!projectPath ? <p className="agent-empty-hint">{t('agent_page_empty_hint')}</p> : null}
              <div className="agent-suggestions">
                {SUGGESTIONS.map(item => (
                  <button
                    type="button"
                    key={item.text}
                    className="agent-suggestion"
                    title={t(item.description)}
                    disabled={busy}
                    onClick={() => {
                      setDraft(t(item.text));
                      // 与 Qt5 一致：填入后聚焦并全选，便于直接发送或改写。
                      requestAnimationFrame(() => { inputRef.current?.focus(); inputRef.current?.select(); });
                    }}
                  >
                    <span className="agent-suggestion-copy">
                      <span className="agent-suggestion-text">{t(item.text)}</span>
                      <span className="agent-suggestion-desc">{t(item.description)}</span>
                    </span>
                    <span className="agent-suggestion-arrow" aria-hidden="true">↗</span>
                  </button>
                ))}
              </div>
            </div>
          ) : session.messages.map(message => {
            const label = statusLabel(t, message.status);
            return (
              <article className="agent-message" data-role={message.role} data-status={message.status} key={message.id}>
                <div className="agent-message-meta">
                  <strong>{message.role === 'user' ? t('agent_page_user_label') : 'Agent'}</strong>
                  {label ? <span className="agent-message-status" data-status={message.status}>{label}</span> : null}
                </div>
                {message.reasoning ? (
                  <details className="agent-detail">
                    <summary>{t('agent_page_thinking_process')}</summary>
                    <div className="agent-plain-text">{message.reasoning}</div>
                  </details>
                ) : null}
                {message.tools?.map((tool, index) => {
                  const info = toolStatusInfo(tool);
                  return (
                    // 失败时默认展开，让错误原因直接可见；其余状态折叠，点击查看参数和结果。
                    <details className="agent-detail agent-tool" key={index} data-status={info.tone} open={info.tone === 'failed'}>
                      <summary>
                        <span className="agent-tool-name" title={tool.name}>{TOOL_NAMES[tool.name] ? t(TOOL_NAMES[tool.name]) : tool.name}</span>
                        <span className="agent-tool-status">{info.label}</span>
                      </summary>
                      {tool.message ? <p className="agent-tool-message">{tool.message}</p> : null}
                      {!tool.message && tool.status === 'running' ? <p className="agent-tool-message">{t('agent_page_tool_running_detail')}</p> : null}
                      {hasKeys(tool.arguments) ? (
                        <>
                          <span className="agent-tool-label">{t('agent_page_tool_arguments')}</span>
                          <pre>{JSON.stringify(tool.arguments, null, 2)}</pre>
                        </>
                      ) : null}
                      {hasKeys(tool.data) ? (
                        <>
                          <span className="agent-tool-label">{t('agent_page_tool_result')}</span>
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
                    {confirmation ? t('agent_page_waiting_confirmation') : t('agent_page_running')}
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
                        .then(() => state.pushToast('success', t('agent_page_copied')))
                        .catch(() => state.pushToast('error', t('agent_page_copy_failed')));
                    }}
                  >
                    {t('agent_page_copy')}</button>
                ) : null}
              </article>
            );
          })}
        </div>
        {showLatest && session?.messages.length ? (
          <Button
            className="agent-scroll-latest"
            shape="circle"
            aria-label={t('agent_page_scroll_latest')}
            title={t('agent_page_scroll_latest')}
            icon={<ArrowDown size={16} strokeWidth={1.75} />}
            onClick={scrollToLatest}
          />
        ) : null}
      </div>

      {confirmation ? (() => {
        const summary = confirmationSummary(t, confirmation);
        const locked = !connected || pending;
        return (
          <section className="agent-confirmation" aria-label={t('agent_page_confirmation_aria')}>
            <div className="agent-confirmation-copy">
              <strong>{summary.title}</strong>
              <p>{summary.note}{t('agent_page_confirmation_note')}</p>
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
              <summary>{t('agent_page_execution_arguments')}</summary>
              <pre>{JSON.stringify({ arguments: confirmation.arguments, context: confirmation.data }, null, 2)}</pre>
            </details>
            <div className="agent-confirmation-actions">
              {confirmation.name === 'unpack_rpa_files' ? (
                <Checkbox checked={dontAskUnpack} disabled={locked || autoApprove} onChange={event => setDontAskUnpack(event.target.checked)}>
                  {t('agent_page_unpack_dont_ask')}</Checkbox>
              ) : null}
              <span role="timer" aria-live="off">
                {autoApprove && pending ? t('agent_page_auto_unpack_confirming') : expired ? t('agent_page_confirmation_expired') : t('agent_page_remaining').replace('{time}', formatRemaining(remaining))}
              </span>
              <Button type="default" disabled={locked || expired} onClick={() => void resolveConfirmation(confirmation, false)}>{t('agent_page_reject')}</Button>
              <Button type="primary" disabled={locked || expired} onClick={() => void resolveConfirmation(confirmation, true)}>{t('agent_page_confirm_run')}</Button>
            </div>
          </section>
        );
      })() : null}

      <form className="agent-composer" onSubmit={event => { event.preventDefault(); void send(); }}>
        <textarea
          ref={inputRef}
          aria-label={t('agent_page_input_aria')}
          placeholder={t('agent_page_input_placeholder')}
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
              ? t('agent_page_hint_offline')
              : session?.status === 'stopping'
                ? t('agent_page_hint_stopping')
                : confirmation
                  ? t('agent_page_hint_confirmation')
                  : busy
                    ? t('agent_page_hint_busy')
                    : !platform
                      ? t('agent_page_hint_no_platform')
                      : t('agent_page_send_hint')}
          </span>
          {busy ? (
            <Button type="default" disabled={!connected || pending || session?.status === 'stopping'} onClick={() => void perform(api.stopAgent)} icon={<Square size={14} strokeWidth={1.75} />}>
              {t('agent_page_stop')}</Button>
          ) : (
            <Button htmlType="submit" disabled={!canSend}>
              {pending ? t('agent_page_sending') : t('agent_page_send')}
            </Button>
          )}
        </div>
      </form>

      {resetDialog ? (
        <Dialog
          title={t('agent_page_new_task_title')}
          confirmText={t('agent_page_new_task_confirm')}
          onCancel={() => setResetDialog(false)}
          onConfirm={startNewTask}
        >
          {busy ? t('agent_page_new_task_running') : t('agent_page_new_task_idle')}{t('agent_page_new_task_keep_files')}</Dialog>
      ) : null}
    </div>
  );
}
