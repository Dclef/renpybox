import os
import signal

from PyQt5.QtCore import QEvent
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QTimer
from PyQt5.QtCore import QUrl
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import QLabel
from PyQt5.QtWidgets import QWidget
from qfluentwidgets import FluentIcon
from qfluentwidgets import FluentWindow
from qfluentwidgets import MessageBox
from qfluentwidgets import NavigationAvatarWidget
from qfluentwidgets import NavigationItemPosition
from qfluentwidgets import NavigationPushButton
from qfluentwidgets import PushButton
from qfluentwidgets import Theme
from qfluentwidgets import isDarkTheme
from qfluentwidgets import setTheme
from qfluentwidgets import setThemeColor

from base.Base import Base
from base.EventTelemetry import HeartbeatMonitor
from frontend.NotificationService import NotificationService
from base.LogManager import LogManager
from base.PathHelper import get_resource_path
from base.Version import Version
from base.VersionManager import VersionManager
from frontend.AppSettingsPage import AppSettingsPage
from frontend.Agent.AgentPage import AgentPage
from frontend.Project.PlatformPage import PlatformPage
from frontend.Project.ProjectPage import ProjectPage
from frontend.Setting.BasicSettingsPage import BasicSettingsPage
from frontend.Setting.CustomPromptPage import CustomPromptPage
from frontend.Setting.ExpertSettingsPage import ExpertSettingsPage
from frontend.Setting.ChangelogDialog import ChangelogDialog
from frontend.Workbench.RenpyWorkbenchPage import RenpyWorkbenchPage
from frontend.TranslationPage import TranslationPage
from frontend.RenpyToolbox.RenpyToolboxPage import RenpyToolboxPage
from module.Config import Config
from module.Localizer.Localizer import Localizer
from widget.ThemeHelper import get_navigation_stylesheet


class AppFluentWindow(FluentWindow, Base):

    APP_WIDTH: int = 1280
    APP_HEIGHT: int = 800
    # 深靛蓝主题色将浅色模式按钮白字对比度提升至 6.29:1，完全满足并超越 WCAG AA
    # 4.5:1 标准，彻底清除旧版 2.39:1 导致的发灰看不清问题。
    APP_THEME_COLOR: str = "#4F46E5"
    HOMEPAGE: str = " RenpyBox"

    @classmethod
    def _resolve_window_size(cls) -> tuple[int, int]:
        """按主屏可用区域收缩窗口尺寸。

        高分屏（125%/150% 缩放）下逻辑分辨率变小，固定 1280x800 会超出屏幕，
        导致窗口盖住任务栏、右侧控件被裁掉。
        """
        screen = QApplication.primaryScreen()
        if screen is None:
            return cls.APP_WIDTH, cls.APP_HEIGHT
        available = screen.availableGeometry()
        return (
            min(cls.APP_WIDTH, available.width()),
            min(cls.APP_HEIGHT, available.height()),
        )

    def __init__(self) -> None:
        super().__init__()
        self._is_closing = False
        # 关闭系统 Mica 透明材质，确保原型定义的双主题表面在不同 Windows 设置下稳定。
        self.setMicaEffectEnabled(False)
        self.setCustomBackgroundColor("#F8FAFC", "#0B0F17")
        # Toast 决策（去重/聚合/级别）在服务内，窗口只负责展示适配
        self.notification = NotificationService(self)
        # 主线程心跳漂移测量：tick 实际间隔与名义间隔之差，>=50ms 记入遥测
        self._heartbeat = HeartbeatMonitor(interval_ms = 1000)
        self._heartbeat_timer = QTimer(self)
        self._heartbeat_timer.setInterval(1000)
        self._heartbeat_timer.timeout.connect(self._on_heartbeat_tick)
        self._heartbeat_timer.start()

        # 设置主题颜色
        setThemeColor(AppFluentWindow.APP_THEME_COLOR)

        # 设置窗口属性（在可用区域内居中，不压住任务栏）
        target_width, target_height = self._resolve_window_size()
        self.resize(target_width, target_height)
        self.setMinimumSize(target_width, target_height)
        self.setWindowTitle(f"RenpyBox {VersionManager.get().get_version()}")
        self._configure_title_bar()

        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            self.move(
                available.left() + max(0, (available.width() - self.width()) // 2),
                available.top() + max(0, (available.height() - self.height()) // 2),
            )

        # 设置侧边栏宽度
        self.navigationInterface.setExpandWidth(256)

        # 原型侧栏是固定 256px，不随窗口进入浮层菜单模式。
        self.navigationInterface.setCollapsible(False)
        self.navigationInterface.panel.setMenuButtonVisible(False)
        self.navigationInterface.setMinimumExpandWidth(self.APP_WIDTH)
        self.navigationInterface.expand(useAni = False)

        # 隐藏返回按钮
        self.navigationInterface.panel.setReturnButtonVisible(False)

        # 添加页面
        self.add_pages()
        self._apply_shell_theme()

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

        # 升级后的第一次启动仅展示当前版本日志；首次安装保持静默。
        self._schedule_post_update_changelog()

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
        self._heartbeat_timer.stop()

        strings = Localizer.get()
        message_box = MessageBox(strings.warning, strings.app_close_message_box, self)
        message_box.yesButton.setText(strings.confirm)
        message_box.cancelButton.setText(strings.cancel)

        if not message_box.exec():
            self._is_closing = False
            event.ignore()
        else:
            os.kill(os.getpid(), signal.SIGTERM)

    def _on_heartbeat_tick(self) -> None:
        if self._is_app_closing():
            self._heartbeat_timer.stop()
            return
        self._heartbeat.tick()

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

    # 响应显示 Toast 事件
    def show_toast(self, event: str, data: dict) -> None:
        if self._is_app_closing() or not self._is_qobject_alive(self):
            return

        self.notification.show(
            data.get("type", Base.ToastType.INFO),
            data.get("message", ""),
            data.get("duration", 2500),
        )

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
        self._apply_shell_theme()

    def _configure_title_bar(self) -> None:
        """将 QFluent 默认 48px 标题栏收敛为原型的 38px 壳层。"""
        self.titleBar.setFixedHeight(38)
        self.widgetLayout.setContentsMargins(0, 38, 0, 0)
        self.titleBar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        icon = self.titleBar.iconLabel
        icon.show()
        icon.setText(Localizer.get().app_brand_short)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            "background: #4F46E5; color: #FFFFFF; border-radius: 4px; "
            "font-size: 10px; font-weight: 700;"
        )
        self.titleBar.titleLabel.setText(Localizer.get().app_brand_name)

        version = QLabel(VersionManager.get().get_version(), self.titleBar)
        version.setObjectName("titleBarVersion")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version.setFixedHeight(20)
        self.titleBar.hBoxLayout.insertWidget(2, version, 0, Qt.AlignmentFlag.AlignVCenter)

        config = Config().load()
        project_path = str(getattr(config, "renpy_project_path", "") or "").strip()
        project_name = os.path.basename(os.path.normpath(project_path)) if project_path else ""
        project = QLabel(self.titleBar)
        project.setObjectName("titleBarProject")
        project.setText(
            Localizer.get().app_titlebar_project.format(NAME=project_name)
            if project_name
            else Localizer.get().app_titlebar_project_unset
        )
        project.setToolTip(project_path)
        project.setMaximumWidth(260)
        self.titleBar.hBoxLayout.insertWidget(3, project, 0, Qt.AlignmentFlag.AlignVCenter)

        theme_button = PushButton(
            Localizer.get().app_theme_btn,
            self.titleBar,
        )
        theme_button.setObjectName("titleBarThemeButton")
        theme_button.setFixedHeight(28)
        theme_button.clicked.connect(self.switch_theme)
        self.titleBar.hBoxLayout.insertWidget(4, theme_button, 0, Qt.AlignmentFlag.AlignVCenter)

    def resizeEvent(self, event: QEvent) -> None:
        """保留原生控制按钮，同时让标题栏覆盖完整窗口宽度。"""
        super().resizeEvent(event)
        self.titleBar.move(0, 0)
        self.titleBar.resize(self.width(), self.titleBar.height())

    def _apply_shell_theme(self) -> None:
        """同步窗口表面、导航背景和导航项颜色。"""
        self.setCustomBackgroundColor("#F8FAFC", "#0B0F17")
        panel = self.navigationInterface.panel
        panel.setStyleSheet(get_navigation_stylesheet())

        if isDarkTheme():
            title_bg = "#0F1420"
            title_fg = "#F1F5F9"
            muted = "#94A3B8"
            border = "rgba(255, 255, 255, 0.08)"
            button_bg = "#141B2A"
        else:
            title_bg = "#F1F5F9"
            title_fg = "#0F172A"
            muted = "#64748B"
            border = "rgba(15, 23, 42, 0.08)"
            button_bg = "#FFFFFF"
        self.titleBar.setStyleSheet(
            f"FluentTitleBar {{ background-color: {title_bg}; border-bottom: 1px solid {border}; }}"
            f"QLabel#titleLabel {{ color: {title_fg}; font-size: 12px; font-weight: 700; }}"
            f"QLabel#titleBarVersion {{ color: #6366F1; background: rgba(99, 102, 241, 0.12); "
            f"border: 1px solid rgba(99, 102, 241, 0.25); border-radius: 4px; padding: 0 6px; "
            f"font-size: 10px; font-weight: 600; }}"
            f"QLabel#titleBarProject {{ color: {muted}; background: {button_bg}; border: 1px solid {border}; "
            f"border-radius: 10px; padding: 0 9px; font-size: 11px; }}"
            f"QPushButton#titleBarThemeButton {{ color: {title_fg}; background: {button_bg}; border: 1px solid {border}; "
            f"border-radius: 4px; padding: 0 9px; font-size: 11px; }}"
            f"QPushButton#titleBarThemeButton:hover {{ background: {title_bg}; }}"
        )

        light_text = QColor("#334155")
        dark_text = QColor("#CBD5E1")
        light_indicator = QColor("#4F46E5")
        dark_indicator = QColor("#6366F1")
        for item in panel.items.values():
            for widget in (item.widget, *item.widget.findChildren(QWidget)):
                if hasattr(widget, "setTextColor"):
                    widget.setTextColor(light_text, dark_text)
                if hasattr(widget, "setIndicatorColor"):
                    widget.setIndicatorColor(light_indicator, dark_indicator)

    def open_app_settings_page(self) -> None:
        self.switchTo(self.app_settings_page)

    def _refresh_update_indicator(self) -> None:
        manager = VersionManager.get()
        state = (
            manager.get_update_state()
            if hasattr(manager, "get_update_state")
            else {"status": manager.get_status(), "downloaded_size": 0, "total_size": 0}
        )
        status = state.get("status", VersionManager.Status.NONE)
        latest = state.get("latest") if isinstance(state.get("latest"), dict) else {}
        known_update_available = (
            VersionManager.parse_version(str(state.get("version", Version.CURRENT)))
            < VersionManager.parse_version(str(latest.get("tag_name", "")))
        )
        if (
            status == VersionManager.Status.NEW_VERSION
            or status == VersionManager.Status.NONE and known_update_available
        ):
            name = Localizer.get().app_new_version
        elif status == VersionManager.Status.UPDATING:
            downloaded = state.get("downloaded_size", 0)
            total = state.get("total_size", 0)
            try:
                percent = int(int(downloaded) / max(1, int(total)) * 100)
            except (TypeError, ValueError):
                percent = 0
            name = Localizer.get().app_new_version_update.replace(
                "{PERCENT}", f"{max(0, min(100, percent))}%"
            )
        elif status == VersionManager.Status.DOWNLOADED:
            name = Localizer.get().app_new_version_downloaded
        else:
            name = __class__.HOMEPAGE
        self.home_page_widget.setName(name)

    # 更新 - 检查完成
    def app_update_check_done(self, event: str, data: dict) -> None:
        self._refresh_update_indicator()

    # 更新 - 下载完成
    def app_update_download_done(self, event: str, data: dict) -> None:
        self._refresh_update_indicator()

    # 更新 - 下载报错
    def app_update_download_error(self, event: str, data: dict) -> None:
        self._refresh_update_indicator()

    # 更新 - 下载更新
    def app_update_download_update(self, event: str, data: dict) -> None:
        self._refresh_update_indicator()

    def _schedule_post_update_changelog(self) -> None:
        config = Config().load()
        last_seen = str(getattr(config, "last_seen_version", "") or "").strip()
        if not last_seen:
            # 首次安装、或旧配置尚无该字段：静默记录，不打扰。
            config.last_seen_version = Version.CURRENT
            config.save()
            return
        if (
            VersionManager.parse_version(last_seen)
            < VersionManager.parse_version(Version.CURRENT)
        ):
            QTimer.singleShot(500, self._show_post_update_changelog)

    def _show_post_update_changelog(self) -> None:
        from frontend.Setting.ChangelogDialog import build_changelog_markdown

        if build_changelog_markdown(current_only_version=Version.CURRENT).strip():
            ChangelogDialog(self, current_only_version=Version.CURRENT).exec()

        config = Config().load()
        config.last_seen_version = Version.CURRENT
        config.save()

    # 开始添加页面
    def add_pages(self) -> None:
        self.add_project_pages()
        self.navigationInterface.addSeparator(NavigationItemPosition.SCROLL)
        self.add_workbench_pages()
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
                Localizer.get().app_theme_btn,
                False
            ),
            onClick = self.switch_theme,
            position = NavigationItemPosition.BOTTOM
        )

        # 语言设置按钮
        self.navigationInterface.addWidget(
            routeKey = "language_navigation_button",
            widget = NavigationPushButton(
                FluentIcon.LANGUAGE,
                Localizer.get().app_language_btn,
                False,
            ),
            onClick = self.open_app_settings_page,
            position = NavigationItemPosition.BOTTOM,
        )

        # 应用设置按钮
        self.app_settings_page = AppSettingsPage("app_settings_page", self)
        self.addSubInterface(
            self.app_settings_page,
            FluentIcon.SETTING,
            Localizer.get().app_settings_page,
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
            onClick = self.open_app_settings_page,
            position = NavigationItemPosition.BOTTOM
        )
        self._refresh_update_indicator()

    # 添加项目类页面
    def add_project_pages(self) -> None:
        # 接口管理
        self.addSubInterface(
            PlatformPage("platform_page", self),
            FluentIcon.IOT,
            Localizer.get().app_platform_page,
            NavigationItemPosition.SCROLL
        )

        # 项目设置
        self.addSubInterface(
            ProjectPage("project_page", self),
            FluentIcon.FOLDER,
            Localizer.get().app_project_page,
            NavigationItemPosition.SCROLL
        )

    # 添加 Ren'Py 页面
    def add_renpy_pages(self) -> None:
        # Ren'Py 百宝箱（统一的工具箱）
        self.renpy_toolbox_page = RenpyToolboxPage("renpy_toolbox_page", self)
        self.addSubInterface(
            self.renpy_toolbox_page,
            FluentIcon.GAME,
            Localizer.get().app_renpy_toolbox_page,
            NavigationItemPosition.SCROLL
        )

    # 添加角色 / 世界观工作台页面
    def add_workbench_pages(self) -> None:
        self.renpy_workbench_page = RenpyWorkbenchPage("renpy_workbench_page", self)
        self.addSubInterface(
            self.renpy_workbench_page,
            FluentIcon.PEOPLE,
            Localizer.get().app_workbench_page,
            NavigationItemPosition.SCROLL,
        )

    # 添加任务类页面
    def add_task_pages(self) -> None:
        # Agent 助手
        self.agent_page = AgentPage("agent_page", self)
        self.addSubInterface(
            self.agent_page,
            FluentIcon.ROBOT,
            Localizer.get().app_agent_page,
            NavigationItemPosition.SCROLL,
        )

        # 开始翻译
        self.translation_page = TranslationPage("translation_page", self)
        self.addSubInterface(
            self.translation_page,
            FluentIcon.PLAY,
            Localizer.get().app_translation_page,
            NavigationItemPosition.SCROLL
        )

    # 添加设置类页面
    def add_setting_pages(self) -> None:
        # 基础设置
        self.addSubInterface(
            BasicSettingsPage("basic_settings_page", self),
            FluentIcon.ZOOM,
            Localizer.get().app_basic_settings_page,
            NavigationItemPosition.SCROLL,
        )

        # 专家设置
        # 专家设置（如果启用）
        if LogManager.get().is_expert_mode():
            self.addSubInterface(
                ExpertSettingsPage("expert_settings_page", self),
                FluentIcon.EDUCATION,
                Localizer.get().app_expert_settings_page,
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

    def navigate_back_to_toolbox(self) -> None:
        """返回 Ren'Py 工具箱入口页。"""
        if getattr(self, "renpy_toolbox_page", None) is not None:
            self.switchTo(self.renpy_toolbox_page)

    # 添加质量类页面

