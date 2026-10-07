// 壳页面脚本：只做展示，能力全部走 preload 暴露的 window.shellBridge
// 严格 CSP 下不允许 inline script，所以逻辑放在外链文件里。
(async function () {
  const $ = (id) => document.getElementById(id);
  const bridge = window.shellBridge;

  $('v-electron').textContent = bridge?.versions?.electron || '—';
  $('v-chrome').textContent = bridge?.versions?.chrome || '—';

  // 主窗口的 sidecar 信息通过 BroadcastChannel 转发过来（壳窗口不直接连 sidecar）
  const channel = 'BroadcastChannel' in window ? new BroadcastChannel('renpy-shell') : null;
  channel?.addEventListener('message', (e) => {
    if (e.data?.type === 'sidecar-info') render(e.data.payload);
  });
  channel?.postMessage({ type: 'shell-ready' });

  function render(info) {
    if (!info) return;
    const health = $('v-health');
    health.textContent = info.ok ? '就绪' : '未就绪';
    health.className = 'v ' + (info.ok ? 'ok' : 'bad');
    $('v-port').textContent = String(info.port ?? '—');
  }
})();