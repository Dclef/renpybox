# -*- coding: utf-8 -*-
"""MaExtractor - 集成自“翻译套件”的抽取后处理流程。

该模块在官方/补充抽取结束后运行，用于：
- 扫描游戏源码中可能需要翻译的字符串（角色名、对白、变量、替换文本）
- 应用统一的过滤规则，生成 Excel 表格和删除日志
- 根据过滤后的结果生成终极结构：`translate_names.rpy`、`translate_others.rpy`
- 生成 replace_text 钩子和角色名 AI 提示词

实现要点：
- 正则与判定逻辑来自原脚本，替换为项目内的 `filter_extracted_strings` 规则
- 对 pandas/openpyxl 做兼容处理，缺失依赖时退化为 CSV 输出
- 保留原脚本的目录结构 (translate/1_待翻译Excel 等)，便于沿用既往工作流
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from base.LogManager import LogManager
from module.Config import Config
from module.Text.SkipRules import filter_extracted_strings

try:  # pandas / openpyxl 为可选依赖
    import pandas as _pd  # type: ignore
except Exception:  # pragma: no cover - 环境缺少 pandas 时记录日志并退化
    _pd = None


@dataclass
class MaExtractorResult:
    """导出流程的统计结果"""

    names_count: int = 0
    others_count: int = 0
    replace_count: int = 0
    deleted_count: int = 0
    emoji_replacements: int = 0
    emoji_output_dir: Optional[Path] = None
    excel_paths: Dict[str, Path] = field(default_factory=dict)
    result_dir: Optional[Path] = None


class MaExtractor:
    """封装“终极结构”导出流程。"""

    def __init__(self, logger: Optional[LogManager] = None) -> None:
        self.logger = logger or LogManager.get()

    # ------------------------------------------------------------------
    # 对外接口
    # ------------------------------------------------------------------
    def run(
        self,
        project_root: Path,
        tl_name: str,
        preserve_set: Set[str],
        existing_translations: Dict[str, str],
        config: Config,
    ) -> Optional[MaExtractorResult]:
        """执行终极结构导出。

        Args:
            project_root: 游戏工程根目录
            tl_name: tl 语言名称
            preserve_set: 禁翻集合
            existing_translations: 已有翻译映射，用于排除重复
            config: 全局配置，控制是否拆分角色名等
        """

        game_dir = project_root / "game"
        if not game_dir.exists():
            self.logger.warning(f"终极结构导出跳过：未找到 game 目录 ({game_dir})")
            return None

        tl_dir = game_dir / "tl" / tl_name
        if not tl_dir.exists():
            # 保持兼容：允许在未进行官方抽取时仍然基于源码导出 Excel/终极结构
            self.logger.info(f"未找到 tl 目录 ({tl_dir})，将仅基于源码生成结果")

        translate_root = project_root / "translate"
        excel_dir = translate_root / "1_待翻译Excel"
        translated_dir = translate_root / "2_已翻译Excel(来自旧版)"
        result_dir = translate_root / "3_最终成果"
        for directory in (translate_root, excel_dir, translated_dir, result_dir):
            directory.mkdir(parents=True, exist_ok=True)

        # 1. 扫描源码提取候选字符串
        tl_exclude = game_dir / "tl"
        rpy_files = self._scan_directory_for_rpy(game_dir, exclude_dirs={tl_exclude})
        name_candidates: List[str] = []
        text_candidates: List[str] = []
        variable_candidates: List[str] = []
        replace_candidates: List[str] = []
        deleted_all: List[str] = []

        for rpy_path in rpy_files:
            names, texts, variables, replace_strings = self._extract_strings_from_rpy(rpy_path)
            name_candidates.extend(names)
            text_candidates.extend(texts)
            variable_candidates.extend(variables)
            replace_candidates.extend(replace_strings)

        # 2. 统一过滤
        extra_checks: Sequence = ()
        filtered_names, deleted_names = filter_extracted_strings(
            name_candidates, preserve_set, extra_checks
        )
        filtered_texts, deleted_texts = filter_extracted_strings(
            text_candidates, preserve_set, extra_checks
        )
        filtered_variables, deleted_variables = filter_extracted_strings(
            variable_candidates, preserve_set, extra_checks
        )
        filtered_replace, deleted_replace = filter_extracted_strings(
            replace_candidates, preserve_set, extra_checks
        )
        deleted_all.extend(deleted_names + deleted_texts + deleted_variables + deleted_replace)

        # 3. Excel 导出
        excel_paths: Dict[str, Path] = {}
        excel_paths["name"] = self._save_to_excel(
            filtered_names,
            excel_dir / "name.xlsx",
            ["Original Text (原文)", "Translation (在此填入译文)", "Description (备注)"],
            is_name_file=True,
        )
        excel_paths["text"] = self._save_to_excel(
            filtered_texts,
            excel_dir / "text.xlsx",
            ["Original Text (原文)", "Translation (在此填入译文)"],
        )
        excel_paths["variable"] = self._save_to_excel(
            filtered_variables,
            excel_dir / "variable.xlsx",
            ["Original Text (原文)", "Translation (在此填入译文)"],
        )
        excel_paths["replace"] = self._save_to_excel(
            filtered_replace,
            excel_dir / "replace.xlsx",
            ["Original Text (原文)", "Translation (在此填入译文)"],
        )

        self._save_deleted_strings(deleted_all, result_dir / "deleted_strings_log.txt")
        self._generate_ai_prompt(filtered_names, result_dir / "character_glossary_prompt.txt")

        # 4. 生成终极结构 rpy
        old_strings_set = {k for k, v in existing_translations.items() if v}

        names_to_translate: List[str]
        if config.extract_split_names:
            names_to_translate = [s for s in filtered_names if s not in old_strings_set]
        else:
            names_to_translate = []

        combined_others = list({
            s for s in filtered_texts + filtered_variables if s and s not in filtered_names
        })
        others_to_translate = [
            s for s in sorted(combined_others)
            if s not in old_strings_set
        ]

        translate_names_path = result_dir / "translate_names.rpy"
        translate_others_path = result_dir / "translate_others.rpy"
        replace_rpy_path = result_dir / "replace.rpy"

        if config.extract_split_names:
            self._generate_old_new_file(names_to_translate, translate_names_path, tl_name)
        else:
            translate_names_path.unlink(missing_ok=True)

        self._generate_old_new_file(others_to_translate, translate_others_path, tl_name)
        self._generate_replace_file(filtered_replace, tl_name, replace_rpy_path, existing_translations)

        result = MaExtractorResult(
            names_count=len(names_to_translate),
            others_count=len(others_to_translate),
            replace_count=len(filtered_replace),
            deleted_count=len(deleted_all),
            excel_paths=excel_paths,
            result_dir=result_dir,
        )

        self.logger.info(
            "终极结构导出完成: names=%s, others=%s, replace=%s",
            result.names_count,
            result.others_count,
            result.replace_count,
        )
        return result

    # ------------------------------------------------------------------
    # 源码解析
    # ------------------------------------------------------------------
    def _scan_directory_for_rpy(self, root: Path, *, exclude_dirs: Set[Path]) -> List[Path]:
        files: List[Path] = []
        normalized_exclude = {p.resolve() for p in exclude_dirs}
        for dirpath, dirnames, filenames in os.walk(root):
            current = Path(dirpath).resolve()
            if any(current == ex or str(current).startswith(str(ex) + os.sep) for ex in normalized_exclude):
                continue
            for filename in filenames:
                if filename.endswith(".rpy"):
                    files.append(Path(dirpath) / filename)
        return files

    def _extract_strings_from_rpy(self, file_path: Path) -> Tuple[List[str], List[str], List[str], List[str]]:
        """从 rpy 文件中提取角色名 / 文本 / 变量 / replace 字符串"""
        name_strings: List[str] = []
        text_strings: List[str] = []
        variable_strings: List[str] = []
        replace_strings: List[str] = []

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:  # pragma: no cover - IO 失败时跳过
            self.logger.warning(f"读取 {file_path} 失败: {exc}")
            return name_strings, text_strings, variable_strings, replace_strings

        # 角色名匹配
        char_patterns = [
            r'Character\s*\(\s*(["\'])((?:\\\1|.)*?)\1',
            r'define\s+\w+\s*=\s*Character\s*\(\s*(["\'])((?:\\\1|.)*?)\1',
        ]
        for pattern in char_patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                raw_name = match.group(2)
                cleaned = self._unescape(raw_name)
                if cleaned:
                    name_strings.append(cleaned)

        # 文本相关匹配
        text_patterns = [
            r'\btext\s+(["\'])((?:\\\1|.)*?)\1\s*:',
            r'\b(?:text|textbutton|show\s+text)\s+(["\'])((?:\\\1|.)*?)\1',
            r'renpy\.input\s*\(\s*(["\'])((?:\\\1|.)*?)\1',
        ]
        for pattern in text_patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE | re.MULTILINE):
                raw_text = match.group(2) if len(match.groups()) >= 2 else ""
                cleaned = self._unescape(raw_text)
                if cleaned:
                    text_strings.append(cleaned)

        # 变量 & 替换文本
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped:
                continue

            if re.search(r'default\s+\w+\s*=\s*', line) or re.search(r'define\s+\w+\s*=\s*', line) or re.search(r'\$\s*\w+\s*=\s*', line):
                for match in re.finditer(r'(["\'])((?:\\\1|.)*?)\1', line):
                    variable_strings.append(self._unescape(match.group(2)))

            if ('f"' in line or "f'" in line) and '_.(' not in line:
                for match in re.finditer(r'f(["\'])((?:\\\1|.)*?)\1', line):
                    replace_strings.append(self._unescape(match.group(2)))

            if re.search(r'\bcall\s+.*\s+from\b', line):
                for match in re.finditer(r'(["\'])((?:\\\1|.)*?)\1', line):
                    text_strings.append(self._unescape(match.group(2)))

            if re.search(r'renpy\.notify\s*\(', line):
                for match in re.finditer(r'renpy\.notify\s*\(\s*(["\'])((?:\\\1|.)*?)\1', line):
                    text_strings.append(self._unescape(match.group(2)))

        tooltip_pattern = r'\btooltip\s*\(\s*(["\'])((?:\\\1|.)*?)\1'
        for match in re.finditer(tooltip_pattern, content, re.IGNORECASE):
            replace_strings.append(self._unescape(match.group(2)))

        return name_strings, text_strings, variable_strings, replace_strings

    # ------------------------------------------------------------------
    # 输出工具
    # ------------------------------------------------------------------
    def _save_to_excel(
        self,
        strings: List[str],
        file_path: Path,
        headers: Sequence[str],
        *,
        is_name_file: bool = False,
    ) -> Path:
        if not strings:
            file_path.unlink(missing_ok=True)
            return file_path

        if _pd is None:
            # 退化为 csv
            lines = [",".join(headers)]
            for value in strings:
                row = [value, "", "character" if (is_name_file and len(headers) > 2) else ""]
                lines.append(",".join(row))
            file_path.with_suffix(".csv").write_text("\n".join(lines), encoding="utf-8")
            self.logger.warning("缺少 pandas/openpyxl，已退化为 CSV: %s", file_path.with_suffix(".csv"))
            return file_path.with_suffix(".csv")

        data: Dict[str, List[str]] = {}
        data[headers[0]] = strings
        data[headers[1]] = ["" for _ in strings]
        if is_name_file and len(headers) > 2:
            data[headers[2]] = ["character" for _ in strings]

        df = _pd.DataFrame(data)
        try:
            df.to_excel(file_path, index=False, header=True, engine="openpyxl")
        except Exception as exc:
            self.logger.warning("写入 Excel 失败 (%s)，尝试 CSV: %s", exc, file_path)
            csv_path = file_path.with_suffix(".csv")
            df.to_csv(csv_path, index=False, header=True, encoding="utf-8-sig")
            return csv_path
        return file_path

    def _save_deleted_strings(self, strings: Iterable[str], output_file: Path) -> None:
        unique = sorted({s for s in strings if s})
        if not unique:
            output_file.unlink(missing_ok=True)
            return
        lines = [
            "--- 以下为根据过滤规则排除的字符串 ---",
            "--- 请视情况手动复核 ---",
            "",
        ]
        lines.extend(unique)
        output_file.write_text("\n".join(lines), encoding="utf-8")

    def _generate_ai_prompt(self, names: Sequence[str], output_path: Path) -> None:
        if not names:
            output_path.unlink(missing_ok=True)
            return
        lines = [
            "### 游戏角色名库 (翻译时请严格遵守)",
            "格式: 原文: 译文",
            "-------------------------------------",
        ]
        lines.extend(f"{name}: " for name in names)
        lines.append("-------------------------------------")
        output_path.write_text("\n".join(lines), encoding="utf-8")

    def _generate_old_new_file(self, strings: Sequence[str], output_file: Path, tl_name: str) -> None:
        if not strings:
            output_file.unlink(missing_ok=True)
            return
        lines = [f"translate {tl_name} strings:", ""]
        for text in strings:
            escaped = text.replace('"', '\\"')
            lines.append(f'    old "{escaped}"')
            lines.append('    new ""')
            lines.append("")
        output_file.write_text("\n".join(lines), encoding="utf-8")

    def _generate_replace_file(
        self,
        replace_strings: Sequence[str],
        tl_name: str,
        output_file: Path,
        existing_translations: Dict[str, str],
    ) -> None:
        if not replace_strings:
            output_file.unlink(missing_ok=True)
            return

        mapping: Dict[str, str] = {}
        for text in replace_strings:
            mapping[text] = existing_translations.get(text, "")

        lines = [
            "init python:",
            "    # 自动生成的 replace_text 函数",
            f"    if preferences.language == \"{tl_name}\":",
            "        def replace_text(s):",
            "            if not isinstance(s, str):",
            "                return s",
            "",
        ]

        for old_text, new_text in sorted(mapping.items(), key=lambda kv: len(kv[0]), reverse=True):
            escaped_old = old_text.replace('\\', '\\\\').replace('"', '\\"')
            escaped_new = new_text.replace('\\', '\\\\').replace('"', '\\"')
            lines.append(f'            s = s.replace("{escaped_old}", "{escaped_new}")')

        lines.extend([
            "            return s",
            "        config.replace_text = replace_text",
            "    else:",
            "        def replace_text(s):",
            "            return s",
            "        config.replace_text = replace_text",
        ])
        output_file.write_text("\n".join(lines), encoding="utf-8")

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------
    def _unescape(self, text: str) -> str:
        return (
            text
            .replace('\\"', '"')
            .replace("\\'", "'")
            .replace('\\\\', '\\')
            .strip()
        )


__all__ = ["MaExtractor", "MaExtractorResult"]
