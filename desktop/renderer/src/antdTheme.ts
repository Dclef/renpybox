/**
 * Ant Design 主题：主色使用 Ant 默认蓝（亮色 #1677ff，暗色由 darkAlgorithm 推导）。
 * --rb-accent* 从 Ant 实际计算出的 design token 派生，导航、选中行、进度与按钮同源。
 */
import type { ThemeConfig } from 'antd';
import { theme } from 'antd';

import { DARK, LIGHT, toCssVariables, type AccentTokens, type ThemeName } from './theme';

export const FONT_FAMILY =
  '"Microsoft YaHei UI", "PingFang SC", "Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif';
export const MONO_FAMILY = '"Cascadia Mono", Consolas, monospace';

const PRIMARY = '#1677ff';

export function buildAntdTheme(scheme: ThemeName): ThemeConfig {
  const palette = scheme === 'DARK' ? DARK : LIGHT;
  const isDark = scheme === 'DARK';
  return {
    algorithm: isDark ? theme.darkAlgorithm : theme.defaultAlgorithm,
    // success / warning / error 不覆盖，交给 Ant 算法按明暗主题推导标准语义色，
    // 避免 Alert 等状态组件出现与默认蓝不协调的深色块。
    token: {
      colorPrimary: PRIMARY,
      colorInfo: PRIMARY,
      colorBgBase: palette.background,
      colorBgContainer: palette.surface,
      colorBgElevated: isDark ? '#232326' : '#FFFFFF',
      colorBgLayout: palette.chrome,
      colorBorder: palette.borderStrong,
      colorBorderSecondary: palette.border,
      colorText: palette.textPrimary,
      colorTextSecondary: palette.textSecondary,
      colorTextTertiary: palette.textPlaceholder,
      colorTextQuaternary: palette.textDisabled,
      fontFamily: FONT_FAMILY,
      fontFamilyCode: MONO_FAMILY,
      fontSize: 14,
      lineHeight: 1.6,
      borderRadius: 10,
      borderRadiusLG: 14,
      borderRadiusSM: 8,
      controlHeight: 36,
      controlHeightSM: 30,
      controlHeightLG: 40,
    },
    components: {
      Button: {
        fontWeight: 500,
      },
      Table: {
        headerBg: palette.surfaceSubtle,
        headerColor: palette.textSecondary,
        rowHoverBg: palette.surfaceHover,
        borderColor: palette.border,
        cellPaddingBlock: 8,
        cellPaddingInline: 12,
        fontSize: 13,
      },
      Checkbox: {
        borderRadiusSM: 4,
      },
    },
  };
}

/** 读取 Ant 按当前算法算出的主色系，保证 CSS 变量与组件颜色一致。 */
function accentFor(scheme: ThemeName): AccentTokens {
  const token = theme.getDesignToken(buildAntdTheme(scheme));
  return {
    accent: token.colorPrimary,
    accentHover: token.colorPrimaryHover,
    accentPressed: token.colorPrimaryActive,
    accentText: token.colorPrimaryText,
    accentSurface: token.colorPrimaryBg,
    onAccent: token.colorTextLightSolid,
  };
}

/** 把 --rb-* 写到 documentElement，供布局 CSS 使用。 */
export function applyRbCssVariables(scheme: ThemeName, root: HTMLElement = document.documentElement): void {
  const vars = toCssVariables(scheme, accentFor(scheme));
  for (const [key, value] of Object.entries(vars)) {
    root.style.setProperty(key, value);
  }
  root.style.setProperty('--rb-font-mono', MONO_FAMILY);
}
