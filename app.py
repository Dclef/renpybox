import sys
import os
# 让 PyInstaller 找到 base、module、frontend 等包
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import argparse
import ctypes
import signal
import time
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
from PyQt5.QtGui import QFont
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication
from qfluentwidgets import Theme
from qfluentwidgets import setTheme
from rich.console import Console

from base.Base import Base
from base.CLIManager import CLIManager
from base.LogManager import LogManager
from base.VersionManager import VersionManager
from base.Version import Version
from base.PathHelper import get_resource_path
from frontend.AppFluentWindow import AppFluentWindow
from module.Config import Config
from module.Engine.Engine import Engine
from module.Localizer.Localizer import Localizer

# 切换到脚本所在目录
if getattr(sys, 'frozen', False):
    script_dir = os.path.dirname(sys.executable)
else:
    script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)

def excepthook(exc_type: type[BaseException], exc_value: BaseException, exc_traceback: TracebackType) -> None:
    LogManager.get().error(Localizer.get().log_crash, exc_value)

    if not isinstance(exc_value, KeyboardInterrupt):
        print("")
        for i in range(3):
            print(f"退出中 … Exiting … {3 - i} …")
            time.sleep(1)

    os.kill(os.getpid(), signal.SIGTERM)

if __name__ == "__main__":
    # 捕获全局异常
    sys.excepthook = lambda exc_type, exc_value, exc_traceback: excepthook(exc_type, exc_value, exc_traceback)

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

    # 设置工作目录
    sys.path.append(os.path.dirname(os.path.abspath(sys.argv[0])))

    # 创建文件夹
    os.makedirs("./input", exist_ok = True)
    os.makedirs("./output", exist_ok = True)

    # 载入并保存默认配置
    config = Config().load()

    # 加载版本号
    # 从 base.Version 获取单一事实来源
    version = Version.CURRENT
    
    # 尝试将版本号写入运行目录的 version.txt (可选，仅作展示)
    try:
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            
        v_path = os.path.join(base_dir, "version.txt")
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

    # 设置全局缩放比例
    if config.scale_factor == "50%":
        os.environ["QT_SCALE_FACTOR"] = "0.50"
    elif config.scale_factor == "75%":
        os.environ["QT_SCALE_FACTOR"] = "0.75"
    elif config.scale_factor == "150%":
        os.environ["QT_SCALE_FACTOR"] = "1.50"
    elif config.scale_factor == "200%":
        os.environ["QT_SCALE_FACTOR"] = "2.00"
    else:
        os.environ.pop("QT_SCALE_FACTOR", None)

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
    from widget.ThemeHelper import get_current_stylesheet, ThemeManager
    app.setStyleSheet(get_current_stylesheet())
    # 初始化主题管理器，监听主题切换
    theme_manager = ThemeManager.get()

    # 启动任务引擎
    Engine.get().run()

    # 创建版本管理器
    VersionManager.get().set_version(version)

    # 处理启动参数
    if CLIManager.get().run() == False:
        app_fluent_window = AppFluentWindow()
        app_fluent_window.show()

    # 进入事件循环，等待用户操作
    sys.exit(app.exec())