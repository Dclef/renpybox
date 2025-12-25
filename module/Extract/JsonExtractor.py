
import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from base.LogManager import LogManager
from module.Renpy.json_handler import JsonExporter
from module.Translate.RenpySourceTranslator import RenpySourceParser, LineType, TranslationEntry

class JsonExtractor:
    """
    Extracts Ren'Py script files (.rpy) into JSON format.
    Each .rpy file is extracted to a corresponding .json file.
    """

    def __init__(self):
        self.logger = LogManager.get()
        self.parser = RenpySourceParser()
        self.exporter = JsonExporter()

    def _line_type_to_label(self, entry: TranslationEntry) -> str:
        mapping = {
            LineType.DIALOGUE: "dialogue",
            LineType.NARRATION: "narration",
            LineType.MENU_OPTION: "menu",
            LineType.STRING_BLOCK: "string",
        }
        return mapping.get(entry.line_type, "text")

    def extract_file(self, file_path: Path, output_path: Path, entry_key: Optional[str] = None) -> bool:
        """
        Extracts a single .rpy file to .json.
        """
        try:
            parsed_entries = self.parser.parse_file(file_path)
            if not parsed_entries:
                return False

            entries: List[Dict] = []
            last_old_text: Optional[str] = None

            for entry in parsed_entries:
                text = entry.text.strip()
                if not entry.needs_translation or not text:
                    if entry.line_type != LineType.STRING_BLOCK:
                        last_old_text = None
                    continue

                if entry.line_type == LineType.STRING_BLOCK:
                    if entry.string_is_old:
                        last_old_text = entry.text
                        continue

                    original_text = last_old_text if last_old_text is not None else entry.text
                    translation_text = entry.text if last_old_text is not None else ""

                    entries.append({
                        "line": entry.line_number,
                        "type": "string",
                        "original": original_text,
                        "translation": translation_text,
                        "context": entry.original_line.rstrip("\n"),
                    })
                    last_old_text = None
                    continue

                last_old_text = None
                item = {
                    "line": entry.line_number,
                    "type": self._line_type_to_label(entry),
                    "original": entry.text,
                    "context": entry.original_line.rstrip("\n"),
                }

                if entry.speaker:
                    item["speaker"] = entry.speaker
                if entry.menu_hints:
                    item["hint"] = entry.menu_hints
                if entry.menu_condition:
                    item["condition"] = entry.menu_condition
                if entry.protected_tags:
                    item["protected"] = entry.protected_tags

                entries.append(item)

            if last_old_text:
                entries.append({
                    "line": 0,
                    "type": "string",
                    "original": last_old_text,
                    "translation": "",
                    "context": "dangling old string",
                })

            if not entries:
                return False

            # Prepare data for export
            # JsonExporter expects Dict[str, List[Dict]]
            # But we want to export one file.
            # We can construct a dict with one key (the file name)
            
            translations = {str(entry_key or file_path.name): entries}
            
            # Export
            return self.exporter.export(translations, str(output_path), include_metadata=True)

        except Exception as e:
            self.logger.error(f"Failed to extract {file_path}: {e}")
            return False

    def extract_directory(self, input_dir: Path, output_dir: Path):
        """
        Extracts all .rpy files in input_dir to .json files in output_dir.
        """
        input_dir = Path(input_dir)
        output_dir = Path(output_dir)
        
        if not input_dir.exists():
            self.logger.error(f"Input directory does not exist: {input_dir}")
            return

        output_dir.mkdir(parents=True, exist_ok=True)

        for rpy_file in input_dir.rglob('*.rpy'):
            # Calculate relative path to maintain structure
            rel_path = rpy_file.relative_to(input_dir)
            json_path = output_dir / rel_path.with_suffix('.rpy.json')
            
            self.logger.info(f"Extracting {rpy_file} to {json_path}")
            self.extract_file(rpy_file, json_path, rel_path.as_posix())
