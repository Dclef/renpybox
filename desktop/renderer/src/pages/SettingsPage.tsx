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

import { useCallback, useEffect, useRef, useState } from 'react';

import * as api from '../api';
import { ChangelogView } from '../components/ChangelogView';
import { useT } from '../i18n';
import {
  APP_FIELDS,
  BALANCED_THROUGHPUT,
  BASIC_FIELDS,
  EXPERT_FIELDS,
  type FieldSpec,
} from '../settingsSchema';
import type { UpdateState } from '../types';
import type { AppState } from '../useAppState';
import type { DesktopAppInfo, DesktopUpdateState } from '../preload';
import { Dialog, NumberInput, PageHeader, SelectInput, SettingCard, SettingsGroup, Switch, TextInput } from '../ui';
import { Button, Progress, Tooltip } from 'antd';
import { displayVersion, formatMegabytes, resolveWebUpdateUi } from '../webUpdateStatus.mjs';

type Variant = 'basic' | 'expert' | 'app';

/** 替换文案里的 {name} 占位符，与 OneKeyTranslatePage 同款最小实现。 */
const fill = (text: string, vars: Record<string, string | number>) =>
  Object.entries(vars).reduce((acc, [key, value]) => acc.split(`{${key}}`).join(String(value)), text);

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
  const t = useT();
  const set = (next: unknown) => onChange(spec.key, next);
  const title = spec.titleKey ? t(spec.titleKey) : spec.title;
  const description = spec.descriptionKey ? t(spec.descriptionKey) : spec.description;
  const options = (spec.options ?? []).map(option => ({
    value: option.value,
    label: option.labelKey ? t(option.labelKey) : option.label,
  }));

  let control: React.ReactNode;
  switch (spec.kind) {
    case 'switch':
      control = <Switch checked={value === true} disabled={disabled} label={title} onChange={set} />;
      break;
    case 'spin':
      control = (
        <NumberInput
          value={typeof value === 'number' ? value : Number(value ?? 0)}
          min={spec.min ?? 0}
          max={spec.max ?? 9999999}
          disabled={disabled}
          label={title}
          onCommit={set}
        />
      );
      break;
    case 'select':
      control = (
        <SelectInput
          value={typeof value === 'string' ? value : ''}
          options={options}
          label={title}
          disabled={disabled}
          onCommit={set}
        />
      );
      break;
    default:
      control = (
        <TextInput
          value={typeof value === 'string' ? value : ''}
          label={title}
          disabled={disabled}
          allowEmpty={spec.allowEmpty}
          onCommit={set}
        />
      );
      break;
  }

  return (
    <SettingCard title={title} description={description}>
      {control}
    </SettingCard>
  );
}

/**
 * 改完这些设置必须重启才生效。以前只在说明文字里写「重启后生效」，
 * 改完什么都不弹，用户以为没生效。现在保存成功后直接弹重启确认。
 *
 * 「稍后重启」= 放弃本次修改，把配置退回修改前的值。否则下拉框已经显示
 * 「英文」、界面却还是中文，用户无法判断到底生效了没有（2026-10-18 反馈）。
 */
const RESTART_SETTING_KEYS = new Set(['app_language', 'expert_mode', 'font_hinting', 'scale_factor']);

export function SettingsPage(props: {
  state: AppState;
  variant: Variant;
  title: string;
  description: string;
  embedded?: boolean;
}) {
  const { state, variant, title, description, embedded = false } = props;
  const t = useT();
  const values = state.settings?.values;
  const fields = fieldsFor(variant);
  const [restartFor, setRestartFor] = useState<{ key: string; label: string; previous: unknown } | null>(null);

  const applyBalanced = useCallback(async () => {
    // 一次改三个字段：串行应用并在失败处停下，避免留下半套配置。
    for (const [key, value] of Object.entries(BALANCED_THROUGHPUT.values)) {
      if (!(await state.setSetting(key, value))) return;
    }
  }, [state]);

  const applySetting = useCallback(async (key: string, value: unknown) => {
    // 先记下修改前的值：点「稍后重启」要把配置退回这里。
    const previous = values?.[key];
    const ok = await state.setSetting(key, value);
    if (ok && RESTART_SETTING_KEYS.has(key)) {
      const spec = [...BASIC_FIELDS, ...EXPERT_FIELDS, ...APP_FIELDS].find(item => item.key === key);
      setRestartFor({ key, label: spec ? (spec.titleKey ? t(spec.titleKey) : spec.title) : key, previous });
    }
  }, [state, t, values]);

  const cards = (specs: FieldSpec[]) =>
    specs.map((spec) => (
      <SpecCard
        key={spec.key}
        spec={spec}
        value={values?.[spec.key]}
        disabled={state.saving}
        onChange={(key, next) => { void applySetting(key, next); }}
      />
    ));

  const balancedButton = variant === 'basic' ? (
    <Tooltip title={t('setting_balanced_throughput_tooltip')}>
      <Button type="default" disabled={state.saving} onClick={() => void applyBalanced()}>{t('setting_balanced_throughput_label')}</Button>
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
      {restartFor ? (
        <Dialog
          title={t('app_settings_restart_title')}
          confirmText={t('app_settings_restart_confirm')}
          cancelText={t('app_settings_restart_later')}
          onCancel={() => {
            // 「稍后重启」= 放弃本次修改。不退回的话下拉框显示「英文」、
            // 界面还是中文，用户根本判断不出到底生效没有（2026-10-18 反馈）。
            const pending = restartFor;
            setRestartFor(null);
            void state.setSetting(pending.key, pending.previous);
          }}
          onConfirm={() => {
            setRestartFor(null);
            void window.renpy?.relaunch();
          }}
        >
          {fill(t('app_settings_restart_body'), { setting: restartFor.label })}
        </Dialog>
      ) : null}
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
  const t = useT();
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
      .catch((error) => { if (active) state.pushToast('error', fill(t('app_read_desktop_info_failed'), { reason: String(error?.message || error) })); });
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
  const version = appInfo?.appVersion || update?.currentVersion || t('app_read_state_loading');
  const enabled = update?.packaged === true;
  let statusText = loadError ? fill(t('app_read_state_failed'), { reason: loadError }) : t('app_read_state_loading');
  if (status === 'dev') statusText = t('app_update_dev_mode_hint');
  else if (status === 'idle') statusText = t('app_update_status_not_checked');
  else if (status === 'checking') statusText = t('app_update_status_checking');
  else if (status === 'available') statusText = fill(t('app_update_status_new'), { version: displayVersion(update?.version || '') });
  else if (status === 'latest') statusText = t('app_update_status_latest');
  // 下载中文案不再带百分数：百分比只在进度条右侧显示一次，避免同一行重复出现
  else if (status === 'downloading') statusText = t('app_update_status_downloading');
  else if (status === 'downloaded') statusText = t('app_update_status_downloaded');
  else if (status === 'error') statusText = update?.error || t('app_update_status_failed');

  return (
    <>
      <SettingsGroup title={t('app_update_group_title')} description={t('app_update_desktop_group_description')}>
        <SettingCard title={t('app_update_current_version')} description={appInfo?.packaged === false ? t('app_update_dev_mode') : null}>
          <span className="rb-setting-value">{displayVersion(version)}</span>
          <Button type="default" size="small" disabled={!enabled || pending.length > 0 || ['checking', 'downloading', 'downloaded'].includes(status || '')} onClick={() => void run('check')}>
            {status === 'checking' || pending.includes('check') ? t('app_update_checking') : t('app_update_check')}
          </Button>
        </SettingCard>
        <SettingCard title={t('app_update_python_backend')} description={null}>
          <span className="rb-setting-value">{state.health?.python_version || '—'}</span>
        </SettingCard>
        <SettingCard title={t('app_update_desktop_status')} description={null}>
          <div className="rb-update-status" aria-live="polite">
            <span>{statusText}</span>
            {status === 'downloading' ? (
              <div className="rb-update-progress" aria-label={fill(t('app_update_download_progress'), { percent: progress })}>
                <Progress percent={progress} style={{ width: 160 }} size="small" showInfo={false} />
                <span>{progress}%</span>
              </div>
            ) : null}
            <div className="rb-update-actions">
              {status === 'available' ? <Button size="small" disabled={!enabled || pending.length > 0} onClick={() => void run('download')}>{t('app_update_download')}</Button> : null}
              {status === 'downloading' ? (
                <Button type="default" size="small" disabled={pending.includes('cancel')} onClick={() => void run('cancel')}>
                  {pending.includes('cancel') ? t('app_update_cancelling') : t('app_update_cancel_download')}
                </Button>
              ) : null}
              {status === 'downloaded' ? <Button size="small" disabled={!enabled || pending.length > 0} onClick={() => setInstallConfirm(true)}>{t('app_update_restart_install')}</Button> : null}
            </div>
          </div>
        </SettingCard>
        <SettingCard title={t('app_update_changelog_title')} description={null}>
          <Button type="default" size="small" disabled={loadingChangelog} onClick={() => {
            if (update?.releaseNotes?.trim()) {
              setChangelog(update.releaseNotes);
              return;
            }
            setLoadingChangelog(true);
            void window.renpy?.changelog()
              .then((markdown) => setChangelog(markdown.trim() ? markdown : t('app_changelog_empty')))
              .catch((error) => state.pushToast('error', String(error?.message || error)))
              .finally(() => setLoadingChangelog(false));
          }}>{loadingChangelog ? t('app_read_state_loading') : t('app_update_changelog_action')}</Button>
        </SettingCard>
        <SettingCard title={t('app_update_logs_title')} description={t('app_update_logs_description')}>
          <Button type="default" size="small" onClick={() => {
            void window.renpy?.openLogs().catch((error) => state.pushToast('error', String(error?.message || error)));
          }}>{t('app_update_logs_action')}</Button>
        </SettingCard>
      </SettingsGroup>
      {installConfirm ? (
        <Dialog title={t('app_update_install')} confirmText={t('app_update_restart_install')} onCancel={() => setInstallConfirm(false)} onConfirm={() => {
          setInstallConfirm(false);
          void run('install');
        }}>
          {t('app_update_install_dialog_body')}
        </Dialog>
      ) : null}
      {changelog !== null ? (
        <Dialog title={t('app_update_desktop_changelog_title')} cancelText={t('app_close')} onCancel={() => setChangelog(null)}>
          <ChangelogView markdown={changelog} />
        </Dialog>
      ) : null}
    </>
  );
}

/** 网页端沿用 Python 的更新接口和 WebSocket 事件。 */
function WebAboutCard(props: { state: AppState }) {
  const { state } = props;
  const t = useT();
  const version = state.version?.app_version ?? state.health?.app_version ?? '—';
  const python = state.health?.python_version ?? '—';
  const [update, setUpdate] = useState<UpdateState>(EMPTY_UPDATE);
  const [checking, setChecking] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [busy, setBusy] = useState(false);
  const [changelog, setChangelog] = useState<string | null>(null);
  const [installConfirm, setInstallConfirm] = useState(false);
  // 对齐 Qt UpdateDetailsDialog：先看说明，确认后再开始下载
  const [detailsOpen, setDetailsOpen] = useState(false);

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
          if (data.error) state.pushToast('error', `${t('app_update_check_failure')}${data.error}`);
          else if (!data.new_version) state.pushToast('success', t('app_update_check_latest_toast'));
        }
      }
      if (event.event === 'APP_UPDATE_DOWNLOAD_ERROR') {
        setCancelling(false);
        // 失败 toast 由 VersionManager 的 APP_TOAST_SHOW 统一弹出；这里只补「已取消」
        const data = event.data as { cancelled?: boolean };
        if (data.cancelled) state.pushToast('info', t('app_update_cancelled'));
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

  const ui = resolveWebUpdateUi(update, checking);
  // 对齐 Qt UpdateDetailsDialog：包大小取 latest.asset.size，日期取 published_at 前十位
  const releaseSize = Number(update.latest?.asset?.size) || 0;
  const publishedAt = String(update.latest?.published_at || '').trim();

  return (
    <>
      <SettingsGroup title={t('app_update_group_title')} description={t('app_update_group_description')}>
        <SettingCard title={t('app_update_current_version')} description={null}>
          <span className="rb-setting-value">{version}</span>
          <Button
            type="default"
            size="small"
            disabled={busy || checking || ui.status === 'UPDATING' || state.link !== 'open'}
            onClick={() => void run(() => api.checkUpdate(true), { checking: true })}
          >
            {checking ? t('app_update_checking') : t('app_update_check')}
          </Button>
        </SettingCard>
        <SettingCard title={t('app_update_python_backend')} description={null}>
          <span className="rb-setting-value">{python}</span>
        </SettingCard>
        <SettingCard title={t('app_update_status_title')} description={null}>
          <div className="rb-update-status" aria-live="polite">
            <span>
              {ui.offerMigration && !checking
                ? fill(t('app_desktop_update_title'), { version: ui.tag }).trim()
                : ui.statusText}
            </span>
            {ui.showProgress ? (
              <div className="rb-update-progress" aria-label={fill(t('app_update_download_progress'), { percent: ui.progress })}>
                <Progress percent={ui.progress} style={{ width: 160 }} size="small" showInfo={false} />
                {/* 状态文案自带百分数时不再重复渲染，保证整行只有一处百分比 */}
                {ui.statusText.includes('%') ? null : <span>{ui.progress}%</span>}
              </div>
            ) : null}
            <div className="rb-update-actions">
              {/* 与 Qt 一致：单入口打开详情；legacy 确认后下载，migration 确认后打开发布页 */}
              {ui.offerUpdate || ui.offerMigration ? (
                <Button type="default" size="small" disabled={busy} onClick={() => setDetailsOpen(true)}>
                  {ui.offerMigration ? t('app_desktop_update_action') : t('app_update_view_update')}
                </Button>
              ) : null}
              {ui.showCancel ? (
                <Button type="default" size="small" disabled={busy || cancelling} onClick={() => void run(api.cancelUpdateDownload, { cancelling: true })}>
                  {cancelling ? t('app_update_cancelling') : t('app_update_cancel')}
                </Button>
              ) : null}
              {ui.showInstall ? (
                <Button size="small" disabled={busy} onClick={() => setInstallConfirm(true)}>{t('app_update_install')}</Button>
              ) : null}
            </div>
          </div>
        </SettingCard>
        <SettingCard title={t('app_update_changelog_title')} description={null}>
          <Button
            type="default"
            size="small"
            disabled={busy}
            onClick={() => {
              void api.getChangelog()
                .then((result) => setChangelog(result.empty ? t('app_changelog_empty') : result.markdown))
                .catch((error) => state.pushToast('error', error instanceof Error ? error.message : String(error)));
            }}
          >
            {t('app_update_changelog_action')}
          </Button>
        </SettingCard>
      </SettingsGroup>

      {detailsOpen ? (
        <Dialog
          title={fill(
            t(ui.offerMigration ? 'app_desktop_update_title' : 'app_update_details_title'),
            { version: ui.tag },
          ).trim()}
          confirmText={ui.offerMigration ? t('app_desktop_update_action') : t('app_update_download')}
          cancelText={t('app_update_later')}
          onCancel={() => setDetailsOpen(false)}
          onConfirm={() => {
            setDetailsOpen(false);
            if (ui.offerMigration) {
              const url = String(update.release_url || '').trim();
              if (!url) {
                state.pushToast('error', t('app_desktop_update_open_failed'));
                return;
              }
              try {
                // noopener intentionally returns null even when the new tab opens.
                window.open(url, '_blank', 'noopener,noreferrer');
              } catch {
                state.pushToast('error', t('app_desktop_update_open_failed'));
              }
              return;
            }
            void run(api.downloadUpdate);
          }}
        >
          {ui.offerMigration ? (
            <p className="rb-update-migration-desc">{t('app_desktop_update_description')}</p>
          ) : null}
          {/* ChangelogView 只渲染文本节点，不注入 HTML */}
          <ChangelogView markdown={String(update.latest?.body || '').trim() || t('app_update_notes_empty')} />
          <p className="rb-update-release-meta">
            {fill(t('app_update_release_metadata'), {
              size: releaseSize <= 0 ? t('app_update_size_unknown') : formatMegabytes(releaseSize),
              date: publishedAt ? publishedAt.slice(0, 10) : t('app_update_date_unknown'),
            })}
          </p>
        </Dialog>
      ) : null}

      {installConfirm ? (
        <Dialog
          title={t('app_update_install')}
          confirmText={t('app_update_install')}
          onCancel={() => setInstallConfirm(false)}
          onConfirm={() => {
            setInstallConfirm(false);
            void run(api.installUpdate);
          }}
        >
          {t('app_update_install_busy')}
        </Dialog>
      ) : null}

      {changelog !== null ? (
        <Dialog title={t('app_update_changelog_title')} cancelText={t('app_close')} onCancel={() => setChangelog(null)}>
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
  const t = useT();
  const title = t('setting_proxy_url_title');
  const address = typeof value === 'string' ? value.trim() : '';
  return (
    <SettingCard
      title={title}
      description={t('setting_proxy_url_body')}
    >
      <TextInput
        value={typeof value === 'string' ? value : ''}
        label={title}
        disabled={state.saving}
        placeholder={t('app_settings_page_proxy_url')}
        allowEmpty
        onCommit={(next) => state.setSetting('proxy_url', next)}
      />
      <Switch
        checked={proxyEnabled === true}
        disabled={state.saving}
        label={t('app_settings_page_proxy_enable')}
        onChange={(next) => {
          state.setSetting('proxy_enable', next);
          // 开关打开但地址留空 = 跟随系统代理，这条提示要让用户当场看见。
          if (next && !address) state.pushToast('info', t('app_settings_page_proxy_system_hint'));
          else state.pushToast('info', t('app_settings_page_proxy_restart_hint'));
        }}
      />
    </SettingCard>
  );
}
