"""Translation import/export helpers using JSON payloads."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from base.LogManager import LogManager

logger = LogManager.get()


def _build_metadata(translations: Dict[str, List[Dict]], extra: Optional[Dict] = None) -> Dict:
    total_files = len(translations)
    total_entries = sum(len(items) for items in translations.values())
    metadata: Dict = {
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "total_files": total_files,
        "total_entries": total_entries,
        "format": "renpybox-translations-json",
        "version": "1.0",
    }
    if extra:
        metadata.update(extra)
    return metadata


def _normalise_entry(entry: Dict) -> Dict:
    return {
        "line": entry.get("line", 0),
        "original": entry.get("original", ""),
        "translation": entry.get("translation", ""),
        "type": entry.get("type", "dialogue"),
        "status": entry.get("status", "pending"),
        "note": entry.get("note", ""),
        "identifier": entry.get("identifier", ""),
    }


def _escape_rpy_string(value: str) -> str:
    return (
        (value or "")
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "\\n")
    )


class JsonExporter:
    """Export translation entries into a structured JSON file."""

    def export(
        self,
        translations: Dict[str, List[Dict]],
        output_path: str,
        include_metadata: bool = True,
    ) -> bool:
        try:
            payload = {
                "translations": {file_path: [
                    _normalise_entry(item) for item in items
                ] for file_path, items in translations.items()}
            }
            if include_metadata:
                payload["meta"] = _build_metadata(translations)

            output = Path(output_path)
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("w", encoding="utf-8") as writer:
                json.dump(payload, writer, ensure_ascii=False, indent=2)

            logger.info(f"JSON 导出成功: {output}")
            return True
        except Exception as exc:
            logger.error(f"JSON 导出失败: {exc}", exc)
            return False


class JsonImporter:
    """Load translation entries from a JSON file."""

    def import_translations(self, json_path: str) -> Dict[str, List[Dict]]:
        try:
            path = Path(json_path)
            if not path.exists():
                raise FileNotFoundError(f"文件不存在: {json_path}")

            with path.open("r", encoding="utf-8") as reader:
                payload = json.load(reader)

            if isinstance(payload, dict) and "translations" in payload:
                raw = payload.get("translations", {})
            else:
                raw = payload

            if isinstance(raw, list):
                translations: Dict[str, List[Dict]] = {}
                for item in raw:
                    if not isinstance(item, dict):
                        continue
                    file_name = str(item.get("file") or item.get("name") or "")
                    entries = item.get("entries")
                    if not file_name or not isinstance(entries, list):
                        continue
                    translations[file_name] = [_normalise_entry(entry) for entry in entries if isinstance(entry, dict)]
            elif isinstance(raw, dict):
                translations = {
                    str(file_name): [_normalise_entry(entry) for entry in entries if isinstance(entry, dict)]
                    for file_name, entries in raw.items()
                    if isinstance(entries, list)
                }
            else:
                translations = {}

            logger.info(f"JSON 导入成功: {json_path}，共 {len(translations)} 个文件")
            return translations
        except Exception as exc:
            logger.error(f"JSON 导入失败: {exc}", exc)
            return {}

    def apply_translations(
        self,
        translations: Dict[str, List[Dict]],
        game_dir: str,
        target_language: str = "chinese",
        backup: bool = True,
    ) -> bool:
        try:
            logger.info("开始应用 JSON 翻译到游戏文件")
            project_path = Path(game_dir)
            if not project_path.exists():
                raise FileNotFoundError(f"游戏目录不存在: {game_dir}")

            tl_dir = project_path / "game" / "tl" / target_language
            tl_dir.mkdir(parents=True, exist_ok=True)

            seen_global: set[str] = set()
            dup_count = 0

            for file_name, items in translations.items():
                target = tl_dir / file_name
                target.parent.mkdir(parents=True, exist_ok=True)

                if backup and target.exists():
                    backup_path = target.with_suffix(target.suffix + ".bak")
                    shutil.copy2(target, backup_path)
                    logger.info(f"已备份: {backup_path}")

                content_lines = [
                    "# Generated by RenpyBox JSON import",
                    "# Source file: " + str(file_name),
                    "",
                    f"translate {target_language} strings:",
                    "",
                ]

                for item in items:
                    original_raw = item.get("original") or ""
                    if original_raw in seen_global:
                        dup_count += 1
                        continue
                    seen_global.add(original_raw)

                    original = _escape_rpy_string(original_raw)
                    translation = _escape_rpy_string(
                        item.get("translation") or item.get("original") or ""
                    )
                    line_number = item.get("line", "?")
                    content_lines.append(f"    # Line {line_number}")
                    content_lines.append(f"    old \"{original}\"")
                    content_lines.append(f"    new \"{translation}\"")
                    content_lines.append("")

                target.write_text("\n".join(content_lines), encoding="utf-8")
                logger.info(f"已应用翻译: {target}")

            if dup_count > 0:
                logger.warning(f"跳过 {dup_count} 条重复原文（跨文件只保留首次出现的 old），避免 Ren'Py 重复翻译报错")

            logger.info("JSON 翻译应用完成")
            return True
        except Exception as exc:
            logger.error(f"应用翻译失败: {exc}", exc)
            return False


# Backward compatibility aliases -------------------------------------------------
ExcelExporter = JsonExporter
ExcelImporter = JsonImporter
