"""添加语言入口与设置默认语言，供 API 与旧 Qt 页共用。

资源原文只从 resource 读取，不把 Hook 或模板抄进代码。
语言名只接受或拒绝，不改写大小写，也不剥掉 _new 后缀。
"""

from __future__ import annotations

import ast
import os
import stat
import textwrap
from pathlib import Path, PureWindowsPath

from base.PathHelper import get_resource_path
from module.File.AtomicWrite import atomic_write_text
from module.Renpy.ProjectPaths import RenpyProjectPaths

HOOK_NAME = "hook_add_change_language_entrance.rpy"
DEFAULT_SCRIPT_NAME = "set_default_language_at_startup.rpy"
_PLACEHOLDER = "{tl_name}"
_HOOK_PARTS = ("resource", "hooks", HOOK_NAME)
_TEMPLATE_PARTS = ("resource", "templates", "default_langauge_template.txt")
_INVALID_CHARS = set('<>:"/\\|?*\'')
_ABNORMAL = {"none", "null", "undefined", "tl", "game"}
_SUFFIXES = ("_new", "_filtered_suspicious")
_REPARSE_POINT = 0x400
_MAX_SCRIPT_BYTES = 65536


class LanguageToolsError(Exception):
    """共享逻辑的中文内部异常。界面文案仍由调用方的 Localizer 负责。"""

    def __init__(self, message: str, *, code: str = "", source: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.source = source


def language_rejection(language: object) -> str:
    """返回拒绝原因；合法名称原样可用，调用方不得再改写。"""
    if not isinstance(language, str) or not language or language != language.strip():
        return "语言名无效"
    if language in {".", ".."} or language.endswith("."):
        return "语言名无效"
    folded = language.casefold()
    if folded in _ABNORMAL or any(folded.endswith(suffix) for suffix in _SUFFIXES):
        return "语言名无效"
    if any(ord(char) < 32 or char in _INVALID_CHARS for char in language):
        return "语言名无效"
    if len(language) > 255 or PureWindowsPath(language).is_reserved():
        return "语言名无效"
    return ""


def require_language(language: object) -> str:
    if language_rejection(language):
        raise LanguageToolsError("语言名无效", code="bad_language")
    return str(language)


def describe_project(raw: str | Path) -> dict:
    """查看游戏根或 game 目录上的语言工具状态。"""
    return describe_paths(resolve_project(raw))


def describe_paths(paths: RenpyProjectPaths) -> dict:
    """查看已解析项目。链接越界时拒绝，不把外部文件当成项目状态。"""
    return _describe(paths)


def ensure_hook_resource() -> None:
    """确认语言入口资源可读，不把内容复制进代码。"""
    _read_resource(*_HOOK_PARTS, code="missing_hook", label="语言入口资源缺失")


def install_language_entrance(raw: str | Path) -> dict:
    """把语言入口 Hook 原子写入 game 目录。"""
    paths = resolve_project(raw)
    game = contained_game(paths)
    target = ensure_file_target(game, HOOK_NAME)
    text, _newline, _source = _read_resource(*_HOOK_PARTS, code="missing_hook", label="语言入口资源缺失")
    _atomic_write(target, text, game, newline="", label="语言入口写入失败，原文件已保留")
    return {
        "action": "entrance",
        "path": str(target),
        "message": "语言入口已写入",
        "written": True,
        "language": None,
    }


def install_default_language(raw: str | Path, language: str) -> dict:
    """确认翻译目录存在后，用模板生成默认语言脚本。"""
    language = require_language(language)
    paths = resolve_project(raw)
    game = contained_game(paths)
    ensure_tl(game, language)
    target = ensure_file_target(game, DEFAULT_SCRIPT_NAME)
    script = render_default_script(language)
    _atomic_write(
        target,
        script,
        game,
        newline="\n",
        label="默认语言写入失败，原文件已保留",
        validator=lambda text: require_default_assignment(text, language),
    )
    return {
        "action": "default",
        "path": str(target),
        "message": "默认语言已写入",
        "written": True,
        "language": language,
    }


def render_default_script(language: str) -> str:
    """只替换模板占位符，并在写入前确认它仍是一条字符串赋值。"""
    language = require_language(language)
    template, _newline, _source = _read_resource(
        *_TEMPLATE_PARTS, code="missing_template", label="默认语言模板缺失",
    )
    if template.count(_PLACEHOLDER) != 1:
        raise LanguageToolsError("默认语言模板无效", code="missing_template", source=_source)
    script = template.replace(_PLACEHOLDER, language, 1)
    require_default_assignment(script, language)
    return script


def parse_default_language(text: str) -> str | None:
    """只解析赋值，不执行脚本。格式不对时返回空。"""
    try:
        return _assignment_language(text)
    except (LanguageToolsError, SyntaxError, ValueError):
        return None


def require_default_assignment(text: str, expected: str) -> str:
    found = _assignment_language(text)
    if found != expected:
        raise LanguageToolsError("默认语言脚本赋值不安全", code="bad_script")
    return found


def resolve_project(raw: str | Path) -> RenpyProjectPaths:
    if not isinstance(raw, (str, Path)) or not str(raw).strip():
        raise LanguageToolsError("项目路径不能为空", code="missing_project")
    path = Path(raw)
    try:
        exists = path.exists()
    except OSError as exc:
        raise LanguageToolsError("项目路径不存在", code="missing_project") from exc
    if not exists:
        raise LanguageToolsError("项目路径不存在", code="missing_project")
    paths = RenpyProjectPaths.from_path(path)
    if paths is None or not paths.game_dir.is_dir():
        raise LanguageToolsError("找不到 game 目录", code="missing_project")
    contained_game(paths)
    return paths


def contained_game(paths: RenpyProjectPaths) -> Path:
    """game 目录的真实位置必须留在项目根内。"""
    root = paths.project_root
    game = paths.game_dir
    linked_outside = _is_link(game) and not _within(root, game)
    if linked_outside or (_is_link(game) and not game.is_dir()):
        raise LanguageToolsError("游戏目录通过符号链接或目录联接越出项目", code="escape")
    if not game.is_dir():
        raise LanguageToolsError("找不到 game 目录", code="missing_project")
    if not _within(root, game):
        raise LanguageToolsError("游戏目录通过符号链接或目录联接越出项目", code="escape")
    return game.resolve()


def ensure_file_target(game: Path, name: str) -> Path:
    """目标必须是 game 目录内的文件；越界链接和目录都拒绝。"""
    if name != Path(name).name:
        raise LanguageToolsError("目标文件名无效", code="bad_target")
    target = game / name
    if _is_link(target):
        if not _within(game, target):
            raise LanguageToolsError("目标符号链接或目录联接越出游戏目录", code="escape")
        if target.is_dir():
            raise LanguageToolsError("目标是目录而不是文件", code="target_dir")
        if not target.is_file():
            raise LanguageToolsError("目标符号链接未指向文件", code="escape")
        return target
    if target.exists() and not target.is_file():
        raise LanguageToolsError("目标是目录而不是文件", code="target_dir")
    if not _within(game, target.parent):
        raise LanguageToolsError("目标路径越出游戏目录", code="escape")
    return target


def ensure_tl(game: Path, language: str) -> Path:
    language = require_language(language)
    tl_dir = game / "tl" / language
    if ((_is_link(game / "tl") or _is_link(tl_dir) or tl_dir.exists()) and not _within(game, tl_dir)):
        raise LanguageToolsError("翻译目录越出游戏目录", code="escape")
    if not tl_dir.is_dir():
        raise LanguageToolsError(f"找不到翻译目录：{tl_dir}", code="missing_tl")
    return tl_dir


def list_tl_languages(game: Path) -> list[str]:
    tl_root = game / "tl"
    if not tl_root.is_dir() or not _within(game, tl_root):
        return []
    names: list[str] = []
    try:
        children = list(tl_root.iterdir())
    except OSError:
        return []
    for child in children:
        name = child.name
        if language_rejection(name) or not child.is_dir() or not _within(tl_root, child):
            continue
        names.append(name)
    return sorted(names, key=str.casefold)


def _describe(paths: RenpyProjectPaths) -> dict:
    game = contained_game(paths)
    entrance = game / HOOK_NAME
    default_path = game / DEFAULT_SCRIPT_NAME
    return {
        "project_key": paths.project_key,
        "project_root": str(paths.project_root),
        "game_dir": str(game),
        "languages": list_tl_languages(game),
        "entrance_exists": _safe_regular_file(game, entrance),
        "default_script_exists": _safe_regular_file(game, default_path),
        "default_language": _read_default_language(game, default_path),
    }


def _read_default_language(game: Path, path: Path) -> str | None:
    if not _safe_regular_file(game, path):
        return None
    try:
        if path.stat().st_size > _MAX_SCRIPT_BYTES:
            return None
        return parse_default_language(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError):
        return None


def _safe_regular_file(root: Path, path: Path) -> bool:
    try:
        if not path.exists() and not _is_link(path):
            return False
        if not _within(root, path):
            return False
        return path.is_file()
    except OSError:
        return False


def _assignment_language(text: str) -> str:
    lines = text.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines or not lines[0].strip().lower().startswith("init ") or not lines[0].strip().lower().endswith("python:"):
        raise LanguageToolsError("默认语言脚本格式无效", code="bad_script")
    if not _is_init_python(lines[0]):
        raise LanguageToolsError("默认语言脚本格式无效", code="bad_script")
    body = textwrap.dedent("\n".join(lines[1:]))
    tree = ast.parse(body)
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.Assign):
        raise LanguageToolsError("默认语言脚本不是单一赋值", code="bad_script")
    assign = tree.body[0]
    if len(assign.targets) != 1 or not _is_preference_language(assign.targets[0]):
        raise LanguageToolsError("默认语言脚本赋值目标无效", code="bad_script")
    value = assign.value
    if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
        raise LanguageToolsError("默认语言脚本赋值不是字符串", code="bad_script")
    if language_rejection(value.value):
        raise LanguageToolsError("默认语言脚本中的语言名无效", code="bad_script")
    return value.value


def _is_init_python(line: str) -> bool:
    parts = line.strip().split()
    return len(parts) == 3 and parts[0].lower() == "init" and parts[1].isdigit() and parts[2].lower() == "python:"


def _is_preference_language(node: ast.AST) -> bool:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return False
    parts.append(current.id)
    return list(reversed(parts)) == ["renpy", "game", "preferences", "language"]


def _read_resource(*parts: str, code: str, label: str) -> tuple[str, str, str]:
    source = Path(get_resource_path(*parts))
    if not source.is_file() or source.is_symlink():
        raise LanguageToolsError(label, code=code, source=str(source))
    try:
        raw = source.read_bytes()
        text = raw.decode("utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise LanguageToolsError(label, code=code, source=str(source)) from exc
    newline = "\r\n" if b"\r\n" in raw else "\n"
    return text, newline, str(source)


def _atomic_write(
    target: Path,
    text: str,
    game: Path,
    *,
    newline: str,
    label: str,
    validator=None,
) -> None:
    try:
        atomic_write_text(
            target,
            text,
            encoding="utf-8",
            newline=newline,
            validator=validator,
            allowed_roots=[game],
        )
    except LanguageToolsError:
        raise
    except Exception as exc:
        raise LanguageToolsError(label, code="write_failed") from exc


def _within(root: Path, path: Path) -> bool:
    try:
        root_real = Path(os.path.normcase(os.path.abspath(root.resolve(strict=False))))
        real = Path(os.path.normcase(os.path.abspath(path.resolve(strict=False))))
    except OSError:
        return False
    return real == root_real or real.is_relative_to(root_real)


def _is_link(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    attributes = getattr(info, "st_file_attributes", 0) or 0
    return bool(attributes & _REPARSE_POINT)


__all__ = [
    "DEFAULT_SCRIPT_NAME",
    "HOOK_NAME",
    "LanguageToolsError",
    "contained_game",
    "describe_paths",
    "describe_project",
    "ensure_file_target",
    "ensure_hook_resource",
    "ensure_tl",
    "install_default_language",
    "install_language_entrance",
    "language_rejection",
    "list_tl_languages",
    "parse_default_language",
    "render_default_script",
    "require_language",
    "resolve_project",
]
