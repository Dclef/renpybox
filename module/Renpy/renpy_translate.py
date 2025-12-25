"""
Compatibility stub for renpy-translator's API-based translation.

In this project, online/API translation for Ren'Py is disabled by design.
This module remains as a placeholder to avoid import and runtime errors.

If you need API translation later, integrate it via the Engine/TaskRequester
flow or enable it explicitly in a separate module.
"""

from __future__ import annotations

from typing import Any, Dict, List

from base.LogManager import LogManager

logger = LogManager.get()

# Compatibility variables that some docs or legacy code may reference
engineList: List[str] = []
engineDic: Dict[str, Dict[str, Any]] = {}


class Translate:  # type: ignore
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError(
            "pygtrans/Translate is not available. API translation is disabled in RenpyBox.")


class ApiKeyTranslate:  # type: ignore
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError(
            "pygtrans/ApiKeyTranslate is not available. API translation is disabled in RenpyBox.")


def TranslateToList(*args: Any, **kwargs: Any) -> Dict[str, str]:  # pragma: no cover
    raise RuntimeError("TranslateToList is disabled. Use the Excel workflow instead.")


def init_client() -> None:  # pragma: no cover
    logger.warning("renpy_translate.init_client() called but API translation is disabled.")
    raise RuntimeError("API translation is disabled in this build.")


# Legacy placeholders so that potential imports do not crash on attribute errors
translate_threads: List[Any] = []
translate_lock = None
client_openai = None
web_brower_export_name = 'translate_with_web_brower.html'
rpy_info_dic: Dict[str, Any] = {}

