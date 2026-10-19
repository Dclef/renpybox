from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from base.Base import Base
from module.Cache.CacheItem import CacheItem
from module.Config import Config
from module.Text.SkipRules import should_skip_text
from module.Workbench.WorkbenchData import build_character_id, normalize_text, normalize_text_list

ScanProgress = Callable[[str], None]


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
    speaker_counts: dict[str, int] = field(default_factory = dict)
    # 角色名 -> 源码文本里真实出现过的 `[var]` 插值（var 是该角色的 Character 变量）
    speaker_variables: dict[str, list[str]] = field(default_factory = dict)
    file_count: int = 0
    line_count: int = 0


class CharacterScanner(Base):
    """角色名、样本台词与共现关系扫描器。

    关键点：Ren'Py 里 `x = Character("Name")` 的定义常常集中写在
    characters.rpy，而台词散落在各个 events/*.rpy 文件里。早期实现按文件
    建立 var→name 映射，导致绝大多数台词找不到说话人、样本数恒为 0；
    这里改为**全局建立映射**后再逐文件抽台词。
    """

    RE_CHARACTER_CALL = re.compile(
        r"(?:define\s+)?(?P<var>[A-Za-z_]\w*)\s*=\s*Character\s*\(\s*(?:_\(\s*)?(?P<quote>['\"])(?P<name>.*?)(?P=quote)",
        re.MULTILINE,
    )
    RE_DIALOGUE_LINE = re.compile(
        r"^[ \t]*(?P<speaker>[A-Za-z_]\w*)"
        r"(?:[ \t]+(?:@|[A-Za-z_]\w*|-[A-Za-z_]\w*))*[ \t]+"
        r"(?P<quote>\"(?:\\.|[^\"\n])*\"|'(?:\\.|[^'\n])*')",
        re.MULTILINE,
    )
    # `define airi = mom`：把已有 Character 变量换个名字引用。
    RE_CHARACTER_ALIAS = re.compile(
        r"^\s*define\s+(?P<var>[A-Za-z_]\w*)\s*=\s*(?P<target>[A-Za-z_]\w*)\s*(?:#.*)?$",
        re.MULTILINE,
    )
    RE_VARIABLE_IN_TEXT = re.compile(r"\[(\w+)\]")
    RE_DIGITS = re.compile(r"\d")

    # 扫描结果缓存：路径 -> (指纹, 结果)。指纹取所有 rpy 的 mtime+size，
    # 项目没改动时重复分析（世界观/角色卡多次生成）不再重扫源码。
    _CACHE: dict[str, tuple[tuple, ProjectCharacterScanResult]] = {}
    _CACHE_LIMIT = 8

    # 单人角色最多保留多少条台词样本（从全部去重台词里按源码位置均匀抽取）
    MAX_SAMPLES_PER_NAME = 24
    # 角色候选携带的样本数
    CANDIDATE_SAMPLE_LIMIT = 12
    # 低于该台词数视为低置信度
    LOW_CONFIDENCE_LINES = 3
    # 通用身份标签：它们确实是「说话人」，但做成角色卡没有意义。
    # 注意保留 Mom / Mama 这类在这两款游戏里真的是具体角色的称呼。
    _GENERIC_SPEAKER_LABELS = frozenset(
        {
            "soldier",
            "soldiers",
            "woman",
            "women",
            "man",
            "men",
            "villager",
            "villagers",
            "unknown",
            "nun",
            "hunter",
            "fatty",
            "master",
            "everyone",
            "narrator",
            "voice",
            "crowd",
            "guard",
            "maid",
            "shopkeeper",
            "stranger",
            "passerby",
            "school girls",
            "tv",
            "television",
            "radio",
            "phone",
            "computer",
            "screen",
        }
    )

    def __init__(self) -> None:
        super().__init__()

    # Ren'Py 富文本标签（{b}Airi{/b} / {color=#fff}Airi{/color}）与转义花括号
    RE_FORMAT_TAG = re.compile(r"\{[^{}]*\}")
    RE_ESCAPED_BRACE = re.compile(r"\{\{|\}\}")

    @classmethod
    def strip_format_tags(cls, value: str) -> str:
        """剥离 Ren'Py 富文本标签，保留可读文本。"""
        if not value or "{" not in value:
            return value
        text = cls.RE_ESCAPED_BRACE.sub("", value)
        text = cls.RE_FORMAT_TAG.sub("", text)
        return text.strip()

    @classmethod
    def clean_character_name(cls, value: str) -> str:
        """清洗角色名。"""
        text = normalize_text(value)
        if text == "":
            return ""
        text = text.replace('\\"', '"').replace("\\'", "'").replace("\\\\", "\\")
        text = cls.strip_format_tags(text).strip()
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

    @staticmethod
    def select_evenly(values: list[str], limit: int) -> list[str]:
        """按位置均匀抽取 limit 条并保持原顺序，覆盖开头、中段和结尾。"""
        if limit <= 0:
            return []
        if len(values) <= limit:
            return list(values)
        if limit == 1:
            return [values[0]]
        last = len(values) - 1
        indexes = sorted({round(index * last / (limit - 1)) for index in range(limit)})
        return [values[index] for index in indexes]

    # ------------------------------------------------------------------ scan
    @classmethod
    def _iter_source_files(cls, game_dir: Path):
        """遍历源码文件，排除 game 内部的 tl / cache 等运行时目录（不看祖先目录名）。"""
        excluded = {"tl", "cache", "__pycache__"}
        for path in game_dir.rglob("*.rpy"):
            parts = {part.casefold() for part in path.relative_to(game_dir).parts[:-1]}
            if parts & excluded:
                continue
            yield path

    @classmethod
    def _fingerprint(cls, files: list[Path]) -> tuple:
        """文件指纹：数量 + 每个文件路径/纳秒修改时间/大小的有序快照。"""
        entries: list[tuple[str, int, int]] = []
        for path in files:
            try:
                stat = path.stat()
            except OSError:
                continue
            entries.append((path.as_posix(), stat.st_mtime_ns, stat.st_size))
        entries.sort()
        return (len(files), tuple(entries))

    def scan_project(
        self,
        project_root: str | Path,
        progress: ScanProgress | None = None,
    ) -> ProjectCharacterScanResult:
        """扫描项目根目录，返回角色名、样本台词与共现关系。"""
        root = Path(project_root)
        if root.name.lower() == "game":
            root = root.parent

        game_dir = root / "game"
        result = ProjectCharacterScanResult()
        if game_dir.exists() is False:
            return result

        files = sorted(self._iter_source_files(game_dir))
        result.file_count = len(files)
        cache_key = str(game_dir.resolve())
        fingerprint = self._fingerprint(files)

        cached = self._CACHE.get(cache_key)
        if cached is not None and cached[0] == fingerprint:
            if progress is not None:
                progress("已复用上次的角色扫描结果")
            self.info(f"[CharacterScanner] 复用缓存：{len(cached[1].names)} 个角色名")
            return cached[1]

        if progress is not None:
            progress(f"正在读取 {len(files)} 个脚本文件…")

        # 第一遍：建立全局 var -> 角色名映射，同时缓存文件内容避免二次读盘。
        contents: dict[Path, str] = {}
        speaker_map: dict[str, str] = {}
        alias_pairs: list[tuple[str, str]] = []
        report_step = max(1, len(files) // 8)
        for position, path in enumerate(files, start = 1):
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            contents[path] = content
            for match in self.RE_CHARACTER_CALL.finditer(content):
                raw_name = match.group("name") or ""
                name = self.clean_character_name(raw_name)
                if name == "":
                    continue
                if name.startswith("[") and name.endswith("]"):
                    result.preserves.add(name)
                    continue
                if should_skip_text(name) or self.looks_like_character_name(name) is False:
                    continue
                if self._is_low_value_name(name):
                    continue
                speaker_map.setdefault(match.group("var"), name)
                result.names.add(name)
            alias_pairs.extend(
                (match.group("var"), match.group("target"))
                for match in self.RE_CHARACTER_ALIAS.finditer(content)
            )
            if progress is not None and (position % report_step == 0 or position == len(files)):
                progress(f"正在读取脚本 {position}/{len(files)}，已识别 {len(result.names)} 个角色")

        # 别名可能先于目标定义或成链（a = b, b = mom），多轮解析到稳定为止。
        for _ in range(4):
            resolved = False
            for var, target in alias_pairs:
                if var not in speaker_map and target in speaker_map:
                    speaker_map[var] = speaker_map[target]
                    resolved = True
            if not resolved:
                break

        if progress is not None:
            progress(f"已建立 {len(speaker_map)} 个角色映射，正在抽取台词…")

        # 第二遍：全局映射抽取台词与共现关系。
        # 先按源码顺序收集每个角色全部去重台词，最后再均匀抽样；只留前 N 条会让
        # 样本全部来自第一个场景（DarkMagic 这类项目的台词散落在几十个文件里）。
        speaker_samples: dict[str, dict[str, str]] = defaultdict(dict)
        speaker_counts: Counter[str] = Counter()
        co_counters: dict[str, Counter] = defaultdict(Counter)
        text_variables: set[str] = set()
        total_files = max(1, len(contents))
        step = max(1, total_files // 8)

        for position, (path, content) in enumerate(contents.items(), start = 1):
            for var_name in self.RE_VARIABLE_IN_TEXT.findall(content):
                result.preserves.add(f"[{var_name}]")
                text_variables.add(var_name)

            file_speakers: list[str] = []
            for match in self.RE_DIALOGUE_LINE.finditer(content):
                speaker_var = match.group("speaker") or ""
                speaker_name = speaker_map.get(speaker_var, "")
                if speaker_name == "":
                    continue

                result.line_count += 1
                speaker_counts[speaker_name] += 1

                quoted = match.group("quote") or ""
                text = quoted[1:-1] if len(quoted) >= 2 else quoted
                sample = self.normalize_sample_line(text)
                if sample == "" or should_skip_text(sample):
                    continue

                speaker_samples[speaker_name].setdefault(sample.casefold(), sample)
                if speaker_name not in file_speakers:
                    file_speakers.append(speaker_name)

            for speaker in file_speakers:
                for other in file_speakers:
                    if other != speaker:
                        co_counters[speaker][other] += 1
            if progress is not None and (position % step == 0 or position == total_files):
                progress(
                    f"正在抽取台词 {position}/{total_files}，"
                    f"已累计 {result.line_count} 行、{len(speaker_counts)} 个角色"
                )

        # 有台词的说话人才是角色；只在 Character() 里出现、从未开口的多半是
        # 地名/界面标签（Dark Forest / The Unity / Time Recorder）。
        result.names &= set(speaker_counts)

        result.speaker_samples = {
            key: self.select_evenly(list(values.values()), self.MAX_SAMPLES_PER_NAME)
            for key, values in speaker_samples.items()
            if key
        }
        variables: dict[str, list[str]] = defaultdict(list)
        for var_name, speaker_name in speaker_map.items():
            if var_name in text_variables and speaker_name in result.names:
                variables[speaker_name].append(f"[{var_name}]")
        result.speaker_variables = {key: sorted(values) for key, values in variables.items()}
        result.co_occurrence = {
            key: [name for name, _ in counter.most_common(8)]
            for key, counter in co_counters.items()
            if key
        }
        result.speaker_counts = dict(speaker_counts)

        if progress is not None:
            progress(f"已抽取 {result.line_count} 行台词，识别 {len(result.names)} 个角色")

        self.info(
            f"[CharacterScanner] 扫描完成：{result.file_count} 个文件 / "
            f"{result.line_count} 行台词 / {len(result.names)} 个角色"
        )
        self._remember(cache_key, fingerprint, result)
        return result

    def _remember(
        self,
        cache_key: str,
        fingerprint: tuple,
        result: ProjectCharacterScanResult,
    ) -> None:
        """写入扫描缓存，超出上限时淘汰最早写入的项。"""
        self._CACHE[cache_key] = (fingerprint, result)
        while len(self._CACHE) > self._CACHE_LIMIT:
            oldest = next(iter(self._CACHE))
            if oldest == cache_key:
                break
            self._CACHE.pop(oldest, None)

    @classmethod
    def _is_low_value_name(cls, name: str) -> bool:
        """过滤明显不是角色名的标签（界面文案、语气词、带编号的群众演员）。

        注意：这里**不**套用通用停用词表。Mom / Mama / Fatty 这类称呼在
        Ren'Py 游戏里常常是具体角色的固定标签，被停用词误杀会让角色卡缺人；
        真正要挡的是 Soldier / Woman / Unknown 这种「群体或占位」标签。
        """
        cleaned = name.strip()
        if cleaned == "":
            return True
        if cls.RE_DIGITS.search(cleaned):
            return True
        if any(char in cleaned for char in "#[]{}<>"):
            return True
        folded = cleaned.casefold()
        if folded in cls._GENERIC_SPEAKER_LABELS:
            return True
        # 群体编号标签（School Girls #1 已在数字规则里被挡，这里兜底 "School Girls"）。
        if folded.startswith("school girl"):
            return True
        return False

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
        progress: ScanProgress | None = None,
    ) -> list[CharacterCandidate]:
        """基于配置、缓存条目和项目源码构建角色候选。"""
        scan = (
            self.scan_project(project_root, progress = progress)
            if project_root
            else ProjectCharacterScanResult()
        )
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

        # 源码模式解析出的条目没有 name_src（item_counts 全为 0），排序必须以
        # 源码扫描的真实台词行数为准，否则世界观拿到的「高频角色」只是字母序。
        def line_count(value: str) -> int:
            return max(scan.speaker_counts.get(value, 0), item_counts.get(value, 0))

        limit = self.CANDIDATE_SAMPLE_LIMIT
        candidates: list[CharacterCandidate] = []
        for name in sorted(names, key = lambda value: (-line_count(value), value.casefold())):
            sample_lines = self.select_evenly(normalize_text_list(scan.speaker_samples.get(name, [])), limit)
            if len(sample_lines) < limit:
                seen = {line.casefold() for line in sample_lines}
                extra = [line for line in normalize_text_list(item_samples.get(name, [])) if line.casefold() not in seen]
                sample_lines += self.select_evenly(extra, limit - len(sample_lines))

            co_names = normalize_text_list(
                scan.co_occurrence.get(name, []) + [other for other, _ in item_co.get(name, Counter()).most_common(8)]
            )
            count = line_count(name)

            candidate = CharacterCandidate(
                name = name,
                aliases = [],
                match_keywords = normalize_text_list([name] + scan.speaker_variables.get(name, [])),
                sample_lines = sample_lines,
                related_names = co_names[:8],
                name_translation = glossary_names.get(name, ""),
                sample_count = count,
                low_confidence = max(count, len(sample_lines)) < self.LOW_CONFIDENCE_LINES,
            )
            candidates.append(candidate)

        return candidates
