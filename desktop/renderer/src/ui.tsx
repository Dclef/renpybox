/**
 * 通用控件 —— 对应 PyQt 侧的 widget/ 卡片组件。
 *
 * SpinCard / SwitchButtonCard / ComboBoxCard / PushButtonCard 在这里分别是
 * FieldRow + 一行 FieldControl；GroupCard 是 Card。标题与说明的排版
 * （标题 14px、说明 12px 灰字）沿用 qfluentwidgets 的 StrongBodyLabel +
 * CaptionLabel 组合。
 */

import { useEffect, useRef, type ReactNode } from 'react';

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

/**
 * 一张设置卡 —— 对应 PyQt 侧的 `widget/SpinCard.py`、`SwitchButtonCard.py`、
 * `ComboBoxCard.py`、`PushButtonCard.py`、`LineEditCard.py`（它们都是同一个骨架，
 * 只换右侧控件）。实测几何见 renderer/src/styles.css 里 `.setting-card` 的注释。
 */
export function SettingCard(props: {
  title: ReactNode;
  description: ReactNode;
  children?: ReactNode;
}) {
  const { title, description, children } = props;
  return (
    <section className="setting-card">
      <div className="setting-card-text">
        <span className="setting-card-title">{title}</span>
        <span className="setting-card-description">
          {typeof description === 'string' ? <RichDescription text={description} /> : description}
        </span>
      </div>
      {children ? <div className="setting-card-control">{children}</div> : null}
    </section>
  );
}

/** 纯 CSS 开关，与 SwitchButtonCard 一样靠 aria-checked 暴露状态。 */
export function Switch(props: {
  checked: boolean;
  disabled?: boolean;
  onChange: (next: boolean) => void;
  label: string;
}) {
  const { checked, disabled, onChange, label } = props;
  return (
    <button
      type="button"
      className="switch"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
    />
  );
}

/** 数字输入。空串允许临时存在（用户正在输入），失焦时回落到上界内的值。 */
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
    <input
      type="number"
      aria-label={label}
      value={Number.isFinite(value) ? value : ''}
      min={min}
      max={max}
      disabled={disabled}
      onChange={(event) => {
        const next = Number(event.target.value);
        // 空输入时保持原值：直接写 0 会把用户还没打完的数字变成 0
        if (Number.isFinite(next) && event.target.value !== '') onCommit(next);
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
    <input
      type="text"
      aria-label={label}
      value={value}
      disabled={disabled}
      placeholder={placeholder}
      onChange={(event) => {
        const next = event.target.value;
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
    <select
      aria-label={label}
      value={value}
      disabled={disabled}
      onChange={(event) => onCommit(event.target.value)}
    >
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
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
    <div className="banner" data-tone={tone} role="status">
      <div style={{ flex: 1, minWidth: 0 }}>{children}</div>
      {onDismiss ? (
        <button type="button" className="btn" onClick={onDismiss}>
          知道了
        </button>
      ) : null}
    </div>
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
  const dialogRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef(onCancel);
  cancelRef.current = onCancel;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const dialog = dialogRef.current;
    const controls = () => Array.from(dialog?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex="0"]') ?? []).filter(element => element.getClientRects().length > 0);
    if (!dialog?.contains(document.activeElement)) controls()[0]?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); cancelRef.current(); }
      if (event.key !== 'Tab') return;
      const fields = controls();
      const first = fields[0]; const last = fields.at(-1);
      if (!first) { event.preventDefault(); dialog?.focus(); return; }
      if (event.shiftKey && (document.activeElement === first || !dialog?.contains(document.activeElement))) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && (document.activeElement === last || !dialog?.contains(document.activeElement))) { event.preventDefault(); first.focus(); }
    };
    dialog?.addEventListener('keydown', keydown);
    return () => { dialog?.removeEventListener('keydown', keydown); if (previous?.isConnected) previous.focus(); };
  }, []);
  return (
    <div
      className="dialog-backdrop"
      role="presentation"
      onClick={(event) => {
        if (event.target === event.currentTarget) onCancel();
      }}
    >
      <div ref={dialogRef} tabIndex={-1} className="dialog" role="dialog" aria-modal="true" aria-label={title}>
        <h2 className="dialog-title">{title}</h2>
        {children ? <div className="dialog-body">{children}</div> : null}
        <div className="dialog-actions">
          <button type="button" className="btn" onClick={onCancel}>
            {cancelText}
          </button>
          {extraText ? (
            <button type="button" className="btn" onClick={onExtra ?? onCancel}>
              {extraText}
            </button>
          ) : null}
          {onConfirm ? (
            <button type="button" className="btn btn-primary" onClick={onConfirm} autoFocus>
              {confirmText}
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export function Empty(props: { children: ReactNode }) {
  return <div className="empty">{props.children}</div>;
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
