"""
YiJianFanyiPage - 一键翻译向导页面
向导式分步骤流程：每次只显示一个进度页面，完成后自动进入下一步
"""

import os
import shutil
import tempfile
import time
from pathlib import Path
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFileDialog,
    QStackedWidget,
    QSizePolicy,
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
    write_run_manifest,
)
from module.Engine.Translator.ProjectAssetsRepository import ProjectAssetsRepository
from module.Cache.CacheManager import CacheManager
from module.Config import Config
from module.Renpy.renpy_tl_core import parse_tl_document, tl_block_kind_name
from module.Renpy.renpy_tl_io import RenpyTlItemExtractor
from module.Workbench.CharacterScanner import CharacterCandidate, CharacterScanner
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
        return (
            "renpy-ast",
            str(item.get_file_path() or ""),
            lang,
            label,
            template_digest,
            template_line - header_line,
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
    return (
        str(item.get_file_path() or ""),
        lang,
        label,
        template_digest,
        template_line - header_line,
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
                lambda msg, pct: self.progress.emit(msg, pct)
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
            
            self.finished.emit(result.success, result.message, result)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.finished.emit(False, str(e), None)
        finally:
            self.unified_extractor.set_progress_callback(None)

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
        self.has_old_translation = False  # 是否检测到旧翻译
        self.incremental_mode = False     # 是否使用增量抽取
        self._ner_model = None            # 懒加载的 NER 模型
        self._ner_model_loaded = False
        # 一键翻译结束后，按需串起“自动补全漏翻”流程
        self._onekey_translation_started = False
        self._auto_hook_pending = False
        self._auto_hook_running = False
        self._incremental_dir = None
        self._incremental_output_dir = None
        self._apply_target_dir = None
        self._last_onekey_output_dir = None
        # 自动 hook 临时把配置指向 game/tl；完成后恢复主输出，但保留
        # 最近运行清单指向 hook 缓存，供校对页继续载入。
        self._hook_restore_paths = None
        
        self._init_ui()
        self.subscribe(Base.Event.TRANSLATION_DONE, self._on_translation_done)
        self.subscribe(Base.Event.TRANSLATION_STOP, self._on_translation_stop)
    
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
            back_btn.setToolTip("返回工具箱")
            back_btn.clicked.connect(self._exit_wizard)
        else:
            back_btn.setToolTip("返回上一步")
            # 使用 lambda 捕获当前 step 值
            back_btn.clicked.connect(lambda checked, s=step: self._go_previous_step(s))
        header_layout.addWidget(back_btn)
        
        title_label = TitleLabel(f"步骤 {step}/5：{title}")
        header_layout.addWidget(title_label)
        header_layout.addStretch(1)
        
        if step > 1:
            exit_btn = PushButton("退出向导")
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
        page, layout = self._create_page_container("选择游戏", 1)
        
        # 提示文字 - 更友好的说明
        tip_card = CardWidget()
        tip_layout = QVBoxLayout(tip_card)
        tip_layout.setContentsMargins(12, 12, 12, 12)
        tip_layout.setSpacing(6)
        
        tip_title = StrongBodyLabel("💡 小白指南")
        tip_layout.addWidget(tip_title)
        
        tip_text = CaptionLabel(
            "1. 选择游戏目录（包含 game 文件夹的那个）\n"
            "2. 点击「开始提取文本」自动抽取翻译\n"
            "3. 完成后点击「开始翻译」即可\n"
            "💬 如果之前翻译过，会自动保留已有翻译"
        )
        tip_text.setStyleSheet("color: #666; line-height: 1.5;")
        tip_text.setWordWrap(True)
        tip_layout.addWidget(tip_text)
        layout.addWidget(tip_card)
        
        # 游戏路径输入框（支持直接粘贴）
        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        
        self.game_path_edit = LineEdit()
        self.game_path_edit.setPlaceholderText("输入或粘贴游戏目录路径，例如: D:\\Games\\MyGame")
        self.game_path_edit.textChanged.connect(self._on_path_text_changed)
        path_row.addWidget(self.game_path_edit, 1)
        
        self.browse_btn = PushButton("浏览...")
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
        
        self.old_trans_title = StrongBodyLabel("🔍 检测到已有翻译")
        old_trans_layout.addWidget(self.old_trans_title)
        
        self.old_trans_desc = CaptionLabel("该游戏已有翻译文件，请选择处理方式：")
        self.old_trans_desc.setWordWrap(True)
        old_trans_layout.addWidget(self.old_trans_desc)

        # 选项文本采用“短标题 + 说明”两行布局，避免窗口较窄时勾选框文本重叠
        self.incremental_rb = CheckBox("增量抽取（推荐）")
        self.incremental_rb.setChecked(True)
        old_trans_layout.addWidget(self.incremental_rb)
        incremental_desc = CaptionLabel("保留已有翻译，抽取新增内容 + 未翻译占位")
        incremental_desc.setWordWrap(True)
        incremental_desc.setStyleSheet("padding-left: 28px; color: #666;")
        old_trans_layout.addWidget(incremental_desc)

        self.full_extract_rb = CheckBox("完整抽取（重做全量）")
        self.full_extract_rb.setChecked(False)
        self.full_extract_rb.setToolTip("会把 tl/<lang> 备份后重新生成，占位会被重置，慎用")
        old_trans_layout.addWidget(self.full_extract_rb)
        full_extract_desc = CaptionLabel("备份旧翻译后重新抽取全部内容，仅在需要推倒重做时使用")
        full_extract_desc.setWordWrap(True)
        full_extract_desc.setStyleSheet("padding-left: 28px; color: #666;")
        old_trans_layout.addWidget(full_extract_desc)
        
        tip_label = CaptionLabel("小提示：默认选择增量抽取，避免覆盖已有翻译；完整抽取只在重做全量时使用。")
        tip_label.setWordWrap(True)
        old_trans_layout.addWidget(tip_label)

        self.auto_merge_cleanup_chk = CheckBox("抽取后自动合并并清理重复")
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

        options_title = StrongBodyLabel("高级选项")
        options_layout.addWidget(options_title)

        from module.Config import Config
        config = Config().load()

        self.inject_base_box_chk = CheckBox("注入 UI 翻译包（base_box）")
        self.inject_base_box_chk.setChecked(getattr(config, "onekey_inject_base_box", False))
        self.inject_base_box_chk.setToolTip(
            "自动注入预置的 UI 翻译（开始、保存、设置等）。\n"
            "如果你已有自定义 UI 翻译，请取消勾选。"
        )
        self.inject_base_box_chk.stateChanged.connect(self._on_inject_base_box_changed)
        options_layout.addWidget(self.inject_base_box_chk)

        self.extract_compiled_chk = CheckBox("提取 .pyc 编译字符串到标准翻译（translate strings）")
        self.extract_compiled_chk.setChecked(getattr(config, "extract_use_compiled", True))
        self.extract_compiled_chk.setToolTip(
            "把随包 .pyc 中玩家可见的常量（如 WIP 提示、短信、任务文本）写成标准\n"
            "old/new 翻译块，而不是留给 replace_text 补全钩子。"
        )
        self.extract_compiled_chk.stateChanged.connect(self._on_extract_compiled_changed)
        options_layout.addWidget(self.extract_compiled_chk)

        layout.addWidget(options_card)

        layout.addSpacing(20)        # 语言设置（简化）
        layout.addWidget(SubtitleLabel("翻译语言设置"))
        
        lang_row = QHBoxLayout()
        lang_row.setSpacing(20)
        
        # 源语言
        src_layout = QVBoxLayout()
        src_layout.setSpacing(4)
        src_layout.addWidget(CaptionLabel("游戏原语言"))
        self.src_lang_combo = ComboBox()
        self.src_lang_combo.addItems(["英语", "日语", "韩语", "俄语", "其他"])
        self.src_lang_combo.setFixedWidth(150)
        src_layout.addWidget(self.src_lang_combo)
        lang_row.addLayout(src_layout)
        
        # 目标语言
        tgt_layout = QVBoxLayout()
        tgt_layout.setSpacing(4)
        tgt_layout.addWidget(CaptionLabel("翻译成"))
        self.tgt_lang_combo = ComboBox()
        self.tgt_lang_combo.addItems(["简体中文", "繁体中文", "日语", "英语"])
        self.tgt_lang_combo.setFixedWidth(150)
        tgt_layout.addWidget(self.tgt_lang_combo)
        lang_row.addLayout(tgt_layout)
        
        # TL 文件夹名（折叠/隐藏给高级用户）
        tl_layout = QVBoxLayout()
        tl_layout.setSpacing(4)
        tl_layout.addWidget(CaptionLabel("TL 文件夹名"))
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
        self.quick_tip_label = CaptionLabel("直接点击“开始提取文本”即可，完成后进入翻译。如果已有翻译，默认会保留。")
        self.quick_tip_label.setWordWrap(True)
        layout.addWidget(self.quick_tip_label)
        
        # 跳过抽取按钮（已有翻译时显示）
        self.skip_extract_btn = PushButton("跳过抽取，直接翻译 →")
        self.skip_extract_btn.clicked.connect(self._skip_to_translate)
        self.skip_extract_btn.setVisible(False)  # 默认隐藏，检测到翻译后显示
        next_row.addWidget(self.skip_extract_btn)
        
        self.step1_next_btn = PrimaryPushButton("开始提取文本 →")
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
                self.path_status_label.setText("✓ 检测到有效的 Ren'Py 游戏目录")
                self.path_status_label.setStyleSheet("color: #27ae60;")
                self.step1_next_btn.setEnabled(True)
                # 检测旧翻译
                self._check_old_translation(self.game_dir)
            else:
                self.path_status_label.setText("⚠ 目录中未找到 game 文件夹，可能不是 Ren'Py 游戏")
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
            self.path_status_label.setText("✓ 已选择游戏文件")
            self.path_status_label.setStyleSheet("color: #27ae60;")
            self.step1_next_btn.setEnabled(True)
            # 检测旧翻译
            self._check_old_translation(self.game_dir)
        else:
            self.path_status_label.setText("✗ 路径不存在")
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
            self.old_trans_title.setText(f"🔍 检测到已有翻译 ({rpy_count} 个文件)")
            self.old_trans_desc.setText(f"该游戏在 tl/{tl_name} 中已有翻译文件，请选择处理方式：")
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
        page, layout = self._create_page_container("提取文本", 2)
        
        layout.addStretch(1)
        
        self.step2_status = TitleLabel("准备开始提取...")
        self.step2_status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.step2_status)
        
        self.step2_desc = BodyLabel("正在从游戏中提取文本并生成翻译文件，请稍候。完成后点击“开始翻译”进入下一步，随时可重新抽取。")
        self.step2_desc.setAlignment(Qt.AlignCenter)
        self.step2_desc.setWordWrap(True)
        layout.addWidget(self.step2_desc)
        
        layout.addStretch(1)
        
        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        
        # 重试按钮 (默认隐藏，失败后显示)
        self.step2_retry_btn = PushButton("重新抽取")
        self.step2_retry_btn.clicked.connect(self._retry_extraction)
        self.step2_retry_btn.setVisible(False)
        btn_row.addWidget(self.step2_retry_btn)

        self.step2_unpack_btn = PrimaryPushButton(
            "前往 RPA 解包",
            icon=FluentIcon.ZIP_FOLDER,
        )
        self.step2_unpack_btn.clicked.connect(self._open_rpa_unpack)
        self.step2_unpack_btn.setVisible(False)
        btn_row.addWidget(self.step2_unpack_btn)
        
        # 跳过按钮 (失败时可跳过)
        self.step2_skip_btn = PushButton("跳过此步骤")
        self.step2_skip_btn.clicked.connect(self._go_step3)
        self.step2_skip_btn.setVisible(False)
        btn_row.addWidget(self.step2_skip_btn)
        
        # 下一步按钮 (默认隐藏，完成后显示)
        self.step2_next_btn = PrimaryPushButton("下一步 →")
        self.step2_next_btn.clicked.connect(self._go_step3)
        self.step2_next_btn.setVisible(False)
        btn_row.addWidget(self.step2_next_btn)

        self.step2_merge_btn = PushButton("合并并清理重复")
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
            InfoBar.warning("提示", "请先选择有效的游戏目录", parent=self)
            return

        page = self._get_tool_page("pack_unpack")

        if not page.set_game_directory(self.game_dir):
            InfoBar.warning("提示", "无法定位游戏的 game 目录", parent=self)
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

    def _merge_incremental_dir(self):
        """合并增量目录并清理重复"""
        try:
            # 新流程必须先翻译到独立输出目录，再由“应用翻译”语义合并。
            # 禁止旧入口提前合并并删除仍作为翻译输入的 chinese_new。
            if self._incremental_output_dir:
                InfoBar.warning(
                    "请先完成翻译",
                    "当前增量内容尚未应用，请完成翻译后返回工具箱，点击“应用翻译到游戏”。",
                    parent=self,
                )
                return
            if not self.game_dir:
                InfoBar.warning("提示", "请先选择游戏目录", parent=self)
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
                InfoBar.success("合并完成", result.message, parent=self)
            else:
                InfoBar.warning("合并失败", result.message, parent=self)
        except Exception as exc:
            self.logger.error(f"合并失败: {exc}")
            InfoBar.error("错误", str(exc), parent=self)
    
    # ==================== 进度三：术语表 ====================
    def _create_step3_page(self):
        """进度三：项目资产与术语表。"""
        page, layout = self._create_page_container("术语与翻译上下文", 3)
        
        layout.addWidget(SubtitleLabel("术语表与禁翻表"))
        layout.addWidget(BodyLabel("术语表可以帮助你统一专有名词的翻译，禁翻表可以防止翻译不需要翻译的内容。本地词库页还支持手动扫描术语候选。"))
        
        layout.addSpacing(16)
        
        self.glossary_info_label = BodyLabel("正在查找项目中的术语表...")
        layout.addWidget(self.glossary_info_label)
        
        layout.addSpacing(16)
        
        btn_row = QHBoxLayout()
        self.open_glossary_btn = PushButton("📂 打开本地词库管理")
        self.open_glossary_btn.setToolTip("可在本地词库页手动执行“扫描术语候选”，补齐角色名之外的正文专名")
        self.open_glossary_btn.clicked.connect(self._open_local_glossary)
        btn_row.addWidget(self.open_glossary_btn)
        
        self.open_preserve_btn = PushButton("🚫 打开禁翻表管理")
        self.open_preserve_btn.clicked.connect(self._open_text_preserve)
        btn_row.addWidget(self.open_preserve_btn)
        
        self.scan_names_btn = PushButton("🔍 自动提取角色名")
        self.scan_names_btn.clicked.connect(self._scan_character_names)
        btn_row.addWidget(self.scan_names_btn)

        self.open_workbench_btn = PushButton("🎭 打开角色/世界观工作台")
        self.open_workbench_btn.setToolTip("维护世界观和角色卡；翻译开始时会生成不可变上下文快照")
        self.open_workbench_btn.clicked.connect(self._open_workbench_from_onekey)
        btn_row.addWidget(self.open_workbench_btn)
        
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.workbench_asset_status = BodyLabel("正在读取项目资产…")
        self.workbench_asset_status.setWordWrap(True)
        layout.addWidget(self.workbench_asset_status)
        
        layout.addStretch(1)
        
        next_row = QHBoxLayout()
        next_row.addStretch(1)
        self.step3_next_btn = PrimaryPushButton("下一步 (开始翻译) →")
        self.step3_next_btn.clicked.connect(self._go_step4)
        next_row.addWidget(self.step3_next_btn)
        layout.addLayout(next_row)
        
        self.step3_page = page
        self.stacked.addWidget(page)
    
    # ==================== 进度四：开始翻译 ====================
    def _create_step4_page(self):
        """进度四：开始翻译"""
        page, layout = self._create_page_container("执行 AI 翻译", 4)
        
        layout.addWidget(SubtitleLabel("准备翻译"))
        self.step4_status = BodyLabel(
            "翻译文件将输出到游戏根目录下的独立文件夹，不会被引擎识别。\n"
            "完成后可在「后续处理」中应用到游戏。"
        )
        layout.addWidget(self.step4_status)
        
        layout.addSpacing(20)
        
        # 翻译按钮
        btn_row = QHBoxLayout()
        self.start_trans_btn = PrimaryPushButton("🚀 开始翻译")
        self.start_trans_btn.clicked.connect(self._on_start_translate_clicked)
        btn_row.addWidget(self.start_trans_btn)

        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        from module.Config import Config
        auto_hook_row = QHBoxLayout()
        self.auto_hook_supplement_chk = CheckBox("翻译完成后自动补全漏翻（replace_text）")
        self.auto_hook_supplement_chk.setChecked(
            getattr(Config().load(), "onekey_auto_hook_supplement", False)
        )
        self.auto_hook_supplement_chk.setToolTip(
            "默认关闭。\n"
            "开启后，主翻译完成会自动再跑一轮补全漏翻，生成/翻译 replace_text_auto.rpy。"
        )
        self.auto_hook_supplement_chk.stateChanged.connect(self._on_auto_hook_supplement_changed)
        auto_hook_row.addWidget(self.auto_hook_supplement_chk)
        auto_hook_row.addStretch(1)
        layout.addLayout(auto_hook_row)
        
        layout.addStretch(1)
        
        # 底部按钮
        action_row = QHBoxLayout()
        action_row.addStretch(1)
        
        self.skip_trans_btn = PushButton("跳过翻译 →")
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
        page, layout = self._create_page_container("检查、导出与后处理", 5)
        
        layout.addWidget(SubtitleLabel("🎉 翻译已完成"))
        layout.addWidget(BodyLabel("可继续检查、补全或导出翻译结果。"))
        layout.addWidget(
            CaptionLabel("如果切换到中文后仍有漏翻文本，优先使用“补全漏翻”生成 replace_text_auto.rpy。")
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
            ("检查、润色并导出", "查看质量报告，校对或润色选中译文，然后导出翻译文件", self._tool_open_proofreading),
            ("补全漏翻", "扫描 tl 未覆盖的文本并生成 replace_text_auto.rpy", self._tool_hook_supplement),
            ("检测/修复报错", "修复缩进和格式问题", self._tool_fix_errors),
            ("设置默认语言", "设置游戏启动时的默认语言", self._tool_set_default_lang),
            ("添加语言切换", "注入语言切换按钮", self._tool_add_lang_switch),
            ("批量注入字体", "注入预置字体包", self._tool_replace_font),
            ("打开游戏目录", "查看翻译结果", self._tool_open_game_dir),
            ("导出语言补丁", "导出 tl 目录为 zip", self._tool_export_patch),
        ]
        
        for title, desc, func in tools:
            flow_layout.addWidget(
                ItemCard(parent=self, title=title, description=desc, clicked=func)
            )
        
        scroll_layout.addWidget(flow_container)
        scroll_layout.addStretch(1)
        
        scroll_area.setWidget(scroll_widget)
        layout.addWidget(scroll_area)
        
        self.step5_page = page
        self.stacked.addWidget(page)

    # ==================== 逻辑处理 ====================
    
    def _select_game_dir(self):
        """浏览选择游戏目录"""
        dir_path = QFileDialog.getExistingDirectory(self, "选择游戏目录", "")
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
        
        game_path = Path(game_dir) / "game"
        if not game_path.exists():
            return 'empty', '未找到 game 目录'
        
        rpy_count = len(list(game_path.rglob("*.rpy")))
        rpyc_count = len(list(game_path.rglob("*.rpyc")))
        rpa_count = len(list(game_path.glob("*.rpa")))
        
        if rpa_count > 0 and rpy_count == 0 and rpyc_count == 0:
            return 'need_unpack', f'检测到 {rpa_count} 个 RPA 包，需要解包'
        
        if rpy_count == 0 and rpyc_count > 0:
            return 'need_decompile', f'检测到 {rpyc_count} 个 RPYC 文件，需要反编译'
        
        if rpy_count > 0 and rpyc_count > 0:
            return 'mixed', f'检测到 {rpy_count} 个 RPY 和 {rpyc_count} 个 RPYC 文件'
        
        if rpy_count > 0:
            return 'ready', f'检测到 {rpy_count} 个 RPY 文件，可直接提取'
        
        return 'empty', '未检测到可提取的文件'
    
    def _auto_decompile(self, game_dir: str) -> tuple:
        """
        自动执行反编译
        
        Returns:
            (success, message)
        """
        unren_error = None
        try:
            from pathlib import Path
            from module.Tool.Packer import Packer

            game_path = Path(game_dir)
            if game_path.name.lower() != "game":
                game_path = game_path / "game"

            ok, _lines = Packer().unpack_all_unren_bat(
                str(game_path),
                lang="zh",
                options="2x",
                purpose="反编译",
                timeout_s=60 * 60,
            )
            if ok:
                return True, "反编译完成 (UnRen)"
        except Exception as unren_exc:
            unren_error = unren_exc

        try:
            from module.Tool.RenpyDecompiler import RenpyDecompiler

            decompiler = RenpyDecompiler()
            decompiler.decompile(game_dir, overwrite=False)
            
            return True, "反编译完成 (unrpyc v2)"
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            if unren_error:
                return False, f"反编译失败（UnRen 失败：{unren_error}）：{e}"
            return False, f"反编译失败（可能版本不兼容/加密/脚本特殊）：{e}"
        
    def _go_step2(self):
        """进入步骤2并开始提取"""
        # 如果正在抽取中，避免重复启动线程
        if self.extraction_worker and self.extraction_worker.isRunning():
            InfoBar.warning("提示", "抽取正在进行中，请等待完成后再操作。", parent=self)
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
        self.step2_desc.setText("正在从游戏中提取文本并生成翻译文件，请稍候。")
        self.step2_page.progress_bar.setValue(0)
        
        # 启动提取线程
        game_dir = self.game_dir
        tl_name = self.tl_folder_edit.text().strip() or "chinese"
        
        exe_guess = Path(game_dir) / "game.exe"
        exe_path = exe_guess if exe_guess.exists() else game_dir
        if self.game_path and os.path.isfile(self.game_path) and self.game_path.endswith(".exe"):
             exe_path = self.game_path
        
        # ===== 新增：游戏预处理检测 =====
        self.step2_status.setText("🔍 检测游戏状态...")
        self.step2_page.progress_ring.setVisible(True)
        self.step2_page.progress_bar.setValue(5)
        
        status, status_msg = self._detect_game_status(game_dir)
        
        if status == 'need_decompile':
            self.step2_status.setText("🔨 正在反编译 RPYC 文件...")
            self.step2_desc.setText(status_msg + "\n正在自动执行反编译，请稍候...")
            self.step2_page.progress_bar.setValue(10)
            
            # 执行反编译
            success, decompile_msg = self._auto_decompile(game_dir)
            
            if not success:
                self.step2_page.progress_ring.setVisible(False)
                self.step2_status.setText("✗ 反编译失败")
                self.step2_desc.setText(
                    f"{decompile_msg}\n\n"
                    "可能的原因：\n"
                    "• 游戏使用了加密/混淆\n"
                    "• Ren'Py 版本不兼容\n"
                    "• 缺少游戏的 Python 运行时\n\n"
                    "建议：尝试使用其他反编译工具或联系开发者"
                )
                self.step2_retry_btn.setVisible(True)
                self.step2_skip_btn.setVisible(True)
                self.step2_retry_btn.setEnabled(True)
                self.step2_skip_btn.setEnabled(True)
                InfoBar.warning("提示", "反编译失败，请检查游戏文件", parent=self)
                return
            
            self.step2_desc.setText(decompile_msg)
            self.step2_page.progress_bar.setValue(20)
        
        elif status == 'need_unpack':
            self.step2_page.progress_ring.setVisible(False)
            self.step2_status.setText("📦 需要解包 RPA")
            self.step2_desc.setText(
                f"{status_msg}\n\n"
                "请先使用「RPA 解包」功能解包游戏资源，\n"
                "解包完成后返回此页，点击「重新抽取」。"
            )
            self.step2_unpack_btn.setVisible(True)
            self.step2_unpack_btn.setEnabled(True)
            self.step2_retry_btn.setVisible(True)
            self.step2_skip_btn.setVisible(True)
            self.step2_retry_btn.setEnabled(True)
            self.step2_skip_btn.setEnabled(True)
            InfoBar.warning("提示", "请先解包 RPA 资源", parent=self)
            return
        
        elif status == 'empty':
            self.step2_page.progress_ring.setVisible(False)
            self.step2_status.setText("✗ 未找到游戏文件")
            self.step2_desc.setText(status_msg)
            self.step2_retry_btn.setVisible(True)
            self.step2_retry_btn.setEnabled(True)
            self.step2_skip_btn.setVisible(False)
            self.step2_skip_btn.setEnabled(False)
            return
        
        # ===== 继续正常的提取流程 =====
        # 检测是否使用增量模式
        incremental = self.has_old_translation and self.incremental_rb.isChecked()
        
        if incremental:
            self.step2_status.setText("🔄 增量抽取中...")
        else:
            self.step2_status.setText("正在提取...")
        self.step2_page.progress_ring.setVisible(True)
        
        self.extraction_worker = ExtractionWorker(self.unified_extractor, game_dir, tl_name, exe_path, incremental=incremental)
        self.extraction_worker.progress.connect(self._on_extract_progress)
        self.extraction_worker.finished.connect(self._on_extract_finished)
        self.extraction_worker.start()
        
    def _on_extract_progress(self, msg, percent):
        self.step2_status.setText(msg)
        self.step2_page.progress_bar.setValue(percent)
        
    def _on_extract_finished(self, success, msg, result=None):
        self.step2_page.progress_ring.setVisible(False)
        if success:
            self.step2_status.setText("✓ 提取完成")
            tl_name = self.tl_folder_edit.text().strip() or "chinese"
            
            # 如果是增量抽取并且有单独的增量目录，显示更详细的信息
            if result and result.incremental_dir and result.incremental_dir.exists():
                detail_msg = (
                    f"{msg}\n\n"
                    f"💡 新增内容已输出到单独文件夹：{result.incremental_dir.name}/\n"
                    f"原有翻译保持不变，可分别处理新增内容。"
                )
                self._incremental_dir = result.incremental_dir
                # 暂存目录需要保留到翻译完成；提前合并会删除它，
                # 导致翻译页面回退到完整的主语言目录。
                from module.Config import Config
                config = Config().load()
                apply_target, delta_output = configure_incremental_translation_paths(
                    config, self.game_dir, tl_name, result.incremental_dir
                )
                preserved_output = preserve_incremental_translation_cache(delta_output)
                delta_output.mkdir(parents=True, exist_ok=True)
                config.save()
                self._apply_target_dir = apply_target
                self._incremental_output_dir = delta_output
                self._last_onekey_output_dir = delta_output
                detail_msg += (
                    f"\n增量翻译输入：{result.incremental_dir.name}/"
                    f"\n增量翻译输出：{delta_output.name}/"
                )
                if preserved_output is not None:
                    detail_msg += (
                        f"\n检测到上一轮增量缓存，已保存在：{preserved_output.name}/"
                        "（未删除，可手动恢复）"
                    )
            else:
                detail_msg = f'{msg}\n已保留占位（new==old），可直接进入翻译。需要更新术语/禁翻后可再次点击"重新抽取"。'
                self._incremental_dir = None
                self._incremental_output_dir = None
                self._apply_target_dir = None
                paths = RenpyProjectPaths.from_path(self.game_dir, tl_name)
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
            self.step2_next_btn.setText("开始翻译 →")
            # 增量暂存目录是后续翻译输入，翻译前不能通过旧按钮直接合并或删除。
            self.step2_merge_btn.setVisible(False)
            self.step2_merge_btn.setEnabled(False)
            
            # 自动执行角色名和禁翻表扫描（仅第一次执行，避免重复卡顿）
            self._extract_character_names()
            
            InfoBar.success("成功", "提取完成，已自动扫描角色名和变量引用", parent=self)
        else:
            self.step2_status.setText("✗ 提取遇到问题")
            self.step2_desc.setText(f'错误信息：{msg}\n\n建议先点"重新抽取"。如仍失败，可跳过直接翻译，或检查路径/权限后再试。')
            self.step2_retry_btn.setVisible(True)
            self.step2_skip_btn.setVisible(True)
            self.step2_retry_btn.setEnabled(True)
            self.step2_skip_btn.setEnabled(True)
            self.step2_next_btn.setVisible(False)
            self.step2_next_btn.setEnabled(False)
            self.step2_merge_btn.setVisible(False)
            self.step2_merge_btn.setEnabled(False)
            InfoBar.warning("提示", "提取过程遇到问题，你可以重试或跳过", parent=self)

    def _scan_character_names(self):
        """扫描角色候选并写入工作台，变量引用继续写入禁翻表。"""
        self._extract_character_names(force=True)
        InfoBar.success("成功", "已扫描角色候选(→角色工作台)和变量引用(→禁翻表)", parent=self)

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
                "当前项目资产："
                f"世界观{'已启用' if assets.worldbook_enabled else '未启用'}，"
                f"角色卡 {len(assets.character_cards)} 张，"
                f"术语 {len(assets.glossary)} 项，"
                f"禁翻 {len(assets.do_not_translate)} 项；"
                f"待确认术语候选 {len(candidates)} 项，"
                f"角色草稿 {len(character_drafts)} 张。"
            )
        except Exception as exc:
            label.setText(f"项目资产暂不可用：{exc}")

    def _open_workbench_from_onekey(self) -> None:
        """从一键流程打开工作台，并先同步当前项目路径。"""
        try:
            if self.game_dir:
                self._sync_game_dir_to_config(self.game_dir)
            page = getattr(self.window, "renpy_workbench_page", None)
            if page is None and hasattr(self.window, "findChild"):
                page = self.window.findChild(QWidget, "renpy_workbench_page")
            if page is None:
                InfoBar.warning("提示", "未找到角色/世界观工作台页面", parent = self)
                return
            if hasattr(page, "refresh_from_config"):
                page.refresh_from_config()
            self.window.navigate_to_page(page)
        except Exception as exc:
            self.logger.error(f"打开工作台失败：{exc}")
            InfoBar.error("错误", f"打开工作台失败：{exc}", parent = self)
        
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
            self.glossary_info_label.setText(f"找到文件: {', '.join(found_files)}")
        else:
            self.glossary_info_label.setText("未找到术语表文件，将使用默认配置。")

    def _open_local_glossary(self):
        page = self._get_tool_page("local_glossary")
        self.window.navigate_to_page(page)

    def _open_text_preserve(self):
        page = self._get_tool_page("text_preserve")
        self.window.navigate_to_page(page)

    def _go_step4(self):
        self.current_step = 4
        self.stacked.setCurrentIndex(3)
        self._refresh_step4_ready()
    
    def _on_start_translate_clicked(self):
        """检查配置后再进入翻译面板"""
        if not self._refresh_step4_ready():
            InfoBar.warning("提示", "请先在接口设置激活翻译平台，并在项目设置填写输入/输出目录。", parent=self)
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
            "📁 翻译目录说明",
            f"<b>输入目录</b>（待翻译文件）：<br>"
            f"<code style='background:{code_bg};padding:2px 4px;'>{config.input_folder}</code><br><br>"
            f"<b>输出目录</b>（翻译结果）：<br>"
            f"<code style='background:{code_bg};padding:2px 4px;'>{config.output_folder}</code><br><br>"
            f"<p style='color:{hint_color};'><i>💡 输出目录位于游戏根目录下，不会被 Ren'Py 引擎识别。<br>"
            f"翻译完成后，可在「后续处理」中应用到游戏。</i></p>",
            self
        )
        msg_box.yesButton.setText("开始翻译")
        msg_box.cancelButton.setText("取消")
        
        if msg_box.exec():
            self._onekey_translation_started = True
            self._auto_hook_pending = self.auto_hook_supplement_chk.isChecked()
            self._auto_hook_running = False
            self._open_legacy_translation_page()

    def _on_auto_hook_supplement_changed(self, state):
        """保存一键翻译后的自动补漏开关。"""
        try:
            from module.Config import Config

            config = Config().load()
            config.onekey_auto_hook_supplement = bool(state)
            config.save()
        except Exception as e:
            self.logger.warning(f"保存自动补全漏翻配置失败: {e}")
        
    def _open_legacy_translation_page(self):
        """打开传统翻译页面，保留续翻译能力"""
        try:
            if not self.window:
                raise RuntimeError("未找到主窗口，无法打开翻译面板")

            page = getattr(self.window, "translation_page", None)
            if page is None:
                page = TranslationPage("translation_page", self.window)
                self.window.translation_page = page
            self.window.navigate_to_page(page)
        except Exception as e:
            LogManager.get().error(f"打开传统翻译面板失败: {e}")
            InfoBar.error("错误", f"打开传统翻译面板失败: {e}", parent=self)
        
    def _go_step5(self):
        self.current_step = 5
        self.stacked.setCurrentIndex(4)
        self.step5_page.progress_bar.setValue(100)

    def _start_auto_hook_supplement(self):
        """主翻译完成后自动执行补全漏翻。"""
        try:
            from module.Config import Config

            if not self.game_dir:
                self._reset_auto_hook_state()
                return

            tl_name = self.tl_folder_edit.text().strip() or "chinese"
            paths = RenpyProjectPaths.from_path(self.game_dir, tl_name)
            if paths is None:
                raise RuntimeError("无法解析当前 Ren'Py 项目路径")
            project_root = paths.project_root
            tl_dir = paths.tl_language_dir
            if not tl_dir.exists():
                InfoBar.warning("提示", f"未找到 tl 目录，已跳过自动补全：{tl_dir}", parent=self)
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

            self.emit(
                Base.Event.TRANSLATION_START,
                {
                    "config": config,
                    "status": Base.TranslationStatus.UNTRANSLATED,
                    "input_folder": str(tl_dir),
                    "output_folder": str(tl_dir),
                    "source_language": config.source_language,
                    "target_language": config.target_language,
                },
            )
            InfoBar.success("已开始", "主翻译完成，正在自动补全漏翻…", parent=self)
        except Exception as e:
            self.logger.error(f"自动补全漏翻启动失败: {e}")
            InfoBar.error("错误", f"自动补全漏翻启动失败: {e}", parent=self)
            self._restore_paths_after_auto_hook()
            self._reset_auto_hook_state()

    def _reset_auto_hook_state(self):
        """重置自动补全漏翻相关状态。"""
        self._onekey_translation_started = False
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

    def _on_translation_done(self, event, data):
        """监听翻译完成，按需接续 replace_text 补漏。"""
        payload = data if isinstance(data, dict) else {}
        failed = payload.get("success") is False or payload.get("stopped") is True

        if self._auto_hook_running:
            self._restore_paths_after_auto_hook()
            self._reset_auto_hook_state()
            if failed:
                InfoBar.warning("已停止", "自动补全漏翻未完成，已恢复主翻译路径。", parent=self)
            else:
                InfoBar.success("完成", "自动补全漏翻完成", parent=self)
            return

        if self._onekey_translation_started and self._auto_hook_pending:
            # 主输出必须先由用户确认并应用到 game/tl，再扫描漏翻；否则全量
            # 输出尚未落地、增量输出尚未合并，都会以旧 TL 作为扫描依据。
            if failed:
                self._reset_auto_hook_state()
                return
            return

        if self._onekey_translation_started:
            self._reset_auto_hook_state()

    def _on_translation_stop(self, event, data):
        """翻译停止时清理一键翻译的自动补漏状态。"""
        if self._onekey_translation_started or self._auto_hook_pending or self._auto_hook_running:
            if self._auto_hook_running:
                self._restore_paths_after_auto_hook()
            self._reset_auto_hook_state()
    
    def _refresh_step4_ready(self) -> bool:
        """检查翻译前的必备配置"""
        from module.Config import Config
        cfg = Config().load()

        missing: list[str] = []
        input_dir = Path(cfg.input_folder) if cfg.input_folder else None
        output_dir = Path(cfg.output_folder) if cfg.output_folder else None

        if not input_dir or not input_dir.exists():
            missing.append("输入目录未设置或不存在")
        if not output_dir:
            missing.append("输出目录未设置")
        elif input_dir and output_dir and input_dir.exists():
            try:
                if output_dir.resolve() == input_dir.resolve():
                    missing.append("输入/输出目录不能相同")
            except Exception:
                pass
        if output_dir and not output_dir.exists():
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                missing.append("输出目录无法创建")

        platform_ready = False
        if cfg.platforms:
            for p in cfg.platforms:
                if p.get("id") == cfg.activate_platform:
                    platform_ready = True
                    break
        if not platform_ready:
            missing.append("未激活翻译接口（请在接口设置启用平台）")

        ready = len(missing) == 0
        if ready:
            self.step4_status.setText("✔ 已准备好翻译，可直接开始。")
            self.step4_status.setStyleSheet("color: #27ae60;")
            self.start_trans_btn.setEnabled(True)
        else:
            self.step4_status.setText("⚠ 需先完成配置：\n" + "\n".join(missing))
            self.step4_status.setStyleSheet("color: #e67e22;")
            self.start_trans_btn.setEnabled(False)
        return ready
    
    def _go_previous_step(self, current_step: int):
        """返回上一步"""
        if current_step <= 1:
            # 步骤1返回到工具箱
            self._exit_wizard()
        else:
            # 返回上一步
            self.current_step = current_step - 1
            self.stacked.setCurrentIndex(current_step - 2)  # index 从 0 开始
        
    def _exit_wizard(self):
        """退出向导，返回工具箱页面"""
        if self.window:
            self.window.navigate_back_to_toolbox()
        
        # 重置状态（为下次使用做准备）
        self.current_step = 1
        self.stacked.setCurrentIndex(0)
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
            InfoBar.error("错误", f"输出目录不存在：{output_dir}", parent=ui_parent)
            return
        
        if input_dir is None or not input_dir.exists():
            InfoBar.error("错误", f"目标目录不存在：{input_dir}", parent=ui_parent)
            return
        
        # 统计文件
        output_files = list(output_dir.rglob("*.rpy"))
        if not output_files:
            InfoBar.warning("提示", "输出目录中没有翻译文件（.rpy）", parent=ui_parent)
            return
        
        # 确认对话框 - 根据主题选择样式颜色
        code_bg = "#2d2d2d" if isDarkTheme() else "#f5f5f5"
        warn_color = "#e67e22" if isDarkTheme() else "#d35400"
        
        msg_box = MessageBox(
            "确认应用翻译",
            f"<b>即将应用翻译到游戏</b><br><br>"
            f"<b>源目录：</b><br><code style='background:{code_bg};padding:2px 4px;'>{output_dir}</code><br><br>"
            f"<b>目标目录：</b><br><code style='background:{code_bg};padding:2px 4px;'>{input_dir}</code><br><br>"
            f"<b>文件数量：</b>{len(output_files)} 个<br><br>"
            f"<p style='color:{warn_color};'><i>⚠️ 这将覆盖目标目录中的同名文件！<br>"
            f"建议先备份原始文件。</i></p>",
            ui_parent
        )
        msg_box.yesButton.setText("应用翻译")
        msg_box.cancelButton.setText("取消")
        
        if not msg_box.exec():
            return
        
        # 增量文件只包含部分条目，必须通过语义合并写回，不能整文件覆盖主 TL。
        if incremental_output:
            try:
                tl_name = self.tl_folder_edit.text().strip() or "chinese"
                merge_result = self.unified_extractor.merge_incremental_folder(
                    self.game_dir,
                    tl_name,
                    output_dir,
                    clean_duplicates=True,
                )
                if not merge_result.success:
                    InfoBar.warning("合并失败", merge_result.message, parent=ui_parent)
                    return
                main_output = (
                    project_paths.translation_output_dir
                    if project_paths is not None
                    else output_dir.parent / tl_name
                )
                cache_dir = output_dir / "cache"
                cache_was_present = cache_dir.is_dir()
                cache_migrated = merge_incremental_translation_cache(
                    output_dir,
                    main_output,
                ) if cache_was_present else True
                if cache_was_present and not cache_migrated:
                    # 合并函数已写回 TL，但缓存迁移失败时保留增量目录，
                    # 让校对页仍能载入本轮结果，避免“文件成功、缓存丢失”。
                    InfoBar.warning(
                        "缓存暂未合并",
                        f"翻译文件已应用，但缓存仍保留在：{output_dir / 'cache'}，请稍后重试应用。",
                        parent=ui_parent,
                    )
                    return
                if output_dir.exists():
                    shutil.rmtree(str(output_dir), ignore_errors=True)
                staging_input = getattr(self, "_incremental_dir", None)
                if staging_input and Path(staging_input).exists():
                    shutil.rmtree(str(staging_input), ignore_errors=True)
                # 应用增量后恢复全局主路径，并把运行清单更新到已经
                # 合并的主缓存；不能继续指向刚删除的 <lang>_new。
                configure_main_translation_paths(
                    config,
                    self.game_dir,
                    tl_name,
                    remember_run = True,
                )
                config.save()
                self._last_onekey_output_dir = main_output
                self._incremental_dir = None
                self._incremental_output_dir = None
                self._apply_target_dir = None
                InfoBar.success("应用成功", merge_result.message, duration=5000, parent=ui_parent)
                if self._onekey_translation_started and self._auto_hook_pending:
                    self._auto_hook_pending = False
                    QTimer.singleShot(0, self._start_auto_hook_supplement)
                elif self._onekey_translation_started:
                    self._reset_auto_hook_state()
                return
            except Exception as e:
                self.logger.error(f"应用增量翻译失败: {e}")
                InfoBar.error("错误", f"应用增量翻译失败：{e}", parent=ui_parent)
                return

        # 全量翻译按批次应用；任一文件失败就恢复本批次已覆盖的目标。
        try:
            success_count = apply_translation_files_transactionally(
                output_files,
                output_dir,
                input_dir,
            )
            InfoBar.success(
                "应用成功",
                f"已成功应用 {success_count} 个翻译文件到游戏目录！\n"
                f"现在可以启动游戏查看翻译效果。",
                duration=5000,
                parent=ui_parent
            )

            # 应用成功后把全局配置恢复为向导项目的主路径，再允许自动
            # hook 接续；这样 hook 扫描到的是真实的最新 TL。
            if project_paths is not None:
                configure_main_translation_paths(
                    config,
                    project_paths.project_root,
                    project_paths.language,
                    remember_run = False,
                )
                config.save()
                self._last_onekey_output_dir = project_paths.translation_output_dir
            if self._onekey_translation_started and self._auto_hook_pending:
                self._auto_hook_pending = False
                QTimer.singleShot(0, self._start_auto_hook_supplement)
            elif self._onekey_translation_started:
                self._reset_auto_hook_state()
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            InfoBar.error("错误", f"应用翻译失败：{e}", parent=ui_parent)

    def _tool_hook_supplement(self, card):
        """打开补全漏翻页面，并沿用当前项目上下文。"""
        try:
            if self.game_dir:
                self._sync_game_dir_to_config(self.game_dir)
            self.window.navigate_to_page(self._get_tool_page("hook_supplement"))
        except Exception as e:
            self.logger.error(f"打开补全翻译页面失败: {e}")
            InfoBar.error("错误", f"打开补全翻译页面失败: {e}", parent=self)
    
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
            InfoBar.error("错误", f"打开错误修复页面失败：{exc}", parent=self)

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
                InfoBar.warning("提示", "请先选择游戏目录。", parent=self)
                return
            tl_name = self.tl_folder_edit.text().strip() or "chinese"
            patch_path, missing_count = generate_patch(self.game_dir, tl_name)
            if patch_path is None:
                InfoBar.info("提示", "未发现缺失翻译，无需生成补丁。", parent=self)
                return
            InfoBar.success(
                "导出完成",
                f"已生成漏翻补丁：{patch_path}（{missing_count} 条）",
                parent=self,
                duration=5000,
            )
        except Exception as exc:
            self.logger.error(f"导出语言补丁失败: {exc}")
            InfoBar.error("错误", f"导出语言补丁失败：{exc}", parent=self)
    
    def _tool_view_glossary(self, card):
        self._open_local_glossary()


# 兼容旧引用
OneKeyTranslatePage = YiJianFanyiPage
__all__ = ["YiJianFanyiPage", "OneKeyTranslatePage"]
