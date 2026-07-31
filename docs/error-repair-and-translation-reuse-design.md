# 通用 BUG 扫描 / 重复 old-new 处置 / 更新翻译复用 实现说明

对应 issue [#22](https://github.com/Dclef/renpybox/issues/22) 的第 1、4、5 条。第 2、3 条
（画廊解锁、修改器注入）见同级的 [game-mod-injection-design.md](game-mod-injection-design.md)。

本文记录已经落地的行为和最终决策，不再作为待办方案使用。三个需求共用一个原则：扫描可以积极，
写入必须保守；无法无歧义修复的内容只报告，不猜测用户原意。

## 1. 最终范围与状态

| issue | 最终处理 | 状态 |
| --- | --- | --- |
| 1 | 用静态通用 BUG 扫描替代运行时弹窗识别 | 已实现 |
| 4 | 同文件和跨文件重复 `old/new` 默认注释，可配置为删除 | 已实现 |
| 5 | 按原文把旧译文安全复用到新版本的空条目 | 已实现 |

第 1 条不做 OCR，也不监听游戏崩溃弹窗。Ren'Py `lint` 和翻译文件静态扫描能在应用译文前给出
文件及行号；等弹窗出现时游戏已经停止运行，修复时机太晚。深度 lint 入口复用
[ErrorRepairer.py](../module/Tool/ErrorRepairer.py) 的 `exec_renpy_lint()` 和
`parse_lint_errors()`，通用翻译检查走同一文件的 `check_file()` / `check_folder()`。

## 2. 引号安全修复

### 2.1 根因是全局作用域，不是执行顺序

旧实现对整行执行中文弯引号到英文直引号的 `str.replace`。它不理解字符串边界，例如：

```renpy
define quote_text = "他说“你好”"
```

若全局替换，会得到无法解析的 `define quote_text = "他说"你好""`。另一方面，合法译文：

```renpy
new "他说“你好”，然后走了"
```

正文里的中文引号本来就是内容，不应改动。这里的缺陷是替换范围过大；把两个修复步骤简单调换
不能解决问题，因为未转义直引号修复器不会把中文弯引号当作待转义字符。

### 2.2 已实现行为

[ErrorRepairer.py](../module/Tool/ErrorRepairer.py) 现在拆成两个保守操作：

- `repair_unescaped_dialogue_quotes()` 只处理能明确识别的 Ren'Py 对话、`old`、`new` 行，
  只转义正文内成对出现的未转义直双引号；Python 表达式、菜单条件、screen action、三引号、
  注释等歧义结构保持原样。
- `repair_curly_string_delimiters()` 只把明确充当整条字符串**外层定界符**的中文弯引号规范化，
  字符串正文和行尾注释中的中文引号保持原样。
- 两个操作都要求幂等；同一文件重复执行不会叠加反斜杠。
- 撇号不再按全行奇偶数判断，`old "I don't know"` 不会误报单引号不匹配。

[ErrorRepairPage.py](../frontend/RenpyToolbox/ErrorRepairPage.py) 中两个写入型选项
「规范化外层中文引号」和「修复未转义引号」均**默认关闭**；
`auto_fix_file(..., fix_quotes=False, fix_dialogue_quotes=False)` 的后端默认值也保持关闭。
扫描仍会报告可确认的引号问题，是否写入由用户显式选择。

原来的「修复编码问题」死勾选框已移除。读取编码继续由后端参数明确传入，不提供一个没有实现语义的 UI 开关。

## 3. 通用 BUG 扫描

### 3.1 公共接口

扫描沿用 [ErrorRepairer.py](../module/Tool/ErrorRepairer.py) 的统一结果结构：

```python
check_file(
    file_path,
    ...,
    check_translation_issues=True,
) -> list[dict]
check_folder(
    folder_path,
    ...,
    check_translation_issues=True,
) -> dict[str, list[dict]]
```

每条问题包含 `line`、`type`、`message`、`content`；目录扫描按文件路径聚合。
[ErrorRepairPage.py](../frontend/RenpyToolbox/ErrorRepairPage.py) 保存最近一次扫描结果，并可通过已有的
`export_error_report()` 导出 Excel。报告保留完整文件路径，并把占位符计数、原文行号、重复项首次位置等
附加字段写入结构化详情列。扫描、自动修复和 lint 都在后台线程执行，完成后通过 Qt 信号回主线程。

### 3.2 翻译专项规则

翻译专项检查以解析后的成对条目为单位，同时覆盖 strings 块的 `old/new` 和 label 翻译块的模板/目标语句。
最终行为如下：

| 检查 | 报告类型 | 判定 | 处理 |
| --- | --- | --- | --- |
| 占位符缺失/额外 | `placeholder_missing` / `placeholder_extra` | 分别用 `Counter` 统计原文和译文中的 `[name]`、`{name}` 等占位符，比较种类和出现次数 | 只报告 |
| 占位符疑似被改写 | `placeholder_rewritten` | 同类括号中原占位符消失、同时出现新占位符 | 只报告 |
| 换行不一致 | `linebreak_mismatch` | 解析后的原文和译文换行数量不同 | 只报告 |
| 空字符串残留 | `extra_empty_string` | 目标语句中空字符串与其他字面量无分隔相邻；只有一个空目标字面量（包括 `new ""`）不报 | 只报告 |
| 重复 `old/new` | `duplicate_old_new` | 同一语言的同一原文在 strings 条目中重复注册 | 报告；实际处置走第 4 节统一去重接口 |

占位符必须比较 `Counter`，不能只比较集合：`[name]` 在原文出现两次、译文只剩一次同样属于丢失。
这些语义问题全部只报告。尤其占位符不能自动补回，因为插入位置需要猜测；猜错的位置比缺失本身更难排查。

### 3.3 Lint 只报告，不自动改写

`fix_by_lint()` 仍保留在后端以兼容旧代码，但**不接 UI**。它的历史策略曾对无法识别的语句执行清空或
替换，因此不作为面向用户的自动修复能力。后端现已额外收紧为安全类型白名单：每轮最多修改一处可确认的
引号或缩进问题，随后立即重新 lint；未知语句、重复翻译、空块等类型不写文件。
[ErrorRepairPage.py](../frontend/RenpyToolbox/ErrorRepairPage.py) 的深度 lint 卡片只调用
`exec_renpy_lint()`、解析并展示结果，不提供「Lint 并自动修复」按钮。

扫描报告可以导出；lint 和通用扫描都不会因为“发现问题”而自动写游戏文件。

## 4. 重复 old-new 统一处置

### 4.1 单一实现与默认策略

[renpy_extract.py](../module/Renpy/renpy_extract.py) 提供两个入口：

```python
remove_repeat_for_file(path, duplicate_action="comment")
remove_repeat_extracted_from_tl(
    tl_dir,
    is_py2,
    cross_file_dedup=True,
    duplicate_action="comment",
)
```

同文件和跨文件去重都复用 `_mark_duplicate_entry()`，默认 `duplicate_action="comment"`。
兼容旧行为时可传 `"delete"`。全局配置
[Config.py](../module/Config.py) 的 `renpy_duplicate_string_action` 默认也是 `"comment"`，
[ExtractTab.py](../frontend/RenpyToolbox/ExtractTab.py) 和统一抽取流程会把该值传给去重函数。

注释模式输出可追踪记录，例如：

```renpy
# [renpybox] duplicate; first at a_first.rpy:12
# old "Same text"
# new "重复译文"
```

原有相邻注释不会被吞掉。跨文件扫描先按相对路径稳定排序，再保留第一次出现，因此记录中的来源位置
在不同文件系统上可重复。

### 4.2 只有重复项的 strings 块

如果一个 `translate <lang> strings:` 块只剩被注释的重复项，活动块头也会被注释：

```renpy
# translate chinese strings:
    # [renpybox] duplicate; first at a_first.rpy:12
    # old "Same text"
    # new "重复译文"
```

这样既保留审计记录，也不会把「非空但无有效语句」的活动块交给 Ren'Py 解析。删除模式则继续清掉整个空块。

### 4.3 调用面

目录级入口 `remove_repeat_extracted_from_tl()` 在生产代码中有 4 个直接调用点：

- [renpy_extract.py](../module/Renpy/renpy_extract.py) 的补充抽取收尾；
- [UnifiedExtractor.py](../module/Extract/UnifiedExtractor.py) 的增量目录合并；
- 同文件中的统一后处理；
- [ExtractTab.py](../frontend/RenpyToolbox/ExtractTab.py) 的手动清理入口。

另有 1 个直接测试模块 [test_renpy_extract.py](../tests/module/test_renpy_extract.py)，其中覆盖同文件、
跨文件、幂等、稳定首项、仅注释空块和 `delete` 兼容行为。修改去重语义时必须同时考虑常规抽取、
增量抽取、增量目录合并和手动清理，不能另写第二套匹配逻辑。

## 5. 更新翻译复用

### 5.1 公共接口

[UnifiedExtractor.py](../module/Extract/UnifiedExtractor.py) 已提供正式入口：

```python
preview_translation_reuse(source_tl_dir, target_tl_dir) -> TranslationReuseResult
reuse_translations(source_tl_dir, target_tl_dir) -> TranslationReuseResult
```

旧译文来源只收集 `new != ""` 且 `new != old` 的 `{原文: 译文}`。匹配键是解析后的**原文文本**，
不依赖 Ren'Py translate label 中的哈希，因此游戏更新导致哈希变化时仍可复用。

### 5.2 安全规则

- 目标 `new` 为空或 `new == old` 时才允许填入旧译文。
- 目标已有相同译文时计入 `already_reused`，不重复写入。
- 目标已有其他非空译文时计入 `conflicts`，绝不覆盖。
- 找不到同原文旧译文的条目计入 `unmatched_entries`。
- `preview_translation_reuse()` 全程只读，返回统计但不创建备份、不写文件。
- `reuse_translations()` 默认先完整备份目标 tl 目录，再执行写入；标准 `game/tl/<语言>` 目录的备份放在
  项目根目录，避免 Ren'Py 递归加载备份中的 `.rpy`。没有可复用条目时不制造空备份。
- 来源、目标目录必须存在且不能是同一路径。

`TranslationReuseResult` 同时返回来源译文数、目标条目数、匹配数、可复用数、实际写入数、已一致数、
冲突数、未匹配数和备份路径，UI 不需要重新扫描或实现另一套统计。

### 5.3 工具箱入口

[TranslationReusePage.py](../frontend/RenpyToolbox/TranslationReusePage.py) 已注册到
[ToolRegistry.py](../frontend/RenpyToolbox/ToolRegistry.py) 的工程工具组，图标由
[ToolIcon.py](../frontend/RenpyToolbox/ToolIcon.py) 提供。页面接受旧版和新版的具体 `game/tl/<语言>` 目录，
支持只读预览与执行复用；页面执行入口始终先备份。两个操作都在后台线程运行，冲突、已一致、未匹配和备份路径
会显示在结果区。

## 6. 测试与约束

自动化覆盖分布如下：

| 文件 | 覆盖内容 |
| --- | --- |
| [test_error_repairer.py](../tests/module/tool/test_error_repairer.py) | 引号边界、正文中文引号保留、撇号误报、歧义行失败关闭、幂等、通用扫描规则 |
| [test_error_repair_page.py](../tests/frontend/test_error_repair_page.py) | 写入选项默认值、后台任务互斥、扫描结果保存与导出、lint 只读入口 |
| [test_renpy_extract.py](../tests/module/test_renpy_extract.py) | 同文件/跨文件去重、注释空块、来源稳定、删除兼容、幂等，以及常规/增量抽取流程回归 |
| [test_translation_reuse.py](../tests/module/test_translation_reuse.py) | 只读预览、空值和 `new == old` 占位写入、冲突保护、备份、二次执行幂等、路径校验 |
| [test_translation_reuse_page.py](../tests/frontend/test_translation_reuse_page.py) | 页面目标目录预填、备份默认值和操作入口 |
| [test_toolbox_ui.py](../tests/frontend/test_toolbox_ui.py) | 工具注册及页面可加载性 |

最终约束：

- 通用扫描新增规则默认只报告，不借 `fix_by_lint()` 猜测性改写源码。
- 两个引号写入选项默认关闭；开启后也只处理可无歧义识别的结构。
- 重复处置默认注释；只有用户配置 `delete` 时才恢复旧的破坏性行为。
- 译文复用只能调用公开的预览/执行接口，禁止复制 `_get_existing_translations()` 或匹配逻辑另写一份。
- 任何新增写入路径都要有临时目录测试；面向整个 tl 目录的迁移操作必须先备份。
