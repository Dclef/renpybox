// 日志只通过受限 preload 读取，并始终作为纯文本显示。
(function () {
  const $ = (id) => document.getElementById(id);
  const bridge = window.shellBridge;
  const output = $('log-output');
  const status = $('status');
  const sourceSelect = $('source');
  const autoRefresh = $('auto-refresh');
  let source = 'app';
  let loading = false;
  let copying = false;
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
  $('close').addEventListener('click', () => bridge?.close ? bridge.close() : window.close());
  window.addEventListener('unload', () => { disposed = true; clearInterval(timer); }, { once: true });

  if (!bridge?.logs?.read || !bridge?.logs?.copy) {
    setStatus('日志接口不可用，请重新打开应用。', true);
    output.textContent = '暂无可显示的日志';
    $('refresh').disabled = true;
    $('copy').disabled = true;
    sourceSelect.disabled = true;
    autoRefresh.disabled = true;
    return;
  }
  syncAutoRefresh();
  void refresh();
})();
