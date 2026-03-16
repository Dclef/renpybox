import hashlib
import os
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Any

from base.LogManager import LogManager
from base.PathHelper import get_resource_path


class OpenCCHelper:
    """OpenCC 懒加载与中文路径兼容辅助。"""

    _LOCK: threading.Lock = threading.Lock()
    _CONVERTERS: dict[str, Any | None] = {}
    _FAILED_KEYS: set[str] = set()
    _FALLBACK_KEYS: set[str] = set()

    @classmethod
    def get_converter(cls, config: str):
        key = cls._normalize_config_key(config)
        with cls._LOCK:
            if key not in cls._CONVERTERS:
                cls._CONVERTERS[key] = cls._create_converter(key)
            return cls._CONVERTERS[key]

    @classmethod
    def convert(cls, config: str, text: str) -> str:
        if text == "":
            return text

        converter = cls.get_converter(config)
        if converter is None:
            return text

        try:
            return converter.convert(text)
        except Exception as exc:
            cls._log_failure_once(config, "OpenCC 转换失败，已回退为原文", exc)
            return text

    @classmethod
    def _create_converter(cls, config: str):
        try:
            import opencc
        except Exception as exc:
            cls._log_failure_once(config, "OpenCC 导入失败，已跳过简繁转换", exc)
            return None

        try:
            return opencc.OpenCC(config)
        except Exception as default_exc:
            ascii_config = cls._prepare_ascii_config_path(config)
            if ascii_config is not None:
                try:
                    converter = opencc.OpenCC(str(ascii_config))
                    cls._log_fallback_once(config, ascii_config, default_exc)
                    return converter
                except Exception as fallback_exc:
                    cls._log_failure_once(config, "OpenCC ASCII 兼容模式初始化失败，已跳过简繁转换", fallback_exc)
                    return None

            cls._log_failure_once(config, "OpenCC 初始化失败，且未找到可复制的配置目录", default_exc)
            return None

    @classmethod
    def _prepare_ascii_config_path(cls, config: str) -> Path | None:
        source_dir = cls._find_opencc_share_dir()
        if source_dir is None or not source_dir.exists():
            return None

        cache_dir = cls._ensure_ascii_share_dir(source_dir)
        if cache_dir is None:
            return None

        config_name = cls._normalize_config_filename(config)
        config_path = cache_dir / config_name
        return config_path if config_path.exists() else None

    @classmethod
    def _find_opencc_share_dir(cls) -> Path | None:
        try:
            import opencc

            pkg_dir = Path(opencc.__file__).resolve().parent
            candidate = pkg_dir / "clib" / "share" / "opencc"
            if candidate.exists():
                return candidate
        except Exception:
            pass

        for segments in (
            ("opencc", "clib", "share", "opencc"),
            ("opencc", "cLib", "share", "opencc"),
        ):
            candidate = Path(get_resource_path(*segments))
            if candidate.exists():
                return candidate

        return None

    @classmethod
    def _ensure_ascii_share_dir(cls, source_dir: Path) -> Path | None:
        cache_root = cls._get_ascii_cache_root()
        try:
            cache_root.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            cls._log_failure_once(str(source_dir), "创建 OpenCC ASCII 缓存目录失败", exc)
            return None

        digest = hashlib.md5(str(source_dir).encode("utf-8", errors="ignore")).hexdigest()[:12]
        target_dir = cache_root / f"opencc_{digest}"
        if (target_dir / "t2s.json").exists():
            return target_dir

        temp_dir = cache_root / f"opencc_{digest}_tmp"
        try:
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
            shutil.copytree(source_dir, temp_dir, dirs_exist_ok=True)
            if target_dir.exists():
                shutil.rmtree(target_dir, ignore_errors=True)
            temp_dir.replace(target_dir)
            return target_dir
        except Exception as exc:
            cls._log_failure_once(str(source_dir), "复制 OpenCC 配置到 ASCII 临时目录失败", exc)
            return None
        finally:
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    @classmethod
    def _get_ascii_cache_root(cls) -> Path:
        if os.name == "nt":
            system_drive = os.environ.get("SystemDrive", "C:")
            return Path(f"{system_drive}\\RenpyBoxCache\\opencc")
        return Path(tempfile.gettempdir()) / "RenpyBoxCache" / "opencc"

    @classmethod
    def _normalize_config_key(cls, config: str) -> str:
        config = str(config).strip()
        return config if config != "" else "t2s"

    @classmethod
    def _normalize_config_filename(cls, config: str) -> str:
        name = Path(str(config)).name
        if not name.endswith(".json"):
            name += ".json"
        return name

    @classmethod
    def _log_failure_once(cls, key: str, message: str, exc: Exception) -> None:
        key = f"fail:{key}:{message}"
        if key in cls._FAILED_KEYS:
            return
        cls._FAILED_KEYS.add(key)
        LogManager.get().warning(message, exc)

    @classmethod
    def _log_fallback_once(cls, config: str, ascii_config: Path, exc: Exception) -> None:
        key = f"fallback:{config}"
        if key in cls._FALLBACK_KEYS:
            return
        cls._FALLBACK_KEYS.add(key)
        LogManager.get().warning(
            f"OpenCC 默认初始化失败，已切换到 ASCII 兼容目录: {ascii_config.parent}",
            exc,
        )
