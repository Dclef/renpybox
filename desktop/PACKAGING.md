# Windows New UI 测试包

仅在 `new_UI` 分支打包和试运行。安装包使用项目原有的 `resource/icon.ico`，应用名为 `RenpyBox New UI`，独立 appId 避免覆盖 Qt 版。

## 本机打包

构建机器需要 Windows x64、Node.js 22 和 Python 3.10 x64；安装包使用者无需安装 Node.js 或 Python。

```powershell
python -m pip install -r desktop/scripts/requirements-backend.txt
npm ci --prefix desktop
npm run pack:win --prefix desktop
```

可设置 `RENPYBOX_BUILD_PYTHON` 为专用构建虚拟环境的 `python.exe`。构建先用 PyInstaller 冻结 API 后端和依赖，再打包 Electron。后端从 Git 跟踪的资源列表打包，排除 `config.json`、凭据文件和 `.env`；运行时配置存放在用户目录。动态导入的翻译 SDK、Agent tools、`update_integrity` 和 token/OpenCC 字典包含在冻结运行时内。无需先运行开发服务器。

输出（同一次构建产出四个文件）：

- `desktop/release/RenpyBox-NewUI-<version>-x64.exe`（NSIS 安装包，支持自动更新与差分下载）
- `desktop/release/RenpyBox-NewUI-<version>-x64.exe.blockmap`（差分下载必需，必须随安装包一起发布）
- `desktop/release/RenpyBox-NewUI-<version>-x64.zip`（免安装包，内部群手动分发用）
- `desktop/release/newui.yml`（electron-updater 的 newui 频道元数据）

`win-unpacked/RenpyBox New UI.exe` 可直接启动用于排查。请保持整个 `win-unpacked` 目录完整，不能只复制其中的 exe。

**zip 与安装包必须一起构建**：electron-builder 只在同一次构建里存在 nsis 目标时才写 `resources/app-update.yml`（`app-builder-lib/out/publish/PublishManager.js` 的 `isSuitableWindowsTarget` 只认 `nsis`），两个产物共用同一个 `win-unpacked`。所以 `pack:win` 固定使用 `--win nsis zip`，`verify:package` 会校验 zip 里确实带上了 `resources/app-update.yml`，避免免安装版失去更新能力。

`npm run build:backend --prefix desktop` 单独构建后端；输入文件未变更时复用已通过自检的结果。强制重建使用 `npm run build:backend --prefix desktop -- --force`。`npm run verify:package --prefix desktop` 检查 Python DLL、原图标、排除私有文件、生成的更新配置，以及 zip 内的更新配置。

## 版本号规则

New UI 的数字部分**始终跟随它所基于的 Python 版**，后缀 `-newui.N` 只表示该基线下的第 N 个测试包：

| 位置 | 当前值 | 说明 |
| --- | --- | --- |
| `base/Version.py` `CURRENT` | `v0.8.2` | 后端版本，Python 版与 New UI 共用 |
| `version.txt` | `v0.8.2` | 同上，发版脚本读取 |
| `desktop/package.json` `version` | `0.8.2-newui.1` | 主进程比较时取 `-` 前半段，必须与 `base/Version.py` 一致（`desktop/main/sidecar.js` 会校验） |
| `desktop/package-lock.json` | `0.8.2-newui.1` | 与 package.json 保持一致，CI 的 `npm ci` 会读 |

合并 Python 版新发布后（`git merge origin/main`），把后三位跟上 Python 版并把 `-newui.N` 归 1，同时在本文件与 `CHANGELOG.md` 顶部记录。

## GitHub 测试发布与更新

推送 `new_UI` 只生成 Actions artifact，不发布正式 Release。进入 **RenpyBox New UI desktop** workflow，选择 `new_UI` 并手动启用 `publish`，才会创建 `v0.8.2-newui.1` 形式的 prerelease，上传安装器、blockmap、zip、`newui.yml` 四个文件。流程不会写 `latest.yml`，也不会把测试版标成正式最新版本 —— 这一点是必须的：Qt 版用 `https://api.github.com/repos/dclef/RenpyBox/releases/latest` 检查更新（`base/VersionManager.py:39`），而 GitHub 的 `latest` 接口会跳过 prerelease，因此 New UI 测试包不会干扰 Python 版的更新链路；一旦误发成正式 latest，Qt 版会去下载 `RenpyBox_<版本>.zip` 之类的资产而直接报错。

测试自动更新需要两个不同版本：先安装 `0.8.2-newui.1`，随后把 `desktop/package.json` 和锁文件版本增为 `0.8.2-newui.2`，再次手动发布 prerelease，再从已安装的应用检查更新。相同版本重复发布会失败，避免静默覆盖已发布安装器。打包成功本身不等于已验证 GitHub 下载、安装和重启全过程。

### 更新是差分还是全量

- 应用只在用户点「下载更新」后开始下载（`autoDownload = false`），下载完成后由用户确认「重启安装」（`autoInstallOnAppQuit = false`）。
- electron-updater 走 `NsisUpdater.differentialDownloadInstaller`：它同时取**新版本的 `.blockmap`** 与**旧版本的 `.blockmap`**（旧包优先用缓存目录里的 `current.blockmap`），生成差异计划，只对变化的字节区间发多次 Range 请求（`electron-updater/out/AppUpdater.js:643-699`、`out/differentialDownloader/*`）。
- 因此：本机第一次更新（缓存里还没有旧安装包与旧 blockmap）会**全量下载**约 267 MB；从第二次起是**差分下载**，通常只下几十 MB。要保住差分能力，历史版本的 `.blockmap` 不要从 Release 里删掉，且同一频道保持相同的打包配置。
- 免安装 zip 因为带上了 `app-update.yml`，同样能「检查更新 / 下载 / 重启安装」，但 Windows 上 electron-updater 只会下载并运行 NSIS 安装包 —— 也就是说解压使用的用户点更新后会被装成正式安装版（不会自动替换他手里那份 zip 目录）。如果希望免安装用户留在免安装形态，需要另做一条「下载新 zip」的分支。

此包仍是 UI 迁移测试版。依赖游戏或 Ren'Py SDK 的工具仍需用户选择相应游戏/SDK 路径；可选 spaCy 命名实体提取不随 API 运行时打包，使用已有回退逻辑。

## 本地验证记录（2026-10-10）

- Node 进程、日志与更新回归测试 19 项通过；Python 路径及校对 API 测试 9 项通过，渲染器类型检查通过。
- 直接运行 `win-unpacked/RenpyBox New UI.exe`，使用新的中文含空格用户目录，并故意将系统 Python 环境指向不存在的路径：实际页面渲染、WebSocket 连接、内置后端启动和配置保存通过。
- 关于页显示 `0.8.1-newui.1`、真实后端状态和原图标；随包更新日志、更新弹窗 IPC 通过。主程序及后端 EXE 内嵌图标图像与仓库原 ICO 逐字节一致。
- 正常关窗后应用和所属后端进程退出；后端崩溃恢复、首次重启失败后继续重试、探活过程中关闭均经过真实子进程验证。磁盘中的中文日志保持 UTF-8。
- 当时的 GitHub 实际检查返回没有可用的 `newui` 发布版本。安装器交互安装、两版本下载升级、用户旧配置迁移和所有业务页面与 Qt5 的完整对齐，均不在这些已通过结果内。

回归测试：`node --test desktop/tests/logger-contract.test.mjs desktop/tests/sidecar-contract.test.mjs desktop/tests/updater-contract.test.mjs`。CI 在打包前执行这组测试。
