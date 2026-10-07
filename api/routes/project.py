"""项目路径设置。

写项目路径会触发 ProjectStore 发PROJECT_CHANGED 事件，
由 api/events.py 的桥转成 WS 消息推给渲染端——这条链路正好用来验证
「业务逻辑 → 事件总线 → WebSocket」全链路是否通。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from api.schemas import ProjectInfo, ProjectPathRequest
from module.Project.ProjectStore import ProjectStore

router = APIRouter(prefix = "/api/project", tags = ["project"])


def _info(request: Request) -> ProjectInfo:
    config = request.app.state.config
    return ProjectInfo(
        renpy_project_path = getattr(config, "renpy_project_path", ""),
        renpy_game_folder = getattr(config, "renpy_game_folder", ""),
        renpy_tl_folder = getattr(config, "renpy_tl_folder", ""),
        theme = getattr(config, "theme", ""),
        app_language = getattr(config, "app_language", ""),
    )


@router.get("", response_model = ProjectInfo)
def read_project(request: Request) -> ProjectInfo:
    return _info(request)


@router.post("/path", response_model = ProjectInfo)
def set_project_path(request: Request, body: ProjectPathRequest) -> ProjectInfo:
    config = request.app.state.config

    if not body.project_path.strip():
        raise HTTPException(status_code = 400, detail = "项目路径不能为空")

    store = ProjectStore.get()
    store.set_project_path(config, body.project_path.strip())
    if body.game_folder:
        store.set_game_folder(config, body.game_folder)

    # persist() 才会发PROJECT_CHANGED：set_project_path 只改内存，
    # 单独调用它事件不会触发，渲染端就收不到路径变更。
    store.persist(config)

    return _info(request)