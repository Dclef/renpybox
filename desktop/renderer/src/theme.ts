/**
 * 设计令牌。中性色在这里；强调色为 Ant 默认蓝，由 antdTheme 按算法推导后注入 ConfigProvider 与 --rb-*。
 */

export type ThemeName = 'LIGHT' | 'DARK';

export interface ThemePalette {
  background: string;
  surface: string;
  surfaceSubtle: string;
  surfaceHover: string;
  surfacePressed: string;
  chrome: string;
  sidebarHover: string;
  textPrimary: string;
  textSecondary: string;
  textPlaceholder: string;
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
  shadowOverlay: string;
}

export interface AccentTokens {
  accent: string;
  accentHover: string;
  accentPressed: string;
  accentText: string;
  accentSurface: string;
  onAccent: string;
}

export const LIGHT: ThemePalette = {
  background: '#FFFFFF',
  surface: '#FFFFFF',
  surfaceSubtle: '#F4F4F5',
  surfaceHover: '#F4F4F5',
  surfacePressed: '#E4E4E7',
  chrome: '#F4F4F5',
  sidebarHover: '#E4E4E7',
  textPrimary: '#18181B',
  textSecondary: '#52525B',
  textPlaceholder: '#71717A',
  textDisabled: '#A1A1AA',
  border: '#E4E4E7',
  borderStrong: '#D4D4D8',
  divider: '#E4E4E7',
  scrollbar: '#A1A1AA',
  scrollbarHover: '#71717A',
  success: '#15803D',
  warning: '#B45309',
  error: '#B91C1C',
  info: '#1D4ED8',
  shadowOverlay: '0 8px 24px rgba(0,0,0,.12)',
};

export const DARK: ThemePalette = {
  background: '#18181B',
  surface: '#18181B',
  surfaceSubtle: '#232326',
  surfaceHover: '#232326',
  surfacePressed: '#2A2A2E',
  chrome: '#111113',
  sidebarHover: '#1F1F23',
  textPrimary: '#FAFAFA',
  textSecondary: '#A1A1AA',
  textPlaceholder: '#71717A',
  textDisabled: '#52525B',
  border: 'rgba(255,255,255,.08)',
  borderStrong: 'rgba(255,255,255,.14)',
  divider: 'rgba(255,255,255,.08)',
  scrollbar: '#52525B',
  scrollbarHover: '#71717A',
  success: '#4ADE80',
  warning: '#FBBF24',
  error: '#F87171',
  info: '#60A5FA',
  shadowOverlay: '0 8px 24px rgba(0,0,0,.5)',
};

const NEUTRAL_VARS: Record<keyof ThemePalette, string> = {
  background: '--rb-background',
  surface: '--rb-surface',
  surfaceSubtle: '--rb-surface-subtle',
  surfaceHover: '--rb-surface-hover',
  surfacePressed: '--rb-surface-pressed',
  chrome: '--rb-chrome',
  sidebarHover: '--rb-sidebar-hover',
  textPrimary: '--rb-text-primary',
  textSecondary: '--rb-text-secondary',
  textPlaceholder: '--rb-text-placeholder',
  textDisabled: '--rb-text-disabled',
  border: '--rb-border',
  borderStrong: '--rb-border-strong',
  divider: '--rb-divider',
  scrollbar: '--rb-scrollbar',
  scrollbarHover: '--rb-scrollbar-hover',
  success: '--rb-success',
  warning: '--rb-warning',
  error: '--rb-error',
  info: '--rb-info',
  shadowOverlay: '--rb-shadow-overlay',
};

const ACCENT_VARS: Record<keyof AccentTokens, string> = {
  accent: '--rb-accent',
  accentHover: '--rb-accent-hover',
  accentPressed: '--rb-accent-pressed',
  accentText: '--rb-accent-text',
  accentSurface: '--rb-accent-surface',
  onAccent: '--rb-on-accent',
};

/** 中性色和强调色合成 --rb-* 变量表。 */
export function toCssVariables(scheme: ThemeName, accent: AccentTokens): Record<string, string> {
  const palette = scheme === 'DARK' ? DARK : LIGHT;
  const vars: Record<string, string> = {};
  for (const key of Object.keys(NEUTRAL_VARS) as (keyof ThemePalette)[]) {
    vars[NEUTRAL_VARS[key]] = palette[key];
  }
  for (const key of Object.keys(ACCENT_VARS) as (keyof AccentTokens)[]) {
    vars[ACCENT_VARS[key]] = accent[key];
  }
  return vars;
}

/** 切换明暗标记；CSS 变量由 antdTheme.applyRbCssVariables 同步写入。 */
export function applyTheme(theme: ThemeName, root: HTMLElement = document.documentElement): ThemePalette {
  root.dataset.theme = theme;
  root.style.colorScheme = theme === 'DARK' ? 'dark' : 'light';
  return theme === 'DARK' ? DARK : LIGHT;
}

/** 读取本地缓存的主题偏好；没有偏好时固定为 LIGHT，保证首帧不先黑后白。 */
export function readStoredTheme(): ThemeName {
  try {
    const stored = localStorage.getItem('renpybox.theme');
    if (stored === 'LIGHT' || stored === 'DARK') return stored;
  } catch {
    // 隐私模式 / 存储被禁：退回浅色兜底
  }
  return 'LIGHT';
}

export function persistTheme(theme: ThemeName): void {
  try {
    localStorage.setItem('renpybox.theme', theme);
  } catch {
    // 存不住不影响使用
  }
}
