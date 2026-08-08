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

- For commercial use, please contact the author for authorization first.

## Feature Advantages 📌

- One-click translation wizard: automatically detects `game/tl/<lang>` and supports incremental or full extraction, resume from checkpoints, pause, and continue.
- Glossary and do-not-translate management: extract character names, manage local glossaries and do-not-translate lists, protect text, apply replacements, and clean mixed-language text.
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

- 2026-08-08 v0.7.4:
  - Reworked Ren'Py incremental translation to identify statements by file and dialogue scope. When source text changes, only the changed content is retranslated, preventing translations from being incorrectly reused across scenes.
  - One-click translation can extract hidden interface text from the game and incrementally complete it at runtime. Existing translations are preserved.
  - Applying translations now runs in the background with progress feedback. If extraction or write-back fails, the original translation directory and backups can be restored.
  - Added an entry to clear the project-level do-not-translate list and a second confirmation switch for uppercase abbreviations, reducing false positives for UI text such as SMS labels, membership terms, and identifiers.
  - Fixed duplicate entries, empty translation blocks, accidental deletion of comment-only files, natural-language text being skipped, and prompt content being written into the game.
  - Improved in-app update download progress with clearer percentages, theme colors, and download status.

- 2026-08-03 v0.7.3:
  - Fixed structured-output settings being incorrectly applied as a JSON object constraint to interface tests, glossary extraction, AI analysis, single-line translation, and glossary translation. This caused errors such as `Prompt must contain the word 'json'` with DeepSeek.
  - Output-format constraints are now selected per request. Interface parameter errors are no longer retried pointlessly, and the returned reason is shown when a request fails.
  - The default DeepSeek model is now `deepseek-v4-flash` because the official service retired the `deepseek-chat` alias. Old official configurations migrate automatically; custom relay endpoints keep their existing values.
  - The Interface Management page now groups local models, traditional machine translation, online large language models, and custom interfaces, with the active interface shown at the top.
  - Removed interface scaling options below 100% and fixed misaligned controls.

- 2026-07-31 v0.7.2:
  - Added About & Updates to application settings, including manual update checks, release notes, download progress, and cancellation.
  - Added in-app release notes, shown on the first launch after an upgrade.
  - Reworked the Ren'Py toolbox entry and navigation with keyword search, keyboard operation, and project-directory readiness prompts.
  - Fixed inconsistent update-package paths when launching outside the installation directory and missing integrity checks for downloaded packages.
  - Running tasks are now checked before installing an update to avoid silently interrupting translation.

- 2026-07-26 v0.7.1:
  - Fixed Android resource linking for legacy RAPT projects using the Alternative Saves SDK when `res/xml/backup.xml` was missing.

- 2026-07-26 v0.7.0:
  - Reworked the translation workflow with pre-translation checks, task snapshots, and clearer runtime states. Stop, pause, and resume are more reliable.
  - Added project-level world settings, character cards, glossaries, and do-not-translate entries, while fixing migration issues that could overwrite or lose project data.
  - Added initial-translation quality reports, AI proofreading, and polishing, with task cancellation, issue filtering, and batch confirmation and retry.
  - Reworked prompt settings so the base mode, writing style, and output protocol can be selected independently, with options to view and copy the current prompts.
  - Improved one-click translation and the Ren'Py toolbox with direct navigation to RPA unpacking, automatic path transfer, and workflow-oriented tool organization.
  - Fixed token-estimation crashes, cumulative-time jumps, abnormal task states, and crashes during batch font replacement.

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

- UI and some code are adapted from [LinguaGacha](https://github.com/neavo/LinguaGacha) and [AiNiee](https://github.com/NEKOparapa/AiNiee).
- The module design was inspired by [renpy-translator](https://github.com/anonymousException/renpy-translator).
- See the [RenpyBox user tutorial](https://www.bilibili.com/video/BV1KPBoBhEMD) for a walkthrough.
- See the [Ren'Py translation documentation](https://docs.dclef.com/) for more information.
