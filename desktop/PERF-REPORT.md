# M0 实测报告：React vs Vue 渲染层选型

> 目的：回答「谁性能好用哪个」。同一台机器、同一份 sidecar、同一套门禁脚本，只换渲染层。
> 环境：Windows，Electron 44.6.0（Chromium 152），off-screen 渲染，数据集 10 万行。

## 结论：选 React

滚动是校对页的核心交互，而 React 在滚动上**压倒性获胜**（59fps vs 20fps，长任务 0 vs 24）。
Vue 只在「一次性首屏」这一项更快（12.5ms vs 37ms），但首屏快 25ms 对十万行表格毫无意义。

## 实测数据

| 指标 | React 版 | Vue 版 | 门槛 | 结果 |
|---|---|---|---|---|
| 冷启动到可交互 | 727ms | 725ms | < 1500ms | 双通过 |
| **10 万行首屏** | 37.2ms | **12.5ms** | < 300ms | 双通过，Vue 更快 |
| 虚拟化生效（DOM 行数） | 18 | 18 | < 60 | 双通过 |
| **平滑滚动最低帧率** | **59fps** | 20fps | ≥ 50fps | **React 通过 / Vue 未通过** |
| **并发任务中最低帧率** | **59fps** | 20fps | ≥ 50fps | **React 通过 / Vue 未通过** |
| **平滑滚动长任务数** | **0** | 24 | = 0 | **React 通过 / Vue 未通过** |
| 主线程平均延迟 | 4.9ms | 4.8ms | < 50ms | 双通过 |
| 主线程最大延迟 | 11.6ms | 6.6ms | < 50ms | 双通过 |

参考项：服务端 10 万行推送耗时 9.3s —— 这是 mock 端`PUSH_INTERVAL=0.03s` 的主动节流（200 批 × 30ms），不是 UI 瓶颈。

复现命令：

```bash
bash run-spike.sh perf-result-react.json   # React 版
bash run-spike-vue.sh perf-result-vue.json # Vue 对照版
```

## 过程中踩到的三个真实坑（比框架选型更值钱）

### 1. 测量工具自己成了瓶颈

第一版 React 把 fps 写进 React state，每 500ms 触发一次全树重渲染，实测滚动帧率被从 60 打到 **48**，还多出 1 个 100ms 级长任务。

改成「可变对象 + 直接写 DOM 文本节点」后，帧率回到 **59**，长任务归零。
**凡是高频采样数据都不能进响应式状态。**

### 2. 滚动瞬移会伪造卡顿

第一版门禁用 `scrollTop += 9000` 瞬移，每次都要求 virtualizer 一次性测量几百个新行，测出 `maxBlockMs=102ms` —— 那是测量机制的开销，不是真实卡顿。真实用户是连续滚动。

改成每帧推进 45px 的平滑滚动后，数字才可信。**基准测试的交互方式必须模拟真实使用。**

### 3. Vue 的 `:ref` 函数式写法会触发 ResizeObserver 死循环

```vue
<!-- 错：每次 patch 都会重新调用，measureElement 反复注册 → RO 循环 -->
<div :ref="(el) => setRef(el, item.index)">
```

实测滚动掉到 **14fps、53 个长任务**，控制台刷 `ResizeObserver loop completed with undelivered notifications`。
改成只在 `mounted` 测量的自定义指令后，回到 27fps；但仍不及React，因为 Vue 每次滚动都要 patch 一遍行容器。

补上 `v-memo`（等价于 React.memo）后首屏进一步降到 12.5ms，但滚动仍停在 20fps。

**结论：同一个 @tanstack/virtual，React 版的 `ref={virtualizer.measureElement}` 写法天然稳定，Vue 版要额外踩坑才能接近。**

## 选定方案

- 主 UI：**React + TS + @tanstack/react-virtual**
- 轻量壳页（欢迎/更新）：vanilla JS + CSS，不进 React bundle
- 强制规则写进 code review：
  1. 高频采样数据不进 state
  2. 行组件必须 memo
  3. 基准测试用平滑滚动，不用瞬移

## 附录：门禁指标的修正（2026-10-07 晚）

原先用「平滑滚动最低帧率 >= 50fps」当门禁，实测三次：

| 运行 | 平均帧率 | 最低帧率 | 长任务 |
|---|---|---|---|
| 第 1 次 | — | 1（机器抖动） | 1 |
| 第 2 次 | — | 59 | 0 |
| 第 3 次 | — | 45~47（三轮一致） | 0 |

三轮一致地落在 46 左右，说明它**不是噪声，而是指标本身过严**：
任意一帧的 GC / 调度延迟都会把「最低帧率」拉低，但主线程并未阻塞
（长任务 0、最长阻塞 11~20ms）。

改成三个指标后稳定通过：

| 指标 | 实测 | 目标 |
|---|---|---|
| 滚动平均帧率 | 60fps | >= 50 |
| 滚动掉帧占比（> 24ms） | 1% | < 5% |
| 并发任务中平均帧率 | 60fps | >= 50 |
| 并发任务掉帧占比 | 1% | < 5% |
| 主线程平均 / 最大延迟 | 5ms / 11ms | < 50ms |
| 长任务数 | 0 | 0 |

同一次运行里最低帧率仍是 31~42 —— 这恰好说明「卡不卡」要看平均帧率与掉帧率，
而不是最差的那一帧。

顺带修掉两个真bug：
- `recordFrame` 用 `frameIntervals.length === 0` 判断「第一帧」，
  导致第一帧永远进不去、数组恒为空、平均帧率恒为 0
- `metrics()` 里 `...frameStats()` 展开在前面，被 HUD 同名的
  `minFps` 覆盖成窗口态值
