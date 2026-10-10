import './styles/layers.css';
import './styles.css';
import './styles/app.css';

import { StrictMode, useEffect, useMemo } from 'react';
import { createRoot } from 'react-dom/client';
import { App as AntApp, ConfigProvider } from 'antd';
import enUS from 'antd/locale/en_US';
import zhCN from 'antd/locale/zh_CN';

import { App } from './App';
import { applyRbCssVariables, buildAntdTheme } from './antdTheme';
import { applyTheme, readStoredTheme, type ThemeName } from './theme';
import { useAppState } from './useAppState';

// 首个 HTML 绘制前同步写入 data-theme 与 --rb-* 变量，避免启动先黑后白；
// 与 useAppState 的 fallbackTheme 同源，服务端主题到达后再由 Root effect 覆盖。
const initialScheme = readStoredTheme();
applyTheme(initialScheme);
applyRbCssVariables(initialScheme);
// 记录已写入 DOM 的主题，Root effect 只在实际变化时重写。
let appliedScheme: ThemeName = initialScheme;

function Root() {
  const state = useAppState();
  const scheme = state.theme === 'DARK' ? 'DARK' : 'LIGHT';
  const antdTheme = useMemo(() => buildAntdTheme(scheme), [scheme]);
  const locale = state.bootLanguage === 'EN' ? enUS : zhCN;

  // 主题切换只改 ConfigProvider token 与 CSS 变量，不 remount 业务树以免丢稿。
  useEffect(() => {
    if (scheme === appliedScheme) return;
    applyTheme(scheme);
    applyRbCssVariables(scheme);
    appliedScheme = scheme;
  }, [scheme]);

  return (
    <ConfigProvider locale={locale} theme={antdTheme} button={{ autoInsertSpace: false }}>
      {/* 不输出 .ant-app 包裹层，保持 #root > .rb-shell 的百分比高度链。 */}
      <AntApp component={false}>
        <App state={state} link={state.link} />
      </AntApp>
    </ConfigProvider>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
);
