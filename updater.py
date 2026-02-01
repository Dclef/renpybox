import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import time
import traceback
import webbrowser
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional


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


def _ensure_output_streams() -> None:
    if getattr(sys, "stdout", None) is None:
        try:
            sys.stdout = open(os.devnull, "w", encoding = "utf-8")
        except Exception:
            pass
    if getattr(sys, "stderr", None) is None:
        try:
            sys.stderr = open(os.devnull, "w", encoding = "utf-8")
        except Exception:
            pass


class _UpdaterArgumentParser(argparse.ArgumentParser):
    def _print_message(self, message: str | None, file = None) -> None:
        if not message:
            return
        _message_box("RenpyBox Updater", message)

    def error(self, message: str) -> None:
        self.exit(2, f"{message}\n\nRenpyBoxUpdater 是自动更新组件，请不要直接运行。")


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


def _file_hash(path: Path, *, chunk_size: int = 262144) -> str:
    """快速计算文件哈希值（256KB缓冲区）"""
    try:
        hasher = hashlib.md5(usedforsecurity=False)
        with open(path, "rb") as f:
            while chunk := f.read(chunk_size):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        return ""


def _should_update_file(src: Path, dst: Path) -> bool:
    """判断文件是否需要更新"""
    if not dst.exists():
        return True
    
    try:
        src_stat = src.stat()
        dst_stat = dst.stat()
        
        # 快速检查：大小不同
        if src_stat.st_size != dst_stat.st_size:
            return True
        
        # 小文件：直接比较内容（比哈希更快）
        if src_stat.st_size < 8192:
            return src.read_bytes() != dst.read_bytes()
        
        # 大文件：比较哈希
        return _file_hash(src) != _file_hash(dst)
    except Exception:
        return True


def _parallel_extract(zip_path: Path, dest_dir: Path, *, max_workers: int = 4) -> None:
    """并行解压ZIP文件"""
    with zipfile.ZipFile(zip_path, 'r') as zf:
        members = zf.infolist()
        
        def extract_member(member: zipfile.ZipInfo) -> None:
            # 安全检查
            member_path = dest_dir / member.filename
            try:
                resolved = member_path.resolve()
                if dest_dir.resolve() not in resolved.parents and resolved != dest_dir.resolve():
                    return  # 跳过不安全路径
            except Exception:
                return
            zf.extract(member, dest_dir)
        
        # 小文件数量少时用单线程，避免开销
        if len(members) < 50:
            for m in members:
                extract_member(m)
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                list(executor.map(extract_member, members))


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
        # 使用并行解压（大幅提速）
        _parallel_extract(zip_path, staging_dir, max_workers=4)

        payload_dir = _find_payload_dir(staging_dir, exe_name = exe_name)

        running_exe_path = Path(sys.executable).resolve()
        preserve_dirs = {"input", "output", "log"}
        updated_count = 0
        skipped_count = 0
        deleted_count = 0
        
        # 收集新版本中的所有文件路径（用于清理旧文件）
        new_files: set[Path] = set()
        for item in payload_dir.iterdir():
            if item.name in preserve_dirs:
                continue
            if item.is_dir():
                for src_file in item.rglob("*"):
                    if src_file.is_file():
                        rel = src_file.relative_to(payload_dir)
                        new_files.add(rel)
            elif item.name.lower() != "config.json":
                new_files.add(Path(item.name))
        
        # 增量更新文件
        for item in payload_dir.iterdir():
            if item.name in preserve_dirs:
                continue

            dest = install_dir / item.name
            if item.is_dir():
                for src_file in item.rglob("*"):
                    if not src_file.is_file():
                        continue
                    
                    rel_path = src_file.relative_to(item)
                    dest_file = dest / rel_path
                    
                    if _should_update_file(src_file, dest_file):
                        _copy2_with_retry(src_file, dest_file, retries = 20, delay_sec = 0.15)
                        updated_count += 1
                    else:
                        skipped_count += 1
            else:
                if item.name.lower() == "config.json":
                    continue
                if str(dest.resolve()).lower() == str(running_exe_path).lower():
                    continue
                
                if _should_update_file(item, dest):
                    _copy2_with_retry(item, dest, retries = 20, delay_sec = 0.15)
                    updated_count += 1
                else:
                    skipped_count += 1
        
        # 清理旧文件（新版本中不存在的文件）
        internal_dir = install_dir / "_internal"
        if internal_dir.exists():
            for old_file in internal_dir.rglob("*"):
                if not old_file.is_file():
                    continue
                rel = Path("_internal") / old_file.relative_to(internal_dir)
                # 保护更新器和配置文件
                if "updater" in old_file.name.lower():
                    continue
                if old_file.suffix.lower() in {".json", ".log", ".bak"}:
                    continue
                if rel not in new_files:
                    try:
                        old_file.unlink()
                        deleted_count += 1
                    except Exception:
                        pass
        
        # 写入更新统计到日志
        try:
            log_file = log_dir / "last_update.log"
            with open(log_file, "w", encoding="utf-8") as f:
                f.write(f"Updated: {updated_count} files\n")
                f.write(f"Skipped: {skipped_count} files (unchanged)\n")
                f.write(f"Deleted: {deleted_count} files (obsolete)\n")
        except Exception:
            pass

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
    try:
        _ensure_output_streams()
        if not argv or any(a in {"-h", "--help"} for a in argv):
            _message_box(
                "RenpyBox Updater",
                "RenpyBoxUpdater 是自动更新组件，请在 RenpyBox 内点击“更新”使用。\n\n"
                "现在可以直接关闭此窗口。",
            )
            return 0

        parser = _UpdaterArgumentParser(description = "RenpyBox standalone updater")
        parser.add_argument("--pid", type = int, default = 0)
        parser.add_argument("--zip", dest = "zip_path", required = True)
        parser.add_argument("--install-dir", dest = "install_dir", required = True)
        parser.add_argument("--release-url", dest = "release_url", default = "")
        parser.add_argument("--restart", action = "store_true")
        parser.add_argument("--exe-name", dest = "exe_name", default = "RenpyBox.exe")
        args = parser.parse_args(argv)

        apply_update(
            pid = int(args.pid),
            zip_path = Path(args.zip_path),
            install_dir = Path(args.install_dir),
            release_url = str(args.release_url).strip() or None,
            restart = bool(args.restart),
            exe_name = str(args.exe_name).strip() or "RenpyBox.exe",
        )
        return 0
    except SystemExit as exc:
        try:
            return int(getattr(exc, "code", 0) or 0)
        except Exception:
            return 1
    except Exception as exc:
        detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        _message_box("RenpyBox Updater", f"更新失败：\n\n{detail}", error = True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
