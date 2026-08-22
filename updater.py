import argparse
import hashlib
import json
import os
import shutil
import stat as stat_module
import subprocess
import sys
import time
import traceback
import webbrowser
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from update_path_policy import (
    safe_target,
    safe_target_cached,
    validate_file_paths,
    validate_manifest_paths,
    validate_patch_paths,
    validate_zip_members,
)


# 与 buildtools/update_assets.py 的协议常量保持一致
MANIFEST_NAME = "_update_manifest.json"
PATCH_META_NAME = "_patch_meta.json"
JOURNAL_NAME = "_update_journal.json"
PATCH_FORMAT = "renpybox-patch/1"
MANIFEST_FORMAT = "renpybox-update-manifest/1"


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


def _safe_extract(
    zip_file: zipfile.ZipFile,
    dest_dir: Path,
    *,
    allowed_protocol_paths: tuple[str, ...] = (),
) -> None:
    members = zip_file.infolist()
    dest_root = dest_dir.resolve()
    validate_zip_members(
        members,
        label="update ZIP",
        allowed_protocol_paths=allowed_protocol_paths,
    )
    parent_cache: dict[str, Path] = {}
    for member in members:
        rel = member.filename[:-1] if member.is_dir() else member.filename
        safe_target_cached(
            dest_dir,
            rel,
            label="update ZIP member",
            parent_cache=parent_cache,
            root_resolved=dest_root,
        )
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


def _file_sha256(path: Path, *, chunk_size: int = 524288) -> str:
    """全文件 sha256，供增量协议校验（meta 清单使用 sha256）。"""
    hasher = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        return ""


def _should_update_file(
    src: Path,
    dst: Path,
    *,
    expected_size: int | None = None,
    expected_sha256: str | None = None,
) -> bool:
    """判断文件是否需要更新。

    不使用 mtime——copy2 会保留旧构建的时间戳，新构建时间恒更新，
    mtime 快速通道会把内容相同的文件全部判为需复制（已核实的历史缺陷）。
    新包有 manifest 时只校验安装态目标的 sha256；旧包才回退双边内容哈希。
    """
    if not dst.exists():
        return True

    try:
        src_stat = src.stat()
        dst_stat = dst.stat()

        if expected_size is not None and src_stat.st_size != expected_size:
            # manifest 与 staging 不一致时回退完整内容判断，避免错误跳过。
            expected_size = None
            expected_sha256 = None

        # manifest 的 size 优先；没有 manifest 时仍以源文件为准。
        source_size = src_stat.st_size if expected_size is None else expected_size
        if source_size != dst_stat.st_size:
            return True

        if (
            isinstance(expected_sha256, str)
            and len(expected_sha256) == 64
            and all(char in "0123456789abcdefABCDEF" for char in expected_sha256)
        ):
            # 发布包的 manifest 已经计算过源文件哈希，只需验证安装态目标。
            return _file_sha256(dst).casefold() != expected_sha256.casefold()

        return _file_hash(src) != _file_hash(dst)
    except Exception:
        return True


def _parallel_extract(
    zip_path: Path,
    dest_dir: Path,
    *,
    max_workers: int = 4,
    allowed_protocol_paths: tuple[str, ...] = (),
) -> None:
    """并行解压ZIP文件"""
    with zipfile.ZipFile(zip_path, 'r') as zf:
        members = zf.infolist()

    # 必须在创建任何目录或解压任何文件前校验整个包，不能静默跳过危险条目。
    validate_zip_members(
        members,
        label="update ZIP",
        allowed_protocol_paths=allowed_protocol_paths,
    )

    # 规则校验已确认路径安全；staging 是刚清空的目录，不再对每个条目调用 resolve。
    member_paths = {
        member.filename: dest_dir.joinpath(
            *(member.filename[:-1] if member.is_dir() else member.filename).split("/")
        )
        for member in members
    }

    # 先创建所有目录
    dir_paths: set[Path] = set()
    file_members: list[zipfile.ZipInfo] = []
    for m in members:
        member_path = member_paths[m.filename]
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

    raise RuntimeError(f"Update payload missing required executable: {exe_name}")


def _zip_toplevel_has(zip_path: Path, name: str) -> bool:
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            return name in zf.namelist()
    except Exception:
        return False


def _rel_to_path(
    install_dir: Path,
    rel: str,
    *,
    parent_cache: dict[str, Path] | None = None,
    root_resolved: Path | None = None,
    resolve_target: bool = True,
) -> Path:
    if not resolve_target:
        return safe_target(
            install_dir,
            rel,
            label="patch path",
            resolve_target=False,
        )
    if parent_cache is None:
        return safe_target(
            install_dir,
            rel,
            label="patch path",
            root_resolved=root_resolved,
        )
    return safe_target_cached(
        install_dir,
        rel,
        label="patch path",
        parent_cache=parent_cache,
        root_resolved=root_resolved,
    )


def _atomic_write_json(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding = "utf-8") as writer:
        json.dump(payload, writer, ensure_ascii = False)
    os.replace(tmp, path)


def _ensure_writable(path: Path) -> None:
    """PyInstaller 产物偶见只读属性，替换前先清掉，否则 os.replace 会失败。"""
    try:
        if path.exists() and not os.access(path, os.W_OK):
            os.chmod(path, stat_module.S_IWRITE)
    except Exception:
        pass


def _cleanup_old_executables(install_dir: Path) -> None:
    """清理上一次自升级 rename-swap 留下的 .old 残留。"""
    for old_dir in (install_dir, install_dir / "_internal"):
        try:
            for leftover in old_dir.glob("*.exe.old"):
                try:
                    leftover.unlink()
                except Exception:
                    pass
        except Exception:
            pass


def _read_patch_meta(zip_path: Path) -> dict:
    with zipfile.ZipFile(zip_path, "r") as zf:
        members = zf.infolist()
        if sum(member.filename == PATCH_META_NAME for member in members) != 1:
            raise RuntimeError(f"Patch must contain exactly one {PATCH_META_NAME}")
        meta = json.loads(zf.read(PATCH_META_NAME).decode("utf-8"))
    if not isinstance(meta, dict) or meta.get("format") != PATCH_FORMAT:
        raise RuntimeError("Invalid patch meta format")
    if not isinstance(meta.get("files"), dict) or not isinstance(meta.get("manifest"), dict):
        raise RuntimeError("Invalid patch meta content")
    manifest = meta["manifest"]
    if (
        manifest.get("format") != MANIFEST_FORMAT
        or manifest.get("version") != meta.get("version")
        or not isinstance(manifest.get("files"), dict)
    ):
        raise RuntimeError("Invalid target manifest")
    validate_patch_paths(
        meta,
        members,
        patch_meta_name=PATCH_META_NAME,
        manifest_name=MANIFEST_NAME,
    )
    return meta


def _validate_patch_base_manifest(install_dir: Path, meta: dict) -> None:
    """确认安装态确实是 patch 声明的基线版本。"""
    base_version = str(meta.get("base_version") or "").strip()
    if not base_version:
        raise RuntimeError("Patch is missing base version")

    manifest_path = install_dir / MANIFEST_NAME
    try:
        installed = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            "Patch requires an installed manifest; apply the full package first"
        ) from exc

    if (
        not isinstance(installed, dict)
        or installed.get("format") != MANIFEST_FORMAT
        or installed.get("version") != base_version
        or not isinstance(installed.get("files"), dict)
    ):
        raise RuntimeError(
            f"Patch base version mismatch: expected installed {base_version!r}"
        )
    validate_manifest_paths(
        installed,
        label="installed base manifest",
        reserved_paths=(MANIFEST_NAME, PATCH_META_NAME),
    )


def _apply_patch_update(
    *,
    zip_path: Path,
    install_dir: Path,
    log_dir: Path,
    release_url: str | None,
    restart: bool,
    exe_name: str,
    wait_pid_sec: float,
    total_start: float,
) -> None:
    """增量应用：全部变化文件先就位为 .new（stage），再逐个原子提交（commit）。

    commit 中断后 journal 记录进度，重跑同版本可续传；不做自动回退，
    失败时提示用户改走全量包。
    """
    meta = _read_patch_meta(zip_path)
    _validate_patch_base_manifest(install_dir, meta)
    patch_version = str(meta.get("version") or "")
    patch_files: dict[str, dict] = meta["files"]
    deleted: list[str] = list(meta.get("deleted") or [])

    journal_path = install_dir / JOURNAL_NAME
    manifest_path = install_dir / MANIFEST_NAME
    staging_dir = install_dir / "_update_staging"
    install_root_resolved = install_dir.resolve()
    install_parent_cache: dict[str, Path] = {}

    journal: dict = {}
    try:
        if journal_path.is_file():
            journal = json.loads(journal_path.read_text(encoding = "utf-8"))
    except Exception:
        journal = {}

    journal_staged: list[str] = []
    journal_committed: list[str] = []
    try:
        if journal:
            if not isinstance(journal, dict):
                raise RuntimeError("Invalid update journal")
            raw_staged = journal.get("staged")
            raw_committed = journal.get("committed")
            if not isinstance(raw_staged, list) or not isinstance(raw_committed, list):
                raise RuntimeError("Invalid update journal path lists")
            validate_file_paths(raw_staged, label="journal staged path")
            validate_file_paths(raw_committed, label="journal committed path")
            journal_staged = list(raw_staged)
            journal_committed = list(raw_committed)
    except RuntimeError:
        # journal 是本地恢复提示，不可信路径不得用于任何清理或续传。
        journal = {}
        journal_staged = []
        journal_committed = []

    resumable = (
        isinstance(journal, dict)
        and journal.get("version") == patch_version
        and set(journal_staged) == set(patch_files)
        and set(journal_committed).issubset(patch_files)
    )
    committed: list[str] = journal_committed if resumable else []

    if not resumable:
        # 旧 journal 属于别的版本：连同其 .new 残留一并清理后全新开始
        for rel in journal_staged:
            try:
                stale = _rel_to_path(
                    install_dir,
                    f"{rel}.new",
                    parent_cache=install_parent_cache,
                    root_resolved=install_root_resolved,
                )
                stale.unlink()
            except Exception:
                pass

    # ---- Stage：解压校验、就位 .new、写 journal ----
    stage_start = time.perf_counter()
    if staging_dir.exists():
        _rmtree_with_retry(staging_dir, retries=5, delay_sec=0.1)
    staging_dir.mkdir(parents = True, exist_ok = True)

    _parallel_extract(
        zip_path,
        staging_dir,
        max_workers=4,
        allowed_protocol_paths=(PATCH_META_NAME,),
    )

    staged: list[str] = sorted(patch_files)
    for rel in staged:
        staged_file = _rel_to_path(staging_dir, rel, resolve_target=False)
        if not staged_file.is_file():
            raise RuntimeError(f"Patch file missing in archive: {rel}")
        if _file_sha256(staged_file) != patch_files[rel].get("sha256"):
            raise RuntimeError(f"Patch file checksum mismatch: {rel}")

        new_path = _rel_to_path(
            install_dir,
            f"{rel}.new",
            parent_cache=install_parent_cache,
            root_resolved=install_root_resolved,
        )
        if rel in committed:
            # 续传时已提交项不需要再次复制；异常中断若留下 .new，
            # 在确认目标内容正确后清掉残留，避免成功重试后污染安装目录。
            dest = _rel_to_path(
                install_dir,
                rel,
                parent_cache=install_parent_cache,
                root_resolved=install_root_resolved,
            )
            if dest.is_file() and _file_sha256(dest) == patch_files[rel].get("sha256"):
                try:
                    new_path.unlink(missing_ok=True)
                except Exception as exc:
                    raise RuntimeError(f"Cannot clean committed staging file: {rel}") from exc
                continue
            committed.remove(rel)

        new_path.parent.mkdir(parents = True, exist_ok = True)
        _copy2_with_retry(staged_file, new_path, retries=5, delay_sec=0.05)

    _atomic_write_json(journal_path, {
        "format": PATCH_FORMAT,
        "version": patch_version,
        "staged": staged,
        "committed": committed,
    })
    stage_sec = time.perf_counter() - stage_start

    # ---- Commit：逐文件原子提交，journal 随进度更新 ----
    commit_start = time.perf_counter()
    running_exe_key = os.path.normcase(str(Path(sys.executable).resolve()))
    committed_set = set(committed)
    for rel in staged:
        if rel in committed_set:
            continue

        dest = _rel_to_path(
            install_dir,
            rel,
            parent_cache=install_parent_cache,
            root_resolved=install_root_resolved,
        )
        new_path = _rel_to_path(
            install_dir,
            f"{rel}.new",
            parent_cache=install_parent_cache,
            root_resolved=install_root_resolved,
        )
        if not new_path.is_file():
            raise RuntimeError(f"Staged file lost before commit: {rel}")

        if os.path.normcase(str(dest)) == running_exe_key:
            # Windows 上运行中的 exe 可改名不可覆盖：先移走旧文件
            try:
                os.replace(dest, dest.with_name(dest.name + ".old"))
            except Exception as exc:
                raise RuntimeError(f"Cannot swap running updater file: {rel}") from exc

        _ensure_writable(dest)
        try:
            os.replace(new_path, dest)
        except Exception as exc:
            raise RuntimeError(f"Commit failed at {rel}: {exc}") from exc

        committed.append(rel)
        committed_set.add(rel)
        _atomic_write_json(journal_path, {
            "format": PATCH_FORMAT,
            "version": patch_version,
            "staged": staged,
            "committed": committed,
        })
    commit_sec = time.perf_counter() - commit_start

    # ---- 收尾：删除清单、installed manifest、清理 ----
    deleted_count = 0
    for rel in deleted:
        target = _rel_to_path(
            install_dir,
            rel,
            parent_cache=install_parent_cache,
            root_resolved=install_root_resolved,
        )
        if not target.exists():
            continue
        try:
            _ensure_writable(target)
            target.unlink()
            deleted_count += 1
        except Exception as exc:
            # 保留 journal 和 .new，下一次可从提交进度继续，不能把目标
            # manifest 写成新版本而留下旧文件。
            raise RuntimeError(f"Delete failed at {rel}: {exc}") from exc

    _atomic_write_json(manifest_path, meta["manifest"])
    try:
        journal_path.unlink()
    except Exception:
        pass

    try:
        log_file = log_dir / "last_update.log"
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(f"Patch: {patch_version} (base {meta.get('base_version')})\n")
            f.write(f"Applied: {len(staged)} files\n")
            f.write(f"Deleted: {deleted_count} files (obsolete)\n")
            f.write(
                "StageTimings: "
                f"stage={stage_sec:.2f}s commit={commit_sec:.2f}s "
                f"total={time.perf_counter() - total_start:.2f}s\n"
            )
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

    log_dir = install_dir / "log"

    # 增量包分流：顶层带 _patch_meta.json 走 patch 路径（两阶段原子应用），
    # 其余走下方全量路径
    if _zip_toplevel_has(zip_path, PATCH_META_NAME):
        patch_meta = _read_patch_meta(zip_path)
        _validate_patch_base_manifest(install_dir.resolve(), patch_meta)
        _cleanup_old_executables(install_dir)
        try:
            log_dir.mkdir(parents = True, exist_ok = True)
        except Exception:
            pass
        _apply_patch_update(
            zip_path = zip_path,
            install_dir = install_dir,
            log_dir = log_dir,
            release_url = release_url,
            restart = restart,
            exe_name = exe_name,
            wait_pid_sec = wait_pid_sec,
            total_start = total_start,
        )
        return

    # 全量包同样先整体 fail closed，避免危险条目触发 staging 清理或部分解压。
    with zipfile.ZipFile(zip_path, "r") as zf:
        validate_zip_members(
            zf.infolist(),
            label="full update ZIP",
            allowed_protocol_paths=(MANIFEST_NAME,),
        )

    config_candidates = [
        install_dir / "config.json",
        install_dir / "resource" / "config.json",
    ]
    config_backup_pairs: list[tuple[Path, Path]] = []
    for cfg in config_candidates:
        config_backup_pairs.append((cfg, cfg.with_suffix(cfg.suffix + ".bak")))

    staging_dir = install_dir / "_update_staging"
    if staging_dir.exists():
        _rmtree_with_retry(staging_dir, retries=5, delay_sec=0.1)
    staging_dir.mkdir(parents = True, exist_ok = True)

    try:
        # 使用并行解压（大幅提速）
        stage_start = time.perf_counter()
        _parallel_extract(
            zip_path,
            staging_dir,
            max_workers=4,
            allowed_protocol_paths=(MANIFEST_NAME,),
        )
        extract_sec = time.perf_counter() - stage_start

        payload_dir = _find_payload_dir(staging_dir, exe_name = exe_name)

        embedded_manifest_data: dict | None = None
        embedded_manifest = staging_dir / MANIFEST_NAME
        try:
            if embedded_manifest.is_file():
                candidate_manifest = json.loads(
                    embedded_manifest.read_text(encoding="utf-8")
                )
                if (
                    isinstance(candidate_manifest, dict)
                    and candidate_manifest.get("format") == MANIFEST_FORMAT
                ):
                    validate_manifest_paths(
                        candidate_manifest,
                        label="full update manifest",
                        reserved_paths=(MANIFEST_NAME, PATCH_META_NAME),
                    )
                    embedded_manifest_data = candidate_manifest
        except (OSError, UnicodeError, json.JSONDecodeError):
            # 兼容旧全量包：无可读 manifest 时仍按全量更新，但不写安装态。
            embedded_manifest_data = None

        # payload 结构确认后才允许触碰安装态、恢复件与用户配置备份。
        _cleanup_old_executables(install_dir)

        try:
            log_dir.mkdir(parents = True, exist_ok = True)
        except Exception:
            pass

        for cfg, bak in config_backup_pairs:
            if cfg.is_file():
                try:
                    bak.parent.mkdir(parents=True, exist_ok=True)
                    _copy2_with_retry(cfg, bak, retries=5, delay_sec=0.05)
                except Exception:
                    pass

        running_exe_path = Path(sys.executable).resolve()
        running_exe_path_key = os.path.normcase(str(running_exe_path))
        install_root_resolved = install_dir
        install_parent_cache: dict[str, Path] = {}
        preserve_dirs = {"input", "output", "log"}
        manifest_files = (
            embedded_manifest_data.get("files", {})
            if isinstance(embedded_manifest_data, dict)
            else {}
        )

        # 收集所有需要处理的文件任务
        stage_start = time.perf_counter()
        copy_tasks: list[tuple[Path, Path, dict | None]] = []  # (src, dst, manifest entry)
        new_files: set[Path] = set()
        skipped_count = 0

        for item in payload_dir.iterdir():
            if item.name in preserve_dirs:
                continue

            if item.is_dir():
                for src_file in item.rglob("*"):
                    if not src_file.is_file():
                        continue

                    rel_to_payload = src_file.relative_to(payload_dir)
                    rel_text = rel_to_payload.as_posix()
                    dest_file = _rel_to_path(
                        install_dir,
                        rel_text,
                        parent_cache=install_parent_cache,
                        root_resolved=install_root_resolved,
                    )
                    new_files.add(rel_to_payload)

                    entry = manifest_files.get(rel_text)
                    copy_tasks.append(
                        (src_file, dest_file, entry if isinstance(entry, dict) else None)
                    )
            else:
                if item.name.lower() == "config.json":
                    continue
                # 更新协议元数据只供本程序读取，不落入安装目录
                if item.name in {MANIFEST_NAME, PATCH_META_NAME}:
                    continue
                dest_file = _rel_to_path(
                    install_dir,
                    item.name,
                    parent_cache=install_parent_cache,
                    root_resolved=install_root_resolved,
                )
                rel_text = item.name
                new_files.add(Path(rel_text))

                entry = manifest_files.get(rel_text)
                copy_tasks.append(
                    (item, dest_file, entry if isinstance(entry, dict) else None)
                )
        collect_sec = time.perf_counter() - stage_start
        
        # 预先创建所有目标目录（避免并行时的竞争）
        dest_dirs: set[Path] = {task[1].parent for task in copy_tasks}
        for d in dest_dirs:
            d.mkdir(parents=True, exist_ok=True)
        
        # 并行复制文件
        updated_count = 0
        bytes_copied = 0

        def _copy_if_needed(task: tuple[Path, Path, dict | None]) -> tuple[int, int]:
            """返回 (是否更新, 写入字节数)；目标为运行中的 exe 时先 rename-swap 腾位"""
            src, dst, manifest_entry = task
            expected_size = (
                manifest_entry.get("size")
                if isinstance(manifest_entry, dict)
                and isinstance(manifest_entry.get("size"), int)
                else None
            )
            expected_sha256 = (
                manifest_entry.get("sha256")
                if isinstance(manifest_entry, dict)
                else None
            )
            if not _should_update_file(
                src,
                dst,
                expected_size=expected_size,
                expected_sha256=expected_sha256,
            ):
                return (0, 0)
            if os.path.normcase(str(dst)) == running_exe_path_key:
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
        internal_dir = _rel_to_path(
            install_dir,
            "_internal",
            parent_cache=install_parent_cache,
            root_resolved=install_root_resolved,
        )
        if internal_dir.exists():
            files_to_delete: list[Path] = []
            protected_suffixes = {".json", ".log", ".bak"}
            
            for old_file in internal_dir.rglob("*"):
                if not old_file.is_file():
                    continue
                try:
                    rel_to_install = old_file.relative_to(install_dir).as_posix()
                    old_file = _rel_to_path(
                        install_dir,
                        rel_to_install,
                        parent_cache=install_parent_cache,
                        root_resolved=install_root_resolved,
                    )
                except (RuntimeError, ValueError):
                    # 既有 junction/symlink 指向安装目录外时绝不跟随删除。
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

        # 全量包若内嵌 manifest（新版发布起），把安装态 manifest 落盘，
        # 之后的版本即可走增量更新；旧包没有则跳过（下次仍走全量）
        if embedded_manifest_data is not None:
            try:
                _atomic_write_json(install_dir / MANIFEST_NAME, embedded_manifest_data)
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
