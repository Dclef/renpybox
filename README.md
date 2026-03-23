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
- 中文（本页）

## 概述 📢
- RenpyBox：PyQt + Fluent UI 打造的 Ren'Py 本地化工具箱，提取、翻译、修复、打包于一体的Ren'Py 专用翻译解决方案
- 目标用户：视觉小说开发者、同人翻译组、Ren'Py翻译者
- **建议使用[硅基流动](https://cloud.siliconflow.cn/i/Cvmvkm5d) 进行翻译**


## 特别说明 ⚠️
- 若涉及商业用途，请先联系作者获取授权

## 功能优势 📌
- 一键翻译向导：自动检测 `game/tl/<lang>`，支持增量/全量提取、断点续译、暂停/继续
- 术语与禁译：角色名提取、术语表/禁译表本地管理，支持文本保护、前后替换、混合语清理
- 多引擎并发：内置 OpenAI/DeepSeek/Anthropic/Google/火山等模板，可在“接口管理”添加自定义端点
- 高保真格式：AST 补全 + 缺失文本扫描 + miss_patch，同步生成 `replace_text*.rpy` 补丁，保留既有译文
- Ren'Py 工具链：RPY 格式化、缩进/引号检查与修复、尾空格清理、批量字体替换、RPA 解包/打包、语言入口/默认语言设置、安卓打包（安卓外壳打包）
- 进度可视化：并发控制、速率限制、token/进度仪表盘。


## 工具箱模块 🧰
- 一键翻译 / 翻译提取 / 直接翻译 RPY/源码 / 增量翻译
- 本地术语表、文本保护、前后替换、名称字段提取、局部重翻、批量修正
- RPA 解包/打包、字体注入、默认语言/入口配置、格式化与错误修复、HTML/Excel/JSON 导入导出


## 支持的文本格式 🏷️
- Ren'Py 导出 `.rpy`、本地术语表/替换规则
- 其他格式持续补充，欢迎在 Issues 提交需求

## 近期更新 📅

- 2026-3-23 v0.5.5：
  - 拆分 Ren'Py 补全翻译模式，保留 `replace_text` 写回流程
  - 新增运行时 HOOK 翻译模式，支持 `strings` 抽取、目标语言目录创建与提取
  - 修复 Ren'Py 提取流程与 HOOK 补全流程问题
  - 为一键翻译增加完成后自动补全漏翻选项

- 2026-3-17 v0.5.4：
  - 新增输入/输出目录分离校验、源码引用路径解析与代码结构恢复能力
  - 添加条件提示元组文本提取
  - 增加对 Ren'Py 对话行未转义引号和缩进层级问题的修复
  - 修复源码翻译续翻卡顿与 OpenCC 启动兼容问题
  - 修复 Ren'Py 7 项目误用 `UnRen-current` 导致的反编译问题
  - 优化构建流程
  - 为本地词库和禁翻表增加命中统计



## 常见问题 📥
- 运行日志位于 `./log`，反馈问题请附相关日志
- 缓存存放在 `output/cache`，可在暂停后直接继续任务或导出已完成部分
- 若外部接口超时/限速，可在“接口管理”调整并发与速率限制

## 反馈与支持 💬
- 欢迎通过 Issues/PR 反馈问题或贡献功能
- 反馈问题的时候请附上log日志，日志文件位于 `./log` 目录下
- QQ 群：821152470



## 致谢 🙏
此项目继承[LinguaGacha](https://github.com/neavo/LinguaGacha) 它的UI和翻译引擎(本人太懒了没有灵感写额外的UI😂)。

由于目的是专注于Ren'py的翻译,所以此项目并不是LinguaGacha的分支版本。

相较于LinguaGacha，本项目的独特优势是Renpy相关的工具使用。

- 相关代码取于[AiNiee](https://github.com/NEKOparapa/AiNiee)
- 模块的设计理念来自于[renpy-translator](https://github.com/anonymousException/renpy-translator)
- 教程请看[RenpyBox使用教程](https://www.bilibili.com/video/BV1KPBoBhEMD)
- 文档请看[Renpy汉化教程](https://docs.dclef.com/)

