"""术语候选抽取服务。"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Sequence

import json_repair as repair

from base.Base import Base
from module.Config import Config
from module.Engine.TaskRequester import TaskRequester
from module.Extract.ReplaceGenerator import (
    _get_game_dir,
    _is_character_name,
    _strip_format_tags,
    collect_glossary_candidate_texts,
    extract_names_from_game,
)
from module.Text.SkipRules import should_skip_text

AUTO_COMMENT = "术语候选 (自动提取)"
DEFAULT_TL_NAME = "chinese"

ProgressCallback = Callable[[str, int], None]
CancelCallback = Callable[[], bool]


class GlossaryCandidateDecoder(Base):
    """解析术语候选抽取响应。"""

    RE_MARKDOWN_FENCE = re.compile(r"```(?:json|jsonline)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)

    def decode(self, response_text: str) -> list[dict[str, str]]:
        if not isinstance(response_text, str) or response_text.strip() == "":
            return []

        candidates: list[dict[str, str]] = []
        candidates.extend(self._decode_jsonline(response_text))

        if candidates == []:
            fenced_match = self.RE_MARKDOWN_FENCE.search(response_text)
            if fenced_match is not None:
                candidates.extend(self._decode_jsonline(fenced_match.group(1)))

        if candidates == []:
            candidates.extend(self._decode_whole_json(response_text))

        return candidates

    def _decode_jsonline(self, text: str) -> list[dict[str, str]]:
        results: list[dict[str, str]] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if line == "" or line.startswith("```"):
                continue

            try:
                payload = repair.loads(line)
            except Exception:
                continue

            entry = self._normalize_payload(payload)
            if entry is not None:
                results.append(entry)
        return results

    def _decode_whole_json(self, text: str) -> list[dict[str, str]]:
        try:
            payload = repair.loads(text)
        except Exception:
            return []

        if isinstance(payload, dict):
            entry = self._normalize_payload(payload)
            return [entry] if entry is not None else []

        if isinstance(payload, list):
            results: list[dict[str, str]] = []
            for item in payload:
                entry = self._normalize_payload(item)
                if entry is not None:
                    results.append(entry)
            return results

        return []

    def _normalize_payload(self, payload: Any) -> dict[str, str] | None:
        if not isinstance(payload, dict):
            return None

        src = str(
            payload.get("src")
            or payload.get("term")
            or payload.get("name")
            or payload.get("text")
            or ""
        ).strip()
        if src == "":
            return None

        type_name = str(
            payload.get("type")
            or payload.get("category")
            or payload.get("kind")
            or payload.get("label")
            or payload.get("info")
            or ""
        ).strip()

        return {
            "src": src,
            "dst": "",
            "type": type_name,
            "comment": AUTO_COMMENT,
            "info": AUTO_COMMENT,
            "case_sensitive": False,
        }


class GlossaryCandidateService(Base):
    """从 Ren'Py 源码中抽取术语候选。"""

    SUPPORTED_LLM_FORMATS = {
        Base.APIFormat.OPENAI,
        Base.APIFormat.GOOGLE,
        Base.APIFormat.ANTHROPIC,
        Base.APIFormat.SAKURALLM,
    }
    CONNECTOR_WORDS = {"of", "the", "and", "de", "la", "da", "van", "von"}
    COMMON_SINGLE_WORDS = {
        "The",
        "This",
        "That",
        "These",
        "Those",
        "There",
        "Here",
        "You",
        "Your",
        "Yours",
        "They",
        "Them",
        "Their",
        "We",
        "Our",
        "Ours",
        "He",
        "His",
        "She",
        "Her",
        "Hers",
        "It",
        "Its",
        "I",
        "My",
        "Mine",
        "Me",
        "Hello",
        "Yes",
        "No",
        "Okay",
        "Thanks",
        "Thank",
        "Please",
        "Well",
        "Right",
        "Left",
        "Back",
        "Next",
        "Continue",
        "Start",
        "Load",
        "Save",
        "Quick",
        "Auto",
        "Menu",
        "History",
        "Preferences",
        "Return",
        "Scene",
    }
    UI_EXACT_TERMS = {
        "about",
        "accesses the game menu",
        "after choices",
        "all",
        "answer",
        "arrow keys",
        "auto",
        "auto-forward time",
        "automatic saves",
        "back",
        "calibrate",
        "camera",
        "center name box",
        "chat",
        "contacts",
        "ctrl",
        "enter",
        "escape",
        "exit",
        "followers",
        "following",
        "fullscreen",
        "gallery",
        "gamepad",
        "help",
        "history",
        "keyboard",
        "left click",
        "left shoulder",
        "left trigger",
        "load",
        "main menu",
        "middle click",
        "mouse",
        "quick menu",
        "right click",
        "right shoulder",
        "right trigger",
        "save",
        "shift",
        "skip",
        "space",
        "start",
    }
    UI_CONTAINS_PATTERNS = (
        "click",
        "trigger",
        "shoulder",
        "game menu",
        "main menu",
        "quick menu",
        "name box",
        "auto-forward",
    )
    TITLE_PREFIXES = {
        "mr",
        "mrs",
        "ms",
        "miss",
        "dr",
        "doctor",
        "prof",
        "professor",
        "sir",
        "lady",
        "lord",
        "captain",
        "commander",
        "queen",
        "king",
        "prince",
        "princess",
    }
    PLACE_KEYWORDS = (
        "city",
        "village",
        "town",
        "forest",
        "mountain",
        "hill",
        "park",
        "garden",
        "school",
        "academy",
        "college",
        "campus",
        "church",
        "temple",
        "shrine",
        "castle",
        "tower",
        "dungeon",
        "cave",
        "ruins",
        "harbor",
        "port",
        "station",
        "beach",
        "island",
        "lake",
        "river",
        "bridge",
        "street",
        "road",
        "avenue",
        "hotel",
        "inn",
        "bar",
        "cafe",
        "shop",
        "market",
        "library",
        "palace",
        "district",
    )
    ORG_KEYWORDS = (
        "guild",
        "order",
        "church",
        "army",
        "guard",
        "company",
        "clan",
        "family",
        "house",
        "society",
        "union",
        "legion",
        "alliance",
        "federation",
        "kingdom",
        "empire",
        "council",
        "committee",
        "team",
        "squad",
        "group",
        "band",
    )
    ITEM_KEYWORDS = (
        "sword",
        "blade",
        "dagger",
        "bow",
        "gun",
        "rifle",
        "pistol",
        "armor",
        "shield",
        "ring",
        "necklace",
        "amulet",
        "bracelet",
        "crown",
        "helmet",
        "boots",
        "gloves",
        "potion",
        "elixir",
        "herb",
        "scroll",
        "book",
        "map",
        "key",
        "card",
        "ticket",
        "coin",
        "gem",
        "crystal",
        "stone",
        "orb",
        "staff",
        "wand",
        "medal",
        "artifact",
        "relic",
    )
    SPECIAL_ITEM_KEYWORDS = (
        "artifact",
        "relic",
        "amulet",
        "orb",
        "crystal",
        "gem",
        "medal",
        "crown",
        "sword",
        "blade",
        "dagger",
        "potion",
        "elixir",
        "scroll",
        "staff",
        "wand",
        "key",
    )
    TYPE_HINTS = {
        "角色": ("角色", "人名", "姓名", "person", "character", "male", "female", "per", "npc"),
        "地名": ("地名", "地点", "位置", "设施", "location", "place", "gpe", "loc", "fac"),
        "组织": ("组织", "家族", "阵营", "派系", "guild", "family", "faction", "org", "organization", "group"),
        "物品": ("物品", "道具", "装备", "artifact", "item", "product", "weapon", "relic"),
        "术语": ("术语", "其他", "生物", "怪物", "creature", "monster", "beast", "other", "entity"),
    }
    RE_WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*")
    RE_LATIN_TERM = re.compile(r"[A-Za-z]")
    RE_BOUNDARY_SAFE_TERM = re.compile(r"[A-Za-z0-9_ .'\-’]+")

    def __init__(
        self,
        *,
        config: Config,
        target_path: str | Path,
        platform: dict[str, Any] | None,
        progress_callback: ProgressCallback | None = None,
        cancel_callback: CancelCallback | None = None,
    ) -> None:
        super().__init__()
        self.config = config
        self.target_path = str(target_path)
        self.platform = platform if isinstance(platform, dict) else None
        self.progress_callback = progress_callback
        self.cancel_callback = cancel_callback
        self.decoder = GlossaryCandidateDecoder()

    def run(self) -> dict[str, Any]:
        game_dir = _get_game_dir(self.target_path)
        tl_name = str(getattr(self.config, "renpy_tl_folder", "") or DEFAULT_TL_NAME).strip() or DEFAULT_TL_NAME
        tl_name = self._normalize_tl_name(tl_name)

        self._ensure_not_cancelled()
        self._report("正在扫描源码候选文本...", 5)
        corpus_texts = collect_glossary_candidate_texts(self.target_path, tl_name = tl_name)
        if corpus_texts == ():
            raise ValueError("未在游戏源码中找到可用于术语扫描的文本")

        self._ensure_not_cancelled()
        self._report(f"已扫描 {len(corpus_texts)} 条候选文本，正在生成规则候选...", 20)
        rule_candidates = self._collect_rule_candidates(corpus_texts, game_dir)

        llm_candidates: list[dict[str, Any]] = []
        warnings: list[str] = []
        llm_chunks_total = 0
        llm_chunks_success = 0
        used_llm = False

        if self._can_use_llm_platform(self.platform):
            used_llm = True
            chunks = self._build_prompt_chunks(corpus_texts)
            llm_chunks_total = len(chunks)
            for index, chunk in enumerate(chunks):
                self._ensure_not_cancelled()
                percent = 20 + int(((index + 1) / max(1, llm_chunks_total)) * 60)
                self._report(
                    f"正在使用 LLM 抽取术语候选... ({index + 1}/{llm_chunks_total})",
                    percent,
                )
                success, payload = self._extract_chunk_with_llm(chunk, index)
                if success:
                    llm_chunks_success += 1
                    llm_candidates.extend(payload)
                elif payload:
                    warnings.append(str(payload))
        else:
            warnings.append("未找到支持术语抽取的 LLM，已仅使用规则候选。")

        self._ensure_not_cancelled()
        self._report("正在聚合候选术语...", 88)
        merged = self._merge_candidates(rule_candidates, llm_candidates)
        self._ensure_not_cancelled()
        enriched = self._attach_counts_and_contexts(merged, corpus_texts)

        self._ensure_not_cancelled()
        self._report("术语候选扫描完成", 100)
        return {
            "entries": enriched,
            "corpus_count": len(corpus_texts),
            "rule_candidate_count": len(rule_candidates),
            "llm_candidate_count": len(llm_candidates),
            "used_llm": used_llm,
            "llm_chunks_total": llm_chunks_total,
            "llm_chunks_success": llm_chunks_success,
            "warnings": warnings,
        }

    def _report(self, message: str, percent: int) -> None:
        if callable(self.progress_callback):
            self.progress_callback(message, percent)
        self.info(f"[GlossaryCandidate] {percent}% {message}")

    def _ensure_not_cancelled(self) -> None:
        """在关键阶段检查是否已请求取消。"""
        if callable(self.cancel_callback) and self.cancel_callback():
            raise InterruptedError("术语候选扫描已停止")

    @staticmethod
    def _normalize_tl_name(raw_tl: str) -> str:
        """兼容保存了完整 tl 路径的配置，仅保留语言目录名。"""
        raw_value = str(raw_tl or "").strip()
        if raw_value == "":
            return DEFAULT_TL_NAME
        try:
            path_name = Path(raw_value).name
            if path_name:
                return path_name
        except Exception:
            pass
        return raw_value

    def _can_use_llm_platform(self, platform: dict[str, Any] | None) -> bool:
        if not isinstance(platform, dict):
            return False
        return platform.get("api_format") in self.SUPPORTED_LLM_FORMATS

    def _build_prompt_chunks(self, texts: Sequence[str]) -> list[list[str]]:
        chunks: list[list[str]] = []
        current: list[str] = []
        current_length = 0

        for raw_text in texts:
            text = str(raw_text or "").strip()
            if text == "":
                continue

            projected_length = current_length + len(text)
            if current != [] and (len(current) >= 40 or projected_length > 2500):
                chunks.append(current)
                current = []
                current_length = 0

            current.append(text)
            current_length += len(text)

        if current != []:
            chunks.append(current)

        return chunks

    def _build_candidate_prompt(self, texts: Sequence[str]) -> list[dict[str, str]]:
        payload = "\n".join(
            json.dumps({str(index): text}, ensure_ascii = False)
            for index, text in enumerate(texts)
        )
        prompt = (
            "你是 Ren'Py 游戏本地化的术语抽取器。\n"
            "任务：从输入文本片段中提取适合加入本地词库的专有名词候选。\n"
            "只提取以下类别，并统一映射为这 5 类之一：角色、地名、组织、物品、术语。\n"
            "提取规则：\n"
            "1. 只提取角色名、地名/设施、组织/家族/阵营、特殊物品、特殊生物或其他专有名词。\n"
            "2. 不要输出普通词、完整句子、界面常用词、变量、占位符、路径、代码、函数名、文件名。\n"
            "3. 术语边界要尽量干净，不要包含 Mr.、Dr.、Sir、Lady、the 等常见称呼或冠词，除非它们是专名不可分割的一部分。\n"
            "4. dst 一律输出空字符串。\n"
            "5. 只输出 JSONLINE，不要解释，不要代码块。\n"
            "输出格式：\n"
            "{\"src\":\"<术语原文>\",\"dst\":\"\",\"type\":\"<类别>\"}\n"
            "输入：\n"
            f"{payload}"
        )
        return [
            {
                "role": "user",
                "content": prompt,
            }
        ]

    def _extract_chunk_with_llm(self, chunk: Sequence[str], index: int) -> tuple[bool, list[dict[str, Any]] | str]:
        if self.platform is None:
            return False, "未找到可用平台"

        requester = TaskRequester(self.config, self.platform, index)
        messages = self._build_candidate_prompt(chunk)
        skip, _, response_text, _, _ = requester.request(messages)
        if skip or not isinstance(response_text, str) or response_text.strip() == "":
            return False, f"第 {index + 1} 个分块未返回可解析结果"

        if '"blocked"' in response_text:
            return False, f"第 {index + 1} 个分块被安全过滤阻止"

        decoded = self.decoder.decode(response_text)
        if decoded == []:
            preview = response_text[:120].replace("\n", " ")
            return False, f"第 {index + 1} 个分块解析失败: {preview}"

        normalized: list[dict[str, Any]] = []
        for entry in decoded:
            src = self._normalize_candidate_text(entry.get("src", ""))
            if not self._is_viable_candidate_text(src):
                continue

            normalized.append(
                {
                    "src": src,
                    "dst": "",
                    "type": self._normalize_candidate_type(entry.get("type", ""), src),
                    "comment": AUTO_COMMENT,
                    "info": AUTO_COMMENT,
                    "case_sensitive": False,
                    "origin": "llm",
                }
            )

        if normalized == []:
            return False, f"第 {index + 1} 个分块没有产出有效术语"
        return True, normalized

    def _collect_rule_candidates(self, texts: Sequence[str], game_dir: Path) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        seen: set[str] = set()

        for name in sorted(extract_names_from_game(game_dir)):
            self._ensure_not_cancelled()
            src = self._normalize_candidate_text(name)
            if not self._is_viable_candidate_text(src):
                continue
            key = self._normalize_key(src)
            if key in seen:
                continue
            seen.add(key)
            results.append(
                {
                    "src": src,
                    "dst": "",
                    "type": "角色",
                    "comment": AUTO_COMMENT,
                    "info": AUTO_COMMENT,
                    "case_sensitive": False,
                    "origin": "rule_name",
                }
            )

        for raw_text in texts:
            self._ensure_not_cancelled()
            direct = self._normalize_candidate_text(raw_text)
            if self._should_keep_direct_candidate(direct):
                key = self._normalize_key(direct)
                if key not in seen:
                    seen.add(key)
                    results.append(
                        {
                            "src": direct,
                            "dst": "",
                            "type": self._guess_candidate_type(direct, default = "术语"),
                            "comment": AUTO_COMMENT,
                            "info": AUTO_COMMENT,
                            "case_sensitive": False,
                            "origin": "rule_direct",
                        }
                    )

            for phrase in self._extract_embedded_candidate_phrases(raw_text):
                key = self._normalize_key(phrase)
                if key in seen:
                    continue
                seen.add(key)
                results.append(
                    {
                        "src": phrase,
                        "dst": "",
                        "type": self._guess_candidate_type(phrase, default = "术语"),
                        "comment": AUTO_COMMENT,
                        "info": AUTO_COMMENT,
                        "case_sensitive": False,
                        "origin": "rule_phrase",
                    }
                )

        return results

    def _merge_candidates(
        self,
        rule_candidates: Sequence[dict[str, Any]],
        llm_candidates: Sequence[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        buckets: dict[str, dict[str, Any]] = {}

        for entry in list(rule_candidates) + list(llm_candidates):
            src = self._normalize_candidate_text(entry.get("src", ""))
            if not self._is_viable_candidate_text(src):
                continue

            key = self._normalize_key(src)
            bucket = buckets.setdefault(
                key,
                {
                    "src": src,
                    "dst": "",
                    "comment": AUTO_COMMENT,
                    "info": AUTO_COMMENT,
                    "case_sensitive": False,
                    "type_votes": Counter(),
                    "origins": set(),
                },
            )

            if self._prefer_display_src(src, bucket.get("src", "")):
                bucket["src"] = src

            origin = str(entry.get("origin", "") or "rule")
            bucket["origins"].add(origin)
            vote_type = self._normalize_candidate_type(entry.get("type", ""), src)
            bucket["type_votes"][vote_type] += self._type_vote_weight(origin)

        results: list[dict[str, Any]] = []
        for bucket in buckets.values():
            type_votes: Counter = bucket.pop("type_votes")
            final_type = "术语"
            if len(type_votes) > 0:
                final_type = type_votes.most_common(1)[0][0]

            results.append(
                {
                    "src": bucket.get("src", ""),
                    "dst": "",
                    "type": final_type,
                    "comment": AUTO_COMMENT,
                    "info": AUTO_COMMENT,
                    "case_sensitive": False,
                    "origins": set(bucket.get("origins", set())),
                }
            )

        return results

    def _attach_counts_and_contexts(
        self,
        candidates: Sequence[dict[str, Any]],
        corpus_texts: Sequence[str],
    ) -> list[dict[str, Any]]:
        if candidates == []:
            return []

        lines_original = [str(text or "") for text in corpus_texts]
        lines_work = [self._clean_haystack_text(text) for text in lines_original]
        results: list[dict[str, Any]] = []

        candidates_sorted = sorted(
            candidates,
            key = lambda item: len(str(item.get("src", "") or "")),
            reverse = True,
        )

        for candidate in candidates_sorted:
            self._ensure_not_cancelled()
            src = str(candidate.get("src", "") or "").strip()
            if src == "":
                continue

            pattern = self._compile_candidate_pattern(src)
            matched_indexes: list[int] = []
            contexts: list[str] = []

            for index, haystack in enumerate(lines_work):
                if haystack == "":
                    continue
                if pattern.search(haystack) is None:
                    continue

                matched_indexes.append(index)

                context = self._normalize_context_text(lines_original[index])
                if context and context not in contexts:
                    contexts.append(context)

            if matched_indexes == []:
                continue

            if self._should_drop_by_count(candidate, len(matched_indexes)):
                continue

            for index in matched_indexes:
                lines_work[index] = pattern.sub(
                    lambda match: "#" * len(match.group(0)),
                    lines_work[index],
                )

            enriched = dict(candidate)
            enriched["count"] = len(matched_indexes)
            enriched["contexts"] = contexts[:3]
            results.append(enriched)

        results.sort(
            key = lambda item: (-int(item.get("count", 0) or 0), str(item.get("src", ""))),
        )
        return results

    def _should_keep_direct_candidate(self, text: str) -> bool:
        if not self._is_viable_candidate_text(text):
            return False

        return self._should_keep_rule_candidate(text)

    def _should_keep_rule_candidate(self, text: str) -> bool:
        if not self._is_viable_candidate_text(text):
            return False

        words = text.split()
        if len(words) > 6:
            return False

        if re.search(r"[!?。！？；;]", text):
            return False

        guessed = self._guess_candidate_type(text, default = "")
        lower = text.casefold()
        if guessed in {"地名", "组织"}:
            return True
        if guessed == "角色":
            return self._accept_single_word_phrase(text) if len(words) == 1 else True
        if guessed == "物品":
            return any(keyword in lower for keyword in self.SPECIAL_ITEM_KEYWORDS)
        return False

    def _extract_embedded_candidate_phrases(self, text: str) -> list[str]:
        cleaned = self._clean_haystack_text(text)
        if cleaned == "":
            return []

        results: set[str] = set()
        tokens = self.RE_WORD.findall(cleaned)
        current: list[str] = []
        capitalized_count = 0

        for token in tokens + [""]:
            if token != "" and self._should_append_phrase_token(token, current):
                current.append(token)
                if self._is_capitalized_token(token):
                    capitalized_count += 1
                continue

            if current != []:
                phrase = " ".join(current)
                phrase = self._normalize_candidate_text(phrase)
                if (
                    capitalized_count >= 2
                    and self._is_viable_candidate_text(phrase)
                    and self._should_keep_rule_candidate(phrase)
                ):
                    results.add(phrase)
                elif (
                    capitalized_count == 1
                    and len(current) == 1
                    and self._accept_single_word_phrase(phrase)
                ):
                    results.add(phrase)

            current = []
            capitalized_count = 0

        return sorted(results)

    def _should_append_phrase_token(self, token: str, current: Sequence[str]) -> bool:
        if self._is_capitalized_token(token):
            return True
        return current != [] and token.lower() in self.CONNECTOR_WORDS

    def _is_capitalized_token(self, token: str) -> bool:
        if token == "":
            return False
        if token.isupper() and len(token) > 1:
            return True
        return token[0].isupper()

    def _accept_single_word_phrase(self, phrase: str) -> bool:
        if not self._is_viable_candidate_text(phrase):
            return False
        if len(phrase) < 4:
            return False
        if phrase in self.COMMON_SINGLE_WORDS:
            return False
        if phrase.lower() in {word.lower() for word in self.TITLE_PREFIXES}:
            return False
        return self._looks_like_title_term(phrase) or self._guess_candidate_type(phrase, default = "") != ""

    def _looks_like_title_term(self, text: str) -> bool:
        if not self._is_viable_candidate_text(text):
            return False

        words = text.split()
        if words == [] or len(words) > 6:
            return False

        latin_words = [word for word in words if self.RE_LATIN_TERM.search(word)]
        if latin_words == []:
            return False

        capitalized_words = 0
        for word in latin_words:
            if self._is_capitalized_token(word) or word.lower() in self.CONNECTOR_WORDS:
                if self._is_capitalized_token(word):
                    capitalized_words += 1
                continue
            return False

        return capitalized_words > 0

    def _normalize_candidate_type(self, raw_type: str, src: str) -> str:
        normalized = str(raw_type or "").strip().lower()
        if normalized != "":
            for type_name, hints in self.TYPE_HINTS.items():
                if any(hint in normalized for hint in hints):
                    return type_name

        guessed = self._guess_candidate_type(src, default = "")
        return guessed or "术语"

    def _guess_candidate_type(self, text: str, *, default: str) -> str:
        if text == "":
            return default

        lower = text.lower()
        if any(keyword in lower for keyword in self.PLACE_KEYWORDS):
            return "地名"
        if any(keyword in lower for keyword in self.ORG_KEYWORDS):
            return "组织"
        if any(keyword in lower for keyword in self.ITEM_KEYWORDS):
            return "物品"
        if _is_character_name(text):
            return "角色"
        if self._looks_like_title_term(text):
            return "术语"
        return default

    def _normalize_candidate_text(self, text: str) -> str:
        cleaned = _strip_format_tags(str(text or ""))
        cleaned = cleaned.replace("\r", " ").replace("\n", " ").replace("\u3000", " ")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        cleaned = cleaned.strip("\"'“”‘’()[]{}<>")
        cleaned = self._strip_title_edges(cleaned)
        return cleaned.strip()

    def _strip_title_edges(self, text: str) -> str:
        if text == "":
            return ""

        words = text.split()
        while words != [] and words[0].rstrip(".").lower() in self.TITLE_PREFIXES:
            words.pop(0)
        return " ".join(words)

    def _normalize_context_text(self, text: str) -> str:
        context = str(text or "").replace("\r", " ").replace("\n", " ")
        context = re.sub(r"\s+", " ", context).strip()
        return context

    def _clean_haystack_text(self, text: str) -> str:
        cleaned = _strip_format_tags(str(text or ""))
        cleaned = cleaned.replace("\r", " ").replace("\n", " ").replace("\u3000", " ")
        return re.sub(r"\s+", " ", cleaned).strip()

    def _is_viable_candidate_text(self, text: str) -> bool:
        if text == "":
            return False
        if len(text) < 2 or len(text) > 64:
            return False
        lower_text = text.casefold()
        if lower_text in self.UI_EXACT_TERMS:
            return False
        if any(pattern in lower_text for pattern in self.UI_CONTAINS_PATTERNS):
            return False
        if should_skip_text(text):
            return False
        if re.search(r"https?://", text, re.IGNORECASE):
            return False
        if re.search(r"\[[^\]]+\]|\{[^}]+\}", text):
            return False
        if re.fullmatch(r"[\W_]+", text):
            return False
        if re.fullmatch(r"\d+", text):
            return False
        return True

    def _normalize_key(self, text: str) -> str:
        normalized = re.sub(r"\s+", " ", str(text or "")).strip()
        return normalized.casefold()

    def _type_vote_weight(self, origin: str) -> int:
        if origin == "llm":
            return 3
        if origin == "rule_name":
            return 2
        return 1

    def _prefer_display_src(self, candidate: str, current: str) -> bool:
        if current == "":
            return True
        if current.casefold() == current and candidate != candidate.casefold():
            return True
        return len(candidate) > len(current)

    def _compile_candidate_pattern(self, src: str) -> re.Pattern:
        escaped = re.escape(src)
        if self.RE_BOUNDARY_SAFE_TERM.fullmatch(src) is not None:
            return re.compile(
                rf"(?<![A-Za-z0-9_]){escaped}(?![A-Za-z0-9_])",
                flags = re.IGNORECASE,
            )
        return re.compile(escaped, flags = re.IGNORECASE)

    def _should_drop_by_count(self, candidate: dict[str, Any], count: int) -> bool:
        if count <= 0:
            return True

        src = str(candidate.get("src", "") or "")
        origins = set(candidate.get("origins", set()))
        if "llm" in origins or "rule_name" in origins:
            return False

        if len(src.split()) == 1 and candidate.get("type") == "术语" and count < 2:
            return True

        return False


def extract_glossary_candidates(
    *,
    config: Config,
    target_path: str | Path,
    platform: dict[str, Any] | None,
    progress_callback: ProgressCallback | None = None,
    cancel_callback: CancelCallback | None = None,
) -> dict[str, Any]:
    """执行术语候选抽取。"""
    service = GlossaryCandidateService(
        config = config,
        target_path = target_path,
        platform = platform,
        progress_callback = progress_callback,
        cancel_callback = cancel_callback,
    )
    return service.run()
