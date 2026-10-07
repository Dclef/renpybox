// 更新弹窗：演示进度条渲染。真实增量更新逻辑留在 Python sidecar。
(function () {
  const fill = document.getElementById('fill');
  const pct = document.getElementById('pct');
  document.getElementById('from').textContent = '当前版本';

  let progress = 0;
  const timer = setInterval(() => {
    progress = Math.min(100, progress + 7);
    fill.style.width = progress + '%';
    pct.textContent = String(Math.round(progress));
    if (progress >= 100) clearInterval(timer);
  }, 220);

  document.getElementById('later').addEventListener('click', () => window.close());
  document.getElementById('now').addEventListener('click', () => {
    clearInterval(timer);
    fill.style.width = '100%';
    pct.textContent = '已下载，等待重启安装';
  });
})();