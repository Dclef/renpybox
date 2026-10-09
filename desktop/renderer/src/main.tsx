import './styles/layers.css';
import '@mantine/core/styles.layer.css';
import './styles.css';
import './styles/app.css';

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { MantineProvider } from '@mantine/core';

import { App } from './App';
import { rbCssVariables, rbTheme } from './mantineTheme';
import { useAppState } from './useAppState';

function Root() {
  const state = useAppState();
  return (
    <MantineProvider
      theme={rbTheme}
      cssVariablesResolver={rbCssVariables}
      forceColorScheme={state.theme === 'DARK' ? 'dark' : 'light'}
    >
      <App state={state} link={state.link} />
    </MantineProvider>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
);
