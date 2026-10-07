"""按域划分的路由。每个模块导出 router，由 api/app.py 统一挂载。"""

from api.routes import glossary, jobs, project, settings, system, ws

__all__ = ["glossary", "jobs", "project", "settings", "system", "ws"]