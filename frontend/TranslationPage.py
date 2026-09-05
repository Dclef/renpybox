import os
import time
import threading
import copy
from typing import Callable

from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QTime
from PyQt5.QtCore import QTimer
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QWidget
from PyQt5.QtWidgets import QLayout
from PyQt5.QtWidgets import QHBoxLayout
from PyQt5.QtWidgets import QGridLayout
from PyQt5.QtWidgets import QSizePolicy
from PyQt5.QtWidgets import QVBoxLayout

from qfluentwidgets import Action
from qfluentwidgets import InfoBar
from qfluentwidgets import TimeEdit
from qfluentwidgets import CardWidget
from qfluentwidgets import FluentIcon
from qfluentwidgets import MessageBox
from qfluentwidgets import MessageBoxBase
from qfluentwidgets import FluentWindow
from qfluentwidgets import ProgressRing
from qfluentwidgets import CaptionLabel
from qfluentwidgets import SubtitleLabel
from qfluentwidgets import StrongBodyLabel
from qfluentwidgets import PushButton
from qfluentwidgets import IndeterminateProgressRing
from qfluentwidgets import ToolTipFilter
from qfluentwidgets import ToolTipPosition

from base.Base import Base
from base.compat import StrEnum
from module.Config import Config
from module.Engine.Engine import Engine
from module.Engine.Quality.QualityTaskCoordinator import QualityTaskCoordinator, QualityTaskType
from module.Cache.CacheManager import CacheManager
from module.File.FileManager import FileManager
from module.Engine.Translator.ProjectAssetsRepository import ProjectAssetsRepository
from module.Engine.Translator.TranslationPreflightService import TranslationPreflightService
from module.Localizer.Localizer import Localizer
from module.TokenEstimator import TokenEstimator
from module.Renpy.ProjectPaths import (
    RenpyProjectPaths,
    read_run_manifest,
    resolve_translation_output,
)
from widget.WaveformWidget import WaveformWidget
from widget.CommandBarCard import CommandBarCard
from widget.ThemeHelper import mark_app_page


def restore_resumable_translation_paths(config: Config) -> Config:
    """Bind a resume request to the cache selected by the last-run manifest."""
    output_path = resolve_translation_output(config)
    if output_path is None:
        return config

    config.output_folder = str(output_path)
    paths = RenpyProjectPaths.from_config(config)
    manifest = read_run_manifest(paths) if paths is not None else None
    if manifest is None:
        return config

    manifest_output = os.path.normcase(os.path.abspath(manifest["output_folder"]))
    selected_output = os.path.normcase(os.path.abspath(str(output_path)))
    if manifest_output != selected_output:
        return config

    input_folder = str(manifest.get("input_folder", "") or "").strip()
    if input_folder:
        config.input_folder = input_folder
    return config


class DashboardCard(CardWidget):

    def __init__(self, parent: QWidget, title: str, value: str, unit: str, init: Callable = None, clicked: Callable = None) -> None:
        super().__init__(parent)

        # 指标卡保留原有 set_value/set_unit 接口，同时适配原型的紧凑信息层级。
        self.setBorderRadius(8)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumWidth(0)
        self.setFixedHeight(96)

        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(14, 12, 14, 10) # 左、上、右、下
        self.root.setSpacing(4)

        self.title_label = CaptionLabel(title, self)
        self.title_label.setTextColor(QColor("#64748B"), QColor("#94A3B8"))
        self.root.addWidget(self.title_label)

        # 数值与单位在同一基线区域排列，避免旧版大字号造成的垂直浪费。
        self.body_hbox_container = QWidget(self)
        self.body_hbox = QHBoxLayout(self.body_hbox_container)
        self.body_hbox.setSpacing(4)
        self.body_hbox.setContentsMargins(0, 0, 0, 0)

        self.value_label = SubtitleLabel(value, self)
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        self.unit_label = CaptionLabel(unit, self)
        self.unit_label.setTextColor(QColor("#64748B"), QColor("#94A3B8"))
        self.unit_label.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft)

        self.body_hbox.addWidget(self.value_label)
        self.body_hbox.addWidget(self.unit_label)
        self.body_hbox.addStretch(1)
        self.root.addStretch(1)
        self.root.addWidget(self.body_hbox_container)

        self.detail_label = CaptionLabel("", self)
        self.detail_label.setTextColor(QColor("#64748B"), QColor("#94A3B8"))
        self.detail_label.setVisible(False)
        self.root.addWidget(self.detail_label)

        if callable(init):
            init(self)

        if callable(clicked):
            self.clicked.connect(lambda : clicked(self))

    def set_unit(self, unit: str) -> None:
        self.unit_label.setText(unit)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)

    def set_detail(self, detail: str) -> None:
        self.detail_label.setText(detail)
        self.detail_label.setVisible(bool(detail))

class TimerMessageBox(MessageBoxBase):

    def __init__(self, parent, title: str, message_box_close: Callable = None) -> None:
        super().__init__(parent = parent)

        # 初始化
        self.delay = 0
        self.message_box_close = message_box_close

        # 设置框体
        self.yesButton.setText(Localizer.get().confirm)
        self.cancelButton.setText(Localizer.get().cancel)

        # 设置主布局
        self.viewLayout.setContentsMargins(16, 16, 16, 16) # 左、上、右、下

        # 标题
        self.title_label = StrongBodyLabel(title, self)
        self.viewLayout.addWidget(self.title_label)

        # 输入框
        self.time_edit = TimeEdit(self)
        self.time_edit.setMinimumWidth(256)
        self.time_edit.setTimeRange(QTime(0, 0), QTime(23, 59))
        self.time_edit.setTime(QTime(2, 0))
        self.viewLayout.addWidget(self.time_edit)

    # 重写验证方法
    def validate(self) -> bool:
        if callable(self.message_box_close):
            self.message_box_close(self, self.time_edit.time())

        return True

class TranslationPage(QWidget, Base):

    runtime_status_updated = pyqtSignal(object, object)
    token_estimate_done = pyqtSignal(object, object)

    class TokenDisplayMode(StrEnum):
        INPUT = "INPUT"
        OUTPUT = "OUTPUT"

    def __init__(self, text: str, window: FluentWindow) -> None:
        super().__init__(window)
        self.setObjectName(text.replace(" ", "-"))
        mark_app_page(self)

        # 初始化
        self.data = {}
        self.status_text = {
            Engine.Status.IDLE: Localizer.get().translation_page_status_idle,
            Engine.Status.TESTING: Localizer.get().translation_page_status_testing,
            Engine.Status.TRANSLATING: Localizer.get().translation_page_status_translating,
            Engine.Status.QUALITY: Localizer.get().translation_page_status_quality,
            Engine.Status.AGENT: Localizer.get().translation_page_status_agent,
            Engine.Status.STOPPING: Localizer.get().translation_page_status_stopping,
        }

        # 载入并保存默认配置
        config = Config().load().save()
        self._config_snapshot = config

        # 设置主容器
        self.container = QVBoxLayout(self)
        self.container.setSpacing(12)
        self.container.setContentsMargins(24, 18, 24, 18) # 左、上、右、下

        # 添加控件
        self.add_widget_head(self.container, config, window)
        self.add_widget_body(self.container, config, window)
        self.add_widget_foot(self.container, config, window)

        # 注册事件
        self.subscribe(Base.Event.PLATFORM_TEST_DONE, self.update_button_status)
        self.subscribe(Base.Event.PLATFORM_TEST_START, self.update_button_status)
        self.subscribe(Base.Event.TRANSLATION_START, self.update_button_status)
        self.subscribe(Base.Event.TRANSLATION_STOP, self.update_button_status)
        self.subscribe(Base.Event.TRANSLATION_DONE, self.translation_stop_done)
        self.subscribe(Base.Event.TRANSLATION_UPDATE, self.translation_update)
        self.subscribe(Base.Event.CACHE_FILE_AUTO_SAVE, self.cache_file_auto_save)
        self.subscribe(Base.Event.PROJECT_STATUS_CHECK_DONE, self.update_button_status)
        self.runtime_status_updated.connect(self.update_button_status)
        self.token_estimate_done.connect(self._on_token_estimate_done)
        self._token_estimate_running = False
        self._peak_speed = 0.0
        self._peak_speed_start_time = 0

        # 定时器
        self.ui_update_timer = QTimer(self)
        self.ui_update_timer.timeout.connect(self.update_ui_tick)
        self.ui_update_timer.start(500)

    # 页面显示事件
    def showEvent(self, event) -> None:
        super().showEvent(event)

        # 重置 frontend 状态
        self.action_continue.setEnabled(False)
        self.action_retry_failed.setEnabled(False)

        # 触发事件
        self.emit(Base.Event.PROJECT_STATUS, {})

    # 更新 frontend 定时器
    def update_ui_tick(self) -> None:
        self.update_time(self.data)
        self.update_line(self.data)
        self.update_token(self.data)
        self.update_task(self.data)
        self.update_status(self.data)
        self._update_dashboard_details()

    # 更新按钮状态事件
    def update_button_status(self, event: str, data: dict) -> None:
        # 检查是否有缓存数据（用于判断是否可以导出）
        has_cache_data = bool(
            data.get('status') in (Base.TranslationStatus.TRANSLATING, Base.TranslationStatus.TRANSLATED)
            or data.get('line', 0) > 0
            or data.get('total_line', 0) > 0
        )

        # 如果是项目状态检查完成事件，更新缓存的进度数据
        if event == Base.Event.PROJECT_STATUS_CHECK_DONE:
            # 状态检查返回的是完整 progress，必须合并 Token 统计，
            # 否则重新打开页面后 Token 会被清零。
            if isinstance(data, dict):
                self.data = {**self.data, **data}
            self.update_status(self.data)

        if Engine.get().get_status() == Engine.Status.IDLE:
            self.indeterminate_hide()
            self.action_start.setEnabled(True)
            self.action_stop.setEnabled(False)
            # 空闲状态下，如果有缓存数据也允许导出
            self.action_export.setEnabled(has_cache_data)
            self.action_reinject_cache.setEnabled(has_cache_data)
        elif Engine.get().get_status() == Engine.Status.TESTING:
            self.action_start.setEnabled(False)
            self.action_stop.setEnabled(False)
            self.action_export.setEnabled(False)
            self.action_reinject_cache.setEnabled(False)
        elif Engine.get().get_status() == Engine.Status.TRANSLATING:
            self.action_start.setEnabled(False)
            self.action_stop.setEnabled(True)
            self.action_export.setEnabled(True)
            self.action_reinject_cache.setEnabled(False)
        elif Engine.get().get_status() == Engine.Status.STOPPING:
            self.action_start.setEnabled(False)
            self.action_stop.setEnabled(False)
            self.action_export.setEnabled(False)
            self.action_reinject_cache.setEnabled(False)
        elif Engine.get().get_status() == Engine.Status.QUALITY:
            # 润色/校对与初译共享同一引擎锁，期间禁止启动或导出初译任务。
            self.action_start.setEnabled(False)
            quality = self.data.get("quality_task", {})
            cancel_requested = (
                bool(quality.get("cancel_requested", False))
                if isinstance(quality, dict)
                else False
            )
            self.action_stop.setEnabled(not cancel_requested)
            self.action_export.setEnabled(False)
            self.action_reinject_cache.setEnabled(False)

        if Engine.get().get_status() == Engine.Status.IDLE and data.get('status') == Base.TranslationStatus.TRANSLATING:
            self.action_continue.setEnabled(True)
            self.action_retry_failed.setEnabled(True)
        else:
            self.action_continue.setEnabled(False)
            self.action_retry_failed.setEnabled(False)

    # 翻译更新事件
    def translation_update(self, event: str, data: dict) -> None:
        if isinstance(data, dict) and "quality_task" in data:
            # 质量任务只更新自己的分区，不能覆盖初译的行数与 Token 统计。
            self.data = {**self.data, **data}
            self.runtime_status_updated.emit(event, self.data)
        else:
            self.data = data if isinstance(data, dict) else {}
        refresh = getattr(self, "_update_dashboard_details", None)
        if callable(refresh):
            refresh()

    # 翻译停止完成事件
    def translation_stop_done(self, event: str, data: dict) -> None:
        # 更新按钮状态
        self.update_button_status(event, data)

        # 更新继续翻译按钮状态
        self.emit(Base.Event.PROJECT_STATUS, {
            "prefer_runtime_output": True,
        })

    # 更新时间
    def update_time(self, data: dict) -> None:
        engine_status = Engine.get().get_status()
        if engine_status not in (
            Engine.Status.IDLE,
            Engine.Status.STOPPING,
            Engine.Status.TRANSLATING,
        ):
            return None

        if engine_status == Engine.Status.IDLE:
            # 任务结束后使用缓存中的耗时快照，不能继续用 start_time 累加。
            total_time = max(0, int(self.data.get("time", 0) or 0))
        elif self.data.get("start_time", 0) == 0:
            total_time = 0
        else:
            total_time = max(0, int(time.time() - self.data.get("start_time", 0)))

        if total_time < 60:
            self.time.set_unit("S")
            self.time.set_value(f"{total_time}")
        elif total_time < 60 * 60:
            self.time.set_unit("M")
            self.time.set_value(f"{(total_time / 60):.2f}")
        else:
            self.time.set_unit("H")
            self.time.set_value(f"{(total_time / 60 / 60):.2f}")

        line = max(0, int(self.data.get("line", 0) or 0))
        total_line = max(0, int(self.data.get("total_line", 0) or 0))
        remaining = max(0, total_line - line)
        remaining_time = max(0, int(total_time / max(1, line) * remaining))
        if remaining_time < 60:
            self.remaining_time.set_unit("S")
            self.remaining_time.set_value(f"{remaining_time}")
        elif remaining_time < 60 * 60:
            self.remaining_time.set_unit("M")
            self.remaining_time.set_value(f"{(remaining_time / 60):.2f}")
        else:
            self.remaining_time.set_unit("H")
            self.remaining_time.set_value(f"{(remaining_time / 60 / 60):.2f}")

    # 更新行数
    def update_line(self, data: dict) -> None:
        if Engine.get().get_status() not in (
            Engine.Status.IDLE,
            Engine.Status.STOPPING,
            Engine.Status.TRANSLATING,
        ):
            return None

        line = max(0, int(self.data.get("line", 0) or 0))
        if line < 1000:
            self.line_card.set_unit("Line")
            self.line_card.set_value(f"{line}")
        elif line < 1000 * 1000:
            self.line_card.set_unit("KLine")
            self.line_card.set_value(f"{(line / 1000):.2f}")
        else:
            self.line_card.set_unit("MLine")
            self.line_card.set_value(f"{(line / 1000 / 1000):.2f}")

        total_line = max(0, int(self.data.get("total_line", 0) or 0))
        remaining_line = max(0, total_line - line)
        if remaining_line < 1000:
            self.remaining_line.set_unit("Line")
            self.remaining_line.set_value(f"{remaining_line}")
        elif remaining_line < 1000 * 1000:
            self.remaining_line.set_unit("KLine")
            self.remaining_line.set_value(f"{(remaining_line / 1000):.2f}")
        else:
            self.remaining_line.set_unit("MLine")
            self.remaining_line.set_value(f"{(remaining_line / 1000 / 1000):.2f}")

    # 更新实时任务数
    def update_task(self, data: dict) -> None:
        task = Engine.get().get_running_task_count()
        if task < 1000:
            self.task.set_unit("Task")
            self.task.set_value(f"{task}")
        else:
            self.task.set_unit("KTask")
            self.task.set_value(f"{(task / 1000):.2f}")

    # 更新 Token 数据
    def update_token(self, data: dict) -> None:
        if Engine.get().get_status() not in (
            Engine.Status.IDLE,
            Engine.Status.STOPPING,
            Engine.Status.TRANSLATING,
        ):
            return None

        display_mode = getattr(self, "token_display_mode", self.TokenDisplayMode.OUTPUT)
        if display_mode == self.TokenDisplayMode.OUTPUT:
            token = self.data.get("total_output_tokens", 0)
        else:
            token = self.data.get("total_input_tokens", 0)
            if token == 0:
                token = self.data.get("total_tokens", 0) - self.data.get("total_output_tokens", 0)
        if token < 1000:
            self.token.set_unit("Token")
            self.token.set_value(f"{token}")
        elif token < 1000 * 1000:
            self.token.set_unit("KToken")
            self.token.set_value(f"{(token / 1000):.2f}")
        else:
            self.token.set_unit("MToken")
            self.token.set_value(f"{(token / 1000 / 1000):.2f}")

        start_time = self.data.get("start_time", 0)
        if start_time != self._peak_speed_start_time:
            self._peak_speed_start_time = start_time
            self._peak_speed = 0.0
        speed = self.data.get("total_output_tokens", 0) / max(1, time.time() - start_time)
        self._peak_speed = max(self._peak_speed, speed)
        self.waveform.add_value(speed)
        self.waveform_peak_label.setText(
            Localizer.get().translation_page_peak_speed.format(
                SPEED=f"{self._peak_speed:.2f}"
            )
        )
        if speed < 1000:
            self.speed.set_unit("T/S")
            self.speed.set_value(f"{speed:.2f}")
        else:
            self.speed.set_unit("KT/S")
            self.speed.set_value(f"{(speed / 1000):.2f}")

    def _update_header_description(self) -> None:
        """用当前配置和引擎状态组成标题栏摘要，不复制原型演示任务。"""
        label = getattr(self, "header_description_label", None)
        if label is None:
            return
        config = getattr(self, "_config_snapshot", None) or Config().load()
        source = getattr(getattr(config, "source_language", ""), "value", "")
        target = getattr(getattr(config, "target_language", ""), "value", "")
        running = Engine.get().get_running_task_count()
        maximum = max(0, int(getattr(config, "max_workers", 0) or 0))
        template = getattr(
            Localizer.get(),
            "translation_page_header_summary",
            Localizer.get().translation_page_header_description,
        )
        label.setText(
            template.format(
                SOURCE=source or "-",
                TARGET=target or "-",
                RUNNING=running,
                MAX=maximum,
            )
        )

    @staticmethod
    def _format_duration(seconds: int) -> str:
        """将秒数格式化为本地化的紧凑时长。"""
        seconds = max(0, int(seconds or 0))
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        strings = Localizer.get()
        if hours:
            return strings.translation_page_duration_hms.format(H=hours, M=minutes, S=seconds)
        if minutes:
            return strings.translation_page_duration_ms.format(M=minutes, S=seconds)
        return strings.translation_page_duration_s.format(S=seconds)

    @staticmethod
    def _format_token_count(value: int) -> str:
        value = max(0, int(value or 0))
        if value < 1000:
            return str(value)
        if value < 1_000_000:
            return f"{value / 1000:.2f}K"
        return f"{value / 1_000_000:.2f}M"

    def _update_dashboard_details(self) -> None:
        """刷新 Hero 底部摘要、两个原型指标卡及实时流水空态。"""
        if not hasattr(self, "elapsed_label"):
            return
        self._update_header_description()
        total_time = max(0, int(self.data.get("time", 0) or 0))
        if Engine.get().get_status() == Engine.Status.TRANSLATING:
            start_time = self.data.get("start_time", 0)
            if start_time:
                total_time = max(0, int(time.time() - start_time))
        line = max(0, int(self.data.get("line", 0) or 0))
        total_line = max(0, int(self.data.get("total_line", 0) or 0))
        remaining = max(0, total_line - line)
        remaining_time = max(0, int(total_time / max(1, line) * remaining))
        strings = Localizer.get()
        self.elapsed_label.setText(
            strings.translation_page_elapsed.format(TIME=self._format_duration(total_time))
        )
        self.remaining_label.setText(
            strings.translation_page_remaining.format(TIME=self._format_duration(remaining_time))
        )

        output_tokens = max(0, int(self.data.get("total_output_tokens", 0) or 0))
        input_tokens = max(0, int(self.data.get("total_input_tokens", 0) or 0))
        self.token.set_detail(
            strings.translation_page_token_detail.format(
                OUTPUT=self._format_token_count(output_tokens),
                INPUT=self._format_token_count(input_tokens),
            )
        )
        running = Engine.get().get_running_task_count()
        maximum = max(0, int(getattr(getattr(self, "_config_snapshot", None), "max_workers", 0) or 0))
        failed = max(0, int(self.data.get("failed_line_count", 0) or 0))
        self.task.title_label.setText(strings.translation_page_thread_title)
        self.task.set_value(str(running))
        self.task.set_unit(strings.translation_page_thread_unit)
        self.task.set_detail(
            strings.translation_page_thread_detail.format(
                RUNNING=running,
                MAX=maximum,
                FAILED=failed,
            )
        )
        self._refresh_stream_feed()

    def _refresh_stream_feed(self) -> None:
        """展示引擎明确提供的最近流水；没有数据时保持真实空态。"""
        items = self.data.get("recent_items", [])
        if not isinstance(items, list):
            items = []
        items = [item for item in items if isinstance(item, dict)]
        signature = repr(items[-3:])
        if signature == getattr(self, "_stream_feed_signature", None):
            return
        self._stream_feed_signature = signature
        while self.feed_items_layout.count():
            item = self.feed_items_layout.takeAt(0)
            widget = item.widget()
            if widget is not None and widget is not self.feed_empty_label:
                widget.deleteLater()
        if not items:
            self.feed_empty_label.setVisible(True)
            self.feed_items_layout.addWidget(self.feed_empty_label)
            return
        self.feed_empty_label.setVisible(False)
        for item in items[-3:][::-1]:
            row = QWidget(self.feed_items_container)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(8, 5, 8, 5)
            row_layout.setSpacing(12)
            row.setStyleSheet(
                "background: rgba(100, 116, 139, 0.08); border-radius: 4px;"
            )
            row_layout.addWidget(CaptionLabel(str(item.get("id", "")), row), 0)
            row_layout.addWidget(CaptionLabel(str(item.get("source", "")), row), 1)
            row_layout.addWidget(CaptionLabel(str(item.get("target", "")), row), 1)
            self.feed_items_layout.addWidget(row)

    def _trigger_snapshot_export(self) -> None:
        action = getattr(self, "action_export", None)
        if action is not None and action.isEnabled():
            action.trigger()

    def _open_proofreading_page(self, window: FluentWindow) -> None:
        """复用工具箱中的校对页，避免新增导航路由。"""
        toolbox = getattr(window, "renpy_toolbox_page", None)
        if toolbox is not None and hasattr(toolbox, "get_tool_page"):
            try:
                window.navigate_to_page(toolbox.get_tool_page("proofreading"))
                return
            except Exception:
                pass
        page = window.findChild(QWidget, "proofreading_page") if hasattr(window, "findChild") else None
        if page is not None:
            window.navigate_to_page(page)

    # 更新进度环
    def update_status(self, data: dict) -> None:
        if Engine.get().get_status() == Engine.Status.STOPPING:
            line = max(0, int(self.data.get("line", 0) or 0))
            total_line = max(0, int(self.data.get("total_line", 0) or 0))
            percent = min(1.0, max(0.0, line / max(1, total_line)))
            self._set_ring_progress(percent, line, total_line)
        elif Engine.get().get_status() == Engine.Status.TRANSLATING:
            line = max(0, int(self.data.get("line", 0) or 0))
            total_line = max(0, int(self.data.get("total_line", 0) or 0))
            percent = min(1.0, max(0.0, line / max(1, total_line)))
            self._set_ring_progress(percent, line, total_line)
        elif Engine.get().get_status() == Engine.Status.QUALITY:
            quality = self.data.get("quality_task", {})
            completed = quality.get("completed_count", 0) if isinstance(quality, dict) else 0
            total = quality.get("total_count", 0) if isinstance(quality, dict) else 0
            percent = completed / max(1, total)
            self._set_ring_progress(percent, completed, total)
        else:
            # 空闲状态：如果有缓存数据，显示缓存的进度
            line = max(0, int(self.data.get("line", 0) or 0))
            total_line = max(0, int(self.data.get("total_line", 0) or 0))
            if line > 0 and total_line > 0:
                percent = min(1.0, max(0.0, line / total_line))
                self._set_ring_progress(percent, line, total_line)
            else:
                self._set_ring_progress(0.0, 0, 0)

    def _set_ring_progress(self, percent: float, completed: int, total: int) -> None:
        """以原型的百分比和完成/总数双行格式更新进度环。"""
        percent = min(1.0, max(0.0, float(percent)))
        completed = max(0, int(completed or 0))
        total = max(0, int(total or 0))
        self.ring.setValue(int(percent * 10000))
        self.ring.setFormat(f"{percent * 100:.1f}%\n{completed:,} / {total:,}")

    @staticmethod
    def _quality_status_label(quality: object) -> str:
        """返回质量任务的明确类型和停止状态。"""
        strings = Localizer.get()
        quality_data = quality if isinstance(quality, dict) else {}
        task_type = quality_data.get("task_type")
        if isinstance(task_type, QualityTaskType):
            task_type = task_type.value
        cancelling = bool(quality_data.get("cancel_requested", False))

        if task_type == QualityTaskType.POLISHER.value:
            key = (
                "translation_page_status_stopping_polishing"
                if cancelling
                else "translation_page_status_polishing"
            )
            fallback = "正在停止 AI 润色" if cancelling else "AI 润色中"
        elif task_type == QualityTaskType.PROOFREADER.value:
            key = (
                "translation_page_status_stopping_proofreading"
                if cancelling
                else "translation_page_status_proofreading"
            )
            fallback = "正在停止 AI 校对" if cancelling else "AI 校对中"
        else:
            key = "translation_page_status_quality"
            fallback = "质量处理中"
        return getattr(strings, key, fallback)

    # 缓存文件自动保存事件
    def cache_file_auto_save(self, event: str, data: dict) -> None:
        if self.indeterminate.isHidden():
            self.indeterminate_show(Localizer.get().translation_page_indeterminate_saving)

            # 延迟关闭
            QTimer.singleShot(1500, lambda: self.indeterminate_hide())

    # 头部
    def add_widget_head(self, parent: QLayout, config: Config, window: FluentWindow) -> None:
        del config
        self.head_hbox_container = QWidget(self)
        self.head_hbox_container.setObjectName("translationPageHeader")
        self.head_hbox = QHBoxLayout(self.head_hbox_container)
        self.head_hbox.setContentsMargins(0, 0, 0, 0)
        self.head_hbox.setSpacing(12)

        header_text = QWidget(self.head_hbox_container)
        header_layout = QVBoxLayout(header_text)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(2)
        title = StrongBodyLabel(Localizer.get().translation_page_header_title, header_text)
        title_font = title.font()
        title_font.setPixelSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        header_layout.addWidget(title)
        self.header_description_label = CaptionLabel("", header_text)
        self.header_description_label.setWordWrap(True)
        self.header_description_label.setTextColor(QColor("#64748B"), QColor("#94A3B8"))
        header_layout.addWidget(self.header_description_label)
        self.head_hbox.addWidget(header_text, 1)

        header_actions = QHBoxLayout()
        header_actions.setContentsMargins(0, 0, 0, 0)
        header_actions.setSpacing(8)
        self.open_proofreading_button = PushButton(
            FluentIcon.DOCUMENT,
            Localizer.get().translation_page_open_proofreading,
            self.head_hbox_container,
        )
        self.open_proofreading_button.setFixedHeight(32)
        self.open_proofreading_button.clicked.connect(
            lambda: self._open_proofreading_page(window)
        )
        header_actions.addWidget(self.open_proofreading_button)
        self.snapshot_button = PushButton(
            FluentIcon.SHARE,
            Localizer.get().translation_page_export_snapshot,
            self.head_hbox_container,
        )
        self.snapshot_button.setFixedHeight(32)
        self.snapshot_button.clicked.connect(self._trigger_snapshot_export)
        header_actions.addWidget(self.snapshot_button)
        self.head_hbox.addLayout(header_actions)
        parent.addWidget(self.head_hbox_container)
        self._update_header_description()

    # 中部
    def add_widget_body(self, parent: QLayout, config: Config, window: FluentWindow) -> None:
        del config, window
        self.flow_container = QWidget(self)
        self.flow_container.setObjectName("translationDashboardGrid")
        self.flow_layout = QGridLayout(self.flow_container)
        self.flow_layout.setHorizontalSpacing(14)
        self.flow_layout.setVerticalSpacing(14)
        self.flow_layout.setContentsMargins(0, 0, 0, 0)
        self.flow_layout.setColumnStretch(0, 2)
        self.flow_layout.setColumnStretch(1, 3)
        self.flow_layout.setColumnStretch(2, 3)

        # 左侧完成度 Hero 卡片。
        hero_card = CardWidget(self.flow_container)
        hero_card.setObjectName("translationProgressCard")
        hero_card.setFixedHeight(248)
        hero_layout = QVBoxLayout(hero_card)
        hero_layout.setContentsMargins(16, 14, 16, 14)
        hero_layout.setSpacing(6)
        hero_title = CaptionLabel(
            Localizer.get().translation_page_progress_title,
            hero_card,
        )
        hero_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_layout.addWidget(hero_title)
        self.ring = ProgressRing(hero_card)
        self.ring.setRange(0, 10000)
        self.ring.setValue(0)
        self.ring.setTextVisible(True)
        self.ring.setStrokeWidth(8)
        self.ring.setFixedSize(140, 140)
        self.ring.setFormat(Localizer.get().translation_page_progress_empty)
        ring_container = QWidget(hero_card)
        ring_layout = QHBoxLayout(ring_container)
        ring_layout.setContentsMargins(0, 0, 0, 0)
        ring_layout.addStretch(1)
        ring_layout.addWidget(self.ring)
        ring_layout.addStretch(1)
        hero_layout.addWidget(ring_container, 1)
        hero_meta = QHBoxLayout()
        hero_meta.setContentsMargins(0, 8, 0, 0)
        self.elapsed_label = CaptionLabel("", hero_card)
        self.elapsed_label.setTextColor(QColor("#64748B"), QColor("#94A3B8"))
        self.remaining_label = CaptionLabel("", hero_card)
        self.remaining_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.remaining_label.setTextColor(QColor("#4F46E5"), QColor("#818CF8"))
        hero_meta.addWidget(self.elapsed_label)
        hero_meta.addStretch(1)
        hero_meta.addWidget(self.remaining_label)
        hero_layout.addLayout(hero_meta)

        # 右侧吞吐卡片，波形只绘制真实运行速率。
        throughput_card = CardWidget(self.flow_container)
        throughput_card.setObjectName("translationThroughputCard")
        throughput_card.setFixedHeight(136)
        throughput_layout = QVBoxLayout(throughput_card)
        throughput_layout.setContentsMargins(16, 14, 16, 14)
        throughput_layout.setSpacing(8)
        throughput_header = QHBoxLayout()
        throughput_header.setContentsMargins(0, 0, 0, 0)
        throughput_header.addWidget(
            CaptionLabel(Localizer.get().translation_page_throughput_title, throughput_card)
        )
        throughput_header.addStretch(1)
        self.waveform_peak_label = CaptionLabel(
            Localizer.get().translation_page_peak_speed.format(SPEED="0.00"),
            throughput_card,
        )
        self.waveform_peak_label.setTextColor(QColor("#4F46E5"), QColor("#818CF8"))
        throughput_header.addWidget(self.waveform_peak_label)
        throughput_layout.addLayout(throughput_header)
        self.waveform = WaveformWidget(throughput_card)
        self.waveform.set_matrix_size(80, 7)
        throughput_layout.addWidget(self.waveform, 1)

        # 旧的七个字段仍然由同一套更新逻辑维护；只有原型中对应的两张
        # 指标卡放入可见网格，其余卡片保留为兼容对象但不再占用版面。
        self.add_time_card(None, None, None)
        self.add_remaining_time_card(None, None, None)
        self.add_line_card(None, None, None)
        self.add_remaining_line_card(None, None, None)
        self.add_speed_card(None, None, None)
        self.add_token_card(None, None, None)
        self.add_task_card(None, None, None)
        for card in (
            self.time,
            self.remaining_time,
            self.line_card,
            self.remaining_line,
            self.speed,
        ):
            card.hide()

        # 实际数据指标与原型的两列 metric-box 对齐。
        self.flow_layout.addWidget(hero_card, 0, 0, 2, 1, Qt.AlignmentFlag.AlignTop)
        self.flow_layout.addWidget(throughput_card, 0, 1, 1, 2, Qt.AlignmentFlag.AlignTop)
        self.flow_layout.addWidget(self.token, 1, 1, Qt.AlignmentFlag.AlignTop)
        self.flow_layout.addWidget(self.task, 1, 2, Qt.AlignmentFlag.AlignTop)
        self.token.set_detail("")
        self.task.set_detail("")

        self.stream_feed_card = CardWidget(self.flow_container)
        self.stream_feed_card.setObjectName("translationStreamFeedCard")
        self.stream_feed_card.setMinimumHeight(132)
        self.stream_feed_card.setMaximumHeight(190)
        feed_layout = QVBoxLayout(self.stream_feed_card)
        feed_layout.setContentsMargins(14, 12, 14, 12)
        feed_layout.setSpacing(8)
        feed_header = QHBoxLayout()
        feed_header.setContentsMargins(0, 0, 0, 0)
        feed_header.addWidget(
            CaptionLabel(Localizer.get().translation_page_feed_title, self.stream_feed_card)
        )
        feed_header.addStretch(1)
        self.feed_mode_label = CaptionLabel(
            Localizer.get().translation_page_feed_mode,
            self.stream_feed_card,
        )
        self.feed_mode_label.setTextColor(QColor("#64748B"), QColor("#94A3B8"))
        feed_header.addWidget(self.feed_mode_label)
        feed_layout.addLayout(feed_header)
        self.feed_items_container = QWidget(self.stream_feed_card)
        self.feed_items_layout = QVBoxLayout(self.feed_items_container)
        self.feed_items_layout.setContentsMargins(0, 0, 0, 0)
        self.feed_items_layout.setSpacing(6)
        self.feed_empty_label = CaptionLabel(
            Localizer.get().translation_page_feed_empty,
            self.feed_items_container,
        )
        self.feed_empty_label.setTextColor(QColor("#64748B"), QColor("#94A3B8"))
        self.feed_items_layout.addWidget(self.feed_empty_label)
        feed_layout.addWidget(self.feed_items_container, 1)
        self.flow_layout.addWidget(self.stream_feed_card, 2, 0, 1, 3, Qt.AlignmentFlag.AlignTop)
        self.flow_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.container.addWidget(self.flow_container, 1)
        self._update_dashboard_details()

    # 底部
    def add_widget_foot(self, parent: QLayout, config: Config, window: FluentWindow) -> None:
        self.command_bar_card = CommandBarCard()
        self.command_bar_card.setObjectName("translationFooterBar")
        self.command_bar_card.setFixedHeight(58)
        parent.addWidget(self.command_bar_card)

        # 单层操作栏：按核心控制、异常恢复、产物工具分组。
        self.command_bar_card.set_minimum_width(640)
        self.add_command_bar_action_start(self.command_bar_card, config, window)
        self.add_command_bar_action_stop(self.command_bar_card, config, window)
        self.command_bar_card.add_separator()
        self.add_command_bar_action_continue(self.command_bar_card, config, window)
        self.add_command_bar_action_retry_failed(self.command_bar_card, config, window)
        self.command_bar_card.add_separator()
        self.add_command_bar_action_export(self.command_bar_card, config, window)
        self.add_command_bar_action_reinject_cache(self.command_bar_card, config, window)
        self.add_command_bar_action_estimate(self.command_bar_card, config, window)
        self.add_command_bar_action_timer(self.command_bar_card, config, window)

        # 添加信息条
        self.indeterminate = IndeterminateProgressRing()
        self.indeterminate.setFixedSize(16, 16)
        self.indeterminate.setStrokeWidth(3)
        self.indeterminate.hide()
        self.info_label = CaptionLabel(Localizer.get().translation_page_indeterminate_saving, self)
        self.info_label.setTextColor(QColor(96, 96, 96), QColor(160, 160, 160))
        self.info_label.hide()

        self.command_bar_card.add_stretch(1)
        self.footer_backup_label = CaptionLabel(
            Localizer.get().translation_page_footer_backup,
            self.command_bar_card,
        )
        self.footer_backup_label.setTextColor(QColor("#64748B"), QColor("#94A3B8"))
        self.command_bar_card.add_widget(self.footer_backup_label)
        self.command_bar_card.add_spacing(10)
        self.command_bar_card.add_widget(self.info_label)
        self.command_bar_card.add_spacing(4)
        self.command_bar_card.add_widget(self.indeterminate)

    # 累计时间
    def add_time_card(self, parent: QLayout | None, config: Config | None, window: FluentWindow | None) -> None:
        self.time = DashboardCard(
            parent = self,
            title = Localizer.get().translation_page_card_time,
            value = Localizer.get().none,
            unit = "",
        )
        if parent is not None:
            parent.addWidget(self.time)

    # 剩余时间
    def add_remaining_time_card(self, parent: QLayout | None, config: Config | None, window: FluentWindow | None) -> None:
        self.remaining_time = DashboardCard(
            parent = self,
            title = Localizer.get().translation_page_card_remaining_time,
            value = Localizer.get().none,
            unit = "",
        )
        if parent is not None:
            parent.addWidget(self.remaining_time)

    # 翻译行数
    def add_line_card(self, parent: QLayout | None, config: Config | None, window: FluentWindow | None) -> None:
        self.line_card = DashboardCard(
            parent = self,
            title = Localizer.get().translation_page_card_line,
            value = Localizer.get().none,
            unit = "",
        )
        if parent is not None:
            parent.addWidget(self.line_card)

    # 剩余行数
    def add_remaining_line_card(self, parent: QLayout | None, config: Config | None, window: FluentWindow | None) -> None:
        self.remaining_line = DashboardCard(
            parent = self,
            title = Localizer.get().translation_page_card_remaining_line,
            value = Localizer.get().none,
            unit = "",
        )
        if parent is not None:
            parent.addWidget(self.remaining_line)

    # 平均速度
    def add_speed_card(self, parent: QLayout | None, config: Config | None, window: FluentWindow | None) -> None:
        self.speed = DashboardCard(
            parent = self,
            title = Localizer.get().translation_page_card_speed,
            value = Localizer.get().none,
            unit = "",
        )
        if parent is not None:
            parent.addWidget(self.speed)

    # 累计消耗
    def add_token_card(self, parent: QLayout | None, config: Config | None, window: FluentWindow | None) -> None:
        self.token_display_mode = self.TokenDisplayMode.OUTPUT

        def on_token_card_clicked(card: DashboardCard) -> None:
            if self.token_display_mode == self.TokenDisplayMode.OUTPUT:
                self.token_display_mode = self.TokenDisplayMode.INPUT
                card.title_label.setText(Localizer.get().translation_page_card_token_input)
            else:
                self.token_display_mode = self.TokenDisplayMode.OUTPUT
                card.title_label.setText(Localizer.get().translation_page_card_token_output)

            self._animate_token_card_switch()

        self.token = DashboardCard(
            parent = self,
            title = Localizer.get().translation_page_card_token_output,
            value = Localizer.get().none,
            unit = "",
            clicked = on_token_card_clicked,
        )
        self.token.setCursor(Qt.CursorShape.PointingHandCursor)
        self.token.installEventFilter(ToolTipFilter(self.token, 300, ToolTipPosition.TOP))
        self.token.setToolTip(Localizer.get().translation_page_card_token_tooltip)
        if parent is not None:
            parent.addWidget(self.token)

    def _animate_token_card_switch(self) -> None:
        from PyQt5.QtCore import QEasingCurve
        from PyQt5.QtCore import QPropertyAnimation
        from PyQt5.QtWidgets import QGraphicsOpacityEffect

        value_label = self.token.value_label
        unit_label = self.token.unit_label

        if not hasattr(self, "_token_value_opacity_effect") or self._token_value_opacity_effect is None:
            self._token_value_opacity_effect = QGraphicsOpacityEffect(value_label)
            value_label.setGraphicsEffect(self._token_value_opacity_effect)

        if not hasattr(self, "_token_unit_opacity_effect") or self._token_unit_opacity_effect is None:
            self._token_unit_opacity_effect = QGraphicsOpacityEffect(unit_label)
            unit_label.setGraphicsEffect(self._token_unit_opacity_effect)

        fade_out = QPropertyAnimation(self._token_value_opacity_effect, b"opacity")
        fade_out.setDuration(100)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.3)
        fade_out.setEasingCurve(QEasingCurve.Type.InOutQuad)

        fade_out_unit = QPropertyAnimation(self._token_unit_opacity_effect, b"opacity")
        fade_out_unit.setDuration(100)
        fade_out_unit.setStartValue(1.0)
        fade_out_unit.setEndValue(0.3)
        fade_out_unit.setEasingCurve(QEasingCurve.Type.InOutQuad)

        fade_in = QPropertyAnimation(self._token_value_opacity_effect, b"opacity")
        fade_in.setDuration(100)
        fade_in.setStartValue(0.3)
        fade_in.setEndValue(1.0)
        fade_in.setEasingCurve(QEasingCurve.Type.InOutQuad)

        fade_in_unit = QPropertyAnimation(self._token_unit_opacity_effect, b"opacity")
        fade_in_unit.setDuration(100)
        fade_in_unit.setStartValue(0.3)
        fade_in_unit.setEndValue(1.0)
        fade_in_unit.setEasingCurve(QEasingCurve.Type.InOutQuad)

        def on_fade_out_finished() -> None:
            self.update_token(self.data)
            fade_in.start()
            fade_in_unit.start()

        fade_out.finished.connect(on_fade_out_finished)
        fade_out.start()
        fade_out_unit.start()

        self._token_fade_out_anim = fade_out
        self._token_fade_out_unit_anim = fade_out_unit
        self._token_fade_in_anim = fade_in
        self._token_fade_in_unit_anim = fade_in_unit

    # 并行任务
    def add_task_card(self, parent: QLayout | None, config: Config | None, window: FluentWindow | None) -> None:
        self.task = DashboardCard(
            parent = self,
            title = Localizer.get().translation_page_card_task,
            value = Localizer.get().none,
            unit = "",
        )
        if parent is not None:
            parent.addWidget(self.task)

    def _request_translation_start(
        self,
        status: Base.TranslationStatus,
        window: FluentWindow,
        request_id: str = "",
    ) -> bool:
        engine = Engine.get()
        if (
            engine.get_status() != Engine.Status.IDLE
            or engine.has_stop_barrier()
            or engine.has_single_tasks()
        ):
            InfoBar.warning(
                Localizer.get().alert,
                Localizer.get().translator_running,
                parent=window,
            )
            return False

        # 在发出事件前冻结完整配置快照。翻译线程可能稍后才真正开始，
        # 此期间用户切换项目/平台时不能让本轮任务读取到新的全局路径。
        config = Config().load()
        if status in Base.PROJECT_RESUMABLE_STATUSES:
            config = restore_resumable_translation_paths(config)
        payload = {"status": status}
        if request_id:
            payload["request_id"] = str(request_id)
        # 旧的轻量事件调用方可能提供 SimpleNamespace 配置；真实页面
        # 使用 Config 实例时才附加快照，保持兼容而不牺牲正式流程隔离。
        if isinstance(config, Config):
            payload["config"] = copy.deepcopy(config)
        if status == Base.TranslationStatus.UNTRANSLATED:
            try:
                state = ProjectAssetsRepository.from_config(config).load(config)
                preflight = TranslationPreflightService.check(state.assets)
            except Exception as exc:
                InfoBar.error(
                    Localizer.get().alert,
                    Localizer.get().translation_page_preflight_load_error.replace("{ERROR}", str(exc)),
                    parent = window,
                    duration = 5000,
                )
                return False

            if preflight.should_prompt_for_missing_assets:
                message_box = MessageBox(
                    Localizer.get().translation_page_preflight_missing_assets_title,
                    Localizer.get().translation_page_preflight_missing_assets_content,
                    window,
                )
                message_box.yesButton.setText(
                    Localizer.get().translation_page_preflight_open_workbench
                )
                message_box.cancelButton.setText(
                    Localizer.get().translation_page_preflight_continue
                )
                continue_selected = {"value": False}
                cancel_signal = getattr(message_box, "cancelSignal", None)
                if cancel_signal is not None and hasattr(cancel_signal, "connect"):
                    cancel_signal.connect(
                        lambda: continue_selected.__setitem__("value", True)
                    )
                if message_box.exec():
                    self._open_workbench(window)
                    return False
                if cancel_signal is not None and continue_selected["value"] is False:
                    return False

            # UI 已找到有效资产或收到明确的继续决定。
            # 后端使用该标记避免重复弹窗。
            payload["preflight_confirmed"] = True

        self.emit(Base.Event.TRANSLATION_START, payload)
        return True

    def _open_workbench(self, window: FluentWindow) -> None:
        page = getattr(window, "renpy_workbench_page", None)
        if page is None and hasattr(window, "findChild"):
            page = window.findChild(QWidget, "renpy_workbench_page")
        if page is None:
            InfoBar.warning(
                Localizer.get().alert,
                Localizer.get().translation_page_preflight_workbench_unavailable,
                parent = window,
            )
            return
        window.navigate_to_page(page)

    # 开始
    def add_command_bar_action_start(self, parent: CommandBarCard, config: Config, window: FluentWindow) -> None:
        def triggered() -> None:
            if self.action_continue.isEnabled():
                message_box = MessageBox(Localizer.get().alert, Localizer.get().alert_reset_translation, window)
                message_box.yesButton.setText(Localizer.get().confirm)
                message_box.cancelButton.setText(Localizer.get().cancel)

                # 点击取消，则不触发开始翻译事件
                if not message_box.exec():
                    return

            self._request_translation_start(Base.TranslationStatus.UNTRANSLATED, window)

        self.action_start = parent.add_action(
            Action(FluentIcon.PLAY, Localizer.get().start, parent, triggered = triggered)
        )

    # 停止
    def add_command_bar_action_stop(self, parent: CommandBarCard, config: Config, window: FluentWindow) -> None:
        def triggered() -> None:
            self._on_stop_clicked(window)

        self.action_stop = parent.add_action(
            Action(FluentIcon.CANCEL_MEDIUM, Localizer.get().stop, parent,  triggered = triggered),
        )
        self.action_stop.setEnabled(False)

    def _on_stop_clicked(self, window: FluentWindow) -> None:
        """按当前引擎状态停止初译或质量任务。"""
        engine_status = Engine.get().get_status()
        if engine_status == Engine.Status.QUALITY:
            coordinator = QualityTaskCoordinator.get()
            if not coordinator.cancel():
                return
            progress = coordinator.get_progress()
            if progress is not None:
                self.data = {
                    **self.data,
                    "quality_task": progress.as_dict(),
                }
            self.action_stop.setEnabled(False)
            self.update_status(self.data)
            self.indeterminate_show(self._quality_status_label(self.data.get("quality_task", {})))
            return

        if engine_status != Engine.Status.TRANSLATING:
            return

        message_box = MessageBox(
            Localizer.get().alert,
            Localizer.get().translation_page_alert_pause,
            window,
        )
        message_box.yesButton.setText(Localizer.get().confirm)
        message_box.cancelButton.setText(Localizer.get().cancel)

        if message_box.exec():
            self.indeterminate_show(Localizer.get().translation_page_indeterminate_stoping)
            self.emit(Base.Event.TRANSLATION_STOP, {})

    # 继续翻译
    def add_command_bar_action_continue(self, parent: CommandBarCard, config: Config, window: FluentWindow) -> None:

        def triggered() -> None:
            self._request_translation_start(Base.TranslationStatus.TRANSLATING, window)

        self.action_continue = parent.add_action(
            Action(FluentIcon.ROTATE, Localizer.get().translation_page_continue, parent, triggered = triggered),
        )
        self.action_continue.setEnabled(False)

    # 重翻失败项（原译相同的条目）
    def add_command_bar_action_retry_failed(self, parent: CommandBarCard, config: Config, window: FluentWindow) -> None:

        def triggered() -> None:
            current_config = Config().load()
            output_path = resolve_translation_output(current_config)
            if output_path is None:
                InfoBar.warning(
                    Localizer.get().notice,
                    Localizer.localize("未找到当前项目缓存", "The current project cache was not found."),
                    parent=window,
                )
                return
            cache_manager = CacheManager(service = False)
            try:
                cache_manager.load_from_file(str(output_path), strict = True)
            except Exception as exc:
                InfoBar.warning(
                    Localizer.get().notice,
                    Localizer.localize("缓存载入失败：{error}", "Failed to load the cache: {error}").format(error=exc),
                    parent=window,
                )
                return
            count = cache_manager.reset_same_translation_items()
            if count > 0:
                # 保存缓存
                saved = cache_manager.save_to_file(
                    project = cache_manager.get_project(),
                    items = cache_manager.get_items(),
                    output_folder = str(output_path),
                )
                if saved is not True:
                    InfoBar.error(
                        title=Localizer.localize("保存失败", "Save Failed"),
                        content=Localizer.localize("缓存写入失败，未确认重置结果，请检查输出目录权限后重试", "The cache could not be written, so the reset was not confirmed. Check the output-folder permissions and retry."),
                        parent=window,
                        duration=5000,
                    )
                    return
                InfoBar.success(
                    title=Localizer.localize("重置成功", "Reset Complete"),
                    content=Localizer.localize("已将 {count} 条原译相同的条目重置为未翻译状态，可点击「继续任务」重新翻译", "Reset {count} source-equals-translation entries to untranslated. Use Continue Task to translate them again.").format(count=count),
                    parent=window,
                    duration=5000
                )
                # 更新界面显示
                self.emit(Base.Event.TRANSLATION_UPDATE, cache_manager.get_project().get_extras())
            else:
                InfoBar.info(
                    title=Localizer.localize("无需重置", "No Reset Needed"),
                    content=Localizer.localize("没有找到原译相同的条目", "No source-equals-translation entries were found."),
                    parent=window,
                    duration=3000
                )

        self.action_retry_failed = parent.add_action(
            Action(FluentIcon.SYNC, Localizer.localize("重翻失败项", "Retry Failed Entries"), parent, triggered = triggered),
        )
        self.action_retry_failed.setEnabled(False)

    # 导出已完成的内容
    def add_command_bar_action_export(self, parent: CommandBarCard, config: Config, window: FluentWindow) -> None:
        def triggered() -> None:
            self.emit(Base.Event.TRANSLATION_MANUAL_EXPORT, {})
            self.emit(Base.Event.APP_TOAST_SHOW, {
                "type": Base.ToastType.SUCCESS,
                "message": Localizer.get().task_success,
            })

        self.action_export = parent.add_action(
            Action(FluentIcon.SHARE, Localizer.get().translation_page_export, parent, triggered = triggered),
        )
        self.action_export.installEventFilter(ToolTipFilter(self.action_export, 300, ToolTipPosition.TOP))
        self.action_export.setToolTip(Localizer.get().translation_page_export_tooltip)
        self.action_export.setEnabled(False)

    # 从缓存重新注入
    def add_command_bar_action_reinject_cache(self, parent: CommandBarCard, config: Config, window: FluentWindow) -> None:
        def triggered() -> None:
            message_box = MessageBox(
                Localizer.get().alert,
                Localizer.get().translation_page_reinject_cache_confirm,
                window,
            )
            message_box.yesButton.setText(Localizer.get().confirm)
            message_box.cancelButton.setText(Localizer.get().cancel)

            if not message_box.exec():
                return

            current_config = Config().load()
            self.emit(Base.Event.TRANSLATION_CACHE_REINJECT, {
                "output_folder": current_config.output_folder,
            })

        self.action_reinject_cache = parent.add_action(
            Action(FluentIcon.SYNC, Localizer.get().translation_page_reinject_cache, parent, triggered = triggered),
        )
        self.action_reinject_cache.installEventFilter(ToolTipFilter(self.action_reinject_cache, 300, ToolTipPosition.TOP))
        self.action_reinject_cache.setToolTip(Localizer.get().translation_page_reinject_cache_tooltip)
        self.action_reinject_cache.setEnabled(False)

    def add_command_bar_action_estimate(self, parent: CommandBarCard, config: Config, window: FluentWindow) -> None:

        def triggered() -> None:
            if self._token_estimate_running:
                return
            current_config = Config().load()
            platform = current_config.get_platform(current_config.activate_platform)
            if platform is None:
                InfoBar.warning(
                    title=Localizer.localize("估算失败", "Estimate Failed"),
                    content=Localizer.localize("未找到激活的平台配置", "No active API configuration was found."),
                    parent=window,
                    duration=3000,
                )
                return

            self._token_estimate_running = True
            self.action_estimate.setEnabled(False)
            InfoBar.info(
                title=Localizer.localize("正在估算", "Estimating"),
                content=Localizer.localize("正在读取当前项目缓存或输入目录…", "Reading the current project cache or input folder..."),
                parent=window,
                duration=2000,
            )

            def task() -> None:
                try:
                    items = self._load_items_for_token_estimate(current_config)
                    if not items:
                        raise ValueError(Localizer.localize("当前项目没有可估算的翻译条目", "The current project has no translation entries to estimate."))
                    result = TokenEstimator(current_config, platform, items).estimate()
                    self.token_estimate_done.emit(result, "")
                except Exception as exc:
                    self.token_estimate_done.emit(None, str(exc))

            threading.Thread(target = task, daemon = True).start()

        self.action_estimate = parent.add_action(
            Action(FluentIcon.CALORIES, Localizer.localize("Token 估算", "Token Estimate"), parent, triggered=triggered),
        )

    def _load_items_for_token_estimate(self, config: Config) -> list:
        """按运行缓存、磁盘缓存、输入目录的顺序读取估算条目。"""
        output_path = resolve_translation_output(config)
        translator = getattr(Engine.get(), "translator", None)
        runtime_manager = getattr(translator, "cache_manager", None)
        if runtime_manager is not None:
            runtime_items = runtime_manager.copy_items()
            runtime_output = str(
                getattr(translator, "_active_cache_output_folder", "")
                or getattr(translator, "_last_runtime_output_folder", "")
                or ""
            ).strip()
            same_project = bool(
                runtime_output
                and output_path is not None
                and os.path.normcase(os.path.abspath(runtime_output))
                == os.path.normcase(os.path.abspath(str(output_path)))
            )
            if runtime_items and same_project:
                return runtime_items

        if output_path is not None:
            manager = CacheManager(service = False)
            try:
                manager.load_items_from_file(str(output_path), strict = True)
                if manager.get_items():
                    return manager.get_items()
            except Exception:
                pass

        # 首次翻译尚未产生缓存时，直接按统一输入目录预读。
        _, items = FileManager(config).read_from_path()
        return items

    def _on_token_estimate_done(self, result, error: str) -> None:
        self._token_estimate_running = False
        self.action_estimate.setEnabled(True)
        if error:
            self.emit(Base.Event.APP_TOAST_SHOW, {
                "type": Base.ToastType.WARNING,
                "message": Localizer.localize("Token 估算失败：{error}", "Token estimate failed: {error}").format(error=error),
            })
            return
        if result is None or result.untranslated_count == 0:
            self.emit(Base.Event.APP_TOAST_SHOW, {
                "type": Base.ToastType.INFO,
                "message": Localizer.localize("所有条目已翻译完成，或当前没有待翻译内容。", "All entries are translated, or there is no untranslated content."),
            })
            return

        def format_tokens(n: int) -> str:
            if n < 1000:
                return f"{n}"
            if n < 1_000_000:
                return f"{n / 1000:.1f}K"
            return f"{n / 1_000_000:.2f}M"

        lines = [
            Localizer.localize("待翻译条目: {count}", "Untranslated entries: {count}").format(count=result.untranslated_count),
            Localizer.localize("预估批次数: {count}", "Estimated batches: {count}").format(count=result.batch_count),
            Localizer.localize("原文 Token: ~{count}", "Source tokens: ~{count}").format(count=format_tokens(result.total_source_tokens)),
            Localizer.localize("预估输入 Token: ~{count}", "Estimated input tokens: ~{count}").format(count=format_tokens(result.estimated_input_tokens)),
            Localizer.localize("预估输出 Token: ~{count}", "Estimated output tokens: ~{count}").format(count=format_tokens(result.estimated_output_tokens)),
        ]
        if result.estimated_cost > 0:
            lines.append(Localizer.localize("预估费用: ${cost:.4f}", "Estimated cost: ${cost:.4f}").format(cost=result.estimated_cost))
        # QWidget.window 是方法，不能作为 QDialog 的 parent 传入。
        message_box = MessageBox(Localizer.localize("Token 估算", "Token Estimate"), "\n".join(lines), self)
        message_box.yesButton.setText(Localizer.get().confirm)
        message_box.cancelButton.hide()
        message_box.exec()

    # 定时器
    def add_command_bar_action_timer(self, parent: CommandBarCard, config: Config, window: FluentWindow) -> None:

        interval = 1
        delay_time = None

        def format_time(full: int) -> str:
            hours = int(full / 3600)
            minutes = int((full - hours * 3600) / 60)
            seconds = full - hours * 3600 - minutes * 60

            return f"{hours:02}:{minutes:02}:{seconds:02}"

        def timer_interval() -> None:
            nonlocal interval
            nonlocal delay_time

            if not isinstance(delay_time, int):
                return None

            if delay_time > 0:
                delay_time = delay_time - interval
                self.action_timer.setText(format_time(delay_time))
            else:
                self._request_translation_start(Base.TranslationStatus.UNTRANSLATED, window)

                delay_time = None
                self.action_timer.setText(Localizer.get().timer)

        def message_box_close(widget: TimerMessageBox, input_time: QTime) -> None:
            nonlocal delay_time

            delay_time = input_time.hour() * 3600 + input_time.minute() * 60 + input_time.second()

        def triggered() -> None:
            nonlocal delay_time

            if not isinstance(delay_time, int):
                TimerMessageBox(
                    parent = window,
                    title = Localizer.get().translation_page_timer,
                    message_box_close = message_box_close,
                ).exec()
            else:
                message_box = MessageBox(Localizer.get().alert, Localizer.get().alert_reset_timer, window)
                message_box.yesButton.setText(Localizer.get().confirm)
                message_box.cancelButton.setText(Localizer.get().cancel)

                # 点击取消，则不触发开始翻译事件
                if not message_box.exec():
                    return

                delay_time = None
                self.action_timer.setText(Localizer.get().timer)

        self.action_timer = parent.add_action(
            Action(FluentIcon.HISTORY, Localizer.get().timer, parent, triggered = triggered)
        )

        # 定时检查
        timer = QTimer(self)
        timer.setInterval(interval * 1000)
        timer.timeout.connect(timer_interval)
        timer.start()

    # 显示信息条
    def indeterminate_show(self, msg: str) -> None:
        self.indeterminate.show()
        self.info_label.show()
        self.info_label.setText(msg)

    # 隐藏信息条
    def indeterminate_hide(self) -> None:
        self.indeterminate.hide()
        self.info_label.hide()
        self.info_label.setText("")
