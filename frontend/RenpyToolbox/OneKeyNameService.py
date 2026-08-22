"""一键翻译流程的人名/术语自动识别服务。

从 OneKeyTranslatePage 外移的非 UI 逻辑（行为零变化）：角色候选扫描、
变量引用收集、术语分类与本地 spaCy NER 模型懒加载。模块级单例——页面
为单例导航页，NER 模型跨页面实例共享与原语义等价；测试用 reset() 隔离。
"""

import time
from pathlib import Path

from base.LogManager import LogManager
from base.PathHelper import get_resource_path
from module.Engine.Translator.ProjectAssetsRepository import ProjectAssetsRepository
from module.Config import Config
from module.Workbench.CharacterScanner import CharacterCandidate, CharacterScanner
from module.Renpy.ProjectPaths import RenpyProjectPaths


class OneKeyNameService:

    _instance: "OneKeyNameService | None" = None

    def __init__(self) -> None:
        self._ner_model = None
        self._ner_model_loaded = False

    @classmethod
    def get(cls) -> "OneKeyNameService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """测试隔离用：清空单例（含 NER 模型缓存）。"""
        cls._instance = None


    def extract_character_names(self, game_dir: str, tl_name: str, *, force: bool = False):
        """自动扫描角色候选、角色草稿和变量引用。"""
        if not game_dir:
            return

        paths = RenpyProjectPaths.from_path(
            game_dir,
            tl_name or "chinese",
        )
        game_path = paths.game_dir if paths is not None else Path(game_dir) / "game"
        if not game_path.exists():
            return
            
        found_names = set()
        found_preserves = set()  # 用于存储变量引用
        candidate_cards: list[dict] = []
        
        config = Config().load()
        cache_key = str(game_path.resolve())
        auto_cache = dict(getattr(config, "glossary_auto_scan_cache", {}) or {})

        if not force and cache_key in auto_cache:
            LogManager.get().info(
                "Skip character scan: already scanned for %s", cache_key
            )
            return

        try:
            # 统一复用工作台扫描器，确保一键流程与角色工作台识别结果一致。
            scanner = CharacterScanner()
            scan_result = scanner.scan_project(game_path.parent)
            found_names.update(scan_result.names)
            found_preserves.update(scan_result.preserves)

            # 将本地扫描结果先形成待确认角色草稿；AI 分析仍由工作台按需触发。
            glossary_names = scanner.collect_glossary_character_names(config)
            for name in sorted(scan_result.names, key = lambda value: value.casefold()):
                samples = list(scan_result.speaker_samples.get(name, []))[:12]
                candidate = CharacterCandidate(
                    name = name,
                    match_keywords = [name],
                    sample_lines = samples,
                    related_names = list(scan_result.co_occurrence.get(name, []))[:8],
                    name_translation = glossary_names.get(name, ""),
                    sample_count = len(samples),
                    low_confidence = len(samples) < 3,
                )
                candidate_cards.append(candidate.as_card_seed())
        except Exception as exc:
            LogManager.get().warning(f"统一角色扫描失败：{exc}")
            
        # 角色名由项目资产仓库统一维护为待确认候选；这里只保留变量引用的
        # legacy text_preserve 配置同步，避免角色术语绕过项目资产边界。
        self._update_config(set(), found_preserves, config)

        # 同步到稳定的项目资产仓库。空译名保留为候选，避免项目缓存已经
        # 存在时仅修改全局 Config 却不进入实际翻译快照。
        try:
            repository = ProjectAssetsRepository.from_config(config)
            state = repository.load(config)
            term_entries = [
                {
                    "source": self._clean_text_for_type(name),
                    "target": "",
                    "note": "一键流程自动提取角色名",
                    "type": "角色",
                }
                for name in sorted(found_names, key = lambda value: value.casefold())
                if self._clean_text_for_type(name)
            ]
            analysis_candidates = (
                repository.merge_analysis_terms(term_entries)
                if term_entries
                else state.analysis_candidates
            )

            # 将本地扫描出的角色放入工作台待确认草稿，避免一键流程只更新
            # 全局术语表而遗漏角色样本和说话风格上下文。
            if candidate_cards:
                existing_drafts = analysis_candidates.get("character_drafts", [])
                existing_drafts = [
                    item for item in existing_drafts
                    if isinstance(item, dict)
                ] if isinstance(existing_drafts, list) else []
                existing_ids = {
                    str(item.get("id", "")).strip()
                    for item in existing_drafts
                    if str(item.get("id", "")).strip()
                }
                for card in candidate_cards:
                    card_id = str(card.get("id", "")).strip()
                    if card_id and card_id not in existing_ids:
                        existing_drafts.append(card)
                        existing_ids.add(card_id)
                analysis_candidates["character_drafts"] = existing_drafts
                repository.save_analysis_candidates(analysis_candidates)

            current_preserves = [item.to_dict() for item in state.assets.do_not_translate]
            current_sources = {
                str(item.get("source", "")).strip()
                for item in current_preserves
                if isinstance(item, dict)
            }
            current_preserves.extend(
                {"source": value, "target": "", "note": "一键流程自动提取变量"}
                for value in sorted(found_preserves)
                if value not in current_sources
            )
            if found_preserves:
                repository.replace_do_not_translate(
                    current_preserves,
                    enabled = True,
                )
        except Exception as exc:
            LogManager.get().warning(f"同步一键项目资产失败：{exc}")

        auto_cache[cache_key] = time.time()
        config.glossary_auto_scan_cache = auto_cache
        config.save()

    @staticmethod
    def _clean_text_for_type(text: str) -> str:
        """去除格式标签/空白，便于分类"""
        if not text:
            return ""
        import re
        cleaned = re.sub(r"\{/?[^}]+\}", "", text)
        return cleaned.replace("\u3000", " ").strip()

    @staticmethod
    def _should_ignore_extracted_name(text: str) -> bool:
        """过滤明显无效的候选（如单字母 A/Q/变量样式）"""
        if not text:
            return True
        if len(text) <= 1:
            return True
        # 单字母 + 可选标点（A. / Q. / A）
        import re
        if re.fullmatch(r"[A-Za-z](?:\.|!|\?)?", text):
            return True
        # 过短且包含点/下划线通常是变量或占位
        if len(text) <= 3 and any(ch in text for ch in ".:_"):
            return True
        return False

    @staticmethod
    def _categorize_term(text: str, default: str = "") -> str:
        """基于 LocalGlossary 的关键词规则做简易分类"""
        if not text:
            return default
        t = text.strip()
        lower = t.lower()
        place_keywords = [
            "city", "village", "town", "forest", "mountain", "hill", "park", "garden",
            "school", "academy", "college", "campus", "church", "temple", "shrine",
            "castle", "tower", "dungeon", "cave", "ruins", "harbor", "port", "station",
            "beach", "island", "lake", "river", "bridge", "street", "road", "avenue",
            "hotel", "inn", "bar", "cafe", "shop", "market", "library"
        ]
        item_keywords = [
            "sword", "blade", "dagger", "bow", "gun", "rifle", "pistol", "armor", "shield",
            "ring", "necklace", "amulet", "bracelet", "crown", "helmet", "boots", "gloves",
            "potion", "elixir", "herb", "scroll", "book", "map", "key", "card", "ticket",
            "coin", "gem", "crystal", "stone", "orb", "staff", "wand", "medal"
        ]
        if any(k in lower for k in place_keywords):
            return "地名"
        if any(k in lower for k in item_keywords):
            return "物品"
        words = t.split()
        if words and all(w[:1].isupper() for w in words if w):
            return default or ""
        return default

    def _find_ner_model_path(self) -> Path | None:
        """查找本地 NER 模型路径（resource/Models/ner 下），兼容打包路径."""
        candidates: list[Path] = []
        candidate_roots = [
            Path(get_resource_path("resource", "Models", "ner")),
        ]
        for model_root in candidate_roots:
            if not model_root.exists():
                continue
            for p in model_root.iterdir():
                if p.is_dir() and (p / "meta.json").exists():
                    candidates.append(p)
        if not candidates:
            return None
        candidates.sort()
        return candidates[0]

    def _load_ner_model(self):
        """懒加载 spaCy NER 模型，失败则返回 None"""
        if self._ner_model_loaded:
            return self._ner_model
        self._ner_model_loaded = True
        try:
            import spacy
        except Exception:
            self._ner_model = None
            return None
        model_path = self._find_ner_model_path()
        if not model_path:
            self._ner_model = None
            return None
        try:
            self._ner_model = spacy.load(
                str(model_path),
                exclude=["parser", "tagger", "lemmatizer", "attribute_ruler", "tok2vec"],
            )
        except Exception:
            self._ner_model = None
        return self._ner_model

    def _ner_guess_type(self, text: str, default: str = "") -> str:
        """使用 NER 预测类别（角色/地名/组织/物品），失败则返回默认"""
        nlp = self._load_ner_model()
        if not nlp:
            return default
        label_map = {
            "PER": "角色",
            "PERSON": "角色",
            "PER_NO": "角色",
            "LOC": "地名",
            "GPE": "地名",
            "ORG": "组织",
            "FAC": "地名",
            "PRODUCT": "物品",
            "ITEM": "物品",
        }
        try:
            doc = nlp(text)
            for ent in doc.ents:
                mapped = label_map.get(ent.label_)
                if mapped:
                    return mapped
        except Exception:
            return default
        return default

    def _update_config(self, found_names, found_preserves, config):
        """更新配置文件，返回是否写入新数据"""
        updated = False

        # 更新术语表
        if found_names:
            existing_src = set()
            if config.glossary_data:
                for item in config.glossary_data:
                    if isinstance(item, dict):
                        existing_src.add(item.get("src", ""))
                    elif isinstance(item, str):
                        existing_src.add(item)

            new_entries = []
            for name in found_names:
                cleaned = self._clean_text_for_type(name)
                if not cleaned or cleaned in existing_src:
                    continue
                if self._should_ignore_extracted_name(cleaned):
                    continue
                type_guess = self._ner_guess_type(cleaned, default="") or self._categorize_term(cleaned, default="")
                new_entries.append({
                    "src": cleaned,
                    "dst": "",
                    "info": "角色名 (自动提取)",
                    "type": type_guess
                })

            if new_entries:
                if not config.glossary_data:
                    config.glossary_data = []
                config.glossary_data.extend(new_entries)
                config.glossary_enable = True
                updated = True
                
        # 更新禁翻表
        if found_preserves:
            existing_preserve = set()
            if config.text_preserve_data:
                for item in config.text_preserve_data:
                    if isinstance(item, dict):
                        existing_preserve.add(item.get("src", ""))
                    elif isinstance(item, str):
                        existing_preserve.add(item)
                        
            new_preserves = []
            for text in found_preserves:
                if text not in existing_preserve:
                    new_preserves.append({"src": text})
                    
            if new_preserves:
                if not config.text_preserve_data:
                    config.text_preserve_data = []
                config.text_preserve_data.extend(new_preserves)
                config.text_preserve_enable = True
                updated = True
                
        return updated

    @staticmethod
    def _looks_like_character_name(name: str) -> bool:
        if not name:
            return False
        if any(char.isupper() for char in name):
            return True
        if any(ord(char) > 127 and char.isalpha() for char in name):
            return True
        return False
