/**
 * 设置页 —— 一份代码驱动基础设置 / 专家设置 / 应用设置三个页面。
 *
 * 字段表在 settingsSchema.ts，标题与说明逐字取自 LocalizerZH。
 * 改动直接 PATCH 落盘（save=true），失败回滚到服务端真实值，
 * 与 PyQt 侧每个卡片回调里 config.save() 的行为一致。
 *
 * 版式照 PyQt 实测（`renpybox/frontend/Setting/BasicSettingsPage.py:32-83`、
 * `renpybox/frontend/Setting/ExpertSettingsPage.py:39-81`、
 * `renpybox/frontend/AppSettingsPage.py:57-98`）：
 *   页头 975x36 @ (24,24)：TitleLabel 18px + CaptionLabel 12px @ y=20
 *   滚动区 975x669 @ (24,68)
 *   一个字段一张卡（不是把整页塞进一张大卡），**卡间距 6**
 *   卡内：标题 14px @ y=17、说明 12px @ y=37（间距 6）、右侧控件垂直居中
 *   说明换行时卡跟着长高（实测 1 行 66/67、2 行 82）
 *
 * 基础设置页的「均衡吞吐」是个**普通 PushButton**（实测 975x27 @ y=395），
 * 夹在 max_output_tokens 和 request_timeout 两张卡之间，不是卡片。
 */

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';

import * as api from '../api';
import {
  APP_FIELDS,
  BALANCED_THROUGHPUT,
  BASIC_FIELDS,
  EXPERT_FIELDS,
  PROXY_FIELD,
  type FieldSpec,
} from '../settingsSchema';
import type { UpdateState } from '../types';
import type { AppState } from '../useAppState';
import type { DesktopAppInfo, DesktopUpdateState } from '../preload';
import { Dialog, NumberInput, PageHeader, SelectInput, SettingCard, SettingsGroup, Switch, TextInput } from '../ui';
import { Button, Progress, Tooltip } from 'antd';

type Variant = 'basic' | 'expert' | 'app';

function fieldsFor(variant: Variant): FieldSpec[] {
  if (variant === 'basic') return BASIC_FIELDS;
  if (variant === 'expert') return EXPERT_FIELDS;
  return APP_FIELDS;
}

/** 一个字段 = 一张卡；控件按 spec.kind 选择，和 SpecField 同一套映射。 */
function SpecCard(props: {
  spec: FieldSpec;
  value: unknown;
  disabled: boolean;
  onChange: (key: string, next: unknown) => void;
}) {
  const { spec, value, disabled, onChange } = props;
  const set = (next: unknown) => onChange(spec.key, next);

  let control: React.ReactNode;
  switch (spec.kind) {
    case 'switch':
      control = <Switch checked={value === true} disabled={disabled} label={spec.title} onChange={set} />;
      break;
    case 'spin':
      control = (
        <NumberInput
          value={typeof value === 'number' ? value : Number(value ?? 0)}
          min={spec.min ?? 0}
          max={spec.max ?? 9999999}
          disabled={disabled}
          label={spec.title}
          onCommit={set}
        />
      );
      break;
    case 'select':
      control = (
        <SelectInput
          value={typeof value === 'string' ? value : ''}
          options={spec.options ?? []}
          label={spec.title}
          disabled={disabled}
          onCommit={set}
        />
      );
      break;
    default:
      control = (
        <TextInput
          value={typeof value === 'string' ? value : ''}
          label={spec.title}
          disabled={disabled}
          allowEmpty={spec.allowEmpty}
          onCommit={set}
        />
      );
      break;
  }

  return (
    <SettingCard title={spec.title} description={spec.description}>
      {control}
    </SettingCard>
  );
}

export function SettingsPage(props: {
  state: AppState;
  variant: Variant;
  title: string;
  description: string;
  embedded?: boolean;
}) {
  const { state, variant, title, description, embedded = false } = props;
  const values = state.settings?.values;
  const fields = fieldsFor(variant);

  const applyBalanced = useCallback(() => {
    // 一次改三个字段：逐个 PATCH 会在中途失败时留下半套配置
    state.setSetting('token_threshold', BALANCED_THROUGHPUT.values.token_threshold);
    state.setSetting('max_batch_source_tokens', BALANCED_THROUGHPUT.values.max_batch_source_tokens);
    state.setSetting('max_output_tokens', BALANCED_THROUGHPUT.values.max_output_tokens);
  }, [state]);

  const cards = (specs: FieldSpec[]) =>
    specs.map((spec) => (
      <SpecCard
        key={spec.key}
        spec={spec}
        value={values?.[spec.key]}
        disabled={state.saving}
        onChange={state.setSetting}
      />
    ));

  const balancedButton = variant === 'basic' ? (
    <Tooltip title={BALANCED_THROUGHPUT.tooltip}>
      <Button type="default" onClick={applyBalanced}>{BALANCED_THROUGHPUT.label}</Button>
    </Tooltip>
  ) : null;

  return (
    <div className={embedded ? 'rb-embedded' : 'rb-page rb-page-narrow'}>
      <div className="rb-page-scroll">
        {embedded
          ? (balancedButton ? <div className="rb-embedded-actions">{balancedButton}</div> : null)
          : <PageHeader title={title} description={description} actions={balancedButton} />}
        {variant === 'app' ? (
          <>
            <SettingsGroup>
              {cards(fields)}
              <ProxyCard state={state} value={values?.proxy_url} proxyEnabled={values?.proxy_enable} />
            </SettingsGroup>
            <AboutCard state={state} />
          </>
        ) : (
          <SettingsGroup>{cards(fields)}</SettingsGroup>
        )}
      </div>
    </div>
  );
}

function displayVersion(tag: string): string {
  const match = /^(?:RenpyBox_)?v?(\d+(?:\.\d+){2,3})$/.exec(String(tag).trim());
  return match ? `v${match[1]}` : tag;
}

function formatMegabytes(size: number): string {
  return `${(Math.max(0, size) / (1024 * 1024)).toFixed(1)} MB`;
}

type MarkdownBlock =
  | { type: 'heading'; level: number; text: string }
  | { type: 'list'; ordered: boolean; items: { depth: number; text: string }[] }
  | { type: 'code'; text: string }
  | { type: 'quote'; text: string }
  | { type: 'rule' }
  | { type: 'paragraph'; text: string };

/** GitHub 发布说明可能是 HTML：只做文本替换降级为 Markdown，不解析、不插入任何 HTML。 */
function htmlToMarkdown(source: string): string {
  if (!/<\/?(?:h[1-6]|p|ul|ol|li|br|code|pre|a|strong|div)\b/i.test(source)) return source;
  return source
    .replace(/<h([1-6])[^>]*>/gi, (_, level: string) => `\n${'#'.repeat(Number(level))} `)
    .replace(/<li[^>]*>/gi, '\n- ')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/(?:h[1-6]|p|div|ul|ol|li|pre)>/gi, '\n')
    .replace(/<\/?code[^>]*>/gi, '`')
    .replace(/<\/?(?:strong|b)>/gi, '**')
    .replace(/<a\s[^>]*href="([^"]*)"[^>]*>([\s\S]*?)<\/a>/gi, '[$2]($1)')
    .replace(/<[^>]+>/g, '')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&');
}

/** 按行切分 Markdown 块：标题、列表、围栏代码、引用、分隔线，其余合并为段落。 */
function parseMarkdown(source: string): MarkdownBlock[] {
  const blocks: MarkdownBlock[] = [];
  const lines = htmlToMarkdown(source).replace(/\r\n?/g, '\n').split('\n');
  let paragraph: string[] = [];
  const flush = () => {
    if (paragraph.length) blocks.push({ type: 'paragraph', text: paragraph.join(' ') });
    paragraph = [];
  };
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const last = blocks[blocks.length - 1];
    const fence = /^\s*(```|~~~)/.exec(line);
    if (fence) {
      flush();
      const code: string[] = [];
      for (index += 1; index < lines.length && !lines[index].trim().startsWith(fence[1]); index += 1) code.push(lines[index]);
      blocks.push({ type: 'code', text: code.join('\n') });
      continue;
    }
    if (!line.trim()) {
      flush();
      continue;
    }
    const heading = /^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/.exec(line);
    if (heading) {
      flush();
      blocks.push({ type: 'heading', level: heading[1].length, text: heading[2] });
      continue;
    }
    if (/^\s{0,3}([-*_])(\s*\1){2,}\s*$/.test(line)) {
      flush();
      blocks.push({ type: 'rule' });
      continue;
    }
    const item = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/.exec(line);
    if (item) {
      flush();
      const ordered = /\d/.test(item[2]);
      const entry = { depth: Math.min(3, Math.floor(item[1].replace(/\t/g, '  ').length / 2)), text: item[3] };
      // 缩进子项并入当前列表，靠 data-depth 缩进显示
      if (last?.type === 'list' && (last.ordered === ordered || entry.depth > 0)) last.items.push(entry);
      else blocks.push({ type: 'list', ordered, items: [entry] });
      continue;
    }
    const quote = /^\s*>\s?(.*)$/.exec(line);
    if (quote) {
      flush();
      if (last?.type === 'quote') last.text += ` ${quote[1]}`;
      else blocks.push({ type: 'quote', text: quote[1] });
      continue;
    }
    // 列表项的缩进续行归入上一项，而不是另起段落
    if (!paragraph.length && last?.type === 'list' && /^\s+\S/.test(line)) {
      last.items[last.items.length - 1].text += ` ${line.trim()}`;
      continue;
    }
    paragraph.push(line.trim());
  }
  flush();
  return blocks;
}

const INLINE_PATTERN = /`([^`]+)`|\*\*([^*]+)\*\*|\[([^\]]+)\]\(([^)\s]+)\)|(https?:\/\/[^\s<>()]+)/g;

/** 行内格式只认代码、粗体、链接；链接仅放行 http(s)，由主进程转交系统浏览器打开。 */
function renderInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let cursor = 0;
  for (const match of text.matchAll(INLINE_PATTERN)) {
    const start = match.index ?? 0;
    if (start > cursor) nodes.push(text.slice(cursor, start));
    const key = nodes.length;
    if (match[1] !== undefined) nodes.push(<code key={key}>{match[1]}</code>);
    else if (match[2] !== undefined) nodes.push(<strong key={key}>{match[2]}</strong>);
    else {
      const label = match[3] ?? match[5];
      const href = match[4] ?? match[5];
      nodes.push(/^https?:\/\//i.test(href)
        ? <a key={key} href={href} target="_blank" rel="noopener noreferrer">{label}</a>
        : label);
    }
    cursor = start + match[0].length;
  }
  if (cursor < text.length) nodes.push(text.slice(cursor));
  return nodes;
}

/** 更新日志的 Markdown 只读视图：全部走 React 文本节点，不注入 HTML。 */
function ChangelogView({ markdown }: { markdown: string }) {
  const blocks = useMemo(() => parseMarkdown(markdown), [markdown]);
  return (
    <div className="update-changelog">
      {blocks.map((block, index) => {
        switch (block.type) {
          case 'heading': {
            // 弹窗标题已是最高层级，正文标题统一下沉到 h3~h6
            const Tag = `h${Math.min(6, block.level + 2)}` as 'h3';
            return <Tag key={index} data-level={block.level}>{renderInline(block.text)}</Tag>;
          }
          case 'list': {
            const List = block.ordered ? 'ol' : 'ul';
            return (
              <List key={index}>
                {block.items.map((item, itemIndex) => <li key={itemIndex} data-depth={item.depth}>{renderInline(item.text)}</li>)}
              </List>
            );
          }
          case 'code':
            return <pre key={index}><code>{block.text}</code></pre>;
          case 'quote':
            return <blockquote key={index}>{renderInline(block.text)}</blockquote>;
          case 'rule':
            return <hr key={index} />;
          default:
            return <p key={index}>{renderInline(block.text)}</p>;
        }
      })}
    </div>
  );
}

const EMPTY_UPDATE: UpdateState = {
  status: 'NONE',
  version: '',
  latest: {},
  downloaded_size: 0,
  total_size: 0,
  error: '',
  new_version: false,
  release_url: 'https://github.com/dclef/RenpyBox/releases/latest',
  can_install: false,
};

function AboutCard(props: { state: AppState }) {
  return window.renpy ? <DesktopAboutCard {...props} /> : <WebAboutCard {...props} />;
}

/** 桌面安装包只通过 Electron 更新，避免调用 Qt 的覆盖安装接口。 */
function DesktopAboutCard({ state }: { state: AppState }) {
  const [appInfo, setAppInfo] = useState<DesktopAppInfo | null>(null);
  const [update, setUpdate] = useState<DesktopUpdateState | null>(null);
  const [loadError, setLoadError] = useState('');
  const [pending, setPending] = useState<string[]>([]);
  const pendingRef = useRef(new Set<string>());
  const [installConfirm, setInstallConfirm] = useState(false);
  const [changelog, setChangelog] = useState<string | null>(null);
  const [loadingChangelog, setLoadingChangelog] = useState(false);

  useEffect(() => {
    const bridge = window.renpy;
    if (!bridge) return;
    let active = true;
    let receivedState = false;
    const unsubscribe = bridge.updater.onState((next) => {
      receivedState = true;
      if (!active) return;
      setUpdate(next);
      setLoadError('');
    });
    void bridge.updater.state()
      .then((next) => { if (active && !receivedState) setUpdate(next); })
      .catch((error) => { if (active && !receivedState) setLoadError(String(error?.message || error)); });
    void bridge.appInfo()
      .then((info) => { if (active) setAppInfo(info); })
      .catch((error) => { if (active) state.pushToast('error', `读取桌面信息失败：${String(error?.message || error)}`); });
    return () => { active = false; unsubscribe(); };
  }, [state.pushToast]);

  const run = async (action: 'check' | 'download' | 'cancel' | 'install') => {
    const updater = window.renpy?.updater;
    if (!updater || !update?.packaged || pendingRef.current.has(action)) return;
    if (action === 'cancel' && update.status !== 'downloading') return;
    if (action === 'download' && update.status !== 'available') return;
    if (action === 'install' && update.status !== 'downloaded') return;
    if (action === 'check' && ['checking', 'downloading', 'downloaded'].includes(update.status)) return;
    if (action !== 'cancel' && pendingRef.current.size > 0) return;
    pendingRef.current.add(action);
    setPending([...pendingRef.current]);
    try {
      if (action === 'install') await updater.install();
      else setUpdate(await updater[action]());
      setLoadError('');
    } catch (error) {
      state.pushToast('error', error instanceof Error ? error.message : String(error));
    } finally {
      pendingRef.current.delete(action);
      setPending([...pendingRef.current]);
    }
  };

  const status = update?.status;
  const progress = Math.max(0, Math.min(100, Math.round(update?.progress || 0)));
  const version = appInfo?.appVersion || update?.currentVersion || '读取中…';
  const enabled = update?.packaged === true;
  let statusText = loadError ? `读取更新状态失败：${loadError}` : '读取更新状态…';
  if (status === 'dev') statusText = '开发模式，请使用安装版测试自动更新';
  else if (status === 'idle') statusText = '尚未检查更新';
  else if (status === 'checking') statusText = '正在检查更新…';
  else if (status === 'available') statusText = `发现新版本 ${displayVersion(update?.version || '')}`;
  else if (status === 'latest') statusText = '当前已是最新版本';
  else if (status === 'downloading') statusText = `正在下载 ${progress}%`;
  else if (status === 'downloaded') statusText = '下载完成，可以重启安装';
  else if (status === 'error') statusText = update?.error || '更新失败，请重试';

  return (
    <>
      <SettingsGroup title="关于与更新" description="RenpyBox 桌面版 · GitHub 发布更新">
        <SettingCard title="当前版本" description={appInfo?.packaged === false ? '开发模式' : null}>
          <span className="rb-setting-value">{displayVersion(version)}</span>
          <Button type="default" size="small" disabled={!enabled || pending.length > 0 || ['checking', 'downloading', 'downloaded'].includes(status || '')} onClick={() => void run('check')}>
            {status === 'checking' || pending.includes('check') ? '检查中…' : '检查更新'}
          </Button>
        </SettingCard>
        <SettingCard title="后端 Python" description={null}>
          <span className="rb-setting-value">{state.health?.python_version || '—'}</span>
        </SettingCard>
        <SettingCard title="桌面更新" description={null}>
          <div className="rb-update-status" aria-live="polite">
            <span>{statusText}</span>
            {status === 'downloading' ? (
              <div className="rb-update-progress" aria-label={`下载进度 ${progress}%`}>
                <Progress percent={progress} style={{ width: 160 }} size="small" />
                <span>{progress}%</span>
              </div>
            ) : null}
            <div className="rb-update-actions">
              {status === 'available' ? <Button size="small" disabled={!enabled || pending.length > 0} onClick={() => void run('download')}>下载更新</Button> : null}
              {status === 'downloading' ? (
                <Button type="default" size="small" disabled={pending.includes('cancel')} onClick={() => void run('cancel')}>
                  {pending.includes('cancel') ? '正在取消…' : '取消下载'}
                </Button>
              ) : null}
              {status === 'downloaded' ? <Button size="small" disabled={!enabled || pending.length > 0} onClick={() => setInstallConfirm(true)}>重启并安装</Button> : null}
            </div>
          </div>
        </SettingCard>
        <SettingCard title="更新日志" description={null}>
          <Button type="default" size="small" disabled={loadingChangelog} onClick={() => {
            if (update?.releaseNotes?.trim()) {
              setChangelog(update.releaseNotes);
              return;
            }
            setLoadingChangelog(true);
            void window.renpy?.changelog()
              .then((markdown) => setChangelog(markdown.trim() ? markdown : '暂无更新日志'))
              .catch((error) => state.pushToast('error', String(error?.message || error)))
              .finally(() => setLoadingChangelog(false));
          }}>{loadingChangelog ? '读取中…' : '查看更新日志'}</Button>
        </SettingCard>
        <SettingCard title="运行日志" description="启动、后端与更新记录">
          <Button type="default" size="small" onClick={() => {
            void window.renpy?.openLogs().catch((error) => state.pushToast('error', String(error?.message || error)));
          }}>查看日志</Button>
        </SettingCard>
      </SettingsGroup>
      {installConfirm ? (
        <Dialog title="安装更新" confirmText="重启并安装" onCancel={() => setInstallConfirm(false)} onConfirm={() => {
          setInstallConfirm(false);
          void run('install');
        }}>
          安装会关闭并重启 RenpyBox。请先保存工作，并等待正在运行的任务完成。
        </Dialog>
      ) : null}
      {changelog !== null ? (
        <Dialog title="桌面更新日志" cancelText="关闭" onCancel={() => setChangelog(null)}>
          <ChangelogView markdown={changelog} />
        </Dialog>
      ) : null}
    </>
  );
}

/** 网页端沿用 Python 的更新接口和 WebSocket 事件。 */
function WebAboutCard(props: { state: AppState }) {
  const { state } = props;
  const version = state.version?.app_version ?? state.health?.app_version ?? '—';
  const python = state.health?.python_version ?? '—';
  const [update, setUpdate] = useState<UpdateState>(EMPTY_UPDATE);
  const [checking, setChecking] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [busy, setBusy] = useState(false);
  const [changelog, setChangelog] = useState<string | null>(null);
  const [installConfirm, setInstallConfirm] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setUpdate(await api.getUpdateState());
    } catch {
      /* 后端短暂不可达时保留上次状态 */
    }
  }, []);

  useEffect(() => {
    void refresh();
    return state.subscribe((event) => {
      if (!String(event.event).startsWith('APP_UPDATE_')) return;
      if (event.event === 'APP_UPDATE_CHECK_DONE') {
        setChecking(false);
        const data = event.data as { error?: string; new_version?: boolean; manual?: boolean };
        if (data.manual) {
          if (data.error) state.pushToast('error', `检查更新失败：${data.error}`);
          else if (!data.new_version) state.pushToast('success', '当前已是最新版本');
        }
      }
      if (event.event === 'APP_UPDATE_DOWNLOAD_ERROR') {
        setCancelling(false);
        const data = event.data as { cancelled?: boolean; error?: string };
        if (data.cancelled) state.pushToast('info', '已取消下载');
        else if (data.error) state.pushToast('error', String(data.error));
      }
      if (event.event === 'APP_UPDATE_DOWNLOAD_DONE') setCancelling(false);
      void refresh();
    });
  }, [refresh, state]);

  const run = async (operation: () => Promise<UpdateState>, options?: { checking?: boolean; cancelling?: boolean }) => {
    setBusy(true);
    if (options?.checking) setChecking(true);
    if (options?.cancelling) setCancelling(true);
    try {
      setUpdate(await operation());
    } catch (error) {
      state.pushToast('error', error instanceof Error ? error.message : String(error));
      if (options?.checking) setChecking(false);
      if (options?.cancelling) setCancelling(false);
    } finally {
      setBusy(false);
    }
  };

  const tag = displayVersion(String(update.latest.tag_name || ''));
  const status = String(update.status || 'NONE');
  const progress = Math.max(0, Math.min(100, Math.round((update.downloaded_size / Math.max(1, update.total_size)) * 100)));
  let statusText = '尚未检查更新';
  if (checking) statusText = '检查中…';
  else if (status === 'NEW_VERSION' || update.new_version) statusText = `发现新版本 ${tag || ''}`.trim();
  else if (status === 'UPDATING') {
    statusText = `正在下载 ${formatMegabytes(update.downloaded_size)} / ${formatMegabytes(update.total_size)}`;
  } else if (status === 'DOWNLOADED' || update.can_install) statusText = '下载完成，重启后生效';
  else if (update.error) statusText = '检查更新失败，请重试';
  else if (update.latest.tag_name) statusText = '已是最新版本';

  return (
    <>
      <SettingsGroup title="关于与更新" description="查看当前版本、检查并安装更新">
        <SettingCard title="当前版本" description={null}>
          <span className="rb-setting-value">{version}</span>
          <Button type="default" size="small" disabled={busy || checking || status === 'UPDATING' || state.link !== 'open'} onClick={() => void run(() => api.checkUpdate(true), { checking: true })}>
            {checking ? '检查中…' : '检查更新'}
          </Button>
        </SettingCard>
        <SettingCard title="后端 Python" description={null}>
          <span className="rb-setting-value">{python}</span>
        </SettingCard>
        <SettingCard title="更新状态" description={null}>
          <div className="rb-update-status">
            <span>{statusText}</span>
            {status === 'UPDATING' ? (
              <div className="rb-update-progress" aria-label={`下载进度 ${progress}%`}>
                <Progress percent={progress} style={{ width: 160 }} size="small" />
                <span>{progress}%</span>
              </div>
            ) : null}
            <div className="rb-update-actions">
              {(status === 'NEW_VERSION' || update.new_version) && status !== 'UPDATING' && status !== 'DOWNLOADED' ? (
                <>
                  <Button type="default" size="small" disabled={busy} onClick={() => window.open(update.release_url, '_blank', 'noopener,noreferrer')}>查看详情</Button>
                  <Button size="small" disabled={busy || state.link !== 'open'} onClick={() => void run(api.downloadUpdate)}>下载更新</Button>
                </>
              ) : null}
              {status === 'UPDATING' ? (
                <Button type="default" size="small" disabled={busy || cancelling} onClick={() => void run(api.cancelUpdateDownload, { cancelling: true })}>
                  {cancelling ? '正在取消…' : '取消'}
                </Button>
              ) : null}
              {(status === 'DOWNLOADED' || update.can_install) ? (
                <Button size="small" disabled={busy} onClick={() => setInstallConfirm(true)}>立即重启并安装</Button>
              ) : null}
            </div>
          </div>
        </SettingCard>
        <SettingCard title="更新日志" description={null}>
          <Button
            type="default"
            size="small"
            disabled={busy}
            onClick={() => {
              void api.getChangelog()
                .then((result) => setChangelog(result.empty ? '暂无更新日志' : result.markdown))
                .catch((error) => state.pushToast('error', error instanceof Error ? error.message : String(error)));
            }}
          >
            查看更新日志
          </Button>
        </SettingCard>
      </SettingsGroup>

      {installConfirm ? (
        <Dialog
          title="安装更新"
          confirmText="立即重启并安装"
          onCancel={() => setInstallConfirm(false)}
          onConfirm={() => {
            setInstallConfirm(false);
            void run(api.installUpdate);
          }}
        >
          当前有任务正在运行时安装会中断任务并重启应用。源码模式下会打开发布页，请下载新版覆盖安装目录。
        </Dialog>
      ) : null}

      {changelog !== null ? (
        <Dialog title="更新日志" cancelText="关闭" onCancel={() => setChangelog(null)}>
          <ChangelogView markdown={changelog} />
        </Dialog>
      ) : null}
    </>
  );
}

/**
 * 网络代理 —— 对应 `LineEditCard`（实测 975x67）：左边标题+说明，
 * 右边一个 256x33 输入框 + 8px 间隔 + 56x22 开关。
 * 原壳改开关会弹重启确认框，这里用同一个 Dialog 语义。
 */
function ProxyCard(props: { state: AppState; value: unknown; proxyEnabled: unknown }) {
  const { state, value, proxyEnabled } = props;
  return (
    <SettingCard
      title={PROXY_FIELD.title}
      description={PROXY_FIELD.description}
    >
      <TextInput
        value={typeof value === 'string' ? value : ''}
        label={PROXY_FIELD.title}
        disabled={state.saving}
        placeholder="示例 - http://127.0.0.1:7890"
        allowEmpty
        onCommit={(next) => state.setSetting('proxy_url', next)}
      />
      <Switch
        checked={proxyEnabled === true}
        disabled={state.saving}
        label="启用网络代理"
        onChange={(next) => {
          state.setSetting('proxy_enable', next);
          state.pushToast('info', '代理设置将在重启应用后生效');
        }}
      />
    </SettingCard>
  );
}
