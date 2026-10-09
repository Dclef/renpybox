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
  FolderCog,
  Info,
  Languages,
  Plug,
  Settings,
  SlidersHorizontal,
  SpellCheck,
  UsersRound,
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
  | 'UsersRound'
  | 'SlidersHorizontal'
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
  UsersRound,
  SlidersHorizontal,
  Settings,
  Info,
};
