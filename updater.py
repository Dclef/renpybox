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


def _rmtree_with_retry(path: Path, *, retries: int = 10, delay_sec: float = 0.1) -> None:
    """带重试的删除目录"""
    for i in range(max(1, retries)):
        try:
            if path.exists():
                shutil.rmtree(path, ignore_errors=False)
            return
        except Exception as exc:
            if i == retries - 1:
                raise exc
            time.sleep(delay_sec * (1 + i * 0.5))  # 渐进延迟


def _copy2_with_retry(src: Path, dst: Path, *, retries: int = 5, delay_sec: float = 0.05) -> None:
    """带重试的文件复制（优化版）"""
    for i in range(max(1, retries)):
        try:
            # 仅在首次尝试时创建目录
            if i == 0:
                dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            return
        except Exception as exc:
            if i == retries - 1:
                raise exc
            time.sleep(delay_sec * (1 + i))  # 渐进延迟


def _file_hash(path: Path, *, chunk_size: int = 524288) -> str:
    """快速计算文件哈希值（512KB缓冲区，使用更快的xxhash风格）"""
    try:
        # 使用 md5 但只取部分数据来加速（首尾+中间采样）
        file_size = path.stat().st_size
        hasher = hashlib.md5(usedforsecurity=False)
        
        with open(path, "rb") as f:
            # 小于1MB直接全读
            if file_size < 1048576:
                hasher.update(f.read())
            else:
                # 读取首部512KB
                hasher.update(f.read(chunk_size))
                # 读取中间512KB
                mid_pos = file_size // 2
                f.seek(mid_pos)
                hasher.update(f.read(chunk_size))
                # 读取尾部512KB
                f.seek(max(0, file_size - chunk_size))
                hasher.update(f.read(chunk_size))
                # 加入文件大小作为额外校验
                hasher.update(str(file_size).encode())
        
        return hasher.hexdigest()
    except Exception:
        return ""


def _should_update_file(src: Path, dst: Path) -> bool:
    """判断文件是否需要更新（优化版）"""
    if not dst.exists():
        return True
    
    try:
        src_stat = src.stat()
        dst_stat = dst.stat()
        
        # 快速检查：大小不同，必须更新
        if src_stat.st_size != dst_stat.st_size:
            return True
        
        # 小文件（<32KB）：直接比较内容
        if src_stat.st_size < 32768:
            return src.read_bytes() != dst.read_bytes()
        
        # 中等文件（<1MB）：比较修改时间，如果源文件更新则更新
        if src_stat.st_size < 1048576:
            if src_stat.st_mtime > dst_stat.st_mtime + 1:
                return True
            return src.read_bytes() != dst.read_bytes()
        
        # 大文件：先比较修改时间，再用采样哈希
        if src_stat.st_mtime > dst_stat.st_mtime + 1:
            return True
        
        return _file_hash(src) != _file_hash(dst)
    except Exception:
        return True


def _parallel_extract(zip_path: Path, dest_dir: Path, *, max_workers: int = 4) -> None:
    """并行解压ZIP文件"""
    with zipfile.ZipFile(zip_path, 'r') as zf:
        members = zf.infolist()
    
    dest_root = dest_dir.resolve()

    def _safe_member_path(member_name: str) -> Path | None:
        member_path = dest_dir / member_name
        try:
            resolved = member_path.resolve()
            if dest_root not in resolved.parents and resolved != dest_root:
                return None
        except Exception:
            return None
        return member_path

    # 先创建所有目录
    dir_paths: set[Path] = set()
    file_members: list[zipfile.ZipInfo] = []
    for m in members:
        member_path = _safe_member_path(m.filename)
        if member_path is None:
            continue
        if m.is_dir():
            dir_paths.add(member_path)
        else:
            file_members.append(m)
            if member_path.parent != dest_dir:
                dir_paths.add(member_path.parent)
    
    for d in sorted(dir_paths, key=lambda p: len(p.parts)):
        d.mkdir(parents=True, exist_ok=True)

    def _extract_batch(batch: list[zipfile.ZipInfo]) -> None:
        # 每个线程单独打开 ZipFile，避免线程安全问题
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for member in batch:
                if _safe_member_path(member.filename) is None:
                    continue
                zf.extract(member, dest_dir)

    # 小文件数量少时用单线程
    if len(file_members) < 50:
        _extract_batch(file_members)
    else:
        # 分批并行解压
        batch_size = (len(file_members) + max_workers - 1) // max_workers
        batches = [file_members[i:i + batch_size] for i in range(0, len(file_members), batch_size)]
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            list(executor.map(_extract_batch, batches))


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
                bak.parent.mkdir(parents=True, exist_ok=True)
                _copy2_with_retry(cfg, bak, retries=5, delay_sec=0.05)
            except Exception:
                pass

    staging_dir = install_dir / "_update_staging"
    if staging_dir.exists():
        _rmtree_with_retry(staging_dir, retries=5, delay_sec=0.1)
    staging_dir.mkdir(parents = True, exist_ok = True)

    try:
        # 使用并行解压（大幅提速）
        _parallel_extract(zip_path, staging_dir, max_workers=4)

        payload_dir = _find_payload_dir(staging_dir, exe_name = exe_name)

        running_exe_path = Path(sys.executable).resolve()
        running_exe_path_lower = str(running_exe_path).lower()
        preserve_dirs = {"input", "output", "log"}
        updater_names = {"renpyboxupdater.exe", "updater.exe"}
        
        # 收集所有需要处理的文件任务
        copy_tasks: list[tuple[Path, Path]] = []  # (src, dst)
        new_files: set[Path] = set()
        skipped_count = 0
        
        for item in payload_dir.iterdir():
            if item.name in preserve_dirs:
                continue
            
            if item.is_dir():
                for src_file in item.rglob("*"):
                    if not src_file.is_file():
                        continue
                    
                    rel_path = src_file.relative_to(item)
                    dest_file = (install_dir / item.name / rel_path)
                    rel_to_payload = src_file.relative_to(payload_dir)
                    new_files.add(rel_to_payload)
                    
                    # 跳过更新器自身
                    if str(dest_file.resolve()).lower() == running_exe_path_lower:
                        skipped_count += 1
                        continue
                    if dest_file.name.lower() in updater_names:
                        skipped_count += 1
                        continue
                    
                    copy_tasks.append((src_file, dest_file))
            else:
                if item.name.lower() == "config.json":
                    continue
                dest_file = install_dir / item.name
                new_files.add(Path(item.name))
                
                if str(dest_file.resolve()).lower() == running_exe_path_lower:
                    continue
                if item.name.lower() in updater_names:
                    continue
                
                copy_tasks.append((item, dest_file))
        
        # 预先创建所有目标目录（避免并行时的竞争）
        dest_dirs: set[Path] = {task[1].parent for task in copy_tasks}
        for d in dest_dirs:
            d.mkdir(parents=True, exist_ok=True)
        
        # 并行复制文件
        updated_count = 0
        
        def _copy_if_needed(task: tuple[Path, Path]) -> int:
            """返回 1 如果更新了文件，否则返回 0"""
            src, dst = task
            if _should_update_file(src, dst):
                _copy2_with_retry(src, dst, retries=5, delay_sec=0.05)
                return 1
            return 0
        
        # 根据任务数量选择串行或并行
        if len(copy_tasks) < 30:
            for task in copy_tasks:
                updated_count += _copy_if_needed(task)
            skipped_count += len(copy_tasks) - updated_count
        else:
            with ThreadPoolExecutor(max_workers=8) as executor:
                results = list(executor.map(_copy_if_needed, copy_tasks))
            updated_count = sum(results)
            skipped_count += len(copy_tasks) - updated_count
        
        # 清理旧文件（新版本中不存在的文件）
        deleted_count = 0
        internal_dir = install_dir / "_internal"
        if internal_dir.exists():
            files_to_delete: list[Path] = []
            protected_suffixes = {".json", ".log", ".bak"}
            
            for old_file in internal_dir.rglob("*"):
                if not old_file.is_file():
                    continue
                rel = Path("_internal") / old_file.relative_to(internal_dir)
                
                # 保护更新器和配置文件
                if "updater" in old_file.name.lower():
                    continue
                if old_file.suffix.lower() in protected_suffixes:
                    continue
                if rel not in new_files:
                    files_to_delete.append(old_file)
            
            # 批量删除
            for f in files_to_delete:
                try:
                    f.unlink()
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
                    cfg.parent.mkdir(parents=True, exist_ok=True)
                    _copy2_with_retry(bak, cfg, retries=5, delay_sec=0.05)
                except Exception:
                    pass

        try:
            zip_path.unlink()
        except Exception:
            pass

        try:
            _rmtree_with_retry(staging_dir, retries=5, delay_sec=0.1)
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
