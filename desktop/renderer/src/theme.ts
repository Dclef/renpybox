/**
 * 设计令牌沿用 Python 侧 widget/ThemeTokens.py 的语义命名。
 *
 * Electron 使用独立配色；修改时保持各语义色的明暗与状态对比，
 * 避免影响文字可读性和交互辨识。
 *
 * 注释里保留的设计原则（来自 ThemeTokens.py）：
 * 中性表面跟随 Windows 11 明暗调色板，颜色只留给交互与状态，
 * 工作区保持安静。
 */

export type ThemeName = 'LIGHT' | 'DARK';

export interface ThemePalette {
  accent: string;
  accentHover: string;
  accentPressed: string;
  accentSurface: string;
  onAccent: string;
  background: string;
  surface: string;
  surfaceSubtle: string;
  surfaceHover: string;
  surfacePressed: string;
  chrome: string;
  textPrimary: string;
  textSecondary: string;
  textDisabled: string;
  border: string;
  borderStrong: string;
  divider: string;
  scrollbar: string;
  scrollbarHover: string;
  success: string;
  warning: string;
  error: string;
  info: string;
}

export const LIGHT: ThemePalette = {
  accent: '#0E7C7B',
  accentHover: '#0B6D6C',
  accentPressed: '#095A59',
  accentSurface: '#DDF2EF',
  onAccent: '#FFFFFF',
  background: '#F5F7F7',
  surface: '#FFFFFF',
  surfaceSubtle: '#F0F4F4',
  surfaceHover: '#F3F8F7',
  surfacePressed: '#E3ECEC',
  chrome: '#EEF2F2',
  textPrimary: '#182329',
  textSecondary: '#607079',
  textDisabled: '#9BA8AC',
  border: 'rgba(24, 35, 41, 0.12)',
  borderStrong: 'rgba(24, 35, 41, 0.22)',
  divider: 'rgba(24, 35, 41, 0.10)',
  scrollbar: '#A6B3B6',
  scrollbarHover: '#7D8C90',
  success: '#2D7D56',
  warning: '#AD6B1F',
  error: '#B94A48',
  info: '#2E709A',
};

export const DARK: ThemePalette = {
  accent: '#66FFE8',
  accentHover: '#85FFF0',
  accentPressed: '#33D9C7',
  accentSurface: '#103B3C',
  onAccent: '#10201F',
  background: '#15191C',
  surface: '#1C2326',
  surfaceSubtle: '#182023',
  surfaceHover: '#242D30',
  surfacePressed: '#2A3639',
  chrome: '#12171A',
  textPrimary: '#F1F5F5',
  textSecondary: '#A9B8BA',
  textDisabled: '#6D7B7E',
  border: 'rgba(235, 245, 245, 0.12)',
  borderStrong: 'rgba(235, 245, 245, 0.24)',
  divider: 'rgba(235, 245, 245, 0.10)',
  scrollbar: '#657376',
  scrollbarHover: '#8B9B9D',
  success: '#75C99B',
  warning: '#E5B86D',
  error: '#F08C86',
  info: '#7CB9E2',
};

const CAMEL_TO_KEBAB: Record<keyof ThemePalette, string> = {
  accent: 'accent',
  accentHover: 'accent-hover',
  accentPressed: 'accent-pressed',
  accentSurface: 'accent-surface',
  onAccent: 'on-accent',
  background: 'background',
  surface: 'surface',
  surfaceSubtle: 'surface-subtle',
  surfaceHover: 'surface-hover',
  surfacePressed: 'surface-pressed',
  chrome: 'chrome',
  textPrimary: 'text-primary',
  textSecondary: 'text-secondary',
  textDisabled: 'text-disabled',
  border: 'border',
  borderStrong: 'border-strong',
  divider: 'divider',
  scrollbar: 'scrollbar',
  scrollbarHover: 'scrollbar-hover',
  success: 'success',
  warning: 'warning',
  error: 'error',
  info: 'info',
};

/** 把调色板写成 :root 上的 CSS 变量，组件样式只消费变量，不写死色值。 */
export function applyTheme(theme: ThemeName, root: HTMLElement = document.documentElement): ThemePalette {
  const palette = theme === 'DARK' ? DARK : LIGHT;
  for (const key of Object.keys(palette) as (keyof ThemePalette)[]) {
    root.style.setProperty(`--rb-${CAMEL_TO_KEBAB[key]}`, palette[key]);
  }
  root.dataset.theme = theme;
  root.style.colorScheme = theme === 'DARK' ? 'dark' : 'light';
  return palette;
}

export function readStoredTheme(): ThemeName {
  try {
    const stored = localStorage.getItem('renpybox.theme');
    if (stored === 'LIGHT' || stored === 'DARK') return stored;
  } catch {
    // 隐私模式 / 存储被禁：退回跟随系统
  }
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'DARK' : 'LIGHT';
}

export function persistTheme(theme: ThemeName): void {
  try {
    localStorage.setItem('renpybox.theme', theme);
  } catch {
    // 存不住不影响使用
  }
}
