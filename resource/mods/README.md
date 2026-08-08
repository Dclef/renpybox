# 随包分发的 Ren'Py 模组

这些模组由「游戏模组注入」功能复制进用户的游戏目录。
其中画廊解锁器和 URM 为第三方作品，内置修改器由 RenpyBox 自研。仅支持 PC / 模拟器版，不支持安卓版。

| 目录 | 模组 | 作者 | 注入目标 |
| --- | --- | --- | --- |
| `gallery_unlock/` | 通用画廊解锁器（Universal Gallery Unlocker） | ZLZK | `game/hook_gallery_unlock.rpy` |
| `urm/` | 0x52-URM 通用游戏数据修改器 2.6.2 汉化版 | 0x52 | `game/0x52-URM-2.6.2.rpa`、`game/hook_urm_button.rpy` |
| `simple_modifier/` | 内置修改器（RenpyBox 自研） | RenpyBox | `game/hook_simple_modifier.rpy` |

## 画廊解锁器：soft 与 hard

上游提供两个版本，**二者互斥，只能装一个**：

| 目录 | 上游名 | 特性 |
| --- | --- | --- |
| `upstream/soft_safe/` | 软版 | 效果较差，但更安全 |
| `upstream/hard_aggressive/` | 硬版 | 更有效，但风险更大 |

上游原始路径是 `game/_mods/ZLZK_UGU_soft`（或 `_hard`）。

## 注意

- `gallery_unlock/upstream/` 是 ZLZK 原版存档，**不直接注入**。原版在 `init` 期硬 hook，
  装上即永久生效、没有开关。实际注入物是据其思路重写的单文件 hook，带 persistent 开关。
  注入后游戏内会显示 RenpyBox 自研的「MOD」面板：`F9` 打开面板，选择「开启全部画廊」或
  「恢复游戏原本的画廊进度」；`F10` 可直接切换画廊状态。后者仅关闭强制解锁，不会清除游戏进度。
  面板中的「内置修改器」是第三个同级入口，提供对话框字号/宽度/位置、选项框样式和快捷菜单设置。
  它使用 Ren'Py 原生样式，不覆盖 `screen say`、`screen choice` 或 `config.overlay_screens`，也不会扫描或改写普通运行时变量。
  内置修改器可以单独安装；与画廊 Hook 同时安装时由画廊的 MOD 面板统一显示入口。
  `upstream/__ugu.rpy` 是单文件版参考实现，但为 Python 2 写法，Ren'Py 8 下需改写。
- `upstream/hard_aggressive/tools/` 原始下载包中名为 `tools(1)`（重名产物），已还原。
- URM 由「MOD」面板通过 `x52URM.Open()` 打开，并保留其自带的 `Alt+M` 快捷键。只安装 URM 时，
  伴随 Hook 会显示独立的「修改器」按钮；同时安装画廊 Hook 时，它会自动隐藏以避免重复入口。
- 画廊硬解锁会跳过 `persistent.URMSettings`；对于已安装旧版独木桥的游戏，也会继续跳过
  `persistent.dumuqiao*`，避免把旧模组设置误改为解锁值。
- 独木桥不再随 RenpyBox 分发，也不再接管游戏菜单。工具检测到旧安装时会提供明确的清理按钮，
  仅删除 `game/dumuqiao.rpy` 与 `game/dumuqiao.rpyc`，保留 `.bak` 备份文件。
- **URM 已知限制**：上游说明提到 URM 报 `API.rpyc` 错误时应改用压缩包版（`0x52-URM 2.6.2.7z`
  或 `.zip`，解压码 `666666`）。精简时该压缩包已被删除，故目前没有这个兜底。若实测遇到该错误，
  需从上游重新获取压缩包版。
- 上游原始压缩包、安卓版、旧版本和安装教程视频未随包分发（原始素材共 159M）。
- `.rpa` 默认被 `.gitignore` 忽略，`resource/mods/**/*.rpa` 已加否定规则放行。
