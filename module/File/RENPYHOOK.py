from __future__ import annotations

import json
from pathlib import Path
from typing import List

from base.Base import Base
from module.Cache.CacheItem import CacheItem
from module.Config import Config
from module.Extract.ReplaceGenerator import (
    HOOK_MANIFEST,
    MISS_DIR,
    build_replace_pairs_from_entries,
    collect_hook_translation_entries,
    write_replace_script,
)
from module.Extract.SimpleRpyExtractor import SimpleRpyExtractor


class RENPYHOOK(Base):
    """Ren'Py replace_text supplement reader/writer."""

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config

    def _resolve_target_path(self) -> Path:
        target = str(
            getattr(self.config, "renpy_game_folder", "")
            or getattr(self.config, "input_folder", "")
            or ""
        ).strip()
        if target == "":
            raise RuntimeError("补全翻译缺少游戏目录")
        return Path(target)

    def _resolve_tl_dir(self, target_path: Path) -> Path:
        configured_tl = str(getattr(self.config, "renpy_tl_folder", "") or "").strip()
        if configured_tl != "":
            return Path(configured_tl)

        if target_path.parent.name.lower() == "tl":
            return target_path
        if target_path.name.lower() == "tl":
            return target_path / "chinese"

        game_dir = SimpleRpyExtractor.get_game_dir(target_path)
        return game_dir / "tl" / "chinese"

    def _resolve_hook_output_path(self, target_path: Path) -> Path:
        return self._resolve_tl_dir(target_path) / "replace_text_auto.rpy"

    def _resolve_manifest_path(self, target_path: Path) -> Path:
        return self._resolve_tl_dir(target_path) / MISS_DIR / HOOK_MANIFEST

    def read_from_path(self, abs_paths: List[str]) -> List[CacheItem]:
        del abs_paths

        target_path = self._resolve_target_path()
        tl_dir = self._resolve_tl_dir(target_path)
        tl_name = tl_dir.name or "chinese"

        entries, stats = collect_hook_translation_entries(
            target_path,
            tl_name,
            write_manifest=True,
            auto_update_glossary=True,
        )

        items: List[CacheItem] = []
        rel_output = Path("tl") / tl_name / "replace_text_auto.rpy"
        for index, entry in enumerate(entries, start=1):
            items.append(
                CacheItem.from_dict(
                    {
                        "src": entry.get("src", ""),
                        "dst": entry.get("dst", ""),
                        "row": index,
                        "file_type": CacheItem.FileType.RENPYHOOK,
                        "file_path": str(rel_output).replace("\\", "/"),
                        "text_type": CacheItem.TextType.RENPY,
                        "status": entry.get("status", Base.TranslationStatus.UNTRANSLATED),
                        "extra_field": {
                            "renpy_hook": {
                                "prefilled": bool(entry.get("prefilled", False)),
                                "manifest_path": stats.get("manifest_path", ""),
                                "hook_output_path": stats.get("hook_output_path", ""),
                            }
                        },
                    }
                )
            )

        self.info(
            f"[SUPPLEMENT] 已生成待翻译条目 {len(items)} 条，"
            f"术语预填 {int(stats.get('auto_filled_count', 0) or 0)} 条"
        )
        return items

    def write_to_path(self, items: List[CacheItem]) -> None:
        target_items = [
            item for item in items if item.get_file_type() == CacheItem.FileType.RENPYHOOK
        ]
        if not target_items:
            return

        target_path = self._resolve_target_path()
        output_path = self._resolve_hook_output_path(target_path)
        manifest_path = self._resolve_manifest_path(target_path)
        tl_name = output_path.parent.name or "chinese"

        pairs = build_replace_pairs_from_entries(target_items)
        if pairs:
            write_replace_script(
                output_path,
                pairs,
                language=tl_name,
                use_translate_python=True,
                wrap_existing=True,
            )
        elif output_path.exists():
            output_path.unlink()

        self._update_manifest_result(manifest_path, target_items, output_path, len(pairs))
        self._write_report(target_items, output_path, len(pairs))

        if pairs:
            self.info(f"[SUPPLEMENT] 已生成 replace_text hook: {output_path} ({len(pairs)} 条)")
        else:
            self.info(f"[SUPPLEMENT] 未发现有效译文，已清理自动 hook: {output_path}")

    def _update_manifest_result(
        self,
        manifest_path: Path,
        items: List[CacheItem],
        output_path: Path,
        pair_count: int,
    ) -> None:
        payload: dict = {}
        if manifest_path.exists():
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                payload = {}

        payload["translated_count"] = sum(
            1
            for item in items
            if isinstance(item.get_dst(), str)
            and item.get_dst() != ""
            and item.get_dst() != item.get_src()
        )
        payload["total_count"] = len(items)
        payload["pair_count"] = pair_count
        payload["hook_output_path"] = str(output_path)
        payload["hook_exists"] = output_path.exists()

        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _write_report(
        self,
        items: List[CacheItem],
        output_path: Path,
        pair_count: int,
    ) -> None:
        report_path = Path(self.config.output_folder) / "writeback_report_renpy_hook.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "hook_output_path": str(output_path),
            "items": len(items),
            "translated_items": sum(
                1
                for item in items
                if isinstance(item.get_dst(), str)
                and item.get_dst() != ""
                and item.get_dst() != item.get_src()
            ),
            "pair_count": pair_count,
            "applied": pair_count,
            "skipped": max(0, len(items) - pair_count),
        }
        report_path.write_text(
            json.dumps([report], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
