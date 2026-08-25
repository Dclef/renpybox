import hashlib
import json
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import pytest

import updater
from buildtools.update_assets import build_manifest, build_patch


# ---------- _should_update_file / _file_hash ----------

def test_should_update_file_missing_dst(tmp_path: Path) -> None:
    src = tmp_path / "src.bin"
    src.write_bytes(b"hello")
    assert updater._should_update_file(src, tmp_path / "dst.bin") is True


def test_should_update_file_size_mismatch(tmp_path: Path) -> None:
    src = tmp_path / "src.bin"
    dst = tmp_path / "dst.bin"
    src.write_bytes(b"hello")
    dst.write_bytes(b"hey")
    assert updater._should_update_file(src, dst) is True


def test_should_update_file_same_content_same_mtime(tmp_path: Path) -> None:
    src = tmp_path / "src.bin"
    dst = tmp_path / "dst.bin"
    src.write_bytes(b"hello")
    dst.write_bytes(b"hello")
    assert updater._should_update_file(src, dst) is False


def test_should_update_file_same_content_newer_src_mtime(tmp_path: Path) -> None:
    # 回归用例：copy2 保留旧构建时间戳，新构建时间恒更新。
    # 旧实现的 mtime 快速通道会把内容相同的文件判为需复制。
    src = tmp_path / "src.bin"
    dst = tmp_path / "dst.bin"
    src.write_bytes(b"hello")
    dst.write_bytes(b"hello")
    past = time.time() - 3600
    os.utime(dst, (past, past))
    os.utime(src, (time.time() + 3600, time.time() + 3600))
    assert updater._should_update_file(src, dst) is False


def test_should_update_file_same_size_different_content(tmp_path: Path) -> None:
    src = tmp_path / "src.bin"
    dst = tmp_path / "dst.bin"
    src.write_bytes(b"hello")
    dst.write_bytes(b"world")
    assert updater._should_update_file(src, dst) is True


def test_should_update_file_uses_manifest_hash_without_hashing_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    src = tmp_path / "src.bin"
    dst = tmp_path / "dst.bin"
    src.write_bytes(b"same content")
    dst.write_bytes(b"same content")
    expected_sha256 = hashlib.sha256(src.read_bytes()).hexdigest()

    def fail_legacy_hash(*args, **kwargs):
        raise AssertionError("manifest path must not use the legacy double hash")

    monkeypatch.setattr(updater, "_file_hash", fail_legacy_hash)
    assert updater._should_update_file(
        src,
        dst,
        expected_size=src.stat().st_size,
        expected_sha256=expected_sha256,
    ) is False

    dst.write_bytes(b"changed text")
    assert updater._should_update_file(
        src,
        dst,
        expected_size=src.stat().st_size,
        expected_sha256=expected_sha256,
    ) is True


def test_file_hash_detects_change_outside_sampled_region(tmp_path: Path) -> None:
    # 回归用例：旧实现对 >1MB 文件只采样首/中/尾 512KB，未采样区的修改会漏检。
    payload = b"a" * (2 * 1024 * 1024)
    a = tmp_path / "a.bin"
    b = tmp_path / "b.bin"
    a.write_bytes(payload)
    b.write_bytes(payload[:700_000] + b"X" + payload[700_001:])
    assert updater._file_hash(a) != updater._file_hash(b)
    assert updater._file_hash(a) == updater._file_hash(a)


# ---------- _parallel_extract ----------

def test_parallel_extract_restores_zip_mtime(tmp_path: Path) -> None:
    zip_path = tmp_path / "pkg.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        info = zipfile.ZipInfo("nested/file.txt", date_time=(2020, 1, 2, 3, 4, 5))
        zf.writestr(info, "content")

    dest = tmp_path / "staging"
    dest.mkdir()
    updater._parallel_extract(zip_path, dest, max_workers=2)

    extracted = dest / "nested" / "file.txt"
    assert extracted.read_text(encoding="utf-8") == "content"
    expected = time.mktime((2020, 1, 2, 3, 4, 5, 0, 0, -1))
    assert abs(extracted.stat().st_mtime - expected) < 2


# ---------- _wait_for_pid_exit ----------

def test_wait_for_pid_exit_non_positive_pid() -> None:
    assert updater._wait_for_pid_exit(0) is True
    assert updater._wait_for_pid_exit(-1) is True


def test_wait_for_pid_exit_timeout_on_running_process() -> None:
    # 等待自身：进程不会退出，超时后必须返回 False（fail-closed）
    assert updater._wait_for_pid_exit(os.getpid(), timeout_sec=1) is False


def test_wait_for_pid_exit_returns_true_for_exited_process() -> None:
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait(timeout=30)
    assert updater._wait_for_pid_exit(proc.pid, timeout_sec=10) is True


# ---------- apply_update 端到端 ----------

def _build_payload_zip(zip_path: Path, *, files: dict[str, bytes]) -> None:
    with zipfile.ZipFile(zip_path, "w") as zf:
        for rel, data in files.items():
            info = zipfile.ZipInfo(rel, date_time=(2021, 6, 1, 12, 0, 0))
            zf.writestr(info, data)


def test_full_update_rejects_payload_without_main_executable(tmp_path: Path) -> None:
    install_dir = tmp_path / "install"
    internal = install_dir / "_internal"
    internal.mkdir(parents=True)
    existing = internal / "existing.bin"
    existing.write_bytes(b"KEEP")
    config = install_dir / "config.json"
    config.write_text('{"keep":true}', encoding="utf-8")
    recovery = install_dir / "RenpyBoxUpdater2.exe.old"
    recovery.write_bytes(b"RECOVERY")
    manifest = install_dir / updater.MANIFEST_NAME
    manifest.write_text('{"version":"v1.0.0"}', encoding="utf-8")
    zip_path = tmp_path / "symbols.zip"
    _build_payload_zip(zip_path, files={"symbols/debug.pdb": b"DEBUG"})

    with pytest.raises(RuntimeError, match="missing required executable"):
        updater.apply_update(
            pid=0,
            zip_path=zip_path,
            install_dir=install_dir,
            release_url=None,
            restart=False,
            exe_name="RenpyBox.exe",
        )

    assert existing.read_bytes() == b"KEEP"
    assert manifest.read_text(encoding="utf-8") == '{"version":"v1.0.0"}'
    assert config.read_text(encoding="utf-8") == '{"keep":true}'
    assert not (install_dir / "config.json.bak").exists()
    assert recovery.read_bytes() == b"RECOVERY"
    assert not (install_dir / "log").exists()
    assert zip_path.is_file()


def test_patch_meta_rejects_deleted_escape_before_install(tmp_path: Path) -> None:
    meta = {
        "format": updater.PATCH_FORMAT,
        "version": "v2.0.0",
        "base_version": "v1.0.0",
        "files": {},
        "deleted": ["../victim.txt"],
        "manifest": {
            "format": updater.MANIFEST_FORMAT,
            "version": "v2.0.0",
            "files": {},
        },
    }
    zip_path = tmp_path / "unsafe.patch.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(updater.PATCH_META_NAME, json.dumps(meta))

    install_dir = tmp_path / "install"
    install_dir.mkdir()
    with pytest.raises(RuntimeError):
        updater.apply_update(
            pid=0,
            zip_path=zip_path,
            install_dir=install_dir,
            release_url=None,
            restart=False,
            exe_name="RenpyBox.exe",
        )

    assert not (tmp_path / "victim.txt").exists()
    assert not (install_dir / updater.JOURNAL_NAME).exists()


@pytest.mark.parametrize(
    "reserved_member",
    [
        "_update_journal.json",
        "_UPDATE_JOURNAL.JSON",
        "_update_staging/escape.bin",
    ],
)
def test_full_update_rejects_protocol_namespace_before_side_effects(
    tmp_path: Path,
    reserved_member: str,
) -> None:
    """协议保留名不能伪装成全量载荷写入安装目录。"""
    install_dir = tmp_path / "install"
    install_dir.mkdir()
    sentinel = install_dir / "sentinel.txt"
    sentinel.write_text("keep", encoding="utf-8")
    zip_path = tmp_path / "malicious.zip"
    _build_payload_zip(
        zip_path,
        files={"RenpyBox.exe": b"MAIN", reserved_member: b"BAD"},
    )

    with pytest.raises(RuntimeError, match="reserved protocol"):
        updater.apply_update(
            pid=0,
            zip_path=zip_path,
            install_dir=install_dir,
            release_url=None,
            restart=False,
            exe_name="RenpyBox.exe",
        )

    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert not (install_dir / "_update_staging").exists()
    assert zip_path.is_file()


def test_apply_update_end_to_end(tmp_path: Path) -> None:
    install_dir = tmp_path / "install"
    install_dir.mkdir()
    zip_path = tmp_path / "update.zip"

    # 预置安装目录：RenpyBox.exe、未变化文件、将被更新的文件、
    # 将被删除的 obsolete 文件、需要保留的 config 与用户目录
    (install_dir / "RenpyBox.exe").write_bytes(b"OLD-MAIN")
    unchanged = install_dir / "_internal" / "same.txt"
    unchanged.parent.mkdir()
    unchanged.write_bytes(b"UNCHANGED")
    old_mtime = unchanged.stat().st_mtime
    changed = install_dir / "_internal" / "changed.txt"
    changed.write_bytes(b"OLD-CONTENT")
    obsolete = install_dir / "_internal" / "obsolete.txt"
    obsolete.write_bytes(b"TO-BE-DELETED")
    (install_dir / "config.json").write_text('{"keep": true}', encoding="utf-8")
    for name in ("input", "output", "log"):
        (install_dir / name).mkdir()
        (install_dir / name / "user.txt").write_text("user data", encoding="utf-8")

    _build_payload_zip(zip_path, files={
        "RenpyBox.exe": b"OLD-MAIN",
        "_internal/same.txt": b"UNCHANGED",
        "_internal/changed.txt": b"NEW-CONTENT",
        "_internal/RenpyBoxUpdater2.exe": b"NEW-UPDATER",
    })

    updater.apply_update(
        pid=0,
        zip_path=zip_path,
        install_dir=install_dir,
        release_url=None,
        restart=False,
        exe_name="RenpyBox.exe",
    )

    # 内容未变化的文件零写入（mtime 未动）
    assert unchanged.read_bytes() == b"UNCHANGED"
    assert unchanged.stat().st_mtime == old_mtime
    # 变化文件被更新
    assert changed.read_bytes() == b"NEW-CONTENT"
    # 载荷中不存在且不受保护的旧文件被删除
    assert not obsolete.exists()
    # config.json 与用户目录保留
    assert (install_dir / "config.json").read_text(encoding="utf-8") == '{"keep": true}'
    assert (install_dir / "input" / "user.txt").exists()
    assert (install_dir / "output" / "user.txt").exists()
    # 更新器不再被按名跳过
    assert (install_dir / "_internal" / "RenpyBoxUpdater2.exe").read_bytes() == b"NEW-UPDATER"
    # staging 已清理
    assert not (install_dir / "_update_staging").exists()

    log_text = (install_dir / "log" / "last_update.log").read_text(encoding="utf-8")
    assert "Updated: 2 files" in log_text
    assert "Skipped: 2 files (unchanged)" in log_text
    assert "Deleted: 1 files (obsolete)" in log_text
    assert "StageTimings:" in log_text
    assert "wait_pid=" in log_text


def test_apply_update_fail_closed_when_pid_still_running(tmp_path: Path) -> None:
    install_dir = tmp_path / "install"
    install_dir.mkdir()
    zip_path = tmp_path / "update.zip"
    _build_payload_zip(zip_path, files={"RenpyBox.exe": b"MAIN"})

    with pytest.raises(RuntimeError, match="超时"):
        updater.apply_update(
            pid=os.getpid(),
            zip_path=zip_path,
            install_dir=install_dir,
            release_url=None,
            restart=False,
            exe_name="RenpyBox.exe",
        )

    # 中止必须发生在任何文件改动之前
    assert not (install_dir / "RenpyBox.exe").exists()
    assert not (install_dir / "_update_staging").exists()
    assert zip_path.is_file()


def test_apply_update_rename_swap_for_running_updater(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_dir = tmp_path / "install"
    install_dir.mkdir()
    zip_path = tmp_path / "update.zip"

    # 模拟用户直接从安装目录运行更新器：sys.executable 指向安装目录内的 updater
    running_updater = install_dir / "RenpyBoxUpdater2.exe"
    running_updater.write_bytes(b"OLD-UPDATER")
    monkeypatch.setattr(sys, "executable", str(running_updater))

    _build_payload_zip(zip_path, files={
        "RenpyBox.exe": b"MAIN",
        "RenpyBoxUpdater2.exe": b"NEW-UPDATER",
    })

    updater.apply_update(
        pid=0,
        zip_path=zip_path,
        install_dir=install_dir,
        release_url=None,
        restart=False,
        exe_name="RenpyBox.exe",
    )

    assert running_updater.read_bytes() == b"NEW-UPDATER"
    assert (install_dir / "RenpyBoxUpdater2.exe.old").read_bytes() == b"OLD-UPDATER"


def test_apply_update_cleans_stale_exe_old_leftovers(tmp_path: Path) -> None:
    install_dir = tmp_path / "install"
    install_dir.mkdir()
    zip_path = tmp_path / "update.zip"

    stale_root = install_dir / "RenpyBoxUpdater2.exe.old"
    stale_root.write_bytes(b"OLD-UPDATER")
    internal = install_dir / "_internal"
    internal.mkdir()
    stale_internal = internal / "RenpyBoxUpdater.exe.old"
    stale_internal.write_bytes(b"OLD-UPDATER")

    _build_payload_zip(zip_path, files={"RenpyBox.exe": b"MAIN"})

    updater.apply_update(
        pid=0,
        zip_path=zip_path,
        install_dir=install_dir,
        release_url=None,
        restart=False,
        exe_name="RenpyBox.exe",
    )

    assert not stale_root.exists()
    assert not stale_internal.exists()


def test_patch_delete_failure_keeps_old_manifest_and_journal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    v1 = tmp_path / "v1"
    v2 = tmp_path / "v2"
    (v1 / "_internal").mkdir(parents=True)
    (v2 / "_internal").mkdir(parents=True)
    (v1 / "RenpyBox.exe").write_bytes(b"MAIN")
    (v2 / "RenpyBox.exe").write_bytes(b"MAIN")
    (v1 / "_internal" / "changed.txt").write_text("old", encoding="utf-8")
    (v2 / "_internal" / "changed.txt").write_text("new", encoding="utf-8")
    (v1 / "_internal" / "obsolete.txt").write_text("remove", encoding="utf-8")

    install_dir = tmp_path / "install"
    for item in v1.rglob("*"):
        if item.is_file():
            target = install_dir / item.relative_to(v1)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(item.read_bytes())
    (install_dir / updater.MANIFEST_NAME).write_text(
        json.dumps(build_manifest(v1, "v1.0.0")), encoding="utf-8"
    )
    patch_zip = tmp_path / "v2.patch.zip"
    build_patch(v2, "v2.0.0", v1, "v1.0.0", patch_zip)

    old_unlink = Path.unlink
    obsolete = install_dir / "_internal" / "obsolete.txt"

    def fail_obsolete_unlink(path: Path, *args, **kwargs):
        if path == obsolete:
            raise PermissionError("simulated delete failure")
        return old_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_obsolete_unlink)

    with pytest.raises(RuntimeError, match="Delete failed"):
        updater.apply_update(
            pid=0,
            zip_path=patch_zip,
            install_dir=install_dir,
            release_url=None,
            restart=False,
            exe_name="RenpyBox.exe",
        )

    installed = json.loads((install_dir / updater.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert installed["version"] == "v1.0.0"
    assert obsolete.exists()
    assert (install_dir / updater.JOURNAL_NAME).exists()

    monkeypatch.undo()
    updater.apply_update(
        pid=0,
        zip_path=patch_zip,
        install_dir=install_dir,
        release_url=None,
        restart=False,
        exe_name="RenpyBox.exe",
    )
    installed = json.loads((install_dir / updater.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert installed["version"] == "v2.0.0"
    assert not obsolete.exists()
    assert not list(install_dir.rglob("*.new"))
