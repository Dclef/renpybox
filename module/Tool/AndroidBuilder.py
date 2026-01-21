from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Iterable

from base.LogManager import LogManager


class AndroidBuilder:
    def __init__(self, sdk_root: str, project_dir: str) -> None:
        self.sdk_root = Path(sdk_root).expanduser().resolve()
        self.project_dir = Path(project_dir).expanduser().resolve()
        self.logger = LogManager.get()

    @property
    def renpy_exe(self) -> Path:
        return self.sdk_root / "renpy.exe"

    @property
    def python_exe(self) -> Path:
        return self.sdk_root / "lib" / "py3-windows-x86_64" / "python.exe"

    @property
    def rapt_root(self) -> Path:
        return self.sdk_root / "rapt"

    @property
    def rapt_bin(self) -> Path:
        return self.rapt_root / "bin"

    @property
    def runner_script(self) -> Path:
        return Path(__file__).resolve().parent / "android_build_runner.py"

    def validate_paths(self) -> list[str]:
        errors: list[str] = []
        if not self.sdk_root.exists():
            errors.append(f"SDK 目录不存在: {self.sdk_root}")
        if not self.renpy_exe.exists():
            errors.append(f"renpy.exe 不存在: {self.renpy_exe}")
        if not self.python_exe.exists():
            errors.append(f"python.exe 不存在: {self.python_exe}")
        if not self.runner_script.exists():
            errors.append(f"缺少运行脚本: {self.runner_script}")
        if not self.project_dir.exists():
            errors.append(f"项目目录不存在: {self.project_dir}")
        return errors

    def _creationflags_no_window(self) -> int:
        if os.name != "nt":
            return 0
        try:
            return subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
        except Exception:
            return 0

    def _run_process(
        self,
        args: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        on_output: Callable[[str], None] | None = None,
    ) -> int:
        merged_env = os.environ.copy()
        merged_env["PYTHONIOENCODING"] = "utf-8"
        merged_env["PYTHONUTF8"] = "1"
        if env:
            merged_env.update(env)

        process = subprocess.Popen(
            args,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="ignore",
            env=merged_env,
            creationflags=self._creationflags_no_window(),
        )
        if process.stdout:
            for line in process.stdout:
                if on_output:
                    on_output(line.rstrip())
        return process.wait()

    def write_android_json(
        self,
        *,
        package_name: str,
        app_name: str,
        version: str,
        permissions: list[str] | None = None,
        orientation: str = "sensorLandscape",
        update_always: bool = True,
        update_icons: bool = True,
        update_keystores: bool = True,
        store: str = "none",
    ) -> Path:
        json_path = self.project_dir / "android.json"
        data: dict[str, object] = {}
        if json_path.exists():
            try:
                with open(json_path, "r", encoding="utf-8") as reader:
                    data = json.load(reader) or {}
            except Exception:
                data = {}

        perms = permissions or data.get("permissions") or ["VIBRATE", "INTERNET"]
        if isinstance(perms, str):
            perms = [p for p in perms.split() if p]
        perms = list(dict.fromkeys(perms))

        data.update(
            {
                "package": package_name,
                "name": app_name,
                "icon_name": app_name,
                "version": version,
                "permissions": perms,
                "orientation": orientation,
                "store": store,
                "update_always": update_always,
                "update_icons": update_icons,
                "update_keystores": update_keystores,
            }
        )

        json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as writer:
            json.dump(data, writer, ensure_ascii=False, indent=4)

        return json_path

    def clean_dist_dir(self, dist_dir: str) -> Path:
        dist_path = Path(dist_dir).resolve()
        if dist_path.exists():
            shutil.rmtree(dist_path, ignore_errors=True)
        dist_path.mkdir(parents=True, exist_ok=True)
        return dist_path

    def run_distribute(
        self,
        *,
        dist_dir: str,
        on_output: Callable[[str], None] | None = None,
    ) -> bool:
        dist_path = self.clean_dist_dir(dist_dir)
        args = [
            str(self.renpy_exe),
            str(self.sdk_root),
            "distribute",
            "--package",
            "android",
            "--no-archive",
            "--no-update",
            "--packagedest",
            str(dist_path),
            str(self.project_dir),
        ]
        code = self._run_process(args, cwd=str(self.sdk_root), on_output=on_output)
        return code == 0

    def run_runner(
        self,
        args: Iterable[str],
        *,
        on_output: Callable[[str], None] | None = None,
    ) -> bool:
        cmd = [str(self.python_exe), str(self.runner_script), *args]
        code = self._run_process(cmd, cwd=str(self.sdk_root), on_output=on_output)
        return code == 0

    def install_sdk(self, on_output: Callable[[str], None] | None = None) -> bool:
        return self.run_runner(["install_sdk", "--sdk", str(self.sdk_root)], on_output=on_output)

    def generate_keys(
        self,
        *,
        dname: str | None = None,
        on_output: Callable[[str], None] | None = None,
    ) -> bool:
        args = ["generate_keys", "--sdk", str(self.sdk_root), "--project", str(self.project_dir)]
        if dname:
            args.extend(["--dname", dname])
        return self.run_runner(args, on_output=on_output)

    def build_android(
        self,
        *,
        dist_dir: str,
        install: bool = False,
        launch: bool = False,
        on_output: Callable[[str], None] | None = None,
    ) -> bool:
        args = [
            "build",
            "--sdk",
            str(self.sdk_root),
            "--project",
            str(self.project_dir),
            "--dist",
            str(Path(dist_dir).resolve()),
        ]
        if install:
            args.append("--install")
        if launch:
            args.append("--launch")
        return self.run_runner(args, on_output=on_output)

    def list_outputs(self) -> list[Path]:
        if not self.rapt_bin.exists():
            return []
        return sorted(
            [*self.rapt_bin.glob("*.apk")],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

    def copy_outputs(self, dest_dir: str) -> list[Path]:
        dest_path = Path(dest_dir).resolve()
        dest_path.mkdir(parents=True, exist_ok=True)
        outputs = self.list_outputs()
        copied: list[Path] = []
        for src in outputs:
            target = dest_path / src.name
            shutil.copy2(src, target)
            copied.append(target)
        return copied
