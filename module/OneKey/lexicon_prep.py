"""一条龙的词库预处理：术语/人名交给 Agent，禁翻表保留结构扫描。

历史：这里曾经用「扫描 Character 定义 + 词形启发式过滤」生成术语候选
（NOT_TERM_PHRASES / looks_like_term / filter_not_terms）。规则既漏提非英语名字，
也把 Rose 这类普通名词混进候选。现在术语与人名一律由 Agent 通道判定（见
module/Extract/GlossaryCandidateService.py），本模块只负责：

1. 把 Agent 候选转换成可落盘的候选行（只补缺失的 src，绝不覆盖已有条目）；
2. 扫描 [variable] 合并进禁翻表（结构解析，与术语判定无关）。

本模块不依赖 api，也不直接写配置：调用方拿到计划后自己落盘。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from module.Localizer.Localizer import Localizer
from module.Tool import LexiconOps

# 与 GlossaryCandidateService / 一键流程共用的状态词。
STATUS_COMPLETED = "completed"
STATUS_PARTIAL = "partial"
STATUS_SKIPPED = "skipped"
STATUS_FAILED = "failed"


@dataclass
class GlossaryPrepResult:
    """术语预处理的产物与统计。

    entries 只有「本次应当新增」的候选：调用方用它做 merge，不得 replace，
    这样已有译名、备注与禁用状态都不会被覆盖或重新启用。
    """

    entries: list[dict[str, Any]] = field(default_factory=list)
    added: int = 0
    scanned: int = 0
    kept_existing: int = 0
    status: str = STATUS_SKIPPED
    warnings: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def changed(self) -> bool:
        return bool(self.added)

    def summary(self) -> str:
        if self.status == STATUS_SKIPPED:
            return "术语提取已跳过"
        if self.status == STATUS_FAILED:
            return f"Agent 提取术语失败：{self.error}"
        if self.status == STATUS_PARTIAL:
            return f"Agent 只完成部分分块，已保留 {self.added} 条候选"
        return f"Agent 已提取 {self.added} 条术语候选"


def normalize_src(value: Any) -> str:
    """候选原文的规范化键，与仓库合并口径保持一致。"""
    return LexiconOps.normalize_glossary_src(str(value or ""))


def existing_src_keys(rows: Iterable[Mapping[str, Any]]) -> set[str]:
    """已有条目的规范化键集合；它们不会被本次候选覆盖。"""
    keys: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        key = normalize_src(row.get("src", row.get("source", "")))
        if key:
            keys.add(key)
    return keys


def build_candidate_rows(entries: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """把 Agent 候选转换成候选行（只做结构整形，不做语义判断）。"""
    rows: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        src = str(entry.get("src", entry.get("source", "")) or "").strip()
        if not src:
            continue
        type_name = str(entry.get("type", "") or "").strip()
        note = str(entry.get("info", entry.get("comment", "")) or "").strip()
        rows.append(
            {
                "src": src,
                "dst": str(entry.get("dst", entry.get("target", "")) or "").strip(),
                "type": f"候选 / {type_name}" if type_name else "候选",
                "info": note or "术语候选 (Agent 提取)",
                "comment": note or "术语候选 (Agent 提取)",
                "case_sensitive": bool(entry.get("case_sensitive", False)),
                "candidate": True,
                "candidate_confirmed": False,
                "enabled": True,
                "regex": False,
            }
        )
    return rows


def select_new_entries(
    candidate_rows: Sequence[Mapping[str, Any]],
    known_keys: set[str],
) -> list[dict[str, Any]]:
    """只保留尚不存在的候选；同批内重复也只留第一条。"""
    fresh: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in candidate_rows:
        if not isinstance(row, Mapping):
            continue
        key = normalize_src(row.get("src", ""))
        if not key or key in known_keys or key in seen:
            continue
        seen.add(key)
        fresh.append(dict(row))
    return fresh


def prepare_glossary(
    config: Any,
    existing_rows: Sequence[Mapping[str, Any]],
    *,
    extract: Callable[[], Mapping[str, Any]] | None = None,
    enabled: bool = True,
    cancel_check: Callable[[], bool] | None = None,
) -> GlossaryPrepResult:
    """调用 Agent 抽取术语候选，返回「只新增」的候选行。

    extract 由调用方注入（通常包装 GlossaryCandidateService 的公共入口），
    本模块不自己发请求，也不做任何词形/频次判断。
    """
    if not enabled:
        return GlossaryPrepResult(status=STATUS_SKIPPED)

    if cancel_check is not None and cancel_check():
        raise InterruptedError("术语提取已取消")

    if extract is None:
        message = "未配置 Agent 术语抽取通道"
        return GlossaryPrepResult(status=STATUS_FAILED, error=message, warnings=[message])

    try:
        payload = extract()
    except InterruptedError:
        raise
    except Exception as exc:  # 抽取失败不能拖垮一键流程
        message = str(exc)
        return GlossaryPrepResult(status=STATUS_FAILED, error=message, warnings=[message])

    if not isinstance(payload, Mapping):
        message = "Agent 未返回可用结果"
        return GlossaryPrepResult(status=STATUS_FAILED, error=message, warnings=[message])

    status = str(payload.get("status") or STATUS_COMPLETED)
    warnings = [str(item) for item in (payload.get("warnings") or []) if str(item).strip()]
    entries = payload.get("entries") or []

    if status == STATUS_FAILED:
        error = "；".join(warnings) if warnings else "Agent 未返回可用术语"
        return GlossaryPrepResult(
            status=STATUS_FAILED, error=error, warnings=warnings or [error]
        )

    known = existing_src_keys(existing_rows)
    rows = build_candidate_rows(entries)
    fresh = select_new_entries(rows, known)

    return GlossaryPrepResult(
        entries=fresh,
        added=len(fresh),
        scanned=len(rows),
        kept_existing=len(known),
        status=STATUS_PARTIAL if status == STATUS_PARTIAL else STATUS_COMPLETED,
        warnings=warnings,
    )


@dataclass
class PreservePrepResult:
    """禁翻预处理的产物。"""

    entries: list[dict[str, Any]] = field(default_factory=list)
    added: int = 0
    enabled: bool = False
    scanned: int = 0
    status: str = STATUS_SKIPPED
    warnings: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def changed(self) -> bool:
        return bool(self.added)

    def summary(self) -> str:
        if self.status == STATUS_SKIPPED:
            return "禁翻表准备已跳过"
        if self.status == STATUS_FAILED:
            return f"禁翻表准备失败：{self.error}"
        return f"禁翻表已更新 {self.added} 条"


def merge_preserve_entries(
    existing_entries: Sequence[Mapping[str, Any]],
    scanned_entries: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """把新扫描到的 [variable] 合并到现有禁翻表，只补新增。

    已有行完整复制：enabled / regex / 嵌套 metadata 等字段一律原样保留，
    只允许新增缺失的 src，绝不重建或丢弃既有条目。
    """
    merged: list[dict[str, Any]] = [
        dict(item)
        for item in existing_entries
        if isinstance(item, Mapping) and str(item.get("src", "") or "").strip()
    ]
    seen = {
        key
        for key in (
            LexiconOps.normalize_preserve_src(str(item.get("src", "") or ""))
            for item in merged
        )
        if key
    }

    added = 0
    for entry in scanned_entries:
        if not isinstance(entry, Mapping):
            continue
        src = str(entry.get("src", "") or "").strip()
        if not src:
            continue
        key = LexiconOps.normalize_preserve_src(src)
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append({"src": src, "comment": ""})
        added += 1
    return merged, added


def _scan_preserve(
    config: Any,
    cancel_check: Callable[[], bool] | None,
    scan_paths: Sequence[Any] | None,
) -> dict[str, Any]:
    """在限定目录内扫描 [variable]；未限定则退回 LexiconOps 默认候选。"""
    if not scan_paths:
        return LexiconOps.scan_preserve_variables(config, cancel_check)

    roots: list[Path] = []
    for raw in scan_paths:
        if raw is None:
            continue
        path = raw if isinstance(raw, Path) else Path(str(raw))
        if not path.is_dir():
            continue
        if any(part.lower() == "tl" for part in path.parts):
            continue
        roots.append(path)
    if not roots:
        # 复用已有本地化键：警告会直接展示给用户，不能夹硬编码中文。
        raise LexiconOps.LexiconOpsError(
            Localizer.get().onekey_lexicon_game_dir_unresolved
        )

    found: set[str] = set()
    scanned_root: Path | None = None
    for root in roots:
        if cancel_check is not None:
            cancel_check()
        try:
            if LexiconOps.count_source_rpy_files(root) <= 0:
                continue
        except Exception:
            continue
        scanned_root = root
        for rpy_file in root.rglob("*.rpy"):
            if cancel_check is not None:
                cancel_check()
            if "tl" in [part.lower() for part in rpy_file.parts]:
                continue
            try:
                content = rpy_file.read_text(encoding="utf-8", errors="ignore")
            except OSError as exc:
                # 只带原始路径与异常，不写死任何语言的提示文案。
                raise LexiconOps.LexiconOpsError(f"{rpy_file}: {exc}") from exc
            for var_name in LexiconOps.RE_VARIABLE_IN_TEXT.findall(content):
                found.add(f"[{var_name}]")
        break

    if scanned_root is None:
        raise LexiconOps.LexiconOpsError(
            Localizer.get().onekey_lexicon_game_dir_unresolved
        )
    if not found:
        # prepare_preserve 只消费 entries / enabled，message 一并去掉，避免硬编码文案。
        return {
            "entries": [],
            "game_path": str(scanned_root),
            "cleared": True,
            "enabled": False,
        }
    return {
        "entries": [{"src": text} for text in sorted(found)],
        "game_path": str(scanned_root),
        "cleared": False,
        "enabled": True,
    }

def prepare_preserve(
    config: Any,
    existing_entries: Sequence[Mapping[str, Any]],
    *,
    cancel_check: Callable[[], bool] | None = None,
    enabled: bool = True,
    scan_paths: Sequence[Any] | None = None,
) -> PreservePrepResult:
    """扫描 [variable] 并合并进禁翻表；已有条目不动，只补新增。

    scan_paths 由调用方限定扫描根（本次请求项目内的源码目录），
    避免 LexiconOps 按配置里的旧路径回退到别的项目；为空时退回默认候选。
    """
    if not enabled:
        return PreservePrepResult(status=STATUS_SKIPPED)

    try:
        result = _scan_preserve(config, cancel_check, scan_paths)
    except InterruptedError:
        raise
    except Exception as exc:
        return PreservePrepResult(status=STATUS_FAILED, error=str(exc), warnings=[str(exc)])

    scanned_entries = list(result.get("entries", []) or [])
    merged, added = merge_preserve_entries(existing_entries, scanned_entries)

    return PreservePrepResult(
        entries=merged,
        added=added,
        enabled=bool(result.get("enabled", True)) or bool(merged),
        scanned=len(scanned_entries),
        status=STATUS_COMPLETED,
    )


__all__ = [
    "GlossaryPrepResult",
    "PreservePrepResult",
    "STATUS_COMPLETED",
    "STATUS_FAILED",
    "STATUS_PARTIAL",
    "STATUS_SKIPPED",
    "build_candidate_rows",
    "existing_src_keys",
    "merge_preserve_entries",
    "normalize_src",
    "prepare_glossary",
    "prepare_preserve",
    "select_new_entries",
]
