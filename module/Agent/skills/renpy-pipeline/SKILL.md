---
name: renpy-pipeline
description: Ren'Py 游戏汉化的完整流水线判据与执行顺序，用户要求解包、反编译、抽取、翻译、回填、打补丁中任意一段或全流程时使用
---

# Ren'Py 汉化流水线

## 顺序不可颠倒

```
设定项目 → 解包 RPA → 反编译 RPYC → 抽取文本 → 启动翻译 → 查询进度 → 回填译文 → 刷新兜底
```

每一步的输出是下一步的输入。跳过任何一步都会让后面拿到空数据或旧数据。

## 每步的判据

### 0. 设定项目
用户没给路径就不要猜。任何工具返回 `PROJECT_NOT_SET` 时，停下来问用户游戏根目录，拿到路径再 `set_project`。

### 1. 解包 RPA
判据：`list_rpa_files` 返回 `rpa_count > 0` 且 `unpack_required` 为真。
工具：`unpack_rpa_files`。会写入 game 目录，必须让界面确认。
不要重复解包：`unpack_required` 为假说明已经解过。

### 2. 反编译 RPYC
判据：game 目录里有 `*.rpyc` 但没有对应的 `*.rpy`，或体检返回 `DECOMPILE_SCRIPTS`。
工具：`decompile_rpyc_files`。会覆盖同名 `.rpy`，必须确认。
`RPYC_NOT_FOUND` 不是错误——说明这个游戏直接给了 `.rpy`，跳过本步。

### 3. 抽取文本
工具：`run_project_extraction`。
- 返回 `NEED_UNPACK` → 回到第 1 步
- 返回 `NEED_DECOMPILE` → 回到第 2 步
- 返回 `EXTRACTION_FAILED` → 让用户看日志，不要自己重试第三次

增量 vs 全量：已有译文时默认增量（`incremental=true`），只处理新增条目；首次抽取或用户要求重来时用全量。用户没有明确要求重来时**不要**用全量，那会覆盖已有译文。

### 4. 启动翻译
前置：`translation_status` 显示 `engine_status` 为 idle，且 `untranslated_count > 0`。
工具：`start_translation`。
- `accepted=true` 只代表请求被受理，**不代表翻译已经开始**。真实进度以 `translation_status` 为准。
- 不要连续调用两次。第二次会拿到 `ENGINE_BUSY`。
- `mode=source` 被禁用（源码备份路径耗时长），需要时让用户在翻译页手动启动。

### 5. 查询进度
工具：`translation_status`。只读，翻译进行中也可以调用。
看 `progress.percent` 判断完成度，`untranslated_count` 判断还剩多少条。
翻译是长任务，不要在单轮里反复轮询——把进度告诉用户，让用户决定何时再看。

### 6. 停止
工具：`stop_translation`。用户主动要求停止时才调用。
停止之后**不要**在同一轮里自动重启翻译。

### 7. 回填译文
判据：翻译完成（`untranslated_count` 为 0 或用户确认可以了）。
工具：`apply_translation`。会覆盖游戏里的 tl 目录，必须确认。
`NO_OUTPUT_FILES` 说明还没翻译完或输出目录不对。
`APPLY_TARGET_INVALID` 说明配置里的输入/输出目录缺失，让用户在设置里补。

### 8. 刷新兜底补丁
判据：体检返回 `REFRESH_REPLACE_FALLBACK`，或用户反馈"补充抽取的文本没生效"。
工具：`refresh_replace_fallback`。已是最新时会返回 `refreshed=false`，这是正常结果。

## 全流程请求怎么处理

用户说"帮我汉化这个游戏"这类全流程请求时：

1. 先 `inspect_translation_project` 看现状，不要从第一步无脑开始。
2. 按 `next_action_code` 决定起点，而不是永远从解包开始。
3. 每一步做完向用户报告结果，再进下一步——解包和回填都有覆盖风险，需要用户在场。
4. 任何一步返回失败码，停下来解释，不要跳过继续。

## 常见误判

- `accepted=true` 不等于翻译已开始，必须用 `translation_status` 复核。
- 体检报告是**建议**，不是已执行。不要声称已经做了建议里的操作。
- 抽取成功不代表有翻译，`entry_count` 为 0 说明项目里没有可翻译的文本。
- 反编译失败通常是缺 unren 工具，此时应让用户手动处理，不要反复重试。
