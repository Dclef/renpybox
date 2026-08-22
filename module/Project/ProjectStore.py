"""项目事实写入口（第一层）。

收口两种写入语义：
- ``apply_resolved``：路径解析后的规范化回写（内部走 Renpy ProjectPaths 的
  ``apply_to_config``，五字段一致）；
- ``save_edited_paths``：项目设置页的表单编辑保存（仅三字段，保留用户显式值）。

两者都在持久化成功后发 ``PROJECT_CHANGED`` 事件，供页面在项目切换后刷新。

注意：ProjectPage / HookTranslatePage / OneKeyTranslatePage 等现有
``apply_to_config`` 调用方暂不经本类（各自有精细的保存时机与上下文），
随页面拆分逐步迁移；AndroidBuildPage 的单字段写入语义存疑，明确不收口。
"""

from base.Base import Base
from base.compat import Self
from module.Renpy.ProjectPaths import RenpyProjectPaths, apply_to_config


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

    def apply_resolved(
        self,
        config,
        paths: RenpyProjectPaths,
        *,
        input_folder = None,
        output_folder = None,
    ):
        """规范化写入（project/game/tl/input/output 五字段一致）并持久化。"""
        apply_to_config(
            config,
            paths,
            input_folder = input_folder,
            output_folder = output_folder,
        )
        config.save()
        self._emit_changed(config)
        return config

    def save_edited_paths(self, config, project_path: str, game_folder: str, tl_folder: str):
        """表单编辑语义：仅三字段，input/output 与其他字段不动。"""
        config.renpy_project_path = str(project_path or "")
        config.renpy_game_folder = str(game_folder or "")
        config.renpy_tl_folder = str(tl_folder or "")
        config.save()
        self._emit_changed(config)
        return config
