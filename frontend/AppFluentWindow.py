import os
import signal

from PyQt5.QtCore import QEvent
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QTimer
from PyQt5.QtCore import QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QApplication
from qfluentwidgets import FluentIcon
from qfluentwidgets import FluentWindow
from qfluentwidgets import InfoBar
from qfluentwidgets import InfoBarPosition
from qfluentwidgets import MessageBox
from qfluentwidgets import NavigationAvatarWidget
from qfluentwidgets import NavigationItemPosition
from qfluentwidgets import NavigationPushButton
from qfluentwidgets import Theme
from qfluentwidgets import isDarkTheme
from qfluentwidgets import setTheme
from qfluentwidgets import setThemeColor

from base.Base import Base
from base.LogManager import LogManager
from base.PathHelper import get_resource_path
from base.VersionManager import VersionManager
from frontend.AppSettingsPage import AppSettingsPage
from frontend.Project.PlatformPage import PlatformPage
from frontend.Project.ProjectPage import ProjectPage
from frontend.Setting.BasicSettingsPage import BasicSettingsPage
from frontend.Setting.CustomPromptPage import CustomPromptPage
from frontend.Setting.ExpertSettingsPage import ExpertSettingsPage
from frontend.TranslationPage import TranslationPage
from frontend.RenpyToolbox.RenpyToolboxPage import RenpyToolboxPage
from module.Config import Config
from module.Localizer.Localizer import Localizer

class AppFluentWindow(FluentWindow, Base):

    APP_WIDTH: int = 1280
    APP_HEIGHT: int = 800
    APP_THEME_COLOR: str = "#BCA483"
    HOMEPAGE: str = " RenpyBox"

    def __init__(self) -> None:
        super().__init__()
        self._is_closing = False

        # 设置主题颜色
        setThemeColor(AppFluentWindow.APP_THEME_COLOR)

        # 设置窗口属性
        self.resize(AppFluentWindow.APP_WIDTH, AppFluentWindow.APP_HEIGHT)
        self.setMinimumSize(AppFluentWindow.APP_WIDTH, AppFluentWindow.APP_HEIGHT)
        self.setWindowTitle(f"RenpyBox {VersionManager.get().get_version()}")
        self.titleBar.iconLabel.hide()

        # 设置启动位置
        desktop = QApplication.desktop().availableGeometry()
        self.move(desktop.width()//2 - self.width()//2, desktop.height()//2 - self.height()//2)

        # 设置侧边栏宽度
        self.navigationInterface.setExpandWidth(256)

        # 侧边栏默认展开
        self.navigationInterface.setMinimumExpandWidth(self.APP_WIDTH)
        self.navigationInterface.expand(useAni = False)

        # 隐藏返回按钮
        self.navigationInterface.panel.setReturnButtonVisible(False)

        # 添加页面
        self.add_pages()

        # 注册事件
        self.subscribe(Base.Event.APP_TOAST_SHOW, self.show_toast)
        self.subscribe(Base.Event.APP_UPDATE_CHECK_DONE, self.app_update_check_done)
        self.subscribe(Base.Event.APP_UPDATE_DOWNLOAD_DONE, self.app_update_download_done)
        self.subscribe(Base.Event.APP_UPDATE_DOWNLOAD_ERROR, self.app_update_download_error)
        self.subscribe(Base.Event.APP_UPDATE_DOWNLOAD_UPDATE, self.app_update_download_update)

        # 启动音效（可在“应用设置”里关闭）
        QTimer.singleShot(0, self.play_startup_sound)

        # 检查更新
        QTimer.singleShot(3000, lambda: self.emit(Base.Event.APP_UPDATE_CHECK_START, {}))

    def play_startup_sound(self) -> None:
        config = Config().load()
        if getattr(config, "startup_sound_enable", False) != True:
            return

        raw_path = getattr(config, "startup_sound_path", "")
        if isinstance(raw_path, str):
            raw_path = raw_path.strip()
        else:
            raw_path = ""

        sound_path = get_resource_path(raw_path) if raw_path else get_resource_path("resource", "Ciallo.mp3")
        if not os.path.isfile(sound_path):
            return

        try:
            from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer
        except Exception:
            return

        if getattr(self, "_startup_sound_player", None) is None:
            self._startup_sound_player = QMediaPlayer(self)

        volume = getattr(config, "startup_sound_volume", 80)
        volume = volume if isinstance(volume, int) else 80
        volume = max(0, min(100, volume))

        self._startup_sound_player.stop()
        self._startup_sound_player.setVolume(volume)
        self._startup_sound_player.setMedia(QMediaContent(QUrl.fromLocalFile(sound_path)))
        self._startup_sound_player.play()

    # 重写窗口关闭函数
    def closeEvent(self, event: QEvent) -> None:
        self._is_closing = True
        message_box = MessageBox("警告", "确定要关闭应用吗？", self)
        message_box.yesButton.setText("确认")
        message_box.cancelButton.setText("取消")

        if not message_box.exec():
            self._is_closing = False
            event.ignore()
        else:
            os.kill(os.getpid(), signal.SIGTERM)

    def _is_qobject_alive(self, obj) -> bool:
        """检查 Qt 对象是否仍可访问，避免访问已释放的 C++ 对象。"""
        if obj is None:
            return False
        try:
            # 访问底层 QObject 接口，若对象已释放会抛 RuntimeError
            _ = obj.metaObject()
            _ = obj.objectName()
        except RuntimeError:
            return False
        except Exception:
            pass
        return True

    def _is_app_closing(self) -> bool:
        app = QApplication.instance()
        if app is None:
            return True
        return self._is_closing or app.closingDown()

    def _cleanup_infobar_stale_refs(self) -> None:
        """清理 InfoBarManager 中已失效的条目，避免已删除对象参与布局计算。"""
        try:
            from qfluentwidgets.components.widgets.info_bar import InfoBarManager
        except Exception:
            return

        managers = getattr(InfoBarManager, "managers", {}) or {}
        for manager_cls in managers.values():
            try:
                manager = manager_cls()
                info_bars = getattr(manager, "infoBars", None)
                if info_bars is None or self not in info_bars:
                    continue

                bars = list(info_bars.get(self, []))
                alive_bars = [bar for bar in bars if self._is_qobject_alive(bar)]

                if len(alive_bars) != len(bars):
                    info_bars[self] = alive_bars
            except Exception:
                continue

    # 响应显示 Toast 事件
    def show_toast(self, event: str, data: dict) -> None:
        if self._is_app_closing() or not self._is_qobject_alive(self):
            return

        toast_type = data.get("type", Base.ToastType.INFO)
        toast_message = data.get("message", "")
        toast_duration = data.get("duration", 2500)

        if toast_type == Base.ToastType.ERROR:
            toast_func = InfoBar.error
        elif toast_type == Base.ToastType.WARNING:
            toast_func = InfoBar.warning
        elif toast_type == Base.ToastType.SUCCESS:
            toast_func = InfoBar.success
        else:
            toast_func = InfoBar.info

        # 创建新 toast 前先清理历史残留，避免 qfluentwidgets 在布局时访问已删除对象。
        self._cleanup_infobar_stale_refs()

        try:
            toast_func(
                title = "",
                content = toast_message,
                parent = self,
                duration = toast_duration,
                orient = Qt.Orientation.Horizontal,
                position = InfoBarPosition.TOP,
                isClosable = True,
            )
        except RuntimeError as exc:
            # 兼容 qfluentwidgets 已知竞态：InfoBar 在动画/布局阶段对象被释放。
            if "InfoBar has been deleted" in str(exc):
                self.warning(f"[UI] 忽略已删除 InfoBar 竞态异常: {exc}", console = False)
                self._cleanup_infobar_stale_refs()
                return
            raise

    # 切换主题
    def switch_theme(self) -> None:
        from widget.ThemeHelper import get_current_stylesheet
        from PyQt5.QtWidgets import QApplication
        
        config = Config().load()
        if not isDarkTheme():
            setTheme(Theme.DARK)
            config.theme = Config.THEME_DARK
        else:
            setTheme(Theme.LIGHT)
            config.theme = Config.THEME_LIGHT
        config.save()
        
        # 更新全局样式
        QApplication.instance().setStyleSheet(get_current_stylesheet())

    # 切换语言

    def open_project_page(self) -> None:
        if VersionManager.get().get_status() == VersionManager.Status.NEW_VERSION:
            # 更新 UI
            self.home_page_widget.setName(
                Localizer.get().app_new_version_update.replace("{PERCENT}", "0%")
            )

            # 触发下载事件
            self.emit(Base.Event.APP_UPDATE_DOWNLOAD_START, {})
        elif VersionManager.get().get_status() == VersionManager.Status.UPDATING:
            pass
        elif VersionManager.get().get_status() == VersionManager.Status.DOWNLOADED:
            self.emit(Base.Event.APP_UPDATE_EXTRACT, {})
        else:
            QDesktopServices.openUrl(QUrl(VersionManager.RELEASE_URL))

    # 更新 - 检查完成
    def app_update_check_done(self, event: str, data: dict) -> None:
        if data.get("new_version", False) == True:
            self.home_page_widget.setName(Localizer.get().app_new_version)

    # 更新 - 下载完成
    def app_update_download_done(self, event: str, data: dict) -> None:
        self.home_page_widget.setName(Localizer.get().app_new_version_downloaded)

    # 更新 - 下载报错
    def app_update_download_error(self, event: str, data: dict) -> None:
        self.home_page_widget.setName(__class__.HOMEPAGE)

    # 更新 - 下载更新
    def app_update_download_update(self, event: str, data: dict) -> None:
        total_size: int = data.get("total_size", 0)
        downloaded_size: int = data.get("downloaded_size", 0)
        percent = f"{downloaded_size / max(1, total_size) * 100:.2f}%"
        self.home_page_widget.setName(
            Localizer.get().app_new_version_update.replace("{PERCENT}", percent)
        )

    # 开始添加页面
    def add_pages(self) -> None:
        self.add_project_pages()
        self.navigationInterface.addSeparator(NavigationItemPosition.SCROLL)
        self.add_renpy_pages()  # 新增 Ren'Py 页面
        self.navigationInterface.addSeparator(NavigationItemPosition.SCROLL)
        self.add_task_pages()
        self.navigationInterface.addSeparator(NavigationItemPosition.SCROLL)
        self.add_setting_pages()
        self.navigationInterface.addSeparator(NavigationItemPosition.SCROLL)

        # 设置默认页面
        self.switchTo(self.translation_page)

        # 主题切换按钮
        self.navigationInterface.addWidget(
            routeKey = "theme_navigation_button",
            widget = NavigationPushButton(
                FluentIcon.CONSTRACT,
                "切换主题",
                False
            ),
            onClick = self.switch_theme,
            position = NavigationItemPosition.BOTTOM
        )

        # 应用设置按钮
        self.addSubInterface(
            AppSettingsPage("app_settings_page", self),
            FluentIcon.SETTING,
            "应用设置",
            NavigationItemPosition.BOTTOM,
        )

        # 项目主页按钮
        self.home_page_widget = NavigationAvatarWidget(
            __class__.HOMEPAGE,
            get_resource_path("resource", "icon.ico"),
        )
        self.navigationInterface.addWidget(
            routeKey = "avatar_navigation_widget",
            widget = self.home_page_widget,
            onClick = self.open_project_page,
            position = NavigationItemPosition.BOTTOM
        )

    # 添加项目类页面
    def add_project_pages(self) -> None:
        # 接口管理
        self.addSubInterface(
            PlatformPage("platform_page", self),
            FluentIcon.IOT,
            "接口管理",
            NavigationItemPosition.SCROLL
        )

        # 项目设置
        self.addSubInterface(
            ProjectPage("project_page", self),
            FluentIcon.FOLDER,
            "项目设置",
            NavigationItemPosition.SCROLL
        )

    # 添加 Ren'Py 页面
    def add_renpy_pages(self) -> None:
        # Ren'Py 百宝箱（统一的工具箱）
        self.addSubInterface(
            RenpyToolboxPage("renpy_toolbox_page", self),
            FluentIcon.GAME,
            "Ren'Py 百宝箱",
            NavigationItemPosition.SCROLL
        )

    # 添加任务类页面
    def add_task_pages(self) -> None:
        # 开始翻译
        self.translation_page = TranslationPage("translation_page", self)
        self.addSubInterface(
            self.translation_page,
            FluentIcon.PLAY,
            "开始翻译",
            NavigationItemPosition.SCROLL
        )

    # 添加设置类页面
    def add_setting_pages(self) -> None:
        # 基础设置
        self.addSubInterface(
            BasicSettingsPage("basic_settings_page", self),
            FluentIcon.ZOOM,
            "基础设置",
            NavigationItemPosition.SCROLL,
        )

        # 专家设置
        # 专家设置（如果启用）
        if LogManager.get().is_expert_mode():
            self.addSubInterface(
                ExpertSettingsPage("expert_settings_page", self),
                FluentIcon.EDUCATION,
                "专家设置",
                NavigationItemPosition.SCROLL
            )

        # 自定义提示词（独立导航）
        self.addSubInterface(
            CustomPromptPage("custom_prompt_page", self),
            FluentIcon.SPEAKERS,
            Localizer.get().app_custom_prompt_navigation_item,
            NavigationItemPosition.SCROLL,
        )

    def navigate_to_page(self, page):
        """导航到指定页面（不添加到侧边栏导航）"""
        if page is None:
            return
        # 如果页面不在 stackedWidget 中，先添加
        if page not in [self.stackedWidget.widget(i) for i in range(self.stackedWidget.count())]:
            self.stackedWidget.addWidget(page)
        # 切换到该页面
        self.stackedWidget.setCurrentWidget(page)

    # 添加质量类页面

