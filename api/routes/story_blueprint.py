"""剧情蓝图接口：按章节返回全部 label、真实翻译进度与控制流。

只读接口，不写任何文件；数据由 `module/Story/BlueprintScanner.py` 扫描得到，
画面由 `/asset` 按 game 相对路径回源（安全规则与校对页的 asset 接口一致）。
"""

from __future__ import annotations

import copy
import threading
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from module.Localizer.Localizer import Localizer
from module.Renpy.ProjectPaths import RenpyProjectPaths
from module.Story.BlueprintScanner import read_label, scan
from module.Story.TranslationIndex import TranslationIndex

router = APIRouter(prefix = "/api/story-blueprint", tags = ["story-blueprint"])

# Windows 自带 mimetypes 不认 webp/avif，显式给一份，别让浏览器当成附件下载。
_ASSET_MEDIA_TYPES = {
    ".webp": "image/webp",
    ".avif": "image/avif",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
}
_ASSET_SUFFIXES = frozenset(_ASSET_MEDIA_TYPES)

# 整份扫描要 5 秒上下（1000+ label、4 万多 tl 块）。页面进进出出时没必要重扫，
# 同工程 30 秒内直接复用；换了工程、缓存变了都会因为 key 不同而失效。
_SCAN_LOCK = threading.Lock()
_SCAN_MEMO: dict[tuple, tuple[float, dict]] = {}
_SCAN_TTL = 30.0


def _context(request: Request) -> tuple[object, RenpyProjectPaths]:
    config = copy.deepcopy(request.app.state.config)
    paths = RenpyProjectPaths.from_config(config)
    if paths is None:
        raise HTTPException(status_code = 409, detail = Localizer.get().story_blueprint_no_project)
    return config, paths


def _paths_or_409(request: Request) -> RenpyProjectPaths:
    return _context(request)[1]


@router.get("")
def read_blueprint(request: Request) -> dict:
    """整份剧情蓝图：章节、label 节点、连线与真实翻译进度。

    进度以应用翻译缓存为准（游戏里实际显示的译文），缓存缺失时退回 tl 文件口径。
    """
    config, paths = _context(request)
    language = str(paths.language or "chinese")
    tl_dir = paths.tl_language_dir
    if tl_dir is None:
        tl_dir = Path(paths.game_dir) / "tl" / language
    translations, cache_path = TranslationIndex.from_cache(config)
    key = (str(paths.game_dir), str(tl_dir), language, cache_path)
    with _SCAN_LOCK:
        cached = _SCAN_MEMO.get(key)
        result = cached[1] if cached is not None and time.monotonic() - cached[0] < _SCAN_TTL else None
    if result is None:
        try:
            result = scan(Path(paths.game_dir), Path(tl_dir), language, translations)
        except Exception as error:  # noqa: BLE001 - 扫描失败要原样告诉前端原因
            detail = Localizer.get().story_blueprint_scan_failed.format(error = error)
            raise HTTPException(status_code = 500, detail = detail) from error
        with _SCAN_LOCK:
            _SCAN_MEMO[key] = (time.monotonic(), result)
    return {
        "ok": True,
        "project": {
            "project_key": paths.project_key,
            "game_dir": str(paths.game_dir),
            "tl_dir": str(tl_dir),
            "language": language,
            "cache": cache_path,
        },
        **result,
    }


@router.get("/label")
def read_label_detail(
    request: Request,
    chapter: str = Query(min_length = 1, max_length = 300),
    label_id: str = Query(alias = "id", min_length = 1, max_length = 200),
) -> dict:
    """一个 label 的逐行明细：行号、说话人、原文、缓存译文与状态。"""
    config, paths = _context(request)
    translations, _ = TranslationIndex.from_cache(config)
    node = read_label(Path(paths.game_dir), chapter, label_id, translations)
    if node is None:
        raise HTTPException(status_code = 404, detail = Localizer.get().story_blueprint_label_missing)
    return {"ok": True, **node}


@router.get("/readiness")
def read_readiness(request: Request) -> dict:
    """项目体检：剧情蓝图能不能出图，卡在哪一步，以及下一步该做什么。

    扫描器只认 `game/**/*.rpy`，所以三类前提缺一不可：绑工程、有解包后的
    game 目录、game 里有 .rpy。`.rpa` 打包的游戏必须先解包，否则扫出来是空的
    —— 这里显式把「有 rpa 但没有 rpy」判成 packed，前端才能给出正确引导。
    """
    config = copy.deepcopy(request.app.state.config)
    paths = RenpyProjectPaths.from_config(config)
    if paths is None:
        return {
            "ok": True,
            "stage": "unbound",
            "game_dir": "",
            "rpy_files": 0,
            "rpa_files": 0,
            "has_tl": False,
            "has_cache": False,
            "language": "",
        }

    game_dir = Path(paths.game_dir)
    rpy_files = 0
    if game_dir.is_dir():
        for path in game_dir.rglob("*.rpy"):
            head = path.relative_to(game_dir).parts[0].lower() if path.relative_to(game_dir).parts else ""
            if head in {"tl", "cache"}:
                continue
            rpy_files += 1
    rpa_files = len(list(game_dir.glob("*.rpa"))) if game_dir.is_dir() else 0
    language = str(paths.language or "chinese")
    tl_dir = paths.tl_language_dir or (game_dir / "tl" / language)
    _, cache_path = TranslationIndex.from_cache(config)

    if not game_dir.is_dir():
        stage = "no_game"
    elif rpy_files > 0:
        stage = "ready"
    elif rpa_files > 0:
        stage = "packed"
    else:
        stage = "no_script"

    return {
        "ok": True,
        "stage": stage,
        "game_dir": str(game_dir),
        "rpy_files": rpy_files,
        "rpa_files": rpa_files,
        "has_tl": Path(tl_dir).is_dir(),
        "has_cache": bool(cache_path),
        "language": language,
    }


@router.get("/asset")
def read_asset(
    request: Request,
    path: str = Query(min_length = 1, max_length = 600),
) -> FileResponse:
    """按 game/ 下的相对路径回源图或视频；路径必须落在工程 game 目录内。"""
    paths = _paths_or_409(request)
    game = Path(paths.game_dir).resolve()
    raw = str(path or "").replace("\\", "/").lstrip("/")
    if not raw or ".." in raw.split("/"):
        raise HTTPException(status_code = 400, detail = Localizer.get().story_blueprint_asset_path_invalid)
    target = (game / raw).resolve()
    try:
        target.relative_to(game)
    except ValueError as error:
        raise HTTPException(
            status_code = 403,
            detail = Localizer.get().story_blueprint_asset_outside,
        ) from error
    if target.suffix.lower() not in _ASSET_SUFFIXES:
        raise HTTPException(status_code = 403, detail = Localizer.get().story_blueprint_asset_type)
    if not target.is_file():
        raise HTTPException(status_code = 404, detail = Localizer.get().story_blueprint_asset_missing)
    return FileResponse(
        str(target),
        media_type = _ASSET_MEDIA_TYPES.get(target.suffix.lower()),
        headers = {"Cache-Control": "public, max-age=3600"},
    )
