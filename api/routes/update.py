"""应用更新：复用 VersionManager，网页与 Electron 共用同一套检查/下载/安装。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from base.Base import Base
from base.VersionManager import VersionManager

router = APIRouter(prefix="/api/update", tags=["update"])


class UpdateCheckRequest(BaseModel):
    manual: bool = True


class UpdateActionResponse(BaseModel):
    ok: bool = True
    status: str
    version: str = ""
    latest: dict = Field(default_factory=dict)
    downloaded_size: int = 0
    total_size: int = 0
    error: str = ""
    new_version: bool = False
    release_url: str = VersionManager.RELEASE_URL
    can_install: bool = False


class ChangelogResponse(BaseModel):
    markdown: str
    empty: bool = False


def _manager(request: Request) -> VersionManager:
    manager = getattr(request.app.state, "version_manager", None)
    if manager is None:
        manager = VersionManager.get()
        request.app.state.version_manager = manager
    return manager


def _payload(manager: VersionManager) -> UpdateActionResponse:
    state = manager.get_update_state()
    latest = state.get("latest") if isinstance(state.get("latest"), dict) else {}
    tag = str(latest.get("tag_name", "") or "")
    new_version = bool(
        tag
        and VersionManager.parse_version(str(state.get("version") or manager.get_version()))
        < VersionManager.parse_version(tag)
    )
    return UpdateActionResponse(
        status=str(state.get("status") or VersionManager.Status.NONE),
        version=str(state.get("version") or manager.get_version()),
        latest=latest,
        downloaded_size=int(state.get("downloaded_size") or 0),
        total_size=int(state.get("total_size") or 0),
        error=str(state.get("error") or ""),
        new_version=new_version,
        release_url=VersionManager.RELEASE_URL,
        can_install=str(state.get("status")) == VersionManager.Status.DOWNLOADED,
    )


@router.get("", response_model=UpdateActionResponse)
def get_update_state(request: Request) -> UpdateActionResponse:
    return _payload(_manager(request))


@router.post("/check", response_model=UpdateActionResponse)
def check_update(request: Request, body: UpdateCheckRequest | None = None) -> UpdateActionResponse:
    manager = _manager(request)
    manual = True if body is None else body.manual
    manager.emit(Base.Event.APP_UPDATE_CHECK_START, {"manual": manual})
    return _payload(manager)


@router.post("/download", response_model=UpdateActionResponse)
def download_update(request: Request) -> UpdateActionResponse:
    manager = _manager(request)
    state = manager.get_update_state()
    status = str(state.get("status") or "")
    if status == VersionManager.Status.UPDATING:
        raise HTTPException(status_code=409, detail="正在下载更新")
    if status == VersionManager.Status.DOWNLOADED:
        return _payload(manager)
    latest = state.get("latest") if isinstance(state.get("latest"), dict) else {}
    if not latest:
        raise HTTPException(status_code=400, detail="请先检查更新")
    manager.emit(Base.Event.APP_UPDATE_DOWNLOAD_START, {})
    return _payload(manager)


@router.post("/cancel", response_model=UpdateActionResponse)
def cancel_download(request: Request) -> UpdateActionResponse:
    manager = _manager(request)
    if not manager.cancel_download():
        raise HTTPException(status_code=409, detail="当前没有进行中的下载")
    manager.emit(Base.Event.APP_UPDATE_DOWNLOAD_CANCEL, {})
    return _payload(manager)


@router.post("/install", response_model=UpdateActionResponse)
def install_update(request: Request) -> UpdateActionResponse:
    manager = _manager(request)
    state = manager.get_update_state()
    if str(state.get("status") or "") != VersionManager.Status.DOWNLOADED:
        raise HTTPException(status_code=409, detail="尚未下载完成，无法安装")
    try:
        from module.Engine.Engine import Engine
        engine = Engine.get()
        if engine.get_status() != Engine.Status.IDLE or engine.has_stop_barrier():
            raise HTTPException(status_code=409, detail="当前有任务正在运行，请先停止任务再安装更新")
    except HTTPException:
        raise
    except Exception:
        pass
    manager.emit(Base.Event.APP_UPDATE_EXTRACT, {})
    return _payload(manager)


def _read_changelog() -> str:
    roots = [
        Path(__file__).resolve().parents[2],
        Path(__file__).resolve().parents[2] / "resource",
    ]
    for root in roots:
        for name in ("CHANGELOG.md", "resource/CHANGELOG.md"):
            path = (root / name).resolve()
            try:
                if path.is_file():
                    return path.read_text(encoding="utf-8-sig").strip()
            except (OSError, UnicodeError):
                continue
    return ""


@router.get("/changelog", response_model=ChangelogResponse)
def get_changelog() -> ChangelogResponse:
    markdown = _read_changelog()
    return ChangelogResponse(markdown=markdown, empty=not bool(markdown))
