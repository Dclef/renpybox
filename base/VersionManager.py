import os
import re
import shutil
import signal
import sys
import threading
import time
import zipfile
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
        exe_bak_path = install_dir / f"{exe_path.name}.bak"

        version_path = install_dir / "version.txt"
        version_bak_path = install_dir / "version.txt.bak"

        config_path = install_dir / "resource" / "config.json"
        config_bak_path = install_dir / "resource" / "config.json.bak"

        temp_zip_path = (
            (install_dir / Path(__class__.TEMP_PATH)).resolve()
            if not Path(__class__.TEMP_PATH).is_absolute()
            else Path(__class__.TEMP_PATH).resolve()
        )

        extracted_root_path = install_dir / "RenpyBox"

        # 删除临时/备份文件（包含旧逻辑的遗留文件）
        for legacy in [
            install_dir / "app.exe.bak",
            exe_bak_path,
            version_bak_path,
        ]:
            try:
                legacy.unlink()
            except Exception:
                pass

        try:
            if extracted_root_path.exists():
                shutil.rmtree(extracted_root_path, ignore_errors = True)
        except Exception:
            pass

        # 备份用户配置（保留用户设置，不随更新覆盖）
        if config_path.is_file():
            try:
                os.makedirs(config_path.parent, exist_ok = True)
                shutil.copy2(config_path, config_bak_path)
            except Exception:
                pass

        # 备份关键文件
        try:
            if exe_path.is_file():
                os.rename(exe_path, exe_bak_path)
            else:
                raise FileNotFoundError(str(exe_path))
        except Exception as e:
            self.emit(Base.Event.APP_TOAST_SHOW, {
                "type": Base.ToastType.ERROR,
                "message": f"{Localizer.get().app_new_version_apply_failure}{e}",
                "duration": 60 * 1000,
            })
            with self.lock:
                self.extracting = False
            return

        try:
            if version_path.is_file():
                try:
                    os.rename(version_path, version_bak_path)
                except Exception:
                    pass

            # 开始更新（解压到安装目录）
            with zipfile.ZipFile(temp_zip_path) as zip_file:
                zip_file.extractall(install_dir)

            # 先复制再删除的方式实现覆盖同名文件
            shutil.copytree(extracted_root_path, install_dir, dirs_exist_ok = True)
            shutil.rmtree(extracted_root_path, ignore_errors = True)

            # 恢复用户配置
            if config_bak_path.is_file():
                try:
                    shutil.copy2(config_bak_path, config_path)
                except Exception:
                    pass

            # 删除临时包
            try:
                os.remove(temp_zip_path)
            except Exception:
                pass

            # 显示提示
            self.emit(Base.Event.APP_TOAST_SHOW,{
                "type": Base.ToastType.SUCCESS,
                "message": Localizer.get().app_new_version_waiting_restart,
                "duration": 60 * 1000,
            })

            # 延迟3秒后关闭应用并打开更新日志
            time.sleep(3)
            QDesktopServices.openUrl(QUrl(__class__.RELEASE_URL))
            os.kill(os.getpid(), signal.SIGTERM)
        except Exception as e:
            self.error("Apply update failed", e)

            # 尝试回滚关键文件
            try:
                if exe_path.is_file():
                    os.remove(exe_path)
            except Exception:
                pass
            try:
                if exe_bak_path.is_file():
                    os.rename(exe_bak_path, exe_path)
            except Exception:
                pass

            try:
                if version_path.is_file():
                    os.remove(version_path)
            except Exception:
                pass
            try:
                if version_bak_path.is_file():
                    os.rename(version_bak_path, version_path)
            except Exception:
                pass

            # 恢复用户配置
            if config_bak_path.is_file():
                try:
                    shutil.copy2(config_bak_path, config_path)
                except Exception:
                    pass

            # 清理临时目录（失败也尽量不影响用户）
            try:
                if extracted_root_path.exists():
                    shutil.rmtree(extracted_root_path, ignore_errors = True)
            except Exception:
                pass

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
            a, b, c = re.findall(r"v(\d+)\.(\d+)\.(\d+)$", VersionManager.get().get_version())[-1]
            x, y, z = re.findall(r"v(\d+)\.(\d+)\.(\d+)$", result.get("tag_name", "v0.0.0"))[-1]

            if (
                int(a) < int(x)
                or (int(a) == int(x) and int(b) < int(y))
                or (int(a) == int(x) and int(b) == int(y) and int(c) < int(z))
            ):
                self.set_status(VersionManager.Status.NEW_VERSION)
                self.emit(Base.Event.APP_TOAST_SHOW, {
                    "type": Base.ToastType.SUCCESS,
                    "message": Localizer.get().app_new_version_toast.replace("{VERSION}", f"v{x}.{y}.{z}"),
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
            with httpx.stream("GET", browser_download_url, timeout = 60, follow_redirects = True) as response:
                response.raise_for_status()

                # 获取文件总大小
                total_size: int = int(response.headers.get("Content-Length", 0))
                downloaded_size: int = 0

                # 有效性检查
                if total_size == 0:
                    raise Exception("Content-Length is 0 ...")

                # 写入文件并更新进度
                os.remove(__class__.TEMP_PATH) if os.path.isfile(__class__.TEMP_PATH) else None
                os.makedirs(os.path.dirname(__class__.TEMP_PATH), exist_ok = True)
                with open(__class__.TEMP_PATH, "wb") as writer:
                    for chunk in response.iter_bytes(chunk_size = 1024 * 1024):
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
