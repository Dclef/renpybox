# 画廊解锁 hook 设计（实施顺序第 4 步）

承接 [game-mod-injection-design.md](game-mod-injection-design.md) 的第 4 步。第 1~3 步（资源重组、
`ModInjector` + 单测、`GameModPage` + 注册 + 图标）已完成并通过测试，本文只讲**画廊解锁**这一个 mod
的落地，外加第 5 步（URM 按钮）的前置条件。

范围：写出 `resource/mods/gallery_unlock/hook_gallery_unlock.rpy`，把它接进现有 `ModInjector` /
`GameModPage`，补单测，然后在 Ren'Py 7 和 8 上各实测一次开关。

## 0. 先修一个已存在的缺陷

[ModInjector.install](../module/Tool/ModInjector.py#L90-L107) 备份并覆盖了 `.rpy`，但**没有清理同名
`.rpyc`**。`uninstall` 清了（`ModInjector.py:116-117`），`install` 没清。

后果：用户手工装过同名旧 hook 并让游戏编译出 `.rpyc`，之后用本工具安装时，
`shutil.copy2` 会连源文件的 mtime 一起复制过去（源文件在 PyInstaller 解包目录里，mtime 可能比那个
`.rpyc` 还旧）。Ren'Py 判断 `.rpyc` 是否过期依赖 rpy 的时间戳/摘要，一个"看起来更新"的旧 `.rpyc`
有让新装的 rpy 不生效的风险。加了画廊 hook 之后这个坑会更明显 —— 用户装完发现开关没出现，
而文件明明在那儿。

我没有实测过 Ren'Py 各版本 rpyc 新鲜度判定的确切实现（7.x 与 8.x 的 `script.py` 不完全一样），
所以这条是纸面推断。但无论判定细节如何，**安装时删掉旧 `.rpyc` 都是无损的**（Ren'Py 会重新编译），
成本极低，请直接做：

```python
# install() 内，copy2 之前
if target.exists():
    target.replace(target.with_name(f"{target.name}.bak"))
if spec.has_rpyc:
    target.with_suffix(".rpyc").unlink(missing_ok=True)
```

顺带补一条单测：装之前放一个假 `.rpyc`，装完断言它没了。

## 1. 为什么不直接用上游

`resource/mods/gallery_unlock/upstream/` 三份都是**装上即永久生效、游戏内没有开关**的形状，
满足不了 issue 要的"随时解锁 / 锁住"：

- `upstream/__ugu.rpy`（单文件版，206 行）：`init 1000` 期无条件 hook。
- `upstream/soft_safe/`（7 个 rpy）：`init 1400 python in _mods.ZLZK._base_`，同样无条件
  （`hijacks.rpy:19-38`），还额外 hook 了 `_m1_00gallery__GalleryArbitraryCondition.check`。
- `upstream/hard_aggressive/`（5 个 rpy）：更激进，风险更大。

我们要的是**同样的 hook 点 + 每次调用时读一个 persistent 开关**，所以重写一份单文件版。
上游继续只做存档参考，不注入。

## 2. 必须同时兼容 Python 2 和 3

这一条要纠正母文档第 4.2 节的说法。母文档写的是"新 hook 必须写成 Python 3 兼容"，但验收要求是
**Ren'Py 7 和 8 各测一次**，而 **Ren'Py 7.x 跑的是 Python 2，Ren'Py 8.x 跑的是 Python 3**。
所以目标不是"Py3 兼容"，是**两边都能跑**。硬约束：

- 不用 f-string（Py2 语法错误，整个 rpy 直接编译失败）。用 `"{}".format(...)` 或 `%`。
- 不用 `unicode`（Py3 没有）。`__ugu.rpy:46` 的 `str = unicode` 直接删掉，用内建 `str`。
- 不用 `:=`、不用类型标注、不用 `dict | dict`。
- 不写 `print x` 这种 Py2-only 形式。
- `o is 0` / `o is ""`（`__ugu.rpy:121,124`）两边都不可靠（CPython 字面量缓存是实现细节，
  Py3.8+ 还会给 `SyntaxWarning`）。改用显式类型判断，见 4.3。

上游 2024 版之所以有 `PY2` 探测和 `pystr` 兜底（`upstream/soft_safe/__namespace.rpy:20-27`）
就是为了这件事。我们靠"只用两边都合法的子集"来规避，比探测简单。

## 3. 注入物

单文件：`resource/mods/gallery_unlock/hook_gallery_unlock.rpy` → `game/hook_gallery_unlock.rpy`。
卸载删 `.rpy` + `.rpyc`。命名沿用 `resource/hooks/hook_add_change_language_entrance.rpy` 的
`hook_` 前缀习惯。

## 4. hook 实现要点

以下是设计约束和骨架，不是可直接粘贴的成品 —— 具体写法由实现者定，但下面每条都必须满足。

### 4.1 开关变量名必须以 `_` 开头

```renpy
default persistent._rb_gallery_unlocked = False
```

这不是风格问题，是**正确性问题**。因为我们要 hook `Persistent.__getattr__` 让缺失的持久变量返回
真值，而 hook 内部又要读自己的开关。上游用 `name.startswith("_")` 把下划线开头的名字排除在
hook 之外（`__ugu.rpy:172-175`），我们的开关叫 `_rb_gallery_unlocked`，正好落在被排除的一侧，
读它不会被自己的 hook 拦截。

### 4.2 `_` 检查必须排在读开关之前

这是最容易写出无限递归的地方。`__getattribute__` 的 wrapper 里，如果先读
`persistent._rb_gallery_unlocked` 再判断 `name`，那读开关本身又会进入 wrapper → 递归爆栈。

正确顺序：

```renpy
init 1000 python:
    def _rb_hook_persistent_getattribute(orig):
        def wrapper(self, name):
            if name.startswith("_"):          # ← 必须第一个，先于任何开关读取
                return orig(self, name)
            if not _rb_unlocked():
                return orig(self, name)
            return _rb_swap(orig(self, name))
        return wrapper
```

`_rb_unlocked()` 内部也走 `orig`（或直接读 `renpy.game.persistent.__dict__`），不要走属性访问链。
写完请专门验一次"开关关闭状态下进主菜单不崩"—— 递归错误在这里表现为启动即 `RecursionError`。

### 4.3 值替换（`_swap`）的 Py2/Py3 兼容写法

替母文档没写的部分。`__ugu.rpy:114-141` 的逻辑要保留（False→True、0→1、""→" "、
容器递归、并给 set/list/dict 套一层 `__contains__` 恒真的子类），但比较方式要改：

```renpy
def _rb_swap_one(o):
    if isinstance(o, bool):
        return True if o is False else o
    if isinstance(o, int) and o == 0:         # bool 已在上面拦掉，不会误伤 False
        return 1
    if isinstance(o, str) and o == "":
        return " "
    ...
```

注意 `isinstance(o, bool)` 必须在 `isinstance(o, int)` 之前 —— Py 里 `bool` 是 `int` 的子类，
`False == 0` 为真，顺序错了 `False` 会被当成 `0` 处理。

字符串类型在 Py2 下还有 `unicode` 一支。两边都要覆盖的话，在文件顶部做一次：

```renpy
init -1100 python:
    try:
        _rb_text_types = (str, unicode)
    except NameError:
        _rb_text_types = (str,)
```

### 4.4 hook 点

沿用上游确认过的四类（`__ugu.rpy:153-183`），每个都套 4.2 的开关判断：

| hook 目标 | 开启时行为 |
| --- | --- |
| `renpy.exports.seen_label` | 恒 `True` |
| `renpy.exports.seen_image` | 恒 `True` |
| `renpy.exports.seen_audio` | 恒 `True` |
| `renpy.game.Persistent.__getattr__` | 非 `_` 开头的缺失变量返回 `True` |
| `renpy.game.Persistent.__getattribute__` | 非 `_` 开头的值走 `_rb_swap` |

`soft_safe/hijacks.rpy:36` 那个 `_m1_00gallery__GalleryArbitraryCondition.check`
**先不要抄**。它属于 Ren'Py 自带 gallery 模块的内部名，游戏没用 `00gallery` 时该名字不存在，
抄了要额外写存在性判断，收益不明。等前五个 hook 实测效果不够再加。

因为判断在每次调用时发生，切开关立即生效，不需要重启游戏 —— 这是我们相对上游的唯一实质改进，
实测时要专门确认这一点。

### 4.5 `utter_restart` 卸载

保留 `__ugu.rpy:188-191` 的做法：hook `renpy.exports.utter_restart`，在里面把所有替换过的属性
还原回去。不做的话开发模式热重载会把 wrapper 叠成好几层，表现为越重载越慢、行为越怪。
记录原值用一个模块级列表，还原时 `setattr(*item)`。

### 4.6 按钮

同一个 rpy 里定义 screen 并 **append** 进 overlay：

```renpy
init 999 python:
    if "_rb_gallery_toggle" not in config.overlay_screens:
        config.overlay_screens.append("_rb_gallery_toggle")
```

**必须 append，不能覆盖 `config.overlay_screens`。** 覆盖整个列表会踩掉别人的 overlay，也是按钮
互相顶掉的根源。加 `not in` 判断是
防重复（热重载时 `init` 可能再跑一次）。

现行实现显示自研「MOD」入口，面板内再展示状态和动作：

```renpy
screen _rb_gallery_toggle():
    zorder 100
    textbutton "MOD":
        action ToggleScreen("_rb_game_tools")
```

面板位于右上角，`F9` 打开或关闭面板，`F10` 直接切换画廊状态。文案使用「开启全部画廊」与
「恢复游戏原本的画廊进度」；后者仅关闭强制解锁，不会清除游戏进度。

## 5. 接进现有代码

### 5.1 ModInjector

[ModInjector.MODS](../module/Tool/ModInjector.py#L27-L42) 加第三条，现有 `ModSpec` 结构够用，
不用改 dataclass：

```python
"gallery_unlock": ModSpec(
    key="gallery_unlock",
    title="解锁画廊（ZLZK 通用画廊解锁器改写版）",
    resource_parts=("resource", "mods", "gallery_unlock", "hook_gallery_unlock.rpy"),
    target_name="hook_gallery_unlock.rpy",
    has_rpyc=True,
),
```

`status` / `install` / `uninstall` 都是按 `MODS` 遍历或按 key 取的，加完自动支持，无需改动逻辑。

### 5.2 GameModPage

[GameModPage._init_ui](../frontend/RenpyToolbox/GameModPage.py#L43-L91) 里将画廊卡放在修改器卡之前
（issue 里画廊解锁是主诉求）：

- 调 `self._build_mod_card("gallery_unlock", ...)`，拿到两个按钮。
- 把新按钮加进 `self._buttons`，否则操作期间它不会被禁用，能重复点。
- `_build_game_dir_card` 加一个 `self.gallery_status_label`，`_refresh_status` 里两条分支都要更新它
  （未选目录时的文案 + 已选目录时的已装/未装），漏一个会显示上一次的残留状态。

卡片说明文字要写清：装后游戏内出现「MOD」面板，可随时开启全部画廊或恢复游戏原本的画廊进度；
提供 `F9` / `F10` 快捷键；画廊解锁器为第三方作品（ZLZK）。

### 5.3 测试

[tests/module/tool/test_mod_injector.py](../tests/module/tool/test_mod_injector.py) 的
`_fake_resources` 现在只造两个资源文件、并用 `parts[-1]` 查表，加 `hook_gallery_unlock.rpy` 一条即可。
要改到的地方：

- `_fake_resources` 的 `resources` 字典加新文件。
- `test_install_status_and_uninstall_all_mods` 的 `status` 断言是精确字典比较，必须与当前两个随包模组同步。
- `test_resource_directory_is_never_modified` 的循环加一项。
- 新增：装 `gallery_unlock` → 造 `.rpyc` → 卸载 → 断言 rpy 和 rpyc 都没了。
- 新增：第 0 节那条，安装时清理旧 `.rpyc`。

[tests/frontend/test_game_mod_page.py](../tests/frontend/test_game_mod_page.py) 里凡是断言卡片数量、
按钮数量或状态标签文案的，同步更新。

rpy 本身的运行时行为（hook 是否生效）**测不了** —— 没有 Ren'Py 运行时。可以做的静态检查：
用 `ast.parse` 确认抽出来的 python 块两边语法都合法意义不大（Py2 语法要 Py2 解析器）。
建议只做一条低成本断言：文件里不含 `f"` 和 `unicode`，防回归。真正的验证靠第 6 节手工验收。

## 6. 手工验收（必做，自动化覆盖不到）

Ren'Py 7 和 8 各准备一个真实游戏，逐条走：

1. 装解锁画廊 → 游戏能正常启动（不崩、无 `RecursionError`）。
2. 开关默认关闭 → 画廊仍是锁的（确认没有装上即生效）。
3. 点「MOD」→ 选择「开启全部画廊」→ **不重启** → 画廊立即可看。
4. 选择「恢复游戏原本的画廊进度」→ 立即按游戏进度显示画廊。
5. 退出重进 → 开关状态被 persistent 记住。
6. 卸载 → 确认 `.rpy` 和 `.rpyc` 都没了 → 游戏正常启动、画廊回到原状。
7. 装 URM → 确认 MOD 面板能打开修改器；只装 URM 时，确认独立「修改器」按钮可用。

第 1、3 两条是这次的核心风险点：第 1 条查 Py2/Py3 兼容和递归，第 3 条查"能切换"这个主诉求。

## 7. 第 5 步（URM 按钮）的前置条件

已从上游 PC 压缩包确认安全入口是 `x52URM.Open()`，默认快捷键为 `Alt+M`。不要写
`ShowMenu("URM_main")`，否则会绕过 URM 自己的欢迎页和警告流程。画廊 Hook 已安装时由 MOD 面板
调用此入口；只装 URM 时由伴随 Hook 显示独立按钮。

## 8. 完成后要更新的文档

- [game-mod-injection-design.md](game-mod-injection-design.md) 第 8 节第 4 步划掉。
- [roadmap.md](roadmap.md) 的「注入画廊解锁器」勾上（目前状态与实现一致，本次做完才需要动它）。
- `resource/mods/README.md`：记录 MOD 面板的快捷键、画廊动作含义和 URM 入口。
