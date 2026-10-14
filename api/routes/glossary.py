"""术语表 / 替换规则 / 文本保护。

M1 把 Qt 从 module/TableManager.py 里拆掉了，这里直接消费纯数据层：
Electron 侧拿到的是 JSON 行，渲染由 React 虚拟表格负责。
"""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Request

from api.schemas import (
    GlossaryLoadRequest,
    GlossaryRows,
    GlossarySaveRequest,
    GlossarySearchRequest,
    GlossarySyncRequest,
    TableKind,
)
from base.AppPaths import get_app_paths
from base.Base import Base
from base.EventManager import EventManager
from module.TableManager import TableManager

router = APIRouter(prefix="/api/glossary", tags = ["glossary"])


def _manager(kind: TableKind, rows: list[dict] | None = None) -> TableManager:
    return TableManager(kind.value, rows if rows is not None else [])


def _emit_refresh() -> None:
    EventManager.get().emit(Base.Event.GLOSSARY_REFRESH, {})


@router.post("/load", response_model = GlossaryRows)
def load(request: Request, body: GlossaryLoadRequest) -> GlossaryRows:
    path = body.path
    if not os.path.isfile(path):
        raise HTTPException(status_code = 404, detail = f"文件不存在：{path}")

    manager = _manager(body.kind)
    lowered = path.lower()

    if lowered.endswith(".json"):
        rows = manager.load_from_json_file(path)
    elif lowered.endswith(".xlsx"):
        rows = manager.load_from_xlsx_file(path)
    else:
        raise HTTPException(status_code = 400, detail = "仅支持 .json / .xlsx")

    return GlossaryRows(kind = body.kind, rows = rows, total = len(rows))


@router.post("/sync", response_model = GlossaryRows)
def sync(request: Request, body: GlossarySyncRequest) -> GlossaryRows:
    """按 src 去重（保留译文更全的那条）。"""
    manager = _manager(body.kind, list(body.rows))
    manager.sync()

    _emit_refresh()

    return GlossaryRows(kind = body.kind, rows = manager.get_data(), total = len(manager.get_data()))


@router.post("/search")
def search(request: Request, body: GlossarySearchRequest) -> dict:
    manager = _manager(body.kind, list(body.rows))
    index = manager.search(body.keyword, body.start)

    return {"index": index, "total": len(body.rows)}


@router.post("/save", response_model = GlossaryRows)
def save(request: Request, body: GlossarySaveRequest) -> GlossaryRows:
    manager = _manager(body.kind, list(body.rows))
    manager.sync()

    target = body.path or str(get_app_paths().output_path / body.kind.value.lower())
    base = os.path.splitext(target)[0]

    if body.format in ("xlsx", "both"):
        manager.export(base)  # export 同时写 xlsx 与 json

    _emit_refresh()

    return GlossaryRows(kind = body.kind, rows = manager.get_data(), total = len(manager.get_data()))