import sys
import os
# 让 PyInstaller 找到 base、module、frontend 等包
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import contextlib
import ctypes
import io
import signal
import time
import warnings
from pathlib import Path
from types import TracebackType

# 添加项目根目录到 Python 路径，确保在 PyInstaller 环境下也能正确导入模块
if getattr(sys, 'frozen', False):
    # 如果是 PyInstaller 打包的程序
    application_path = Path(sys.executable).parent
else:
    # 如果是直接从源码运行
    application_path = Path(__file__).parent

# 将应用根目录添加到 sys.path
if str(application_path) not in sys.path:
    sys.path.insert(0, str(application_path))

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtGui import QFont
from PyQt5.QtGui import QIcon
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import QSplashScreen
from rich.console import Console

# 屏蔽 requests 在冻结环境中的依赖兼容警告，避免启动时污染控制台。
warnings.filterwarnings(
    "ignore",
    message = r"urllib3 .* or chardet .*/charset_normalizer .* doesn't match a supported version!",
    category = Warning,
    module = r"requests(\..*)?$",
)

# qfluentwidgets 导入时会直接 print Pro 提示，这里在启动阶段静默处理。
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    from qfluentwidgets import Theme
    from qfluentwidgets import setTheme

from base.CLIManager import CLIManager
from base.AppPaths import get_app_paths
from base.LogManager import LogManager
from base.VersionManager import VersionManager
from base.Version import Version
from base.PathHelper import get_resource_path
from module.Config import Config
from module.Engine.Engine import Engine
from module.Localizer.Localizer import Localizer

def excepthook(exc_type: type[BaseException], exc_value: BaseException, exc_traceback: TracebackType) -> None:
    LogManager.get().error(Localizer.get().log_crash, exc_value)

    if not isinstance(exc_value, KeyboardInterrupt):
        print("")
        for i in range(3):
            print(f"退出中 … Exiting … {3 - i} …")
            time.sleep(1)

    os.kill(os.getpid(), signal.SIGTERM)

def _threading_excepthook(args) -> None:
    if args.exc_type is SystemExit:
        return
    LogManager.get().error(f"[Thread-{args.thread and args.thread.name}] 子线程未捕获异常", args.exc_value)


def _create_startup_splash(app: QApplication) -> QSplashScreen:
    """创建轻量启动页，让初始化期间立即有可见反馈。"""
    pixmap = QPixmap(get_resource_path("resource", "startup", "renpybox-splash.png"))
    if pixmap.isNull():
        pixmap = QPixmap(640, 360)
        pixmap.fill(QColor("#17263D"))
    else:
        pixmap = pixmap.scaled(
            640,
            360,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )

    splash = QSplashScreen(pixmap, Qt.WindowStaysOnTopHint)
    splash.setWindowIcon(app.windowIcon())
    splash.show()
    app.processEvents()
    return splash

if __name__ == "__main__":
    # 捕获全局异常
    sys.excepthook = lambda exc_type, exc_value, exc_traceback: excepthook(exc_type, exc_value, exc_traceback)

    # 捕获子线程未处理异常，避免子线程异常导致主进程崩溃
    import threading
    threading.excepthook = _threading_excepthook

    # 当运行在 Windows 系统且没有运行在新终端时，禁用快速编辑模式
    if os.name == "nt" and Console().color_system != "truecolor":
        kernel32 = ctypes.windll.kernel32

        # 获取控制台句柄
        hStdin = kernel32.GetStdHandle(-10)
        mode = ctypes.c_ulong()

        # 获取当前控制台模式
        if kernel32.GetConsoleMode(hStdin, ctypes.byref(mode)):
            # 清除启用快速编辑模式的标志 (0x0040)
            mode.value &= ~0x0040
            # 设置新的控制台模式
            kernel32.SetConsoleMode(hStdin, mode)

    # 1. 全局缩放使能 (Enable High DPI Scaling)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    # 2. 适配非整数倍缩放 (Adapt non-integer scaling)
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    # 仅添加导入路径，不改变进程工作目录；所有应用文件通过 AppPaths 定位。
    sys.path.append(os.path.dirname(os.path.abspath(sys.argv[0])))

    # 创建文件夹
    paths = get_app_paths()
    paths.input_path.mkdir(parents = True, exist_ok = True)
    paths.output_path.mkdir(parents = True, exist_ok = True)

    # deepcopy 调用热点遥测（幂等；独立脚本不受影响，见 base/EventTelemetry.py）
    try:
        from base.EventTelemetry import install_deepcopy_instrumentation

        install_deepcopy_instrumentation()
    except Exception:
        pass

    # 载入并保存默认配置
    config = Config().load()

    # 先持久化稳定凭据身份，再迁移存量 API Key；失败保留可恢复来源等下次启动
    try:
        from module.Secret.SecretStore import SecretStore

        SecretStore.get().migrate_config(config)
    except Exception as e:
        LogManager.get().warning(f"[Secret] 密钥迁移失败，保留明文存储: {e}")

    # 加载版本号
    # 从 base.Version 获取单一事实来源
    version = Version.CURRENT
    
    # 尝试将版本号写入运行目录的 version.txt (可选，仅作展示)
    try:
        v_path = paths.app("version.txt")
        with open(v_path, "w", encoding="utf-8") as f:
            f.write(version)
    except Exception:
        # 写入失败也不影响程序运行
        pass

    # 设置主题
    setTheme(Theme.DARK if config.theme == Config.THEME_DARK else Theme.LIGHT)

    # 设置应用语言
    Localizer.set_app_language(config.app_language)

    # 打印日志
    LogManager.get().info(f"RenpyBox {version}")
    LogManager.get().info(Localizer.get().log_expert_mode) if LogManager.get().is_expert_mode() else None

    # 网络代理
    if config.proxy_enable == False or config.proxy_url == "":
        os.environ.pop("http_proxy", None)
        os.environ.pop("https_proxy", None)
    else:
        LogManager.get().info(Localizer.get().log_proxy)
        os.environ["http_proxy"] = config.proxy_url
        os.environ["https_proxy"] = config.proxy_url

    # 小于 1 的设备像素比会导致 Qt5 控件错位，旧配置统一回退到系统缩放。
    scale_factor = Config.UI_SCALE_FACTORS.get(config.scale_factor)
    if scale_factor is None:
        os.environ.pop("QT_SCALE_FACTOR", None)
    else:
        os.environ["QT_SCALE_FACTOR"] = scale_factor

    # 创建全局应用对象
    app = QApplication(sys.argv)

    # 设置应用图标
    app.setWindowIcon(QIcon(get_resource_path("resource", "icon.ico")))

    # 设置全局字体属性，解决狗牙问题
    font = QFont()
    if config.font_hinting == True:
        font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    else:
        font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    app.setFont(font)

    # 应用全局主题样式（处理原生 Qt 控件）
    from widget.ThemeHelper import get_current_stylesheet
    app.setStyleSheet(get_current_stylesheet())

    splash = None
    if "--cli" not in sys.argv:
        splash = _create_startup_splash(app)

    # 创建版本管理器
    VersionManager.get().set_version(version)

    # 启动任务引擎；启动页会覆盖这段初始化等待。
    Engine.get().run()

    # 处理启动参数
    if CLIManager.get().run() == False:
        # 加载页已经显示，再导入重型窗口页面，避免用户看到空白等待。
        from frontend.AppFluentWindow import AppFluentWindow

        app_fluent_window = AppFluentWindow()
        app_fluent_window.show()
        if splash is not None:
            splash.finish(app_fluent_window)

    # 进入事件循环，等待用户操作
    sys.exit(app.exec())
