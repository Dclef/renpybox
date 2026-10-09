# RenpyBox

<div align="center">
  <img src="./resource/icon.ico" width="196px" />
</div>
<div align="center">
  <img src="https://img.shields.io/github/v/release/dclef/RenpyBox" />
  <img src="https://img.shields.io/github/license/dclef/RenpyBox" />
  <img src="https://img.shields.io/github/stars/dclef/RenpyBox" />
</div>
<p align="center">An AI-powered toolbox for one-click translation of Ren'Py and visual novel text</p>

## README 🌍

- [中文](./README.md)
- English (this page)
- Please avoid Chinese characters in file paths

## Overview 📢

- RenpyBox is a Ren'Py localization toolbox built with PyQt and Fluent UI. It combines text extraction, translation, repair, and packaging in one Ren'Py-focused solution.
- Intended users: visual novel developers, fan translation teams, and Ren'Py translators.
- **[SiliconFlow](https://cloud.siliconflow.cn/i/Cvmvkm5d) is recommended for translation.**

## Special Notice ⚠️

- This tool is for lawful use only. Any use of this tool for unlawful, infringing, or illegal profit-making activities is neither endorsed nor supported by the project; the person engaging in such conduct bears the relevant legal responsibility under applicable law.

## Feature Advantages 📌

- One-click translation wizard: automatically detects `game/tl/<lang>` and supports incremental or full extraction, resume from checkpoints, pause, and continue.
- Glossary and do-not-translate management: extract character names, manage local glossaries and do-not-translate lists, protect text, apply replacements, and clean mixed-language text.
- Free translation: built-in Google and Bing free engines, no API key required; usable for batch translation and the local glossary.
- Concurrent engines: built-in templates for OpenAI, DeepSeek, Anthropic, Google, Volcano Engine, and more; custom endpoints can be added in Interface Management.
- High-fidelity formatting: AST completion, missing-text scanning, and `miss_patch` support generate `replace_text*.rpy` patches while preserving existing translations.
- Ren'Py toolbox: RPY formatting, indentation and quote checks and repairs, trailing-space cleanup, batch font replacement, RPA unpacking and packing, RPYC decompilation, language entry and default-language settings, and Android packaging through the Android wrapper workflow.
- Progress visibility: concurrency controls, rate limits, and token/progress dashboards.

## Toolbox Modules 🧰

- One-click translation, translation extraction, direct translation of RPY/source files, and incremental translation
- Local glossaries, text protection, replacements, name-field extraction, partial retranslation, and batch corrections
- RPA unpacking/packing, RPYC decompilation, font injection, default-language and entry configuration, formatting and error repair, and HTML/Excel/JSON import and export

## Supported Text Formats 🏷️

- Ren'Py exports: `.rpy`
- Local glossaries and replacement rules
- More formats will be added over time. Feature requests are welcome in Issues.

## Recent Updates 📅

- 2026-10-09 v0.8.2:
  - Fixed slow write-back validation for large Ren'Py projects while preserving duplicate-text, character-name, and AST matching semantics.
  - Fixed cache exports and fallback reinjection reading from the output directory; incremental and proofreading exports now restore the matching input path from the run manifest.
  - Strengthened write-back path safety checks and fixed first-time export of a single TL script.

- 2026-10-02 v0.8.0:
  - Opening the model list no longer waits for every translation SDK to load, and switching projects and saving the translation cache are noticeably faster.
  - Proofreading filters, similarity checks, and placeholder checks are faster, so large projects no longer stutter repeatedly.
  - Fixed incomplete translations being reported as success, lost progress after a task stops unexpectedly, and one failing check aborting the whole report.
  - Fixed per-language runtime replacement patches overwriting each other, interrupted write-back leaving damaged translations, and silent success on incomplete backfill.
  - Fixed the extraction-rules dialog and the proofreading target dialog keeping a light background in the dark theme.
  - RPY extraction settings are now grouped by the syntax they read, note which flows share each rule set, and say when a change has not been applied yet.

- 2026-09-27 v0.7.12:
  - Added RPY extraction settings with separate source-RPY and TL-RPY profiles for built-in, custom, and combined modes.
  - Custom extraction is available in one-click, TL, and source translation, with a beginner-friendly default view and optional advanced rule editing.
  - Improved TL pairing and source write-back safety for custom rules.

- 2026-09-22 v0.7.11:
  - Added Google and Bing free translation engines, no API key required; available in one-click, TL, source-code, and direct-RPY translation as well as the local glossary.
  - The direct-RPY page adds an "auto write-back" switch and a manual write-back button; fixed switch labels losing their text when turned on.
  - Removed unused interfaces such as DeepL, DeepLX, Caiyun, Youdao, and Alibaba, and cleaned up legacy compatibility modules.

- 2026-09-17 v0.7.10:
  - Fixed the permission error that interrupted updates when the updater replaced itself.
  - Restored incremental updates: when the version matches and installed files are intact, only changed files are downloaded.
  - Missing, corrupted, or previously interrupted installations are automatically repaired with a full package.
  - Incremental packages are verified before release, and user configs and input files are preserved during updates.

See [CHANGELOG.md](./CHANGELOG.md) for the complete change history.

## FAQ 📥

- Runtime logs are stored in `./log`. Please attach the relevant logs when reporting an issue.
- Caches are stored in `output/cache`. After pausing a task, you can continue it directly or export the completed portion.
- If an external interface times out or is rate-limited, adjust concurrency and rate limits in Interface Management.

## Feedback and Support 💬

- Issues and pull requests are welcome for bug reports, suggestions, and contributions.
- Please include the relevant files from the `./log` directory when reporting a problem.
- QQ group: 821152470

## Acknowledgements 🙏

- Early versions referenced the former Python version of [LinguaGacha](https://github.com/neavo/LinguaGacha); the related code has since been reimplemented. Some code and architecture were adapted from [AiNiee](https://github.com/NEKOparapa/AiNiee).
- The module design was inspired by [renpy-translator](https://github.com/anonymousException/renpy-translator).
- See the [RenpyBox user tutorial](https://www.bilibili.com/video/BV1KPBoBhEMD) for a walkthrough.
- See the [Ren'Py translation documentation](https://docs.dclef.com/) for more information.
