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

            for entry in entries:
                text = (entry.text or "").strip()
                if not entry.needs_translation or text == "":
                    continue
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

        for rel_path, group_items in grouped.items():
            source_path = self._resolve_source_path(rel_path)
            if not source_path.exists():
                self.warning(f"RENPY 源码不存在: {source_path}")
                continue

            reference_path = self._resolve_reference_path(rel_path)

            try:
                text = source_path.read_text(encoding="utf-8", errors="replace")
            except Exception as exc:
                self.error(f"读取 Ren'Py 源码失败: {source_path}", exc)
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
                new_line = translator._replace_text_in_line(original_line, src, dst)
                if reference_lines is not None and row <= len(reference_lines):
                    # 用原始源码恢复非字符串代码结构，避免 screen action 等表达式被污染。
                    new_line = translator._restore_non_literal_structure(reference_lines[row - 1], new_line)
                if new_line == original_line:
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

            target_path.write_text("\n".join(lines), encoding="utf-8")

            report.append(
                {
                    "file": rel_path,
                    "source": str(source_path),
                    "target": str(target_path),
                    "items": len(group_items),
                    "translated_items": translated_items,
                    "applied": applied,
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
