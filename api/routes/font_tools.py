"""字体注入 / 扫描 / 一键替换：复用 FontReplacer，只操作当前绑定项目，长任务走协作取消 Job。"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import stat
import time
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict

from api.jobs import Job
from module.Cache.CacheManager import CacheManager
from module.Engine.Engine import Engine
from module.Renpy.ProjectPaths import RenpyProjectPaths
from module.Tool.FontReplacer import FontReplacer
from module.Tool.LanguageTools import (
    LanguageToolsError,
    contained_game,
    ensure_tl,
    list_tl_languages,
    require_language,
    resolve_project,
)

# 与 LanguageTools 一致：识别 Windows 目录联接（reparse point）
_REPARSE_POINT = 0x400
# 备份树内不得出现可被 Ren'Py 加载的 live 脚本（源码 + 编译）
_SCRIPT_SUFFIXES = {".rpy", ".rpym", ".rpyc", ".rpymc"}

router = APIRouter(prefix="/api/font-tools", tags=["font-tools"])

KIND_SCAN = "font_scan"
KIND_INJECT = "font_inject"
KIND_REPLACE = "font_replace"
KINDS = (KIND_SCAN, KIND_INJECT, KIND_REPLACE)
_WRITE_KINDS = (KIND_INJECT, KIND_REPLACE)
_BUSY = "已有任务正在运行或收尾，请稍后再试"
_FONT_SUFFIXES = {suffix.lower() for suffix in FontReplacer.FONT_SUFFIXES}


class ProjectKeyBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_key: str = ""
    game_path: str = ""


class InjectBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_key: str = ""
    game_path: str = ""
    language: str = "chinese"
    generate_gui_hook: bool = False
    custom_font: str = ""
    confirm: bool = False


class ReplaceBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_key: str = ""
    game_path: str = ""
    replace_all: bool = False
    selected_font: str = ""
    original_font: str = ""
    custom_font: str = ""
    create_backup: bool = True
    confirm: bool = False


def current_paths(config: Any) -> RenpyProjectPaths | None:
    return RenpyProjectPaths.from_config(config)


def _norm(value: str) -> str:
    return os.path.normcase(os.path.abspath(value)) if value else ""


def _project_identity(config: Any) -> tuple[str, ...]:
    """绑定项目 owner 身份；与手动 game_path 目标键分开，切项目时失效。"""
    return tuple(
        _norm(str(getattr(config, field, "") or ""))
        for field in (
            "renpy_project_path",
            "renpy_game_folder",
            "renpy_tl_folder",
            "input_folder",
            "output_folder",
        )
    )


def _bound_paths(config: Any) -> RenpyProjectPaths:
    paths = current_paths(config)
    if paths is None or not paths.game_dir.is_dir():
        raise HTTPException(status_code=400, detail="未绑定游戏项目")
    return paths


def _reject_explicit_empty_game_path(*, game_path_provided: bool, game_path: str) -> None:
    """显式传入空 game_path 必须拒绝；省略字段仍可回退绑定项目（旧调用兼容）。"""
    if game_path_provided and not str(game_path or "").strip():
        raise HTTPException(status_code=400, detail="游戏目录不能为空")


def _resolve_font_target(
    config: Any,
    *,
    game_path: str = "",
    body_project_key: str = "",
    require_body_key: bool = True,
    game_path_provided: bool = False,
) -> tuple[RenpyProjectPaths, tuple[str, ...]]:
    """解析字体工具目标：requires_project 的 owner + 可选手动 game_path。

    - owner：当前绑定项目身份（写前校验未切换）
    - target.project_key：canonical 目标键（可与 owner 不同）
    - 不修改全局 ProjectStore
    - 显式空 game_path → 400；省略 → 绑定项目
    """
    _reject_explicit_empty_game_path(
        game_path_provided=game_path_provided,
        game_path=game_path,
    )
    bound = _bound_paths(config)
    owner_identity = _project_identity(config)
    raw = str(game_path or "").strip()
    if raw:
        try:
            target = resolve_project(raw)
        except LanguageToolsError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        target = bound
    body_key = str(body_project_key or "").strip()
    if require_body_key and not body_key:
        raise HTTPException(status_code=400, detail="project_key 必填")
    if body_key and body_key != target.project_key:
        raise HTTPException(status_code=409, detail="项目已切换，请重新加载后再操作")
    return target, owner_identity


def _latest_job(request: Request, project_key: str, *, kinds: tuple[str, ...] = KINDS) -> Job | None:
    return next(
        (
            job for job in request.app.state.jobs.list()
            if job.kind in kinds and isinstance(job.result, dict)
            and job.result.get("project_key") == project_key
        ),
        None,
    )


def _acquire_engine() -> Engine:
    engine = Engine.get()
    if not engine.try_set_status(Engine.Status.IDLE, Engine.Status.TESTING):
        raise HTTPException(status_code=409, detail=_BUSY)
    return engine


def _describe(paths: RenpyProjectPaths) -> dict:
    game = contained_game(paths)
    languages = list_tl_languages(game)
    # 与 Qt 一致：始终提供 chinese，便于新建汉化
    if "chinese" not in languages:
        languages = [*languages, "chinese"]
    return {
        "project_key": paths.project_key,
        "project_root": str(paths.project_root),
        "game_dir": str(game),
        "languages": languages,
        "font_refs": [],
        "font_files": [],
        "font_ref_count": 0,
        "font_file_count": 0,
    }


def _merge_scan_fields(
    payload: dict,
    job: Job | None,
    *,
    write_job: Job | None = None,
) -> None:
    """把最近一次成功扫描的结果并入 status；写入成功后旧引用作废。"""
    payload.setdefault("fonts_scanned", False)
    payload.setdefault("scan_stale", False)
    if job is None or not isinstance(job.result, dict):
        return
    if job.kind != KIND_SCAN or job.status.value not in {"done"}:
        return
    # 替换/注入已写入且新于扫描 → 旧 refs 作废，避免误导下一次操作
    if (
        write_job is not None
        and write_job.kind in _WRITE_KINDS
        and isinstance(write_job.result, dict)
        and write_job.result.get("written")
        and write_job.status.value in {"done", "failed"}
        and write_job.created_at >= job.created_at
    ):
        payload["font_refs"] = []
        payload["font_files"] = []
        payload["font_ref_count"] = 0
        payload["font_file_count"] = 0
        payload["fonts_scanned"] = False
        payload["scan_stale"] = True
        return
    result = job.result
    refs = list(result.get("font_refs") or [])
    files = list(result.get("font_files") or [])
    payload["font_refs"] = refs
    payload["font_files"] = files
    payload["font_ref_count"] = int(result.get("font_ref_count") or len(refs))
    payload["font_file_count"] = int(result.get("font_file_count") or len(files))
    payload["fonts_scanned"] = True
    payload["scan_stale"] = False
    languages = list(result.get("languages") or payload.get("languages") or [])
    if "chinese" not in languages:
        languages = [*languages, "chinese"]
    payload["languages"] = languages


def _within(root: Path, path: Path) -> bool:
    """真实路径是否仍在 root 内（与 LanguageTools._within 等价）。"""
    try:
        root_real = Path(os.path.normcase(os.path.abspath(root.resolve(strict=False))))
        real = Path(os.path.normcase(os.path.abspath(path.resolve(strict=False))))
    except OSError:
        return False
    return real == root_real or real.is_relative_to(root_real)


def _is_link(path: Path) -> bool:
    """符号链接或 Windows 目录联接（与 LanguageTools._is_link 等价）。"""
    try:
        info = path.lstat()
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    attributes = getattr(info, "st_file_attributes", 0) or 0
    return bool(attributes & _REPARSE_POINT)


def _ensure_descendants_safe(game: Path, root: Path, *, label: str) -> None:
    """遍历已有目录树：任何符号链接 / reparse point，或 resolve 越出 game 都拒绝。"""
    for current, dirnames, filenames in os.walk(root, followlinks=False):
        base = Path(current)
        for name in (*dirnames, *filenames):
            child = base / name
            if _is_link(child):
                raise LanguageToolsError(
                    f"{label}内存在符号链接或目录联接，拒绝写入",
                    code="escape",
                )
            if not _within(game, child):
                raise LanguageToolsError(
                    f"{label}通过符号链接或目录联接越出游戏目录",
                    code="escape",
                )


def _ensure_existing_inject_path(
    game: Path,
    path: Path,
    *,
    expect_dir: bool,
    label: str,
) -> None:
    """已有产物若含链接、越界或类型不对则拒绝；不存在则允许后续新建。"""
    if not (_is_link(path) or path.exists()):
        return
    if _is_link(path):
        raise LanguageToolsError(
            f"{label}是符号链接或目录联接，拒绝写入",
            code="escape",
        )
    if not _within(game, path):
        raise LanguageToolsError(f"{label}通过符号链接或目录联接越出游戏目录", code="escape")
    if expect_dir:
        if not path.is_dir():
            raise LanguageToolsError(f"{label}不是目录", code="bad_target")
        _ensure_descendants_safe(game, path, label=label)
        return
    if path.is_dir():
        raise LanguageToolsError(f"{label}是目录而不是文件", code="target_dir")
    if not path.is_file():
        raise LanguageToolsError(f"{label}不是文件", code="bad_target")


def _ensure_fonts_backup_root(game: Path) -> None:
    """备份根已存在时须为 game 内普通目录，且子项无越界链接。"""
    _ensure_existing_inject_path(
        game,
        game / FontReplacer.BACKUP_DIR_NAME,
        expect_dir=True,
        label="fonts_backup",
    )


def _ensure_game_fonts_dir(game: Path) -> None:
    """GUI / 替换都会写入 game/fonts，已有则校验无链接越界。"""
    _ensure_existing_inject_path(game, game / "fonts", expect_dir=True, label="game/fonts")


def _ensure_tl_tree(game: Path, language: str) -> Path:
    """校验或准备 tl/<language>；语言目录不存在时允许后续新建。"""
    language = require_language(language)
    tl_dir = game / "tl" / language
    try:
        ensured = ensure_tl(game, language)
    except LanguageToolsError as exc:
        if getattr(exc, "code", "") != "missing_tl":
            raise
        tl_root = game / "tl"
        if _is_link(tl_root) or tl_root.exists():
            if not _within(game, tl_root):
                raise LanguageToolsError("翻译目录越出游戏目录", code="escape") from exc
            if not tl_root.is_dir():
                raise LanguageToolsError("翻译目录不是目录", code="bad_tl") from exc
        if _is_link(tl_dir) or tl_dir.exists():
            if not _within(game, tl_dir):
                raise LanguageToolsError("翻译目录越出游戏目录", code="escape") from exc
            if not tl_dir.is_dir():
                raise LanguageToolsError("翻译目录不是目录", code="bad_tl") from exc
        ensured = tl_dir
    else:
        # ensure_tl 成功时仍要扫整棵语言树（GUI 会改写其中脚本）
        _ensure_descendants_safe(game, ensured, label=f"tl/{language}")
    return ensured


def _ensure_font_inject_targets(game: Path, language: str, *, gui_hook: bool) -> Path:
    """注入前校验 tl 目标与已有 base_box/fonts/gui.rpy，以及 fonts_backup。"""
    ensured = _ensure_tl_tree(game, language)
    for name in ("base_box", "fonts"):
        _ensure_existing_inject_path(game, ensured / name, expect_dir=True, label=name)
    if gui_hook:
        _ensure_existing_inject_path(
            game, ensured / "gui.rpy", expect_dir=False, label="gui.rpy",
        )
        # GUI Hook 还会复制字体到 game/fonts，并遍历整个 TL 目录替换 {font}
        _ensure_game_fonts_dir(game)
        if ensured.exists():
            _ensure_descendants_safe(game, ensured, label=f"tl/{language}")
    _ensure_fonts_backup_root(game)
    return ensured


def _ensure_replace_targets(game: Path) -> None:
    """一键替换会改写 game 下脚本并写入 game/fonts，拒绝链接树。"""
    _ensure_game_fonts_dir(game)
    _ensure_fonts_backup_root(game)
    # 跳过 fonts_backup 子树（备份目录自身已单独校验）
    for current, dirnames, filenames in os.walk(game, followlinks=False):
        base = Path(current)
        try:
            rel_parts = base.relative_to(game).parts
        except ValueError:
            raise LanguageToolsError("游戏目录遍历越界", code="escape") from None
        if rel_parts and rel_parts[0] == FontReplacer.BACKUP_DIR_NAME:
            dirnames[:] = []
            continue
        # 不深入备份目录
        dirnames[:] = [name for name in dirnames if name != FontReplacer.BACKUP_DIR_NAME]
        for name in (*dirnames, *filenames):
            child = base / name
            if name == FontReplacer.BACKUP_DIR_NAME:
                continue
            if _is_link(child):
                raise LanguageToolsError(
                    "游戏目录内存在符号链接或目录联接，拒绝写入",
                    code="escape",
                )
            if not _within(game, child):
                raise LanguageToolsError(
                    "游戏目录通过符号链接或目录联接越出边界",
                    code="escape",
                )


def _unique_backup_dir(backup_root: Path, prefix: str) -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    candidate = backup_root / f"{prefix}_{stamp}"
    counter = 1
    while candidate.exists() or _is_link(candidate):
        candidate = backup_root / f"{prefix}_{stamp}_{counter}"
        counter += 1
    return candidate


def _sanitize_backup_scripts(root: Path) -> None:
    """安全网：若仍有 live 源码/编译脚本，改名为 *.bak，防止 Ren'Py 执行。"""
    scripts = [
        path for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in _SCRIPT_SUFFIXES
    ]
    for path in scripts:
        target = path.with_name(f"{path.name}.bak")
        counter = 1
        while target.exists() or _is_link(target):
            target = path.with_name(f"{path.name}.bak_{counter}")
            counter += 1
        path.replace(target)


def _backup_dest_rel(rel: Path) -> Path:
    """脚本备份相对路径：四扩展名一开始就带 .bak，不先 copy 后改名。"""
    if rel.suffix.lower() in _SCRIPT_SUFFIXES:
        return rel.with_name(f"{rel.name}.bak")
    return rel


def _copy_path_into_backup(src: Path, backup_root: Path, game: Path) -> None:
    """把文件或目录拷进备份树；.rpy/.rpym/.rpyc/.rpymc 直接以 .bak 落盘。"""
    if src.is_file():
        dest = backup_root / _backup_dest_rel(src.relative_to(game))
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return
    if not src.is_dir():
        raise RuntimeError(f"无法备份目标: {src}")
    for file_path in src.rglob("*"):
        if not file_path.is_file():
            continue
        dest = backup_root / _backup_dest_rel(file_path.relative_to(game))
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, dest)


class FontWorkError(RuntimeError):
    """写入阶段业务失败：携带已发生的 written/partial/backup 等字段，供 Job.result 合并。"""

    def __init__(self, message: str, payload: dict[str, Any]):
        super().__init__(message)
        self.payload = payload


def _backup_existing_targets(game: Path, language: str, *, gui_hook: bool) -> str | None:
    """覆盖已有目标前备份；GUI 时额外备份会改写的整棵 TL 与 game/fonts。"""
    _ensure_fonts_backup_root(game)
    tl_dir = game / "tl" / language
    targets: list[Path] = []
    if gui_hook:
        # GUI Hook 会改写 tl/<lang> 下脚本并复制字体到 game/fonts
        if tl_dir.is_dir():
            targets.append(tl_dir)
        fonts_dir = game / "fonts"
        if fonts_dir.is_dir():
            targets.append(fonts_dir)
    else:
        for name in ("base_box", "fonts"):
            path = tl_dir / name
            if path.exists():
                targets.append(path)
    if not targets:
        return None
    backup_root = _unique_backup_dir(game / FontReplacer.BACKUP_DIR_NAME, "inject")
    backup_root.mkdir(parents=True, exist_ok=True)
    try:
        for path in targets:
            _copy_path_into_backup(path, backup_root, game)
    except Exception as exc:
        # 复制中断时绝不留下 live .rpy；保留目录供人工恢复
        with contextlib.suppress(Exception):
            _sanitize_backup_scripts(backup_root)
        raise RuntimeError(
            f"备份失败，已拒绝修改；可恢复路径: {backup_root}"
        ) from exc
    # 防御：确认备份树无 live 源码/编译脚本
    live = [
        p for p in backup_root.rglob("*")
        if p.is_file() and p.suffix.lower() in _SCRIPT_SUFFIXES
    ]
    if live:
        with contextlib.suppress(Exception):
            _sanitize_backup_scripts(backup_root)
        raise RuntimeError(
            f"备份含可编译脚本，已拒绝修改；可恢复路径: {backup_root}"
        )
    return str(backup_root)


def _find_builtin_pack_roots() -> tuple[Path | None, Path | None]:
    """定位内置 base_box 与 fonts 资源根（写前检查用）。"""

    def _find_root(start: Path) -> Path | None:
        for parent in [start] + list(start.parents):
            if (parent / "resource").exists():
                return parent
        return None

    root = _find_root(Path(__file__).resolve())
    if root is None:
        return None, None
    base_src = next(
        (
            p for p in (
                root / "resource" / "base_box",
                root / "dist" / "base_box",
                root / "dist" / "base_ma",
            )
            if p.exists()
        ),
        None,
    )
    fonts_src = next(
        (
            p for p in (
                root / "resource" / "fonts",
                root / "dist" / "fonts",
            )
            if p.exists()
        ),
        None,
    )
    return base_src, fonts_src


def _resolve_font_source(custom_font: str, *, required: bool) -> str:
    """解析自定义或内置字体；写前检查扩展名与存在性。"""
    font_source = str(custom_font or "").strip()
    if font_source:
        path = Path(font_source)
        if path.suffix.lower() not in _FONT_SUFFIXES:
            raise RuntimeError("自定义字体扩展名无效，仅支持 .ttf/.otf/.ttc/.otc")
        if not path.is_file():
            raise RuntimeError("自定义字体文件不存在")
        return str(path)
    if not required:
        return ""
    builtin = FontReplacer().get_builtin_font_path() or ""
    if not builtin:
        raise RuntimeError("未找到内置字体")
    return builtin


def resolve_original_fonts(
    *,
    replace_all: bool,
    selected_font: str,
    original_font: str,
    detected: list[str],
) -> list[str] | None:
    """与 Qt `_replace_all_fonts` 对齐，并让检测下拉选项生效。

    - replace_all：使用已检测列表（空则由调用方再扫）
    - 否则优先手输原字体，其次检测下拉选中项
    - 都没有则返回 None（调用方提示用户）
    """
    manual = str(original_font or "").strip()
    selected = str(selected_font or "").strip()
    if replace_all:
        return list(detected)
    if manual:
        return [manual]
    if selected:
        return [selected]
    return None


def _run_scan(project_root: str, check_cancel: Callable[[], None]) -> dict:
    check_cancel()
    paths = resolve_project(project_root)
    game = contained_game(paths)
    check_cancel()
    replacer = FontReplacer()
    font_refs = list(replacer.scan_fonts(str(game), check_cancel=check_cancel))
    check_cancel()
    font_files = [rel for rel, _ in replacer.discover_font_files(str(game), check_cancel=check_cancel)]
    check_cancel()
    languages = list_tl_languages(game)
    if "chinese" not in languages:
        languages = [*languages, "chinese"]
    check_cancel()
    return {
        "written": False,
        "action": "scan",
        "font_refs": font_refs,
        "font_files": font_files,
        "font_ref_count": len(font_refs),
        "font_file_count": len(font_files),
        "languages": languages,
        "lang_count": len(languages),
        "message": (
            f"扫描完成：检测到 {len(font_refs)} 个字体引用，"
            f"发现 {len(font_files)} 个字体文件，{len(languages)} 个翻译语言"
        ),
    }


def _run_inject(
    project_root: str,
    language: str,
    *,
    generate_gui_hook: bool,
    custom_font: str,
    check_cancel: Callable[[], None],
) -> dict:
    """在工作线程中执行注入；写文件开始后不再协作取消检查点。"""
    check_cancel()
    paths = resolve_project(project_root)
    game = contained_game(paths)
    language = require_language(language)
    # 写前：自定义/内置字体、内置资源包、目标路径（失败须零副作用）
    font_source = ""
    if generate_gui_hook:
        font_source = _resolve_font_source(custom_font, required=True)
        replacer_probe = FontReplacer()
        if not Path(replacer_probe.template_path).is_file():
            raise RuntimeError(f"模板文件不存在: {replacer_probe.template_path}")
    base_src, fonts_src = _find_builtin_pack_roots()
    if base_src is None or fonts_src is None:
        missing = "base_box/base_ma" if base_src is None else "fonts"
        raise RuntimeError(f"资源缺失: {missing}")
    _ensure_font_inject_targets(game, language, gui_hook=generate_gui_hook)
    check_cancel()
    # 从此处起进入写入：备份 / 部署 / GUI，不再因取消中断并谎称未写入
    backup_path: str | None = None
    written = False
    partial = False
    gui_ok: bool | None = None

    def _payload(message: str) -> dict[str, Any]:
        return {
            "written": written,
            "partial": partial,
            "language": language,
            "message": message,
            "backup_path": backup_path,
            "gui_hook": gui_ok,
            "base_box": str(game / "tl" / language / "base_box"),
            "fonts_dir": str(game / "tl" / language / "fonts"),
            "action": "inject",
        }

    try:
        backup_path = _backup_existing_targets(game, language, gui_hook=generate_gui_hook)
    except Exception as exc:
        # 仅备份目录可能有残留；游戏源码未改
        path_hint = getattr(exc, "backup_path", None)
        if path_hint:
            backup_path = str(path_hint)
        elif "可恢复路径:" in str(exc):
            backup_path = str(exc).rsplit("可恢复路径:", 1)[-1].strip()
        raise FontWorkError(str(exc), _payload(str(exc))) from exc

    try:
        replacer = FontReplacer()
        ok, message = replacer.deploy_builtin_font_pack(str(game), language)
        if not ok:
            # 部署已执行：可能 mkdir / 写了一部分，不得谎称未写入
            written = True
            partial = True
            raise FontWorkError(message or "字体包注入失败", _payload(message or "字体包注入失败"))
        written = True
        if generate_gui_hook:
            try:
                gui_ok = bool(replacer.gen_gui_fonts(str(game), language, font_source, is_rtl=False))
            except Exception as exc:
                partial = True
                gui_ok = False
                msg = f"字体包已注入，但 GUI Hook 生成异常: {exc}"
                raise FontWorkError(msg, _payload(msg)) from exc
            if not gui_ok:
                partial = True
                warning = "字体包已注入，但 GUI Hook 生成失败"
                return _payload(warning)
    except FontWorkError:
        raise
    except Exception as exc:
        if written:
            partial = True
        raise FontWorkError(str(exc), _payload(str(exc))) from exc
    return _payload(f"字体包已注入 tl/{language}。")


def _run_replace(
    project_root: str,
    *,
    replace_all: bool,
    selected_font: str,
    original_font: str,
    custom_font: str,
    create_backup: bool,
    check_cancel: Callable[[], None],
) -> dict:
    """一键替换脚本字体引用；写前校验，写入开始后不再协作取消。"""
    check_cancel()
    paths = resolve_project(project_root)
    game = contained_game(paths)
    font_source = _resolve_font_source(custom_font, required=True)
    _ensure_replace_targets(game)
    check_cancel()
    replacer = FontReplacer()
    detected = list(replacer.scan_fonts(str(game), check_cancel=check_cancel))
    originals = resolve_original_fonts(
        replace_all=replace_all,
        selected_font=selected_font,
        original_font=original_font,
        detected=detected,
    )
    if originals is None:
        if detected:
            raise RuntimeError("请勾选“替换所有检测到的字体”或填写/选择要替换的原字体")
        raise RuntimeError("未检测到任何字体引用")
    if replace_all and not originals:
        raise RuntimeError("未检测到任何字体引用")
    check_cancel()
    # 写入阶段：safe_replace_font（备份 + 复制字体 + 改脚本）
    success, message, details = replacer.safe_replace_font(
        game_dir=str(game),
        source_font_path=font_source,
        original_fonts=originals,
        create_backup=create_backup,
    )
    backup_name = str(details.get("backup_name") or "")
    backup_path = str(game / FontReplacer.BACKUP_DIR_NAME / backup_name) if backup_name else None
    replaced_files = int(details.get("replaced_files") or 0)
    replaced_count = int(details.get("replaced_count") or 0)
    failed_files = [str(item) for item in (details.get("failed_files") or [])]
    font_copied = bool(details.get("font_copied"))
    scripts_written = bool(details.get("scripts_written") or replaced_files > 0)
    font_residue = str(details.get("font_residue") or "")
    restored = details.get("restored")
    payload = {
        "action": "replace",
        "backup_path": backup_path,
        "backup_name": backup_name,
        "replaced_files": replaced_files,
        "replaced_count": replaced_count,
        "failed_files": failed_files,
        "font_copied": font_copied,
        "scripts_written": scripts_written,
        "font_residue": font_residue or None,
        "original_fonts": originals,
        "restored": restored,
    }
    if not success:
        # 用 details 真实副作用判定，禁止再用 bool(backup_name) 猜测 written。
        # atomic 写失败进 failed_files 但原稿未坏，不能单靠 failed_files 标 written。
        game_touched = bool(
            font_copied
            or scripts_written
            or replaced_files > 0
            or replaced_count > 0
            or font_residue
        )
        if restored is True and not font_residue:
            written = False
            partial = False
        elif game_touched:
            written = True
            partial = True
        elif backup_name and "备份失败" in (message or ""):
            # 仅备份阶段失败：源码与 fonts 未改
            written = False
            partial = False
        else:
            written = False
            partial = False
        raise FontWorkError(
            message or "字体替换失败",
            {
                **payload,
                "written": written,
                "partial": partial,
                "message": message or "字体替换失败",
            },
        )
    # 成功：按实际复制/脚本写入标记，不用备份目录存在推断
    written = bool(font_copied or scripts_written or replaced_files > 0 or replaced_count > 0)
    return {
        **payload,
        "written": written,
        "partial": False,
        "message": (
            f"字体替换完成：修改 {replaced_files} 个文件，共 {replaced_count} 处"
            + (f"；备份：{backup_name}" if backup_name else "")
            if written
            else (message or "没有需要替换的字体引用")
        ),
    }


async def _start_font_job(
    request: Request,
    *,
    kind: str,
    project_key: str,
    message: str,
    seed: dict[str, Any],
    compute: Callable[[Callable[[], None]], dict],
    owner_identity: tuple[str, ...],
    allow_cancel_after_write: bool = False,
) -> dict:
    """统一启动字体 Job；写前校验冻结 owner，写入后结果不被取消/切项目掩盖。"""
    engine = _acquire_engine()
    manager = request.app.state.jobs
    try:
        job = manager.create(kind, total=1, cooperative_cancel=True)
    except Exception:
        engine.release_status(Engine.Status.TESTING)
        raise
    job.result = {
        "project_key": project_key,
        "message": message,
        "written": False,
        "partial": False,
        "worker_active": True,
        "owner_identity": owner_identity,
        **seed,
    }
    loop = asyncio.get_running_loop()
    frozen_owner = owner_identity

    def owner_still() -> bool:
        with CacheManager.LOCK:
            live = request.app.state.config
        return _project_identity(live) == frozen_owner

    def check_cancel() -> None:
        """协作取消 + 冻结 owner；切项目后尚未写入时禁止继续。"""
        if job.cancel_event.is_set():
            raise asyncio.CancelledError()
        if not owner_still():
            raise RuntimeError("项目已切换，未写入")

    def run_compute() -> dict:
        check_cancel()
        result = compute(check_cancel)
        if isinstance(job.result, dict) and job.result.get("worker_active"):
            job.result.update(result)
        return result

    async def worker(_: Job) -> dict:
        try:
            check_cancel()
            future = loop.run_in_executor(None, run_compute)
            try:
                result = await asyncio.shield(future)
            except asyncio.CancelledError:
                job.cancel_event.set()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await asyncio.shield(future)
                # 线程可能已写完：保留 result，勿用「未写入」掩盖；不提前释放已发生结果
                if isinstance(job.result, dict) and job.result.get("written") and not allow_cancel_after_write:
                    job.cancel_event.clear()
                    job.result["worker_active"] = False
                    manager.progress(job.id, done=1, total=1)
                    return job.result
                raise
            if isinstance(job.result, dict):
                job.result.update(result)
                if job.cancel_event.is_set() and not job.result.get("written"):
                    job.result["message"] = "任务已取消"
                    raise asyncio.CancelledError()
                # 已写入则即使收到取消也按完成回报
                if job.cancel_event.is_set() and job.result.get("written") and not allow_cancel_after_write:
                    job.cancel_event.clear()
            manager.progress(job.id, done=1, total=1)
            return job.result
        except asyncio.CancelledError:
            if isinstance(job.result, dict):
                if job.result.get("written") and not allow_cancel_after_write:
                    job.result.setdefault("partial", True)
                    job.result.setdefault("message", "任务完成（取消请求在写入后到达）")
                    job.cancel_event.clear()
                    manager.progress(job.id, done=1, total=1)
                    return job.result
                job.result["message"] = "任务已取消"
            raise
        except Exception as exc:
            # 业务失败携带的 written/partial/backup 必须先合并，再决定是否改写为取消
            if isinstance(exc, FontWorkError) and isinstance(job.result, dict):
                job.result.update(exc.payload)
            if job.cancel_event.is_set() and not (isinstance(job.result, dict) and job.result.get("written")):
                if isinstance(job.result, dict):
                    job.result["message"] = "任务已取消"
                raise asyncio.CancelledError() from exc
            if isinstance(job.result, dict):
                if not isinstance(exc, FontWorkError):
                    job.result["message"] = str(exc)
                    if job.result.get("written"):
                        job.result["partial"] = True
                    else:
                        job.result["written"] = False
                else:
                    job.result.setdefault("message", str(exc))
            raise
        finally:
            if isinstance(job.result, dict):
                job.result["worker_active"] = False
            engine.release_status(Engine.Status.TESTING)

    try:
        await manager.run(job.id, worker)
    except BaseException:
        if isinstance(job.result, dict):
            job.result["worker_active"] = False
        engine.release_status(Engine.Status.TESTING)
        raise
    return {"job": job.snapshot()}


@router.get("")
def read_font_tools(
    request: Request,
    game_path: str | None = Query(default=None),
) -> dict:
    """返回目标项目的字体工具状态；job 为最近任务，last_write_job 保留写入报告。"""
    with CacheManager.LOCK:
        paths, _owner = _resolve_font_target(
            request.app.state.config,
            game_path=game_path or "",
            body_project_key="",
            require_body_key=False,
            game_path_provided=game_path is not None,
        )
        try:
            payload = _describe(paths)
        except LanguageToolsError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        project_key = paths.project_key
    scan_job = _latest_job(request, project_key, kinds=(KIND_SCAN,))
    write_job = _latest_job(request, project_key, kinds=_WRITE_KINDS)
    job = _latest_job(request, project_key)
    _merge_scan_fields(payload, scan_job, write_job=write_job)
    payload["job"] = job.snapshot() if job else None
    payload["last_write_job"] = write_job.snapshot() if write_job else None
    return payload


@router.post("/scan")
async def scan_fonts(request: Request, body: ProjectKeyBody) -> dict:
    """只读扫描：脚本字体引用 / 实际字体文件 / TL 语言；可协作取消。"""
    with CacheManager.LOCK:
        paths, owner_identity = _resolve_font_target(
            request.app.state.config,
            game_path=body.game_path,
            body_project_key=body.project_key,
            game_path_provided="game_path" in body.model_fields_set,
        )
        project_key = paths.project_key
        snapshot = str(paths.project_root)

    return await _start_font_job(
        request,
        kind=KIND_SCAN,
        project_key=project_key,
        message="准备扫描字体",
        seed={"action": "scan", "game_path": str(body.game_path or "")},
        owner_identity=owner_identity,
        compute=lambda check_cancel: _run_scan(snapshot, check_cancel),
        allow_cancel_after_write=True,
    )


@router.post("/inject")
async def inject_fonts(request: Request, body: InjectBody) -> dict:
    """确认后向目标项目注入预置字体包（可选 GUI Hook）。"""
    if not body.confirm:
        raise HTTPException(status_code=400, detail="写入字体包需要 confirm=true")
    try:
        language = require_language(body.language or "chinese")
    except LanguageToolsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # 建任务前即可失败的写前检查（自定义字体 / 资源 / 路径）
    try:
        if body.generate_gui_hook:
            _resolve_font_source(body.custom_font, required=True)
        base_src, fonts_src = _find_builtin_pack_roots()
        if base_src is None or fonts_src is None:
            missing = "base_box/base_ma" if base_src is None else "fonts"
            raise RuntimeError(f"资源缺失: {missing}")
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    with CacheManager.LOCK:
        paths, owner_identity = _resolve_font_target(
            request.app.state.config,
            game_path=body.game_path,
            body_project_key=body.project_key,
            game_path_provided="game_path" in body.model_fields_set,
        )
        try:
            game = contained_game(paths)
            _ensure_font_inject_targets(game, language, gui_hook=body.generate_gui_hook)
        except LanguageToolsError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        project_key = paths.project_key
        snapshot = str(paths.project_root)

    custom_font = body.custom_font
    generate_gui_hook = body.generate_gui_hook
    return await _start_font_job(
        request,
        kind=KIND_INJECT,
        project_key=project_key,
        message="准备注入字体包",
        owner_identity=owner_identity,
        seed={
            "action": "inject",
            "language": language,
            "generate_gui_hook": generate_gui_hook,
            "game_path": str(body.game_path or ""),
        },
        compute=lambda check_cancel: _run_inject(
            snapshot,
            language,
            generate_gui_hook=generate_gui_hook,
            custom_font=custom_font,
            check_cancel=check_cancel,
        ),
    )


@router.post("/replace")
async def replace_fonts(request: Request, body: ReplaceBody) -> dict:
    """确认后一键替换脚本中的字体引用（破坏性，可备份）。"""
    if not body.confirm:
        raise HTTPException(status_code=400, detail="替换字体会修改脚本，需要 confirm=true")

    try:
        _resolve_font_source(body.custom_font, required=True)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # 空/全部模式按 Qt：未勾选全部且未选手输/检测项 → 400
    preview = resolve_original_fonts(
        replace_all=body.replace_all,
        selected_font=body.selected_font,
        original_font=body.original_font,
        detected=["__preview__"] if body.replace_all else [],
    )
    if preview is None:
        raise HTTPException(
            status_code=400,
            detail="请勾选“替换所有检测到的字体”或填写/选择要替换的原字体",
        )

    with CacheManager.LOCK:
        paths, owner_identity = _resolve_font_target(
            request.app.state.config,
            game_path=body.game_path,
            body_project_key=body.project_key,
            game_path_provided="game_path" in body.model_fields_set,
        )
        try:
            game = contained_game(paths)
            _ensure_replace_targets(game)
        except LanguageToolsError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        project_key = paths.project_key
        snapshot = str(paths.project_root)

    return await _start_font_job(
        request,
        kind=KIND_REPLACE,
        project_key=project_key,
        message="准备替换字体",
        owner_identity=owner_identity,
        seed={
            "action": "replace",
            "replace_all": body.replace_all,
            "create_backup": body.create_backup,
            "game_path": str(body.game_path or ""),
        },
        compute=lambda check_cancel: _run_replace(
            snapshot,
            replace_all=body.replace_all,
            selected_font=body.selected_font,
            original_font=body.original_font,
            custom_font=body.custom_font,
            create_backup=body.create_backup,
            check_cancel=check_cancel,
        ),
    )
