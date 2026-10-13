/** Main-process fallback for a renderer that cannot show its normal quit dialog. */
export function createWindowCloseGuard({
  window: win, showMessageBox, requestQuit, isQuitting = () => false,
  getLocale = () => 'ZH', log = () => {},
}) {
  const contents = win.webContents;
  let unavailable = false;
  let unresponsive = false;
  let confirmed = false;
  let disposed = false;
  let shutdown = false;
  let cleanupDone = false;
  let reloadPending = false;
  let prompt = null;

  const alive = () => !disposed && !win.isDestroyed();
  const quitting = () => shutdown || isQuitting();
  const unhealthy = () => unavailable || unresponsive || contents.isDestroyed() || contents.isCrashed();
  const invalidatePrompt = () => {
    const previous = prompt;
    prompt = null;
    previous?.abort();
  };
  const destroyAfterCleanup = () => {
    if (alive() && cleanupDone && unhealthy()) win.destroy();
  };
  const reloadAfterCrash = () => queueMicrotask(() => {
    if (!reloadPending || !alive() || quitting()) return;
    reloadPending = false;
    try { if (!contents.isDestroyed()) contents.reload(); }
    catch (error) { log(error); }
  });

  async function offerFallback() {
    if (!alive() || quitting() || prompt) return;
    const current = new AbortController();
    prompt = current;
    try {
      const en = /^en(?:$|[-_])/i.test(String(getLocale()));
      const { response } = await showMessageBox(win, {
        type: 'warning', title: 'RenpyBox',
        message: en ? 'The interface is not responding.' : '界面已停止响应。',
        detail: en
          ? 'Reloading the interface discards unsaved edits; background tasks will keep running. Quitting stops background tasks before closing the application.'
          : '重新加载界面会丢弃未保存的编辑，后台任务会继续运行。退出程序会先停止后台任务再关闭应用。',
        buttons: en ? ['Reload interface', 'Quit', 'Cancel'] : ['重新加载界面', '退出程序', '取消'],
        defaultId: 2, cancelId: 2, noLink: true, signal: current.signal,
      });
      // Recovery, destruction or application shutdown makes this response stale.
      if (prompt !== current || !alive() || quitting()) return;
      prompt = null;
      if (response === 1) {
        requestQuit();
      } else if (response === 0) {
        confirmed = false;
        unavailable = true;
        // A hung renderer cannot run beforeunload. Wait for its exit event:
        // reload immediately after forcefullyCrashRenderer can be silently lost.
        const mustCrash = unresponsive && !contents.isDestroyed() && !contents.isCrashed();
        unresponsive = false;
        reloadPending = true;
        if (mustCrash) {
          try { contents.forcefullyCrashRenderer(); }
          catch (error) { reloadPending = false; throw error; }
        } else reloadAfterCrash();
      }
    } catch (error) {
      if (alive() && !current.signal.aborted) log(error);
    } finally {
      if (prompt === current) prompt = null;
    }
  }

  function onClose(event) {
    if (!alive()) return;
    if (quitting()) {
      if (!cleanupDone) {
        event.preventDefault();
      } else if (unhealthy()) {
        event.preventDefault();
        win.destroy();
      }
      return;
    }
    if (confirmed && !unhealthy()) return;
    event.preventDefault();
    if (unhealthy()) {
      void offerFallback();
      return;
    }
    try { contents.send('window:close-requested'); }
    catch (error) {
      log(error);
      unavailable = true;
      void offerFallback();
    }
  }
  function onGone() {
    unavailable = true;
    confirmed = false;
    destroyAfterCleanup();
    if (reloadPending) reloadAfterCrash();
  }
  function onUnresponsive() {
    unresponsive = true;
    confirmed = false;
    destroyAfterCleanup();
  }
  function onResponsive() {
    unresponsive = false;
    if (!unhealthy()) invalidatePrompt();
  }
  function onLoaded() {
    reloadPending = false;
    unavailable = false;
    unresponsive = false;
    confirmed = false;
    invalidatePrompt();
  }
  function onWillPreventUnload(event) {
    // app.quit (including update installation) has already committed to shutdown.
    // Healthy user closes still respect the renderer's dirty/RPY barrier.
    if (quitting()) event.preventDefault();
    else confirmed = false;
  }
  function dispose() {
    if (disposed) return;
    disposed = true;
    reloadPending = false;
    invalidatePrompt();
    win.removeListener('close', onClose);
    win.removeListener('closed', dispose);
    win.removeListener('unresponsive', onUnresponsive);
    win.removeListener('responsive', onResponsive);
    contents.removeListener('render-process-gone', onGone);
    contents.removeListener('did-finish-load', onLoaded);
    contents.removeListener('will-prevent-unload', onWillPreventUnload);
  }

  win.on('close', onClose);
  win.on('closed', dispose);
  win.on('unresponsive', onUnresponsive);
  win.on('responsive', onResponsive);
  contents.on('render-process-gone', onGone);
  contents.on('did-finish-load', onLoaded);
  contents.on('will-prevent-unload', onWillPreventUnload);
  return {
    confirm() {
      if (!alive() || quitting() || unhealthy() || prompt) return;
      confirmed = true;
      win.close();
    },
    beginQuit() {
      shutdown = true;
      reloadPending = false;
      invalidatePrompt();
    },
    finishQuit() {
      shutdown = true;
      cleanupDone = true;
      reloadPending = false;
      invalidatePrompt();
      destroyAfterCleanup();
    },
    dispose,
  };
}
