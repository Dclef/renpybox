"""Ren'Py RPYC 反编译辅助工具（按游戏 Python 版本选择 unrpyc v1/v2）。

Workflow:
- copy the matching bundled `resource/unrpyc_python_v1` or `v2` into the target game root;
- backup `renpy/common` and execute the game's python with `unrpyc.py`;
- restore the original files afterwards.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from base.LogManager import LogManager
from base.PathHelper import get_resource_path
from utils.call_game_python import (
    get_game_path_from_game_dir,
    get_python_path_from_game_path,
)
from utils.unzipdir import unzip_file, zip_dir


def remove_decompiled_rpyc(game_dir: str | Path) -> int:
    """删除源码区内已有同名 RPY 的 RPYC 文件。"""

    root = Path(game_dir)
    tl_root = root / "tl"

    def is_source(path: Path) -> bool:
        try:
            path.relative_to(tl_root)
            return False
        except ValueError:
            return True

    files = [path for path in root.rglob("*") if path.is_file() and is_source(path)]
    rpy_keys = {
        path.relative_to(root).with_suffix("").as_posix().casefold()
        for path in files
        if path.suffix.casefold() == ".rpy"
    }
    removed = 0
    for path in files:
        if path.suffix.casefold() != ".rpyc":
            continue
        key = path.relative_to(root).with_suffix("").as_posix().casefold()
        if key not in rpy_keys:
            continue
        path.unlink()
        removed += 1
    return removed


class RenpyDecompiler:
    RESOURCE_VARIANT = "unrpyc_python_v2"

    def __init__(self, resource_variant: str | None = None) -> None:
        self.logger = LogManager.get()
        self.resource_root = Path(get_resource_path("resource"))
        self.resource_variant = resource_variant or self.RESOURCE_VARIANT
        self.resource_dir = self.resource_root / self.resource_variant
        self._injected_names: list[str] = []
        self._cleanup_candidates: set[str] = set()
        self._configure_resource_variant(self.resource_variant)

    def decompile(
        self,
        target: str,
        *,
        overwrite: bool = False,
        output_callback=None,
    ) -> None:
        """
        Decompile all RPYC files under the game's `game/` directory into RPY.

        Args:
            target: Path to the game executable or its parent directory.
            overwrite: If True, pass `--clobber` to unrpyc to overwrite existing files.
        """
        root_dir, exe_path = self._resolve_game_root(Path(target))
        game_dir = root_dir / "game"
        if not game_dir.exists():
            raise FileNotFoundError(f"Missing game directory: {game_dir}")

        python_path = get_python_path_from_game_path(str(exe_path))
        if not python_path:
            raise FileNotFoundError("Could not locate python.exe in the game folder.")

        python_exe = Path(python_path)
        python_major = self._detect_embedded_python_major(python_exe)
        variant = "unrpyc_python_v1" if python_major == 2 else "unrpyc_python_v2"
        self._configure_resource_variant(variant)

        renpy_common = root_dir / "renpy" / "common"
        if not renpy_common.exists():
            raise FileNotFoundError(f"Missing renpy/common directory: {renpy_common}")

        backup_zip = root_dir / "common_backup.zip"

        self.logger.info(
            f"Start decompiling {exe_path} (unrpyc={self.resource_variant.removeprefix('unrpyc_python_')})"
        )
        unrpyc_error: Exception | None = None
        unrpyc_output: str | None = None
        try:
            self.logger.debug(f"Backing up renpy/common -> {backup_zip}")
            zip_dir(str(renpy_common), str(backup_zip))

            self._restore_common_from_backup(root_dir, backup_zip, keep_backup=True)
            self._cleanup_injected_files(root_dir)
            self._copy_unrpyc_resources(root_dir)
            result = self._run_unrpyc(
                python_exe,
                root_dir,
                game_dir,
                overwrite,
                output_callback=output_callback,
            )
            unrpyc_output = (result.stdout or "").strip() if result else ""
            if unrpyc_output:
                self.logger.info(unrpyc_output)
            if result.returncode != 0:
                raise RuntimeError(f"unrpyc returned non-zero exit code {result.returncode}")
            self.logger.info("Decompile finished, cleaning up temporary files")
        except Exception as exc:
            unrpyc_error = exc
        finally:
            self._cleanup_injected_files(root_dir)
            self._restore_common_from_backup(root_dir, backup_zip, keep_backup=False)

        if unrpyc_error is None:
            return

        renpy_version = self._read_renpy_version(root_dir) or self._infer_renpy_version_from_python(python_exe) or "unknown"
        detail = ""
        if unrpyc_output:
            detail += f"\n\n[unrpyc output]\n{unrpyc_output.strip()}"

        raise RuntimeError(
            "反编译失败（可能是 Ren'Py 版本过高或脚本格式变更导致 unrpyc 不兼容）。\n"
            f"Ren'Py version: {renpy_version}{detail}"
        ) from unrpyc_error

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _configure_resource_variant(self, variant: str) -> None:
        """根据游戏 Python 主版本切换对应的 unrpyc 资源。"""
        resource_dir = self.resource_root / variant
        if not resource_dir.is_dir():
            raise FileNotFoundError(f"Missing resource directory: {resource_dir}")
        self.resource_variant = variant
        self.resource_dir = resource_dir
        injected = {path.name for path in resource_dir.iterdir()}
        self._injected_names = sorted(injected)
        self._cleanup_candidates = set(injected)

    def _read_renpy_version(self, root_dir: Path) -> str | None:
        version_file = root_dir / "renpy" / "version.txt"
        if not version_file.is_file():
            return None
        try:
            text = version_file.read_text(encoding="utf-8", errors="ignore").strip()
        except Exception:
            try:
                text = version_file.read_text(errors="ignore").strip()
            except Exception:
                return None
        if not text:
            return None
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        return lines[0] if lines else None

    def _detect_embedded_python_major(self, python_exe: Path) -> int | None:
        python_path = str(python_exe).replace("\\", "/").lower()
        if "/py2-" in python_path or "python2" in python_path:
            return 2
        if "/py3-" in python_path or "python3" in python_path:
            return 3

        creationflags = 0
        if os.name == "nt":
            try:
                creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
            except Exception:
                creationflags = 0

        try:
            result = subprocess.run(
                [str(python_exe), "-c", "import sys; print(sys.version_info[0])"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="ignore",
                creationflags=creationflags,
                timeout=5,
            )
            if result.returncode == 0:
                value = (result.stdout or "").strip()
                if value in ("2", "3"):
                    return int(value)
        except Exception as exc:
            self.logger.debug(f"检测游戏内置 Python 主版本失败: {exc}")

        return None

    def _infer_renpy_version_from_python(self, python_exe: Path) -> str | None:
        python_major = self._detect_embedded_python_major(python_exe)
        if python_major == 2:
            return "inferred-7.x (Python 2)"
        if python_major == 3:
            return "inferred-8.x (Python 3)"
        return None

    def _resolve_game_root(self, target: Path) -> tuple[Path, Path]:
        target = target.resolve()
        if target.is_file() and target.suffix.lower() == ".exe":
            return target.parent, target
        if target.is_dir():
            if target.name.lower() == "game":
                root_dir = target.parent
                exe = self._find_game_exe(root_dir)
                if exe:
                    return exe.parent, exe
            exe = self._find_game_exe(target)
            if exe:
                return exe.parent, exe
        raise FileNotFoundError("Please provide the game root directory, game folder, or executable (.exe).")

    def _find_game_exe(self, directory: Path) -> Path | None:
        game_path = get_game_path_from_game_dir(str(directory))
        if game_path:
            return Path(game_path)
        candidates = sorted(directory.glob("*.exe"))
        return candidates[0] if candidates else None

    def _copy_unrpyc_resources(self, root_dir: Path) -> None:
        self.logger.debug(f"Copying {self.resource_variant} resources -> {root_dir}")
        shutil.copytree(self.resource_dir, root_dir, dirs_exist_ok=True)

    def _run_unrpyc(
        self,
        python_exe: Path,
        root_dir: Path,
        game_dir: Path,
        overwrite: bool,
        *,
        output_callback=None,
    ) -> subprocess.CompletedProcess[str]:
        command = [
            str(python_exe),
            "-O",
            str(root_dir / "unrpyc.py"),
        ]
        if overwrite:
            command.append("--clobber")
        command.append(str(game_dir))

        self.logger.info(f"Running unrpyc: {' '.join(command)}")
        from utils.process_runner import run_process

        result = run_process(
            command,
            cwd=str(root_dir),
            output_callback=output_callback,
        )
        return result

    def _restore_common_from_backup(self, root_dir: Path, backup_zip: Path, *, keep_backup: bool) -> None:
        """Restore renpy/common using the backup zip."""
        try:
            renpy_dir = root_dir / "renpy"
            common_dir = renpy_dir / "common"
            if backup_zip.exists():
                if common_dir.exists():
                    shutil.rmtree(common_dir, ignore_errors=True)
                unzip_file(str(backup_zip), str(common_dir))
                if not keep_backup:
                    backup_zip.unlink(missing_ok=True)
        except Exception as exc:
            self.logger.warning(f"Failed to restore renpy/common: {exc}")

    def _cleanup_injected_files(self, root_dir: Path) -> None:
        cleanup_targets = set(self._cleanup_candidates or [])
        cleanup_targets.update({"__pycache__", "unrpyc.pyo", "deobfuscate.pyo", "unrpyc.complete"})
        for name in cleanup_targets:
            path = root_dir / name
            try:
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                elif path.exists():
                    path.unlink()
            except Exception as exc:
                self.logger.debug(f"Failed to delete temporary file {path}: {exc}")
