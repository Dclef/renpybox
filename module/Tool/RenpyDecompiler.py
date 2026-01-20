"""Ren'Py RPYC decompiler helper (unrpyc v2 only).

Workflow:
- copy bundled `resource/unrpyc_python_v2` into the target game root;
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
    copy_files_under_directory_to_directory,
    get_game_path_from_game_dir,
    get_python_path_from_game_path,
)
from utils.unzipdir import unzip_file, zip_dir


class RenpyDecompiler:
    RESOURCE_VARIANT = "unrpyc_python_v2"

    def __init__(self) -> None:
        self.logger = LogManager.get()
        self.resource_root = Path(get_resource_path("resource"))
        self.resource_dir = self.resource_root / self.RESOURCE_VARIANT
        if not self.resource_dir.exists():
            raise FileNotFoundError(f"Missing resource directory: {self.resource_dir}")
        injected = {path.name for path in self.resource_dir.iterdir()}
        self._injected_names = sorted(injected)
        self._cleanup_candidates: set[str] = set(injected)

    def decompile(self, target: str, *, overwrite: bool = False) -> None:
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
        renpy_common = root_dir / "renpy" / "common"
        if not renpy_common.exists():
            raise FileNotFoundError(f"Missing renpy/common directory: {renpy_common}")

        backup_zip = root_dir / "common_backup.zip"

        self.logger.info(f"Start decompiling {exe_path} (unrpyc=v2)")
        unrpyc_error: Exception | None = None
        unrpyc_output: str | None = None
        try:
            self.logger.debug(f"Backing up renpy/common -> {backup_zip}")
            zip_dir(str(renpy_common), str(backup_zip))

            self._restore_common_from_backup(root_dir, backup_zip, keep_backup=True)
            self._cleanup_injected_files(root_dir)
            self._copy_unrpyc_resources(root_dir)
            result = self._run_unrpyc(python_exe, root_dir, game_dir, overwrite)
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

        renpy_version = self._read_renpy_version(root_dir) or "unknown"
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

    def _resolve_game_root(self, target: Path) -> tuple[Path, Path]:
        target = target.resolve()
        if target.is_file() and target.suffix.lower() == ".exe":
            return target.parent, target
        if target.is_dir():
            exe = self._find_game_exe(target)
            if exe:
                return exe.parent, exe
        raise FileNotFoundError("Please provide the game root directory or executable (.exe).")

    def _find_game_exe(self, directory: Path) -> Path | None:
        game_path = get_game_path_from_game_dir(str(directory))
        if game_path:
            return Path(game_path)
        candidates = sorted(directory.glob("*.exe"))
        return candidates[0] if candidates else None

    def _copy_unrpyc_resources(self, root_dir: Path) -> None:
        self.logger.debug(f"Copying {self.RESOURCE_VARIANT} resources -> {root_dir}")
        copy_files_under_directory_to_directory(str(self.resource_dir), str(root_dir))

    def _run_unrpyc(
        self, python_exe: Path, root_dir: Path, game_dir: Path, overwrite: bool
    ) -> subprocess.CompletedProcess[str]:
        command = [
            str(python_exe),
            "-O",
            str(root_dir / "unrpyc.py"),
            str(game_dir),
        ]
        if overwrite:
            command.append("--clobber")

        self.logger.info(f"Running unrpyc: {' '.join(command)}")
        creationflags = 0
        if os.name == "nt":
            try:
                creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
            except Exception:
                creationflags = 0
        return subprocess.run(
            command,
            cwd=str(root_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="ignore",
            creationflags=creationflags,
        )

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
