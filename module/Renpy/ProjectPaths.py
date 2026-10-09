"""Ren'Py 项目路径解析与缓存定位。

路径相关的页面很多，但项目身份只有一个：项目根目录和目标语言。
本模块把 ``project/game/tl/<lang>``、翻译输出和应用目标统一从这个身份派生，
避免页面之间互相复制、覆盖旧路径。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


_PREFERRED_LANGUAGES = (
    "chinese",
    "schinese",
    "tchinese",
    "english",
    "japanese",
    "korean",
    "russian",
)

# 最近一次翻译运行清单保存在稳定的项目输出根目录中，而不是
# ``<lang>_new`` 或 hook 输出目录。这样页面重开后仍能找到实际缓存。
RUN_MANIFEST_SCHEMA_VERSION = 1
RUN_MANIFEST_PREFIX = ".renpybox_last_run_"


def _normalise(value: Any) -> str:
    return str(value or "").strip()


def normalise_path(value: Any) -> Path | None:
    """将路径转为绝对路径；路径不存在时也保留其结构。"""
    text = _normalise(value)
    if text == "":
        return None
    try:
        return Path(text).expanduser().resolve(strict = False)
    except Exception:
        return Path(text)


def looks_like_renpy_path(raw_path: Any) -> bool:
    """判断路径是否明显包含 Ren'Py 项目结构。"""
    path = normalise_path(raw_path)
    if path is None or not path.exists():
        return False
    if path.is_file():
        path = path.parent
    return (
        path.name.casefold() in {"game", "tl"}
        or path.parent.name.casefold() == "tl"
        or (path / "game").is_dir()
    )


def _key(path: Path) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def _safe_language(value: Any, default: str = "chinese") -> str:
    text = _normalise(value).replace("\\", "/").rstrip("/")
    name = Path(text).name if text else ""
    folded = name.casefold()
    if name in ("", ".", "..") or folded in {
        "tl",
        "game",
        "none",
        "null",
        "undefined",
    }:
        return default
    # 增量目录和可疑项过滤目录只表示同一目标语言的运行变体，不能成为
    # 新的项目身份。使用大小写不敏感判断，兼容 Windows 用户手工改名。
    for suffix in ("_filtered_suspicious", "_new"):
        if folded.endswith(suffix):
            name = name[: -len(suffix)].rstrip(" _-")
            if name == "":
                return default
            folded = name.casefold()
            break
    # 语言目录名只能是单层目录，防止配置路径逃出项目根目录。
    if "/" in name or "\\" in name or any(ch in name for ch in '<>:"|?*'):
        return default
    return name


def _language_from_tl_path(value: Any) -> str:
    """从明确位于 ``tl/<lang>`` 的路径提取目标语言。"""
    path = normalise_path(value)
    if path is None:
        return ""
    # 与 from_path 保持一致：文件输入先退回所在目录再判断语言目录。
    if path.is_file() or path.suffix.lower() in {".exe", ".py", ".rpy"}:
        path = path.parent
    # 输入可能是 tl/<lang> 下的具体脚本或子目录；向上查找最近的
    # ``tl`` 父目录，避免把脚本所在子目录误当成语言名。
    while path != path.parent:
        if path.parent.name.casefold() == "tl":
            return _safe_language(path.name, "")
        path = path.parent
    return ""


def _pick_language(
    tl_root: Path,
    preferred: str = "",
    *,
    allow_missing_preferred: bool = False,
) -> str:
    preferred = _safe_language(preferred, "") if preferred else ""
    if preferred and (
        allow_missing_preferred
        or (tl_root / preferred).is_dir()
    ):
        return preferred
    for name in _PREFERRED_LANGUAGES:
        if (tl_root / name).is_dir():
            return name
    try:
        children = sorted(
            (
                item
                for item in tl_root.iterdir()
                if item.is_dir()
                and not item.name.casefold().endswith(("_new", "_filtered_suspicious"))
                and item.name.casefold() not in {
                    "none",
                    "null",
                    "undefined",
                    "_filtered_suspicious",
                }
            ),
            key = lambda item: item.name.casefold(),
        )
    except OSError:
        children = []
    return children[0].name if children else (preferred or "chinese")


@dataclass(frozen = True)
class RenpyProjectPaths:
    """一个 Ren'Py 项目的规范化路径集合。"""

    project_root: Path
    game_dir: Path
    tl_root: Path
    tl_language_dir: Path
    language: str
    translation_output_dir: Path
    application_target_dir: Path

    @property
    def cache_dir(self) -> Path:
        return self.translation_output_dir / "cache"

    @property
    def project_key(self) -> str:
        """返回不依赖盘符大小写的稳定项目键。"""
        return f"{_key(self.project_root)}|{self.language.casefold()}"

    @property
    def run_manifest_path(self) -> Path:
        """返回本项目/语言对应的最近运行清单路径。"""
        return (
            self.project_root
            / "RenpyBox_Translation"
            / f"{RUN_MANIFEST_PREFIX}{self.language}.json"
        )

    @classmethod
    def from_path(cls, raw_path: Any, language: str = "") -> RenpyProjectPaths | None:
        path = normalise_path(raw_path)
        if path is None:
            return None

        # 文件选择（包括 exe 或 rpy）统一从所在目录推导。
        if path.is_file() or path.suffix.lower() in {".exe", ".py", ".rpy"}:
            path = path.parent

        project_root: Path | None = None
        inferred_language = ""
        explicit_tl_root: Path | None = None

        parts = [part.casefold() for part in path.parts]
        if "renpybox_translation" in parts:
            marker = max(index for index, part in enumerate(parts) if part == "renpybox_translation")
            if marker > 0:
                project_root = Path(*path.parts[:marker])
                if marker + 1 < len(path.parts):
                    inferred_language = path.parts[marker + 1].removesuffix("_new")

        if project_root is None:
            # 输入可能是 tl 根、语言目录，也可能是语言目录下的脚本/子目录。
            # 向上定位最近的 tl，统一从其相对路径第一段提取语言，避免
            # 把 sub/story.rpy 当成项目根或语言目录。
            tl_cursor = path
            while True:
                if tl_cursor.name.casefold() == "tl":
                    explicit_tl_root = tl_cursor
                    try:
                        relative_parts = path.relative_to(tl_cursor).parts
                    except ValueError:
                        relative_parts = ()
                    if relative_parts:
                        inferred_language = relative_parts[0]
                    if tl_cursor.parent.name.casefold() == "game":
                        project_root = tl_cursor.parent.parent
                    else:
                        project_root = tl_cursor.parent
                    break
                if tl_cursor.parent == tl_cursor:
                    break
                tl_cursor = tl_cursor.parent
        if project_root is None and path.name.casefold() == "game":
            project_root = path.parent
        if project_root is None and (path / "game").is_dir():
            project_root = path
        if project_root is None:
            # 允许不存在的项目目录，便于用户先选择路径再创建输出目录。
            project_root = path

        game_dir = project_root / "game"
        # 标准项目使用 game/tl；用户也可能把翻译目录放在项目根的
        # tl/ 下。只要输入路径明确位于某个 tl 父目录，就保留该目录，
        # 避免 Direct/Hook 页面再次改写成 game/tl/<lang>。
        tl_root = explicit_tl_root or (game_dir / "tl")
        language_is_explicit = bool(_safe_language(language, ""))
        language = _safe_language(language or inferred_language, "")
        # 明确指定的语言或 tl/<lang> 输入即使尚未创建，也应保留用户选择，
        # 避免已有语言目录抢占新建翻译的路径。
        direct_language_input = bool(
            explicit_tl_root is not None
            and inferred_language
            and language.casefold() == _safe_language(inferred_language, "").casefold()
        )
        language = _pick_language(
            tl_root,
            language,
            allow_missing_preferred = language_is_explicit or direct_language_input,
        )
        tl_language_dir = tl_root / language
        output_dir = project_root / "RenpyBox_Translation" / language
        return cls(
            project_root = project_root,
            game_dir = game_dir,
            tl_root = tl_root,
            tl_language_dir = tl_language_dir,
            language = language,
            translation_output_dir = output_dir,
            application_target_dir = tl_language_dir,
        )

    @classmethod
    def from_config(cls, config: Any, language: str = "") -> RenpyProjectPaths | None:
        """从配置按明确 Ren'Py 字段优先级解析项目。"""
        configured_tl = _normalise(getattr(config, "renpy_tl_folder", ""))
        configured_input = _normalise(getattr(config, "input_folder", ""))
        configured_language = language
        # 当前输入目录是页面刚选择的事实来源。旧项目可能仍残留
        # renpy_tl_folder（例如 chinese），不能用它污染新的 tl/japanese。
        if not configured_language and configured_input:
            configured_language = _language_from_tl_path(configured_input)
        if not configured_language and configured_tl:
            candidate = normalise_path(configured_tl)
            if candidate is not None and candidate.parent.name.casefold() == "tl":
                configured_language = _safe_language(candidate.name, "")

        candidates: list[Any] = [
            getattr(config, "renpy_project_path", ""),
            getattr(config, "renpy_game_folder", ""),
            configured_tl,
            configured_input,
            getattr(config, "output_folder", ""),
        ]

        # 明确的 tl/<lang> 输入是当前页面选择的项目身份。即使旧的
        # renpy_tl_folder 仍指向另一套已存在的项目，也不能被冲突检查抢回。
        if not language and _language_from_tl_path(configured_input):
            input_path = normalise_path(configured_input)
            if input_path is not None:
                input_resolved = cls.from_path(input_path, configured_language)
                if input_resolved is not None and input_resolved.game_dir.is_dir():
                    return input_resolved

        # 如果页面刚选择了另一套 game/tl，而专用字段还残留旧项目，
        # 结构明确的当前输入/语言目录应优先，避免继续把文件读到旧项目。
        explicit: list[RenpyProjectPaths] = []
        for raw in candidates[:2]:
            path = normalise_path(raw)
            if path is None:
                continue
            resolved = cls.from_path(path, configured_language)
            if resolved is not None and resolved.game_dir.is_dir():
                explicit.append(resolved)

        for raw in (configured_tl, getattr(config, "input_folder", "")):
            path = normalise_path(raw)
            if path is None:
                continue
            resolved = cls.from_path(path, configured_language)
            if (
                resolved is not None
                and resolved.game_dir.is_dir()
                and explicit
                and any(
                    resolved.project_key != item.project_key
                    or _key(resolved.tl_language_dir) != _key(item.tl_language_dir)
                    for item in explicit
                )
            ):
                return resolved

        # 页面切换项目后，旧的专用字段可能暂时还指向已不存在的目录。
        # 只要当前输入/输出能解析出真实 game 目录，就应优先使用它，
        # 不能让后面的专用字段兜底把项目又解析回旧路径。
        for raw in candidates[3:]:
            path = normalise_path(raw)
            if path is None:
                continue
            resolved = cls.from_path(path, configured_language)
            if resolved is not None and resolved.game_dir.is_dir():
                return resolved

        seen: set[str] = set()
        for raw in candidates:
            path = normalise_path(raw)
            if path is None or _key(path) in seen:
                continue
            seen.add(_key(path))
            resolved = cls.from_path(path, configured_language)
            if resolved is None:
                continue
            # 有 game 目录的候选优先；明确的 renpy_* 字段即使暂时不存在也可作为兜底。
            if resolved.game_dir.is_dir() or raw in candidates[:3]:
                return resolved
        return None


@dataclass
class SourceScriptSummary:
    """源码统计；取消或读取失败时，部分计数仅用于诊断。"""

    rpy_count: int = 0
    rpyc_count: int = 0
    pending_rpyc_count: int = 0
    first_pending_rpyc: str = ""
    cancelled: bool = False
    error: str = ""


def source_script_summary(
    paths: RenpyProjectPaths,
    *,
    cancel_check=None,
) -> SourceScriptSummary:
    """一次扫描源码区，按同目录文件名配对 RPY/RPYC，保留原始数量。"""
    game_dir = paths.game_dir
    tl_root = getattr(paths, "tl_root", game_dir / "tl")
    excluded = {_key(tl_root), _key(game_dir / "tl")}
    result = SourceScriptSummary()

    def check_cancelled() -> bool:
        result.cancelled = bool(cancel_check is not None and cancel_check())
        return result.cancelled

    def record_error(error: OSError) -> None:
        # os.walk 默认忽略读取错误；显式记录，避免部分扫描被判断为就绪。
        if not result.error:
            result.error = str(error)

    try:
        for current, dirnames, filenames in os.walk(
            str(game_dir), topdown=True, onerror=record_error,
        ):
            if check_cancelled():
                return result
            if _key(Path(current)) in excluded:
                dirnames[:] = []
                continue
            source_names: set[str] = set()
            compiled_names: list[str] = []
            for name in filenames:
                if check_cancelled():
                    return result
                stem, suffix = os.path.splitext(name)
                if suffix.casefold() == ".rpy":
                    result.rpy_count += 1
                    source_names.add(os.path.normcase(stem))
                elif suffix.casefold() == ".rpyc":
                    result.rpyc_count += 1
                    compiled_names.append(name)
            # 在当前目录内匹配，不让其他目录的同名源码抵消待处理文件。
            for name in compiled_names:
                if check_cancelled():
                    return result
                if os.path.normcase(os.path.splitext(name)[0]) not in source_names:
                    result.pending_rpyc_count += 1
                    if not result.first_pending_rpyc:
                        result.first_pending_rpyc = (Path(current) / name).relative_to(game_dir).as_posix()
    except OSError as exc:
        record_error(exc)
    check_cancelled()
    return result


def source_script_counts(
    paths: RenpyProjectPaths,
    *,
    cancel_check=None,
) -> tuple[int, int]:
    """兼容展示入口：返回翻译目录之外的原始 RPY/RPYC 数量。"""
    result = source_script_summary(paths, cancel_check=cancel_check)
    return result.rpy_count, result.rpyc_count


def is_derived_run_folder(value: Any) -> bool:
    """判断某个运行目录是否属于工具自己的派生态（而非用户自选目录）。

    派生态有三类形态：标准 TL 目录 ``game/tl/<lang>``、翻译输出
    ``<project>/RenpyBox_Translation/<lang>``，以及增量/兜底变体
    ``<lang>_new``、``<lang>_filtered_suspicious``。
    """
    path = normalise_path(value)
    if path is None:
        return False
    if path.parent.name.casefold() == "tl":
        return True
    return any(
        part.casefold() == "RenpyBox_Translation".casefold()
        for part in path.parts
    )


def _is_app_placeholder_folder(path: Path) -> bool:
    """判断是否仍是未配置时的应用默认输入/输出目录。"""
    try:
        from base.AppPaths import get_app_paths

        app_paths = get_app_paths()
        return _key(path) in {_key(app_paths.input_path), _key(app_paths.output_path)}
    except Exception:
        return False


def _derive_project_run_folder(config: Any, field: str, derived: Path) -> str:
    """决定规范路径回写时该字段是否仍应跟随项目派生。

    ``input_folder``/``output_folder`` 有两个来源：项目身份派生（标准
    ``game/tl/<lang>`` 与 ``RenpyBox_Translation/<lang>``），以及用户自己
    选择的目录。历史行为是无条件回落派生值，于是「项目设置页选择输入
    目录」或「一键翻译切项目」都会把用户的选择悄悄改写掉，用户再点
    一次「开始」就看到凭空多出来的 ``tl`` 目录。

    现在只刷新「本来就是派生态」的值——包括上一个项目遗留的
    ``game/tl/<lang>``、``RenpyBox_Translation/<lang>``、``<lang>_new``
    以及尚未配置时的应用默认目录，这样历史项目不会因为改了默认值而
    卡在旧路径；用户自选的任意目录则原样保留。
    """
    current = str(getattr(config, field, "") or "").strip()
    if current == "":
        return str(derived)
    current_path = normalise_path(current)
    if current_path is None:
        return str(derived)
    derived_path = normalise_path(derived) or derived
    if _key(current_path) == _key(derived_path):
        return str(derived)
    if _is_app_placeholder_folder(current_path) or is_derived_run_folder(current_path):
        return str(derived)
    return current


def apply_to_config(
    config: Any,
    paths: RenpyProjectPaths,
    *,
    input_folder: Any = None,
    output_folder: Any = None,
) -> Any:
    """把规范路径写入配置，并保留专用运行输入/输出的可选覆盖。

    ``input_folder``/``output_folder`` 不传时不再无条件回落派生目录：
    派生目录的归属由 ``_derive_project_run_folder`` 判定，只有当前值
    本身就是旧派生态时才会被刷新；用户显式选择的自定义目录原样保留。
    """
    config.renpy_project_path = str(paths.project_root)
    # 兼容旧字段：该字段历史上保存的是项目根目录，继续保持这一语义。
    config.renpy_game_folder = str(paths.project_root)
    config.renpy_tl_folder = str(paths.tl_language_dir)
    config.input_folder = str(
        input_folder if input_folder is not None
        else _derive_project_run_folder(config, "input_folder", paths.tl_language_dir)
    )
    config.output_folder = str(
        output_folder if output_folder is not None
        else _derive_project_run_folder(config, "output_folder", paths.translation_output_dir)
    )
    return config


def _has_cache(path: Path) -> bool:
    cache = path / "cache"
    db_path = cache / "cache.db"

    def has_valid_json() -> bool:
        # JSON 缓存必须同时具备项目和条目；单独的残留文件不能让校对页选中
        # 一个必然会严格载入失败的目录。
        if not (cache / "items.json").is_file() or not (cache / "project.json").is_file():
            return False
        try:
            # 只需要确认这是可解析的条目数组，不必把整份 items.json 物化出来：
            # 大项目的 items.json 动辄几十 MB，整份 loads 会在“选目录”这一步
            # 就把调用方（多处都在 GUI 线程）冻住。
            with (cache / "items.json").open(encoding = "utf-8-sig") as handle:
                if handle.read(1).lstrip() != "[":
                    return False
            project = json.loads((cache / "project.json").read_text(encoding = "utf-8-sig"))
            return isinstance(project, dict)
        except (OSError, ValueError, TypeError):
            return False

    def sqlite_schema_is_usable() -> bool:
        # 这里只回答“严格载入会不会成功”，不需要知道有多少条目。CacheDB.get_items()
        # 会把整张 items 表反序列化成 CacheItem（6 万条约 2.2s），而本函数只要一个
        # 布尔值——所以走只读 URI，只确认表存在且可查询。
        import sqlite3

        try:
            # 只读 URI：允许读 WAL 但不建表、不写 journal。immutable=1 在这里
            # 不可用——它会忽略未 checkpoint 的 WAL，把“刚写完还没落盘”的缓存
            # 误判成不可用。
            uri = f"{db_path.resolve().as_uri()}?mode=ro"
            with sqlite3.connect(uri, uri = True) as connection:
                names = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
                if "items" not in names:
                    return False
                # 表结构必须可查，且每一行都必须能被 json.loads 解析——旧实现
                # 走 CacheDB.get_items()，任何一行 data 坏掉都会整份抛异常。
                # json_valid 让这个判断留在 SQLite 内部完成，不必把 6 万行
                # 拉回 Python（实测 262ms vs 旧路径 2.2s）。
                broken = connection.execute(
                    "SELECT count(*) FROM items"
                    " WHERE data IS NULL OR NOT json_valid(data)"
                ).fetchone()[0]
                if broken:
                    return False
                # 严格载入还需要 meta 里的 project 行。
                if "meta" in names:
                    row = connection.execute(
                        "SELECT value FROM meta WHERE key = ?", ("project",)
                    ).fetchone()
                    if row is not None:
                        return isinstance(json.loads(row[0]), dict)
                return False
        except Exception:
            return False

    # CacheManager 严格载入时优先使用 SQLite；先按同一优先级验证，避免
    # “有效 JSON + 损坏 DB”被误判为可用后又在校对页载入失败。
    if db_path.is_file():
        if sqlite_schema_is_usable():
            return True
        # SQLite 损坏时允许同目录完整 JSON 作为严格载入的回退。
        return has_valid_json() or (cache / "reset.journal.json").is_file()

    if has_valid_json():
        return True
    if (cache / "reset.journal.json").is_file():
        return True
    return False


def _is_within(path: Path, parent: Path) -> bool:
    """判断路径是否位于指定项目根目录内。"""
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _manifest_path(paths: RenpyProjectPaths) -> Path:
    return paths.run_manifest_path


def _is_allowed_run_output(paths: RenpyProjectPaths, output: Path) -> bool:
    """限制运行缓存不能跨项目/跨语言，同时兼容用户自定义项目内输出。"""
    allowed = (
        paths.translation_output_dir,
        paths.translation_output_dir.parent / f"{paths.language}_new",
        paths.application_target_dir,
    )
    if any(_key(output) == _key(candidate) for candidate in allowed):
        return True
    # game/tl 下的一级目录同样代表语言；不能因为它是项目内路径，
    # 就让 chinese 运行清单误载入 english 的缓存。
    if _is_within(output, paths.tl_root):
        try:
            relative = output.relative_to(paths.tl_root)
            if not relative.parts:
                return False
            language = _safe_language(relative.parts[0], "").casefold()
            return language == paths.language.casefold()
        except (ValueError, IndexError):
            return False
    # RenpyBox_Translation 下的一级目录按语言命名，明确拒绝其它语言。
    translation_root = paths.project_root / "RenpyBox_Translation"
    if _key(output.parent) == _key(translation_root):
        name = _safe_language(output.name, "").casefold()
        return name == paths.language.casefold()
    # 传统翻译页允许项目内的自定义输出目录，项目键仍负责隔离项目。
    return _is_within(output, paths.project_root) and _key(output) != _key(paths.project_root)


def write_run_manifest(
    paths: RenpyProjectPaths,
    output_folder: Any = None,
    *,
    input_folder: Any = None,
    application_target_dir: Any = None,
    run_kind: str = "translation",
    status: str = "active",
    extra: dict[str, Any] | None = None,
) -> Path:
    """记录最近一次翻译运行的实际缓存目录。

    清单只保存项目内路径和稳定 ``project_key``，用于页面重开后的缓存定位；
    读取时会再次校验项目键，避免旧项目路径被静默复用。
    """
    output = normalise_path(
        output_folder if output_folder is not None else paths.translation_output_dir
    )
    if output is None:
        output = paths.translation_output_dir
    input_path = normalise_path(input_folder)
    target = normalise_path(
        application_target_dir
        if application_target_dir is not None
        else paths.application_target_dir
    )

    # 不把项目外目录写入清单；hook/翻译输出均应位于项目根下。
    if not _is_within(output, paths.project_root) or not _is_allowed_run_output(paths, output):
        raise ValueError("运行缓存目录必须位于 Ren'Py 项目根目录内")
    if input_path is not None and not _is_within(input_path, paths.project_root):
        raise ValueError("运行输入目录必须位于 Ren'Py 项目根目录内")
    if target is not None and not _is_within(target, paths.project_root):
        raise ValueError("应用目标目录必须位于 Ren'Py 项目根目录内")

    payload: dict[str, Any] = {
        "schema_version": RUN_MANIFEST_SCHEMA_VERSION,
        "project_key": paths.project_key,
        "project_root": str(paths.project_root),
        "language": paths.language,
        "output_folder": str(output),
        "input_folder": str(input_path) if input_path is not None else "",
        "application_target_dir": str(target) if target is not None else "",
        "run_kind": str(run_kind or "translation"),
        "status": str(status or "active"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if isinstance(extra, dict):
        # 只允许简单 JSON 值，避免清单因为页面对象无法序列化。
        for key, value in extra.items():
            if key not in payload:
                payload[str(key)] = value

    manifest = _manifest_path(paths)
    manifest.parent.mkdir(parents = True, exist_ok = True)
    temp = manifest.with_name(f"{manifest.name}.tmp")
    try:
        temp.write_text(
            json.dumps(payload, ensure_ascii = False, indent = 2),
            encoding = "utf-8",
        )
        os.replace(str(temp), str(manifest))
    finally:
        if temp.is_file():
            try:
                temp.unlink()
            except OSError:
                pass
    return manifest


def read_run_manifest(paths: RenpyProjectPaths) -> dict[str, Any] | None:
    """读取并校验最近运行清单；不合法或不属于当前项目时返回 ``None``。"""
    manifest = _manifest_path(paths)
    if not manifest.is_file():
        return None
    try:
        payload = json.loads(manifest.read_text(encoding = "utf-8-sig"))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    try:
        version = int(payload.get("schema_version", 0))
    except (TypeError, ValueError):
        return None
    if version != RUN_MANIFEST_SCHEMA_VERSION:
        return None
    if str(payload.get("project_key", "")) != paths.project_key:
        return None
    if _safe_language(payload.get("language", ""), "").casefold() != paths.language.casefold():
        return None

    root = normalise_path(payload.get("project_root"))
    if root is None or _key(root) != _key(paths.project_root):
        return None
    output = normalise_path(payload.get("output_folder"))
    if (
        output is None
        or not _is_within(output, paths.project_root)
        or not _is_allowed_run_output(paths, output)
    ):
        return None
    # 统一返回规范化路径，调用方无需再次处理相对路径。
    payload["project_root"] = str(root)
    payload["output_folder"] = str(output)
    for key in ("input_folder", "application_target_dir"):
        value = normalise_path(payload.get(key))
        if value is not None and _is_within(value, paths.project_root):
            payload[key] = str(value)
        elif value is not None:
            payload[key] = ""
    return payload


def translation_output_candidates(config: Any, preferred: Any = None) -> list[Path]:
    """返回当前运行、最近运行和规范输出的去重候选。"""
    paths = RenpyProjectPaths.from_config(config)
    manifest = read_run_manifest(paths) if paths is not None else None
    configured_output = normalise_path(getattr(config, "output_folder", ""))
    manifest_output = normalise_path(manifest.get("output_folder")) if manifest else None
    manifest_is_hook = bool(
        manifest is not None
        and str(manifest.get("run_kind", "")).strip().casefold() == "hook"
    )
    # 用户明确切换到增量/hook/自定义输出时，以当前配置为准；只有配置已
    # 恢复到规范主目录时，才让最近运行清单优先恢复刚完成的任务。
    manifest_first = (
        paths is None
        or configured_output is None
        or _key(configured_output) == _key(paths.translation_output_dir)
    ) and not manifest_is_hook
    # ``preferred`` 仅在属于当前项目时优先，避免校对页复用上一个项目实例。
    configured_is_hook_output = bool(
        paths is not None
        and configured_output is not None
        and _key(configured_output) == _key(paths.application_target_dir)
    )
    recovering_stale_hook = bool(
        manifest_is_hook
        and paths is not None
        and (configured_output is None or configured_is_hook_output)
    )
    if recovering_stale_hook:
        # Hook 运行是临时写回 game/tl；若程序在收尾前退出，优先尝试
        # 稳定主/增量缓存，只有它们都不可用时才回退到 Hook 缓存。
        run_values = (
            paths.translation_output_dir,
            paths.translation_output_dir.parent / f"{paths.language}_new",
            configured_output,
            paths.application_target_dir,
            manifest_output,
        )
    else:
        run_values = (
            manifest_output,
            configured_output,
        ) if manifest_first else (
            configured_output,
            manifest_output,
        )

    # preferred 只代表上一次成功载入的目录。它必须仍与当前显式配置或
    # 当前项目清单一致；否则切换到同项目的另一输出目录时，不能把旧缓存
    # 放在候选首位。
    preferred_path = normalise_path(preferred)
    preferred_is_current = preferred_path is not None and not recovering_stale_hook and (
        (configured_output is not None and _key(preferred_path) == _key(configured_output))
        or (
            manifest_first
            and manifest_output is not None
            and _key(preferred_path) == _key(manifest_output)
        )
    )
    values: Iterable[Any] = (
        (preferred_path, *run_values)
        if preferred_is_current
        else run_values
    )
    result: list[Path] = []
    seen: set[str] = set()
    for value in values:
        path = normalise_path(value)
        if (
            path is not None
            and (paths is None or _is_within(path, paths.project_root))
            and _key(path) not in seen
        ):
            seen.add(_key(path))
            result.append(path)

    if paths is not None:
        for path in (
            paths.translation_output_dir,
            paths.translation_output_dir.parent / f"{paths.language}_new",
            paths.application_target_dir,
        ):
            if _key(path) not in seen:
                seen.add(_key(path))
                result.append(path)
    return result


def resolve_translation_output(config: Any, preferred: Any = None) -> Path | None:
    """优先返回含缓存的输出目录；没有缓存时返回规范输出目录。"""
    candidates = translation_output_candidates(config, preferred)
    for path in candidates:
        if _has_cache(path):
            return path
    return candidates[0] if candidates else None


def restore_resumable_translation_paths(config: Any, output_folder: Any = None) -> Any:
    """Restore the source/output pair for the selected cached run."""
    output_path = (
        normalise_path(output_folder)
        if output_folder is not None
        else resolve_translation_output(config)
    )
    if output_path is None:
        return config

    config.output_folder = str(output_path)
    paths = RenpyProjectPaths.from_config(config)
    manifest = read_run_manifest(paths) if paths is not None else None
    if manifest is None or _key(Path(manifest["output_folder"])) != _key(output_path):
        return config

    input_folder = _normalise(manifest.get("input_folder"))
    if input_folder:
        config.input_folder = input_folder
    return config
