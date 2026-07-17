# -*- coding: utf-8 -*-
"""
UnifiedExtractor - 统一翻译提取接口

设计目标：
1. 简化调用：提供 extract_regular 和 extract_incremental 两个核心方法
2. 统一逻辑：合并官方抽取、自定义抽取、过滤、清理等步骤
3. 健壮性：统一处理路径、备份、异常
"""

from __future__ import annotations

import ast
import csv
import os
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Set, Callable, List, Tuple

from base.PathHelper import get_resource_path
from base.LogManager import LogManager
from module.Config import Config
from module.Extract.RenpyExtractor import RenpyExtractor
from module.Extract.MaExtractor import MaExtractor
from module.Extract.JsonExtractor import JsonExtractor
from module.Renpy.renpy_tl_io import RenpyTlItemExtractor
from module.Renpy.renpy_tl_core import (
    parse_tl_document,
    scan_quoted_literals,
    escape_tl_string,
)
from module.Renpy.renpy_tl_io import RenpyTlLineUpdater
from module.Renpy.renpy_tl_core import TlStmtKind
from module.Renpy import renpy_extract as rx
from module.Text.SkipRules import should_skip_text


@dataclass
class ExtractionResult:
    """提取结果"""
    success: bool = True
    message: str = ""
    tl_dir: Optional[Path] = None
    new_strings: int = 0
    total_files: int = 0
    incremental_dir: Optional[Path] = None  # 增量抽取的新增内容目录
    preserved_count: int = 0  # 保留的已有翻译数量


class UnifiedExtractor:
    """
    统一翻译提取器
    """

    # Escape-aware old/new line match. Uses backreference so text like "Don't" won't be truncated.
    OLD_LINE_RE = re.compile(r'^\s*old\s+(["\'])(?P<text>(?:\\.|(?!\1).)*?)\1\s*$', re.MULTILINE)
    NEW_LINE_RE = re.compile(r'^\s*new\s+(["\'])(?P<text>(?:\\.|(?!\1).)*?)\1\s*$', re.MULTILINE)
    BUILTIN_UI_DIRS = {"base_box"}
    BUILTIN_UI_FILES = {
        "common.rpy",
        "screens.rpy",
        "common_box.rpy",
        "screens_box.rpy",
        "style_box.rpy",
    }
    AUTO_SCREEN_FILE = "auto_screens_default.rpy"
    INTERNAL_TL_DIRS = {"_filtered_suspicious"}
    SUSPICIOUS_BACKUP_DIR = "_filtered_suspicious"
    SUSPICIOUS_MANIFEST_NAME = "restore_manifest.csv"
    SUSPICIOUS_BOOL_EXPR_RE = re.compile(
        r"\b[A-Za-z_][A-Za-z0-9_]*\b\s*(?:==|!=|=)\s*(?:True|False|true|false)\b"
    )
    
    def __init__(self, renpy_extractor: Optional[RenpyExtractor] = None):
        self.logger = LogManager.get()
        self.renpy_extractor = renpy_extractor or RenpyExtractor()
        self._progress_callback: Optional[Callable[[str, int], None]] = None
        self._last_suspicious_manifest: Optional[Path] = None
        self._last_suspicious_removed_count: int = 0

    def _warn_if_writeback_report(self, tl_dir: Path) -> None:
        report_path = tl_dir / "writeback_report_renpy.json"
        if not report_path.exists():
            return
        try:
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(report_path.stat().st_mtime))
        except Exception:
            ts = "unknown"
        self.logger.warning(
            f"检测到翻译写回报告 {report_path} (mtime={ts})，本次抽取可能覆盖译文"
        )
    
    def set_progress_callback(self, callback: Optional[Callable[[str, int], None]]):
        """设置进度回调 (message, percent)"""
        self._progress_callback = callback

    def extract_json(self, game_dir: Path, output_dir: Path) -> ExtractionResult:
        """
        Extracts all .rpy files in game_dir to .json files in output_dir.
        """
        self._emit_progress("Starting JSON extraction...", 0)
        try:
            extractor = JsonExtractor()
            extractor.extract_directory(game_dir, output_dir)
            
            # Count files
            total_files = len(list(output_dir.rglob("*.json")))
            
            self._emit_progress("JSON extraction completed.", 100)
            return ExtractionResult(
                success=True,
                message=f"Successfully extracted {total_files} files to JSON.",
                tl_dir=output_dir,
                total_files=total_files
            )
        except Exception as e:
            self.logger.error(f"JSON extraction failed: {e}")
            return ExtractionResult(success=False, message=str(e))
    
    def _emit_progress(self, message: str, percent: int):
        self.logger.info(f"[{percent}%] {message}")
        if self._progress_callback:
            self._progress_callback(message, percent)

    def _is_builtin_ui_file(self, path: Path) -> bool:
        """检查是否为内置 UI/字体模板文件"""
        try:
            name = path.name.lower()
            if name in self.BUILTIN_UI_FILES:
                return True
            if path.parent.name.lower() in self.BUILTIN_UI_DIRS:
                return True
        except Exception:
            pass
        return False

    def _iter_rpy_files(self, tl_dir: Path):
        """遍历 tl 目录下的 rpy 文件，自动跳过内置 UI/模板文件"""
        for rpy_file in tl_dir.rglob("*.rpy"):
            try:
                rel_parts = [part.lower() for part in rpy_file.relative_to(tl_dir).parts[:-1]]
                if any(part in self.INTERNAL_TL_DIRS for part in rel_parts):
                    continue
            except Exception:
                pass
            # 缺失补丁：仅作为生成 replace_text 的中间文件，不应参与抽取/增量统计与后处理
            if rpy_file.name.startswith("miss_ready_replace"):
                continue
            if self._is_builtin_ui_file(rpy_file):
                self.logger.debug(f"跳过内置 UI 文件: {rpy_file}")
                continue
            yield rpy_file

    def _deploy_builtin_ui_pack(self, tl_dir: Path, tl_name: str) -> int:
        """将内置 base_box（UI 文本翻译）注入到 tl 目录，避免后续重复翻译 UI。

        同时会对 `tl_dir` 内现有翻译进行一次冲突处理，避免 Ren'Py 因重复 strings 翻译崩溃：
        - 若其他文件仅存在占位翻译（new == "" 或 new == old），删除这些占位条目，保留 base_box 翻译；
        - 若 screens/common 存在有效翻译且 base_box 为占位，则用其补全 base_box，并清理重复条目。
        """
        try:
            src_dir = Path(get_resource_path("resource", "base_box"))
            if not src_dir.exists():
                return 0

            dest_dir = tl_dir / "base_box"
            dest_dir.mkdir(parents=True, exist_ok=True)

            def decode_literal(quote: str, text: str) -> str:
                literal = f"{quote}{text}{quote}"
                try:
                    return ast.literal_eval(literal)
                except Exception:
                    return text.replace('\\"', '"').replace("\\'", "'")

            def iter_old_new_pairs(lines: List[str]) -> List[Tuple[str, str]]:
                pairs: List[Tuple[str, str]] = []
                i = 0
                while i < len(lines):
                    old_match = self.OLD_LINE_RE.match(lines[i])
                    if old_match and i + 1 < len(lines):
                        j = i + 1
                        while j < len(lines):
                            probe = lines[j].strip()
                            if not probe or probe.startswith("#"):
                                j += 1
                                continue
                            break
                        if j < len(lines):
                            new_match = self.NEW_LINE_RE.match(lines[j])
                        else:
                            new_match = None
                        if new_match:
                            old_value = decode_literal(old_match.group(1), old_match.group("text"))
                            new_value = decode_literal(new_match.group(1), new_match.group("text"))
                            pairs.append((old_value, new_value))
                            i = j + 1
                            continue
                    i += 1
                return pairs

            def collect_base_box_entries() -> Tuple[Set[str], Set[str]]:
                base_old: Set[str] = set()
                placeholder_old: Set[str] = set()
                for fn in ("common_box.rpy", "screens_box.rpy"):
                    fp = src_dir / fn
                    if not fp.is_file():
                        continue
                    try:
                        lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
                    except Exception:
                        continue
                    for old_value, new_value in iter_old_new_pairs(lines):
                        base_old.add(old_value)
                        if new_value == "" or new_value == old_value:
                            placeholder_old.add(old_value)
                return base_old, placeholder_old

            def remove_string_entries_by_old_values(file_path: Path, olds_to_remove: Set[str]) -> int:
                if not olds_to_remove:
                    return 0
                try:
                    lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
                except Exception:
                    return 0

                removed = 0
                new_lines: List[str] = []
                i = 0
                changed = False
                while i < len(lines):
                    old_match = self.OLD_LINE_RE.match(lines[i])
                    if old_match and i + 1 < len(lines):
                        j = i + 1
                        while j < len(lines):
                            probe = lines[j].strip()
                            if not probe or probe.startswith("#"):
                                j += 1
                                continue
                            break
                        if j < len(lines):
                            new_match = self.NEW_LINE_RE.match(lines[j])
                        else:
                            new_match = None
                        if new_match:
                            old_value = decode_literal(old_match.group(1), old_match.group("text"))
                            if old_value in olds_to_remove:
                                removed += 1
                                changed = True
                                i = j + 1
                                continue
                            new_lines.extend(lines[i : j + 1])
                            i = j + 1
                            continue
                    new_lines.append(lines[i])
                    i += 1

                if changed:
                    # 清理连续空行
                    cleaned: List[str] = []
                    prev_empty = False
                    for line in new_lines:
                        is_empty = not line.strip()
                        if is_empty and prev_empty:
                            continue
                        cleaned.append(line)
                        prev_empty = is_empty
                    file_path.write_text("\n".join(cleaned).rstrip() + "\n", encoding="utf-8")
                    try:
                        rx.remove_repeat_for_file(str(file_path))
                    except Exception:
                        pass
                return removed

            def is_extracted_ui_file(file_path: Path) -> bool:
                return file_path.name.lower() in {"common.rpy", "screens.rpy"}

            def apply_overrides_to_base_box(
                file_path: Path,
                overrides: Dict[str, str],
                placeholder_olds: Set[str],
            ) -> int:
                if not overrides or not placeholder_olds:
                    return 0
                try:
                    lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
                except Exception:
                    return 0

                updated = 0
                i = 0
                while i < len(lines):
                    old_match = self.OLD_LINE_RE.match(lines[i])
                    if old_match:
                        old_value = decode_literal(old_match.group(1), old_match.group("text"))
                        if old_value in placeholder_olds and old_value in overrides:
                            j = i + 1
                            while j < len(lines):
                                probe = lines[j].strip()
                                if not probe or probe.startswith("#"):
                                    j += 1
                                    continue
                                break
                            if j < len(lines):
                                new_match = self.NEW_LINE_RE.match(lines[j])
                            else:
                                new_match = None
                            if new_match:
                                indent_match = re.match(r'^(\s*)new', lines[j])
                                indent = indent_match.group(1) if indent_match else ""
                                escaped = self._escape_rpy_string(overrides[old_value])
                                lines[j] = f'{indent}new "{escaped}"'
                                updated += 1
                                i = j + 1
                                continue
                    i += 1

                if updated:
                    file_path.write_text("\n".join(lines), encoding="utf-8")
                return updated

            injected = 0
            removed_placeholders = 0
            removed_ui_duplicates = 0
            overrides_applied = 0

            base_box_old_set, base_box_placeholder_set = collect_base_box_entries()
            ui_translation_overrides: Dict[str, str] = {}
            ui_files: List[Path] = []

            # 1) 先扫描 tl_dir 里的其它文件：清理占位翻译，并收集 screens/common 的有效翻译用于补全 base_box 占位。
            for rpy_file in tl_dir.rglob("*.rpy"):
                try:
                    rel = rpy_file.relative_to(tl_dir)
                    if any(part.lower() in self.BUILTIN_UI_DIRS for part in rel.parts):
                        continue
                except Exception:
                    pass

                try:
                    lines = rpy_file.read_text(encoding="utf-8", errors="replace").splitlines()
                except Exception:
                    continue

                if is_extracted_ui_file(rpy_file):
                    ui_files.append(rpy_file)

                placeholder_olds: Set[str] = set()
                for old_value, new_value in iter_old_new_pairs(lines):
                    if old_value not in base_box_old_set:
                        continue
                    if new_value == "" or new_value == old_value:
                        placeholder_olds.add(old_value)
                        continue
                    if is_extracted_ui_file(rpy_file):
                        ui_translation_overrides.setdefault(old_value, new_value)

                if placeholder_olds:
                    removed_placeholders += remove_string_entries_by_old_values(rpy_file, placeholder_olds)

            # 处理占位清理后可能出现的空 strings 块（例如仅剩 `translate xxx strings:`），避免 Ren'Py 解析报错。
            try:
                self._remove_empty_translate_blocks(tl_dir, tl_name)
            except Exception:
                pass

            for filename in ("common_box.rpy", "screens_box.rpy"):
                src = src_dir / filename
                if not src.is_file():
                    continue

                content = src.read_text(encoding="utf-8", errors="replace")
                # 支持旧模板（schinese 占位）与新版 {tl_name} 占位
                content = content.replace("translate schinese", f"translate {tl_name}")
                content = content.replace("tl/schinese", f"tl/{tl_name}")
                content = content.replace("{tl_name}", tl_name)

                dest_file = dest_dir / filename
                dest_file.write_text(content, encoding="utf-8")

                # 2) 对 base_box 的占位翻译进行补全（仅在 new=="" 或 new==old 时使用 screens/common 的翻译）。
                overrides_applied += apply_overrides_to_base_box(
                    dest_file, ui_translation_overrides, base_box_placeholder_set
                )

                # 若过滤后无任何 old 条目，直接删除文件（否则会留下空 translate 块导致 Ren'Py 报错）
                try:
                    final_text = dest_file.read_text(encoding="utf-8", errors="replace")
                    if not self.OLD_LINE_RE.search(final_text):
                        dest_file.unlink()
                        continue
                except Exception:
                    pass

                injected += 1

            if ui_files and base_box_old_set:
                for ui_file in ui_files:
                    removed_ui_duplicates += remove_string_entries_by_old_values(ui_file, base_box_old_set)
                    try:
                        remain_text = ui_file.read_text(encoding="utf-8", errors="replace")
                        if not self.OLD_LINE_RE.search(remain_text):
                            ui_file.unlink()
                    except Exception:
                        pass

            if removed_placeholders or removed_ui_duplicates or overrides_applied:
                self.logger.info(
                    f"已清理 base_box 冲突: 删除占位 {removed_placeholders} 条，"
                    f"清理重复 {removed_ui_duplicates} 条，补全占位 {overrides_applied} 条"
                )

            return injected
        except Exception as exc:
            self.logger.warning(f"注入内置 base_box 失败: {exc}")
            return 0

    def _decode_literal_value(self, quote: str, text: str) -> str:
        """解析 old/new 字面量文本，兼容转义。"""
        literal = f"{quote}{text}{quote}"
        try:
            return ast.literal_eval(literal)
        except Exception:
            return text.replace('\\"', '"').replace("\\'", "'")

    def _collect_base_box_old_values(self, tl_dir: Path) -> Set[str]:
        """收集 base_box 中所有 old 原文。"""
        base_dir = tl_dir / "base_box"
        if not base_dir.exists():
            return set()

        olds: Set[str] = set()
        for rpy_file in base_dir.rglob("*.rpy"):
            try:
                lines = rpy_file.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception:
                continue
            for line in lines:
                old_match = self.OLD_LINE_RE.match(line)
                if not old_match:
                    continue
                old_value = self._decode_literal_value(old_match.group(1), old_match.group("text"))
                if old_value:
                    olds.add(old_value)
        return olds

    def _remove_placeholder_duplicates_for_base_box(self, tl_dir: Path, tl_name: str) -> int:
        """清理 base_box 重复；有效人工译文先迁移到 base_box 再删除重复项。"""
        base_old_set = self._collect_base_box_old_values(tl_dir)
        if not base_old_set:
            return 0

        removed_total = 0
        translation_overrides: Dict[str, str] = {}
        for rpy_file in sorted(tl_dir.rglob("*.rpy"), key=lambda item: item.as_posix()):
            try:
                rel = rpy_file.relative_to(tl_dir)
                if any(part.lower() == "base_box" for part in rel.parts):
                    continue
            except Exception:
                pass

            try:
                lines = rpy_file.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception:
                continue

            new_lines: List[str] = []
            i = 0
            changed = False

            while i < len(lines):
                old_match = self.OLD_LINE_RE.match(lines[i])
                if old_match:
                    old_value = self._decode_literal_value(old_match.group(1), old_match.group("text"))

                    j = i + 1
                    while j < len(lines):
                        probe = lines[j].strip()
                        if not probe or probe.startswith("#"):
                            j += 1
                            continue
                        break

                    new_value = ""
                    if j < len(lines):
                        new_match = self.NEW_LINE_RE.match(lines[j])
                        if new_match:
                            new_value = self._decode_literal_value(new_match.group(1), new_match.group("text"))

                    if old_value in base_old_set:
                        if new_value and new_value != old_value:
                            # 普通 TL 中的有效人工译文优先于内置包；先暂存，
                            # 稍后覆盖 base_box，再删除此处重复以保持全局唯一。
                            translation_overrides.setdefault(old_value, new_value)
                        removed_total += 1
                        changed = True
                        i = j + 1 if j > i else i + 1
                        continue

                new_lines.append(lines[i])
                i += 1

            if changed:
                cleaned: List[str] = []
                prev_empty = False
                for line in new_lines:
                    is_empty = not line.strip()
                    if is_empty and prev_empty:
                        continue
                    cleaned.append(line)
                    prev_empty = is_empty
                rpy_file.write_text("\n".join(cleaned).rstrip() + "\n", encoding="utf-8")

        if translation_overrides:
            base_dir = tl_dir / "base_box"
            for base_file in sorted(base_dir.rglob("*.rpy"), key=lambda item: item.as_posix()):
                try:
                    lines = base_file.read_text(
                        encoding="utf-8", errors="replace"
                    ).splitlines()
                except Exception:
                    continue
                changed = False
                i = 0
                while i < len(lines):
                    old_match = self.OLD_LINE_RE.match(lines[i])
                    if not old_match:
                        i += 1
                        continue
                    old_value = self._decode_literal_value(
                        old_match.group(1), old_match.group("text")
                    )
                    override = translation_overrides.get(old_value)
                    if override is None:
                        i += 1
                        continue
                    j = i + 1
                    while j < len(lines) and (
                        not lines[j].strip() or lines[j].lstrip().startswith("#")
                    ):
                        j += 1
                    if j < len(lines) and self.NEW_LINE_RE.match(lines[j]):
                        indent = lines[j][: len(lines[j]) - len(lines[j].lstrip())]
                        lines[j] = f'{indent}new "{self._escape_rpy_string(override)}"'
                        changed = True
                        i = j + 1
                        continue
                    i += 1
                if changed:
                    base_file.write_text(
                        "\n".join(lines).rstrip() + "\n", encoding="utf-8"
                    )

        if removed_total:
            try:
                self._remove_empty_translate_blocks(tl_dir, tl_name)
            except Exception:
                pass

        return removed_total

    def _collect_source_registered_old_values(self, game_dir: Path, tl_name: str) -> Set[str]:
        """收集 game/tl 外源码 translate strings 块已经注册的原文。"""
        game_root = game_dir / "game"
        if not game_root.is_dir():
            return set()
        header_re = re.compile(
            rf"^\s*translate\s+{re.escape(tl_name)}\s+strings\s*:\s*$"
        )
        values: Set[str] = set()
        for source_file in game_root.rglob("*.rpy"):
            try:
                relative = source_file.relative_to(game_root)
                if relative.parts and relative.parts[0].lower() == "tl":
                    continue
                lines = source_file.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
            except Exception:
                continue
            in_strings = False
            for line in lines:
                if header_re.match(line):
                    in_strings = True
                    continue
                if in_strings and re.match(r"^\s*translate\s+", line):
                    in_strings = False
                if not in_strings:
                    continue
                old_match = self.OLD_LINE_RE.match(line)
                if old_match:
                    values.add(
                        self._decode_literal_value(
                            old_match.group(1), old_match.group("text")
                        )
                    )
        return values

    def _remove_source_registered_string_duplicates(
        self, game_dir: Path, tl_dir: Path, tl_name: str
    ) -> int:
        """删除已由游戏源码直接注册的 TL old/new 重复条目。"""
        source_values = self._collect_source_registered_old_values(game_dir, tl_name)
        if not source_values:
            return 0
        removed = 0
        for rpy_file in tl_dir.rglob("*.rpy"):
            try:
                lines = rpy_file.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
            except Exception:
                continue
            output: List[str] = []
            i = 0
            changed = False
            while i < len(lines):
                old_match = self.OLD_LINE_RE.match(lines[i])
                if old_match:
                    old_value = self._decode_literal_value(
                        old_match.group(1), old_match.group("text")
                    )
                    j = i + 1
                    while j < len(lines) and (
                        not lines[j].strip() or lines[j].lstrip().startswith("#")
                    ):
                        j += 1
                    if (
                        old_value in source_values
                        and j < len(lines)
                        and self.NEW_LINE_RE.match(lines[j])
                    ):
                        while output and (
                            not output[-1].strip()
                            or output[-1].lstrip().startswith("# game/")
                        ):
                            output.pop()
                        removed += 1
                        changed = True
                        i = j + 1
                        continue
                output.append(lines[i])
                i += 1
            if changed:
                rpy_file.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
        if removed:
            self._remove_empty_translate_blocks(tl_dir, tl_name)
        return removed

    def _load_glossary_map(self, config: Config) -> Dict[str, str]:
        """加载用户术语库，返回 {原文: 译文}。"""
        mapping: Dict[str, str] = {}
        try:
            if not getattr(config, "glossary_enable", True):
                return {}

            for item in getattr(config, "glossary_data", None) or []:
                src = dst = ""
                if isinstance(item, dict):
                    src = item.get("src", "") or item.get("source", "")
                    dst = item.get("dst", "") or item.get("target", "")
                elif isinstance(item, (list, tuple)) and len(item) >= 2:
                    src, dst = item[0], item[1]

                if src and dst:
                    mapping[str(src)] = str(dst)
        except Exception as exc:
            self.logger.warning(f"加载术语库失败: {exc}")
        return mapping

    def _apply_glossary_to_tl(self, tl_dir: Path, glossary: Dict[str, str]) -> int:
        """将 glossary 中的翻译自动填充到 tl 文件（仅覆盖 new 与 old 相同的条目）。"""
        if not glossary or not tl_dir.exists():
            return 0

        updated = 0
        for rpy_file in self._iter_rpy_files(tl_dir):
            try:
                lines = rpy_file.read_text(encoding="utf-8").splitlines()
            except Exception as exc:
                self.logger.warning(f"读取翻译文件失败 {rpy_file}: {exc}")
                continue

            changed = False
            i = 0
            while i < len(lines):
                old_match = self.OLD_LINE_RE.match(lines[i])
                if old_match and i + 1 < len(lines):
                    indent_match = re.match(r'^(\s*)old', lines[i])
                    indent = indent_match.group(1) if indent_match else ""
                    raw_old = old_match.group("text")
                    old_text = raw_old.replace('\\"', '"').replace("\\'", "'")

                    new_line = lines[i + 1]
                    new_match = self.NEW_LINE_RE.match(new_line)
                    if not new_match:
                        i += 1
                        continue

                    current_new = new_match.group("text").replace('\\"', '"').replace("\\'", "'")

                    if old_text in glossary:
                        target = glossary[old_text]
                        # 仅在未翻译或空翻译时覆盖
                        if (current_new == "" or current_new == old_text) and target and target != old_text:
                            escaped = (
                                target.replace("\\", "\\\\")
                                .replace('"', '\\"')
                                .replace("\r\n", "\n")
                                .replace("\r", "\n")
                                .replace("\n", "\\n")
                            )
                            lines[i + 1] = f'{indent}new "{escaped}"'
                            updated += 1
                            changed = True
                    i += 2
                    continue
                i += 1

            if changed:
                rpy_file.write_text("\n".join(lines), encoding="utf-8")

        return updated

    def _escape_rpy_string(self, value: str) -> str:
        """转义写入 rpy 的字符串。"""
        return (
            value.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            .replace("\n", "\\n")
        )

    @staticmethod
    def _decode_rpy_string(quote: str, value: str) -> str:
        literal = f"{quote}{value}{quote}"
        try:
            decoded = ast.literal_eval(literal)
            return decoded if isinstance(decoded, str) else str(decoded)
        except Exception:
            return value.replace('\\"', '"').replace("\\'", "'")

    @classmethod
    def _canonical_rpy_string(cls, quote: str, value: str) -> str:
        """解码 TL 字面量，并折叠旧增量输出中的双重转义引号。"""
        decoded = cls._decode_rpy_string(quote, value)
        # 旧版增量输出会再次转义已经转义过的原始字面量，导致 Ren'Py 将
        # ``\\\"`` 视为反斜杠加引号，而源码值只有引号。比较或重新输出前
        # 先规范化，确保两种写法只保留一个全局条目。
        previous = None
        while decoded != previous:
            previous = decoded
            decoded = decoded.replace('\\"', '"').replace("\\'", "'")
        return decoded

    def get_last_suspicious_manifest(self) -> Optional[Path]:
        return self._last_suspicious_manifest

    @staticmethod
    def _is_restore_flag_enabled(value: str) -> bool:
        return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "checked", "x", "v", "ok"}

    def _is_suspicious_bool_expr_text(self, text: str) -> bool:
        candidate = text.strip()
        if not candidate or "\n" in candidate or "\r" in candidate:
            return False

        if not self.SUSPICIOUS_BOOL_EXPR_RE.search(candidate):
            return False

        lower_candidate = candidate.lower()
        if "==" in candidate or "!=" in candidate:
            return True
        if " and " in lower_candidate or " or " in lower_candidate or " not " in lower_candidate:
            return True
        if "_" in candidate:
            return True
        return bool(
            re.fullmatch(
                r"[A-Za-z_][A-Za-z0-9_]*\s*=\s*(?:True|False|true|false)",
                candidate,
            )
        )

    def _collect_existing_old_values(self, file_path: Path) -> Set[str]:
        olds: Set[str] = set()
        if not file_path.exists():
            return olds

        try:
            lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            return olds

        for line in lines:
            old_match = self.OLD_LINE_RE.match(line)
            if not old_match:
                continue
            old_text = self._decode_rpy_string(old_match.group(1), old_match.group("text"))
            olds.add(old_text)
        return olds

    def _write_suspicious_backup(
        self,
        tl_dir: Path,
        tl_name: str,
        removed_by_file: Dict[str, List[Dict[str, str | int]]],
    ) -> Optional[Path]:
        if not removed_by_file:
            return None

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        run_dir = tl_dir / self.SUSPICIOUS_BACKUP_DIR / timestamp
        entries_dir = run_dir / "entries"
        entries_dir.mkdir(parents=True, exist_ok=True)

        manifest_path = run_dir / self.SUSPICIOUS_MANIFEST_NAME
        fieldnames = ["restore", "id", "file", "line", "old", "new", "reason", "backup_file"]

        counter = 1
        with manifest_path.open("w", encoding="utf-8-sig", newline="") as csv_writer:
            writer = csv.DictWriter(csv_writer, fieldnames=fieldnames)
            writer.writeheader()

            for rel_path in sorted(removed_by_file.keys()):
                entries = removed_by_file[rel_path]
                backup_rel = Path("entries") / Path(rel_path)
                backup_file = run_dir / backup_rel
                backup_file.parent.mkdir(parents=True, exist_ok=True)

                backup_lines = [
                    "# RenpyBox: filtered suspicious bool-expression entries",
                    f"# source: {rel_path}",
                    "",
                    f"translate {tl_name} strings:",
                    "",
                ]

                for item in entries:
                    old_text = str(item.get("old", ""))
                    new_text = str(item.get("new", ""))
                    line_no = int(item.get("line", 0) or 0)
                    reason = str(item.get("reason", "suspicious_bool_expr"))

                    backup_lines.append(f"    # old line: {line_no}")
                    backup_lines.append(f'    old "{self._escape_rpy_string(old_text)}"')
                    backup_lines.append(f'    new "{self._escape_rpy_string(new_text)}"')
                    backup_lines.append("")

                    writer.writerow(
                        {
                            "restore": "0",
                            "id": str(counter),
                            "file": rel_path,
                            "line": str(line_no),
                            "old": old_text,
                            "new": new_text,
                            "reason": reason,
                            "backup_file": backup_rel.as_posix(),
                        }
                    )
                    counter += 1

                backup_file.write_text("\n".join(backup_lines).rstrip() + "\n", encoding="utf-8")

        readme_path = run_dir / "README.txt"
        readme_path.write_text(
            "\n".join(
                [
                    "RenpyBox filtered suspicious entries backup",
                    "",
                    "1) Open restore_manifest.csv",
                    "2) For entries you want back, set column 'restore' to 1",
                    "3) In RenpyBox click: 恢复误提取勾选项",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        latest_hint = tl_dir / self.SUSPICIOUS_BACKUP_DIR / "latest_manifest.txt"
        try:
            latest_hint.write_text(str(manifest_path), encoding="utf-8")
        except Exception:
            pass

        return manifest_path

    def _remove_suspicious_bool_expr_entries(self, tl_dir: Path, tl_name: str) -> Tuple[int, Optional[Path]]:
        removed_total = 0
        removed_by_file: Dict[str, List[Dict[str, str | int]]] = {}

        for rpy_file in self._iter_rpy_files(tl_dir):
            try:
                lines = rpy_file.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception as exc:
                self.logger.warning(f"读取翻译文件失败 {rpy_file}: {exc}")
                continue

            changed = False
            new_lines: List[str] = []
            i = 0
            rel_path = rpy_file.relative_to(tl_dir).as_posix()

            while i < len(lines):
                old_match = self.OLD_LINE_RE.match(lines[i])
                if old_match and i + 1 < len(lines):
                    j = i + 1
                    while j < len(lines):
                        probe = lines[j].strip()
                        if not probe or probe.startswith("#"):
                            j += 1
                            continue
                        break
                    new_match = self.NEW_LINE_RE.match(lines[j]) if j < len(lines) else None
                    if new_match:
                        old_text = self._decode_rpy_string(old_match.group(1), old_match.group("text"))
                        if self._is_suspicious_bool_expr_text(old_text):
                            new_text = self._decode_rpy_string(new_match.group(1), new_match.group("text"))
                            removed_by_file.setdefault(rel_path, []).append(
                                {
                                    "line": i + 1,
                                    "old": old_text,
                                    "new": new_text,
                                    "reason": "suspicious_bool_expr",
                                }
                            )
                            removed_total += 1
                            changed = True
                            i = j + 1
                            while i < len(lines) and not lines[i].strip():
                                i += 1
                            continue

                        new_lines.extend(lines[i : j + 1])
                        i = j + 1
                        continue

                new_lines.append(lines[i])
                i += 1

            if changed:
                final_lines: List[str] = []
                prev_empty = False
                for entry in new_lines:
                    is_empty = not entry.strip()
                    if is_empty and prev_empty:
                        continue
                    final_lines.append(entry)
                    prev_empty = is_empty

                final_text = "\n".join(final_lines).rstrip()
                if final_text:
                    final_text += "\n"
                rpy_file.write_text(final_text, encoding="utf-8")

        manifest_path = self._write_suspicious_backup(tl_dir, tl_name, removed_by_file)
        return removed_total, manifest_path

    def _find_latest_suspicious_manifest(self, tl_dir: Path) -> Optional[Path]:
        backup_root = tl_dir / self.SUSPICIOUS_BACKUP_DIR
        if not backup_root.exists():
            return None

        candidates = list(backup_root.glob(f"*/{self.SUSPICIOUS_MANIFEST_NAME}"))
        if not candidates:
            fallback = backup_root / self.SUSPICIOUS_MANIFEST_NAME
            return fallback if fallback.exists() else None

        candidates.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0.0, reverse=True)
        return candidates[0] if candidates else None

    def restore_flagged_suspicious_entries(
        self,
        game_dir: str | Path,
        tl_name: str,
        manifest_path: str | Path | None = None,
    ) -> ExtractionResult:
        result = ExtractionResult(success=False)
        game_dir = Path(game_dir)
        tl_dir = game_dir / "game" / "tl" / tl_name
        result.tl_dir = tl_dir

        if not tl_dir.exists():
            result.message = f"未找到 tl 目录: {tl_dir}"
            return result

        if manifest_path is not None:
            manifest = Path(manifest_path)
        else:
            manifest = self._find_latest_suspicious_manifest(tl_dir)

        if manifest is None or not manifest.exists():
            result.message = "未找到可恢复清单（_filtered_suspicious/*/restore_manifest.csv）"
            return result

        selected_by_file: Dict[str, List[Tuple[str, str]]] = {}
        try:
            with manifest.open("r", encoding="utf-8-sig", newline="") as reader:
                csv_reader = csv.DictReader(reader)
                for row in csv_reader:
                    if not self._is_restore_flag_enabled(row.get("restore", "")):
                        continue
                    rel_path = (row.get("file", "") or "").replace("\\", "/").strip().lstrip("/")
                    old_text = row.get("old", "") or ""
                    new_text = row.get("new", "") or ""
                    if not rel_path:
                        continue
                    selected_by_file.setdefault(rel_path, []).append((old_text, new_text))
        except Exception as exc:
            result.message = f"读取恢复清单失败: {exc}"
            return result

        if not selected_by_file:
            result.message = "恢复清单中没有勾选项（请把 restore 列改为 1）"
            return result

        restored = 0
        skipped_duplicates = 0
        invalid_entries = 0
        touched_files = 0

        for rel_path, entries in selected_by_file.items():
            rel_obj = Path(rel_path)
            if rel_obj.is_absolute() or ".." in rel_obj.parts:
                invalid_entries += len(entries)
                continue

            target_file = tl_dir / rel_obj
            target_file.parent.mkdir(parents=True, exist_ok=True)

            existing_olds = self._collect_existing_old_values(target_file)
            pending: List[Tuple[str, str]] = []
            seen_olds = set(existing_olds)

            for old_text, new_text in entries:
                normalized_old = (old_text or "").strip()
                if not normalized_old:
                    invalid_entries += 1
                    continue
                if normalized_old in seen_olds:
                    skipped_duplicates += 1
                    continue
                seen_olds.add(normalized_old)
                pending.append((normalized_old, new_text or ""))

            if not pending:
                continue

            existed = target_file.exists()
            old_content = ""
            if existed:
                try:
                    old_content = target_file.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    old_content = ""

            restore_source = manifest.name
            try:
                restore_source = manifest.relative_to(tl_dir).as_posix()
            except Exception:
                restore_source = str(manifest)

            append_lines = [
                f"# restored from: {restore_source}",
                f"translate {tl_name} strings:",
                "",
            ]
            for old_text, new_text in pending:
                append_lines.append(f'    old "{self._escape_rpy_string(old_text)}"')
                append_lines.append(f'    new "{self._escape_rpy_string(new_text)}"')
                append_lines.append("")

            with target_file.open("a", encoding="utf-8", newline="\n") as writer:
                if old_content and not old_content.endswith(("\n", "\r")):
                    writer.write("\n")
                if old_content:
                    writer.write("\n")
                writer.write("\n".join(append_lines).rstrip() + "\n")

            restored += len(pending)
            touched_files += 1

        result.success = restored > 0
        if result.success:
            result.message = (
                f"已恢复 {restored} 条，涉及 {touched_files} 个文件；"
                f"跳过重复 {skipped_duplicates} 条，无效 {invalid_entries} 条"
            )
        else:
            result.message = (
                f"未恢复任何条目；跳过重复 {skipped_duplicates} 条，无效 {invalid_entries} 条"
            )
        return result

    def _cleanup_legacy_auto_screens_translation(self, tl_dir: Path) -> None:
        """清理旧版本生成的 auto_screens_default.rpy（历史遗留）。"""
        auto_file = tl_dir / self.AUTO_SCREEN_FILE
        if not auto_file.exists():
            return
        try:
            auto_file.unlink()
            self.logger.info(f"已移除旧的默认 screens 翻译: {auto_file}")
        except Exception as exc:
            self.logger.warning(f"删除 {auto_file} 失败: {exc}")

    def _remove_empty_translate_blocks(self, tl_dir: Path, tl_name: str) -> int:
        """移除空的 translate xxx strings: 块（避免官方抽取报 non-empty block 错误）。"""
        pattern = re.compile(r'^(\s*)translate\s+' + re.escape(tl_name) + r'\s+strings\s*:\s*$')
        removed_blocks = 0

        for rpy_file in self._iter_rpy_files(tl_dir):
            try:
                lines = rpy_file.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception as exc:
                self.logger.warning(f"读取翻译文件失败 {rpy_file}: {exc}")
                continue

            new_lines: List[str] = []
            i = 0
            changed = False

            while i < len(lines):
                match = pattern.match(lines[i])
                if match:
                    base_indent = len(match.group(1))
                    block_lines: List[str] = []
                    j = i + 1
                    while j < len(lines):
                        line_j = lines[j]
                        # 空行直接加入 block 范围
                        if not line_j.strip():
                            block_lines.append(line_j)
                            j += 1
                            continue

                        indent = len(line_j) - len(line_j.lstrip(' '))
                        # 继续在 block 内
                        if indent > base_indent:
                            block_lines.append(line_j)
                            j += 1
                            continue
                        else:
                            break

                    # 判断块内是否有有效内容（old/new 或其他非注释语句）
                    has_content = False
                    for blk in block_lines:
                        stripped_blk = blk.strip()
                        if not stripped_blk:
                            continue
                        if stripped_blk.startswith("#"):
                            continue
                        if stripped_blk.startswith(("old ", "new ")):
                            has_content = True
                            break
                        # 其他任意语句也视为内容
                        has_content = True
                        break

                    if not has_content:
                        removed_blocks += 1
                        changed = True
                        i = j
                        continue

                    # 保留该块
                    new_lines.extend(lines[i:j])
                    i = j
                    continue

                new_lines.append(lines[i])
                i += 1

            if changed:
                rpy_file.write_text("\n".join(new_lines), encoding="utf-8")

        return removed_blocks

    def extract_regular(
        self,
        game_dir: str | Path,
        tl_name: str,
        exe_path: str | Path = None,
        use_official: bool = True
    ) -> ExtractionResult:
        """
        常规抽取：官方抽取 + 自定义补充抽取
        
        会先备份原有翻译（如果存在），然后重新生成。
        """
        result = ExtractionResult()
        game_dir = Path(game_dir)
        tl_dir = game_dir / "game" / "tl" / tl_name
        result.tl_dir = tl_dir
        self._warn_if_writeback_report(tl_dir)
        
        try:
            config = Config().load()
            allow_official = bool(use_official and config.extract_use_official and exe_path)
            allow_custom = bool(config.extract_use_custom)

            if not allow_official and not allow_custom:
                result.success = False
                result.message = "常规抽取已被禁用，请启用官方或补充抽取后重试"
                return result

            # 1. 备份
            self._backup_tl_dir(game_dir, tl_name)
            
            # 2. 官方抽取
            if allow_official:
                self._emit_progress("正在执行官方抽取...", 20)
                try:
                    self.renpy_extractor.official_extract(
                        str(exe_path), tl_name, generate_empty=False, force=True
                    )
                except Exception as e:
                    self.logger.warning(f"官方抽取失败: {e}，将仅使用补充抽取")
            elif use_official and not exe_path:
                self.logger.warning("未提供可执行文件，已跳过官方抽取")
            else:
                self.logger.info("根据配置跳过官方抽取阶段")
            
            # 3. 自定义补充抽取
            if allow_custom:
                self._emit_progress("正在执行补充抽取...", 50)
                tl_dir.mkdir(parents=True, exist_ok=True)
                # ExtractAllFilesInDir(dirName, is_open_filter, filter_length, is_gen_empty, is_skip_underline)
                # 放宽长度过滤，减少 UI 短词漏提取
                rx.ExtractAllFilesInDir(str(tl_dir), True, 4, False, True)
            else:
                self.logger.info("根据配置跳过补充抽取阶段")
            
            # 4. 静态补充抽取：把官方/自定义流程仍可能漏掉的源码文本写入标准 TL。
            self._append_static_supplement_entries(game_dir, tl_dir, tl_name)

            # 5. 过滤与清理 + 终极结构导出
            self._post_process(game_dir, tl_name, tl_dir, config, None)
            # 6. 注入内置 UI 包（common_box/screens_box）
            injected_ui = 0
            if getattr(config, "onekey_inject_base_box", False):
                injected_ui = self._deploy_builtin_ui_pack(tl_dir, tl_name)
                if injected_ui:
                    self.logger.info(f"已注入 base_box UI 翻译: {injected_ui} 个文件")
            else:
                self.logger.debug("跳过 base_box 注入（配置已关闭）")
            
            # 统计
            result.total_files = len(list(self._iter_rpy_files(tl_dir)))
            result.success = True
            ui_note = "（已注入 base_box UI 翻译）" if injected_ui else ""
            suspicious_note = ""
            if self._last_suspicious_removed_count:
                suspicious_note = (
                    f"，已过滤疑似误提取 {self._last_suspicious_removed_count} 条"
                    "（可在 _filtered_suspicious 勾选恢复）"
                )
            result.message = f"常规抽取完成，共 {result.total_files} 个文件{ui_note}{suspicious_note}"
            self._emit_progress("抽取完成", 100)
            
        except Exception as e:
            import traceback
            self.logger.error(traceback.format_exc())
            result.success = False
            result.message = str(e)
            
        return result

    def extract_incremental(
        self,
        game_dir: str | Path,
        tl_name: str,
        exe_path: str | Path = None,
        use_official: bool = True,
        output_to_separate_folder: bool = True  # 新增：是否输出到独立文件夹
    ) -> ExtractionResult:
        """
        增量抽取：保留已有翻译，只提取新增内容
        
        Args:
            game_dir: 游戏目录
            tl_name: 翻译目录名称
            exe_path: 游戏可执行文件路径
            use_official: 是否使用官方抽取
            output_to_separate_folder: 如果为 True，新增内容输出到 tl/{tl_name}_new 文件夹
                                       如果为 False，直接合并到原 tl 目录（旧行为）
        """
        result = ExtractionResult()
        game_dir = Path(game_dir)
        tl_dir = game_dir / "game" / "tl" / tl_name
        result.tl_dir = tl_dir
        self._warn_if_writeback_report(tl_dir)
        
        # 新增内容的输出目录
        incremental_dir = game_dir / "game" / "tl" / f"{tl_name}_new" if output_to_separate_folder else None
        result.incremental_dir = incremental_dir
        
        try:
            config = Config().load()
            allow_official = bool(use_official and config.extract_use_official and exe_path)
            allow_custom = bool(config.extract_use_custom)

            if not allow_official and not allow_custom:
                result.success = False
                result.message = "增量抽取已被禁用，请启用官方或补充抽取后重试"
                return result

            self._emit_progress("正在分析已有翻译...", 10)

            repaired_comments = self._repair_block_comments_from_source(game_dir, tl_dir)
            if repaired_comments:
                self.logger.info(f"已按游戏源码修正 {repaired_comments} 条翻译块原文注释")
            
            # 1. 获取已翻译内容 {original: translated}
            existing_translations = self._get_existing_translations(tl_dir)
            translated_count = len(existing_translations)
            result.preserved_count = translated_count
            self.logger.info(f"发现 {translated_count} 条有效翻译")
            
            # 2. 获取当前所有原文（用于后续对比新增）
            existing_originals = set(existing_translations.keys())
            existing_string_originals = self._get_all_originals(tl_dir)
            block_originals = self._collect_block_originals(tl_dir)
            all_current_originals = existing_string_originals | block_originals
            self.logger.info(
                f"当前覆盖 {len(all_current_originals)} 条原文 "
                f"(strings={len(existing_string_originals)}, blocks={len(block_originals)})"
            )

            # 3. 创建临时目录进行抽取
            temp_extract_dir = game_dir / f"_temp_extract_{tl_name}_{int(time.time())}"
            temp_tl_dir = temp_extract_dir / "game" / "tl" / tl_name
            temp_tl_dir.parent.mkdir(parents=True, exist_ok=True)
            temp_backup_dir = temp_extract_dir / "_tl_backup"
            
            try:
                # 4. 在真实游戏目录里执行抽取，但先备份 tl 目录避免污染原翻译。
                #    注意：renpy_extract 的补充抽取依赖 tl_dir/../../game 结构，临时目录里缺少 game 源文件会导致抽取为空。
                def _relocate_dir(src: Path, dst: Path, *, remove_src: bool = True) -> None:
                    if not src.exists():
                        return
                    if dst.exists():
                        shutil.rmtree(str(dst), ignore_errors=True)
                    try:
                        shutil.move(str(src), str(dst))
                        return
                    except Exception as move_exc:
                        try:
                            shutil.copytree(str(src), str(dst), dirs_exist_ok=True)
                            if remove_src:
                                shutil.rmtree(str(src), ignore_errors=True)
                        except Exception as copy_exc:
                            raise RuntimeError(f"Relocate failed: {move_exc}; {copy_exc}") from copy_exc

                # 先把原 tl 目录挪走备份，给本次抽取留一个干净的 tl_dir
                if temp_backup_dir.exists():
                    shutil.rmtree(str(temp_backup_dir), ignore_errors=True)
                _relocate_dir(tl_dir, temp_backup_dir, remove_src=True)
                tl_dir.mkdir(parents=True, exist_ok=True)

                try:
                    # 5. 官方抽取（写入到 tl_dir）
                    if allow_official:
                        self._emit_progress("正在执行官方抽取...", 30)
                        try:
                            self.renpy_extractor.official_extract(
                                str(exe_path), tl_name, generate_empty=False, force=True
                            )
                        except Exception as e:
                            self.logger.warning(f"官方抽取失败: {e}")
                    else:
                        if use_official and not exe_path:
                            self.logger.warning("增量抽取：未提供可执行文件，已跳过官方抽取")
                        else:
                            self.logger.info("增量抽取：根据配置跳过官方抽取阶段")

                    # 6. 补充抽取（必须在真实 tl_dir 下执行，才能找到对应 game/*.rpy）
                    if allow_custom:
                        self._emit_progress("正在执行补充抽取...", 50)
                        try:
                            rx.ExtractAllFilesInDir(str(tl_dir), True, 4, False, True)
                        except Exception as e:
                            self.logger.warning(f"补充抽取失败: {e}")
                    else:
                        self.logger.info("增量抽取：根据配置跳过补充抽取阶段")

                    # 7. 捕获本次抽取结果到临时目录，用于对比新增
                    _relocate_dir(tl_dir, temp_tl_dir, remove_src=True)
                    temp_tl_dir.mkdir(parents=True, exist_ok=True)
                finally:
                    # 恢复原 tl 目录
                    if tl_dir.exists():
                        shutil.rmtree(str(tl_dir), ignore_errors=True)
                    _relocate_dir(temp_backup_dir, tl_dir, remove_src=True)
                
                # 6. 获取新抽取的所有原文
                # 静态源码文本必须写入标准 TL，不交给 replace_text。
                static_candidates = rx.collect_static_source_strings(game_dir)
                self._append_static_supplement_entries(game_dir, temp_tl_dir, tl_name)
                new_extracted_originals = self._get_all_originals(temp_tl_dir)
                self.logger.info(f"新抽取共 {len(new_extracted_originals)} 条原文")
                
                # 7. 计算新增原文
                new_originals = self._select_incremental_originals(
                    new_extracted_originals,
                    existing_string_originals,
                    block_originals,
                    static_candidates,
                    tl_dir,
                )
                self.logger.info(f"检测到 {len(new_originals)} 条新增原文")
                result.new_strings = len(new_originals)

                pending_originals: Set[str] = set()
                if output_to_separate_folder and getattr(config, "renpy_incremental_include_untranslated", False):
                    # tl 已存在但没翻译过/只有占位（new==old/new==""）时，把这些也纳入待翻译包
                    pending_originals = self._get_untranslated_originals(tl_dir)
                    # 对话块覆盖可以排除合成的对话占位，但显式 strings 占位
                    # （例如菜单选项）即使与其他对话同文，也仍需翻译。
                    pending_originals -= block_originals - existing_string_originals
                    pending_originals -= set(existing_translations.keys())
                    self.logger.info(f"检测到 {len(pending_originals)} 条未翻译占位原文")

                selected_originals = set(new_originals) | set(pending_originals)
                
                if output_to_separate_folder:
                    # 8a. 将新增内容输出到单独文件夹
                    self._emit_progress("正在分离新增/待翻译内容...", 70)
                    if incremental_dir.exists():
                        shutil.rmtree(str(incremental_dir))
                    incremental_dir.mkdir(parents=True, exist_ok=True)
                    
                    self._extract_new_entries_to_folder(
                        temp_tl_dir, incremental_dir, selected_originals, tl_name, game_dir
                    )
                    
                    # 统计输出文件
                    result.total_files = len(list(self._iter_rpy_files(incremental_dir)))
                    
                    # 9. 对新增目录进行后处理
                    self._post_process(game_dir, tl_name, incremental_dir, config, None)
                    
                    result.success = True
                    msg_lines = [
                        "增量抽取完成",
                        f"• 保留已有翻译: {translated_count} 条",
                        f"• 新增待翻译: {len(new_originals)} 条",
                    ]
                    if pending_originals:
                        msg_lines.append(f"• 未翻译待补全: {len(pending_originals)} 条")
                    if self._last_suspicious_removed_count:
                        msg_lines.append(
                            "• 已过滤疑似误提取: "
                            f"{self._last_suspicious_removed_count} 条（_filtered_suspicious 可勾选恢复）"
                        )
                    msg_lines.append(f"• 新增内容位置: {incremental_dir.name}/")
                    result.message = "\n".join(msg_lines)
                else:
                    # 8b. 合并到原 tl 目录（旧行为）
                    self._emit_progress("正在合并新增内容...", 70)
                    self._merge_new_entries(tl_dir, temp_tl_dir, new_originals, existing_translations)
                    
                    # 9. 回填翻译
                    self._emit_progress("正在回填已有翻译...", 80)
                    self._merge_translations(tl_dir, existing_translations)
                    
                    # 10. 后处理
                    self._post_process(game_dir, tl_name, tl_dir, config, existing_translations)
                    
                    result.total_files = len(list(self._iter_rpy_files(tl_dir)))
                    result.success = True
                    suspicious_note = ""
                    if self._last_suspicious_removed_count:
                        suspicious_note = (
                            f"，并过滤疑似误提取 {self._last_suspicious_removed_count} 条"
                            "（可在 _filtered_suspicious 勾选恢复）"
                        )
                    result.message = (
                        f"增量抽取完成，保留了 {translated_count} 条已有翻译，"
                        f"新增 {len(new_originals)} 条{suspicious_note}"
                    )

                # 注入内置 UI 包（仅影响主 tl 目录，不影响增量输出目录）
                injected_ui = 0
                if getattr(config, "onekey_inject_base_box", False):
                    injected_ui = self._deploy_builtin_ui_pack(tl_dir, tl_name)
                    if injected_ui and result.success:
                        self.logger.info(f"已注入 base_box UI 翻译: {injected_ui} 个文件")
                        if output_to_separate_folder and isinstance(result.message, str) and result.message.startswith("增量抽取完成"):
                            result.message = result.message + "\n• 已注入 base_box UI 翻译"
                        elif not output_to_separate_folder and result.message:
                            result.message = result.message + "（已注入 base_box UI 翻译）"
                elif result.success:
                    self.logger.debug("跳过 base_box 注入（配置已关闭）")
                
                self._emit_progress("增量抽取完成", 100)

            finally:
                # 清理临时目录
                if temp_extract_dir.exists():
                    shutil.rmtree(str(temp_extract_dir), ignore_errors=True)
            
        except Exception as e:
            import traceback
            self.logger.error(traceback.format_exc())
            result.success = False
            result.message = str(e)
            
        return result

    def merge_incremental_folder(
        self,
        game_dir: str | Path,
        tl_name: str,
        incremental_dir: str | Path | None = None,
        *,
        clean_duplicates: bool = True,
    ) -> ExtractionResult:
        """合并 tl/<lang>_new 到 tl/<lang>，并可选清理重复条目。"""
        result = ExtractionResult()
        game_dir = Path(game_dir)
        tl_dir = game_dir / "game" / "tl" / tl_name
        result.tl_dir = tl_dir

        if incremental_dir is None:
            incremental_dir = game_dir / "game" / "tl" / f"{tl_name}_new"
        incremental_dir = Path(incremental_dir)
        result.incremental_dir = incremental_dir

        if not incremental_dir.exists():
            result.success = False
            result.message = f"未找到增量目录: {incremental_dir}"
            return result

        def decode_literal(quote: str, text: str) -> str:
            return self._canonical_rpy_string(quote, text)

        def collect_pairs(lines: List[str]) -> List[Tuple[str, str, List[str]]]:
            pairs: List[Tuple[str, str, List[str]]] = []
            i = 0
            while i < len(lines):
                old_match = self.OLD_LINE_RE.match(lines[i])
                if old_match and i + 1 < len(lines):
                    j = i + 1
                    while j < len(lines):
                        probe = lines[j].strip()
                        if not probe or probe.startswith("#"):
                            j += 1
                            continue
                        break
                    if j < len(lines):
                        new_match = self.NEW_LINE_RE.match(lines[j])
                    else:
                        new_match = None
                    if new_match:
                        old_value = decode_literal(old_match.group(1), old_match.group("text"))
                        new_value = decode_literal(new_match.group(1), new_match.group("text"))
                        comments: List[str] = []
                        back = i - 1
                        while back >= 0 and (
                            not lines[back].strip() or lines[back].lstrip().startswith("#")
                        ):
                            if lines[back].lstrip().startswith("# game/"):
                                comments.insert(0, lines[back].strip())
                            back -= 1
                        pairs.append((old_value, new_value, comments))
                        i = j + 1
                        continue
                i += 1
            return pairs

        def collect_target_map(lines: List[str]) -> Dict[str, Tuple[str, int]]:
            target_map: Dict[str, Tuple[str, int]] = {}
            i = 0
            while i < len(lines):
                old_match = self.OLD_LINE_RE.match(lines[i])
                if old_match and i + 1 < len(lines):
                    j = i + 1
                    while j < len(lines):
                        probe = lines[j].strip()
                        if not probe or probe.startswith("#"):
                            j += 1
                            continue
                        break
                    if j < len(lines):
                        new_match = self.NEW_LINE_RE.match(lines[j])
                    else:
                        new_match = None
                    if new_match:
                        old_value = decode_literal(old_match.group(1), old_match.group("text"))
                        new_value = decode_literal(new_match.group(1), new_match.group("text"))
                        target_map.setdefault(old_value, (new_value, j))
                        i = j + 1
                        continue
                i += 1
            return target_map

        merged_files = 0
        added_entries = 0
        updated_entries = 0

        for rpy_file in self._iter_rpy_files(incremental_dir):
            try:
                inc_lines = rpy_file.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception as exc:
                self.logger.warning(f"读取增量文件失败 {rpy_file}: {exc}")
                continue

            inc_pairs = collect_pairs(inc_lines)
            if not inc_pairs:
                continue

            rel_path = rpy_file.relative_to(incremental_dir)
            target_file = tl_dir / rel_path

            if not target_file.exists():
                target_file.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(str(rpy_file), str(target_file))
                    merged_files += 1
                    added_entries += len(inc_pairs)
                except Exception as exc:
                    self.logger.warning(f"合并文件失败 {rpy_file}: {exc}")
                continue

            try:
                target_lines = target_file.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception as exc:
                self.logger.warning(f"读取目标文件失败 {target_file}: {exc}")
                continue

            target_map = collect_target_map(target_lines)
            new_entries: List[Tuple[str, str, List[str]]] = []
            changed = False

            for old_text, new_text, comments in inc_pairs:
                if old_text in target_map:
                    current_new, new_line_idx = target_map[old_text]
                    if (not current_new or current_new == old_text) and new_text and new_text != old_text:
                        # 仅用增量翻译补全占位，避免覆盖已有译文
                        indent_match = re.match(r'^(\s*)new', target_lines[new_line_idx])
                        indent = indent_match.group(1) if indent_match else "    "
                        escaped_new = self._escape_rpy_string(new_text)
                        target_lines[new_line_idx] = f'{indent}new "{escaped_new}"'
                        updated_entries += 1
                        changed = True
                    continue
                new_entries.append((old_text, new_text, comments))

            if new_entries:
                append_lines: List[str] = []
                for old_text, new_text, comments in new_entries:
                    append_lines.extend(f"    {comment}" for comment in comments)
                    escaped_old = self._escape_rpy_string(old_text)
                    escaped_new = self._escape_rpy_string(new_text) if new_text else ""
                    append_lines.append(f'    old "{escaped_old}"')
                    append_lines.append(f'    new "{escaped_new}"')
                    append_lines.append("")

                strings_header = re.compile(
                    rf"^\s*translate\s+{re.escape(tl_name)}\s+strings\s*:\s*$"
                )
                header_indexes = [
                    index for index, line in enumerate(target_lines) if strings_header.match(line)
                ]
                if header_indexes:
                    header_index = header_indexes[-1]
                    insert_at = len(target_lines)
                    for index in range(header_index + 1, len(target_lines)):
                        if re.match(r"^\s*translate\s+", target_lines[index]):
                            insert_at = index
                            break
                    while insert_at > header_index + 1 and not target_lines[insert_at - 1].strip():
                        insert_at -= 1
                    target_lines[insert_at:insert_at] = [""] + append_lines
                else:
                    target_lines.extend(["", f"translate {tl_name} strings:", ""] + append_lines)
                added_entries += len(new_entries)
                changed = True

            if changed:
                target_file.write_text("\n".join(target_lines).rstrip() + "\n", encoding="utf-8")
                merged_files += 1

        if clean_duplicates:
            try:
                rx.remove_repeat_extracted_from_tl(str(tl_dir), is_py2=False)
            except Exception as exc:
                self.logger.warning(f"清理重复失败 {tl_dir}: {exc}")
            config = Config().load()
            if getattr(config, "renpy_remove_string_duplicates", False):
                removed = self._remove_string_duplicates_with_blocks(tl_dir)
                if removed:
                    self.logger.info(f"已移除 {removed} 条与翻译块重复的 strings 翻译")
            # base_box 一旦存在就会被 Ren'Py 加载；即使本次未启用注入，
            # 也要清理它与增量占位条目的重复。
            if (tl_dir / "base_box").exists():
                removed_ui = self._remove_placeholder_duplicates_for_base_box(tl_dir, tl_name)
                if removed_ui:
                    self.logger.info(f"已按 base_box 优先清理占位重复 {removed_ui} 条")
            removed_source = self._remove_source_registered_string_duplicates(
                game_dir, tl_dir, tl_name
            )
            if removed_source:
                self.logger.info(f"已清理与游戏源码翻译重复的 strings 条目 {removed_source} 条")
            try:
                removed_blocks = self._remove_empty_translate_blocks(tl_dir, tl_name)
                if removed_blocks:
                    self.logger.info(f"已移除 {removed_blocks} 个空的 translate strings 块")
            except Exception:
                pass
            removed_truncated = self._remove_strings_covered_by_truncated_block_comment(tl_dir)
            if removed_truncated:
                self.logger.info(
                    f"已清理 {removed_truncated} 条由官方截断注释造成的伪 strings 重复"
                )
                # 截断重复可能是 strings 块内唯一条目，删除后需再次清理空块。
                removed_blocks = self._remove_empty_translate_blocks(tl_dir, tl_name)
                if removed_blocks:
                    self.logger.info(
                        f"截断重复清理后又移除 {removed_blocks} 个空的 translate strings 块"
                    )

        # 合并与去重成功后，增量目录不再是可加载的翻译来源，
        # 避免遗留目录造成重复加载和困惑。
        try:
            shutil.rmtree(str(incremental_dir))
        except Exception as exc:
            self.logger.warning(f"合并完成但清理增量目录失败 {incremental_dir}: {exc}")

        result.success = True
        result.total_files = len(list(self._iter_rpy_files(tl_dir)))
        result.message = (
            f"合并完成：更新占位 {updated_entries} 条，"
            f"新增 {added_entries} 条，涉及 {merged_files} 个文件；已清理 {incremental_dir.name}"
        )
        return result

    def _get_file_block_originals(self, rpy_file: Path) -> Set[str]:
        """读取单个文件中 translate 对话块注释里的原文。"""
        if not rpy_file.exists():
            return set()
        try:
            lines = rpy_file.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            return set()

        originals: Set[str] = set()
        in_block = False
        block_indent = 0
        for line in lines:
            stripped = line.lstrip()
            indent = len(line) - len(stripped)
            if stripped.startswith("translate ") and stripped.endswith(":"):
                in_block = not stripped.endswith(" strings:")
                block_indent = indent
                continue
            if not in_block:
                continue
            if stripped and indent <= block_indent:
                in_block = False
                continue
            if stripped.startswith("#"):
                match = re.search(r'"((?:\\.|[^"])*)"', stripped)
                if match:
                    originals.add(match.group(1).replace('\\"', '"').replace("\\'", "'"))
        return originals

    def _repair_block_comments_from_source(self, game_dir: Path, tl_dir: Path) -> int:
        """按 game/路径:行号锚点修复官方 TL 模板注释。"""
        repaired = 0
        location_re = re.compile(r"^\s*#\s+(game/.+?):(\d+)\s*$")
        source_cache: Dict[Path, List[str]] = {}

        for tl_file in self._iter_rpy_files(tl_dir):
            try:
                lines = tl_file.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception:
                continue
            changed = False

            for index, line in enumerate(lines):
                location = location_re.match(line)
                if not location:
                    continue
                source_file = game_dir / location.group(1)
                source_line_no = int(location.group(2))
                if not source_file.is_file() or source_line_no <= 0:
                    continue
                source_lines = source_cache.get(source_file)
                if source_lines is None:
                    try:
                        source_lines = source_file.read_text(
                            encoding="utf-8", errors="replace"
                        ).splitlines()
                    except Exception:
                        continue
                    source_cache[source_file] = source_lines
                if source_line_no > len(source_lines):
                    continue
                source_literals = scan_quoted_literals(source_lines[source_line_no - 1])
                if not source_literals:
                    continue
                source_text = source_literals[-1].value

                # 官方对话锚点后允许经过一个 translate 头和空行再到模板注释；
                # old/new、新位置锚点或第二个 translate 头都表示已离开当前条目。
                seen_header = False
                for probe in range(index + 1, min(index + 10, len(lines))):
                    stripped = lines[probe].lstrip()
                    if not stripped:
                        continue
                    if stripped.startswith("# game/"):
                        break
                    if stripped.startswith("translate "):
                        if not seen_header:
                            seen_header = True
                            continue
                        break
                    if self.OLD_LINE_RE.match(lines[probe]) or self.NEW_LINE_RE.match(
                        lines[probe]
                    ):
                        break
                    if not stripped.startswith("#"):
                        break
                    comment_literals = scan_quoted_literals(lines[probe])
                    if not comment_literals:
                        continue
                    literal = comment_literals[-1]
                    if literal.value == source_text:
                        break
                    replacement = f'"{escape_tl_string(source_text)}"'
                    lines[probe] = (
                        lines[probe][:literal.start_col]
                        + replacement
                        + lines[probe][literal.end_col:]
                    )
                    repaired += 1
                    changed = True
                    break

            if changed:
                tl_file.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        return repaired

    def _select_incremental_originals(
        self,
        extracted_originals: Set[str],
        existing_string_originals: Set[str],
        block_originals: Set[str],
        static_candidates: Dict[str, str],
        tl_dir: Path,
    ) -> Set[str]:
        """选择真实增量任务，同时保留与对话同文的菜单 strings。"""
        selected = extracted_originals - existing_string_originals - block_originals
        menu_candidates = set(rx.collect_static_menu_strings(tl_dir.parents[2]))
        file_block_cache: Dict[Path, Set[str]] = {}

        # 对话块通常表示文本已有翻译，但菜单选项仍需要独立的 strings 条目，
        # 因此不能仅凭同文对话块就把菜单文本排除出增量任务。
        for original, relative_path in static_candidates.items():
            if original not in extracted_originals or original in existing_string_originals:
                continue
            if original in menu_candidates:
                selected.add(original)
                continue
            target_file = tl_dir / relative_path
            file_blocks = file_block_cache.get(target_file)
            if file_blocks is None:
                file_blocks = self._get_file_block_originals(target_file)
                file_block_cache[target_file] = file_blocks
            if self._is_covered_by_file_block(original, file_blocks):
                continue
            selected.add(original)
        return selected

    @staticmethod
    def _is_covered_by_file_block(original: str, file_blocks: Set[str]) -> bool:
        """匹配完整块，以及结尾封装符被官方注释截断的块。"""
        if original in file_blocks:
            return True

        # 官方抽取注释偶尔会丢失括号文本末尾的封装符。仅在这一种窄化场景
        # 下把截断注释视为已覆盖，避免扩大模糊匹配范围。
        def without_trailing_wrapper(value: str) -> str:
            return re.sub(r"\s*[\)\]\}]\s*$", "", value).rstrip()

        normalized = without_trailing_wrapper(original)
        if normalized == original.rstrip():
            return False
        return any(without_trailing_wrapper(value) == normalized for value in file_blocks)

    def _remove_strings_covered_by_truncated_block_comment(self, tl_dir: Path) -> int:
        """只删除封装符截断造成的重复，保留同文菜单条目。"""
        removed = 0
        for rpy_file in self._iter_rpy_files(tl_dir):
            file_blocks = self._get_file_block_originals(rpy_file)
            if not file_blocks:
                continue
            try:
                lines = rpy_file.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception:
                continue

            indexes: Set[int] = set()
            i = 0
            while i < len(lines):
                old_match = self.OLD_LINE_RE.match(lines[i])
                if not old_match:
                    i += 1
                    continue
                old_text = self._canonical_rpy_string(
                    old_match.group(1), old_match.group("text")
                )
                # 完全相同的文本可能是真实菜单项；只有去掉官方块注释末尾的
                # 封装符后才匹配时，才视为应删除的截断重复。
                if old_text in file_blocks or not self._is_covered_by_file_block(old_text, file_blocks):
                    i += 1
                    continue
                j = i + 1
                while j < len(lines) and (not lines[j].strip() or lines[j].lstrip().startswith("#")):
                    j += 1
                if j < len(lines) and self.NEW_LINE_RE.match(lines[j]):
                    indexes.update(range(i, j + 1))
                    removed += 1
                    i = j + 1
                    continue
                i += 1

            if indexes:
                kept = [line for index, line in enumerate(lines) if index not in indexes]
                rpy_file.write_text("\n".join(kept).rstrip() + "\n", encoding="utf-8")
        return removed

    def _append_static_supplement_entries(
        self,
        game_dir: Path,
        tl_dir: Path,
        tl_name: str,
    ) -> int:
        """把静态漏抽文本写入其首次出现的标准翻译文件。"""
        candidates = rx.collect_static_source_strings(game_dir)
        menu_candidates = set(rx.collect_static_menu_strings(game_dir))
        if not candidates:
            return 0

        existing = self._get_all_originals(tl_dir)
        added = 0
        for original, relative_path in candidates.items():
            if original in existing:
                continue

            target_file = tl_dir / relative_path
            # 非菜单静态文本若已由同文件对话块覆盖则跳过；菜单必须保留 strings。
            if (
                original not in menu_candidates
                and self._is_covered_by_file_block(
                    original, self._get_file_block_originals(target_file)
                )
            ):
                continue
            target_file.parent.mkdir(parents=True, exist_ok=True)
            escaped = self._escape_rpy_string(original)
            source_file = (game_dir / "game" / relative_path)
            source_line = self._find_source_text_line(source_file, original)
            location_comment = (
                f"    # game/{relative_path}:{source_line}\n"
                if source_line is not None
                else ""
            )
            with target_file.open("a", encoding="utf-8") as handle:
                handle.write(
                    f"\ntranslate {tl_name} strings:\n\n"
                    f"{location_comment}"
                    f'    old "{escaped}"\n'
                    f'    new "{escaped}"\n'
                )
            existing.add(original)
            added += 1

        if added:
            self.logger.info(f"标准补充抽取：已添加 {added} 条静态翻译条目")
        return added

    @staticmethod
    def _find_source_text_line(source_file: Path, original: str) -> Optional[int]:
        try:
            lines = source_file.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            return None
        for line_no, line in enumerate(lines, 1):
            if any(literal.value == original for literal in scan_quoted_literals(line)):
                return line_no
        return None

    def _get_all_originals(self, tl_dir: Path) -> Set[str]:
        """获取 translate strings 中真实 old 条目的原文。"""
        originals: Set[str] = set()
        if not tl_dir.exists():
            return originals

        for rpy_file in self._iter_rpy_files(tl_dir):
            try:
                content = rpy_file.read_text(encoding="utf-8", errors="replace")
                for match in self.OLD_LINE_RE.finditer(content):
                    old_text = self._canonical_rpy_string(match.group(1), match.group("text"))
                    originals.add(old_text)
            except Exception:
                continue
        return originals

    def _get_untranslated_originals(self, tl_dir: Path) -> Set[str]:
        """
        获取 tl 目录中未翻译（new==old 或 new==""）的原文集合。

        说明：这是为“增量抽取”补全未翻译文件/条目用的，不会改动原 tl 目录。
        """
        pending: Set[str] = set()
        if not tl_dir.exists():
            return pending

        for rpy_file in self._iter_rpy_files(tl_dir):
            try:
                content = rpy_file.read_text(encoding="utf-8", errors="replace")
                doc = parse_tl_document(content.splitlines())
                extractor = RenpyTlItemExtractor()
                items = extractor.extract(doc, str(rpy_file))
                for item in items:
                    src = item.get_src()
                    if should_skip_text(src):
                        continue
                    if item.get_dst() == "" or item.get_dst() == src:
                        pending.add(src)
                continue
            except Exception:
                pass

            try:
                lines = rpy_file.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception:
                continue

            i = 0
            while i < len(lines):
                old_match = self.OLD_LINE_RE.match(lines[i])
                if not old_match:
                    i += 1
                    continue

                old_text = old_match.group("text").replace('\\"', '"').replace("\\'", "'")
                if should_skip_text(old_text):
                    i += 1
                    continue

                # 查找对应的 new（跳过空行/注释）
                j = i + 1
                while j < len(lines):
                    probe = lines[j].strip()
                    if not probe or probe.startswith("#"):
                        j += 1
                        continue
                    break

                new_text = ""
                if j < len(lines):
                    new_match = self.NEW_LINE_RE.match(lines[j])
                    if new_match:
                        new_text = new_match.group("text").replace('\\"', '"').replace("\\'", "'")

                if not new_text or new_text == old_text:
                    pending.add(old_text)

                i = j + 1 if j > i else i + 1

        return pending

    def _collect_selected_blocks_from_ast(
        self,
        doc,
        lines: List[str],
        items: List,
        tl_name: Optional[str] = None,
    ) -> List[Dict]:
        """根据 AST 抽取结果收集需要输出的翻译块。"""
        block_by_header = {block.header_line_no: block for block in doc.blocks}
        grouped: Dict[int, List] = {}

        for item in items:
            extra_raw = item.get_extra_field()
            extra = extra_raw if isinstance(extra_raw, dict) else {}
            renpy = extra.get("renpy", {}) if isinstance(extra.get("renpy"), dict) else {}
            block = renpy.get("block", {}) if isinstance(renpy.get("block"), dict) else {}
            lang = block.get("lang")
            if tl_name and isinstance(lang, str) and lang != tl_name:
                continue
            header_line = block.get("header_line")
            if not isinstance(header_line, int) or header_line <= 0:
                continue
            grouped.setdefault(header_line, []).append(item)

        selections: List[Dict] = []
        for header_line in sorted(grouped.keys()):
            block = block_by_header.get(header_line)
            if block is None:
                continue

            include_lines: Set[int] = set()
            idx_by_line = {s.line_no: idx for idx, s in enumerate(block.statements)}

            for item in grouped[header_line]:
                extra_raw = item.get_extra_field()
                extra = extra_raw if isinstance(extra_raw, dict) else {}
                renpy = extra.get("renpy", {}) if isinstance(extra.get("renpy"), dict) else {}
                pair = renpy.get("pair", {}) if isinstance(renpy.get("pair"), dict) else {}

                template_line = pair.get("template_line")
                target_line = pair.get("target_line")

                if isinstance(template_line, int) and template_line > 0:
                    include_lines.add(template_line)
                    # 吸收紧邻模板行的 META 注释（位置说明）
                    idx = idx_by_line.get(template_line)
                    if idx is not None:
                        j = idx - 1
                        while j >= 0:
                            stmt = block.statements[j]
                            if stmt.stmt_kind != TlStmtKind.META:
                                break
                            include_lines.add(stmt.line_no)
                            j -= 1

                if isinstance(target_line, int) and target_line > 0:
                    include_lines.add(target_line)

            if not include_lines:
                continue

            selected_lines: List[str] = []
            for stmt in block.statements:
                if stmt.line_no in include_lines and 1 <= stmt.line_no <= len(lines):
                    selected_lines.append(lines[stmt.line_no - 1])

            if not selected_lines:
                continue

            header_text = (
                lines[header_line - 1]
                if 1 <= header_line <= len(lines)
                else f"translate {block.lang} {block.label}:"
            )
            selections.append(
                {
                    "header_line_no": header_line,
                    "header_line": header_text,
                    "lang": block.lang,
                    "label": block.label,
                    "kind": str(block.kind),
                    "lines": selected_lines,
                }
            )

        return selections

    def _extract_new_entries_to_folder(
        self,
        source_dir: Path,
        target_dir: Path,
        selected_originals: Set[str],
        tl_name: str,
        game_dir: Optional[Path] = None,
    ):
        """将指定条目（新增/未翻译）提取到目标文件夹"""
        if not selected_originals:
            return

        extractor = RenpyTlItemExtractor()
        menu_locations = (
            rx.collect_static_menu_strings(game_dir) if game_dir is not None else {}
        )
        selected_menu_strings = selected_originals.intersection(menu_locations)

        for rpy_file in self._iter_rpy_files(source_dir):
            # AST 优先
            try:
                content = rpy_file.read_text(encoding="utf-8", errors="replace")
                lines = content.splitlines()
                doc = parse_tl_document(lines)
                items = extractor.extract(doc, str(rpy_file))
                if not items:
                    continue

                selected_items = [
                    item for item in items
                    if item.get_src() in selected_originals
                    and item.get_src() not in selected_menu_strings
                ]
                if not selected_items:
                    continue

                selections = self._collect_selected_blocks_from_ast(
                    doc, lines, selected_items, tl_name
                )
                if not selections:
                    continue

                rel_path = rpy_file.relative_to(source_dir)
                target_file = target_dir / rel_path
                target_file.parent.mkdir(parents=True, exist_ok=True)

                output_lines = [
                    "# 增量抽取 - 新增/待翻译内容",
                    f"# 来源: {rpy_file.name}",
                    "",
                ]

                for sel in selections:
                    output_lines.append(sel["header_line"])
                    output_lines.extend(sel["lines"])
                    if output_lines and output_lines[-1].strip() != "":
                        output_lines.append("")

                text = "\n".join(output_lines).rstrip() + "\n"
                target_file.write_text(text, encoding="utf-8")
                continue
            except Exception as e:
                self.logger.warning(f"AST 增量提取失败 {rpy_file}: {e}")

            # 回退旧正则逻辑
            try:
                content = rpy_file.read_text(encoding='utf-8', errors='replace')
                lines = content.split('\n')

                new_entries: List[Tuple[str, str]] = []  # (old_text, new_text)

                i = 0
                while i < len(lines):
                    line = lines[i]
                    old_match = self.OLD_LINE_RE.match(line)
                    if old_match:
                        old_text = old_match.group("text").replace('\\"', '"').replace("\\'", "'")
                        new_text = ""

                        if i + 1 < len(lines):
                            new_line = lines[i + 1]
                            new_match = self.NEW_LINE_RE.match(new_line)
                            if new_match:
                                new_text = new_match.group("text")

                        # 只提取被选中的原文
                        if (
                            old_text in selected_originals
                            and old_text not in selected_menu_strings
                        ):
                            new_entries.append((old_text, new_text))

                        i += 2
                        continue
                    i += 1

                # 写入目标文件
                if new_entries:
                    rel_path = rpy_file.relative_to(source_dir)
                    target_file = target_dir / rel_path
                    target_file.parent.mkdir(parents=True, exist_ok=True)

                    output_lines = [
                        f"# 增量抽取 - 新增/待翻译内容",
                        f"# 来源: {rpy_file.name}",
                        "",
                        f"translate {tl_name} strings:",
                        "",
                    ]

                    for old_text, new_text in new_entries:
                        escaped_old = self._escape_rpy_string(old_text)
                        escaped_new = self._escape_rpy_string(new_text) if new_text else ""
                        output_lines.append(f'    old "{escaped_old}"')
                        output_lines.append(f'    new "{escaped_new}"')
                        output_lines.append("")

                    target_file.write_text('\n'.join(output_lines), encoding='utf-8')

            except Exception as e:
                self.logger.warning(f"处理文件失败 {rpy_file}: {e}")

        if game_dir is not None:
            for original in sorted(selected_menu_strings):
                relative_path = menu_locations[original]
                target_file = target_dir / relative_path
                target_file.parent.mkdir(parents=True, exist_ok=True)
                source_file = game_dir / "game" / relative_path
                source_line = self._find_source_menu_line(source_file, original)
                escaped = self._escape_rpy_string(original)
                entry_lines = []
                if source_line is not None:
                    entry_lines.append(f"    # game/{relative_path}:{source_line}")
                entry_lines.extend([f'    old "{escaped}"', f'    new "{escaped}"', ""])

                if target_file.exists():
                    lines = target_file.read_text(
                        encoding="utf-8", errors="replace"
                    ).splitlines()
                else:
                    lines = [
                        "# 增量抽取 - 新增/待翻译内容",
                        f"# 来源: {Path(relative_path).name}",
                        "",
                    ]
                header_re = re.compile(
                    rf"^\s*translate\s+{re.escape(tl_name)}\s+strings\s*:\s*$"
                )
                if not any(header_re.match(line) for line in lines):
                    if lines and lines[-1].strip():
                        lines.append("")
                    lines.extend([f"translate {tl_name} strings:", ""])
                lines.extend(entry_lines)
                target_file.write_text(
                    "\n".join(lines).rstrip() + "\n", encoding="utf-8"
                )

            self._annotate_incremental_string_locations(game_dir, target_dir)

    def _annotate_incremental_string_locations(
        self, game_dir: Path, target_dir: Path
    ) -> int:
        """为增量 old/new 条目补充源文件和行号注释。"""
        added = 0
        for target_file in self._iter_rpy_files(target_dir):
            try:
                relative_path = target_file.relative_to(target_dir)
                source_file = game_dir / "game" / relative_path
                if not source_file.is_file():
                    continue
                lines = target_file.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
            except Exception:
                continue
            output: List[str] = []
            changed = False
            for line in lines:
                old_match = self.OLD_LINE_RE.match(line)
                if old_match:
                    previous = next(
                        (entry.strip() for entry in reversed(output) if entry.strip()), ""
                    )
                    if not previous.startswith("# game/"):
                        original = self._decode_literal_value(
                            old_match.group(1), old_match.group("text")
                        )
                        source_line = self._find_source_text_line(source_file, original)
                        if source_line is not None:
                            output.append(
                                f"    # game/{relative_path.as_posix()}:{source_line}"
                            )
                            added += 1
                            changed = True
                output.append(line)
            if changed:
                target_file.write_text(
                    "\n".join(output).rstrip() + "\n", encoding="utf-8"
                )
        return added

    @staticmethod
    def _find_source_menu_line(source_file: Path, original: str) -> Optional[int]:
        menu_choice_re = re.compile(
            r'^\s*"(?P<text>(?:\\.|[^"\\])*)"\s*(?:\([^)]*\))?\s*:\s*(?:#.*)?$'
        )
        try:
            lines = source_file.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines()
        except Exception:
            return None
        for line_no, line in enumerate(lines, 1):
            match = menu_choice_re.match(line)
            if not match:
                continue
            try:
                value = ast.literal_eval(f'"{match.group("text")}"')
            except Exception:
                value = match.group("text").replace('\\"', '"').replace("\\'", "'")
            if value == original:
                return line_no
        return None

    def _merge_new_entries(
        self,
        tl_dir: Path,
        source_dir: Path,
        new_originals: Set[str],
        existing_translations: Dict[str, str]
    ):
        """将新增条目合并到原 tl 目录（旧行为）"""
        if not new_originals:
            return

        extractor = RenpyTlItemExtractor()

        for rpy_file in self._iter_rpy_files(source_dir):
            rel_path = rpy_file.relative_to(source_dir)
            target_file = tl_dir / rel_path

            # AST 优先
            try:
                content = rpy_file.read_text(encoding="utf-8", errors="replace")
                lines = content.splitlines()
                doc = parse_tl_document(lines)
                items = extractor.extract(doc, str(rpy_file))
                if not items:
                    continue

                selected_items = [item for item in items if item.get_src() in new_originals]
                if not selected_items:
                    continue

                if not target_file.exists():
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(rpy_file), str(target_file))
                    continue

                target_content = target_file.read_text(encoding="utf-8", errors="replace")
                target_lines = target_content.splitlines()
                target_doc = parse_tl_document(target_lines)
                target_items = extractor.extract(target_doc, str(target_file))
                target_originals = {item.get_src() for item in target_items}

                filtered_items = [item for item in selected_items if item.get_src() not in target_originals]
                if not filtered_items:
                    continue

                selections = self._collect_selected_blocks_from_ast(doc, lines, filtered_items)
                if not selections:
                    continue

                block_map = {}
                for block in target_doc.blocks:
                    key = (block.lang, block.label, str(block.kind))
                    block_map[key] = block

                combined: Dict[Tuple[str, str, str], Dict[str, List[str]]] = {}
                for sel in sorted(selections, key=lambda x: x["header_line_no"]):
                    key = (sel["lang"], sel["label"], sel["kind"])
                    entry = combined.get(key)
                    if entry is None:
                        entry = {"header": sel["header_line"], "lines": []}
                        combined[key] = entry
                    entry["lines"].extend(sel["lines"])

                insert_ops: List[Tuple[int, List[str]]] = []
                append_lines: List[str] = []

                for key, entry in combined.items():
                    lines_to_insert = entry["lines"]
                    if not lines_to_insert:
                        continue
                    block = block_map.get(key)
                    if block is not None:
                        end_line = block.statements[-1].line_no if block.statements else block.header_line_no
                        insert_ops.append((end_line, lines_to_insert))
                    else:
                        header = entry["header"]
                        if append_lines and append_lines[-1].strip() != "":
                            append_lines.append("")
                        append_lines.append(header)
                        append_lines.extend(lines_to_insert)

                for index, insert_lines in sorted(insert_ops, key=lambda x: x[0], reverse=True):
                    if index < 0:
                        continue
                    if index > len(target_lines):
                        index = len(target_lines)
                    target_lines[index:index] = insert_lines

                if append_lines:
                    if target_lines and target_lines[-1].strip() != "":
                        target_lines.append("")
                    target_lines.extend(append_lines)

                if insert_ops or append_lines:
                    target_file.write_text("\n".join(target_lines), encoding="utf-8")
                continue
            except Exception as e:
                self.logger.warning(f"AST 合并新增失败 {rpy_file}: {e}")

            # 回退旧正则逻辑
            try:
                content = rpy_file.read_text(encoding='utf-8', errors='replace')
                rel_path = rpy_file.relative_to(source_dir)
                target_file = tl_dir / rel_path

                if target_file.exists():
                    # 追加新条目到现有文件
                    target_content = target_file.read_text(encoding='utf-8', errors='replace')
                    target_originals = set()
                    for match in self.OLD_LINE_RE.finditer(target_content):
                        target_originals.add(match.group("text").replace('\\"', '"').replace("\\'", "'"))

                    lines = content.split('\n')
                    new_entries = []

                    i = 0
                    while i < len(lines):
                        line = lines[i]
                        old_match = self.OLD_LINE_RE.match(line)
                        if old_match:
                            old_text = old_match.group("text").replace('\\"', '"').replace("\\'", "'")

                            if old_text in new_originals and old_text not in target_originals:
                                new_text = ""
                                if i + 1 < len(lines):
                                    new_line = lines[i + 1]
                                    new_match = self.NEW_LINE_RE.match(new_line)
                                    if new_match:
                                        new_text = new_match.group("text")

                                new_entries.append((old_text, new_text))

                            i += 2
                            continue
                        i += 1

                    if new_entries:
                        append_lines = ["\n# 增量抽取新增"]
                        for old_text, new_text in new_entries:
                            escaped_old = self._escape_rpy_string(old_text)
                            escaped_new = self._escape_rpy_string(new_text) if new_text else ""
                            append_lines.append(f'    old "{escaped_old}"')
                            append_lines.append(f'    new "{escaped_new}"')

                        with target_file.open('a', encoding='utf-8') as f:
                            f.write('\n'.join(append_lines))
                else:
                    # 创建新文件
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(rpy_file), str(target_file))

            except Exception as e:
                self.logger.warning(f"合并文件失败 {rpy_file}: {e}")

    def _collect_block_originals(self, tl_dir: Path) -> Set[str]:
        """收集 translate 块中的原文（从注释行提取），用于与 strings 去重"""
        block_originals: Set[str] = set()
        if not tl_dir.exists():
            return block_originals

        for rpy_file in self._iter_rpy_files(tl_dir):
            try:
                content = rpy_file.read_text(encoding="utf-8", errors="replace")
                doc = parse_tl_document(content.splitlines())
                extractor = RenpyTlItemExtractor()
                items = extractor.extract(doc, str(rpy_file))
                for item in items:
                    extra = item.get_extra_field()
                    if not isinstance(extra, dict):
                        continue
                    renpy = extra.get("renpy")
                    if not isinstance(renpy, dict):
                        continue
                    block = renpy.get("block")
                    if not isinstance(block, dict):
                        continue
                    kind = block.get("kind")
                    kind_value = getattr(kind, "value", kind)
                    kind_text = str(kind_value)
                    if kind_text.startswith("TlBlockKind."):
                        kind_text = kind_text.split(".", 1)[1]
                    if kind_text == "LABEL":
                        block_originals.add(item.get_src())
                continue
            except Exception:
                pass

            try:
                lines = rpy_file.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception:
                continue

            in_block = False
            block_indent = 0
            for line in lines:
                stripped = line.lstrip()
                # 进入新的 translate 块
                if stripped.startswith("translate ") and stripped.endswith(":"):
                    in_block = True
                    block_indent = len(line) - len(stripped)
                    continue

                if not in_block:
                    continue

                current_indent = len(line) - len(stripped)
                # 块结束：出现不缩进或新的 translate
                if stripped and current_indent <= block_indent:
                    in_block = False
                    block_indent = 0
                    continue

                # 提取注释里的原文
                if stripped.startswith("#"):
                    # Ren'Py 官方生成的注释基本使用双引号包裹原文
                    m = re.search(r'"((?:\\.|[^"])*)"', stripped)
                    if m:
                        txt = m.group(1).replace('\\"', '"').replace("\\'", "'")
                        block_originals.add(txt)
        return block_originals

    def _remove_string_duplicates_with_blocks(self, tl_dir: Path) -> int:
        """保留与对话块同文的 strings 条目，避免误删菜单等静态文本。"""
        del tl_dir
        # Ren'Py 允许对话块和 strings 同时存在，仅按 old 文本去重会误删菜单。
        return 0

    def _backup_tl_dir(self, game_dir: Path, tl_name: str):
        """备份 tl 目录"""
        tl_dir = game_dir / "game" / "tl" / tl_name
        if tl_dir.exists():
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            backup_path = game_dir / f"tl_backup_{tl_name}_{timestamp}"
            try:
                shutil.move(str(tl_dir), str(backup_path))
                self._emit_progress(f"已备份旧翻译", 5)
            except Exception as e:
                self.logger.warning(f"备份失败: {e}")

    def _post_process(
        self,
        project_root: Path,
        tl_name: str,
        tl_dir: Path,
        config: Config,
        existing_translations: Optional[Dict[str, str]] = None,
    ):
        """后处理：应用保留库过滤 + 清理空文件"""
        self._last_suspicious_manifest = None
        self._last_suspicious_removed_count = 0
        preserve_set = self._load_preserve_set(config)
        
        # 应用过滤
        if preserve_set:
            self._emit_progress("正在应用保留库过滤...", 80)
            self._filter_tl_files(tl_dir, preserve_set)

        # 过滤疑似误提取的代码布尔表达式（例如 foo == True / bar = false）
        if getattr(config, "renpy_filter_suspicious_bool_expr", True):
            removed_suspicious, manifest_path = self._remove_suspicious_bool_expr_entries(tl_dir, tl_name)
            self._last_suspicious_removed_count = removed_suspicious
            self._last_suspicious_manifest = manifest_path
            if removed_suspicious:
                manifest_msg = str(manifest_path) if manifest_path else "N/A"
                self.logger.info(
                    f"已过滤疑似误提取条目 {removed_suspicious} 条，可在清单勾选恢复: {manifest_msg}"
                )

        # 抽取后统一做一次 old/new 去重，避免同一原文重复导致 Ren'Py 报错。
        try:
            rx.remove_repeat_extracted_from_tl(str(tl_dir), is_py2=False)
        except Exception as exc:
            self.logger.warning(f"去重失败 {tl_dir}: {exc}")

        removed_source = self._remove_source_registered_string_duplicates(
            project_root, tl_dir, tl_name
        )
        if removed_source:
            self.logger.info(f"已清理与游戏源码翻译重复的 strings 条目 {removed_source} 条")

        # 移除与 translate 块重复的 strings 条目（保留块翻译，删掉 old/new）
        if getattr(config, "renpy_remove_string_duplicates", False):
            removed = self._remove_string_duplicates_with_blocks(tl_dir)
            if removed:
                self.logger.info(f"已移除 {removed} 条与翻译块重复的 strings 翻译")
            
        # 移除 Hook 及工具型文件
        if getattr(config, "extract_skip_hook_files", False):
            self._prune_hook_files(tl_dir)

        # 清理空 translate strings 块，避免后续官方抽取报错
        removed_blocks = self._remove_empty_translate_blocks(tl_dir, tl_name)
        if removed_blocks:
            self.logger.info(f"已移除 {removed_blocks} 个空的 translate strings 块")

        # 自动套用用户术语库，避免重复翻译（仅填充 new==old 或 new=="" 的占位）
        glossary_map = self._load_glossary_map(config)
        if glossary_map:
            self._emit_progress("正在应用术语库填充...", 85)
            applied = self._apply_glossary_to_tl(tl_dir, glossary_map)
            if applied:
                self.logger.info(f"已自动填充 {applied} 条术语库翻译")

        # 清理旧版本遗留的 auto_screens_default.rpy（历史遗留，避免混入翻译目录）
        self._cleanup_legacy_auto_screens_translation(tl_dir)

        # 清理空文件
        self._emit_progress("正在清理空文件...", 90)
        for rpy_file in self._iter_rpy_files(tl_dir):
            try:
                if rpy_file.stat().st_size == 0:
                    rpy_file.unlink()
            except:
                pass

        # 终极结构导出
        if getattr(config, "extract_export_excel", False):
            if existing_translations is None:
                existing_translations = self._get_existing_translations(tl_dir)
            try:
                exporter = MaExtractor(self.logger)
                exporter.run(project_root, tl_name, preserve_set, existing_translations, config)
            except Exception as exc:
                self.logger.warning(f"终极结构导出失败: {exc}")

    def _load_preserve_set(self, config: Config) -> Set[str]:
        """加载保留文本库"""
        try:
            preserve_set = set()
            if config.text_preserve_enable and config.text_preserve_data:
                for item in config.text_preserve_data:
                    if isinstance(item, dict):
                        src = item.get("src", "").strip()
                        if src: preserve_set.add(src)
                    elif isinstance(item, str) and item.strip():
                        preserve_set.add(item.strip())
            return preserve_set
        except:
            return set()

    def _prune_hook_files(self, tl_dir: Path):
        """删除官方抽取生成的 Hook / 工具脚本。"""
        hook_names = set(RenpyExtractor.HOOK_FILES)
        extra_patterns = (
            "hook_",
            "unrpyc",
            "set_default_language_at_startup",
        )
        for rpy_file in tl_dir.rglob("*.rpy"):
            name = rpy_file.name
            stem = rpy_file.stem
            if name in hook_names or any(stem.startswith(pat) for pat in extra_patterns):
                try:
                    rpy_file.unlink()
                except Exception as exc:
                    self.logger.warning(f"删除 Hook 文件失败 {rpy_file}: {exc}")
                companion = rpy_file.with_suffix(".rpyc")
                if companion.exists():
                    try:
                        companion.unlink()
                    except Exception:
                        pass
            else:
                # 同名 rpyc 一并删除
                rpyc_path = rpy_file.with_suffix(".rpyc")
                if rpyc_path.exists() and (
                    rpyc_path.name in hook_names
                    or any(rpyc_path.stem.startswith(pat) for pat in extra_patterns)
                ):
                    try:
                        rpyc_path.unlink()
                    except Exception:
                        pass

    def _get_existing_translations(self, tl_dir: Path) -> Dict[str, str]:
        """
        获取有效的翻译对 {original: translated}
        条件：new != "" AND new != old
        """
        translations: Dict[str, str] = {}
        if not tl_dir.exists():
            return translations

        extractor = RenpyTlItemExtractor()
        for rpy_file in self._iter_rpy_files(tl_dir):
            try:
                content = rpy_file.read_text(encoding="utf-8", errors="replace")
                doc = parse_tl_document(content.splitlines())
                items = extractor.extract(doc, str(rpy_file))
                for item in items:
                    src = item.get_src()
                    dst = item.get_dst()
                    if dst and dst != src:
                        translations[src] = dst
                continue
            except Exception:
                pass

            # AST 失败时回退到旧正则逻辑
            try:
                content = rpy_file.read_text(encoding="utf-8", errors="replace")
                lines = content.split("\n")
                i = 0
                while i < len(lines):
                    line = lines[i]
                    # 匹配 old
                    old_match = self.OLD_LINE_RE.match(line)
                    if old_match:
                        old_text = old_match.group("text")
                        # 查找对应的 new（跳过空行/注释）
                        j = i + 1
                        while j < len(lines):
                            probe = lines[j].strip()
                            if not probe or probe.startswith("#"):
                                j += 1
                                continue
                            break

                        if j < len(lines):
                            new_line = lines[j]
                            new_match = self.NEW_LINE_RE.match(new_line)
                            if new_match:
                                new_text = new_match.group("text")
                                # 只有当 new_text 有内容且不等于 old_text 时才保存
                                if new_text and new_text != old_text:
                                    # 处理转义字符
                                    old_text_u = old_text.replace('\\"', '"').replace("\\'", "'")
                                    new_text_u = new_text.replace('\\"', '"').replace("\\'", "'")
                                    translations[old_text_u] = new_text_u
                                i = j
                    i += 1
            except Exception:
                pass
        return translations

    def _merge_translations(self, tl_dir: Path, translations: Dict[str, str]):
        """将翻译回填到新生成的文件中"""
        if not translations:
            return

        extractor = RenpyTlItemExtractor()
        writer = RenpyTlLineUpdater()

        for rpy_file in self._iter_rpy_files(tl_dir):
            # 优先使用 AST 回填，失败再走旧正则逻辑
            try:
                content = rpy_file.read_text(encoding="utf-8", errors="replace")
                lines = content.splitlines()
                doc = parse_tl_document(lines)
                items = extractor.extract(doc, str(rpy_file))
                if items:
                    updated = False
                    for item in items:
                        src = item.get_src()
                        if src in translations:
                            item.set_dst(translations[src])
                            updated = True

                    if updated:
                        def get_target_line(cache_item) -> int:
                            extra_raw = cache_item.get_extra_field()
                            extra = extra_raw if isinstance(extra_raw, dict) else {}
                            renpy = extra.get("renpy", {}) if isinstance(extra.get("renpy"), dict) else {}
                            pair = renpy.get("pair", {}) if isinstance(renpy.get("pair"), dict) else {}
                            line = pair.get("target_line")
                            return int(line) if isinstance(line, int) else 0

                        items.sort(key=get_target_line)
                        applied, _ = writer.apply_items_to_lines(lines, items)
                        if applied > 0:
                            rpy_file.write_text("\n".join(lines), encoding="utf-8")
                    continue
            except Exception as e:
                self.logger.warning(f"AST 回填翻译失败 {rpy_file}: {e}")

            # 回退旧正则逻辑
            try:
                content = rpy_file.read_text(encoding="utf-8")
                lines = content.split("\n")
                new_lines = []
                modified = False

                i = 0
                while i < len(lines):
                    line = lines[i]
                    # 匹配 old
                    match = re.match(r'(\s*)old\s+(["\'])(.+?)\2', line)
                    if match and i + 1 < len(lines):
                        indent = match.group(1)
                        old_text = match.group(3)
                        old_text_unescaped = old_text.replace('\\"', '"').replace("\\'", "'")

                        # 检查是否有翻译
                        if old_text_unescaped in translations:
                            trans_text = translations[old_text_unescaped]
                            # 转义
                            trans_text_escaped = trans_text.replace('"', '\\"')

                            new_lines.append(line)  # old 行不变
                            new_lines.append(f'{indent}new "{trans_text_escaped}"')  # 替换 new 行
                            modified = True
                            i += 2  # 跳过原来的 new 行
                            continue

                    new_lines.append(line)
                    i += 1

                if modified:
                    rpy_file.write_text("\n".join(new_lines), encoding="utf-8")
            except Exception as e:
                self.logger.warning(f"回填翻译失败 {rpy_file}: {e}")

    def _filter_tl_files(self, tl_dir: Path, preserve_set: Set[str]):
        """过滤 tl 文件：移除在 preserve_set 中的条目 或 should_skip_text 的条目"""
        for rpy_file in self._iter_rpy_files(tl_dir):
            try:
                content = rpy_file.read_text(encoding='utf-8')
                lines = content.split('\n')
                filtered: List[str] = []
                modified = False
                i = 0

                while i < len(lines):
                    line = lines[i]
                    match = self.OLD_LINE_RE.match(line)
                    if match:
                        old_text = match.group("text").replace('\\"', '"').replace("\\'", "'")

                        next_line = lines[i + 1] if i + 1 < len(lines) else ""
                        new_match = self.NEW_LINE_RE.match(next_line)

                        if (
                            old_text in preserve_set
                            or should_skip_text(old_text)
                        ):
                            modified = True
                            # 跳过 old 行和其后的 new 行
                            i += 2 if new_match else 1
                            continue

                    filtered.append(line)
                    i += 1

                if modified:
                    # 移除连续空行
                    final_lines: List[str] = []
                    prev_empty = False
                    for entry in filtered:
                        is_empty = not entry.strip()
                        if is_empty and prev_empty:
                            continue
                        final_lines.append(entry)
                        prev_empty = is_empty

                    rpy_file.write_text('\n'.join(final_lines), encoding='utf-8')

            except Exception:
                pass







