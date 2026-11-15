"""Agent 术语与人名候选抽取服务。

术语与人名的判断全部交给项目既有的 Agent 通道（AgentRequester）。本模块只做结构
解析（读取 .rpy 源码、保留来源行与说话人上下文）、分块、证据定位与聚合，不再用
正则、大小写、词形或频次规则产生、筛选、猜类型或补漏候选。
"""

from __future__ import annotations

import copy
import json
from bisect import bisect_left
import queue
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable, Sequence

import json_repair as repair

from base.Base import Base
from module.Agent.AgentRequester import AgentRequester
from module.Config import Config
from module.Extract.ExtractionCheckpoint import ExtractionCheckpoint, clean_rows, digest, semantic_fingerprint
from module.Extract.ReplaceGenerator import _get_game_dir, _strip_format_tags
from module.Localizer.Localizer import Localizer

AUTO_COMMENT = "术语候选 (Agent 提取)"
FENCE = "```"

# 执行进度事件：低频心跳，只放可读摘要，绝不带 prompt、密钥或整段思维链。
PROGRESS_MIN_INTERVAL_SECONDS = 0.5
PROGRESS_HEARTBEAT_SECONDS = 1.0
PROGRESS_MAX_CANDIDATES = 20
PROGRESS_MAX_ACTIVE_CHUNKS = 4
PROGRESS_MAX_SOURCES = 3
PROGRESS_EVIDENCE_CHARS = 40
PHASE_COLLECTING = "collecting"
PHASE_EXTRACTING = "extracting"
PHASE_AGGREGATING = "aggregating"
PHASE_COMPLETED = "completed"

ProgressCallback = Callable[[str, int], None]
CancelCallback = Callable[[], bool]
EventCallback = Callable[[dict[str, Any]], None]

_ESCAPES = {
    "n": "\n",
    "t": "\t",
    "r": "\r",
    '"': '"',
    "'": "'",
    "\\": "\\",
}


def _unescape(text: str) -> str:
    """只还原 Ren'Py 字符串里常见的转义，避免 unicode_escape 破坏非 ASCII。"""
    out: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char == "\\" and index + 1 < length:
            out.append(_ESCAPES.get(text[index + 1], text[index + 1]))
            index += 2
            continue
        out.append(char)
        index += 1
    return "".join(out)


class GlossaryCandidateDecoder(Base):
    """解析 Agent 返回的候选 JSONLINE（纯格式解析，不做术语判断）。"""

    RE_MARKDOWN_FENCE = re.compile(
        FENCE + r"(?:json|jsonline)?\s*(.*?)\s*" + FENCE,
        re.DOTALL | re.IGNORECASE,
    )

    def decode(self, response_text: str) -> list[dict[str, Any]]:
        if not isinstance(response_text, str) or response_text.strip() == "":
            return []

        candidates: list[dict[str, Any]] = []
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

    def _decode_jsonline(self, text: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if line == "" or line.startswith(FENCE):
                continue

            try:
                payload = repair.loads(line)
            except Exception:
                continue

            entry = self._normalize_payload(payload)
            if entry is not None:
                results.append(entry)
        return results

    def _decode_whole_json(self, text: str) -> list[dict[str, Any]]:
        try:
            payload = repair.loads(text)
        except Exception:
            return []

        if isinstance(payload, dict):
            entry = self._normalize_payload(payload)
            return [entry] if entry is not None else []

        if isinstance(payload, list):
            results: list[dict[str, Any]] = []
            for item in payload:
                entry = self._normalize_payload(item)
                if entry is not None:
                    results.append(entry)
            return results

        return []

    def _normalize_payload(self, payload: Any) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None

        src = str(
            payload.get("src")
            or payload.get("source")
            or payload.get("term")
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
            or ""
        ).strip()

        line = payload.get("line", payload.get("id"))
        try:
            line_index = int(str(line).strip()) if line is not None else -1
        except (TypeError, ValueError):
            line_index = -1

        # evidence 只用于进度摘要展示，不参与落盘判定。
        evidence = str(payload.get("evidence") or payload.get("reason") or "").strip()
        return {"src": src, "type": type_name, "line": line_index, "evidence": evidence}




def _chunk_sources(chunk: Sequence[dict[str, Any]]) -> list[str]:
    """该分块涉及的去重来源路径，最多 3 条；只给路径，不给正文。"""
    sources: list[str] = []
    for item in chunk:
        name = str(item.get("source", "") or "").strip()
        if name == "" or name in sources:
            continue
        sources.append(name)
        if len(sources) >= PROGRESS_MAX_SOURCES:
            break
    return sources


def _short_evidence(raw: Any) -> str:
    """模型给出的短依据：压缩空白并截断，避免把整段推理塞进快照。"""
    text = re.sub(r"\s+", " ", str(raw or "")).strip()
    if text == "":
        return ""
    if len(text) <= PROGRESS_EVIDENCE_CHARS:
        return text
    return text[: PROGRESS_EVIDENCE_CHARS - 1] + "…"


class ExtractionProgress:
    """Thread-safe snapshots; only the coordinator publishes lifecycle events."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._started = time.monotonic()
        self._phase = PHASE_COLLECTING
        self._total = 0
        self._sources: dict[int, list[str]] = {}
        self._active: dict[int, float] = {}
        self._finished: dict[int, bool] = {}
        self._reused: set[int] = set()
        self._requested: set[int] = set()
        self._checkpoint: dict[str, Any] = {}
        self._candidate_keys: set[str] = set()
        self._candidate_preview: dict[str, dict[str, Any]] = {}
        self._dirty = True
        self._closed = False
        self._last_emit = 0.0

    def set_phase(self, phase: str) -> None:
        with self._lock:
            if not self._closed and self._phase != phase:
                self._phase = phase
                self._dirty = True

    def set_chunks(self, chunks: Sequence[Sequence[dict[str, Any]]]) -> None:
        with self._lock:
            if self._closed:
                return
            self._total = len(chunks)
            self._sources = {index: _chunk_sources(chunk) for index, chunk in enumerate(chunks)}
            self._dirty = True

    def chunk_started(self, index: int, started: float | None = None) -> None:
        with self._lock:
            if self._closed or index in self._finished or index in self._active:
                return
            self._active[index] = time.monotonic() if started is None else started
            self._requested.add(index)
            self._dirty = True

    def chunk_finished(self, index: int, success: bool, *, reused: bool = False) -> None:
        with self._lock:
            if self._closed or index in self._finished:
                return
            self._active.pop(index, None)
            self._finished[index] = success
            if reused:
                self._reused.add(index)
            self._dirty = True

    def set_checkpoint(self, details: dict[str, Any]) -> None:
        with self._lock:
            if not self._closed and details != self._checkpoint:
                self._checkpoint = copy.deepcopy(details)
                self._dirty = True

    def see_candidates(self, rows: Sequence[dict[str, Any]]) -> None:
        with self._lock:
            if self._closed:
                return
            for row in rows:
                src = str(row.get("src", "") or "").strip()
                key = src.casefold()
                if not src or key in self._candidate_keys:
                    continue
                self._candidate_keys.add(key)
                if len(self._candidate_preview) < PROGRESS_MAX_CANDIDATES:
                    preview = {"src": src, "type": str(row.get("type", "术语"))}
                    for name in ("evidence", "source", "line"):
                        if row.get(name) is not None:
                            preview[name] = row[name]
                    if "evidence" in preview:
                        preview["evidence"] = _short_evidence(preview["evidence"])
                    self._candidate_preview[key] = preview
                self._dirty = True

    def close(self) -> None:
        with self._lock:
            self._closed = True

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed

    def should_emit(self, *, force: bool = False) -> bool:
        now = time.monotonic()
        with self._lock:
            if self._closed:
                return False
            if force or (self._dirty and now - self._last_emit >= PROGRESS_MIN_INTERVAL_SECONDS) or now - self._last_emit >= PROGRESS_HEARTBEAT_SECONDS:
                self._dirty = False
                self._last_emit = now
                return True
            return False

    def snapshot(self) -> dict[str, Any]:
        now = time.monotonic()
        with self._lock:
            active = [
                {"index": index + 1, "sources": list(self._sources.get(index, [])),
                 "elapsed_seconds": round(max(0.0, now - started), 3)}
                for index, started in sorted(self._active.items())
            ]
            completed = len(self._finished)
            successful = sum(self._finished.values())
            return {
                "phase": self._phase,
                "total_chunks": self._total,
                "completed_chunks": completed,
                "successful_chunks": successful,
                "reused_chunks": len(self._reused),
                "requested_chunks": len(self._requested),
                **copy.deepcopy(self._checkpoint),
                "failed_chunks": completed - successful,
                "pending_chunks": max(0, self._total - completed - len(active)),
                "elapsed_seconds": round(max(0.0, now - self._started), 3),
                "active_chunks": active,
                "candidate_count": len(self._candidate_keys),
                "candidates": [dict(row) for row in self._candidate_preview.values()],
            }


class GlossaryCandidateService(Base):
    """用 Agent 从 Ren'Py 源码中抽取术语候选（含角色人名）。"""

    # 只用模型自己标注的类别做归一；不再按词面内容猜类型。
    TYPE_HINTS = {
        "角色": ("角色", "人名", "姓名", "person", "character", "male", "female", "npc"),
        "地名": ("地名", "地点", "位置", "设施", "location", "place", "gpe", "loc", "fac"),
        "组织": ("组织", "家族", "阵营", "派系", "guild", "family", "faction", "org", "organization", "group"),
        "物品": ("物品", "道具", "装备", "artifact", "item", "product", "weapon", "relic"),
        "术语": ("术语", "其他", "生物", "怪物", "creature", "monster", "beast", "other", "entity"),
    }
    SUPPORTED_FORMATS = (
        str(Base.APIFormat.OPENAI).casefold(),
        str(Base.APIFormat.ANTHROPIC).casefold(),
        str(Base.APIFormat.GOOGLE).casefold(),
    )

    RE_CHARACTER_DEF = re.compile(r"Character\s*\(", re.IGNORECASE)
    # define / default 等赋值行保留整行语境：显示名与变量名的对应关系就在这里。
    RE_DEFINITION = re.compile(r"^\s*(?:define|default|init\s+python)\b", re.IGNORECASE)
    # Ren'Py 界面语句：这类行属于 UI 上下文，排在角色与剧情之后再送。
    RE_UI_LINE = re.compile(
        r"^\s*(?:screen|style|text|textbutton|imagebutton|button|label|bar|frame|"
        r"vbox|hbox|fixed|grid|side|window|timer|add|use|showif|if|elif|else)\b",
        re.IGNORECASE,
    )
    RE_STRING = re.compile(r'"((?:[^"\\\n]|\\.)*)"' + r"|'((?:[^'\\\n]|\\.)*)'")
    RE_SPEAKER = re.compile(r"^\s*(?P<speaker>[^\W\d][\w.]*)\s+(?:(?:@\s*)?[\w.]+\s+)*(?=\"|')")
    # 结构性噪声：文件路径、扩展名标识符、十六进制颜色、纯数字。
    RE_STRUCTURAL_NOISE = re.compile(
        r"^(?:#[0-9a-fA-F]{3,8}|[\w./\\-]+\.(?:rpy|rpyc|py|png|jpg|jpeg|webp|ogg|mp3|wav|ttf|otf|json|txt)|"
        r"[0-9]+(?:\.[0-9]+)?)$"
    )

    # 40 项/2500 字会把一次对话切成过碎的分块：语境被截断后模型更容易把
    # 泛用 UI 词当成术语。常规容量提到 80 项/8000 字，仍保留总块上限与覆盖诊断。
    CHUNK_MAX_ITEMS = 80
    CHUNK_MAX_CHARS = 8000
    MAX_ITEM_CHARS = 600
    # 超长行切分时的重叠字符数：名字跨在切点上时仍能在相邻段里完整出现。
    SEGMENT_OVERLAP = 40
    MAX_CANDIDATE_CHARS = 80
    CHUNK_CONCURRENCY = 4
    CHUNK_TIMEOUT_SECONDS = 240
    # 取消后有界退出：等待活跃请求收尾的上限，超时不再等待网络。
    CLOSE_TIMEOUT_SECONDS = 5
    MAX_LLM_CHUNKS = 2000
    # 内置/生成目录与模板文件：结构名单，不是词表，判断依据是文件来源不是词形。
    SKIP_DIRS = frozenset({"tl", "cache", "__pycache__", "base_box", "saves"})
    # Basenames do not prove ownership: user common*.rpy/scripts remain in scope.
    RE_ASSIGNMENT = re.compile(r"^\s*(?:(?:define|default)\s+(?:-?\d+\s+)?|\$\s*)?(?P<name>[^\W\d][\w.]*)\s*=(?!=)")
    RE_IDENTIFIER = re.compile(r"[^\W\d][\w.]*")

    def __init__(
        self,
        *,
        config: Config,
        target_path: str | Path,
        platform: dict[str, Any] | None,
        progress_callback: ProgressCallback | None = None,
        cancel_callback: CancelCallback | None = None,
        character_only: bool = False,
        event_callback: EventCallback | None = None,
        resume: bool = True,
        force: bool = False,
        checkpoint_root: str | Path | None = None,
        checkpoint_enabled: bool = False,
        checkpoint_completion: Callable[[ExtractionCheckpoint], None] | None = None,
    ) -> None:
        super().__init__()
        self.config = config
        self.target_path = str(target_path)
        self.platform = copy.deepcopy(platform) if isinstance(platform, dict) else None
        self.progress_callback = progress_callback
        self.cancel_callback = cancel_callback
        self.character_only = bool(character_only)
        # 结构化执行摘要走独立通道：旧的两参数 progress 契约保持不变。
        self.event_callback = event_callback
        self.progress = ExtractionProgress()
        self.decoder = GlossaryCandidateDecoder()
        self.resume = bool(resume)
        self.force = bool(force)
        self.checkpoint_root = checkpoint_root
        self.checkpoint_enabled = bool(checkpoint_enabled or checkpoint_root is not None)
        self.checkpoint_completion = checkpoint_completion
        self._checkpoint: ExtractionCheckpoint | None = None
        self._resume_results: dict[int, tuple[bool, Any]] = {}
        self._checkpoint_diagnostics: list[str] = []

    # ------------------------------------------------------------------ run

    def run(self) -> dict[str, Any]:
        try:
            return self._run()
        finally:
            self.progress.close()
            if self._checkpoint is not None:
                self._checkpoint.close()

    def _checkpoint_metadata(self) -> dict[str, Any]:
        details = self._checkpoint.metadata() if self._checkpoint is not None else {
            'checkpoint_status': 'unavailable', 'resume_available': False,
            'checkpoint_diagnostics': list(self._checkpoint_diagnostics),
        }
        return {**details, 'reused_chunks': len(self._resume_results),
                'requested_chunks': getattr(self, '_started_chunks', 0)}

    def _valid_checkpoint_entry(self, entry: dict[str, Any], chunk: Sequence[dict[str, Any]]) -> bool:
        try:
            clean_rows([entry])
        except (TypeError, ValueError, KeyError):
            return False
        src, evidence = entry['src'], entry['evidence']
        if not src or self._normalize_candidate_text(src) != src or len(src) > self.MAX_CANDIDATE_CHARS:
            return False
        for item in chunk:
            text = str(item.get('text', ''))
            if item.get('source') != entry['source'] or item.get('line') != entry['line']:
                continue
            if self._match_source_slice(src, text) != src or not evidence.strip() or evidence not in text:
                continue
            if self._match_source_slice(src, evidence) is not None:
                return True
            # Long names can extend beyond the 40-character preview. Accept
            # only a source window that the normal grounding path can produce.
            position = text.find(src)
            while position >= 0:
                for prefix in range(13):
                    start = max(0, position - prefix)
                    if _short_evidence(text[start:start + PROGRESS_EVIDENCE_CHARS]) == evidence:
                        return True
                position = text.find(src, position + 1)
        return False

    def _restore_checkpoint(self, chunks: Sequence[Sequence[dict[str, Any]]]) -> None:
        self._ensure_not_cancelled()
        if not self.checkpoint_enabled:
            self._checkpoint_diagnostics.append('disabled')
            return
        chunk_keys = []
        for chunk in chunks:
            self._ensure_not_cancelled()
            chunk_keys.append(digest(self._build_prompt(chunk)))
        try:
            project = _get_game_dir(Path(self.target_path)) or Path(self.target_path)
            capacity = {'input_bytes': self._input_byte_limit(),
                        'source_language': getattr(self.config, 'source_language', None),
                        'target_language': getattr(self.config, 'target_language', None)}
            self._checkpoint = ExtractionCheckpoint(
                project=project, mode='characters' if self.character_only else 'glossary',
                model_hash=semantic_fingerprint(self.platform or {}, capacity),
                chunk_keys=chunk_keys, root=self.checkpoint_root)
            restored = self._checkpoint.begin(resume=self.resume, force=self.force)
        except (OSError, TypeError, ValueError):
            self._checkpoint_diagnostics.append('identity_error')
            return
        valid = True
        for index, entries in restored.items():
            self._ensure_not_cancelled()
            for entry in entries:
                if not self._valid_checkpoint_entry(entry, chunks[index]):
                    valid = False
                    break
        if not valid:
            self._checkpoint.discard(list(restored))
            restored = {}
        self._resume_results = {index: (True, entries) for index, entries in restored.items()}

    def _run(self) -> dict[str, Any]:
        self.progress.set_phase(PHASE_COLLECTING)
        self._emit(force = True)
        self._report(Localizer.get().agent_glossary_collecting, 3)
        items, corpus_warnings = self._collect_corpus()
        warnings: list[str] = list(corpus_warnings)
        if items == []:
            raise ValueError(Localizer.get().agent_glossary_corpus_empty)

        base_payload: dict[str, Any] = {
            "entries": [],
            "corpus_count": len(items),
            "rule_candidate_count": 0,
            "llm_candidate_count": 0,
            "used_llm": False,
            "llm_chunks_total": 0,
            "llm_chunks_success": 0,
            "warnings": warnings,
        }
        # 读取失败本身就是部分覆盖，必须在状态里体现。
        incomplete = bool(corpus_warnings)

        usable, reason = self._agent_ready()
        if not usable:
            # 没有可用 Agent 就如实失败：绝不退回规则候选。
            warnings.append(reason)
            self.progress.set_phase(PHASE_COMPLETED)
            self._emit(force = True)
            return {**base_payload, "status": "failed", "coverage_complete": False}

        self._report(Localizer.get().agent_glossary_chunking, 10)
        chunks = self._build_chunks(items)
        planned_chunks = list(chunks)
        context_limited = getattr(self, "_context_limited_count", 0)
        if context_limited:
            incomplete = True
            warnings.append(Localizer.get().agent_glossary_context_limited.format(count = context_limited))
        self._restore_checkpoint(planned_chunks)
        missing = [index for index in range(len(planned_chunks)) if index not in self._resume_results]
        self._request_indices = missing[:max(0, self.MAX_LLM_CHUNKS)]
        total = len(self._resume_results) + len(self._request_indices)
        if len(missing) > len(self._request_indices):
            incomplete = True
            warnings.append(Localizer.get().agent_glossary_coverage_limited.format(
                total=len(planned_chunks), sent=total))
        self._ensure_not_cancelled()
        base_payload.update({'used_llm': bool(self._request_indices), 'llm_chunks_total': total})
        self.progress.set_phase(PHASE_EXTRACTING)
        self.progress.set_chunks(planned_chunks)
        for index, (_, entries) in sorted(self._resume_results.items()):
            self.progress.chunk_finished(index, True, reused=True)
            self.progress.see_candidates([row for row in entries if not self.character_only or row.get('type') == '角色'])
        if self._checkpoint is not None:
            self.progress.set_checkpoint(self._checkpoint.metadata())
        self._emit(force=True)
        results, chunk_warnings = self._run_chunks(chunks)
        warnings.extend(chunk_warnings)

        payloads: list[list[dict[str, Any]]] = []
        succeeded = 0
        for index in sorted(results):
            success, value = results[index]
            if success:
                succeeded += 1
                payloads.append(list(value))

        self._ensure_not_cancelled()
        self.progress.set_phase(PHASE_AGGREGATING)
        self._emit(force = True)
        self._report(Localizer.get().agent_glossary_aggregating, 92)
        merged = self._merge_candidates(payloads)
        if self.character_only:
            merged = [entry for entry in merged if entry.get("type") == "角色"]
        enriched = self._attach_evidence(merged, items)

        if succeeded == 0:
            status = "failed"
        elif succeeded < total or incomplete or warnings:
            status = "partial"
        else:
            status = "completed"

        self._ensure_not_cancelled()
        if self._checkpoint is not None:
            if succeeded == len(planned_chunks):
                if self.checkpoint_completion is None:
                    self._checkpoint.finish()
                else:
                    self.checkpoint_completion(self._checkpoint)
            self.progress.set_checkpoint(self._checkpoint.metadata())
        self.progress.set_phase(PHASE_COMPLETED)
        self._emit(force = True)
        planned_total = len(planned_chunks)
        coverage_percent = int(100 * succeeded / max(1, planned_total))
        if status != "completed":
            coverage_percent = min(99, coverage_percent)
        self._report(
            Localizer.get().agent_glossary_done.format(count = len(enriched)) if status == "completed"
            else Localizer.get().agent_glossary_partial_done.format(done = succeeded, total = planned_total, count = len(enriched)),
            coverage_percent if status != "completed" else 100,
        )
        return {
            **base_payload,
            "entries": enriched,
            **self._checkpoint_metadata(),
            "llm_candidate_count": sum(len(payload) for payload in payloads),
            "llm_chunks_success": succeeded,
            "llm_chunks_planned": planned_total,
            "llm_chunks_completed": len(results),
            "llm_chunks_failed": len(results) - succeeded,
            "llm_chunks_started": getattr(self, "_started_chunks", len(results)),
            "llm_chunks_pending": planned_total - len(results),
            "coverage_percent": coverage_percent,
            "warnings": warnings,
            "status": status,
            "coverage_complete": status == "completed",
        }

    def _emit(self, *, force: bool = False) -> None:
        """按低频间隔推送结构化快照；取消后不再发晚到事件。"""
        if self._cancelled():
            self.progress.close()
        if not callable(self.event_callback):
            return
        if not self.progress.should_emit(force = force):
            return
        try:
            self.event_callback(self.progress.snapshot())
        except Exception as exc:  # 事件通道不能影响提取本身
            self.debug(f"[GlossaryCandidate] 进度事件发送失败: {exc}")

    def _report(self, message: str, percent: int) -> None:
        if self.progress.closed or self._cancelled():
            return
        if callable(self.progress_callback):
            self.progress_callback(message, percent)
        self.info(f"[GlossaryCandidate] {percent}% {message}")

    def _cancelled(self) -> bool:
        return callable(self.cancel_callback) and bool(self.cancel_callback())

    def _ensure_not_cancelled(self) -> None:
        if self._cancelled():
            self.progress.close()
            raise InterruptedError(Localizer.get().agent_glossary_cancelled)

    def _agent_ready(self) -> tuple[bool, str]:
        if not isinstance(self.platform, dict) or not self.platform:
            return False, Localizer.get().agent_api_unset
        api_format = str(self.platform.get("api_format") or "").strip().casefold()
        if api_format not in self.SUPPORTED_FORMATS:
            return False, Localizer.get().agent_request_unsupported_format
        return True, ""

    # -------------------------------------------------------------- corpus

    def _collect_corpus(self) -> tuple[list[dict[str, Any]], list[str]]:
        """按源文件、行号顺序收集上下文；结构解析，不做任何名字判定。

        每一行都保留来源文件、行号、说话人与行种类：角色定义行整行保留，
        对白行保留说话人，普通字符串行保留原文。只有同一行内的完全相同文本
        才去重，跨行重复一律保留（不同语境不能合并成一条）。
        """
        warnings: list[str] = []
        try:
            game_dir = _get_game_dir(self.target_path)
        except Exception as exc:
            raise ValueError(Localizer.get().agent_glossary_corpus_empty) from exc

        items: list[dict[str, Any]] = []
        source_files, source_warning = self._source_files(game_dir)
        if source_warning:
            warnings.append(source_warning)
        for path in source_files:
            self._ensure_not_cancelled()
            try:
                content = path.read_text(encoding = "utf-8", errors = "ignore")
            except OSError:
                warnings.append(
                    Localizer.get().agent_glossary_read_failed.format(name = path.name)
                )
                continue
            try:
                # 相对路径是模型侧可核对的真实来源，不能用裸文件名。
                source_name = path.relative_to(game_dir).as_posix()
            except ValueError:
                source_name = path.name
            definition_name = ""
            definition_kind = ""
            depth = 0
            for number, raw in enumerate(content.splitlines(), start = 1):
                self._ensure_not_cancelled()
                assignment = self.RE_ASSIGNMENT.match(raw)
                if depth <= 0:
                    definition_name = assignment.group("name") if assignment else ""
                    definition_kind = "character-definition" if self.RE_CHARACTER_DEF.search(self.RE_STRING.sub("", raw)) else "definition"
                before = len(items)
                if depth > 0 and definition_name:
                    value = self._normalize_definition(raw)
                    if value:
                        self._push(items, set(), value, source_name, number, definition_kind, "")
                else:
                    self._append_line(items, set(), raw, source_name, number)
                if definition_name:
                    for item in items[before:]:
                        item["definition_name"] = definition_name
                # Structural continuation only; no evaluation of game expressions.
                code = self.RE_STRING.sub("", raw).split("#", 1)[0]
                depth = max(0, depth + sum(code.count(c) for c in "([{") - sum(code.count(c) for c in ")]}")) if definition_name else 0
        return self._order_items(items), warnings

    def _source_files(self, game_dir: Path) -> tuple[list[Path], str]:
        """列出源文件；遍历失败要作为覆盖缺口上报，不能静默当成完整语料。"""
        files: list[Path] = []
        try:
            candidates = sorted(
                game_dir.rglob("*.rpy"), key = lambda item: str(item).casefold()
            )
        except OSError as exc:
            return files, Localizer.get().agent_glossary_list_failed.format(reason = str(exc))
        for path in candidates:
            try:
                parts = path.relative_to(game_dir).parts
            except ValueError:
                parts = path.parts
            if any(part.casefold() in self.SKIP_DIRS for part in parts):
                continue
            files.append(path)
        return files, ""


    # 语境证据强度：角色定义 > 其它赋值 > 剧情对白 > UI 上下文。
    KIND_ORDER = {
        "character-definition": 0,
        "definition": 1,
        "dialogue": 2,
        "ui": 3,
    }

    def _order_items(self, items: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        """按证据强度稳定排序，并重排 id；不丢任何一条语料。

        请求之间没有记忆；排序只决定处理优先级。每块自己的依赖定义和邻接
        对白由 _build_chunks 补齐，不能把先发送某块当成其它块的上下文。
        """
        ordered = sorted(
            items,
            key = lambda item: (
                self.KIND_ORDER.get(str(item.get("kind", "")), 2),
                str(item.get("source", "")),
                int(item.get("line", 0) or 0),
                int(item.get("id", 0) or 0),
            ),
        )
        results: list[dict[str, Any]] = []
        for index, item in enumerate(ordered):
            results.append({**item, "id": index})
        return results

    def _append_line(
        self,
        items: list[dict[str, Any]],
        seen_in_line: set[str],
        raw: str,
        source: str,
        number: int,
    ) -> None:
        line = str(raw or "")
        if line.strip() == "":
            return

        # 角色定义行整行保留：模型能看到 Character(...) 的上下文与显示名。
        if self.RE_CHARACTER_DEF.search(self.RE_STRING.sub("", line)) is not None:
            text = self._normalize_definition(line)
            if text:
                self._push(items, seen_in_line, text, source, number, "character-definition", "")
            return

        # define / default 等赋值行整行保留：变量名与显示名的对应关系本身就是证据，
        # 只送字符串字面量会丢掉“谁是谁”的语境。
        if self.RE_DEFINITION.search(line) is not None or self.RE_ASSIGNMENT.match(line) is not None:
            text = self._normalize_definition(line)
            if text:
                self._push(items, seen_in_line, text, source, number, "definition", "")
            return

        speaker_match = self.RE_SPEAKER.match(line)
        speaker = speaker_match.group("speaker") if speaker_match is not None else ""
        literals = self._string_literals(line)
        if not literals:
            return
        # UI 语句里的字符串属于界面上下文，排在角色与剧情之后，但仍全部发送。
        kind = "ui" if self.RE_UI_LINE.search(line) is not None else "dialogue"
        for literal in literals:
            text = self._normalize_context(literal)
            if text:
                before = len(items)
                self._push(items, seen_in_line, text, source, number, kind, speaker)
                for item in items[before:]:
                    # Keep syntax/usage without repeating an arbitrarily long literal.
                    item["statement"] = self._normalize_context(self.RE_STRING.sub('"<text>"', line))

    def _push(
        self,
        items: list[dict[str, Any]],
        seen_in_line: set[str],
        text: str,
        source: str,
        number: int,
        kind: str,
        speaker: str,
    ) -> None:
        for segment in self._split_long_text(text):
            key = f"{kind}|{segment}"
            if key in seen_in_line:
                continue
            seen_in_line.add(key)
            items.append(
                {
                    "id": len(items),
                    "text": segment,
                    "source": source,
                    "line": number,
                    "kind": kind,
                    "speaker": speaker,
                }
            )

    def _string_literals(self, line: str) -> list[str]:
        literals: list[str] = []
        for match in self.RE_STRING.finditer(str(line or "")):
            raw = match.group(1) if match.group(1) is not None else match.group(2)
            if raw is None:
                continue
            literals.append(_unescape(raw))
        return literals

    @staticmethod
    def _normalize_definition(text: str) -> str:
        # Braces in assignments can be dictionaries, not formatting tags.
        return " ".join(str(text or "").split())

    @staticmethod
    def _normalize_context(text: str) -> str:
        cleaned = _strip_format_tags(str(text or ""))
        cleaned = cleaned.replace("\r", " ").replace("\n", " ").replace("\u3000", " ")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned == "":
            return ""
        if GlossaryCandidateService.RE_STRUCTURAL_NOISE.fullmatch(cleaned) is not None:
            return ""
        return cleaned

    def _split_long_text(self, text: str) -> list[str]:
        """超长文本按句读/词边界切段，带重叠，避免把名字切两半。"""
        limit = self.MAX_ITEM_CHARS
        if len(text) <= limit:
            return [text]

        overlap = self.SEGMENT_OVERLAP
        boundaries = ".!?;。！？；"
        segments: list[str] = []
        start = 0
        length = len(text)
        while start < length:
            end = min(start + limit, length)
            if end < length:
                window = text[start:end]
                cut = max(window.rfind(char) for char in boundaries)
                if cut <= limit // 3:
                    # 没有句读时退到最近的空白，避免切断词或名字。
                    cut = window.rfind(" ")
                if cut <= limit // 3:
                    cut = limit - 1
                end = start + cut + 1
            segment = text[start:end].strip()
            if segment:
                segments.append(segment)
            if end >= length:
                break
            # 带重叠前进：跨切点的名字在下一段仍然完整。
            start = max(end - overlap, start + 1)
        return segments

    def _input_byte_limit(self) -> int:
        """Conservative input guard including JSON metadata and the prompt.

        UTF-8 bytes upper-bound ordinary tokenizer tokens. Model capacity comes
        from the same read-only catalogue as AgentRequester; reasoning settings
        and platform configuration are never altered here.
        """
        if not hasattr(self, "_cached_input_byte_limit"):
            from module.Agent.ModelBudget import resolve_capability
            try:
                from module.Agent.ModelCatalog import get as get_catalog
                catalog = get_catalog(self.platform)
            except Exception:
                catalog = None
            context, output = resolve_capability(self.platform, catalog)
            try:
                explicit_context = int((self.platform or {}).get("context_window") or 0)
            except (TypeError, ValueError):
                explicit_context = 0
            if explicit_context > 0:
                context = min(context, explicit_context)
            self._cached_input_byte_limit = max(0, context - output - 256)
        return self._cached_input_byte_limit

    def _build_chunks(self, items: Sequence[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        """Cover every source item with bounded context repeated per request.

        Dependency lookup uses identifiers/assignments only, never name heuristics.
        Original ids, relative paths and line numbers survive all context copies.
        """
        definitions: dict[str, list[dict[str, Any]]] = {}
        references: dict[int, set[str]] = {}
        character_users: dict[str, list[dict[str, Any]]] = {}
        dialogue: dict[str, list[dict[str, Any]]] = {}
        for item in items:
            value = str(item.get("text", ""))
            assignment = self.RE_ASSIGNMENT.match(value)
            name = str(item.get("definition_name") or (assignment.group("name") if assignment else ""))
            if name:
                definitions.setdefault(name, []).append(item)
            code = self.RE_STRING.sub("", str(item.get("statement", value if item.get("kind") in {"definition", "character-definition"} else "")))
            refs = set(self.RE_IDENTIFIER.findall(code))
            refs.update(self.RE_IDENTIFIER.findall(str(item.get("speaker", ""))))
            for expression in re.findall(r"(?<!\[)\[([^\[\]]+)\]", value):
                refs.update(self.RE_IDENTIFIER.findall(expression))
            refs.discard(name)
            references[int(item["id"])] = refs
            if item.get("kind") == "character-definition":
                for ref in refs:
                    character_users.setdefault(ref, []).append(item)
            if item.get("kind") == "dialogue":
                dialogue.setdefault(str(item.get("source", "")), []).append(item)
        dialogue_lines: dict[str, list[int]] = {}
        for source, rows in dialogue.items():
            rows.sort(key = lambda row: (int(row.get("line", 0)), int(row["id"])))
            dialogue_lines[source] = [int(row.get("line", 0)) for row in rows]

        def context_for(item: dict[str, Any]) -> list[dict[str, Any]]:
            related: list[dict[str, Any]] = []
            visited = {int(item["id"])}
            todo = [item]
            source = str(item.get("source", ""))
            rows = dialogue.get(source, [])
            if rows and item.get("kind") in {"dialogue", "ui", "definition", "character-definition"}:
                position = bisect_left(dialogue_lines[source], int(item.get("line", 0)))
                for neighbour in rows[max(0, position - 1):position + 2]:
                    if int(neighbour["id"]) not in visited:
                        related.append(neighbour)
                        visited.add(int(neighbour["id"]))
                        todo.append(neighbour)
            while todo:
                current = todo.pop()
                assignment = self.RE_ASSIGNMENT.match(str(current.get("text", "")))
                name = str(current.get("definition_name") or (assignment.group("name") if assignment else ""))
                dependencies = list(character_users.get(name, []))
                for ref in sorted(references.get(int(current["id"]), set())):
                    dependencies.extend(definitions.get(ref, []))
                if name:
                    dependencies.extend(definitions.get(name, []))
                for row in dependencies:
                    identifier = int(row["id"])
                    if identifier not in visited:
                        visited.add(identifier)
                        related.append(row)
                        todo.append(row)
            return sorted(related, key = lambda row: self.KIND_ORDER.get(str(row.get("kind", "")), 2))

        def size(item: dict[str, Any]) -> int:
            return len(str(item.get("text", ""))) + len(str(item.get("statement", "")))

        chunks: list[list[dict[str, Any]]] = []
        current: dict[int, dict[str, Any]] = {}
        chars = 0
        self._context_limited_count = 0
        prompt_bytes = len(json.dumps(self._build_prompt([]), ensure_ascii = False).encode("utf-8"))
        byte_limit = max(0, self._input_byte_limit() - prompt_bytes)
        current_bytes = 0
        def encoded_size(row: dict[str, Any]) -> int:
            # JSONLINE is itself encoded in the message's JSON string.
            line = json.dumps(row, ensure_ascii = False) + "\n"
            return len(json.dumps(line, ensure_ascii = False).encode("utf-8"))
        for item in items:
            self._ensure_not_cancelled()
            group = [item, *context_for(item)]
            additions = [row for row in group if int(row["id"]) not in current]
            if current and (len(current) + len(additions) > self.CHUNK_MAX_ITEMS or chars + sum(map(size, additions)) > self.CHUNK_MAX_CHARS or current_bytes + sum(map(encoded_size, additions)) > byte_limit):
                chunks.append(list(current.values()))
                current = {}
                chars = 0
                current_bytes = 0
            for row in group:
                identifier = int(row["id"])
                if identifier in current:
                    continue
                if current and (len(current) >= self.CHUNK_MAX_ITEMS or chars + size(row) > self.CHUNK_MAX_CHARS or current_bytes + encoded_size(row) > byte_limit):
                    self._context_limited_count += 1
                    continue
                current[identifier] = row
                chars += size(row)
                current_bytes += encoded_size(row)
        if current:
            chunks.append(list(current.values()))
        return chunks


    def _build_prompt(self, chunk: Sequence[dict[str, Any]]) -> list[dict[str, str]]:
        payload = "\n".join(json.dumps(item, ensure_ascii = False) for item in chunk)
        if self.character_only:
            goal = (
                "任务：从输入文本里找出人物名字，判断依据是语义：在剧情里指代具体人物。\n"
                "kind=character-definition 是角色定义，但动态玩家输入不能猜名字；"
                "kind=definition 只是 define/default 等普通赋值语境，不等于人名。"
                "default item_name = \"Moon Blade\" 是物品；default hero_name = \"Luma\" "
                "需结合 Character(hero_name) 或对白中的人物指代来判断。\n"
            )
        else:
            goal = (
                "任务：找出这款游戏特有的专有名词：人名、地名、组织、物品、"
                "以及游戏世界观里的设定、称谓、专用词。\n"
            )
        prompt = (
            "你是 Ren'Py 游戏本地化的专名抽取器。\n" + goal
            + "判断完全依据语义与当前请求的语境，不要依赖大小写、词形、出现频次或常见英文名；"
            "非英语人名及其它专名和只出现一次的专名同样可提取。每个请求独立，不记得其它分块。\n"
            "通用界面词、通用按键/设备提示、引擎与运行时名词在这些通用用途下不属于目标；不按单词拼写设黑名单。"
            "反例：textbutton \"History\" action ShowMenu(\"history\") 是菜单用途，"
            "Help 页面里的 Mouse、Enter、Keyboard、Gamepad 是通用操作说明，应输出 []。"
            "但 define h = Character('History') 且 h 在剧情说话时，History 是角色，应提取；"
            "Help 或 Mouse 若确为游戏人物或专用实体也可提取。Ren'Py 只作引擎说明时不提取。\n"
            "[变量] 是原样保护的引用，不自动当姓名；变量名只是引用，不等于真实显示名。"
            "保留名字本身合法的 []，不得执行代码或猜动态玩家输入。\n"
            "define/default/常量仅提供语境，赋值里的字符串并非都指人物。"
            "Luma drew the Moon Blade at Eastwatch. 中分别是角色、物品、地名。\n"
            "输入是 JSONLINE，字段 id、source、line、kind、speaker、text。source 是相对路径，line 是真实源码行号。character-definition/definition 提供定义语境，"
            "dialogue 为剧情，ui 为界面；语境标签不替代语义判断。\n"
            "只输出 JSONLINE，每行一个对象：\n"
            '{"src":"原文专名","type":"角色|地名|组织|物品|术语","line":0,"evidence":"短原文依据"}\n'
            "line 必须填该输入行的 id。src 必须是 text 里逐字出现的原样片段，保留大小写，"
            "不得改写、翻译、拼接或臆造。evidence 用该行中包含 src 的短原文片段，"
            "不要推理过程。同一概念只输出一次，不输出整句。没有候选只输出 []，不加解释或代码块。\n"
            "输入：\n" + payload
        )
        return [{"role": "user", "content": prompt}]

    def _run_chunks(
        self, chunks: Sequence[Sequence[dict[str, Any]]]
    ) -> tuple[dict[int, tuple[bool, Any]], list[str]]:
        """Fixed request slots, per-chunk deadlines, and a single event publisher.

        Timed-out slots are never replaced by more request threads. Healthy slots
        continue consuming the queue. Cancellation/close may themselves block, so
        a fixed set of daemon cleanup slots performs cancellation off this thread.
        """
        total = len(chunks)
        request_indices = getattr(self, '_request_indices', list(range(total)))
        self._started_chunks = 0
        if not request_indices:
            return dict(self._resume_results), []
        if not total:
            return {}, []
        workers = max(1, min(self.CHUNK_CONCURRENCY, len(request_indices)))
        lock = threading.Lock()
        stop = threading.Event()
        user_cancelled = threading.Event()
        results: dict[int, tuple[bool, Any]] = dict(self._resume_results)
        active: dict[int, dict[str, Any]] = {}
        events: queue.Queue = queue.Queue()
        cancellations: queue.Queue = queue.Queue()
        cancel_sent: set[int] = set()
        next_index = 0
        self._started_chunks = 0

        def cancel_worker() -> None:
            while True:
                requester = cancellations.get()
                if requester is None:
                    return
                try:
                    requester.cancel()
                except Exception:
                    pass

        def queue_cancel(index: int, entry: dict[str, Any]) -> None:
            requester = entry.get("requester")
            if requester is not None and index not in cancel_sent:
                cancel_sent.add(index)
                cancellations.put(requester)

        def worker() -> None:
            nonlocal next_index
            while True:
                with lock:
                    if stop.is_set() or next_index >= len(request_indices):
                        return
                    index = request_indices[next_index]
                    next_index += 1
                    started = time.monotonic()
                    active[index] = {"requester": None, "started": started, "settled": None}
                    self._started_chunks += 1
                    events.put(("start", index, started))
                requester = None
                try:
                    if self._cancelled():
                        raise InterruptedError(Localizer.get().agent_glossary_cancelled)
                    requester = AgentRequester(self.config, self.platform or {})
                    with lock:
                        active[index]["requester"] = requester
                        abandoned = stop.is_set() or index in results
                        if abandoned:
                            queue_cancel(index, active[index])
                    if abandoned:
                        return
                    outcome = self._request_chunk(index, chunks[index], requester)
                except InterruptedError:
                    user_cancelled.set()
                    stop.set()
                    outcome = (False, Localizer.get().agent_glossary_cancelled)
                except Exception as exc:
                    outcome = (False, Localizer.get().agent_glossary_chunk_failed.format(
                        index = index + 1, reason = str(exc)))
                finally:
                    # Settlement precedes close: a blocking cleanup must not lose
                    # an already valid response or free a physically occupied slot.
                    with lock:
                        if not stop.is_set() and index not in results:
                            finished = time.monotonic()
                            # Check the deadline here as well: a late result can
                            # arrive between coordinator polling ticks.
                            if finished - active[index]["started"] >= self.CHUNK_TIMEOUT_SECONDS:
                                outcome = (False, Localizer.get().agent_glossary_chunk_timeout.format(index = index + 1))
                            results[index] = outcome
                            active[index]["settled"] = finished
                            events.put(("finish", index, outcome))
                    if requester is not None:
                        try:
                            requester.close()
                        except Exception:
                            pass
                    with lock:
                        active.pop(index, None)

        def drain_events() -> None:
            while not events.empty():
                if self._cancelled() or self.progress.closed:
                    return
                event, index, value = events.get_nowait()
                if event == "start":
                    self.progress.chunk_started(index, value)
                else:
                    success, rows = value
                    if success and isinstance(rows, list) and self._checkpoint is not None:
                        if not all(self._valid_checkpoint_entry(row, chunks[index]) for row in rows):
                            success = False
                            rows = Localizer.get().agent_glossary_chunk_failed.format(
                                index=index + 1, reason=Localizer.get().agent_glossary_invalid_response)
                            with lock:
                                results[index] = (False, rows)
                        else:
                            committed = self._checkpoint.save(index, rows)
                            if committed is not None:
                                rows = committed
                                with lock:
                                    results[index] = (True, rows)
                        self.progress.set_checkpoint(self._checkpoint.metadata())
                    self.progress.chunk_finished(index, bool(success))
                    if success and isinstance(rows, list):
                        visible = [row for row in rows if not self.character_only or row.get("type") == "角色"]
                        self.progress.see_candidates(visible)
                    done = self.progress.snapshot()["completed_chunks"]
                    self._report(Localizer.get().agent_glossary_requesting.format(done = done, total = total),
                                 12 + int(done / total * 78))
                self._emit(force = True)

        cleaners = [threading.Thread(target = cancel_worker, name = f"glossary-cancel-{i}", daemon = True)
                    for i in range(workers)]
        threads = [threading.Thread(target = worker, name = f"glossary-agent-{i}", daemon = True)
                   for i in range(workers)]
        for thread in cleaners + threads:
            thread.start()
        cancelled = False
        try:
            while True:
                if self._cancelled() or user_cancelled.is_set():
                    cancelled = True
                    self.progress.close()
                    break
                now = time.monotonic()
                with lock:
                    for index, entry in active.items():
                        if index not in results and now - entry["started"] >= self.CHUNK_TIMEOUT_SECONDS:
                            outcome = (False, Localizer.get().agent_glossary_chunk_timeout.format(index = index + 1))
                            results[index] = outcome
                            entry["settled"] = now
                            events.put(("finish", index, outcome))
                            queue_cancel(index, entry)
                    settled = len(results) == len(self._resume_results) + len(request_indices)
                    # The grace applies only to a completely blocked window,
                    # never to healthy slots still making progress after a timeout.
                    blocked = len(active) == workers and all(
                        entry["settled"] is not None and now - entry["settled"] >= self.CLOSE_TIMEOUT_SECONDS
                        for entry in active.values())
                drain_events()
                self._emit()
                if settled or blocked or not any(thread.is_alive() for thread in threads):
                    break
                stop.wait(0.05)
        finally:
            with lock:
                stop.set()
                for index, entry in active.items():
                    queue_cancel(index, entry)
            deadline = time.monotonic() + self.CLOSE_TIMEOUT_SECONDS
            for thread in threads:
                thread.join(max(0.0, deadline - time.monotonic()))
            for _ in cleaners:
                cancellations.put(None)
            for thread in cleaners:
                thread.join(max(0.0, deadline - time.monotonic()))
        if cancelled or user_cancelled.is_set() or self._cancelled():
            self.progress.close()
            raise InterruptedError(Localizer.get().agent_glossary_cancelled)
        drain_events()
        with lock:
            settled_results = dict(results)
        warnings = [Localizer.get().agent_glossary_chunk_unresolved.format(index = index + 1)
                    for index in request_indices if index not in settled_results]
        warnings.extend(value for success, value in settled_results.values()
                        if not success and isinstance(value, str))
        return settled_results, warnings


    def _request_chunk(
        self,
        index: int,
        chunk: Sequence[dict[str, Any]],
        requester: AgentRequester,
    ) -> tuple[bool, Any]:
        self.info(
            "[GlossaryCandidate] "
            + Localizer.get().agent_glossary_chunk_label.format(index = index + 1)
        )
        messages = self._build_prompt(chunk)
        if len(json.dumps(messages, ensure_ascii = False).encode("utf-8")) > self._input_byte_limit():
            return False, Localizer.get().agent_glossary_chunk_failed.format(
                index = index + 1, reason = Localizer.get().agent_glossary_prompt_budget)
        result = requester.request_text(messages)
        if result.error_code == "CANCELLED":
            if self._cancelled():
                raise InterruptedError(Localizer.get().agent_glossary_cancelled)
            return False, Localizer.get().agent_glossary_chunk_timeout.format(
                index = index + 1
            )
        if not result.success:
            return False, Localizer.get().agent_glossary_chunk_failed.format(
                index = index + 1,
                reason = result.error_message or result.error_code or "",
            )

        text = str(result.text or "")
        if text.strip() == "":
            return False, Localizer.get().agent_glossary_chunk_failed.format(
                index = index + 1, reason = Localizer.get().agent_glossary_empty_response
            )
        if self.decoder.is_empty_result(text):
            return True, []

        decoded = self.decoder.decode(text)
        if decoded == []:
            return False, Localizer.get().agent_glossary_chunk_failed.format(
                index = index + 1,
                reason = Localizer.get().agent_glossary_invalid_response,
            )

        grounded: list[dict[str, Any]] = []
        rejected = 0
        for entry in decoded:
            located = self._locate_candidate_source(entry, chunk)
            if located is None:
                rejected += 1
                continue
            src, source_item = located
            source_text = str(source_item["text"])
            evidence = self._match_source_slice(str(entry.get("evidence", "")).strip(), source_text)
            if not evidence or self._match_source_slice(src, evidence) is None:
                start = max(0, source_text.find(src) - 12)
                evidence = source_text[start:start + PROGRESS_EVIDENCE_CHARS]
            elif len(evidence) > PROGRESS_EVIDENCE_CHARS:
                start = max(0, evidence.find(src) - 8)
                evidence = evidence[start:start + PROGRESS_EVIDENCE_CHARS]
            grounded.append(
                {
                    "src": src,
                    "dst": "",
                    "type": self._normalize_candidate_type(entry.get("type", "")),
                    "comment": AUTO_COMMENT,
                    "info": AUTO_COMMENT,
                    "case_sensitive": False,
                    "origin": "agent",
                    "evidence": _short_evidence(evidence),
                    "source": str(source_item.get("source", "")),
                    "line": int(source_item.get("line", 0)),
                }
            )

        if grounded == [] and rejected > 0:
            # 模型给出的词在输入里找不到，是无效响应，不能算「零候选」。
            return False, Localizer.get().agent_glossary_chunk_failed.format(
                index = index + 1,
                reason = Localizer.get().agent_glossary_ungrounded.format(count = rejected),
            )
        return True, grounded

    def _locate_candidate(
        self, entry: dict[str, Any], chunk: Sequence[dict[str, Any]]
    ) -> str | None:
        located = self._locate_candidate_source(entry, chunk)
        return located[0] if located else None

    def _locate_candidate_source(
        self, entry: dict[str, Any], chunk: Sequence[dict[str, Any]]
    ) -> tuple[str, dict[str, Any]] | None:
        """Resolve spelling AND actual evidence row; never trust model paths."""
        src = self._normalize_candidate_text(str(entry.get("src", "")))
        if not src or len(src) > self.MAX_CANDIDATE_CHARS or "\n" in src or "\r" in src:
            return None
        hinted = [item for item in chunk if item.get("id") == entry.get("line")]
        for item in [*hinted, *chunk]:
            found = self._match_source_slice(src, str(item["text"]))
            if found is not None:
                return found, item
        return None

    @staticmethod
    def _match_source_slice(src: str, text: str) -> str | None:
        """返回源文里真实出现的切片：大小写与原文一致，找不到就是找不到。

        模型可能把 nora 报成 NORA；直接返回模型写法会产出源码里不存在的术语。
        但 casefold 后的下标不是原文字符下标（ß 展开成 ss、İ 展开成两个码位），
        直接拿它切原文会切出 'ORA' 这类错位片段，所以这里先把折叠串逐字映射回
        原文位置，只在「起点是字符起点、终点是字符终点」且切片的 casefold 与
        候选完全相等时才接受。"""
        if src == "" or text == "":
            return None

        exact = text.find(src)
        if exact >= 0:
            return text[exact : exact + len(src)]

        needle = src.casefold()
        if needle == "":
            return None

        # folded 是逐字折叠结果；mapping[i] 是 folded[i] 对应的原文字符下标。
        folded_parts: list[str] = []
        mapping: list[int] = []
        for index, char in enumerate(text):
            piece = char.casefold()
            folded_parts.append(piece)
            mapping.extend([index] * len(piece))
        folded = "".join(folded_parts)

        start = folded.find(needle)
        while start >= 0:
            end_position = start + len(needle) - 1
            starts_on_boundary = start == 0 or mapping[start - 1] != mapping[start]
            ends_on_boundary = (
                end_position + 1 >= len(mapping)
                or mapping[end_position + 1] != mapping[end_position]
            )
            if starts_on_boundary and ends_on_boundary:
                slice_start = mapping[start]
                slice_end = mapping[end_position] + 1
                candidate = text[slice_start:slice_end]
                # 可证明正确的逐字校验：折叠后必须与候选完全一致。
                if candidate.casefold() == needle:
                    return candidate
            start = folded.find(needle, start + 1)
        return None

    # ------------------------------------------------------------ aggregate

    def _merge_candidates(
        self, payloads: Sequence[Sequence[dict[str, Any]]]
    ) -> list[dict[str, Any]]:
        buckets: dict[str, dict[str, Any]] = {}
        votes: dict[str, dict[str, int]] = {}
        for payload in payloads:
            for entry in payload:
                src = str(entry.get("src", "")).strip()
                if src == "":
                    continue
                key = src.casefold()
                buckets.setdefault(key, {**entry, "src": src})
                counter = votes.setdefault(key, {})
                type_name = str(entry.get("type", "") or "术语")
                counter[type_name] = counter.get(type_name, 0) + 1

        results: list[dict[str, Any]] = []
        for key, entry in buckets.items():
            counter = votes.get(key, {})
            final_type = "术语"
            if counter:
                final_type = max(counter.items(), key = lambda item: item[1])[0]
            results.append({**entry, "type": final_type})
        return results

    def _attach_evidence(
        self, candidates: Sequence[dict[str, Any]], items: Sequence[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if candidates == []:
            return []

        lines = [str(item["text"]) for item in items]
        lowered = [line.casefold() for line in lines]
        results: list[dict[str, Any]] = []
        for candidate in candidates:
            self._ensure_not_cancelled()
            src = str(candidate.get("src", "")).strip()
            if src == "":
                continue
            needle = src.casefold()
            matched = [
                index for index, haystack in enumerate(lowered) if needle in haystack
            ]
            if not matched:
                continue
            results.append(
                {
                    "src": src,
                    "dst": "",
                    "type": str(candidate.get("type", "术语") or "术语"),
                    "comment": AUTO_COMMENT,
                    "info": AUTO_COMMENT,
                    "case_sensitive": False,
                    "count": len(matched),
                    "contexts": [lines[index] for index in matched[:3]],
                }
            )

        results.sort(
            key = lambda item: (-int(item.get("count", 0) or 0), str(item.get("src", "")))
        )
        return results

    # --------------------------------------------------------------- utils

    def _normalize_candidate_text(self, text: str) -> str:
        cleaned = _strip_format_tags(str(text or ""))
        cleaned = cleaned.replace("\r", " ").replace("\n", " ").replace("\u3000", " ")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned.strip("\"'“”‘’(){}<>.,;:!?")

    def _normalize_candidate_type(self, raw_type: Any) -> str:
        normalized = str(raw_type or "").strip().lower()
        if normalized != "":
            for type_name, hints in self.TYPE_HINTS.items():
                if any(hint in normalized for hint in hints):
                    return type_name
        return "术语"


def extract_glossary_candidates(
    *,
    config: Config,
    target_path: str | Path,
    platform: dict[str, Any] | None,
    progress_callback: ProgressCallback | None = None,
    cancel_callback: CancelCallback | None = None,
    event_callback: EventCallback | None = None,
    resume: bool = True,
    force: bool = False,
    checkpoint_root: str | Path | None = None,
    checkpoint_enabled: bool = False,
    checkpoint_completion: Callable[[ExtractionCheckpoint], None] | None = None,
) -> dict[str, Any]:
    """执行术语候选抽取（全部候选由 Agent 判定）。"""
    service = GlossaryCandidateService(
        config = config,
        target_path = target_path,
        platform = platform,
        progress_callback = progress_callback,
        cancel_callback = cancel_callback,
        event_callback = event_callback,
        resume = resume,
        force = force,
        checkpoint_root = checkpoint_root,
        checkpoint_enabled = checkpoint_enabled,
        checkpoint_completion = checkpoint_completion,
    )
    return service.run()


def extract_character_candidates(
    *,
    config: Config,
    target_path: str | Path,
    platform: dict[str, Any] | None,
    progress_callback: ProgressCallback | None = None,
    cancel_callback: CancelCallback | None = None,
    event_callback: EventCallback | None = None,
    resume: bool = True,
    force: bool = False,
    checkpoint_root: str | Path | None = None,
    checkpoint_enabled: bool = False,
    checkpoint_completion: Callable[[ExtractionCheckpoint], None] | None = None,
) -> dict[str, Any]:
    """角色人名抽取：同一 Agent 通道，只保留模型标注为「角色」的候选。"""
    service = GlossaryCandidateService(
        config = config,
        target_path = target_path,
        platform = platform,
        progress_callback = progress_callback,
        cancel_callback = cancel_callback,
        character_only = True,
        event_callback = event_callback,
        resume = resume,
        force = force,
        checkpoint_root = checkpoint_root,
        checkpoint_enabled = checkpoint_enabled,
        checkpoint_completion = checkpoint_completion,
    )
    payload = service.run()
    payload["names"] = [str(entry.get("src", "")) for entry in payload.get("entries", [])]
    return payload
