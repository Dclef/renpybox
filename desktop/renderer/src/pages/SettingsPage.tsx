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

import { useCallback, useEffect, useState } from 'react';

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
import { Dialog, NumberInput, SelectInput, SettingCard, Switch, TextInput } from '../ui';

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
}) {
  const { state, variant, title, description } = props;
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

  // 基础设置页的均衡吞吐按钮插在第 5 张卡（max_output_tokens）之后
  const balancedButton = (
    <button
      type="button"
      className="btn settings-solo-button"
      title={BALANCED_THROUGHPUT.tooltip}
      onClick={applyBalanced}
    >
      {BALANCED_THROUGHPUT.label}
    </button>
  );

  return (
    <div className="settings-layout">
      <header className="settings-header">
        <h1 className="settings-title">{title}</h1>
        <p className="settings-subtitle">{description}</p>
      </header>

      <div className="settings-scroll">
        <div className="settings-card-list">
          {variant === 'basic' ? (
            <>
              {cards(fields.slice(0, 5))}
              {balancedButton}
              {cards(fields.slice(5))}
            </>
          ) : null}

          {variant === 'expert' ? cards(fields) : null}

          {variant === 'app' ? (
            <>
              {/* 应用语言是第 1 张卡；「关于与更新」GroupCard 插在它后面 */}
              {cards(fields.slice(0, 1))}
              <AboutCard state={state} />
              {cards(fields.slice(1))}
              <ProxyCard state={state} value={values?.proxy_url} proxyEnabled={values?.proxy_enable} />
            </>
          ) : null}
        </div>
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

/**
 * 「关于与更新」—— 对接 /api/update（复用 VersionManager）。
 * 检查 / 下载 / 取消 / 安装与 Qt 原壳同一事件流；进度经 WebSocket 推送。
 */
function AboutCard(props: { state: AppState }) {
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
    <section className="group-card">
      <div className="setting-card-text">
        <span className="setting-card-title">关于与更新</span>
        <span className="setting-card-description">查看当前版本、检查并安装更新</span>
      </div>
      <div className="group-card-body">
        <div className="group-row group-row-version">
          <span className="group-row-label">当前版本</span>
          <div className="group-row-value update-version-row">
            <span>{version}</span>
            <button
              type="button"
              className="btn"
              disabled={busy || checking || status === 'UPDATING' || state.link !== 'open'}
              onClick={() => void run(() => api.checkUpdate(true), { checking: true })}
            >
              {checking ? '检查中…' : '检查更新'}
            </button>
          </div>
        </div>
        <div className="group-row">
          <span className="group-row-label">后端 Python</span>
          <span className="group-row-value">{python}</span>
        </div>
        <div className="group-row update-status-row">
          <span className="group-row-label">更新状态</span>
          <div className="group-row-value update-status-value">
            <span>{statusText}</span>
            {status === 'UPDATING' ? (
              <div className="update-progress" aria-label={`下载进度 ${progress}%`}>
                <div className="update-progress-track">
                  <div className="update-progress-bar" style={{ width: `${progress}%` }} />
                </div>
                <span>{progress}%</span>
              </div>
            ) : null}
            <div className="update-actions">
              {(status === 'NEW_VERSION' || update.new_version) && status !== 'UPDATING' && status !== 'DOWNLOADED' ? (
                <>
                  <button type="button" className="btn" disabled={busy} onClick={() => window.open(update.release_url, '_blank', 'noopener,noreferrer')}>
                    查看详情
                  </button>
                  <button type="button" className="btn btn-primary" disabled={busy || state.link !== 'open'} onClick={() => void run(api.downloadUpdate)}>
                    下载更新
                  </button>
                </>
              ) : null}
              {status === 'UPDATING' ? (
                <button type="button" className="btn" disabled={busy || cancelling} onClick={() => void run(api.cancelUpdateDownload, { cancelling: true })}>
                  {cancelling ? '正在取消…' : '取消'}
                </button>
              ) : null}
              {(status === 'DOWNLOADED' || update.can_install) ? (
                <button type="button" className="btn btn-primary" disabled={busy} onClick={() => setInstallConfirm(true)}>
                  立即重启并安装
                </button>
              ) : null}
            </div>
          </div>
        </div>
        <div className="group-row">
          <span className="group-row-label">更新日志</span>
          <div className="group-row-value">
            <button
              type="button"
              className="btn"
              disabled={busy}
              onClick={() => {
                void api.getChangelog()
                  .then((result) => setChangelog(result.empty ? '暂无更新日志' : result.markdown))
                  .catch((error) => state.pushToast('error', error instanceof Error ? error.message : String(error)));
              }}
            >
              查看更新日志
            </button>
          </div>
        </div>
      </div>

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
          <pre className="update-changelog">{changelog}</pre>
        </Dialog>
      ) : null}
    </section>
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
