import json
import zipfile
from pathlib import Path

import pytest

import updater
from buildtools.update_assets import (
    MANIFEST_NAME,
    PATCH_META_NAME,
    build_manifest,
    build_patch,
    append_manifest_to_zip,
    file_sha256,
)


def _make_version_tree(root: Path, version: str, big: bool = False) -> Path:
    """伪造一个版本的 dist 目录（含主程序标记 exe 与若干文件）。"""
    import random

    dist = root / f"dist_{version.replace('.', '_')}"
    (dist / "_internal").mkdir(parents=True)
    # exe 内容跨版本固定：是否进 patch 由测试显式控制，避免默认出现在 changed 里
    (dist / "RenpyBox.exe").write_bytes(b"EXE-MARK")
    (dist / "_internal" / "base.py").write_text(f"# base {version}", encoding="utf-8")
    # 随机内容防止 deflate 把大文件压没了，保证体积断言有意义
    payload = random.Random(42).randbytes(1024 * 1024) if big else b"x" * 128
    (dist / "_internal" / "data.bin").write_bytes(payload)
    (dist / "resource").mkdir()
    (dist / "resource" / "model.bin").write_bytes(b"m" * 2048)
    return dist


def _make_full_zip(dist: Path, zip_path: Path, version: str) -> Path:
    """生成与真实发布一致的全量包：载荷文件位于 zip 顶层 + 内嵌 manifest。"""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=5) as zf:
        for item in sorted(dist.rglob("*")):
            if item.is_file():
                zf.write(item, item.relative_to(dist).as_posix())
    append_manifest_to_zip(zip_path, build_manifest(dist, version))
    return zip_path


def _install_from(dist: Path, install_dir: Path, version: str | None = None, manifest: dict | None = None) -> None:
    for item in dist.rglob("*"):
        if item.is_file():
            target = install_dir / item.relative_to(dist)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(item.read_bytes())
    if manifest is not None:
        (install_dir / MANIFEST_NAME).write_text(
            json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
        )


def _extract_prev(root: Path, prev_zip: Path) -> Path:
    from buildtools.update_assets import extract_prev_zip

    return extract_prev_zip(prev_zip, root / "prev_extract")


def _build_patch_for(tmp_path: Path, v1: Path, v2: Path) -> Path:
    prev_zip = _make_full_zip(v1, tmp_path / "v1_full.zip", "v1.0.0")
    prev_payload = _extract_prev(tmp_path, prev_zip)
    patch_zip = tmp_path / "RenpyBox_v2.0.0.from-v1.0.0.patch.zip"
    build_patch(v2, "v2.0.0", prev_payload, "v1.0.0", patch_zip)
    return patch_zip


def test_build_manifest_covers_all_files(tmp_path: Path) -> None:
    dist = _make_version_tree(tmp_path, "v1.0.0")
    manifest = build_manifest(dist, "v1.0.0")

    assert manifest["version"] == "v1.0.0"
    assert set(manifest["files"]) == {
        "RenpyBox.exe",
        "_internal/base.py",
        "_internal/data.bin",
        "resource/model.bin",
    }
    assert manifest["files"]["RenpyBox.exe"]["sha256"] == file_sha256(dist / "RenpyBox.exe")
    assert manifest["files"]["RenpyBox.exe"]["size"] == (dist / "RenpyBox.exe").stat().st_size


def test_manifest_append_is_readbackable_and_unique(tmp_path: Path) -> None:
    dist = _make_version_tree(tmp_path, "v1.0.0")
    zip_path = _make_full_zip(dist, tmp_path / "full.zip", "v1.0.0")

    with zipfile.ZipFile(zip_path, "r") as zf:
        assert MANIFEST_NAME in zf.namelist()
        meta = json.loads(zf.read(MANIFEST_NAME).decode("utf-8"))
    assert meta["version"] == "v1.0.0"

    # 重复追加必须报错（zip 内出现双份 manifest 会让探测读到旧的）
    with pytest.raises(RuntimeError):
        append_manifest_to_zip(zip_path, meta)


def test_build_patch_detects_changed_added_deleted(tmp_path: Path) -> None:
    v1 = _make_version_tree(tmp_path, "v1.0.0", big=True)
    v2 = _make_version_tree(tmp_path, "v2.0.0", big=True)
    (v2 / "_internal" / "base.py").write_text("# base v2.0.0 CHANGED", encoding="utf-8")
    (v2 / "_internal" / "new_file.txt").write_text("new", encoding="utf-8")
    (v2 / "resource" / "model.bin").unlink()

    patch_zip = _build_patch_for(tmp_path, v1, v2)

    with zipfile.ZipFile(patch_zip, "r") as zf:
        names = set(zf.namelist())
        meta = json.loads(zf.read(PATCH_META_NAME).decode("utf-8"))

    assert PATCH_META_NAME in names
    assert set(meta["files"]) == {"_internal/base.py", "_internal/new_file.txt"}
    assert meta["deleted"] == ["resource/model.bin"]
    assert meta["base_version"] == "v1.0.0"
    assert meta["version"] == "v2.0.0"
    # meta 内嵌完整目标 manifest
    assert set(meta["manifest"]["files"]) == {
        "RenpyBox.exe",
        "_internal/base.py",
        "_internal/data.bin",
        "_internal/new_file.txt",
    }


def test_patch_zip_far_smaller_than_full_zip(tmp_path: Path) -> None:
    """验收口径：patch 场景 download_bytes ≈ compressed_changed_payload。"""
    v1 = _make_version_tree(tmp_path, "v1.0.0", big=True)
    v2 = _make_version_tree(tmp_path, "v2.0.0", big=True)
    (v2 / "_internal" / "base.py").write_text("# base v2.0.0 CHANGED", encoding="utf-8")

    full_v2 = _make_full_zip(v2, tmp_path / "v2_full.zip", "v2.0.0")
    patch_zip = _build_patch_for(tmp_path, v1, v2)

    # 只有 base.py 变化的 patch 必须远小于全量包（全量含 1MB 的 data.bin）
    assert patch_zip.stat().st_size < full_v2.stat().st_size // 10


def test_updater_applies_patch_end_to_end(tmp_path: Path) -> None:
    v1 = _make_version_tree(tmp_path, "v1.0.0", big=True)
    v2 = _make_version_tree(tmp_path, "v2.0.0", big=True)
    (v2 / "_internal" / "base.py").write_text("# base v2.0.0 CHANGED", encoding="utf-8")
    (v2 / "_internal" / "new_file.txt").write_text("new", encoding="utf-8")
    (v2 / "resource" / "model.bin").unlink()

    install_dir = tmp_path / "install"
    _install_from(v1, install_dir, manifest=build_manifest(v1, "v1.0.0"))
    patch_zip = _build_patch_for(tmp_path, v1, v2)

    updater.apply_update(
        pid = 0,
        zip_path = patch_zip,
        install_dir = install_dir,
        release_url = None,
        restart = False,
        exe_name = "RenpyBox.exe",
    )

    # 变化文件已提交、新增文件就位、删除清单生效
    assert (install_dir / "_internal" / "base.py").read_text(encoding="utf-8") == "# base v2.0.0 CHANGED"
    assert (install_dir / "_internal" / "new_file.txt").read_text(encoding="utf-8") == "new"
    assert not (install_dir / "resource" / "model.bin").exists()
    # 未变化的文件保持原样
    assert (install_dir / "_internal" / "data.bin").read_bytes() == (v1 / "_internal" / "data.bin").read_bytes()
    # 安装态 manifest 已更新为 v2 全量清单
    installed = json.loads((install_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert installed["version"] == "v2.0.0"
    assert "_internal/new_file.txt" in installed["files"]
    # journal、.new、staging 全部清理，patch 包删除
    assert not (install_dir / updater.JOURNAL_NAME).exists()
    assert not list(install_dir.rglob("*.new"))
    assert not (install_dir / "_update_staging").exists()
    assert not patch_zip.exists()

    log_text = (install_dir / "log" / "last_update.log").read_text(encoding="utf-8")
    assert "Patch: v2.0.0" in log_text
    assert "Applied: 2 files" in log_text


def test_updater_patch_resumes_interrupted_commit(tmp_path: Path) -> None:
    v1 = _make_version_tree(tmp_path, "v1.0.0")
    v2 = _make_version_tree(tmp_path, "v2.0.0")
    # 两个变化文件：构造一个已提交、一个中断在现场的 journal
    (v2 / "_internal" / "base.py").write_text("# base v2.0.0 CHANGED", encoding="utf-8")
    (v2 / "_internal" / "data.bin").write_bytes(b"y" * 256)

    install_dir = tmp_path / "install"
    _install_from(v1, install_dir)
    patch_zip = _build_patch_for(tmp_path, v1, v2)

    meta = updater._read_patch_meta(patch_zip)
    rels = sorted(meta["files"])
    assert len(rels) == 2
    committed_rel, staged_rel = rels[0], rels[1]

    with zipfile.ZipFile(patch_zip, "r") as zf:
        # 已提交项：目标已是 v2 内容；中断项：.new 已就位
        (install_dir.joinpath(*committed_rel.split("/"))).write_bytes(zf.read(committed_rel))
        staged_new = install_dir.joinpath(*staged_rel.split("/"))
        staged_new = staged_new.with_name(staged_new.name + ".new")
        staged_new.write_bytes(zf.read(staged_rel))

    (install_dir / updater.JOURNAL_NAME).write_text(
        json.dumps({
            "format": updater.PATCH_FORMAT,
            "version": "v2.0.0",
            "staged": rels,
            "committed": [committed_rel],
        }),
        encoding="utf-8",
    )

    updater.apply_update(
        pid = 0,
        zip_path = patch_zip,
        install_dir = install_dir,
        release_url = None,
        restart = False,
        exe_name = "RenpyBox.exe",
    )

    # 全部文件抵达 v2 状态，journal 与 .new 清理
    assert (install_dir / "_internal" / "base.py").read_text(encoding="utf-8") == "# base v2.0.0 CHANGED"
    assert (install_dir / "_internal" / "data.bin").read_bytes() == b"y" * 256
    assert not (install_dir / updater.JOURNAL_NAME).exists()
    assert not list(install_dir.rglob("*.new"))


def test_updater_patch_stale_journal_is_discarded(tmp_path: Path) -> None:
    """版本不匹配的旧 journal 与 .new 残留必须被清理后全新应用。"""
    v1 = _make_version_tree(tmp_path, "v1.0.0")
    v2 = _make_version_tree(tmp_path, "v2.0.0")
    (v2 / "_internal" / "base.py").write_text("# base v2.0.0 CHANGED", encoding="utf-8")

    install_dir = tmp_path / "install"
    _install_from(v1, install_dir)
    stale_new = install_dir / "_internal" / "base.py.new"
    stale_new.write_bytes(b"stale")
    (install_dir / updater.JOURNAL_NAME).write_text(
        json.dumps({
            "format": updater.PATCH_FORMAT,
            "version": "v9.9.9",
            "staged": ["_internal/base.py"],
            "committed": [],
        }),
        encoding="utf-8",
    )

    patch_zip = _build_patch_for(tmp_path, v1, v2)
    updater.apply_update(
        pid = 0,
        zip_path = patch_zip,
        install_dir = install_dir,
        release_url = None,
        restart = False,
        exe_name = "RenpyBox.exe",
    )

    assert (install_dir / "_internal" / "base.py").read_text(encoding="utf-8") == "# base v2.0.0 CHANGED"
    assert not stale_new.exists()
    assert not (install_dir / updater.JOURNAL_NAME).exists()


def test_full_update_embeds_installed_manifest(tmp_path: Path) -> None:
    """全量包（内嵌 manifest）应用后写入安装态 manifest，meta 不落入安装目录。"""
    v2 = _make_version_tree(tmp_path, "v2.0.0")
    full_zip = _make_full_zip(v2, tmp_path / "v2_full.zip", "v2.0.0")

    install_dir = tmp_path / "install"
    install_dir.mkdir()

    updater.apply_update(
        pid = 0,
        zip_path = full_zip,
        install_dir = install_dir,
        release_url = None,
        restart = False,
        exe_name = "RenpyBox.exe",
    )

    installed = json.loads((install_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert installed["version"] == "v2.0.0"
    # meta 只被读取，不作为普通文件复制进安装目录
    assert not (install_dir / "_internal" / MANIFEST_NAME).exists()


def test_full_update_without_manifest_skips_install_state(tmp_path: Path) -> None:
    """旧版全量包（无内嵌 manifest）应用后不写安装态 manifest，行为与旧版一致。"""
    v2 = _make_version_tree(tmp_path, "v2.0.0")
    full_zip = tmp_path / "v2_full.zip"
    with zipfile.ZipFile(full_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in sorted(v2.rglob("*")):
            if item.is_file():
                zf.write(item, item.relative_to(v2).as_posix())

    install_dir = tmp_path / "install"
    install_dir.mkdir()
    updater.apply_update(
        pid = 0,
        zip_path = full_zip,
        install_dir = install_dir,
        release_url = None,
        restart = False,
        exe_name = "RenpyBox.exe",
    )
    assert not (install_dir / MANIFEST_NAME).exists()
