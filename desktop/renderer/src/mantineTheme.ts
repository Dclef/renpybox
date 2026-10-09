import { createTheme, type CSSVariablesResolver, type MantineColorsTuple } from '@mantine/core';

import { DARK, LIGHT, toCssVariables, type AccentTokens, type ThemeName } from './theme';

export const FONT_FAMILY = "'Segoe UI Variable Text', 'Segoe UI', 'Microsoft YaHei UI', 'PingFang SC', system-ui, sans-serif";
const MONO_FAMILY = "'Cascadia Mono', Consolas, monospace";

export type AccentName = 'blue' | 'indigo' | 'teal';

interface AccentSet {
  accent: string;
  accentHover: string;
  accentPressed: string;
  accentText: Record<ThemeName, string>;
  accentSurface: Record<ThemeName, string>;
  onAccent: string;
  brand: MantineColorsTuple;
}

export const ACCENTS: Record<AccentName, AccentSet> = {
  blue: {
    accent: '#2563EB',
    accentHover: '#1D4ED8',
    accentPressed: '#1E40AF',
    accentText: { LIGHT: '#2563EB', DARK: '#60A5FA' },
    accentSurface: { LIGHT: '#EFF6FF', DARK: 'rgba(59,130,246,.15)' },
    onAccent: '#FFFFFF',
    brand: ['#EFF6FF', '#DBEAFE', '#BFDBFE', '#93C5FD', '#60A5FA', '#3B82F6', '#2563EB', '#1D4ED8', '#1E40AF', '#1E3A8A'],
  },
  indigo: {
    accent: '#4F46E5',
    accentHover: '#4338CA',
    accentPressed: '#3730A3',
    accentText: { LIGHT: '#4F46E5', DARK: '#818CF8' },
    accentSurface: { LIGHT: '#EEF2FF', DARK: 'rgba(99,102,241,.15)' },
    onAccent: '#FFFFFF',
    brand: ['#EEF2FF', '#E0E7FF', '#C7D2FE', '#A5B4FC', '#818CF8', '#6366F1', '#4F46E5', '#4338CA', '#3730A3', '#312E81'],
  },
  teal: {
    accent: '#0F766E',
    accentHover: '#115E59',
    accentPressed: '#134E4A',
    accentText: { LIGHT: '#0F766E', DARK: '#2DD4BF' },
    accentSurface: { LIGHT: '#F0FDFA', DARK: 'rgba(20,184,166,.15)' },
    onAccent: '#FFFFFF',
    brand: ['#F0FDFA', '#CCFBF1', '#99F6E4', '#5EEAD4', '#2DD4BF', '#14B8A6', '#0F766E', '#115E59', '#134E4A', '#042F2E'],
  },
};

const GRAY: MantineColorsTuple = ['#FAFAFA', '#F4F4F5', '#E4E4E7', '#D4D4D8', '#A1A1AA', '#71717A', '#52525B', '#3F3F46', '#27272A', '#18181B'];
const DARK_SCALE: MantineColorsTuple = ['#FAFAFA', '#D4D4D8', '#A1A1AA', '#71717A', '#3F3F46', '#2A2A2E', '#232326', '#18181B', '#141416', '#111113'];

export function readAccent(): AccentName {
  try {
    const stored = localStorage.getItem('renpybox.accent');
    if (stored === 'blue' || stored === 'indigo' || stored === 'teal') return stored;
  } catch {
    // 存不住就用默认蓝
  }
  return 'blue';
}

function accentTokens(name: AccentName, scheme: ThemeName): AccentTokens {
  const set = ACCENTS[name];
  return {
    accent: set.accent,
    accentHover: set.accentHover,
    accentPressed: set.accentPressed,
    accentText: set.accentText[scheme],
    accentSurface: set.accentSurface[scheme],
    onAccent: set.onAccent,
  };
}

const accent = ACCENTS[readAccent()];

export const rbTheme = createTheme({
  primaryColor: 'brand',
  primaryShade: { light: 6, dark: 6 },
  defaultRadius: 'sm',
  respectReducedMotion: true,
  fontFamily: FONT_FAMILY,
  fontFamilyMonospace: MONO_FAMILY,
  fontSizes: { xs: '12px', sm: '13px', md: '14px', lg: '16px', xl: '20px' },
  fontWeights: { regular: '400', medium: '500', bold: '600' },
  radius: { xs: '4px', sm: '6px', md: '8px', lg: '8px', xl: '999px' },
  spacing: { xs: '4px', sm: '8px', md: '12px', lg: '16px', xl: '24px' },
  headings: {
    fontWeight: '600',
    sizes: {
      h1: { fontSize: '20px', lineHeight: '1.3', fontWeight: '600' },
      h2: { fontSize: '16px', lineHeight: '1.35', fontWeight: '600' },
      h3: { fontSize: '14px', lineHeight: '1.4', fontWeight: '600' },
      h4: { fontSize: '14px', lineHeight: '1.4', fontWeight: '500' },
      h5: { fontSize: '13px', lineHeight: '1.4', fontWeight: '500' },
      h6: { fontSize: '12px', lineHeight: '1.4', fontWeight: '500' },
    },
  },
  colors: {
    brand: accent.brand,
    gray: GRAY,
    dark: DARK_SCALE,
  },
  components: {
    Button: { defaultProps: { size: 'sm', fw: 500 } },
    Badge: { defaultProps: { variant: 'light', tt: 'none' } },
    Paper: { defaultProps: { withBorder: true, radius: 'md' } },
    Modal: { defaultProps: { radius: 'md', centered: true } },
  },
});

function mantineSchemeVars(scheme: ThemeName): Record<string, string> {
  const palette = scheme === 'DARK' ? DARK : LIGHT;
  return {
    ...toCssVariables(scheme, accentTokens(readAccent(), scheme)),
    '--mantine-color-body': palette.background,
    '--mantine-color-text': palette.textPrimary,
    '--mantine-color-dimmed': palette.textSecondary,
    '--mantine-color-placeholder': palette.textPlaceholder,
    '--mantine-color-default': scheme === 'DARK' ? '#232326' : '#FFFFFF',
    '--mantine-color-default-hover': palette.surfaceHover,
    '--mantine-color-default-color': palette.textPrimary,
    '--mantine-color-default-border': palette.borderStrong,
  };
}

export const rbCssVariables: CSSVariablesResolver = () => ({
  variables: {},
  light: mantineSchemeVars('LIGHT'),
  dark: mantineSchemeVars('DARK'),
});
