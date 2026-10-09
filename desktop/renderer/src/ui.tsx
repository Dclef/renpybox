/**
 * 通用控件 —— 对应 PyQt 侧的 widget/ 卡片组件。
 *
 * SpinCard / SwitchButtonCard / ComboBoxCard / PushButtonCard 在这里分别是
 * FieldRow + 一行 FieldControl；GroupCard 是 Card。标题与说明的排版
 * （标题 14px、说明 12px 灰字）沿用 qfluentwidgets 的 StrongBodyLabel +
 * CaptionLabel 组合。
 */

import type { CSSProperties, ReactNode } from 'react';
import { Alert, Button, Modal, NumberInput as MantineNumberInput, Select, Switch as MantineSwitch, TextInput as MantineTextInput } from '@mantine/core';

import type { FieldSpec } from './settingsSchema';

export function Card(props: {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
}) {
  const { title, description, actions, children } = props;
  return (
    <section className="card">
      {(title || actions) && (
        <header
          style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
            {typeof title === 'string' ? <div className="card-title">{title}</div> : title}
            {typeof description === 'string' ? (
              <div className="card-description">{description}</div>
            ) : (
              description
            )}
          </div>
          {actions ? <div style={{ flexShrink: 0 }}>{actions}</div> : null}
        </header>
      )}
      {children}
    </section>
  );
}

export function FieldRow(props: { title: ReactNode; hint?: ReactNode; children: ReactNode }) {
  const { title, hint, children } = props;
  return (
    <div className="field">
      <div className="field-label">
        <span className="field-label-text">{title}</span>
        {hint ? <span className="field-label-hint">{hint}</span> : null}
      </div>
      <div className="field-control">{children}</div>
    </div>
  );
}

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

/**
 * 按 FieldSpec 渲染一行控件并回调新值。
 * 回调只给出「用户改成什么」，落盘与乐观更新由页面负责。
 */
export function SpecField(props: {
  spec: FieldSpec;
  value: unknown;
  disabled?: boolean;
  onChange: (key: string, next: unknown) => void;
}) {
  const { spec, value, disabled, onChange } = props;
  const set = (next: unknown) => onChange(spec.key, next);

  let control: ReactNode;
  switch (spec.kind) {
    case 'switch':
      control = (
        <Switch
          checked={value === true}
          disabled={disabled}
          label={spec.title}
          onChange={set}
        />
      );
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
    case 'password':
    case 'multiline':
    case 'text':
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
    <FieldRow title={spec.title} hint={spec.description}>
      {control}
    </FieldRow>
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

export function Stat(props: { label: ReactNode; value: ReactNode; tone?: string }) {
  const { label, value, tone } = props;
  return (
    <div className="stat">
      <span className="stat-label">{label}</span>
      <span className="stat-value" data-tone={tone}>
        {value}
      </span>
    </div>
  );
}

/**
 * 现代 Fluent Design (WinUI 3 风格) 表格组件
 */
export function Table(props: {
  className?: string;
  container?: boolean;
  striped?: boolean;
  compact?: boolean;
  relaxed?: boolean;
  children: ReactNode;
  style?: CSSProperties;
}) {
  const { className = '', container = false, striped, compact, relaxed, children, style } = props;
  const classes = [
    'table',
    striped ? 'table-striped' : '',
    compact ? 'table-compact' : '',
    relaxed ? 'table-relaxed' : '',
    className,
  ].filter(Boolean).join(' ');

  const content = (
    <table className={classes} style={style}>
      {children}
    </table>
  );

  if (container) {
    return <div className="table-container">{content}</div>;
  }
  return content;
}

export function TableHead(props: { className?: string; children: ReactNode }) {
  return <thead className={props.className}>{props.children}</thead>;
}

export function TableBody(props: { className?: string; children: ReactNode }) {
  return <tbody className={props.className}>{props.children}</tbody>;
}

export function TableRow(props: {
  selected?: boolean;
  className?: string;
  onClick?: () => void;
  children: ReactNode;
  style?: CSSProperties;
}) {
  const { selected, className = '', onClick, children, style } = props;
  const classes = [selected ? 'is-selected' : '', className].filter(Boolean).join(' ');
  return (
    <tr
      className={classes || undefined}
      data-selected={selected || undefined}
      aria-selected={selected || undefined}
      onClick={onClick}
      style={style}
    >
      {children}
    </tr>
  );
}

export function TableHeaderCell(props: {
  align?: 'left' | 'center' | 'right';
  width?: number | string;
  tag?: string;
  tagAccent?: boolean;
  className?: string;
  style?: CSSProperties;
  children?: ReactNode;
}) {
  const { align, width, tag, tagAccent, className = '', style, children } = props;
  const alignClass = align === 'right' ? 'col-num' : align === 'center' ? 'col-center' : '';
  const classes = [alignClass, className].filter(Boolean).join(' ');
  return (
    <th className={classes || undefined} style={{ width, ...style }}>
      {children}
      {tag ? (
        <span className={`table-header-tag${tagAccent ? ' table-header-tag-accent' : ''}`}>
          {tag}
        </span>
      ) : null}
    </th>
  );
}

export function TableCell(props: {
  align?: 'left' | 'center' | 'right';
  time?: boolean;
  num?: boolean;
  mono?: boolean;
  muted?: boolean;
  nowrap?: boolean;
  colSpan?: number;
  rowSpan?: number;
  className?: string;
  style?: CSSProperties;
  children?: ReactNode;
}) {
  const {
    align,
    time,
    num,
    mono,
    muted,
    nowrap,
    colSpan,
    rowSpan,
    className = '',
    style,
    children,
  } = props;
  const classes = [
    time ? 'col-time' : '',
    num || align === 'right' ? 'col-num' : '',
    align === 'center' ? 'col-center' : '',
    mono ? 'mono' : '',
    muted ? 'col-muted' : '',
    nowrap ? 'col-nowrap' : '',
    className,
  ].filter(Boolean).join(' ');

  return (
    <td
      className={classes || undefined}
      colSpan={colSpan}
      rowSpan={rowSpan}
      style={style}
    >
      {children}
    </td>
  );
}
