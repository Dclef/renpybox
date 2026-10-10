"""解包 / 反编译 / 打包的无界面操作，供 API 与旧 Qt 页共用。"""

from __future__ import annotations

import os
import re
import shutil
import stat
from decimal import Decimal
from pathlib import Path
from typing import Callable

from module.Localizer.Localizer import Localizer
from module.Tool.Packer import Packer, PackerUnpackError
from module.Tool.RenpyDecompiler import RenpyDecompiler

SIZE_LIMIT_PATTERN = re.compile(
    r"^\s*([0-9]+(?:\.[0-9]+)?)\s*(G(?:I?B)?|M(?:I?B)?)?\s*$",
    re.IGNORECASE,
)
GAME_DIR_NAME = "game"
EXE_SUFFIX = ".exe"
RPA_SUFFIX = ".rpa"

# 解包/反编译工具遗留物白名单（与 Qt5 CleanupWorker 一致），只按固定名称匹配，不做通配。
TEMP_GAME_DIRS = ("__pycache__", "unpacked_rpa")
TEMP_ROOT_FILES = (
    "unpack.finish",
    "game.pid",
    "common_backup.zip",
    "unrpyc.complete",
    "decomp.cab",
    "decomp.cab.tmp",
    "unrpyc.py",
    "unrpyc.pyo",
    "deobfuscate.py",
    "deobfuscate.pyo",
)
TEMP_ROOT_DIRS = ("decompiler",)


def parse_rpa_size_limit(value: str) -> int:
    """解析 G、GB、GiB、M、MB、MiB 容量格式，无单位时按 MiB。"""
    match = SIZE_LIMIT_PATTERN.fullmatch(value)
    if not match:
        raise ValueError(Localizer.get().pack_unpack_invalid_part_size_enter_1g_1_5g)
    number = Decimal(match.group(1))
    if number <= 0:
        raise ValueError(Localizer.get().pack_unpack_part_size_must_greater_than_0)
    unit = (match.group(2) or "M").upper()
    multiplier = 1024 ** 3 if unit.startswith("G") else 1024 ** 2
    size_bytes = int(number * multiplier)
    if size_bytes <= 0:
        raise ValueError(Localizer.get().pack_unpack_part_size_must_greater_than_0)
    return size_bytes


def resolve_game_dir(target: str | Path) -> Path:
    """从游戏根、game 目录或可执行文件解析 game 目录。"""
    if isinstance(target, str) and not target.strip():
        raise ValueError("游戏路径不能为空")
    path = Path(target).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"路径不存在：{path}")
    resolved = path.resolve()
    if resolved.is_file() and resolved.suffix.lower() == EXE_SUFFIX:
        root_dir = resolved.parent
    else:
        root_dir = resolved
    if root_dir.is_dir() and root_dir.name.lower() == GAME_DIR_NAME:
        return root_dir
    game_dir = root_dir / GAME_DIR_NAME
    if game_dir.is_dir():
        return game_dir
    raise FileNotFoundError(Localizer.get().pack_unpack_could_not_locate_game_folder_unren_fallback)


def resolve_pack_source(path: str | Path) -> Path:
    """打包源必须是已存在的目录。"""
    if isinstance(path, str) and not path.strip():
        raise ValueError("打包源路径不能为空")
    source = Path(path).expanduser().resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"打包源目录不存在：{source}")
    return source


def resolve_pack_output(source_dir: str | Path, output_file: str | Path | None) -> Path:
    """解析打包输出；留空时按 Qt5 规则推导为源目录同级的“源目录名.rpa”。"""
    source = resolve_pack_source(source_dir)
    text = str(output_file or "").strip()
    if text:
        output = Path(text).expanduser().resolve()
    else:
        if not source.name:
            raise ValueError(f"无法从源目录推导输出文件名：{source}")
        output = source.parent / f"{source.name}{RPA_SUFFIX}"
    if not output.name.lower().endswith(RPA_SUFFIX):
        raise ValueError("输出文件必须以 .rpa 结尾")
    if not output.parent.is_dir():
        raise FileNotFoundError(f"输出目录不存在：{output.parent}")
    return output


def unpack_game(
    game_dir: str | Path,
    *,
    direct: bool = True,
    script_only: bool = False,
    progress_callback: Callable[[str], None] | None = None,
    packer: Packer | None = None,
) -> dict:
    """解包 RPA；始终保留源档（remove_archives=False）。"""
    if isinstance(game_dir, str) and not game_dir.strip():
        raise ValueError("游戏目录不能为空")
    target = Path(game_dir)
    if not target.is_dir():
        raise FileNotFoundError(f"游戏目录不存在：{target}")
    messages = {
        "direct": Localizer.get().pack_unpack_trying_direct_unpacking,
        "direct_failed": Localizer.get().pack_unpack_direct_unpacking_failed_trying_external_tools,
        "external": Localizer.get().pack_unpack_unpacking,
        "unren_bat": Localizer.get().pack_unpack_trying_unren_fallback,
    }

    def on_stage(stage: str) -> None:
        if progress_callback is not None:
            progress_callback(messages.get(stage, stage))

    result = (packer or Packer()).unpack_rpa_files(
        str(target),
        direct=direct,
        script_only=script_only,
        remove_archives=False,
        progress_callback=on_stage,
    )
    method = result.get("method")
    count = int(result.get("count", 0))
    if result.get("success"):
        if method == "direct":
            message = Localizer.get().pack_unpack_directly_unpacked_archive_s.format(count=count)
        elif method == "external":
            message = Localizer.get().pack_unpack_unpacked_rpa_file_s.format(count=count)
        else:
            message = Localizer.get().pack_unpack_unpacked_unren_fallback_check_game_folder_output
        return {
            "success": True,
            "level": "success",
            "message": message,
            "method": method,
            "count": count,
            "archives_removed": False,
            "game_dir": str(target),
        }
    return {
        "success": False,
        "level": "info",
        "message": Localizer.get().pack_unpack_error(str(result.get("code") or "")),
        "method": method,
        "count": count,
        "code": result.get("code"),
        "archives_removed": False,
        "game_dir": str(target),
    }


def decompile_target(
    target: str | Path,
    *,
    overwrite: bool = False,
    use_unren: bool = True,
    fallback_unren_options: str | None = "2x",
    progress_callback: Callable[[str], None] | None = None,
    packer: Packer | None = None,
    decompiler: RenpyDecompiler | None = None,
) -> dict:
    """先 unrpyc，失败且启用时用 UnRen 兜底。"""
    from base.LogManager import LogManager

    def progress(message: str) -> None:
        if progress_callback is not None:
            progress_callback(message)

    unrpyc_error: Exception | None = None
    try:
        progress(Localizer.get().pack_unpack_decompiling_unrpyc)
        game_dir = resolve_game_dir(target)
        (decompiler or RenpyDecompiler()).decompile(
            str(target),
            overwrite=overwrite,
            output_callback=lambda line: progress(f"unrpyc：{line}"),
        )
        return {
            "success": True,
            "level": "success",
            "message": Localizer.get().pack_unpack_decompilation_complete_generated_rpy_files,
            "method": "unrpyc",
            "game_dir": str(game_dir),
            "overwrite": overwrite,
        }
    except Exception as exc:
        unrpyc_error = exc
        LogManager.get().error(f"unrpyc 反编译失败: {exc}")

    unren_error: Exception | None = None
    if use_unren and fallback_unren_options:
        try:
            progress(Localizer.get().pack_unpack_decompiling_unren)
            game_dir = resolve_game_dir(target)
            ok, _lines = (packer or Packer()).unpack_all_unren_bat(
                str(game_dir),
                lang="zh",
                options=fallback_unren_options,
                purpose="反编译兜底",
                timeout_s=60 * 60,
                output_callback=lambda line: progress(f"UnRen：{line}"),
            )
            if ok:
                return {
                    "success": True,
                    "level": "success",
                    "message": Localizer.get().pack_unpack_decompilation_completed_unren,
                    "method": "unren",
                    "game_dir": str(game_dir),
                    "overwrite": overwrite,
                }
            unren_error = RuntimeError("UnRen 返回失败")
        except Exception as unren_exc:
            unren_error = unren_exc
            LogManager.get().error(f"UnRen 反编译兜底失败: {unren_exc}")

    extra = ""
    if unrpyc_error:
        extra += f"\nunrpyc：{unrpyc_error}"
    if unren_error:
        extra += "\n" + Localizer.get().pack_unpack_unren_failed.format(unren_error=unren_error)
    return {
        "success": False,
        "level": "error",
        "message": Localizer.get().pack_unpack_decompilation_failed_2.format(
            exc=unrpyc_error or unren_error or "未知错误",
            extra=extra,
        ),
        "method": "failed",
        "overwrite": overwrite,
    }


def pack_directory(
    source_dir: str | Path,
    output_file: str | Path,
    *,
    max_part_size_bytes: int | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
    stop_check: Callable[[], bool] | None = None,
    packer: Packer | None = None,
) -> dict:
    """把目录打成 RPA，可选分卷。"""
    source = resolve_pack_source(source_dir)
    if isinstance(output_file, str) and not output_file.strip():
        raise ValueError("输出文件不能为空")
    output = Path(output_file).expanduser().resolve()
    if not output.parent.is_dir():
        raise FileNotFoundError(f"输出目录不存在：{output.parent}")
    paths = (packer or Packer()).pack_from_dir(
        str(source),
        str(output),
        progress_callback=progress_callback,
        stop_check=stop_check,
        max_part_size_bytes=max_part_size_bytes,
    )
    return {
        "success": True,
        "level": "success",
        "message": Localizer.get().pack_unpack_packaging_complete_generated_rpa_file_s.format(
            output_paths_count=len(paths)
        ),
        "outputs": [str(path) for path in paths],
        "count": len(paths),
        "source_dir": str(source),
    }


def _is_link(path: Path) -> bool:
    """符号链接或 Windows 联接点（junction）一律视为链接，清理时不跟随。"""
    if path.is_symlink():
        return True
    try:
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _is_disposable_dir(path: Path) -> bool:
    """整目录删除前确认：本身及内部都没有链接，也没有 .rpy 用户脚本。"""
    if _is_link(path) or not path.is_dir():
        return False
    for current, dirs, files in os.walk(path, followlinks=False):
        for name in [*dirs, *files]:
            if name.casefold().endswith(".rpy") or _is_link(Path(current) / name):
                return False
    return True


def cleanup_unpack_artifacts(
    target: str | Path,
    *,
    stop_check: Callable[[], bool] | None = None,
) -> dict:
    """按固定白名单清理解包/反编译遗留物；不碰白名单外的任何文件或目录。"""
    from base.LogManager import LogManager

    game_dir = resolve_game_dir(target)
    root_dir = game_dir.parent
    candidates: list[tuple[Path, bool]] = [(game_dir / name, True) for name in TEMP_GAME_DIRS]
    # game 位于盘符根下时不清理根级遗留物，避免误删磁盘根目录里的同名文件。
    if root_dir.parent != root_dir:
        candidates += [(root_dir / name, False) for name in TEMP_ROOT_FILES]
        candidates += [(root_dir / name, True) for name in TEMP_ROOT_DIRS]

    removed: list[str] = []
    skipped: list[str] = []
    for path, is_dir in candidates:
        if stop_check is not None and stop_check():
            break
        if not os.path.lexists(path):
            continue
        try:
            if is_dir:
                if not _is_disposable_dir(path):
                    skipped.append(str(path))
                    continue
                shutil.rmtree(path)
            else:
                if _is_link(path) or not path.is_file():
                    skipped.append(str(path))
                    continue
                path.unlink()
            removed.append(str(path))
        except OSError as exc:
            skipped.append(str(path))
            LogManager.get().warning(f"清理临时文件失败 {path}: {exc}")

    message = (
        Localizer.get().pack_unpack_removed_temporary_item_s.format(removed=len(removed))
        if removed
        else Localizer.get().pack_unpack_no_temporary_files_need_cleaned
    )
    return {
        "success": True,
        "level": "success" if removed else "info",
        "message": message,
        "count": len(removed),
        "outputs": removed,
        "skipped": skipped,
        "game_dir": str(game_dir),
    }


def remove_matching_rpyc(game_dir: str | Path) -> int:
    """与 Qt5 清理页一致：game 目录树（含 tl）内删除同目录存在同名 .rpy 的 .rpyc，孤儿保留。"""
    from base.LogManager import LogManager

    removed = 0
    for current, dirs, files in os.walk(game_dir, followlinks=False):
        base = Path(current)
        dirs[:] = [name for name in dirs if not _is_link(base / name)]
        stems = {name[:-4].casefold() for name in files if name.casefold().endswith(".rpy")}
        for name in files:
            if not name.casefold().endswith(".rpyc") or name[:-5].casefold() not in stems:
                continue
            path = base / name
            if _is_link(path):
                continue
            try:
                path.unlink()
                removed += 1
            except OSError as exc:
                LogManager.get().warning(f"清理 RPYC 失败 {path}: {exc}")
    return removed


def cleanup_decompiled_rpyc(target: str | Path) -> dict:
    """删除已有同名 .rpy 的 .rpyc（含 tl 目录），保留唯一脚本来源。"""
    game_dir = resolve_game_dir(target)
    removed = remove_matching_rpyc(game_dir)
    message = (
        Localizer.get().pack_unpack_removed_rpyc_file_s.format(removed=removed)
        if removed
        else Localizer.get().pack_unpack_no_removable_rpyc_files_found
    )
    return {
        "success": True,
        "level": "success" if removed else "info",
        "message": message,
        "count": removed,
        "game_dir": str(game_dir),
    }


__all__ = [
    "PackerUnpackError",
    "cleanup_decompiled_rpyc",
    "cleanup_unpack_artifacts",
    "decompile_target",
    "pack_directory",
    "parse_rpa_size_limit",
    "remove_matching_rpyc",
    "resolve_game_dir",
    "resolve_pack_output",
    "resolve_pack_source",
    "unpack_game",
]
