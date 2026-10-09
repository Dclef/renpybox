/**
 * 通用控件 —— 对应 PyQt 侧的 widget/ 卡片组件。
 *
 * SpinCard / SwitchButtonCard / ComboBoxCard / PushButtonCard 在这里分别是
 * FieldRow + 一行 FieldControl；GroupCard 是 Card。标题与说明的排版
 * （标题 14px、说明 12px 灰字）沿用 qfluentwidgets 的 StrongBodyLabel +
 * CaptionLabel 组合。
 */

import type { ReactNode } from 'react';
import { Alert, Button, Modal, NumberInput as MantineNumberInput, Select, Switch as MantineSwitch, TextInput as MantineTextInput } from '@mantine/core';

/**
 * 卡片说明的极简富文本 —— 只支持 <b>（加粗）与换行。
 *
 * LocalizerZH 的说明里混着 `<br>` 和 `<font color=...><b>RPM</b></font>`
 * 这类 HTML（例如 `renpybox/module/Localizer/LocalizerZH.py:742-756`），
 * 原壳用 CaptionLabel 的富文本直接渲染。这里**不引入 HTML 渲染**（dangerouslySetInnerHTML
 * 用在文案上是没必要的风险面），只把换行和加粗两种真正影响版式的标记翻出来：
 * 换行决定卡高（1 行 66 / 2 行 82），加粗是原文就有的强调。颜色丢弃。
 */
function RichDescription(props: { text: string }) {
  const lines = String(props.text).split('\n');
  return (
    <>
      {lines.map((line, lineIndex) => (
        <span key={lineIndex} className="setting-card-description-line">
          {line.split(/(<b>.*?<\/b>)/g).map((piece, pieceIndex) => {
            const bold = /^<b>.*<\/b>$/.test(piece);
            const text = bold ? piece.slice(3, -4) : piece.replace(/<[^>]+>/g, '');
            if (!text) return null;
            return bold ? <b key={pieceIndex}>{text}</b> : <span key={pieceIndex}>{text}</span>;
          })}
        </span>
      ))}
    </>
  );
}

const TONE_COLOR = { info: 'brand', success: 'green', warning: 'yellow', error: 'red' } as const;

/** 设置行。单独出现时自带面板；放进 SettingsGroup 后只保留分隔线。 */
export function SettingCard(props: {
  title: ReactNode;
  description: ReactNode;
  children?: ReactNode;
}) {
  const { title, description, children } = props;
  return (
    <section className="rb-setting-row">
      <div className="rb-setting-text">
        <div className="rb-setting-title">{title}</div>
        <div className="rb-setting-desc">
          {typeof description === 'string' ? <RichDescription text={description} /> : description}
        </div>
      </div>
      {children ? <div className="rb-setting-control">{children}</div> : null}
    </section>
  );
}

export function PageHeader(props: {
  title: ReactNode;
  description?: ReactNode;
  titleExtra?: ReactNode;
  actions?: ReactNode;
}) {
  const { title, description, titleExtra, actions } = props;
  return (
    <header className="rb-page-header">
      <div>
        <div className="rb-page-title-row">
          <h1 className="rb-page-title">{title}</h1>
          {titleExtra}
        </div>
        {description ? <p className="rb-page-desc">{description}</p> : null}
      </div>
      {actions ? <div className="rb-page-actions">{actions}</div> : null}
    </header>
  );
}

export function SettingsGroup(props: {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
}) {
  const { title, description, actions, children } = props;
  const headed = title != null || description != null || actions != null;
  return (
    <section className="rb-settings-group">
      {headed ? (
        <header className="rb-settings-head">
          <div>
            {title ? <h2 className="rb-settings-title">{title}</h2> : null}
            {description ? <p className="rb-settings-desc">{description}</p> : null}
          </div>
          {actions ? <div className="rb-settings-actions">{actions}</div> : null}
        </header>
      ) : null}
      <div className="rb-settings-body">{children}</div>
    </section>
  );
}

export function Switch(props: {
  checked: boolean;
  disabled?: boolean;
  onChange: (next: boolean) => void;
  label: string;
}) {
  const { checked, disabled, onChange, label } = props;
  return (
    <MantineSwitch
      checked={checked}
      disabled={disabled}
      aria-label={label}
      onChange={(event) => onChange(event.currentTarget.checked)}
    />
  );
}

/** 数字输入。空串允许临时存在（用户正在输入），不提交。 */
export function NumberInput(props: {
  value: number;
  min: number;
  max: number;
  disabled?: boolean;
  label: string;
  onCommit: (next: number) => void;
}) {
  const { value, min, max, disabled, label, onCommit } = props;
  return (
    <MantineNumberInput
      w={120}
      aria-label={label}
      value={Number.isFinite(value) ? value : ''}
      min={min}
      max={max}
      disabled={disabled}
      onChange={(next) => {
        if (typeof next === 'number' && Number.isFinite(next)) onCommit(next);
      }}
    />
  );
}

export function TextInput(props: {
  value: string;
  label: string;
  disabled?: boolean;
  placeholder?: string;
  allowEmpty?: boolean;
  onCommit: (next: string) => void;
}) {
  const { value, label, disabled, placeholder, allowEmpty, onCommit } = props;
  return (
    <MantineTextInput
      w={240}
      aria-label={label}
      value={value}
      disabled={disabled}
      placeholder={placeholder}
      onChange={(event) => {
        const next = event.currentTarget.value;
        if (allowEmpty || next !== '') onCommit(next);
      }}
    />
  );
}

export function SelectInput(props: {
  value: string;
  options: { value: string; label: string }[];
  label: string;
  disabled?: boolean;
  onCommit: (next: string) => void;
}) {
  const { value, options, label, disabled, onCommit } = props;
  return (
    <Select
      w={200}
      aria-label={label}
      value={value}
      data={options}
      disabled={disabled}
      allowDeselect={false}
      onChange={(next) => {
        if (next != null) onCommit(next);
      }}
    />
  );
}

export function Banner(props: {
  tone?: 'info' | 'success' | 'warning' | 'error';
  children: ReactNode;
  onDismiss?: () => void;
}) {
  const { tone = 'info', children, onDismiss } = props;
  return (
    <Alert className="banner" variant="light" color={TONE_COLOR[tone]}>
      <div className="rb-banner">
        <div className="rb-banner-text">{children}</div>
        {onDismiss ? (
          <Button variant="subtle" size="xs" onClick={onDismiss}>知道了</Button>
        ) : null}
      </div>
    </Alert>
  );
}

export function Dialog(props: {
  title: string;
  children?: ReactNode;
  confirmText?: string;
  cancelText?: string;
  extraText?: string;
  onConfirm?: () => void;
  onCancel: () => void;
  /** 第三个按钮的独立回调；缺省时等同于取消（如「打开工作台」而不是「取消」）。 */
  onExtra?: () => void;
}) {
  const {
    title,
    children,
    confirmText = '确认',
    cancelText = '取消',
    extraText,
    onConfirm,
    onCancel,
    onExtra,
  } = props;
  return (
    <Modal
      opened
      onClose={onCancel}
      size={560}
      title={title}
      withCloseButton={false}
      classNames={{ content: 'dialog' }}
      onKeyDown={(event) => {
        if (event.key === 'Escape') onCancel();
      }}
    >
      {children}
      <div className="rb-dialog-actions">
        <Button variant="default" onClick={onCancel}>{cancelText}</Button>
        {extraText ? <Button variant="default" onClick={onExtra ?? onCancel}>{extraText}</Button> : null}
        {onConfirm ? <Button data-autofocus onClick={onConfirm}>{confirmText}</Button> : null}
      </div>
    </Modal>
  );
}

export function Empty(props: { children: ReactNode }) {
  return <div className="rb-empty">{props.children}</div>;
}
