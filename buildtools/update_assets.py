"""RenpyBox 更新资产生成工具（发布侧）。

生成全量包内嵌 manifest：

- manifest：遍历 dist 目录生成 sha256 清单，以追加模式写入全量 zip 顶层
  `_update_manifest.json`。

只用标准库，可在本地与 CI 直接运行。
"""

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

if __package__ in {None, ""}:
    # 兼容 CI 继续以脚本路径执行，同时让规则只保留一份权威实现。
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from update_path_policy import (  # noqa: E402
    validate_manifest_paths,
    validate_zip_members,
)


MANIFEST_NAME = "_update_manifest.json"
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
    manifest = {
        "version": version,
        "generator": "renpybox-update-assets/1",
        "format": FORMAT_MANIFEST,
        "files": files,
    }
    validate_manifest_paths(
        manifest,
        label="generated manifest",
        reserved_paths=(MANIFEST_NAME,),
    )
    return manifest


def append_manifest_to_zip(zip_path: Path, manifest: dict) -> None:
    validate_manifest_paths(
        manifest,
        label="full update manifest",
        reserved_paths=(MANIFEST_NAME,),
    )
    with zipfile.ZipFile(zip_path, "a") as zf:
        members = zf.infolist()
        archive_files = validate_zip_members(
            members,
            label="full update ZIP",
            allowed_protocol_paths=(MANIFEST_NAME,),
        )
        if MANIFEST_NAME.casefold() in {path.casefold() for path in archive_files}:
            raise RuntimeError(f"{MANIFEST_NAME} already exists in {zip_path}")
        zf.writestr(MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False))


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


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="RenpyBox update asset generator")
    sub = parser.add_subparsers(dest="command", required=True)

    p_manifest = sub.add_parser("manifest", help="generate manifest into full zip")
    p_manifest.add_argument("--dist", required=True, help="dist/RenpyBox dir")
    p_manifest.add_argument("--version", required=True)
    p_manifest.add_argument("--zip", required=True, help="full release zip")
    p_manifest.set_defaults(func=cmd_manifest)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
