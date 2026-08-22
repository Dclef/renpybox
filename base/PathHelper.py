"""运行时路径工具。"""
from __future__ import annotations

from base.AppPaths import get_app_paths


def get_resource_path(*segments: str) -> str:
    """解析兼容旧调用约定的资源路径。"""
    paths = get_app_paths()
    if segments:
        first = str(segments[0]).replace("\\", "/")
        if first == "resource" or first.startswith("resource/"):
            first_parts = tuple(part for part in first.split("/")[1:] if part)
            return str(paths.resource(*first_parts, *segments[1:]))
    return str(paths.app(*segments))


def get_app_path(*segments: str) -> str:
    """返回稳定的应用目录路径，不受当前工作目录变化影响。"""
    return str(get_app_paths().app(*segments))
