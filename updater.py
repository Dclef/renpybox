import argparse
import os
import shutil
import subprocess
import sys
import time
import traceback
import webbrowser
import zipfile
from pathlib import Path


def _message_box(title: str, message: str, *, error: bool = False) -> None:
    if os.name != "nt":
        return

    try:
        import ctypes

        MB_OK = 0x0
        MB_ICONERROR = 0x10
        MB_ICONINFORMATION = 0x40
        flags = MB_OK | (MB_ICONERROR if error else MB_ICONINFORMATION)
        ctypes.windll.user32.MessageBoxW(None, message, title, flags)
    except Exception:
        return


def _wait_for_pid_exit(pid: int, *, timeout_sec: int = 120) -> None:
    if pid <= 0:
        return

    if os.name != "nt":
        deadline = time.time() + max(1, timeout_sec)
        while time.time() < deadline:
            try:
                os.kill(pid, 0)
            except Exception:
                return
            time.sleep(0.2)
        return

    try:
        import ctypes

        SYNCHRONIZE = 0x00100000
        WAIT_OBJECT_0 = 0x0
        WAIT_TIMEOUT = 0x102

        handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if not handle:
            return
        try:
            waited = 0.0
            while waited < timeout_sec:
                res = ctypes.windll.kernel32.WaitForSingleObject(handle, 200)
                if res == WAIT_OBJECT_0:
                    return
                if res != WAIT_TIMEOUT:
                    return
                waited += 0.2
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    except Exception:
        deadline = time.time() + max(1, timeout_sec)
        while time.time() < deadline:
            try:
                os.kill(pid, 0)
            except Exception:
                return
            time.sleep(0.2)


def _safe_extract(zip_file: zipfile.ZipFile, dest_dir: Path) -> None:
    dest_dir_resolved = dest_dir.resolve()
    for member in zip_file.infolist():
        member_path = dest_dir / member.filename
        try:
            member_resolved = member_path.resolve()
        except Exception:
            member_resolved = (dest_dir_resolved / member.filename).resolve()

        if (
            member_resolved != dest_dir_resolved
            and dest_dir_resolved not in member_resolved.parents
        ):
            raise RuntimeError(f"Unsafe path in zip: {member.filename}")
        zip_file.extract(member, dest_dir)


def _rmtree_with_retry(path: Path, *, retries: int = 40, delay_sec: float = 0.25) -> None:
    last_exc: Exception | None = None
    for _ in range(max(1, retries)):
        try:
            if path.exists():
                shutil.rmtree(path, ignore_errors = False)
            return
        except Exception as exc:
            last_exc = exc
            time.sleep(delay_sec)
    if last_exc is not None:
        raise last_exc


def _copy2_with_retry(src: Path, dst: Path, *, retries: int = 40, delay_sec: float = 0.25) -> None:
    last_exc: Exception | None = None
    for _ in range(max(1, retries)):
        try:
            os.makedirs(dst.parent, exist_ok = True)
            shutil.copy2(src, dst)
            return
        except Exception as exc:
            last_exc = exc
            time.sleep(delay_sec)
    if last_exc is not None:
        raise last_exc


def _find_payload_dir(staging_dir: Path, *, exe_name: str) -> Path:
    common_candidates = [
        staging_dir,
        staging_dir / "RenpyBox",
        staging_dir / "dist" / "RenpyBox",
    ]
    for candidate in common_candidates:
        if (candidate / exe_name).is_file():
            return candidate

    try:
        for child in staging_dir.iterdir():
            if child.is_dir() and (child / exe_name).is_file():
                return child
    except Exception:
        pass

    return staging_dir


def apply_update(*, pid: int, zip_path: Path, install_dir: Path, release_url: str | None, restart: bool, exe_name: str) -> None:
    _wait_for_pid_exit(pid, timeout_sec = 120)
    time.sleep(0.5)

    if not zip_path.is_file():
        raise FileNotFoundError(str(zip_path))

    install_dir = install_dir.resolve()
    zip_path = zip_path.resolve()

    log_dir = install_dir / "log"
    try:
        log_dir.mkdir(parents = True, exist_ok = True)
    except Exception:
        pass

    config_candidates = [
        install_dir / "config.json",
        install_dir / "resource" / "config.json",
    ]
    config_backup_pairs: list[tuple[Path, Path]] = []
    for cfg in config_candidates:
        config_backup_pairs.append((cfg, cfg.with_suffix(cfg.suffix + ".bak")))

    for cfg, bak in config_backup_pairs:
        if cfg.is_file():
            try:
                os.makedirs(bak.parent, exist_ok = True)
                _copy2_with_retry(cfg, bak, retries = 10, delay_sec = 0.2)
            except Exception:
                pass

    staging_dir = install_dir / "_update_staging"
    if staging_dir.exists():
        _rmtree_with_retry(staging_dir, retries = 10, delay_sec = 0.2)
    staging_dir.mkdir(parents = True, exist_ok = True)

    try:
        with zipfile.ZipFile(zip_path) as zip_file:
            _safe_extract(zip_file, staging_dir)

        payload_dir = _find_payload_dir(staging_dir, exe_name = exe_name)

        running_exe_path = Path(sys.executable).resolve()
        preserve_dirs = {"input", "output", "log"}
        for item in payload_dir.iterdir():
            if item.name in preserve_dirs:
                continue

            dest = install_dir / item.name
            if item.is_dir():
                if dest.exists():
                    _rmtree_with_retry(dest, retries = 40, delay_sec = 0.25)
                shutil.copytree(item, dest, dirs_exist_ok = False)
            else:
                if item.name.lower() == "config.json":
                    continue
                if str(dest.resolve()).lower() == str(running_exe_path).lower():
                    continue
                _copy2_with_retry(item, dest, retries = 40, delay_sec = 0.25)

        for cfg, bak in config_backup_pairs:
            if bak.is_file():
                try:
                    os.makedirs(cfg.parent, exist_ok = True)
                    _copy2_with_retry(bak, cfg, retries = 10, delay_sec = 0.2)
                except Exception:
                    pass

        try:
            zip_path.unlink()
        except Exception:
            pass

        try:
            _rmtree_with_retry(staging_dir, retries = 10, delay_sec = 0.2)
        except Exception:
            pass

        if restart:
            exe_path = install_dir / exe_name
            if exe_path.is_file():
                subprocess.Popen([str(exe_path)], cwd = str(install_dir))

        if release_url:
            try:
                webbrowser.open(release_url)
            except Exception:
                pass
    finally:
        try:
            if staging_dir.exists():
                _rmtree_with_retry(staging_dir, retries = 3, delay_sec = 0.2)
        except Exception:
            pass


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description = "RenpyBox standalone updater")
    parser.add_argument("--pid", type = int, default = 0)
    parser.add_argument("--zip", dest = "zip_path", required = True)
    parser.add_argument("--install-dir", dest = "install_dir", required = True)
    parser.add_argument("--release-url", dest = "release_url", default = "")
    parser.add_argument("--restart", action = "store_true")
    parser.add_argument("--exe-name", dest = "exe_name", default = "RenpyBox.exe")
    args = parser.parse_args(argv)

    try:
        apply_update(
            pid = int(args.pid),
            zip_path = Path(args.zip_path),
            install_dir = Path(args.install_dir),
            release_url = str(args.release_url).strip() or None,
            restart = bool(args.restart),
            exe_name = str(args.exe_name).strip() or "RenpyBox.exe",
        )
        return 0
    except Exception as exc:
        detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        _message_box("RenpyBox Updater", f"更新失败：\n\n{detail}", error = True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
