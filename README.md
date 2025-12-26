# RenpyBox

<div align="center">
  <img src="./resource/icon.ico" width="196px" />
</div>
<div align="center">
  <img src="https://img.shields.io/github/v/release/dclef/RenpyBox" />
  <img src="https://img.shields.io/github/license/dclef/RenpyBox" />
  <img src="https://img.shields.io/github/stars/dclef/RenpyBox" />
</div>
<p align="center">使用 AI 能力一键翻译 Ren'Py / 视觉小说文本的次世代工具箱</p>

## README 🌍
- 中文（本页）；其他语言版本计划追加

## 概述 📢
- RenpyBox：PyQt + Fluent UI 打造的 Ren'Py 本地化工具箱，集提取、翻译、修复、打包于一体
- 支持 `中` `英` `日` `韩` 等多语互译，可接入 OpenAI、DeepSeek、Anthropic、Google 等本地/在线接口
- 提供“开箱即用 + 向导式”体验，默认配置即可跑通一键翻译，进阶用户可深度自定义

> 🖼️ 截图与视频演示待补充，欢迎在 Issues/PR 中提供示例

## 特别说明 ⚠️
- 若涉及商业用途，请先联系作者获取授权

## 功能优势 📌
- 一键翻译向导：自动检测 `game/tl/<lang>`，支持增量/全量提取、断点续译、暂停/继续
- 术语与禁译：角色名提取、术语表/禁译表本地管理，支持文本保护、前后替换、混合语清理
- 多引擎并发：内置 OpenAI/DeepSeek/Anthropic/Google/火山等模板，可在“接口管理”添加自定义端点
- 高保真格式：AST 补全 + 缺失文本扫描 + miss_patch，同步生成 `replace_text*.rpy` 补丁，保留既有译文
- Ren'Py 工具链：RPY 格式化、缩进/引号检查与修复、尾空格清理、批量字体替换、RPA 解包/打包、语言入口/默认语言设置
- 进度可视化：并发控制、速率限制、token/进度仪表盘，缓存落盘于 `output/cache`，随时导出已完成部分

## 配置要求 🖥️
- 建议 Python 3.10+ 环境
- 安装依赖：`python -m pip install -r requirements.txt`
- 需要可用的本地或在线大模型接口（如 OpenAI、DeepSeek 等），在应用内配置密钥与地址

## 基本流程 🛸
1. 克隆或下载本项目，安装依赖：`python -m pip install -r requirements.txt`
2. 运行应用：`python app.py`（首次会生成 `config.json`）
3. 在 “接口管理” 激活或添加翻译平台，填写密钥/地址
4. 在 “项目设置” 指定输入/输出目录与源/目标语言
5. 进入 “Ren'Py 百宝箱” 或 “一键翻译”，选择增量/全量模式并开始任务，进度可视化可随时暂停/恢复

## 工具箱模块 🧰
- 一键翻译 / 翻译提取 / 直接翻译 RPY/源码 / 增量翻译
- 本地术语表、文本保护、前后替换、名称字段提取、局部重翻、批量修正
- RPA 解包/打包、字体注入、默认语言/入口配置、格式化与错误修复、HTML/Excel/JSON 导入导出
- MaSuite、SourceTranslate、PackUnpack 等专项卡片，覆盖从资源处理到打包的常见需求

## 支持的文本格式 🏷️
- Ren'Py 导出 `.rpy`、本地术语表/替换规则
- 常见文本：`.txt` `.md`，字幕：`.srt` `.ass`
- MTool/自定义 JSON 与 Excel 导出，HTML 片段导入
- 其他格式持续补充，欢迎在 Issues 提交需求

## 近期更新 📅
- 2025-12-25 `v0.3.3`：修复缺失补丁生成流程问题, 优化文件处理逻辑（详见提交记录）

## 常见问题 📥
- 运行日志位于 `./log`，反馈问题请附相关日志
- 缓存存放在 `output/cache`，可在暂停后直接继续任务或导出已完成部分
- 若外部接口超时/限速，可在“接口管理”调整并发与速率限制

## 反馈与支持 💬
- 欢迎通过 Issues/PR 反馈问题或贡献功能
- 也可在讨论区分享使用体验与最佳实践

## 致谢 🙏
此项目继承[LinguaGacha](https://github.com/neavo/LinguaGacha) 它的UI和翻译引擎(本人太懒了没有灵感写额外的UI),

本人目的是专注于Ren'py的翻译,所以此项目并不是LinguaGacha的分支版本,

相较于LinguaGacha,本项目的独特优势是Renpy相关的工具使用.

- 相关代码取于[AiNiee](https://github.com/NEKOparapa/AiNiee)
- 模块的设计理念来自于[renpy-translator](https://github.com/anonymousException/renpy-translator)

