from __future__ import annotations

import copy
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

import json_repair as repair

from base.Base import Base
from module.Cache.CacheItem import CacheItem
from module.Cache.CacheManager import CacheManager
from module.Config import Config
from module.Localizer.Localizer import Localizer
from module.Engine.Engine import Engine
from module.Engine.TaskRequester import TaskRequester
from module.Engine import LiveActivity
from module.Engine.RequestProgress import request_progress
from module.File.FileManager import FileManager
from module.Text.SkipRules import is_path_like, is_resource_name
from module.Workbench.AnalysisRequestPolicy import build_analysis_platform
from module.Workbench.CharacterScanner import CharacterCandidate, CharacterScanner
from module.Workbench.WorkbenchData import (
    ANALYSIS_SCOPE_CURRENT,
    ANALYSIS_SCOPE_FULL,
    create_default_character_card,
    normalize_analysis_scope,
    normalize_character_card,
    normalize_character_cards,
    normalize_relation_category,
    normalize_text,
    normalize_text_list,
    normalize_worldbook,
)
from module.Renpy.ProjectPaths import RenpyProjectPaths, resolve_translation_output


@dataclass
class AnalysisResult:
    """AI 分析结果。"""

    scope: str
    worldbook_draft: dict[str, Any]
    character_drafts: list[dict[str, Any]]
    worldbook_raw: str = ""
    character_raw: list[str] = field(default_factory = list)
    source_summary: str = ""


class AnalysisServiceError(RuntimeError):
    """工作台分析异常。"""

    def __init__(self, message: str, *, raw_response: str = "") -> None:
        super().__init__(message)
        self.raw_response = raw_response


class WorkbenchAnalysisService(Base):
    """工作台 AI 分析服务。"""

    SUPPORTED_FORMATS = (
        Base.APIFormat.OPENAI,
        Base.APIFormat.GOOGLE,
        Base.APIFormat.ANTHROPIC,
        Base.APIFormat.SAKURALLM,
    )

    # 角色卡分批请求的并发上限。批次数通常是个位到十几个，
    # 并发 3 是在不触发常见接口速率限制前提下明显缩短总等待时间的档位。
    CHARACTER_BATCH_CONCURRENCY = 3
    CHARACTER_BATCH_SIZE = 8
    # 每个角色写进提示词的样本台词数，以及角色卡最终保留的样本数。
    CHARACTER_PROMPT_SAMPLES = 8
    CHARACTER_SAMPLE_LIMIT = 6
    CHARACTER_DESCRIPTIVE_FIELDS = ("identity", "personality", "speech_style", "relationship_notes")
    NOTE_MISSING_ANALYSIS = "AI 未返回该角色的分析，需手动补全。"
    NOTE_EMPTY_ANALYSIS = "AI 返回的人设字段为空，需手动补全。"
    # 日志里展示的模型思考片段长度。
    THINK_EXCERPT_CHARS = 200
    # 进度回调的重载签名：兼容只接收 message 的旧实现。
    ProgressCallback = Callable[..., None]

    # 全项目源码解析结果缓存（按 game 目录指纹失效），避免连续分析重复解析十几秒。
    FULL_PROJECT_CACHE_LIMIT = 4
    _full_project_cache: dict[str, tuple[tuple[Any, ...], list[CacheItem]]] = {}
    _full_project_cache_lock = threading.Lock()

    # options.rpy 里的 `define config.name = _("Title")` / `build.name = "title"`，只认字面量。
    RE_DECLARED_TITLE = re.compile(
        r"^[ \t]*(?:define[ \t]+)?(?P<key>config\.name|build\.name)[ \t]*=[ \t]*"
        r"(?:_\([ \t]*(?P<wrapped>\"(?:[^\"\\\n]|\\.)*\"|'(?:[^'\\\n]|\\.)*')[ \t]*\)"
        r"|(?P<plain>\"(?:[^\"\\\n]|\\.)*\"|'(?:[^'\\\n]|\\.)*'))"
        r"[ \t]*(?:#.*)?$",
        re.MULTILINE,
    )
    # 世界观代表文本：剧情台词/旁白优先，界面脚本（screens/gui/options）垫底。
    STORY_LINE_TYPES = ("", "DIALOGUE", "NARRATION")
    UI_FILE_TOKENS = frozenset({"screen", "screens", "gui", "options", "option", "preferences", "settings", "config"})
    RE_LINK_TEXT = re.compile(r"\{a=|https?://|www\.|discord\.gg", re.IGNORECASE)
    RE_BARE_PATH = re.compile(r"[^\s]*[/\\][^\s]*")
    RE_TEXT_VARIABLE = re.compile(r"\[[^\[\]\n]*\]")
    RE_SENTENCE_MARK = re.compile(r"[.!?,;:…。！？，、~()（）\"'“”‘’-]")
    # 别名里只有这些称谓/泛称时不能当触发词（Miss / Sister / Master 会命中所有人的台词）。
    GENERIC_ALIAS_WORDS = frozenset(
        {
            "the", "a", "an", "of", "my", "our", "your",
            "mr", "mrs", "ms", "miss", "mister", "sir", "madam", "lady", "lord", "dr", "doctor",
            "king", "queen", "prince", "princess", "master", "mistress", "teacher", "boss",
            "mom", "mother", "mama", "dad", "father", "papa", "sister", "brother", "aunt", "uncle",
            "chan", "san", "kun", "sama", "senpai", "sensei",
        }
    )

    def __init__(self) -> None:
        super().__init__()
        self.scanner = CharacterScanner()
        self.progress_callback: WorkbenchAnalysisService.ProgressCallback | None = None
        self._progress_lock = threading.Lock()
        self._started_at = 0.0
        # 本次分析语料全文，用于核对模型给出的别名是否真的在源码里出现。
        self._evidence_text = ""

    def _report_progress(self, message: str, percent: int | None = None) -> None:
        """记录分析阶段，并把同一信息交给界面显示。

        percent 为 None 时表示该阶段没有可量化的进度（例如等待模型回复），
        此时只更新文案，不推进进度条。
        """
        self.info(f"[Workbench] {message}")
        if self.progress_callback is None:
            return
        callback = self.progress_callback
        with self._progress_lock:
            try:
                if percent is None:
                    callback(message)
                else:
                    callback(message, percent)
            except TypeError:
                # 旧回调只接收 message，退回单参数调用。
                callback(message)

    def _elapsed_hint(self) -> str:
        """把已用时长拼进阶段文案，让等待中的用户知道还在推进。"""
        if self._started_at <= 0:
            return ""
        seconds = max(0, int(time.perf_counter() - self._started_at))
        return Localizer.get().workbench_progress_elapsed.format(
            minutes = seconds // 60,
            seconds = seconds % 60,
        )

    def _report_with_elapsed(self, message: str, percent: int | None = None) -> None:
        """阶段文案 + 已用时间，用于耗时较长的模型等待阶段。"""
        elapsed = self._elapsed_hint()
        if elapsed == "":
            self._report_progress(message, percent)
            return
        self._report_progress(f"{message} · {elapsed}", percent)

    def _log_model_exchange(
        self,
        label: str,
        think: str,
        input_tokens: int,
        output_tokens: int,
        elapsed: float,
    ) -> None:
        """把模型思考片段、token 与耗时写入日志。"""
        thinking = str(think or "").strip()
        if thinking != "":
            excerpt = re.sub(r"\s+", " ", thinking)[: self.THINK_EXCERPT_CHARS]
            self.info(f"[Workbench] {label} 思考片段：{excerpt}…")
        else:
            self.info(f"[Workbench] {label} 未返回思考内容")
        self.info(
            f"[Workbench] {label} 完成：耗时 {elapsed:.1f}s，tokens {input_tokens}/{output_tokens}"
        )

    def ensure_analysis_ready(
        self,
        config: Config,
        *,
        engine_reserved: bool = False,
    ) -> dict[str, Any]:
        """校验分析前置条件。"""
        engine_status = Engine.get().get_status()
        reserved_by_caller = engine_reserved and engine_status == Engine.Status.TESTING
        if engine_status != Engine.Status.IDLE and not reserved_by_caller:
            raise AnalysisServiceError("翻译任务正在运行，暂时不能执行 AI 分析。")

        platform = config.get_platform(config.activate_platform)
        if not platform:
            raise AnalysisServiceError("未找到当前激活接口，请先在接口管理中启用有效接口。")

        api_format = platform.get("api_format")
        if api_format not in self.SUPPORTED_FORMATS:
            raise AnalysisServiceError("当前接口不支持世界观/人设 AI 分析，请切换到大模型接口。")

        model_name = normalize_text(platform.get("model", ""))
        if model_name == "":
            raise AnalysisServiceError("当前接口未配置模型名称。")
        return platform

    def analyze_all(
        self,
        config: Config,
        scope: str,
        *,
        engine_reserved: bool = False,
    ) -> AnalysisResult:
        """生成世界观和角色卡草稿。"""
        scope = normalize_analysis_scope(scope)
        platform = self.ensure_analysis_ready(config, engine_reserved = engine_reserved)
        items, candidates, source_summary = self._prepare_analysis(config, scope)
        worldbook_draft, worldbook_raw = self.generate_worldbook_draft(
            config = config,
            platform = platform,
            scope = scope,
            items = items,
            candidates = candidates,
        )
        character_drafts, character_raw = self.generate_character_drafts(
            config = config,
            platform = platform,
            scope = scope,
            candidates = candidates,
            worldbook_draft = worldbook_draft,
        )
        self._report_progress(
            Localizer.get().workbench_progress_complete.format(worlds = 1, count = len(character_drafts)),
            100,
        )
        return AnalysisResult(
            scope = scope,
            worldbook_draft = worldbook_draft,
            character_drafts = character_drafts,
            worldbook_raw = worldbook_raw,
            character_raw = character_raw,
            source_summary = source_summary,
        )

    def generate_worldbook_only(
        self,
        config: Config,
        scope: str,
        *,
        engine_reserved: bool = False,
    ) -> AnalysisResult:
        """仅生成世界观草稿。"""
        scope = normalize_analysis_scope(scope)
        platform = self.ensure_analysis_ready(config, engine_reserved = engine_reserved)
        items, candidates, source_summary = self._prepare_analysis(config, scope)
        worldbook_draft, worldbook_raw = self.generate_worldbook_draft(
            config = config,
            platform = platform,
            scope = scope,
            items = items,
            candidates = candidates,
        )
        self._report_progress(
            Localizer.get().workbench_progress_complete.format(worlds = 1, count = 0),
            100,
        )
        return AnalysisResult(
            scope = scope,
            worldbook_draft = worldbook_draft,
            character_drafts = [],
            worldbook_raw = worldbook_raw,
            character_raw = [],
            source_summary = source_summary,
        )

    def _prepare_analysis(
        self,
        config: Config,
        scope: str,
    ) -> tuple[list[CacheItem], list[CharacterCandidate], str]:
        """载入语料并扫描角色候选，同时把阶段与百分比推给界面。"""
        self._started_at = time.perf_counter()
        self._report_progress(Localizer.get().workbench_progress_loading, 2)
        started_at = time.perf_counter()
        items, source_summary = self.load_scope_items(config, scope)
        self._evidence_text = self._build_evidence([item.get_src() for item in items])
        self.info(
            f"[Workbench] 语料载入完成：{len(items)} 条，来源 {source_summary}，"
            f"耗时 {time.perf_counter() - started_at:.1f}s"
        )
        self._report_with_elapsed(
            Localizer.get().workbench_progress_scanning_characters.format(count = len(items)),
            8,
        )
        started_at = time.perf_counter()
        candidates = self.scanner.build_candidates(
            config,
            items,
            self.resolve_project_root(config),
            self._report_progress,
        )
        self.info(
            f"[Workbench] 角色候选完成：{len(candidates)} 个，"
            f"耗时 {time.perf_counter() - started_at:.1f}s"
        )
        return items, candidates, source_summary

    def generate_character_only(
        self,
        config: Config,
        scope: str,
        card_id: str | None = None,
        *,
        engine_reserved: bool = False,
    ) -> AnalysisResult:
        """生成角色卡草稿，可选单角色。"""
        scope = normalize_analysis_scope(scope)
        platform = self.ensure_analysis_ready(config, engine_reserved = engine_reserved)
        items, candidates, source_summary = self._prepare_analysis(config, scope)
        identity_candidates = list(candidates)
        if normalize_text(card_id) != "":
            normalized_cards = normalize_character_cards(getattr(config, "renpy_workbench_character_cards", []))
            current_card = next((card for card in normalized_cards if card.get("id") == card_id), None)
            if current_card is None:
                raise AnalysisServiceError("未找到当前角色卡。")
            candidates = self.filter_single_candidate(candidates, current_card)

        worldbook_draft = normalize_worldbook(getattr(config, "renpy_workbench_generated_worldbook_draft", {}))
        if not any(worldbook_draft.values()):
            worldbook_draft = normalize_worldbook(getattr(config, "renpy_workbench_worldbook_data", {}))

        character_drafts, character_raw = self.generate_character_drafts(
            config = config,
            platform = platform,
            scope = scope,
            candidates = candidates,
            worldbook_draft = worldbook_draft,
            identity_candidates = identity_candidates,
        )
        self._report_progress(
            Localizer.get().workbench_progress_complete.format(worlds = 0, count = len(character_drafts)),
            100,
        )
        return AnalysisResult(
            scope = scope,
            worldbook_draft = {},
            character_drafts = character_drafts,
            worldbook_raw = "",
            character_raw = character_raw,
            source_summary = source_summary,
        )

    def filter_single_candidate(
        self,
        candidates: list[CharacterCandidate],
        current_card: dict[str, Any],
    ) -> list[CharacterCandidate]:
        """过滤出当前角色。"""
        card_name = normalize_text(current_card.get("name", ""))
        aliases = {value.casefold() for value in current_card.get("aliases", []) if isinstance(value, str)}
        matched = [
            candidate
            for candidate in candidates
            if candidate.name.casefold() == card_name.casefold()
            or candidate.name.casefold() in aliases
        ]
        if matched:
            return matched[:1]

        fallback = copy.deepcopy(create_default_character_card(card_name))
        fallback["aliases"] = current_card.get("aliases", [])
        fallback["match_keywords"] = current_card.get("match_keywords", [])
        candidate = CharacterCandidate(
            name = fallback["name"],
            aliases = fallback["aliases"],
            match_keywords = fallback["match_keywords"],
            sample_lines = current_card.get("sample_lines", [])[:12],
            related_names = [],
            name_translation = normalize_text(current_card.get("name_translation", "")),
            # 扫描没找到该角色的台词，卡片里存的样本条数不是源码台词数。
            sample_count = 0,
            low_confidence = len(current_card.get("sample_lines", [])) < 3,
        )
        return [candidate]

    @staticmethod
    def _normalize_existing_path(raw: Any) -> Path | None:
        """把配置路径解析为已存在的 Path。"""
        text = normalize_text(raw)
        if text == "":
            return None
        try:
            path = Path(text).expanduser().resolve()
        except Exception:
            path = Path(text)
        return path if path.exists() else None

    def _collect_project_candidates(self, config: Config) -> list[Path]:
        """按优先级收集可能的项目根目录候选。"""
        raws = [
            getattr(config, "renpy_project_path", ""),
            getattr(config, "renpy_game_folder", ""),
            getattr(config, "renpy_tl_folder", ""),
            getattr(config, "input_folder", ""),
            getattr(config, "output_folder", ""),
        ]
        candidates: list[Path] = []
        for raw in raws:
            path = self._normalize_existing_path(raw)
            if path is None:
                continue

            if path.is_file():
                path = path.parent

            if path.parent.name.lower() == "tl":
                if path.parent.parent.name.lower() == "game":
                    candidates.append(path.parent.parent.parent)
                else:
                    candidates.append(path.parent.parent)
                continue

            if path.name.lower() == "tl":
                if path.parent.name.lower() == "game":
                    candidates.append(path.parent.parent)
                else:
                    candidates.append(path.parent)
                continue

            if path.name.lower() == "game":
                candidates.append(path.parent)
                continue

            if (path / "game").is_dir():
                candidates.append(path)
                continue

            candidates.append(path)

        deduped: list[Path] = []
        seen: set[str] = set()
        for candidate in candidates:
            try:
                key = str(candidate.resolve()).lower()
            except Exception:
                key = str(candidate).lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(candidate)
        return deduped

    def resolve_project_root(self, config: Config) -> Path | None:
        """解析项目根目录。"""
        canonical = RenpyProjectPaths.from_config(config)
        if canonical is not None and canonical.game_dir.is_dir():
            return canonical.project_root
        candidates = self._collect_project_candidates(config)
        if candidates == []:
            return None

        for candidate in candidates:
            if (candidate / "game").is_dir():
                return candidate

        fallback = candidates[0]
        if fallback.name.lower() == "game":
            return fallback.parent
        return fallback

    def load_scope_items(self, config: Config, scope: str) -> tuple[list[CacheItem], str]:
        """按范围载入分析语料。"""
        if scope == ANALYSIS_SCOPE_FULL:
            items = self.load_full_project_items(config)
            return items, "全项目源码"

        items = self.load_cache_items(config)
        if items:
            return items, "当前缓存快照"

        items = self.load_input_items(config)
        return items, "当前输入目录"

    def load_cache_items(self, config: Config) -> list[CacheItem]:
        """读取当前输出目录缓存。"""
        output_path = resolve_translation_output(config)
        if output_path is None:
            return []

        cache_manager = CacheManager(service = False)
        cache_manager.load_items_from_file(str(output_path))
        return self.filter_analysis_items(cache_manager.get_items())

    def load_input_items(self, config: Config) -> list[CacheItem]:
        """读取当前输入目录条目。"""
        working = copy.deepcopy(config)
        project, items = FileManager(working).read_from_path()
        del project
        return self.filter_analysis_items(items)

    def load_full_project_items(self, config: Config) -> list[CacheItem]:
        """读取全项目源码条目。

        全项目解析（DarkMagic 这类项目 5 万条文本）要十几秒，而用户在同一个项目里
        往往连续点「扫描角色」「生成世界观」「生成角色卡」；这里按 .rpy 文件指纹
        缓存解析结果，文件没变就直接复用，改过脚本后指纹变化会自动重新解析。
        """
        project_root = self.resolve_project_root(config)
        if project_root is None:
            raise AnalysisServiceError("未配置 Ren'Py 项目目录，无法执行全项目分析。")

        game_dir = project_root / "game"
        if game_dir.exists() is False:
            raise AnalysisServiceError("未找到 game 目录，无法执行全项目分析。")

        cache_key = str(game_dir.resolve())
        fingerprint = self._source_fingerprint(game_dir)
        cached = self._cached_full_project(cache_key, fingerprint)
        if cached is not None:
            self.info(f"[Workbench] 全项目解析命中缓存：{len(cached)} 条")
            return cached

        working = copy.deepcopy(config)
        working.input_folder = str(game_dir)
        working.output_folder = normalize_text(getattr(config, "output_folder", "")) or str(project_root / "output")
        working.renpy_source_translate = True
        working.renpy_hook_translate = False
        project, items = FileManager(working).read_from_path()
        del project
        result = self.filter_analysis_items(items)
        # 被取消的解析只返回部分（甚至为空）条目，不能当成完整结果缓存。
        if not self._is_parse_cancelled():
            self._remember_full_project(cache_key, fingerprint, result)
        # 返回副本，避免调用方就地清空/追加污染缓存里的那份列表。
        return list(result)

    @staticmethod
    def _is_parse_cancelled() -> bool:
        """与 FileManager 的停止判据一致：Engine 停止中或当前运行已请求取消。"""
        try:
            return bool(TaskRequester.is_cancel_requested())
        except Exception:
            return False

    @classmethod
    def _source_fingerprint(cls, game_dir: Path) -> tuple[Any, ...]:
        """文件数 + 每个 .rpy 的相对路径/纳秒修改时间/大小的有序快照。

        遍历规则与 FileManager 源码模式解析一致（只跳过 game 下的 tl 目录），
        排除判断只看相对 game 的目录片段，祖先目录名不影响结果。
        """
        entries: list[tuple[str, int, int]] = []
        for root, dirs, files in os.walk(game_dir):
            dirs[:] = [name for name in dirs if name.lower() != "tl"]
            for file in files:
                if not file.lower().endswith(".rpy"):
                    continue
                full_path = os.path.join(root, file)
                try:
                    info = os.stat(full_path)
                except OSError:
                    continue
                relative = os.path.relpath(full_path, game_dir).replace("\\", "/")
                entries.append((relative, info.st_mtime_ns, info.st_size))
        entries.sort()
        return len(entries), tuple(entries)

    @classmethod
    def _remember_full_project(
        cls,
        cache_key: str,
        fingerprint: tuple[Any, ...],
        items: list[CacheItem],
    ) -> None:
        """写入全项目解析缓存，超出上限时淘汰最久未写入的项。"""
        with cls._full_project_cache_lock:
            # 先删再插，保证刚写入的项排在字典末尾（最新）。
            cls._full_project_cache.pop(cache_key, None)
            cls._full_project_cache[cache_key] = (fingerprint, items)
            while len(cls._full_project_cache) > cls.FULL_PROJECT_CACHE_LIMIT:
                oldest = next(iter(cls._full_project_cache))
                cls._full_project_cache.pop(oldest, None)

    @classmethod
    def _cached_full_project(
        cls,
        cache_key: str,
        fingerprint: tuple[Any, ...],
    ) -> list[CacheItem] | None:
        """读取命中的全项目解析结果；指纹不一致返回 None。"""
        with cls._full_project_cache_lock:
            cached = cls._full_project_cache.get(cache_key)
        if cached is None or cached[0] != fingerprint:
            return None
        # 返回副本，避免调用方就地修改污染缓存。
        return list(cached[1])

    def filter_analysis_items(self, items: list[CacheItem]) -> list[CacheItem]:
        """过滤可用于分析的条目。"""
        result: list[CacheItem] = []
        for item in items:
            status = item.get_status()
            if status in (Base.TranslationStatus.EXCLUDED, Base.TranslationStatus.DUPLICATED):
                continue
            src = normalize_text(item.get_src())
            if src == "":
                continue
            result.append(item)
        return result

    @classmethod
    def _is_ui_file(cls, file_path: Any) -> bool:
        """screens.rpy / gui.rpy / options.rpy / infoscreen.rpy 这类界面脚本。"""
        stem = Path(normalize_text(file_path).replace("\\", "/")).stem.casefold()
        if stem == "":
            return False
        tokens = [token for token in re.split(r"[^0-9a-z]+", stem) if token]
        return any(token in cls.UI_FILE_TOKENS for token in tokens) or stem.endswith(("screen", "screens", "gui"))

    @staticmethod
    def _item_line_type(item: CacheItem) -> str:
        extra = item.get_extra_field()
        if isinstance(extra, dict):
            source = extra.get("renpy_source")
            if isinstance(source, dict):
                return normalize_text(source.get("line_type")).upper()
        return ""

    def _excerpt_tier(self, item: CacheItem, text: str) -> int | None:
        """0 = 剧情台词/旁白，1 = 剧情脚本里的其他文本，2 = 界面脚本；None = 不可作为设定依据。"""
        if not any(char.isalpha() for char in text):
            return None
        if self.RE_LINK_TEXT.search(text) or self.RE_BARE_PATH.fullmatch(text):
            return None
        if is_path_like(text) or is_resource_name(text):
            return None
        if self._is_ui_file(item.get_file_path()):
            return 2
        if self._item_line_type(item) not in self.STORY_LINE_TYPES:
            return 1
        # Character("news") / "{b}Book of Lovers{/b}" 这类定义字面量、标题也被解析成
        # DIALOGUE/NARRATION；去掉文本标签后没有标点的短词组多是标签。
        plain = self.RE_TEXT_VARIABLE.sub(" ", CharacterScanner.strip_format_tags(text))
        if len(plain.split()) <= 4 and self.RE_SENTENCE_MARK.search(plain) is None:
            return 1
        return 0

    def select_representative_texts(
        self,
        items: list[CacheItem],
        *,
        max_items: int,
        exclude: Sequence[str] = (),
    ) -> list[str]:
        """从条目中抽取代表文本：剧情台词优先并在全篇均匀分布，界面/链接/路径文案靠后或剔除。"""
        excluded = {normalize_text(value).casefold() for value in exclude if normalize_text(value) != ""}
        tiers: list[list[str]] = [[], [], []]
        seen: set[str] = set()
        for item in items:
            text = normalize_text(item.get_src())
            if text == "":
                continue
            key = text.casefold()
            if key in seen or key in excluded:
                continue
            seen.add(key)
            tier = self._excerpt_tier(item, text)
            if tier is None:
                continue
            tiers[tier].append(text[:220])

        result: list[str] = []
        for texts in tiers:
            remaining = max_items - len(result)
            if remaining <= 0:
                break
            result.extend(CharacterScanner.select_evenly(texts, remaining))
        return result

    @classmethod
    def _decode_title_literal(cls, literal: str) -> str:
        body = literal[1:-1]
        body = re.sub(r"\\(.)", lambda match: match.group(1), body)
        title = normalize_text(body)
        # 带插值或文本标签的是运行时拼出来的名字，不能当声明标题。
        if title == "" or len(title) > 120 or any(char in title for char in "[]{}"):
            return ""
        return title

    def read_declared_title(self, project_root: Path | None) -> dict[str, str]:
        """读取源码声明的 config.name / build.name 字面量，不执行任何代码。

        优先 options.rpy，没找到再看 game 目录下其他顶层脚本。
        """
        result: dict[str, str] = {}
        if project_root is None:
            return result
        game_dir = Path(project_root)
        if game_dir.name.lower() != "game":
            game_dir = game_dir / "game"
        if not game_dir.is_dir():
            return result

        options = game_dir / "options.rpy"
        others = sorted(path for path in game_dir.glob("*.rpy") if path.name.lower() != "options.rpy")
        for path in ([options] if options.is_file() else []) + others:
            try:
                content = path.read_text(encoding = "utf-8-sig", errors = "ignore")
            except OSError:
                continue
            for match in self.RE_DECLARED_TITLE.finditer(content):
                key = match.group("key")
                if key in result:
                    continue
                title = self._decode_title_literal(match.group("wrapped") or match.group("plain") or "")
                if title != "":
                    result[key] = title
            if "config.name" in result and "build.name" in result:
                break
        return result

    def request_json_text(
        self,
        config: Config,
        platform: dict[str, Any],
        prompt: str,
        *,
        round_index: int = 0,
        label: str = "AI 分析",
    ) -> str:
        """发起一次 JSON 文本请求，并把思考片段/用量/耗时写进日志。"""
        text, _input_tokens, _output_tokens = self.request_json_text_verbose(
            config, platform, prompt, round_index = round_index, label = label,
        )
        return text

    def request_json_text_verbose(
        self,
        config: Config,
        platform: dict[str, Any],
        prompt: str,
        *,
        round_index: int = 0,
        label: str = "AI 分析",
    ) -> tuple[str, int, int]:
        """同 request_json_text，但额外返回 (文本, 输入 tokens, 输出 tokens)。"""
        request_platform = build_analysis_platform(
            platform,
            lambda message: self.info(f"[Workbench] {label} {message}"),
        )
        requester = TaskRequester(config, request_platform, round_index)
        self.info(f"[Workbench] {label} 请求：prompt {len(prompt)} 字，首行 {prompt.splitlines()[0][:60]}")
        started_at = time.perf_counter()
        # 界面要能看到模型正在想什么：下面这段只要走流式，就会把增量写进这个缓冲。
        LiveActivity.begin(f"{label} · prompt {len(prompt)} 字")
        try:
            with request_progress(self.info, f"[Workbench] {label}"):
                skip, response_think, response_text, input_tokens, output_tokens = requester.request(
                [
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                response_shape = "none",
            )
        finally:
            LiveActivity.finish()
        # 思考内容只写日志的话界面上什么都看不到；挂到实例上，让调用方能把它带回前端。
        self._last_think = str(response_think or "")
        self._log_model_exchange(
            label,
            response_think,
            input_tokens,
            output_tokens,
            time.perf_counter() - started_at,
        )
        if skip or not isinstance(response_text, str) or response_text.strip() == "":
            raise AnalysisServiceError("AI 分析接口返回为空，请稍后重试。")
        return response_text.strip(), input_tokens, output_tokens

    def generate_worldbook_draft(
        self,
        config: Config,
        platform: dict[str, Any],
        scope: str,
        items: list[CacheItem],
        candidates: list[CharacterCandidate],
    ) -> tuple[dict[str, Any], str]:
        """生成世界观草稿。"""
        excerpt_limit = 48 if scope == ANALYSIS_SCOPE_CURRENT else 96
        excerpts = self.select_representative_texts(
            items,
            max_items = excerpt_limit,
            exclude = [candidate.name for candidate in candidates],
        )
        top_candidates = candidates[:12]
        declared = self.read_declared_title(self.resolve_project_root(config))
        declared_title = declared.get("config.name") or declared.get("build.name", "")
        if declared_title != "":
            title_lines = [
                f"源码声明的游戏标题：{declared_title}",
                "project_name 必须原样填写该标题，不要根据剧情、文件名、路径或界面文案另起名字。",
            ]
            build_name = declared.get("build.name", "")
            if build_name != "" and build_name != declared_title:
                title_lines.append(f"源码构建名（build.name）：{build_name}，仅供参考。")
        else:
            title_lines = ["源码未声明游戏标题：project_name 留空，不要根据剧情、文件名、路径或界面文案猜测。"]

        def describe_candidate(candidate: CharacterCandidate) -> str:
            if candidate.sample_count > 0:
                return f"- {candidate.name}（源码台词 {candidate.sample_count} 行）"
            return f"- {candidate.name}"

        prompt = "\n".join(
            [
                "你是视觉小说本地化策划助手，需要根据项目样本生成“翻译工作台”用的世界观草稿。",
                "请严格只输出 JSON 对象，不要输出 Markdown、解释、前后缀、代码块。返回内容必须是可直接解析的 json。",
                "字段必须且只能包含：project_name, genre, setting_summary, era_background, tone_style, narrative_rules, format_rules, spoiler_notes。",
                "约束：",
                "1. 轻剧透：允许总结背景、关系、说话风格、公开设定。",
                "2. 不要把关键反转、最终真相、结局直接写进 setting_summary。",
                "3. 如果确实需要提醒翻译者注意隐藏身份或潜在线索，只写进 spoiler_notes。",
                "4. narrative_rules 和 format_rules 要聚焦翻译执行建议，不要写空话。",
                "5. 所有字段值都必须是字符串。",
                "6. 样本是从全篇剧情台词/旁白中均匀抽取的片段，只能据此概括；样本里看不出的设定不要编造，不确定的内容用“可能/疑似”标注。",
                *title_lines,
                f"分析范围：{'当前翻译范围' if scope == ANALYSIS_SCOPE_CURRENT else '全项目扩展分析'}",
                "高频角色候选（按源码台词行数排序）：",
                "\n".join(describe_candidate(candidate) for candidate in top_candidates) if top_candidates else "- 暂无",
                "项目样本文本：",
                "\n".join(f"{idx + 1}. {text}" for idx, text in enumerate(excerpts)) if excerpts else "暂无样本",
                "请按以下 json 对象示例输出：",
                """{
  "project_name": "",
  "genre": "",
  "setting_summary": "",
  "era_background": "",
  "tone_style": "",
  "narrative_rules": "",
  "format_rules": "",
  "spoiler_notes": ""
}""",
            ]
        )

        self._report_with_elapsed(
            Localizer.get().workbench_progress_worldbook.format(count = len(excerpts)),
            20,
        )
        raw = self.request_json_text(config, platform, prompt, round_index = 0, label = "世界观草稿")
        try:
            parsed = repair.loads(raw)
        except Exception as exc:
            raise AnalysisServiceError(f"世界观草稿解析失败：{exc}", raw_response = raw) from exc

        if not isinstance(parsed, dict):
            raise AnalysisServiceError("世界观草稿解析失败：模型返回的不是 JSON 对象。", raw_response = raw)

        self._report_with_elapsed(Localizer.get().workbench_progress_worldbook_done, 48)
        worldbook = normalize_worldbook(parsed)
        # 标题只采用源码字面量；无法确认时留空，避免模型凭剧情再猜一个名字。
        worldbook["project_name"] = declared_title
        return worldbook, raw

    def generate_character_drafts(
        self,
        config: Config,
        platform: dict[str, Any],
        scope: str,
        candidates: list[CharacterCandidate],
        worldbook_draft: dict[str, Any],
        identity_candidates: Sequence[CharacterCandidate] | None = None,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """批量生成角色卡草稿；分批并发请求，边完成边推送进度。

        identity_candidates 是本次扫描到的全部角色（单角色重生成时比 candidates 多），
        用来拒绝把别人的名字写成当前角色的别名。
        """
        normalized_world = normalize_worldbook(worldbook_draft)
        identities = self._identity_names(list(identity_candidates or []) + list(candidates))
        drafts: list[dict[str, Any]] = []
        raws: list[str] = []
        if not candidates:
            self._report_progress(Localizer.get().workbench_progress_no_characters, 100)
            return drafts, raws

        chunk_size = self.CHARACTER_BATCH_SIZE
        chunks = [
            candidates[offset: offset + chunk_size]
            for offset in range(0, len(candidates), chunk_size)
        ]
        total_batches = len(chunks)
        self.info(
            f"[Workbench] 角色卡分批：{len(candidates)} 个候选 / {total_batches} 批，"
            f"并发 {self.CHARACTER_BATCH_CONCURRENCY}"
        )

        def run_batch(batch_index: int, chunk: Sequence[CharacterCandidate]) -> tuple[list[dict[str, Any]], str]:
            prompt = self.build_character_prompt(scope, list(chunk), normalized_world)
            label = f"角色卡第 {batch_index + 1}/{total_batches} 批（{len(chunk)} 人）"
            raw = self.request_json_text(
                config,
                platform,
                prompt,
                round_index = batch_index,
                label = label,
            )
            try:
                parsed = repair.loads(raw)
            except Exception as exc:
                raise AnalysisServiceError(f"角色卡草稿解析失败：{exc}", raw_response = raw) from exc
            if not isinstance(parsed, list):
                raise AnalysisServiceError("角色卡草稿解析失败：模型返回的不是 JSON 数组。", raw_response = raw)
            return self.normalize_character_drafts_from_response(parsed, list(chunk), identities = identities), raw

        # 线程池工作线程不会继承 Worker 线程的取消上下文，必须显式绑定同一事件，
        # 否则取消后仍在排队的批次会继续发起网络请求。
        cancel_context = getattr(TaskRequester, "RUN_CANCEL_CONTEXT", None)
        cancel_event = getattr(cancel_context, "event", None) if cancel_context is not None else None
        binder = getattr(TaskRequester, "bind_run_cancel_event", None)
        unbinder = getattr(TaskRequester, "unbind_run_cancel_event", None)

        def worker(batch_index: int, chunk: Sequence[CharacterCandidate]) -> tuple[list[dict[str, Any]], str]:
            bound = cancel_event is not None and callable(binder)
            if bound:
                binder(cancel_event)
            try:
                return run_batch(batch_index, chunk)
            finally:
                if bound and callable(unbinder):
                    unbinder()

        completed = 0
        with ThreadPoolExecutor(max_workers = max(1, min(self.CHARACTER_BATCH_CONCURRENCY, total_batches))) as pool:
            futures = {
                pool.submit(worker, index, chunk): index
                for index, chunk in enumerate(chunks)
            }
            ordered: dict[int, tuple[list[dict[str, Any]], str]] = {}
            try:
                for future in as_completed(futures):
                    batch_index = futures[future]
                    ordered[batch_index] = future.result()
                    completed += 1
                    percent = 50 + int((completed / total_batches) * 45)
                    self._report_with_elapsed(
                        Localizer.get().workbench_progress_characters_progress.format(
                            completed = completed,
                            total = total_batches,
                        ),
                        percent,
                    )
            except BaseException:
                for future in futures:
                    future.cancel()
                raise

        for index in range(total_batches):
            batch_drafts, raw = ordered[index]
            drafts.extend(batch_drafts)
            raws.append(raw)

        self._report_progress(Localizer.get().workbench_progress_characters_done.format(count=len(drafts)), 96)
        return drafts, raws

    def build_character_prompt(
        self,
        scope: str,
        candidates: list[CharacterCandidate],
        worldbook_draft: dict[str, Any],
    ) -> str:
        """构建角色卡分析提示词。"""
        world_text = normalize_worldbook(worldbook_draft)
        candidate_blocks: list[str] = []
        for candidate in candidates:
            samples = self._prompt_samples(candidate)
            trusted = self._trusted_keywords(candidate)
            lines = [
                f"角色名: {candidate.name}",
                f"已有译名: {candidate.name_translation or '暂无'}",
                f"源码可确认的称呼: {', '.join(trusted)}",
                f"同文件出现的其他说话人: {', '.join(candidate.related_names) if candidate.related_names else '暂无'}",
                f"源码台词行数: {candidate.sample_count if candidate.sample_count > 0 else '未统计'}",
                f"低置信度: {'是' if candidate.low_confidence else '否'}",
                f"样本台词（从全部台词中按出场位置均匀抽取 {len(samples)} 条）:",
            ]
            if samples:
                lines.extend(f"- {line}" for line in samples)
            else:
                lines.append("- 暂无可用样本")
            candidate_blocks.append("\n".join(lines))

        return "\n".join(
            [
                "你是视觉小说本地化策划助手，需要根据角色样本生成“翻译工作台”用的人设草稿。",
                "请严格只输出 JSON 数组，不要输出 Markdown、解释、代码块。返回内容必须是可直接解析的 json。",
                "数组元素必须且只能包含以下键：name, aliases, match_keywords, identity, personality, speech_style, relationship_notes, prompt_notes, sample_lines。",
                "约束：",
                "1. 轻剧透：可总结公开身份、关系、语气、口癖，但避免直接揭露关键反转。",
                "2. 如果证据不足，请在 prompt_notes 首句注明“低置信度候选”。",
                "3. aliases 和 match_keywords 必须是字符串数组。aliases 只填写样本中确实用来指代该角色本人的名字变体（如全名、名字的简称）；不要填写其他角色的名字、玩家名变量（如 [xxx]）、称谓泛称、普通名词、台词片段或剧情关键词，没有就输出空数组。match_keywords 只填「源码可确认的称呼」里的值，其他内容会被系统丢弃。",
                "4. sample_lines 只能从该角色给定的「样本台词」中原样复制 1-6 条，保持原文拼写与语言，不得翻译、改写或编造；没有合适样本时输出空数组。",
                "5. identity、personality、speech_style、relationship_notes、prompt_notes 使用中文描述；name、aliases、match_keywords 保留游戏原文拼写，sample_lines 按第 4 条保留原文。",
                "6. 「同文件出现的其他说话人」只表示他们在同一脚本文件里都有台词，是很弱的线索，不代表已确立的关系；relationship_notes 只写样本台词能直接证明的关系，证据不足时写“关系待确认”，不要把共现名单罗列成关系。",
                "7. 「源码台词行数」是该角色作为说话人的台词行统计，不是总出场次数；样本只是其中一小部分。不要据此写“只出现一次”“出场很少”之类推断。",
                "8. 区分确定与推测：样本能直接证明的写成陈述，推测内容用“可能/疑似”标注；不要合并或改写角色名，也不要猜测拼写变体。",
                f"分析范围：{'当前翻译范围' if scope == ANALYSIS_SCOPE_CURRENT else '全项目扩展分析'}",
                "世界观摘要：",
                f"- 项目名称：{world_text.get('project_name', '') or '未确定'}",
                f"- 类型：{world_text.get('genre', '') or '未确定'}",
                f"- 背景摘要：{world_text.get('setting_summary', '') or '未确定'}",
                f"- 时代背景：{world_text.get('era_background', '') or '未确定'}",
                f"- 语气风格：{world_text.get('tone_style', '') or '未确定'}",
                "角色候选：",
                "\n\n".join(candidate_blocks),
                "请按以下 json 数组示例输出：",
                """[
  {
    "name": "",
    "aliases": [],
    "match_keywords": [],
    "identity": "",
    "personality": "",
    "speech_style": "",
    "relationship_notes": "",
    "prompt_notes": "",
    "sample_lines": []
  }
]""",
            ]
        )

    def normalize_character_drafts_from_response(
        self,
        parsed: list[Any],
        candidates: list[CharacterCandidate],
        *,
        identities: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        """规范化模型返回的角色草稿。

        匹配关键词只保留候选自带、源码可确认的称呼（角色名、可信别名、`[var]` 插值）；
        模型给的 match_keywords 一律不进触发词。模型别名只在与本角色名字成词级包含
        关系、且不撞其他角色身份时才保留（见 _grounded_aliases）。
        """
        candidate_by_name = {
            candidate.name.casefold(): candidate
            for candidate in candidates
        }
        known = set(identities) if identities is not None else self._identity_names(candidates)
        drafts: list[dict[str, Any]] = []
        used: set[str] = set()

        for raw in parsed:
            if not isinstance(raw, dict):
                continue
            name = normalize_text(raw.get("name", ""))
            if name == "":
                continue
            candidate = candidate_by_name.get(name.casefold())
            if candidate is None or candidate.name.casefold() in used:
                continue

            card = create_default_character_card(candidate.name)
            card["aliases"] = normalize_text_list(
                candidate.aliases + self._grounded_aliases(raw.get("aliases"), candidate, known)
            )
            card["match_keywords"] = self._trusted_keywords(candidate)
            for key in self.CHARACTER_DESCRIPTIVE_FIELDS:
                card[key] = normalize_text(raw.get(key, ""))
            prompt_notes = normalize_text(raw.get("prompt_notes", ""))
            if candidate.low_confidence and "低置信度候选" not in prompt_notes:
                prompt_notes = ("低置信度候选。" + prompt_notes).strip("。")
            if not any(card[key] for key in self.CHARACTER_DESCRIPTIVE_FIELDS):
                prompt_notes = self._prepend_note(self.NOTE_EMPTY_ANALYSIS, prompt_notes)
            card["prompt_notes"] = prompt_notes
            card["sample_lines"] = self._trusted_sample_lines(raw.get("sample_lines"), candidate)
            card["name_translation"] = candidate.name_translation
            drafts.append(normalize_character_card(card))
            used.add(candidate.name.casefold())

        for candidate in candidates:
            if candidate.name.casefold() in used:
                continue
            fallback = candidate.as_card_seed()
            fallback["prompt_notes"] = self._prepend_note(self.NOTE_MISSING_ANALYSIS, fallback.get("prompt_notes", ""))
            drafts.append(normalize_character_card(fallback))
        return drafts

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        """只接受字符串或字符串数组，其他类型（null/数字/对象）视为空。"""
        if isinstance(value, str):
            return [value]
        if isinstance(value, (list, tuple)):
            return [item for item in value if isinstance(item, str)]
        return []

    @staticmethod
    def _prepend_note(note: str, prompt_notes: str) -> str:
        if note in prompt_notes:
            return prompt_notes
        return f"{note}{prompt_notes}"

    @staticmethod
    def _trusted_keywords(candidate: CharacterCandidate) -> list[str]:
        """候选自带的称呼：角色名 + 扫描/术语表/现有角色卡给出的别名与关键词。"""
        return normalize_text_list([candidate.name] + candidate.aliases + candidate.match_keywords)

    @classmethod
    def _identity_names(cls, candidates: Sequence[CharacterCandidate]) -> set[str]:
        names: set[str] = set()
        for candidate in candidates:
            names.update(value.casefold() for value in cls._trusted_keywords(candidate))
        return names

    @staticmethod
    def _name_words(value: str) -> list[str]:
        return re.findall(r"[^\W_]+", value.casefold())

    @staticmethod
    def _contains_run(words: list[str], run: list[str]) -> bool:
        """run 是否作为连续整词出现在 words 里。"""
        if not run or len(run) > len(words):
            return False
        return any(words[index: index + len(run)] == run for index in range(len(words) - len(run) + 1))

    @staticmethod
    def _word_pattern(value: str, *, ignore_case: bool) -> re.Pattern[str]:
        return re.compile(
            rf"(?<![^\W_]){re.escape(value)}(?![^\W_])",
            re.IGNORECASE if ignore_case else 0,
        )

    def _is_generic_alias(self, alias: str, evidence: str) -> bool:
        """全是称谓泛称，或在语料里多以小写出现的普通词组（fairy / lady thief）。"""
        words = self._name_words(alias)
        if all(len(word) < 2 or word in self.GENERIC_ALIAS_WORDS for word in words):
            return True
        if evidence == "":
            return False
        phrase = " ".join(alias.split()).casefold()
        lower_hits = len(self._word_pattern(phrase, ignore_case = False).findall(evidence))
        if lower_hits == 0:
            return False
        all_hits = len(self._word_pattern(phrase, ignore_case = True).findall(evidence))
        return lower_hits * 2 >= all_hits

    @classmethod
    def _build_evidence(cls, texts: Sequence[str]) -> str:
        """别名核对用的语料；`[sakimi]` 这类插值变量是小写标识符，不能算作普通名词的证据。"""
        return cls.RE_TEXT_VARIABLE.sub(" ", "\n".join(normalize_text(text) for text in texts))

    def _grounded_aliases(
        self,
        raw_aliases: Any,
        candidate: CharacterCandidate,
        identities: set[str],
    ) -> list[str]:
        """只保留与本角色名字成整词包含关系、且源码可佐证的模型别名。

        - 简称（Sakimi ⊂ Lady Thief Sakimi）：不能全是称谓/普通名词；
        - 全称（Elena Carter ⊃ Elena）：必须原样出现在语料或样本里；
        - 与其他角色身份互相包含、带 `[var]`/标签/下划线标识符、拼写变体一律丢弃。
        """
        own = {value.casefold() for value in self._trusted_keywords(candidate)}
        others = [self._name_words(value) for value in identities - own if not value.startswith("[")]
        name_words = self._name_words(candidate.name)
        evidence = self._evidence_text or self._build_evidence(candidate.sample_lines)

        accepted: list[str] = []
        for value in self._string_list(raw_aliases):
            alias = normalize_text(value)
            key = alias.casefold()
            if key in own or len(alias) < 2 or any(char in alias for char in "[]{}_"):
                continue
            alias_words = self._name_words(alias)
            if not alias_words:
                continue
            if any(self._contains_run(other, alias_words) or self._contains_run(alias_words, other) for other in others if other):
                continue
            if self._contains_run(name_words, alias_words):
                if self._is_generic_alias(alias, evidence):
                    continue
            elif self._contains_run(alias_words, name_words):
                if self._word_pattern(alias, ignore_case = True).search(evidence) is None:
                    continue
            else:
                continue
            accepted.append(alias)
        return normalize_text_list(accepted)

    def _prompt_samples(self, candidate: CharacterCandidate) -> list[str]:
        """提示词里的样本：从候选样本中按位置均匀抽取，避免全部来自开头场景。"""
        lines = [line for line in candidate.sample_lines if isinstance(line, str) and line.strip() != ""]
        return CharacterScanner.select_evenly(lines, self.CHARACTER_PROMPT_SAMPLES)

    def _trusted_sample_lines(self, model_samples: Any, candidate: CharacterCandidate) -> list[str]:
        """只保留提示词里真实给出的原文样本，模型翻译/编造的台词一律丢弃。"""
        originals: dict[str, str] = {}
        for line in self._prompt_samples(candidate):
            originals.setdefault(line.strip(), line)

        selected: list[str] = []
        for value in self._string_list(model_samples):
            original = originals.get(value.strip())
            if original is not None and original not in selected:
                selected.append(original)
            if len(selected) >= self.CHARACTER_SAMPLE_LIMIT:
                break
        if selected:
            return selected
        return CharacterScanner.select_evenly(list(originals.values()), self.CHARACTER_SAMPLE_LIMIT)

    # -------------------------------------------------------- 关系 AI 复核
    # 一次复核请求最多带多少条候选边；边太多会让单次请求超时/超 token。
    RELATION_REVIEW_MAX_PAIRS = 60
    # 角色清洗：一次请求最多带多少个候选名字。名字 + 两三条样本大概 60 token，
    # 60 个一批既能让模型横向比较，又不至于让提示词长到稀释判断质量。
    CHARACTER_CLEAN_BATCH = 60
    CHARACTER_CLEAN_MAX = 400
    CHARACTER_CLEAN_ROLES: tuple[str, ...] = ("main", "side", "walkon", "noise")
    # 复核提示词里每条候选最多带几条证据原文。
    RELATION_REVIEW_SAMPLES = 3
    # 关系推断：一次请求最多带多少对「只有同场共现、没有规则证据」的角色。
    # 同场次数本身就是现成证据，候选多了反而稀释判断，12 对足够覆盖主要人物。
    RELATION_INFER_MAX_PAIRS = 12
    # 推断提示词里每个角色最多带几条台词样例，用来判断说话风格与称呼口吻。
    RELATION_INFER_SAMPLES = 2

    def build_relation_review_prompt(
        self,
        candidates: Sequence[dict[str, Any]],
        worldbook_draft: Any,
    ) -> str:
        """构建关系复核提示词；只给有源码证据的候选，不让模型自由生成人物对。"""
        world_text = normalize_worldbook(worldbook_draft)
        blocks: list[str] = []
        for index, row in enumerate(candidates, start = 1):
            samples = [normalize_text(item) for item in row.get("samples", [])][: self.RELATION_REVIEW_SAMPLES]
            count = int(row.get("count") or 0)
            lines = [
                f"{index}. {row.get('from', '')} → {row.get('to', '')}",
                f"   称谓词：{row.get('word', '')}",
                f"   规则判定：{row.get('relation', '')}（{row.get('category', '')}）",
                f"   命中次数：{count if count > 0 else 1}",
            ]
            if samples:
                lines.append("   源码证据：")
                lines.extend(f"   - {sample}" for sample in samples)
            else:
                lines.append("   源码证据：暂无（命中次数不足以留样）")
            blocks.append("\n".join(lines))

        return "\n".join(
            [
                "你是视觉小说本地化策划助手。下面是按「称谓词 × 同场景角色」规则从源码挖出的人物关系候选，",
                "每条都附有源码台词证据。请逐条复核：规则判定是否成立、关系词是否恰当。",
                "请严格只输出 JSON 数组，不要输出 Markdown、解释、代码块。返回内容必须是可直接解析的 json。",
                "数组元素必须且只能包含以下键：from, to, relation, category, keep, reason。",
                "约束：",
                "1. 只复核输入清单里的人物对，from/to 必须原样照抄输入值，不得新增、合并或改写角色名。",
                "2. keep=true 表示规则判定成立（relation 可根据证据改写成更准确的中文关系词，category 取 family/romantic/friendly/hostile/work/other 之一）。",
                "3. keep=false 表示规则误判（例如台词里的称谓只是比喻、称呼错了对象、或两个角色并非该关系），并在 reason 里用中文说明原因；被否决的人物对会留档为「已否决」，不再在关系图上画线，但角色本身不会被删除。",
                "4. reason 用中文，一句话即可；不确定时写「证据不足，维持规则判定」。",
                "5. 证据里看不出的设定不要编造；证据只证明「提到过」时不等于关系成立，需结合称谓变量同场出现这一点判断。",
                "6. 「命中次数」是该人物对在源码里被同一称谓规则命中的次数，次数多说明证据更可靠，但不是关系成立的充分条件。",
                "世界观摘要：",
                f"- 项目名称：{world_text.get('project_name', '') or '未确定'}",
                f"- 背景摘要：{world_text.get('setting_summary', '') or '未确定'}",
                "候选关系：",
                "\n".join(blocks) if blocks else "（无候选）",
                "请按以下 json 数组示例输出：",
                """[
  {
    "from": "",
    "to": "",
    "relation": "",
    "category": "",
    "keep": true,
    "reason": ""
  }
]""",
            ]
        )

    def build_relation_infer_prompt(
        self,
        candidates: Sequence[dict[str, Any]],
        worldbook_draft: Any,
    ) -> str:
        """构建关系推断提示词：只给「同场共现」与双方人设，不让模型凭空造人物对。

        规则复核问的是「这条规则判定对不对」；推断问的是「这两个人到底是什么关系」。
        后者只有同场次数当证据，所以必须把双方的身份/性格/说话风格/关系备注/台词样例
        一并给模型，否则它只能按名字瞎猜。
        """
        world_text = normalize_worldbook(worldbook_draft)
        blocks: list[str] = []
        for index, row in enumerate(candidates, start = 1):
            count = int(row.get("count") or 0)
            lines = [f"{index}. {row.get('from', '')} ↔ {row.get('to', '')}（同场 {count} 次）"]
            for label, card in (("角色 A", row.get("from_card") or {}), ("角色 B", row.get("to_card") or {})):
                lines.append(
                    f"   {label}：{normalize_text(card.get('name', ''))}（{int(card.get('line_count') or 0)} 句台词）"
                )
                for key, caption in (
                    ("identity", "身份"),
                    ("personality", "性格"),
                    ("speech_style", "说话风格"),
                    ("relationship_notes", "关系备注"),
                ):
                    value = normalize_text(card.get(key, ""))
                    if value:
                        lines.append(f"     {caption}：{value}")
                samples = [
                    normalize_text(item) for item in (card.get("sample_lines") or [])
                ][: self.RELATION_INFER_SAMPLES]
                if samples:
                    lines.append("     台词样例：")
                    lines.extend(f"       - {sample}" for sample in samples)
            blocks.append("\n".join(lines))

        return "\n".join(
            [
                "你是视觉小说本地化策划助手。下面是同一场景里反复出现的角色对（同场共现统计），",
                "但源码里没有「称谓词 × 角色变量」的规则证据，需要你根据双方资料推断他们最可能的关系。",
                "请严格只输出 JSON 数组，不要输出 Markdown、解释、代码块。返回内容必须是可直接解析的 json。",
                "数组元素必须且只能包含以下键：from, to, relation, category, keep, reason。",
                "约束：",
                "1. 只判断输入清单里的人物对，from/to 必须原样照抄输入值，不得新增、合并或改写角色名。",
                "2. keep=true 表示资料足够支撑一个关系判断；relation 用简洁的中文关系词（如：恋人、姐妹、师生、同事、邻居）。",
                "3. category 取 family / romantic / friendly / hostile / work / other 之一。",
                "4. keep=false 表示资料里看不出关系（只是同场、没有说话往来），不要硬猜；reason 写清为什么证据不足。",
                "5. reason 用中文一句话，必须同时提到「同场次数」和资料里的具体线索（身份/性格/关系备注/台词样例）。",
                "6. 同场次数多只代表两人经常一起出现，不等于亲密关系；资料里没有的关系不要编造。",
                "世界观摘要：",
                f"- 项目名称：{world_text.get('project_name', '') or '未确定'}",
                f"- 背景摘要：{world_text.get('setting_summary', '') or '未确定'}",
                "同场共现的角色对：",
                "\n".join(blocks) if blocks else "（无候选）",
                "请按以下 json 数组示例输出：",
                """[
  {
    "from": "",
    "to": "",
    "relation": "",
    "category": "",
    "keep": true,
    "reason": ""
  }
]""",
            ]
        )

    def build_character_clean_prompt(
        self,
        candidates: Sequence[dict[str, Any]],
        worldbook_draft: Any,
    ) -> str:
        """构建角色清洗提示词。

        扫描是机械的：每句台词的说话人都会被收进来，所以名单里必然混着
        报幕员、音效、未解析的占位符、群戏标签。这一步只让模型做归类，
        不允许它新增或改名——名字必须原样返回，否则服务端直接丢弃。

        这一步只判断「谁是人」，不碰任何一条人物关系：关系是另一条 AI 复核线管的，
        清洗顺手改关系会让用户改好的边莫名消失。
        """
        world_text = normalize_worldbook(worldbook_draft)
        context = "、".join(
            f"{label}：{normalize_text(world_text.get(key, ''))}"
            for key, label in (
                ("project_name", "作品"),
                ("genre", "类型"),
                ("setting_summary", "背景"),
                ("tone_style", "基调"),
            )
            if normalize_text(world_text.get(key, ""))
        )
        blocks: list[str] = []
        for index, row in enumerate(candidates, start = 1):
            samples = [normalize_text(line)[:60] for line in (row.get("samples") or [])][:2]
            sample_text = " / ".join(f"「{line}」" for line in samples if line)
            variable = normalize_text(row.get("variable", ""))
            parts = [f"{index}. {row.get('name', '')}"]
            parts.append(f"台词 {int(row.get('lines') or 0)} 条")
            if variable:
                parts.append(f"变量名 {variable}")
            if sample_text:
                parts.append(f"样本 {sample_text}")
            blocks.append(" | ".join(parts))
        background = f"作品背景：{context}" if context else "（没有背景资料，只按名字和台词判断）"
        roster = chr(10).join(blocks)
        # 提示词里有大量花括号（JSON 示例、占位符字样），用普通字符串 + 替换拼接，
        # 免得写成 f-string 时被当成表达式。
        return """你在清洗一份从 Ren'Py 游戏源码自动扫描出来的角色名单。

扫描是机械的：每一句台词的说话人都被收了进来，所以名单里混着不是角色的东西。
你要给每个名字归类，只能从下面四类里选：

- main：主角或贯穿全篇的核心角色（台词多、有专属立绘、剧情围绕他展开）
- side：有名字、有独立人格的配角
- walkon：有台词、但没有独立人格的人类路人（店员、士兵、守卫、路人甲这类）
- noise：根本不是角色

最重要的判断：这个说话人是不是一个「人」。
下面这些一律归 noise，不管它台词有多少条：
1. 动物与非人类：猫、狗、宠物、妖怪、使魔、机器人、AI、精灵、拟人吉祥物。
   名字像 A Cat / Cat / Dog / Puppy / Tama 这种，或者样本里在喵、汪、叫的，都是 noise。
2. 旁白与报幕：旁白、叙述者、Narrator、Announcer、报幕员、系统提示、屏幕文字、字幕。
3. 音效与标记：Sfx、Sound、音效、音乐标记、??? 、*** 、空名字。
4. 未解析的占位符：名字里带方括号、花括号、尖括号、$ 、% 的，是没渲染出来的插值。
5. 群体标签：Everyone / A group / Two voices / 众人 / 群演 / 全班同学 这种集合。

判据：
1. 台词条数只是参考，主要看样本内容指不指向一个「具体的人」。
2. walkon 只留给有人类身份、有台词、但没有独立人格的路人；不是人类就不是 walkon，是 noise。
3. 同一个人的不同写法（台词里带格式标记的、缩写）看起来重复时，选一个当 main 或 side，其余的 note 写「疑似重复」。
4. faction 只在你能从名字、样本、背景里明确看出所属群体时才写，拿不准就留空，不要猜。

{background}

只输出 JSON 数组，不要任何解释。每个元素四个键：
{"name": "原样照抄名单里的名字", "role": "main|side|walkon|noise", "faction": "8 字以内的中文群体标签，如 王家/商会/教会/主角家，拿不准就留空", "note": "20 字以内，说清判断依据"}

硬性要求：
1. 不要新增名单里没有的名字，不要改写名字。
2. 只做角色归类，不要输出、评论或修改任何人物关系。

名单：
{roster}""".replace("{background}", background).replace("{roster}", roster)

    def clean_characters(
        self,
        config: Config,
        candidates: Sequence[dict[str, Any]],
        worldbook_draft: Any,
        *,
        batch_size: int | None = None,
    ) -> dict[str, Any]:
        """让模型给扫描出来的名字归类，返回 {name 小写: 判定}。

        只做归类，不删除也不新增：服务端按「输入清单里出现过的名字」过滤，
        模型编出来的名字直接丢掉。是否真的删掉角色由调用方决定。
        """
        if not candidates:
            return {"judged": {}, "prompt_tokens": 0, "completion_tokens": 0}
        platform = self.ensure_analysis_ready(config, engine_reserved = False)
        size = max(1, int(batch_size or self.CHARACTER_CLEAN_BATCH))
        selected = list(candidates)[: self.CHARACTER_CLEAN_MAX]
        known = {normalize_text(row.get("name", "")).casefold(): row for row in selected}
        judged: dict[str, dict[str, Any]] = {}
        thinks: list[str] = []
        prompt_tokens = 0
        completion_tokens = 0
        for start in range(0, len(selected), size):
            batch = selected[start: start + size]
            prompt = self.build_character_clean_prompt(batch, worldbook_draft)
            raw, input_tokens, output_tokens = self.request_json_text_verbose(
                config, platform, prompt, round_index = 0, label = "角色清洗",
            )
            prompt_tokens += int(input_tokens)
            completion_tokens += int(output_tokens)
            think = str(getattr(self, "_last_think", "") or "")
            if think:
                thinks.append(f"[第 {len(thinks) + 1} 批] " + think)
            try:
                parsed = repair.loads(raw)
            except Exception as exc:
                raise AnalysisServiceError(f"角色清洗解析失败：{exc}", raw_response = raw) from exc
            if not isinstance(parsed, list):
                raise AnalysisServiceError("角色清洗解析失败：模型返回的不是 JSON 数组。", raw_response = raw)
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                key = normalize_text(item.get("name", "")).casefold()
                row = known.get(key)
                if row is None:
                    continue
                role = normalize_text(item.get("role", "")).casefold()
                if role not in self.CHARACTER_CLEAN_ROLES:
                    role = "side"
                judged[key] = {
                    "name": row.get("name", ""),
                    "role": role,
                    "faction": normalize_text(item.get("faction", ""))[:16],
                    "note": normalize_text(item.get("note", ""))[:40],
                }
        self.info(
            f"[Workbench] 角色清洗完成：{len(judged)} / {len(selected)} 个名字有判定，"
            f"tokens {prompt_tokens}/{completion_tokens}"
        )
        return {
            "judged": judged,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            # 分批调用会攒出好几段思考，只把最后 6000 字带回去，够看又不至于撑爆响应。
            "think": (chr(10) + chr(10)).join(thinks)[-6000:],
        }

    def analyze_relations(
        self,
        config: Config,
        candidate_edges: Sequence[dict[str, Any]],
        worldbook_draft: Any,
        *,
        max_pairs: int | None = None,
    ) -> dict[str, Any]:
        """用 AI 复核规则挖出的关系边。

        candidate_edges 是 RelationMiner 输出整理后的候选（含 from/to/word/relation/
        category/count/samples），只复核有证据的边；返回 applied/rejected 明细与 token 用量。
        """
        if not candidate_edges:
            return {"applied": [], "rejected": [], "prompt_tokens": 0, "completion_tokens": 0}
        platform = self.ensure_analysis_ready(config, engine_reserved = False)
        limit = max(1, int(max_pairs or self.RELATION_REVIEW_MAX_PAIRS))
        selected = list(candidate_edges)[:limit]
        prompt = self.build_relation_review_prompt(selected, worldbook_draft)
        raw, input_tokens, output_tokens = self.request_json_text_verbose(
            config, platform, prompt, round_index = 0, label = "关系复核",
        )
        try:
            parsed = repair.loads(raw)
        except Exception as exc:
            raise AnalysisServiceError(f"关系复核解析失败：{exc}", raw_response = raw) from exc
        if not isinstance(parsed, list):
            raise AnalysisServiceError("关系复核解析失败：模型返回的不是 JSON 数组。", raw_response = raw)

        # 只认「输入清单里出现过的 from/to 对」；模型幻觉出来的人物对直接丢弃。
        index_by_pair: dict[tuple[str, str], dict[str, Any]] = {}
        for row in selected:
            key = (normalize_text(row.get("from", "")).casefold(), normalize_text(row.get("to", "")).casefold())
            index_by_pair.setdefault(key, row)

        applied: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for item in parsed:
            if not isinstance(item, dict):
                continue
            key = (normalize_text(item.get("from", "")).casefold(), normalize_text(item.get("to", "")).casefold())
            row = index_by_pair.get(key)
            if row is None:
                continue
            # 模型偶尔会把同一个人物对吐两遍（一次 keep 一次否决），只认第一条。
            if key in seen:
                continue
            seen.add(key)
            entry = {
                "from": row.get("from", ""),
                "to": row.get("to", ""),
                "word": row.get("word", ""),
                "relation": normalize_text(item.get("relation", "")) or row.get("relation", ""),
                "category": normalize_relation_category(item.get("category", "")),
                # count/samples 原样带回写回端：候选里已经按人物对合并过全部规则边。
                "count": int(row.get("count") or 0),
                "samples": [normalize_text(text) for text in (row.get("samples") or [])],
                "keep": bool(item.get("keep", False)),
                "reason": normalize_text(item.get("reason", "")),
            }
            (applied if entry["keep"] else rejected).append(entry)
        self.info(
            f"[Workbench] 关系复核完成：{len(applied)} 条确认 / {len(rejected)} 条误判，"
            f"tokens {input_tokens}/{output_tokens}"
        )
        return {
            "applied": applied,
            "rejected": rejected,
            "prompt_tokens": int(input_tokens),
            "completion_tokens": int(output_tokens),
            "think": str(getattr(self, "_last_think", "") or "")[-4000:],
        }

    def infer_relations(
        self,
        config: Config,
        candidate_pairs: Sequence[dict[str, Any]],
        worldbook_draft: Any,
        *,
        max_pairs: int | None = None,
    ) -> dict[str, Any]:
        """按同场共现 + 双方人设让模型推断关系。

        规则关系靠「称谓词 × 角色变量名」，变量名是 s/p 这种短名的工程一条都挖不到；
        但每张角色卡都记着「和谁同场过多少次」，这是现成的弱证据。这一步把它交给模型，
        让它结合身份/性格/关系备注判断「这两个人是什么关系」。keep=false 表示资料不足，
        只计入 rejected 计数、不写回任何卡（没有规则边可留档）。
        """
        if not candidate_pairs:
            return {"applied": [], "rejected": [], "prompt_tokens": 0, "completion_tokens": 0}
        platform = self.ensure_analysis_ready(config, engine_reserved = False)
        limit = max(1, int(max_pairs or self.RELATION_INFER_MAX_PAIRS))
        selected = list(candidate_pairs)[:limit]
        prompt = self.build_relation_infer_prompt(selected, worldbook_draft)
        raw, input_tokens, output_tokens = self.request_json_text_verbose(
            config, platform, prompt, round_index = 0, label = "关系推断",
        )
        try:
            parsed = repair.loads(raw)
        except Exception as exc:
            raise AnalysisServiceError(f"关系推断解析失败：{exc}", raw_response = raw) from exc
        if not isinstance(parsed, list):
            raise AnalysisServiceError("关系推断解析失败：模型返回的不是 JSON 数组。", raw_response = raw)

        # 只认输入清单里的人物对；模型幻觉出来的名字直接丢弃。
        index_by_pair: dict[tuple[str, str], dict[str, Any]] = {}
        for row in selected:
            key = (normalize_text(row.get("from", "")).casefold(), normalize_text(row.get("to", "")).casefold())
            index_by_pair.setdefault(key, row)

        applied: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for item in parsed:
            if not isinstance(item, dict):
                continue
            key = (normalize_text(item.get("from", "")).casefold(), normalize_text(item.get("to", "")).casefold())
            row = index_by_pair.get(key)
            if row is None or key in seen:
                continue
            seen.add(key)
            relation = normalize_text(item.get("relation", ""))
            entry = {
                "from": row.get("from", ""),
                "to": row.get("to", ""),
                # 同场次数直接当证据强度写进 count，前端按它排序/显示。
                "count": max(int(row.get("count") or 0), 1),
                "relation": relation,
                "category": normalize_relation_category(item.get("category", "")),
                "keep": bool(item.get("keep", False)) and relation != "",
                "reason": normalize_text(item.get("reason", "")),
            }
            (applied if entry["keep"] else rejected).append(entry)
        self.info(
            f"[Workbench] 关系推断完成：{len(applied)} 对采纳 / {len(rejected)} 对证据不足，"
            f"tokens {input_tokens}/{output_tokens}"
        )
        return {
            "applied": applied,
            "rejected": rejected,
            "prompt_tokens": int(input_tokens),
            "completion_tokens": int(output_tokens),
            "think": str(getattr(self, "_last_think", "") or "")[-4000:],
        }
