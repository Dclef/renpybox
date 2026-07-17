import os
import re
import shutil
import subprocess
import signal
import sys
import threading
import time
from pathlib import Path
from base.compat import StrEnum, Self

import httpx
from PyQt5.QtCore import QUrl
from PyQt5.QtGui import QDesktopServices

from base.Base import Base
from base.Version import Version
from module.Localizer.Localizer import Localizer

class VersionManager(Base):

    class Status(StrEnum):

        NONE = "NONE"
        NEW_VERSION = "NEW_VERSION"
        UPDATING = "UPDATING"
        DOWNLOADED = "DOWNLOADED"

    # 更新时的临时文件
    TEMP_PATH: str = "./resource/update.temp"

    # URL 地址
    API_URL: str = "https://api.github.com/repos/dclef/RenpyBox/releases/latest"
    RELEASE_URL: str = "https://github.com/dclef/RenpyBox/releases/latest"
    VERSION_RE: re.Pattern = re.compile(r"^(?:RenpyBox_)?v?(\d+(?:\.\d+){2,3})$")

    def __init__(self) -> None:
        super().__init__()

        # 初始化
        self.status = __class__.Status.NONE
        self.version = Version.CURRENT
        self.extracting = False

        # 线程锁
        self.lock: threading.Lock = threading.Lock()

        # 注册事件
        self.subscribe(Base.Event.APP_UPDATE_EXTRACT, self.app_update_extract)
        self.subscribe(Base.Event.APP_UPDATE_CHECK_START, self.app_update_check_start)
        self.subscribe(Base.Event.APP_UPDATE_DOWNLOAD_START, self.app_update_download_start)

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

    # 解压
    def app_update_extract(self, event: str, data: dict) -> None:
        with self.lock:
            if self.extracting == False:
                threading.Thread(
                    target = self.app_update_extract_task,
                    args = (event, data),
                ).start()

    # 检查
    def app_update_check_start(self, event: str, data: dict) -> None:
        threading.Thread(
            target = self.app_update_check_start_task,
            args = (event, data),
        ).start()

    # 下载
    def app_update_download_start(self, event: str, data: dict) -> None:
        threading.Thread(
            target = self.app_update_download_start_task,
            args = (event, data),
        ).start()

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
        temp_zip_path = (
            (install_dir / Path(__class__.TEMP_PATH)).resolve()
            if not Path(__class__.TEMP_PATH).is_absolute()
            else Path(__class__.TEMP_PATH).resolve()
        )

        updater_candidates = [
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
        try:
            # 获取更新信息
            response = httpx.get(__class__.API_URL, timeout = 60)
            response.raise_for_status()

            result: dict = response.json()
            latest_version = result.get("tag_name", "v0.0.0")

            if VersionManager.parse_version(VersionManager.get().get_version()) < VersionManager.parse_version(latest_version):
                self.set_status(VersionManager.Status.NEW_VERSION)
                self.emit(Base.Event.APP_TOAST_SHOW, {
                    "type": Base.ToastType.SUCCESS,
                    "message": Localizer.get().app_new_version_toast.replace("{VERSION}", latest_version),
                    "duration": 60 * 1000,
                })
                self.emit(Base.Event.APP_UPDATE_CHECK_DONE, {
                    "new_version": True,
                })
        except Exception:
            pass

    # 下载
    def app_update_download_start_task(self, event: str, data: dict) -> None:
        try:
            # 更新状态
            self.set_status(VersionManager.Status.UPDATING)

            # 获取更新信息
            response = httpx.get(__class__.API_URL, timeout = 60)
            response.raise_for_status()

            # 开始下载
            assets: list[dict] = response.json().get("assets", [])
            if not assets:
                raise Exception("No release assets found ...")

            zip_assets = [
                a for a in assets
                if str(a.get("name", "")).lower().endswith(".zip")
                or str(a.get("browser_download_url", "")).lower().endswith(".zip")
            ]
            target_asset = zip_assets[0] if zip_assets else assets[0]
            browser_download_url = target_asset.get("browser_download_url", "")
            if not browser_download_url:
                raise Exception("browser_download_url is empty ...")
            with httpx.stream("GET", browser_download_url, timeout = 120, follow_redirects = True) as response:
                response.raise_for_status()

                # 获取文件总大小
                total_size: int = int(response.headers.get("Content-Length", 0))
                downloaded_size: int = 0

                # 有效性检查
                if total_size == 0:
                    raise Exception("Content-Length is 0 ...")

                # 写入文件并更新进度（使用4MB缓冲区加速下载）
                os.remove(__class__.TEMP_PATH) if os.path.isfile(__class__.TEMP_PATH) else None
                os.makedirs(os.path.dirname(__class__.TEMP_PATH), exist_ok = True)
                with open(__class__.TEMP_PATH, "wb") as writer:
                    for chunk in response.iter_bytes(chunk_size = 4 * 1024 * 1024):
                        if chunk is not None:
                            writer.write(chunk)
                            downloaded_size = downloaded_size + len(chunk)
                            if total_size > downloaded_size:
                                self.emit(Base.Event.APP_UPDATE_DOWNLOAD_UPDATE, {
                                    "total_size": total_size,
                                    "downloaded_size": downloaded_size,
                                })
                            else:
                                self.set_status(VersionManager.Status.DOWNLOADED)
                                self.emit(Base.Event.APP_TOAST_SHOW, {
                                    "type": Base.ToastType.SUCCESS,
                                    "message": Localizer.get().app_new_version_success,
                                    "duration": 60 * 1000,
                                })
                                self.emit(Base.Event.APP_UPDATE_DOWNLOAD_DONE, {})
        except Exception as e:
            self.set_status(VersionManager.Status.NONE)
            self.emit(Base.Event.APP_TOAST_SHOW, {
                "type": Base.ToastType.ERROR,
                "message": Localizer.get().app_new_version_failure + str(e),
                "duration": 60 * 1000,
            })
            self.emit(Base.Event.APP_UPDATE_DOWNLOAD_ERROR, {})

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
