"""RPY 抽取设置：复用 RuleStore / RuleScan，按分类隔离绑定；预览走协作取消 Job。"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import os
import time
from pathlib import Path
from typing import Any, Callable, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from api.jobs import Job
from module.Cache.CacheManager import CacheManager
from module.Engine.Engine import Engine
from module.Extract.GameExtractionRules import (
    RuleError,
    RuleScan,
    RuleStore,
    binding_key,
    new_profile,
    new_rule,
    project_key,
    validate_profile,
)
from module.Extract.RpyExtractionSettings import context_for_path, starter_profile

router = APIRouter(prefix="/api/rpy-extraction", tags=["rpy-extraction"])

KIND_PREVIEW = "rpy_preview"
KIND_SAVE = "rpy_save"
KINDS = (KIND_PREVIEW, KIND_SAVE)
_BUSY = "已有任务正在运行或收尾，请稍后再试"
_PAGE_SIZE = 200
_MODE_LABELS = {
    "builtin": "只用内置",
    "combined": "内置＋自定义",
    "custom": "仅自定义",
}
_NO_PROFILE = "未选择自定义方案"


class ContextBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_key: str = ""
    path: str = ""
    category: Literal["source", "tl"] = "source"
    language: str = "chinese"


class SelectBody(ContextBody):
    mode: Literal["builtin", "combined", "custom"] = "builtin"
    profile_id: str | None = None


class ProfileBody(ContextBody):
    profile: dict[str, Any] = Field(default_factory=dict)
    starter: bool = False


class ProfileIdBody(ContextBody):
    profile_id: str = ""


class PreviewBody(ContextBody):
    profile: dict[str, Any] = Field(default_factory=dict)


class SaveBody(ContextBody):
    profile: dict[str, Any] = Field(default_factory=dict)


def _store(request: Request) -> RuleStore:
    """测试可把 app.state.rpy_rule_store_path 指到 tmp，避免写真实 storage。"""
    override = getattr(request.app.state, "rpy_rule_store_path", None)
    return RuleStore(Path(override)) if override is not None else RuleStore()


def _sessions(request: Request) -> dict[str, dict[str, Any]]:
    sessions = getattr(request.app.state, "rpy_scan_sessions", None)
    if sessions is None:
        sessions = {}
        request.app.state.rpy_scan_sessions = sessions
    return sessions


def _http(exc: Exception, status_code: int = 400) -> HTTPException:
    if isinstance(exc, RuleError):
        detail = f"game_rules_error_{exc.code}"
        if exc.detail:
            detail = f"{detail}: {exc.detail}"
        return HTTPException(status_code=status_code, detail=detail)
    return HTTPException(status_code=status_code, detail=str(exc))


def _default_path(config: Any) -> str:
    for attr in ("renpy_game_folder", "renpy_project_path", "input_folder"):
        value = str(getattr(config, attr, "") or "").strip()
        if value:
            return value
    return ""


def _resolve_context(config: Any, path: str, category: str, language: str) -> tuple[Path, Path, str]:
    text = str(path or "").strip() or _default_path(config)
    if not text:
        raise RuleError("project")
    root, base = context_for_path(text, category, language or "chinese")
    return root, base, project_key(root)


def _owner_identity(config: Any) -> str:
    """当前配置所属项目 owner（可与手动 target 不同）；空串表示未绑定。"""
    text = ""
    for attr in ("renpy_project_path", "renpy_game_folder"):
        text = str(getattr(config, attr, "") or "").strip()
        if text:
            break
    if not text:
        return ""
    try:
        root, _, key = _resolve_context(config, text, "source", "chinese")
        return key
    except Exception:
        return os.path.normcase(text).replace("\\", "/")


def _match_key(body_key: str, resolved_key: str) -> str:
    if not str(body_key or "").strip():
        raise HTTPException(status_code=400, detail="project_key 必填")
    if body_key != resolved_key:
        raise HTTPException(status_code=409, detail="项目已切换，请重新加载后再操作")
    return resolved_key


def _require_idle_engine() -> None:
    """同步写接口与后台 Job / 单条重译互斥；忙碌时 409，不改规则库。"""
    if Engine.get().is_rules_locked():
        raise HTTPException(status_code=409, detail=_BUSY)


def _acquire_engine() -> Engine:
    engine = Engine.get()
    if engine.has_stop_barrier() or not engine.try_set_status(Engine.Status.IDLE, Engine.Status.TESTING):
        raise HTTPException(status_code=409, detail=_BUSY)
    return engine


def _session_key(root: Path, category: str, base: Path, language: str) -> str:
    """预览会话按 root+category+base+language 隔离；分类绑定配置仍沿 Qt binding_key。"""
    base_norm = os.path.normcase(str(Path(base).resolve())).replace("\\", "/")
    return f"{binding_key(root, category)}::{base_norm}::{language or 'chinese'}"


def _get_session(
    request: Request,
    root: Path,
    category: str,
    base: Path,
    language: str,
) -> dict[str, Any] | None:
    return _sessions(request).get(_session_key(root, category, base, language or "chinese"))


def _set_session(
    request: Request,
    root: Path,
    category: str,
    base: Path,
    language: str,
    payload: dict[str, Any] | None,
) -> None:
    key = _session_key(root, category, base, language or "chinese")
    sessions = _sessions(request)
    if payload is None:
        sessions.pop(key, None)
    else:
        sessions[key] = payload


def _clear_category_sessions(request: Request, root: Path, category: str) -> None:
    """分类下任意语言/base 的旧会话全部失效（编辑草稿后）。"""
    prefix = binding_key(root, category) + "::"
    sessions = _sessions(request)
    for key in [k for k in sessions if k.startswith(prefix) or k == binding_key(root, category)]:
        sessions.pop(key, None)


def _latest_job(
    request: Request,
    project_key_value: str,
    category: str,
    *,
    language: str | None = None,
    base: str | None = None,
) -> Job | None:
    return next(
        (
            job for job in request.app.state.jobs.list()
            if job.kind in KINDS and isinstance(job.result, dict)
            and job.result.get("project_key") == project_key_value
            and job.result.get("category") == category
            and (language is None or job.result.get("language") == language)
            and (base is None or job.result.get("base") == base)
        ),
        None,
    )


def _profile_summary(profile: dict | None) -> dict | None:
    if not profile:
        return None
    enabled = sum(1 for rule in profile.get("rules", []) if rule.get("enabled"))
    return {
        "id": profile["id"],
        "name": profile.get("name") or "",
        "note": profile.get("note") or "",
        "category": profile.get("category", "source"),
        "rule_count": len(profile.get("rules") or []),
        "enabled_count": enabled,
    }


def _mode_label(mode: str) -> str:
    return _MODE_LABELS.get(mode, mode)


def _selection_label(mode: str, name: str) -> str:
    return f"当前已生效：{_mode_label(mode)} · {name}"


def _pending_label(mode: str, name: str) -> str:
    return f"未保存：{_mode_label(mode)} · {name}（点「应用设置」后生效）"


def _public_profile(profile: dict) -> dict:
    return copy.deepcopy(profile)


def _new_rule_template(category: str) -> dict:
    """与 Qt _add_rule 一致：TL 取 starter old 模板，源码取 new_rule。"""
    if category == "tl":
        rule = copy.deepcopy(starter_profile("tl")["rules"][0])
    else:
        rule = new_rule()
    rule["enabled"] = True
    return rule


def _aligned_profile(body_category: str, profile: dict, store: RuleStore | None = None) -> dict:
    """拒绝 body/profile/已存 id 跨类别不一致；不强制改写掩盖错误。"""
    if not profile:
        raise RuleError("schema")
    out = copy.deepcopy(profile)
    profile_cat = out.get("category", body_category)
    if profile_cat != body_category:
        raise RuleError("binding")
    out["category"] = body_category
    if store is not None and out.get("id"):
        data = store.load()
        existing = next((p for p in data["profiles"] if p["id"] == out["id"]), None)
        if existing is not None and existing.get("category", "source") != body_category:
            raise RuleError("binding")
    validate_profile(out)
    return out


def _scan_payload(
    scan: RuleScan | None,
    covered: set[str],
    declined: set[str],
    profile: dict,
    *,
    page: int = 1,
) -> dict:
    if scan is None:
        return {
            "has_scan": False,
            "completed": False,
            "error": "",
            "files_read": 0,
            "raw_matches": 0,
            "filtered": 0,
            "candidates": [],
            "candidate_total": 0,
            "page": 1,
            "page_size": _PAGE_SIZE,
            "page_count": 1,
            "diagnostics": [],
            "can_save_bind": False,
            "can_continue": False,
        }
    names = {rule["id"]: rule.get("name") or "" for rule in profile.get("rules", [])}
    texts = {c.text for c in scan.candidates}
    entries = [
        {
            "path": c.path,
            "line": c.line,
            "text": c.text,
            "rule_id": c.rule_id,
            "rule_name": names.get(c.rule_id, ""),
            "state": "declined" if c.text in declined else "covered" if c.text in covered else "new",
        }
        for c in scan.candidates
    ]
    entries += [
        {"path": path, "line": line, "text": "", "rule_id": "", "rule_name": "", "state": reason}
        for path, line, reason in scan.diagnostics
    ]
    total = len(entries)
    page_count = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE) if total else 1
    current = max(1, min(int(page or 1), page_count))
    start = (current - 1) * _PAGE_SIZE
    return {
        "has_scan": True,
        "completed": bool(scan.completed),
        "error": scan.error or "",
        "files_read": scan.files_read,
        "raw_matches": scan.raw_matches,
        "filtered": scan.filtered,
        "valid": len(texts),
        "covered": len(texts & covered),
        "new": len(texts - covered - declined),
        "candidates": entries[start:start + _PAGE_SIZE],
        "candidate_total": total,
        "page": current,
        "page_size": _PAGE_SIZE,
        "page_count": page_count,
        "diagnostics": [{"path": p, "line": n, "reason": r} for p, n, r in scan.diagnostics[:50]],
        "can_save_bind": bool(scan.completed and not scan.error),
        "can_continue": bool(not scan.completed and not scan.error),
    }


def _preview_extras(root: Path, language: str, category: str, cancel: Callable[[], bool]) -> tuple[set[str], set[str]]:
    if category == "tl":
        return set(), set()
    from module.Extract.ReplaceGenerator import load_declined_candidates
    from module.Extract.UnifiedExtractor import UnifiedExtractor

    extractor = UnifiedExtractor()
    extractor.set_cancel_callback(cancel)
    tl = root / "game" / "tl" / language
    covered = extractor._get_string_originals(tl)
    covered.update(extractor._collect_base_box_old_values(tl))
    covered.update(extractor._collect_source_registered_old_values(root, language))
    return covered, load_declined_candidates(root, language)


def _status_payload(
    request: Request,
    *,
    root: Path,
    base: Path,
    category: str,
    language: str,
    resolved_key: str,
    path: str,
    page: int = 1,
) -> dict:
    store = _store(request)
    data = store.load()
    mode, selected = store.selection(root, category)
    category_profiles = [
        p for p in data["profiles"]
        if p.get("category", "source") == category
    ]
    profiles = [_profile_summary(p) for p in category_profiles]
    applied_name = selected["name"] if selected else _NO_PROFILE
    session = _get_session(request, root, category, base, language)
    scan_info = _scan_payload(
        session.get("scan") if session else None,
        session.get("covered", set()) if session else set(),
        session.get("declined", set()) if session else set(),
        session.get("profile") if session else (selected or {}),
        page=page,
    )
    job = _latest_job(
        request,
        resolved_key,
        category,
        language=language,
        base=str(base),
    )
    return {
        "project_key": resolved_key,
        "path": path,
        "root": str(root),
        "base": str(base),
        "category": category,
        "language": language,
        "mode": mode,
        "applied_mode": mode,
        "applied_profile_id": selected["id"] if selected else None,
        "applied_name": applied_name,
        "profile": _public_profile(selected) if selected else None,
        "profile_summary": _profile_summary(selected),
        "profiles": profiles,
        "profile_docs": [_public_profile(p) for p in category_profiles],
        "new_rule_template": _public_profile(_new_rule_template(category)),
        "summary": _selection_label(mode, applied_name),
        "pending_summary_template": "未保存：{mode} · {name}（点「应用设置」后生效）",
        "mode_labels": dict(_MODE_LABELS),
        "no_profile_label": _NO_PROFILE,
        "scan": scan_info,
        "job": job.snapshot() if job else None,
        "dirty": False,
        "pending_mode": mode,
        "pending_profile_id": selected["id"] if selected else None,
        "pending_name": applied_name,
    }


@router.get("")
def read_status(
    request: Request,
    path: str = Query(default=""),
    category: Literal["source", "tl"] = Query(default="source"),
    language: str = Query(default="chinese"),
    page: int = Query(default=1, ge=1),
    pending_mode: str | None = Query(default=None),
    pending_profile_id: str | None = Query(default=None),
) -> dict:
    """返回路径+分类+语言下的生效方案、方案列表与预览会话摘要（候选按页 200）。"""
    with CacheManager.LOCK:
        try:
            root, base, key = _resolve_context(request.app.state.config, path, category, language)
            payload = _status_payload(
                request,
                root=root,
                base=base,
                category=category,
                language=language or "chinese",
                resolved_key=key,
                path=str(path or _default_path(request.app.state.config)),
                page=page,
            )
        except RuleError as exc:
            raise _http(exc) from exc
        except Exception as exc:
            raise _http(exc) from exc

    if pending_mode is not None or pending_profile_id is not None:
        mode = pending_mode or payload["applied_mode"]
        profile_id = pending_profile_id if pending_profile_id is not None else payload["applied_profile_id"]
        name = next(
            (p["name"] for p in payload["profiles"] if p["id"] == profile_id),
            _NO_PROFILE,
        )
        dirty = (mode, profile_id) != (payload["applied_mode"], payload["applied_profile_id"])
        payload["pending_mode"] = mode
        payload["pending_profile_id"] = profile_id
        payload["pending_name"] = name
        payload["dirty"] = dirty
        payload["summary"] = (
            _pending_label(mode, name) if dirty else _selection_label(payload["applied_mode"], payload["applied_name"])
        )
    else:
        payload["dirty"] = False
        payload["pending_mode"] = payload["applied_mode"]
        payload["pending_profile_id"] = payload["applied_profile_id"]
        payload["pending_name"] = payload["applied_name"]
    return payload


@router.post("/select")
def apply_select(request: Request, body: SelectBody) -> dict:
    """显式应用抽取方式与方案绑定；与编辑器未保存草稿无关。"""
    with CacheManager.LOCK:
        _require_idle_engine()
        try:
            root, base, key = _resolve_context(request.app.state.config, body.path, body.category, body.language)
            _match_key(body.project_key, key)
            store = _store(request)
            if body.mode != "builtin" and not body.profile_id:
                raise RuleError("binding")
            if body.mode == "custom":
                data = store.load()
                profile = next((p for p in data["profiles"] if p["id"] == body.profile_id), None)
                if profile is None or profile.get("category", "source") != body.category:
                    raise RuleError("binding")
                if not any(r["enabled"] for r in profile["rules"]):
                    raise RuleError("empty_custom")
            store.select(root, body.category, body.mode, body.profile_id)
            return _status_payload(
                request,
                root=root,
                base=base,
                category=body.category,
                language=body.language or "chinese",
                resolved_key=key,
                path=body.path or _default_path(request.app.state.config),
            )
        except RuleError as exc:
            raise _http(exc) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise _http(exc) from exc


@router.post("/profiles")
def create_profile(request: Request, body: ProfileBody) -> dict:
    """新建/复制内置/克隆：仅返回编辑稿，关闭未保存不落盘（对齐 Qt）。"""
    with CacheManager.LOCK:
        _require_idle_engine()
        try:
            root, base, key = _resolve_context(request.app.state.config, body.path, body.category, body.language)
            _match_key(body.project_key, key)
            if body.starter:
                profile = starter_profile(body.category)
            elif body.profile:
                profile = copy.deepcopy(body.profile)
                # 克隆：强制新 id，类别必须与 body 一致
                profile["id"] = new_profile(body.category)["id"]
                profile["category"] = body.category
                validate_profile(profile)
                for rule in profile.get("rules", []):
                    rule["enabled"] = False
            else:
                profile = new_profile(body.category)
                profile["name"] = "当前游戏补充规则"
            payload = _status_payload(
                request,
                root=root,
                base=base,
                category=body.category,
                language=body.language or "chinese",
                resolved_key=key,
                path=body.path or _default_path(request.app.state.config),
            )
            payload["editor_profile"] = _public_profile(profile)
            return payload
        except RuleError as exc:
            raise _http(exc) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise _http(exc) from exc


@router.post("/profiles/update")
def update_profile_draft(request: Request, body: ProfileBody) -> dict:
    """更新方案正文为全部禁用草稿（不要求预览证明）。"""
    with CacheManager.LOCK:
        _require_idle_engine()
        try:
            root, base, key = _resolve_context(request.app.state.config, body.path, body.category, body.language)
            _match_key(body.project_key, key)
            store = _store(request)
            profile = _aligned_profile(body.category, body.profile, store)
            for rule in profile.get("rules", []):
                rule["enabled"] = False
            store.save(profile, root, bind=False)
            _clear_category_sessions(request, root, body.category)
            payload = _status_payload(
                request,
                root=root,
                base=base,
                category=body.category,
                language=body.language or "chinese",
                resolved_key=key,
                path=body.path or _default_path(request.app.state.config),
            )
            payload["editor_profile"] = _public_profile(profile)
            return payload
        except RuleError as exc:
            raise _http(exc) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise _http(exc) from exc


@router.post("/profiles/delete")
def delete_profile(request: Request, body: ProfileIdBody) -> dict:
    with CacheManager.LOCK:
        _require_idle_engine()
        try:
            root, base, key = _resolve_context(request.app.state.config, body.path, body.category, body.language)
            _match_key(body.project_key, key)
            if not body.profile_id:
                raise RuleError("schema")
            _store(request).delete(body.profile_id)
            _clear_category_sessions(request, root, body.category)
            return _status_payload(
                request,
                root=root,
                base=base,
                category=body.category,
                language=body.language or "chinese",
                resolved_key=key,
                path=body.path or _default_path(request.app.state.config),
            )
        except RuleError as exc:
            raise _http(exc) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise _http(exc) from exc


@router.post("/profiles/unbind")
def unbind_profile(request: Request, body: ContextBody) -> dict:
    """当前分类改回内置；方案文件保留。"""
    with CacheManager.LOCK:
        _require_idle_engine()
        try:
            root, base, key = _resolve_context(request.app.state.config, body.path, body.category, body.language)
            _match_key(body.project_key, key)
            _store(request).unbind(root, body.category)
            _clear_category_sessions(request, root, body.category)
            return _status_payload(
                request,
                root=root,
                base=base,
                category=body.category,
                language=body.language or "chinese",
                resolved_key=key,
                path=body.path or _default_path(request.app.state.config),
            )
        except RuleError as exc:
            raise _http(exc) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise _http(exc) from exc


@router.post("/preview")
async def start_preview(request: Request, body: PreviewBody) -> dict:
    """启动预览扫描 Job；会话按 base+language 隔离，失败撤销旧 can_save_bind。"""
    with CacheManager.LOCK:
        try:
            root, base, key = _resolve_context(request.app.state.config, body.path, body.category, body.language)
            _match_key(body.project_key, key)
            store = _store(request)
            profile = _aligned_profile(body.category, body.profile, store)
            root_s, base_s, language = str(root), str(base), body.language or "chinese"
            category = body.category
            owner_at_start = _owner_identity(request.app.state.config)
            # 新预览开始即清掉同上下文旧会话，避免失败后仍返回旧 can_save_bind
            _set_session(request, root, category, base, language, None)
        except RuleError as exc:
            raise _http(exc) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise _http(exc) from exc

    def compute(cancel_check: Callable[[], None]) -> dict:
        def cancel() -> bool:
            try:
                cancel_check()
            except asyncio.CancelledError:
                return True
            return False

        try:
            scan = RuleScan(Path(root_s), profile, cancel, base=Path(base_s))
            scan.advance(cancel)
            covered, declined = _preview_extras(Path(root_s), language, category, cancel)
        except Exception:
            # 预览失败：确保不留下旧 proof
            with CacheManager.LOCK:
                _set_session(request, Path(root_s), category, Path(base_s), language, None)
            raise
        with CacheManager.LOCK:
            _set_session(
                request,
                Path(root_s),
                category,
                Path(base_s),
                language,
                {
                    "scan": scan,
                    "covered": covered,
                    "declined": declined,
                    "profile": copy.deepcopy(profile),
                    "root": Path(root_s),
                    "base": Path(base_s),
                    "language": language,
                    "category": category,
                },
            )
        return {
            "action": "preview",
            "category": category,
            "language": language,
            "base": base_s,
            "message": "预览已完整完成，可以保存启用。" if scan.completed else "扫描尚未完成，请继续扫描。",
            "scan": _scan_payload(scan, covered, declined, profile, page=1),
            "written": False,
        }

    return await _start_job(
        request,
        kind=KIND_PREVIEW,
        project_key_value=key,
        category=category,
        message="正在后台检查游戏规则…",
        seed={"action": "preview", "path": body.path, "language": language, "base": base_s},
        compute=compute,
        snapshot_root=root_s,
        owner_at_start=owner_at_start,
    )


@router.post("/preview/continue")
async def continue_preview(request: Request, body: PreviewBody) -> dict:
    """在已有预览会话上继续；会话须匹配 base+language，且 profile 与冻结快照一致。"""
    with CacheManager.LOCK:
        try:
            root, base, key = _resolve_context(request.app.state.config, body.path, body.category, body.language)
            _match_key(body.project_key, key)
            language = body.language or "chinese"
            session = _get_session(request, root, body.category, base, language)
            if not session or session.get("scan") is None:
                raise HTTPException(status_code=400, detail="请先开始预览")
            if Path(session.get("base")).resolve() != base.resolve() or session.get("language") != language:
                raise HTTPException(status_code=400, detail="预览上下文已切换，请重新预览")
            profile = session["profile"]
            # 若客户端提交了当前编辑稿，必须与会话冻结 profile 一致
            if body.profile:
                submitted = _aligned_profile(body.category, body.profile)
                if submitted != profile:
                    raise RuleError("preview_required")
            scan: RuleScan = session["scan"]
            covered = session.get("covered", set())
            declined = session.get("declined", set())
            root_s, base_s, category = str(root), str(base), body.category
            owner_at_start = _owner_identity(request.app.state.config)
        except RuleError as exc:
            raise _http(exc) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise _http(exc) from exc

    def compute(cancel_check: Callable[[], None]) -> dict:
        def cancel() -> bool:
            try:
                cancel_check()
            except asyncio.CancelledError:
                return True
            return False

        scan.advance(cancel)
        extras = _preview_extras(Path(root_s), language, category, cancel)
        with CacheManager.LOCK:
            current = _get_session(request, Path(root_s), category, Path(base_s), language) or {}
            if current.get("scan") is not scan:
                raise RuntimeError("预览会话已失效，请重新预览")
            current.update({
                "scan": scan,
                "covered": extras[0],
                "declined": extras[1],
                "profile": profile,
                "base": Path(base_s),
                "language": language,
            })
            _set_session(request, Path(root_s), category, Path(base_s), language, current)
        return {
            "action": "preview_continue",
            "category": category,
            "language": language,
            "base": base_s,
            "message": "预览已完整完成，可以保存启用。" if scan.completed else "扫描尚未完成，请继续扫描。",
            "scan": _scan_payload(scan, extras[0], extras[1], profile, page=1),
            "written": False,
        }

    return await _start_job(
        request,
        kind=KIND_PREVIEW,
        project_key_value=key,
        category=category,
        message="正在继续扫描…",
        seed={"action": "preview_continue", "path": body.path, "language": language, "base": base_s},
        compute=compute,
        snapshot_root=root_s,
        owner_at_start=owner_at_start,
    )


@router.post("/save-bind")
async def save_bind(request: Request, body: SaveBody) -> dict:
    """保存并绑定到当前分类；需要同会话完整预览证明（base+language+profile）。"""
    with CacheManager.LOCK:
        try:
            root, base, key = _resolve_context(request.app.state.config, body.path, body.category, body.language)
            _match_key(body.project_key, key)
            store = _store(request)
            profile = _aligned_profile(body.category, body.profile, store)
            language = body.language or "chinese"
            session = _get_session(request, root, body.category, base, language)
            if not session or session.get("scan") is None:
                raise RuleError("preview_required")
            if Path(session.get("base")).resolve() != base.resolve() or session.get("language") != language:
                raise RuleError("preview_required")
            proof: RuleScan = session["scan"]
            if session.get("profile") != profile:
                raise RuleError("preview_required")
            root_s, base_s, category = str(root), str(base), body.category
            owner_at_start = _owner_identity(request.app.state.config)
        except RuleError as exc:
            raise _http(exc) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise _http(exc) from exc

    def compute(cancel_check: Callable[[], None]) -> dict:
        def cancel() -> bool:
            try:
                cancel_check()
            except asyncio.CancelledError:
                return True
            return False

        if cancel():
            raise RuleError("cancelled")
        # 锁外预检可提前失败；真正写库前 RuleStore.save 仍会再次 verify_sources
        if any(r.get("enabled") for r in profile.get("rules", [])):
            proof.verify_sources(cancel, time.monotonic() + 20)
        with CacheManager.LOCK:
            # 最终短临界区：cancel 钩子含 owner/target 复核；save 内再次 verify_sources
            if cancel():
                raise RuleError("cancelled")
            session = _get_session(request, Path(root_s), category, Path(base_s), language)
            if not session or session.get("scan") is not proof or session.get("profile") != profile:
                raise RuleError("preview_required")
            store = _store(request)
            store.save(profile, Path(root_s), bind=True, proof=proof, cancel=cancel)
            mode, _ = store.selection(Path(root_s), category)
            store.select(Path(root_s), category, "combined" if mode == "builtin" else mode, profile["id"])
        return {
            "action": "save_bind",
            "category": category,
            "language": language,
            "base": base_s,
            "message": "方案已保存并用于当前分类。后续任务自动加载。",
            "profile_id": profile["id"],
            "written": True,
        }

    return await _start_job(
        request,
        kind=KIND_SAVE,
        project_key_value=key,
        category=category,
        message="正在保存并绑定方案…",
        seed={"action": "save_bind", "path": body.path, "language": language, "base": base_s},
        compute=compute,
        snapshot_root=root_s,
        owner_at_start=owner_at_start,
    )


@router.post("/save-draft")
async def save_draft(request: Request, body: SaveBody) -> dict:
    """全部禁用后保存草稿，不要求预览证明；类别不一致拒绝且不写库。"""
    with CacheManager.LOCK:
        try:
            root, base, key = _resolve_context(request.app.state.config, body.path, body.category, body.language)
            _match_key(body.project_key, key)
            store = _store(request)
            profile = _aligned_profile(body.category, body.profile, store)
            for rule in profile.get("rules", []):
                rule["enabled"] = False
            root_s, base_s, category = str(root), str(base), body.category
            language = body.language or "chinese"
            owner_at_start = _owner_identity(request.app.state.config)
        except RuleError as exc:
            raise _http(exc) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise _http(exc) from exc

    def compute(cancel_check: Callable[[], None]) -> dict:
        def cancel() -> bool:
            try:
                cancel_check()
            except asyncio.CancelledError:
                return True
            return False

        if cancel():
            raise RuleError("cancelled")
        with CacheManager.LOCK:
            if cancel():
                raise RuleError("cancelled")
            _store(request).save(profile, Path(root_s), bind=False)
            _clear_category_sessions(request, Path(root_s), category)
        return {
            "action": "save_draft",
            "category": category,
            "language": language,
            "base": base_s,
            "message": "已保存全部禁用草稿，不会执行这些规则。",
            "profile_id": profile["id"],
            "written": True,
        }

    return await _start_job(
        request,
        kind=KIND_SAVE,
        project_key_value=key,
        category=category,
        message="正在保存草稿…",
        seed={"action": "save_draft", "path": body.path, "language": language, "base": base_s},
        compute=compute,
        snapshot_root=root_s,
        owner_at_start=owner_at_start,
    )


async def _start_job(
    request: Request,
    *,
    kind: str,
    project_key_value: str,
    category: str,
    message: str,
    seed: dict[str, Any],
    compute: Callable[[Callable[[], None]], dict],
    snapshot_root: str,
    owner_at_start: str,
) -> dict:
    engine = _acquire_engine()
    manager = request.app.state.jobs
    try:
        job = manager.create(kind, total=1, cooperative_cancel=True)
    except Exception:
        engine.release_status(Engine.Status.TESTING)
        raise
    job.result = {
        "project_key": project_key_value,
        "category": category,
        "message": message,
        "written": False,
        "worker_active": True,
        **seed,
    }
    loop = asyncio.get_running_loop()

    def context_still() -> bool:
        """冻结 owner（含空串）与 target root/base/category/language；任一变化即禁止写入。"""
        with CacheManager.LOCK:
            # 取消 truthiness：未绑定→绑定也必须识别
            if _owner_identity(request.app.state.config) != owner_at_start:
                return False
            try:
                root, base, key = _resolve_context(
                    request.app.state.config,
                    seed.get("path") or "",
                    category,
                    seed.get("language") or "chinese",
                )
            except Exception:
                return False
            if key != project_key_value or str(root) != snapshot_root:
                return False
            seed_base = str(seed.get("base") or "")
            if seed_base:
                try:
                    if Path(base).resolve() != Path(seed_base).resolve():
                        return False
                except Exception:
                    return False
            return True

    def check_cancel() -> None:
        if job.cancel_event.is_set():
            raise asyncio.CancelledError()
        # 写入前 / cancel 钩子统一复核上下文，避免只在 compute 开头校验
        if not context_still():
            raise RuntimeError("项目已切换，未写入")

    def run_compute() -> dict:
        check_cancel()
        try:
            result = compute(check_cancel)
        except RuleError as exc:
            raise RuntimeError(f"game_rules_error_{exc.code}" + (f": {exc.detail}" if exc.detail else "")) from exc
        if isinstance(job.result, dict) and job.result.get("worker_active"):
            job.result.update(result)
        return result

    async def worker(_: Job) -> dict:
        try:
            check_cancel()
            future = loop.run_in_executor(None, run_compute)
            try:
                result = await asyncio.shield(future)
            except asyncio.CancelledError:
                job.cancel_event.set()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await asyncio.shield(future)
                if isinstance(job.result, dict) and job.result.get("written"):
                    job.cancel_event.clear()
                    job.result["worker_active"] = False
                    manager.progress(job.id, done=1, total=1)
                    return job.result
                raise
            if isinstance(job.result, dict):
                job.result.update(result)
                if job.cancel_event.is_set() and not job.result.get("written"):
                    job.result["message"] = "任务已取消"
                    raise asyncio.CancelledError()
                if job.cancel_event.is_set() and job.result.get("written"):
                    job.cancel_event.clear()
            manager.progress(job.id, done=1, total=1)
            return job.result
        except asyncio.CancelledError:
            if isinstance(job.result, dict):
                job.result["message"] = "任务已取消"
            raise
        except Exception as exc:
            if job.cancel_event.is_set() and not (isinstance(job.result, dict) and job.result.get("written")):
                if isinstance(job.result, dict):
                    job.result["message"] = "任务已取消"
                raise asyncio.CancelledError() from exc
            if isinstance(job.result, dict):
                job.result["message"] = str(exc)
                job.result["written"] = bool(job.result.get("written"))
            raise
        finally:
            if isinstance(job.result, dict):
                job.result["worker_active"] = False
            engine.release_status(Engine.Status.TESTING)

    try:
        await manager.run(job.id, worker)
    except BaseException:
        if isinstance(job.result, dict):
            job.result["worker_active"] = False
        engine.release_status(Engine.Status.TESTING)
        raise
    return {"job": job.snapshot()}
