"""应用更新：复用 VersionManager，网页与 Electron 共用同一套检查/下载/安装。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from base.Base import Base
from base.VersionManager import VersionManager

router = APIRouter(prefix="/api/update", tags=["update"])

_DESKTOP_AUTO_UPDATE_DETAIL = "桌面版需前往发布页单独下载安装，不能使用自动更新"


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


def _is_desktop_delivery(status: str, latest: dict) -> bool:
    return status == VersionManager.Status.DESKTOP_AVAILABLE or latest.get("delivery") == "desktop"


def _reject_desktop_auto_update(status: str, latest: dict) -> None:
    if _is_desktop_delivery(status, latest):
        raise HTTPException(status_code=400, detail=_DESKTOP_AUTO_UPDATE_DETAIL)


def _payload(manager: VersionManager) -> UpdateActionResponse:
    state = manager.get_update_state()
    latest = state.get("latest") if isinstance(state.get("latest"), dict) else {}
    status = str(state.get("status") or VersionManager.Status.NONE)
    tag = str(latest.get("tag_name", "") or "")
    current = VersionManager.parse_version(str(state.get("version") or manager.get_version()))
    available = VersionManager.parse_version(tag) if tag else (0, 0, 0, 0)
    desktop = _is_desktop_delivery(status, latest)
    # 同版本桌面迁移也要标 new_version，前端才能展示迁移入口而不是「已是最新」
    new_version = bool(tag and (current < available or (desktop and current == available)))
    release_url = VersionManager.RELEASE_URL
    if desktop:
        try:
            release_url = VersionManager.desktop_release_url(latest)
        except ValueError:
            pass
    return UpdateActionResponse(
        status=status,
        version=str(state.get("version") or manager.get_version()),
        latest=latest,
        downloaded_size=int(state.get("downloaded_size") or 0),
        total_size=int(state.get("total_size") or 0),
        error=str(state.get("error") or ""),
        new_version=new_version,
        release_url=release_url,
        can_install=(
            status == VersionManager.Status.DOWNLOADED
            and not desktop
        ),
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
    latest = state.get("latest") if isinstance(state.get("latest"), dict) else {}
    _reject_desktop_auto_update(status, latest)
    if status == VersionManager.Status.UPDATING:
        raise HTTPException(status_code=409, detail="正在下载更新")
    if status == VersionManager.Status.DOWNLOADED:
        return _payload(manager)
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
    status = str(state.get("status") or "")
    latest = state.get("latest") if isinstance(state.get("latest"), dict) else {}
    _reject_desktop_auto_update(status, latest)
    if status != VersionManager.Status.DOWNLOADED:
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
