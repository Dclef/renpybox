from __future__ import annotations

import os
import secrets
import shutil
from pathlib import Path
from typing import Callable, Iterable


def validate_write_path(path: str | Path, allowed_roots: Iterable[Path]) -> None:
    """Reject destinations whose resolved path leaves the permitted roots."""
    requested_target = Path(path)
    resolved_target = requested_target.resolve(strict=False)
    if not any(
        resolved_target.is_relative_to(Path(root).resolve(strict=False))
        for root in allowed_roots
    ):
        raise RuntimeError(
            f"Write target escapes allowed roots: {requested_target} -> {resolved_target}"
        )


def atomic_write_text(
    path: str | Path,
    text: str,
    *,
    encoding: str = "utf-8",
    newline: str | None = None,
    validator: Callable[[str], object] | None = None,
    allowed_roots: Iterable[Path] | None = None,
) -> None:
    """Validate and atomically replace a text file in its destination directory."""
    requested_target = Path(path)
    allowed_roots = tuple(allowed_roots or ())
    if allowed_roots:
        validate_write_path(requested_target, allowed_roots)
    if validator is not None:
        validator(text)

    if requested_target.is_symlink():
        try:
            unresolved_target = requested_target.resolve(strict=False)
            target = (
                unresolved_target.parent.resolve(strict=True) / unresolved_target.name
            )
        except (OSError, RuntimeError) as exc:
            raise RuntimeError(
                f"Unable to resolve symbolic-link write target {requested_target}: {exc}"
            ) from exc
        if target.exists() and not target.is_file():
            raise RuntimeError(
                f"Symbolic-link write target is not a file: {requested_target}"
            )
        if allowed_roots:
            validate_write_path(target, allowed_roots)
    else:
        target = requested_target

    target.parent.mkdir(parents=True, exist_ok=True)
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

        with os.fdopen(
            descriptor,
            mode="w",
            encoding=encoding,
            newline=newline,
        ) as writer:
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
