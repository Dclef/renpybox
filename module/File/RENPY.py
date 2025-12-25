from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from base.Base import Base
from module.Cache.CacheItem import CacheItem
from module.Config import Config
from module.Renpy.renpy_io import RenpyStringEntry, RenpyStringReader, RenpyStringWriter


class RENPY(Base):
    """Ren'Py reader/writer built around line-accurate parsing (inspired by AiNiee)."""

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self.input_path = Path(config.input_folder)
        self.output_path = Path(config.output_folder)
        encoding = config.renpy_default_encoding or "utf-8"
        self.reader = RenpyStringReader(encoding=encoding)
        self.writer = RenpyStringWriter(encoding=encoding)
        self._skip_dirs = {"base_box"}
        self._skip_files = {
            "common.rpy",
            "common_box.rpy",
            "screens_box.rpy",
            "style_box.rpy",
        }

    def read_from_path(self, abs_paths: List[str]) -> List[CacheItem]:
        """Parse .rpy files into cache items with precise line mapping."""
        items: List[CacheItem] = []
        for abs_path in abs_paths:
            path = Path(abs_path)
            if not path.is_file():
                continue

            rel_path = self._relative_to_input(path)
            if self._should_skip_file(path, rel_path):
                self.debug(f"Skip builtin UI file: {rel_path}")
                continue
            try:
                entries = self.reader.read(path)
            except Exception as exc:
                self.error(f"Failed to parse {path}", exc)
                continue

            for entry in entries:
                dst = entry.translation or ""
                translated = bool(dst and dst != entry.source)
                status = (
                    Base.TranslationStatus.TRANSLATED_IN_PAST if translated else Base.TranslationStatus.UNTRANSLATED
                )
                items.append(
                    CacheItem.from_dict(
                        {
                            "src": entry.source,
                            "dst": dst if translated else "",
                            "row": len(items),
                            "file_type": CacheItem.FileType.RENPY,
                            "file_path": rel_path,
                            "text_type": CacheItem.TextType.RENPY,
                            "status": status,
                            "extra_field": json.dumps(
                                {
                                    "line_no": entry.line_no,
                                    "tag": entry.tag,
                                    "format": entry.format_type,
                                },
                                ensure_ascii=False,
                            ),
                        }
                    )
                )

        return items

    def write_to_path(self, items: List[CacheItem]) -> None:
        """Write translated items back to .rpy files using stored line metadata."""
        grouped: Dict[str, List[RenpyStringEntry]] = {}
        for item in items:
            if item.get_file_type() != CacheItem.FileType.RENPY:
                continue

            entry = self._build_entry_from_item(item)
            if entry is None:
                continue
            grouped.setdefault(item.get_file_path(), []).append(entry)

        for rel_path, entries in grouped.items():
            target_path = self.output_path / rel_path
            source_path = target_path if target_path.exists() else self.input_path / rel_path
            try:
                self.writer.write(target_path, entries, source_file_path=source_path)
            except Exception as exc:
                self.error(f"Failed to write Ren'Py file {target_path}", exc)

    def _relative_to_input(self, path: Path) -> str:
        try:
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

    def _build_entry_from_item(self, item: CacheItem) -> Optional[RenpyStringEntry]:
        extra = self._load_extra(item.get_extra_field())
        if not isinstance(extra, dict):
            return None

        line_no = extra.get("line_no")
        if line_no is None:
            return None

        dst = item.get_dst()
        if not dst or dst == item.get_src():
            return None

        return RenpyStringEntry(
            source=item.get_src(),
            translation=dst,
            line_no=int(line_no),
            tag=extra.get("tag"),
            format_type=extra.get("format", ""),
        )

    def _load_extra(self, extra_field: str | Dict) -> Optional[Dict]:
        if isinstance(extra_field, dict):
            return extra_field
        if isinstance(extra_field, str) and extra_field.strip():
            try:
                return json.loads(extra_field)
            except Exception:
                return None
        return None
