"""平行校对台：读取真实缓存、带版本校验的译文编辑与纯文本批量替换。"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from contextlib import contextmanager
from typing import Iterator

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from base.Base import Base
from module.Cache.CacheItem import CacheItem
from module.Cache.CacheManager import CacheManager
from module.Engine.Engine import Engine
from module.Renpy.ProjectPaths import translation_output_candidates

router = APIRouter(prefix="/api/proofreading", tags=["proofreading"])


class RowReference(BaseModel):
    id: int = Field(ge=0)
    version: str = Field(min_length=64, max_length=64)


class EditRequest(BaseModel):
    cache_token: str = Field(min_length=64, max_length=64)
    row: RowReference
    dst: str = Field(max_length=100000)


class ReplaceRequest(BaseModel):
    cache_token: str = Field(min_length=64, max_length=64)
    rows: list[RowReference] = Field(min_length=1, max_length=100)
    find: str = Field(min_length=1, max_length=2000)
    replace: str = Field(max_length=10000)
    case_sensitive: bool = True


def _key(path: str) -> str:
    return os.path.normcase(os.path.abspath(path)) if path else ""


def _cache_token(config, output: str) -> str:
    # 令牌绑定项目身份及输入/输出配置，不能拿旧页面的索引修改新项目。
    paths = [_key(str(getattr(config, name, "") or "")) for name in (
        "renpy_project_path", "renpy_game_folder", "renpy_tl_folder", "input_folder", "output_folder",
    )]
    return hashlib.sha256(json.dumps([*paths, _key(output)]).encode("utf-8")).hexdigest()


def _version(item: CacheItem) -> str:
    payload = json.dumps(item.asdict(), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_cache(config) -> tuple[str, CacheManager]:
    empty_cache = None
    candidates = translation_output_candidates(config)
    for candidate in candidates:
        manager = CacheManager(service=False)
        try:
            manager.load_from_file(str(candidate), strict=True)
        except Exception:
            continue
        if any(item.get_src().strip() for item in manager.get_items()):
            return str(candidate), manager
        if empty_cache is None:
            empty_cache = (str(candidate), manager)
    if empty_cache is not None:
        return empty_cache
    raise HTTPException(status_code=404, detail="没有可读取的完整翻译缓存，请先完成一次翻译。")


def _row(index: int, item: CacheItem) -> dict:
    return {
        "id": index, "version": _version(item), "src": item.get_src(), "dst": item.get_dst(),
        "status": str(item.get_status()), "file_path": item.get_file_path(), "row": item.get_row(),
    }


def _readonly() -> bool:
    engine = Engine.get()
    return engine.get_status() != Engine.Status.IDLE or engine.has_stop_barrier() or engine.has_single_tasks()


@router.get("")
def read_rows(
    request: Request,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    query: str = Query(default="", max_length=2000),
    status: str = Query(default="", max_length=32),
    file_path: str = Query(default="", max_length=2048),
) -> dict:
    """分页返回原译对照。搜索同时匹配原文、译文及相对文件路径。"""
    if status and status not in Base.ITEM_VALID_STATUSES:
        raise HTTPException(status_code=400, detail="未知条目状态")
    config = copy.deepcopy(request.app.state.config)
    with CacheManager.LOCK:
        output, manager = _load_cache(config)
        items = manager.get_items()
        visible = [(index, item) for index, item in enumerate(items) if item.get_src().strip()]
        needle = query.casefold().strip()
        matches = [
            (index, item) for index, item in visible
            if (not status or item.get_status() == status)
            and (not file_path or item.get_file_path() == file_path)
            and (not needle or needle in "\n".join((item.get_src(), item.get_dst(), item.get_file_path())).casefold())
        ]
        page = min(page, max(1, (len(matches) + limit - 1) // limit))
        # ponytail: 每次读取完整缓存后只返回一页；大缓存成为瓶颈时再给 CacheDB 增加分页查询。
        return {
            "cache_token": _cache_token(config, output), "cache_folder": output,
            "total": len(visible), "matched": len(matches), "page": page, "limit": limit,
            "files": sorted({item.get_file_path() for _, item in visible}),
            "readonly": _readonly(),
            "items": [_row(index, item) for index, item in matches[(page - 1) * limit:page * limit]],
        }


@contextmanager
def _write_access(request: Request, token: str) -> Iterator[tuple[str, CacheManager]]:
    engine = Engine.get()
    # 原子占用现有引擎状态，翻译/质量任务无法在校对落盘中途启动。
    if not engine.try_set_status(Engine.Status.IDLE, Engine.Status.AGENT):
        raise HTTPException(status_code=409, detail="任务正在运行或停止收尾，校对台暂时只读。")
    try:
        config = copy.deepcopy(request.app.state.config)
        with CacheManager.LOCK:
            output, manager = _load_cache(config)
            if token != _cache_token(config, output):
                raise HTTPException(status_code=409, detail="项目或缓存目录已切换，请刷新后再保存。")
            runtime = _runtime_cache(output)
            if runtime is not None and runtime.require_flag:
                # 先完成本来就待保存的翻译结果，再核对版本；不能用磁盘旧译文覆盖它。
                try:
                    runtime.save_to_file(runtime.get_project(), runtime.get_items(), output, strict=True)
                    manager.load_from_file(output, strict=True)
                except Exception as exc:
                    raise HTTPException(status_code=500, detail=f"翻译结果待保存，请稍后重试：{exc}") from exc
            yield output, manager
    finally:
        engine.release_status(Engine.Status.AGENT)


def _targets(manager: CacheManager, references: list[RowReference]) -> list[tuple[int, CacheItem]]:
    items = manager.get_items()
    result = []
    seen = set()
    for ref in references:
        if ref.id in seen:
            continue
        if ref.id >= len(items) or _version(items[ref.id]) != ref.version:
            raise HTTPException(status_code=409, detail="译文或缓存条目已更新，请刷新后再编辑。")
        seen.add(ref.id)
        result.append((ref.id, items[ref.id]))
    return result


def _set_translation(item: CacheItem, dst: str) -> None:
    item.set_dst(dst)
    if dst and item.get_status() == Base.TranslationStatus.UNTRANSLATED:
        item.set_status(Base.TranslationStatus.TRANSLATED)


def _runtime_cache(output: str):
    translator = getattr(Engine.get(), "translator", None)
    runtime = getattr(translator, "cache_manager", None)
    runtime_output = str(getattr(translator, "_active_cache_output_folder", "") or getattr(translator, "_last_runtime_output_folder", "") or "")
    return runtime if runtime is not None and _key(runtime_output) == _key(output) else None


def _save(request: Request, output: str, manager: CacheManager, token: str) -> None:
    if token != _cache_token(request.app.state.config, output):
        raise HTTPException(status_code=409, detail="项目配置已变化，本次编辑未保存，请重新载入。")
    try:
        saved = manager.save_to_file(manager.get_project(), manager.get_items(), output, strict=True)
        if saved is not True:
            raise RuntimeError("未确认缓存保存成功")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"译文保存失败：{exc}") from exc
    # 停止后的翻译器仍有自动保存缓存。同步同一项目的内存，避免旧快照覆盖刚保存的译文。
    runtime = _runtime_cache(output)
    if runtime is not None:
        runtime.set_project(manager.get_project())
        runtime.set_items(manager.get_items())
        runtime.require_flag = False


@router.patch("/item")
def edit_item(request: Request, body: EditRequest) -> dict:
    """校验行版本后立即将译文保存到当前项目缓存。"""
    with _write_access(request, body.cache_token) as (output, manager):
        index, item = _targets(manager, [body.row])[0]
        _set_translation(item, body.dst)
        _save(request, output, manager, body.cache_token)
        return {"ok": True, "item": _row(index, item)}


@router.post("/replace")
def replace_rows(request: Request, body: ReplaceRequest) -> dict:
    """对当前页或所选行做纯文本替换；任一版本冲突时整批不写入。"""
    pattern = re.compile(re.escape(body.find), flags=0 if body.case_sensitive else re.IGNORECASE)
    with _write_access(request, body.cache_token) as (output, manager):
        targets = _targets(manager, body.rows)
        changed = 0
        for _, item in targets:
            dst = pattern.sub(lambda _: body.replace, item.get_dst())
            if dst != item.get_dst():
                _set_translation(item, dst)
                changed += 1
        if changed:
            _save(request, output, manager, body.cache_token)
        return {"ok": True, "changed": changed}
