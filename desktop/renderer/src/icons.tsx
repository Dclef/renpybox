/**
 * 图标。
 *
 * 导航与命令栏的图标在 PyQt 侧是 qfluentwidgets 的字体图标（FluentIcon.*），
 * 渲染端没有这套字体，所以按 Fluent 的视觉语义手写内联 SVG 补齐：
 * 线宽 1.6、24 视框、currentColor 描边，尺寸靠 font-size 或 width/height 控制。
 *
 * 工具箱 25 个图标直接用项目自带的 resource/icons/toolbox/*.svg（Lucide），
 * 见 toolIcons.ts —— 不在这里重复画一遍，避免和 PyQt 侧的 ToolIcon 漂移。
 */

import type { SVGProps } from 'react';
import {
  BookOpenText,
  Bot,
  FlaskConical,
  FolderCog,
  Info,
  Languages,
  MessageSquareText,
  Plug,
  Settings,
  ShieldBan,
  SlidersHorizontal,
  SpellCheck,
  UsersRound,
  Variable,
  Wrench,
  type LucideIcon,
} from 'lucide-react';

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function Svg({ size = 18, children, ...rest }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      {children}
    </svg>
  );
}

/** 翻译任务 */
export function IconPlay(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="M8 5.5v13l11-6.5z" fill="currentColor" stroke="none" />
    </Svg>
  );
}

/** Agent 助手 */
export function IconRobot(p: IconProps) {
  return (
    <Svg {...p}>
      <rect x="4" y="8" width="16" height="11" rx="3" />
      <path d="M12 4v4" />
      <circle cx="9" cy="13.5" r="1.1" fill="currentColor" stroke="none" />
      <circle cx="15" cy="13.5" r="1.1" fill="currentColor" stroke="none" />
      <path d="M9 17h6" />
    </Svg>
  );
}

/** 项目设置 */
export function IconFolder(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="M3 7a2 2 0 0 1 2-2h4l2 2.5h6a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
    </Svg>
  );
}

/** 接口管理 */
export function IconIot(p: IconProps) {
  return (
    <Svg {...p}>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 3v3M12 18v3M3 12h3M18 12h3M6 6l2 2M16 16l2 2M18 6l-2 2M8 16l-2 2" />
    </Svg>
  );
}

/** Ren'Py 工具箱 */
export function IconGame(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="M7 9h10a4 4 0 0 1 4 4v2a3 3 0 0 1-5.2 2L15 16H9l-.8 1A3 3 0 0 1 3 15v-2a4 4 0 0 1 4-4z" />
      <path d="M8 11v2.5M6.5 12.2h3" />
      <circle cx="15.5" cy="12" r="1" fill="currentColor" stroke="none" />
      <circle cx="17.5" cy="13.6" r="1" fill="currentColor" stroke="none" />
    </Svg>
  );
}

/** 角色 / 世界观工作台 */
export function IconPeople(p: IconProps) {
  return (
    <Svg {...p}>
      <circle cx="9" cy="8.5" r="3" />
      <path d="M3.5 19a5.5 5.5 0 0 1 11 0" />
      <path d="M16 6.2a3 3 0 0 1 0 5.6M17.5 19a5.5 5.5 0 0 0-2-4.3" />
    </Svg>
  );
}

/** 基础设置 */
export function IconZoom(p: IconProps) {
  return (
    <Svg {...p}>
      <circle cx="10.5" cy="10.5" r="6" />
      <path d="M15 15l5 5" />
      <path d="M8 10.5h5" />
    </Svg>
  );
}

/** 专家设置 */
export function IconEducation(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="M12 4l9 4-9 4-9-4z" />
      <path d="M7 10.5V16c0 1.4 2.2 2.5 5 2.5s5-1.1 5-2.5v-5.5" />
    </Svg>
  );
}

/** 翻译提示 */
export function IconSpeakers(p: IconProps) {
  return (
    <Svg {...p}>
      <rect x="5" y="9" width="3.5" height="6" rx="1" />
      <path d="M11.5 9h2a4 4 0 0 1 0 6h-2z" />
      <path d="M18 8.5a5 5 0 0 1 0 7" />
    </Svg>
  );
}

/** 应用设置 */
export function IconSetting(p: IconProps) {
  return (
    <Svg {...p}>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1V21a2 2 0 1 1-4 0v-.1A1.6 1.6 0 0 0 7.5 19.4l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.6 1.6 0 0 0 3 13.9H3a2 2 0 1 1 0-4h.1A1.6 1.6 0 0 0 4.6 7.5l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.6 1.6 0 0 0 10 3.6V3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 2.7 1.1l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0 1.1 2.7H21a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1.3z" />
    </Svg>
  );
}

/** 切换主题 */
export function IconContrast(p: IconProps) {
  return (
    <Svg {...p}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 3.5v17a8.5 8.5 0 0 0 0-17z" fill="currentColor" stroke="none" />
    </Svg>
  );
}

/** 停止 */
export function IconStop(p: IconProps) {
  return (
    <Svg {...p}>
      <circle cx="12" cy="12" r="8.5" />
      <rect x="9" y="9" width="6" height="6" rx="1" fill="currentColor" stroke="none" />
    </Svg>
  );
}

/** 继续任务 */
export function IconRotate(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="M20 12a8 8 0 1 1-2.6-5.9" />
      <path d="M20 4.5V10h-5.5" />
    </Svg>
  );
}

/** 重翻失败项 */
export function IconSync(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="M4.5 12a7.5 7.5 0 0 1 12.8-5.3L20 9" />
      <path d="M20 5v4h-4" />
      <path d="M19.5 12a7.5 7.5 0 0 1-12.8 5.3L4 15" />
      <path d="M4 19v-4h4" />
    </Svg>
  );
}

/** 写入译文文件 */
export function IconShare(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="M12 3v11" />
      <path d="M8.5 6.5L12 3l3.5 3.5" />
      <path d="M5 13v5a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-5" />
    </Svg>
  );
}

/** Token 估算 */
export function IconCalories(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="M12 21c3.5 0 6-2.3 6-5.6 0-4-3.2-5.9-4.4-9.4-.4-1.1-1.8-1.3-2.4-.2C9 8.2 7 9.5 7.2 12.6 7.3 15 8.6 16.4 10.4 17" />
      <path d="M9.5 17.5A3.2 3.2 0 0 0 12 16" />
    </Svg>
  );
}

/** 打开平行校对台 */
export function IconDocument(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="M13.5 3.5H7a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V9z" />
      <path d="M13.5 3.5V9H19" />
      <path d="M9 13h6M9 16.5h4" />
    </Svg>
  );
}

/** 关于与诊断 */
export function IconInfo(p: IconProps) {
  return (
    <Svg {...p}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 11v5" />
      <circle cx="12" cy="8" r="0.9" fill="currentColor" stroke="none" />
    </Svg>
  );
}

/** 搜索 */
export function IconSearch(p: IconProps) {
  return (
    <Svg {...p}>
      <circle cx="11" cy="11" r="6.5" />
      <path d="M16 16l4 4" />
    </Svg>
  );
}

/** 打开 / 跳转箭头（工具卡右上角） */
export function IconChevronRight(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="M9.5 5.5l6.5 6.5-6.5 6.5" />
    </Svg>
  );
}

/** 复制图标 */
export function IconCopy(p: IconProps) {
  return (
    <Svg size={14} {...p}>
      <rect x="9" y="9" width="12" height="12" rx="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </Svg>
  );
}

/** 编辑图标 */
export function IconEdit(p: IconProps) {
  return (
    <Svg size={14} {...p}>
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
    </Svg>
  );
}

/** 确认 / 对勾图标 */
export function IconCheck(p: IconProps) {
  return (
    <Svg size={14} {...p}>
      <polyline points="20 6 9 17 4 12" />
    </Svg>
  );
}

/** 更多操作 (···) 图标 */
export function IconDots(p: IconProps) {
  return (
    <Svg size={16} {...p}>
      <circle cx="12" cy="12" r="1.5" fill="currentColor" stroke="none" />
      <circle cx="19" cy="12" r="1.5" fill="currentColor" stroke="none" />
      <circle cx="5" cy="12" r="1.5" fill="currentColor" stroke="none" />
    </Svg>
  );
}

/**
 * 无边框窗口的控制图标 —— Windows 11 标题栏口径：10px 字形、1px 细线，
 * 所以这几个单独用 10 视框而不是 24，避免缩放后线宽失真。
 */
export function IconChromeMinimize(p: IconProps) {
  return (
    <Svg viewBox="0 0 10 10" strokeWidth={1} {...p}>
      <path d="M0.5 5h9" />
    </Svg>
  );
}

export function IconChromeMaximize(p: IconProps) {
  return (
    <Svg viewBox="0 0 10 10" strokeWidth={1} {...p}>
      <path d="M0.5 0.5h9v9h-9z" />
    </Svg>
  );
}

export function IconChromeRestore(p: IconProps) {
  return (
    <Svg viewBox="0 0 10 10" strokeWidth={1} {...p}>
      <path d="M3.2 0.5h6.3v6.3" />
      <path d="M0.5 3.2h6.3v6.3h-6.3z" />
    </Svg>
  );
}

export function IconChromeClose(p: IconProps) {
  return (
    <Svg viewBox="0 0 10 10" strokeWidth={1} {...p}>
      <path d="M0.5 0.5l9 9" />
      <path d="M9.5 0.5l-9 9" />
    </Svg>
  );
}

/**
 * 导航图标名 —— nav.ts 里只存名字，渲染时再由这里解析成组件，
 * 这样 nav.ts 保持纯数据（可回查 labelKey），不牵涉 JSX。
 */
export type NavIconName =
  | 'Languages'
  | 'SpellCheck'
  | 'Bot'
  | 'FolderCog'
  | 'Plug'
  | 'Wrench'
  | 'BookOpenText'
  | 'ShieldBan'
  | 'Variable'
  | 'UsersRound'
  | 'SlidersHorizontal'
  | 'FlaskConical'
  | 'MessageSquareText'
  | 'Settings'
  | 'Info';

export const NAV_ICONS: Record<NavIconName, LucideIcon> = {
  Languages,
  SpellCheck,
  Bot,
  FolderCog,
  Plug,
  Wrench,
  BookOpenText,
  ShieldBan,
  Variable,
  UsersRound,
  SlidersHorizontal,
  FlaskConical,
  MessageSquareText,
  Settings,
  Info,
};
