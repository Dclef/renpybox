import json
import os
from typing import Any, Dict, List

from base.Base import Base
from base.BaseLanguage import BaseLanguage
from module.Cache.CacheItem import CacheItem
from module.Config import Config
from module.Text.SkipRules import should_skip_text


class RENPYTRANSLATIONSJSON(Base):
    """
    解析/写回 RenpyBox 导出的 translations JSON（meta.format = renpybox-translations-json）
    数据结构：
    {
        "translations": {
            "file1.rpy": [
                {"line": 1, "original": "...", "translation": "...", "type": "dialogue", ...},
                ...
            ],
            ...
        },
        "meta": {...}
    }
    """

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self.input_path: str = config.input_folder
        self.output_path: str = config.output_folder
        self.source_language: BaseLanguage.Enum = config.source_language
        self.target_language: BaseLanguage.Enum = config.target_language

    def _is_supported(self, path: str) -> bool:
        try:
            with open(path, "r", encoding="utf-8") as reader:
                data = json.load(reader)
            if isinstance(data, dict) and data.get("meta", {}).get("format") == "renpybox-translations-json":
                return True
            if isinstance(data, dict) and "translations" in data:
                return True
        except Exception:
            return False
        return False

    def read_from_path(self, abs_paths: List[str]) -> List[CacheItem]:
        items: List[CacheItem] = []
        for abs_path in abs_paths:
            if not abs_path.lower().endswith(".json"):
                continue
            if not self._is_supported(abs_path):
                continue
            try:
                with open(abs_path, "r", encoding="utf-8") as reader:
                    data = json.load(reader)
                translations: Dict[str, List[Dict[str, Any]]] = data.get("translations", {}) if isinstance(data, dict) else {}
                for file_name, entries in translations.items():
                    for idx, entry in enumerate(entries):
                        src = entry.get("original", "") or ""
                        dst = entry.get("translation", "") or ""
                        text_type = entry.get("type", "dialogue")
                        if should_skip_text(src):
                            status = Base.TranslationStatus.EXCLUDED
                        elif dst and dst != src:
                            status = Base.TranslationStatus.TRANSLATED_IN_PAST
                        else:
                            status = Base.TranslationStatus.UNTRANSLATED

                        items.append(
                            CacheItem.from_dict(
                                {
                                    "src": src,
                                    "dst": dst or src,
                                    "name_src": None,
                                    "name_dst": None,
                                    "extra_field": entry,
                                    "row": len(items),
                                    "file_type": CacheItem.FileType.KVJSON,
                                    "file_path": file_name,
                                    "text_type": CacheItem.TextType.JSON,
                                    "status": status,
                                }
                            )
                        )
            except Exception as e:
                self.error("读取 translations JSON 失败", e)
        return items

    def write_to_path(self, items: List[CacheItem]) -> None:
        # 只写回通过本格式解析出来的条目
        target_items = [item for item in items if item.get_file_type() == CacheItem.FileType.KVJSON]
        if not target_items:
            return

        grouped: Dict[str, List[CacheItem]] = {}
        for item in target_items:
            grouped.setdefault(item.get_file_path(), []).append(item)

        translations: Dict[str, List[Dict[str, Any]]] = {}
        for file_name, file_items in grouped.items():
            entries: List[Dict[str, Any]] = []
            for item in file_items:
                src = item.get_src()
                dst = item.get_dst()
                extra = item.get_extra_field() or {}
                line = 0
                try:
                    line = int(extra.get("line", 0))
                except Exception:
                    line = 0
                entries.append(
                    {
                        "line": line,
                        "original": src,
                        "translation": dst,
                        "type": extra.get("type", "dialogue"),
                        "status": extra.get("status", "done"),
                        "note": extra.get("note", ""),
                        "identifier": extra.get("identifier", ""),
                    }
                )
            translations[file_name] = entries

        payload = {
            "translations": translations,
            "meta": {
                "format": "renpybox-translations-json",
                "saved_by": "Engine Translator",
            },
        }
        os.makedirs(self.output_path, exist_ok=True)
        target = os.path.join(self.output_path, "translations_engine_output.json")
        with open(target, "w", encoding="utf-8") as writer:
            json.dump(payload, writer, ensure_ascii=False, indent=2)
