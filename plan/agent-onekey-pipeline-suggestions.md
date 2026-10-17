# Agent 一条龙（解包 → 反编译 → 提取 → 翻译 → 回填）内部建议

- 状态：待确认
- 日期：2026-10-17
- 目标分支：dev
- 关联方向：桌面端（Electron）为唯一前端，Qt5 版本功能冻结、后续移除

---

## 一、要解决的问题

用户诉求原话：**「我直接通过 agent 就能进行解包翻译一条龙，目前功能不完善」**。

拆开看是三个断层，不是一个：

| 断层 | 现象 | 证据 |
|---|---|---|
| 能力断层 | Agent 只有 7 个工具，覆盖到「解包 + 体检」，反编译/提取/翻译/回填全在门外 | `module/Agent/ToolDispatcher.py:59-152` |
| 交接断层 | 点「一键翻译」后由 Qt 向导接管，Agent 立刻失去控制权，看不到进度也无法收尾 | `frontend/Agent/AgentPage.py:2953` → `frontend/RenpyToolbox/OneKeyTranslatePage.py:2434` |
| 呈现断层 | 桌面端 Agent 页只有 7 个工具名和 4 条建议，没有任何流水线入口 | `desktop/renderer/src/pages/AgentPage.tsx:13-23` |

能力断层是根因；另外两层都要跟着补，否则「一条龙」仍然在向导页断掉。

---

## 二、现状盘点（实现级）

### 2.1 工具注册表

`module/Agent/ToolDispatcher.py:59-152` 现有 7 个工具：

`set_project`、`get_project_info`、`inspect_translation_project`、`list_rpa_files`、`scan_script_errors`、`unpack_rpa_files`、`optimize_old_new_translations`。

`ToolDef`（`module/Agent/types.py:42-50`）已支持 `requires_confirmation` 与 `requires_idle_engine`，但**没有**「后台任务 / 立即返回 job_id」的语义，所有 handler 都是同步阻塞的。

### 2.2 体检给出的下一步 vs 界面能做的事

`module/Agent/tools/inspection_tools.py:509-550` 的 `_next_action()` 会产出 10 种 action code：

`REPAIR_CACHE` / `CONTINUE_TRANSLATION` / `START_TRANSLATION` / `REVIEW_QUALITY` / `REFRESH_REPLACE_FALLBACK` / `REVIEW_TRANSLATION` / `UNPACK_RPA` / `DECOMPILE_SCRIPTS` / `CHECK_PROJECT_FILES` / `REVIEW_WORKBENCH`

`frontend/Agent/AgentPage.py:2726-2772` 只映射了 9 种，缺两种实质：

- `REFRESH_REPLACE_FALLBACK`：**完全没有按钮**。Agent 会告诉用户「需要刷新 replace 补丁」，却给不出入口，而 `optimize_old_new_translations` 工具本身是存在的。
- `DECOMPILE_SCRIPTS`：只跳到工具箱页（`frontend/Agent/AgentPage.py:2757-2761`），不能真正执行反编译。

### 2.3 一键流程的 UI 耦合

`frontend/RenpyToolbox/OneKeyTranslatePage.py:2512-2555` 的 `_on_start_translate_clicked()` 里直接做 `MessageBox` 弹窗、`configure_tl_translation_mode`、`_open_legacy_translation_page()` 跳页。这条链路无法在无界面环境复用。

`start_current_project()`（同文件 `:2434`）是唯一的 Agent 入口，前置条件堆了 11 个 `return False`（引擎空闲、无桩、无单任务、无 request_id、无 apply……），任一命中就静默失败，Agent 侧只看到「启动了/没启动」。

### 2.4 服务层其实已经就绪

关键好消息：**无 UI 依赖的流水线库已经存在**，`module/OneKey/flow.py`（908 行）：

- `detect_game_status()` `:708`
- `prepare_extraction_paths()` `:790`
- `extract_project_text()` `:823`
- `resolve_translation_apply_paths()` `:480`
- `apply_translation_files_transactionally()` `:489`
- `apply_full_translation()` `:972` / `apply_incremental_translation()` `:901`
- `merge_incremental_translation_cache()` `:348`

API 侧已经用它跑通了 headless 全链路：`api/routes/onekey.py:353` 的 `compute()` 在 390-460 行依次做 detect → unpack → decompile → extract，`api/routes/onekey.py:552` 的 `/apply` 负责回填。

**结论：缺的不是能力，是把能力接到 Agent 上。**

### 2.5 长任务基础设施

`api/jobs.py` 的 `JobManager` 已经具备：`job_id`、`total/done`、WS 推送（`{"type": "job", ...}`）、协作取消、终态收敛。`api/routes/agent.py` 目前只有 5 个端点，`agent.start()` 立即返回快照，事件走 WS——**Agent 的运行本身已经是异步的**，这对接长任务是利好。

### 2.6 两处硬约束

- `module/Agent/AgentService.py:36`：`max_iterations = 8`。一条龙按「每轮一个动作」走必然超限。
- `module/Agent/ToolDispatcher.py:45`：`MAX_RESULT_CHARS = 2000`。进度类结果会被截断。
- `module/Agent/AgentService.py:29`：`DEFAULT_MAX_CONTEXT_CHARS = 128_000`，超限是**硬裁剪**（`:220`），没有摘要压缩。

---

## 三、竞品参考：LinguaGacha 的 Agent

用户点名参考 `neavo/LinguaGacha`。它的 Agent 目录 `src/backend/agent/` 有 60+ 文件，架构文档在 `docs/AGENT_RUNTIME.md`，系统提示在 `builtin/system.md`。抽掉无关内容后，有 6 个点值得直接借鉴：

### 3.1 技能包（最重要）

`builtin/system.md` 里明确要求：按任务选择 `builtin/skills/*/SKILL.md`，通过 `read_skill` 工具加载正文后再执行。

例如 `builtin/skills/translation/SKILL.md` 只有几行：

> 先加载当前可用且尚未加载的写作技能，包括 `writing-guide` 和所有以 `writing-guide-` 开头的技能。随后按任务需要读取资源……

真正的领域知识放在 `references/item-translate.md` 这类子文件里，模型按需读取。

**对 RenpyBox 的意义**：现在所有工具说明都是 `module/Localizer/LocalizerZH.py` 里的 `agent_tool_*_description` 字符串，塞死在 `ToolDispatcher` 里。解包/反编译/提取/术语/禁翻/审校/RenPy 语法这些知识没法按场景加载，只能全塞系统提示，或者干脆不告诉模型。

### 3.2 `doing` 阶段播报

`src/backend/agent/tools/doing.ts` 提供一个 `doing(text: string | null)` 工具，用于「更新当前任务处理阶段，处理完成或结束时传 `null` 清空，内容跨回合保留」。

正好解决「翻译跑两小时，Agent 一直静默」的体验问题。

### 3.3 批量翻译 + 停止语义

`docs/AGENT_RUNTIME.md`「Agent 内的批量翻译」一节：

> 用户主动停止批量翻译后，同轮后续调用继续保留停止决定。显式继续或新一轮请求再开启执行，避免自动工具循环撤销用户的停止意图。

这是长任务工具的必备语义：停止意图必须跨工具调用保持，否则自动循环会立刻把用户刚停的任务重新拉起来。

### 3.4 写操作统一走「准备差异 → 审批 → 事务提交」

`workspace_apply` + 持久化偏好 `agent_approval_mode`（`allow_once` 只放行当前批次），且「审批摘要和实际提交使用同一份差异」。

RenpyBox 现在是逐工具 `requires_confirmation`，`optimize_old_new_translations` 已经用「签名比对」防陈旧确认（`module/Agent/tools/translation_tools.py:106-111`），这个思路对，可以推广到所有写操作。

### 3.5 `ask_user` 结构化提问

RenpyBox 现在完全靠自由文本，模型问「你想翻译成哪种语言」时用户得手打。桌面端已经有 input 组件，加一个带选项的提问不贵。

### 3.6 CodeAct：一个脚本跑完程序化步骤

`builtin/system.md`「CodeAct 范式」：

> 由模型确定目标、规则与语义结论，再用单个脚本按数据依赖关系连续完成尽可能多的数据处理步骤……减少模型工具调用的轮数、减少进入上下文的过程数据。

RenpyBox 的 `module/OneKey/flow.py` 本身就是确定性流水线，比「让模型写脚本」更安全，直接包一层工具即可拿到同样的收益。

---

## 四、设计目标

一句话：**Agent 说「把 D 盘这个游戏译成中文」之后，从解包到可玩，中间不需要用户再点第二次。**

拆成四条可验收的目标：

1. 全链路工具化：解包、反编译、提取、启动翻译、查看进度、回填译文、生成 replace 补丁，每一步 Agent 都能自己发起。
2. 进度可观测：长任务返回 `job_id`，Agent 能在后续回合查询阶段与百分比，并把它播报给用户。
3. 收尾可托管：翻译结束后可以自动回填 + 生成补丁，不必让用户守着点。
4. 领域知识可加载：RenPy 流水线知识做成技能包，Agent 按阶段读取，不挤占每次请求的上下文。

**不做的**：不引入模型可写脚本的能力（CodeAct 的 `workspace_run`），安全面太大，收益可以用 `flow.py` 包工具替代。

---

## 五、分期提议

### 第一期：把能力接上（后端为主，不改界面结构）

核心动作：**新建 `module/OneKey/service.py` 作为无 UI 的流水线门面**，Qt 页面、API、Agent 三方共用。当前 `OneKeyTranslatePage` 里那些「判断状态 → 调 flow → 决定下一步」的逻辑上移到这里，页面只负责显示。

新增工具（全部复用 `flow.py` / `ArchiveOps`，不重写算法）：

| 工具 | 后端来源 | 确认 | 空闲引擎 |
|---|---|---|---|
| `decompile_rpyc_files` | `module/Tool/ArchiveOps.decompile_target` | 需要 | 需要 |
| `run_project_extraction` | `flow.prepare_extraction_paths` + `flow.extract_project_text` | 需要 | 需要 |
| `start_translation` | 抽出的 service 启动翻译（同 `api/routes/translation.py:871` 的入参语义） | 需要 | 需要 |
| `translation_status` | 复用 `api/routes/translation.py:1091` 的只读快照逻辑 | 不需要 | **不需要**（关键：不能加锁） |
| `stop_translation` | 同 `/stop` | 不需要 | 不需要 |
| `apply_translation` | `flow.apply_full_translation` / `apply_incremental_translation` | 需要 | 需要 |
| `refresh_replace_fallback` | `flow._replace_fallback` + `translation_tools` | 需要 | 需要 |

同时补两个既有缺口：

- `inspection_tools` 的 `REFRESH_REPLACE_FALLBACK` 接到 `refresh_replace_fallback` 工具上。
- `DECOMPILE_SCRIPTS` 从「跳工具箱页」改成「直接调 `decompile_rpyc_files`」。

验收：
- `pytest tests/module/agent tests/api` 全绿；
- 新增 `tests/module/agent/test_agent_pipeline_tools.py`，对每个新工具覆盖成功 / 未设项目 / 引擎忙 / 确认陈旧四类分支；
- 手工跑一次真实项目的解包→提取，确认与 Qt 向导结果一致（比对 `tl` 目录文件数与签名）。

**风险点**：`requires_idle_engine` 与长任务冲突。`translation_status` 必须显式声明不需要空闲引擎，否则查进度时会被自己的翻译任务挡回去。

### 第二期：技能包 + 阶段播报 + 续跑

1. **技能包机制**
   - 新增 `module/Agent/skills/` 目录与 `read_skill` 工具（名字与语义对齐 LinguaGacha）。
   - 内置技能：`renpy-pipeline`（全流程顺序与判据）、`glossary`（术语表生成与合并）、`text-preserve`（禁翻规则）、`proofreading`（审校口径）、`rpy-syntax`（RenPy 语法陷阱）。
   - `ToolDispatcher` 的工具说明改为「技能里写知识，schema 里只写参数」。

2. **阶段播报**
   - 新增 `set_stage` 工具（`doing` 的等价物），写入 Agent 会话的阶段字段，随事件推给前端。
   - 桌面 Agent 页显示当前阶段徽标 + job 进度条。

3. **续跑（"一条龙"的关键）**
   - `start_translation` 成功后注册完成回调：完成 → 自动 `apply_translation` → 自动 `refresh_replace_fallback` → 把结果作为一条系统事件推回 Agent 会话。
   - 停止语义照抄 LinguaGacha：用户主动停止后，同轮后续的自动调用不得重新拉起任务。

4. **轮次预算**
   - `max_iterations = 8` 对长任务不够。建议改成「按类型计数」：轮询类工具调用不占预算，或把上限提到可配置（默认 24）。

验收：一条龙录制一次完整会话，从「帮我翻译 D:\game\xxx」到「已生成译文与补丁」，中间不出现需要用户点按钮的断点。

### 第三期：桌面端界面重做 + 移除 Qt

1. `desktop/renderer/src/pages/AgentPage.tsx`：
   - 建议卡改成「流水线预设」（一键全流程 / 只解包 / 只提取 / 续跑翻译 / 只回填），对齐 LinguaGacha 的预设指令形态；
   - 工具卡片增加阶段时间轴与 job 进度；
   - 补 `REFRESH_REPLACE_FALLBACK` 等新工具的中文名（`TOOL_NAMES`，`AgentPage.tsx:13-17`）。
2. 移除阶段：`frontend/` 整体退场。前置条件是 2.1 的 service 抽取完成，Qt 页面不再持有业务判断。

---

## 六、迁移方向说明

用户已明确「完善以后可以移除 python 版本」。据此定两条约定：

1. **新功能只进桌面端**。`frontend/Agent/AgentPage.py` 与 `frontend/RenpyToolbox/OneKeyTranslatePage.py` 从本期起功能冻结，只接受修 bug。
2. **业务判断必须留在 `module/`**。凡是「判断当前处于哪一步、下一步该做什么」的逻辑，只允许写在 `module/OneKey/service.py` 与 `module/Agent/tools/`，不允许写在任何页面里。

这条约定比任何具体功能都重要：它决定了 Qt 版本能不能被删干净。

---

## 七、风险清单

| 风险 | 影响 | 处置 |
|---|---|---|
| 引擎互斥锁 | 查进度工具被自己的翻译任务挡住 | `translation_status` 不声明 `requires_idle_engine` |
| 8 轮上限 | 一条龙走不完 | 第二期改为轮询不占预算 |
| 双前端分叉 | 同一功能两套实现 | 第六节约定：功能冻结 Qt |
| 写游戏目录不可逆 | 回填失败污染工程 | 复用 `flow.apply_translation_files_transactionally` 的事务路径，禁止另写一套 |
| 确认陈旧 | 用户确认后工程被改 | 沿用 `optimize_old_new_translations` 的签名比对（`translation_tools.py:106`） |

---

## 八、待确认问题

1. **范围**：这一轮只做第一期（把能力接上），还是一次做到第二期（含技能包与续跑）？第三期界面重做可以单独排。
2. **托管程度**：翻译完成后，是 Agent 自动回填（全托管），还是只提示用户「可以回填了」，由用户确认？我倾向自动回填但保留确认阈值（剩余失败项 > 0 时停下来问）。
3. **技能包**：是否接受新增 `module/Agent/skills/*/SKILL.md` 这套资源目录（意味着 agent 的领域知识从 `LocalizerZH.py` 的字符串迁到 Markdown 文件，i18n 需要另做）？
4. **Qt 冻结**：是否同意从现在起 `frontend/` 不再接收新功能，只修 bug？
5. **分工**：如果交给 cursor 子智能体写，建议按「后端工具层」「服务层抽取」「桌面界面」三个不相交的写入范围拆，我负责串起来并跑测试。是否按这个拆法？

确认后我出第一期的施工单（文件级清单 + 验收命令），再进入开发。
