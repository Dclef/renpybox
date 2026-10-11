"""源码 .rpy 备份：Qt 源码翻译与 API source mode 共用。"""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Callable

from base.LogManager import LogManager


def _cleanup_atomic_tmp(tmp_path: Path) -> None:
    """清理原子复制留下的临时文件。

    Windows 上 ``shutil.copy2`` 会复制源只读属性，直接 unlink 会 PermissionError。
    只清自己的 tmp 只读位再删；删除仍失败则抛出，不得吞掉后假装无副作用。
    """
    if not tmp_path.exists():
        return
    try:
        os.chmod(tmp_path, stat.S_IWRITE | stat.S_IREAD)
    except OSError:
        pass
    tmp_path.unlink(missing_ok=True)


def _atomic_copy2(src: Path, dest: Path) -> None:
    """先写同目录临时文件再 replace，避免 copy2 中断留下半写目标。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{dest.name}.",
        suffix=".tmp",
        dir=str(dest.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        os.close(fd)
        shutil.copy2(src, tmp_path)
        os.replace(tmp_path, dest)
    except Exception:
        # 清理失败必须可见，不能 suppress 后留下只读 .tmp 却像已回滚。
        _cleanup_atomic_tmp(tmp_path)
        raise


def _path_key(path: Path) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def _is_link_or_reparse(path: Path) -> bool:
    """符号链接或 Windows reparse/junction，一律视为危险链接。"""
    try:
        if path.is_symlink():
            return True
    except OSError:
        return True
    try:
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _paths_overlap(left: Path, right: Path) -> bool:
    try:
        left_resolved = left.resolve(strict=False)
        right_resolved = right.resolve(strict=False)
    except Exception:
        left_resolved, right_resolved = left, right
    if _path_key(left_resolved) == _path_key(right_resolved):
        return True
    try:
        left_resolved.relative_to(right_resolved)
        return True
    except ValueError:
        pass
    try:
        right_resolved.relative_to(left_resolved)
        return True
    except ValueError:
        pass
    return False


def _validate_path_chain(path: Path, *, label: str) -> str | None:
    """校验路径自身及尚未存在时的父树：拒绝链接/reparse。"""
    try:
        current = path if path.exists() else path.parent
    except OSError as exc:
        return f"{label}不可用：{exc}"

    # 向上检查到根，避免父目录是 junction 导致越界写。
    seen: set[str] = set()
    while True:
        key = _path_key(current)
        if key in seen:
            break
        seen.add(key)
        try:
            if current.exists() and _is_link_or_reparse(current):
                return f"{label}或其父路径不能是符号链接/重解析点：{current}"
        except OSError as exc:
            return f"{label}检查失败：{exc}"
        parent = current.parent
        if _path_key(parent) == key:
            break
        current = parent
    return None


def validate_external_backup_root(
    backup_root: Path,
    *,
    source_root: Path,
    output_dir: Path | None = None,
    game_dir: Path | None = None,
) -> str | None:
    """校验外部备份目录；返回错误说明，None 表示可接受。"""
    try:
        resolved = backup_root.resolve(strict=False)
    except Exception as exc:
        return f"无法解析备份目录：{exc}"

    chain_error = _validate_path_chain(resolved, label="外部备份目录")
    if chain_error:
        return chain_error

    if _is_link_or_reparse(resolved) if resolved.exists() else False:
        return "外部备份目录不能是符号链接或重解析点"

    for label, other in (
        ("源码输入", source_root),
        *((("输出目录", output_dir),) if output_dir is not None else ()),
        *((("game 目录", game_dir),) if game_dir is not None else ()),
    ):
        try:
            other_resolved = other.resolve(strict=False)
        except Exception:
            other_resolved = other
        if _paths_overlap(resolved, other_resolved):
            return f"外部备份目录与{label}重叠，已拒绝：{resolved}"

    if game_dir is not None:
        try:
            game_resolved = game_dir.resolve(strict=False)
            if _paths_overlap(resolved, game_resolved):
                return (
                    f"禁止将 .rpy 备份写入 Ren'Py 会加载的 game 目录内：{resolved}"
                )
        except Exception:
            pass

    return None


def _plan_external_destinations(
    candidates: list[Path],
    *,
    base_dir: Path,
    backup_root: Path,
) -> tuple[list[tuple[Path, Path]], list[str]]:
    """写前全量规划外部备份目标；未通过前不 mkdir。"""
    planned: list[tuple[Path, Path]] = []
    warnings: list[str] = []
    seen_dest: set[str] = set()

    for path in candidates:
        if not path.is_file():
            continue
        if _is_link_or_reparse(path):
            warnings.append(f"跳过符号链接源文件：{path}")
            continue
        try:
            rel = path.relative_to(base_dir)
        except ValueError:
            rel = Path(path.name)
        dest = backup_root / rel
        dest_key = _path_key(dest.resolve(strict=False) if dest.exists() else dest)
        if dest_key in seen_dest:
            warnings.append(f"跳过重复备份目标：{dest}")
            continue
        seen_dest.add(dest_key)

        chain_error = _validate_path_chain(dest, label=f"备份目标 {dest}")
        if chain_error:
            warnings.append(chain_error)
            continue
        if dest.exists() and _is_link_or_reparse(dest):
            warnings.append(f"跳过指向符号链接的备份目标：{dest}")
            continue
        planned.append((path, dest))

    return planned, warnings


def backup_source_rpy(
    target: Path,
    backup_root: Path | None,
    *,
    should_stop: Callable[[], bool] | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
    output_dir: Path | None = None,
    game_dir: Path | None = None,
) -> dict[str, object]:
    """备份 .rpy 源文件。

    - ``backup_root`` 有值：复制到外部目录，保留相对路径，同名覆盖。
    - 否则：在源文件旁写 ``*.rpy.bak``，已存在则跳过。
    - 目录 ``target``：``rglob('*.rpy')``；单文件：仅自身。
    - 失败按 Qt 语义记 warning 并继续；取消时返回已复制数。
    """
    logger = LogManager.get()
    warnings: list[str] = []
    copied = 0
    cancelled = False
    written_files: list[str] = []

    target = Path(target)
    if backup_root is not None:
        backup_root = Path(backup_root)
        validation_error = validate_external_backup_root(
            backup_root,
            source_root=target if target.is_dir() else target.parent,
            output_dir=output_dir,
            game_dir=game_dir,
        )
        if validation_error:
            warnings.append(validation_error)
            return {
                "copied": 0,
                "warnings": warnings,
                "cancelled": False,
                "written_files": [],
            }

    base_dir = target.parent if target.is_file() else target
    candidates = [target] if target.is_file() else list(target.rglob("*.rpy"))

    if backup_root is not None:
        planned, plan_warnings = _plan_external_destinations(
            candidates,
            base_dir=base_dir,
            backup_root=backup_root,
        )
        warnings.extend(plan_warnings)
        if not planned and plan_warnings and not candidates:
            return {
                "copied": 0,
                "warnings": warnings,
                "cancelled": False,
                "written_files": [],
            }
        # 全部目标规划通过后才创建根目录。
        try:
            if planned:
                backup_root.mkdir(parents=True, exist_ok=True)
                if _is_link_or_reparse(backup_root):
                    warnings.append("外部备份目录创建后变成链接，已拒绝写入")
                    return {
                        "copied": 0,
                        "warnings": warnings,
                        "cancelled": False,
                        "written_files": [],
                    }
        except Exception as exc:
            warnings.append(f"创建备份目录失败：{exc}")
            return {
                "copied": 0,
                "warnings": warnings,
                "cancelled": False,
                "written_files": [],
            }

        total = len(planned)
        for index, (path, dest) in enumerate(planned, start=1):
            if should_stop is not None and should_stop():
                cancelled = True
                warnings.append("备份已取消")
                break
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                if _is_link_or_reparse(dest.parent):
                    warnings.append(f"跳过链接父目录下的备份目标：{dest}")
                    continue
                _atomic_copy2(path, dest)
                copied += 1
                written_files.append(str(dest))
            except Exception as exc:
                message = f"备份失败 {path}: {exc}"
                warnings.append(message)
                logger.warning(message)
            if progress_callback is not None:
                progress_callback(index, total, f"备份 {index}/{total}")
        return {
            "copied": copied,
            "warnings": warnings,
            "cancelled": cancelled,
            "written_files": written_files,
        }

    # 本地 *.rpy.bak：已存在不覆盖。
    file_candidates = [p for p in candidates if p.is_file() and not _is_link_or_reparse(p)]
    total = len(file_candidates)
    for index, path in enumerate(file_candidates, start=1):
        if should_stop is not None and should_stop():
            cancelled = True
            warnings.append("备份已取消")
            break
        try:
            bak = path.with_suffix(path.suffix + ".bak")
            if bak.exists():
                if progress_callback is not None:
                    progress_callback(index, total, f"跳过已有备份 {index}/{total}")
                continue
            if _is_link_or_reparse(bak) if bak.exists() else False:
                warnings.append(f"跳过链接备份目标：{bak}")
                continue
            _atomic_copy2(path, bak)
            copied += 1
            written_files.append(str(bak))
        except Exception as exc:
            message = f"备份失败 {path}: {exc}"
            warnings.append(message)
            logger.warning(message)
        if progress_callback is not None:
            progress_callback(index, total, f"备份 {index}/{total}")

    return {
        "copied": copied,
        "warnings": warnings,
        "cancelled": cancelled,
        "written_files": written_files,
    }
