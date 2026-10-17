---
name: rpy-syntax
description: Ren'Py 脚本语法与常见汉化故障，涉及脚本报错、缩进、标签、字符串引号问题时使用
---

# Ren'Py 语法要点

## 缩进是语法

Ren'Py 用缩进定义块结构，和 Python 一样。四个空格一层，不能混用 Tab。

抽取和回填流程会保留缩进，但人工改过的文本容易破坏它。看到 `IndentationError` 或 `TabError` 时先查缩进。

## 字符串

```renpy
"普通对话"

e "角色说话"

"带插值：[player_name]，你好。"

'单引号也可以'

"转义引号：\"你好\""
```

译文里如果出现英文双引号 `"`，必须转义成 `\"`，否则字符串提前结束，脚本报错。中文引号 `""` 不需要转义。

## 标签与跳转

```renpy
label start:
    ...
    jump chapter2

label chapter2:
    ...
    return
```

`label` 名不要翻译。`jump`、`call` 后面的目标名不要翻译。

## 菜单

```renpy
menu:
    "要接受吗？":
        jump accept
    "拒绝":
        jump refuse
```

菜单选项的文字可以翻译，`jump` 目标不能。

## 翻译文件结构

```renpy
translate chinese label_1_2a3b4c:
    # e "Hello"
    e "你好"
```

- `translate <语言> <标识符>:` 这一行不能改
- `# e "Hello"` 是原文字面量的注释，由工具生成，不要删
- 缩进层级要对齐

## 四种汉化落地方式

| 方式 | 位置 | 适用 | 风险 |
|---|---|---|---|
| tl 翻译文件 | `game/tl/<语言>/*.rpy` | 标准方式，覆盖对话与菜单 | 需要重新抽取，游戏原有逻辑不受影响 |
| replace_text 补丁 | `game/replace_text_auto.rpy` | 补漏，处理 tl 不覆盖的运行时字符串 | 全局字符串替换，可能误伤 |
| 直接改源文件 | `game/*.rpy` | 不推荐 | 会被后续解包覆盖，无法增量 |
| 字体替换 | 替换字体文件 | 中文显示为方块时 | 可能破坏排版 |

## 常见故障对照

| 现象 | 原因 | 处理 |
|---|---|---|
| 游戏启动报 `expected statement` | 译文里有未转义引号或破坏缩进 | 用 `scan_script_errors` 定位 |
| 中文显示成方块 | 字体不支持中文 | 用字体替换功能 |
| 部分文字还是原文 | 该字符串不在 tl 覆盖范围 | 生成 replace_text 兜底 |
| 文本溢出对话框 | 译文过长或换行丢失 | 缩短译文或补换行 |
| `NameError: name 'xxx' is not defined` | 变量插值被翻译了 | 还原方括号内容 |
| 存档读档后文字变回原文 | 使用了直接改源文件方式 | 改用 tl 翻译文件 |

## 排错顺序

1. `scan_script_errors` 扫描当前语言目录
2. 按报错定位到具体文件和行
3. 对照上表判断原因
4. 修完重扫，确认清零
