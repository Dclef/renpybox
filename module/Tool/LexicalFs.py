"""工程核心（错误修复 / 格式化 / 译文复用）共用的 lexical 文件系统边界。

不跟随 symlink/junction/reparse 遍历；先查 lexical 身份再决定是否进入子树。
"""

from __future__ import annotations

import os
import stat
from pathlib import Path


def lexical_abs(path: str | Path) -> Path:
    """规范化绝对路径但不跟随 reparse/symlink。"""
    return Path(os.path.normcase(os.path.abspath(os.path.expanduser(str(path)))))


def is_link_or_reparse(path: str | Path) -> bool:
    """符号链接或 Windows reparse/junction。"""
    target = Path(path)
    try:
        if target.is_symlink():
            return True
    except OSError:
        return True
    try:
        attributes = getattr(os.lstat(target), "st_file_attributes", 0) or 0
    except OSError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def reject_if_link_root(path: str | Path, *, label: str = "路径") -> Path:
    """拒绝根路径本身是链接/联接；返回 lexical 绝对路径。"""
    root = lexical_abs(path)
    if root.exists() and is_link_or_reparse(root):
        raise ValueError(f"{label}不能是符号链接/联接点: {root}")
    return root


def iter_rpy_files_lexical(folder_path: str | Path) -> list[Path]:
    """在 lexical 根下收集 .rpy；不进入 symlink/junction 子树，也不跟随文件链接。"""
    root = lexical_abs(folder_path)
    if not root.is_dir() or is_link_or_reparse(root):
        return []
    found: list[Path] = []
    for current, dirnames, filenames in os.walk(root, followlinks=False):
        base = Path(current)
        # 就地过滤，阻止 walk 进入联接目录
        dirnames[:] = sorted(
            name for name in dirnames if not is_link_or_reparse(base / name)
        )
        for name in filenames:
            if not name.casefold().endswith(".rpy"):
                continue
            path = base / name
            if is_link_or_reparse(path):
                continue
            if path.is_file():
                found.append(path)
    found.sort(key=lambda item: item.as_posix().casefold())
    return found


def path_has_link_escape(folder_path: str | Path) -> str | None:
    """若目录树内存在会被旧 rglob 跟随的链接/联接，返回说明；否则 None。"""
    root = lexical_abs(folder_path)
    if not root.is_dir():
        return None
    if is_link_or_reparse(root):
        return f"目录本身是符号链接/联接点: {root}"
    for current, dirnames, filenames in os.walk(root, followlinks=False):
        base = Path(current)
        for name in list(dirnames):
            child = base / name
            if is_link_or_reparse(child):
                return f"目录含链接/联接，已拒绝越界: {child}"
        for name in filenames:
            child = base / name
            if is_link_or_reparse(child):
                return f"目录含链接/联接文件，已拒绝越界: {child}"
    return None


def require_no_link_escape(folder_path: str | Path, *, label: str = "目录") -> Path:
    """写入前校验：根与子树不得含 symlink/junction；返回 lexical 根。

    路径缺失时抛出 FileNotFoundError（保留既有消息契约），链接/越界仍为 ValueError。
    """
    root = reject_if_link_root(folder_path, label=label)
    if not root.is_dir():
        # 与历史 resolve 校验一致：缺失/非目录用 FileNotFoundError，勿吞成 ValueError
        raise FileNotFoundError(f"{label}不存在: {root}")
    reason = path_has_link_escape(root)
    if reason:
        raise ValueError(reason)
    return root


def copytree_lexical(src: str | Path, dst: str | Path) -> Path:
    """按 lexical 边界复制目录树，跳过 symlink/junction 子项。"""
    import shutil

    source = require_no_link_escape(src, label="备份源")
    destination = lexical_abs(dst)

    def _ignore(directory: str, names: list[str]) -> list[str]:
        base = Path(directory)
        return [name for name in names if is_link_or_reparse(base / name)]

    shutil.copytree(source, destination, ignore=_ignore, symlinks=False)
    return destination
