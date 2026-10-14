// 日志只通过受限 preload 读取，并始终作为纯文本显示。
(function () {
  const $ = (id) => document.getElementById(id);
  const bridge = window.shellBridge;
  const output = $('log-output');
  const status = $('status');
  const sourceSelect = $('source');
  const autoRefresh = $('auto-refresh');
  const exportButton = $('export');
  const revealButton = $('reveal');
  let source = 'app';
  let loading = false;
  let copying = false;
  let exporting = false;
  let revealing = false;
  let disposed = false;
  let firstRead = true;
  let text = '';
  let requestId = 0;
  let timer;
  let noticeUntil = 0;

  function setStatus(message, error = false, hold = false) {
    status.textContent = message;
    status.dataset.error = String(error);
    noticeUntil = hold ? Date.now() + 5000 : 0;
  }

  async function refresh(manual = false) {
    if (disposed || loading || !bridge?.logs?.read) return;
    const id = ++requestId;
    loading = true;
    $('refresh').disabled = true;
    if (manual || firstRead) setStatus('读取中…');
    try {
      const result = await bridge.logs.read(source);
      if (disposed || id !== requestId) return;
      if (typeof result?.text !== 'string') throw new Error('日志内容读取异常');
      // 更新文本前计算，读取期间用户往上滚动也不会被拉回底部。
      const followTail = firstRead || output.scrollHeight - output.clientHeight - output.scrollTop <= 32;
      const previousTop = output.scrollTop;
      if (firstRead || text !== result.text) {
        text = result.text;
        output.textContent = text || '暂无日志';
        output.dataset.empty = String(!text);
        output.scrollTop = followTail ? output.scrollHeight : previousTop;
      }
      firstRead = false;
      $('copy').disabled = copying || !text;
      exportButton.disabled = exporting || !text;
      $('truncation').hidden = result.truncated !== true;
      if (manual || Date.now() >= noticeUntil) {
        const time = new Date().toLocaleTimeString('zh-CN', { hour12: false });
        setStatus(text ? '已刷新 · ' + time : '暂无日志');
      }
    } catch (error) {
      if (!disposed && id === requestId) {
        setStatus('读取失败：' + (error?.message || error), true);
        if (firstRead) output.textContent = '暂无可显示的日志，请重试。';
      }
    } finally {
      if (id === requestId) {
        loading = false;
        if (!disposed) $('refresh').disabled = false;
      }
    }
  }

  function syncAutoRefresh() {
    clearInterval(timer);
    timer = undefined;
    if (autoRefresh.checked && !disposed) timer = setInterval(() => void refresh(), 2000);
  }

  $('refresh').addEventListener('click', () => void refresh(true));
  autoRefresh.addEventListener('change', syncAutoRefresh);
  sourceSelect.addEventListener('change', () => {
    source = sourceSelect.value === 'desktop' ? 'desktop' : 'app';
    ++requestId;
    loading = false;
    firstRead = true;
    text = '';
    noticeUntil = 0;
    output.textContent = '正在读取日志…';
    output.dataset.empty = 'true';
    output.scrollTop = 0;
    $('truncation').hidden = true;
    $('copy').disabled = true;
    exportButton.disabled = true;
    void refresh(true);
  });
  $('copy').addEventListener('click', async () => {
    if (copying || !text || !bridge?.logs?.copy) return;
    const copiedSource = source;
    copying = true;
    $('copy').disabled = true;
    try {
      await bridge.logs.copy(text);
      if (!disposed && source === copiedSource) setStatus('已复制当前显示的日志', false, true);
    } catch (error) {
      if (!disposed && source === copiedSource) setStatus('复制失败：' + (error?.message || error), true, true);
    } finally {
      copying = false;
      if (!disposed) $('copy').disabled = !text;
    }
  });
  exportButton.addEventListener('click', async () => {
    if (exporting || !text || !bridge?.logs?.export) return;
    const exportedSource = source;
    exporting = true;
    exportButton.disabled = true;
    try {
      const result = await bridge.logs.export(exportedSource, text);
      if (disposed || source !== exportedSource) return;
      if (result?.canceled) setStatus('已取消导出', false, true);
      else if (result?.written === false) setStatus('日志还没有内容，暂无可导出的文件', true, true);
      else setStatus('已导出日志 · ' + (result?.path || ''), false, true);
    } catch (error) {
      if (!disposed && source === exportedSource) setStatus('导出失败：' + (error?.message || error), true, true);
    } finally {
      exporting = false;
      if (!disposed) exportButton.disabled = !text;
    }
  });
  revealButton.addEventListener('click', async () => {
    if (revealing || !bridge?.logs?.reveal) return;
    const revealedSource = source;
    revealing = true;
    revealButton.disabled = true;
    try {
      const result = await bridge.logs.reveal(revealedSource);
      if (disposed || source !== revealedSource) return;
      setStatus(result?.kind === 'file' ? '已在文件管理器中定位日志文件' : '日志文件尚未生成，已打开日志目录', false, true);
    } catch (error) {
      if (!disposed && source === revealedSource) setStatus('打开日志失败：' + (error?.message || error), true, true);
    } finally {
      revealing = false;
      if (!disposed) revealButton.disabled = false;
    }
  });
  $('close').addEventListener('click', () => bridge?.close ? bridge.close() : window.close());
  window.addEventListener('unload', () => { disposed = true; clearInterval(timer); }, { once: true });

  if (!bridge?.logs?.read || !bridge?.logs?.copy || !bridge?.logs?.export || !bridge?.logs?.reveal) {
    setStatus('日志接口不可用，请重新打开应用。', true);
    output.textContent = '暂无可显示的日志';
    $('refresh').disabled = true;
    $('copy').disabled = true;
    exportButton.disabled = true;
    revealButton.disabled = true;
    sourceSelect.disabled = true;
    autoRefresh.disabled = true;
    return;
  }
  syncAutoRefresh();
  void refresh();
})();
