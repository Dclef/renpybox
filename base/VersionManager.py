import copy
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
from PyQt5.QtCore import QUrl
from PyQt5.QtGui import QDesktopServices

from base.Base import Base
from base.Version import Version
from base.compat import Self, StrEnum
from module.Localizer.Localizer import Localizer


class _DownloadCancelled(Exception):
    pass


class VersionManager(Base):

    class Status(StrEnum):

        NONE = "NONE"
        NEW_VERSION = "NEW_VERSION"
        UPDATING = "UPDATING"
        DOWNLOADED = "DOWNLOADED"

    # URL 地址
    API_URL: str = "https://api.github.com/repos/dclef/RenpyBox/releases/latest"
    RELEASE_URL: str = "https://github.com/dclef/RenpyBox/releases/latest"
    RELEASES_URL: str = "https://github.com/dclef/RenpyBox/releases"
    VERSION_RE: re.Pattern = re.compile(r"^(?:RenpyBox_)?v?(\d+(?:\.\d+){2,3})$")
    SHA256_RE: re.Pattern = re.compile(r"^sha256:([0-9a-fA-F]{64})$")
    DOWNLOAD_CHUNK_SIZE: int = 64 * 1024
    PROGRESS_EMIT_INTERVAL_SECONDS: float = 0.2

    def __init__(self) -> None:
        super().__init__()

        # 更新状态由后台线程和 UI 线程共享，均由 lock 保护。
        self.status = __class__.Status.NONE
        self.version = Version.CURRENT
        self.latest: dict = {}
        self.downloaded_size = 0
        self.total_size = 0
        self.error = ""
        self.extracting = False

        self.lock: threading.Lock = threading.Lock()
        self._last_emit_ts: float | None = None
        self._download_cancel_event = threading.Event()
        self._download_active = False
        self._active_download_response = None

        # 注册事件
        self.subscribe(Base.Event.APP_UPDATE_EXTRACT, self.app_update_extract)
        self.subscribe(Base.Event.APP_UPDATE_CHECK_START, self.app_update_check_start)
        self.subscribe(Base.Event.APP_UPDATE_DOWNLOAD_START, self.app_update_download_start)
        self.subscribe(Base.Event.APP_UPDATE_DOWNLOAD_CANCEL, self.app_update_download_cancel)

    @classmethod
    def get(cls) -> Self:
        if getattr(cls, "__instance__", None) is None:
            cls.__instance__ = cls()

        return cls.__instance__

    @classmethod
    def parse_version(cls, version: str) -> tuple[int, int, int, int]:
        """解析应用版本或发布标签，统一补齐为四段用于比较。"""
        result = cls.VERSION_RE.match(str(version).strip())
        if result is None:
            return (0, 0, 0, 0)

        parts = [int(v) for v in result.group(1).split(".")]
        while len(parts) < 4:
            parts.append(0)
        return (parts[0], parts[1], parts[2], parts[3])

    @classmethod
    def display_version(cls, version: str) -> str:
        """把发布标签规范化为界面展示用的版本号。这里统一成 vX.Y.Z。  """
        text = str(version).strip()
        result = cls.VERSION_RE.match(text)
        if result is None:
            return text
        return f"v{result.group(1)}"

    @classmethod
    def temp_zip_path(cls) -> Path:
        base = (
            Path(sys.executable).resolve().parent
            if getattr(sys, "frozen", False)
            else Path.cwd()
        )
        return (base / "resource" / "update.temp").resolve()

    @staticmethod
    def _safe_int(value: object) -> int:
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0

    @classmethod
    def _normalize_release(cls, result: dict) -> dict:
        assets: list[dict] = []
        raw_assets = result.get("assets", [])
        if isinstance(raw_assets, list):
            for asset in raw_assets:
                if not isinstance(asset, dict):
                    continue
                assets.append({
                    "name": str(asset.get("name") or ""),
                    "size": cls._safe_int(asset.get("size")),
                    "browser_download_url": str(asset.get("browser_download_url") or ""),
                    "digest": str(asset.get("digest") or ""),
                })

        latest = {
            "tag_name": str(result.get("tag_name") or "v0.0.0"),
            "body": str(result.get("body") or ""),
            "published_at": str(result.get("published_at") or ""),
            "assets": assets,
        }
        if assets:
            latest["asset"] = cls._select_download_asset(latest)
        return latest

    @classmethod
    def _installed_manifest_version(cls) -> str | None:
        """读取安装态 manifest 的版本；无 manifest（存量安装/源码运行）返回 None。"""
        if not getattr(sys, "frozen", False):
            return None
        try:
            manifest_path = Path(sys.executable).resolve().parent / "_update_manifest.json"
            data = json.loads(manifest_path.read_text(encoding = "utf-8"))
            version = data.get("version") if isinstance(data, dict) else None
            return str(version) if version else None
        except Exception:
            return None

    @classmethod
    def _select_download_asset(cls, latest: dict) -> dict:
        assets = latest.get("assets", [])
        if not isinstance(assets, list) or not assets:
            raise RuntimeError("No release assets found")

        tag_name = str(latest.get("tag_name") or "").strip()
        version = (
            tag_name[len("RenpyBox_"):]
            if tag_name.casefold().startswith("renpybox_")
            else tag_name
        )
        if not version:
            raise RuntimeError("Release tag_name is empty")

        assets_by_name = {
            str(asset.get("name", "")).casefold(): asset
            for asset in assets
            if isinstance(asset, dict)
        }

        # 增量优先：本地安装态 manifest 版本与 patch 资产的 base 精确匹配才走增量，
        # 否则一律全量，避免把 patch 包当全量包应用
        installed = cls._installed_manifest_version()
        if installed:
            installed_version = (
                installed[len("RenpyBox_"):]
                if installed.casefold().startswith("renpybox_")
                else installed
            )
            patch_name = (
                f"RenpyBox_{version}.from-{installed_version}.patch.zip".casefold()
            )
            if patch_name in assets_by_name:
                return copy.deepcopy(assets_by_name[patch_name])

        full_name = f"RenpyBox_{version}.zip".casefold()
        target_asset = assets_by_name.get(full_name)
        if target_asset is None:
            raise RuntimeError(f"Expected release asset not found: RenpyBox_{version}.zip")
        return copy.deepcopy(target_asset)

    @classmethod
    def _expected_sha256(cls, digest: object) -> str | None:
        digest_text = str(digest or "").strip()
        if not digest_text:
            return None

        match = cls.SHA256_RE.fullmatch(digest_text)
        if match is not None:
            return match.group(1).lower()
        if digest_text.lower().startswith("sha256:"):
            raise RuntimeError("Invalid sha256 digest")

        # GitHub may add other digest algorithms; only sha256 is supported here.
        return None

    def _state_locked(self) -> dict:
        return {
            "status": self.status,
            "version": self.version,
            "latest": copy.deepcopy(self.latest),
            "downloaded_size": self.downloaded_size,
            "total_size": self.total_size,
            "error": self.error,
        }

    def get_update_state(self) -> dict:
        with self.lock:
            return self._state_locked()

    def get_latest(self) -> dict:
        with self.lock:
            return copy.deepcopy(self.latest)

    def get_download_progress(self) -> dict[str, int]:
        with self.lock:
            return {
                "downloaded_size": self.downloaded_size,
                "total_size": self.total_size,
            }

    def _prepare_download_locked(self) -> threading.Event:
        cancel_event = threading.Event()
        self._download_cancel_event = cancel_event
        self._download_active = True
        self.status = __class__.Status.UPDATING
        self.downloaded_size = 0
        self.total_size = 0
        self.error = ""
        self._last_emit_ts = None
        return cancel_event

    def _emit_download_progress(
        self,
        downloaded_size: int,
        total_size: int,
        *,
        force: bool = False,
    ) -> None:
        now = time.monotonic()
        with self.lock:
            self.downloaded_size = max(0, downloaded_size)
            self.total_size = max(0, total_size)
            should_emit = (
                force
                or self._last_emit_ts is None
                or now - self._last_emit_ts >= __class__.PROGRESS_EMIT_INTERVAL_SECONDS
            )
            if not should_emit:
                return
            self._last_emit_ts = now
            payload = self._state_locked()

        self.emit(Base.Event.APP_UPDATE_DOWNLOAD_UPDATE, payload)

    def _set_download_failure(self, error: str, *, cancelled: bool) -> dict:
        with self.lock:
            latest_version = str(self.latest.get("tag_name", ""))
            self.status = (
                __class__.Status.NEW_VERSION
                if __class__.parse_version(self.version)
                < __class__.parse_version(latest_version)
                else __class__.Status.NONE
            )
            self.downloaded_size = 0
            self.total_size = 0
            self.error = "" if cancelled else error
            payload = self._state_locked()
            payload["cancelled"] = cancelled
        return payload

    @staticmethod
    def _remove_temp_file(path: Path | None) -> None:
        if path is None:
            return
        try:
            if path.is_file():
                path.unlink()
        except OSError:
            pass

    # 解压
    def app_update_extract(self, event: str, data: dict) -> None:
        with self.lock:
            if self.extracting:
                return
            self.extracting = True
        thread = threading.Thread(
            target = self.app_update_extract_task,
            args = (event, data),
        )
        try:
            thread.start()
        except Exception:
            with self.lock:
                self.extracting = False
            raise

    # 检查
    def app_update_check_start(self, event: str, data: dict) -> None:
        threading.Thread(
            target = self.app_update_check_start_task,
            args = (event, data),
        ).start()

    # 下载
    def app_update_download_start(self, event: str, data: dict) -> None:
        with self.lock:
            if self._download_active or self.status == __class__.Status.UPDATING:
                return
            self._prepare_download_locked()

        threading.Thread(
            target = self.app_update_download_start_task,
            args = (event, data),
        ).start()

    # 取消下载
    def app_update_download_cancel(self, event: str, data: dict) -> None:
        self.cancel_download()

    def cancel_download(self) -> bool:
        with self.lock:
            if not self._download_active or self.status != __class__.Status.UPDATING:
                return False
            self._download_cancel_event.set()
            response = self._active_download_response

        # Closing the active stream interrupts a blocked read instead of waiting
        # for the next buffered chunk before cancellation can take effect.
        if response is not None:
            try:
                response.close()
            except Exception:
                pass
        return True

    # 解压
    def app_update_extract_task(self, event: str, data: dict) -> None:
        # 更新状态
        with self.lock:
            self.extracting = True

        if not getattr(sys, "frozen", False):
            self.emit(Base.Event.APP_TOAST_SHOW, {
                "type": Base.ToastType.WARNING,
                "message": "源码运行模式不支持自动更新，请下载新版覆盖安装目录 …",
                "duration": 10 * 1000,
            })
            with self.lock:
                self.extracting = False
            QDesktopServices.openUrl(QUrl(__class__.RELEASE_URL))
            return

        install_dir = Path(sys.executable).resolve().parent
        exe_path = Path(sys.executable).resolve()
        temp_zip_path = __class__.temp_zip_path()

        updater_candidates = [
            # V2 在前：存量安装里新旧两个更新器可能并存，优先用新版
            install_dir / "_internal" / "RenpyBoxUpdater2.exe",
            install_dir / "RenpyBoxUpdater2.exe",
            install_dir / "_internal" / "RenpyBoxUpdater.exe",
            install_dir / "RenpyBoxUpdater.exe",
        ]
        updater_exe = next((p for p in updater_candidates if p.is_file()), None)
        if updater_exe is None:
            self.emit(Base.Event.APP_TOAST_SHOW, {
                "type": Base.ToastType.ERROR,
                "message": f"{Localizer.get().app_new_version_apply_failure}Updater not found",
                "duration": 60 * 1000,
            })
            with self.lock:
                self.extracting = False
            QDesktopServices.openUrl(QUrl(__class__.RELEASE_URL))
            return

        if not temp_zip_path.is_file():
            self.emit(Base.Event.APP_TOAST_SHOW, {
                "type": Base.ToastType.ERROR,
                "message": f"{Localizer.get().app_new_version_apply_failure}Update package not found: {temp_zip_path}",
                "duration": 60 * 1000,
            })
            with self.lock:
                self.extracting = False
            return

        # 将 updater 复制到系统临时目录运行，避免更新时覆盖自身导致失败
        updater_runtime = updater_exe
        try:
            import tempfile

            tmp_dir = Path(tempfile.gettempdir())
            tmp_name = f"RenpyBoxUpdater_{os.getpid()}_{int(time.time())}.exe"
            updater_runtime = tmp_dir / tmp_name
            shutil.copy2(updater_exe, updater_runtime)
        except Exception:
            updater_runtime = updater_exe

        try:
            subprocess.Popen(
                [
                    str(updater_runtime),
                    "--pid",
                    str(os.getpid()),
                    "--zip",
                    str(temp_zip_path),
                    "--install-dir",
                    str(install_dir),
                    "--exe-name",
                    str(exe_path.name),
                    "--restart",
                ],
                cwd = str(install_dir),
            )

            self.emit(Base.Event.APP_TOAST_SHOW, {
                "type": Base.ToastType.SUCCESS,
                "message": Localizer.get().app_new_version_waiting_restart,
                "duration": 10 * 1000,
            })

            time.sleep(1)
            os.kill(os.getpid(), signal.SIGTERM)
        except Exception as e:
            self.emit(Base.Event.APP_TOAST_SHOW, {
                "type": Base.ToastType.ERROR,
                "message": f"{Localizer.get().app_new_version_apply_failure}{e}",
                "duration": 60 * 1000,
            })

            with self.lock:
                self.extracting = False

    # 检查
    def app_update_check_start_task(self, event: str, data: dict) -> None:
        manual = bool((data or {}).get("manual", False))
        try:
            response = httpx.get(__class__.API_URL, timeout = 60)
            response.raise_for_status()

            result = response.json()
            if not isinstance(result, dict):
                raise RuntimeError("Invalid release response")
            latest = __class__._normalize_release(result)
            latest_version = latest["tag_name"]
            new_version = (
                __class__.parse_version(self.get_version())
                < __class__.parse_version(latest_version)
            )

            with self.lock:
                self.latest = latest
                self.error = ""
                if self.status not in (
                    __class__.Status.UPDATING,
                    __class__.Status.DOWNLOADED,
                ):
                    self.status = (
                        __class__.Status.NEW_VERSION
                        if new_version
                        else __class__.Status.NONE
                    )
                payload = self._state_locked()

            payload.update({
                "new_version": new_version,
                "manual": manual,
            })

            if new_version:
                self.emit(Base.Event.APP_TOAST_SHOW, {
                    "type": Base.ToastType.SUCCESS,
                    "message": Localizer.get().app_new_version_toast.replace(
                        "{VERSION}", __class__.display_version(latest_version)
                    ),
                    "duration": 10 * 1000,
                })
            self.emit(Base.Event.APP_UPDATE_CHECK_DONE, payload)
        except Exception as exc:
            error = str(exc) or exc.__class__.__name__
            with self.lock:
                self.error = error
                payload = self._state_locked()
            payload.update({
                "new_version": False,
                "manual": manual,
                "error": error,
            })
            self.emit(Base.Event.APP_UPDATE_CHECK_DONE, payload)

    def _latest_for_download(self) -> dict:
        latest = self.get_latest()
        if latest.get("assets"):
            return latest

        response = httpx.get(__class__.API_URL, timeout = 60)
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict):
            raise RuntimeError("Invalid release response")
        latest = __class__._normalize_release(result)
        with self.lock:
            self.latest = latest
        return latest

    # 下载
    def app_update_download_start_task(self, event: str, data: dict) -> None:
        temp_zip_path = __class__.temp_zip_path()
        with self.lock:
            if not self._download_active:
                cancel_event = self._prepare_download_locked()
            else:
                cancel_event = self._download_cancel_event

        try:
            __class__._remove_temp_file(temp_zip_path)
            if cancel_event.is_set():
                raise _DownloadCancelled()

            latest = self._latest_for_download()
            target_asset = __class__._select_download_asset(latest)
            browser_download_url = str(target_asset.get("browser_download_url") or "")
            if not browser_download_url:
                raise RuntimeError("browser_download_url is empty")
            # digest fail-closed：资产没有可信 sha256 时拒绝自动下载安装，
            # 引导用户手动下载（GitHub 正常发布会自动生成 sha256 digest）
            expected_sha256 = __class__._expected_sha256(target_asset.get("digest"))
            if expected_sha256 is None:
                raise RuntimeError("Release asset has no sha256 digest, automatic update refused")
            if cancel_event.is_set():
                raise _DownloadCancelled()

            temp_zip_path.parent.mkdir(parents = True, exist_ok = True)

            with httpx.stream(
                "GET",
                browser_download_url,
                timeout = 120,
                follow_redirects = True,
            ) as response:
                with self.lock:
                    self._active_download_response = response
                try:
                    if cancel_event.is_set():
                        raise _DownloadCancelled()
                    response.raise_for_status()
                    try:
                        total_size = int(response.headers.get("Content-Length", 0))
                    except (TypeError, ValueError) as exc:
                        raise RuntimeError("Invalid Content-Length") from exc
                    if total_size <= 0:
                        raise RuntimeError("Content-Length is 0")

                    asset_size = __class__._safe_int(target_asset.get("size"))
                    downloaded_size = 0
                    sha256 = hashlib.sha256()
                    self._emit_download_progress(0, total_size, force = True)

                    with temp_zip_path.open("wb") as writer:
                        for chunk in response.iter_bytes(
                            chunk_size = __class__.DOWNLOAD_CHUNK_SIZE
                        ):
                            if cancel_event.is_set():
                                raise _DownloadCancelled()
                            if not chunk:
                                continue
                            writer.write(chunk)
                            sha256.update(chunk)
                            downloaded_size += len(chunk)
                            self._emit_download_progress(
                                downloaded_size,
                                total_size,
                                force = downloaded_size >= total_size,
                            )

                    if cancel_event.is_set():
                        raise _DownloadCancelled()
                finally:
                    with self.lock:
                        if self._active_download_response is response:
                            self._active_download_response = None

            actual_size = temp_zip_path.stat().st_size
            if actual_size != total_size:
                raise RuntimeError(
                    f"Downloaded size mismatch: expected {total_size}, got {actual_size}"
                )
            if asset_size > 0 and actual_size != asset_size:
                raise RuntimeError(
                    f"Asset size mismatch: expected {asset_size}, got {actual_size}"
                )
            if expected_sha256 is not None and sha256.hexdigest().lower() != expected_sha256:
                raise RuntimeError("sha256 digest mismatch")
            with self.lock:
                if cancel_event.is_set():
                    raise _DownloadCancelled()
                self.status = __class__.Status.DOWNLOADED
                self.downloaded_size = actual_size
                self.total_size = total_size
                self.error = ""
                self._download_active = False
                payload = self._state_locked()

            self.emit(Base.Event.APP_TOAST_SHOW, {
                "type": Base.ToastType.SUCCESS,
                "message": Localizer.get().app_new_version_success,
                "duration": 10 * 1000,
            })
            self.emit(Base.Event.APP_UPDATE_DOWNLOAD_DONE, payload)
        except _DownloadCancelled:
            __class__._remove_temp_file(temp_zip_path)
            payload = self._set_download_failure("", cancelled = True)
            with self.lock:
                self._download_active = False
            self.emit(Base.Event.APP_UPDATE_DOWNLOAD_ERROR, payload)
        except Exception as exc:
            __class__._remove_temp_file(temp_zip_path)
            if cancel_event.is_set():
                payload = self._set_download_failure("", cancelled = True)
                with self.lock:
                    self._download_active = False
                self.emit(Base.Event.APP_UPDATE_DOWNLOAD_ERROR, payload)
                return
            error = str(exc) or exc.__class__.__name__
            payload = self._set_download_failure(error, cancelled = False)
            with self.lock:
                self._download_active = False
            self.emit(Base.Event.APP_TOAST_SHOW, {
                "type": Base.ToastType.ERROR,
                "message": Localizer.get().app_new_version_failure + error,
                "duration": 60 * 1000,
            })
            self.emit(Base.Event.APP_UPDATE_DOWNLOAD_ERROR, payload)

    def get_status(self) -> Status:
        with self.lock:
            return self.status

    def set_status(self, status: Status) -> None:
        with self.lock:
            self.status = status

    def get_version(self) -> str:
        with self.lock:
            return self.version

    def set_version(self, version: str) -> None:
        with self.lock:
            self.version = version
