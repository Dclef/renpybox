"""Private, atomic checkpoints for Agent extraction (never a game script asset).

Only normalized identity hashes and successful, grounded candidate rows are stored.
Prompts, source corpus, credentials and model reasoning are never serialized here.
An old running extraction without these records cannot be migrated from its UI
counters or its truncated preview. It must finish; this code applies on next use.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from base.AppPaths import AppPaths

SCHEMA_VERSION = 1
SEMANTICS_VERSION = 1  # Bump when decoder/grounding semantics change.
MAX_BYTES = 32 * 1024 * 1024
LOCK_TIMEOUT_SECONDS = 1.0
_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()
_CANDIDATE_FIELDS = ("src", "type", "evidence", "source", "line")
_TYPES = {"角色", "地名", "组织", "物品", "术语"}


def default_checkpoint_root() -> Path:
    return AppPaths.detect().app("storage", "extraction_checkpoints")


def digest(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def normalized_project(path: str | Path) -> str:
    return os.path.normcase(str(Path(path).expanduser().resolve()))


def semantic_fingerprint(platform: dict[str, Any], capacity: Any) -> str:
    # Keep every non-credential setting (including unknown future knobs). Only
    # the hash is written; even an endpoint containing a token stays private.
    credentials = {"api_key", "api_keys", "key", "keys", "token", "access_token",
                   "secret", "password", "api_key_ref", "api_key_secret_id", "secret_ref"}
    semantics = {key: value for key, value in platform.items() if str(key).casefold() not in credentials}
    return digest({"platform": semantics, "capacity": capacity, "semantics": SEMANTICS_VERSION})


def clean_rows(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list) or len(rows) > 4096:
        raise ValueError("invalid_results")
    result = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("invalid_results")
        value = {field: row[field] for field in _CANDIDATE_FIELDS if field in row}
        if (not isinstance(value.get('src'), str) or not 0 < len(value['src']) <= 80
                or not value['src'].strip() or value['src'] != value['src'].strip()):
            raise ValueError("invalid_results")
        if value.get("type") not in _TYPES:
            raise ValueError("invalid_results")
        if not isinstance(value.get("source"), str) or len(value["source"]) > 4096:
            raise ValueError("invalid_results")
        if type(value.get("line")) is not int or value["line"] < 1:
            raise ValueError("invalid_results")
        if (not isinstance(value.get('evidence'), str) or len(value['evidence']) > 40
                or not value['evidence'].strip()):
            raise ValueError("invalid_results")
        result.append(value)
    return result


class CheckpointError(Exception):
    """Stable, non-sensitive diagnostics; do not expose OS exception strings."""


@contextmanager
def _file_lock(path: Path) -> Iterator[None]:
    key = str(path.resolve())
    with _LOCKS_GUARD:
        thread_lock = _LOCKS.setdefault(key, threading.Lock())
    if not thread_lock.acquire(timeout=LOCK_TIMEOUT_SECONDS):
        raise CheckpointError("busy")
    handle = None
    locked = False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("a+b", buffering=0)
        if path.stat().st_size == 0:
            handle.write(b"0")
        deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
        while True:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise CheckpointError("busy")
                time.sleep(0.01)
        yield
    finally:
        try:
            if handle is not None:
                try:
                    if locked:
                        handle.seek(0)
                        if os.name == "nt":
                            import msvcrt
                            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                        else:
                            import fcntl
                            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                finally:
                    handle.close()
        finally:
            thread_lock.release()


class ExtractionCheckpoint:
    """Merge successful chunks under a short OS lock and a generation fence.

    No scan or network operation runs under this lock. Concurrent resumptions
    may duplicate a request, but cannot lose committed rows or overwrite a
    forced/new generation. OS locks are released automatically after a crash.
    """

    def __init__(self, *, project: str | Path, mode: str, model_hash: str,
                 chunk_keys: list[str], root: str | Path | None = None):
        self.root = Path(root) if root is not None else default_checkpoint_root()
        self.project = normalized_project(project)
        self.scope = digest({"project": self.project, "mode": mode})
        self.chunk_keys = list(chunk_keys)
        self.identity = digest({"schema": SCHEMA_VERSION, "scope": self.scope,
                                "model": model_hash, "chunks": chunk_keys})
        self.path = self.root / self.scope / (self.identity + ".json")
        self.lock_path = self.root / self.scope / "checkpoint.lock"
        self.generation = ""
        self.status = "new"
        self.diagnostics: list[str] = []
        self.enabled = True
        self.saved_count = 0
        self.complete = False
        self.closed = False

    def _safe_root(self) -> None:
        project = Path(self.project)
        root = self.root.resolve()
        if root == project or project in root.parents:
            raise CheckpointError("unsafe_root")
        target = self.path.resolve()
        if root not in target.parents:
            raise CheckpointError("unsafe_root")

    def _diagnose(self, code: str, *, disable: bool = False) -> None:
        if code not in self.diagnostics:
            self.diagnostics.append(code)
        if disable:
            self.enabled = False
            self.status = "superseded" if code == "superseded" else "unavailable"

    def _read(self) -> dict[str, Any] | None:
        try:
            with self.path.open("rb") as handle:
                raw = handle.read(MAX_BYTES + 1)
        except FileNotFoundError:
            return None
        if len(raw) > MAX_BYTES:
            raise CheckpointError("corrupt")
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError()
            if data.get("schema_version") != SCHEMA_VERSION:
                raise CheckpointError("version_mismatch")
            if set(data) != {'schema_version', 'identity', 'generation', 'chunk_keys', 'complete', 'successes', 'updated_at'}:
                raise ValueError()
            if data.get("identity") != self.identity or data.get("chunk_keys") != self.chunk_keys:
                raise CheckpointError("identity_mismatch")
            generation = data.get("generation")
            if not isinstance(generation, str) or len(generation) != 32 or any(c not in "0123456789abcdef" for c in generation):
                raise ValueError()
            if type(data.get("complete")) is not bool or not isinstance(data.get("successes"), dict):
                raise ValueError()
            for key, record in data["successes"].items():
                if not key.isdigit() or str(int(key)) != key or not 0 <= int(key) < len(self.chunk_keys):
                    raise ValueError()
                if not isinstance(record, dict) or set(record) != {'chunk_key', 'entries', 'digest'} or record.get("chunk_key") != self.chunk_keys[int(key)]:
                    raise ValueError()
                cleaned = clean_rows(record.get("entries"))
                if cleaned != record["entries"] or digest(cleaned) != record.get("digest"):
                    raise ValueError()
            if data["complete"] and len(data["successes"]) != len(self.chunk_keys):
                raise ValueError()
            return data
        except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
            raise CheckpointError("corrupt") from None

    def _write(self, data: dict[str, Any]) -> None:
        encoded = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        if len(encoded) > MAX_BYTES:
            raise CheckpointError("size_limit")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp = tempfile.mkstemp(prefix=self.identity + ".", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, self.path)
        finally:
            try:
                os.unlink(temp)
            except FileNotFoundError:
                pass

    def begin(self, *, resume: bool = True, force: bool = False) -> dict[int, list[dict[str, Any]]]:
        try:
            self._safe_root()
            with _file_lock(self.lock_path):
                try:
                    data = self._read()
                except CheckpointError as exc:
                    self._diagnose(str(exc))
                    self.status = 'incompatible' if str(exc) in {'version_mismatch', 'identity_mismatch'} else 'corrupt'
                    data = None
                if data is not None and resume and not force and not data["complete"]:
                    self.generation = data["generation"]
                    self.saved_count = len(data["successes"])
                    self.status = "resumed" if self.saved_count else "new"
                    return {int(key): record["entries"] for key, record in data["successes"].items()}
                self.generation = uuid.uuid4().hex
                fresh = {"schema_version": SCHEMA_VERSION, "identity": self.identity,
                         "generation": self.generation, "chunk_keys": self.chunk_keys,
                         "complete": False, "successes": {}, "updated_at": time.time()}
                self._write(fresh)
                return {}
        except (OSError, ValueError, CheckpointError) as exc:
            self._diagnose(str(exc) if isinstance(exc, CheckpointError) else "io_error", disable=True)
            return {}

    def _current(self) -> dict[str, Any]:
        data = self._read()
        if data is None or data["generation"] != self.generation or data["complete"]:
            raise CheckpointError("superseded")
        return data

    def save(self, index: int, rows: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
        if self.closed or not self.enabled:
            return None
        try:
            cleaned = clean_rows(rows)
            if type(index) is not int or not 0 <= index < len(self.chunk_keys):
                raise CheckpointError("invalid_results")
            record = {"chunk_key": self.chunk_keys[index], "entries": cleaned, "digest": digest(cleaned)}
            with _file_lock(self.lock_path):
                data = self._current()
                # First valid success wins; duplicated concurrent requests do
                # not replace previously committed model decisions.
                data["successes"].setdefault(str(index), record)
                data["updated_at"] = time.time()
                self._write(data)
                self.saved_count = len(data["successes"])
            if self.status in {'corrupt', 'incompatible'}:
                self.status = 'new'
            return [dict(row) for row in data['successes'][str(index)]['entries']]
        except (OSError, ValueError, CheckpointError) as exc:
            self._diagnose(str(exc) if isinstance(exc, CheckpointError) else "io_error", disable=True)
            return None

    def discard(self, indices: list[int]) -> None:
        if not indices or self.closed or not self.enabled:
            return
        try:
            with _file_lock(self.lock_path):
                data = self._current()
                for index in indices:
                    data["successes"].pop(str(index), None)
                self._write(data)
                self.saved_count = len(data["successes"])
            self._diagnose('invalid_results')
            self.status = 'corrupt'
        except (OSError, ValueError, CheckpointError) as exc:
            self._diagnose(str(exc) if isinstance(exc, CheckpointError) else "io_error", disable=True)

    def finish(self) -> None:
        # API may acknowledge completion after the service closed its writer.
        # save/discard remain closed, and the generation fence still applies.
        if not self.enabled:
            return
        try:
            with _file_lock(self.lock_path):
                data = self._current()
                if len(data["successes"]) != len(self.chunk_keys):
                    return
                data["complete"] = True
                data["updated_at"] = time.time()
                self._write(data)
                self.complete = True
                self.status = "complete"
        except (OSError, ValueError, CheckpointError) as exc:
            self._diagnose(str(exc) if isinstance(exc, CheckpointError) else "io_error", disable=True)

    def close(self) -> None:
        self.closed = True

    def metadata(self) -> dict[str, Any]:
        return {"checkpoint_status": self.status, "checkpoint_diagnostics": list(self.diagnostics),
                "resume_available": self.enabled and not self.complete and self.saved_count > 0 and self.status in {'new', 'resumed'}}
