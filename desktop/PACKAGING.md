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

输出：`desktop/release/RenpyBox-NewUI-0.8.1-newui.1-x64.exe`、同名 `.blockmap`、`newui.yml`。`win-unpacked/RenpyBox New UI.exe` 可直接启动用于排查。请保持整个 `win-unpacked` 目录完整，不能只复制其中的 exe。

`npm run build:backend --prefix desktop` 单独构建后端；输入文件未变更时复用已通过自检的结果。强制重建使用 `npm run build:backend --prefix desktop -- --force`。`npm run verify:package --prefix desktop` 检查 Python DLL、原图标、排除私有文件和生成的更新配置。

## GitHub 测试发布与更新

推送 `new_UI` 只生成 Actions artifact，不发布正式 Release。进入 **RenpyBox New UI desktop** workflow，选择 `new_UI` 并手动启用 `publish`，才会创建 `v0.8.1-newui.1` 形式的 prerelease，上传安装器、blockmap、`newui.yml` 三个文件。流程不会写 `latest.yml`，也不会把测试版标成正式最新版本。

测试自动更新需要两个不同版本：先安装 `0.8.1-newui.1`，随后把 `desktop/package.json` 和锁文件版本增为 `0.8.1-newui.2`，再次手动发布 prerelease，再从已安装的应用检查更新。相同版本重复发布会失败，避免静默覆盖已发布安装器。打包成功本身不等于已验证 GitHub 下载、安装和重启全过程。

此包仍是 UI 迁移测试版。依赖游戏或 Ren'Py SDK 的工具仍需用户选择相应游戏/SDK 路径；可选 spaCy 命名实体提取不随 API 运行时打包，使用已有回退逻辑。

## 本地验证记录（2026-10-10）

- Node 进程、日志与更新回归测试 19 项通过；Python 路径及校对 API 测试 9 项通过，渲染器类型检查通过。
- 直接运行 `win-unpacked/RenpyBox New UI.exe`，使用新的中文含空格用户目录，并故意将系统 Python 环境指向不存在的路径：实际页面渲染、WebSocket 连接、内置后端启动和配置保存通过。
- 关于页显示 `0.8.1-newui.1`、真实后端状态和原图标；随包更新日志、更新弹窗 IPC 通过。主程序及后端 EXE 内嵌图标图像与仓库原 ICO 逐字节一致。
- 正常关窗后应用和所属后端进程退出；后端崩溃恢复、首次重启失败后继续重试、探活过程中关闭均经过真实子进程验证。磁盘中的中文日志保持 UTF-8。
- 当时的 GitHub 实际检查返回没有可用的 `newui` 发布版本。安装器交互安装、两版本下载升级、用户旧配置迁移和所有业务页面与 Qt5 的完整对齐，均不在这些已通过结果内。

回归测试：`node --test desktop/tests/logger-contract.test.mjs desktop/tests/sidecar-contract.test.mjs desktop/tests/updater-contract.test.mjs`。CI 在打包前执行这组测试。
