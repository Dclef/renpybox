from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from base.Base import Base
from module.Cache.CacheItem import CacheItem
from module.Config import Config
from module.Extract.ReplaceGenerator import extract_names_from_game
from module.Text.SkipRules import should_skip_text
from module.Workbench.WorkbenchData import build_character_id, normalize_text, normalize_text_list


@dataclass
class CharacterCandidate:
    """角色候选数据。"""

    name: str
    aliases: list[str] = field(default_factory = list)
    match_keywords: list[str] = field(default_factory = list)
    sample_lines: list[str] = field(default_factory = list)
    related_names: list[str] = field(default_factory = list)
    name_translation: str = ""
    sample_count: int = 0
    low_confidence: bool = False

    def as_card_seed(self) -> dict[str, Any]:
        """转换为角色卡草稿。"""
        prompt_notes = "低置信度候选：样本文本较少，请手动核对。"
        if self.low_confidence is False:
            prompt_notes = ""
        return {
            "id": build_character_id(self.name),
            "name": self.name,
            "aliases": self.aliases,
            "name_translation": self.name_translation,
            "match_keywords": normalize_text_list([self.name] + self.match_keywords),
            "identity": "",
            "personality": "",
            "speech_style": "",
            "relationship_notes": "",
            "prompt_notes": prompt_notes,
            "sample_lines": self.sample_lines[:12],
            "enabled": True,
            "is_primary": False,
        }


@dataclass
class ProjectCharacterScanResult:
    """项目角色扫描结果。"""

    names: set[str] = field(default_factory = set)
    preserves: set[str] = field(default_factory = set)
    speaker_samples: dict[str, list[str]] = field(default_factory = dict)
    co_occurrence: dict[str, list[str]] = field(default_factory = dict)


class CharacterScanner(Base):
    """角色名、样本台词与共现关系扫描器。"""

    RE_CHARACTER_CALL = re.compile(
        r"(?:define\s+)?(?P<var>[A-Za-z_]\w*)\s*=\s*Character\s*\(\s*(?:_\(\s*)?(?P<quote>['\"])(?P<name>.*?)(?P=quote)",
        re.MULTILINE,
    )
    RE_DIALOGUE_LINE = re.compile(
        r"^\s*(?P<speaker>[A-Za-z_]\w*)\s+(?P<quote>\"(?:\\.|[^\"])*\"|'(?:\\.|[^'])*')",
        re.MULTILINE,
    )
    RE_VARIABLE_IN_TEXT = re.compile(r"\[(\w+)\]")

    def __init__(self) -> None:
        super().__init__()

    @staticmethod
    def clean_character_name(value: str) -> str:
        """清洗角色名。"""
        text = normalize_text(value)
        if text == "":
            return ""
        text = text.replace('\\"', '"').replace("\\'", "'").replace("\\\\", "\\").strip()
        return text

    @staticmethod
    def looks_like_character_name(name: str) -> bool:
        """粗略判断是否像角色名。"""
        if not name:
            return False
        if any(char.isupper() for char in name):
            return True
        if any(ord(char) > 127 and char.isalpha() for char in name):
            return True
        return False

    @staticmethod
    def normalize_sample_line(text: str) -> str:
        """清洗样本台词。"""
        value = normalize_text(text)
        if value == "":
            return ""
        value = value.replace("\\n", " ").replace("\n", " ").strip()
        value = re.sub(r"\s+", " ", value)
        return value[:200]

    def scan_project(self, project_root: str | Path) -> ProjectCharacterScanResult:
        """扫描项目根目录。"""
        root = Path(project_root)
        if root.name.lower() == "game":
            root = root.parent

        game_dir = root / "game"
        result = ProjectCharacterScanResult()
        if game_dir.exists() is False:
            return result

        try:
            extra_names = extract_names_from_game(game_dir)
            for name in extra_names:
                cleaned = self.clean_character_name(name)
                if cleaned and should_skip_text(cleaned) is False:
                    result.names.add(cleaned)
        except Exception as exc:
            self.warning(f"从 UI 控件提取角色名失败: {exc}", console = False)

        speaker_samples: dict[str, list[str]] = defaultdict(list)
        co_counters: dict[str, Counter] = defaultdict(Counter)

        for path in game_dir.rglob("*.rpy"):
            if "tl" in {part.lower() for part in path.parts}:
                continue
            try:
                content = path.read_text(encoding = "utf-8", errors = "ignore")
            except Exception:
                continue

            speaker_map: dict[str, str] = {}
            file_speakers: list[str] = []
            for match in self.RE_CHARACTER_CALL.finditer(content):
                raw_name = match.group("name") or ""
                name = self.clean_character_name(raw_name)
                if name.startswith("[") and name.endswith("]"):
                    result.preserves.add(name)
                    continue
                if name == "" or should_skip_text(name) or self.looks_like_character_name(name) is False:
                    continue
                speaker_map[match.group("var")] = name
                result.names.add(name)

            for var_name in self.RE_VARIABLE_IN_TEXT.findall(content):
                result.preserves.add(f"[{var_name}]")

            for match in self.RE_DIALOGUE_LINE.finditer(content):
                speaker_var = match.group("speaker") or ""
                speaker_name = speaker_map.get(speaker_var, "")
                if speaker_name == "":
                    continue

                quoted = match.group("quote") or ""
                text = quoted[1:-1] if len(quoted) >= 2 else quoted
                sample = self.normalize_sample_line(text)
                if sample == "" or should_skip_text(sample):
                    continue

                speaker_samples[speaker_name].append(sample)
                file_speakers.append(speaker_name)

            unique_speakers = list(dict.fromkeys(file_speakers))
            for speaker in unique_speakers:
                for other in unique_speakers:
                    if other != speaker:
                        co_counters[speaker][other] += 1

        result.speaker_samples = {
            key: normalize_text_list(values)[:24]
            for key, values in speaker_samples.items()
            if key
        }
        result.co_occurrence = {
            key: [name for name, _ in counter.most_common(8)]
            for key, counter in co_counters.items()
            if key
        }
        return result

    def collect_glossary_character_names(self, config: Config) -> dict[str, str]:
        """从术语表中提取角色类条目。"""
        result: dict[str, str] = {}
        for item in getattr(config, "glossary_data", []) or []:
            if not isinstance(item, dict):
                continue

            src = self.clean_character_name(item.get("src", ""))
            if src == "":
                continue

            item_type = normalize_text(item.get("type", ""))
            item_info = normalize_text(item.get("info", ""))
            if "角色" not in item_type and "角色" not in item_info and "角色名" not in item_info:
                continue

            result[src] = normalize_text(item.get("dst", ""))
        return result

    def build_candidates(
        self,
        config: Config,
        items: list[CacheItem],
        project_root: str | Path | None,
    ) -> list[CharacterCandidate]:
        """基于配置、缓存条目和项目源码构建角色候选。"""
        scan = self.scan_project(project_root) if project_root else ProjectCharacterScanResult()
        glossary_names = self.collect_glossary_character_names(config)

        item_samples: dict[str, list[str]] = defaultdict(list)
        item_counts: Counter[str] = Counter()
        item_co: dict[str, Counter[str]] = defaultdict(Counter)
        file_speakers: dict[str, list[str]] = defaultdict(list)

        for item in items:
            name = self.clean_character_name(item.get_first_name_src())
            if name == "" or should_skip_text(name):
                continue

            src = self.normalize_sample_line(item.get_src())
            item_counts[name] += 1
            file_speakers[item.get_file_path()].append(name)
            if src != "":
                item_samples[name].append(src)

        for names in file_speakers.values():
            unique_names = list(dict.fromkeys(names))
            for name in unique_names:
                for other in unique_names:
                    if other != name:
                        item_co[name][other] += 1

        names: set[str] = set(glossary_names.keys())
        names.update(scan.names)
        names.update({name for name in item_counts if name})
        names = {
            self.clean_character_name(name)
            for name in names
            if self.clean_character_name(name) != ""
        }

        candidates: list[CharacterCandidate] = []
        for name in sorted(names, key = lambda value: (-item_counts.get(value, 0), value.casefold())):
            sample_lines = normalize_text_list(
                scan.speaker_samples.get(name, []) + item_samples.get(name, []),
                unique = True,
            )[:12]

            co_names = normalize_text_list(
                scan.co_occurrence.get(name, []) + [other for other, _ in item_co.get(name, Counter()).most_common(8)]
            )

            candidate = CharacterCandidate(
                name = name,
                aliases = [],
                match_keywords = [name],
                sample_lines = sample_lines[:12],
                related_names = co_names[:8],
                name_translation = glossary_names.get(name, ""),
                sample_count = len(sample_lines),
                low_confidence = len(sample_lines) < 3,
            )
            candidates.append(candidate)

        return candidates
