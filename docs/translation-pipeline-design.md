# RenpyBox 翻译管线整体改造设计

> 状态：`future` 分支实施基线
>
> 基线：RenpyBox v0.6.0 (`e75c2ce`)
>
> 编写日期：2026-07-24；最后更新：2026-07-25
>
> 主要参考：AiNiee `afdda76ace1d5e2b2e0cd0240785f2436a82bf46`

本文档是翻译管线改造的唯一实施依据，替代此前的流程设计与评审文档。本次工作是整体修改现有管线，不建立一套长期并存的补丁管线。

## 1. 最终决策

1. `Config` 只保存用户当前可编辑设置，不能作为翻译线程共享的可变运行对象。
2. 世界观、角色卡、术语和禁翻项成为项目级 `ProjectAssets`。
3. 新任务从当前配置生成只读 `TranslationTaskContext`，并把语义快照持久化到项目缓存。
4. 新任务使用当前设置；继续翻译必须复用原任务快照。
5. 批量请求和响应统一使用严格的 0-based `request_index`，不得按返回顺序猜测或补空行。
6. 基础提示词、输出协议、写作风格和项目资产是互相独立的层。
7. 增加 `POLISHED` 条目状态，并贯通缓存、统计、续译、写回和人工校对。
8. 润色与校对是独立任务，不强制自动串联。
9. 保留 RenpyBox 的 Ren'Py AST、tl 写回、RPA、字体、hook、源码翻译与 Android 工具。

## 2. 参考边界

### 2.1 从 AiNiee 借鉴

- 基础提示词模式：`COMMON`、`COT`、`THINK`、`LOCAL`，外加替换基础提示词的 `CUSTOM`。
- `writing_style` 是独立追加的自由文本层。
- glossary、project terms、project characters、exclusion entries 和角色描述按当前批次命中注入。
- world building 和 writing style 完整注入。
- 任务开始时创建任务配置，润色和校对为独立任务。
- 批量润色消费 `TRANSLATED` 并写 `POLISHED`。
- 校对为单条纯文本响应，每条最多两次 API 尝试，也写 `POLISHED`。

### 2.2 不复制 AiNiee

- 不复制可见 1-based、内部 0-based 的 textarea 编号协议。
- 不依赖模型返回顺序。
- 不把 source 默认当正则。
- 不照搬其缓存布局；RenpyBox 需要持久化续译快照。
- 不让分析结果直接污染当前任务资产。
- 不依赖模型自行保证占位符，写回前必须确定性复验。

### 2.3 LinguaGacha 范围

只采用以下流程思想：

```text
项目分析 -> 生成候选 -> 用户确认 -> 带确认资产翻译
```

`<why>` 属于 LinguaGacha 行为，不进入本设计。任何模式都不得要求可见思维链。

## 3. 目标架构

```text
项目文件 / Ren'Py tl
        |
        v
抽取与缓存（保留现有实现）
        |
        +---- 分析候选 ---- 用户确认 ----+
        |                               |
        +---- 用户维护项目资产 ---------+
                                        v
                                 ProjectAssets
                                        |
                              TranslationPreflight
                                        |
                       新任务创建 / 旧任务继续
                                        |
                                        v
                           TranslationTaskContext
                                 （深拷贝、只读）
                                        |
                          translation_snapshot
                                        |
                                        v
                 Batch -> Prompt -> Request -> Decode
                                        |
                         Index Align -> Check
                                        |
                      Post-process -> Cache write
                                        |
                    +-------------------+------------------+
                    |                                      |
              PolisherTask                          ProofreadTask
                    |                                      |
                    +-------------------+------------------+
                                        |
                          人工校对 / 报告 / 文件写回
```

## 4. 数据所有权

### 4.1 `Config`

新增版本化配置字段：

```text
config_version
translation_prompt_mode       COMMON | COT | THINK | LOCAL | CUSTOM
translation_custom_prompts    {"zh": "...", "en": "..."}
translation_style_id          NONE | LITERARY | CLASSICAL | R18 | CUSTOM
translation_custom_style
translation_output_protocol   STRUCTURED | JSONLINE | SINGLE_TEXT
asset_regex_enable            默认 false
asset_prompt_token_budget     有限正整数
asset_prompt_max_items        有限正整数
```

约束：

- `CUSTOM` 只替换基础提示词，不能覆盖输出协议和占位符协议。
- prompt mode 与 writing style 正交。
- `SINGLE_TEXT` 只用于显式单条任务。
- provider thinking/reasoning 参数与 prompt mode 相互独立。
- `Config.load()` 必须先执行幂等的 `migrate_dict(raw)`。

旧配置迁移：

- 旧 `custom_prompt_*_enable=true` 迁移为 `CUSTOM`，data 保持“替换基础提示词”语义。
- 未启用旧 custom prompt 时迁移为 `COMMON`。
- `structured_output_enable=true` 迁移为 `STRUCTURED`，否则为 `JSONLINE`。
- 旧字段至少保留一个版本周期的只读兼容。

### 4.2 `ProjectAssets`

正式资产保存在 `CacheProject.extras["project_assets"]`：

```json
{
  "schema_version": 1,
  "revision": 1,
  "worldbook": {"enabled": true, "data": {}},
  "character_cards": {"enabled": true, "items": []},
  "glossary": {"enabled": true, "items": []},
  "do_not_translate": {"enabled": false, "items": []}
}
```

正式术语统一为：

```json
{
  "record_id": "term_3f3ac52bc51c3d20",
  "origin": "LOCAL",
  "source": "Alice",
  "target": "爱丽丝",
  "enabled": true,
  "regex": false,
  "note": ""
}
```

- `origin` 允许 `LOCAL`、`ANALYSIS`。
- 角色卡推荐译名在构造上下文时转成只读 `CHARACTER` 记录。
- 分析输出先写 `extras["analysis_candidates"]`，用户确认后才进入正式资产。
- 运行中产生的新术语只能进入候选区，不得修改当前快照。
- 旧术语迁移时设为 `LOCAL`，稳定 ID 由 origin、U+0000、normalized source 的 SHA-256 前缀生成。

### 4.3 `TranslationTaskContext`

上下文工厂必须：

1. 加载当前 Config 和项目资产。
2. 应用入口提供的路径、语言和任务参数覆写。
3. 规范化字符串、枚举和数据结构。
4. 深拷贝平台配置和所有影响翻译的设置。
5. 转换为 frozen dataclass、tuple 或只读映射。
6. 解析实际使用的基础提示词、风格和协议版本。
7. 生成可序列化快照与稳定哈希。

Translator、TranslatorTask、PromptBuilder 和重试逻辑只能读取上下文。动态批大小、退避、限流、token 阈值等放在任务本地运行状态，不能写回 Config 或上下文。

### 4.4 Snapshot

`CacheProject.extras` 使用版本化分区：

```json
{
  "schema_version": 2,
  "progress": {},
  "project_assets": {},
  "analysis_candidates": {},
  "translation_snapshot": {
    "schema_version": 1,
    "snapshot_id": "sha256:...",
    "source_language": "JA",
    "target_language": "ZH",
    "prompt": {},
    "assets": {},
    "processing": {},
    "checking": {},
    "request_policy": {}
  }
}
```

快照包含所有影响翻译结果或响应解释的纯数据；不得包含 API key、token、secret、password、临时限流状态、客户端或锁。

- 新建/重新开始：用当前配置创建新快照。
- 继续翻译：复用缓存中的原快照。
- 续译只使用当前凭据建立连接，不替换快照语义。
- 不支持的快照版本必须报错，不能静默回退当前配置。

### 4.5 重新开始翻译

`project_assets` 与 `analysis_candidates` 是长期数据；items、progress、snapshot 和 quality progress 是单次运行数据。

“重新开始”必须执行缓存事务：

1. 保留 project id、project assets、analysis candidates 和未知长期 extras。
2. 重新读取并替换 items。
3. 清空旧 progress、snapshot 与质量任务进度。
4. 创建新快照。
5. 临时写入完整缓存后原子替换。

不得继续通过删除整个 `output/cache` 实现重新开始。只有显式“删除项目数据”动作可以删除长期资产。

## 5. 翻译前检查

所有翻译入口统一调用 `TranslationPreflightService`。

有效资产必须“开关启用且规范化后非空”：

- glossary：至少一条 source、target 都非空的 enabled 记录。
- worldbook：至少一个业务字段非空。
- character cards：至少一张 enabled 且有 name 和可注入内容的卡片。
- do-not-translate：至少一条非空 enabled source。

没有有效资产时提示“打开工作台/术语页”或“仍然继续”，但不强制阻止翻译。一个启动动作只提示一次。

若基础提示词、工程协议、完整 worldbook 与完整 style 已超过上下文，preflight 必须明确失败，不得静默截断固定层。

## 6. 提示词体系

### 6.1 基础模式

| 模式 | 作用 |
| --- | --- |
| `COMMON` | 通用游戏本地化翻译 |
| `COT` | 输出前自检，只输出最终协议内容 |
| `THINK` | 面向深度推理模型，不输出推理文本 |
| `LOCAL` | 面向本地或指令遵循较弱模型的短指令 |
| `CUSTOM` | 替换基础提示词文本 |

供应商返回的 `reasoning_content` 与 `content` 分离，只有 content 进入解码器。

### 6.2 独立风格

首版提供 `NONE`、`LITERARY`、`CLASSICAL`、`R18`、`CUSTOM`。这些预设是 RenpyBox 扩展，最终都解析成独立 writing style 文本。

### 6.3 固定拼装顺序

```text
system:
  selected base mode
  + non-overridable output/engineering protocol
  + writing style
  + worldbook
  + matched glossary/project terms
  + matched do-not-translate entries
  + matched character cards
  + placeholder protocol

user:
  retry hint
  + preceding context
  + current indexed batch
```

- base 不得硬编码 JSONLINE 或 R18。
- worldbook 与 style 完整注入。
- glossary、禁翻项与角色只按当前批命中。
- 空层完全省略；相同快照和批次必须生成相同 prompt。

## 7. 响应契约

### 7.1 索引

每批只使用连续的 `0..N-1`。缓存 ID 与文件位置保存在带外映射中。

### 7.2 Structured

```json
{
  "translations": [
    {"request_index": 0, "text": "第一行译文"},
    {"request_index": 1, "text": "第二行译文"}
  ],
  "new_glossary": []
}
```

### 7.3 JSONLINE

```jsonline
{"request_index":0,"text":"第一行译文"}
{"request_index":1,"text":"第二行译文"}
```

JSONLINE 不混入术语对象。自动术语候选使用 structured 独立字段或独立分析任务。

### 7.4 Single text

只允许显式单条任务。调用方带外提供唯一期望索引，解码器把纯文本包装成规范记录。批量失败不得退化为纯文本。

### 7.5 严格解码

规范结果：

```text
DecodedTranslation(request_index: int, text: str)
ResponseDecodeResult(translations, new_glossary, method)
```

顺序：

1. 解析 JSON 与 schema。
2. 验证每条含 request_index 和字符串 text。
3. 索引必须是真正整数；拒绝 bool、float、数字字符串和 null。
4. 拒绝负数、重复、额外、越界和 1-based。
5. 索引集合必须恰好等于 `set(range(expected_count))`。
6. 乱序允许，但必须按索引重排。
7. 对齐完成后才进入 ResponseChecker。

禁止：

- 按返回顺序猜测。
- 补空行。
- 自动将 1-based 减一。
- 丢弃额外行后继续。
- 从自然语言推断索引。
- 让 json repair 创造或补齐索引。

## 8. 资产匹配

- CJK source 使用规范化字面子串匹配。
- Latin source 使用 casefold 后的 Unicode 整词匹配。
- 角色同时匹配正文与 speaker/name metadata。
- 默认 source 按字面量；只有显式 regex=true 才编译正则。
- 非法正则在资产确认阶段拒绝。

冲突优先级：

```text
do-not-translate
  > LOCAL glossary
  > CHARACTER recommended translation
  > ANALYSIS term
```

先按规范化 source 去重，再按优先级、source 长度、source、record id 稳定排序。动态资产受 item 数与 token 双重预算，超限时稳定截断，不随机抽样。

## 9. 状态机

在 `Base.TranslationStatus` 增加 `POLISHED`，但项目和条目使用不同状态域。

项目：

```text
UNTRANSLATED -> TRANSLATING -> TRANSLATED
TRANSLATING -> TRANSLATING     # 暂停后可续译
TRANSLATED -> UNTRANSLATED     # 显式重新开始
```

项目不得写 `POLISHED`。质量任务完成后项目仍为 `TRANSLATED`。

条目：

```text
UNTRANSLATED -> TRANSLATED
UNTRANSLATED -> EXCLUDED | DUPLICATED
TRANSLATED -> POLISHED
POLISHED -> POLISHED
TRANSLATED | POLISHED -> UNTRANSLATED  # 显式重置并清空译文
```

集中 helper：

```text
PROJECT_RESUMABLE_STATUSES = {TRANSLATING}
PROJECT_COMPLETED_STATUSES = {TRANSLATED}
ITEM_COMPLETED_STATUSES = {TRANSLATED, POLISHED, TRANSLATED_IN_PAST}
ITEM_POLISHABLE_STATUSES = {TRANSLATED}
ITEM_PROOFREADABLE_STATUSES = {TRANSLATED, POLISHED}
```

所有统计、续译、重置、去重、文件写回和校对 UI 必须复用 helper。

润色和校对都写 `POLISHED`。来源使用 `quality_origin=POLISHER|PROOFREADER` metadata，不增加状态。

首版没有译文历史，不承诺“回退初译”。失败必须保留原 dst 与原 status。

## 10. 质量任务

### 10.1 PolisherTask

- 只消费 `TRANSLATED`。
- 批量执行严格索引协议。
- 整批索引对齐后逐条复验。
- 每条译文、状态与 metadata 原子写回。
- 成功写 `POLISHED`，失败保留原文和状态。

### 10.2 ProofreadTask

- 消费用户选择或质量报告标记的 `TRANSLATED`/`POLISHED`。
- 一次一条，使用纯文本响应。
- 每条最多两次 API 尝试，含首次。
- 输入原文、当前译文、错误类型、命中资产、占位符和少量上下文。
- 输出只能是修订译文。
- 写回前验证空响应、占位符、保护标记、术语和明显残留。
- 成功写 `POLISHED`；失败保留原状态。

初译、润色与校对不自动串联。

## 11. 实施顺序

1. Config migration、ProjectAssets、TaskContext/snapshot、严格 ResponseDecoder 与测试。
2. 五种基础模式、独立 style、互斥输出协议与 UI。
3. 项目资产迁移、统一 preflight、批次命中与预算。
4. `POLISHED` 贯通 Base、CacheItem、CacheManager、Engine、统计、所有 writer、Proofreading UI 与 Localizer。
5. 新建 `module/Engine/Quality/PolisherTask.py` 和 `ProofreadTask.py`。
6. 接入 `QualityTaskCoordinator`、`Engine.Status.QUALITY`、质量进度分区与校对页命令。
7. 定向重试、质量报告与端到端回归。

## 12. 验收测试

- Config 迁移幂等，旧 custom prompt 语义不变。
- 任务启动后修改 Config/平台/工作台不影响上下文。
- JSON 与 SQLite snapshot round-trip 一致，缓存中无凭据。
- 继续任务复用旧 snapshot，重新开始创建新 snapshot 并保留长期资产。
- structured/JSONLINE 支持乱序重排，拒绝重复、缺失、负数、越界、非整数、1-based 和额外索引。
- 任何对齐失败都不能进入 ResponseChecker 或写回。
- 五种 base 模式互斥，style 独立且每请求只有一个输出协议。
- 空资产不注入，禁用资产不注入；冲突、排序和预算结果可重复。
- `POLISHED` 参与条目统计、续译、重置、筛选和全部文件写回，但不用于项目状态。
- 润色/校对失败不修改原译文和原状态。
- `QUALITY` 与初译、平台测试、工作台分析互斥；取消只停止后续批次，已完成批次可重载。
- `polishing_progress`/`proofreading_progress` 按 schema 持久化，缺快照时安全失败且不泄露凭据。
- 质量报告可稳定格式化错误统计，并按报告索引选择条目启动校对。
- 暂停、关闭、重开后续译仍使用原快照。
- 现有 Ren'Py、RPA、字体、hook、源码翻译和 Android 回归测试保持通过。

## 13. 首版明确排除

- `<why>` 或可见思维过程。
- 全局 Top-K 术语无条件注入。
- 自动全管线串联。
- 重写 Ren'Py 抽取与工具箱能力。
- 默认正则匹配。
- 没有版本历史时的译文回滚。

## 14. 质量任务 UI 与调度接线

本节接线已在 `future` 分支继续完成：

- 校对页提供独立的“AI 润色”“AI 校对”“质量报告”和“停止质量任务”命令。
- “AI 润色”只接收选中的 `TRANSLATED`；“AI 校对”接收选中的 `TRANSLATED`/`POLISHED`，并把当前结果检查错误类型传入核心任务。
- `QualityTaskCoordinator` 统一处理全局 busy、取消、分批进度、异常、回调与缓存保存。
- 质量任务从缓存中的 `translation_snapshot` 恢复语义，只合入当前 provider 凭据；不与初译自动串联，也不修改项目级 `TRANSLATED` 状态。
- 每个完成批次立即保存条目和对应进度分区；取消只阻止尚未开始的后续批次，当前批次正常完成并保存。
- 校对页可展示 `TranslationQualityReport` 的失败、fallback、索引/行数错位和错误类型统计，并按报告条目直接启动 AI 校对。

### 14.1 全局任务占用与取消

`Engine.Status` 增加 `QUALITY`。初译、平台测试、工作台分析和质量任务都必须通过原子状态切换抢占引擎：

```text
IDLE -> TESTING
IDLE -> TRANSLATING
IDLE -> QUALITY
```

任务结束时只能释放自己持有的状态，不能无条件覆盖后来任务的状态。质量任务期间：

- 初译、平台测试和工作台分析入口拒绝并发启动。
- 校对页保留已加载条目，但进入只读状态。
- 停止命令只设置取消标记，不强制中断当前网络请求。
- 润色与校对默认每批 8 条；停止只阻止尚未开始的后续批次，当前批次完成并
  保存后才结束，因此校对的最小取消粒度为当前批次（可通过 `batch_size=1`
  将校对调整为逐条取消）。

协调器公开接口：

```text
start_polishing(config, all_items, selected_items, ...)
start_proofreading(config, all_items, selected_items, warning_map=..., ...)
cancel()
is_busy()
get_progress()
```

`on_progress` 和 `on_done` 在 `ENGINE_QUALITY` 工作线程执行；Qt 页面必须通过 `pyqtSignal` 回到 UI 线程。

### 14.2 质量进度缓存

润色写入 `CacheProject.extras["polishing_progress"]`，校对写入 `CacheProject.extras["proofreading_progress"]`。两者使用同一 schema：

```json
{
  "schema_version": 1,
  "task_type": "POLISHER",
  "state": "RUNNING",
  "snapshot_id": "sha256:...",
  "total_count": 16,
  "completed_count": 8,
  "updated_count": 7,
  "failed_count": 1,
  "skipped_count": 0,
  "batch_count": 1,
  "total_batch_count": 2,
  "input_tokens": 1200,
  "output_tokens": 500,
  "failures": [
    {"item_index": 5, "reason": "VALIDATION_FAILED", "attempts": 1}
  ],
  "error_type_counts": {"VALIDATION_FAILED": 1},
  "cancel_requested": false,
  "error_message": "",
  "started_at": "2026-07-25T00:00:00+00:00",
  "updated_at": "2026-07-25T00:00:05+00:00",
  "completed_at": ""
}
```

`state` 只允许 `RUNNING`、`COMPLETED`、`CANCELLED`、`FAILED`。缓存中不得写入 API key、token、password 或包含凭据的 provider 运行对象。

### 14.3 失败边界

- 缺少 `translation_snapshot`、快照版本不支持或当前没有可用 provider 时，质量任务写 `FAILED` 并向 UI 返回明确错误，不回退到当前可变配置重新构造语义。
- 单条或单批失败时保留原 `dst/status/metadata`；只有通过确定性复验的结果才能写 `POLISHED`。
- 核心任务在当前批次中途抛出异常时，协调器恢复该批次全部条目的 `dst/status/metadata`，再保存 `FAILED` 进度。
- 项目状态始终保留 `TRANSLATED`。
- UI 关闭、取消或任务异常后，已经完成并保存的批次不得丢失。

## 15. 路径、项目资产与停止边界

### 15.1 Ren'Py 路径契约

所有页面通过 `module.Renpy.ProjectPaths.RenpyProjectPaths` 从“项目根目录 + 目标语言”派生路径，禁止各页面自行拼接旧路径：

```text
翻译输入：<项目>/game/tl/<lang>
增量输入：<项目>/game/tl/<lang>_new
翻译输出：<项目>/RenpyBox_Translation/<lang>
增量输出：<项目>/RenpyBox_Translation/<lang>_new
应用目标：<项目>/game/tl/<lang>
```

每次一键翻译、增量翻译和 hook 运行都会写入项目内的 `.renpybox_last_run_<lang>.json`。校对页和 Token 估算页先校验项目键、语言和输出目录，再恢复最近一次实际运行缓存；显式指定的自定义输出优先于旧清单。若 hook 在恢复主配置前异常退出，载入顺序固定为主缓存、增量缓存、hook 缓存，避免补漏子集遮蔽完整翻译。应用增量翻译时，除语义合并 RPY 文件外，还必须把增量缓存条目合并到主缓存，并在成功后把运行清单指回主输出；缓存迁移失败时保留 `<lang>_new/cache`，不得静默删除。`<lang>_new`、`None` 和跨语言目录只作为运行变体或非法输入处理，不会创建新的项目身份。

### 15.2 角色工作台与轻量 RAG

一键流程在翻译前复用 `CharacterScanner` 扫描角色名、说话样本、共现关系和变量引用：角色结果进入项目资产候选/角色草稿，变量进入禁翻表，不能绕过项目资产直接写入全局术语表。翻译开始时生成不可变资产快照；提示词按当前批次匹配世界观、角色卡、术语和禁翻项，并受 `asset_prompt_token_budget` 与条目数量限制。当前使用确定性的批次匹配，不引入向量数据库；只有在项目规模和召回质量证明必要时才评估向量 RAG。

### 15.3 Token 估算

Token 估算使用与实际翻译相同的输入目录、批次行数、文件边界、主提示词和项目资产上下文。优先使用 `o200k_base`/`cl100k_base`，编码器不可用时退回 UTF-8 字节近似；估算失败不能创建后台缓存服务线程，也不能把上一个项目的内存缓存用于当前项目。

### 15.4 立即停止与旧线程隔离

停止操作先设置取消标记、取消排队任务并在锁外释放 SDK 客户端；退避等待、文件扫描、AST 解析和流式响应都必须可响应取消。停止 watcher 只等待停止时已存在的工作线程，并设置有界清理期限。旧线程绑定线程级取消标记，清理期限后即使新任务开始，旧回调也不能继续请求或写入新任务缓存；停止屏障期间禁止新的翻译、质量任务和单条重译抢占引擎。

## 16. 本轮验证状态

- 已覆盖质量任务核心、协调器、快照语义恢复、当前凭据合入、分批保存、取消边界、全局 busy 拒绝和质量报告选择逻辑的自动化测试。
- 仍需在带真实 Qt 窗口和真实 provider 的环境执行一次人工冒烟：命令栏布局、长文本显示、任务停止交互和实际 API 响应。该验证不要求构建安装包。
