from __future__ import annotations

import os
import shutil
import tempfile
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
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding=encoding,
            newline="",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as writer:
            writer.write(text)
            writer.flush()
            os.fsync(writer.fileno())
            temp_path = Path(writer.name)
        if target.exists():
            # NamedTemporaryFile defaults to 0600 on POSIX. Preserve the target's
            # permission bits without copying its stale timestamps.
            shutil.copymode(target, temp_path)
        os.replace(str(temp_path), str(target))
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
