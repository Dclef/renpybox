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
        "choice_screen_fix_auto.rpy",
    }
    CHOICE_SCREEN_FIX_FILE = "choice_screen_fix_auto.rpy"
    AUTO_SCREEN_FILE = "auto_screens_default.rpy"

    CHOICE_SCREEN_DEF_RE = re.compile(
        r"^\s*(?:init\s+[-\d]+\s+)?screen\s+choice\s*\(\s*items\s*\)\s*:\s*$",
        re.IGNORECASE,
    )
    
    def __init__(self, renpy_extractor: Optional[RenpyExtractor] = None):
        self.logger = LogManager.get()
        self.renpy_extractor = renpy_extractor or RenpyExtractor()
        self._progress_callback: Optional[Callable[[str, int], None]] = None
    
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
        - 若 `tl_dir` 的其他文件已存在“有效翻译”（new != "" 且 new != old），则从 base_box 中移除对应条目；
        - 若其他文件仅存在占位翻译（new == "" 或 new == old），则删除这些占位条目，保留 base_box 翻译。
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

            def collect_base_box_old_values() -> Set[str]:
                base_old: Set[str] = set()
                for fp in sorted(src_dir.glob("*.rpy")):
                    if not fp.is_file():
                        continue
                    try:
                        content = fp.read_text(encoding="utf-8", errors="replace")
                    except Exception:
                        continue
                    for m in self.OLD_LINE_RE.finditer(content):
                        base_old.add(decode_literal(m.group(1), m.group("text")))
                return base_old

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

            injected = 0
            removed_placeholders = 0
            removed_from_base_box = 0

            base_box_old_set = collect_base_box_old_values()
            prefer_user_translation: Set[str] = set()

            # 1) 先扫描 tl_dir 里的其它文件：对 base_box 范围内的占位翻译做清理；若已存在有效翻译则标记为“用户优先”。
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

                placeholder_olds: Set[str] = set()
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
                            if old_value in base_box_old_set:
                                new_value = decode_literal(new_match.group(1), new_match.group("text"))
                                if new_value == "" or new_value == old_value:
                                    placeholder_olds.add(old_value)
                                else:
                                    prefer_user_translation.add(old_value)
                            i = j + 1
                            continue
                    i += 1

                if placeholder_olds:
                    removed_placeholders += remove_string_entries_by_old_values(rpy_file, placeholder_olds)

            # 处理占位清理后可能出现的空 strings 块（例如仅剩 `translate xxx strings:`），避免 Ren'Py 解析报错。
            try:
                self._remove_empty_translate_blocks(tl_dir, tl_name)
            except Exception:
                pass

            for src in sorted(src_dir.glob("*.rpy")):
                if not src.is_file():
                    continue

                content = src.read_text(encoding="utf-8", errors="replace")
                # 支持旧模板（schinese 占位）与新版 {tl_name} 占位
                content = content.replace("translate schinese", f"translate {tl_name}")
                content = content.replace("tl/schinese", f"tl/{tl_name}")
                content = content.replace("{tl_name}", tl_name)

                dest_file = dest_dir / src.name
                dest_file.write_text(content, encoding="utf-8")

                # 2) 若 tl_dir 其它文件已存在有效翻译，则从 base_box 中移除对应条目，避免重复。
                if prefer_user_translation:
                    removed_from_base_box += remove_string_entries_by_old_values(dest_file, prefer_user_translation)

                # 若文件只剩空 translate 块，直接删除（否则会导致 Ren'Py 报错）
                try:
                    final_text = dest_file.read_text(encoding="utf-8", errors="replace")
                    meaningful = False
                    for line in final_text.splitlines():
                        stripped = line.strip()
                        if not stripped or stripped.startswith("#"):
                            continue
                        if stripped.startswith("translate "):
                            continue
                        meaningful = True
                        break
                    # strings 翻译文件必须至少包含一个 old 条目，否则视为无意义
                    if self.TRANSLATE_STRINGS_PATTERN.search(final_text) and not self.OLD_LINE_RE.search(final_text):
                        meaningful = False
                    if not meaningful:
                        dest_file.unlink()
                        continue
                except Exception:
                    pass

                injected += 1

            if removed_placeholders or removed_from_base_box:
                self.logger.info(
                    f"已清理 base_box 冲突: 删除占位 {removed_placeholders} 条，"
                    f"从 base_box 移除 {removed_from_base_box} 条"
                )

            return injected
        except Exception as exc:
            self.logger.warning(f"注入内置 base_box 失败: {exc}")
            return 0

    def _deploy_choice_screen_fix(self, game_dir: Path, tl_dir: Path) -> Optional[Path]:
        """为自定义 `choice` 屏幕生成修补文件，避免 `item.caption` 被字符串拼接后失去翻译效果。

        常见写法：`"... " + item.caption + " ..."`。此时 `item.caption` 会先变成纯字符串，
        导致 Ren'Py 的 strings 翻译无法命中。修补策略：仅在拼接场景下将其改为 `_(str(item.caption))`。

        生成文件：`tl/<lang>/choice_screen_fix_auto.rpy`（若已存在则不覆盖）。
        """
        try:
            if not (game_dir and tl_dir and tl_dir.exists()):
                return None

            target = tl_dir / self.CHOICE_SCREEN_FIX_FILE
            if target.exists():
                return target

            scripts_dir = game_dir / "game"
            if not scripts_dir.exists():
                return None

            def read_text_loose(path: Path) -> str:
                try:
                    return path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    return ""

            def extract_block(lines: List[str], start: int) -> List[str]:
                header = lines[start]
                base_indent = len(header) - len(header.lstrip())
                block: List[str] = [header]
                i = start + 1
                while i < len(lines):
                    line = lines[i]
                    stripped = line.strip()
                    if stripped == "":
                        block.append(line)
                        i += 1
                        continue
                    indent = len(line) - len(line.lstrip())
                    if indent <= base_indent:
                        break
                    block.append(line)
                    i += 1
                return block

            def needs_fix(block: List[str]) -> bool:
                for line in block:
                    if "item.caption" not in line:
                        continue
                    if re.search(r"\+\s*item\.caption\b|\bitem\.caption\s*\+", line):
                        return True
                return False

            def patch_block(block: List[str]) -> List[str]:
                if not block:
                    return block

                header = block[0]
                header_indent = header[: len(header) - len(header.lstrip())]
                patched: List[str] = [f"{header_indent}init 999 screen choice(items):"]

                for line in block[1:]:
                    updated = line
                    updated = re.sub(
                        r"(\+\s*)item\.caption(\s*\+)",
                        r"\1_(str(item.caption))\2",
                        updated,
                    )
                    updated = re.sub(
                        r"(\+\s*)item\.caption\b(?!\s*\+)",
                        r"\1_(str(item.caption))",
                        updated,
                    )
                    updated = re.sub(
                        r"\bitem\.caption(\s*\+)",
                        r"_(str(item.caption))\1",
                        updated,
                    )
                    patched.append(updated)

                return patched

            found: Optional[Tuple[Path, int, List[str]]] = None
            for fp in sorted(scripts_dir.rglob("*.rpy")):
                try:
                    rel = fp.relative_to(scripts_dir)
                    if rel.parts and rel.parts[0].lower() == "tl":
                        continue
                except Exception:
                    pass
                raw = read_text_loose(fp)
                if "choice(" not in raw and "screen choice" not in raw:
                    continue

                lines = raw.splitlines()
                for idx, line in enumerate(lines):
                    if not self.CHOICE_SCREEN_DEF_RE.match(line):
                        continue
                    block = extract_block(lines, idx)
                    if needs_fix(block):
                        found = (fp, idx + 1, block)  # 1-based line for humans
                        break
                if found:
                    break

            if not found:
                return None

            src_path, src_line, block = found
            patched_block = patch_block(block)
            if patched_block == block:
                return None

            header_lines = [
                "# Auto-generated by Ren'Py Translation Tool",
                "# Fix: translate menu captions when custom choice screen concatenates item.caption",
                f"# Source: {src_path.as_posix()}:{src_line}",
                "",
            ]
            content = "\n".join(header_lines + patched_block).rstrip() + "\n"
            target.write_text(content, encoding="utf-8")
            self.logger.info(f"已生成 choice 屏幕修补文件: {target}")
            return target
        except Exception as exc:
            self.logger.warning(f"生成 choice 屏幕修补失败: {exc}")
            return None

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
            
            # 4. 过滤与清理 + 终极结构导出
            self._post_process(game_dir, tl_name, tl_dir, config, None)

            # 5. 注入内置 UI 包（common_box/screens_box）
            injected_ui = self._deploy_builtin_ui_pack(tl_dir, tl_name)
            if injected_ui:
                self.logger.info(f"已注入 base_box UI 翻译: {injected_ui} 个文件")

            # 6. 修补自定义 choice(items) 屏幕（避免 item.caption 拼接导致 strings 翻译失效）
            self._deploy_choice_screen_fix(game_dir, tl_dir)
            
            # 统计
            result.total_files = len(list(self._iter_rpy_files(tl_dir)))
            result.success = True
            ui_note = "（已注入 base_box UI 翻译）" if injected_ui else ""
            result.message = f"常规抽取完成，共 {result.total_files} 个文件{ui_note}"
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
            
            # 1. 获取已翻译内容 {original: translated}
            existing_translations = self._get_existing_translations(tl_dir)
            translated_count = len(existing_translations)
            result.preserved_count = translated_count
            self.logger.info(f"发现 {translated_count} 条有效翻译")
            
            # 2. 获取当前所有原文（用于后续对比新增）
            existing_originals = set(existing_translations.keys())
            all_current_originals = self._get_all_originals(tl_dir)
            self.logger.info(f"当前共 {len(all_current_originals)} 条原文")
            
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
                new_extracted_originals = self._get_all_originals(temp_tl_dir)
                self.logger.info(f"新抽取共 {len(new_extracted_originals)} 条原文")
                
                # 7. 计算新增原文
                new_originals = new_extracted_originals - all_current_originals
                self.logger.info(f"检测到 {len(new_originals)} 条新增原文")
                result.new_strings = len(new_originals)

                pending_originals: Set[str] = set()
                if output_to_separate_folder and getattr(config, "renpy_incremental_include_untranslated", False):
                    # tl 已存在但没翻译过/只有占位（new==old/new==""）时，把这些也纳入待翻译包
                    pending_originals = self._get_untranslated_originals(tl_dir)
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
                        temp_tl_dir, incremental_dir, selected_originals, tl_name
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
                    result.message = f"增量抽取完成，保留了 {translated_count} 条已有翻译，新增 {len(new_originals)} 条"

                # 注入内置 UI 包（仅影响主 tl 目录，不影响增量输出目录）
                injected_ui = self._deploy_builtin_ui_pack(tl_dir, tl_name)
                if injected_ui and result.success:
                    self.logger.info(f"已注入 base_box UI 翻译: {injected_ui} 个文件")
                    if output_to_separate_folder and isinstance(result.message, str) and result.message.startswith("增量抽取完成"):
                        result.message = result.message + "\n• 已注入 base_box UI 翻译"
                    elif not output_to_separate_folder and result.message:
                        result.message = result.message + "（已注入 base_box UI 翻译）"

                # 修补自定义 choice(items) 屏幕（避免 item.caption 拼接导致 strings 翻译失效）
                self._deploy_choice_screen_fix(game_dir, tl_dir)
                
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

    def _get_all_originals(self, tl_dir: Path) -> Set[str]:
        """获取 tl 目录中所有的原文"""
        originals = set()
        if not tl_dir.exists():
            return originals
            
        for rpy_file in self._iter_rpy_files(tl_dir):
            try:
                content = rpy_file.read_text(encoding='utf-8', errors='replace')
                for match in self.OLD_LINE_RE.finditer(content):
                    old_text = match.group("text").replace('\\"', '"').replace("\\'", "'")
                    originals.add(old_text)
            except Exception:
                pass
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

    def _extract_new_entries_to_folder(
        self,
        source_dir: Path,
        target_dir: Path,
        selected_originals: Set[str],
        tl_name: str
    ):
        """将指定条目（新增/未翻译）提取到目标文件夹"""
        if not selected_originals:
            return
            
        for rpy_file in self._iter_rpy_files(source_dir):
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
                        if old_text in selected_originals:
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
            
        for rpy_file in self._iter_rpy_files(source_dir):
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

    # ================= 内部辅助方法 =================

    def _collect_block_originals(self, tl_dir: Path) -> Set[str]:
        """收集 translate 块中的原文（从注释行提取），用于与 strings 去重"""
        block_originals: Set[str] = set()
        if not tl_dir.exists():
            return block_originals

        for rpy_file in self._iter_rpy_files(tl_dir):
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
        """
        移除 translate strings 中与 translate 块原文重复的条目（优先保留块翻译）。
        返回删除的条目数量。
        """
        block_originals = self._collect_block_originals(tl_dir)
        if not block_originals:
            return 0

        removed = 0
        for rpy_file in self._iter_rpy_files(tl_dir):
            try:
                lines = rpy_file.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception:
                continue

            new_lines: List[str] = []
            i = 0
            changed = False

            while i < len(lines):
                line = lines[i]
                match = self.OLD_LINE_RE.match(line)
                if match:
                    old_text = match.group("text").replace('\\"', '"').replace("\\'", "'")
                    next_line = lines[i + 1] if i + 1 < len(lines) else ""
                    new_match = self.NEW_LINE_RE.match(next_line)

                    if old_text in block_originals:
                        removed += 1
                        changed = True
                        # 跳过 old/new 行
                        i += 2 if new_match else 1
                        # 跳过紧随其后的空行，避免留下多余空白
                        while i < len(lines) and not lines[i].strip():
                            i += 1
                        continue

                new_lines.append(line)
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

                try:
                    rpy_file.write_text("\n".join(final_lines), encoding="utf-8")
                except Exception:
                    pass

        return removed

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
        preserve_set = self._load_preserve_set(config)
        
        # 应用过滤
        if preserve_set:
            self._emit_progress("正在应用保留库过滤...", 80)
            self._filter_tl_files(tl_dir, preserve_set)

        # 移除与 translate 块重复的 strings 条目（保留块翻译，删掉 old/new）
        if getattr(config, "renpy_remove_string_duplicates", False):
            removed = self._remove_string_duplicates_with_blocks(tl_dir)
            if removed:
                self.logger.info(f"已移除 {removed} 条与翻译块重复的 strings 翻译")
            
        # 移除 Hook 及工具型文件
        if config.extract_skip_hook_files:
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
        if config.extract_export_excel:
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
                if rpyc_path.exists() and (rpyc_path.name in hook_names or any(rpyc_path.stem.startswith(pat) for pat in extra_patterns)):
                    try:
                        rpyc_path.unlink()
                    except Exception:
                        pass

    def _get_existing_translations(self, tl_dir: Path) -> Dict[str, str]:
        """
        获取有效的翻译对 {original: translated}
        条件：new != "" AND new != old
        """
        translations = {}
        if not tl_dir.exists():
            return translations
            
        for rpy_file in self._iter_rpy_files(tl_dir):
            try:
                content = rpy_file.read_text(encoding='utf-8', errors='replace')
                # 简单的正则匹配可能不够准确，但对于标准 rpy 格式通常足够
                # 匹配 old "xxx" ... new "yyy"
                # 注意：这里简化处理，假设 old 和 new 是成对出现的
                
                lines = content.split('\n')
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

        for rpy_file in self._iter_rpy_files(tl_dir):
            try:
                content = rpy_file.read_text(encoding='utf-8')
                lines = content.split('\n')
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
                            
                            new_lines.append(line) # old 行不变
                            new_lines.append(f'{indent}new "{trans_text_escaped}"') # 替换 new 行
                            modified = True
                            i += 2 # 跳过原来的 new 行
                            continue
                            
                    new_lines.append(line)
                    i += 1
                
                if modified:
                    rpy_file.write_text('\n'.join(new_lines), encoding='utf-8')
                    
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
