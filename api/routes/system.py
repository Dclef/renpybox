"""系统级接口：健康检查与版本。"""

from __future__ import annotations

import os
import sys

from fastapi import APIRouter, Request

from api.schemas import HealthResponse, VersionResponse
from base.Version import Version

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    """Electron 主进程轮询这个接口决定何时开窗。"""
    config = request.app.state.config
    return HealthResponse(
        ok = True,
        pid = os.getpid(),
        app_version = Version.CURRENT,
        config_path = str(getattr(type(config), "CONFIG_PATH", "")),
        python_version = sys.version.split()[0],
        mode = "api",
    )


@router.get("/api/version", response_model=VersionResponse)
def version() -> VersionResponse:
    return VersionResponse(app_version = Version.CURRENT)