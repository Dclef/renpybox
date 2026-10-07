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

import { useCallback } from 'react';

import {
  APP_FIELDS,
  BALANCED_THROUGHPUT,
  BASIC_FIELDS,
  EXPERT_FIELDS,
  PROXY_FIELD,
  type FieldSpec,
} from '../settingsSchema';
import type { AppState } from '../useAppState';
import { Banner, NumberInput, SelectInput, SettingCard, Switch, TextInput } from '../ui';

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

/**
 * 「关于与更新」—— 对应 `renpybox/widget/GroupCard.py`（实测 975x220）。
 * 原壳这里有检查更新 / 下载 / 安装一整条链路，Electron 侧还没接更新服务，
 * 所以这一块只如实显示当前版本，不摆不能按的按钮。
 */
function AboutCard(props: { state: AppState }) {
  const { state } = props;
  const version = state.version?.app_version ?? state.health?.app_version ?? '—';
  const python = state.health?.python_version ?? '—';
  return (
    <section className="group-card">
      <div className="setting-card-text">
        <span className="setting-card-title">关于与更新</span>
        <span className="setting-card-description">查看当前版本、检查并安装更新</span>
      </div>
      <div className="group-card-body">
        <div className="group-row group-row-version">
          <span className="group-row-label">当前版本</span>
          <span className="group-row-value">{version}</span>
        </div>
        <div className="group-row">
          <span className="group-row-label">后端 Python</span>
          <span className="group-row-value">{python}</span>
        </div>
        <div className="group-row">
          <span className="group-row-label">更新通道</span>
          <span className="group-row-value">
            <Banner tone="info">Electron 版尚未接入更新服务，检查更新与自动安装在原壳里由 Qt 侧完成。</Banner>
          </span>
        </div>
      </div>
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
