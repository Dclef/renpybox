/**
 * 设计令牌沿用 Python 侧 widget/ThemeTokens.py 的语义命名。
 *
 * 色值与 widget/ThemeTokens.py 一致：Windows 11 中性表面 + 系统蓝强调色。
 * Qt 样式表里的 alpha（0–255）在这里换成 CSS 的 0–1。
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
  accent: '#0078D4',
  accentHover: '#006CBE',
  accentPressed: '#005A9E',
  accentSurface: '#E5F3FB',
  onAccent: '#FFFFFF',
  background: '#F3F3F3',
  surface: '#FFFFFF',
  surfaceSubtle: '#F9F9F9',
  surfaceHover: '#F6F6F6',
  surfacePressed: '#EAEAEA',
  chrome: '#F3F3F3',
  textPrimary: '#1A1A1A',
  textSecondary: '#5D5D5D',
  textDisabled: '#9A9A9A',
  border: 'rgba(0, 0, 0, 0.08)',
  borderStrong: 'rgba(0, 0, 0, 0.14)',
  divider: 'rgba(0, 0, 0, 0.07)',
  scrollbar: '#8A8A8A',
  scrollbarHover: '#666666',
  success: '#0F7B0F',
  warning: '#9D5D00',
  error: '#C42B1C',
  info: '#0067C0',
};

export const DARK: ThemePalette = {
  accent: '#4CC2FF',
  accentHover: '#60CDFF',
  accentPressed: '#0091EA',
  accentSurface: '#0B3A4A',
  onAccent: '#000000',
  background: '#202020',
  surface: '#2B2B2B',
  surfaceSubtle: '#252525',
  surfaceHover: '#323232',
  surfacePressed: '#3A3A3A',
  chrome: '#202020',
  textPrimary: '#FFFFFF',
  textSecondary: '#C7C7C7',
  textDisabled: '#777777',
  border: 'rgba(255, 255, 255, 0.08)',
  borderStrong: 'rgba(255, 255, 255, 0.14)',
  divider: 'rgba(255, 255, 255, 0.07)',
  scrollbar: '#8A8A8A',
  scrollbarHover: '#B0B0B0',
  success: '#6CCB5F',
  warning: '#FCE100',
  error: '#FF99A4',
  info: '#60CDFF',
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
