"""项目事实写入口。

收口项目路径的写入语义：
- ``apply_resolved``：路径解析后的规范化回写（内部走 Renpy ProjectPaths 的
  ``apply_to_config``，五字段一致）；
- ``save_edited_paths``：项目设置页的表单编辑保存（仅三字段，保留用户显式值）；
- ``persist``：统一的配置持久化出口。

所有项目事实写入都先经过本类，再由调用方明确选择是否立即持久化。
运行期临时目录可以使用 ``persist=False``，但不能绕过字段写入收口。
"""

from base.Base import Base
from base.compat import Self
from module.Renpy.ProjectPaths import RenpyProjectPaths, apply_to_config
from collections.abc import Callable


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
        """规范化写入，并在同一次持久化前应用额外项目字段。"""
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
