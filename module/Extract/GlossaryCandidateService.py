"""术语候选抽取服务。"""

from __future__ import annotations

import json
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Sequence

import json_repair as repair

from base.Base import Base
from module.Config import Config
from module.Engine.TaskRequester import TaskRequester
from module.Engine.RequestProgress import request_progress
from module.Extract.ProperNounDetector import (
    _COMMON_NON_TERM_SINGLE_WORDS,
    _HONORIFIC_NOISE,
    CorpusEvidence,
    ProperNounDetector,
    _is_stopword_casefold,
)
from module.Extract.ReplaceGenerator import (
    _get_game_dir,
    _is_character_name,
    _strip_format_tags,
    collect_glossary_candidate_texts,
)
from module.Workbench.AnalysisRequestPolicy import build_analysis_platform
from module.Workbench.CharacterScanner import CharacterScanner
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

    def is_empty_result(self, response_text: str) -> bool:
        """模型明确回答「没有新术语」（严格 JSON 空数组，可带代码块）。"""
        text = str(response_text or "").strip()
        fenced_match = self.RE_MARKDOWN_FENCE.fullmatch(text)
        if fenced_match is not None:
            text = fenced_match.group(1).strip()
        try:
            return json.loads(text) == []
        except ValueError:
            return False

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
        "mount",
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
    # 从 .rpyc 字节码漏出来的代码行：函数调用、语句、路径、条件判断。
    # 它们含大写标识符，会被误当成「句中大写专名」，但完全不是台词。
    RE_CODE_LINE = re.compile(
        r"(?:^\s*(?:wait_event|delta_day|show|hide|play|stop|jump|call|label|scene|"
        r"screen|if|elif|else|while|for|def|class|init|python|style|transform|image|"
        r"define|default|return|pass|menu)\b)"
        r"|(?:[A-Za-z_]\w*\s*\(.*\)\s*$)"
        r"|(?:[A-Za-z_]\w*\s*\(\s*['\"])"
        r"|(?:^[\w./ -]+\.(?:rpy|rpyc|py|png|jpg|jpeg|webp|ogg|mp3|wav|ttf|otf|json|txt)\b)"
        r"|(?:=>|==|!=|->)"
        r"|(?:^\s*[A-Za-z_]\w*\.[A-Za-z_]\w*\s*=)",
        flags = re.MULTILINE,
    )

    MAX_LLM_CHUNK_ITEMS = 40
    MAX_LLM_CHUNK_CHARS = 2500
    # 送入 LLM 的每段文本最大长度，超长句子没有术语价值且会挤占上下文
    MAX_LLM_LINE_CHARS = 300
    # 单次扫描最多请求多少块。DarkMagic 这种 5 万条语料的项目会切出上千块，
    # 串行请求永远跑不完；改为「只送有专名证据的行」+ 上限截断。
    MAX_LLM_CHUNKS = 40
    # 并发请求数：每块互相独立，并发能把几十块的总耗时压到单块量级。
    LLM_CHUNK_CONCURRENCY = 4

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
        self.detector = ProperNounDetector()

    def run(self) -> dict[str, Any]:
        game_dir = _get_game_dir(self.target_path)
        tl_name = str(getattr(self.config, "renpy_tl_folder", "") or DEFAULT_TL_NAME).strip() or DEFAULT_TL_NAME
        tl_name = self._normalize_tl_name(tl_name)

        self._ensure_not_cancelled()
        self._report("正在扫描游戏源码文本…", 3)
        corpus_texts = collect_glossary_candidate_texts(self.target_path, tl_name = tl_name)
        if corpus_texts == ():
            raise ValueError("未在游戏源码中找到可用于术语扫描的文本")

        self._ensure_not_cancelled()
        self._report(f"已读取 {len(corpus_texts)} 条文本，正在统计词语证据…", 12)
        evidence = CorpusEvidence(corpus_texts)
        self.info(
            f"[GlossaryCandidate] 语料统计完成：{len(evidence.words)} 个词形 / "
            f"{len(evidence.phrases)} 个短语"
        )

        self._ensure_not_cancelled()
        self._report("正在识别专有名词（角色名/地名/组织/物品）…", 26)
        rule_candidates = self._collect_rule_candidates(corpus_texts, game_dir, evidence)
        self.info(f"[GlossaryCandidate] 规则候选：{len(rule_candidates)} 条")

        llm_candidates: list[dict[str, Any]] = []
        warnings: list[str] = []
        llm_chunks_total = 0
        llm_chunks_success = 0
        used_llm = False

        if self._can_use_llm_platform(self.platform):
            used_llm = True
            accepted = [str(item.get("src", "")) for item in rule_candidates]
            self._report("正在挑选需要 AI 判断的专名上下文…", 28)
            llm_texts = self._select_llm_texts(corpus_texts, evidence, accepted)
            chunks = self._build_prompt_chunks(llm_texts)
            if len(chunks) > self.MAX_LLM_CHUNKS:
                chunks = chunks[: self.MAX_LLM_CHUNKS]
                sent_lines = sum(len(chunk) for chunk in chunks)
                message = (
                    f"AI 上下文超过 {self.MAX_LLM_CHUNKS} 个分块上限，"
                    f"本次仅分析 {sent_lines}/{len(llm_texts)} 条选中文本；"
                    "部分低频专名尚未经过 AI 判定。"
                )
                warnings.append(message)
                self.warning(f"[GlossaryCandidate] {message}")
            llm_chunks_total = len(chunks)
            known_terms = accepted
            self.info(
                f"[GlossaryCandidate] LLM 分块：{llm_chunks_total} 块"
                f"（从 {len(corpus_texts)} 行中挑出 {len(llm_texts)} 行有专名证据的文本），"
                f"参考专名 {len(known_terms)} 个，并发 {self.LLM_CHUNK_CONCURRENCY}"
            )
            if llm_chunks_total > 0:
                llm_chunks_success, llm_payloads, llm_warnings = self._run_llm_chunks(
                    chunks,
                    known_terms,
                )
                for payload in llm_payloads:
                    llm_candidates.extend(payload)
                warnings.extend(llm_warnings)
            elif llm_texts == []:
                warnings.append("语料中没有需要模型判定的专名文本，已仅使用规则候选。")
        else:
            warnings.append("未找到支持术语抽取的 LLM，已仅使用规则候选。")

        self._ensure_not_cancelled()
        self._report("正在聚合候选术语…", 90)
        merged = self._merge_candidates(rule_candidates, llm_candidates)
        merged, rejected_llm_count = self._filter_unsupported_llm_candidates(merged, evidence)
        if rejected_llm_count:
            self.info(
                f"[GlossaryCandidate] 语料证据复核：过滤 {rejected_llm_count} 条弱证据模型候选"
            )
        self._ensure_not_cancelled()
        enriched = self._attach_counts_and_contexts(merged, corpus_texts)

        self._ensure_not_cancelled()
        self._report(f"术语候选扫描完成，共 {len(enriched)} 条", 100)
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
            if len(text) > self.MAX_LLM_LINE_CHARS:
                text = text[: self.MAX_LLM_LINE_CHARS]

            projected_length = current_length + len(text)
            if current != [] and (
                len(current) >= self.MAX_LLM_CHUNK_ITEMS
                or projected_length > self.MAX_LLM_CHUNK_CHARS
            ):
                chunks.append(current)
                current = []
                current_length = 0

            current.append(text)
            current_length += len(text)

        if current != []:
            chunks.append(current)

        return chunks

    def _select_llm_texts(
        self,
        texts: Sequence[str],
        evidence: CorpusEvidence,
        accepted: Sequence[str],
    ) -> list[str]:
        """挑出「值得问模型」的行，避免把整部剧本都塞进 LLM。

        规则通道已经收录的词不需要再问；剩下的可疑专名散落在几万行里时，
        整本送进模型既慢又没有增益。这里只保留含有「句中大写、非停用词、
        尚未收录」词形的行，并按候选词数量从多到少排序，超上限就截断。
        """
        accepted_keys = {str(item).casefold() for item in accepted}
        unresolved: set[str] = set()
        for position, (word, stat) in enumerate(evidence.words.items()):
            if position % 128 == 0:
                self._ensure_not_cancelled()
            if word in accepted_keys:
                continue
            if stat.mid_capitalized < 1:
                continue
            if len(word) < 2 or word.isdigit():
                continue
            if word in _HONORIFIC_NOISE:
                # Your Majesty / Miss / Sensei 之类称谓满篇都是，
                # 让它们参与选样只会把台词行全捞进来。
                continue
            if _is_stopword_casefold(word):
                continue
            unresolved.add(word)
        if unresolved == set():
            return []

        scored: list[tuple[int, int, str]] = []
        skipped_code = 0
        seen_lines: set[str] = set()
        for index, raw_text in enumerate(texts):
            if index % 128 == 0:
                self._ensure_not_cancelled()
            text = str(raw_text or "").strip()
            if text == "":
                continue
            line_key = re.sub(r"\s+", " ", text).casefold()
            if line_key in seen_lines:
                continue
            # 语料里混着从 .rpyc 抽出来的代码行（wait_event(...) / show screen ...），
            # 它们含大写标识符却不是台词，问模型只会浪费配额。
            if self._looks_like_code_line(text):
                skipped_code += 1
                continue
            hits = 0
            for match in self.RE_WORD.finditer(text):
                token = match.group(0)
                if token.casefold() in unresolved:
                    hits += 1
            if hits > 0:
                seen_lines.add(line_key)
                # 命中越多越可能是术语密集的行；同行数按原顺序做稳定次键。
                scored.append((-hits, index, text))

        scored.sort()
        limit = self.MAX_LLM_CHUNKS * self.MAX_LLM_CHUNK_ITEMS

        if len(scored) > limit:
            # 命中多的行往往是「整段人物介绍」，一条行塞十几个名字，
            # 覆盖面反而差；这里改成按未定词逐个挑一条最干净的上下文行，
            # 用同样的块数覆盖尽可能多的候选词。
            focused = self._pick_coverage_lines(texts, unresolved, evidence, limit)
            if len(focused) > 0:
                self.info(
                    f"[GlossaryCandidate] 含专名证据的行 {len(scored)} 条，"
                    f"按覆盖优先挑出 {len(focused)} 条"
                    f"（已跳过代码样行 {skipped_code} 条）"
                )
                return focused
            self.info(
                f"[GlossaryCandidate] 含专名证据的行 {len(scored)} 条，"
                f"按上限截断为 {limit} 条（已跳过代码样行 {skipped_code} 条）"
            )
            scored = scored[:limit]

        return [text for _, _, text in scored]

    def _pick_coverage_lines(
        self,
        texts: Sequence[str],
        unresolved: set[str],
        evidence: CorpusEvidence,
        limit: int,
    ) -> list[str]:
        """为每个未定词挑一条最短的干净上下文行，直到用完额度。

        术语扫描的瓶颈是「每个可疑词都要有证据可判」，不是「行数要够多」。
        一条人物介绍里塞十几个名字时模型往往只报一半；而一条短台词
        「Leo went to East Square.」能同时给出名字与用法。
        """
        # 一次遍历建立词 → 行号索引；逐词只查看实际含有它的行。
        line_hits: dict[int, set[str]] = {}
        line_texts: dict[int, str] = {}
        word_lines: dict[str, list[int]] = {}
        seen_texts: set[str] = set()
        for index, raw_text in enumerate(texts):
            if index % 128 == 0:
                self._ensure_not_cancelled()
            text = str(raw_text or "").strip()
            if text == "" or len(text) > self.MAX_LLM_LINE_CHARS:
                continue
            if self._looks_like_code_line(text):
                continue
            line_key = re.sub(r"\s+", " ", text).casefold()
            if line_key in seen_texts:
                continue
            keys = {
                match.group(0).casefold()
                for match in self.RE_WORD.finditer(text)
                if match.group(0).casefold() in unresolved
            }
            if keys:
                seen_texts.add(line_key)
                line_hits[index] = keys
                line_texts[index] = text
                for word in keys:
                    word_lines.setdefault(word, []).append(index)

        if not line_hits:
            return []

        ranks = {
            index: (
                0 if 25 <= len(text) <= 160 else 1,
                abs(len(text) - 80),
                len(line_hits[index]),
                index,
            )
            for index, text in line_texts.items()
        }
        chosen: list[str] = []
        used_lines: set[int] = set()
        # 高频词优先覆盖；同行数作为稳定次键，结果不受集合迭代顺序影响。
        ordered_words = sorted(
            unresolved,
            key = lambda word: (-evidence.words[word].mid_capitalized, word)
            if word in evidence.words
            else (0, word),
        )
        for word in ordered_words:
            self._ensure_not_cancelled()
            if len(chosen) >= limit:
                break
            candidates = (index for index in word_lines.get(word, ()) if index not in used_lines)
            best = min(candidates, key = ranks.__getitem__, default = None)
            if best is None:
                continue
            used_lines.add(best)
            chosen.append(line_texts[best])

        return chosen

    def _looks_like_code_line(self, text: str) -> bool:
        """判断一行是不是从字节码里漏出来的代码，而不是台词/界面文本。"""
        value = text.strip()
        if value == "":
            return True
        if self.RE_CODE_LINE.search(value) is not None:
            return True
        # 代码里几乎不会出现下面这些标点；台词和界面文案则很常见。
        if any(char in value for char in ".?!,;:\"'"):
            return False
        # 没有句读又含有下划线/括号的短行，基本是函数调用或标识符。
        return "(" in value or ")" in value or "_" in value

    def _build_candidate_prompt(
        self,
        texts: Sequence[str],
        known_terms: Sequence[str] = (),
    ) -> list[dict[str, str]]:
        payload = "\n".join(
            json.dumps({str(index): text}, ensure_ascii = False)
            for index, text in enumerate(texts)
        )
        known_hint = ""
        terms = [str(item) for item in known_terms if str(item).strip() != ""]
        if terms != []:
            sample = "、".join(terms[:30])
            known_hint = (
                "参考：本地规则已从这些文本里识别出下列专名，可作为判断依据，"
                "不需要重复输出它们：\n"
                f"{sample}\n"
            )
        prompt = (
            "你是 Ren'Py 游戏本地化的术语抽取器。\n"
            "任务：从输入的游戏文本片段中，找出翻译时必须保持一致的专有名词。\n"
            "只提取以下 5 类之一：角色、地名、组织、物品、术语。\n"
            "判断标准：\n"
            "1. 只有当这个词是这个虚构世界里「特定的名字」，而不是普通词义时才输出。\n"
            "   例：'East Square'（地名）、'Red Witch'（角色）、'Nyarlathotep'（神名）。\n"
            "2. 不要输出：日常词汇、代词、语气词、按钮与界面文案、完整句子、变量、"
            "路径、代码标识符、纯数字。\n"
            "3. 同一概念只输出一次，变体取最常见写法；称谓（Mr./Dr./Sir）与冠词（the）"
            "不进入术语，除非属于专名本身。\n"
            "4. dst 一律输出空字符串。\n"
            "5. 只输出 JSONLINE（每行一个 JSON），不要解释，不要代码块。\n"
            "6. 如果没有新的有效术语，只输出 []，不要输出其他内容。\n"
            f"{known_hint}"
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

    def _run_llm_chunks(
        self,
        chunks: Sequence[Sequence[str]],
        known_terms: Sequence[str],
    ) -> tuple[int, list[list[dict[str, Any]]], list[str]]:
        """并发跑完所有分块，边完成边推进度。

        分块之间互相独立，串行请求会让几十块的总耗时线性叠加；这里用线程池
        并发，任何一块完成都立刻更新「已完成 N/M 块」的进度文案。
        """
        total = len(chunks)
        results: dict[int, tuple[bool, list[dict[str, Any]] | str]] = {}
        completed = 0

        # 线程局部的取消事件只能在调用线程读取；工作线程不继承绑定，
        # 必须在这里捕获后交给每个工作线程自行绑定。
        cancel_context = getattr(TaskRequester, "RUN_CANCEL_CONTEXT", None)
        cancel_event = getattr(cancel_context, "event", None) if cancel_context is not None else None
        binder = getattr(TaskRequester, "bind_run_cancel_event", None)
        unbinder = getattr(TaskRequester, "unbind_run_cancel_event", None)
        bind = cancel_event is not None and callable(binder) and callable(unbinder)

        def is_cancelled() -> bool:
            if cancel_event is not None and cancel_event.is_set():
                return True
            return callable(self.cancel_callback) and bool(self.cancel_callback())

        def work(index: int, chunk: Sequence[str]) -> tuple[bool, list[dict[str, Any]] | str] | None:
            # 排队中的分块在开始请求前确认未取消，取消后不再联网。
            if is_cancelled():
                return None
            if bind:
                binder(cancel_event)
            try:
                return self._extract_chunk_with_llm(chunk, index, known_terms = known_terms)
            finally:
                if bind:
                    unbinder()

        workers = max(1, min(self.LLM_CHUNK_CONCURRENCY, total))
        pool = ThreadPoolExecutor(max_workers = workers, thread_name_prefix = "glossary-llm")
        try:
            futures = {
                pool.submit(work, index, chunk): index
                for index, chunk in enumerate(chunks)
            }
            for future in as_completed(futures):
                outcome = future.result()
                if outcome is None or is_cancelled():
                    raise InterruptedError("术语候选扫描已停止")
                results[futures[future]] = outcome
                completed += 1
                percent = 30 + int((completed / max(1, total)) * 55)
                self._report(
                    f"正在使用 LLM 抽取术语候选… (已完成 {completed}/{total} 块，并发 {workers})",
                    percent,
                )
        finally:
            # 等待正在运行的请求协作退出（已绑定取消事件），不留下孤立请求。
            pool.shutdown(wait = True, cancel_futures = True)

        # 按块顺序汇总，保证同票类别与大小写选择不受完成先后影响。
        payloads: list[list[dict[str, Any]]] = []
        warnings: list[str] = []
        succeeded = 0
        for index in sorted(results):
            success, payload = results[index]
            if success:
                succeeded += 1
                payloads.append(list(payload))
            elif payload:
                warnings.append(str(payload))

        for warning in warnings:
            self.info(f"[GlossaryCandidate] {warning}")
        return succeeded, payloads, warnings

    def _extract_chunk_with_llm(
        self,
        chunk: Sequence[str],
        index: int,
        *,
        known_terms: Sequence[str] = (),
    ) -> tuple[bool, list[dict[str, Any]] | str]:
        if self.platform is None:
            return False, "未找到可用平台"

        platform = build_analysis_platform(
            self.platform,
            lambda message: self.info(f"[GlossaryCandidate] 第 {index + 1} 块{message}"),
        )
        requester = TaskRequester(self.config, platform, index)
        messages = self._build_candidate_prompt(chunk, known_terms)
        label = f"[GlossaryCandidate] 第 {index + 1} 块（{len(chunk)} 行）"
        self.info(f"{label} 开始请求")
        started_at = time.perf_counter()
        with request_progress(self.info, label):
            skip, response_think, response_text, input_tokens, output_tokens = requester.request(
                messages,
                response_shape = "none",
            )
        self._log_llm_exchange(
            index,
            len(chunk),
            response_think,
            input_tokens,
            output_tokens,
            time.perf_counter() - started_at,
        )
        if skip or not isinstance(response_text, str) or response_text.strip() == "":
            return False, f"第 {index + 1} 个分块未返回可解析结果"

        if '"blocked"' in response_text:
            return False, f"第 {index + 1} 个分块被安全过滤阻止"

        decoded = self.decoder.decode(response_text)
        if decoded == [] and self.decoder.is_empty_result(response_text):
            return True, []
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

    def _log_llm_exchange(
        self,
        index: int,
        text_count: int,
        think: str,
        input_tokens: int,
        output_tokens: int,
        elapsed: float,
    ) -> None:
        """把每次 LLM 请求的思考片段与用量写进日志，便于观察扫描进度。"""
        thinking = str(think or "").strip()
        if thinking != "":
            excerpt = re.sub(r"\s+", " ", thinking)[:200]
            self.info(f"[GlossaryCandidate] 第 {index + 1} 块思考片段：{excerpt}…")
        self.info(
            f"[GlossaryCandidate] 第 {index + 1} 块完成：输入 {text_count} 条文本，"
            f"耗时 {elapsed:.1f}s，tokens {input_tokens}/{output_tokens}"
        )

    def _collect_rule_candidates(
        self,
        texts: Sequence[str],
        game_dir: Path,
        evidence: CorpusEvidence,
    ) -> list[dict[str, Any]]:
        """收集规则候选：角色名通道 + 语料统计专名通道。

        早期实现把「任何首字母大写的词」都当候选，导致句首虚词（What/Just/
        Yeah）全部入库、产出上千条噪音。现在只保留两条有证据支撑的通道：

        1. 角色名：`Character()` 定义 + 实际开口台词数（角色卡扫描器保证
           这个名字真的在剧本里说过话，能过滤掉 Soldier/Unknown 这类占位标签）。
        2. 专有名词：句中大写且从不以小写形式出现的词，或连续大写词组。
        """
        results: list[dict[str, Any]] = []
        seen: set[str] = set()

        def append(src_text: str, type_name: str, origin: str) -> None:
            src = self._normalize_candidate_text(src_text)
            if not src or not self._is_viable_candidate_text(src):
                return
            key = self._normalize_key(src)
            if key in seen:
                return
            seen.add(key)
            results.append(
                {
                    "src": src,
                    "dst": "",
                    "type": type_name,
                    "comment": AUTO_COMMENT,
                    "info": AUTO_COMMENT,
                    "case_sensitive": False,
                    "origin": origin,
                }
            )

        # ---- 通道 1：角色名（有台词证据的 Character 定义）
        for name in self._collect_character_names(game_dir):
            self._ensure_not_cancelled()
            append(name, "角色", "rule_name")

        # ---- 通道 2：语料统计得到的专有名词
        # 类型只按关键词推断，**不**再靠 `_is_character_name` 猜「角色」——
        # 否则 God / Egypt / Friday 这类单词专名会全被标成角色。
        for display in self.detector.detect(evidence):
            self._ensure_not_cancelled()
            append(display, self._guess_term_type(display), "rule_phrase")

        return results

    def _guess_term_type(self, text: str) -> str:
        """为统计通道的专名推断类别，默认「术语」。"""
        lower = text.casefold()
        if any(keyword in lower for keyword in self.PLACE_KEYWORDS):
            return "地名"
        if any(keyword in lower for keyword in self.ORG_KEYWORDS):
            return "组织"
        if any(keyword in lower for keyword in self.ITEM_KEYWORDS):
            return "物品"
        return "术语"

    def _collect_character_names(self, game_dir: Path) -> list[str]:
        """从项目源码中提取「真的说过话」的角色名。"""
        try:
            scan = CharacterScanner().scan_project(game_dir)
        except Exception as exc:  # 源码异常不应让整个扫描失败
            self.warning(f"[GlossaryCandidate] 角色名扫描失败：{exc}")
            return []

        names = [str(name) for name in scan.names if str(name or "").strip()]
        names.sort(key = lambda value: (-scan.speaker_counts.get(value, 0), value.casefold()))
        self.info(f"[GlossaryCandidate] 角色名通道命中 {len(names)} 个（均有台词证据）")
        return names

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

    def _filter_unsupported_llm_candidates(
        self,
        candidates: Sequence[dict[str, Any]],
        evidence: CorpusEvidence,
    ) -> tuple[list[dict[str, Any]], int]:
        """复核模型新增候选；角色定义和统计规则已有各自的证据门槛。"""
        kept: list[dict[str, Any]] = []
        rejected = 0
        for candidate in candidates:
            self._ensure_not_cancelled()
            origins = set(candidate.get("origins", set()))
            if origins != {"llm"} or self._has_proper_name_evidence(
                str(candidate.get("src", "")),
                evidence,
                type_name = str(candidate.get("type", "")),
            ):
                kept.append(candidate)
            else:
                rejected += 1
        return kept, rejected

    def _has_proper_name_evidence(
        self,
        src: str,
        evidence: CorpusEvidence,
        *,
        type_name: str = "",
    ) -> bool:
        tokens = self._candidate_token_keys(src)
        meaningful = [token for token in tokens if token not in self.CONNECTOR_WORDS]
        if not meaningful:
            return False
        if len(tokens) == 1 and (
            tokens[0] in _COMMON_NON_TERM_SINGLE_WORDS or _is_stopword_casefold(tokens[0])
        ):
            return False

        # 只查看倒排索引定位到的行，避免为每个模型候选重扫整部剧本。
        pattern = self._compile_candidate_pattern(src)
        matching_lines = [
            evidence.lines[index]
            for index in sorted(evidence.line_indexes_for(src))
            if pattern.search(self._clean_haystack_text(evidence.lines[index])) is not None
        ]
        if not matching_lines:
            return False
        if self._has_explicit_term_evidence(src, matching_lines):
            return True
        if any(_is_stopword_casefold(token) for token in meaningful):
            return False

        if len(tokens) == 1:
            stat = evidence.words.get(tokens[0])
            return bool(stat and stat.lowercase == 0 and (stat.mid_capitalized or stat.sentence_start))

        if type_name == "地名" and set(tokens).intersection(self.PLACE_KEYWORDS):
            return True
        # 大小写混用的缩写仍能构成专名，例如 HPL virus。
        for line in matching_lines:
            cleaned = self._clean_haystack_text(line)
            for match in pattern.finditer(cleaned):
                actual = match.group(0)
                if self._looks_like_title_term(actual):
                    return True
                if any(
                    len(word) >= 2 and word.isupper() and not _is_stopword_casefold(word.casefold())
                    for word in self.RE_WORD.findall(actual)
                ):
                    return True

        # 游戏机制、魔法和特殊道具常以小写出现；要求模型类别与重复原文共同支持。
        if type_name in {"术语", "物品"} and len(matching_lines) >= 2:
            special_words = set(self.SPECIAL_ITEM_KEYWORDS) | {"magic", "spell", "ritual", "curse", "mana"}
            if set(tokens).intersection(special_words):
                return True
        return False

    def _has_explicit_term_evidence(self, src: str, lines: Sequence[str]) -> bool:
        term_pattern = self._compile_candidate_pattern(src)
        # 允许 called it... The X / called me ‘The X.’ 这类命名句式。
        named_pattern = re.compile(
            rf"\b(?:called|named|known\s+as|titled)\s+"
            rf"(?:(?:me|you|him|her|us|them|it|this|that)\b\s*)?"
            rf"[\s.:…\-\"'“‘]*(?:the\s+)?(?P<term>{re.escape(src)})(?=$|\W)",
            flags = re.IGNORECASE,
        )
        label_pattern = re.compile(
            r"\b(?:artifact|relic|weapon|spell|ritual|technique|book)\s*:\s*([^.!?;\n]{1,100})",
            flags = re.IGNORECASE,
        )
        for line in lines:
            original = str(line or "")
            for marked in re.finditer(r"\{(?P<tag>b|i)\}(.*?)\{/(?P=tag)\}", original, flags = re.IGNORECASE):
                label = self._clean_haystack_text(marked.group(2)).strip(" .,!?:;\"'“”‘’")
                if self._looks_like_title_term(label) and term_pattern.fullmatch(label) is not None:
                    return True
            cleaned = self._clean_haystack_text(original)
            named = named_pattern.search(cleaned)
            if named is not None and named.group("term")[:1].isupper():
                return True
            for label in label_pattern.finditer(cleaned):
                if term_pattern.search(label.group(1)) is not None:
                    return True
        return False

    def _build_line_token_index(self, lines: Sequence[str]) -> dict[str, set[int]]:
        """建立「词 → 行号集合」索引，用于把候选定位到可能命中的行。

        早期实现在 `_attach_counts_and_contexts` 里对每个候选全量遍历语料
        （O(候选数 × 行数)），大项目上动辄几十秒；有了索引后只需对有交集
        的少量行做精确正则校验。
        """
        index: dict[str, set[int]] = {}
        for line_index, text in enumerate(lines):
            if not text:
                continue
            for token in self.RE_WORD.findall(text):
                key = token.strip("-'’").casefold()
                if len(key) > 2 and (key.endswith("'s") or key.endswith("’s")):
                    key = key[:-2]
                if not key:
                    continue
                posting = index.get(key)
                if posting is None:
                    index[key] = {line_index}
                else:
                    posting.add(line_index)
        return index

    @staticmethod
    def _candidate_token_keys(text: str) -> list[str]:
        """把候选文本拆成与 `_build_line_token_index` 一致的索引键。"""
        keys: list[str] = []
        for token in GlossaryCandidateService.RE_WORD.findall(text):
            key = token.strip("-'’").casefold()
            if len(key) > 2 and (key.endswith("'s") or key.endswith("’s")):
                key = key[:-2]
            if key and key not in keys:
                keys.append(key)
        return keys

    def _candidate_line_hints(
        self,
        src: str,
        index: dict[str, set[int]],
    ) -> set[int] | None:
        """返回候选可能出现的行号集合；无法定位时返回 None 表示需全量扫描。"""
        keys = self._candidate_token_keys(src)
        if not keys:
            return None
        postings = [index.get(key) for key in keys]
        if any(posting is None for posting in postings):
            return set()
        postings.sort(key = len)
        candidates = set(postings[0])
        for other in postings[1:]:
            candidates &= other
            if not candidates:
                return candidates
        return candidates

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

        index = self._build_line_token_index(lines_work)

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

            hints = self._candidate_line_hints(src, index)
            if hints is not None and not hints:
                continue

            pattern = self._compile_candidate_pattern(src)
            matched_indexes: list[int] = []
            contexts: list[str] = []

            if hints is None:
                searchable = range(len(lines_work))
            else:
                searchable = sorted(hints)

            for position in searchable:
                haystack = lines_work[position]
                if haystack == "":
                    continue
                if pattern.search(haystack) is None:
                    continue

                matched_indexes.append(position)

                context = self._normalize_context_text(lines_original[position])
                if context and context not in contexts:
                    contexts.append(context)

            if matched_indexes == []:
                continue

            if self._should_drop_by_count(candidate, len(matched_indexes)):
                continue

            for position in matched_indexes:
                lines_work[position] = pattern.sub(
                    lambda match: "#" * len(match.group(0)),
                    lines_work[position],
                )

            enriched = dict(candidate)
            enriched["count"] = len(matched_indexes)
            enriched["contexts"] = contexts[:3]
            results.append(enriched)

        results.sort(
            key = lambda item: (-int(item.get("count", 0) or 0), str(item.get("src", ""))),
        )
        return results

    def _is_capitalized_token(self, token: str) -> bool:
        if token == "":
            return False
        if token.isupper() and len(token) > 1:
            return True
        return token[0].isupper()

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

        # 只剥带点的缩写称呼（"Mr." / "Dr."）：这类写法一定是称谓 + 名字，
        # 剥掉后留下真正的专名。不带点的 Miss/Queen/Lady 往往是专名的一部分
        # （"Miss Carter"、"Queen of the Kingdom"），剥掉只会切出残缺片段。
        words = text.split()
        while len(words) > 1 and words[0].endswith(".") and words[0].rstrip(".").lower() in self.TITLE_PREFIXES:
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
