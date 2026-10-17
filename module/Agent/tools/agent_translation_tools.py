"""Agent 自带翻译能力：按批读取待译条目、把译文写回项目缓存与输出文件。

这里不另造一套翻译流水线，而是复用项目既有实现：

- 缓存：``module.Cache.CacheManager``（与翻译引擎同一份 cache.db / project.json）
- 质量闸：``module.ResultChecker.ResultChecker``（含标记保留、术语、相似度检查）
- 写回：``module.File.FileManager.write_to_path``（行级更新，可只写本批条目）

因此 Agent 译出来的内容与引擎译出来的内容落在同一个位置，后续的
``apply_translation`` / ``refresh_replace_fallback`` 无需区分来源。
"""

from __future__ import annotations

import threading
from typing import Any

from base.Base import Base
from module.Localizer.Localizer import Localizer

from ..types import ToolResult


ID_SEPARATOR = "｜"
# 现代大窗口模型（200k～1M token）可以一次吞下更多条目，批次给足能显著减少轮数；
# 同时给输出侧留余量：一批 200 条约需 12k～16k 输出 token，仍在常见上限内。
DEFAULT_BATCH_SIZE = 80
MAX_BATCH_SIZE = 400
DEFAULT_BATCH_CHARS = 40_000
MAX_BATCH_CHARS = 200_000

# 同一进程里读批与写批不能交错，否则两份 CacheManager 会互相覆盖缓存文件。
_WRITE_LOCK = threading.Lock()


def _item_id(item: Any) -> str:
    """条目对外标识：文件相对路径 + 行号，够稳定也够短。"""

    return f"{item.get_file_path()}{ID_SEPARATOR}{item.get_row()}"


def _load_cache(config: Any) -> Any:
    """按当前配置加载翻译缓存；项目未抽取时抛 RuntimeError。"""

    from module.Cache.CacheManager import CacheManager

    output_folder = str(getattr(config, "output_folder", "") or "").strip()
    if not output_folder:
        raise RuntimeError("translation_output_dir_missing")

    manager = CacheManager(service = False)
    manager.load_from_file(output_folder)
    return manager


def _is_pending(item: Any) -> bool:
    """待译条目：真正还没译的，排除已排除/重复/已完成。"""

    status = item.get_status()
    if Base.is_item_completed(status):
        return False
    if status in (Base.TranslationStatus.EXCLUDED, Base.TranslationStatus.DUPLICATED):
        return False
    return True


def _render_item(item: Any) -> dict[str, Any]:
    """把缓存条目压缩成模型易读的最小字段集。"""

    payload: dict[str, Any] = {
        "id": _item_id(item),
        "src": item.get_src(),
    }
    name_src = item.get_name_src()
    if isinstance(name_src, str) and name_src.strip():
        payload["name_src"] = name_src
    elif isinstance(name_src, list) and name_src:
        payload["name_src"] = name_src
    text_type = str(getattr(item.get_text_type(), "value", item.get_text_type() or ""))
    if text_type and text_type != "NONE":
        payload["text_type"] = text_type
    return payload


def _platform_of(config: Any) -> Any:
    """取当前 Agent 平台配置，用于按模型容量推导批次大小。"""

    try:
        platform_id = int(getattr(config, "agent_platform", -1))
    except (TypeError, ValueError):
        return None
    if platform_id < 0:
        return None
    try:
        platform = config.get_platform(platform_id)
    except Exception:  # noqa: BLE001 - 平台配置脏时退回兜底容量
        return None
    return platform if isinstance(platform, dict) else None


def read_translation_batch(
    *,
    config_loader: Any = None,
    batch_size: int | None = None,
    max_chars: int | None = None,
) -> ToolResult:
    """返回一批待译条目，供 Agent 自行翻译。

    两个参数都省略时，按当前模型容量自动决定：条目数由单次**输出**预算反推
    （输出小的时候给太多条只会在半路截断），字符数由**输入**预算的四分之一。
    """

    localizer = Localizer.get()
    from module.Agent.ModelBudget import batch_capacity
    from module.Config import Config

    config = config_loader() if config_loader is not None else Config().load()
    capacity = batch_capacity(_platform_of(config))
    try:
        manager = _load_cache(config)
    except RuntimeError:
        return ToolResult(
            False,
            localizer.agent_translate_output_missing,
            code = "TRANSLATION_TARGET_MISSING",
        )
    except Exception as exc:  # noqa: BLE001 - 缓存损坏要变成可读结果
        return ToolResult(
            False,
            localizer.agent_translate_cache_failed.format(detail = exc),
            code = "CACHE_LOAD_FAILED",
        )

    items = [
        item for item in manager.get_items()
        if _is_pending(item) and str(item.get_src() or "").strip()
    ]
    if not items:
        return ToolResult(
            True,
            localizer.agent_translate_batch_empty,
            data = {"remaining": 0, "items": []},
        )

    size = max(1, min(int(batch_size or capacity["max_entries"]), MAX_BATCH_SIZE))
    budget = max(500, min(int(max_chars or capacity["max_chars"]), MAX_BATCH_CHARS))

    batch: list[dict[str, Any]] = []
    used = 0
    current_file = ""
    for item in items[:size]:
        file_path = str(item.get_file_path() or "")
        # 同一批只喂一个文件的条目：跨文件的上下文彼此无关，混在一批里
        # 既稀释语境，也让失败重试牵连整批（照 LinguaGacha 的断批规则）。
        if batch and file_path != current_file:
            break
        entry = _render_item(item)
        cost = len(str(entry.get("src") or "")) + len(str(entry.get("name_src") or ""))
        if batch and used + cost > budget:
            break
        batch.append(entry)
        current_file = file_path
        used += cost

    return ToolResult(
        True,
        localizer.agent_translate_batch_ready.format(
            count = len(batch),
            remaining = len(items),
        ),
        data = {
            "remaining": len(items),
            "returned": len(batch),
            "items": batch,
        },
        # 还有条目可译，本回合视为长任务在推进。
        continues = bool(batch),
    )


def _apply_translations(
    manager: Any,
    translations: list[dict[str, Any]],
) -> tuple[list[Any], list[str]]:
    """把译文写进缓存条目；返回成功条目与被拒原因。"""

    by_id = {_item_id(item): item for item in manager.get_items()}
    written: list[Any] = []
    rejected: list[str] = []
    seen: set[str] = set()

    for entry in translations:
        if not isinstance(entry, dict):
            rejected.append("entry_not_object")
            continue
        item_id = str(entry.get("id") or "").strip()
        dst = entry.get("dst")
        if not item_id or not isinstance(dst, str) or not dst.strip():
            rejected.append(f"{item_id or '?'}:empty_translation")
            continue
        if item_id in seen:
            rejected.append(f"{item_id}:duplicated")
            continue
        item = by_id.get(item_id)
        if item is None:
            rejected.append(f"{item_id}:unknown_id")
            continue
        seen.add(item_id)

        item.set_dst(dst)
        name_dst = entry.get("name_dst")
        name_src = item.get_name_src()
        if isinstance(name_dst, str) and name_dst.strip() and name_src:
            # name_src 可能是列表（多名字条目），此时按位置补齐成同形结构。
            if isinstance(name_src, list):
                item.set_name_dst(
                    [name_dst] + [str(value) for value in name_src[1:]]
                )
            else:
                item.set_name_dst(name_dst)
        item.set_status(Base.TranslationStatus.TRANSLATED)
        written.append(item)

    return written, rejected


def _check_batch(config: Any, items: list[Any]) -> dict[str, str]:
    """用引擎自己的响应校验器逐条判定，返回 {条目 id: 错误码}。"""

    if not items:
        return {}
    try:
        from module.Response.ResponseChecker import ResponseChecker
    except Exception:  # noqa: BLE001 - 缺少校验器时按全部通过处理
        return {}

    checker = ResponseChecker(config, items)
    none = ResponseChecker.Error.NONE
    groups: dict[Any, list[Any]] = {}
    for item in items:
        groups.setdefault(item.get_text_type(), []).append(item)

    failures: dict[str, str] = {}
    for text_type, group in groups.items():
        try:
            codes = checker.check(
                [str(item.get_src() or "") for item in group],
                [str(item.get_dst() or "") for item in group],
                text_type,
                line_items = group,
            )
        except Exception:  # noqa: BLE001 - 校验异常不阻断写回，与引擎一致
            continue
        for item, code in zip(group, codes):
            if code != none:
                failures[_item_id(item)] = str(code)
    return failures


def write_translation_batch(
    *,
    config_loader: Any = None,
    translations: list[dict[str, Any]] | None = None,
) -> ToolResult:
    """把 Agent 给出的译文写回缓存与输出文件。"""

    localizer = Localizer.get()
    from module.Config import Config

    config = config_loader() if config_loader is not None else Config().load()
    payload = translations if isinstance(translations, list) else []
    if not payload:
        return ToolResult(
            False,
            localizer.agent_translate_translations_required,
            code = "TRANSLATIONS_REQUIRED",
        )

    with _WRITE_LOCK:
        try:
            manager = _load_cache(config)
        except RuntimeError:
            return ToolResult(
                False,
                localizer.agent_translate_output_missing,
                code = "TRANSLATION_TARGET_MISSING",
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                False,
                localizer.agent_translate_cache_failed.format(detail = exc),
                code = "CACHE_LOAD_FAILED",
            )

        written, rejected = _apply_translations(manager, payload)
        if not written:
            return ToolResult(
                False,
                localizer.agent_translate_nothing_written.format(count = len(rejected)),
                code = "NOTHING_WRITTEN",
                data = {"rejected": rejected[:20]},
            )

        # 与引擎一致的顺序：先说引擎自己的校验器过一遍（占位符、空译文、
        # 提示词回显、退化、混排等），不合格的条目打回未翻译让模型重译，再写回文件。
        failures = _check_batch(config, written)
        checked = []
        for item in written:
            if _item_id(item) in failures:
                item.set_status(Base.TranslationStatus.UNTRANSLATED)
            else:
                checked.append(item)

        writeback_error = ""
        if checked:
            try:
                from module.File.FileManager import FileManager

                FileManager(config).write_to_path(checked)
            except Exception as exc:  # noqa: BLE001 - 写回失败要如实报告
                writeback_error = str(exc)

        try:
            manager.save_to_file(
                manager.get_project(),
                manager.get_items(),
                str(config.output_folder),
            )
        except Exception as exc:  # noqa: BLE001
            writeback_error = writeback_error or str(exc)

    failed = len(written) - len(checked)
    failed_items = [
        {"id": item_id, "code": code}
        for item_id, code in list(failures.items())[:10]
    ]
    if writeback_error:
        return ToolResult(
            False,
            localizer.agent_translate_writeback_failed.format(detail = writeback_error),
            code = "WRITEBACK_FAILED",
            data = {
                "written": len(checked),
                "failed": failed,
                "failed_items": failed_items,
                "rejected": rejected[:20],
            },
        )

    return ToolResult(
        True,
        localizer.agent_translate_batch_written.format(
            written = len(checked),
            failed = failed,
        ),
        data = {
            "written": len(checked),
            "failed": failed,
            "failed_items": failed_items,
            "rejected": rejected[:20],
        },
        # 有失败条目时模型还要继续改，同样算长任务在推进。
        continues = bool(checked) or bool(failures),
    )


__all__ = [
    "read_translation_batch",
    "write_translation_batch",
    "DEFAULT_BATCH_SIZE",
    "MAX_BATCH_SIZE",
]
