import json
import os
import subprocess
import zipfile
from pathlib import Path

import pytest

import updater
from buildtools.update_assets import (
    MANIFEST_NAME,
    build_manifest,
    append_manifest_to_zip,
    file_sha256,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_BUNDLED_7ZA = _REPO_ROOT / "resource" / "7za.exe"
# 与 build.yml Compress compatibility archive 压缩参数对齐（不含路径）。
_WORKFLOW_7ZA_COMPRESS = ("a", "-y", "-bt", "-mx5")
_WORKFLOW_7ZA_UTF8 = "-mcu=on"


def _make_version_tree(root: Path, version: str) -> Path:
    """伪造一个版本的 dist 目录（含主程序标记 exe 与若干文件）。"""
    dist = root / f"dist_{version.replace('.', '_')}"
    (dist / "_internal").mkdir(parents=True)
    (dist / "RenpyBox.exe").write_bytes(b"EXE-MARK")
    (dist / "_internal" / "base.py").write_text(f"# base {version}", encoding="utf-8")
    (dist / "_internal" / "data.bin").write_bytes(b"x" * 128)
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


def test_release_workflow_ships_desktop_artifacts_only() -> None:
    """Qt/Python 客户端退役后，发布草稿只等桌面产物，不再打包 Python 兼容包。"""
    import yaml

    workflow_dir = Path(__file__).resolve().parents[1] / ".github" / "workflows"
    assert not (workflow_dir / "build.yml").exists()

    release = yaml.load(
        (workflow_dir / "release.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    assert set(release["jobs"]) == {"desktop", "draft"}
    assert set(release["jobs"]["draft"]["needs"]) == {"desktop"}
    assert release["jobs"]["desktop"]["uses"] == "./.github/workflows/desktop.yml"
    draft_run = next(step["run"] for step in release["jobs"]["draft"]["steps"] if "run" in step)
    for artifact in (
        "RenpyBox-$version-x64.exe",
        "RenpyBox-$version-x64.zip",
    ):
        assert artifact in draft_run
    assert "RenpyBox_v$version.zip" not in draft_run
    assert "version.txt" in draft_run
    # 已发布的 release 不得被覆盖：草稿任务必须先查 isDraft，再决定替换还是跳过。
    assert "if (!$existing.isDraft)" in draft_run
    assert "is already published; skipping replacement" in draft_run
    release_commands = [line.strip() for line in draft_run.splitlines() if line.strip().startswith(("gh release create", "gh release edit"))]
    assert len(release_commands) == 2
    assert all("--draft" in command and "--notes-file" in command for command in release_commands)

    # 发布草稿按 pattern 下载产物：pattern 必须真的匹配 desktop.yml 上传的 artifact 名，
    # 否则 download-artifact 会静默下载 0 个产物，直到 draft 校验才报 Missing artifact。
    import fnmatch

    desktop = yaml.load(
        (workflow_dir / "desktop.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    upload_name = next(
        step["with"]["name"]
        for step in desktop["jobs"]["package"]["steps"]
        if str(step.get("uses", "")).startswith("actions/upload-artifact")
    )
    download_pattern = next(
        step["with"]["pattern"]
        for step in release["jobs"]["draft"]["steps"]
        if str(step.get("uses", "")).startswith("actions/download-artifact")
    )
    assert fnmatch.fnmatch(upload_name, download_pattern), (
        f"release.yml 下载 pattern {download_pattern!r} 匹配不到 desktop.yml 上传的 {upload_name!r}"
    )


def _run_7za(*args: str) -> subprocess.CompletedProcess[str]:
    assert _BUNDLED_7ZA.is_file(), f"missing bundled 7za: {_BUNDLED_7ZA}"
    return subprocess.run(
        [str(_BUNDLED_7ZA), *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _chinese_release_payload(root: Path) -> Path:
    """模拟发布包内含中文路径的小载荷（复现 CP936 本地名损坏）。"""
    payload = root / "payload"
    files = {
        "ok.txt": b"ascii-ok",
        "resource/中文目录/说明.txt": "说明内容".encode("utf-8"),
        "resource/字体/黑体.ttf": b"font-bytes",
        "resource/图片/背景.png": b"png-bytes",
        "resource/语音/欢迎.ogg": b"ogg-bytes",
        "resource/配置/默认.json": b'{"k":1}',
        "resource/补丁/更新说明.md": "# 更新\n".encode("utf-8"),
        "resource/插件/示例插件.py": b"# plugin\n",
    }
    for rel, data in files.items():
        path = payload.joinpath(*rel.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return payload


@pytest.mark.skipif(os.name != "nt", reason="7za CP936 ZIP name corruption is Windows-locale specific")
def test_7za_workflow_zip_utf8_survives_python_manifest_append(tmp_path: Path) -> None:
    """CP936 下无 -mcu=on 时，append_manifest_to_zip 会改写中央目录致 7za Headers Error；
    workflow 的 -mcu=on 必须让中文名在追加后仍可被 7za t 与 Python 精确读写。"""
    payload = _chinese_release_payload(tmp_path)
    expected_names = {
        rel.replace("\\", "/")
        for rel in (
            "ok.txt",
            "resource/中文目录/说明.txt",
            "resource/字体/黑体.ttf",
            "resource/图片/背景.png",
            "resource/语音/欢迎.ogg",
            "resource/配置/默认.json",
            "resource/补丁/更新说明.md",
            "resource/插件/示例插件.py",
        )
    }
    expected_bytes = {
        rel: (payload.joinpath(*rel.split("/"))).read_bytes() for rel in expected_names
    }
    version = "v9.9.9"
    glob = str(payload / "*")

    fixed = tmp_path / "fixed.zip"
    fixed_pack = _run_7za(*_WORKFLOW_7ZA_COMPRESS, _WORKFLOW_7ZA_UTF8, str(fixed), glob)
    assert fixed_pack.returncode == 0, fixed_pack.stderr
    append_manifest_to_zip(fixed, build_manifest(payload, version))
    fixed_test = _run_7za("t", str(fixed))
    assert fixed_test.returncode == 0, fixed_test.stdout + fixed_test.stderr
    assert "Headers Error" not in (fixed_test.stdout + fixed_test.stderr)
    assert "Everything is Ok" in fixed_test.stdout

    with zipfile.ZipFile(fixed, "r") as zf:
        names = set(zf.namelist())
        assert MANIFEST_NAME in names
        for rel, data in expected_bytes.items():
            assert rel in names, f"missing exact UTF-8 name: {rel!r} in {sorted(names)}"
            assert zf.read(rel) == data


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


def test_full_update_uses_manifest_without_legacy_double_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    v2 = _make_version_tree(tmp_path, "v2.0.0")
    full_zip = _make_full_zip(v2, tmp_path / "v2_full.zip", "v2.0.0")
    install_dir = tmp_path / "install"
    _install_from(v2, install_dir)

    def fail_legacy_hash(*args, **kwargs):
        raise AssertionError("manifest-backed update must not use legacy MD5")

    monkeypatch.setattr(updater, "_file_hash", fail_legacy_hash)
    updater.apply_update(
        pid=0,
        zip_path=full_zip,
        install_dir=install_dir,
        release_url=None,
        restart=False,
        exe_name="RenpyBox.exe",
    )


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


def test_desktop_workflow_embeds_update_manifest() -> None:
    """全量包必须内嵌清单，更新器才能记录安装态文件哈希。"""
    import yaml

    workflow_dir = Path(__file__).resolve().parents[1] / ".github" / "workflows"
    desktop = yaml.load(
        (workflow_dir / "desktop.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    steps = desktop["jobs"]["package"]["steps"]
    manifest_step = next(
        step for step in steps
        if step.get("name") == "Embed update manifest into the portable zip"
    )
    assert "buildtools/update_assets.py manifest" in manifest_step["run"]
    # 清单内嵌失败只告警，不能让安装包构建失败
    assert manifest_step["continue-on-error"] == "true"
    # 增量 patch 通道已整体移除，发布流程不得再生成 patch 包
    assert not any(
        "update_assets.py patch" in str(step.get("run") or "") for step in steps
    )
