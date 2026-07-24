# RenpyBox 翻译管线整体改造设计

> 状态：`future` 分支实施基线
>
> 基线：RenpyBox v0.6.0 (`e75c2ce`)
>
> 编写日期：2026-07-24
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
6. 定向重试、质量报告与端到端回归。

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
- 暂停、关闭、重开后续译仍使用原快照。
- 现有 Ren'Py、RPA、字体、hook、源码翻译和 Android 回归测试保持通过。

## 13. 首版明确排除

- `<why>` 或可见思维过程。
- 全局 Top-K 术语无条件注入。
- 自动全管线串联。
- 重写 Ren'Py 抽取与工具箱能力。
- 默认正则匹配。
- 没有版本历史时的译文回滚。

## 14. `future` 首次提交后的接线任务

核心 `PolisherTask`、`ProofreadTask`、严格响应协议、质量校验和 `POLISHED` 状态已实现并有模块测试。本次首次提交不仓促加入尚未完整验证的质量任务 UI 调度层，后续继续完成：

- 在校对页增加独立的“AI 润色”和“AI 校对”命令；前者只接收选中的 `TRANSLATED`，后者接收选中的 `TRANSLATED`/`POLISHED` 和当前错误类型。
- 增加质量任务协调器，统一处理 busy、取消、分批进度、异常和缓存保存；运行时阻止初译、平台测试和工作台分析并发启动。
- 从缓存中的 `translation_snapshot` 恢复质量任务语义，只合入当前 provider 凭据；不得与初译自动串联或修改项目级 `TRANSLATED` 状态。
- 每个成功批次保存条目并更新 `polishing_progress` 或 `proofreading_progress`；取消只阻止后续批次。
- 在校对页展示 `TranslationQualityReport` 的失败、fallback、索引错位和错误类型统计，并允许按报告选择条目启动校对。
- UI 验收必须覆盖成功写 `POLISHED`、失败保持原 `dst/status/metadata`、取消后不丢已保存批次，以及缓存和日志不出现任何运行凭据。
