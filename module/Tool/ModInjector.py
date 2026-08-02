"""游戏模组安装与卸载工具。"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from base.LogManager import LogManager
from base.PathHelper import get_resource_path


@dataclass(frozen=True)
class ModSpec:
    """随应用分发的模组规格。"""

    key: str
    title: str
    resource_parts: tuple[str, ...]
    target_name: str
    has_rpyc: bool


class ModInjector:
    """将随包模组复制到 Ren'Py 游戏目录。"""

    MODS: dict[str, ModSpec] = {
        "urm": ModSpec(
            key="urm",
            title="修改器（0x52-URM 2.6.2 汉化版）",
            resource_parts=("resource", "mods", "urm", "0x52-URM-2.6.2.rpa"),
            target_name="0x52-URM-2.6.2.rpa",
            has_rpyc=False,
        ),
        "quick_menu": ModSpec(
            key="quick_menu",
            title="底部按钮栏（独木桥模组 6.27 版）",
            resource_parts=("resource", "mods", "quick_menu", "dumuqiao.rpy"),
            target_name="dumuqiao.rpy",
            has_rpyc=True,
        ),
    }

    def __init__(self) -> None:
        self.logger = LogManager.get()

    def _ensure_safe_target(self, target: Path) -> None:
        """拒绝修改随应用分发的模组资源目录。"""
        resource_root = Path(get_resource_path("resource", "mods")).resolve()
        try:
            target.resolve().relative_to(resource_root)
        except ValueError:
            return
        raise ValueError(f"目标路径不能位于随包模组资源目录：{target}")

    def resolve_game_dir(self, path: str) -> Path:
        """解析项目根目录、game 目录或游戏内文件路径。"""
        try:
            p = Path(path)
            if p.is_file():
                p = p.parent

            if p.name.lower() == "game" and p.is_dir():
                return p

            candidate = p / "game"
            if candidate.exists() and candidate.is_dir():
                return candidate

            for parent in p.parents:
                cand = parent / "game"
                if cand.exists() and cand.is_dir():
                    return cand

            return p
        except Exception:
            return Path(path)

    def status(self, game_dir: str) -> dict[str, bool]:
        """返回各模组是否已安装。"""
        game_path = self.resolve_game_dir(game_dir)
        result = {}
        for key, spec in self.MODS.items():
            target = game_path / spec.target_name
            result[key] = target.is_file() or (
                spec.has_rpyc and target.with_suffix(".rpyc").is_file()
            )
        return result

    def install(self, game_dir: str, key: str) -> tuple[bool, str]:
        """安装指定模组，覆盖前将旧文件改名为 .bak。"""
        try:
            spec = self.MODS[key]
            source = Path(get_resource_path(*spec.resource_parts))
            if not source.is_file():
                raise FileNotFoundError(f"模组资源不存在：{source}")

            target = self.resolve_game_dir(game_dir) / spec.target_name
            self._ensure_safe_target(target)
            if target.exists():
                target.replace(target.with_name(f"{target.name}.bak"))

            shutil.copy2(source, target)
            return True, f"{spec.title}安装成功"
        except Exception as exc:
            self.logger.error(f"安装模组失败：{key}", exc)
            return False, str(exc)

    def uninstall(self, game_dir: str, key: str) -> tuple[bool, str]:
        """卸载指定模组及其可能残留的 Ren'Py 编译文件。"""
        try:
            spec = self.MODS[key]
            target = self.resolve_game_dir(game_dir) / spec.target_name
            self._ensure_safe_target(target)
            target.unlink(missing_ok=True)
            if spec.has_rpyc:
                target.with_suffix(".rpyc").unlink(missing_ok=True)
            return True, f"{spec.title}卸载成功"
        except Exception as exc:
            self.logger.error(f"卸载模组失败：{key}", exc)
            return False, str(exc)
