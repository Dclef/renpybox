"""项目路径设置。

写项目路径会触发 ProjectStore 发 PROJECT_CHANGED 事件，
由 api/events.py 的桥转成 WS 消息推给渲染端——这条链路正好用来验证
「业务逻辑 → 事件总线 → WebSocket」全链路是否通。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from api.schemas import ProjectInfo, ProjectPathRequest, ProjectResolveRequest
from module.Project.ProjectStore import ProjectStore
from module.Renpy.ProjectPaths import RenpyProjectPaths, looks_like_renpy_path

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


@router.post("/resolve", response_model = ProjectInfo)
def resolve_project(request: Request, body: ProjectResolveRequest) -> ProjectInfo:
    """按给定目录解析 Ren'Py 项目身份。

    与 frontend/Project/ProjectPage.py:135-161 ``_sync_renpy_paths_from_selection``
    等价（只是去掉了 Qt）：**只有路径本身带 Ren'Py 项目结构时才同步项目身份**。
    用户选的翻译输入目录通常是自己建的任意文件夹，把它当成项目根会让
    ``renpy_project_path`` / ``renpy_tl_folder`` 指向一个并不存在的
    ``game/tl/<lang>``，项目设置反而变错。

    所以不含项目结构时返回 409，调用方应忽略并只保留 input_folder。
    """
    config = request.app.state.config
    raw = str(body.path or "").strip()
    if not raw:
        raise HTTPException(status_code = 400, detail = "路径不能为空")

    if not looks_like_renpy_path(raw):
        raise HTTPException(
            status_code = 409,
            detail = "该目录不含 Ren'Py 项目结构（未找到 game/ 或 *.rpy），仅作为输入目录保留",
        )

    paths = RenpyProjectPaths.from_path(raw)
    if paths is None:
        raise HTTPException(status_code = 409, detail = "无法从该目录推导 Ren'Py 项目结构")

    # apply_resolved 内部会走 apply_to_config 规范五字段，再 persist 发 PROJECT_CHANGED
    ProjectStore.get().apply_resolved(config, paths)
    return _info(request)
