import hashlib
import json
import importlib
import sys
from pathlib import Path

import httpx
import pytest

from base.Base import Base
from base.VersionManager import VersionManager


version_manager_module = importlib.import_module("base.VersionManager")


class _JsonResponse:

    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self.payload


class _StreamResponse:

    def __init__(
        self,
        content_length: int,
        chunks: list[bytes],
        after_chunk = None,
    ) -> None:
        self.headers = {"Content-Length": str(content_length)}
        self.chunks = chunks
        self.after_chunk = after_chunk
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        pass

    def raise_for_status(self) -> None:
        pass

    def iter_bytes(self, chunk_size: int):
        assert chunk_size == VersionManager.DOWNLOAD_CHUNK_SIZE
        for index, chunk in enumerate(self.chunks):
            if self.closed:
                raise httpx.ReadError("stream closed")
            yield chunk
            if self.after_chunk is not None:
                self.after_chunk(index)

    def close(self) -> None:
        self.closed = True


def _manager_with_events(monkeypatch):
    with monkeypatch.context() as init_patch:
        init_patch.setattr(Base, "subscribe", lambda *args, **kwargs: None)
        manager = VersionManager()
    emitted: list[tuple[Base.Event, dict]] = []
    monkeypatch.setattr(
        manager,
        "emit",
        lambda event, data: emitted.append((event, data)),
    )
    return manager, emitted


def _seed_release(manager: VersionManager, content: bytes, digest: str = "") -> None:
    latest = VersionManager._normalize_release({
        "tag_name": "v9.9.9",
        "body": "Release notes",
        "published_at": "2026-07-31T00:00:00Z",
        "assets": [{
            "name": "RenpyBox.zip",
            "size": len(content),
            "browser_download_url": "https://example.invalid/RenpyBox.zip",
            "digest": digest,
        }],
    })
    with manager.lock:
        manager.latest = latest


def _patch_temp_path(monkeypatch, path: Path) -> None:
    monkeypatch.setattr(
        VersionManager,
        "temp_zip_path",
        classmethod(lambda cls: path),
    )


def test_parse_version_accepts_app_and_release_formats() -> None:
    assert VersionManager.parse_version("v0.6.0") == (0, 6, 0, 0)
    assert VersionManager.parse_version("RenpyBox_v0.6.0") == (0, 6, 0, 0)
    assert VersionManager.parse_version("v0.5.13") == (0, 5, 13, 0)


def test_temp_zip_path_uses_cwd_in_source_mode(monkeypatch, tmp_path) -> None:
    monkeypatch.delattr(sys, "frozen", raising = False)
    monkeypatch.chdir(tmp_path)

    assert VersionManager.temp_zip_path() == (
        tmp_path / "resource" / "update.temp"
    ).resolve()


def test_temp_zip_path_uses_install_dir_when_frozen(monkeypatch, tmp_path) -> None:
    executable = tmp_path / "install" / "RenpyBox.exe"
    monkeypatch.setattr(sys, "frozen", True, raising = False)
    monkeypatch.setattr(sys, "executable", str(executable))

    assert VersionManager.temp_zip_path() == (
        executable.parent / "resource" / "update.temp"
    ).resolve()


def test_check_caches_release_metadata_and_emits_manual_result(monkeypatch) -> None:
    manager, emitted = _manager_with_events(monkeypatch)
    manager.set_version("v1.0.0")
    release = {
        "tag_name": "v1.1.0",
        "body": "## Changes\n- Fixed updates",
        "published_at": "2026-07-31T00:00:00Z",
        "assets": [{
            "name": "RenpyBox.zip",
            "size": 123,
            "browser_download_url": "https://example.invalid/RenpyBox.zip",
            "digest": "sha256:" + "a" * 64,
        }],
    }
    monkeypatch.setattr(
        version_manager_module.httpx,
        "get",
        lambda *args, **kwargs: _JsonResponse(release),
    )

    manager.app_update_check_start_task("", {"manual": True})

    latest = manager.get_latest()
    assert latest["tag_name"] == release["tag_name"]
    assert latest["body"] == release["body"]
    assert latest["published_at"] == release["published_at"]
    assert latest["assets"] == release["assets"]
    assert latest["asset"] == release["assets"][0]
    latest["assets"][0]["name"] = "mutated.zip"
    latest["asset"]["name"] = "also-mutated.zip"
    assert manager.get_latest()["assets"][0]["name"] == "RenpyBox.zip"
    assert manager.get_latest()["asset"]["name"] == "RenpyBox.zip"

    check_payload = next(
        data for event, data in emitted
        if event == Base.Event.APP_UPDATE_CHECK_DONE
    )
    assert check_payload["manual"] is True
    assert check_payload["new_version"] is True
    assert check_payload["error"] == ""
    assert check_payload["status"] == VersionManager.Status.NEW_VERSION
    assert check_payload["latest"]["body"] == release["body"]


def test_manual_check_error_is_reported_in_result_and_state(monkeypatch) -> None:
    manager, emitted = _manager_with_events(monkeypatch)

    def fail_request(*args, **kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(version_manager_module.httpx, "get", fail_request)

    manager.app_update_check_start_task("", {"manual": True})

    payload = next(
        data for event, data in emitted
        if event == Base.Event.APP_UPDATE_CHECK_DONE
    )
    assert payload["manual"] is True
    assert payload["new_version"] is False
    assert payload["error"] == "offline"
    assert manager.get_update_state()["error"] == "offline"


def test_progress_events_are_throttled_but_final_update_is_forced(monkeypatch) -> None:
    manager, emitted = _manager_with_events(monkeypatch)
    timestamps = iter([1.0, 1.05, 1.19, 1.21, 1.22])
    monkeypatch.setattr(
        version_manager_module.time,
        "monotonic",
        lambda: next(timestamps),
    )

    manager._emit_download_progress(1, 10)
    manager._emit_download_progress(2, 10)
    manager._emit_download_progress(3, 10)
    manager._emit_download_progress(4, 10)
    manager._emit_download_progress(10, 10, force = True)

    progress = [
        data["downloaded_size"]
        for event, data in emitted
        if event == Base.Event.APP_UPDATE_DOWNLOAD_UPDATE
    ]
    assert progress == [1, 4, 10]
    assert manager.get_download_progress() == {
        "downloaded_size": 10,
        "total_size": 10,
    }


def test_download_validates_size_and_sha256_before_completion(
    monkeypatch,
    tmp_path,
) -> None:
    manager, emitted = _manager_with_events(monkeypatch)
    content = b"verified update package"
    digest = "sha256:" + hashlib.sha256(content).hexdigest()
    _seed_release(manager, content, digest)
    temp_path = tmp_path / "resource" / "update.temp"
    _patch_temp_path(monkeypatch, temp_path)
    stream = _StreamResponse(len(content), [content[:5], content[5:]])
    monkeypatch.setattr(
        version_manager_module.httpx,
        "stream",
        lambda *args, **kwargs: stream,
    )

    manager.app_update_download_start_task("", {})

    assert temp_path.read_bytes() == content
    state = manager.get_update_state()
    assert state["status"] == VersionManager.Status.DOWNLOADED
    assert state["downloaded_size"] == len(content)
    assert state["total_size"] == len(content)
    done_payload = next(
        data for event, data in emitted
        if event == Base.Event.APP_UPDATE_DOWNLOAD_DONE
    )
    assert done_payload["status"] == VersionManager.Status.DOWNLOADED
    assert done_payload["latest"]["assets"][0]["digest"] == digest


@pytest.mark.parametrize(
    ("content_length", "digest", "error_text"),
    [
        # digest fail-closed：资产无 sha256 时拒绝自动下载（下载开始前即失败）
        (7, "", "no sha256 digest"),
        (8, "sha256:" + hashlib.sha256(b"payload").hexdigest(), "Downloaded size mismatch"),
        (7, "sha256:" + "0" * 64, "sha256 digest mismatch"),
    ],
)
def test_failed_download_validation_removes_temp_file(
    monkeypatch,
    tmp_path,
    content_length,
    digest,
    error_text,
) -> None:
    manager, emitted = _manager_with_events(monkeypatch)
    content = b"payload"
    _seed_release(manager, content, digest)
    temp_path = tmp_path / "resource" / "update.temp"
    _patch_temp_path(monkeypatch, temp_path)
    monkeypatch.setattr(
        version_manager_module.httpx,
        "stream",
        lambda *args, **kwargs: _StreamResponse(content_length, [content]),
    )

    manager.app_update_download_start_task("", {})

    assert not temp_path.exists()
    state = manager.get_update_state()
    assert state["status"] == VersionManager.Status.NEW_VERSION
    assert error_text in state["error"]
    error_payload = next(
        data for event, data in emitted
        if event == Base.Event.APP_UPDATE_DOWNLOAD_ERROR
    )
    assert error_payload["cancelled"] is False
    assert error_text in error_payload["error"]


def test_cancel_download_removes_partial_file_and_resets_state(
    monkeypatch,
    tmp_path,
) -> None:
    manager, emitted = _manager_with_events(monkeypatch)
    content = b"first-second"
    _seed_release(manager, content, "sha256:" + hashlib.sha256(content).hexdigest())
    temp_path = tmp_path / "resource" / "update.temp"
    _patch_temp_path(monkeypatch, temp_path)
    cancel_results: list[bool] = []

    def cancel_after_first_chunk(index: int) -> None:
        if index == 0:
            cancel_results.append(manager.cancel_download())

    stream = _StreamResponse(
        len(content),
        [b"first-", b"second"],
        cancel_after_first_chunk,
    )
    monkeypatch.setattr(
        version_manager_module.httpx,
        "stream",
        lambda *args, **kwargs: stream,
    )

    manager.app_update_download_start_task("", {})

    assert cancel_results == [True]
    assert stream.closed is True
    assert not temp_path.exists()
    state = manager.get_update_state()
    assert state["status"] == VersionManager.Status.NEW_VERSION
    assert state["downloaded_size"] == 0
    assert state["total_size"] == 0
    assert state["error"] == ""
    error_payload = next(
        data for event, data in emitted
        if event == Base.Event.APP_UPDATE_DOWNLOAD_ERROR
    )
    assert error_payload["cancelled"] is True


def test_cancel_before_release_fetch_removes_stale_temp_file(
    monkeypatch,
    tmp_path,
) -> None:
    manager, emitted = _manager_with_events(monkeypatch)
    temp_path = tmp_path / "resource" / "update.temp"
    _patch_temp_path(monkeypatch, temp_path)
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path.write_bytes(b"stale update")
    with manager.lock:
        manager._prepare_download_locked()
        manager._download_cancel_event.set()

    manager.app_update_download_start_task("", {})

    assert not temp_path.exists()
    state = manager.get_update_state()
    assert state["status"] == VersionManager.Status.NONE
    error_payload = next(
        data
        for event, data in emitted
        if event == Base.Event.APP_UPDATE_DOWNLOAD_ERROR
    )
    assert error_payload["cancelled"] is True


def test_extract_event_claims_single_worker_slot_before_thread_starts(
    monkeypatch,
) -> None:
    manager, _ = _manager_with_events(monkeypatch)
    started = []

    class _Thread:
        def start(self) -> None:
            started.append(True)

    monkeypatch.setattr(
        version_manager_module.threading,
        "Thread",
        lambda **kwargs: _Thread(),
    )

    manager.app_update_extract("", {})
    manager.app_update_extract("", {})

    assert started == [True]
    assert manager.extracting is True


def test_source_mode_extract_still_warns_and_opens_release_page(monkeypatch) -> None:
    manager, emitted = _manager_with_events(monkeypatch)
    opened_urls = []
    monkeypatch.delattr(sys, "frozen", raising = False)
    monkeypatch.setattr(
        version_manager_module.QDesktopServices,
        "openUrl",
        lambda url: opened_urls.append(url.toString()),
    )

    manager.app_update_extract_task("", {})

    assert opened_urls == [VersionManager.RELEASE_URL]
    assert manager.extracting is False
    toast = next(
        data for event, data in emitted
        if event == Base.Event.APP_TOAST_SHOW
    )
    assert toast["type"] == Base.ToastType.WARNING


def _fake_installed_manifest(monkeypatch, tmp_path, version: str | None) -> None:
    """把安装态伪装成 frozen 运行，manifest 写在 exe 旁。"""
    install_dir = tmp_path / "install"
    install_dir.mkdir(exist_ok=True)
    exe = install_dir / "RenpyBox.exe"
    exe.write_bytes(b"EXE")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    if version is not None:
        (install_dir / "_update_manifest.json").write_text(
            json.dumps({"version": version, "files": {}}), encoding="utf-8"
        )


def _release_with_assets(*asset_names: str) -> dict:
    return {
        "assets": [
            {
                "name": name,
                "size": 10,
                "browser_download_url": f"https://example.invalid/{name}",
                "digest": "sha256:" + "0" * 64,
            }
            for name in asset_names
        ]
    }


def test_installed_manifest_version_read_from_exe_dir(monkeypatch, tmp_path) -> None:
    _fake_installed_manifest(monkeypatch, tmp_path, "v1.2.3")
    assert VersionManager._installed_manifest_version() == "v1.2.3"


def test_installed_manifest_version_none_without_manifest(monkeypatch, tmp_path) -> None:
    _fake_installed_manifest(monkeypatch, tmp_path, None)
    assert VersionManager._installed_manifest_version() is None


def test_select_download_asset_prefers_matching_patch(monkeypatch, tmp_path) -> None:
    _fake_installed_manifest(monkeypatch, tmp_path, "v1.0.0")
    latest = _release_with_assets(
        "RenpyBox_v2.0.0.zip",
        "RenpyBox_v2.0.0.from-v1.0.0.patch.zip",
    )
    asset = VersionManager._select_download_asset(latest)
    assert asset["name"] == "RenpyBox_v2.0.0.from-v1.0.0.patch.zip"


def test_select_download_asset_falls_back_to_full_when_base_mismatch(monkeypatch, tmp_path) -> None:
    _fake_installed_manifest(monkeypatch, tmp_path, "v0.9.0")
    latest = _release_with_assets(
        "RenpyBox_v2.0.0.zip",
        "RenpyBox_v2.0.0.from-v1.0.0.patch.zip",
    )
    asset = VersionManager._select_download_asset(latest)
    assert asset["name"] == "RenpyBox_v2.0.0.zip"


def test_select_download_asset_never_picks_patch_without_manifest(monkeypatch, tmp_path) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    latest = _release_with_assets(
        "RenpmBox_v2.0.0.zip",
        "RenpyBox_v2.0.0.from-v1.0.0.patch.zip",
    )
    latest["assets"][0]["name"] = "RenpyBox_v2.0.0.zip"
    asset = VersionManager._select_download_asset(latest)
    assert asset["name"] == "RenpyBox_v2.0.0.zip"
