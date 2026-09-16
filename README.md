# RenpyBox

<div align="center">
  <img src="./resource/icon.ico" width="196px" />
</div>
<div align="center">
  <img src="https://img.shields.io/github/v/release/dclef/RenpyBox" />
  <img src="https://img.shields.io/github/license/dclef/RenpyBox" />
  <img src="https://img.shields.io/github/stars/dclef/RenpyBox" />
</div>
<p align="center">使用 AI 能力一键翻译 Ren'Py / 视觉小说文本的工具箱</p>

## README 🌍
- [中文（本页）](./README.md)
- [English](./README_EN.md)
- 请不要有中文路径

## 概述 📢
- RenpyBox：PyQt + Fluent UI 打造的 Ren'Py 本地化工具箱，提取、翻译、修复、打包于一体的Ren'Py 专用翻译解决方案
- 目标用户：视觉小说开发者、同人翻译组、Ren'Py翻译者
- **建议使用[硅基流动](https://cloud.siliconflow.cn/i/Cvmvkm5d) 进行翻译**


## 特别说明 ⚠️
- 本工具仅限合法使用。任何利用本工具实施违法、侵权或违法牟利活动的行为，均不受项目方认可或支持；相关法律责任由行为人依法自行承担

## 功能优势 📌
- 一键翻译向导：自动检测 `game/tl/<lang>`，支持增量/全量提取、断点续译、暂停/继续
- 术语与禁译：角色名提取、术语表/禁译表本地管理，支持文本保护、前后替换、混合语清理
- 多引擎并发：内置 OpenAI/DeepSeek/Anthropic/Google/火山等模板，可在“接口管理”添加自定义端点
- 高保真格式：AST 补全 + 缺失文本扫描 + miss_patch，同步生成 `replace_text*.rpy` 补丁，保留既有译文
- Ren'Py 工具链：RPY 格式化、缩进/引号检查与修复、尾空格清理、批量字体替换、RPA 解包/打包、RPYC 反编译、语言入口/默认语言设置、安卓打包（安卓外壳打包）
- 进度可视化：并发控制、速率限制、token/进度仪表盘。


## 工具箱模块 🧰
- 一键翻译 / 翻译提取 / 直接翻译 RPY/源码 / 增量翻译
- 本地术语表、文本保护、前后替换、名称字段提取、局部重翻、批量修正
- RPA 解包/打包、RPYC 反编译、字体注入、默认语言/入口配置、格式化与错误修复、HTML/Excel/JSON 导入导出


## 支持的文本格式 🏷️
- Ren'Py 导出 `.rpy`、本地术语表/替换规则
- 其他格式持续补充，欢迎在 Issues 提交需求

## 近期更新 📅

- 2026-09-17 v0.7.10：
  - 修复自动更新替换更新器时提示权限不足、导致更新中断的问题
  - 恢复增量更新，版本匹配且安装文件完整时只下载变化文件，减少下载量
  - 本地缺文件、文件损坏或上次更新中断时，自动使用全量包修复
  - 发布前自动验证增量包能否还原完整新版，更新时保留用户配置和输入文件

- 2026-09-17 v0.7.9：
  - 启动页阶段预热主界面、翻译页项目状态和 Ren'Py 工具页，减少进入页面后的卡顿
  - 翻译启动前的项目检查改为后台准备，大项目缓存写入和预处理过程保持界面响应
  - 优化默认吞吐配置和请求超时，控制台进度条会计算剩余时间并补全 Token 统计
  - Ren'Py 文本抽取、增量合并和官方抽取改为后台执行，取消后会正确恢复目录并收口界面
  - 反编译会按游戏 Python 版本选择资源，修复 32/64 位启动器识别、归档验证和部分 unrpyc 输出问题
  - 修复启动图提前关闭后的空白等待、标题栏样式警告、旧任务线程统计和旧回调影响当前进度的问题

- 2026-09-13 v0.7.8：
  - 优化深浅色界面、任务监控和一键翻译步骤，修复“应用生效”页面多余滚动与空白
  - 改善 Agent 长会话、消息显示和缓存统计，简化角色与世界观编辑及双语校对操作
  - 完善自动解包、反编译与漏翻补丁生成，减少重复抽取
  - 合并重复入口为“写入译文文件”，修复点击闪退并显示实际写入目录
  - 修复继续翻译的行数设置不生效、译文复用误报冲突、剩余时间丢失及游戏菜单报错

完整记录见 [CHANGELOG.md](./CHANGELOG.md)

## 常见问题 📥
- 运行日志位于 `./log`，反馈问题请附相关日志
- 缓存存放在 `output/cache`，可在暂停后直接继续任务或导出已完成部分
- 若外部接口超时/限速，可在“接口管理”调整并发与速率限制

## 反馈与支持 💬
- 欢迎通过 Issues/PR 反馈问题或贡献功能
- 反馈问题的时候请附上log日志，日志文件位于 `./log` 目录下
- QQ 群：821152470



## 致谢 🙏
- 部分代码与架构参考 [AiNiee](https://github.com/NEKOparapa/AiNiee)和 [LinguaGacha](https://github.com/neavo/LinguaGacha)
- 模块的设计理念来自于[renpy-translator](https://github.com/anonymousException/renpy-translator)
- 本工具使用教程请看[RenpyBox使用教程](https://www.bilibili.com/video/BV1KPBoBhEMD)
- 本工具使用文档请看[Renpy汉化教程](https://docs.dclef.com/)

