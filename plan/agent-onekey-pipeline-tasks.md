# Agent 一条龙 施工单

- 前置：`plan/agent-onekey-pipeline-suggestions.md`（已确认）
- 已确认决策
  - 范围：三期全做，方向是「桌面端为唯一前端，Qt 版本移除」
  - 回填策略：自动回填；失败项 > 0 时停下来问用户
- 分支：dev
- 提交规范：`<type>: <中文描述>`

---

## 阶段划分

| 阶段 | 目标 | 是否重构既有不变量 | 阻塞后续 |
|---|---|---|---|
| 1a | 补齐「不会碰并发安全」的 4 个工具 + 2 个 action 映射 | 否 | 否 |
| 1b | 抽服务层，补 `start_translation` / `stop_translation` / `apply_translation` | 是（谨慎） | 是 |
| 2 | 技能包 + `read_skill` + `set_stage` + 自动续跑 | 否 | 是 |
| 3 | 桌面 Agent 页重做 + Qt 退场 | 否 | — |

**1a 先落地**：它不触碰 `api/routes/translation.py` 的并发预占逻辑（上一个提交 `eba370d` 刚修好竞态与越权），风险最小，且立刻让「解包 → 反编译 → 提取 → 体检 → 补丁」这段可被 Agent 自主执行。

---

# 阶段 1a

## 目标

Agent 能自主完成：`set_project` → `unpack_rpa_files` → `decompile_rpyc_files` → `run_project_extraction` → `inspect_translation_project` → `refresh_replace_fallback`，全程不需要用户点按钮。

翻译阶段（start/stop/apply）留给 1b。

## 任务

### T1a-1 新增 `module/Agent/tools/pipeline_tools.py`

四个 handler，签名统一带 `config_loader`，写操作额外接收 `confirmed_*` 字段（由 `ToolDispatcher` 从可信上下文注入，禁止从模型参数拿）。

```python
def decompile_rpyc_files(
    *, config_loader: Callable[[], Config] | None = None,
    confirmed_game_dir: str | None = None,
    __cancel_check__: Callable[[], bool] | None = None,
) -> ToolResult
```
- 复用 `module/Tool/ArchiveOps.decompile_target`，参数照抄 `api/routes/onekey.py:417-423`（`overwrite=False`、`use_unren=True`、`fallback_unren_options="2x"`）。
- 前置：`RenpyProjectPaths.from_config` 解析成功且 `game_dir.is_dir()`；`confirmed_game_dir` 与当前 `game_dir` 的 `os.path.normcase` 不一致时返回 `CONFIRMATION_STALE`（照抄 `module/Agent/tools/archive_tools.py:33-42`）。
- 若项目里没有 `*.rpyc`，返回 `ToolResult(False, ..., code="RPYC_NOT_FOUND")`。
- 成功返回 `data={"decompiled_count": int, "method": str}`。

```python
def run_project_extraction(
    *, config_loader=None, incremental: bool | None = None,
    confirmed_project_root: str | None = None,
    __cancel_check__: Callable[[], bool] | None = None,
) -> ToolResult
```
- 只做 detect → （必要时）提示需要先解包/反编译 → `flow.extract_project_text`。
- **不要**在这里做 unpack/decompile 的自动串联：那两步是独立工具，各自有确认，串起来就绕过了确认。
  - `detect_game_status` 返回 `need_unpack` / `need_decompile` 时，返回 `ToolResult(False, ..., code="NEED_UNPACK"/"NEED_DECOMPILE", data={"next_tool": "unpack_rpa_files"/"decompile_rpyc_files"})`。
  - 这让模型自己决定下一步，符合现有「模型决定、工具受限」的约定。
- 成功后返回 `data={"tl_dir": ..., "output_dir": ..., "incremental": bool, "entry_count": int}`。
- 抽取前保存配置这一点**暂不做**（1b 的服务层负责），工具只返回路径，由后续 `start_translation` 依赖的配置校验兜底。

```python
def translation_status(*, config_loader=None) -> ToolResult
```
- 纯只读。照 `api/routes/translation.py:1091-1151` 的取数逻辑，但**不要** import `api.*`：把该逻辑复制成 `module/Agent/tools/pipeline_tools.py` 内的私有函数，取 `Engine.get().get_status()`、`Engine.get().get_running_task_count()`、`has_stop_barrier()`、`has_single_tasks()`，再从 `CacheManager(service=False)` 读 `get_progress()`。
- `data` 里回：`engine_status`、`running/max`、`progress`（`line`/`total`/`percent`）、`untranslated_count`、`project_status`。
- **必须**在 `ToolDispatcher` 里声明 `requires_idle_engine=False`（默认值即可，但要写测试锁死）。

```python
def refresh_replace_fallback(
    *, config_loader=None, confirmed_context: dict | None = None,
) -> ToolResult
```
- 结构照抄 `module/Agent/tools/translation_tools.py:93-166` 的 `optimize_old_new_translations`（同样的签名比对、备份、异常回滚）。
- 差别：先按 `flow._replace_fallback` 的语义判断是否需要刷新，`needs_refresh` 为假时直接返回成功 + `data={"refreshed": False}`，不写文件。

### T1a-2 注册工具

`module/Agent/ToolDispatcher.py:59-152` 的 `_build_tools()` 追加四块，`requires_confirmation` / `requires_idle_engine` 取值：

| 工具 | requires_confirmation | requires_idle_engine |
|---|---|---|
| `decompile_rpyc_files` | True | True |
| `run_project_extraction` | True | True |
| `translation_status` | False | False |
| `refresh_replace_fallback` | True | True |

`execute()`（同文件 `:227-246`）的 `trusted_context` 注入分支追加：
- `decompile_rpyc_files` ← `confirmed_game_dir`
- `run_project_extraction` ← `confirmed_project_root`
- `refresh_replace_fallback` ← `confirmed_context`

`module/Agent/tools/__init__.py:7-22` 的 `_EXPORTS` 追加四项。

### T1a-3 确认上下文

`module/Agent/AgentService.py:125` 的 `run_confirmed_tool` 与确认生成处需要为新工具产出可信上下文：

- `decompile_rpyc_files`：`{"game_dir": <解析后的绝对路径>}`
- `run_project_extraction`：`{"project_root": <绝对路径>, "language": <str>, "incremental": <bool>}`
- `refresh_replace_fallback`：直接复用 `translation_tools.old_new_replace_confirmation_context()`

参考现有 `unpack_rpa_files` 的做法（`AgentService.py:111` 附近）。

### T1a-4 本地化

`module/Localizer/LocalizerZH.py` 与 `module/Localizer/LocalizerEN.py` 各新增：

- `agent_tool_decompile_rpyc_files_description`
- `agent_tool_run_project_extraction_description`
- `agent_tool_translation_status_description`
- `agent_tool_refresh_replace_fallback_description`
- 四个工具的成功/失败提示（命名 `agent_<tool>_...`）
- 确认框标题/正文：`agent_page_decompile_confirmation`、`agent_page_extract_confirmation`、`agent_page_refresh_fallback_confirmation`

文案口径：工具 description 写给模型看，必须说明「何时用、前置条件、副作用」，不要写实现细节。

### T1a-5 补两个 action code 映射

`frontend/Agent/AgentPage.py:2726-2772` 的 `primary` 映射表补：

- `REFRESH_REPLACE_FALLBACK` → 新常量 `ACTION_REFRESH_FALLBACK`，点击后走 `_confirm_*_action()` → `_start_confirmed_tool("refresh_replace_fallback", ctx)`
- `DECOMPILE_SCRIPTS` → 从「跳工具箱页」改为 `ACTION_DECOMPILE`，直接调已确认工具

新增常量放 `frontend/Agent/AgentPage.py:105-111`。
新增按钮文案：`agent_page_action_decompile`、`agent_page_action_refresh_fallback`（zh/en）。

> Qt 侧只改这两处映射，其余冻结。后续整体移除。

### T1a-6 桌面渲染端文案

`desktop/renderer/src/i18n/zh.ts` / `en.ts` 追加对应 `agent_page_tool_*` 键；`desktop/renderer/src/pages/AgentPage.tsx:13-17` 的 `TOOL_NAMES` 追加四项映射。

## 测试

新增 `tests/module/agent/test_agent_pipeline_tools.py`，每个工具覆盖：

1. 未设置项目 → `PROJECT_NOT_SET`
2. 路径已被改动 → `CONFIRMATION_STALE`
3. 引擎忙 → `ENGINE_BUSY`（通过 monkeypatch `Engine.get()`）
4. 正常路径 → 成功且 `data` 字段齐全
5. `translation_status` 在 `Engine.Status.TRANSLATING` 下仍能返回（回归锁：不能要求空闲引擎）

`tests/module/agent/test_agent_tools.py` 追加：四个新工具都在 `ToolDispatcher.tools` 里，且 confirmation/idle 标志与上表一致。

## 验收命令

```powershell
python -m pytest tests/module/agent tests/api -q
python -m pytest tests -q
```

---

# 阶段 1b

## 目标

Agent 能启动、停止、回填翻译。**这是唯一需要动并发不变量的阶段，必须最保守。**

## 关键约束（违反即打回）

`api/routes/translation.py:871-975` 的启动路径包含：状态检查 → `reserve_translation()` 预占 → owner 校验 → 候选构建 → 载荷准备 → 事件投递 → `finally` 归还票据。上一个提交 `eba370d` 刚修好这里的竞态与越权。

**禁止**：在 `module/Agent` 里重新实现这段逻辑或直接 `_emit(Base.Event.TRANSLATION_START, ...)`。

## 任务

### T1b-1 抽服务层

新建 `module/Engine/TranslationStartService.py`：

```python
async def start_translation_core(app_state: AppStateLike, body: TranslationStartRequestLike)
    -> TranslationStartResponseLike
```

- 把 `api/routes/translation.py:884-975` 的函数体整体搬进来，`request` 只保留 `request.app.state` 的用法，改为参数传入。
- `_prepare_payload` / `_start_source_with_prebackup`（同文件 `:615` / `:871` 区域）同步搬迁，改为接收 `app_state`。
- 路由函数退化成三行：调用 core、把异常翻译成 `HTTPException`。
- `AppStateLike` 用 `Protocol` 定义，只声明 `config` 与 `jobs`。
- **验收锁**：搬迁前后 `tests/api/test_onekey_safety.py`、`tests/api/test_translation*.py` 必须全绿且断言不变。

### T1b-2 同步桥接

`module/Agent/tools/pipeline_tools.py` 追加：

```python
def start_translation(*, config_loader=None, confirmed_project_key: str | None = None) -> ToolResult
def stop_translation(*, config_loader=None) -> ToolResult
```

- Agent 工具跑在独立线程（`AgentService` 的后台线程），用 `asyncio.run(start_translation_core(app_state, body))` 桥接。
- `app_state` 由 `ToolDispatcher` 构造时注入（新增 `app_state_provider` 可选参数，默认 `None`；`None` 时工具返回 `code="AGENT_APP_CONTEXT_MISSING"`，Qt5 侧就是这个分支）。
- `stop_translation` 是同步函数（`api/routes/translation.py:977`），直接调用即可。

### T1b-3 回填工具

```python
def apply_translation(
    *, config_loader=None, mode: str = "full", confirmed_context: dict | None = None,
) -> ToolResult
```
- 复用 `flow.apply_full_translation` / `flow.apply_incremental_translation` / `flow.resolve_translation_apply_paths`。
- 回填前计算 `confirmed_context`（`tl_dir` 签名、输出路径、待写条数），签名不符返回 `CONFIRMATION_STALE`。
- 返回 `data` 含 `applied_count`、`failed_count`、`failed_samples`（最多 5 条）。

### T1b-4 抽提取服务

新建 `module/OneKey/pipeline.py`，把 `api/routes/onekey.py:388-505` 的 detect → unpack → decompile → extract → `prepare_extraction_paths` 搬成：

```python
def run_preprocess(
    *, config: Config, project_root: str, language: str, incremental: bool,
    exe_path: str | None, progress: Callable[[str, int, str], None],
    cancel_check: Callable[[], bool],
) -> dict
```

路由 `prepare()` 与 `run_project_extraction` 都调用它。配置落盘留在调用方。

> 注意：这条会改变 1a 里 `run_project_extraction` 的实现（从「只抽取」升级为「可串联解包/反编译」）。1b 完成后，1a 的 `NEED_UNPACK` 返回值可以保留（仍是正确行为），但改由 `run_preprocess` 统一判断。

## 测试

- `tests/api/test_onekey_safety.py` 断言不变（回归锁）
- 新增 `tests/module/agent/test_agent_translation_tools.py`：引擎忙 / owner 不符 / 正常受理 / 停止 / 回填签名陈旧
- 并发回归：并发两个 `start_translation` 只允许一个 `accepted=True`（照 `tests/api/` 里现有竞态测试的写法）

---

# 阶段 2

## T2-1 技能包

新建：

```
module/Agent/skills/__init__.py
module/Agent/skills/renpy-pipeline/SKILL.md
module/Agent/skills/glossary/SKILL.md
module/Agent/skills/text-preserve/SKILL.md
module/Agent/skills/proofreading/SKILL.md
module/Agent/skills/rpy-syntax/SKILL.md
```

`SKILL.md` 首部 Front Matter：

```markdown
---
name: renpy-pipeline
description: 一句话说明何时使用（这句话进系统提示的技能目录）
---
```

正文用中文写领域知识，**不写工具名清单**（工具清单在 schema 里）。

`renpy-pipeline` 至少覆盖：解包 → 反编译 → 提取 → 翻译 → 回填 → 补丁 的判据与顺序、每种 `detect_game_status` 返回值对应的下一步、失败时的回退。

## T2-2 `read_skill` 工具

`module/Agent/tools/skill_tools.py`：

```python
def list_skills() -> ToolResult          # 返回 name + description（不含正文）
def read_skill(name: str) -> ToolResult  # 返回正文，超长截断到 12000 字并提示分段
```

- 路径只允许 `module/Agent/skills/<name>/SKILL.md`，`name` 必须匹配 `^[a-z0-9-]+$`，禁止 `..`。
- 系统提示（`module/Agent/AgentPromptBuilder.py`）追加 `<available_skills>` 段，只列名字与描述。

## T2-3 `set_stage` 工具

```python
def set_stage(stage: str | None) -> ToolResult
```
- 写入 `AgentService` 会话的阶段字段（新增 `self._stage`），随事件推给前端。
- `stage` 为 `None` 时清空。
- `AgentService.snapshot()` 暴露 `stage`；`api/routes/agent.py` 的返回值自动带上。
- 不许写入对话历史（它不是一个消息）。

## T2-4 自动续跑

`module/Agent/AgentService.py` 新增 `_auto_continue`：

- `start_translation` 成功后注册一次性回调。
- 翻译终态事件到达时：
  - `DONE` 且失败项 == 0 → 自动 `apply_translation` → 自动 `refresh_replace_fallback` → 推 `system` 事件说明结果
  - `DONE` 且失败项 > 0 → 推 `system` 事件列出失败项，**停下来等用户**（已确认的决策）
  - `CANCELLED`/`FAILED` → 清掉回调，不自动回填
- 用户主动 `stop_translation` 后，同一轮内的自动调用一律跳过（照 LinguaGacha 的停止语义）。

## T2-5 轮次预算

`module/Agent/AgentService.py:36` 的 `max_iterations = 8` 改为：

- 新增参数 `polling_tools = {"translation_status"}`，调用这些工具的轮次不占预算。
- 其余轮次上限提到 24。

## 测试

`tests/module/agent/test_agent_skills.py`、`test_agent_auto_continue.py`、`test_agent_iterations.py`。

---

# 阶段 3

## T3-1 桌面 Agent 页

`desktop/renderer/src/pages/AgentPage.tsx`：

- 建议卡（`:19-23`）改成「流水线预设」：一键全流程 / 只解包 / 只提取 / 续跑翻译 / 只回填。
- 新增阶段徽标：读 `session.stage`（T2-3）。
- 工具卡片增加进度条：读 WS 的 `{"type":"job"}` 事件（`api/jobs.py:190`）。
- `TOOL_NAMES`（`:13-17`）补齐全部工具。

## T3-2 Qt 退场

前置：1a/1b/2 全部合入并通过测试。

1. `frontend/` 标记冻结（本轮只做：不再新增功能）。
2. 逐页比对桌面端覆盖情况，列缺失清单。
3. 缺失清零后，删除 `frontend/`、`tests/frontend/`，清理 `pyproject.toml` / `requirements.txt` 里的 PySide6/qfluentwidgets 依赖。

**本轮不执行第 3 步**，只产出缺失清单。

---

## 里程碑

| 里程碑 | 完成标志 |
|---|---|
| M1 | 1a 合入，Agent 能自主走到「提取完成」 |
| M2 | 1b 合入，Agent 能「启动翻译 → 查进度 → 停止 → 回填」 |
| M3 | 2 合入，一条龙全托管，失败项停下来问 |
| M4 | 3 合入，桌面端为唯一前端，Qt 冻结 |

---

# 阶段 2-b（已实施）Agent 自己当翻译

> 背景：用户 m00675 澄清「让 agent 自己翻译」，不是让 Agent 去点翻译引擎的按钮。
> 1a/1b 的 `start_translation` 降级为「用户明确要用翻译引擎」时的可选路径，
> 默认路径改为 Agent 逐批翻译。

## 复用的既有实现（不另造流水线）

| 能力 | 复用对象 |
|---|---|
| 条目与缓存 | `module/Cache/CacheManager.py`（`load_from_file` / `get_items` / `save_to_file`） |
| 质量闸 | `module/Response/ResponseChecker.py` 的 `ResponseChecker.check(srcs, dsts, text_type, line_items)` |
| 写回 .rpy | `module/File/FileManager.py` 的 `write_to_path` → `module/File/RENPY.py:95` 的行级更新 |
| 进度 | 已有 `translation_status`（引擎空闲时走缓存口径） |

注意：`module/ResultChecker.py` 只是**出报告**（往输出目录写「结果检查_*.json」），
不会打回条目，所以不能当闸门用；真正的闸门是 `ResponseChecker`。

## 新工具（`module/Agent/tools/agent_translation_tools.py`）

- `read_translation_batch(batch_size=30, max_chars=6000)`
  - 取 `status` 为未完成且非 `EXCLUDED`/`DUPLICATED`、原文非空的条目。
  - 条目 id = `文件相对路径｜行号`。
  - 返回 `{remaining, returned, items:[{id, src, name_src?, text_type?}]}`。
  - 还有条目时 `ToolResult.continues=True`。
- `write_translation_batch(translations=[{id, dst, name_dst?}])`
  - 按 id 定位 → 写 dst → `TRANSLATED`。
  - `ResponseChecker` 逐条校验；失败的条目打回 `UNTRANSLATED`、不写文件，
    并在 `data.failed_items` 里带 `{id, code}` 让模型自己改。
  - 通过校验的才 `FileManager.write_to_path`，最后整份缓存 `save_to_file`。
  - 写同一份缓存的读与写用 `_WRITE_LOCK` 串行化。
- 两个工具都 `requires_confirmation=False`、`requires_idle_engine=True`
  （引擎正在翻译时缓存归引擎所有，Agent 不能碰）。

## 轮次与上下文（`module/Agent/AgentService.py`）

- `ToolResult` 新增 `continues` 字段：工具自报「长任务仍在推进」。
- 新增 `max_long_iterations`（默认 240）：`continues=True` 的迭代不占
  `max_iterations`（默认 8），长任务因此能跑完，普通对话仍受 8 轮约束。
- `ToolDef` 新增 `result_limit`：`read_translation_batch` 放宽到 12000 字符，
  否则默认 2000 会在 JSON 中间截断整批条目。
- `_trim_history` 新增单回合内裁剪 `_trim_within_turn`：一盘游戏只有一个用户回合，
  旧的「按用户回合裁剪」在长任务里不生效，上下文会线性增长。

## 桌面端

- `desktop/renderer/src/pages/AgentPage.tsx`：`TOOL_NAMES` 补两个工具，
  建议卡首位改为「把当前项目翻译成中文」。
- `desktop/renderer/src/i18n/zh.ts` / `en.ts` 补文案。

## 验收

- `python -m pytest tests/module/agent tests/module/test_localizer_coverage.py -q` → 126 passed
- `python -m pytest tests/api -q` → 594 passed
- `node node_modules/typescript/bin/tsc --noEmit -p renderer/tsconfig.json` → 0
- `node --test tests/*.test.mjs` → 225 passed

## 仍未做

- 整条流水线的自动续跑：现在靠模型自己一轮轮调工具，
  模型中途给出结束回复就停在那里，没有「译完自动 apply + 兜底」的钩子。
- `set_stage` 阶段字段与桌面阶段徽标。
- 失败条目阈值的策略化（现在逐条打回，缺少「同一批失败超过 N 条就停下来问」）。

---

# 阶段 2-c（已实施）批量路径：引擎翻译 + Agent 自己的模型

## 为什么加这一条

对照 `neavo/LinguaGacha` 的 `batch_item_translation`
（`src/backend/agent/tools/batch-item-translation.ts:31-58`）：它**不让 Agent 逐条产出译文**，
而是把范围交给内部批量引擎，工具只回统计：

```
items: { total, succeeded, failed, unfinished }
usage: { elapsed_seconds, input_tokens, reasoning_tokens, output_tokens, total_tokens }
status, stop_source    // stop_source: user / parent / shutdown
```

它的技能正文 `builtin/skills/translation/references/item-translate.md:17-21` 明确分档：
小批量由 Agent 亲手译，超过业务单元规模就走批量工具。

RenpyBox 已经有成熟的翻译引擎（prompt 组装、分块、并发、重试、术语表、缓存），
缺的只是「这一轮用 Agent 自己配置的模型」和「回执只有数字」。补上这两点即可对齐。

## 实现

- `api/schemas.py`：`TranslationStartRequest` 增加 **请求级** `platform_id: int | None`。
- `api/routes/translation.py`：`request_translation_start` 在 `mode is None` 且带 `platform_id` 时，
  构造 `candidate = deepcopy(live)` 并改写 `candidate.activate_platform`，
  作为 `config_snapshot` 传给 `_prepare_payload`。
  - 只进本轮冻结快照；`_collect_changed_fields` 的字段白名单不含 `activate_platform`，
    所以**不落盘、不改翻译页设置**。
- `api/pipeline_bridge.py`：`platform_source="agent"` → 解析成 `config.agent_platform`；
  Agent 接口未配置时直接给结构化失败，不投递协程。
- `module/Agent/tools/pipeline_tools.py`：`start_translation` 增加 `use_agent_model`（默认 True），
  转成 `platform_source`。
- `module/Agent/ToolDispatcher.py`：schema 增加同名布尔参数（默认 True）。
- 系统提示词（ZH/EN）改成**两条路径**：
  - 大批量（整盘游戏、上千条）→ `start_translation`（默认 `use_agent_model=true`），
    只看 `translation_status` 的数字，结束后 `apply_translation`；
  - 小批量（几十条、试跑一条、修失败条目）→ `read_translation_batch` / `write_translation_batch`。

## 验收

- `tests/module/agent` + 本地化覆盖 → 126 passed
- `tests/api/test_agent_pipeline_bridge.py` → 9 passed（新增 agent 平台覆盖与未配置两条）
- 全量 `tests/api` → 594 passed

## 仍未做（本阶段）

- 批量工具的「单条试跑闸门」：LinguaGacha 要求首次调用前先用一条目标试跑通过，
  现在靠提示词约束，没有服务端强制。
- `stop_source` 语义：RenpyBox 只有 STOPPING，没有区分 user / parent / shutdown。
- 工具结果落盘 + 补读（`policy.ts:8-13` 的 64KiB 内联额度思路）。

---

# 阶段 2-d（已实施）放大容量：让 Agent 一口气译完整盘

## 背景

用户要求「让 Agent 直接翻译，一步到位」，并指出现代模型已经有 1M 上下文。
原实现的三处硬限额会让整盘翻译被强行切碎：

| 位置 | 原值 | 现值 | 理由 |
|---|---|---|---|
| `AgentService.DEFAULT_MAX_CONTEXT_CHARS` | 128_000 | 300_000 | 128k 字符≈60k～90k token，200k 窗口的模型只用到一半；300k 字符≈100k～150k token，既喂得满 200k 窗口，也不会把 128k 窗口的模型一次撑爆 |
| `AgentService.DEFAULT_MAX_LONG_ITERATIONS` | 240 | 600 | 一轮一批的模型也能跑完万级条目 |
| `agent_translation_tools.DEFAULT_BATCH_SIZE` | 30 | 80 | 单轮吞吐 ×2.7 |
| `MAX_BATCH_SIZE` | 80 | 400 | 大窗口模型可以一次吞几百条 |
| `DEFAULT_BATCH_CHARS` | 6_000 | 40_000 | 原文预算同比放大 |
| `MAX_BATCH_CHARS` | 20_000 | 200_000 | 同上 |
| `ToolDispatcher` 的 `read_translation_batch.result_limit` | 12_000 | 140_000 | 否则 140k 字符的批次仍会在 12k 处被截断 |

## 提示词

两条路径之外补一句硬约束（ZH/EN）：
> 用户说「翻译这个项目」这类整盘任务时，一路译到底：不要译几十条就停下来总结，
> 也不要每批都问用户，直到待译条目为 0 再收尾。

## 验收

- `tests/module/agent` + 本地化覆盖 → 127 passed
- 新增用例 `test_read_translation_batch_supports_large_one_shot_batches`：
  300 条一次读满，`continues=True`

## 仍未做

- 上下文预算没有跟随模型真实窗口自适应（配置里没有 `context_window` 字段），
  现在是固定常量 + 注释，换小窗口模型需要手工调。
- 输出侧没有按 `max_output_tokens` 反推批次上限：一批 400 条约需 25k 输出 token，
  超过部分模型的单次输出上限，模型会自己截断，工具只能事后报 failed。

---

# 阶段 2-e（已实施）按模型容量推导预算

## 先纠正我的误读

我最初按「模型名 → 窗口」写了一张硬编码表，并把它当成主路径。让 cursor 直接核对
LinguaGacha 源码后确认这**不是它的做法**：

- `src/backend/llm/model-capability.ts:28` 明确不按模型名猜，容量来自依赖
  `@earendil-works/pi-ai` 的运行时目录；缺失时走 `FALLBACK_AGENT_LIMITS = 256000 / 32000`。
- 自动输出 = `min(目录 maxTokens, 档位)`，档位是窗口 `< 500000 → 32000`、否则 `64000`
  （`:34-36`、`:353-365`）。
- 用户显式非 0 值优先，但仍被 `窗口 - 32000` 压住（`:375-396`）；
  窗口小到留不出预留时整组退回自动值，不硬凑负数。
- **它没有字符预算、没有消息条数上限**：历史靠 token 级压缩，
  `AGENT_KEEP_RECENT_TOKENS = 32000` 且要除以 `usage / 估算` 的 ratio
  （`agent-chat-context.ts:9,47-48`）。token 估算单位是 `ceil(字符 / 3.5)`。

## 本次落地（`module/Agent/ModelBudget.py`）

三级解析，语义对齐上面四条：

1. 平台配置里的 `context_window` / `max_output_tokens`（**0 = 自动**，非 0 优先）；
2. 内置知名模型表（本地「目录替身」，数字取自 pi-ai@1.3.0 原厂目录，
   最长片段命中优先，避免 `gpt-4` 抢走 `gpt-4.1`）；
3. 兜底 256k / 32k，未知模型**不猜**。

`agent_context_budget()` 输出 `context_window / max_output_tokens / usable_tokens /
max_context_chars / max_messages / keep_recent_tokens`。其中
**字符预算与消息条数是 RenpyBox 独有的本地策略**（LinguaGacha 没有这两个量），
因为我们的历史是简单 list，需要一个可裁剪的边界；换算用 `1 token ≈ 1.5 字符`（保守）。

`batch_capacity()` 由**输出**预算反推批次条目数（一批 N 条就得在一次回复里吐 N 条译文），
字符预算取输入余量的四分之一。

## 断批规则

`read_translation_batch` 新增：**同一批只喂一个文件的条目**，跨文件即断批
（照 `planning/translation-planner.ts:95-100` 的 `file_path` 变化断块）。
理由：跨文件条目语境无关，混批既稀释语境，也让失败重试牵连整批。

## 验收

- `tests/module/agent` → 136 passed（新增 `test_agent_model_budget.py` 15 例 +
  文件边界断批 1 例）

## 仍未做

- 平台配置还没有 `context_window` / `max_output_tokens` 的**界面入口**，
  目前只能手改 config.json；桌面端设置页要补两个输入框。
- 压缩仍是「按用户回合 / 助手边界删除」，没有实现 LinguaGacha 的
  「模型摘要替换历史 + 摘要落盘成功才生效」。
- 单批条目数与输出的咬合只做了静态反推，没有「上批被截断 → 下批减半」的自适应。

---

# 阶段 2-f（已实施）容量改为运行时目录，不再靠静态模型表

## 用户的质问

「你就没发现目前的模型类型太老了吗，其次就是必须要这种才知道模型的上下文长度和最大回复数吗」

对：静态表必然过期，而且 LinguaGacha 本来就不这么干——它从依赖包的运行时目录取容量。
RenpyBox 也有现成的 `/models` 查询链路（`api/routes/platforms.py` 的 `read_models`），
只是以前只取了 `id`，把目录里的容量字段全丢了。

## 本次落地

### 1. `module/Engine/API/ModelList.py`

新增 `list_model_capabilities(api_url, api_key, api_format) -> dict[str, (上下文, 最大输出)]`：

- Google：`Model.input_token_limit` / `output_token_limit`；
- OpenAI 兼容（OpenRouter 等）：直接 GET `{api_url}/models`，取
  `context_length | context_window | max_context_length | max_input_tokens` 与
  `max_completion_tokens | max_output_tokens | max_tokens`，以及
  `top_provider.max_completion_tokens`；
- Anthropic 与 MACHINE 格式：目录不带容量，返回空，交给兜底；
- 任何网络/解析失败返回空字典，**绝不影响主流程**。

### 2. `module/Agent/ModelCatalog.py`（新）

进程级缓存，key = `api_format|api_url`，TTL 3600s：

- `get(platform)`：只读缓存，不联网；
- `ensure_async(platform)`：缺失/过期时起后台线程刷新，**不阻塞本轮**；
- `put_for(platform, catalog)`：供接口页回填。

`api/routes/platforms.py:read_models` 在读取模型列表时顺带 `put_for(...)`，
用户打开一次模型列表就把容量信息带回来了。

### 3. `ModelBudget` 四级优先级

```
平台显式 context_window / max_output_tokens（0 = 自动）
  > 运行时目录（精确匹配，大小写不敏感）
  > 内置离线兜底表（仅断网/目录缺字段时用，已更新到 gpt-5.4/5.5、claude-*-4-6、
    gemini-2.5、grok-4.5~4.7、deepseek-v4、kimi-k3、glm-5.2/5.3 等）
  > 256k / 32k
```

`AgentService._apply_model_budget` 用 `ModelCatalog.get` + `ensure_async`；
`read_translation_batch` 的批次容量同样走目录。

## 验收

- `tests/module/agent` + `test_model_list_capabilities.py` + 本地化覆盖 → 150 passed
- 新增用例：目录优先于内置表、显式配置优先于目录、目录匹配大小写不敏感、
  OpenRouter 风格目录解析、纯 list payload、网络失败返回空、Anthropic/机器翻译格式跳过

## 仍未做

- 显式 `context_window` / `max_output_tokens` 仍没有界面入口（只能手改 config.json）。
- 请求被截断或溢出时没有「下批自动减半 / 收预算」的自适应。
- 压缩仍是删除式，没做摘要式。
