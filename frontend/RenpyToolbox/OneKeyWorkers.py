"""一键翻译页的后台线程：文本提取与应用翻译。

从 OneKeyTranslatePage 外移的 QThread（行为零变化），信号签名与构造参数
保持原样，页面模块继续 re-export 以兼容既有 import。
"""

import os
import shutil
import tempfile
import time
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal

from base.BaseLanguage import BaseLanguage
from module.Cache.CacheManager import CacheManager
from module.Renpy.ProjectPaths import RenpyProjectPaths, apply_to_config, write_run_manifest
from module.Renpy.renpy_tl_core import parse_tl_document, tl_block_kind_name
from module.Renpy.renpy_tl_io import RenpyTlItemExtractor

from base.LogManager import LogManager
from module.Localizer.Localizer import Localizer


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
