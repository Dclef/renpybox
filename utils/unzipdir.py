from __future__ import annotations

from pathlib import Path
import zipfile


def zip_dir(dirname: str, zipfilename: str) -> None:
    """打包目录/文件到 zip，保持相对路径。"""
    src = Path(dirname)
    filelist: list[Path] = []

    if src.is_file():
        filelist.append(src)
    else:
        for path in src.rglob("*"):
            if path.is_file():
                filelist.append(path)

    with zipfile.ZipFile(zipfilename, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in filelist:
            arcname = file_path.relative_to(src)
            zf.write(file_path, arcname)


def unzip_file(zipfilename: str, unziptodir: str) -> None:
    """解压 zip 到目标目录，防止 Zip Slip。"""
    target_root = Path(unziptodir)
    target_root.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zipfilename) as zfobj:
        for member in zfobj.infolist():
            # 规范化路径防止越界
            member_path = Path(member.filename)
            if member_path.is_absolute():
                continue
            dest_path = (target_root / member_path).resolve()
            if target_root not in dest_path.parents and dest_path != target_root:
                # 路径越界，跳过
                continue

            if member.is_dir():
                dest_path.mkdir(parents=True, exist_ok=True)
            else:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                with zfobj.open(member) as src_f, open(dest_path, "wb") as dst_f:
                    dst_f.write(src_f.read())
