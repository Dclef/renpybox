"""RenpyBox 单文件工程容器（``.rbox``）。

``.rbox`` 是一个 SQLite 数据库，而不是压缩包或目录：

- ``meta`` / ``items`` 与 ``CacheDB`` 同构（``project``、``items_digest`` 两个键
  和 ``items.data`` 行格式不变），可以用 ``CacheDB(path, journal_mode = "DELETE")``
  直接读取；不要用默认 WAL 打开，否则文件会被改成 WAL 并产生旁路文件；
- ``settings(key, value)`` 只保存调用方显式传入的项目级设置，value 为 JSON；
  不会自动序列化全局 ``Config``，也拒绝明显的密钥字段；
- ``rbox.*`` 命名空间的 meta 记录格式标识、schema 版本、时间戳、原项目根目录
  以及条目数和条目摘要。

原始 Ren'Py 游戏源码不进入工程文件，只记录 ``project_root``。
文件始终使用 DELETE 日志模式，读取走只读连接，不会留下 ``-wal`` / ``-shm``。
"""

import contextlib
import dataclasses
import hashlib
import json
import os
import sqlite3
import tempfile
from collections.abc import Iterable, Iterator, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from module.Cache.CacheDB import CacheDB
from module.Cache.CacheItem import CacheItem
from module.Cache.CacheProject import CacheProject


class ProjectFileError(RuntimeError):
    """工程文件无法安全读写；``code`` 供上层映射成界面文案。"""

    INVALID_PATH = "invalid_path"
    NOT_FOUND = "not_found"
    INVALID_ARGUMENT = "invalid_argument"
    INVALID_FORMAT = "invalid_format"
    UNSUPPORTED_SCHEMA = "unsupported_schema"
    CORRUPTED = "corrupted"
    WRITE_FAILED = "write_failed"

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclasses.dataclass(frozen = True)
class ProjectFileInfo:
    path: str                                                                   # .rbox 绝对路径
    schema_version: int                                                         # 工程文件 schema 版本
    app_version: str                                                            # 写入时的应用版本
    created_at: str                                                             # 首次导出时间（UTC ISO 8601）
    updated_at: str                                                             # 最近导出时间（UTC ISO 8601）
    project_root: str                                                           # 外部 Ren'Py 项目根目录
    item_count: int                                                             # 条目数
    items_digest: str                                                           # 条目摘要，与 CacheDB.items_digest 一致


@dataclasses.dataclass(frozen = True)
class ProjectFileSnapshot:
    info: ProjectFileInfo
    project: CacheProject
    items: list[CacheItem]
    settings: dict[str, Any]


class ProjectFile:

    FORMAT = "renpybox.project"
    SCHEMA_VERSION = 1
    SUFFIX = ".rbox"
    # SQLite 头部 application_id，ASCII "RBOX"。
    APPLICATION_ID = 0x52424F58
    JOURNAL_MODE = "DELETE"

    META_PROJECT = "project"
    META_ITEMS_DIGEST = "items_digest"
    META_FORMAT = "rbox.format"
    META_SCHEMA_VERSION = "rbox.schema_version"
    META_APP_VERSION = "rbox.app_version"
    META_CREATED_AT = "rbox.created_at"
    META_UPDATED_AT = "rbox.updated_at"
    META_PROJECT_ROOT = "rbox.project_root"
    META_ITEM_COUNT = "rbox.item_count"
    META_RBOX_ITEMS_DIGEST = "rbox.items_digest"

    REQUIRED_TABLES = frozenset({"meta", "items", "settings"})
    SQLITE_HEADER = b"SQLite format 3\x00"

    # settings 中任意层级出现这些键名都会被拒绝：工程文件可能被分享，不能夹带凭据。
    SECRET_KEYS = frozenset({
        "api_key",
        "api_keys",
        "apikey",
        "secret",
        "secrets",
        "password",
        "passwd",
        "access_token",
        "refresh_token",
        "authorization",
    })
    SECRET_SUFFIXES = ("_api_key", "_api_keys", "_secret", "_password")

    @classmethod
    def export(
        cls,
        path: str | os.PathLike,
        project: CacheProject,
        items: Iterable[CacheItem],
        *,
        project_root: str | os.PathLike,
        settings: Mapping[str, Any],
        app_version: str = "",
    ) -> ProjectFileInfo:
        """写出工程文件：先写同目录临时库并校验，再原子替换目标。"""
        target = cls._normalize_path(path)
        if os.path.isdir(target):
            raise ProjectFileError(ProjectFileError.INVALID_PATH, f"Project file path is a directory: {target}")
        parent = os.path.dirname(target)
        if not os.path.isdir(parent):
            raise ProjectFileError(ProjectFileError.INVALID_PATH, f"Project file directory does not exist: {parent}")
        if not isinstance(project, CacheProject):
            raise ProjectFileError(ProjectFileError.INVALID_ARGUMENT, "project must be a CacheProject")
        try:
            item_iter = iter(items)
        except TypeError as exc:
            raise ProjectFileError(ProjectFileError.INVALID_ARGUMENT, "items must be iterable") from exc
        try:
            root = os.fspath(project_root)
        except TypeError as exc:
            raise ProjectFileError(ProjectFileError.INVALID_ARGUMENT, "project_root must be a path string") from exc
        if not isinstance(root, str):
            raise ProjectFileError(ProjectFileError.INVALID_ARGUMENT, "project_root must be a path string")
        if not isinstance(app_version, str):
            raise ProjectFileError(ProjectFileError.INVALID_ARGUMENT, "app_version must be a string")

        settings_rows = cls._encode_settings(settings)
        try:
            project_json = json.dumps(project.asdict(), ensure_ascii = False)
        except (TypeError, ValueError) as exc:
            raise ProjectFileError(ProjectFileError.INVALID_ARGUMENT, f"project is not serializable: {exc}") from exc

        now = datetime.now(timezone.utc).isoformat(timespec = "seconds")
        meta = {
            cls.META_FORMAT: cls.FORMAT,
            cls.META_SCHEMA_VERSION: str(cls.SCHEMA_VERSION),
            cls.META_APP_VERSION: app_version,
            cls.META_CREATED_AT: cls._existing_created_at(target) or now,
            cls.META_UPDATED_AT: now,
            cls.META_PROJECT_ROOT: root,
            cls.META_PROJECT: project_json,
        }

        fd, temp_path = tempfile.mkstemp(
            prefix = f".{os.path.basename(target)}.",
            suffix = ".tmp",
            dir = parent,
        )
        os.close(fd)
        try:
            cls._write(temp_path, meta, item_iter, settings_rows)
            info = cls._inspect_file(temp_path)
            os.replace(temp_path, target)
        except ProjectFileError:
            raise
        except Exception as exc:
            raise ProjectFileError(ProjectFileError.WRITE_FAILED, f"Failed to write project file: {exc}") from exc
        finally:
            cls._remove_temp(temp_path)
        return dataclasses.replace(info, path = target)

    @classmethod
    def inspect(cls, path: str | os.PathLike) -> ProjectFileInfo:
        """只读快速校验：格式、版本、元数据和行数，不解析条目。"""
        return cls._inspect_file(cls._existing_path(path))

    @classmethod
    def refresh_working_meta(cls, path: str | os.PathLike) -> None:
        """引擎直写「绑定的工程文件」后，校准 rbox.* 元数据。

        绑定模式下翻译缓存直接读写 .rbox（CacheDB 的 items/meta 结构不变），
        但 ``rbox.item_count`` / ``rbox.items_digest`` / ``updated_at`` 等
        工程文件标识由本方法补齐，保证它随时仍是可分享、可导入的 .rbox：
        拷到另一台机器走「导入工程文件」不会被摘要校验拒绝。
        """
        target = cls._normalize_path(path)
        conn = CacheDB(target, journal_mode = cls.JOURNAL_MODE)._open()
        try:
            conn.execute("PRAGMA synchronous=FULL")
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(f"PRAGMA application_id={cls.APPLICATION_ID}")
            conn.execute(f"PRAGMA user_version={cls.SCHEMA_VERSION}")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            meta = {row[0]: row[1] for row in conn.execute("SELECT key, value FROM meta")}
            item_count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
            digest = str(meta.get("items_digest") or "")
            now = datetime.now(timezone.utc).isoformat(timespec = "seconds")
            rows = {
                cls.META_FORMAT: cls.FORMAT,
                cls.META_SCHEMA_VERSION: str(cls.SCHEMA_VERSION),
                cls.META_UPDATED_AT: now,
                cls.META_ITEM_COUNT: str(item_count),
                cls.META_ITEMS_DIGEST: digest,
                cls.META_RBOX_ITEMS_DIGEST: digest,
            }
            # 首次由引擎创建（绑定的 .rbox 被删后重建）时补齐不可变标识。
            defaults = {
                cls.META_CREATED_AT: now,
                cls.META_APP_VERSION: "",
                cls.META_PROJECT_ROOT: "",
            }
            for key, value in defaults.items():
                if not isinstance(meta.get(key), str) or meta.get(key) == "":
                    rows[key] = value
            conn.executemany(
                "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                sorted(rows.items()),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @classmethod
    def load(cls, path: str | os.PathLike) -> ProjectFileSnapshot:
        """只读完整加载；所有条目通过解析和摘要校验后才返回。"""
        target = cls._existing_path(path)
        with cls._open_readonly(target) as conn:
            info, meta = cls._read_info(conn, target)
            project = cls._decode_project(meta)
            items = cls._read_items(conn, info)
            settings = cls._read_settings(conn)
        return ProjectFileSnapshot(
            info = info,
            project = project,
            items = items,
            settings = settings,
        )

    @classmethod
    def _normalize_path(cls, path: str | os.PathLike) -> str:
        try:
            value = os.fspath(path)
        except TypeError as exc:
            raise ProjectFileError(ProjectFileError.INVALID_PATH, "Project file path must be a string") from exc
        if not isinstance(value, str) or value.strip() == "":
            raise ProjectFileError(ProjectFileError.INVALID_PATH, "Project file path must be a non-empty string")
        if os.path.splitext(value)[1].lower() != cls.SUFFIX:
            raise ProjectFileError(ProjectFileError.INVALID_PATH, f"Project file must use the {cls.SUFFIX} suffix: {value}")
        return os.path.abspath(value)

    @classmethod
    def _existing_path(cls, path: str | os.PathLike) -> str:
        target = cls._normalize_path(path)
        if not os.path.isfile(target):
            raise ProjectFileError(ProjectFileError.NOT_FOUND, f"Project file not found: {target}")
        return target

    @classmethod
    def _existing_created_at(cls, target: str) -> str | None:
        if not os.path.isfile(target):
            return None
        try:
            return cls._inspect_file(target).created_at
        except ProjectFileError:
            return None

    @classmethod
    def _is_secret_key(cls, key: str) -> bool:
        name = key.strip().lower().replace("-", "_")
        return name in cls.SECRET_KEYS or name.endswith(cls.SECRET_SUFFIXES)

    @classmethod
    def _reject_secrets(cls, value: Any, location: str) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                if isinstance(key, str) and cls._is_secret_key(key):
                    raise ProjectFileError(
                        ProjectFileError.INVALID_ARGUMENT,
                        f"Project settings must not contain secrets: {location}.{key}",
                    )
                cls._reject_secrets(child, f"{location}.{key}")
        elif isinstance(value, (list, tuple)):
            for index, child in enumerate(value):
                cls._reject_secrets(child, f"{location}[{index}]")

    @classmethod
    def _encode_settings(cls, settings: Mapping[str, Any]) -> list[tuple[str, str]]:
        if not isinstance(settings, Mapping):
            raise ProjectFileError(ProjectFileError.INVALID_ARGUMENT, "settings must be a mapping")
        rows: list[tuple[str, str]] = []
        for key, value in settings.items():
            if not isinstance(key, str) or key.strip() == "":
                raise ProjectFileError(ProjectFileError.INVALID_ARGUMENT, f"Invalid settings key: {key!r}")
            if cls._is_secret_key(key):
                raise ProjectFileError(ProjectFileError.INVALID_ARGUMENT, f"Project settings must not contain secrets: {key}")
            cls._reject_secrets(value, key)
            try:
                encoded = json.dumps(
                    value,
                    ensure_ascii = False,
                    allow_nan = False,
                    sort_keys = True,
                    separators = (",", ":"),
                )
            except (TypeError, ValueError) as exc:
                raise ProjectFileError(
                    ProjectFileError.INVALID_ARGUMENT,
                    f"Settings value is not JSON serializable: {key}",
                ) from exc
            rows.append((key, encoded))
        rows.sort()
        return rows

    @staticmethod
    def _checked_items(items: Iterator[Any], counter: list[int]) -> Iterator[CacheItem]:
        for item in items:
            if not isinstance(item, CacheItem):
                raise ProjectFileError(
                    ProjectFileError.INVALID_ARGUMENT,
                    f"items must contain CacheItem, got {type(item).__name__}",
                )
            counter[0] += 1
            yield item

    @classmethod
    def _write(
        cls,
        temp_path: str,
        meta: dict[str, str],
        items: Iterator[Any],
        settings_rows: list[tuple[str, str]],
    ) -> None:
        conn = CacheDB(temp_path, journal_mode = cls.JOURNAL_MODE)._open()
        try:
            conn.execute("PRAGMA synchronous=FULL")
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(f"PRAGMA application_id={cls.APPLICATION_ID}")
            conn.execute(f"PRAGMA user_version={cls.SCHEMA_VERSION}")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            digest = hashlib.sha256()
            counter = [0]
            conn.executemany(
                "INSERT INTO items (data) VALUES (?)",
                CacheDB._iter_item_rows(cls._checked_items(items, counter), digest),
            )
            items_digest = digest.hexdigest()
            rows = dict(meta)
            rows[cls.META_ITEM_COUNT] = str(counter[0])
            rows[cls.META_ITEMS_DIGEST] = items_digest
            rows[cls.META_RBOX_ITEMS_DIGEST] = items_digest
            conn.executemany(
                "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                sorted(rows.items()),
            )
            conn.executemany(
                "INSERT INTO settings (key, value) VALUES (?, ?)",
                settings_rows,
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _remove_temp(temp_path: str) -> None:
        for suffix in ("", "-journal", "-wal", "-shm"):
            try:
                os.remove(temp_path + suffix)
            except FileNotFoundError:
                pass
            except OSError:
                pass

    @classmethod
    def _check_header(cls, path: str) -> None:
        try:
            with open(path, "rb") as reader:
                header = reader.read(100)
        except OSError as exc:
            raise ProjectFileError(ProjectFileError.NOT_FOUND, f"Project file cannot be read: {path}") from exc
        if len(header) < 100 or not header.startswith(cls.SQLITE_HEADER):
            raise ProjectFileError(ProjectFileError.INVALID_FORMAT, f"Not a RenpyBox project file: {path}")
        # 偏移 18/19 为读写格式版本：1 = 回滚日志，2 = WAL。WAL 文件只读打开也可能生成 -shm。
        if header[18] != 1 or header[19] != 1:
            raise ProjectFileError(ProjectFileError.INVALID_FORMAT, f"Project file must not use WAL journal mode: {path}")

    @classmethod
    @contextlib.contextmanager
    def _open_readonly(cls, path: str) -> Iterator[sqlite3.Connection]:
        cls._check_header(path)
        uri = Path(path).resolve().as_uri() + "?mode=ro"
        try:
            conn = sqlite3.connect(uri, uri = True)
        except sqlite3.Error as exc:
            raise ProjectFileError(ProjectFileError.CORRUPTED, f"Project file cannot be opened: {exc}") from exc
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            conn.execute("BEGIN")
            yield conn
        except sqlite3.Error as exc:
            raise ProjectFileError(ProjectFileError.CORRUPTED, f"Project file is damaged: {exc}") from exc
        finally:
            conn.close()

    @classmethod
    def _inspect_file(cls, path: str) -> ProjectFileInfo:
        with cls._open_readonly(path) as conn:
            info, _meta = cls._read_info(conn, path)
        return info

    @staticmethod
    def _parse_count(value: Any, name: str) -> int:
        if not isinstance(value, str) or not value.isascii() or not value.isdigit():
            raise ProjectFileError(ProjectFileError.INVALID_FORMAT, f"Invalid project file metadata: {name}")
        return int(value)

    @staticmethod
    def _parse_text(meta: dict[str, Any], key: str) -> str:
        value = meta.get(key)
        if not isinstance(value, str):
            raise ProjectFileError(ProjectFileError.INVALID_FORMAT, f"Invalid project file metadata: {key}")
        return value

    @classmethod
    def _parse_timestamp(cls, meta: dict[str, Any], key: str) -> str:
        value = cls._parse_text(meta, key)
        try:
            datetime.fromisoformat(value)
        except ValueError as exc:
            raise ProjectFileError(ProjectFileError.INVALID_FORMAT, f"Invalid project file metadata: {key}") from exc
        return value

    @classmethod
    def _read_info(cls, conn: sqlite3.Connection, path: str) -> tuple[ProjectFileInfo, dict[str, Any]]:
        if conn.execute("PRAGMA application_id").fetchone()[0] != cls.APPLICATION_ID:
            raise ProjectFileError(ProjectFileError.INVALID_FORMAT, f"Not a RenpyBox project file: {path}")
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        if not cls.REQUIRED_TABLES <= tables:
            raise ProjectFileError(ProjectFileError.INVALID_FORMAT, "Project file is missing required tables")

        meta = {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM meta")}
        if meta.get(cls.META_FORMAT) != cls.FORMAT:
            raise ProjectFileError(ProjectFileError.INVALID_FORMAT, f"Not a RenpyBox project file: {path}")

        schema_version = cls._parse_count(meta.get(cls.META_SCHEMA_VERSION), cls.META_SCHEMA_VERSION)
        if schema_version > cls.SCHEMA_VERSION:
            raise ProjectFileError(
                ProjectFileError.UNSUPPORTED_SCHEMA,
                f"Project file schema {schema_version} is newer than supported {cls.SCHEMA_VERSION}",
            )
        if schema_version != cls.SCHEMA_VERSION:
            raise ProjectFileError(ProjectFileError.INVALID_FORMAT, f"Invalid project file schema: {schema_version}")
        if conn.execute("PRAGMA user_version").fetchone()[0] != schema_version:
            raise ProjectFileError(ProjectFileError.INVALID_FORMAT, "Project file schema version mismatch")

        item_count = cls._parse_count(meta.get(cls.META_ITEM_COUNT), cls.META_ITEM_COUNT)
        items_digest = cls._parse_text(meta, cls.META_RBOX_ITEMS_DIGEST)
        if (
            len(items_digest) != 64
            or any(char not in "0123456789abcdef" for char in items_digest)
            or meta.get(cls.META_ITEMS_DIGEST) != items_digest
        ):
            raise ProjectFileError(ProjectFileError.CORRUPTED, "Project file items digest metadata is inconsistent")
        if not isinstance(meta.get(cls.META_PROJECT), str):
            raise ProjectFileError(ProjectFileError.INVALID_FORMAT, "Project file is missing project metadata")
        if conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] != item_count:
            raise ProjectFileError(ProjectFileError.CORRUPTED, "Project file item count mismatch")
        conn.execute("SELECT COUNT(*) FROM settings").fetchone()

        info = ProjectFileInfo(
            path = path,
            schema_version = schema_version,
            app_version = cls._parse_text(meta, cls.META_APP_VERSION),
            created_at = cls._parse_timestamp(meta, cls.META_CREATED_AT),
            updated_at = cls._parse_timestamp(meta, cls.META_UPDATED_AT),
            project_root = cls._parse_text(meta, cls.META_PROJECT_ROOT),
            item_count = item_count,
            items_digest = items_digest,
        )
        return info, meta

    @classmethod
    def _decode_project(cls, meta: dict[str, Any]) -> CacheProject:
        try:
            data = json.loads(meta[cls.META_PROJECT])
            if not isinstance(data, dict):
                raise ValueError("project metadata must be an object")
            return CacheProject.from_dict(data)
        except (TypeError, ValueError) as exc:
            raise ProjectFileError(ProjectFileError.CORRUPTED, f"Project metadata is invalid: {exc}") from exc

    @classmethod
    def _read_items(cls, conn: sqlite3.Connection, info: ProjectFileInfo) -> list[CacheItem]:
        digest = hashlib.sha256()
        digest.update(b"[")
        items: list[CacheItem] = []
        for index, row in enumerate(conn.execute("SELECT data FROM items ORDER BY id")):
            try:
                data = json.loads(row["data"])
                if not isinstance(data, dict):
                    raise ValueError("item row must be an object")
                if index:
                    digest.update(b",")
                digest.update(CacheDB._digest_json(data).encode("utf-8"))
                items.append(CacheItem.from_dict(data))
            except (TypeError, ValueError) as exc:
                raise ProjectFileError(ProjectFileError.CORRUPTED, f"Project item {index} is invalid: {exc}") from exc
        digest.update(b"]")
        if len(items) != info.item_count or digest.hexdigest() != info.items_digest:
            raise ProjectFileError(ProjectFileError.CORRUPTED, "Project file items digest mismatch")
        return items

    @classmethod
    def _read_settings(cls, conn: sqlite3.Connection) -> dict[str, Any]:
        settings: dict[str, Any] = {}
        for row in conn.execute("SELECT key, value FROM settings ORDER BY key"):
            key = row["key"]
            try:
                if not isinstance(key, str) or key.strip() == "":
                    raise ValueError("settings key must be a non-empty string")
                value = json.loads(row["value"])
            except (TypeError, ValueError) as exc:
                raise ProjectFileError(ProjectFileError.CORRUPTED, f"Project settings are invalid: {exc}") from exc
            # 文件可能被手工改过：读取时与写入同样拒绝凭据字段，不能把密钥带进配置。
            try:
                cls._reject_secrets({key: value}, "settings")
            except ProjectFileError as exc:
                raise ProjectFileError(ProjectFileError.INVALID_FORMAT, str(exc)) from exc
            settings[key] = value
        return settings
