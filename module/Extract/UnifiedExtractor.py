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
import json
import re
import shutil
import time
from dataclasses import dataclass, field
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
    tl_block_kind_name,
    tl_dir_signature,
)
from module.Renpy.renpy_tl_io import RenpyTlLineUpdater
from module.Renpy.renpy_tl_core import TlStmtKind
from module.Renpy import renpy_extract as rx
from module.Renpy.ProjectPaths import RenpyProjectPaths
from module.Text.SkipRules import should_skip_text
from module.File.AtomicWrite import atomic_write_text
from module.Response.ResponseChecker import ResponseChecker
from module.Extract.ReplaceGenerator import (
    load_declined_candidates,
    record_declined_candidates,
)


# 结果缓存：键为 (tl 目录解析路径, 文件签名)，文件任何变化都会使签名失效，
# 因此缓存命中不会造成遗漏，仅避免同一轮流程对未变化目录的重复全量解析。
_STRING_ORIGINALS_CACHE: Dict[tuple, frozenset] = {}
_NUMBERED_FINGERPRINTS_CACHE: Dict[tuple, dict] = {}
_EXISTING_TRANSLATIONS_CACHE: Dict[tuple, tuple] = {}

_BLOCK_LOCATION_RE = re.compile(r"^\s*#\s+(game/.+?):(\d+)\s*$")

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


@dataclass
class TranslationReuseResult:
    """按原文复用旧译文的预览/执行结果。"""

    source_translations: int = 0
    target_entries: int = 0
    matched_entries: int = 0
    reusable_entries: int = 0
    applied_entries: int = 0
    already_reused: int = 0
    conflicts: int = 0
    unmatched_entries: int = 0
    backup_path: Optional[Path] = None


@dataclass
class ExistingTranslations:
    """按 Ren'Py 作用域保存已有译文，避免编号块按原文串译。"""

    strings: Dict[str, str]
    blocks: Dict[Tuple[str, str, str, str, int], str]
    block_names: Dict[Tuple[str, str, str, str, int], str] = field(
        default_factory=dict
    )

    def __len__(self) -> int:
        return len(self.strings) + len(set(self.blocks) | set(self.block_names))


class _FilteredMergeWriteError(RuntimeError):
    """筛选后的新增翻译无法安全写入。"""


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
        # 内置 UI 文件跳过日志每个文件仅记录一次，避免多次全目录扫描时刷屏
        self._logged_ui_skips: set = set()

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
        callback = getattr(self, "_progress_callback", None)
        if callback:
            callback(message, percent)

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
        files = sorted(
            tl_dir.rglob("*.rpy"),
            key=lambda path: path.relative_to(tl_dir).as_posix().casefold(),
        )
        for rpy_file in files:
            try:
                rel_parts = [part.lower() for part in rpy_file.relative_to(tl_dir).parts[:-1]]
                if any(part in self.INTERNAL_TL_DIRS for part in rel_parts):
                    continue
            except Exception as exc:
                self.logger.warning(f"无法解析翻译文件相对路径 {rpy_file}: {exc}")
            # 缺失补丁：仅作为生成 replace_text 的中间文件，不应参与抽取/增量统计与后处理
            if rpy_file.name.startswith("miss_ready_replace"):
                continue
            if self._is_builtin_ui_file(rpy_file):
                # 每次全目录扫描都会经过同一组内置 UI 文件；只记录一次即可定位，
                # 避免日志刷屏拖慢大批量扫描。
                logged_ui_skips = getattr(self, "_logged_ui_skips", None)
                if logged_ui_skips is None:
                    logged_ui_skips = self._logged_ui_skips = set()
                if str(rpy_file) not in logged_ui_skips:
                    logged_ui_skips.add(str(rpy_file))
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
                    # 有效译文来自任意文件（不仅是 common/screens），用于补全
                    # base_box 占位，避免注入后与源文件译文重复或丢失。
                    ui_translation_overrides.setdefault(old_value, new_value)

                if placeholder_olds:
                    removed_placeholders += remove_string_entries_by_old_values(rpy_file, placeholder_olds)

            # 处理占位清理后可能出现的空 strings 块（例如仅剩 `translate xxx strings:`），避免 Ren'Py 解析报错。
            try:
                self._remove_empty_translate_blocks(tl_dir, tl_name)
            except Exception as exc:
                self.logger.warning(f"清理内置 UI 空翻译块失败 {tl_dir}: {exc}")

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
            except Exception as exc:
                self.logger.warning(
                    f"无法解析 base_box 清理文件相对路径 {rpy_file}: {exc}"
                )

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

    def _delete_empty_translation_files(self, tl_dir: Path, tl_name: str) -> int:
        """删除翻译完成后仍为空的 .rpy 文件。

        空文件对 Ren'Py 无意义；若删除条目后文件只剩 ``translate <lang>
        strings:`` 头而没有条目，Ren'Py 启动会报错，因此整个文件删除。
        纯用户注释可能是手写说明，不得删除；仅含工具位置注释仍视为空文件。
        同名 .rpyc 一并删除，避免 Ren'Py 读到过期的编译缓存。
        """
        header_re = re.compile(
            r"^\s*translate\s+" + re.escape(tl_name) + r"\s+strings\s*:\s*$"
        )
        entry_re = re.compile(r"^\s*(?:old|new)\s+")
        removed = 0
        for rpy_file in self._iter_rpy_files(tl_dir):
            try:
                lines = rpy_file.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
            except Exception:
                continue
            has_content = False
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped.startswith("#"):
                    # 工具生成的位置注释不算内容；其它注释可能是用户备注。
                    if _BLOCK_LOCATION_RE.fullmatch(line):
                        continue
                    has_content = True
                    break
                if header_re.match(line):
                    continue
                if entry_re.match(line):
                    has_content = True
                    break
                # 其它任意语句（say、python、style 等）都视为有效内容。
                has_content = True
                break
            if has_content:
                continue
            try:
                rpyc_file = rpy_file.with_suffix(".rpyc")
                rpy_file.unlink()
                if rpyc_file.exists():
                    rpyc_file.unlink()
                removed += 1
                self.logger.info(
                    f"已删除空翻译文件: {rpy_file.relative_to(tl_dir)}"
                )
            except Exception as exc:
                self.logger.warning(f"删除空翻译文件失败 {rpy_file}: {exc}")
        return removed

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
        # 上次运行若被中断，先把 tl 恢复回来再继续。
        self._recover_stale_incremental_state(game_dir, tl_name)
        self._warn_if_writeback_report(tl_dir)
        backup_path: Optional[Path] = None
        
        try:
            config = Config().load()
            allow_official = bool(use_official and config.extract_use_official and exe_path)
            allow_custom = bool(config.extract_use_custom)

            if not allow_official and not allow_custom:
                result.success = False
                result.message = "常规抽取已被禁用，请启用官方或补充抽取后重试"
                return result

            # 1. 备份
            backup_path = self._backup_tl_dir(game_dir, tl_name)
            
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

            # 4b. 编译补充抽取：随包 .pyc 中玩家可见的常量同样写入标准
            #     translate strings old/new，而不是留给 replace_text 补全。
            compiled_added = 0
            if getattr(config, "extract_use_compiled", True):
                compiled_added = self._append_compiled_supplement_entries(
                    game_dir, tl_dir, tl_name
                )

            # 5. 过滤与清理 + 终极结构导出
            self._post_process(game_dir, tl_name, tl_dir, config, None)
            # 5b. 写入后校验 old 唯一性，避免 Ren'Py 启动报重复翻译错误。
            self._dedupe_string_translations(tl_dir, tl_name)
            # 6. 注入内置 UI 包（common_box/screens_box）
            injected_ui = 0
            if getattr(config, "onekey_inject_base_box", False):
                injected_ui = self._deploy_builtin_ui_pack(tl_dir, tl_name)
                # 注入后的 base_box 可能与其他文件产生重复 old，必须收尾校验。
                self._dedupe_string_translations(tl_dir, tl_name)
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
            if compiled_added:
                result.message += f"（编译字符串 {compiled_added} 条）"
            if backup_path is not None:
                result.message += f"（旧翻译备份: {backup_path.name}）"
            self._emit_progress("抽取完成", 100)
            
        except Exception as e:
            import traceback
            self.logger.error(traceback.format_exc())
            result.success = False
            if backup_path is not None and backup_path.is_dir():
                # 抽取失败必须把原 tl 恢复回去，避免游戏 TL 处于半生成状态。
                try:
                    if tl_dir.exists():
                        shutil.rmtree(str(tl_dir), ignore_errors=True)
                    shutil.move(str(backup_path), str(tl_dir))
                    self.logger.info(f"常规抽取失败，已恢复原翻译目录: {tl_dir}")
                    result.message = f"{e}；已自动恢复原翻译目录"
                except Exception as restore_exc:
                    self.logger.error(f"恢复原翻译目录失败: {restore_exc}")
                    result.message = (
                        f"{e}；恢复原翻译失败，备份位于 {backup_path}: {restore_exc}"
                    )
            else:
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

            # Freeze the loaded TL before extraction. Do not rewrite its source
            # comments from decompiled line numbers here: decompilation can shift
            # lines relative to Ren'Py's official anchors and create a two-run
            # fingerprint oscillation. The fresh extraction is authoritative.
            existing_block_fingerprints = self._collect_numbered_block_fingerprints(tl_dir)
            existing_block_keys = set(existing_block_fingerprints)

            # 旧译文始终按当前磁盘模板身份收集；新快照只负责判定是否变化。
            existing_translations = self._get_existing_translations(tl_dir)
            translated_count = len(existing_translations)
            result.preserved_count = translated_count

            self.logger.info(f"发现 {translated_count} 条有效翻译")
            
            # 2. strings 按原文全局去重；带编号的翻译块按文件与块标签判断。
            #    编号块中的相同原文属于不同语句，不能因为别处翻译过就跳过。
            block_originals: Set[str] = set()
            all_current_string_originals = self._get_string_originals(
                tl_dir, block_originals=block_originals
            )
            # Built-in UI packs are intentionally skipped by the normal TL
            # iterator, but their global strings are still registered by Ren'Py.
            # Include their identities in incremental comparison or every apply
            # cycle will remove duplicates and the next extraction will add them
            # again.
            all_current_string_originals.update(
                self._collect_base_box_old_values(tl_dir)
            )
            # Source files can register language strings outside game/tl. Merge
            # cleanup removes their duplicate TL entries, so incremental compare
            # must also treat those registrations as already present.
            all_current_string_originals.update(
                self._collect_source_registered_old_values(game_dir, tl_name)
            )
            translated_string_originals = set(existing_translations.strings)
            self.logger.info(
                f"当前共有 {len(all_current_string_originals)} 条 strings 原文，"
                    f"{len(existing_block_keys)} 个编号翻译块"
            )

            # 3. 创建临时目录进行抽取
            temp_extract_dir = game_dir / f"_temp_extract_{tl_name}_{int(time.time())}"
            temp_tl_dir = temp_extract_dir / "game" / "tl" / tl_name
            temp_tl_dir.parent.mkdir(parents=True, exist_ok=True)
            temp_backup_dir = temp_extract_dir / "_tl_backup"
            # 崩溃恢复日志：移动 tl 前写入，结束时清除。
            self._write_incremental_journal(game_dir, tl_name, temp_extract_dir, tl_dir)
            
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
                    official_string_originals: Set[str] = set()
                    if allow_official:
                        self._emit_progress("正在执行官方抽取...", 30)
                        try:
                            self.renpy_extractor.official_extract(
                                str(exe_path), tl_name, generate_empty=False, force=True
                            )
                            official_string_originals = self._get_string_originals(tl_dir)
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

                    # 7. 捕获本次抽取结果到临时目录，用于对比新增。保留真实目录
                    # 直到 finally 开始恢复，避免移动/跨卷降级期间把已生成结果
                    # 静默变成空快照。
                    if temp_tl_dir.exists():
                        shutil.rmtree(str(temp_tl_dir), ignore_errors=True)
                    if tl_dir.exists():
                        shutil.copytree(str(tl_dir), str(temp_tl_dir))
                    else:
                        temp_tl_dir.mkdir(parents=True, exist_ok=True)
                finally:
                    # 恢复原 tl 目录
                    if tl_dir.exists():
                        shutil.rmtree(str(tl_dir), ignore_errors=True)
                    _relocate_dir(temp_backup_dir, tl_dir, remove_src=True)
                
                # 静态源码文本必须写入标准 TL，不交给 replace_text。
                static_candidates = rx.collect_static_source_strings(game_dir)
                menu_candidates = set(rx.collect_static_menu_strings(game_dir))
                static_added = self._append_static_supplement_entries(
                    game_dir,
                    temp_tl_dir,
                    tl_name,
                    candidates=static_candidates,
                    menu_candidates=menu_candidates,
                )
                compiled_candidates: Set[str] = set()
                compiled_added = 0
                if getattr(config, "extract_use_compiled", True):
                    try:
                        from module.Extract.ReplaceGenerator import (
                            collect_compiled_candidate_texts,
                        )

                        compiled_candidates = set(
                            collect_compiled_candidate_texts(
                                game_dir,
                                tl_name=tl_name,
                            )
                        )
                    except Exception as exc:
                        self.logger.warning(f"编译字符串收集失败: {exc}")
                        compiled_candidates = set()
                    compiled_added = self._append_compiled_supplement_entries(
                        game_dir,
                        temp_tl_dir,
                        tl_name,
                        candidates=compiled_candidates,
                    )
                    if compiled_added:
                        self.logger.info(
                            f"增量抽取：编译字符串 {compiled_added} 条将作为"
                            "标准 old/new 写入增量目录"
                        )
                # 6. strings 与编号翻译块分别计算增量。
                extracted_block_originals: Set[str] = set()
                new_extracted_string_originals = self._get_string_originals(
                    temp_tl_dir, block_originals=extracted_block_originals
                )
                new_originals = self._select_incremental_originals(
                    extracted_originals=new_extracted_string_originals,
                    existing_string_originals=all_current_string_originals,
                    block_originals=extracted_block_originals,
                    static_candidates=static_candidates,
                    tl_dir=temp_tl_dir,
                    menu_candidates=menu_candidates,
                    # 官方抽取未运行时无可信集合，传 None 走全量差集，
                    # 否则空集交集会把补充抽取结果全部丢弃。
                    trusted_originals=official_string_originals if allow_official else None,
                    compiled_candidates=compiled_candidates,
                )
                # 历史判定不译的候选不再重复提出。
                declined_candidates = load_declined_candidates(game_dir, tl_name)
                if declined_candidates:
                    new_originals -= declined_candidates
                extracted_block_fingerprints = self._collect_numbered_block_fingerprints(
                    temp_tl_dir
                )
                if static_added > 0 and not new_extracted_string_originals:
                    raise RuntimeError(
                        "增量抽取产物校验失败：静态条目已写入，但捕获快照中无法读取任何 strings"
                    )
                new_block_keys = {
                    key
                    for key, fingerprint in extracted_block_fingerprints.items()
                    if existing_block_fingerprints.get(key) != fingerprint
                }
                self.logger.info(
                    f"检测到 {len(new_originals)} 条新增 strings，"
                    f"{len(new_block_keys)} 个新增/变更编号翻译块"
                )
                result.new_strings = len(new_originals) + len(new_block_keys)

                pending_originals: Set[str] = set()
                if output_to_separate_folder and getattr(config, "renpy_incremental_include_untranslated", False):
                    # tl 已存在但没翻译过/只有占位（new==old/new==""）时，把这些也纳入待翻译包
                    pending_originals = self._get_untranslated_originals(tl_dir)
                    # Retry only placeholders that still exist in the current
                    # source. Older broad scans could leave image/resource tags.
                    pending_originals &= (
                        official_string_originals | set(static_candidates)
                    )
                    pending_originals = {
                        original
                        for original in pending_originals
                        if not ResponseChecker.is_structural_text(original)
                    }
                    # 对话块覆盖可以排除合成的对话占位，但显式 strings 占位
                    # （例如菜单选项）即使与其他对话同文，也仍需翻译。
                    pending_originals -= block_originals - all_current_string_originals
                    # 编号块译文不能覆盖全局 strings 占位；这里只排除已经有
                    # 有效 old/new 译文的字符串。
                    pending_originals -= translated_string_originals
                    pending_originals -= declined_candidates
                    self.logger.info(f"检测到 {len(pending_originals)} 条未翻译占位原文")

                selected_string_originals = set(new_originals) | set(pending_originals)
                
                if output_to_separate_folder:
                    # 8a. 将新增内容输出到单独文件夹
                    self._emit_progress("正在分离新增/待翻译内容...", 70)
                    if incremental_dir.exists():
                        shutil.rmtree(str(incremental_dir))
                    incremental_dir.mkdir(parents=True, exist_ok=True)
                    
                    self._extract_new_entries_to_folder(
                        temp_tl_dir,
                        incremental_dir,
                        selected_string_originals,
                        tl_name,
                        game_dir=game_dir,
                        selected_block_keys=new_block_keys,
                    )
                    
                    # 统计输出文件
                    result.total_files = len(list(self._iter_rpy_files(incremental_dir)))
                    
                    # 9. 对新增目录进行后处理
                    self._post_process(game_dir, tl_name, incremental_dir, config, None)

                    # Selection counts are only provisional: preserve/skip rules
                    # can remove every item from a generated file. Drop comment-
                    # only artifacts and report the tasks that actually remain.
                    self._remove_empty_incremental_artifacts(incremental_dir)
                    # 跨文件同 old 必须在进入翻译引擎前就去重，避免重复条目
                    # 被翻译两遍、合并后还需清理。
                    self._dedupe_string_translations(incremental_dir, tl_name)
                    self._remove_empty_incremental_artifacts(incremental_dir)
                    emitted_block_originals: Set[str] = set()
                    emitted_strings = self._get_string_originals(
                        incremental_dir,
                        block_originals=emitted_block_originals,
                    )
                    emitted_blocks = self._collect_numbered_block_fingerprints(
                        incremental_dir
                    )
                    result.new_strings = len(emitted_strings) + len(emitted_blocks)
                    result.total_files = len(list(self._iter_rpy_files(incremental_dir)))
                    
                    result.success = True
                    msg_lines = [
                        "增量抽取完成",
                        f"• 保留已有翻译: {translated_count} 条",
                        f"• 新增 strings: {len(new_originals)} 条",
                        f"• 新增/变更编号翻译块: {len(new_block_keys)} 个",
                    ]
                    if pending_originals:
                        msg_lines.append(f"• 未翻译待补全: {len(pending_originals)} 条")
                    if compiled_added:
                        msg_lines.append(f"• 编译字符串(标准 old/new): {compiled_added} 条")
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
                    self._replace_changed_numbered_blocks(
                        tl_dir,
                        temp_tl_dir,
                        new_block_keys,
                    )
                    self._merge_new_entries(
                        tl_dir,
                        temp_tl_dir,
                        new_originals,
                        existing_translations,
                        selected_block_keys=new_block_keys,
                    )
                    
                    # 9. 回填翻译
                    self._emit_progress("正在回填已有翻译...", 80)
                    self._merge_translations(tl_dir, existing_translations)
                    
                    # 10. 后处理
                    self._post_process(game_dir, tl_name, tl_dir, config, existing_translations)
                    # 按源行号整理编号块，strings 块保持文件最后。
                    try:
                        organized = self._sort_numbered_blocks_by_source_line(
                            game_dir, tl_dir
                        )
                        if organized:
                            self.logger.info(
                                f"已按源行号整理 {organized} 个文件的编号块顺序"
                            )
                    except Exception as exc:
                        self.logger.warning(f"整理编号块顺序失败: {exc}")
                    
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
                if not temp_backup_dir.exists():
                    # 备份已成功放回 tl，恢复日志不再需要。
                    self._clear_incremental_journal(game_dir, tl_name)
            
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
        # 若上次增量抽取被中断，先恢复 tl 再合并。
        self._recover_stale_incremental_state(game_dir, tl_name)
        # 目标 TL 目录优先沿用当前项目配置中的显式路径（例如项目根/tl），
        # 只有配置无法证明属于当前项目时才回退到标准 game/tl 布局。
        tl_dir = None
        try:
            configured_paths = RenpyProjectPaths.from_config(Config().load(), tl_name)
            if (
                configured_paths is not None
                and configured_paths.project_root == game_dir.resolve()
            ):
                tl_dir = configured_paths.tl_language_dir
        except Exception:
            tl_dir = None
        if tl_dir is None:
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

        self._emit_progress("正在分析已有翻译与增量内容...", 10)

        def decode_literal(quote: str, text: str) -> str:
            return self._decode_rpy_string(quote, text)

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
        merge_errors: List[str] = []

        # old/new 使用全局原文身份；编号块使用“相对路径 + label”身份。
        # 先走 AST 合并，确保仅含编号块的文件也会被处理。
        existing_strings_before = self._get_string_originals(tl_dir)
        translated_strings_before = self._get_existing_string_translations(tl_dir)
        existing_block_fingerprints = self._collect_numbered_block_fingerprints(tl_dir)
        existing_blocks_before = set(existing_block_fingerprints)
        incremental_strings = self._get_string_originals(incremental_dir)
        incremental_block_fingerprints = self._collect_numbered_block_fingerprints(
            incremental_dir
        )
        incremental_blocks = set(incremental_block_fingerprints)
        changed_existing_blocks = {
            key
            for key, fingerprint in incremental_block_fingerprints.items()
            if key in existing_block_fingerprints
            and existing_block_fingerprints[key] != fingerprint
        }
        self._emit_progress("正在合并新增翻译...", 30)
        self._replace_changed_numbered_blocks(
            tl_dir,
            incremental_dir,
            changed_existing_blocks,
        )
        try:
            self._merge_new_entries(
                tl_dir,
                incremental_dir,
                incremental_strings - existing_strings_before,
                {},
                selected_block_keys=incremental_blocks,
            )
        except _FilteredMergeWriteError as exc:
            merge_errors.append(str(exc))

        # 原文模板相同不代表译文已经应用。官方模板可能在增量翻译完成后
        # 被重新生成为空值/原文占位符；仅补全这些缺失槽位，保留已有有效人工译文。
        incremental_translations = self._get_existing_translations(incremental_dir)
        current_translations = self._get_existing_translations(tl_dir)
        numbered_translation_updates = {
            key: translated
            for key, translated in incremental_translations.blocks.items()
            if key not in current_translations.blocks
        }
        numbered_name_updates = {
            key: translated
            for key, translated in incremental_translations.block_names.items()
            if key not in current_translations.block_names
        }
        if numbered_translation_updates or numbered_name_updates:
            self._emit_progress("正在回填编号块译文...", 50)
            merge_errors.extend(
                self._merge_translations(
                    tl_dir,
                    ExistingTranslations(
                        strings={},
                        blocks=numbered_translation_updates,
                        block_names=numbered_name_updates,
                    ),
                )
            )
            updated_entries += len(
                set(numbered_translation_updates) | set(numbered_name_updates)
            )

        added_entries += len(incremental_strings - existing_strings_before)
        added_entries += len(incremental_blocks - existing_blocks_before)
        cross_file_placeholder_updates: Dict[str, str] = {}

        inc_rpy_files = list(self._iter_rpy_files(incremental_dir))
        total_inc_files = len(inc_rpy_files) or 1
        for file_index, rpy_file in enumerate(inc_rpy_files, 1):
            self._emit_progress(
                f"正在写入合并文件 {file_index}/{total_inc_files}...",
                55 + int(file_index * 20 / total_inc_files),
            )
            try:
                inc_lines = rpy_file.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception as exc:
                self.logger.warning(f"读取增量文件失败 {rpy_file}: {exc}")
                merge_errors.append(f"读取增量文件失败: {rpy_file}")
                continue

            inc_pairs = collect_pairs(inc_lines)
            if not inc_pairs:
                # 编号块已由上面的 AST 合并路径处理。
                continue

            rel_path = rpy_file.relative_to(incremental_dir)
            target_file = tl_dir / rel_path

            if not target_file.exists():
                # 新 strings/编号块已由前面的 AST 路径创建。目标仍不存在时，
                # 本文件只包含已在其他文件注册的全局 strings，不能整文件复制
                # 造成重复；只收集其中可用于补全全局占位的有效译文。
                for old_text, new_text, _comments in inc_pairs:
                    if (
                        old_text in existing_strings_before
                        and old_text not in translated_strings_before
                        and new_text
                        and new_text != old_text
                    ):
                        cross_file_placeholder_updates[old_text] = new_text
                continue

            try:
                target_lines = target_file.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception as exc:
                self.logger.warning(f"读取目标文件失败 {target_file}: {exc}")
                merge_errors.append(f"读取目标文件失败: {target_file}")
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
                if old_text in existing_strings_before:
                    if (
                        old_text not in translated_strings_before
                        and new_text
                        and new_text != old_text
                    ):
                        cross_file_placeholder_updates[old_text] = new_text
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
                try:
                    atomic_write_text(
                        target_file,
                        "\n".join(target_lines).rstrip() + "\n",
                        validator=lambda value: parse_tl_document(value.splitlines()),
                        allowed_roots=[tl_dir],
                    )
                    merged_files += 1
                except Exception as exc:
                    self.logger.warning(f"写入合并文件失败 {target_file}: {exc}")
                    merge_errors.append(f"写入合并文件失败: {target_file}")

        if cross_file_placeholder_updates:
            merge_errors.extend(
                self._merge_translations(tl_dir, cross_file_placeholder_updates)
            )
            translated_strings_after = self._get_existing_string_translations(tl_dir)
            for original, expected in cross_file_placeholder_updates.items():
                if translated_strings_after.get(original) != expected:
                    merge_errors.append(f"跨文件占位译文未写入: {original!r}")

        # 删除增量目录前验证所有作用域身份均已出现在目标目录。
        missing_strings = incremental_strings - self._get_string_originals(tl_dir)
        target_block_fingerprints = self._collect_numbered_block_fingerprints(tl_dir)
        missing_blocks = {
            key
            for key, fingerprint in incremental_block_fingerprints.items()
            if target_block_fingerprints.get(key) != fingerprint
        }
        applied_translations = self._get_existing_translations(tl_dir)
        unapplied_numbered_translations = {
            key
            for key, expected in numbered_translation_updates.items()
            if applied_translations.blocks.get(key) != expected
        }
        unapplied_numbered_names = {
            key
            for key, expected in numbered_name_updates.items()
            if applied_translations.block_names.get(key) != expected
        }
        if (
            missing_strings
            or missing_blocks
            or unapplied_numbered_translations
            or unapplied_numbered_names
            or merge_errors
        ):
            self._emit_progress("合并校验未通过，已保留增量目录", 100)
            details = list(merge_errors)
            if missing_strings:
                details.append(f"缺少 {len(missing_strings)} 条 strings")
            if missing_blocks:
                details.append(f"缺少 {len(missing_blocks)} 个编号块")
            if unapplied_numbered_translations:
                details.append(
                    f"有 {len(unapplied_numbered_translations)} 条编号块译文未写入"
                )
            if unapplied_numbered_names:
                details.append(
                    f"有 {len(unapplied_numbered_names)} 条编号块角色名译文未写入"
                )
            result.success = False
            result.message = "增量合并未完成，已保留增量目录：" + "；".join(details)
            return result
        merged_files = len(list(self._iter_rpy_files(incremental_dir)))

        if clean_duplicates:
            self._emit_progress("正在清理重复与空文件...", 80)
            config = Config().load()
            try:
                rx.remove_repeat_extracted_from_tl(
                    str(tl_dir),
                    is_py2=False,
                    duplicate_action=getattr(config, "renpy_duplicate_string_action", "comment"),
                )
            except Exception as exc:
                self.logger.warning(f"清理重复失败 {tl_dir}: {exc}")
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
            try:
                removed_empty = self._delete_empty_translation_files(tl_dir, tl_name)
                if removed_empty:
                    self.logger.info(f"已删除 {removed_empty} 个空翻译文件")
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

        # 合并完成后再次做跨文件 old 唯一性校验，杜绝 Ren'Py 重复翻译报错。
        self._emit_progress("正在校验跨文件唯一性...", 88)
        self._dedupe_string_translations(tl_dir, tl_name)

        # 记录本周期提出但未进入翻译输出的候选，后续增量不再重复提出。
        try:
            declined = self._collect_declined_candidates_from_cycle(
                game_dir, tl_name, incremental_dir
            )
            # 仅在合并完整成功时记录“判定不译”：合并出错/中断时的缺失条目
            # 可能只是没来得及写入，不能永久记成判定不译。
            if declined and not merge_errors:
                recorded = record_declined_candidates(game_dir, tl_name, declined)
                if recorded:
                    self.logger.info(
                        f"已记录 {recorded} 条判定不译的候选，后续增量不再重复提出"
                    )
        except Exception as exc:
            self.logger.warning(f"记录判定不译候选失败: {exc}")

        # 合并完成后按源行号整理编号块，strings 块保持文件最后。
        self._emit_progress("正在按行号整理编号块...", 93)
        try:
            organized = self._sort_numbered_blocks_by_source_line(game_dir, tl_dir)
            if organized:
                self.logger.info(
                    f"已按源行号整理 {organized} 个文件的编号块顺序"
                )
        except Exception as exc:
            self.logger.warning(f"整理编号块顺序失败: {exc}")

        # 合并与去重成功后，增量目录不再是可加载的翻译来源，
        # 避免遗留目录造成重复加载和困惑。若目录中带有翻译缓存，
        # 先保留 cache 子目录，交由一键流程把条目合并到主缓存；
        # 不能为了清理 rpy 文件而把刚完成的翻译缓存一起删除。
        cache_preserved = False
        try:
            cache_dir = incremental_dir / "cache"
            if cache_dir.is_dir():
                cache_preserved = True
                for child in list(incremental_dir.iterdir()):
                    if child == cache_dir:
                        continue
                    if child.is_dir():
                        shutil.rmtree(str(child), ignore_errors=True)
                    else:
                        child.unlink(missing_ok=True)
            else:
                shutil.rmtree(str(incremental_dir))
        except Exception as exc:
            self.logger.warning(f"合并完成但清理增量目录失败 {incremental_dir}: {exc}")

        self._emit_progress("合并完成", 100)
        result.success = True
        result.total_files = len(list(self._iter_rpy_files(tl_dir)))
        result.message = (
            f"合并完成：更新占位 {updated_entries} 条，"
            f"新增 {added_entries} 条，涉及 {merged_files} 个文件；"
            + (f"已保留 {incremental_dir.name}/cache 供缓存迁移" if cache_preserved
               else f"已清理 {incremental_dir.name}")
        )
        return result

    def _collect_declined_candidates_from_cycle(
        self,
        game_dir: Path,
        tl_name: str,
        incremental_dir: Path,
    ) -> Set[str]:
        """收集本周期提出但未进入翻译输出的 strings 候选。"""
        staging = game_dir / "game" / "tl" / f"{tl_name}_new"
        if staging.exists():
            proposed = set(self._get_string_originals(staging))
        else:
            proposed = set(self._get_string_originals(incremental_dir))
        if not proposed:
            return set()
        applied = set(self._get_string_originals(incremental_dir))
        return proposed - applied

    def _numbered_block_source_line(
        self,
        block,
        lines: List[str],
    ) -> Optional[int]:
        """读取块头之上 ``# game/<path>:<line>`` 注释中的源行号。

        仅信任翻译文件里已写好的行号注释，不做源码溯源；没有注释时返回
        None，由调用方按“无行号”处理。
        """
        for probe in range(block.header_line_no - 2, -1, -1):
            if not lines[probe].strip():
                continue
            match = _BLOCK_LOCATION_RE.match(lines[probe])
            if not match:
                break
            return int(match.group(2))
        return None

    def _sort_numbered_blocks_by_source_line(
        self,
        game_dir: Path,
        tl_dir: Path,
        rel_paths: Optional[Set[str]] = None,
    ) -> int:
        """按编号块对应源行号升序整理 TL 文件，strings 块保持在文件最后。

        只信任翻译文件里已有的 ``# game/<path>:<line>`` 位置注释，不做源码
        溯源；没有行号注释的块保持原相对顺序排到可排序块之后。返回被重排
        的文件数。
        """
        reordered = 0
        for tl_file in self._iter_rpy_files(tl_dir):
            rel = tl_file.relative_to(tl_dir).as_posix()
            if rel_paths is not None and rel not in rel_paths:
                continue
            try:
                lines = tl_file.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
                doc = parse_tl_document(lines)
            except Exception:
                continue

            segments: List[Dict[str, object]] = []
            for block in doc.blocks:
                kind = tl_block_kind_name(block.kind)
                header_idx = block.header_line_no - 1
                # 块结束位置只取实际翻译内容（TEMPLATE/TARGET）的最后一行。
                # 解析器会把下一块的位置注释/空行挂到当前块尾部，若整段复制
                # 会导致相邻块段重叠，重建时内容成倍膨胀。
                content_lines = [
                    stmt.line_no
                    for stmt in block.statements
                    if stmt.stmt_kind in (TlStmtKind.TEMPLATE, TlStmtKind.TARGET)
                ]
                end_idx = (
                    content_lines[-1]
                    if content_lines
                    else (
                        block.statements[-1].line_no
                        if block.statements
                        else block.header_line_no
                    )
                )
                end_idx = min(end_idx, len(lines))
                meta_start = header_idx
                if kind == "LABEL":
                    probe = header_idx - 1
                    while probe >= 0:
                        stripped = lines[probe].strip()
                        if not stripped:
                            probe -= 1
                            continue
                        if not _BLOCK_LOCATION_RE.match(lines[probe]):
                            break
                        meta_start = probe
                        probe -= 1
                segments.append(
                    {
                        "kind": kind,
                        "label": block.label,
                        "header_idx": header_idx,
                        "meta_start": meta_start,
                        "end_idx": end_idx,
                        "source_line": (
                            self._numbered_block_source_line(block, lines)
                            if kind == "LABEL"
                            else None
                        ),
                    }
                )
            if not segments:
                continue
            segments.sort(key=lambda seg: int(seg["header_idx"]))
            label_segments = [seg for seg in segments if seg["kind"] == "LABEL"]
            string_segments = [seg for seg in segments if seg["kind"] == "STRINGS"]
            non_string_segments = [
                seg for seg in segments if seg["kind"] != "STRINGS"
            ]
            needs_strings_move = (
                bool(string_segments)
                and bool(non_string_segments)
                and min(int(seg["header_idx"]) for seg in string_segments)
                < max(int(seg["header_idx"]) for seg in non_string_segments)
            )
            if len(label_segments) <= 1 and not needs_strings_move:
                continue

            def sort_key(seg):
                line = seg["source_line"]
                return (line if line is not None else float("inf"), int(seg["header_idx"]))

            ordered = sorted(label_segments, key=sort_key)
            already_ordered = all(
                ordered[index]["header_idx"] == label_segments[index]["header_idx"]
                for index in range(len(ordered))
            )
            if already_ordered and not needs_strings_move:
                continue

            output: List[str] = []
            prelude = lines[: segments[0]["meta_start"]]
            while prelude and not prelude[-1].strip():
                prelude.pop()
            output.extend(prelude)

            def append_segment(seg) -> None:
                if output and output[-1].strip() != "":
                    output.append("")
                has_meta = int(seg["meta_start"]) < int(seg["header_idx"])
                if seg["kind"] == "LABEL" and has_meta:
                    output.extend(
                        lines[int(seg["meta_start"]) : int(seg["header_idx"])]
                    )
                output.append(lines[int(seg["header_idx"])])
                output.append("")
                output.extend(lines[int(seg["header_idx"]) + 1 : int(seg["end_idx"])])

            others = [seg for seg in segments if seg["kind"] != "LABEL"]
            strings = [seg for seg in others if seg["kind"] == "STRINGS"]
            other_non_strings = [seg for seg in others if seg["kind"] != "STRINGS"]
            for seg in other_non_strings:
                append_segment(seg)
            for seg in ordered:
                append_segment(seg)
            for seg in strings:
                append_segment(seg)

            postlude = lines[int(segments[-1]["end_idx"]) :]
            output.extend(postlude)
            if output and output[-1].strip() != "":
                output.append("")
            try:
                # 重建时必须保留非 LABEL/STRINGS 块（例如 translate python），
                # 否则排序会静默丢掉这些内容。
                atomic_write_text(
                    tl_file,
                    "\n".join(output).rstrip() + "\n",
                    validator=lambda value: parse_tl_document(value.splitlines()),
                    allowed_roots=[tl_dir],
                )
                reordered += 1
            except Exception as exc:
                self.logger.warning(f"整理编号块顺序失败 {tl_file}: {exc}")
        return reordered

    def _remove_empty_incremental_artifacts(self, incremental_dir: Path) -> int:
        """Remove generated RPY files that contain no extractable TL items."""
        removed = 0
        extractor = RenpyTlItemExtractor()
        for rpy_file in list(incremental_dir.rglob("*.rpy")):
            try:
                text = rpy_file.read_text(encoding="utf-8", errors="replace")
                # ponytail: 被注释的重复条目是纯注释产物，但需保留作去重记录
                if rx.DUPLICATE_MARKER in text:
                    continue
                doc = parse_tl_document(text.splitlines())
                if extractor.extract(doc, str(rpy_file)):
                    continue
                rpy_file.unlink()
                removed += 1
            except Exception as exc:
                self.logger.warning(f"增量空产物检查失败 {rpy_file}: {exc}")

        for directory in sorted(
            (path for path in incremental_dir.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            try:
                directory.rmdir()
            except OSError:
                pass
        return removed

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
        menu_candidates: Optional[Set[str]] = None,
        trusted_originals: Optional[Set[str]] = None,
        compiled_candidates: Optional[Set[str]] = None,
    ) -> Set[str]:
        """选择真实增量任务，同时保留与对话同文的菜单 strings。"""
        if trusted_originals is None:
            selected = extracted_originals - existing_string_originals - block_originals
        else:
            selected = (
                extracted_originals & trusted_originals
            ) - existing_string_originals - block_originals
        # 随包 .pyc 常量不在官方抽取的 trusted 集合里，但可以用原生
        # translate strings old/new 表达，必须显式纳入增量任务。
        if compiled_candidates:
            selected |= compiled_candidates - existing_string_originals
        if menu_candidates is None:
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
                old_text = self._decode_rpy_string(
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
        *,
        candidates: Optional[Dict[str, str]] = None,
        menu_candidates: Optional[Set[str]] = None,
    ) -> int:
        """把静态漏抽文本写入其首次出现的标准翻译文件。"""
        if candidates is None:
            candidates = rx.collect_static_source_strings(game_dir)
        if menu_candidates is None:
            menu_candidates = set(rx.collect_static_menu_strings(game_dir))
        if not candidates:
            return 0

        # 只有全局 old/new 才能覆盖另一个全局字符串。编号翻译块即使原文
        # 相同，也不能阻止菜单或其他静态文本生成 strings 条目。
        existing = self._get_string_originals(tl_dir)
        declined = load_declined_candidates(game_dir, tl_name)
        added = 0
        for original, relative_path in candidates.items():
            if original in existing or original in declined:
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

    def _append_compiled_supplement_entries(
        self,
        game_dir: Path,
        tl_dir: Path,
        tl_name: str,
        *,
        candidates: Optional[Set[str]] = None,
    ) -> int:
        """把随包 .pyc 中玩家可见的常量写成标准 translate strings old/new。

        这些字符串可以用原生 old/new 表达，应该在一键翻译时写入标准 TL，
        而不是留给 replace_text 补全钩子。写入前会按 old 值去重，避免与
        现有翻译条目冲突。
        """
        if candidates is None:
            try:
                from module.Extract.ReplaceGenerator import (
                    collect_compiled_candidate_texts,
                )

                candidates = set(
                    collect_compiled_candidate_texts(
                        game_dir,
                        tl_name=tl_name,
                    )
                )
            except Exception as exc:
                self.logger.warning(f"编译字符串收集失败: {exc}")
                return 0
        if not candidates:
            return 0
        try:
            from module.Extract.ReplaceGenerator import (
                _separate_acronym_candidates,
                record_declined_candidates,
            )

            preserved_acronyms = _separate_acronym_candidates(candidates)
            if preserved_acronyms:
                try:
                    record_declined_candidates(game_dir, tl_name, preserved_acronyms)
                except Exception:
                    pass
                candidates = candidates - preserved_acronyms
        except Exception as exc:
            self.logger.warning(f"编译字符串缩写分离失败: {exc}")
        if not candidates:
            return 0

        declined = load_declined_candidates(game_dir, tl_name)
        if declined:
            candidates = candidates - declined

        existing = self._get_string_originals(tl_dir)
        target_file = tl_dir / "renpybox_bytecode_strings.rpy"
        header_re = re.compile(
            rf"^\s*translate\s+{re.escape(tl_name)}\s+strings\s*:\s*$"
        )

        if target_file.exists():
            lines = target_file.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines()
        else:
            lines = [
                "# 一键翻译 - 编译字符串（源自随包 .pyc 常量，标准 translate strings）",
                f"# 语言: {tl_name}",
                "",
            ]

        new_entries: List[str] = []
        added = 0
        for original in sorted(candidates, key=lambda value: (-len(value), value)):
            if original in existing:
                continue
            escaped = self._escape_rpy_string(original)
            new_entries.extend([f'    old "{escaped}"', f'    new "{escaped}"', ""])
            existing.add(original)
            added += 1

        if not added:
            return 0

        header_indexes = [
            index for index, line in enumerate(lines) if header_re.match(line)
        ]
        if header_indexes:
            header_index = header_indexes[-1]
            insert_at = len(lines)
            for index in range(header_index + 1, len(lines)):
                if re.match(r"^\s*translate\s+", lines[index]):
                    insert_at = index
                    break
            while insert_at > header_index + 1 and not lines[insert_at - 1].strip():
                insert_at -= 1
            lines[insert_at:insert_at] = [""] + new_entries
        else:
            if lines and lines[-1].strip():
                lines.append("")
            lines.extend([f"translate {tl_name} strings:", ""])
            lines.extend(new_entries)

        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        self.logger.info(f"编译补充抽取：已添加 {added} 条标准 old/new 翻译条目")
        return added

    def _dedupe_string_translations(self, tl_dir: Path, tl_name: str) -> int:
        """跨文件校验 translate strings 的 old 唯一性，移除重复条目。

        Ren'Py 按语言把字符串翻译注册到同一个字典，任何重复 old（包括
        miss/ 工作文件）都会在游戏启动时报错，因此写入/合并后必须校验。
        """
        try:
            from module.Extract.ReplaceGenerator import dedupe_string_translations

            removed = dedupe_string_translations(tl_dir, tl_name)
            if removed:
                self.logger.info(f"字符串唯一性校验：已移除 {removed} 条重复 old")
            return removed
        except Exception as exc:
            self.logger.warning(f"字符串唯一性校验失败: {exc}")
            return 0

    @staticmethod
    def _find_source_text_line(source_file: Path, original: str) -> Optional[int]:
        try:
            lines = source_file.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            return None
        for line_no, line in enumerate(lines, 1):
            if any(literal.value == original for literal in scan_quoted_literals(line)):
                return line_no
        # 跨行相邻字符串字面量（Python 隐式拼接）书写的长文本，单行匹配不到；
        # 用合并后的逻辑行定位其起始行。
        try:
            from module.Renpy.renpy_extract import merge_string_literal_continuations

            merged = merge_string_literal_continuations(lines)
        except Exception:
            merged = []
        for merged_line, start_index in merged:
            if any(
                literal.value == original
                for literal in scan_quoted_literals(merged_line)
            ):
                return start_index + 1
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
                    old_text = self._decode_rpy_string(match.group(1), match.group("text"))
                    originals.add(old_text)
            except Exception:
                continue
        return originals

    def _get_string_originals(
        self,
        tl_dir: Path,
        *,
        block_originals: Optional[Set[str]] = None,
    ) -> Set[str]:
        """收集 strings 原文，并可在同一次 AST 扫描中收集编号块原文。"""
        cache_key = None
        if block_originals is None:
            try:
                cache_key = (str(tl_dir.resolve()), tl_dir_signature(tl_dir))
                cached = _STRING_ORIGINALS_CACHE.get(cache_key)
                if cached is not None:
                    return set(cached)
            except Exception:
                pass

        originals: Set[str] = set()
        if not tl_dir.exists():
            return originals

        extractor = RenpyTlItemExtractor()
        for rpy_file in self._iter_rpy_files(tl_dir):
            try:
                content = rpy_file.read_text(encoding="utf-8", errors="replace")
                doc = parse_tl_document(content.splitlines())
                items = extractor.extract(doc, str(rpy_file))
                for item in items:
                    extra = item.get_extra_field()
                    renpy = extra.get("renpy", {}) if isinstance(extra, dict) else {}
                    block = renpy.get("block", {}) if isinstance(renpy, dict) else {}
                    kind = tl_block_kind_name(block.get("kind"))
                    if kind == "STRINGS":
                        originals.add(item.get_src())
                    elif kind == "LABEL" and block_originals is not None:
                        block_originals.add(item.get_src())
                continue
            except Exception as exc:
                self.logger.warning(
                    f"AST strings 原文扫描失败，回退 old/new 扫描 {rpy_file}: {exc}"
                )

            # AST 失败时 old/new 是唯一可以安全识别为全局 strings 的形式。
            try:
                content = rpy_file.read_text(encoding="utf-8", errors="replace")
                for match in self.OLD_LINE_RE.finditer(content):
                    originals.add(
                        self._decode_rpy_string(match.group(1), match.group("text"))
                    )
            except Exception as exc:
                self.logger.warning(f"strings 原文回退扫描失败 {rpy_file}: {exc}")
            if block_originals is not None:
                block_originals.update(self._get_file_block_originals(rpy_file))

        if block_originals is None and cache_key is not None:
            try:
                _STRING_ORIGINALS_CACHE[cache_key] = frozenset(originals)
            except Exception:
                pass
        return originals

    def _get_translated_string_originals(self, tl_dir: Path) -> Set[str]:
        """收集已有有效译文的全局 strings 原文，不包含编号翻译块。"""
        return set(self._get_existing_string_translations(tl_dir))

    def _get_existing_string_translations(self, tl_dir: Path) -> Dict[str, str]:
        """获取有效的全局 old/new 译文，不包含编号翻译块。"""
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
                    extra = item.get_extra_field()
                    renpy = extra.get("renpy", {}) if isinstance(extra, dict) else {}
                    block = renpy.get("block", {}) if isinstance(renpy, dict) else {}
                    if (
                        tl_block_kind_name(block.get("kind")) == "STRINGS"
                        and item.get_dst()
                        and item.get_dst() != item.get_src()
                    ):
                        translations[item.get_src()] = item.get_dst()
                continue
            except Exception as exc:
                self.logger.warning(f"AST strings 译文扫描失败，回退 old/new 扫描 {rpy_file}: {exc}")

            try:
                lines = rpy_file.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception as exc:
                self.logger.warning(f"strings 译文回退扫描失败 {rpy_file}: {exc}")
                continue

            i = 0
            while i < len(lines):
                old_match = self.OLD_LINE_RE.match(lines[i])
                if not old_match:
                    i += 1
                    continue
                old_text = self._decode_rpy_string(old_match.group(1), old_match.group("text"))
                j = i + 1
                while j < len(lines) and (
                    not lines[j].strip() or lines[j].lstrip().startswith("#")
                ):
                    j += 1
                new_match = self.NEW_LINE_RE.match(lines[j]) if j < len(lines) else None
                if new_match:
                    new_text = self._decode_rpy_string(
                        new_match.group(1), new_match.group("text")
                    )
                    if new_text and new_text != old_text:
                        translations[old_text] = new_text
                    i = j + 1
                    continue
                i += 1
        return translations

    def _collect_numbered_block_keys(self, tl_dir: Path) -> Set[Tuple[str, str]]:
        """收集编号翻译块身份：``(相对文件路径, translate 标签)``。"""
        return set(self._collect_numbered_block_fingerprints(tl_dir))

    def _collect_numbered_block_fingerprints(
        self, tl_dir: Path
    ) -> Dict[Tuple[str, str], Tuple[str, ...]]:
        """收集编号块模板指纹；译文变化不影响指纹，原文变化会改变。"""
        try:
            cache_key = (str(tl_dir.resolve()), tl_dir_signature(tl_dir))
            cached = _NUMBERED_FINGERPRINTS_CACHE.get(cache_key)
            if cached is not None:
                return dict(cached)
        except Exception:
            cache_key = None

        fingerprints: Dict[Tuple[str, str], Tuple[str, ...]] = {}
        if not tl_dir.exists():
            return fingerprints

        extractor = RenpyTlItemExtractor()
        for rpy_file in self._iter_rpy_files(tl_dir):
            try:
                rel_path = rpy_file.relative_to(tl_dir).as_posix()
                content = rpy_file.read_text(encoding="utf-8", errors="replace")
                doc = parse_tl_document(content.splitlines())
                digests_by_label: Dict[str, List[Tuple[int, str]]] = {}
                for item in extractor.extract(doc, str(rpy_file)):
                    extra = item.get_extra_field()
                    renpy = extra.get("renpy", {}) if isinstance(extra, dict) else {}
                    block_data = renpy.get("block", {}) if isinstance(renpy, dict) else {}
                    digest_data = renpy.get("digest", {}) if isinstance(renpy, dict) else {}
                    pair_data = renpy.get("pair", {}) if isinstance(renpy, dict) else {}
                    if tl_block_kind_name(block_data.get("kind")) != "LABEL":
                        continue
                    label = str(block_data.get("label", ""))
                    template_digest = digest_data.get("template_raw_sha1")
                    template_line = pair_data.get("template_line", 0)
                    if label and isinstance(template_digest, str) and template_digest:
                        digests_by_label.setdefault(label, []).append(
                            (
                                int(template_line) if isinstance(template_line, int) else 0,
                                template_digest,
                            )
                        )
                for block in doc.blocks:
                    if tl_block_kind_name(block.kind) == "LABEL":
                        ordered = sorted(digests_by_label.get(block.label, []))
                        fingerprints[(rel_path, block.label)] = tuple(
                            digest for _line, digest in ordered
                        )
            except Exception as exc:
                self.logger.warning(f"编号翻译块身份扫描失败 {rpy_file}: {exc}")
                continue
        if cache_key is not None:
            try:
                _NUMBERED_FINGERPRINTS_CACHE[cache_key] = dict(fingerprints)
            except Exception:
                pass
        return fingerprints

    def _replace_changed_numbered_blocks(
        self,
        target_dir: Path,
        source_dir: Path,
        changed_keys: Set[Tuple[str, str]],
    ) -> int:
        """用增量块替换同标签旧块，未变语句沿用旧译文。

        旧块与增量块按语句模板摘要（template_raw_sha1）逐句对齐：摘要相同的
        语句保留旧译文，新增语句保持占位待译，被删除语句不再保留。避免“任
        一行原文变化就整块重译”导致未变行的译文丢失。
        """
        if not changed_keys:
            return 0
        replaced = 0
        keys_by_file: Dict[str, Set[str]] = {}
        for rel_path, label in changed_keys:
            keys_by_file.setdefault(rel_path, set()).add(label)

        extractor = RenpyTlItemExtractor()
        for rel_path, labels in keys_by_file.items():
            source_file = source_dir / Path(rel_path)
            target_file = target_dir / Path(rel_path)
            if not source_file.is_file() or not target_file.is_file():
                continue
            try:
                source_lines = source_file.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
                target_lines = target_file.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
                source_doc = parse_tl_document(source_lines)
                target_doc = parse_tl_document(target_lines)
                source_blocks = {
                    block.label: block
                    for block in source_doc.blocks
                    if tl_block_kind_name(block.kind) == "LABEL" and block.label in labels
                }
                operations: List[Tuple[int, int, List[str]]] = []
                for block in target_doc.blocks:
                    if tl_block_kind_name(block.kind) != "LABEL" or block.label not in source_blocks:
                        continue
                    source_block = source_blocks[block.label]
                    source_end = (
                        source_block.statements[-1].line_no
                        if source_block.statements
                        else source_block.header_line_no
                    )
                    target_end = (
                        block.statements[-1].line_no
                        if block.statements
                        else block.header_line_no
                    )
                    merged = source_lines[
                        source_block.header_line_no - 1:source_end
                    ]
                    # 旧块按语句摘要收集“已翻译的目标行”，重复语句按顺序取用。
                    old_lines_by_digest: Dict[str, List[str]] = {}
                    for item in extractor.extract(target_doc, str(target_file)):
                        extra_raw = item.get_extra_field()
                        extra = extra_raw if isinstance(extra_raw, dict) else {}
                        renpy = extra.get("renpy", {}) if isinstance(extra.get("renpy"), dict) else {}
                        block_data = renpy.get("block", {}) if isinstance(renpy.get("block"), dict) else {}
                        pair_data = renpy.get("pair", {}) if isinstance(renpy.get("pair"), dict) else {}
                        digest_data = renpy.get("digest", {}) if isinstance(renpy.get("digest"), dict) else {}
                        if block_data.get("header_line") != block.header_line_no:
                            continue
                        digest = digest_data.get("template_raw_sha1")
                        target_line = pair_data.get("target_line")
                        src = item.get_src()
                        dst = item.get_dst()
                        name_src = item.get_name_src()
                        name_dst = item.get_name_dst()
                        if not (
                            isinstance(digest, str)
                            and digest
                            and isinstance(target_line, int)
                        ):
                            continue
                        translated = (
                            (isinstance(dst, str) and dst and dst != src)
                            or (
                                isinstance(name_dst, str)
                                and name_dst
                                and name_dst != name_src
                            )
                        )
                        if (
                            translated
                            and 1 <= target_line <= len(target_lines)
                        ):
                            old_lines_by_digest.setdefault(digest, []).append(
                                target_lines[target_line - 1]
                            )

                    # 增量块逐语句对齐：摘要相同则用旧译文行替换占位行。
                    for item in extractor.extract(source_doc, str(source_file)):
                        extra_raw = item.get_extra_field()
                        extra = extra_raw if isinstance(extra_raw, dict) else {}
                        renpy = extra.get("renpy", {}) if isinstance(extra.get("renpy"), dict) else {}
                        block_data = renpy.get("block", {}) if isinstance(renpy.get("block"), dict) else {}
                        pair_data = renpy.get("pair", {}) if isinstance(renpy.get("pair"), dict) else {}
                        digest_data = renpy.get("digest", {}) if isinstance(renpy.get("digest"), dict) else {}
                        if block_data.get("header_line") != source_block.header_line_no:
                            continue
                        digest = digest_data.get("template_raw_sha1")
                        target_line = pair_data.get("target_line")
                        if not (
                            isinstance(digest, str)
                            and digest
                            and isinstance(target_line, int)
                        ):
                            continue
                        carried = old_lines_by_digest.get(digest)
                        if not carried:
                            continue
                        local_index = target_line - source_block.header_line_no
                        if 0 <= local_index < len(merged):
                            merged[local_index] = carried.pop(0)

                    operations.append(
                        (block.header_line_no - 1, target_end, merged)
                    )

                for start, end, replacement in sorted(
                    operations, key=lambda value: value[0], reverse=True
                ):
                    target_lines[start:end] = replacement
                if operations:
                    atomic_write_text(
                        target_file,
                        "\n".join(target_lines).rstrip() + "\n",
                        validator=lambda value: parse_tl_document(value.splitlines()),
                        allowed_roots=[target_dir],
                    )
                    replaced += len(operations)
            except Exception as exc:
                raise RuntimeError(
                    f"替换已变更编号块失败 {source_file}: {exc}"
                ) from exc
        return replaced

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
            except Exception as exc:
                self.logger.warning(f"AST 未翻译条目扫描失败，回退 old/new 扫描 {rpy_file}: {exc}")

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
            # 块头之上的 # game/<path>:<line> 位置注释随块一起输出
            # （容忍注释与块头之间的空行）。
            location_lines: List[str] = []
            probe = header_line - 2
            while probe >= 0:
                stripped = lines[probe].strip()
                if not stripped:
                    probe -= 1
                    continue
                if _BLOCK_LOCATION_RE.match(lines[probe]):
                    location_lines.insert(0, lines[probe])
                    probe -= 1
                    continue
                break
            selections.append(
                {
                    "header_line_no": header_line,
                    "header_line": header_text,
                    "lang": block.lang,
                    "label": block.label,
                    "kind": tl_block_kind_name(block.kind),
                    "lines": selected_lines,
                    "location": location_lines,
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
        selected_block_keys: Optional[Set[Tuple[str, str]]] = None,
    ):
        """将指定条目（新增/未翻译）提取到目标文件夹"""
        selected_block_keys = selected_block_keys or set()
        if not selected_originals and not selected_block_keys:
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

                rel_path = rpy_file.relative_to(source_dir).as_posix()
                selected_items = []
                for item in items:
                    extra = item.get_extra_field()
                    renpy = extra.get("renpy", {}) if isinstance(extra, dict) else {}
                    block = renpy.get("block", {}) if isinstance(renpy, dict) else {}
                    kind = tl_block_kind_name(block.get("kind"))
                    if (
                        kind == "STRINGS"
                        and item.get_src() in selected_originals
                        and item.get_src() not in selected_menu_strings
                    ):
                        selected_items.append(item)
                    elif kind == "LABEL" and (rel_path, str(block.get("label", ""))) in selected_block_keys:
                        selected_items.append(item)
                if not selected_items:
                    continue

                selections = self._collect_selected_blocks_from_ast(
                    doc, lines, selected_items, tl_name
                )
                if not selections:
                    continue

                target_file = target_dir / Path(rel_path)
                target_file.parent.mkdir(parents=True, exist_ok=True)

                output_lines = [
                    "# 增量抽取 - 新增/待翻译内容",
                    f"# 来源: {rpy_file.name}",
                    "",
                ]

                # 编号翻译块始终排在 old/new strings 块之前；
                # ``translate <lang> strings:`` 保持在文件最后。
                for sel in sorted(
                    selections,
                    key=lambda sel: 0 if sel["kind"] == "LABEL" else 1,
                ):
                    output_lines.extend(sel.get("location") or [])
                    output_lines.append(sel["header_line"])
                    # header 与条目之间不留空行：duplicate marker 记录的行号
                    # 依赖紧凑布局（issue22 测试断言 first at a_first.rpy:5）。
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

                        j = i + 1
                        while j < len(lines) and (
                            not lines[j].strip() or lines[j].lstrip().startswith("#")
                        ):
                            j += 1
                        if j < len(lines):
                            new_line = lines[j]
                            new_match = self.NEW_LINE_RE.match(new_line)
                            if new_match:
                                new_text = new_match.group("text")

                        # 只提取被选中的原文
                        if (
                            old_text in selected_originals
                            and old_text not in selected_menu_strings
                        ):
                            new_entries.append((old_text, new_text))

                        i = j + 1 if j > i else i + 1
                        continue
                    i += 1

                # 写入目标文件
                if new_entries:
                    rel_path = rpy_file.relative_to(source_dir)
                    target_file = target_dir / rel_path
                    target_file.parent.mkdir(parents=True, exist_ok=True)

                    output_lines = [
                        "# 增量抽取 - 新增/待翻译内容",
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
        existing_translations: ExistingTranslations | Dict[str, str],
        selected_block_keys: Optional[Set[Tuple[str, str]]] = None,
    ):
        """将新增条目合并到原 tl 目录（旧行为）"""
        selected_block_keys = selected_block_keys or set()
        if not new_originals and not selected_block_keys:
            return

        extractor = RenpyTlItemExtractor()

        for rpy_file in self._iter_rpy_files(source_dir):
            rel_path = rpy_file.relative_to(source_dir)
            rel_key = rel_path.as_posix()
            target_file = tl_dir / rel_path

            # AST 优先
            try:
                content = rpy_file.read_text(encoding="utf-8", errors="replace")
                lines = content.splitlines()
                doc = parse_tl_document(lines)
                items = extractor.extract(doc, str(rpy_file))
                if not items:
                    continue

                selected_items = []
                for item in items:
                    extra = item.get_extra_field()
                    renpy = extra.get("renpy", {}) if isinstance(extra, dict) else {}
                    block = renpy.get("block", {}) if isinstance(renpy, dict) else {}
                    kind = tl_block_kind_name(block.get("kind"))
                    if (
                        kind == "STRINGS"
                        and item.get_src() in new_originals
                    ):
                        selected_items.append(item)
                    elif kind == "LABEL" and (rel_key, str(block.get("label", ""))) in selected_block_keys:
                        selected_items.append(item)
                if not selected_items:
                    continue

                if not target_file.exists():
                    selections = self._collect_selected_blocks_from_ast(
                        doc, lines, selected_items
                    )
                    if not selections:
                        continue

                    output_lines: List[str] = []
                    # 编号翻译块始终排在 old/new strings 块之前；
                    # ``translate <lang> strings:`` 保持在文件最后。
                    selections_sorted = sorted(
                        selections,
                        key=lambda sel: 0 if sel["kind"] == "LABEL" else 1,
                    )
                    for selection in selections_sorted:
                        if output_lines and output_lines[-1].strip() != "":
                            output_lines.append("")
                        output_lines.extend(selection.get("location") or [])
                        output_lines.append(selection["header_line"])
                        if output_lines and output_lines[-1].strip() != "":
                            output_lines.append("")
                        output_lines.extend(selection["lines"])

                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        atomic_write_text(
                            target_file,
                            "\n".join(output_lines).rstrip() + "\n",
                            validator=lambda value: parse_tl_document(value.splitlines()),
                            allowed_roots=[tl_dir],
                        )
                    except Exception as exc:
                        raise _FilteredMergeWriteError(
                            f"写入筛选后的新增翻译失败 {target_file}: {exc}"
                        ) from exc
                    continue

                target_content = target_file.read_text(encoding="utf-8", errors="replace")
                target_lines = target_content.splitlines()
                target_doc = parse_tl_document(target_lines)
                target_items = extractor.extract(target_doc, str(target_file))
                target_string_originals: Set[str] = set()
                for item in target_items:
                    extra = item.get_extra_field()
                    renpy = extra.get("renpy", {}) if isinstance(extra, dict) else {}
                    block = renpy.get("block", {}) if isinstance(renpy, dict) else {}
                    if tl_block_kind_name(block.get("kind")) == "STRINGS":
                        target_string_originals.add(item.get_src())
                target_block_labels = {
                    block.label
                    for block in target_doc.blocks
                    if tl_block_kind_name(block.kind) == "LABEL"
                }

                filtered_items = []
                for item in selected_items:
                    extra = item.get_extra_field()
                    renpy = extra.get("renpy", {}) if isinstance(extra, dict) else {}
                    block = renpy.get("block", {}) if isinstance(renpy, dict) else {}
                    kind = tl_block_kind_name(block.get("kind"))
                    if (
                        kind == "STRINGS"
                        and item.get_src() not in target_string_originals
                    ):
                        filtered_items.append(item)
                    elif kind == "LABEL" and str(block.get("label", "")) not in target_block_labels:
                        filtered_items.append(item)
                if not filtered_items:
                    continue

                selections = self._collect_selected_blocks_from_ast(doc, lines, filtered_items)
                if not selections:
                    continue

                block_map = {}
                for block in target_doc.blocks:
                    key = (block.lang, block.label, tl_block_kind_name(block.kind))
                    block_map[key] = block

                combined: Dict[Tuple[str, str, str], Dict[str, List[str]]] = {}
                for sel in sorted(selections, key=lambda x: x["header_line_no"]):
                    key = (sel["lang"], sel["label"], sel["kind"])
                    entry = combined.get(key)
                    if entry is None:
                        entry = {
                            "header": sel["header_line"],
                            "lines": [],
                            "location": [],
                        }
                        combined[key] = entry
                    entry["lines"].extend(sel["lines"])
                    entry["location"].extend(sel.get("location") or [])

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
                        append_lines.extend(entry.get("location") or [])
                        append_lines.append(header)
                        append_lines.extend(lines_to_insert)

                for index, insert_lines in sorted(insert_ops, key=lambda x: x[0], reverse=True):
                    if index < 0:
                        continue
                    if index > len(target_lines):
                        index = len(target_lines)
                    target_lines[index:index] = insert_lines

                if append_lines:
                    # 新编号块插到 strings 块之前，strings 块始终位于文件末尾。
                    strings_header = next(
                        (
                            block.header_line_no
                            for block in target_doc.blocks
                            if tl_block_kind_name(block.kind) == "STRINGS"
                        ),
                        None,
                    )
                    if strings_header is not None:
                        index = max(0, strings_header - 1)
                        if index > len(target_lines):
                            index = len(target_lines)
                        if index > 0 and target_lines[index - 1].strip() != "":
                            append_lines.insert(0, "")
                        target_lines[index:index] = append_lines
                    else:
                        if target_lines and target_lines[-1].strip() != "":
                            target_lines.append("")
                        target_lines.extend(append_lines)

                if insert_ops or append_lines:
                    atomic_write_text(
                        target_file,
                        "\n".join(target_lines),
                        validator=lambda value: parse_tl_document(value.splitlines()),
                        allowed_roots=[tl_dir],
                    )
                continue
            except _FilteredMergeWriteError:
                # 目标文件不存在时，旧回退会复制整个混合源文件并重新引入
                # 已筛除条目。把失败交给上层处理，绝不执行整文件复制。
                raise
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
                    if tl_block_kind_name(block.get("kind")) == "LABEL":
                        block_originals.add(item.get_src())
                continue
            except Exception as exc:
                self.logger.warning(f"AST 编号块原文扫描失败，回退注释扫描 {rpy_file}: {exc}")

            try:
                lines = rpy_file.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception as exc:
                self.logger.warning(f"编号块注释回退扫描失败 {rpy_file}: {exc}")
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

    def _backup_tl_dir(self, game_dir: Path, tl_name: str) -> Optional[Path]:
        """将现有 tl 目录移动到唯一备份；失败时阻断后续覆盖。"""
        tl_dir = game_dir / "game" / "tl" / tl_name
        if not tl_dir.exists():
            return None

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_path = game_dir / f"tl_backup_{tl_name}_{timestamp}"
        suffix = 1
        while backup_path.exists():
            backup_path = game_dir / f"tl_backup_{tl_name}_{timestamp}_{suffix}"
            suffix += 1
        try:
            shutil.move(str(tl_dir), str(backup_path))
        except Exception as exc:
            raise RuntimeError(f"备份旧翻译失败，已停止抽取: {exc}") from exc
        self._emit_progress("已备份旧翻译", 5)
        return backup_path

    def _incremental_journal_path(self, game_dir: Path, tl_name: str) -> Path:
        return game_dir / f".renpybox_incremental_{tl_name}.json"

    def _write_incremental_journal(
        self,
        game_dir: Path,
        tl_name: str,
        temp_extract_dir: Path,
        tl_dir: Path,
    ) -> None:
        """在移动 tl 前写入恢复日志，崩溃后下一次运行可自动恢复。"""
        try:
            payload = {
                "tl_name": tl_name,
                "temp_dir": str(temp_extract_dir),
                "tl_dir": str(tl_dir),
                "backup_dir": str(temp_extract_dir / "_tl_backup"),
            }
            self._incremental_journal_path(game_dir, tl_name).write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            self.logger.warning(f"写入增量恢复日志失败: {exc}")

    def _clear_incremental_journal(self, game_dir: Path, tl_name: str) -> None:
        try:
            self._incremental_journal_path(game_dir, tl_name).unlink(missing_ok=True)
        except Exception:
            pass

    def _recover_stale_incremental_state(
        self, game_dir: Path, tl_name: str
    ) -> Optional[Path]:
        """恢复上次被中断的增量抽取：把备份 tl 放回原位并清理临时目录。"""
        game_dir = Path(game_dir)
        journal = self._incremental_journal_path(game_dir, tl_name)

        if journal.exists():
            try:
                payload = json.loads(journal.read_text(encoding="utf-8"))
                backup_dir = Path(payload.get("backup_dir", ""))
                tl_dir = Path(payload.get("tl_dir", ""))
                temp_dir = Path(payload.get("temp_dir", ""))
            except Exception as exc:
                self.logger.warning(f"增量恢复日志损坏，已忽略: {exc}")
                self._clear_incremental_journal(game_dir, tl_name)
                return None

            if not backup_dir.is_dir():
                self._clear_incremental_journal(game_dir, tl_name)
                return None
            try:
                if tl_dir.exists():
                    shutil.rmtree(str(tl_dir), ignore_errors=True)
                shutil.move(str(backup_dir), str(tl_dir))
            except Exception as exc:
                self.logger.error(f"恢复中断的增量备份失败: {exc}")
                return None
            self._clear_incremental_journal(game_dir, tl_name)
            try:
                if temp_dir.exists():
                    shutil.rmtree(str(temp_dir), ignore_errors=True)
            except Exception:
                pass
            self.logger.info(f"已恢复中断的增量抽取备份到 {tl_dir}")
            return tl_dir

        # 无日志的遗留临时目录只清理，不触碰现有 tl（可能是正常结束但清理失败）。
        for temp_dir in sorted(game_dir.glob(f"_temp_extract_{tl_name}_*")):
            try:
                shutil.rmtree(str(temp_dir), ignore_errors=True)
            except Exception:
                pass
        return None

    def _post_process(
        self,
        project_root: Path,
        tl_name: str,
        tl_dir: Path,
        config: Config,
        existing_translations: Optional[ExistingTranslations | Dict[str, str]] = None,
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
            rx.remove_repeat_extracted_from_tl(
                str(tl_dir),
                is_py2=False,
                duplicate_action=getattr(config, "renpy_duplicate_string_action", "comment"),
            )
        except Exception as exc:
            self.logger.warning(f"去重失败 {tl_dir}: {exc}")

        removed_source = self._remove_source_registered_string_duplicates(
            project_root, tl_dir, tl_name
        )
        if removed_source:
            self.logger.info(f"已清理与游戏源码翻译重复的 strings 条目 {removed_source} 条")

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

        # 删除空文件（含只剩 translate 头的文件），并清理过期 .rpyc
        self._emit_progress("正在清理空文件...", 90)
        removed_empty = self._delete_empty_translation_files(tl_dir, tl_name)
        if removed_empty:
            self.logger.info(f"已删除 {removed_empty} 个空翻译文件")

        # 终极结构导出
        if getattr(config, "extract_export_excel", False):
            # MaExtractor 生成的是全局 old/new/replace 结构，只能用 strings
            # 译文排除重复；编号块译文属于独立语句，不能参与全局过滤。
            existing_translations = self._get_existing_string_translations(tl_dir)
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

    @staticmethod
    def _numbered_item_translation_key(
        rel_path: str, item
    ) -> Optional[Tuple[str, str, str, str, int]]:
        extra_raw = item.get_extra_field()
        extra = extra_raw if isinstance(extra_raw, dict) else {}
        renpy = extra.get("renpy", {}) if isinstance(extra.get("renpy"), dict) else {}
        block = renpy.get("block", {}) if isinstance(renpy.get("block"), dict) else {}
        digest = renpy.get("digest", {}) if isinstance(renpy.get("digest"), dict) else {}
        pair = renpy.get("pair", {}) if isinstance(renpy.get("pair"), dict) else {}
        if tl_block_kind_name(block.get("kind")) != "LABEL":
            return None
        lang = block.get("lang")
        label = block.get("label")
        template_digest = digest.get("template_raw_sha1")
        header_line = block.get("header_line")
        template_line = pair.get("template_line")
        ordinal = pair.get("statement_ordinal")
        if not all(isinstance(value, str) and value for value in (lang, label, template_digest)):
            return None
        if not isinstance(header_line, int) or not isinstance(template_line, int):
            return None
        # 新元数据携带布局无关的语句序号；旧缓存回退到原始行偏移。
        if not isinstance(ordinal, int):
            ordinal = template_line - header_line
        return (rel_path, lang, label, template_digest, ordinal)

    def _get_existing_translations(self, tl_dir: Path) -> ExistingTranslations:
        """按 strings 与编号块的真实作用域分别收集有效译文。"""
        try:
            cache_key = (str(tl_dir.resolve()), tl_dir_signature(tl_dir))
            cached = _EXISTING_TRANSLATIONS_CACHE.get(cache_key)
            if cached is not None:
                cached_strings, cached_blocks, cached_names = cached
                return ExistingTranslations(
                    strings=dict(cached_strings),
                    blocks=dict(cached_blocks),
                    block_names=dict(cached_names),
                )
        except Exception:
            cache_key = None

        translations = ExistingTranslations(strings={}, blocks={})
        if not tl_dir.exists():
            return translations

        extractor = RenpyTlItemExtractor()
        for rpy_file in self._iter_rpy_files(tl_dir):
            try:
                content = rpy_file.read_text(encoding="utf-8", errors="replace")
                doc = parse_tl_document(content.splitlines())
                items = extractor.extract(doc, str(rpy_file))
                rel_path = rpy_file.relative_to(tl_dir).as_posix()
                for item in items:
                    src = item.get_src()
                    dst = item.get_dst()
                    block_key = self._numbered_item_translation_key(rel_path, item)
                    if block_key is not None:
                        if dst and dst != src:
                            translations.blocks[block_key] = dst
                        name_src = item.get_name_src()
                        name_dst = item.get_name_dst()
                        if (
                            isinstance(name_dst, str)
                            and name_dst
                            and name_dst != name_src
                        ):
                            translations.block_names[block_key] = name_dst
                    else:
                        extra = item.get_extra_field()
                        renpy = extra.get("renpy", {}) if isinstance(extra, dict) else {}
                        block = renpy.get("block", {}) if isinstance(renpy, dict) else {}
                        if (
                            dst
                            and dst != src
                            and tl_block_kind_name(block.get("kind")) == "STRINGS"
                        ):
                            translations.strings[src] = dst
                continue
            except Exception as exc:
                self.logger.warning(f"AST 读取已有翻译失败，回退 old/new 扫描 {rpy_file}: {exc}")

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
                                    old_text_u = self._decode_rpy_string(
                                        old_match.group(1), old_text
                                    )
                                    new_text_u = self._decode_rpy_string(
                                        new_match.group(1), new_text
                                    )
                                    translations.strings[old_text_u] = new_text_u
                                i = j
                    i += 1
            except Exception as exc:
                self.logger.warning(f"读取已有 strings 翻译失败 {rpy_file}: {exc}")
        if cache_key is not None:
            try:
                _EXISTING_TRANSLATIONS_CACHE[cache_key] = (
                    dict(translations.strings),
                    dict(translations.blocks),
                    dict(translations.block_names),
                )
            except Exception:
                pass
        return translations

    def preview_translation_reuse(
        self,
        source_tl_dir: str | Path,
        target_tl_dir: str | Path,
    ) -> TranslationReuseResult:
        """只读统计旧译文可安全复用到目标目录的数量。"""
        source, target = self._validate_translation_reuse_paths(source_tl_dir, target_tl_dir)
        translations = self._get_existing_translations(source)
        return self._apply_translation_reuse(target, translations.strings, dry_run=True)

    def reuse_translations(
        self,
        source_tl_dir: str | Path,
        target_tl_dir: str | Path,
    ) -> TranslationReuseResult:
        """仅填充目标中的空白/原文占位译文，绝不覆盖已有译文。"""
        source, target = self._validate_translation_reuse_paths(source_tl_dir, target_tl_dir)
        translations = self._get_existing_translations(source)
        preview = self._apply_translation_reuse(target, translations.strings, dry_run=True)
        if preview.reusable_entries == 0:
            return preview

        backup_path = self._copy_tl_backup(target)
        result = self._apply_translation_reuse(target, translations.strings, dry_run=False)
        result.backup_path = backup_path
        return result

    def _validate_translation_reuse_paths(
        self,
        source_tl_dir: str | Path,
        target_tl_dir: str | Path,
    ) -> tuple[Path, Path]:
        source = Path(source_tl_dir).expanduser().resolve()
        target = Path(target_tl_dir).expanduser().resolve()
        if not source.is_dir():
            raise FileNotFoundError(f"旧译文目录不存在: {source}")
        if not target.is_dir():
            raise FileNotFoundError(f"目标译文目录不存在: {target}")
        if source == target:
            raise ValueError("旧译文目录和目标译文目录不能相同")
        return source, target

    def _copy_tl_backup(self, target_tl_dir: Path) -> Path:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_parent = target_tl_dir.parent
        for ancestor in target_tl_dir.parents:
            if ancestor.name.lower() == "game":
                backup_parent = ancestor.parent
                break

        base = backup_parent / f"tl_backup_{target_tl_dir.name}_reuse_{timestamp}"
        backup = base
        suffix = 1
        while backup.exists():
            backup = Path(f"{base}_{suffix}")
            suffix += 1
        shutil.copytree(target_tl_dir, backup)
        return backup

    def _apply_translation_reuse(
        self,
        tl_dir: Path,
        translations: Dict[str, str],
        *,
        dry_run: bool = False,
    ) -> TranslationReuseResult:
        """按原文回填译文；已有非占位译文只计为冲突，不覆盖。"""
        result = TranslationReuseResult(source_translations=len(translations))

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
                    items_to_apply = []
                    for item in items:
                        src = item.get_src()
                        dst = item.get_dst()
                        result.target_entries += 1
                        if src not in translations:
                            result.unmatched_entries += 1
                            continue

                        result.matched_entries += 1
                        translated = translations[src]
                        if not dst or dst == src:
                            result.reusable_entries += 1
                            if not dry_run:
                                item.set_dst(translated)
                                items_to_apply.append(item)
                        elif dst == translated:
                            result.already_reused += 1
                        else:
                            result.conflicts += 1

                    if items_to_apply:
                        def get_target_line(cache_item) -> int:
                            extra_raw = cache_item.get_extra_field()
                            extra = extra_raw if isinstance(extra_raw, dict) else {}
                            renpy = extra.get("renpy", {}) if isinstance(extra.get("renpy"), dict) else {}
                            pair = renpy.get("pair", {}) if isinstance(renpy.get("pair"), dict) else {}
                            line = pair.get("target_line")
                            return int(line) if isinstance(line, int) else 0

                        items_to_apply.sort(key=get_target_line)
                        applied, _ = writer.apply_items_to_lines(lines, items_to_apply)
                        if applied > 0:
                            atomic_write_text(
                                rpy_file,
                                "\n".join(lines),
                                validator=lambda value: parse_tl_document(value.splitlines()),
                                allowed_roots=[tl_dir],
                            )
                            result.applied_entries += applied
                    continue
            except Exception as e:
                self.logger.warning(f"AST 回填翻译失败 {rpy_file}: {e}")

            # 回退旧正则逻辑
            try:
                content = rpy_file.read_text(encoding="utf-8")
                lines = content.split("\n")
                file_modified = False

                i = 0
                while i < len(lines):
                    line = lines[i]
                    old_match = self.OLD_LINE_RE.match(line)
                    if old_match is None:
                        i += 1
                        continue

                    old_text = old_match.group("text")
                    old_text_unescaped = old_text.replace('\\"', '"').replace("\\'", "'")
                    j = i + 1
                    while j < len(lines):
                        probe = lines[j].strip()
                        if not probe or probe.startswith("#"):
                            j += 1
                            continue
                        break
                    if j >= len(lines):
                        i += 1
                        continue

                    new_match = self.NEW_LINE_RE.match(lines[j])
                    if new_match is None:
                        i += 1
                        continue

                    new_text = new_match.group("text")
                    new_text_unescaped = new_text.replace('\\"', '"').replace("\\'", "'")
                    result.target_entries += 1
                    if old_text_unescaped not in translations:
                        result.unmatched_entries += 1
                    else:
                        result.matched_entries += 1
                        translated = translations[old_text_unescaped]
                        if not new_text_unescaped or new_text_unescaped == old_text_unescaped:
                            result.reusable_entries += 1
                            if not dry_run:
                                indent = lines[j][:len(lines[j]) - len(lines[j].lstrip())]
                                lines[j] = f'{indent}new "{escape_tl_string(translated)}"'
                                result.applied_entries += 1
                                file_modified = True
                        elif new_text_unescaped == translated:
                            result.already_reused += 1
                        else:
                            result.conflicts += 1
                    i = j
                    i += 1

                if file_modified:
                    atomic_write_text(
                        rpy_file,
                        "\n".join(lines),
                        validator=lambda value: parse_tl_document(value.splitlines()),
                        allowed_roots=[tl_dir],
                    )
            except Exception as e:
                self.logger.warning(f"回填翻译失败 {rpy_file}: {e}")

        return result

    def _merge_translations(
        self,
        tl_dir: Path,
        translations: ExistingTranslations | Dict[str, str],
    ) -> List[str]:
        """按作用域回填译文；旧 dict 输入仅作为 strings 翻译兼容。"""
        if isinstance(translations, dict):
            translations = ExistingTranslations(strings=translations, blocks={})
        if len(translations) == 0:
            return []

        extractor = RenpyTlItemExtractor()
        writer = RenpyTlLineUpdater()
        failures: List[str] = []

        for rpy_file in self._iter_rpy_files(tl_dir):
            # 优先使用 AST 回填，失败再走旧正则逻辑
            try:
                content = rpy_file.read_text(encoding="utf-8", errors="replace")
                lines = content.splitlines()
                doc = parse_tl_document(lines)
                items = extractor.extract(doc, str(rpy_file))
                if items:
                    rel_path = rpy_file.relative_to(tl_dir).as_posix()
                    updated = False
                    for item in items:
                        src = item.get_src()
                        block_key = self._numbered_item_translation_key(rel_path, item)
                        if block_key is not None:
                            if block_key in translations.blocks:
                                item.set_dst(translations.blocks[block_key])
                                updated = True
                            if block_key in translations.block_names:
                                item.set_name_dst(translations.block_names[block_key])
                                updated = True
                            continue

                        extra = item.get_extra_field()
                        renpy = extra.get("renpy", {}) if isinstance(extra, dict) else {}
                        block = renpy.get("block", {}) if isinstance(renpy, dict) else {}
                        if (
                            tl_block_kind_name(block.get("kind")) == "STRINGS"
                            and src in translations.strings
                        ):
                            item.set_dst(translations.strings[src])
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
                            atomic_write_text(
                                rpy_file,
                                "\n".join(lines),
                                validator=lambda value: parse_tl_document(value.splitlines()),
                                allowed_roots=[tl_dir],
                            )
                    continue
            except Exception as e:
                self.logger.warning(f"AST 回填翻译失败 {rpy_file}: {e}")
                ast_error = e
            else:
                ast_error = None

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
                        old_text_unescaped = self._decode_rpy_string(
                            match.group(2), old_text
                        )

                        # 检查是否有翻译
                        if old_text_unescaped in translations.strings:
                            trans_text = translations.strings[old_text_unescaped]
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
                    atomic_write_text(
                        rpy_file,
                        "\n".join(new_lines),
                        validator=lambda value: parse_tl_document(value.splitlines()),
                        allowed_roots=[tl_dir],
                    )
            except Exception as e:
                self.logger.warning(f"回填翻译失败 {rpy_file}: {e}")
                detail = f"AST: {ast_error}; fallback: {e}" if ast_error else str(e)
                failures.append(f"回填翻译失败 {rpy_file}: {detail}")

        return failures

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







