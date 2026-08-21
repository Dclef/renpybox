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
from concurrent.futures import ThreadPoolExecutor
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


def _wait_for_pid_exit(pid: int, *, timeout_sec: int = 120) -> bool:
    """等待进程退出。返回 False 表示超时后进程仍在运行（调用方必须中止更新）。"""
    if pid <= 0:
        return True

    if os.name != "nt":
        deadline = time.time() + max(1, timeout_sec)
        while time.time() < deadline:
            try:
                os.kill(pid, 0)
            except Exception:
                return True
            time.sleep(0.2)
        return False

    try:
        import ctypes

        SYNCHRONIZE = 0x00100000
        WAIT_OBJECT_0 = 0x0
        WAIT_TIMEOUT = 0x102

        handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if not handle:
            return True
        try:
            waited = 0.0
            while waited < timeout_sec:
                res = ctypes.windll.kernel32.WaitForSingleObject(handle, 200)
                if res == WAIT_OBJECT_0:
                    return True
                if res != WAIT_TIMEOUT:
                    return True
                waited += 0.2
            return False
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    except Exception:
        deadline = time.time() + max(1, timeout_sec)
        while time.time() < deadline:
            try:
                os.kill(pid, 0)
            except Exception:
                return True
            time.sleep(0.2)
        return False


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
    """计算整个文件的内容哈希（512KB 分块顺序读）。

    更新判定依赖本哈希，必须覆盖全部字节：采样哈希会漏检未采样区的修改。
    """
    try:
        hasher = hashlib.md5(usedforsecurity=False)
        with open(path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        return ""


def _should_update_file(src: Path, dst: Path) -> bool:
    """判断文件是否需要更新。

    只看内容：大小不同即更新，大小相同则全量哈希比较。
    不使用 mtime——copy2 会保留旧构建的时间戳，新构建时间恒更新，
    mtime 快速通道会把内容相同的文件全部判为需复制（已核实的历史缺陷）。
    """
    if not dst.exists():
        return True

    try:
        src_stat = src.stat()
        dst_stat = dst.stat()

        # 大小不同，内容必然不同
        if src_stat.st_size != dst_stat.st_size:
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

    def _zip_member_epoch(member: zipfile.ZipInfo) -> float | None:
        # date_time 是构建机的本地时间元组，按本地时区解释即可；
        # 该时间戳仅用于元数据保真与遥测，不参与更新判定
        try:
            y, mo, d, h, mi, s = member.date_time
            return time.mktime((y, mo, d, h, mi, min(s, 59), 0, 0, -1))
        except Exception:
            return None

    member_epochs = {m.filename: _zip_member_epoch(m) for m in members}

    def _extract_batch(batch: list[zipfile.ZipInfo]) -> None:
        # 每个线程单独打开 ZipFile，避免线程安全问题
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for member in batch:
                if _safe_member_path(member.filename) is None:
                    continue
                extracted = zf.extract(member, dest_dir)
                epoch = member_epochs.get(member.filename)
                if epoch is not None:
                    try:
                        os.utime(extracted, (epoch, epoch))
                    except Exception:
                        pass

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
    total_start = time.perf_counter()
    stage_start = time.perf_counter()
    if not _wait_for_pid_exit(pid, timeout_sec = 120):
        # 此时尚未改动任何文件，中止是干净的
        raise RuntimeError("等待主进程退出超时（120 秒），已中止更新。请关闭 RenpyBox 后重试。")
    wait_pid_sec = time.perf_counter() - stage_start
    time.sleep(0.5)

    if not zip_path.is_file():
        raise FileNotFoundError(str(zip_path))

    install_dir = install_dir.resolve()
    zip_path = zip_path.resolve()

    # 清理上一次自升级 rename-swap 留下的 .old 残留（best-effort）
    for old_dir in (install_dir, install_dir / "_internal"):
        try:
            for leftover in old_dir.glob("*.exe.old"):
                try:
                    leftover.unlink()
                except Exception:
                    pass
        except Exception:
            pass

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
        stage_start = time.perf_counter()
        _parallel_extract(zip_path, staging_dir, max_workers=4)
        extract_sec = time.perf_counter() - stage_start

        payload_dir = _find_payload_dir(staging_dir, exe_name = exe_name)

        running_exe_path = Path(sys.executable).resolve()
        running_exe_path_lower = str(running_exe_path).lower()
        preserve_dirs = {"input", "output", "log"}

        # 收集所有需要处理的文件任务
        stage_start = time.perf_counter()
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

                    copy_tasks.append((src_file, dest_file))
            else:
                if item.name.lower() == "config.json":
                    continue
                dest_file = install_dir / item.name
                new_files.add(Path(item.name))

                copy_tasks.append((item, dest_file))
        collect_sec = time.perf_counter() - stage_start
        
        # 预先创建所有目标目录（避免并行时的竞争）
        dest_dirs: set[Path] = {task[1].parent for task in copy_tasks}
        for d in dest_dirs:
            d.mkdir(parents=True, exist_ok=True)
        
        # 并行复制文件
        updated_count = 0
        bytes_copied = 0

        def _copy_if_needed(task: tuple[Path, Path]) -> tuple[int, int]:
            """返回 (是否更新, 写入字节数)；目标为运行中的 exe 时先 rename-swap 腾位"""
            src, dst = task
            if not _should_update_file(src, dst):
                return (0, 0)
            if str(dst.resolve()).lower() == running_exe_path_lower:
                # Windows 上运行中的 exe 可改名、不可覆盖：先移走旧文件再复制
                try:
                    os.replace(dst, dst.with_suffix(dst.suffix + ".old"))
                except Exception:
                    return (0, 0)
            _copy2_with_retry(src, dst, retries=5, delay_sec=0.05)
            try:
                return (1, dst.stat().st_size)
            except Exception:
                return (1, 0)

        stage_start = time.perf_counter()
        # 根据任务数量选择串行或并行
        if len(copy_tasks) < 30:
            for task in copy_tasks:
                result = _copy_if_needed(task)
                updated_count += result[0]
                bytes_copied += result[1]
            skipped_count += len(copy_tasks) - updated_count
        else:
            with ThreadPoolExecutor(max_workers=8) as executor:
                results = list(executor.map(_copy_if_needed, copy_tasks))
            updated_count = sum(r[0] for r in results)
            bytes_copied = sum(r[1] for r in results)
            skipped_count += len(copy_tasks) - updated_count
        copy_sec = time.perf_counter() - stage_start

        # 清理旧文件（新版本中不存在的文件）
        stage_start = time.perf_counter()
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
        delete_sec = time.perf_counter() - stage_start

        # 写入更新统计到日志
        try:
            log_file = log_dir / "last_update.log"
            with open(log_file, "w", encoding="utf-8") as f:
                f.write(f"Updated: {updated_count} files\n")
                f.write(f"Skipped: {skipped_count} files (unchanged)\n")
                f.write(f"Deleted: {deleted_count} files (obsolete)\n")
                f.write(f"CopiedBytes: {bytes_copied}\n")
                f.write(
                    "StageTimings: "
                    f"wait_pid={wait_pid_sec:.2f}s "
                    f"extract={extract_sec:.2f}s "
                    f"collect={collect_sec:.2f}s "
                    f"copy={copy_sec:.2f}s "
                    f"delete={delete_sec:.2f}s "
                    f"total={time.perf_counter() - total_start:.2f}s\n"
                )
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
