"""应用运行路径的单一事实来源。"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    """描述源码运行和 PyInstaller 运行共用的应用目录。"""

    root: Path
    resource_root: Path | None = None

    @classmethod
    def detect(cls) -> "AppPaths":
        """根据当前运行方式定位应用根目录。"""
        if getattr(sys, "frozen", False):
            root = Path(sys.executable).resolve().parent
        else:
            root = Path(__file__).resolve().parents[1]

        # PyInstaller one-file 程序把只读资源解压到 _MEIPASS；配置、日志等
        # 可写文件仍然放在 exe 所在目录，避免把用户数据写入临时目录。
        meipass = getattr(sys, "_MEIPASS", None)
        resource_root = Path(meipass).resolve() if meipass else None
        return cls(root, resource_root=resource_root)

    @classmethod
    def from_root(cls, root: str | Path) -> "AppPaths":
        """为测试或外部启动器创建指定根目录的路径集合。"""
        return cls(Path(root).resolve())

    def app(self, *parts: str) -> Path:
        """返回应用目录下的路径。"""
        return self.root.joinpath(*parts)

    def resource(self, *parts: str) -> Path:
        """返回应用资源目录下的路径。"""
        resource_root = self.resource_root or self.root
        return resource_root.joinpath("resource", *parts)

    @property
    def config_path(self) -> Path:
        """返回用户配置文件路径。"""
        return self.app("config.json")

    @property
    def input_path(self) -> Path:
        """返回默认输入目录。"""
        return self.app("input")

    @property
    def output_path(self) -> Path:
        """返回默认输出目录。"""
        return self.app("output")

    @property
    def log_path(self) -> Path:
        """返回日志目录。"""
        return self.app("log")


def get_app_paths() -> AppPaths:
    """返回当前进程的应用路径集合。"""
    return AppPaths.detect()
