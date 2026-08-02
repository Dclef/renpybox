from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Set

from base.Base import Base
from module.Cache.CacheItem import CacheItem
from module.Config import Config
from module.Engine.Engine import Engine
from module.Translate.RenpySourceTranslator import RenpySourceTranslator
from module.File.AtomicWrite import atomic_write_text


class RENPYSOURCE(Base):
    """Ren'Py 源码翻译读写器"""

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self.input_path = Path(config.input_folder)
        self.output_path = Path(config.output_folder)

    def _build_text_preserve_set(self) -> Set[str]:
        """构建禁翻表集合"""
        preserves: Set[str] = set()
        if not getattr(self.config, "text_preserve_enable", False):
            return preserves
        for item in getattr(self.config, "text_preserve_data", []) or []:
            src = item.get("src", "") if isinstance(item, dict) else str(item)
            if src:
                preserves.add(src.strip())
        return preserves

    def _relative_to_input(self, path: Path) -> str:
        try:
            if self.input_path.is_file():
                rel = path.name
            else:
                rel = path.relative_to(self.input_path)
        except ValueError:
            rel = path.name
        return str(rel).replace("\\", "/")

    def _is_in_tl_dir(self, path: Path) -> bool:
        """跳过 tl 目录，避免翻译已存在的翻译文件"""
        parts = [p.lower() for p in path.parts]
        return "tl" in parts

    def _resolve_source_path(self, rel_path: str) -> Path:
        target_path = self.output_path / rel_path
        if target_path.exists():
            return target_path
        if self.input_path.is_file():
            return self.input_path
        return self.input_path / rel_path

    def _resolve_reference_path(self, rel_path: str) -> Path:
        """返回原始输入源码路径，用于写回时恢复代码骨架。"""
        if self.input_path.is_file():
            return self.input_path
        return self.input_path / rel_path

    @staticmethod
    def _literal_slot(line: str, text: str, occurrence: int = 0) -> int | None:
        """Return the quoted-literal slot containing a parser entry."""
        matches = list(RenpySourceTranslator.RE_SINGLE_LINE_STRING_LITERAL.finditer(line))
        matching_slots = [
            index for index, match in enumerate(matches) if match.group("text") == text
        ]
        if 0 <= occurrence < len(matching_slots):
            return matching_slots[occurrence]
        return None

    @staticmethod
    def _literal_slot_has_destination(
        translator: RenpySourceTranslator,
        line: str,
        slot: int,
        destination: str,
    ) -> bool:
        matches = list(translator.RE_SINGLE_LINE_STRING_LITERAL.finditer(line))
        if slot < 0 or slot >= len(matches):
            return False
        literal = matches[slot]
        current = literal.group(0)
        expected = translator._replace_text_in_line(
            current, literal.group("text"), destination
        )
        return current == expected

    @staticmethod
    def _recorded_literal_slot(item: CacheItem) -> int | None:
        extra = item.get_extra_field()
        if not isinstance(extra, dict):
            return None
        source_meta = extra.get("renpy_source")
        if not isinstance(source_meta, dict):
            return None
        candidate = source_meta.get("literal_slot")
        return candidate if isinstance(candidate, int) else None

    @staticmethod
    def _replace_literal_at_slot(
        translator: RenpySourceTranslator,
        line: str,
        slot: int,
        source: str,
        destination: str,
    ) -> str:
        matches = list(translator.RE_SINGLE_LINE_STRING_LITERAL.finditer(line))
        if slot < 0 or slot >= len(matches):
            return line
        literal = matches[slot]
        if literal.group("text") != source:
            return line
        current = literal.group(0)
        replacement = translator._replace_text_in_line(
            current, source, destination
        )
        if replacement == current:
            return line
        return line[:literal.start()] + replacement + line[literal.end():]

    def read_from_path(self, abs_paths: List[str]) -> List[CacheItem]:
        """读取 .rpy 源码并生成 CacheItem"""
        items: List[CacheItem] = []
        parser = RenpySourceTranslator()

        preserves = self._build_text_preserve_set()
        if preserves and hasattr(parser, "set_text_preserve"):
            parser.set_text_preserve(preserves)

        total_files = len(abs_paths)
        for index, abs_path in enumerate(abs_paths, start = 1):
            if Engine.get().get_status() == Engine.Status.STOPPING:
                self.info("源码扫描已停止")
                break

            if index == 1 or index % 5 == 0 or index == total_files:
                self.emit(Base.Event.TRANSLATION_UPDATE, {
                    "phase": "preparing",
                    "message": f"正在扫描源码文件… {index}/{total_files}",
                })

            path = Path(abs_path)
            if not path.is_file():
                continue
            if self._is_in_tl_dir(path):
                continue

            rel_path = self._relative_to_input(path)
            entries = parser.scan_file(path)
            if not entries:
                continue

            entry_occurrences: dict[tuple[int, str], int] = {}
            for entry in entries:
                text = (entry.text or "").strip()
                if not entry.needs_translation or text == "":
                    continue
                occurrence_key = (entry.line_number, entry.text)
                occurrence = entry_occurrences.get(occurrence_key, 0)
                literal_slot = self._literal_slot(
                    entry.original_line, entry.text, occurrence
                )
                entry_occurrences[occurrence_key] = occurrence + 1
                items.append(
                    CacheItem.from_dict(
                        {
                            "src": entry.text,
                            "dst": entry.text,
                            "row": entry.line_number,
                            "file_type": CacheItem.FileType.RENPYSOURCE,
                            "file_path": rel_path,
                            "text_type": CacheItem.TextType.RENPY,
                            "status": Base.TranslationStatus.UNTRANSLATED,
                            "extra_field": {
                                "renpy_source": {
                                    "line": entry.line_number,
                                    "line_type": getattr(entry.line_type, "name", str(entry.line_type)),
                                    "literal_slot": literal_slot,
                                }
                            },
                        }
                    )
                )

        items.sort(key=lambda item: (item.get_file_path(), item.get_row()))
        return items

    def write_to_path(self, items: List[CacheItem]) -> None:
        """将翻译结果写回源码文件"""
        target = [
            item for item in items
            if item.get_file_type() == CacheItem.FileType.RENPYSOURCE
        ]
        if not target:
            return

        grouped: dict[str, list[CacheItem]] = {}
        for item in target:
            grouped.setdefault(item.get_file_path(), []).append(item)

        translator = RenpySourceTranslator()
        report: list[dict] = []
        errors: list[str] = []

        for rel_path, group_items in grouped.items():
            source_path = self._resolve_source_path(rel_path)
            if not source_path.exists():
                self.warning(f"RENPY 源码不存在: {source_path}")
                errors.append(f"源文件不存在: {source_path}")
                continue

            reference_path = self._resolve_reference_path(rel_path)

            try:
                text = source_path.read_text(encoding="utf-8", errors="replace")
            except Exception as exc:
                self.error(f"读取 Ren'Py 源码失败: {source_path}", exc)
                errors.append(f"读取失败 {source_path}: {exc}")
                continue

            reference_lines: list[str] | None = None
            if reference_path.exists():
                try:
                    reference_text = reference_path.read_text(encoding="utf-8", errors="replace")
                    reference_lines = reference_text.split("\n")
                except Exception:
                    reference_lines = None

            lines = text.split("\n")
            applied = 0
            already_applied = 0
            skipped = 0
            translated_items = 0

            group_items.sort(key=lambda item: item.get_row())
            for item in group_items:
                src = item.get_src()
                dst = item.get_dst()
                if not isinstance(src, str) or src.strip() == "":
                    skipped += 1
                    continue
                if not isinstance(dst, str) or dst.strip() == "":
                    skipped += 1
                    continue

                if dst != src:
                    translated_items += 1

                row = item.get_row()
                if row <= 0 or row > len(lines):
                    skipped += 1
                    continue

                original_line = lines[row - 1]
                literal_slot = self._recorded_literal_slot(item)
                if (
                    literal_slot is None
                    and reference_lines is not None
                    and row <= len(reference_lines)
                ):
                    reference_line = reference_lines[row - 1]
                    matching_slots = [
                        index
                        for index, match in enumerate(
                            translator.RE_SINGLE_LINE_STRING_LITERAL.finditer(
                                reference_line
                            )
                        )
                        if match.group("text") == src
                    ]
                    if len(matching_slots) == 1:
                        literal_slot = matching_slots[0]

                if literal_slot is None:
                    new_line = translator._replace_text_in_line(
                        original_line, src, dst
                    )
                else:
                    new_line = self._replace_literal_at_slot(
                        translator,
                        original_line,
                        literal_slot,
                        src,
                        dst,
                    )
                if reference_lines is not None and row <= len(reference_lines):
                    # 用原始源码恢复非字符串代码结构，避免 screen action 等表达式被污染。
                    new_line = translator._restore_non_literal_structure(reference_lines[row - 1], new_line)
                if new_line == original_line:
                    if (
                        dst != src
                        and literal_slot is not None
                        and self._literal_slot_has_destination(
                            translator, original_line, literal_slot, dst
                        )
                    ):
                        already_applied += 1
                        continue
                    skipped += 1
                    continue

                lines[row - 1] = new_line
                applied += 1

            target_path = self.output_path / rel_path
            os.makedirs(target_path.parent, exist_ok=True)

            # 写回前备份（仅本地 .bak）
            if self.config.renpy_backup_original:
                bak_path = target_path.with_suffix(target_path.suffix + ".bak")
                if target_path.exists() and not bak_path.exists():
                    try:
                        bak_path.write_text(target_path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
                    except Exception:
                        pass

            if applied + already_applied < translated_items:
                errors.append(
                    f"译文未生效 {rel_path} (translated={translated_items}, "
                    f"applied={applied}, already_applied={already_applied}, skipped={skipped})"
                )
            try:
                atomic_write_text(
                    target_path,
                    "\n".join(lines),
                    allowed_roots=[self.output_path],
                )
            except Exception as exc:
                self.error(f"写入 Ren'Py 源码失败: {target_path}", exc)
                errors.append(f"写入失败 {target_path}: {exc}")
                continue

            report.append(
                {
                    "file": rel_path,
                    "source": str(source_path),
                    "target": str(target_path),
                    "items": len(group_items),
                    "translated_items": translated_items,
                    "applied": applied,
                    "already_applied": already_applied,
                    "skipped": skipped,
                }
            )

        if report:
            report_path = self.output_path / "writeback_report_renpy_source.json"
            try:
                report_path.write_text(
                    json.dumps(report, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception:
                pass
        if errors:
            raise RuntimeError("Ren'Py 源码写回未完整完成：" + "；".join(errors))
