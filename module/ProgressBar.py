from datetime import datetime
import time
from types import TracebackType
from typing import Any
from base.compat import Self

from rich.progress import BarColumn
from rich.progress import Progress
from rich.progress import TaskID
from rich.progress import TextColumn
from rich.progress import TimeElapsedColumn

class ProgressBar():

    # 类变量
    progress: Progress | None = None

    def __init__(self, transient: bool) -> None:
        super().__init__()

        # 初始化
        self.tasks: dict[TaskID, dict[str, Any]] = {}
        self.transient: bool = transient

    def __enter__(self) -> Self:
        if not isinstance(__class__.progress, Progress):
            __class__.progress = Progress(
                TextColumn(datetime.now().strftime("[%H:%M:%S]"), style = "log.time"),
                TextColumn("INFO    ", style = "logging.level.info"),
                BarColumn(bar_width = None),
                "•",
                TextColumn("{task.completed}/{task.total}", justify = "right"),
                "•",
                TimeElapsedColumn(),
                "/",
                TextColumn("{task.fields[remaining]}", justify = "right"),
                transient = self.transient,
            )
            __class__.progress.start()

        return self

    def __exit__(self, exc_type: BaseException, exc_val: BaseException, exc_tb: TracebackType) -> None:
        for id, attr in self.tasks.items():
            attr["running"] = False
            __class__.progress.stop_task(id)
            __class__.progress.remove_task(id) if self.transient == True else None

        task_ids: set[TaskID] = {k for k, v in self.tasks.items() if v.get('running') == False}
        if all(v in task_ids for v in __class__.progress.task_ids):
            __class__.progress.stop()
            __class__.progress = None

    def new(self) -> TaskID:
        if __class__.progress is None:
            return None
        else:
            id = __class__.progress.add_task("", total = None, remaining = "-:--:--")
            self.tasks[id] = {
                "running": True,
                "completed": 0,
                "started_at": time.monotonic(),
                "total": None,
            }
            return id

    @staticmethod
    def _format_duration(seconds: float) -> str:
        seconds = max(0, int(seconds))
        minutes, secs = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02d}:{secs:02d}"

    def _remaining_text(self, task: dict[str, Any], total: int | None, completed: int) -> str:
        if total is None:
            total = task.get("total")
        else:
            task["total"] = total
        try:
            total_int = int(total or 0)
            completed_int = int(completed or 0)
        except (TypeError, ValueError):
            return "-:--:--"
        if total_int <= 0 or completed_int <= 0:
            return "-:--:--"
        if completed_int >= total_int:
            return "0:00:00"
        started_at = task.get("started_at")
        if started_at is None:
            task["started_at"] = time.monotonic()
            return "-:--:--"
        elapsed = max(0.0, time.monotonic() - float(started_at))
        if elapsed <= 0:
            return "-:--:--"
        speed = completed_int / elapsed
        if speed <= 0:
            return "-:--:--"
        return self._format_duration((total_int - completed_int) / speed)

    def update(self, id: TaskID, *, total: int = None, advance: int = None, completed: int = None) -> None:
        if __class__.progress is None:
            pass
        else:
            task = self.tasks.get(id)
            if task is not None and completed is not None and advance is None:
                previous = int(task.get("completed", 0) or 0)
                task["completed"] = completed
                delta = completed - previous
                remaining = self._remaining_text(task, total, completed)
                if delta > 0:
                    __class__.progress.update(id, total = total, advance = delta, remaining = remaining)
                    return
            elif task is not None and advance is not None:
                task["completed"] = int(task.get("completed", 0) or 0) + advance
            current_completed = completed
            if task is not None:
                current_completed = int(task.get("completed", 0) or 0)
            remaining = self._remaining_text(task, total, current_completed) if task is not None else "-:--:--"
            __class__.progress.update(id, total = total, advance = advance, completed = completed, remaining = remaining)
