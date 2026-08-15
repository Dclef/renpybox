"""
YiJianFanyiPage - 一键翻译向导页面
向导式分步骤流程：每次只显示一个进度页面，完成后自动进入下一步
"""

import os
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFileDialog,
    QStackedWidget,
    QSizePolicy,
    QProgressDialog,
)
from qfluentwidgets import (
    FlowLayout,
    SingleDirectionScrollArea,
    CardWidget,
    SubtitleLabel,
    CaptionLabel,
    BodyLabel,
    PrimaryPushButton,
    PushButton,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    ProgressBar,
    ProgressRing,
    TitleLabel,
    ComboBox,
    LineEdit,
    CheckBox,
    qconfig,
    TransparentToolButton,
    isDarkTheme,
    StrongBodyLabel,
)

from base.Base import Base
from base.BaseLanguage import BaseLanguage
from base.LogManager import LogManager
from base.PathHelper import get_resource_path
from widget.Separator import Separator
from widget.ItemCard import ItemCard
from widget.ThemeHelper import mark_toolbox_widget, mark_toolbox_scroll_area
from module.Extract.PatchGenerator import generate_patch
from module.Extract.UnifiedExtractor import UnifiedExtractor
from module.Renpy import renpy_extract as rx
from module.Renpy.ProjectPaths import (
    RenpyProjectPaths,
    apply_to_config,
    source_script_counts,
    write_run_manifest,
)
from module.Engine.Translator.ProjectAssetsRepository import ProjectAssetsRepository
from module.Engine.Engine import Engine
from module.Cache.CacheManager import CacheManager
from module.Config import Config
from module.Localizer.Localizer import Localizer
from module.Renpy.renpy_tl_core import parse_tl_document, tl_block_kind_name
from module.Renpy.renpy_tl_io import RenpyTlItemExtractor
from module.Workbench.CharacterScanner import CharacterCandidate, CharacterScanner
from frontend.RenpyToolbox.PackUnpackPage import DecompileWorker, UnpackWorker
from frontend.TranslationPage import TranslationPage




def configure_tl_translation_mode(config):
    """一键翻译固定读取 Ren'Py TL 文件，清除其它页面遗留的运行模式。"""
    config.renpy_source_translate = False
    config.renpy_hook_translate = False


def configure_main_translation_paths(config, game_dir, tl_name, *, remember_run = True):
    """将翻译输入和输出恢复到主语言目录。"""
    paths = RenpyProjectPaths.from_path(game_dir, tl_name)
    if paths is None:
        raise ValueError("无法解析 Ren'Py 项目路径")
    apply_to_config(config, paths)
    configure_tl_translation_mode(config)
    if remember_run:
        _remember_translation_run(
            paths,
            output_folder = paths.translation_output_dir,
            input_folder = paths.tl_language_dir,
            run_kind = "translation",
        )
    return paths.tl_language_dir, paths.translation_output_dir


def configure_incremental_translation_paths(config, game_dir, tl_name, incremental_dir):
    """将翻译指向增量目录，同时保留主 TL 合并目标。"""
    paths = RenpyProjectPaths.from_path(game_dir, tl_name)
    if paths is None:
        raise ValueError("无法解析 Ren'Py 项目路径")
    delta_dir = Path(incremental_dir)
    output_dir = paths.translation_output_dir.parent / f"{paths.language}_new"
    apply_to_config(config, paths, input_folder = delta_dir, output_folder = output_dir)
    configure_tl_translation_mode(config)
    _remember_translation_run(
        paths,
        output_folder = output_dir,
        input_folder = delta_dir,
        application_target_dir = paths.application_target_dir,
        run_kind = "incremental",
    )
    return paths.tl_language_dir, output_dir


def preserve_incremental_translation_cache(
    output_dir: Path,
    *,
    stamp: str | None = None,
) -> Path | None:
    """在重新抽取前保留已有增量缓存，返回可恢复的备份目录。

    ``<lang>_new`` 是一键流程的固定运行目录。重新抽取必须从空目录开始，
    但不能直接删除用户尚未应用的译文；将旧目录移动到同一父目录下的时间戳
    备份，既保持路径统一，也让用户可以手动恢复或取回旧进度。
    """
    output_dir = Path(output_dir)
    if not output_dir.exists():
        return None

    # 只允许在原输出目录的父目录中创建备份，避免配置异常时移动到项目外。
    parent = output_dir.parent.resolve()
    resolved_output = output_dir.resolve()
    if resolved_output.parent != parent:
        raise ValueError("增量缓存备份路径不在原输出目录父级内")

    if stamp is None:
        stamp = time.strftime("%Y%m%d-%H%M%S")
    stamp = "".join(char for char in str(stamp) if char.isalnum() or char in "-_")
    if not stamp:
        stamp = "backup"

    candidate = parent / f"{output_dir.name}.backup-{stamp}"
    suffix = 1
    while candidate.exists():
        candidate = parent / f"{output_dir.name}.backup-{stamp}-{suffix}"
        suffix += 1

    # move 是可恢复操作；即使目录只有部分文件，也不能用 rmtree 静默丢弃。
    shutil.move(str(output_dir), str(candidate))
    return candidate


def _remember_translation_run(
    paths,
    *,
    output_folder,
    input_folder = None,
    application_target_dir = None,
    run_kind = "translation",
):
    """写入最近运行清单；清单失败不应阻断翻译主流程。"""
    try:
        return write_run_manifest(
            paths,
            output_folder,
            input_folder = input_folder,
            application_target_dir = application_target_dir,
            run_kind = run_kind,
        )
    except Exception:
        return None


def _renpy_cache_metadata(item) -> tuple[dict, dict, dict]:
    extra = item.get_extra_field()
    renpy = extra.get("renpy", {}) if isinstance(extra, dict) else {}
    block = renpy.get("block", {}) if isinstance(renpy.get("block"), dict) else {}
    pair = renpy.get("pair", {}) if isinstance(renpy.get("pair"), dict) else {}
    digest = renpy.get("digest", {}) if isinstance(renpy.get("digest"), dict) else {}
    return block, pair, digest


def _cache_item_identity(item) -> tuple:
    """优先使用不受文件整体行号漂移影响的 Ren'Py AST 身份。"""
    block, pair, digest = _renpy_cache_metadata(item)
    template_digest = digest.get("template_raw_sha1")
    lang = block.get("lang")
    label = block.get("label")
    header_line = block.get("header_line")
    template_line = pair.get("template_line")
    statement_ordinal = pair.get("statement_ordinal")
    if (
        tl_block_kind_name(block.get("kind")) == "STRINGS"
        and isinstance(lang, str)
        and lang
        and str(item.get_src() or "")
    ):
        # Ren'Py old/new 以原文全局注册，文件路径和块内偏移不是身份的一部分。
        return ("renpy-strings", lang, str(item.get_src()))
    if (
        all(isinstance(value, str) and value for value in (lang, label, template_digest))
        and isinstance(header_line, int)
        and isinstance(template_line, int)
    ):
        if not isinstance(statement_ordinal, int):
            statement_ordinal = template_line - header_line
        return (
            "renpy-ast",
            str(item.get_file_path() or ""),
            lang,
            label,
            template_digest,
            statement_ordinal,
            str(item.get_tag() or ""),
        )
    return (
        "legacy",
        str(item.get_file_path() or ""),
        int(item.get_row() or 0),
        str(item.get_src() or ""),
        str(item.get_tag() or ""),
    )


def _cache_item_source_location(item) -> tuple | None:
    """返回编号翻译块中的稳定槽位；全局 strings 不做位置淘汰。"""
    block, pair, _digest = _renpy_cache_metadata(item)
    # 同一文件可包含多个 label 都为 ``strings`` 的块，且它们的块内偏移
    # 可能完全相同。没有稳定的块实例身份时按位置淘汰会误删另一个块。
    if tl_block_kind_name(block.get("kind")) != "LABEL":
        return None
    header_line = block.get("header_line")
    template_line = pair.get("template_line")
    lang = block.get("lang")
    label = block.get("label")
    if not (
        isinstance(header_line, int)
        and isinstance(template_line, int)
        and isinstance(lang, str)
        and isinstance(label, str)
    ):
        return None
    return (
        str(item.get_file_path() or ""),
        lang,
        label,
        template_line - header_line,
        str(item.get_tag() or ""),
    )


def _cache_item_label_block_identity(item) -> tuple | None:
    """返回可由增量完整快照安全替换的编号翻译块身份。"""
    block, _pair, _digest = _renpy_cache_metadata(item)
    if tl_block_kind_name(block.get("kind")) != "LABEL":
        return None
    lang = block.get("lang")
    label = block.get("label")
    if not (
        isinstance(lang, str)
        and lang
        and isinstance(label, str)
        and label
    ):
        return None
    return (str(item.get_file_path() or ""), lang, label)


def _numbered_disk_identity(item) -> tuple | None:
    """匹配缓存与磁盘中的同一编号语句，不依赖运行期 tag。"""
    block, pair, digest = _renpy_cache_metadata(item)
    if tl_block_kind_name(block.get("kind")) != "LABEL":
        return None
    header_line = block.get("header_line")
    template_line = pair.get("template_line")
    statement_ordinal = pair.get("statement_ordinal")
    template_digest = digest.get("template_raw_sha1")
    lang = block.get("lang")
    label = block.get("label")
    if not (
        isinstance(header_line, int)
        and isinstance(template_line, int)
        and isinstance(template_digest, str)
        and template_digest
        and isinstance(lang, str)
        and isinstance(label, str)
    ):
        return None
    if not isinstance(statement_ordinal, int):
        statement_ordinal = template_line - header_line
    return (
        str(item.get_file_path() or ""),
        lang,
        label,
        template_digest,
        statement_ordinal,
        str(item.get_src() or ""),
    )


def _is_strings_cache_item(item) -> bool:
    block, _pair, _digest = _renpy_cache_metadata(item)
    return tl_block_kind_name(block.get("kind")) == "STRINGS"


def _merge_strings_cache_translation(existing, incoming):
    """把全局 strings 译文迁入主条目的真实文件位置。"""
    existing_dst = str(existing.get_dst() or "")
    existing_translated = bool(existing_dst and existing_dst != existing.get_src())
    if existing_translated:
        return existing

    data = existing.asdict()
    incoming_data = incoming.asdict()
    for field in ("dst", "name_dst", "status", "retry_count", "metadata"):
        data[field] = incoming_data[field]
    return type(existing).from_dict(data)


def _merge_numbered_cache_translation(existing, incoming):
    """把磁盘最终结果中的有效编号译文迁入增量缓存条目。"""
    data = incoming.asdict()
    existing_dst = existing.get_dst()
    if isinstance(existing_dst, str) and existing_dst and existing_dst != existing.get_src():
        existing_data = existing.asdict()
        for field in ("dst", "status", "retry_count", "metadata"):
            data[field] = existing_data[field]

    existing_name_dst = existing.get_name_dst()
    if existing_name_dst and existing_name_dst != existing.get_name_src():
        data["name_dst"] = existing_name_dst
    return type(incoming).from_dict(data)


def _load_numbered_disk_translations(output_dir: Path) -> dict[tuple, object]:
    """读取磁盘合并后的编号块；其内容是本轮应用结果的最终依据。"""
    translations: dict[tuple, object] = {}
    extractor = RenpyTlItemExtractor()
    for rpy_file in Path(output_dir).rglob("*.rpy"):
        try:
            rel_path = rpy_file.relative_to(output_dir).as_posix()
            doc = parse_tl_document(
                rpy_file.read_text(encoding="utf-8", errors="replace").splitlines()
            )
            for item in extractor.extract(doc, rel_path):
                if _cache_item_label_block_identity(item) is None:
                    continue
                dst = item.get_dst()
                if isinstance(dst, str) and dst and dst != item.get_src():
                    identity = _numbered_disk_identity(item)
                    if identity is not None:
                        translations[identity] = item
        except Exception:
            continue
    return translations


def _project_assets_have_state(payload) -> bool:
    """判断缓存中的工作台资产是否包含可用数据。"""
    if not isinstance(payload, dict):
        return False
    try:
        revision = int(payload.get("revision", 0) or 0)
    except (TypeError, ValueError):
        revision = 0
    if revision > 0 or str(payload.get("updated_at", "") or "").strip():
        return True
    for section_name, value_name in (
        ("worldbook", "data"),
        ("character_cards", "items"),
        ("glossary", "items"),
        ("do_not_translate", "items"),
    ):
        section = payload.get(section_name)
        if not isinstance(section, dict):
            continue
        if bool(section.get("enabled")) or section.get(value_name):
            return True
    return False


def merge_incremental_translation_cache(
    incremental_output: Path,
    main_output: Path,
) -> bool:
    """把增量输出缓存合并进主缓存，避免应用翻译时丢失新条目。"""
    incremental_manager = CacheManager(service = False)
    try:
        incremental_manager.load_from_file(str(incremental_output), strict = True)
    except Exception:
        # 增量目录可能只有 rpy 文件而没有缓存；这种情况不需要迁移。
        return False

    main_manager = CacheManager(service = False)
    main_loaded = False
    try:
        main_manager.load_from_file(str(main_output), strict = True)
        main_loaded = True
    except Exception:
        pass

    merged: dict[tuple, object] = {}
    order: list[tuple] = []
    main_locations: dict[tuple, tuple] = {}
    disk_numbered_items = _load_numbered_disk_translations(main_output)
    incremental_items = incremental_manager.get_items()
    replaced_label_blocks = {
        block_identity
        for item in incremental_items
        if (block_identity := _cache_item_label_block_identity(item)) is not None
    }
    if main_loaded:
        for item in main_manager.get_items():
            key = _cache_item_identity(item)
            # 变更编号块的增量缓存是完整块快照。先清除该块的全部旧条目，
            # 才能同步其中被删除的语句；全局 strings 不参与整块淘汰。
            if _cache_item_label_block_identity(item) in replaced_label_blocks:
                continue
            if key not in merged:
                order.append(key)
                merged[key] = item
            elif _is_strings_cache_item(item):
                merged[key] = _merge_strings_cache_translation(merged[key], item)
            else:
                merged[key] = item
            location = _cache_item_source_location(item)
            if location is not None:
                main_locations[location] = key
    for item in incremental_items:
        key = _cache_item_identity(item)
        if _cache_item_label_block_identity(item) is not None:
            disk_item = disk_numbered_items.get(_numbered_disk_identity(item))
            if disk_item is not None:
                item = _merge_numbered_cache_translation(disk_item, item)
        if key in merged and _is_strings_cache_item(item):
            # 跨文件 old/new 共用全局身份，但主缓存条目的路径对应磁盘合并后的
            # 实际目标；只迁移译文状态，不能保留即将删除的 staging 路径。
            merged[key] = _merge_strings_cache_translation(merged[key], item)
            continue
        location = _cache_item_source_location(item)
        stale_key = main_locations.get(location) if location is not None else None
        if stale_key is not None and stale_key != key and stale_key in merged:
            # 同一 AST 槽的原文/模板已变化：用增量条目整体替换，绝不沿用旧译文。
            merged.pop(stale_key)
            if key in order:
                order.remove(stale_key)
            else:
                try:
                    order[order.index(stale_key)] = key
                except ValueError:
                    order.append(key)
        if key not in merged:
            if key not in order:
                order.append(key)
        # 增量任务的状态/译文是本轮刚生成的，覆盖同键旧占位条目。
        merged[key] = item

    items = list(merged[key] for key in order)
    project = incremental_manager.get_project()
    if main_loaded:
        # 工作台资产属于项目级数据。增量运行可能在主工作台更新前启动，
        # 因而不能只根据“是否存在”覆盖主缓存；始终按 revision 保留较新快照。
        try:
            incremental_assets = project.get_project_assets()
            main_assets = main_manager.get_project().get_project_assets()
            try:
                incremental_revision = int(incremental_assets.get("revision", 0) or 0)
            except (TypeError, ValueError):
                incremental_revision = 0
            try:
                main_revision = int(main_assets.get("revision", 0) or 0)
            except (TypeError, ValueError):
                main_revision = 0
            # 旧缓存可能没有 revision：只要主缓存有资产而增量没有，
            # 或两者 revision 相同，就应优先保留稳定主工作台快照。
            if _project_assets_have_state(main_assets) and (
                not _project_assets_have_state(incremental_assets)
                or main_revision >= incremental_revision
            ):
                project.set_project_assets(main_assets)

            # 分析候选没有独立 revision，空快照时仍从主缓存补齐。
            if not project.get_analysis_candidates().get("items"):
                project.set_analysis_candidates(main_manager.get_project().get_analysis_candidates())
        except Exception:
            # 资产迁移是辅助步骤，异常不能阻断翻译缓存合并。
            pass

    saver = CacheManager(service = False)
    if not saver.save_to_file(project, items, str(main_output), strict = False):
        # 坏 SQLite 不应阻止把有效增量缓存落到 JSON；当前实例切换后端，
        # JSON 成功写入后必须移除旧数据库，否则后续新实例仍会优先读取
        # 可读但未合并的 SQLite，并在增量目录删除后丢失本轮条目。
        try:
            saver._mark_json_fallback(str(main_output))
            if not saver.save_to_file(
                project, items, str(main_output), strict = True
            ):
                return False
            stale_db = Path(saver._get_db_path(str(main_output)))
            stale_db.unlink(missing_ok = True)
            if stale_db.exists():
                return False
        except Exception:
            return False
    return True


def resolve_translation_apply_paths(config, incremental_output=None, incremental_target=None):
    """仅在增量输出有效时使用增量目标，避免复用页面时串用旧目录。"""
    if incremental_output:
        if not incremental_target:
            return Path(incremental_output), None
        return Path(incremental_output), Path(incremental_target)
    return Path(config.output_folder), Path(config.input_folder)


def apply_translation_files_transactionally(
    output_files: list[Path],
    output_dir: Path,
    input_dir: Path,
) -> int:
    """应用整批翻译文件；任一文件失败时恢复此前所有目标。"""
    # 相对目标必须按输出目录中的词法路径计算，不能先解引用源符号链接。
    output_dir = Path(os.path.abspath(os.fspath(output_dir)))
    input_dir = Path(input_dir).resolve()
    input_dir.parent.mkdir(parents=True, exist_ok=True)
    backup_root = Path(
        tempfile.mkdtemp(prefix=".renpybox-apply-", dir=str(input_dir.parent))
    )
    input_dir_resolved = input_dir.resolve()
    # 允许 tl 目录内部及游戏目录内的符号链接目标，但禁止写回项目之外。
    allowed_roots = (
        input_dir_resolved,
        input_dir_resolved.parent,
        input_dir_resolved.parent.parent,
    )
    applied: list[tuple[Path, Path | None]] = []
    temp_targets: list[Path] = []
    rollback_failed = False
    try:
        for index, source in enumerate(output_files):
            lexical_source = Path(os.path.abspath(os.fspath(source)))
            rel_path = lexical_source.relative_to(output_dir)
            if rel_path.is_absolute() or ".." in rel_path.parts:
                raise ValueError(f"输出文件越过翻译目录: {lexical_source}")
            source = lexical_source.resolve(strict=True)
            if not source.is_file():
                raise ValueError(f"输出翻译源不是文件: {lexical_source}")
            target = input_dir / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)

            # os.replace 会替换符号链接本身，而不是写入其指向文件。
            # 对链接的真实目标执行整套事务，才能同时保留链接和回滚能力。
            if target.is_symlink():
                try:
                    unresolved_target = target.resolve(strict=False)
                    write_target = (
                        unresolved_target.parent.resolve(strict=True)
                        / unresolved_target.name
                    )
                except (OSError, RuntimeError) as exc:
                    raise RuntimeError(
                        f"无法解析翻译目标符号链接: {target}: {exc}"
                    ) from exc
                if write_target.exists() and not write_target.is_file():
                    raise RuntimeError(f"翻译目标符号链接未指向文件: {target}")
            else:
                write_target = target

            # 防止翻译目录内被植入指向项目外的符号链接，导致写回覆盖外部文件。
            resolved_write_target = write_target.resolve(strict=False)
            if not any(
                resolved_write_target == root
                or root in resolved_write_target.parents
                for root in allowed_roots
            ):
                raise RuntimeError(
                    f"翻译目标符号链接指向翻译目录之外: {target} -> {write_target}"
                )

            backup: Path | None = None
            if write_target.exists():
                backup = backup_root / rel_path
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(write_target, backup)

            temp_fd, temp_name = tempfile.mkstemp(
                prefix=f".{write_target.name}.apply-{index}-",
                suffix=".tmp",
                dir=str(write_target.parent),
            )
            os.close(temp_fd)
            temp_target = Path(temp_name)
            temp_targets.append(temp_target)
            shutil.copy2(source, temp_target)
            os.replace(str(temp_target), str(write_target))
            temp_targets.remove(temp_target)
            applied.append((write_target, backup))
        return len(applied)
    except Exception as apply_exc:
        rollback_errors: list[str] = []
        for target, backup in reversed(applied):
            try:
                if backup is None:
                    target.unlink(missing_ok=True)
                else:
                    restore_fd, restore_name = tempfile.mkstemp(
                        prefix=f".{target.name}.rollback-",
                        suffix=".tmp",
                        dir=str(target.parent),
                    )
                    os.close(restore_fd)
                    restore_temp = Path(restore_name)
                    try:
                        shutil.copy2(backup, restore_temp)
                        os.replace(str(restore_temp), str(target))
                    finally:
                        restore_temp.unlink(missing_ok=True)
            except Exception as rollback_exc:
                rollback_errors.append(f"{target}: {rollback_exc}")
        rollback_failed = bool(rollback_errors)
        preserved_hint = ""
        if rollback_errors:
            # 回滚失败时原文件唯一副本仍在 backup_root，必须保留而不是删除。
            preserved = backup_root.with_name(
                f"{backup_root.name}-rollback-{int(time.time())}"
            )
            try:
                backup_root.replace(preserved)
                preserved_hint = f"；原始文件备份保留在: {preserved}"
            except Exception:
                preserved_hint = f"；原始文件备份目录: {backup_root}（未能重命名）"
        detail = f"；回滚失败：{'；'.join(rollback_errors)}" if rollback_errors else ""
        raise RuntimeError(
            f"应用翻译失败，已回滚本批次：{apply_exc}{detail}{preserved_hint}"
        ) from apply_exc
    finally:
        for temp_target in temp_targets:
            temp_target.unlink(missing_ok=True)
        if not rollback_failed:
            shutil.rmtree(backup_root, ignore_errors=True)

_EXTRACTOR_PROGRESS_EN = {
    "已备份旧翻译": "Backed up the previous translation...",
    "正在执行官方抽取...": "Running official extraction...",
    "正在执行补充抽取...": "Running supplemental extraction...",
    "正在分析已有翻译...": "Analyzing existing translations...",
    "正在分析已有翻译与增量内容...": "Analyzing existing translations and incremental content...",
    "正在分离新增/待翻译内容...": "Separating new and untranslated content...",
    "正在合并新增内容...": "Merging new content...",
    "正在合并新增翻译...": "Merging incremental translations...",
    "正在回填已有翻译...": "Restoring existing translations...",
    "正在回填编号块译文...": "Restoring numbered-block translations...",
    "合并校验未通过，已保留增量目录": "Merge validation failed; the incremental folder was preserved.",
    "正在清理重复与空文件...": "Cleaning duplicates and empty files...",
    "正在校验跨文件唯一性...": "Validating cross-file uniqueness...",
    "正在按行号整理编号块...": "Sorting numbered blocks by source line...",
    "正在应用保留库过滤...": "Applying protected-text filters...",
    "正在应用术语库填充...": "Applying glossary entries...",
    "正在清理空文件...": "Cleaning empty files...",
    "抽取完成": "Extraction complete.",
    "增量抽取完成": "Incremental extraction complete.",
    "合并完成": "Merge complete.",
}


def _localize_extractor_progress(message: str, fallback: str) -> str:
    text = str(message)
    if text.startswith("正在写入合并文件 "):
        detail = text.removeprefix("正在写入合并文件 ").removesuffix("...")
        return Localizer.localize(text, f"Writing merged file {detail}...")
    return Localizer.localize(text, _EXTRACTOR_PROGRESS_EN.get(text, fallback))


def _localize_extraction_result(result, incremental: bool) -> str:
    message = str(getattr(result, "message", "") or "")
    if Localizer.get_app_language() != BaseLanguage.Enum.EN:
        return message or (
            "增量抽取完成" if incremental else "文本提取完成"
        )
    if result.success:
        if incremental:
            incremental_dir = getattr(result, "incremental_dir", None)
            if incremental_dir is not None:
                return f"Incremental extraction completed. New content is in {incremental_dir.name}/."
            preserved = getattr(result, "preserved_count", 0)
            return f"Incremental extraction completed. Preserved {preserved} existing translation(s)."
        total = getattr(result, "total_files", 0)
        return f"Text extraction completed ({total} file(s))."
    if "已被禁用" in message:
        return "Extraction is disabled. Enable official or supplemental extraction and try again."
    if "已自动恢复原翻译目录" in message:
        return "Text extraction failed. The original translation folder was restored. Check the logs for details."
    if "恢复原翻译失败" in message:
        return "Text extraction failed, and the original translation folder could not be restored. Check the logs and backup folder."
    return "Text extraction failed. Check the logs for details."


def _localize_merge_failure(message: str) -> str:
    text = str(message or "")
    if Localizer.get_app_language() != BaseLanguage.Enum.EN:
        return text or "增量翻译文件合并失败"
    if "已保留增量目录" in text:
        return "The incremental merge did not complete. The incremental folder was preserved. Check the logs for details."
    if text.startswith("未找到增量目录:"):
        return "The incremental translation folder was not found."
    return Localizer.get().onekey_incremental_translation_merge_failed


# Worker Thread for Extraction
class ExtractionWorker(QThread):
    progress = pyqtSignal(str, int) # message, percent
    finished = pyqtSignal(bool, str, object) # success, message, result (ExtractionResult)
    
    def __init__(self, unified_extractor, game_dir, tl_name, exe_path, incremental=False, output_to_separate_folder=True):
        super().__init__()
        self.unified_extractor = unified_extractor
        self.game_dir = game_dir
        self.tl_name = tl_name
        self.exe_path = exe_path
        self.incremental = incremental  # 增量模式：保留已有翻译
        self.output_to_separate_folder = output_to_separate_folder  # 增量输出到单独文件夹
        
    def run(self):
        try:
            # 设置进度回调
            self.unified_extractor.set_progress_callback(
                lambda msg, pct: self.progress.emit(
                    _localize_extractor_progress(
                        msg, Localizer.get().onekey_extracting_text
                    ),
                    pct,
                )
            )
            
            if self.incremental:
                # 增量模式：使用统一提取器的增量抽取
                result = self.unified_extractor.extract_incremental(
                    self.game_dir,
                    self.tl_name,
                    self.exe_path,
                    use_official=bool(self.exe_path),
                    output_to_separate_folder=self.output_to_separate_folder
                )
            else:
                # 常规模式：使用统一提取器的完整抽取
                result = self.unified_extractor.extract_regular(
                    self.game_dir,
                    self.tl_name,
                    self.exe_path,
                    use_official=bool(self.exe_path)
                )
            
            if not result.success and result.message:
                LogManager.get().error(f"文本提取失败: {result.message}")
            self.finished.emit(
                result.success, _localize_extraction_result(result, self.incremental), result
            )
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            LogManager.get().error(f"文本提取失败: {e}")
            self.finished.emit(
                False,
                Localizer.localize(
                    f"文本提取失败：{e}",
                    "Text extraction failed. Check the logs for details.",
                ),
                None,
            )
        finally:
            self.unified_extractor.set_progress_callback(None)


class ApplyTranslationWorker(QThread):
    """后台执行“应用翻译到游戏”，避免大批量文件操作阻塞 UI。

    - incremental 模式：语义合并增量目录 -> 迁移缓存 -> 清理增量目录 -> 恢复主路径；
    - 全量模式：事务性覆盖目标 TL 文件。
    进度通过 progress 信号上报，结果通过 finished 信号回传 UI 线程。
    """

    progress = pyqtSignal(str, int)  # message, percent
    finished = pyqtSignal(bool, str, object)  # success, message, payload

    def __init__(
        self,
        unified_extractor,
        *,
        incremental_mode: bool,
        game_dir=None,
        tl_name: str = "chinese",
        output_dir=None,
        input_dir=None,
        output_files=None,
        main_output=None,
        incremental_dir=None,
        config=None,
        project_root=None,
        project_language=None,
    ):
        super().__init__()
        self.unified_extractor = unified_extractor
        self.incremental_mode = incremental_mode
        self.game_dir = game_dir
        self.tl_name = tl_name
        self.output_dir = Path(output_dir) if output_dir else None
        self.input_dir = Path(input_dir) if input_dir else None
        self.output_files = list(output_files) if output_files else []
        self.main_output = Path(main_output) if main_output else None
        self.incremental_dir = Path(incremental_dir) if incremental_dir else None
        self.config = config
        self.project_root = project_root
        self.project_language = project_language

    def run(self):
        try:
            self.unified_extractor.set_progress_callback(
                lambda msg, pct: self.progress.emit(
                    _localize_extractor_progress(
                        msg, Localizer.get().onekey_applying_translation
                    ),
                    pct,
                )
            )
            if self.incremental_mode:
                self._run_incremental()
            else:
                self._run_full()
        except Exception as exc:
            import traceback
            traceback.print_exc()
            LogManager.get().error(f"应用翻译失败: {exc}")
            self.finished.emit(
                False,
                Localizer.localize(
                    f"应用翻译失败：{exc}",
                    "Failed to apply the translation. Check the logs for details.",
                ),
                None,
            )
        finally:
            self.unified_extractor.set_progress_callback(None)

    def _run_incremental(self):
        merge_result = self.unified_extractor.merge_incremental_folder(
            self.game_dir,
            self.tl_name,
            self.output_dir,
            clean_duplicates=True,
        )
        if not merge_result.success:
            LogManager.get().error(
                f"增量翻译文件合并失败: {merge_result.message}"
            )
            self.finished.emit(
                False,
                _localize_merge_failure(merge_result.message),
                {"warning": True},
            )
            return
        cache_dir = self.output_dir / "cache"
        cache_was_present = cache_dir.is_dir()
        cache_migrated = (
            merge_incremental_translation_cache(self.output_dir, self.main_output)
            if cache_was_present
            else True
        )
        if cache_was_present and not cache_migrated:
            # 合并函数已写回 TL，但缓存迁移失败时保留增量目录，
            # 让校对页仍能载入本轮结果，避免“文件成功、缓存丢失”。
            self.finished.emit(
                False,
                Localizer.get().onekey_translation_files_applied_but_cache_remains_try.format(self_output_dir_cache=self.output_dir / 'cache'),
                {"warning": True},
            )
            return
        self.progress.emit(
            Localizer.get().onekey_cleaning_incremental_folders,
            92,
        )
        if self.output_dir.exists():
            shutil.rmtree(str(self.output_dir), ignore_errors=True)
        if self.incremental_dir and self.incremental_dir.exists():
            shutil.rmtree(str(self.incremental_dir), ignore_errors=True)
        # 应用增量后恢复全局主路径，并把运行清单更新到已经
        # 合并的主缓存；不能继续指向刚删除的 <lang>_new。
        self.progress.emit(
            Localizer.get().onekey_restoring_translation_paths,
            96,
        )
        configure_main_translation_paths(
            self.config,
            self.game_dir,
            self.tl_name,
            remember_run=True,
        )
        self.config.save()
        self.finished.emit(
            True,
            Localizer.get().onekey_incremental_translation_applied,
            {"main_output": str(self.main_output)},
        )

    def _run_full(self):
        success_count = apply_translation_files_transactionally(
            self.output_files,
            self.output_dir,
            self.input_dir,
        )
        # 应用成功后把全局配置恢复为向导项目的主路径，再允许自动
        # hook 接续；这样 hook 扫描到的是真实的最新 TL。
        self.progress.emit(
            Localizer.get().onekey_restoring_translation_paths,
            96,
        )
        if self.project_root and self.project_language:
            configure_main_translation_paths(
                self.config,
                self.project_root,
                self.project_language,
                remember_run=False,
            )
            self.config.save()
        self.finished.emit(
            True,
            Localizer.get().onekey_applied_translation_files_game_folder_you_can.format(success_count=success_count),
            {"count": success_count},
        )


class YiJianFanyiPage(Base, QWidget):
    """一键翻译页面 - 向导式分步骤流程"""
    
    def __init__(self, object_name: str = "yi-jian-fanyi", parent=None):
        Base.__init__(self)
        QWidget.__init__(self, parent)
        self.setObjectName(object_name)
        mark_toolbox_widget(self)
        
        self.window = parent
        self.game_path = ""
        self.game_dir = ""
        self.renpy_version = ""
        self.current_step = 1
        self.unified_extractor = UnifiedExtractor()
        self.extraction_worker = None
        self._extraction_generation = 0
        self._preprocess_worker = None
        self.has_old_translation = False  # 是否检测到旧翻译
        self.incremental_mode = False     # 是否使用增量抽取
        self._ner_model = None            # 懒加载的 NER 模型
        self._ner_model_loaded = False
        # 一键翻译结束后，按需串起“自动补全漏翻”流程
        self._onekey_translation_started = False
        self._onekey_translation_completed = False
        self._onekey_request_id = ""
        self._onekey_run_id = None
        self._auto_hook_pending = False
        self._auto_hook_running = False
        self._incremental_dir = None
        self._incremental_output_dir = None
        self._apply_target_dir = None
        self._last_onekey_output_dir = None
        self._apply_running = False  # 防止“应用翻译到游戏”重入
        self._apply_worker = None
        self._apply_card = None
        self._apply_parent = None
        self._apply_project_paths = None
        self._apply_progress_dialog = None
        self._start_translation_after_extraction = False
        self._agent_direct_start = False
        # 自动 hook 临时把配置指向 game/tl；完成后恢复主输出，但保留
        # 最近运行清单指向 hook 缓存，供校对页继续载入。
        self._hook_restore_paths = None
        
        self._init_ui()
        self.subscribe(Base.Event.TRANSLATION_DONE, self._on_translation_done)
        self.subscribe(Base.Event.TRANSLATION_STOP, self._on_translation_stop)
        self.subscribe(
            Base.Event.TRANSLATION_START_RESULT,
            self._on_translation_start_result,
        )
    
    def _init_ui(self):
        """初始化界面"""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setSpacing(0)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        
        # 使用 QStackedWidget 切换不同进度页面
        self.stacked = QStackedWidget()
        self.main_layout.addWidget(self.stacked)
        
        # 创建各个进度页面
        self._create_step1_page()  # 前期设置
        self._create_step2_page()  # 提取进度
        self._create_step3_page()  # 术语表
        self._create_step4_page()  # 开始翻译
        self._create_step5_page()  # 后续处理
        
        # 显示第一步
        self.stacked.setCurrentIndex(0)
    
    def _create_page_container(self, title: str, step: int) -> tuple:
        """创建页面容器，返回 (page, content_layout)"""
        page = QWidget()
        mark_toolbox_widget(page)
        page_layout = QVBoxLayout(page)
        page_layout.setSpacing(12)
        page_layout.setContentsMargins(24, 24, 24, 24)
        
        # 顶部：标题 + 退出按钮
        header = QWidget()
        header.setStyleSheet("background: transparent;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        # 返回按钮
        back_btn = TransparentToolButton(FluentIcon.RETURN)
        if step == 1:
            back_btn.setToolTip(Localizer.get().onekey_back_toolbox)
            back_btn.clicked.connect(self._exit_wizard)
        else:
            back_btn.setToolTip(Localizer.get().onekey_previous_step)
            # 使用 lambda 捕获当前 step 值
            back_btn.clicked.connect(lambda checked, s=step: self._go_previous_step(s))
        header_layout.addWidget(back_btn)
        
        title_label = TitleLabel(
            Localizer.get().onekey_step_5.format(step=step, title=title)
        )
        header_layout.addWidget(title_label)
        header_layout.addStretch(1)
        
        if step > 1:
            exit_btn = PushButton(Localizer.get().onekey_exit_wizard)
            exit_btn.clicked.connect(self._exit_wizard)
            header_layout.addWidget(exit_btn)
        
        page_layout.addWidget(header)
        
        # 分割线
        page_layout.addWidget(Separator(page))
        
        # 内容区域（滚动容器，避免非全屏时控件挤压重叠）
        content_scroll = SingleDirectionScrollArea(orient=Qt.Orientation.Vertical)
        content_scroll.setWidgetResizable(True)
        content_scroll.enableTransparentBackground()
        mark_toolbox_scroll_area(content_scroll)

        content = QWidget()
        mark_toolbox_widget(content, "toolboxScroll")
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(16)
        content_scroll.setWidget(content)
        page_layout.addWidget(content_scroll, 1)
        
        # 底部：进度条
        page_layout.addWidget(Separator(page))
        
        bottom = QWidget()
        bottom.setStyleSheet("background: transparent;")
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(0, 8, 0, 0)
        bottom_layout.setSpacing(4)
        
        status_row = QWidget()
        status_row.setStyleSheet("background: transparent;")
        status_layout = QHBoxLayout(status_row)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(8)
        
        # 进度环
        progress_ring = ProgressRing()
        progress_ring.setFixedSize(20, 20)
        progress_ring.setVisible(False)
        status_layout.addWidget(progress_ring)
        
        # 状态文本
        status_label = CaptionLabel("")
        status_layout.addWidget(status_label)
        status_layout.addStretch(1)
        
        bottom_layout.addWidget(status_row)
        
        # 进度条
        progress_bar = ProgressBar()
        progress_bar.setValue(int((step - 1) / 5 * 100))
        bottom_layout.addWidget(progress_bar)
        
        page_layout.addWidget(bottom)
        
        # 保存引用
        page.progress_ring = progress_ring
        page.status_label = status_label
        page.progress_bar = progress_bar
        page.content_scroll = content_scroll

        return page, content_layout
    
    # ==================== 进度一：前期设置 ====================
    def _create_step1_page(self):
        """进度一：前期设置 - 简洁友好的小白UI"""
        page, layout = self._create_page_container(
            Localizer.get().onekey_select_game,
            1,
        )
        
        # 提示文字 - 更友好的说明
        tip_card = CardWidget()
        tip_layout = QVBoxLayout(tip_card)
        tip_layout.setContentsMargins(12, 12, 12, 12)
        tip_layout.setSpacing(6)
        
        tip_title = StrongBodyLabel(
            Localizer.get().onekey_quick_start
        )
        tip_layout.addWidget(tip_title)
        
        tip_text = CaptionLabel(
            Localizer.get().onekey_1_select_game_folder_contains_game_subfolder
        )
        tip_text.setStyleSheet("color: #666; line-height: 1.5;")
        tip_text.setWordWrap(True)
        tip_layout.addWidget(tip_text)
        layout.addWidget(tip_card)
        
        # 游戏路径输入框（支持直接粘贴）
        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        
        self.game_path_edit = LineEdit()
        self.game_path_edit.setPlaceholderText(
            Localizer.get().onekey_enter_paste_game_folder_path_example_d
        )
        self.game_path_edit.textChanged.connect(self._on_path_text_changed)
        path_row.addWidget(self.game_path_edit, 1)
        
        self.browse_btn = PushButton(Localizer.get().onekey_browse)
        self.browse_btn.clicked.connect(self._select_game_dir)
        path_row.addWidget(self.browse_btn)
        
        layout.addLayout(path_row)
        
        # 状态提示
        self.path_status_label = CaptionLabel("")
        layout.addWidget(self.path_status_label)
        
        # 旧翻译检测提示卡片（默认隐藏）
        self.old_translation_card = CardWidget()
        self.old_translation_card.setVisible(False)
        self.old_translation_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        old_trans_layout = QVBoxLayout(self.old_translation_card)
        old_trans_layout.setContentsMargins(12, 12, 12, 12)
        old_trans_layout.setSpacing(8)
        
        self.old_trans_title = StrongBodyLabel(
            Localizer.get().onekey_existing_translation_detected
        )
        old_trans_layout.addWidget(self.old_trans_title)
        
        self.old_trans_desc = CaptionLabel(
            Localizer.get().onekey_game_already_has_translation_files_choose_how
        )
        self.old_trans_desc.setWordWrap(True)
        old_trans_layout.addWidget(self.old_trans_desc)

        # 选项文本采用“短标题 + 说明”两行布局，避免窗口较窄时勾选框文本重叠
        self.incremental_rb = CheckBox(
            Localizer.get().onekey_incremental_extraction_recommended
        )
        self.incremental_rb.setChecked(True)
        old_trans_layout.addWidget(self.incremental_rb)
        incremental_desc = CaptionLabel(
            Localizer.get().onekey_keep_existing_translations_extract_new_untranslated_entries
        )
        incremental_desc.setWordWrap(True)
        incremental_desc.setStyleSheet("padding-left: 28px; color: #666;")
        old_trans_layout.addWidget(incremental_desc)

        self.full_extract_rb = CheckBox(
            Localizer.get().onekey_full_extraction_start_over
        )
        self.full_extract_rb.setChecked(False)
        self.full_extract_rb.setToolTip(
            Localizer.get().onekey_backs_up_regenerates_tl_lang_existing_placeholders
        )
        old_trans_layout.addWidget(self.full_extract_rb)
        full_extract_desc = CaptionLabel(
            Localizer.get().onekey_back_up_old_translation_extract_everything_again
        )
        full_extract_desc.setWordWrap(True)
        full_extract_desc.setStyleSheet("padding-left: 28px; color: #666;")
        old_trans_layout.addWidget(full_extract_desc)
        
        tip_label = CaptionLabel(
            Localizer.get().onekey_tip_incremental_extraction_protects_existing_translations_use
        )
        tip_label.setWordWrap(True)
        old_trans_layout.addWidget(tip_label)

        self.auto_merge_cleanup_chk = CheckBox(
            Localizer.get().onekey_merge_automatically_remove_duplicates_after_extraction
        )
        try:
            from module.Config import Config
            auto_merge_enabled = getattr(Config().load(), "renpy_incremental_auto_merge_cleanup", True)
        except Exception:
            auto_merge_enabled = False
        self.auto_merge_cleanup_chk.setChecked(auto_merge_enabled)
        self.auto_merge_cleanup_chk.stateChanged.connect(self._on_auto_merge_cleanup_changed)
        old_trans_layout.addWidget(self.auto_merge_cleanup_chk)
        
        # 互斥逻辑
        self.incremental_rb.stateChanged.connect(lambda state: self.full_extract_rb.setChecked(not state) if state else None)
        self.full_extract_rb.stateChanged.connect(lambda state: self.incremental_rb.setChecked(not state) if state else None)
        
        layout.addWidget(self.old_translation_card)

        # 高级选项
        options_card = CardWidget()
        options_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        options_layout = QVBoxLayout(options_card)
        options_layout.setContentsMargins(12, 12, 12, 12)
        options_layout.setSpacing(6)

        options_title = StrongBodyLabel(
            Localizer.get().onekey_advanced_options
        )
        options_layout.addWidget(options_title)

        from module.Config import Config
        config = Config().load()

        self.inject_base_box_chk = CheckBox(
            Localizer.get().onekey_inject_ui_translation_pack_base_box
        )
        self.inject_base_box_chk.setChecked(getattr(config, "onekey_inject_base_box", False))
        self.inject_base_box_chk.setToolTip(
            Localizer.get().onekey_injects_bundled_ui_translations_start_save_settings
        )
        self.inject_base_box_chk.stateChanged.connect(self._on_inject_base_box_changed)
        options_layout.addWidget(self.inject_base_box_chk)

        self.extract_compiled_chk = CheckBox(
            Localizer.get().onekey_extract_translate_hidden_built_text_creates_renpybox
        )
        self.extract_compiled_chk.setChecked(getattr(config, "extract_use_compiled", True))
        self.extract_compiled_chk.setToolTip(
            Localizer.get().onekey_some_player_visible_text_embedded_compiled_files
        )
        self.extract_compiled_chk.stateChanged.connect(self._on_extract_compiled_changed)
        options_layout.addWidget(self.extract_compiled_chk)

        self.verify_uppercase_chk = CheckBox(
            Localizer.get().onekey_review_untranslated_uppercase_abbreviations_uses_additional_quota
        )
        self.verify_uppercase_chk.setChecked(
            getattr(config, "renpy_verify_uppercase_candidates", True)
        )
        self.verify_uppercase_chk.stateChanged.connect(
            self._on_verify_uppercase_changed
        )
        options_layout.addWidget(self.verify_uppercase_chk)

        self.clear_declined_btn = PushButton(
            Localizer.get().onekey_clear_skipped_candidates,
            icon=FluentIcon.DELETE,
        )
        self.clear_declined_btn.clicked.connect(self._clear_declined_candidates)
        options_layout.addWidget(self.clear_declined_btn)

        layout.addWidget(options_card)

        layout.addSpacing(20)        # 语言设置（简化）
        layout.addWidget(
            SubtitleLabel(
                Localizer.get().onekey_translation_languages
            )
        )
        
        lang_row = QHBoxLayout()
        lang_row.setSpacing(20)
        
        # 源语言
        src_layout = QVBoxLayout()
        src_layout.setSpacing(4)
        src_layout.addWidget(
            CaptionLabel(Localizer.get().onekey_source_language)
        )
        self.src_lang_combo = ComboBox()
        self.src_lang_combo.addItems(
            [
                Localizer.get().direct_rpy_english,
                Localizer.get().direct_rpy_japanese,
                Localizer.get().direct_rpy_korean,
                Localizer.get().onekey_russian,
                Localizer.get().onekey_other,
            ]
        )
        self.src_lang_combo.setFixedWidth(150)
        src_layout.addWidget(self.src_lang_combo)
        lang_row.addLayout(src_layout)
        
        # 目标语言
        tgt_layout = QVBoxLayout()
        tgt_layout.setSpacing(4)
        tgt_layout.addWidget(
            CaptionLabel(Localizer.get().onekey_target_language)
        )
        self.tgt_lang_combo = ComboBox()
        self.tgt_lang_combo.addItems(
            [
                Localizer.get().direct_rpy_simplified_chinese,
                Localizer.get().direct_rpy_traditional_chinese,
                Localizer.get().direct_rpy_japanese,
                Localizer.get().direct_rpy_english,
            ]
        )
        self.tgt_lang_combo.setFixedWidth(150)
        tgt_layout.addWidget(self.tgt_lang_combo)
        lang_row.addLayout(tgt_layout)
        
        # TL 文件夹名（折叠/隐藏给高级用户）
        tl_layout = QVBoxLayout()
        tl_layout.setSpacing(4)
        tl_layout.addWidget(
            CaptionLabel(Localizer.get().onekey_tl_folder_name)
        )
        self.tl_folder_edit = LineEdit()
        self.tl_folder_edit.setText("chinese")
        self.tl_folder_edit.setFixedWidth(120)
        self.tl_folder_edit.textChanged.connect(self._on_tl_name_changed)
        tl_layout.addWidget(self.tl_folder_edit)
        lang_row.addLayout(tl_layout)
        
        lang_row.addStretch(1)
        layout.addLayout(lang_row)
        
        layout.addStretch(1)

        # 下一步按钮
        next_row = QHBoxLayout()
        next_row.addStretch(1)
        
        # 轻量说明：一步到位
        self.quick_tip_label = CaptionLabel(
            Localizer.get().onekey_click_extract_text_begin_existing_translations_preserved
        )
        self.quick_tip_label.setWordWrap(True)
        layout.addWidget(self.quick_tip_label)
        
        # 跳过抽取按钮（已有翻译时显示）
        self.skip_extract_btn = PushButton(
            Localizer.get().onekey_skip_extraction_translate
        )
        self.skip_extract_btn.clicked.connect(self._skip_to_translate)
        self.skip_extract_btn.setVisible(False)  # 默认隐藏，检测到翻译后显示
        next_row.addWidget(self.skip_extract_btn)
        
        self.step1_next_btn = PrimaryPushButton(
            Localizer.get().onekey_extract_text
        )
        self.step1_next_btn.clicked.connect(self._go_step2)
        self.step1_next_btn.setEnabled(False)
        next_row.addWidget(self.step1_next_btn)
        layout.addLayout(next_row)
        
        self.step1_page = page
        self.stacked.addWidget(page)
    
    def _skip_to_translate(self):
        """跳过抽取，直接进入翻译步骤"""
        # 直接跳到步骤4（翻译）
        self.current_step = 4
        self.stacked.setCurrentIndex(3)
        self._refresh_step4_ready()
        self.step4_page.progress_bar.setValue(60)  # 60% 进度
    
    def _on_path_text_changed(self, text):
        """路径输入框文本变化时验证"""
        text = text.strip()
        if not text:
            self.path_status_label.setText("")
            self.step1_next_btn.setEnabled(False)
            self.old_translation_card.setVisible(False)
            self.has_old_translation = False
            return
        
        selected_paths = RenpyProjectPaths.from_path(
            text,
            self.tl_folder_edit.text().strip() if hasattr(self, "tl_folder_edit") else "chinese",
        )
        if os.path.isdir(text):
            # 检查是否是有效的 Ren'Py 游戏目录
            game_subdir = str(selected_paths.game_dir) if selected_paths else os.path.join(text, "game")
            if os.path.isdir(game_subdir):
                self.game_dir = str(selected_paths.project_root if selected_paths else Path(text))
                self.game_path = self.game_dir
                self._sync_game_dir_to_config(self.game_dir)
                self.path_status_label.setText(
                    Localizer.get().onekey_valid_ren_py_game_folder_detected
                )
                self.path_status_label.setStyleSheet("color: #27ae60;")
                self.step1_next_btn.setEnabled(True)
                # 检测旧翻译
                self._check_old_translation(self.game_dir)
            else:
                self.path_status_label.setText(
                    Localizer.get().onekey_no_game_subfolder_found_may_not_ren
                )
                self.path_status_label.setStyleSheet("color: #e67e22;")
                # 仍然允许继续
                self.game_dir = str(selected_paths.project_root if selected_paths else Path(text))
                self.game_path = self.game_dir
                self._sync_game_dir_to_config(self.game_dir)
                self.step1_next_btn.setEnabled(True)
                self.old_translation_card.setVisible(False)
                self.has_old_translation = False
        elif os.path.isfile(text):
            self.game_dir = str(selected_paths.project_root if selected_paths else Path(text).parent)
            self.game_path = text
            self._sync_game_dir_to_config(self.game_dir)
            self.path_status_label.setText(
                Localizer.get().onekey_game_file_selected
            )
            self.path_status_label.setStyleSheet("color: #27ae60;")
            self.step1_next_btn.setEnabled(True)
            # 检测旧翻译
            self._check_old_translation(self.game_dir)
        else:
            self.path_status_label.setText(
                Localizer.get().onekey_path_does_not_exist
            )
            self.path_status_label.setStyleSheet("color: #e74c3c;")
            self.step1_next_btn.setEnabled(False)
            self.old_translation_card.setVisible(False)
            self.has_old_translation = False
    
    def _on_inject_base_box_changed(self, state):
        """更新 base_box 注入开关"""
        from module.Config import Config
        config = Config().load()
        config.onekey_inject_base_box = bool(state)
        config.save()

    def _sync_game_dir_to_config(self, game_dir):
        """同步游戏目录到配置文件，包括输入/输出目录"""
        from module.Config import Config

        config = Config().load()
        # 设置 tl 目录路径
        tl_name = getattr(self, 'tl_folder_edit', None)
        tl_name = tl_name.text().strip() if tl_name else "chinese"
        if not tl_name:
            tl_name = "chinese"

        paths = RenpyProjectPaths.from_path(game_dir, tl_name)
        if paths is None:
            raise ValueError(f"无法解析项目目录：{game_dir}")
        apply_to_config(config, paths)
        configure_tl_translation_mode(config)

        # 确保输出目录存在
        paths.translation_output_dir.mkdir(parents = True, exist_ok = True)
        config.save()

        self.info(f"[配置] 输入目录: {config.input_folder}")
        self.info(f"[配置] 输出目录: {config.output_folder}")
    
    def _check_old_translation(self, game_dir):
        """检测是否有旧翻译"""
        tl_name = self.tl_folder_edit.text().strip() or "chinese"
        paths = RenpyProjectPaths.from_path(game_dir, tl_name)
        tl_dir = paths.tl_language_dir if paths is not None else Path(game_dir) / "game" / "tl" / tl_name
        
        if tl_dir.exists() and any(tl_dir.iterdir()):
            # 统计旧翻译文件数量
            rpy_count = len(list(tl_dir.rglob("*.rpy")))
            self.has_old_translation = True
            self.old_trans_title.setText(
                Localizer.get().onekey_existing_translation_detected_files.format(rpy_count=rpy_count)
            )
            self.old_trans_desc.setText(
                Localizer.get().onekey_translation_files_already_exist_tl_choose_how.format(tl_name=tl_name)
            )
            self.old_translation_card.setVisible(True)
            self.incremental_rb.setChecked(True)
            self.full_extract_rb.setChecked(False)
            # 显示跳过按钮
            self.skip_extract_btn.setVisible(True)
        else:
            self.has_old_translation = False
            self.old_translation_card.setVisible(False)
            # 隐藏跳过按钮
            self.skip_extract_btn.setVisible(False)
    
    def _on_tl_name_changed(self, text):
        """TL 文件夹名变化时重新检测旧翻译并同步配置"""
        if self.game_dir:
            self._check_old_translation(self.game_dir)
            # 同步更新配置中的 tl 目录
            self._sync_game_dir_to_config(self.game_dir)
    
    # ==================== 进度二：提取进度 ====================
    def _create_step2_page(self):
        """进度二：提取进度"""
        page, layout = self._create_page_container(
            Localizer.get().onekey_extract_text_2,
            2,
        )
        
        layout.addStretch(1)
        
        self.step2_status = TitleLabel(
            Localizer.get().onekey_ready_extract
        )
        self.step2_status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.step2_status)
        
        self.step2_desc = BodyLabel(
            Localizer.get().onekey_text_extracted_game_translation_files_when_finishes
        )
        self.step2_desc.setAlignment(Qt.AlignCenter)
        self.step2_desc.setWordWrap(True)
        layout.addWidget(self.step2_desc)
        
        layout.addStretch(1)
        
        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        
        # 重试按钮 (默认隐藏，失败后显示)
        self.step2_retry_btn = PushButton(
            Localizer.get().onekey_extract_again
        )
        self.step2_retry_btn.clicked.connect(self._retry_extraction)
        self.step2_retry_btn.setVisible(False)
        btn_row.addWidget(self.step2_retry_btn)

        self.step2_unpack_btn = PrimaryPushButton(
            Localizer.get().onekey_open_rpa_unpacker,
            icon=FluentIcon.ZIP_FOLDER,
        )
        self.step2_unpack_btn.clicked.connect(self._open_rpa_unpack)
        self.step2_unpack_btn.setVisible(False)
        btn_row.addWidget(self.step2_unpack_btn)
        
        # 跳过按钮 (失败时可跳过)
        self.step2_skip_btn = PushButton(
            Localizer.get().onekey_skip_step
        )
        self.step2_skip_btn.clicked.connect(self._go_step3)
        self.step2_skip_btn.setVisible(False)
        btn_row.addWidget(self.step2_skip_btn)
        
        # 下一步按钮 (默认隐藏，完成后显示)
        self.step2_next_btn = PrimaryPushButton(
            Localizer.get().onekey_next
        )
        self.step2_next_btn.clicked.connect(self._go_step3)
        self.step2_next_btn.setVisible(False)
        btn_row.addWidget(self.step2_next_btn)

        self.step2_merge_btn = PushButton(
            Localizer.get().onekey_merge_remove_duplicates
        )
        self.step2_merge_btn.clicked.connect(self._merge_incremental_dir)
        self.step2_merge_btn.setVisible(False)
        btn_row.addWidget(self.step2_merge_btn)
        
        btn_row.addStretch(1)
        layout.addLayout(btn_row)
        
        self.step2_page = page
        self.stacked.addWidget(page)
    
    def _retry_extraction(self):
        """重试提取"""
        self.step2_retry_btn.setVisible(False)
        self.step2_skip_btn.setVisible(False)
        self.step2_unpack_btn.setVisible(False)
        self._go_step2()

    def _get_tool_page(self, key: str) -> QWidget:
        """从工具箱的集中缓存获取工具页。"""
        toolbox = getattr(self.window, "renpy_toolbox_page", None)
        if toolbox is None:
            raise RuntimeError("未找到 Ren'Py 工具箱页面")
        return toolbox.get_tool_page(key)

    def _open_rpa_unpack(self) -> None:
        """打开 RPA 解包页并带入当前项目的 game 目录。"""
        if self.window is None or not self.game_dir:
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.get().onekey_select_valid_game_folder_first,
                parent=self,
            )
            return

        page = self._get_tool_page("pack_unpack")

        if not page.set_game_directory(self.game_dir):
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.get().onekey_could_not_locate_game_s_game_folder,
                parent=self,
            )
            return

        self.window.navigate_to_page(page)

    def _on_auto_merge_cleanup_changed(self, state: int):
        """同步自动合并开关到配置"""
        try:
            from module.Config import Config
            config = Config().load()
            config.renpy_incremental_auto_merge_cleanup = bool(state)
            config.save()
        except Exception as exc:
            self.logger.warning(f"保存自动合并配置失败: {exc}")

    def _on_extract_compiled_changed(self, state: int):
        """同步编译字符串提取开关到配置"""
        try:
            from module.Config import Config
            config = Config().load()
            config.extract_use_compiled = bool(state)
            config.save()
        except Exception as exc:
            self.logger.warning(f"保存编译字符串提取配置失败: {exc}")

    def _on_verify_uppercase_changed(self, state: int):
        """同步大写缩写二次确认开关到配置。"""
        try:
            from module.Config import Config

            config = Config().load()
            config.renpy_verify_uppercase_candidates = bool(state)
            config.save()
        except Exception as exc:
            self.logger.warning(f"保存大写缩写二次确认配置失败: {exc}")

    def _clear_declined_candidates(self):
        """确认后清除当前项目的判定不译清单。"""
        if not self.game_dir:
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.get().onekey_select_game_folder_first,
                parent=self,
            )
            return

        from qfluentwidgets import MessageBox
        from module.Extract.ReplaceGenerator import clear_declined_candidates

        msg_box = MessageBox(
            Localizer.get().onekey_clear_skipped_candidates_2,
            Localizer.get().onekey_these_terms_translated_again_during_next_run,
            self,
        )
        msg_box.yesButton.setText(Localizer.get().onekey_clear)
        msg_box.cancelButton.setText(Localizer.get().app_update_cancel)
        if not msg_box.exec():
            return

        tl_name = self.tl_folder_edit.text().strip() or "chinese"
        cleared = clear_declined_candidates(self.game_dir, tl_name)
        if cleared:
            InfoBar.success(
                Localizer.get().onekey_cleared,
                Localizer.get().onekey_cleared_skipped_candidates.format(cleared=cleared),
                parent=self,
            )
        else:
            InfoBar.info(
                Localizer.get().notice,
                Localizer.get().onekey_there_no_skipped_candidates,
                parent=self,
            )

    def _merge_incremental_dir(self):
        """合并增量目录并清理重复"""
        try:
            # 新流程必须先翻译到独立输出目录，再由“应用翻译”语义合并。
            # 禁止旧入口提前合并并删除仍作为翻译输入的 chinese_new。
            if self._incremental_output_dir:
                InfoBar.warning(
                    Localizer.get().onekey_finish_translation_first,
                    Localizer.get().onekey_incremental_content_has_not_been_applied_finish,
                    parent=self,
                )
                return
            if not self.game_dir:
                InfoBar.warning(
                    Localizer.get().notice,
                    Localizer.get().onekey_select_game_folder_first,
                    parent=self,
                )
                return
            tl_name = self.tl_folder_edit.text().strip() or "chinese"
            incremental_dir = Path(self.game_dir) / "game" / "tl" / f"{tl_name}_new"
            result = self.unified_extractor.merge_incremental_folder(
                self.game_dir,
                tl_name,
                incremental_dir,
                clean_duplicates=True,
            )
            if result.success:
                InfoBar.success(
                    Localizer.get().onekey_merge_completed,
                    Localizer.get().onekey_incremental_files_merged,
                    parent=self,
                )
            else:
                InfoBar.warning(
                    Localizer.get().onekey_merge_failed,
                    Localizer.get().onekey_incremental_files_merge_failed,
                    parent=self,
                )
        except Exception as exc:
            self.logger.error(f"合并失败: {exc}")
            InfoBar.error(
                Localizer.get().error,
                str(exc),
                parent=self,
            )
    
    # ==================== 进度三：术语表 ====================
    def _create_step3_page(self):
        """进度三：项目资产与术语表。"""
        page, layout = self._create_page_container(
            Localizer.get().onekey_terms_translation_context,
            3,
        )
        
        layout.addWidget(
            SubtitleLabel(
                Localizer.get().onekey_glossary_do_not_translate_list
            )
        )
        layout.addWidget(
            BodyLabel(
                Localizer.get().onekey_glossary_keeps_proper_names_consistent_while_do
            )
        )
        
        layout.addSpacing(16)
        
        self.glossary_info_label = BodyLabel(
            Localizer.get().onekey_looking_glossary_files_project
        )
        layout.addWidget(self.glossary_info_label)
        
        layout.addSpacing(16)
        
        btn_row = QHBoxLayout()
        self.open_glossary_btn = PushButton(
            Localizer.get().onekey_open_local_glossary
        )
        self.open_glossary_btn.setToolTip(
            Localizer.get().onekey_use_scan_term_candidates_local_glossary_find
        )
        self.open_glossary_btn.clicked.connect(self._open_local_glossary)
        btn_row.addWidget(self.open_glossary_btn)
        
        self.open_preserve_btn = PushButton(
            Localizer.get().onekey_open_do_not_translate_list
        )
        self.open_preserve_btn.clicked.connect(self._open_text_preserve)
        btn_row.addWidget(self.open_preserve_btn)
        
        self.scan_names_btn = PushButton(
            Localizer.get().onekey_extract_character_names
        )
        self.scan_names_btn.clicked.connect(self._scan_character_names)
        btn_row.addWidget(self.scan_names_btn)

        self.open_workbench_btn = PushButton(
            Localizer.get().onekey_open_character_world_workbench
        )
        self.open_workbench_btn.setToolTip(
            Localizer.get().onekey_manage_worldbook_character_cards_translation_creates_immutable
        )
        self.open_workbench_btn.clicked.connect(self._open_workbench_from_onekey)
        btn_row.addWidget(self.open_workbench_btn)
        
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.workbench_asset_status = BodyLabel(
            Localizer.get().onekey_loading_project_assets
        )
        self.workbench_asset_status.setWordWrap(True)
        layout.addWidget(self.workbench_asset_status)
        
        layout.addStretch(1)
        
        next_row = QHBoxLayout()
        next_row.addStretch(1)
        self.step3_next_btn = PrimaryPushButton(
            Localizer.get().onekey_next_start_translation
        )
        self.step3_next_btn.clicked.connect(self._go_step4)
        next_row.addWidget(self.step3_next_btn)
        layout.addLayout(next_row)
        
        self.step3_page = page
        self.stacked.addWidget(page)
    
    # ==================== 进度四：开始翻译 ====================
    def _create_step4_page(self):
        """进度四：开始翻译"""
        page, layout = self._create_page_container(
            Localizer.get().onekey_run_ai_translation,
            4,
        )
        
        layout.addWidget(
            SubtitleLabel(Localizer.get().onekey_ready_translate)
        )
        self.step4_status = BodyLabel(
            Localizer.get().onekey_translation_files_written_separate_folder_under_game
        )
        layout.addWidget(self.step4_status)
        
        layout.addSpacing(20)
        
        # 翻译按钮
        btn_row = QHBoxLayout()
        self.start_trans_btn = PrimaryPushButton(
            Localizer.get().onekey_start_translation
        )
        self.start_trans_btn.clicked.connect(self._on_start_translate_clicked)
        btn_row.addWidget(self.start_trans_btn)

        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        from module.Config import Config
        auto_hook_row = QHBoxLayout()
        self.auto_hook_supplement_chk = CheckBox(
            Localizer.get().onekey_recover_missed_text_after_translation_replace_text
        )
        self.auto_hook_supplement_chk.setChecked(
            getattr(Config().load(), "onekey_auto_hook_supplement", False)
        )
        self.auto_hook_supplement_chk.setToolTip(
            Localizer.get().onekey_disabled_default_when_enabled_second_pass_generates
        )
        self.auto_hook_supplement_chk.stateChanged.connect(self._on_auto_hook_supplement_changed)
        auto_hook_row.addWidget(self.auto_hook_supplement_chk)
        auto_hook_row.addStretch(1)
        layout.addLayout(auto_hook_row)
        
        layout.addStretch(1)
        
        # 底部按钮
        action_row = QHBoxLayout()
        action_row.addStretch(1)
        
        self.skip_trans_btn = PushButton(
            Localizer.get().onekey_skip_translation
        )
        self.skip_trans_btn.clicked.connect(self._go_step5)
        action_row.addWidget(self.skip_trans_btn)
        
        action_row.addStretch(1)
        layout.addLayout(action_row)
        
        self.step4_page = page
        self.stacked.addWidget(page)
        # 初始化一次检查状态
        self._refresh_step4_ready()
    
    # ==================== 进度五：后续处理 ====================
    def _create_step5_page(self):
        """进度五：后续处理"""
        page, layout = self._create_page_container(
            Localizer.get().onekey_review_export_post_process,
            5,
        )
        
        layout.addWidget(
            SubtitleLabel(
                Localizer.get().onekey_translation_complete
            )
        )
        layout.addWidget(
            BodyLabel(
                Localizer.get().onekey_you_can_now_review_complete_export_translation
            )
        )
        layout.addWidget(
            CaptionLabel(
                Localizer.get().onekey_if_text_still_untranslated_game_use_recover
            )
        )
        
        # 创建滚动区域
        scroll_area = SingleDirectionScrollArea(orient=Qt.Orientation.Vertical)
        scroll_area.setWidgetResizable(True)
        scroll_area.enableTransparentBackground()
        mark_toolbox_scroll_area(scroll_area)
        
        scroll_widget = QWidget()
        mark_toolbox_widget(scroll_widget, "toolboxScroll")
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        
        flow_container = QWidget()
        mark_toolbox_widget(flow_container, "toolboxFlow")
        flow_layout = FlowLayout(flow_container, needAni=False)
        flow_layout.setHorizontalSpacing(8)
        flow_layout.setVerticalSpacing(8)
        flow_layout.setContentsMargins(0, 0, 0, 0)
        
        # 工具卡片
        tools = [
            (
                Localizer.get().onekey_review_polish_export,
                Localizer.get().onekey_review_quality_reports_edit_selected_translations_export,
                self._tool_open_proofreading,
            ),
            (
                Localizer.get().onekey_recover_missed_text,
                Localizer.get().onekey_find_text_missing_tl_generate_replace_text,
                self._tool_hook_supplement,
            ),
            (
                Localizer.get().onekey_detect_repair_errors,
                Localizer.get().onekey_fix_indentation_formatting_issues,
                self._tool_fix_errors,
            ),
            (
                Localizer.get().onekey_set_default_language,
                Localizer.get().onekey_set_language_used_when_game_starts,
                self._tool_set_default_lang,
            ),
            (
                Localizer.get().onekey_add_language_switch,
                Localizer.get().onekey_inject_language_switching_button,
                self._tool_add_lang_switch,
            ),
            (
                Localizer.get().onekey_inject_fonts,
                Localizer.get().onekey_inject_bundled_font_pack,
                self._tool_replace_font,
            ),
            (
                Localizer.get().onekey_open_game_folder,
                Localizer.get().onekey_view_translation_results,
                self._tool_open_game_dir,
            ),
            (
                Localizer.get().onekey_export_language_patch,
                Localizer.get().onekey_export_tl_folder_zip_archive,
                self._tool_export_patch,
            ),
        ]
        
        for title, desc, func in tools:
            card = ItemCard(parent=self, title=title, description=desc, clicked=func)
            card.title_button.setToolTip(
                Localizer.get().onekey_open.format(title=title)
            )
            flow_layout.addWidget(card)
        
        scroll_layout.addWidget(flow_container)
        scroll_layout.addStretch(1)
        
        scroll_area.setWidget(scroll_widget)
        layout.addWidget(scroll_area)
        
        self.step5_page = page
        self.stacked.addWidget(page)

    # ==================== 逻辑处理 ====================
    
    def _select_game_dir(self):
        """浏览选择游戏目录"""
        dir_path = QFileDialog.getExistingDirectory(
            self,
            Localizer.get().onekey_select_game_folder,
            "",
        )
        if dir_path:
            self.game_path_edit.setText(dir_path)
    
    def _detect_game_status(self, game_dir: str) -> tuple:
        """
        检测游戏状态，返回 (status, message)
        
        status:
            - 'ready': 已有 rpy 文件，可直接提取
            - 'need_decompile': 只有 rpyc 文件，需要反编译
            - 'need_unpack': 有 rpa 文件，需要解包
            - 'mixed': 混合状态
            - 'empty': 无可用文件
        """
        from pathlib import Path
        
        paths = RenpyProjectPaths.from_path(
            game_dir,
            self.tl_folder_edit.text().strip() or "chinese",
        )
        if paths is None or not paths.game_dir.exists():
            return 'empty', Localizer.get().onekey_game_folder_not_found

        rpy_count, rpyc_count = source_script_counts(paths)
        rpa_count = len(list(paths.game_dir.glob("*.rpa")))
        
        if rpa_count > 0 and rpy_count == 0 and rpyc_count == 0:
            return 'need_unpack', Localizer.get().onekey_found_rpa_archives_must_unpacked.format(rpa_count=rpa_count)
        
        if rpy_count == 0 and rpyc_count > 0:
            return 'need_decompile', Localizer.get().onekey_found_rpyc_files_must_decompiled.format(rpyc_count=rpyc_count)
        
        if rpy_count > 0 and rpyc_count > 0:
            return 'mixed', Localizer.get().onekey_found_rpy_files_rpyc_files.format(rpy_count=rpy_count, rpyc_count=rpyc_count)
        
        if rpy_count > 0:
            return 'ready', Localizer.get().onekey_found_rpy_files_ready_extraction.format(rpy_count=rpy_count)
        
        return 'empty', Localizer.get().onekey_no_extractable_files_found

    def _show_step2_unpack_failure(self, message: str) -> None:
        """解包失败后的统一界面状态：可重试、可跳过、可转手动解包页。"""
        self.step2_page.progress_ring.setVisible(False)
        self.step2_status.setText(
            Localizer.get().onekey_unpack_failed
        )
        self.step2_desc.setText(message)
        self.step2_unpack_btn.setVisible(True)
        self.step2_unpack_btn.setEnabled(True)
        self.step2_retry_btn.setVisible(True)
        self.step2_skip_btn.setVisible(True)
        self.step2_retry_btn.setEnabled(True)
        self.step2_skip_btn.setEnabled(True)
        InfoBar.warning(
            Localizer.get().notice,
            Localizer.get().onekey_unpack_failed_check_game_files,
            parent=self,
        )

    def _show_step2_decompile_failure(self, message: str) -> None:
        """反编译失败后的统一界面状态。"""
        self.step2_page.progress_ring.setVisible(False)
        self.step2_status.setText(Localizer.get().onekey_decompilation_failed)
        self.step2_desc.setText(
            Localizer.get().onekey_possible_causes_game_uses_encryption_obfuscation_ren.format(
                decompile_msg=message,
            )
        )
        self.step2_retry_btn.setVisible(True)
        self.step2_skip_btn.setVisible(True)
        self.step2_retry_btn.setEnabled(True)
        self.step2_skip_btn.setEnabled(True)
        InfoBar.warning(
            Localizer.get().notice,
            Localizer.get().onekey_decompilation_failed_check_game_files,
            parent=self,
        )

    def _step2_context_is_current(self, generation: int, context: dict) -> bool:
        """确认回调仍属于当前页面、当前配置中的同一项目和语言。"""
        if generation != self._extraction_generation:
            return False

        project_key = str(context.get("project_key", "") or "")
        if not project_key:
            return False
        try:
            current_paths = RenpyProjectPaths.from_config(Config().load())
            page_paths = RenpyProjectPaths.from_path(
                self.game_dir,
                self.tl_folder_edit.text().strip() or "chinese",
            )
        except Exception:
            return False
        return bool(
            current_paths is not None
            and page_paths is not None
            and current_paths.project_key == project_key
            and page_paths.project_key == project_key
        )

    def _on_preprocess_progress(
        self,
        message: str,
        generation: int,
        context: dict,
    ) -> None:
        if self._step2_context_is_current(generation, context):
            self.step2_status.setText(message or "")

    def _start_unpack_worker(self, generation: int, context: dict) -> None:
        paths = RenpyProjectPaths.from_path(
            context["game_dir"],
            context["language"],
        )
        if paths is None:
            self._show_step2_unpack_failure(Localizer.get().onekey_game_folder_not_found)
            return

        worker = UnpackWorker(
            str(paths.game_dir),
            direct=True,
            script_only=False,
        )
        self._preprocess_worker = worker
        worker.progress.connect(
            lambda message, current=generation, snapshot=context: self._on_preprocess_progress(
                message,
                current,
                snapshot,
            )
        )
        worker.finished.connect(
            lambda result, current=generation, snapshot=context, source=worker: self._on_auto_unpack_finished(
                result,
                current,
                snapshot,
                source,
            )
        )
        worker.start()

    def _start_decompile_worker(self, generation: int, context: dict) -> None:
        worker = DecompileWorker(
            context["game_dir"],
            overwrite=False,
            fallback_unren_options="2x",
            use_unren=True,
        )
        self._preprocess_worker = worker
        worker.progress.connect(
            lambda message, current=generation, snapshot=context: self._on_preprocess_progress(
                message,
                current,
                snapshot,
            )
        )
        worker.finished.connect(
            lambda result, current=generation, snapshot=context, source=worker: self._on_auto_decompile_finished(
                result,
                current,
                snapshot,
                source,
            )
        )
        worker.start()

    def _on_auto_unpack_finished(
        self,
        result: dict,
        generation: int,
        context: dict,
        worker,
    ) -> None:
        if self._preprocess_worker is worker:
            self._preprocess_worker = None
        if not self._step2_context_is_current(generation, context):
            return

        result = result if isinstance(result, dict) else {}
        message = str(result.get("message", "") or "")
        if result.get("level") != "success":
            self._show_step2_unpack_failure(
                Localizer.get().onekey_unpack_failed_hint.format(unpack_msg=message)
            )
            return

        status, status_message = self._detect_game_status(context["game_dir"])
        if status in ("need_unpack", "empty"):
            self._show_step2_unpack_failure(
                Localizer.get().onekey_unpack_complete_no_scripts.format(
                    unpack_msg=message,
                )
            )
            return

        self.step2_desc.setText(message)
        self.step2_page.progress_bar.setValue(20)
        self._continue_step2(generation, context, status, status_message)

    def _on_auto_decompile_finished(
        self,
        result: dict,
        generation: int,
        context: dict,
        worker,
    ) -> None:
        if self._preprocess_worker is worker:
            self._preprocess_worker = None
        if not self._step2_context_is_current(generation, context):
            return

        result = result if isinstance(result, dict) else {}
        message = str(result.get("message", "") or "")
        if result.get("level") != "success":
            self._show_step2_decompile_failure(message)
            return

        status, status_message = self._detect_game_status(context["game_dir"])
        if status in ("need_decompile", "need_unpack", "empty"):
            self._show_step2_decompile_failure(status_message or message)
            return

        self.step2_desc.setText(message)
        self.step2_page.progress_bar.setValue(20)
        self._continue_step2(generation, context, status, status_message)

    def _go_step2(self):
        """进入步骤2并开始提取"""
        # 如果正在预处理或抽取，避免重复启动线程。
        if (
            self._preprocess_worker
            and self._preprocess_worker.isRunning()
        ) or (
            self.extraction_worker
            and self.extraction_worker.isRunning()
        ):
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.get().onekey_extraction_already_running_wait_finish,
                parent=self,
            )
            return

        # 每次重新抽取都建立全新的路径上下文，不能沿用上一次项目的增量目标。
        self._incremental_dir = None
        self._incremental_output_dir = None
        self._apply_target_dir = None

        self.current_step = 2
        self.stacked.setCurrentIndex(1)

        # 抽取开始时，禁用“开始翻译/下一步”等按钮，避免在抽取过程中误点
        self.step2_next_btn.setVisible(False)
        self.step2_next_btn.setEnabled(False)
        self.step2_retry_btn.setVisible(False)
        self.step2_retry_btn.setEnabled(False)
        self.step2_unpack_btn.setVisible(False)
        self.step2_unpack_btn.setEnabled(False)
        self.step2_skip_btn.setVisible(False)
        self.step2_skip_btn.setEnabled(False)
        self.step2_merge_btn.setVisible(False)
        self.step2_merge_btn.setEnabled(False)
        self.step2_desc.setText(
            Localizer.get().onekey_extracting_text_game_creating_translation_files
        )
        self.step2_page.progress_bar.setValue(0)
        
        # 启动提取线程
        game_dir = self.game_dir
        tl_name = self.tl_folder_edit.text().strip() or "chinese"
        
        exe_guess = Path(game_dir) / "game.exe"
        exe_path = exe_guess if exe_guess.exists() else game_dir
        if self.game_path and os.path.isfile(self.game_path) and self.game_path.endswith(".exe"):
             exe_path = self.game_path
        
        paths = RenpyProjectPaths.from_path(game_dir, tl_name)
        self._extraction_generation += 1
        generation = self._extraction_generation
        context = {
            "game_dir": str(game_dir),
            "language": tl_name,
            "project_key": paths.project_key if paths is not None else "",
            "exe_path": exe_path,
            "incremental": bool(
                self.has_old_translation and self.incremental_rb.isChecked()
            ),
        }
        self.step2_status.setText(
            Localizer.get().onekey_checking_game_files
        )
        self.step2_page.progress_ring.setVisible(True)
        self.step2_page.progress_bar.setValue(5)

        self._continue_step2(generation, context)

    def _continue_step2(
        self,
        generation: int,
        context: dict,
        status: str | None = None,
        status_msg: str | None = None,
    ) -> None:
        """在同一项目快照内依次完成解包、反编译和文本提取。"""
        if not self._step2_context_is_current(generation, context):
            return

        if status is None:
            status, status_msg = self._detect_game_status(context["game_dir"])
        status_msg = str(status_msg or "")

        if status == 'need_unpack':
            self.step2_status.setText(
                Localizer.get().onekey_unpacking_rpa_archives
            )
            self.step2_desc.setText(
                status_msg
                + Localizer.get().onekey_running_rpa_unpacker_automatically
            )
            self.step2_page.progress_bar.setValue(10)

            self._start_unpack_worker(generation, context)
            return

        if status == 'need_decompile':
            self.step2_status.setText(
                Localizer.get().onekey_decompiling_rpyc_files
            )
            self.step2_desc.setText(
                status_msg
                + Localizer.get().onekey_running_decompiler_automatically
            )
            self.step2_page.progress_bar.setValue(10)

            self._start_decompile_worker(generation, context)
            return

        if status == 'empty':
            self.step2_page.progress_ring.setVisible(False)
            self.step2_status.setText(
                Localizer.get().onekey_game_files_not_found
            )
            self.step2_desc.setText(status_msg)
            self.step2_retry_btn.setVisible(True)
            self.step2_retry_btn.setEnabled(True)
            self.step2_skip_btn.setVisible(False)
            self.step2_skip_btn.setEnabled(False)
            return
        
        incremental = bool(context["incremental"])
        
        if incremental:
            self.step2_status.setText(
                Localizer.get().onekey_running_incremental_extraction
            )
        else:
            self.step2_status.setText(
                Localizer.get().onekey_extracting
            )
        self.step2_page.progress_ring.setVisible(True)
        
        self.extraction_worker = ExtractionWorker(
            self.unified_extractor,
            context["game_dir"],
            context["language"],
            context["exe_path"],
            incremental=incremental,
        )
        self.extraction_worker.progress.connect(
            lambda message, percent, current=generation: self._on_extract_progress(
                message,
                percent,
                current,
            )
        )
        self.extraction_worker.finished.connect(
            lambda success, message, result, current=generation, snapshot=context: self._on_extract_finished(
                success,
                message,
                result,
                current,
                snapshot,
            )
        )
        self.extraction_worker.start()

    def _on_extract_progress(self, msg, percent, generation=None):
        if generation is not None and generation != self._extraction_generation:
            return
        self.step2_status.setText(msg)
        self.step2_page.progress_bar.setValue(percent)
        
    def _on_extract_finished(
        self,
        success,
        msg,
        result=None,
        generation=None,
        context=None,
    ):
        if generation is not None and generation != self._extraction_generation:
            return

        game_dir = self.game_dir
        tl_name = self.tl_folder_edit.text().strip() or "chinese"
        if isinstance(context, dict):
            current_paths = RenpyProjectPaths.from_config(Config().load())
            page_paths = RenpyProjectPaths.from_path(game_dir, tl_name)
            project_key = str(context.get("project_key", "") or "")
            if (
                not project_key
                or current_paths is None
                or page_paths is None
                or current_paths.project_key != project_key
                or page_paths.project_key != project_key
            ):
                self._start_translation_after_extraction = False
                self._agent_direct_start = False
                self.extraction_worker = None
                self.step2_page.progress_ring.setVisible(False)
                self.step2_status.setText(
                    Localizer.get().onekey_project_changed_extract_again
                )
                self.step2_desc.setText(
                    Localizer.get().onekey_project_changed_extract_again
                )
                self.step2_retry_btn.setVisible(True)
                self.step2_retry_btn.setEnabled(True)
                return
            game_dir = str(context.get("game_dir", game_dir) or game_dir)
            tl_name = str(context.get("language", tl_name) or tl_name)

        self.step2_page.progress_ring.setVisible(False)
        if success:
            self.step2_status.setText(
                Localizer.get().onekey_extraction_complete
            )
            # 如果是增量抽取并且有单独的增量目录，显示更详细的信息
            if result and result.incremental_dir and result.incremental_dir.exists():
                detail_msg = (
                    Localizer.get().onekey_new_content_written_existing_translations_left_unchanged.format(msg=msg, name=result.incremental_dir.name)
                )
                self._incremental_dir = result.incremental_dir
                # 暂存目录需要保留到翻译完成；提前合并会删除它，
                # 导致翻译页面回退到完整的主语言目录。
                config = Config().load()
                apply_target, delta_output = configure_incremental_translation_paths(
                    config, game_dir, tl_name, result.incremental_dir
                )
                preserved_output = preserve_incremental_translation_cache(delta_output)
                delta_output.mkdir(parents=True, exist_ok=True)
                config.save()
                self._apply_target_dir = apply_target
                self._incremental_output_dir = delta_output
                self._last_onekey_output_dir = delta_output
                detail_msg += (
                    Localizer.get().onekey_incremental_input_incremental_output.format(name=result.incremental_dir.name, name_2=delta_output.name)
                )
                if preserved_output is not None:
                    detail_msg += (
                        Localizer.get().onekey_previous_incremental_cache_preserved_can_restored_manually.format(name=preserved_output.name)
                    )
            else:
                detail_msg = Localizer.get().onekey_placeholders_preserved_new_old_you_can_translate.format(msg=msg)
                self._incremental_dir = None
                self._incremental_output_dir = None
                self._apply_target_dir = None
                paths = RenpyProjectPaths.from_path(game_dir, tl_name)
                self._last_onekey_output_dir = (
                    paths.translation_output_dir if paths is not None else None
                )
            
            self.step2_desc.setText(detail_msg)
            self.step2_page.progress_bar.setValue(100)
            self.step2_next_btn.setVisible(True)
            self.step2_next_btn.setEnabled(True)
            self.step2_retry_btn.setVisible(True)
            self.step2_retry_btn.setEnabled(True)
            self.step2_skip_btn.setVisible(False)
            self.step2_skip_btn.setEnabled(False)
            self.step2_next_btn.setText(
                Localizer.get().onekey_start_translation_2
            )
            # 增量暂存目录是后续翻译输入，翻译前不能通过旧按钮直接合并或删除。
            self.step2_merge_btn.setVisible(False)
            self.step2_merge_btn.setEnabled(False)
            
            # 自动执行角色名和禁翻表扫描（仅第一次执行，避免重复卡顿）
            self._extract_character_names()
            
            InfoBar.success(
                Localizer.get().extract_json_success,
                Localizer.get().onekey_extraction_completed_character_names_variable_references_scanned,
                parent=self,
            )
            self._continue_agent_start_after_extraction()
        else:
            self.step2_status.setText(
                Localizer.get().onekey_extraction_failed
            )
            self.step2_desc.setText(
                Localizer.get().onekey_error_select_extract_again_if_still_fails.format(msg=msg)
            )
            self.step2_retry_btn.setVisible(True)
            self.step2_skip_btn.setVisible(True)
            self.step2_retry_btn.setEnabled(True)
            self.step2_skip_btn.setEnabled(True)
            self.step2_next_btn.setVisible(False)
            self.step2_next_btn.setEnabled(False)
            self.step2_merge_btn.setVisible(False)
            self.step2_merge_btn.setEnabled(False)
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.get().onekey_extraction_failed_you_can_try_again_skip,
                parent=self,
            )

    def _continue_agent_start_after_extraction(self) -> None:
        """Agent 发起的流程在提取成功后自动进入已有翻译确认。"""
        if not self._start_translation_after_extraction:
            return
        self._start_translation_after_extraction = False
        self._go_step4()
        QTimer.singleShot(0, self._on_start_translate_clicked)

    def _scan_character_names(self):
        """扫描角色候选并写入工作台，变量引用继续写入禁翻表。"""
        self._extract_character_names(force=True)
        InfoBar.success(
            Localizer.get().extract_json_success,
            Localizer.get().onekey_character_candidates_variable_references_scanned,
            parent=self,
        )

    def _extract_character_names(self, *, force: bool = False):
        """自动扫描角色候选、角色草稿和变量引用。"""
        if not self.game_dir:
            return
            
        paths = RenpyProjectPaths.from_path(
            self.game_dir,
            self.tl_folder_edit.text().strip() or "chinese",
        )
        game_path = paths.game_dir if paths is not None else Path(self.game_dir) / "game"
        if not game_path.exists():
            return
            
        found_names = set()
        found_preserves = set()  # 用于存储变量引用
        candidate_cards: list[dict] = []
        
        config = Config().load()
        cache_key = str(game_path.resolve())
        auto_cache = dict(getattr(config, "glossary_auto_scan_cache", {}) or {})

        if not force and cache_key in auto_cache:
            LogManager.get().info(
                "Skip character scan: already scanned for %s", cache_key
            )
            return

        try:
            # 统一复用工作台扫描器，确保一键流程与角色工作台识别结果一致。
            scanner = CharacterScanner()
            scan_result = scanner.scan_project(game_path.parent)
            found_names.update(scan_result.names)
            found_preserves.update(scan_result.preserves)

            # 将本地扫描结果先形成待确认角色草稿；AI 分析仍由工作台按需触发。
            glossary_names = scanner.collect_glossary_character_names(config)
            for name in sorted(scan_result.names, key = lambda value: value.casefold()):
                samples = list(scan_result.speaker_samples.get(name, []))[:12]
                candidate = CharacterCandidate(
                    name = name,
                    match_keywords = [name],
                    sample_lines = samples,
                    related_names = list(scan_result.co_occurrence.get(name, []))[:8],
                    name_translation = glossary_names.get(name, ""),
                    sample_count = len(samples),
                    low_confidence = len(samples) < 3,
                )
                candidate_cards.append(candidate.as_card_seed())
        except Exception as exc:
            LogManager.get().warning(f"统一角色扫描失败：{exc}")
            
        # 角色名由项目资产仓库统一维护为待确认候选；这里只保留变量引用的
        # legacy text_preserve 配置同步，避免角色术语绕过项目资产边界。
        self._update_config(set(), found_preserves, config)

        # 同步到稳定的项目资产仓库。空译名保留为候选，避免项目缓存已经
        # 存在时仅修改全局 Config 却不进入实际翻译快照。
        try:
            repository = ProjectAssetsRepository.from_config(config)
            state = repository.load(config)
            term_entries = [
                {
                    "source": self._clean_text_for_type(name),
                    "target": "",
                    "note": "一键流程自动提取角色名",
                    "type": "角色",
                }
                for name in sorted(found_names, key = lambda value: value.casefold())
                if self._clean_text_for_type(name)
            ]
            analysis_candidates = (
                repository.merge_analysis_terms(term_entries)
                if term_entries
                else state.analysis_candidates
            )

            # 将本地扫描出的角色放入工作台待确认草稿，避免一键流程只更新
            # 全局术语表而遗漏角色样本和说话风格上下文。
            if candidate_cards:
                existing_drafts = analysis_candidates.get("character_drafts", [])
                existing_drafts = [
                    item for item in existing_drafts
                    if isinstance(item, dict)
                ] if isinstance(existing_drafts, list) else []
                existing_ids = {
                    str(item.get("id", "")).strip()
                    for item in existing_drafts
                    if str(item.get("id", "")).strip()
                }
                for card in candidate_cards:
                    card_id = str(card.get("id", "")).strip()
                    if card_id and card_id not in existing_ids:
                        existing_drafts.append(card)
                        existing_ids.add(card_id)
                analysis_candidates["character_drafts"] = existing_drafts
                repository.save_analysis_candidates(analysis_candidates)

            current_preserves = [item.to_dict() for item in state.assets.do_not_translate]
            current_sources = {
                str(item.get("source", "")).strip()
                for item in current_preserves
                if isinstance(item, dict)
            }
            current_preserves.extend(
                {"source": value, "target": "", "note": "一键流程自动提取变量"}
                for value in sorted(found_preserves)
                if value not in current_sources
            )
            if found_preserves:
                repository.replace_do_not_translate(
                    current_preserves,
                    enabled = True,
                )
        except Exception as exc:
            LogManager.get().warning(f"同步一键项目资产失败：{exc}")

        auto_cache[cache_key] = time.time()
        config.glossary_auto_scan_cache = auto_cache
        config.save()

    @staticmethod
    def _clean_text_for_type(text: str) -> str:
        """去除格式标签/空白，便于分类"""
        if not text:
            return ""
        import re
        cleaned = re.sub(r"\{/?[^}]+\}", "", text)
        return cleaned.replace("\u3000", " ").strip()

    @staticmethod
    def _should_ignore_extracted_name(text: str) -> bool:
        """过滤明显无效的候选（如单字母 A/Q/变量样式）"""
        if not text:
            return True
        if len(text) <= 1:
            return True
        # 单字母 + 可选标点（A. / Q. / A）
        import re
        if re.fullmatch(r"[A-Za-z](?:\.|!|\?)?", text):
            return True
        # 过短且包含点/下划线通常是变量或占位
        if len(text) <= 3 and any(ch in text for ch in ".:_"):
            return True
        return False

    @staticmethod
    def _categorize_term(text: str, default: str = "") -> str:
        """基于 LocalGlossary 的关键词规则做简易分类"""
        if not text:
            return default
        t = text.strip()
        lower = t.lower()
        place_keywords = [
            "city", "village", "town", "forest", "mountain", "hill", "park", "garden",
            "school", "academy", "college", "campus", "church", "temple", "shrine",
            "castle", "tower", "dungeon", "cave", "ruins", "harbor", "port", "station",
            "beach", "island", "lake", "river", "bridge", "street", "road", "avenue",
            "hotel", "inn", "bar", "cafe", "shop", "market", "library"
        ]
        item_keywords = [
            "sword", "blade", "dagger", "bow", "gun", "rifle", "pistol", "armor", "shield",
            "ring", "necklace", "amulet", "bracelet", "crown", "helmet", "boots", "gloves",
            "potion", "elixir", "herb", "scroll", "book", "map", "key", "card", "ticket",
            "coin", "gem", "crystal", "stone", "orb", "staff", "wand", "medal"
        ]
        if any(k in lower for k in place_keywords):
            return "地名"
        if any(k in lower for k in item_keywords):
            return "物品"
        words = t.split()
        if words and all(w[:1].isupper() for w in words if w):
            return default or ""
        return default

    def _find_ner_model_path(self) -> Path | None:
        """查找本地 NER 模型路径（resource/Models/ner 下），兼容打包路径."""
        candidates: list[Path] = []
        candidate_roots = [
            Path(get_resource_path("resource", "Models", "ner")),
            (Path(".") / "resource" / "Models" / "ner").resolve(),
            (Path(__file__).resolve().parents[2] / "resource" / "Models" / "ner").resolve(),
        ]
        for model_root in candidate_roots:
            if not model_root.exists():
                continue
            for p in model_root.iterdir():
                if p.is_dir() and (p / "meta.json").exists():
                    candidates.append(p)
        if not candidates:
            return None
        candidates.sort()
        return candidates[0]

    def _load_ner_model(self):
        """懒加载 spaCy NER 模型，失败则返回 None"""
        if self._ner_model_loaded:
            return self._ner_model
        self._ner_model_loaded = True
        try:
            import spacy
        except Exception:
            self._ner_model = None
            return None
        model_path = self._find_ner_model_path()
        if not model_path:
            self._ner_model = None
            return None
        try:
            self._ner_model = spacy.load(
                str(model_path),
                exclude=["parser", "tagger", "lemmatizer", "attribute_ruler", "tok2vec"],
            )
        except Exception:
            self._ner_model = None
        return self._ner_model

    def _ner_guess_type(self, text: str, default: str = "") -> str:
        """使用 NER 预测类别（角色/地名/组织/物品），失败则返回默认"""
        nlp = self._load_ner_model()
        if not nlp:
            return default
        label_map = {
            "PER": "角色",
            "PERSON": "角色",
            "PER_NO": "角色",
            "LOC": "地名",
            "GPE": "地名",
            "ORG": "组织",
            "FAC": "地名",
            "PRODUCT": "物品",
            "ITEM": "物品",
        }
        try:
            doc = nlp(text)
            for ent in doc.ents:
                mapped = label_map.get(ent.label_)
                if mapped:
                    return mapped
        except Exception:
            return default
        return default

    def _update_config(self, found_names, found_preserves, config):
        """更新配置文件，返回是否写入新数据"""
        updated = False

        # 更新术语表
        if found_names:
            existing_src = set()
            if config.glossary_data:
                for item in config.glossary_data:
                    if isinstance(item, dict):
                        existing_src.add(item.get("src", ""))
                    elif isinstance(item, str):
                        existing_src.add(item)

            new_entries = []
            for name in found_names:
                cleaned = self._clean_text_for_type(name)
                if not cleaned or cleaned in existing_src:
                    continue
                if self._should_ignore_extracted_name(cleaned):
                    continue
                type_guess = self._ner_guess_type(cleaned, default="") or self._categorize_term(cleaned, default="")
                new_entries.append({
                    "src": cleaned,
                    "dst": "",
                    "info": "角色名 (自动提取)",
                    "type": type_guess
                })

            if new_entries:
                if not config.glossary_data:
                    config.glossary_data = []
                config.glossary_data.extend(new_entries)
                config.glossary_enable = True
                updated = True
                
        # 更新禁翻表
        if found_preserves:
            existing_preserve = set()
            if config.text_preserve_data:
                for item in config.text_preserve_data:
                    if isinstance(item, dict):
                        existing_preserve.add(item.get("src", ""))
                    elif isinstance(item, str):
                        existing_preserve.add(item)
                        
            new_preserves = []
            for text in found_preserves:
                if text not in existing_preserve:
                    new_preserves.append({"src": text})
                    
            if new_preserves:
                if not config.text_preserve_data:
                    config.text_preserve_data = []
                config.text_preserve_data.extend(new_preserves)
                config.text_preserve_enable = True
                updated = True
                
        return updated

    @staticmethod
    def _looks_like_character_name(name: str) -> bool:
        if not name:
            return False
        if any(char.isupper() for char in name):
            return True
        if any(ord(char) > 127 and char.isalpha() for char in name):
            return True
        return False
            
    def _go_step3(self):
        self.current_step = 3
        self.stacked.setCurrentIndex(2)
        self._find_glossary_files()
        self._refresh_workbench_asset_status()

    def _refresh_workbench_asset_status(self) -> None:
        """显示与当前一键翻译项目绑定的工作台资产数量。"""
        label = getattr(self, "workbench_asset_status", None)
        if label is None:
            return
        try:
            config = Config().load()
            state = ProjectAssetsRepository.from_config(config).load(config)
            assets = state.assets
            candidates = state.analysis_candidates.get("items", [])
            character_drafts = state.analysis_candidates.get("character_drafts", [])
            if not isinstance(candidates, list):
                candidates = []
            if not isinstance(character_drafts, list):
                character_drafts = []
            label.setText(
                Localizer.get().onekey_project_assets_summary.format(
                    worldbook_status=(
                        Localizer.get().enabled
                        if assets.worldbook_enabled
                        else Localizer.get().disabled
                    ),
                    character_count=len(assets.character_cards),
                    glossary_count=len(assets.glossary),
                    preserve_count=len(assets.do_not_translate),
                    candidate_count=len(candidates),
                    draft_count=len(character_drafts),
                )
            )
        except Exception as exc:
            label.setText(
                Localizer.get().onekey_project_assets_currently_unavailable.format(exc=exc)
            )

    def _open_workbench_from_onekey(self) -> None:
        """从一键流程打开工作台，并先同步当前项目路径。"""
        try:
            if self.game_dir:
                self._sync_game_dir_to_config(self.game_dir)
            page = getattr(self.window, "renpy_workbench_page", None)
            if page is None and hasattr(self.window, "findChild"):
                page = self.window.findChild(QWidget, "renpy_workbench_page")
            if page is None:
                InfoBar.warning(
                    Localizer.get().notice,
                    Localizer.get().onekey_character_world_workbench_page_not_found,
                    parent = self,
                )
                return
            if hasattr(page, "refresh_from_config"):
                page.refresh_from_config()
            self.window.navigate_to_page(page)
        except Exception as exc:
            self.logger.error(f"打开工作台失败：{exc}")
            InfoBar.error(
                Localizer.get().error,
                Localizer.get().onekey_could_not_open_workbench.format(exc=exc),
                parent = self,
            )
        
    def _find_glossary_files(self):
        found_files = []
        if self.game_dir:
            patterns = ["glossary.json", "glossary.xlsx", "glossary.txt", "blacklist.json", "blacklist.txt"]
            for pattern in patterns:
                if os.path.exists(os.path.join(self.game_dir, pattern)):
                    found_files.append(pattern)
                if os.path.exists(os.path.join(self.game_dir, "game", pattern)):
                    found_files.append(f"game/{pattern}")
        
        if found_files:
            self.glossary_info_label.setText(
                Localizer.get().onekey_found.format(join_found_files=', '.join(found_files))
            )
        else:
            self.glossary_info_label.setText(
                Localizer.get().onekey_no_glossary_files_found_default_configuration_used
            )

    def _open_local_glossary(self):
        page = self._get_tool_page("local_glossary")
        self.window.navigate_to_page(page)

    def _open_text_preserve(self):
        page = self._get_tool_page("text_preserve")
        self.window.navigate_to_page(page)

    def _go_step4(self):
        self.current_step = 4
        self.stacked.setCurrentIndex(3)
        self._refresh_step4_state()

    def start_current_project(self, project_root: str, language: str) -> bool:
        """由 Agent 带入当前项目并启动提取，完成后继续进入翻译确认。"""
        engine = Engine.get()
        if (
            (
                getattr(self, "_preprocess_worker", None)
                and self._preprocess_worker.isRunning()
            )
            or
            (self.extraction_worker and self.extraction_worker.isRunning())
            or engine.get_status() != Engine.Status.IDLE
            or engine.has_stop_barrier()
            or engine.has_single_tasks()
            or bool(getattr(self, "_onekey_translation_started", False))
            or bool(getattr(self, "_onekey_request_id", ""))
            or bool(getattr(self, "_auto_hook_running", False))
            or bool(getattr(self, "_apply_running", False))
        ):
            return False
        root = str(project_root or "").strip()
        if not root:
            return False

        self._start_translation_after_extraction = True
        self._agent_direct_start = True
        self._onekey_translation_completed = False
        try:
            tl_blocked = self.tl_folder_edit.blockSignals(True)
            self.tl_folder_edit.setText(str(language or "chinese").strip() or "chinese")
            self.tl_folder_edit.blockSignals(tl_blocked)
            path_blocked = self.game_path_edit.blockSignals(True)
            self.game_path_edit.setText(root)
            self.game_path_edit.blockSignals(path_blocked)
            self._on_path_text_changed(root)
            if not self.step1_next_btn.isEnabled():
                self._start_translation_after_extraction = False
                self._agent_direct_start = False
                return False
            self._go_step2()
            return True
        except Exception:
            self._start_translation_after_extraction = False
            self._agent_direct_start = False
            raise

    def _invalidate_step2_run(self) -> None:
        """让仍在后台运行的旧步骤 2 结果失效。"""
        self._extraction_generation += 1
        self._start_translation_after_extraction = False
        self._agent_direct_start = False

    def hideEvent(self, event):
        """页面离开后不允许旧预处理结果继续启动后续任务。"""
        self._invalidate_step2_run()
        super().hideEvent(event)

    def showEvent(self, event):
        """从翻译面板返回本页时刷新第 4 步状态，避免显示“未翻译”的假象。"""
        super().showEvent(event)
        if self.current_step == 4:
            self._refresh_step4_state()
    
    def _on_start_translate_clicked(self):
        """检查配置后再进入翻译面板"""
        if not self._refresh_step4_ready():
            self._agent_direct_start = False
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.get().onekey_activate_translation_provider_configure_input_output_folders,
                parent=self,
            )
            return
        
        # 显示友好的目录说明
        from module.Config import Config
        from qfluentwidgets import MessageBox
        
        config = Config().load()
        # 一键翻译处理的是 game/tl/<语言>，不能沿用“源码翻译/补漏”页面的模式。
        configure_tl_translation_mode(config)
        config.save()
        
        # 根据主题选择样式颜色
        code_bg = "#2d2d2d" if isDarkTheme() else "#f5f5f5"
        hint_color = "#aaa" if isDarkTheme() else "#666"
        
        msg_box = MessageBox(
            Localizer.get().onekey_translation_folders,
            Localizer.get().onekey_b_input_folder_b_files_translate_br.format(code_bg=code_bg, input_folder=config.input_folder, output_folder=config.output_folder, hint_color=hint_color),
            self
        )
        msg_box.yesButton.setText(
            Localizer.get().direct_rpy_start_translation
        )
        msg_box.cancelButton.setText(Localizer.get().app_update_cancel)
        
        direct_start = self._agent_direct_start
        self._agent_direct_start = False
        if msg_box.exec():
            self._onekey_translation_started = not direct_start
            self._onekey_translation_completed = False
            self._auto_hook_pending = self.auto_hook_supplement_chk.isChecked()
            self._auto_hook_running = False
            self._open_legacy_translation_page(start_immediately=direct_start)

    def _on_auto_hook_supplement_changed(self, state):
        """保存一键翻译后的自动补漏开关。"""
        try:
            from module.Config import Config

            config = Config().load()
            config.onekey_auto_hook_supplement = bool(state)
            config.save()
        except Exception as e:
            self.logger.warning(f"保存自动补全漏翻配置失败: {e}")
        
    def _open_legacy_translation_page(self, *, start_immediately: bool = False):
        """打开传统翻译页面，保留续翻译能力"""
        try:
            if not self.window:
                raise RuntimeError("未找到主窗口，无法打开翻译面板")

            page = getattr(self.window, "translation_page", None)
            if page is None:
                page = TranslationPage("translation_page", self.window)
                self.window.translation_page = page
            self.window.navigate_to_page(page)
            if start_immediately:
                request_id = uuid.uuid4().hex
                self._onekey_request_id = request_id
                self._onekey_run_id = None
                if not page._request_translation_start(
                    Base.TranslationStatus.UNTRANSLATED,
                    self.window,
                    request_id=request_id,
                ):
                    self._reset_auto_hook_state()
        except Exception as e:
            self._reset_auto_hook_state()
            LogManager.get().error(f"打开传统翻译面板失败: {e}")
            InfoBar.error(
                Localizer.get().error,
                Localizer.get().onekey_could_not_open_translation_panel.format(e=e),
                parent=self,
            )
        
    def _go_step5(self):
        self.current_step = 5
        self.stacked.setCurrentIndex(4)
        self.step5_page.progress_bar.setValue(100)

    def _start_auto_hook_supplement(
        self,
        project_paths: RenpyProjectPaths | None = None,
    ):
        """主翻译完成后自动执行补全漏翻。"""
        try:
            from module.Config import Config

            if not self.game_dir and project_paths is None:
                self._reset_auto_hook_state()
                return

            if project_paths is not None:
                page_paths = RenpyProjectPaths.from_path(
                    self.game_dir,
                    project_paths.language,
                )
                config_paths = RenpyProjectPaths.from_config(Config().load())
                if (
                    page_paths is None
                    or config_paths is None
                    or page_paths.project_key != project_paths.project_key
                    or config_paths.project_key != project_paths.project_key
                ):
                    self._reset_auto_hook_state()
                    InfoBar.warning(
                        Localizer.get().notice,
                        Localizer.get().agent_project_changed,
                        parent=self,
                    )
                    return
                paths = project_paths
                tl_name = paths.language
            else:
                tl_name = self.tl_folder_edit.text().strip() or "chinese"
                paths = RenpyProjectPaths.from_path(self.game_dir, tl_name)
            if paths is None:
                raise RuntimeError("无法解析当前 Ren'Py 项目路径")
            project_root = paths.project_root
            tl_dir = paths.tl_language_dir
            if not tl_dir.exists():
                InfoBar.warning(
                    Localizer.get().notice,
                    Localizer.get().onekey_tl_folder_not_found_missed_text_recovery.format(tl_dir=tl_dir),
                    parent=self,
                )
                self._reset_auto_hook_state()
                return

            self._sync_game_dir_to_config(str(project_root))

            config = Config().load()
            apply_to_config(
                config,
                paths,
                input_folder = tl_dir,
                output_folder = tl_dir,
            )
            previous_output = self._last_onekey_output_dir or paths.translation_output_dir
            previous_output = Path(previous_output)
            self._hook_restore_paths = (
                str(project_root),
                tl_name,
                str(previous_output),
            )
            _remember_translation_run(
                paths,
                output_folder = tl_dir,
                input_folder = tl_dir,
                application_target_dir = tl_dir,
                run_kind = "hook",
            )
            config.renpy_hook_translate = True
            config.renpy_source_translate = False

            self._auto_hook_running = True
            request_id = uuid.uuid4().hex
            self._onekey_request_id = request_id
            self._onekey_run_id = None

            self.emit(
                Base.Event.TRANSLATION_START,
                {
                    "request_id": request_id,
                    "config": config,
                    "status": Base.TranslationStatus.UNTRANSLATED,
                    "input_folder": str(tl_dir),
                    "output_folder": str(tl_dir),
                    "source_language": config.source_language,
                    "target_language": config.target_language,
                },
            )
        except Exception as e:
            self.logger.error(f"自动补全漏翻启动失败: {e}")
            InfoBar.error(
                Localizer.get().error,
                Localizer.get().onekey_could_not_start_missed_text_recovery.format(e=e),
                parent=self,
            )
            self._restore_paths_after_auto_hook()
            self._reset_auto_hook_state()

    def _reset_auto_hook_state(self):
        """重置自动补全漏翻相关状态。"""
        self._onekey_translation_started = False
        self._onekey_request_id = ""
        self._onekey_run_id = None
        self._auto_hook_pending = False
        self._auto_hook_running = False
        self._hook_restore_paths = None
        self._last_onekey_output_dir = None

    def _restore_paths_after_auto_hook(self) -> None:
        """恢复全局配置，并把最近运行清单指回 Hook 前的有效缓存。"""
        restore = self._hook_restore_paths
        self._hook_restore_paths = None
        if not restore:
            return
        try:
            from module.Config import Config

            config = Config().load()
            # 新版本保存 (项目根, 语言目录名, Hook 前输出目录)；兼容旧版
            # 只有两个元素的状态，避免页面对象在热更新后恢复时崩溃。
            project_root = restore[0]
            tl_name = restore[1]
            previous_output = (
                Path(restore[2])
                if len(restore) >= 3 and restore[2]
                else None
            )
            paths = configure_main_translation_paths(
                config,
                project_root,
                tl_name,
                remember_run = False,
            )
            if previous_output is None:
                previous_output = paths[1]
            # hook 只是自动补漏的临时运行模式；收尾后必须恢复普通翻译
            # 标志，避免下一次一键翻译继续沿用 hook/source 分支。
            config.renpy_hook_translate = False
            config.renpy_source_translate = False
            config.save()

            # Hook 会临时把清单写到 game/tl/<lang>。恢复时必须重新登记
            # Hook 前的主/增量缓存，否则校对页会优先载入 Hook 的空项目。
            output_name = previous_output.name.casefold()
            incremental_name = f"{str(tl_name).strip().casefold()}_new"
            run_kind = "incremental" if output_name == incremental_name else "translation"
            input_folder = (
                paths[0].parent / f"{str(tl_name).strip()}_new"
                if run_kind == "incremental"
                else paths[0]
            )
            restored_paths = RenpyProjectPaths.from_path(project_root, tl_name)
            if restored_paths is not None:
                _remember_translation_run(
                    restored_paths,
                    output_folder = previous_output,
                    input_folder = input_folder,
                    application_target_dir = restored_paths.application_target_dir,
                    run_kind = run_kind,
                )
        except Exception as exc:
            self.logger.warning(f"自动补全完成后恢复主路径失败: {exc}")

    def _on_translation_start_result(self, event, data):
        """只接收本次 Agent 一键启动请求的受理结果。"""
        del event
        payload = data if isinstance(data, dict) else {}
        request_id = str(payload.get("request_id", "") or "")
        if not self._onekey_request_id or request_id != self._onekey_request_id:
            return

        self._onekey_request_id = ""
        if payload.get("accepted") is True:
            self._onekey_run_id = payload.get("run_id")
            self._onekey_translation_started = True
            if getattr(self, "_auto_hook_running", False):
                InfoBar.success(
                    Localizer.get().direct_rpy_started,
                    Localizer.get().onekey_main_translation_complete_recovering_missed_text,
                    parent=self,
                )
            return

        self._onekey_translation_completed = False
        if getattr(self, "_auto_hook_running", False):
            self._restore_paths_after_auto_hook()
        self._reset_auto_hook_state()
        InfoBar.warning(
            Localizer.get().notice,
            Localizer.get().translator_running,
            parent=self,
        )

    def _on_translation_done(self, event, data):
        """监听翻译完成，按需接续 replace_text 补漏。"""
        payload = data if isinstance(data, dict) else {}
        failed = payload.get("success") is False or payload.get("stopped") is True

        if getattr(self, "_auto_hook_running", False):
            request_id = str(payload.get("request_id", "") or "")
            pending_request_id = str(
                getattr(self, "_onekey_request_id", "") or ""
            )
            run_id = getattr(self, "_onekey_run_id", None)
            if pending_request_id:
                if request_id != pending_request_id:
                    return
                self._onekey_request_id = ""
                self._onekey_run_id = payload.get("run_id")
            elif run_id is not None and payload.get("run_id") != run_id:
                return
            self._restore_paths_after_auto_hook()
            self._reset_auto_hook_state()
            if failed:
                InfoBar.warning(
                    Localizer.get().direct_rpy_stopped,
                    Localizer.get().onekey_missed_text_recovery_did_not_finish_main,
                    parent=self,
                )
            else:
                InfoBar.success(
                    Localizer.get().local_glossary_completed,
                    Localizer.get().onekey_missed_text_recovery_completed,
                    parent=self,
                )
            return

        pending_request_id = str(
            getattr(self, "_onekey_request_id", "") or ""
        )
        if pending_request_id:
            if str(payload.get("request_id", "") or "") != pending_request_id:
                return
            self._onekey_request_id = ""
            self._onekey_run_id = payload.get("run_id")
            self._onekey_translation_started = True
        elif (
            getattr(self, "_onekey_run_id", None) is not None
            and payload.get("run_id") != self._onekey_run_id
        ):
            return

        if self._onekey_translation_started and self._auto_hook_pending:
            # 主输出必须先由用户确认并应用到 game/tl，再扫描漏翻；否则全量
            # 输出尚未落地、增量输出尚未合并，都会以旧 TL 作为扫描依据。
            if failed:
                self._reset_auto_hook_state()
                return
            return

        if self._onekey_translation_started:
            self._onekey_translation_completed = not failed
            self._reset_auto_hook_state()
            self._refresh_step4_state()

    def _on_translation_stop(self, event, data):
        """翻译停止时清理一键翻译的自动补漏状态。"""
        if self._onekey_request_id or self._onekey_run_id is not None:
            # 关联运行等待带 run_id 的 TRANSLATION_DONE，不能被其它停止请求清理。
            return
        if self._onekey_translation_started or self._auto_hook_pending or self._auto_hook_running:
            if self._auto_hook_running:
                self._restore_paths_after_auto_hook()
            self._onekey_translation_completed = False
            self._reset_auto_hook_state()
            self._refresh_step4_state()

    def _translation_output_completed(self) -> bool:
        """翻译输出目录缓存已完成时为 True（用于向导重建后的兜底判断）。"""
        try:
            from module.Cache.CacheManager import CacheManager

            cfg = Config().load()
            output = str(getattr(cfg, "output_folder", "") or "")
            if not output:
                return False
            manager = CacheManager(service=False)
            manager.load_project_from_file(output)
            return (
                manager.get_project().get_status()
                == Base.TranslationStatus.TRANSLATED
            )
        except Exception:
            return False

    def _refresh_step4_state(self) -> None:
        """刷新第 4 步界面：翻译已完成时给出明确指引，否则走配置检查。"""
        if self._onekey_translation_completed or self._translation_output_completed():
            self._onekey_translation_completed = True
            self.step4_status.setText(
                Localizer.get().onekey_translation_complete_continue_post_processing_apply_game
            )
            self.step4_status.setStyleSheet("color: #27ae60;")
            self.start_trans_btn.setText(
                Localizer.get().onekey_translate_again
            )
            self.start_trans_btn.setEnabled(True)
            self.skip_trans_btn.setText(
                Localizer.get().onekey_continue_post_processing
            )
            return
        self.start_trans_btn.setText(
            Localizer.get().onekey_start_translation
        )
        self.skip_trans_btn.setText(
            Localizer.get().onekey_skip_translation
        )
        self._refresh_step4_ready()

    def _refresh_step4_ready(self) -> bool:
        """检查翻译前的必备配置"""
        from module.Config import Config
        cfg = Config().load()

        missing: list[str] = []
        input_dir = Path(cfg.input_folder) if cfg.input_folder else None
        output_dir = Path(cfg.output_folder) if cfg.output_folder else None

        if not input_dir or not input_dir.exists():
            missing.append(
                Localizer.get().onekey_input_folder_missing_does_not_exist
            )
        if not output_dir:
            missing.append(
                Localizer.get().onekey_output_folder_not_configured
            )
        elif input_dir and output_dir and input_dir.exists():
            try:
                if output_dir.resolve() == input_dir.resolve():
                    missing.append(
                        Localizer.get().onekey_input_output_folders_must_different
                    )
            except Exception:
                pass
        if output_dir and not output_dir.exists():
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                missing.append(
                    Localizer.get().onekey_output_folder_could_not_created
                )

        platform_ready = False
        if cfg.platforms:
            for p in cfg.platforms:
                if p.get("id") == cfg.activate_platform:
                    platform_ready = True
                    break
        if not platform_ready:
            missing.append(
                Localizer.get().onekey_no_translation_provider_active
            )

        ready = len(missing) == 0
        if ready:
            self.step4_status.setText(
                Localizer.get().onekey_ready_translate_2
            )
            self.step4_status.setStyleSheet("color: #27ae60;")
            self.start_trans_btn.setEnabled(True)
        else:
            self.step4_status.setText(
                Localizer.get().onekey_complete_following_setup_first
                + "\n".join(missing)
            )
            self.step4_status.setStyleSheet("color: #e67e22;")
            self.start_trans_btn.setEnabled(False)
        return ready
    
    def _go_previous_step(self, current_step: int):
        """返回上一步"""
        if (
            self._preprocess_worker
            and self._preprocess_worker.isRunning()
        ) or (
            self.extraction_worker
            and self.extraction_worker.isRunning()
        ):
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.get().onekey_extraction_already_running_wait_finish,
                parent=self,
            )
            return
        if current_step <= 1:
            # 步骤1返回到工具箱
            self._exit_wizard()
        else:
            # 返回上一步
            self.current_step = current_step - 1
            self.stacked.setCurrentIndex(current_step - 2)  # index 从 0 开始
        
    def _exit_wizard(self):
        """退出向导，返回工具箱页面"""
        self._invalidate_step2_run()
        if self.window:
            self.window.navigate_back_to_toolbox()
        
        # 重置状态（为下次使用做准备）
        self.current_step = 1
        self.stacked.setCurrentIndex(0)
        self._onekey_translation_completed = False
        self._start_translation_after_extraction = False
        self._agent_direct_start = False
        self.step1_next_btn.setEnabled(False)
        self.skip_extract_btn.setVisible(False)
        self.game_path = ""
        self.game_dir = ""
        self.game_path_edit.clear()
        self.path_status_label.setText("")
        self.old_translation_card.setVisible(False)
        self.has_old_translation = False
        
    # 工具函数
    def _tool_apply_translation(self, card, feedback_parent=None):
        """应用翻译：将输出目录的文件复制到 tl 目录"""
        from module.Config import Config
        import shutil
        from qfluentwidgets import MessageBox
        from pathlib import Path
        
        ui_parent = feedback_parent or self
        config = Config().load()

        tl_name = self.tl_folder_edit.text().strip() or "chinese"
        project_paths = (
            RenpyProjectPaths.from_path(self.game_dir, tl_name)
            if self.game_dir
            else RenpyProjectPaths.from_config(config, tl_name)
        )

        # 一键向导的项目路径优先于可变全局配置，避免其他页面改写
        # config.output_folder/input_folder 后把翻译应用到另一项目。
        incremental_output = self._incremental_output_dir
        if incremental_output:
            output_dir = Path(incremental_output)
            target_value = self._apply_target_dir or (
                project_paths.application_target_dir
                if project_paths is not None
                else None
            )
            input_dir = Path(target_value) if target_value else None
        elif project_paths is not None:
            output_dir = project_paths.translation_output_dir
            input_dir = project_paths.application_target_dir
        else:
            output_dir, input_dir = resolve_translation_apply_paths(
                config, None, None
            )
        
        if not output_dir.exists():
            InfoBar.error(
                Localizer.get().error,
                Localizer.get().onekey_output_folder_does_not_exist.format(output_dir=output_dir),
                parent=ui_parent,
            )
            return
        
        if input_dir is None or not input_dir.exists():
            InfoBar.error(
                Localizer.get().error,
                Localizer.get().onekey_target_folder_does_not_exist.format(input_dir=input_dir),
                parent=ui_parent,
            )
            return
        
        # 统计文件
        output_files = list(output_dir.rglob("*.rpy"))
        if not output_files:
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.get().onekey_output_folder_does_not_contain_translation_files,
                parent=ui_parent,
            )
            return
        
        # 确认对话框 - 根据主题选择样式颜色
        code_bg = "#2d2d2d" if isDarkTheme() else "#f5f5f5"
        warn_color = "#e67e22" if isDarkTheme() else "#d35400"
        
        msg_box = MessageBox(
            Localizer.get().onekey_confirm_translation_application,
            Localizer.get().onekey_b_apply_translation_game_b_br_br.format(code_bg=code_bg, output_dir=output_dir, input_dir=input_dir, output_files_count=len(output_files), warn_color=warn_color),
            ui_parent
        )
        msg_box.yesButton.setText(
            Localizer.get().onekey_apply_translation
        )
        msg_box.cancelButton.setText(Localizer.get().app_update_cancel)
        
        if not msg_box.exec():
            return
        
        # 防重入：应用进行中不允许再次触发（乱点会导致重复合并/卡死）。
        if getattr(self, "_apply_running", False):
            InfoBar.warning(
                Localizer.get().onekey_applying_translation,
                Localizer.get().onekey_translation_already_being_applied_please_wait,
                parent=ui_parent,
            )
            return
        self._apply_running = True
        if card is not None and hasattr(card, "setEnabled"):
            card.setEnabled(False)

        if incremental_output:
            # 增量文件只包含部分条目，必须通过语义合并写回，不能整文件覆盖主 TL。
            main_output = (
                project_paths.translation_output_dir
                if project_paths is not None
                else output_dir.parent / tl_name
            )
            staging_input = getattr(self, "_incremental_dir", None)
            worker = ApplyTranslationWorker(
                self.unified_extractor,
                incremental_mode=True,
                game_dir=self.game_dir,
                tl_name=tl_name,
                output_dir=output_dir,
                main_output=main_output,
                incremental_dir=staging_input,
                config=config,
            )
        else:
            # 全量翻译按批次应用；任一文件失败就恢复本批次已覆盖的目标。
            worker = ApplyTranslationWorker(
                self.unified_extractor,
                incremental_mode=False,
                output_dir=output_dir,
                input_dir=input_dir,
                output_files=output_files,
                config=config,
                project_root=(
                    project_paths.project_root if project_paths is not None else None
                ),
                project_language=(
                    project_paths.language if project_paths is not None else None
                ),
            )

        progress_dialog = QProgressDialog(
            Localizer.get().onekey_applying_translation_game,
            None,
            0,
            100,
            ui_parent,
        )
        progress_dialog.setWindowTitle(
            Localizer.get().onekey_apply_translation
        )
        progress_dialog.setWindowModality(Qt.ApplicationModal)
        progress_dialog.setCancelButton(None)
        progress_dialog.setMinimumDuration(0)
        progress_dialog.setValue(0)
        progress_dialog.show()

        # 用页面绑定方法接收信号，保证跨线程排队投递到 UI 线程。
        self._apply_card = card
        self._apply_parent = ui_parent
        self._apply_project_paths = project_paths
        self._apply_progress_dialog = progress_dialog
        worker.progress.connect(self._on_apply_progress)
        worker.finished.connect(self._on_apply_finished)
        self._apply_worker = worker
        worker.start()

    def _on_apply_progress(self, msg: str, pct: int) -> None:
        """后台进度信号：更新进度对话框（运行在 UI 线程）。"""
        dialog = getattr(self, "_apply_progress_dialog", None)
        if dialog is not None:
            dialog.setLabelText(str(msg))
            dialog.setValue(int(pct))

    def _on_apply_finished(self, success: bool, msg: str, payload: dict | None):
        """后台应用结束后回到 UI 线程：恢复入口、展示结果、接续 hook。"""
        card = getattr(self, "_apply_card", None)
        ui_parent = getattr(self, "_apply_parent", None)
        project_paths = getattr(self, "_apply_project_paths", None)
        progress_dialog = getattr(self, "_apply_progress_dialog", None)
        self._apply_running = False
        self._apply_worker = None
        self._apply_card = None
        self._apply_parent = None
        self._apply_project_paths = None
        self._apply_progress_dialog = None
        if card is not None and hasattr(card, "setEnabled"):
            card.setEnabled(True)
        if progress_dialog is not None:
            progress_dialog.close()

        if success:
            if payload:
                if payload.get("main_output"):
                    self._last_onekey_output_dir = Path(payload["main_output"])
                    self._incremental_dir = None
                    self._incremental_output_dir = None
                    self._apply_target_dir = None
                elif payload.get("count") is not None and project_paths is not None:
                    self._last_onekey_output_dir = project_paths.translation_output_dir
            InfoBar.success(
                Localizer.get().onekey_translation_applied,
                msg,
                duration=5000,
                parent=ui_parent,
            )
            if self._onekey_translation_started and self._auto_hook_pending:
                self._auto_hook_pending = False
                QTimer.singleShot(
                    0,
                    lambda paths=project_paths: self._start_auto_hook_supplement(
                        paths,
                    ),
                )
            elif self._onekey_translation_started:
                self._reset_auto_hook_state()
            return

        if payload and payload.get("warning"):
            InfoBar.warning(
                Localizer.get().notice,
                msg,
                parent=ui_parent,
            )
        else:
            InfoBar.error(
                Localizer.get().error,
                msg,
                parent=ui_parent,
            )

    def _tool_hook_supplement(self, card):
        """打开补全漏翻页面，并沿用当前项目上下文。"""
        try:
            if self.game_dir:
                self._sync_game_dir_to_config(self.game_dir)
            self.window.navigate_to_page(self._get_tool_page("hook_supplement"))
        except Exception as e:
            self.logger.error(f"打开补全翻译页面失败: {e}")
            InfoBar.error(
                Localizer.get().error,
                Localizer.get().onekey_could_not_open_missed_text_recovery.format(e=e),
                parent=self,
            )
    
    def _tool_fix_errors(self, card):
        """打开错误修复页面，并预填当前项目的 game 目录。"""
        try:
            page = self._get_tool_page("error_repair")
            if self.game_dir and hasattr(page, "game_dir_edit"):
                project_path = Path(self.game_dir)
                game_path = (
                    project_path
                    if project_path.name.casefold() == "game"
                    else project_path / "game"
                )
                page.game_dir_edit.setText(str(game_path))
            self.window.navigate_to_page(page)
        except Exception as exc:
            self.logger.error(f"打开错误修复页面失败: {exc}")
            InfoBar.error(
                Localizer.get().error,
                Localizer.get().onekey_could_not_open_error_repair.format(exc=exc),
                parent=self,
            )

    def _tool_set_default_lang(self, card):
        page = self._get_tool_page("set_default_language")
        if self.game_dir and hasattr(page, "project_dir_edit"):
            page.project_dir_edit.setText(self.game_dir)
        self.window.navigate_to_page(page)

    def _tool_add_lang_switch(self, card):
        page = self._get_tool_page("add_language")
        if self.game_dir and hasattr(page, "game_dir_edit"):
            project_path = Path(self.game_dir)
            game_dir = project_path if project_path.name.casefold() == "game" else project_path / "game"
            page.game_dir_edit.setText(str(game_dir))
        self.window.navigate_to_page(page)

    def _tool_replace_font(self, card):
        page = self._get_tool_page("font_replace")
        if self.game_dir and hasattr(page, "game_dir_edit"):
            page.game_dir_edit.setText(self.game_dir)
        self.window.navigate_to_page(page)

    def _tool_open_game_dir(self, card):
        if self.game_dir:
            os.startfile(self.game_dir)

    def _tool_open_proofreading(self, card):
        """打开检查与润色页面。"""
        del card
        if self.window is None:
            return
        page = self._get_tool_page("proofreading")
        self.window.navigate_to_page(page)
            
    def _tool_export_patch(self, card):
        """生成当前项目的漏翻补丁。"""
        try:
            if not self.game_dir:
                InfoBar.warning(
                    Localizer.get().notice,
                    Localizer.get().onekey_select_game_folder_first_2,
                    parent=self,
                )
                return
            tl_name = self.tl_folder_edit.text().strip() or "chinese"
            patch_path, missing_count = generate_patch(self.game_dir, tl_name)
            if patch_path is None:
                InfoBar.info(
                    Localizer.get().notice,
                    Localizer.get().onekey_no_missing_translations_found_patch_not_needed,
                    parent=self,
                )
                return
            InfoBar.success(
                Localizer.get().onekey_export_complete,
                Localizer.get().onekey_created_missing_translation_patch_entries.format(patch_path=patch_path, missing_count=missing_count),
                parent=self,
                duration=5000,
            )
        except Exception as exc:
            self.logger.error(f"导出语言补丁失败: {exc}")
            InfoBar.error(
                Localizer.get().error,
                Localizer.get().onekey_could_not_export_language_patch.format(exc=exc),
                parent=self,
            )
    
    def _tool_view_glossary(self, card):
        self._open_local_glossary()


# 兼容旧引用
OneKeyTranslatePage = YiJianFanyiPage
__all__ = ["YiJianFanyiPage", "OneKeyTranslatePage"]
