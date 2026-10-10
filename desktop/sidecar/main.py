"""RenpyBox desktop sidecar —— Electron 的 Python 侧进程。

挂载仓库里的 api/ 契约层，暴露真实业务逻辑（配置、项目、术语表、
翻译主流程、任务、WebSocket 事件流）。

开发模式使用项目解释器；安装包使用 PyInstaller 自带的 Python 和依赖。
module/ 与 base/ 已解除 Qt 依赖，sidecar 不需要 QApplication。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Frozen Python may keep the Windows locale encoding even with PYTHONUTF8=1.
# Electron decodes these pipes as UTF-8, so configure them before business logs.
for stream in (sys.stdout, sys.stderr):
    if callable(getattr(stream, "reconfigure", None)):
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")

if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()

if getattr(sys, "frozen", False):
    os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(Path(sys._MEIPASS) / "tiktoken_cache"))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 把仓库根目录加进 sys.path 后挂载真实契约层
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if not getattr(sys, "frozen", False) and REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from api.app import create_app  # noqa: E402

app: FastAPI = create_app()
app.add_middleware(
    CORSMiddleware,
    allow_origins = ["*"],
    allow_methods = ["*"],
    allow_headers = ["*"],
)


def self_test() -> None:
    """Exercise frozen imports, presets and native dependencies without the UI."""
    import importlib
    import json
    from base.AppPaths import get_app_paths
    from module.Cache.CacheItem import CacheItem
    from module.Agent.ToolDispatcher import ToolDispatcher
    from module.OpenCCHelper import OpenCCHelper
    from update_integrity import validate_installed_files
    from update_path_policy import validate_manifest_paths

    for module in ("openai", "anthropic", "google.genai", "google.genai.types",
                   "httpx", "pygtrans", "translators", "openpyxl", "unrpa",
                   "uvicorn.protocols.http.h11_impl", "uvicorn.protocols.websockets.websockets_impl"):
        importlib.import_module(module)
    paths = get_app_paths()
    for asset in ("icon.ico", "prompt", "text_preserve_preset", "platforms", "mods"):
        if not paths.resource(asset).exists():
            raise RuntimeError(f"Missing bundled resource: {asset}")
    if paths.resource("config.json").exists():
        raise RuntimeError("A developer config.json was included in the runtime")
    if CacheItem._get_token_encoder() is None:
        raise RuntimeError("Bundled token dictionary could not be loaded")
    if OpenCCHelper.get_converter("s2t") is None:
        raise RuntimeError("Bundled OpenCC dictionary could not be loaded")
    import module.Agent.tools as tools
    for name in tools.__all__:
        getattr(tools, name)
    assert ToolDispatcher and validate_installed_files and validate_manifest_paths
    print(json.dumps({"ok": True, "frozen": bool(getattr(sys, "frozen", False)),
                      "python": sys.version.split()[0], "resource_root": str(paths.resource())}))


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
        raise SystemExit(0)
    import uvicorn

    uvicorn.run(app, host = "127.0.0.1", port = int(os.environ.get("RENPYBOX_SIDECAR_PORT", "9712")),
                access_log=False)
