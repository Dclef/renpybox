"""游戏模组安装与卸载工具。"""

from __future__ import annotations

import shutil
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

from base.LogManager import LogManager
from base.PathHelper import get_resource_path

_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


@dataclass(frozen=True)
class ModFile:
    """模组中的单个随包文件。"""

    resource_parts: tuple[str, ...]
    target_name: str
    has_rpyc: bool = False


@dataclass(frozen=True)
class ModSpec:
    """随应用分发的模组规格。"""

    key: str
    title: str
    files: tuple[ModFile, ...]


class ModInjector:
    """将随包模组复制到 Ren'Py 游戏目录。"""

    # 仅用于迁移旧版随包独木桥，不会扫描或删除其他用户脚本。
    LEGACY_DUMUQIAO_FILES = ("dumuqiao.rpy", "dumuqiao.rpyc")

    MODS: dict[str, ModSpec] = {
        "gallery_unlock": ModSpec(
            key="gallery_unlock",
            title="解锁画廊（ZLZK 通用画廊解锁器改写版）",
            files=(
                ModFile(
                    resource_parts=(
                        "resource",
                        "mods",
                        "gallery_unlock",
                        "hook_gallery_unlock.rpy",
                    ),
                    target_name="hook_gallery_unlock.rpy",
                    has_rpyc=True,
                ),
            ),
        ),
        "urm": ModSpec(
            key="urm",
            title="修改器（0x52-URM 2.6.2 汉化版）",
            files=(
                ModFile(
                    resource_parts=(
                        "resource",
                        "mods",
                        "urm",
                        "0x52-URM-2.6.2.rpa",
                    ),
                    target_name="0x52-URM-2.6.2.rpa",
                ),
                ModFile(
                    resource_parts=(
                        "resource",
                        "mods",
                        "urm",
                        "hook_urm_button.rpy",
                    ),
                    target_name="hook_urm_button.rpy",
                    has_rpyc=True,
                ),
            ),
        ),
        "simple_modifier": ModSpec(
            key="simple_modifier",
            title="内置修改器（RenpyBox）",
            files=(
                ModFile(
                    resource_parts=(
                        "resource",
                        "mods",
                        "simple_modifier",
                        "hook_simple_modifier.rpy",
                    ),
                    target_name="hook_simple_modifier.rpy",
                    has_rpyc=True,
                ),
            ),
        ),
    }

    def __init__(self) -> None:
        self.logger = LogManager.get()

    def _resource_mods_root(self) -> Path:
        return Path(get_resource_path("resource", "mods")).resolve()

    def _is_link(self, path: Path) -> bool:
        try:
            if path.is_symlink():
                return True
        except OSError:
            return True
        try:
            return bool(path.lstat().st_file_attributes & _REPARSE_POINT)  # type: ignore[attr-defined]
        except (AttributeError, OSError):
            return False

    def _within(self, root: Path, child: Path) -> bool:
        try:
            child.resolve().relative_to(root.resolve())
            return True
        except (ValueError, OSError):
            return False

    def _ensure_safe_target(self, target: Path) -> None:
        """拒绝修改随应用分发的模组资源目录；拒绝链接逃逸与目录目标。"""
        resource_root = self._resource_mods_root()
        try:
            target.resolve().relative_to(resource_root)
        except ValueError:
            pass
        else:
            raise ValueError(f"目标路径不能位于随包模组资源目录：{target}")

        if self._is_link(target):
            # 链接必须仍落在 game 内且最终是文件
            game = target.parent
            if not self._within(game, target):
                raise ValueError(f"目标符号链接或目录联接越出游戏目录：{target}")
            if target.exists() and not target.is_file():
                raise ValueError(f"模组目标必须是文件：{target}")
        elif target.exists() and not target.is_file():
            raise ValueError(f"模组目标必须是文件：{target}")

    def resolve_game_dir(self, path: str) -> Path:
        """解析项目根目录、game 目录或游戏内文件路径。

        找不到 game 时返回输入路径（Qt 兼容）；真正写入请用 require_game_dir。
        """
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

    def require_game_dir(self, path: str) -> Path:
        """解析并校验真实 game 目录；拒绝资源目录、非 game、链接逃逸。"""
        if not str(path or "").strip():
            raise ValueError("游戏路径不能为空")
        resolved = self.resolve_game_dir(path)
        if not resolved.is_dir():
            raise FileNotFoundError(f"游戏目录不存在：{resolved}")
        if resolved.name.lower() != "game":
            raise ValueError(f"未找到有效的 game 目录：{path}")
        if self._is_link(resolved):
            # game 本身若是链接，必须仍像合法目录且不指向资源 mods
            if not resolved.is_dir():
                raise ValueError(f"游戏目录链接无效：{resolved}")
        resource_root = self._resource_mods_root()
        try:
            resolved.resolve().relative_to(resource_root)
        except ValueError:
            pass
        else:
            raise ValueError(f"不能把随包模组资源目录当作游戏目录：{resolved}")
        # 禁止把 resource/mods 的父树误当 game
        try:
            resource_root.relative_to(resolved.resolve())
        except ValueError:
            pass
        else:
            raise ValueError(f"不能把包含随包模组资源的目录当作游戏目录：{resolved}")
        return resolved

    def _require_mod_key(self, key: str) -> ModSpec:
        if key not in self.MODS:
            raise KeyError(f"未知模组键：{key}")
        return self.MODS[key]

    def _staging_parent(self, game_path: Path) -> Path:
        """可执行脚本暂存放在 game 外，避免 Ren'Py 加载中间文件。"""
        parent = game_path.parent
        if parent.exists() and parent.is_dir():
            return parent
        return Path(tempfile.gettempdir())

    def status(self, game_dir: str) -> dict[str, bool]:
        """返回各模组是否已安装。"""
        try:
            game_path = self.require_game_dir(game_dir)
        except Exception:
            return {key: False for key in self.MODS}
        result = {}
        for key, spec in self.MODS.items():
            installed = True
            for mod_file in spec.files:
                target = game_path / mod_file.target_name
                if not target.is_file() and not (
                    mod_file.has_rpyc and target.with_suffix(".rpyc").is_file()
                ):
                    installed = False
                    break
            result[key] = installed
        return result

    def has_legacy_dumuqiao(self, game_dir: str) -> bool:
        """判断游戏目录是否残留旧版随包独木桥文件。"""
        try:
            game_path = self.require_game_dir(game_dir)
        except Exception:
            return False
        return any((game_path / name).is_file() for name in self.LEGACY_DUMUQIAO_FILES)

    def remove_legacy_dumuqiao(self, game_dir: str) -> tuple[bool, str]:
        """显式删除旧版独木桥的确定文件，不扫描其他用户脚本。"""
        try:
            game_path = self.require_game_dir(game_dir)
            targets = [game_path / name for name in self.LEGACY_DUMUQIAO_FILES]
            for target in targets:
                self._ensure_safe_target(target)

            for target in targets:
                target.unlink(missing_ok=True)
            return True, "旧版独木桥文件已删除"
        except Exception as exc:
            self.logger.error("清理旧版独木桥失败", exc)
            return False, str(exc)

    def install(self, game_dir: str, key: str) -> tuple[bool, str]:
        """安装指定模组，覆盖前将旧文件改名为 .bak。"""
        try:
            spec = self._require_mod_key(key)
            game_path = self.require_game_dir(game_dir)
            files = []
            for mod_file in spec.files:
                source = Path(get_resource_path(*mod_file.resource_parts))
                if not source.is_file():
                    raise FileNotFoundError(f"模组资源不存在：{source}")
                if self._is_link(source) and not source.is_file():
                    raise FileNotFoundError(f"模组资源无效：{source}")
                target = game_path / mod_file.target_name
                if target.name != mod_file.target_name:
                    raise ValueError("模组目标文件名无效")
                self._ensure_safe_target(target)
                files.append((mod_file, source, target))

            staging_parent = self._staging_parent(game_path)
            if self._within(game_path, staging_parent) or staging_parent.resolve() == game_path.resolve():
                staging_parent = Path(tempfile.gettempdir())
            # 先写入 game 外临时目录，再统一替换；任一步失败都恢复原文件和既有 .bak。
            with tempfile.TemporaryDirectory(
                prefix=".renpybox-mod-", dir=str(staging_parent)
            ) as temporary_dir:
                temporary_path = Path(temporary_dir)
                rollback_path = temporary_path / "rollback"
                rollback_path.mkdir(parents=True, exist_ok=True)
                staged_files = []
                for index, (mod_file, source, target) in enumerate(files):
                    staged = temporary_path / f"{index}-{target.name}"
                    shutil.copy2(source, staged)
                    staged_files.append((mod_file, staged, target))

                tracked_paths = []
                for mod_file, _, target in staged_files:
                    tracked_paths.extend((target, target.with_name(f"{target.name}.bak")))
                    if mod_file.has_rpyc:
                        tracked_paths.append(target.with_suffix(".rpyc"))

                snapshots = {}
                for index, path in enumerate(tracked_paths):
                    if path.exists() or path.is_symlink():
                        if not path.is_file() and not path.is_symlink():
                            raise IsADirectoryError(f"模组目标必须是文件：{path}")
                        snapshot = rollback_path / str(index)
                        shutil.copy2(path, snapshot)
                        snapshots[path] = snapshot
                    else:
                        snapshots[path] = None

                try:
                    for mod_file, staged, target in staged_files:
                        if target.exists() or target.is_symlink():
                            target.replace(target.with_name(f"{target.name}.bak"))
                        if mod_file.has_rpyc:
                            target.with_suffix(".rpyc").unlink(missing_ok=True)
                        staged.replace(target)
                except Exception:
                    for path, snapshot in snapshots.items():
                        path.unlink(missing_ok=True)
                        if snapshot is not None:
                            shutil.copy2(snapshot, path)
                    raise
            return True, f"{spec.title}安装成功"
        except Exception as exc:
            self.logger.error(f"安装模组失败：{key}", exc)
            return False, str(exc)

    def uninstall(self, game_dir: str, key: str) -> tuple[bool, str]:
        """卸载指定模组及其可能残留的 Ren'Py 编译文件；不自动恢复 .bak。"""
        try:
            spec = self._require_mod_key(key)
            game_path = self.require_game_dir(game_dir)
            targets = []
            for mod_file in spec.files:
                target = game_path / mod_file.target_name
                self._ensure_safe_target(target)
                targets.append((mod_file, target))

            for mod_file, target in targets:
                target.unlink(missing_ok=True)
                if mod_file.has_rpyc:
                    target.with_suffix(".rpyc").unlink(missing_ok=True)
            return True, f"{spec.title}卸载成功"
        except Exception as exc:
            self.logger.error(f"卸载模组失败：{key}", exc)
            return False, str(exc)
