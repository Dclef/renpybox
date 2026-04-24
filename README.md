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
- 请不要有中文路径

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
- 2026-4-24 v0.5.8：
  - 修复token累积除法Bug，减少token翻译成本
  - 修复Gemini OFF模式仍消耗thinking tokens的问题
  - 修正request返回类型注释错误
  - 优化系统/用户消息分离



- 2026-3-31 v0.5.7：
  - 新增“中英混合残留”响应检查
  - 修复重试次数达到阈值后仍可能放行坏译文的问题，中英混杂输出不再被当成成功结果
  - 校对页单条重翻改为复用与主翻译相同的结果校验逻辑，避免手动重翻写回异常结果
  - 结果检查中的“混合翻译错误”报告改为复用主校验逻辑，报告与实际写回判定保持一致

- 2026-3-24 v0.5.6：
  - 增加世界观背景角色工作台
  - 修复文本保护占位符参与相似度检查导致的误判重试问题
  - 优化响应检查流程，降低保护片段过多时的退化与相似度误报
  - 改进翻译任务日志显示，优先输出恢复后的可读文本内容


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

