# -*- coding: utf-8 -*-
"""HakimiSuiteRunner 

特性：
- 扫描 game 目录（排除 tl）提取角色名/文本/变量/replace
- 集成老猫套件 v7.5（多模式版）：外部数据挖掘(.json/.yaml/.yml) + 疯狗模式深度扫描
- 三档模式（标准 / 外部文件 / 外部+疯狗），行为尽量与原脚本一致
- 对比 tl/<lang> 已有 old 翻译，排除重复
- 输出到 translate_output/{1_Excels,2_RPY_Files}，附 AI_Prompt
- 可选生成 Emoji/Tag 保护表（译前/译后）
- 可选先执行官方抽取以刷新 tl
"""

from __future__ import annotations

import os
import re
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence, Set, Tuple

import pandas as pd

from base.LogManager import LogManager
from module.Extract.EmojiReplacer import generate_emoji_replacement_sheets
from module.Extract.RenpyExtractor import RenpyExtractor

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - 可选依赖
    yaml = None


# -------------------- 数据结构 -------------------- #
@dataclass
class HakimiResult:
    names_count: int = 0
    others_count: int = 0
    replace_count: int = 0
    deleted_count: int = 0
    emoji_replacements: int = 0
    base_dir: Optional[Path] = None
    excel_dir: Optional[Path] = None
    rpy_dir: Optional[Path] = None
    emoji_dir: Optional[Path] = None


# -------------------- 核心实现 -------------------- #
class HakimiSuiteRunner:
    def __init__(self, logger: Optional[LogManager] = None, renpy_extractor: Optional[RenpyExtractor] = None) -> None:
        self.logger = logger or LogManager.get()
        self.renpy_extractor = renpy_extractor or RenpyExtractor()

    def run(
        self,
        target_path: str | Path,
        tl_name: str,
        *,
        use_official: bool = False,
        exe_path: str | Path | None = None,
        gen_emoji: bool = False,
        mode: str | int = "1",
    ) -> HakimiResult:
        project_root, game_dir, auto_exe = self._resolve_paths(target_path)
        tl_dir = game_dir / "tl" / tl_name
        mode_str = str(mode).strip() or "1"
        if mode_str not in {"1", "2", "3"}:
            mode_str = "1"
        include_external = mode_str in {"2", "3"}
        mad_dog = mode_str == "3"

        # 可选官方抽取
        if use_official:
            exe = self._pick_exe(exe_path, auto_exe, project_root)
            if exe is None:
                raise FileNotFoundError("开启官方抽取但未找到可执行文件，请手动选择 exe")
            self.logger.info(f"执行官方抽取: {exe}")
            self.renpy_extractor.official_extract(str(exe), tl_name, generate_empty=False, force=True)

        # 扫描源码（安全扫描：屏蔽 tl/saves/cache/gui/images/audio）
        extensions = (".rpy", ".json", ".yaml", ".yml") if include_external else (".rpy",)
        file_list = self._scan_files(game_dir, extensions)
        rpy_files = [p for p in file_list if p.suffix.lower() == ".rpy"]
        external_files = [p for p in file_list if p.suffix.lower() in {".json", ".yaml", ".yml"}]
        names: List[str] = []
        texts: List[str] = []
        variables: List[str] = []
        replaces: List[str] = []
        sandbox_strings: List[str] = []

        self.logger.info(">>> 开始提取...")
        for rpy in rpy_files:
            n, t, v, r = self._extract_strings_from_rpy(rpy)
            names.extend(n)
            texts.extend(t)
            variables.extend(v)
            replaces.extend(r)
            if mad_dog:
                sandbox_strings.extend(self._extract_deep_python_strings(rpy))

        if include_external and external_files:
            sandbox_strings.extend(self._extract_from_external_files(external_files))

        # 过滤
        self.logger.info(">>> 手术级清洗垃圾中...")
        f_names, d_names = self._filter_strings(names)
        f_texts, d_texts = self._filter_strings(texts)
        f_vars, d_vars = self._filter_strings(variables)
        f_replaces, d_replaces = self._filter_strings(replaces)
        f_sandbox, d_sandbox = self._filter_strings(sandbox_strings, strict_mode=True)
        deleted_total = len(d_names) + len(d_texts) + len(d_vars) + len(d_replaces) + len(d_sandbox)
        if mad_dog and d_sandbox:
            self.logger.info("  >>> 疯狗模式：已拦截 %s 条垃圾变量/字符串", len(d_sandbox))

        # 去除已有翻译
        existing_set = self._extract_existing_translations(tl_dir)

        self.logger.info(">>> 对比 SDK 翻译 (%s)...", tl_name)
        final_names = [s for s in f_names if s not in existing_set]
        others_pool = set(f_texts + f_vars)
        final_others = sorted([s for s in others_pool if s not in existing_set and s not in set(final_names)])

        rep_pool = set(f_replaces)
        if f_sandbox:
            used = set(final_names) | set(final_others)
            for s in f_sandbox:
                if s not in existing_set and s not in used:
                    rep_pool.add(s)
        final_replace = sorted(list(rep_pool))

        # 输出目录
        base_out = project_root / "translate_output"
        excel_dir = base_out / "1_Excels"
        rpy_dir = base_out / "2_RPY_Files"
        excel_dir.mkdir(parents=True, exist_ok=True)
        rpy_dir.mkdir(parents=True, exist_ok=True)

        # 写 Excel
        self._save_to_excel(final_names, excel_dir / "names.xlsx", ["Original", "Translation"])
        self._save_to_excel(final_others, excel_dir / "others.xlsx", ["Original", "Translation"])
        self._save_to_excel(final_replace, excel_dir / "replace_text.xlsx", ["Text", "Replacement"])

        # AI Prompt
        ai_prompt = base_out / "AI_Prompt_Names.txt"
        prompt_lines = ["请翻译以下游戏角色名："]
        prompt_lines.extend(final_names)
        ai_prompt.write_text("\n".join(prompt_lines) + "\n", encoding="utf-8")

        # RPY
        self._generate_rpy_file(final_names, rpy_dir / "translate_names.rpy", tl_name)
        self._generate_rpy_file(final_others, rpy_dir / "translate_others.rpy", tl_name)
        if final_replace:
            self._generate_replace_rpy(final_replace, rpy_dir / "replace.rpy", tl_name)

        emoji_dir: Optional[Path] = None
        emoji_count = 0
        if gen_emoji:
            emoji_dir = base_out / "3_Emoji_Tools"
            emoji_dir.mkdir(parents=True, exist_ok=True)
            emoji_count, pre_path, post_path = generate_emoji_replacement_sheets(tl_dir, emoji_dir)
            # 兼容原脚本命名：复制一份 Tag_Protection_*
            try:
                (emoji_dir / "Tag_Protection_Pre(译前).xlsx").write_bytes(pre_path.read_bytes())
                (emoji_dir / "Tag_Protection_Post(译后).xlsx").write_bytes(post_path.read_bytes())
            except Exception:
                pass

        return HakimiResult(
            names_count=len(final_names),
            others_count=len(final_others),
            replace_count=len(final_replace),
            deleted_count=deleted_total,
            emoji_replacements=emoji_count,
            base_dir=base_out,
            excel_dir=excel_dir,
            rpy_dir=rpy_dir,
            emoji_dir=emoji_dir,
        )

    # -------------------- 辅助函数 -------------------- #
    def _resolve_paths(self, target: str | Path) -> Tuple[Path, Path, Optional[Path]]:
        path = Path(target).expanduser().resolve()
        exe_path: Optional[Path] = None
        base = path
        if path.is_file():
            exe_path = path
            base = path.parent
        if base.name.lower() == "game":
            base = base.parent
        game_dir = base / "game"
        if not game_dir.exists():
            raise FileNotFoundError(f"未找到 game 目录: {game_dir}")
        return base, game_dir, exe_path

    def _pick_exe(self, explicit: str | Path | None, auto: Path | None, project_root: Path) -> Optional[Path]:
        if explicit:
            candidate = Path(explicit).expanduser().resolve()
            if candidate.exists():
                return candidate
        if auto and auto.exists():
            return auto
        return self._auto_find_exe(project_root)

    def _auto_find_exe(self, root: Path) -> Optional[Path]:
        for pattern in ("*.exe", "*.py"):
            candidates = [p for p in root.glob(pattern) if p.is_file()]
            if candidates:
                candidates.sort(key=lambda p: p.stat().st_size if p.exists() else 0, reverse=True)
                return candidates[0]
        return None

    def _scan_files(self, root: Path, extensions: Tuple[str, ...]) -> List[Path]:
        # v7.5：仅跳过 tl 目录
        ignored_dirs = {"tl"}
        files: List[Path] = []
        self.logger.info(">>> 开始建立扫描索引 (已屏蔽 tl)...")
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d.lower() not in ignored_dirs]
            for filename in filenames:
                if filename.lower().endswith(extensions):
                    files.append(Path(dirpath) / filename)
        self.logger.info("✔ 索引建立完成。共找到 %s 个有效文件。", len(files))
        return files

    def _filter_strings(self, strings: Sequence[str], *, strict_mode: bool = False) -> Tuple[List[str], List[str]]:
        """老猫 v7.5 过滤逻辑（含 strict_mode：沙盒/疯狗模式）。"""
        filtered_list: List[str] = []
        deleted_list: List[str] = []

        file_extensions = (
            ".mp3",
            ".png",
            ".jpg",
            ".jpeg",
            ".ogg",
            ".wav",
            ".webp",
            ".gif",
            ".avi",
            ".mp4",
            ".mov",
            ".webm",
            ".flv",
            ".wmv",
            ".rpy",
            ".py",
            ".json",
            ".yaml",
            ".yml",
            ".ttf",
            ".otf",
            ".xml",
            ".csv",
        )
        code_keywords = {
            "true",
            "false",
            "none",
            "null",
            "return",
            "jump",
            "call",
            "label",
            "screen",
            "style",
            "transform",
            "image",
            "define",
            "default",
            "init",
            "python",
            "if",
            "else",
            "elif",
            "for",
            "while",
            "in",
            "and",
            "or",
            "not",
            "pass",
            "break",
            "continue",
            "set",
            "get",
            "music",
            "sound",
            "play",
            "stop",
            "scene",
            "show",
            "hide",
            "with",
            "at",
            "persistent",
        }

        for raw in strings:
            s = raw if isinstance(raw, str) else str(raw)
            original = s
            if not s or s.strip() == "":
                deleted_list.append(original)
                continue

            # 老猫套件：含汉字（中日共用区段）默认不抽取（避免把已汉化内容当成待翻译）
            if self._has_chinese(s):
                deleted_list.append(original)
                continue

            lower = s.lower()
            if any(ext in lower for ext in file_extensions) and " " not in s:
                deleted_list.append(original)
                continue
            if s.isdigit():
                deleted_list.append(original)
                continue
            if lower in code_keywords:
                deleted_list.append(original)
                continue

            temp = re.sub(r"\{.*?\}", "", s)
            temp = re.sub(r"\[.*?\]", "", temp)
            if not re.search(r"[\u4e00-\u9fa5a-zA-Z]", temp):
                deleted_list.append(original)
                continue

            if (s.startswith("[") and s.endswith("]")) or (s.startswith("{") and s.endswith("}")):
                if not ("{/" in s or " " in s):
                    deleted_list.append(original)
                    continue

            if s.startswith("#"):
                deleted_list.append(original)
                continue

            if strict_mode:
                if " " not in s and len(s) < 4:
                    deleted_list.append(original)
                    continue
                if s.islower() and "_" in s and " " not in s:
                    deleted_list.append(original)
                    continue
                if s.isupper() and " " not in s:
                    deleted_list.append(original)
                    continue
                if "/" in s and " " not in s:
                    deleted_list.append(original)
                    continue

            filtered_list.append(s)

        return sorted(list(set(filtered_list))), deleted_list

    def _unescape(self, s: str) -> str:
        return s.replace('\\"', '"').replace("\\'", "'").replace("\\\\", "\\")

    def _has_chinese(self, s: str) -> bool:
        return bool(re.search(r"[\u4e00-\u9fa5]", s))

    def _is_camel_case(self, s: str) -> bool:
        return bool(s) and s[0].islower() and any(x.isupper() for x in s) and " " not in s

    def _extract_strings_from_rpy(self, file_path: Path) -> Tuple[List[str], List[str], List[str], List[str]]:
        name_strings: List[str] = []
        text_strings: List[str] = []
        variable_strings: List[str] = []
        replace_strings: List[str] = []

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            self.logger.warning(f"读取失败 {file_path}: {exc}")
            return name_strings, text_strings, variable_strings, replace_strings

        # 角色名
        char_patterns = [
            r'Character\s*\(\s*(["\'])((?:\\\1|.)*?)\1',
            r'define\s+\w+\s*=\s*Character\s*\(\s*(["\'])((?:\\\1|.)*?)\1',
        ]
        for pattern in char_patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                string = self._unescape(match.group(2))
                if not re.search(r'_\s*\(\s*["\']' + re.escape(string), content):
                    name_strings.append(string)

        # 文本
        text_patterns = [
            r'\btext\s+(["\'])((?:\\\1|.)*?)\1\s*:',
            r'\b(text|textbutton|show\s+text)\s+(["\'])((?:\\\2|.)*?)\2',
            r'renpy\.input\s*\(\s*(["\'])((?:\\\1|.)*?)\1',
        ]
        for pattern in text_patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE | re.MULTILINE):
                idx = 3 if pattern == text_patterns[1] else 2
                string = self._unescape(match.group(idx))
                start_pos = match.start()
                line_start = content.rfind('\n', 0, start_pos)
                preceding = content[line_start:start_pos]
                if not re.search(r'_\s*\(\s*$', preceding.strip()):
                    text_strings.append(string)

        # 变量 / 特殊调用
        variable_keywords = [r'default\s+\w+\s*=\s*', r'define\s+\w+\s*=\s*', r'\$\s*\w+\s*=\s*']
        for line in content.split('\n'):
            for keyword in variable_keywords:
                if re.search(keyword, line) and "Character" not in line and not re.search(r'_\s*\(', line):
                    for match in re.finditer(r'(["\'])((?:\\\1|.)*?)\1', line):
                        variable_strings.append(self._unescape(match.group(2)))

            if ('f"' in line or "f'" in line) and not re.search(r'_\s*\(\s*f', line):
                for match in re.finditer(r'f(["\'])((?:\\\1|.)*?)\1', line):
                    replace_strings.append(self._unescape(match.group(2)))

            if re.search(r'^\s*\$\s*(renpy\.notify|csay)\s*\(', line):
                for match in re.finditer(r'(["\'])((?:\\\1|.)*?)\1', line):
                    if not re.search(r'_\s*\(\s*$', line[:match.start()].rstrip()):
                        text_strings.append(self._unescape(match.group(2)))

        tooltip_pattern = r'\btooltip\s*\(\s*(["\'])((?:\\\1|.)*?)\1'
        for match in re.finditer(tooltip_pattern, content, re.IGNORECASE):
            replace_strings.append(self._unescape(match.group(2)))

        return name_strings, text_strings, variable_strings, replace_strings

    def _extract_from_external_files(self, file_list: Sequence[Path]) -> List[str]:
        self.logger.info("  >>> 启动 [外部挖掘机] ...")
        found: List[str] = []
        for path in file_list:
            ext = path.suffix.lower()
            if ext not in {".json", ".yaml", ".yml"}:
                continue

            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            try:
                data: Any
                if ext == ".json":
                    data = json.loads(text)
                else:
                    if yaml is None:
                        self.logger.warning("未安装 PyYAML，已跳过: %s", path.name)
                        continue
                    data = yaml.safe_load(text)
                if data is not None:
                    self._recursive_find_strings(data, found)
            except Exception:
                continue

        self.logger.info("  >>> 外部提取: %s 条", len(found))
        return found

    def _recursive_find_strings(self, data: Any, found_list: List[str]) -> None:
        if isinstance(data, str):
            found_list.append(data)
        elif isinstance(data, list):
            for item in data:
                self._recursive_find_strings(item, found_list)
        elif isinstance(data, dict):
            for value in data.values():
                self._recursive_find_strings(value, found_list)

    def _extract_deep_python_strings(self, path: Path) -> List[str]:
        """疯狗模式：抽取 rpy 里所有引号字符串（后续用 strict_mode 强力过滤）。"""
        found: List[str] = []
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return found
        matches = re.findall(r'(["\'])((?:\\\1|.)*?)\1', content)
        for _, s in matches:
            found.append(self._unescape(s))
        return found

    def _extract_existing_translations(self, tl_dir: Path) -> Set[str]:
        existing: Set[str] = set()
        if not tl_dir.exists():
            return existing
        for rpy in tl_dir.rglob("*.rpy"):
            try:
                content = rpy.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            olds = re.findall(r'^\s*old\s+(["\'])((?:\\\1|.)*?)\1', content, re.MULTILINE)
            for _, s in olds:
                existing.add(self._unescape(s))
        return existing

    def _save_to_excel(self, strings: Sequence[str], path: Path, headers: Sequence[str]) -> None:
        df = pd.DataFrame({headers[0]: strings, headers[1]: [''] * len(strings)})
        df.to_excel(path, index=False)
        try:
            from openpyxl import load_workbook

            wb = load_workbook(path)
            ws = wb.active
            ws.column_dimensions["A"].width = 50
            ws.column_dimensions["B"].width = 50
            wb.save(path)
        except Exception:
            pass
        self.logger.info("已保存 %s 条到 %s", len(strings), path)

    def _generate_rpy_file(self, strings: Sequence[str], output_path: Path, lang_folder: str) -> None:
        if not strings:
            return
        lines = [f"translate {lang_folder} strings:", ""]
        for s in strings:
            escaped = s.replace('"', '\\"')
            lines.append(f'    old "{escaped}"')
            lines.append('    new ""')
            lines.append("")
        output_path.write_text("\n".join(lines), encoding="utf-8")

    def _generate_replace_rpy(self, strings: Sequence[str], output_path: Path, lang_folder: str) -> None:
        if not strings:
            return
        sorted_strings = sorted(list(set(strings)), key=len, reverse=True)
        lines = [
            "init python:",
            "    # Generated by Sandbox Special Edition",
            f'    if preferences.language == "{lang_folder}":',
            "        def replace_text(s):",
            "            if not isinstance(s, str): return s",
        ]
        for s in sorted_strings:
            escaped = s.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'            s = s.replace("{escaped}", "{escaped}") # 待翻译: {escaped}')
        lines.extend([
            "            return s",
            "        config.replace_text = replace_text",
        ])
        output_path.write_text("\n".join(lines), encoding="utf-8")


__all__ = ["HakimiSuiteRunner", "HakimiResult"]
