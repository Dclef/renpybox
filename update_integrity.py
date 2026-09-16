"""客户端与独立更新器共用的安装文件完整性校验。"""

import hashlib
from pathlib import Path

from update_path_policy import safe_target_cached, validate_manifest_paths


def validate_installed_files(
    install_dir: Path, manifest: dict, *, replaced: tuple[str, ...] = ()
) -> None:
    """校验补丁不会提供的文件，防止缺失或损坏的旧依赖被当作完整安装。"""
    validate_manifest_paths(
        manifest,
        label="installed files",
        reserved_paths=("_update_manifest.json", "_patch_meta.json"),
    )
    skipped = set(replaced)
    root = install_dir.resolve()
    parents: dict[str, Path] = {}
    for rel, entry in manifest["files"].items():
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("size"), int)
            or entry["size"] < 0
            or not isinstance(entry.get("sha256"), str)
            or len(entry["sha256"]) != 64
            or any(char not in "0123456789abcdefABCDEF" for char in entry["sha256"])
        ):
            raise RuntimeError(f"安装清单无效，请使用全量更新：{rel}")
        if rel in skipped:
            continue
        path = safe_target_cached(
            install_dir, rel, label="installed file", parent_cache=parents,
            root_resolved=root,
        )
        try:
            if not path.is_file() or path.stat().st_size != entry["size"]:
                raise RuntimeError(f"安装文件缺失或大小不符，请使用全量更新：{rel}")
            digest = hashlib.sha256()
            with path.open("rb") as reader:
                for chunk in iter(lambda: reader.read(512 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != entry["sha256"].lower():
                raise RuntimeError(f"安装文件校验失败，请使用全量更新：{rel}")
        except OSError as exc:
            raise RuntimeError(f"无法校验安装文件，请使用全量更新：{rel}") from exc
