"""RenpyBox 桌面端 API 契约层。

M1 目标：把 module/ 与 base/ 的业务逻辑暴露成 Electron 侧可调用的契约，
同时保证这一层不依赖 Qt（module/ 与 base/ 已解耦，见 commit 7478722）。

分层：
    schemas.py  Pydantic 请求/响应模型
    hub.py      WebSocket 连接集合
    events.py   EventManager → WebSocket 广播桥
    jobs.py     统一任务模型（job_id + 进度 + 取消）
    routes/     按域划分的路由
    app.py      create_app() 工厂与生命周期
"""

from api.app import create_app

__all__ = ["create_app"]