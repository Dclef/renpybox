"""RenpyBox desktop sidecar —— Electron 的 Python 侧进程。

挂载仓库里的 api/ 契约层，暴露真实业务逻辑（配置、项目、术语表、
翻译主流程、任务、WebSocket 事件流）。

复用项目自身解释器（Python 3.10，全套依赖已在其中）：
PyQt5 / qfluentwidgets / openpyxl / tiktoken / unrpa / opencc / translators 都可用。
module/ 与 base/ 已解除 Qt 依赖，sidecar 不需要 QApplication。
"""
from __future__ import annotations

import os
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 把仓库根目录加进 sys.path 后挂载真实契约层
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from api.app import create_app  # noqa: E402

app: FastAPI = create_app()
app.add_middleware(
    CORSMiddleware,
    allow_origins = ["*"],
    allow_methods = ["*"],
    allow_headers = ["*"],
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host = "127.0.0.1", port = int(os.environ.get("RENPYBOX_SIDECAR_PORT", "9712")))
