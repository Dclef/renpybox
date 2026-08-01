from __future__ import annotations

import os
import secrets
import shutil
from pathlib import Path
from typing import Callable


def atomic_write_text(
    path: str | Path,
    text: str,
    *,
    encoding: str = "utf-8",
    validator: Callable[[str], object] | None = None,
) -> None:
    """Validate and atomically replace a text file in its destination directory."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if validator is not None:
        validator(text)

    temp_path: Path | None = None
    try:
        descriptor: int | None = None
        for _attempt in range(100):
            candidate = target.parent / f".{target.name}.{secrets.token_hex(8)}.tmp"
            try:
                descriptor = os.open(
                    candidate,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o666,
                )
                temp_path = candidate
                break
            except FileExistsError:
                continue
        if descriptor is None or temp_path is None:
            raise FileExistsError(f"Unable to create temporary file for {target}")

        with os.fdopen(descriptor, mode="w", encoding=encoding, newline="") as writer:
            writer.write(text)
            writer.flush()
            os.fsync(writer.fileno())
        if target.exists():
            # Preserve an existing target's permission bits without copying its
            # stale timestamps. Fresh files already use normal 0666-and-umask mode.
            shutil.copymode(target, temp_path)
        os.replace(str(temp_path), str(target))
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
