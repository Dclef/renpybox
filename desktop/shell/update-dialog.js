// 状态和进度来自 Electron updater；页面不模拟下载或安装结果。
(function () {
  const $ = (id) => document.getElementById(id);
  const bridge = window.shellBridge;
  const updater = bridge?.updater;
  const pending = new Set();
  let current = null;
  let receivedState = false;
  let confirmOpen = false;

  function showError(error) {
    $('error').textContent = String(error?.message || error || '');
    $('error').hidden = !$('error').textContent;
  }

  function render(next) {
    current = next;
    if (!current) return;
    const { status, packaged, version, currentVersion } = current;
    const progress = Math.max(0, Math.min(100, Math.round(current.progress || 0)));
    $('from').textContent = currentVersion || '—';
    $('to').textContent = version || '—';
    $('target').hidden = !version;
    $('progress').hidden = status !== 'downloading';
    $('progress').value = progress;
    const descriptions = {
      dev: '开发模式，请使用安装版测试自动更新',
      idle: '尚未检查更新',
      checking: '正在检查更新…',
      available: `发现新版本 ${version || ''}`,
      latest: '当前已是最新版本',
      downloading: `正在下载 ${progress}%`,
      downloaded: '下载完成，可以重启安装',
      error: '更新失败，请重试',
    };
    $('status').textContent = descriptions[status] || '更新状态未知';
    if (status === 'error') showError(current.error);
    const cancelling = pending.has('cancel');
    $('now').textContent = status === 'available' ? '下载更新'
      : status === 'downloading' ? (cancelling ? '正在取消…' : '取消下载')
        : status === 'downloaded' ? '重启并安装'
          : status === 'checking' ? '检查中…' : '检查更新';
    $('now').disabled = !packaged || status === 'dev' || status === 'checking'
      || (status === 'downloading' ? cancelling : pending.size > 0) || confirmOpen;
    $('details').hidden = !current.releaseUrl;
    $('details').disabled = confirmOpen;
    $('later').disabled = confirmOpen;
    if (confirmOpen && status !== 'downloaded') closeConfirm();
  }

  async function run(action) {
    if (!updater || !current?.packaged || pending.has(action)) return;
    if (action === 'download' && current.status !== 'available') return;
    if (action === 'cancel' && current.status !== 'downloading') return;
    if (action === 'install' && current.status !== 'downloaded') return;
    if (action === 'check' && ['checking', 'downloading', 'downloaded'].includes(current.status)) return;
    if (action !== 'cancel' && pending.size > 0) return;
    pending.add(action);
    showError('');
    render(current);
    try {
      if (action === 'install') await updater.install();
      else render(await updater[action]());
    } catch (error) { showError(error); }
    finally { pending.delete(action); render(current); }
  }

  function closeConfirm() {
    confirmOpen = false;
    $('install-confirm').hidden = true;
    render(current);
    $('now').focus();
  }

  $('later').addEventListener('click', () => bridge?.close ? bridge.close() : window.close());
  $('now').addEventListener('click', () => {
    if (current?.status === 'downloaded') {
      confirmOpen = true;
      $('install-confirm').hidden = false;
      render(current);
      $('confirm-cancel').focus();
    } else {
      void run(current?.status === 'available' ? 'download' : current?.status === 'downloading' ? 'cancel' : 'check');
    }
  });
  $('confirm-cancel').addEventListener('click', closeConfirm);
  $('confirm-install').addEventListener('click', () => { closeConfirm(); void run('install'); });
  document.addEventListener('keydown', (event) => {
    if (!confirmOpen) return;
    if (event.key === 'Escape') closeConfirm();
    if (event.key === 'Tab') {
      event.preventDefault();
      (document.activeElement === $('confirm-cancel') ? $('confirm-install') : $('confirm-cancel')).focus();
    }
  });
  $('details').addEventListener('click', () => {
    if (current?.releaseUrl) void bridge.openExternal(current.releaseUrl).catch(showError);
  });

  if (!updater) {
    $('status').textContent = '桌面更新接口不可用，请重新打开应用。';
    return;
  }
  const unsubscribe = updater.onState((next) => { receivedState = true; showError(''); render(next); });
  window.addEventListener('unload', unsubscribe, { once: true });
  void updater.state().then((next) => { if (!receivedState) render(next); }).catch((error) => {
    if (!receivedState) { $('status').textContent = '读取更新状态失败'; showError(error); }
  });
})();
