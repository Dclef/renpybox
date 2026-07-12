from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List

from base.Base import Base
from module.Cache.CacheItem import CacheItem
from module.Config import Config
from module.Renpy.renpy_tl_io import RenpyTlItemExtractor
from module.Renpy.renpy_tl_core import parse_tl_document
from module.Renpy.renpy_tl_io import RenpyTlLineUpdater


class RENPY(Base):
    """Ren'Py reader/writer powered by AST-based parsing."""

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self.input_path = Path(config.input_folder)
        self.output_path = Path(config.output_folder)
        self._skip_dirs = {"base_box"}
        self._skip_files = {
            "common.rpy",
            "common_box.rpy",
            "screens_box.rpy",
            "style_box.rpy",
        }

    def read_from_path(self, abs_paths: List[str]) -> List[CacheItem]:
        """Parse .rpy files into cache items via AST extraction."""
        items: List[CacheItem] = []
        extractor = RenpyTlItemExtractor()
        for abs_path in abs_paths:
            path = Path(abs_path)
            if not path.is_file():
                continue

            rel_path = self._relative_to_input(path)
            if self._should_skip_file(path, rel_path):
                self.debug(f"Skip builtin UI file: {rel_path}")
                continue

            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except Exception as exc:
                self.error(f"Failed to read {path}", exc)
                continue

            lines = text.splitlines()
            doc = parse_tl_document(lines)
            items.extend(extractor.extract(doc, rel_path))

        return items

    def write_to_path(self, items: List[CacheItem]) -> None:
        """Write translated items back to .rpy files using AST metadata."""
        target: List[CacheItem] = [
            item for item in items if item.get_file_type() == CacheItem.FileType.RENPY
        ]

        grouped: Dict[str, List[CacheItem]] = {}
        for item in target:
            grouped.setdefault(item.get_file_path(), []).append(item)

        writer = RenpyTlLineUpdater()
        extractor = RenpyTlItemExtractor()

        report: list[dict] = []
        for rel_path, group_items in grouped.items():
            source_path = self._resolve_source_path(rel_path)
            if not source_path.exists():
                self.warning(f"RENPY 导出源文件不存在: {source_path}")
                continue

            try:
                text = source_path.read_text(encoding="utf-8", errors="replace")
            except Exception as exc:
                self.error(f"Failed to read Ren'Py file {source_path}", exc)
                continue

            lines = text.splitlines()
            items_to_apply = self.build_items_for_writeback(
                extractor,
                rel_path,
                lines,
                group_items,
            )
            items_to_apply.sort(key=self.get_item_target_line)

            translated_items = sum(
                1
                for item in group_items
                if isinstance(item.get_dst(), str)
                and item.get_dst() != ""
                and item.get_dst() != item.get_src()
            )
            applied, skipped = writer.apply_items_to_lines(lines, items_to_apply)
            fallback_items: list[CacheItem] | None = None
            if skipped > 0:
                # Fallback: rebuild AST from current file and remap translations by text.
                doc = parse_tl_document(lines)
                fallback_items = extractor.extract(doc, rel_path)
                self.transfer_ast_translations(group_items, fallback_items)
                self.transfer_text_translations(group_items, fallback_items)
                fallback_items.sort(key=self.get_item_target_line)
                applied2, skipped2 = writer.apply_items_to_lines(lines, fallback_items)
                if applied2 > 0:
                    applied, skipped = applied2, skipped2
            if skipped > 0 and translated_items > 0:
                # Last resort: loose writeback without hash checks.
                if fallback_items is None:
                    doc = parse_tl_document(lines)
                    fallback_items = extractor.extract(doc, rel_path)
                    self.transfer_ast_translations(group_items, fallback_items)
                    self.transfer_text_translations(group_items, fallback_items)
                    fallback_items.sort(key=self.get_item_target_line)
                applied3, skipped3 = writer.apply_items_to_lines_loose(lines, fallback_items)
                if applied3 > 0:
                    applied, skipped = applied3, skipped3
                    self.warning(
                        f"RENPY 写回已改用宽松匹配: {rel_path} (applied={applied}, skipped={skipped})",
                        console=False,
                    )
            if skipped > 0:
                self.warning(
                    f"RENPY 导出写回跳过 {skipped} 条: {rel_path} (applied={applied})",
                    console=False,
                )
            if translated_items > 0 and applied == 0:
                self.warning(
                    f"RENPY 写回疑似未生效: {rel_path} (translated={translated_items}, applied={applied}, skipped={skipped})",
                    console=False,
                )

            target_path = self.output_path / rel_path
            os.makedirs(target_path.parent, exist_ok=True)
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
            report_path = self.output_path / "writeback_report_renpy.json"
            try:
                report_path.write_text(
                    json.dumps(report, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception:
                pass

    def build_items_for_writeback(
        self,
        extractor: RenpyTlItemExtractor,
        rel_path: str,
        lines: list[str],
        items: list[CacheItem],
    ) -> list[CacheItem]:
        # If all items already carry AST metadata, use them directly.
        if items and all(self.has_ast_extra_field(v) for v in items):
            return items

        # Rebuild AST from current file and transfer translations by AST keys.
        doc = parse_tl_document(lines)
        new_items = extractor.extract(doc, rel_path)
        self.transfer_ast_translations(items, new_items)
        self.transfer_text_translations(items, new_items)
        return new_items

    def has_ast_extra_field(self, item: CacheItem) -> bool:
        extra_raw = item.get_extra_field()
        if not isinstance(extra_raw, dict):
            return False
        renpy = extra_raw.get("renpy")
        return isinstance(renpy, dict)

    def get_item_target_line(self, item: CacheItem) -> int:
        extra_raw = item.get_extra_field()
        extra = extra_raw if isinstance(extra_raw, dict) else {}
        renpy = extra.get("renpy", {}) if isinstance(extra.get("renpy"), dict) else {}
        pair = renpy.get("pair", {}) if isinstance(renpy.get("pair"), dict) else {}
        line = pair.get("target_line")
        return int(line) if isinstance(line, int) else 0

    def transfer_ast_translations(
        self,
        existing_items: list[CacheItem],
        new_items: list[CacheItem],
    ) -> None:
        existing_by_key: dict[tuple[str, str, str], list[CacheItem]] = {}
        for item in existing_items:
            if not self.has_ast_extra_field(item):
                continue

            keys = self.build_ast_keys(item)
            if not keys:
                continue

            # Only use the primary key to avoid double consumption.
            existing_by_key.setdefault(keys[0], []).append(item)

        for item in new_items:
            keys = self.build_ast_keys(item)
            if not keys:
                continue

            candidates: list[CacheItem] | None = None
            for key in keys:
                bucket = existing_by_key.get(key)
                if bucket:
                    candidates = bucket
                    break
            if candidates is None:
                continue

            picked = self.pick_best_candidate(item, candidates)
            item.set_dst(picked.get_dst())
            if picked.get_name_dst() is not None:
                item.set_name_dst(picked.get_name_dst())

    def transfer_text_translations(
        self,
        existing_items: list[CacheItem],
        new_items: list[CacheItem],
    ) -> None:
        existing_by_text: dict[tuple[str, str], list[CacheItem]] = {}
        for item in existing_items:
            src = item.get_src()
            if not isinstance(src, str) or src == "":
                continue
            name_key = self._normalize_name_key(item.get_name_src())
            existing_by_text.setdefault((src, name_key), []).append(item)

        for item in new_items:
            dst = item.get_dst()
            src = item.get_src()
            if not isinstance(src, str) or src == "":
                continue
            if isinstance(dst, str) and dst != "" and dst != src:
                continue

            name_key = self._normalize_name_key(item.get_name_src())
            candidates = existing_by_text.get((src, name_key))
            if not candidates:
                continue

            picked = self.pick_best_candidate(item, candidates)
            picked_dst = picked.get_dst()
            if isinstance(picked_dst, str) and picked_dst != "" and picked_dst != src:
                item.set_dst(picked_dst)
            if picked.get_name_dst() is not None:
                item.set_name_dst(picked.get_name_dst())

    def build_ast_keys(self, item: CacheItem) -> list[tuple[str, str, str]]:
        extra_raw = item.get_extra_field()
        extra = extra_raw if isinstance(extra_raw, dict) else {}
        renpy = extra.get("renpy")
        if not isinstance(renpy, dict):
            return []
        block = renpy.get("block")
        digest = renpy.get("digest")
        if not isinstance(block, dict) or not isinstance(digest, dict):
            return []
        lang = block.get("lang")
        label = block.get("label")
        if not isinstance(lang, str) or not isinstance(label, str):
            return []

        primary = digest.get("template_raw_sha1")
        fallback = digest.get("template_raw_rstrip_sha1")

        keys: list[tuple[str, str, str]] = []
        if isinstance(primary, str) and primary != "":
            keys.append((lang, label, primary))
        if (
            isinstance(fallback, str)
            and fallback != ""
            and (not keys or fallback != keys[0][2])
        ):
            keys.append((lang, label, fallback))

        return keys

    def pick_best_candidate(
        self, item: CacheItem, candidates: list[CacheItem]
    ) -> CacheItem:
        if len(candidates) == 1:
            return candidates.pop(0)

        src = item.get_src()
        name = item.get_name_src()

        for i, cand in enumerate(candidates):
            if cand.get_src() == src and cand.get_name_src() == name:
                return candidates.pop(i)

        for i, cand in enumerate(candidates):
            if cand.get_src() == src:
                return candidates.pop(i)

        return candidates.pop(0)

    def _normalize_name_key(self, value: str | list[str] | None) -> str:
        if isinstance(value, list):
            return "|".join([str(v) for v in value if v is not None])
        if isinstance(value, str):
            return value
        return ""

    def _relative_to_input(self, path: Path) -> str:
        try:
            if self.input_path.is_file():
                rel = path.name
            else:
                rel = path.relative_to(self.input_path)
        except ValueError:
            rel = path.name
        return str(rel).replace("\\", "/")

    def _should_skip_file(self, path: Path, rel_path: str) -> bool:
        try:
            name = path.name.lower()
            if name in self._skip_files:
                return True
            parts = [p.lower() for p in Path(rel_path).parts]
            return any(part in self._skip_dirs for part in parts)
        except Exception:
            return False

    def _resolve_source_path(self, rel_path: str) -> Path:
        input_path = self.input_path / rel_path
        target_path = self.output_path / rel_path
        # Cache metadata is built from the current input file.  Reusing a stale
        # file left in the output directory shifts line numbers and hashes, which
        # causes line_out_of_range/writeback mismatches on incremental reruns.
        return input_path if input_path.exists() else target_path
