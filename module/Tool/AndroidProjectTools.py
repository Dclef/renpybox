"""安卓壳制作 / 分发清理 / 资源检测：Qt 与 API 共用的无界面业务。

从 AndroidBuildPage 抽出的纯业务；不依赖 PyQt。修复旧页危险边界：
- 清理路径必须严格位于 game 内，拒绝绝对/.. / 根 / 链接逃逸
- 打包前全量校验，失败不 mkdir/write/delete
- archive 写入临时文件成功后原子替换，失败保留旧档与源
- ZIP 备份名唯一；清理目录若不在备份覆盖范围则拒绝
- 分发 sanitize 仅限本项目 android.dist 白名单布局
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

# Windows 目录联接
_REPARSE_POINT = 0x400

RESOURCE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".bmp",
    ".mp3",
    ".ogg",
    ".wav",
    ".flac",
    ".m4a",
    ".aac",
    ".opus",
    ".mp4",
    ".webm",
    ".mkv",
    ".avi",
    ".mov",
}

DEFAULT_DETECT_HINTS = (
    "images,image,audio,video,videos,movies,script"
)

OnOutput = Callable[[str], None]


class AndroidProjectToolsError(ValueError):
    """业务校验失败（路径逃逸、备份未覆盖等）。"""


def split_items(text: str) -> list[str]:
    """按逗号/分号/换行切分列表项。"""
    if not text:
        return []
    return [item.strip() for item in re.split(r"[;,\n\r]+", text) if item.strip()]


def parse_remove_dirs(text: str) -> list[str]:
    """解析清理目录列表；显式空 → 不删除（不回落默认值）。"""
    if not str(text or "").strip():
        return []
    return [item.strip() for item in re.split(r"[;,\s]+", text) if item.strip()]


def merge_items(existing: list[str], items: list[str]) -> list[str]:
    """Windows 不区分大小写去重追加。"""
    merged = list(existing)
    seen = {_item_key(item): True for item in existing}
    for item in items:
        key = _item_key(item)
        if key in seen:
            continue
        merged.append(item)
        seen[key] = True
    return merged


def _item_key(item: str) -> str:
    return item.lower() if os.name == "nt" else item


def _path_key(path: Path) -> str:
    text = str(path)
    return text.lower() if os.name == "nt" else text


def _is_link(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    attributes = getattr(info, "st_file_attributes", 0) or 0
    return bool(attributes & _REPARSE_POINT)


def _norm_real(path: Path) -> Path:
    """解析后的真实路径（会跟随 junction/symlink）。"""
    return Path(os.path.normcase(os.path.abspath(path.resolve(strict=False))))


def _lexical_abs(path: Path) -> Path:
    """规范化绝对路径但不跟随 reparse/symlink（保留 lexical 联接身份）。"""
    return Path(os.path.normcase(os.path.abspath(os.path.expanduser(str(path)))))


def _within(root: Path, path: Path) -> bool:
    try:
        root_real = _norm_real(root)
        real = _norm_real(path)
    except OSError:
        return False
    return real == root_real or real.is_relative_to(root_real)


def _is_fs_root(path: Path) -> bool:
    try:
        resolved = path.resolve(strict=False)
    except OSError:
        return False
    return resolved.parent == resolved


def _reject_link_chain(path: Path, *, stop_at: Path | None = None, label: str = "") -> None:
    """在 resolve 前检查 lexical 路径及其祖先是否含 symlink/junction。"""
    cursor = _lexical_abs(path)
    stop = _lexical_abs(stop_at) if stop_at is not None else None
    tag = label or str(path)
    while True:
        if cursor.exists() and _is_link(cursor):
            raise AndroidProjectToolsError(f"路径含链接/联接，已拒绝: {tag}")
        if stop is not None and _path_key(cursor) == _path_key(stop):
            break
        parent = cursor.parent
        if parent == cursor:
            break
        cursor = parent


def _scan_tree_links(root: Path, *, label: str = "") -> None:
    """全量扫描目录树：拒绝内部文件/目录链接（在任何 ZIP/RPA 写入前）。"""
    tag = label or str(root)
    root_lex = _lexical_abs(root)
    if not root_lex.is_dir():
        return
    try:
        for entry in root_lex.rglob("*"):
            try:
                if _is_link(entry):
                    raise AndroidProjectToolsError(
                        f"源内含链接/联接，已拒绝: {tag} -> {entry.name}"
                    )
            except AndroidProjectToolsError:
                raise
            except OSError:
                continue
    except AndroidProjectToolsError:
        raise
    except OSError as exc:
        raise AndroidProjectToolsError(f"无法扫描源目录: {tag}: {exc}") from exc


def to_long_path(path: Path) -> str:
    """Windows 长路径前缀。"""
    if os.name != "nt":
        return str(path)
    path_str = str(path)
    if path_str.startswith("\\\\?\\"):
        return path_str
    if path_str.startswith("\\\\"):
        return "\\\\?\\UNC\\" + path_str[2:]
    return "\\\\?\\" + path_str


def resolve_project_game(project_dir: str | Path) -> tuple[Path, Path]:
    """返回 (project_root, game_dir)；要求 project/game 均为目录。"""
    project = Path(project_dir).expanduser().resolve()
    if not project.is_dir():
        raise AndroidProjectToolsError(f"项目目录不存在: {project}")
    game = project / "game"
    if not game.is_dir():
        raise AndroidProjectToolsError(f"未找到 game 目录: {game}")
    if _is_link(game) or not _within(project, game):
        raise AndroidProjectToolsError(f"game 目录不安全或越界: {game}")
    return project, game


def project_android_dist(project_dir: Path) -> Path:
    """本项目分发目录：project/android.dist。"""
    return Path(project_dir).resolve() / "android.dist"


def ensure_project_dist_dir(project_dir: Path, dist_dir: str | Path) -> Path:
    """仅允许本项目 android.dist；拒绝任意 rmtree 目标。"""
    expected = project_android_dist(project_dir)
    candidate = Path(dist_dir).expanduser().resolve()
    if _path_key(candidate) != _path_key(expected):
        raise AndroidProjectToolsError(
            f"分发目录必须为本项目 android.dist: {expected}（收到 {candidate}）"
        )
    if _is_fs_root(candidate):
        raise AndroidProjectToolsError("拒绝清理磁盘根目录")
    return candidate


def dir_has_resource_files(folder: Path, *, limit: int = 20000) -> bool:
    """一级资源探测：目录内是否含媒体扩展名文件。"""
    checked = 0
    try:
        iterator = folder.rglob("*")
    except OSError:
        return False
    for entry in iterator:
        try:
            if not entry.is_file():
                continue
            if entry.suffix.lower() in RESOURCE_EXTENSIONS:
                return True
            checked += 1
            if checked >= limit:
                break
        except OSError:
            continue
    return False


def _safe_hint_name(name: str) -> str | None:
    """检测提示只接受 game 下一层相对名，拒绝绝对/.. /分隔符逃逸。"""
    raw = str(name or "").strip()
    if not raw:
        return None
    if os.path.isabs(raw) or raw.startswith("\\\\"):
        return None
    normalized = raw.replace("\\", "/")
    if ".." in Path(normalized).parts:
        return None
    if "/" in normalized or (os.name == "nt" and "\\" in raw):
        # 只允许单层名（与 Qt 文本框默认用法一致）
        parts = Path(normalized).parts
        if len(parts) != 1:
            return None
    return Path(normalized).name


def detect_resource_dirs(
    game_dir: str | Path,
    *,
    hints: Iterable[str] | None = None,
) -> list[str]:
    """检测打包/清理候选目录；跳过 gui；hints 先加入再扫一级子目录。"""
    game = Path(game_dir).resolve()
    if not game.is_dir():
        raise AndroidProjectToolsError(f"game 目录不存在: {game}")

    detected: list[str] = []
    seen: set[str] = set()
    ignored = {"gui"}

    for name in hints or []:
        safe = _safe_hint_name(name)
        if not safe or safe.lower() in ignored:
            continue
        path = game / safe
        if not path.exists():
            continue
        if _is_link(path) or not _within(game, path):
            continue
        key = _item_key(safe)
        if key not in seen:
            detected.append(safe)
            seen.add(key)

    try:
        children = list(game.iterdir())
    except OSError as exc:
        raise AndroidProjectToolsError(f"无法读取 game 目录: {exc}") from exc

    for child in children:
        try:
            if not child.is_dir() or _is_link(child):
                continue
        except OSError:
            continue
        if child.name.lower() in ignored:
            continue
        key = _item_key(child.name)
        if key in seen:
            continue
        if not _within(game, child):
            continue
        if dir_has_resource_files(child):
            detected.append(child.name)
            seen.add(key)
    return detected


def resolve_archive_source_dirs(
    project_dir: str | Path,
    source_text: str,
) -> list[Path]:
    """解析打包源：空列表 → 整个 game；相对以 game 为基准；绝对外部目录允许。

    先对 lexical 路径查链接身份，再 resolve；拒绝源根本身是 junction/symlink。
    """
    project, game = resolve_project_game(project_dir)
    tokens = split_items(source_text)
    if not tokens:
        return [game]

    game_lex = _lexical_abs(game)
    unique: list[Path] = []
    seen: set[str] = set()
    for token in tokens:
        absolute = Path(token).is_absolute() or str(token).startswith("\\\\")
        if absolute:
            lexical = _lexical_abs(Path(token))
        else:
            if ".." in Path(str(token).replace("\\", "/")).parts:
                raise AndroidProjectToolsError(f"打包路径含 ..，已拒绝: {token}")
            lexical = _lexical_abs(game_lex / token)
        # 源根 lexical 联接身份：resolve 前检查
        if lexical.exists() and _is_link(lexical):
            raise AndroidProjectToolsError(f"打包目录不能是符号链接/联接: {token}")
        if not absolute:
            # game 内相对源：祖先链也不得含联接
            _reject_link_chain(lexical, stop_at=game_lex, label=str(token))
        resolved = lexical.resolve(strict=False)
        if not resolved.exists():
            raise AndroidProjectToolsError(f"打包目录不存在: {token}")
        if not resolved.is_dir():
            raise AndroidProjectToolsError(f"打包路径不是文件夹: {token}")
        key = _path_key(resolved)
        if key in seen:
            continue
        seen.add(key)
        unique.append(resolved)
    _ = project
    return unique


def validate_archive_sources(source_dirs: list[Path]) -> None:
    """打包前校验全部源存在且为目录（兼容旧调用；完整校验见 preflight）。"""
    for source_dir in source_dirs:
        lexical = _lexical_abs(source_dir)
        if lexical.exists() and _is_link(lexical):
            raise AndroidProjectToolsError(f"打包目录不能是符号链接/联接: {source_dir}")
        if not source_dir.exists():
            raise AndroidProjectToolsError(f"打包目录不存在: {source_dir}")
        if not source_dir.is_dir():
            raise AndroidProjectToolsError(f"打包路径不是文件夹: {source_dir}")


def resolve_safe_remove_targets(
    game_dir: Path,
    names: list[str],
) -> list[tuple[str, Path]]:
    """规范化清理目标：先查 lexical 联接身份，再 resolve 做 containment。"""
    game = game_dir.resolve()
    game_lex = _lexical_abs(game_dir)
    if _is_fs_root(game):
        raise AndroidProjectToolsError("game 目录不能是磁盘根")

    targets: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for name in names:
        raw = str(name or "").strip()
        if not raw:
            continue
        candidate = Path(raw)
        if candidate.is_absolute() or raw.startswith("\\\\"):
            lexical = _lexical_abs(candidate)
        else:
            if ".." in Path(raw.replace("\\", "/")).parts:
                raise AndroidProjectToolsError(f"清理路径含 ..，已拒绝: {raw}")
            lexical = _lexical_abs(game_lex / raw)

        # 关键：resolve 前检查 lexical 路径及到 game 的祖先链（捕获 Junction alias）
        _reject_link_chain(lexical, stop_at=game_lex, label=raw)
        if lexical.exists() and _is_link(lexical):
            raise AndroidProjectToolsError(f"清理路径含链接/联接，已拒绝: {raw}")

        target = lexical.resolve(strict=False)
        if _path_key(target) == _path_key(game):
            raise AndroidProjectToolsError("拒绝清理 game 目录本身")
        if _is_fs_root(target):
            raise AndroidProjectToolsError(f"拒绝清理磁盘根: {raw}")
        if not _within(game, target):
            raise AndroidProjectToolsError(f"清理路径越出 game: {raw}")

        key = _path_key(target)
        if key in seen:
            continue
        seen.add(key)
        label = raw if candidate.is_absolute() else str(Path(raw))
        targets.append((label, target))
    return targets


class ShellArchivePlan:
    """壳制作预检结果：Qt/API/execute 共用，无写入副作用。"""

    __slots__ = (
        "project",
        "game",
        "source_dirs",
        "remove_targets",
        "archive_path",
        "internal_archive",
        "backup",
    )

    def __init__(
        self,
        *,
        project: Path,
        game: Path,
        source_dirs: list[Path],
        remove_targets: list[tuple[str, Path]],
        archive_path: Path,
        internal_archive: Path,
        backup: bool,
    ) -> None:
        self.project = project
        self.game = game
        self.source_dirs = source_dirs
        self.remove_targets = remove_targets
        self.archive_path = archive_path
        self.internal_archive = internal_archive
        self.backup = backup


def preflight_shell_archive(
    project_dir: str | Path,
    *,
    source_text: str = "",
    remove_text: str = "",
    backup: bool = True,
) -> ShellArchivePlan:
    """全量预检：路径/links/备份覆盖；不 mkdir/write/delete/save。"""
    project, game = resolve_project_game(project_dir)
    source_dirs = resolve_archive_source_dirs(project, source_text)
    validate_archive_sources(source_dirs)
    for source in source_dirs:
        _scan_tree_links(source, label=str(source))

    remove_names = parse_remove_dirs(remove_text)
    remove_targets = resolve_safe_remove_targets(game, remove_names)

    # 目标 archive.rpa：lexical 若已是链接则拒绝（防循链接写外部）
    archive_path = _lexical_abs(project / "archive.rpa")
    internal_archive = _lexical_abs(game / "archive.rpa")
    if archive_path.exists() and _is_link(archive_path):
        raise AndroidProjectToolsError(f"目标 archive.rpa 是链接/联接，已拒绝: {archive_path}")
    if internal_archive.exists() and _is_link(internal_archive):
        raise AndroidProjectToolsError(
            f"game/archive.rpa 是链接/联接，已拒绝: {internal_archive}"
        )

    if backup and remove_targets:
        uncovered = _paths_covered_by_sources(
            [path for _, path in remove_targets],
            source_dirs,
        )
        if uncovered:
            names = ", ".join(str(path) for path in uncovered[:5])
            raise AndroidProjectToolsError(
                f"清理目录未被打包源覆盖，备份无法保护这些路径，已拒绝: {names}"
            )

    return ShellArchivePlan(
        project=project,
        game=game,
        source_dirs=source_dirs,
        remove_targets=remove_targets,
        archive_path=archive_path,
        internal_archive=internal_archive,
        backup=bool(backup),
    )


def _unique_backup_path(external_dir: Path, stamp: str | None = None) -> Path:
    """秒级同名也不覆盖：archive_backup_<ts>[_n].zip。"""
    base = stamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = external_dir / f"archive_backup_{base}.zip"
    if not candidate.exists():
        return candidate
    index = 1
    while True:
        candidate = external_dir / f"archive_backup_{base}_{index}.zip"
        if not candidate.exists():
            return candidate
        index += 1


def _paths_covered_by_sources(targets: list[Path], source_dirs: list[Path]) -> list[Path]:
    """返回未被任一打包源覆盖的清理目标。"""
    uncovered: list[Path] = []
    for target in targets:
        covered = False
        for source in source_dirs:
            if _path_key(target) == _path_key(source) or _within(source, target):
                covered = True
                break
            # 清理目标是源的祖先时也不算「源内已备份」
        if not covered:
            uncovered.append(target)
    return uncovered


def make_shell_archive(
    project_dir: str | Path,
    *,
    source_text: str = "",
    remove_text: str = "",
    backup: bool = True,
    on_output: OnOutput | None = None,
    plan: ShellArchivePlan | None = None,
) -> dict:
    """生成项目根 archive.rpa 并按配置清理资源。

    顺序：preflight（可外部传入）→ ZIP 备份 → 临时 RPA → 原子替换 → 清理 → 移除 game/archive.rpa。
    """
    def emit(line: str) -> None:
        if on_output and line:
            on_output(line)

    plan = plan or preflight_shell_archive(
        project_dir,
        source_text=source_text,
        remove_text=remove_text,
        backup=backup,
    )
    project = plan.project
    game = plan.game
    source_dirs = plan.source_dirs
    remove_targets = plan.remove_targets
    archive_path = plan.archive_path
    internal_archive = plan.internal_archive

    # 排除用 lexical+real，避免把链接目标误纳入打包
    exclude_paths = {archive_path, internal_archive}
    try:
        exclude_paths.add(archive_path.resolve(strict=False))
        exclude_paths.add(internal_archive.resolve(strict=False))
    except OSError:
        pass

    backup_path: Path | None = None
    if plan.backup:
        backup_path = _unique_backup_path(project)
        exclude_paths.add(backup_path)
        emit(f"正在备份打包目录: {backup_path}")
        try:
            _write_backup_zip(backup_path, project, source_dirs, exclude_paths)
        except Exception as exc:
            raise AndroidProjectToolsError(f"备份失败: {exc}") from exc
        emit("备份完成")

    emit(f"开始打包 archive.rpa: {archive_path}")
    pack_result = pack_archive_from_dirs(
        source_dirs,
        game_dir=game,
        archive_path=archive_path,
        exclude_paths=exclude_paths,
        on_output=on_output,
    )
    if not pack_result.get("success"):
        return {
            "success": False,
            "message": pack_result.get("message") or "打包失败",
            "archive_path": str(archive_path),
            "backup_path": str(backup_path) if backup_path else "",
            "packed_count": int(pack_result.get("packed_count") or 0),
            "removed": [],
            "skipped": [],
            "failed": [],
            "partial": False,
            "written": bool(backup_path and backup_path.exists()),
            "written_files": [str(backup_path)] if backup_path and backup_path.exists() else [],
        }

    emit("archive.rpa 打包完成，开始清理资源目录...")
    removed: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []

    if not remove_targets:
        emit("未配置清理目录，已跳过删除")
    else:
        for label, target in remove_targets:
            if not target.exists():
                skipped.append(label)
                continue
            try:
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
                removed.append(label)
            except Exception as exc:
                failed.append(f"{label}: {exc}")
                emit(f"清理失败 {target}: {exc}")

        if removed:
            emit("已删除目录: " + ", ".join(removed))
        elif remove_targets:
            emit("未发现需要删除的目录")

    if internal_archive.exists() and not _is_link(internal_archive):
        try:
            internal_archive.unlink()
            emit("已移除 game/archive.rpa，避免打进 APK")
        except Exception as exc:
            failed.append(f"game/archive.rpa: {exc}")
            emit(f"移除 game/archive.rpa 失败: {exc}")

    partial = bool(failed)
    message = "壳包处理完成" if not partial else "壳包处理完成（部分清理失败）"
    written_files = [str(archive_path)]
    if backup_path and backup_path.exists():
        written_files.insert(0, str(backup_path))
    return {
        "success": True,
        "message": message,
        "archive_path": str(archive_path),
        "backup_path": str(backup_path) if backup_path else "",
        "packed_count": int(pack_result.get("packed_count") or 0),
        "removed": removed,
        "skipped": skipped,
        "failed": failed,
        "partial": partial,
        "written": True,
        "written_files": written_files,
        "internal_archive_removed": not internal_archive.exists(),
    }


def _write_backup_zip(
    backup_path: Path,
    project: Path,
    source_dirs: list[Path],
    exclude_paths: set[Path],
) -> None:
    with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        seen_arc: set[str] = set()
        for source_dir in source_dirs:
            try:
                prefix = source_dir.relative_to(project).as_posix()
            except ValueError:
                prefix = source_dir.name
            if not prefix:
                prefix = source_dir.name
            for entry in source_dir.rglob("*"):
                if _is_link(entry):
                    raise AndroidProjectToolsError(f"备份遇链接/联接，已中止: {entry}")
                if entry.is_dir():
                    continue
                try:
                    resolved = entry.resolve()
                except OSError:
                    continue
                if resolved in exclude_paths or entry in exclude_paths:
                    continue
                rel = entry.relative_to(source_dir)
                arcname = f"{prefix}/{rel.as_posix()}"
                if arcname in seen_arc:
                    continue
                seen_arc.add(arcname)
                zf.write(entry, arcname)


def pack_archive_from_dirs(
    source_dirs: list[Path],
    *,
    game_dir: Path,
    archive_path: Path,
    exclude_paths: set[Path] | None = None,
    on_output: OnOutput | None = None,
) -> dict:
    """聚合多源目录写入 archive.rpa；临时文件成功后原子替换，失败保留旧档。"""
    from module.Tool.rpatool_core import RenPyArchive

    def emit(line: str) -> None:
        if on_output and line:
            on_output(line)

    exclude = set(exclude_paths or ())
    # 使用 lexical 绝对路径，避免 archive.rpa 若为链接时 resolve 写到外部
    out_path = _lexical_abs(archive_path)
    if out_path.exists() and _is_link(out_path):
        return {
            "success": False,
            "message": f"目标 archive.rpa 是链接/联接，已拒绝: {out_path}",
            "packed_count": 0,
        }
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 临时文件与最终档同目录，成功后 os.replace
    temp_path = out_path.with_name(f".{out_path.stem}.tmp{out_path.suffix}")
    if temp_path.exists():
        try:
            temp_path.unlink()
        except OSError as exc:
            return {"success": False, "message": f"无法清理临时归档: {exc}", "packed_count": 0}

    archive = RenPyArchive(version=3, verbose=False)
    seen: set[str] = set()
    added = 0
    for source_dir in source_dirs:
        try:
            prefix = source_dir.relative_to(game_dir).as_posix()
        except ValueError:
            prefix = source_dir.name
        if prefix == ".":
            prefix = ""

        for entry in source_dir.rglob("*"):
            if _is_link(entry):
                return {
                    "success": False,
                    "message": f"打包遇链接/联接，已中止: {entry}",
                    "packed_count": added,
                }
            if entry.is_dir():
                continue
            try:
                entry_resolved = entry.resolve()
            except OSError:
                continue
            if entry_resolved in exclude or entry in exclude:
                continue
            # 跳过临时档自身
            if _path_key(entry_resolved) == _path_key(temp_path):
                continue
            rel = entry.relative_to(source_dir).as_posix()
            archive_name = f"{prefix}/{rel}" if prefix else rel
            if archive_name in seen:
                continue
            seen.add(archive_name)
            archive.add_file_path(archive_name, to_long_path(entry_resolved))
            added += 1
            if added % 500 == 0:
                emit(f"已加入 {added} 个文件...")

    if added == 0:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        return {"success": False, "message": "未找到可打包文件", "packed_count": 0}

    emit(f"已加入 {added} 个文件，正在写入 RPA 文件...")
    save_target = Path(to_long_path(temp_path)) if os.name == "nt" else temp_path
    try:
        archive.save(str(save_target))
        # save() 末尾会 load() 打开句柄；替换前必须关闭，否则 Windows 无法 rename
        handle = getattr(archive, "handle", None)
        if handle is not None:
            try:
                handle.close()
            except OSError:
                pass
            archive.handle = None
        # 原子替换：旧档仅在新档完整后被覆盖
        os.replace(str(temp_path), str(out_path))
    except Exception as exc:
        handle = getattr(archive, "handle", None)
        if handle is not None:
            try:
                handle.close()
            except OSError:
                pass
            archive.handle = None
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        return {
            "success": False,
            "message": f"写入 archive.rpa 失败（已保留旧归档与源文件）: {exc}",
            "packed_count": added,
        }

    emit("RPA 写入完成")
    return {
        "success": True,
        "message": "archive.rpa 已生成",
        "packed_count": added,
        "archive_path": str(out_path),
    }


def sanitize_android_dist_assets(
    project_dir: str | Path,
    dist_dir: str | Path | None = None,
    *,
    on_output: OnOutput | None = None,
) -> dict:
    """清理分发资产：仅本项目 android.dist，两布局白名单。"""
    def emit(line: str) -> None:
        if on_output and line:
            on_output(line)

    project = Path(project_dir).expanduser().resolve()
    target_dist = ensure_project_dist_dir(
        project,
        dist_dir if dist_dir is not None else project_android_dist(project),
    )

    assets_dir = target_dist / "assets"
    android_prefix = "android-"
    if assets_dir.exists():
        target_dir = assets_dir
        keep_dirs = {"game", "renpy"}
        keep_names = {"android.json"}
        keep_py = False
        keep_hint = "game/renpy/android-*/android.json"
    else:
        target_dir = target_dist
        keep_dirs = {"game", "renpy", "lib"}
        keep_names = {"android.json"}
        keep_py = True
        keep_hint = "game/renpy/lib/.py/android-*/android.json"

    if not target_dir.exists():
        emit(f"未找到分发目录，跳过清理: {target_dir}")
        return {
            "success": True,
            "removed": [],
            "failed": [],
            "dist_dir": str(target_dist),
            "message": "未找到分发目录，已跳过",
        }

    emit(f"清理分发目录: {target_dir}")
    removed: list[str] = []
    failed: list[str] = []
    try:
        entries = list(target_dir.iterdir())
    except OSError as exc:
        raise AndroidProjectToolsError(f"无法读取分发目录: {exc}") from exc

    for path in entries:
        # 防御：任何越出 dist 的条目都不删
        if not _within(target_dist, path):
            failed.append(f"{path.name}: 越出 android.dist")
            continue
        name_lower = path.name.lower()
        if name_lower.startswith(android_prefix):
            continue
        if path.is_dir() and name_lower in keep_dirs:
            continue
        if path.is_file() and name_lower in keep_names:
            continue
        if keep_py and path.is_file() and path.suffix.lower() == ".py":
            continue
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            removed.append(path.name)
        except Exception as exc:
            failed.append(f"{path.name}: {exc}")

    if removed:
        emit(f"已清理 {len(removed)} 个文件（保留 {keep_hint}）")
    else:
        emit("未发现需要清理的文件")

    return {
        "success": not failed,
        "partial": bool(failed) and bool(removed),
        "removed": removed,
        "failed": failed,
        "dist_dir": str(target_dist),
        "message": "分发目录清理完成" if not failed else "分发目录清理部分失败",
    }
