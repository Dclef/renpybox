"""RenpyBox 更新资产生成工具（发布侧）。

生成全量包内嵌 manifest 与版本间增量 patch，协议见 docs 内 P0.5 施工单：

- manifest：遍历 dist 目录生成 sha256 清单，以追加模式写入全量 zip 顶层
  `_update_manifest.json`；
- patch：解压上一版全量 zip，与本次 dist 对比，把变化/新增文件按安装相对
  路径打成 patch.zip，顶层内嵌 `_patch_meta.json`（含完整目标 manifest 与
  deleted 清单）。

只用标准库，可在本地与 CI 直接运行。
"""

import argparse
import hashlib
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path


MANIFEST_NAME = "_update_manifest.json"
PATCH_META_NAME = "_patch_meta.json"
FORMAT_PATCH = "renpybox-patch/1"
FORMAT_MANIFEST = "renpybox-update-manifest/1"
CHUNK_SIZE = 512 * 1024


def file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as reader:
        while True:
            chunk = reader.read(CHUNK_SIZE)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def build_manifest(dist_dir: Path, version: str) -> dict:
    files: dict[str, dict] = {}
    for item in sorted(dist_dir.rglob("*")):
        if not item.is_file():
            continue
        rel = item.relative_to(dist_dir).as_posix()
        files[rel] = {"size": item.stat().st_size, "sha256": file_sha256(item)}
    return {
        "version": version,
        "generator": "renpybox-update-assets/1",
        "format": FORMAT_MANIFEST,
        "files": files,
    }


def append_manifest_to_zip(zip_path: Path, manifest: dict) -> None:
    with zipfile.ZipFile(zip_path, "a") as zf:
        if MANIFEST_NAME in zf.namelist():
            raise RuntimeError(f"{MANIFEST_NAME} already exists in {zip_path}")
        zf.writestr(MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False))


def validate_patch_zip(zip_path: Path, expected_version: str | None = None) -> dict:
    """校验发布侧 patch 的最小结构契约并返回元数据。"""
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        if names.count(PATCH_META_NAME) != 1:
            raise RuntimeError(f"patch must contain exactly one {PATCH_META_NAME}")
        meta = json.loads(zf.read(PATCH_META_NAME).decode("utf-8"))

    if not isinstance(meta, dict) or meta.get("format") != FORMAT_PATCH:
        raise RuntimeError("invalid patch meta format")
    if expected_version is not None and meta.get("version") != expected_version:
        raise RuntimeError("patch version does not match release version")
    if not isinstance(meta.get("files"), dict) or not isinstance(meta.get("deleted"), list):
        raise RuntimeError("invalid patch file lists")
    manifest = meta.get("manifest")
    if (
        not isinstance(manifest, dict)
        or manifest.get("format") != FORMAT_MANIFEST
        or manifest.get("version") != meta.get("version")
        or not isinstance(manifest.get("files"), dict)
    ):
        raise RuntimeError("invalid target manifest")
    missing = sorted(set(meta["files"]) - set(names))
    if missing:
        raise RuntimeError(f"patch archive is missing files: {missing[0]}")
    return meta


def find_payload_dir(extract_root: Path) -> Path:
    """与 updater._find_payload_dir 同规则：定位包含 RenpyBox.exe 的目录。"""
    exe_names = {"RenpyBox.exe"}
    for candidate in (extract_root, *sorted(extract_root.rglob("RenpyBox.exe"))):
        if candidate.is_file():
            return candidate.parent
        if candidate.is_dir() and any(
            (candidate / name).is_file() for name in exe_names
        ):
            return candidate
    raise RuntimeError(f"Payload dir not found under {extract_root}")


def extract_prev_zip(prev_zip: Path, dest: Path) -> Path:
    with zipfile.ZipFile(prev_zip, "r") as zf:
        zf.extractall(dest)
    return find_payload_dir(dest)


def build_patch(
    dist_dir: Path,
    version: str,
    prev_payload_dir: Path,
    prev_version: str,
    out_zip: Path,
) -> dict:
    target_manifest = build_manifest(dist_dir, version)

    prev_files: dict[str, dict] = {}
    # 协议元数据不是安装文件：上一版包内嵌的 manifest 若计入会污染 deleted 清单
    protocol_names = {MANIFEST_NAME, PATCH_META_NAME}
    for item in sorted(prev_payload_dir.rglob("*")):
        if not item.is_file():
            continue
        rel = item.relative_to(prev_payload_dir).as_posix()
        if rel in protocol_names:
            continue
        prev_files[rel] = {"size": item.stat().st_size, "sha256": file_sha256(item)}

    changed: list[str] = []
    added: list[str] = []
    deleted: list[str] = []
    for rel, entry in target_manifest["files"].items():
        prev_entry = prev_files.get(rel)
        if prev_entry is None:
            added.append(rel)
        elif prev_entry["sha256"] != entry["sha256"]:
            changed.append(rel)
    deleted = sorted(set(prev_files) - set(target_manifest["files"]))

    meta = {
        "format": FORMAT_PATCH,
        "version": version,
        "base_version": prev_version,
        "files": {rel: target_manifest["files"][rel] for rel in changed + added},
        "deleted": deleted,
        "manifest": target_manifest,
    }

    # 只在 ZIP 完整写入并通过回读校验后发布最终文件；中途异常不能留下
    # 会被 workflow glob 误收集的半包。
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    out_zip.unlink(missing_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{out_zip.name}.",
        suffix=".tmp",
        dir=out_zip.parent,
    )
    os.close(descriptor)
    temp_zip = Path(temp_name)
    try:
        with zipfile.ZipFile(temp_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=5) as zf:
            for rel in changed + added:
                zf.write(dist_dir / Path(*rel.split("/")), rel)
            zf.writestr(PATCH_META_NAME, json.dumps(meta, ensure_ascii=False))
        validate_patch_zip(temp_zip, expected_version=version)
        os.replace(temp_zip, out_zip)
    finally:
        temp_zip.unlink(missing_ok=True)

    return {
        "changed": len(changed),
        "added": len(added),
        "deleted": len(deleted),
        "patch_bytes": out_zip.stat().st_size,
    }


def cmd_manifest(args: argparse.Namespace) -> int:
    dist_dir = Path(args.dist)
    if not dist_dir.is_dir():
        raise RuntimeError(f"dist dir not found: {dist_dir}")
    zip_path = Path(args.zip)
    if not zip_path.is_file():
        raise RuntimeError(f"zip not found: {zip_path}")

    manifest = build_manifest(dist_dir, args.version)
    append_manifest_to_zip(zip_path, manifest)
    print(f"manifest appended to {zip_path.name}: {len(manifest['files'])} files")
    return 0


def cmd_patch(args: argparse.Namespace) -> int:
    dist_dir = Path(args.dist)
    if not dist_dir.is_dir():
        raise RuntimeError(f"dist dir not found: {dist_dir}")
    prev_zip = Path(args.prev_zip)
    if not prev_zip.is_file():
        raise RuntimeError(f"prev zip not found: {prev_zip}")
    out_zip = Path(args.out)
    out_zip.parent.mkdir(parents=True, exist_ok=True)

    extract_root = out_zip.parent / "_prev_extract"
    if extract_root.exists():
        import shutil

        shutil.rmtree(extract_root)
    extract_root.mkdir(parents=True)
    try:
        prev_payload = extract_prev_zip(prev_zip, extract_root)
        stats = build_patch(dist_dir, args.version, prev_payload, args.prev_version, out_zip)
    finally:
        import shutil

        shutil.rmtree(extract_root, ignore_errors=True)

    print(
        "patch written: "
        f"changed={stats['changed']} added={stats['added']} "
        f"deleted={stats['deleted']} bytes={stats['patch_bytes']}"
    )
    return 0


def cmd_validate_patch(args: argparse.Namespace) -> int:
    zip_path = Path(args.zip)
    if not zip_path.is_file():
        raise RuntimeError(f"patch zip not found: {zip_path}")
    meta = validate_patch_zip(zip_path, expected_version=args.version)
    print(f"patch valid: {zip_path.name} ({len(meta['files'])} files)")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="RenpyBox update asset generator")
    sub = parser.add_subparsers(dest="command", required=True)

    p_manifest = sub.add_parser("manifest", help="generate manifest into full zip")
    p_manifest.add_argument("--dist", required=True, help="dist/RenpyBox dir")
    p_manifest.add_argument("--version", required=True)
    p_manifest.add_argument("--zip", required=True, help="full release zip")
    p_manifest.set_defaults(func=cmd_manifest)

    p_patch = sub.add_parser("patch", help="generate incremental patch zip")
    p_patch.add_argument("--dist", required=True, help="dist/RenpyBox dir")
    p_patch.add_argument("--version", required=True)
    p_patch.add_argument("--prev-zip", dest="prev_zip", required=True)
    p_patch.add_argument("--prev-version", dest="prev_version", required=True)
    p_patch.add_argument("--out", required=True)
    p_patch.set_defaults(func=cmd_patch)

    p_validate = sub.add_parser("validate-patch", help="validate patch zip structure")
    p_validate.add_argument("--zip", required=True)
    p_validate.add_argument("--version", required=True)
    p_validate.set_defaults(func=cmd_validate_patch)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
