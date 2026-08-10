# 解锁画廊 / 修改器 注入功能设计

对应 issue [#22](https://github.com/Dclef/renpybox/issues/22) 的第 2、3 条。本文是给实现者（CODEX）的落地方案，
issue 里的第 1、4、5 条（修 bug、重复 old/new、更新翻译复用）不在本次范围内。

## 1. 目标

在 Ren'Py 工具箱里新增一个入口，把预置的第三方或 RenpyBox 自研 mod 注入用户的游戏目录：

- **解锁画廊**：注入后游戏内出现自研「MOD」面板，可随时「开启全部画廊」或「恢复游戏原本的画廊进度」。
- **修改器**：注入 0x52-URM（通用游戏数据修改器，汉化版），游戏内可打开修改器界面。

**本次只做 PC / 模拟器版，不做安卓版。** 画廊解锁器官方就没有安卓版；安卓 URM 是 29M 加密 .7z、
装法也不同（`assets/x-game`）。UI 上要明确写出「暂不支持安卓」。

## 2. 已确认的现状

### 2.1 现有素材（`resource/tools/`，共 159M）

| 路径 | 内容 | 处置 |
| --- | --- | --- |
| `__ugu.rpy` | 单文件版画廊解锁器，206 行，ZLZK 2023-04-03 | 参考实现，见 4.2 |
| `通用游戏设置菜单修改模组/6.27版独木桥模组/模拟器及电脑版/dumuqiao.rpy` | 独木桥模组，930 行，52K，中文 | **移除** |
| `.../通用画廊解锁器 无安卓版/画廊解锁器/软版/` | ZLZK UGU soft，7 个 rpy，56K | **保留** |
| `.../通用画廊解锁器 无安卓版/画廊解锁器/硬版/` | ZLZK UGU hard，5 个 rpy，36K | **保留** |
| `.../汉化版0x52 通用游戏数据修改模组/0x52-URM-2.6.2.rpa` | URM 修改器，RPA-3.0，12M，68 个条目 | **保留** |
| `安卓安装独木桥模组教程.mp4` | 106M 视频 | **删除** |
| `安卓版0x52_2.7z` | 安卓 URM，29M | **删除** |
| `6.27版独木桥模组/安卓版/`、`旧版独木桥模组/`、`6.27版独木桥模组.7z`、`0x52-URM 2.6.2.7z`、`0x52-URM-2.6.2.zip`、`画廊解锁器.7z`、`通用游戏选项提示攻略模组 无安卓版/` | 安卓版、旧版、与已保留内容重复的压缩包、无关模组 | **删除** |

删除后随包体积约 **12.2M**（主要是 URM 的 rpa）。`main.spec` 会把整个 `resource/` 打进 exe
（`main.spec:20`），所以不精简的话 exe 会直接 +159M。

**独木桥模组是什么**：一个通用的游戏设置菜单 mod。它接管游戏底部快速菜单
（`screen dumuqiao_custom_quick_menu`，`dumuqiao.rpy:170`），提供自定义按钮栏 +
一个「模组」设置面板（Alt+9 唤出），可调字号、文本框、对话框宽度，并预留了「作弊1~5」按钮位
（`dumuqiao.rpy:230-248`，只是 `ShowMenu("cheatmenu")` 之类的入口，需要游戏本身装了作弊 mod 才有用）。
它就是 issue 里说的「底部按钮栏」的提供者。**它自己没有 URM 入口，也没有画廊开关**，
这两个按钮需要我们自己的 hook 脚本加。由于它会接管游戏菜单且与其他 overlay 容易冲突，现已
不再随 RenpyBox 分发；旧安装仅提供显式清理，不会在升级时自动删除。

### 2.2 现有的注入范式（要复用）

「添加语言入口」就是把 `resource/hooks/*.rpy` 复制进 `game/`：

```
frontend/RenpyToolbox/AddLanguageEntrancePage.py:157-165
    hook_source = Path(get_resource_path("resource", "hooks", "hook_add_change_language_entrance.rpy"))
    target = Path(game_dir) / "hook_add_change_language_entrance.rpy"
```

用户明确要求「跟切换中文一样做一个按钮」，所以本功能走同一条路：**复制 rpy 进 game/，卸载就删文件**。
资源定位统一用 [PathHelper.py](base/PathHelper.py) 的 `get_resource_path()`，它已经处理了源码运行和
PyInstaller 打包两种情况。

### 2.3 .gitignore 会吞掉 URM（✅ 已修）

[.gitignore:11](.gitignore#L11) 的 `*.rpa` 原本让 `0x52-URM-2.6.2.rpa` 处于 ignored 状态，
不修的话 mod 本体进不了仓库、CI 打出来的包会缺文件。已加否定规则：

```gitignore
*.rpa
# 随包分发的模组本体需要入库
!resource/mods/**/*.rpa
```

注意 `git check-ignore -v` 对否定规则会打印命中的那条 `!` 规则并返回成功，容易误判成「仍被忽略」；
用 `git add -n resource/mods/` 看文件是否出现在待添加列表才是可靠的判断方式。

## 3. 资源目录重组（✅ 已完成）

已把要保留的东西从 `resource/tools/`（那是解包工具的地盘：`rpatool`、`unren_rpatool.py`）挪到
`resource/mods/`，第 2.1 节标「删除」的素材已全部移除。现状：

```
resource/mods/                          # 共 12M
├── README.md                           # 来源、作者、soft/hard 差异、已知限制
├── gallery_unlock/
│   ├── hook_gallery_unlock.rpy         # 画廊开关与自研 MOD 面板（唯一注入物）
│   └── upstream/                       # ZLZK 原版，仅存档参考，不注入
│       ├── __ugu.rpy                   # 单文件版参考实现
│       ├── soft_safe/         (7 rpy)  # 上游「软版」，效果差但安全
│       └── hard_aggressive/   (5 rpy)  # 上游「硬版」，有效但风险大，tools(1) 已还原
└── urm/
    ├── 0x52-URM-2.6.2.rpa              # 12M，原样复制进 game/
    └── hook_urm_button.rpy             # 仅装 URM 时的独立入口
```

上游 soft/hard 目录已按含义重命名（原名只是「软版」「硬版」）。三份上游说明 txt 的内容已归并进
`resource/mods/README.md`，原文件删除。

`resource/tools/` 现只剩 `rpatool` 和 `unren_rpatool.py`（28K）。
`.gitignore` 已加 `!resource/mods/**/*.rpa`，`git add -n` 确认 rpa 可入库。
复制前后所有文件已逐字节校验一致。

## 4. 功能设计

### 4.1 页面与注册

新增 [frontend/RenpyToolbox/GameModPage.py](frontend/RenpyToolbox/GameModPage.py)，
业务逻辑放 [module/Tool/ModInjector.py](module/Tool/ModInjector.py)（与 `FontReplacer`、`Packer` 同级）。

在 [ToolRegistry.py](frontend/RenpyToolbox/ToolRegistry.py) 的 `TOOL_SPECS` 末尾加一条，归到 `ENGINEER` 组：

```python
ToolSpec(
    "game_mod",
    "游戏模组注入",
    "注入解锁画廊、修改器等通用模组",
    ENGINEER,
    object_name="game-mod",
    icon=ToolIcon.MOD,
    lazy_import="frontend.RenpyToolbox.GameModPage:GameModPage",
),
```

`ToolIcon` 里加 `MOD = "wand-2"`（或其他 Lucide 名），并把同名 svg 放进
`resource/icons/toolbox/`。图标必须包含 `currentColor` 才能跟随主题
（[ToolIcon.py:15](frontend/RenpyToolbox/ToolIcon.py#L15) 做字符串替换）。

页面结构照抄 [FontReplacePage.py](frontend/RenpyToolbox/FontReplacePage.py)：
`TitleLabel` + `SingleDirectionScrollArea` + 若干 `CardWidget`，并调用
`mark_toolbox_widget` / `mark_toolbox_scroll_area`。

布局：

1. **说明卡**：标明第三方来源和 RenpyBox 自研内容、用完建议移除、仅 PC。
2. **游戏目录卡**：`LineEdit` + 浏览按钮。复用 `FontReplacer._resolve_game_dir` 的同款逻辑
   （传项目根则自动补 `game/`），并显示各 mod 当前是否已安装。
3. **解锁画廊卡**：安装 / 卸载按钮。
4. **修改器卡**：安装 / 卸载按钮。
5. **内置修改器卡**：安装 RenpyBox 自研 Hook，提供对话框、选项框和快捷菜单调整，不覆盖游戏原有 screen。
6. **旧版迁移提示**：仅检测到旧版独木桥文件时，显示明确的清理按钮；仅删除两个确定文件，保留 `.bak`。

### 4.2 解锁画廊

**为什么不直接用 ZLZK 原版**：原版 soft/hard 在 `init` 期硬 hook，装上即永久生效，游戏内没有开关，
满足不了 issue 要求的「解锁/锁住」切换。另外 hard 版目录名带 `(1)` 后缀
（`game(1)/_mods(1)/.../tools(1)/`），是下载时的重名产物，注入前得还原成 `game/_mods/...`。

**做法**：参照 `resource/tools/__ugu.rpy` 的思路重写一份单文件 hook，把每个 hook 包一层 persistent 判断。
`__ugu.rpy` 的核心就是 hook 四个点（`__ugu.rpy:153-183`）：

- `renpy.exports.seen_label` / `seen_image` / `seen_audio` → 恒 `True`
- `renpy.game.Persistent.__getattr__` / `__getattribute__` → 缺失或假值的持久变量翻成真值

改造成开关的形状（示意，不是最终代码）：

```renpy
default persistent._rb_gallery_unlocked = False

init 1000 python:
    def _rb_hook_seen(orig):
        def wrapper(*args, **kwargs):
            if persistent._rb_gallery_unlocked:
                return True
            return orig(*args, **kwargs)
        return wrapper
    renpy.exports.seen_image = _rb_hook_seen(renpy.exports.seen_image)
```

因为判断发生在每次调用时，切换开关立即生效，不用重启游戏。

**必须验证的兼容性问题**：`__ugu.rpy` 是 Python 2 写法 —— `str = unicode`（第 46 行）、
`if o is 0` / `if o is ""`（第 121、124 行）。Ren'Py 8 跑 Python 3，`unicode` 不存在，
字面量 `is` 比较也不可靠。ZLZK 2024 版之所以有 `PY2` 探测和 `pystr` 兜底
（`upstream/soft_safe/__namespace.rpy:20-27`），就是为了这个。**新 hook 必须写成 Python 3 兼容，
并在 Ren'Py 7 和 8 上各测一次。** 我没有实际跑过游戏，这条是纸面推断，请实测确认。

`__ugu.rpy` 还 hook 了 `utter_restart` 来卸载 hook（第 188-191 行），新实现也要保留，
否则开发模式下热重载会叠加包装。

**按钮**：同一个 rpy 里注册 overlay screen，在右上角显示「MOD」入口。点击或按 `F9` 打开
轻量面板；面板显示当前画廊状态，并提供「开启全部画廊」或「恢复游戏原本的画廊进度」。`F10`
直接切换画廊状态。后一项只关闭强制解锁，不会清空游戏已经记录的进度。

```renpy
textbutton "MOD":
    action ToggleScreen("_rb_game_tools")
```

挂载方式用 `config.overlay_screens.append(...)`，不能覆盖整个列表，否则会踩掉游戏或其他模组的 overlay。

**安装**：`resource/mods/gallery_unlock/hook_gallery_unlock.rpy` → `game/hook_gallery_unlock.rpy`。
**卸载**：删该文件 + 同名 `.rpyc`（Ren'Py 会缓存编译产物，只删 rpy 的话 rpyc 仍然生效，这是最容易漏的一步）。

### 4.3 修改器（0x52-URM）

按上游说明（已归并进 `resource/mods/README.md`）：rpa 直接丢进 `game/` 即可，不用解压。
已知限制：报 `API.rpyc` 错误时上游建议改用压缩包版，但该压缩包在精简时已删除，目前没有兜底。

**安装**：`resource/mods/urm/0x52-URM-2.6.2.rpa` → `game/0x52-URM-2.6.2.rpa`（12M，用
`shutil.copy2`；文件较大，考虑跟 `FontReplacePage` 一样丢后台线程 + 信号回主线程，别卡 UI）。
**卸载**：删该 rpa。

**「修改器」按钮**：已从上游 PC 压缩包确认真实入口是 `x52URM.Open()`，默认快捷键为 `Alt+M`。
画廊 Hook 已安装时，MOD 面板直接提供该入口；只安装 URM 时，伴随 `hook_urm_button.rpy` 提供独立按钮。
URM 自带 quick menu 和其中的 URM 按钮默认均关闭。伴随 Hook 不读取 URM 设置，以免其自定义属性访问抛出非标准异常。不要改成
`ShowMenu("URM_main")`，否则会绕过 URM 自己的欢迎页和警告流程。

## 5. ModInjector 接口

```python
class ModInjector:
    MODS: dict[str, ModSpec]          # key -> 资源相对路径、目标文件名、显示名
    def resolve_game_dir(self, path: str) -> Path
    def status(self, game_dir: str) -> dict[str, bool]     # 各 mod 是否已安装
    def install(self, game_dir: str, key: str) -> tuple[bool, str]
    def uninstall(self, game_dir: str, key: str) -> tuple[bool, str]
```

约束：

- 目标文件已存在时覆盖前先 `.bak`，别静默盖掉用户改过的版本。
- 卸载只删我们装的那几个确定文件名，**不要按目录递归删**。
- 所有失败走 `LogManager.get().error` + `InfoBar.error`，跟现有页面一致。

## 6. 测试

`tests/` 下加 `test_mod_injector.py`，用临时目录造假 `game/`：

- `resolve_game_dir`：传项目根、传 `game/`、传不存在的路径。
- 装 → `status` 全 True → 卸 → 文件都没了（含 rpyc）。
- 目标已存在时生成 `.bak`。
- 缺资源文件时返回失败而不是抛异常。
- 旧版独木桥清理只删除根目录 `dumuqiao.rpy/.rpyc`，保留 `.bak` 和其他用户脚本。

手工验收（自动化测不到，必须做）：Ren'Py 7 和 8 各拿一个真实游戏，装解锁画廊 → 进游戏打开 MOD
面板并切换画廊状态 → 装 URM → 确认面板可唤出修改器 → 只装 URM 时确认独立按钮可用 → 全部卸载 → 游戏能正常启动。

## 7. 风险

| 风险 | 说明 |
| --- | --- |
| Py2/Py3 | `__ugu.rpy` 是 Py2 写法，Ren'Py 8 上大概率报错。新 hook 已按 Py2/Py3 兼容写法实现，仍需 Ren'Py 7/8 实测确认。 |
| URM 入口兼容 | 已确认使用 `x52URM.Open()`；伴随 Hook 只判断入口存在，不读取第三方设置对象。 |
| URM 无兜底版本 | 上游建议 `API.rpyc` 报错时改用压缩包版，该包已在精简时删除，需要时得从上游重新下载。 |
| rpyc 残留 | 只删 rpy 不删 rpyc，卸载会失效。 |
| mod 冲突 | 自研面板只 append 自己的 overlay，不接管游戏原有快捷菜单。 |
| 版权与来源 | 画廊解锁器和修改器是第三方作品（ZLZK、0x52）；自研面板由 RenpyBox 提供。随包分发前确认许可，UI 和 README 里标注作者。 |
| 体积 | 精简后 +12.2M；不精简 +159M。 |

## 8. 实施顺序

1. ~~精简 `resource/tools/`，按第 3 节建 `resource/mods/`，修 `.gitignore`。~~ ✅ 已完成，CODEX 从第 2 步开始。
2. ~~写 `ModInjector` + 单测，支持画廊和 URM，并为旧版独木桥保留显式清理。~~ ✅ 已完成
3. ~~加 `GameModPage` + `ToolRegistry` 注册 + 图标，跑通装/卸。~~ ✅ 已完成
4. ~~写 `hook_gallery_unlock.rpy`，Ren'Py 7/8 双版本实测开关。~~ ✅ 代码已完成，待手工实测
5. ~~确认 URM 入口后，在 MOD 面板中补「修改器」按钮。~~ ✅ 已完成
