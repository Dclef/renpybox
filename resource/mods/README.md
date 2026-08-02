# 随包分发的第三方 Ren'Py 模组

这些模组由「游戏模组注入」功能复制进用户的游戏目录。
均为第三方作品，版权归各自作者所有。仅支持 PC / 模拟器版，不支持安卓版。

| 目录 | 模组 | 作者 | 注入目标 |
| --- | --- | --- | --- |
| `gallery_unlock/` | 通用画廊解锁器（Universal Gallery Unlocker） | ZLZK | `game/hook_gallery_unlock.rpy`（待实现） |
| `urm/` | 0x52-URM 通用游戏数据修改器 2.6.2 汉化版 | 0x52 | `game/0x52-URM-2.6.2.rpa` |
| `quick_menu/` | 独木桥模组 6.27 版（自定义底部按钮栏与设置菜单） | 独木桥 | `game/dumuqiao.rpy` |

## 画廊解锁器：soft 与 hard

上游提供两个版本，**二者互斥，只能装一个**：

| 目录 | 上游名 | 特性 |
| --- | --- | --- |
| `upstream/soft_safe/` | 软版 | 效果较差，但更安全 |
| `upstream/hard_aggressive/` | 硬版 | 更有效，但风险更大 |

上游原始路径是 `game/_mods/ZLZK_UGU_soft`（或 `_hard`）。上游说明还提到这两版
「解决对独木桥模组的按钮冲突」，且警告用完记得移除。

## 注意

- `gallery_unlock/upstream/` 是 ZLZK 原版存档，**不直接注入**。原版在 `init` 期硬 hook，
  装上即永久生效、没有开关。实际注入物是据其思路重写的单文件 hook，带 persistent 开关。
  `upstream/__ugu.rpy` 是单文件版参考实现，但为 Python 2 写法，Ren'Py 8 下需改写。
- `upstream/hard_aggressive/tools/` 原始下载包中名为 `tools(1)`（重名产物），已还原。
- 独木桥模组只需 `dumuqiao.rpy` 一个文件，卸载直接删掉即可。其「作弊1~5」按钮需要游戏本身
  装了对应作弊 mod 才有用。
- **URM 已知限制**：上游说明提到 URM 报 `API.rpyc` 错误时应改用压缩包版（`0x52-URM 2.6.2.7z`
  或 `.zip`，解压码 `666666`）。精简时该压缩包已被删除，故目前没有这个兜底。若实测遇到该错误，
  需从上游重新获取压缩包版。
- 上游原始压缩包、安卓版、旧版本和安装教程视频未随包分发（原始素材共 159M）。
- `.rpa` 默认被 `.gitignore` 忽略，`resource/mods/**/*.rpa` 已加否定规则放行。
