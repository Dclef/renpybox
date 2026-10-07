# RenpyBox desktop shell（M0 spike）

按 **DeepSeek Harness（`@deepseek-ai/dsh-desktop`）的壳工程模式** 重构的桌面壳验证工程。

## 仿的是什么

| DeepSeek 的做法 | 本工程 |
|---|---|
| sidecar 探活后才开窗 | `main/sidecar.js` 轮询 `/health`，就绪才 `show()` |
| 多 preload 按窗口拆分 | `preload-main.cjs`（主窗口）/ `preload-shell.cjs`（欢迎页、更新弹窗） |
| 轻量壳页用 vanilla，不背框架 | `shell/welcome.*`、`shell/update-dialog.*` 纯手写 |
| `sandbox` + `contextIsolation` + 严格 CSP | `main/main.js` 统一 `webPreferences`，HTML 内联 CSP |
| `ws` 单连接通信 | `renderer/src/useRowsSocket.ts`：数据流 + 任务进度 + 控制指令共用一条 WS |
| 自带 woff2 字体 | spike 阶段沿用系统字体，M2 再补 |

## 故意不抄的两条

1. **主 UI 不做远程 `loadURL`** —— RenpyBox 必须离线可用。
2. **sidecar 不用 Node** —— Ren'Py 生态（`unrpa`/`opencc`/`tiktoken`/rpyc 反编译）在 Node 无对应物，M1 会把 `module/` 与 `base/` 原样搬进 Python sidecar。

## 目录

```
desktop/
├── main/
│   ├── main.js            主进程：窗口 / 菜单 / 快捷键 / sidecar 守护
│   ├── sidecar.js         Python sidecar 拉起、探活、崩溃重启、进程树清理
│   ├── preload-main.cjs   主窗口 preload（最小能力暴露）
│   ├── preload-shell.cjs  壳窗口 preload
│   └── perf-gate.js       无头性能门禁，输出 perf-result.json
├── shell/                 vanilla 壳页面（欢迎 / 更新弹窗）
├── sidecar/
│   ├── main.py            FastAPI + WebSocket，模拟 10 万行推送与高并发任务
│   └── requirements.txt
├── renderer/              React + TS 主 UI（**选定方案**）
├── renderer-vue/          Vue 对照版（同条件实测用，见 PERF-REPORT.md）
├── PERF-REPORT.md         React vs Vue 实测对比报告
├── run-spike.sh           一键：sidecar + vite + 门禁（React）
└── run-spike-vue.sh       同上（Vue 对照版）
```

## 实测结论

**选 React。** 10 万行滚动：React 59fps / 长任务 0，Vue 20fps / 长任务 24。
详细数据与踩坑记录见 [PERF-REPORT.md](./PERF-REPORT.md)。

## 跑起来

```bash
cd desktop

# 1) sidecar（Python）
"C:/Users/su/.workbuddy/binaries/python/versions/3.13.12/python.exe" -m venv sidecar/.venv
sidecar/.venv/Scripts/python.exe -m pip install -r sidecar/requirements.txt
npm run sidecar

# 2) 渲染端
npm install
npm run dev:renderer

# 3) 壳
npm run dev
```

快捷键：`Ctrl+Shift+W` 开欢迎页，`Ctrl+Shift+U` 开更新弹窗（验证多 preload 拆分）。

## M0 门禁

```bash
npm run perf-gate      # 无头跑，写出 perf-result.json
```

| 指标 | 目标 |
|---|---|
| 冷启动到可交互 | < 1500ms |
| 10 万行首屏 | < 300ms |
| DOM 中实际渲染的行数 | < 60（证明虚拟化生效） |
| 滚动最低帧率 | >= 50fps |
| 高并发任务期间最低帧率 / 主线程延迟 | >= 50fps / < 50ms |

## 不卡的四条铁律（写进代码里了）

1. **渲染进程只渲染** —— IO、解析、翻译全在 Python sidecar
2. **数据流式到达** —— 解析器生成器化 + 分批推送，不再「全量加载完再显示」
3. **所有长列表虚拟化** —— `useVirtualizer` + 动态行高测量
4. **UI 线程 16ms 预算** —— 超过就离开主线程；批次进缓冲区，由 `requestAnimationFrame` 统一 flush，绝不在每条消息到达时 `setState`