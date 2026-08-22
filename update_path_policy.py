"""更新包两端共用的 Windows 路径安全规则。"""

from __future__ import annotations

import stat
from collections.abc import Iterable
from pathlib import Path, PureWindowsPath


_WINDOWS_INVALID_CHARS = frozenset('<>:"\\|?*')
_WINDOWS_RESERVED_NAMES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)
_PROTOCOL_RESERVED_PATHS = frozenset(
    {"_update_manifest.json", "_patch_meta.json", "_update_journal.json"}
)
_PROTOCOL_RESERVED_ROOTS = frozenset({"_update_staging"})


def windows_path_key(path: str) -> str:
    """返回更新器目标平台使用的大小写不敏感比较键。"""
    return path.casefold()


def validate_relative_path(value: object, *, label: str = "update path") -> str:
    """校验规范 POSIX 相对路径；不尝试修正或重新解释危险输入。"""
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"Unsafe {label}: expected a non-empty string")
    if "\\" in value:
        raise RuntimeError(f"Unsafe {label}: backslash is not allowed: {value!r}")
    if value.startswith("/"):
        raise RuntimeError(f"Unsafe {label}: absolute path is not allowed: {value!r}")

    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise RuntimeError(f"Unsafe {label}: non-canonical path: {value!r}")

    for part in parts:
        if part.endswith((" ", ".")):
            raise RuntimeError(
                f"Unsafe {label}: trailing dot or space is not allowed: {value!r}"
            )
        if any(ord(char) < 32 or char in _WINDOWS_INVALID_CHARS for char in part):
            raise RuntimeError(f"Unsafe {label}: invalid Windows name: {value!r}")
        if (
            part.split(".", 1)[0].casefold() in _WINDOWS_RESERVED_NAMES
            or PureWindowsPath(part).is_reserved()
        ):
            raise RuntimeError(f"Unsafe {label}: reserved Windows name: {value!r}")

    return value


def validate_file_paths(
    values: Iterable[object],
    *,
    label: str,
    allowed_protocol_paths: Iterable[str] = (),
) -> dict[str, str]:
    """校验文件路径集合，并拒绝 Windows 别名与文件/目录前缀冲突。"""
    paths_by_key: dict[str, str] = {}
    allowed_protocol = {
        windows_path_key(path) for path in allowed_protocol_paths
    }
    for value in values:
        path = validate_relative_path(value, label=label)
        _validate_protocol_namespace(
            path,
            label=label,
            allowed_protocol_paths=allowed_protocol,
        )
        key = windows_path_key(path)
        previous = paths_by_key.get(key)
        if previous is not None:
            raise RuntimeError(
                f"Ambiguous {label}: {previous!r} conflicts with {path!r}"
            )
        paths_by_key[key] = path

    for key, path in paths_by_key.items():
        parts = key.split("/")
        for index in range(1, len(parts)):
            parent_key = "/".join(parts[:index])
            if parent_key in paths_by_key:
                raise RuntimeError(
                    f"Ambiguous {label}: file {paths_by_key[parent_key]!r} "
                    f"is a parent of {path!r}"
                )

    return paths_by_key


def _validate_protocol_namespace(
    path: str,
    *,
    label: str,
    allowed_protocol_paths: set[str] | None = None,
) -> None:
    """禁止协议文件名和 staging 根目录被当作普通载荷。"""
    allowed = allowed_protocol_paths or set()
    key = windows_path_key(path)
    if key in {windows_path_key(item) for item in _PROTOCOL_RESERVED_PATHS}:
        if key not in allowed:
            raise RuntimeError(f"Unsafe {label}: reserved protocol file {path!r}")
        # 协议入口必须使用规范大小写，避免探测和跳过逻辑出现别名。
        canonical = next(
            item for item in _PROTOCOL_RESERVED_PATHS
            if windows_path_key(item) == key
        )
        if path != canonical:
            raise RuntimeError(f"Unsafe {label}: non-canonical protocol file {path!r}")
    if windows_path_key(path.split("/", 1)[0]) in {
        windows_path_key(item) for item in _PROTOCOL_RESERVED_ROOTS
    }:
        raise RuntimeError(f"Unsafe {label}: reserved protocol root {path!r}")


def validate_zip_members(
    members: Iterable[object],
    *,
    label: str,
    allowed_protocol_paths: Iterable[str] = (),
) -> set[str]:
    """在解压前校验全部 ZIP 条目，返回非目录条目的原始路径。"""
    entries_by_key: dict[str, tuple[str, bool]] = {}
    file_keys: set[str] = set()
    file_paths: set[str] = set()
    allowed_protocol = {
        windows_path_key(path) for path in allowed_protocol_paths
    }

    for member in members:
        filename = getattr(member, "filename", None)
        is_dir = bool(member.is_dir())
        path = filename[:-1] if is_dir and isinstance(filename, str) else filename
        path = validate_relative_path(path, label=f"{label} member")
        _validate_protocol_namespace(
            path,
            label=f"{label} member",
            allowed_protocol_paths=allowed_protocol,
        )

        unix_mode = (int(getattr(member, "external_attr", 0)) >> 16) & 0xFFFF
        file_type = stat.S_IFMT(unix_mode)
        if stat.S_ISLNK(unix_mode) or file_type not in {
            0,
            stat.S_IFREG,
            stat.S_IFDIR,
        }:
            raise RuntimeError(f"Unsafe {label} member type: {filename!r}")
        if (is_dir and file_type == stat.S_IFREG) or (
            not is_dir and file_type == stat.S_IFDIR
        ):
            raise RuntimeError(f"Unsafe {label} member type: {filename!r}")

        key = windows_path_key(path)
        previous = entries_by_key.get(key)
        if previous is not None:
            raise RuntimeError(
                f"Ambiguous {label} members: {previous[0]!r} conflicts with {filename!r}"
            )
        entries_by_key[key] = (str(filename), is_dir)
        if not is_dir:
            file_keys.add(key)
            file_paths.add(path)

    for key, (path, _) in entries_by_key.items():
        parts = key.split("/")
        for index in range(1, len(parts)):
            parent_key = "/".join(parts[:index])
            if parent_key in file_keys:
                raise RuntimeError(
                    f"Ambiguous {label} members: file "
                    f"{entries_by_key[parent_key][0]!r} is a parent of {path!r}"
                )

    return file_paths


def validate_manifest_paths(
    manifest: object,
    *,
    label: str,
    reserved_paths: Iterable[str] = (),
) -> set[str]:
    """校验 manifest 文件表中的路径并返回原始路径集合。"""
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), dict):
        raise RuntimeError(f"Invalid {label} file list")
    paths_by_key = validate_file_paths(manifest["files"], label=f"{label} path")
    reserved_keys = {
        windows_path_key(path)
        for path in {*_PROTOCOL_RESERVED_PATHS, *reserved_paths}
    }
    conflict = reserved_keys & set(paths_by_key)
    if conflict:
        raise RuntimeError(
            f"Unsafe {label} path: reserved protocol file "
            f"{paths_by_key[next(iter(conflict))]!r}"
        )
    for path in paths_by_key.values():
        if windows_path_key(path.split("/", 1)[0]) in _PROTOCOL_RESERVED_ROOTS:
            raise RuntimeError(f"Unsafe {label} path: reserved protocol root {path!r}")
    return set(paths_by_key.values())


def validate_patch_paths(
    meta: dict,
    members: Iterable[object],
    *,
    patch_meta_name: str,
    manifest_name: str,
) -> None:
    """校验 patch 的 ZIP 载荷和三组协议路径之间的一致性。"""
    files = meta.get("files")
    deleted = meta.get("deleted")
    manifest = meta.get("manifest")
    if not isinstance(files, dict) or not isinstance(deleted, list):
        raise RuntimeError("Invalid patch file lists")

    reserved_paths = (patch_meta_name, manifest_name)
    file_paths_by_key = validate_file_paths(files, label="patch file path")
    deleted_paths_by_key = validate_file_paths(deleted, label="patch deleted path")
    manifest_paths = validate_manifest_paths(
        manifest,
        label="patch manifest",
        reserved_paths=reserved_paths,
    )
    manifest_keys = {windows_path_key(path) for path in manifest_paths}
    reserved_keys = {
        windows_path_key(path)
        for path in {*_PROTOCOL_RESERVED_PATHS, *reserved_paths}
    }

    for label, paths_by_key in (
        ("patch file", file_paths_by_key),
        ("patch deleted", deleted_paths_by_key),
    ):
        conflict = reserved_keys & set(paths_by_key)
        if conflict:
            raise RuntimeError(
                f"Unsafe {label} path: reserved protocol file "
                f"{paths_by_key[next(iter(conflict))]!r}"
            )
        for path in paths_by_key.values():
            if windows_path_key(path.split("/", 1)[0]) in _PROTOCOL_RESERVED_ROOTS:
                raise RuntimeError(
                    f"Unsafe {label} path: reserved protocol root {path!r}"
                )

    overlap = set(file_paths_by_key) & set(deleted_paths_by_key)
    if overlap:
        raise RuntimeError("Patch files and deleted paths overlap")
    if not set(files).issubset(manifest_paths):
        raise RuntimeError("Patch files are not a subset of target manifest")
    if set(deleted_paths_by_key) & manifest_keys:
        raise RuntimeError("Deleted paths still exist in target manifest")

    archive_files = validate_zip_members(
        members,
        label="patch ZIP",
        allowed_protocol_paths=(patch_meta_name,),
    )
    expected_files = {patch_meta_name, *files}
    if archive_files != expected_files:
        raise RuntimeError("Patch ZIP payload does not match patch metadata")


def safe_target(
    root: Path,
    rel: object,
    *,
    label: str = "update path",
    root_resolved: Path | None = None,
    resolve_target: bool = True,
) -> Path:
    """把已校验相对路径映射到 root 内，并防止现有链接把目标引到目录外。"""
    path = validate_relative_path(rel, label=label)
    target = root.joinpath(*path.split("/"))
    if not resolve_target:
        return target
    root_resolved = root.resolve() if root_resolved is None else root_resolved
    target_resolved = target.resolve(strict=False)
    if target_resolved != root_resolved and root_resolved not in target_resolved.parents:
        raise RuntimeError(f"Unsafe {label}: target escapes root: {path!r}")
    return target


def safe_target_cached(
    root: Path,
    rel: object,
    *,
    parent_cache: dict[str, Path],
    label: str = "update path",
    root_resolved: Path | None = None,
) -> Path:
    """按唯一父目录复用安全解析，叶子为现有链接时仍做完整检查。"""
    path = validate_relative_path(rel, label=label)
    parts = path.split("/")
    parent_key = "/".join(parts[:-1])
    if not parent_key:
        parent = root
    else:
        parent = parent_cache.get(parent_key)
        if parent is None:
            parent = safe_target(
                root,
                parent_key,
                label=label,
                root_resolved=root_resolved,
            )
            parent_cache[parent_key] = parent

    target = parent / parts[-1]
    if target.is_symlink():
        # 只有叶子是链接时才解析完整路径，普通文件不支付系统调用成本。
        safe_target(root, path, label=label, root_resolved=root_resolved)
    return target
