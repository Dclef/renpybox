from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import json_repair as repair

from base.Base import Base
from module.Cache.CacheItem import CacheItem
from module.Cache.CacheManager import CacheManager
from module.Config import Config
from module.Engine.Engine import Engine
from module.Engine.TaskRequester import TaskRequester
from module.File.FileManager import FileManager
from module.Workbench.CharacterScanner import CharacterCandidate, CharacterScanner
from module.Workbench.WorkbenchData import (
    ANALYSIS_SCOPE_CURRENT,
    ANALYSIS_SCOPE_FULL,
    create_default_character_card,
    normalize_analysis_scope,
    normalize_character_card,
    normalize_character_cards,
    normalize_text,
    normalize_worldbook,
)


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

    def __init__(self) -> None:
        super().__init__()
        self.scanner = CharacterScanner()

    def ensure_analysis_ready(self, config: Config) -> dict[str, Any]:
        """校验分析前置条件。"""
        if Engine.get().get_status() != Engine.Status.IDLE:
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

    def analyze_all(self, config: Config, scope: str) -> AnalysisResult:
        """生成世界观和角色卡草稿。"""
        scope = normalize_analysis_scope(scope)
        platform = self.ensure_analysis_ready(config)
        items, source_summary = self.load_scope_items(config, scope)
        candidates = self.scanner.build_candidates(config, items, self.resolve_project_root(config))
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
        return AnalysisResult(
            scope = scope,
            worldbook_draft = worldbook_draft,
            character_drafts = character_drafts,
            worldbook_raw = worldbook_raw,
            character_raw = character_raw,
            source_summary = source_summary,
        )

    def generate_worldbook_only(self, config: Config, scope: str) -> AnalysisResult:
        """仅生成世界观草稿。"""
        scope = normalize_analysis_scope(scope)
        platform = self.ensure_analysis_ready(config)
        items, source_summary = self.load_scope_items(config, scope)
        candidates = self.scanner.build_candidates(config, items, self.resolve_project_root(config))
        worldbook_draft, worldbook_raw = self.generate_worldbook_draft(
            config = config,
            platform = platform,
            scope = scope,
            items = items,
            candidates = candidates,
        )
        return AnalysisResult(
            scope = scope,
            worldbook_draft = worldbook_draft,
            character_drafts = [],
            worldbook_raw = worldbook_raw,
            character_raw = [],
            source_summary = source_summary,
        )

    def generate_character_only(
        self,
        config: Config,
        scope: str,
        card_id: str | None = None,
    ) -> AnalysisResult:
        """生成角色卡草稿，可选单角色。"""
        scope = normalize_analysis_scope(scope)
        platform = self.ensure_analysis_ready(config)
        items, source_summary = self.load_scope_items(config, scope)
        candidates = self.scanner.build_candidates(config, items, self.resolve_project_root(config))
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
            sample_count = len(current_card.get("sample_lines", [])),
            low_confidence = len(current_card.get("sample_lines", [])) < 3,
        )
        return [candidate]

    def resolve_project_root(self, config: Config) -> Path | None:
        """解析项目根目录。"""
        raw = normalize_text(getattr(config, "renpy_game_folder", ""))
        if raw == "":
            return None
        path = Path(raw)
        if path.name.lower() == "game":
            return path.parent
        return path

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
        output_folder = normalize_text(getattr(config, "output_folder", ""))
        if output_folder == "":
            return []

        cache_manager = CacheManager(service = False)
        cache_manager.load_items_from_file(output_folder)
        return self.filter_analysis_items(cache_manager.get_items())

    def load_input_items(self, config: Config) -> list[CacheItem]:
        """读取当前输入目录条目。"""
        working = copy.deepcopy(config)
        project, items = FileManager(working).read_from_path()
        del project
        return self.filter_analysis_items(items)

    def load_full_project_items(self, config: Config) -> list[CacheItem]:
        """读取全项目源码条目。"""
        project_root = self.resolve_project_root(config)
        if project_root is None:
            raise AnalysisServiceError("未配置 Ren'Py 项目目录，无法执行全项目分析。")

        game_dir = project_root / "game"
        if game_dir.exists() is False:
            raise AnalysisServiceError("未找到 game 目录，无法执行全项目分析。")

        working = copy.deepcopy(config)
        working.input_folder = str(game_dir)
        working.output_folder = normalize_text(getattr(config, "output_folder", "")) or str(project_root / "output")
        working.renpy_source_translate = True
        working.renpy_hook_translate = False
        project, items = FileManager(working).read_from_path()
        del project
        return self.filter_analysis_items(items)

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

    def select_representative_texts(
        self,
        items: list[CacheItem],
        *,
        max_items: int,
    ) -> list[str]:
        """从条目中抽取代表文本。"""
        texts = []
        seen: set[str] = set()
        for item in items:
            text = normalize_text(item.get_src())
            if text == "":
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            texts.append(text[:220])

        if len(texts) <= max_items:
            return texts

        result: list[str] = []
        last_index = max(1, len(texts) - 1)
        for idx in range(max_items):
            target = round(idx * last_index / max(1, max_items - 1))
            result.append(texts[target])
        return result

    def request_json_text(
        self,
        config: Config,
        platform: dict[str, Any],
        prompt: str,
        *,
        round_index: int = 0,
    ) -> str:
        """发起一次 JSON 文本请求。"""
        requester = TaskRequester(config, platform, round_index)
        skip, _, response_text, _, _ = requester.request(
            [
                {
                    "role": "user",
                    "content": prompt,
                }
            ]
        )
        if skip or not isinstance(response_text, str) or response_text.strip() == "":
            raise AnalysisServiceError("AI 分析接口返回为空，请稍后重试。")
        return response_text.strip()

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
        excerpts = self.select_representative_texts(items, max_items = excerpt_limit)
        top_characters = [candidate.name for candidate in candidates[:12]]

        prompt = "\n".join(
            [
                "你是视觉小说本地化策划助手，需要根据项目样本生成“翻译工作台”用的世界观草稿。",
                "请严格只输出 JSON 对象，不要输出 Markdown、解释、前后缀、代码块。",
                "字段必须且只能包含：project_name, genre, setting_summary, era_background, tone_style, narrative_rules, format_rules, spoiler_notes。",
                "约束：",
                "1. 轻剧透：允许总结背景、关系、说话风格、公开设定。",
                "2. 不要把关键反转、最终真相、结局直接写进 setting_summary。",
                "3. 如果确实需要提醒翻译者注意隐藏身份或潜在线索，只写进 spoiler_notes。",
                "4. narrative_rules 和 format_rules 要聚焦翻译执行建议，不要写空话。",
                "5. 所有字段值都必须是字符串。",
                f"分析范围：{'当前翻译范围' if scope == ANALYSIS_SCOPE_CURRENT else '全项目扩展分析'}",
                "高频角色候选：",
                "\n".join(f"- {name}" for name in top_characters) if top_characters else "- 暂无",
                "项目样本文本：",
                "\n".join(f"{idx + 1}. {text}" for idx, text in enumerate(excerpts)) if excerpts else "暂无样本",
                "请输出 JSON：",
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

        raw = self.request_json_text(config, platform, prompt, round_index = 0)
        try:
            parsed = repair.loads(raw)
        except Exception as exc:
            raise AnalysisServiceError(f"世界观草稿解析失败：{exc}", raw_response = raw) from exc

        if not isinstance(parsed, dict):
            raise AnalysisServiceError("世界观草稿解析失败：模型返回的不是 JSON 对象。", raw_response = raw)

        return normalize_worldbook(parsed), raw

    def generate_character_drafts(
        self,
        config: Config,
        platform: dict[str, Any],
        scope: str,
        candidates: list[CharacterCandidate],
        worldbook_draft: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """批量生成角色卡草稿。"""
        normalized_world = normalize_worldbook(worldbook_draft)
        drafts: list[dict[str, Any]] = []
        raws: list[str] = []
        if not candidates:
            return drafts, raws

        chunk_size = 8
        for offset in range(0, len(candidates), chunk_size):
            chunk = candidates[offset: offset + chunk_size]
            prompt = self.build_character_prompt(scope, chunk, normalized_world)
            raw = self.request_json_text(config, platform, prompt, round_index = offset // chunk_size)
            raws.append(raw)
            try:
                parsed = repair.loads(raw)
            except Exception as exc:
                raise AnalysisServiceError(f"角色卡草稿解析失败：{exc}", raw_response = raw) from exc

            if not isinstance(parsed, list):
                raise AnalysisServiceError("角色卡草稿解析失败：模型返回的不是 JSON 数组。", raw_response = raw)

            drafts.extend(self.normalize_character_drafts_from_response(parsed, chunk))

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
            lines = [
                f"角色名: {candidate.name}",
                f"已有译名: {candidate.name_translation or '暂无'}",
                f"相关角色: {', '.join(candidate.related_names) if candidate.related_names else '暂无'}",
                f"样本数量: {candidate.sample_count}",
                f"低置信度: {'是' if candidate.low_confidence else '否'}",
                "样本台词:",
            ]
            if candidate.sample_lines:
                lines.extend(f"- {line}" for line in candidate.sample_lines[:8])
            else:
                lines.append("- 暂无可用样本")
            candidate_blocks.append("\n".join(lines))

        return "\n".join(
            [
                "你是视觉小说本地化策划助手，需要根据角色样本生成“翻译工作台”用的人设草稿。",
                "请严格只输出 JSON 数组，不要输出 Markdown、解释、代码块。",
                "数组元素必须且只能包含以下键：name, aliases, match_keywords, identity, personality, speech_style, relationship_notes, prompt_notes, sample_lines。",
                "约束：",
                "1. 轻剧透：可总结公开身份、关系、语气、口癖，但避免直接揭露关键反转。",
                "2. 如果证据不足，请在 prompt_notes 首句注明“低置信度候选”。",
                "3. aliases 和 match_keywords 必须是字符串数组。",
                "4. sample_lines 请从给定样本中挑选代表句，数量 1-6 条。",
                "5. 所有字符串必须使用中文描述，除角色名本体外不要输出英文注释。",
                f"分析范围：{'当前翻译范围' if scope == ANALYSIS_SCOPE_CURRENT else '全项目扩展分析'}",
                "世界观摘要：",
                f"- 项目名称：{world_text.get('project_name', '') or '未确定'}",
                f"- 类型：{world_text.get('genre', '') or '未确定'}",
                f"- 背景摘要：{world_text.get('setting_summary', '') or '未确定'}",
                f"- 时代背景：{world_text.get('era_background', '') or '未确定'}",
                f"- 语气风格：{world_text.get('tone_style', '') or '未确定'}",
                "角色候选：",
                "\n\n".join(candidate_blocks),
                "请输出 JSON 数组，例如：",
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
    ) -> list[dict[str, Any]]:
        """规范化模型返回的角色草稿。"""
        candidate_by_name = {
            candidate.name.casefold(): candidate
            for candidate in candidates
        }
        drafts: list[dict[str, Any]] = []
        used: set[str] = set()

        for raw in parsed:
            if not isinstance(raw, dict):
                continue
            name = normalize_text(raw.get("name", ""))
            if name == "":
                continue
            candidate = candidate_by_name.get(name.casefold())
            if candidate is None:
                continue

            card = create_default_character_card(candidate.name)
            card["aliases"] = raw.get("aliases", []) + candidate.aliases
            card["match_keywords"] = raw.get("match_keywords", []) + candidate.match_keywords + [candidate.name]
            card["identity"] = normalize_text(raw.get("identity", ""))
            card["personality"] = normalize_text(raw.get("personality", ""))
            card["speech_style"] = normalize_text(raw.get("speech_style", ""))
            card["relationship_notes"] = normalize_text(raw.get("relationship_notes", ""))
            prompt_notes = normalize_text(raw.get("prompt_notes", ""))
            if candidate.low_confidence and "低置信度候选" not in prompt_notes:
                prompt_notes = ("低置信度候选。" + prompt_notes).strip("。")
            card["prompt_notes"] = prompt_notes
            model_samples = raw.get("sample_lines", [])
            card["sample_lines"] = model_samples[:6] if isinstance(model_samples, list) and model_samples else candidate.sample_lines[:6]
            card["name_translation"] = candidate.name_translation
            drafts.append(normalize_character_card(card))
            used.add(candidate.name.casefold())

        for candidate in candidates:
            if candidate.name.casefold() in used:
                continue
            fallback = candidate.as_card_seed()
            drafts.append(normalize_character_card(fallback))
        return drafts
