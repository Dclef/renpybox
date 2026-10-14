"""项目事实写入口。

收口项目路径的写入语义：
- ``apply_resolved``：路径解析后的规范化回写（内部走 Renpy ProjectPaths 的
  ``apply_to_config``，五字段一致）；
- ``save_edited_paths``：项目设置页的表单编辑保存（仅三字段，保留用户显式值）；
- ``persist``：统一的配置持久化出口。

所有项目事实写入都先经过本类，再由调用方明确选择是否立即持久化。
运行期临时目录可以使用 ``persist=False``，但不能绕过字段写入收口。

模块级补全了两个 Qt5 已有的项目绑定副作用（Electron 端经 API 调用）：
``resolve_target_language``（按真实 ``tl/<lang>`` 推断目标语言）与
``ensure_output_folder``（按需创建输出目录，失败不抛出）。
"""

from base.Base import Base
from base.compat import Self
from module.Renpy.ProjectPaths import (
    RenpyProjectPaths,
    apply_to_config,
    guess_language_from_tl_path,
)
from collections.abc import Callable
from pathlib import Path


def resolve_target_language(config, paths: RenpyProjectPaths) -> bool:
    """项目绑定时按真实 ``tl/<lang>`` 目录推断目标语言。

    等价于 Qt5 ``frontend/Project/ProjectPage.py:151-153`` 的 mutate：只在
    检测到真实语言目录时改写 ``target_language``；推断不出时保留用户当前
    选择（例如尚未创建该语言目录的新项目）。返回是否发生了改写。
    """
    guessed = guess_language_from_tl_path(paths.tl_language_dir)
    if guessed is None:
        return False
    if getattr(config, "target_language", None) == guessed:
        return False
    config.target_language = guessed
    return True


def ensure_output_folder(config, field: str = "output_folder") -> bool:
    """按需创建输出目录（parents + exist_ok），失败只记录不抛出。

    等价于 Qt5 ``frontend/Project/ProjectPage.py:215``：项目绑定后翻译输出
    目录必须存在，否则第一次任务会因为目录不存在直接失败。配置值本身保持
    不变——目录以后仍可创建（例如换盘符或稍后挂载网络盘）。
    """
    raw = str(getattr(config, field, "") or "").strip()
    if raw == "":
        return False
    try:
        path = Path(raw).expanduser()
    except (OSError, ValueError):
        return False
    try:
        path.mkdir(parents = True, exist_ok = True)
    except (OSError, ValueError) as exc:
        Base().warning(f"输出目录创建失败，保留配置路径：{raw}", exc, console = False)
        return False
    return True


class ProjectStore(Base):

    _instance: "ProjectStore | None" = None

    @classmethod
    def get(cls) -> Self:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _emit_changed(self, config) -> None:
        self.emit(Base.Event.PROJECT_CHANGED, {
            "project_root": str(getattr(config, "renpy_project_path", "") or ""),
        })

    def persist(self, config, *, emit: bool = True):
        """持久化已修改配置，并按需广播项目变化。"""
        config.save()
        if emit:
            self._emit_changed(config)
        return config

    def set_project_path(self, config, project_path: str):
        """只修改项目根路径，供需要和其他设置一起保存的页面使用。"""
        config.renpy_project_path = str(project_path or "")
        return config

    def set_game_folder(self, config, game_folder: str):
        """只修改 game 目录，供抽取/工具页和其他设置一起保存。"""
        config.renpy_game_folder = str(game_folder or "")
        return config

    def apply_resolved(
        self,
        config,
        paths: RenpyProjectPaths,
        *,
        input_folder = None,
        output_folder = None,
        mutate: Callable[[object], None] | None = None,
        persist: bool = True,
    ):
        """规范化写入，并在同一次持久化前应用额外项目字段。

        不传 ``input_folder``/``output_folder`` 时不再无条件把运行目录改写
        成 ``game/tl/<lang>``：派生态的归属由 ``apply_to_config`` 判定，
        用户显式选择的目录会被保留。调用方要强制回到主语言目录，必须显式
        传入目录值。
        """
        apply_to_config(
            config,
            paths,
            input_folder = input_folder,
            output_folder = output_folder,
        )
        if mutate is not None:
            mutate(config)
        if persist:
            self.persist(config)
        return config

    def save_edited_paths(
        self,
        config,
        project_path: str,
        game_folder: str,
        tl_folder: str,
        *,
        mutate: Callable[[object], None] | None = None,
    ):
        """表单编辑语义：仅三字段，input/output 与其他字段不动。"""
        config.renpy_project_path = str(project_path or "")
        config.renpy_game_folder = str(game_folder or "")
        config.renpy_tl_folder = str(tl_folder or "")
        if mutate is not None:
            mutate(config)
        return self.persist(config)
