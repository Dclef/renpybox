"""Agent 一期工具实现。"""

from importlib import import_module
from typing import Any


_EXPORTS = {
    "get_project_info": ("project_tools", "get_project_info"),
    "inspect_translation_project": ("inspection_tools", "inspect_translation_project"),
    "list_rpa_files": ("project_tools", "list_rpa_files"),
    "scan_script_errors": ("project_tools", "scan_script_errors"),
    "set_project": ("project_tools", "set_project"),
    "unpack_rpa_files": ("archive_tools", "unpack_rpa_files"),
    "old_new_replace_confirmation_context": (
        "translation_tools",
        "old_new_replace_confirmation_context",
    ),
    "optimize_old_new_translations": (
        "translation_tools",
        "optimize_old_new_translations",
    ),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    """仅在调用方需要某个工具时加载对应实现。"""
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attribute = target
    value = getattr(import_module(f"{__name__}.{module_name}"), attribute)
    globals()[name] = value
    return value
