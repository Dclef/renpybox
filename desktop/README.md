# RenpyBox desktop shell

RenpyBox 的桌面壳：**Electron 主进程 + Python sidecar（FastAPI + WebSocket）+ React/TS 主 UI**。
M0 的性能验证已结束，当前正在迁移主界面；旧性能门禁与 Vue 对照版已移除。**界面能够运行不代表功能迁移已经完成。**

## 当前进度（2026-10-10）

翻译主流程、项目设置与常规设置已接入；新增接口管理读写与测试、工作台编辑与草稿应用、平行校对编辑与批量替换、术语表/禁翻表（与旧 Qt 单元格编辑及 Excel/统计/扫描/翻译对齐，无侧栏）、静态提示词预览、Agent 助手、应用更新（复用 VersionManager）。AI 校对与润色支持选中条目、确认、取消及任务结果查看；本轮接入一键翻译、应用翻译到游戏、解包/反编译/打包，以及资源组三项：终极结构导出、批量修正、姓名提取；其余工具仍有迁移缺口。审计缺口见 [UI 迁移检查记录](UI-REVIEW-2026-10-08.md)；2026-10-09 接到壳上的行为和未完成项见 [补充说明](SUPPLEMENT-2026-10-09.md)；表格组件见 [Table UI 设计规范](TABLE-UI-SPEC.md)；词库对等见 [lexicon-qt-parity](../docs/internal/2026-10-09/dev/lexicon-qt-parity.md)。

开发时网页与桌面共用同一 Python sidecar：`npm run dev` / `npm run dev:web` 都由脚本托管后端；关掉 Electron 不会杀死后端，只有 Ctrl+C 结束开发脚本时才停。

下方的 PyQt 尺寸表是迁移时的历史对照记录。当前外壳使用 38px 标题栏、256px 展开导航、56px 折叠导航；视觉调整以现有 React/CSS 实现为准。

2026-10-09 的 UI 调整按翻译工作区、项目配置、工具与资产、翻译设置组织导航；应用设置、主题和诊断入口固定在侧栏底部。标题栏项目入口与连接状态跨页面保留，项目入口继续保护未保存编辑。

侧栏恢复为四段，校对台与词表只从工具箱进入，并补上打开与保存文件对话框以及任务进度推送。

翻译页展示实际输入目录、语言方向和当前接口，点击目录或接口可进入对应设置；输入目录独立于 Ren'Py 项目身份展示，不修改用户选择的路径。输入/输出 Token 与线程池独立显示；进度环与吞吐面板左右排列，下方为翻译流水；新任务、可继续、有失败项及已完成状态分别显示，明暗主题与减少动态效果设置共用同一套样式。自检覆盖这些入口、状态和五种窗口宽度。

### 工作台补齐（2026-10-10）

继续使用 Mantine。工作台概览新增“扫描角色”和“生成草稿”：前者读取项目文本，不调用 AI；后者可按当前翻译范围或完整游戏生成世界观、角色或全部资料，开始前确认当前接口与 Token 消耗。结果先进入可读的待审核草稿，确认应用后才更新正式资料。

任务支持阶段反馈、取消和切页返回恢复；取消后等待当前请求结束再释放引擎。手工编辑、外部资料版本和项目切换分别保护。角色搜索支持名称、译名、别名与关键词。

本次提交的隔离副本通过 53 项聚焦后端测试、TypeScript 检查和 65 条受控界面断言，五种窗口宽度共 70 处布局检查无越界。工具箱其余执行页和真实游戏全流程仍未全部迁移；未执行 build 或收费模型请求。

## 仿的是什么

| DeepSeek Harness 的做法 | 本工程 |
|---|---|
| sidecar 探活后才开窗 | `main/sidecar.js` 轮询 `/health`，就绪才 `show()` |
| 多 preload 按窗口拆分 | `preload-main.cjs`（主窗口）/ `preload-shell.cjs`（欢迎页、更新弹窗） |
| 轻量壳页用 vanilla，不背框架 | `shell/welcome.*`、`shell/update-dialog.*` 纯手写 |
| `sandbox` + `contextIsolation` + 严格 CSP | `main/main.js` 统一 `webPreferences`，HTML 内联 CSP |
| `ws` 单连接通信 | `renderer/src/useSidecarEvents.ts`：全应用一条 WS，事件流与快照共用 |
| cordis 式注册表 | `renderer/src/nav.ts` + `renderer/src/tools.ts` 镜像 Python 侧的 `AppFluentWindow.add_pages()` 与 `ToolRegistry.TOOL_SPECS` |

## 故意不抄的两条

1. **主 UI 不做远程 `loadURL`** —— RenpyBox 必须离线可用。dev 走本地 vite，生产走 `loadFile(dist/index.html)`。
2. **sidecar 不用 Node** —— Ren'Py 生态（`unrpa`/`opencc`/`tiktoken`/rpyc 反编译）在 Node 无对应物，所以 `module/` 与 `base/` 原样搬进 Python sidecar。

## 目录

```
desktop/
├── main/
│   ├── main.js            主进程：无边框窗口（1280x800）/ 窗口控制 IPC / 壳入口 / sidecar 守护
│   ├── sidecar.js         Python sidecar 拉起、探活、崩溃重启、进程树清理
│   ├── preload-main.cjs   主窗口 preload（openShell / close / minimize / toggleMaximize / onMaximizeChange）
│   └── preload-shell.cjs  壳窗口 preload
├── shell/                 vanilla 壳页面（欢迎 / 更新弹窗）
├── sidecar/
│   ├── main.py            只做一件事：把 renpybox.api.app:app 挂上 CORS 后用 uvicorn 跑起来
│   └── requirements.txt
├── scripts/dev.mjs        一条命令拉起 vite + Electron（npm run dev）
├── renderer/              React + TS 主 UI（产品界面）
│   ├── src/
│   │   ├── App.tsx        外壳：38px 标题栏 + 导航（256 展开 / 56 折叠）+ Ant Design 通知
│   │   ├── nav.ts         导航结构，镜像 AppFluentWindow.add_pages()
│   │   ├── tools.ts       27 个工具，镜像 ToolRegistry.TOOL_SPECS
│   │   ├── icons.tsx      lucide 导航图标与自绘窗口按钮
│   │   ├── icons/toolbox/ 工具箱 25 个 Lucide SVG，直接复用项目自带资源
│   │   ├── Waveform.tsx       吞吐波形，复用旧版绘制口径
│   │   ├── settingsSchema.ts  设置页字段 schema（按 Config 真实类型分派）
│   │   ├── useAppState.ts 唯一状态源：配置乐观更新 + 事件分发 + toast
│   │   ├── useSidecarEvents.ts 全应用单条 WS（指数退避重连）
│   │   ├── theme.ts       灰阶与强调色的语义令牌
│   │   ├── antdTheme.ts   Ant Design ConfigProvider tokens 与 --rb-* 变量
│   │   ├── styles/        分层样式（legacy 尚未完全清理）
│   │   ├── components/    DataSheet 与工具页框架
│   │   ├── preload.d.ts   window.renpy 桥接类型
│   │   ├── pages/         翻译 / 项目 / 工具箱 / 工作台 / 设置
│   │   └── ui.tsx         Ant Design 设置控件 / PageHeader / Dialog / Banner 等
│   └── index.html         含严格 CSP（connect-src 指向 sidecar 端口）
├── PERF-REPORT.md         M0 的 React vs Vue 实测报告（保留作虚拟化决策依据）
└── run-dev.sh / run-dev-api.sh / run-dev.cmd
```

## 跑起来

```bash
cd renpybox/desktop
npm ci --include=dev
npm run dev            # vite + Electron + sidecar（scripts/dev.mjs 托管后端）
npm run dev:web        # 仅 vite + sidecar，浏览器打开；可与桌面端同时用
```

若提示缺少 Vite，请在 `desktop` 目录重新执行 `npm ci --include=dev`。开发启动器会先检查依赖，再启动后端；Electron 运行时缺失时可执行 `node node_modules/electron/install.js` 重试。

`npm run dev` 一条命令就够，不需要另开终端跑 vite：dev 模式下窗口从 vite dev server
加载渲染端，只起 Electron 会拿到 `ERR_CONNECTION_REFUSED`。端口统一由
`RENPYBOX_WEB_PORT`（默认 5173）和 `RENPYBOX_SIDECAR_PORT`（默认 9712）传入，
vite、`main.js` 与 `index.html` 的 CSP 三处必须一致。

关掉桌面窗口后，vite 与 sidecar 仍保持运行，可继续用浏览器，或再执行
`npm run dev:shell` 接回同一后端（复用已运行的进程，不会互杀）。

其它脚本：`npm run sidecar`（只起后端）、`npm run dev:shell`（只起 Electron）、
`npm run dev:renderer`（只起 vite，不带后端）、`npm run typecheck`、`npm run build:renderer`。

> sidecar 端口同时只能有一个持有者。若启动时报 `Errno 10048 … 9712`，说明已有
> 后端占着端口；直接复用即可，不必再起第二份。由本进程 spawn 的后端才会在退出时清理。

想手动联调真实接口（先验 `/health` 与术语表路由，再起窗口）：

```bash
./run-dev-api.sh        # 等价于 run-dev.cmd（Windows 下双击）
```

`sidecar/main.py` 需要能 import 到 `renpybox/`（脚本自动把仓库根加入 `sys.path`）。
主进程的解释器优先级：`RENPYBOX_PYTHON` → `RENPYBOX_PROJECT_PYTHON`（未设时使用本机 Python 3.10 默认路径）→ 系统 `python`。

## 迁移时的设计参考

- **主题**沿用 `widget/ThemeTokens.py` 的语义令牌命名，渲染端在 `theme.ts` 定义独立配色并映射成 `--rb-*` CSS 变量，组件不写死颜色。切换主题只改 `config.theme` 一个字段（`GET/PATCH /api/settings`）。
- **文案**来自 `renpybox/module/Localizer/LocalizerZH.py`，导航项、KPI、流水表头的文字与该文件同名条目逐字一致（含 `{PERCENT:.1f}%` 这类占位符的格式）；不新造术语。
- **操作接真实业务**：接口、工作台、校对和词库均复用 Python 业务层；尚未迁移的工具明确说明使用条件与限制。
- **图标**：工具箱复用项目自带 Lucide SVG；导航和命令栏用 lucide-react；窗口按钮保留现有自绘实现。
- **设计口径**：使用 Ant Design 6，主色为 Ant 默认蓝（亮色 #1677ff，暗色由 darkAlgorithm 推导为 #1668dc），侧栏选中、表格选中行、进度与按钮共用同一组 token，以旧 Qt 的页面组织和操作流程为基准。侧栏四段，工具箱分组卡片；翻译页保留进度环和吞吐图；校对与词表使用 Ant Table（virtual + scroll.x/y）。中性色由 theme.ts 管理，主色系由 antdTheme.ts 从 Ant 实际 design token 派生到 `--rb-accent*`。

## 原 Qt 外壳几何对照（历史记录）

PyQt 侧**没有可读的 QSS** —— qfluentwidgets 把样式编译进 6.4MB 的 `_rc/resource.py`（Qt 资源系统），
`qfluentwidgets._rc.qss` 不存在，`FluentTheme` 也没从包里导出。所以唯一权威依据是**控件几何实测**：
`QT_QPA_PLATFORM=offscreen` 起真 `QApplication` → `app.setStyleSheet(get_current_stylesheet())` →
`AppFluentWindow()` → `resize(1280, 800)` → `show()` + 多轮 `processEvents()`，再遍历 `findChildren`
读 `geometry()`、`font()` 与 `objectName()`。

> 实测陷阱：`_configure_navigation` 在 `__init__` 里就按当时的窗口宽度决定了导航是否展开，
> `resize()` 之后必须再显式 `nav.expand(useAni=False)` 才会拿到 256 展开态（否则只会读到 48）。

以下是迁移初期在 1280×800 窗口下采集的 Qt 几何数据；React 后续调整不要求逐像素一致：

| 位置 | PyQt 实测 | 渲染端 |
|---|---|---|
| `FluentTitleBar` | 38px 高、横跨整窗；chrome 底 + 1px divider；标题 12px/600 | `.titlebar`（`grid-template-rows: 38px 1fr`） |
| 导航宽度 | 256 展开 / 48 折叠，`NAVIGATION_EXPAND_BREAKPOINT = 1000` | `--rb-nav-width: 256px` + `@media (max-width: 999px)` |
| `stackedWidget` | x=256, y=38 | `.content` 落在 (256, 38) |
| `NavigationTreeWidget` | 246x36 @ x=4，纵向节距 40（36 + 4） | `.nav-item` 36 高 / 左 4 右 6 外边距 / 父级 `gap: 4px` |
| `NavigationSeparator` | 256x3、全宽无左右边距 | `.nav-divider` 3px |
| `NavigationIndicator` | 3x16 选中指示条（不是整块高亮） | `.nav-item[aria-current='page']::before` |
| 导航项内容 | 单行「图标 + 文字」；**没有**搜索框 / 品牌块 / 分组标题 / 第二行描述 | 一致（`nav.menuButton` 本来就是 `None`） |
| 页面头部 | `translationPageHeader` @ (24,18)，右侧按钮 32 高 | `.translation-header`；滚动区内边距 `18px 24px 12px` |
| KPI 条 | `translationKpiStrip` 高 88；卡内边距 (14,11,14,10)、图标盒 38x38、值 20px 粗体 | `.kpi-card` / `.kpi-icon` / `.kpi-value` |
| 仪表盘网格 | 280x248 + 889x248（间距 14），第二行全宽 1183x261 | `.dashboard-grid` `280px 1fr` / 行 `248px 261px` / `gap: 14px` |
| 进度环 | `ProgressRing` 122x122、`setStrokeWidth(8)`、range 0..10000 | `ProgressRing.tsx` 默认 `size=122 / stroke=8 / max=10000` |
| 波形 | `WaveformWidget` 50x20 柱、`setFixedHeight(160)` | `Waveform.tsx` `columns=50 / height=160` + CSS `flex: 0 0 160px` |
| 命令栏 | `CommandBarCard` 高 58，**在滚动区之外**钉在页面底部；`CommandBar` @ (15,12) | `.translation-footer` + `.translation-scroll` 两层结构 |
| 命令按钮 | `CommandButton` 高 34、`CommandSeparator` 9x34 | `.translation-footer .btn` 34 高、`.command-separator` 1x20 + 4px 外边距 |

### 设置类页面（项目设置 / 基础设置 / 专家设置 / 应用设置）

这四页是同一个骨架：页头在外、滚动区在内，**一个字段一张卡**（不是把整页塞进一张大卡）。
实测（`frontend/Project/ProjectPage.py`、`frontend/Setting/BasicSettingsPage.py`、
`frontend/Setting/ExpertSettingsPage.py`、`frontend/AppSettingsPage.py`）：

| 位置 | PyQt 实测 | 渲染端 |
|---|---|---|
| 页头 | 975x36 @ (24,24)：`TitleLabel` 18px DemiBold + `CaptionLabel` 12px @ y=20 | `.settings-header`（18px/600 + 12px，gap 2） |
| 滚动区 | 975x669 @ (24,68) | `.settings-scroll` |
| 卡骨架 | 内容撑开高度：1 行说明 66/67、2 行 82；`margins(16,16,16,16)` + 1px 边框 → 缩进 17 | `.setting-card`（`min-height: 66px` / `padding: 16px` / 说明 `line-height: 14px` 跟着换行长高） |
| 卡内排版 | 标题 fpx=14 DemiBold 在 y=17、说明 fpx=12 在 y=37（间距 6） | `.setting-card-title` / `.setting-card-description`（gap 6） |
| 卡间距 | **两档**：项目页 74 = 66+8（`form.setSpacing(8)`）；设置三页 73/88 = +6（Qt 默认 6） | `.setting-card-list` gap 8 / `.settings-card-list` gap 6 |
| 右侧控件 | `SpinBox` 206x33、`SwitchButton` 56x22（`Indicator` 42x22）、`ComboBox` 72~100x27、`LineEdit` 256x33、`PushButton` 78x27 | `.setting-card-control` 下按控件分别定尺寸 |
| 均衡吞吐 | 是**普通 `PushButton`** 975x27 @ y=395，夹在 `max_output_tokens` 与 `request_timeout` 之间，不是卡片 | `.settings-solo-button` |
| 关于与更新 | `GroupCard` 975x220（标题/说明 + 内容行） | `.group-card` / `.group-row` |

> 已知 2px 偏差：1 行说明的卡渲染成 68 而不是 66。要让 1 行/2 行两条都对上，
> 需要 1 行时 `line-height: 12`、2 行时 `14` —— CSS 行盒没法按行数分支，
> 这里选保住「2 行 = 82」的准确（换行卡占多数）。

### Ren'Py 工具箱

| 位置 | PyQt 实测 | 渲染端 |
|---|---|---|
| 页头 | 左侧文字块 639x33 @ (24,24)；**右侧 `SearchLineEdit` 320x33**（placeholder「搜索工具」） | `.toolbox-header` + `.toolbox-search`（320x33）—— 搜索框属于这一页，**不在导航栏** |
| 分组 | 节头 975x14（组名 fpx=14 + 计数 `CaptionLabel` 12px 右对齐）；节头到卡片 20 | `.tool-group` gap 20 / `.tool-group-header` |
| 卡片 | `ItemCard` 316x132、3 列；`margins(14,12,14,12)` | `.tool-grid` `minmax(300px,1fr)` gap 14 / `.tool-card` 132 高 |
| 卡内 | 头部 286x30 @ (15,13)：序号码 22x22（fpx=11）+ 图标 20x20（间距 9）+ 标题 `SubtitleLabel` 14px **粗体**（`RenpyToolboxPage.py:236-239`）+ 右侧箭头 36x30 | `.tool-card-head` / `.tool-card-step` / `.tool-card-icon` / `.tool-card-go` |

### 项目设置页

项目页顶部单独显示已绑定的工程根、game 与 tl；下面 6 张卡顺序同 `frontend/Project/ProjectPage.py:81-86`：原文语言 → 译文语言 → 输入文件夹 →
输出文件夹 → 任务完成时打开输出文件夹 → 使用繁体输出中文。只选不含 `game/` 的目录时只当作输入目录，不会改写工程身份。

**真实 `ProjectPage` 没有「工程路径」卡片** —— 项目身份是选输入目录时由
`_sync_renpy_paths_from_selection()` 顺带绑定的。渲染端为此新增
`POST /api/project/resolve`（`renpybox/api/routes/project.py`）：只有目录本身含 Ren'Py
结构（`looks_like_renpy_path` + `RenpyProjectPaths.from_path`）才同步项目身份，否则 **409**，
调用方静默忽略、只把它当 `input_folder`。理由：用户自建的翻译目录被当成项目根，会让
`renpy_tl_folder` 指向并不存在的 `game/tl/<lang>`，项目设置反而变错。

目录选择与「打开目录」由主进程提供（渲染端没有 `fs`/`dialog`）：
`dialog:pick-folder`（`dialog.showOpenDialog({properties:['openDirectory']})`）与
`shell:open-path`（`shell.openPath`），经 `preload-main.cjs` 暴露为
`window.renpy.pickFolder` / `window.renpy.openPath`。

### 渲染端实测方法（CDP）

`Browser.setWindowBounds` **不会**真的缩放窗口（`innerWidth` 仍是 1282），必须用
`Emulation.setDeviceMetricsOverride({width: 1280, height: 800, deviceScaleFactor: 1, mobile: false})`
才能测折叠态；否则测出来的还是展开态 —— 一个前提悄悄失效的测试比没有测试更糟。

### 角色 / 世界观工作台

`workbenchWorkspace` 是 **QVBoxLayout、margins 0、spacing 0**，四段直接相接（实测）：

| 段 | PyQt 实测 | 渲染端 |
|---|---|---|
| 页头 | 1023x58 @ (0,0)；layout margins (24,18,24,8) spacing 16；左 693x32 = TitleLabel 18px + CaptionLabel 12px @ y=20；右 `导出项目资料` 134x32 + `应用全部草稿` 124x32（都 `setFixedHeight(32)`） | `.workbench-header` |
| Tab 条 | 1023x40 @ (0,58)；margins (24,0,24,12) spacing 8；四个 `QuietPillButton` **54x28 / 68x27 / 68x27 / 96x27** | `.workbench-tabs` + `.quiet-pill`（宽度写实测值） |
| 状态条 | 1023x47 @ (0,98)，objectName `workbenchStatusSurface`；margins (24,7,24,10) spacing 4；`BodyLabel` 975x14 + `CaptionLabel` 975x12 | `.workbench-status` |
| 内容 | `QStackedWidget` 1023x616 @ (0,145) | `.workbench-body`（占满剩余高度） |

以上表格记录初期 Qt 几何。当前工作台支持世界观和角色编辑、资料导出、草稿应用以及真实提示词命中预览，使用项目资产仓库保存。

接口管理支持 CRUD、激活与测试；翻译提示支持静态预览；Agent 仍待迁移。当前功能边界和验证方法以 [UI 迁移检查记录](UI-REVIEW-2026-10-08.md) 为准。

## 不卡的四条铁律

1. **渲染进程只渲染** —— IO、解析、翻译全在 Python sidecar
2. **数据流式到达** —— 解析器生成器化 + 分批推送，不再「全量加载完再显示」
3. **长列表限制渲染量** —— 校对每页 25 / 50 / 100 条、词库每页 40 条；侧边栏和编辑器只渲染当前页面
4. **UI 线程 16ms 预算** —— 超过就离开主线程；批次进缓冲区，由 `requestAnimationFrame` 统一 flush，绝不在每条消息到达时 `setState`

## CSP 与端口

`renderer/index.html` 的 CSP `connect-src` 必须与 `RENPYBOX_SIDECAR_PORT`（默认 **9712**）一致。
sidecar 端口被写死进构建产物，改端口要同时改 `index.html` 与 `main/sidecar.js` 的默认值。

## UI 集成自检

先启动 `npm run dev:renderer`，再以 Electron 主进程运行 `scripts/check-ui.cjs`（启动前清除 `ELECTRON_RUN_AS_NODE`）。可用 `RENPYBOX_UI_URL` 改开发服务器地址，`RENPYBOX_UI_CAPTURE_DIR` 指定截图与日志目录。自检使用受控 HTTP/WS 快照，不读写真实项目；实际持久化由 `tests/api/test_platforms.py`、`test_workbench.py`、`test_proofreading.py` 与 `test_prompt_preview.py` 的临时项目测试覆盖。

## 校对与润色操作

从工具箱打开“检查与润色”，勾选当前页中的译文，再点击“AI 校对”或“AI 润色”。确认框说明本次范围和 Token 消耗；只有确认后才请求当前接口。只处理符合条件的条目，其余由后端返回跳过数量。

处理期间缓存只读，可以取消；完成后自动刷新译文。“质量报告”同时显示翻译失败/降级/行数异常摘要与 AI 校对/润色处理记录，不把二者混为一谈。

表格单击选行，Ctrl 增减选择、Shift 连选；双击原文/译文或按 F2 打开双语编辑弹窗，Ctrl+Enter 保存。右键在鼠标旁弹出；可重译选中行、复制原文/译文/双语、定位译文上下文。达到重试阈值时可人工确认译文无误。复制双语为制表符分隔文本，可粘贴到 Excel；不提供公式、填充柄等电子表格功能。

“导出译文”先保存缓存，再按原格式写回当前实际输出目录中的全部译文，不受页面筛选限制。重译会消耗当前接口额度；失败行保留原译文，取消后等待已发出的请求结束并保存成功结果。

校对读取复用当前项目只读快照；缓存文件或设置变化自动失效。普通翻页只检查当前页，首次启用问题筛选需要扫描候选条目。

## 界面检查

已有开发服务器时，以 Electron 运行 scripts/check-ui.cjs；HTTP/WS 使用受控数据，测试不调用付费接口。RENPYBOX_UI_CAPTURE_ALL=1 会在检查通过后额外生成 14 个页面各两种主题的截图。此检查覆盖五种宽度，不替代真实游戏和安装包验收。


## 一键翻译与解包（2026-10-10）

从工具箱进入“一键翻译”，选择游戏根目录或 game 目录、目标语言目录名（例如 chinese），检测后点击“开始准备”。确认后依次检测、按需解包和反编译、抽取文本并配置翻译路径。默认启用增量保护；已有增量输出会先备份，准备结束不会自动调用翻译接口。

准备完成后点击“打开翻译页”，使用现有的开始、继续或停止操作；译文生成后返回一键翻译，或从工具箱进入“应用翻译到游戏”，确认写回。全量应用覆盖对应 TL 文件，增量应用合并后才清理增量目录；应用路径由后端按当前项目和语言推导，不能指定任意目录用于清理。

“解包/打包”页面支持解包 RPA、反编译 RPYC、打包和分卷。解包保留源 RPA，反编译保留 RPYC；覆盖已有 RPY 与打包写入均有确认。目录可手填，Electron 中还可调用系统目录/保存对话框。

切页返回会恢复任务状态。取消后会等待当前后台操作结束再释放引擎；正在进行的文件应用会完成收尾，不承诺撤销已完成的写入。页面只能恢复当前 sidecar 进程中的任务，重启后端不会续跑旧任务。

### API 约定

所有写操作返回 `{ "job": ... }`，通过 `GET /api/jobs/{id}` 查看状态，`POST /api/jobs/{id}/cancel` 请求协作取消。任务结果中的 `worker_active=false` 表示工作线程已结束；`cancel_requested=true` 本身不代表已经停止。业务失败写入 `job.error`，项目过期或引擎忙返回 409，非法路径和未确认操作返回 400。

| 接口 | 请求与结果 |
|---|---|
| `GET /api/onekey` | 当前项目最近一次准备或应用任务 |
| `POST /api/onekey/detect` | `game_dir`、`language`，可传 `project_key` 校验项目；返回脚本状态 |
| `POST /api/onekey/prepare` | 上述字段加 `incremental`、`confirm_write=true`；可指定项目根目录内的 `exe_path`，否则自动查找游戏程序 |
| `POST /api/onekey/apply` | 上述项目字段加 `incremental`、`confirm=true`；可选路径字段仅用于核对，必须匹配派生目录 |
| `GET /api/archive` | 当前项目最近一次解包、反编译或打包任务；未绑定项目时同样可用 |
| `POST /api/archive/unpack` | `path`、`direct`、`script_only`；不删除源档 |
| `POST /api/archive/decompile` | `path`、`overwrite`、`use_unren`；覆盖时要求 `confirm_overwrite=true` |
| `POST /api/archive/pack` | `source_dir`、`output_file`、`max_part_size`（默认 `1G`，空值不分卷）、`confirm=true` |
| `GET /api/asset-suite/status` | 当前项目最近一次结构/Emoji/批量修正/姓名提取任务 |
| `POST /api/asset-suite/structure` | `path`、`language`、`mode`（1/2/3）、`use_official`、`exe_path`、`gen_emoji`、`confirm_overwrite`；覆盖已有 `translate_output` 前需确认 |
| `POST /api/asset-suite/emoji` | `path`、`target_dir`、`mode=prepare\|restore`、`confirm=true`；先备份再原地替换 |
| `POST /api/asset-suite/corrections/export` | `input_dir`、`output_dir`、`confirm_overwrite`；生成 `批量修正.xlsx` |
| `POST /api/asset-suite/corrections/apply` | `workbook`、`translation_root`、`confirm=true`；原地注入，路径不得越界 |
| `POST /api/asset-suite/names/extract` | `input_dir`；返回 `entries=[{src,context}]` |
| `POST /api/asset-suite/names/export` | `entries`、`format=txt\|json`；可选 `output_file`+`confirm_overwrite`，否则返回可下载正文 |

共享业务位于 `module/OneKey/flow.py`、`module/Tool/ArchiveOps.py` 与 `module/Tool/AssetSuiteOps.py`（结构导出复用 `HakimiSuiteRunner` / `EmojiReplacer`）；旧 Qt 页面继续调用相同逻辑，desktop 不导入 Qt 页面。翻译请求仍通过已有 `/api/translation` 接口执行。

验证覆盖临时项目真实抽取与应用、RPA 打包解包、结构/Emoji/批量修正/姓名提取、项目切换、增量目录保护、取消和界面交互；不等同于真实游戏运行、官方抽取真机、收费模型或打包安装版验收。
