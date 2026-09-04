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
from PyQt5.QtWidgets import QSizePolicy
from PyQt5.QtWidgets import QVBoxLayout

from qfluentwidgets import Action
from qfluentwidgets import InfoBar
from qfluentwidgets import TimeEdit
from qfluentwidgets import CardWidget
from qfluentwidgets import FluentIcon
from qfluentwidgets import FlowLayout
from qfluentwidgets import MessageBox
from qfluentwidgets import MessageBoxBase
from qfluentwidgets import FluentWindow
from qfluentwidgets import ProgressRing
from qfluentwidgets import CaptionLabel
from qfluentwidgets import SubtitleLabel
from qfluentwidgets import TitleLabel
from qfluentwidgets import StrongBodyLabel
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

        # 紧凑指标卡：保留原有数据接口，只收敛视觉密度与自适应尺寸。
        self.setBorderRadius(8)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumWidth(130)
        self.setFixedHeight(88)

        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(14, 12, 14, 12) # 左、上、右、下
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

        if callable(init):
            init(self)

        if callable(clicked):
            self.clicked.connect(lambda : clicked(self))

    def set_unit(self, unit: str) -> None:
        self.unit_label.setText(unit)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)

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

        # 设置主容器
        self.container = QVBoxLayout(self)
        self.container.setSpacing(8)
        self.container.setContentsMargins(24, 24, 24, 24) # 左、上、右、下

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
            self.data = data

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

        speed = self.data.get("total_output_tokens", 0) / max(1, time.time() - self.data.get("start_time", 0))
        self.waveform.add_value(speed)
        if speed < 1000:
            self.speed.set_unit("T/S")
            self.speed.set_value(f"{speed:.2f}")
        else:
            self.speed.set_unit("KT/S")
            self.speed.set_value(f"{(speed / 1000):.2f}")

    # 更新进度环
    def update_status(self, data: dict) -> None:
        if Engine.get().get_status() == Engine.Status.STOPPING:
            percent = min(1.0, max(0.0, self.data.get("line", 0) / max(1, self.data.get("total_line", 0))))
            self.ring.setValue(int(percent * 10000))
            self.ring.setFormat(f"{Localizer.get().translation_page_status_stopping}\n{percent * 100:.2f}%")
        elif Engine.get().get_status() == Engine.Status.TRANSLATING:
            percent = min(1.0, max(0.0, self.data.get("line", 0) / max(1, self.data.get("total_line", 0))))
            self.ring.setValue(int(percent * 10000))
            self.ring.setFormat(f"{Localizer.get().translation_page_status_translating}\n{percent * 100:.2f}%")
        elif Engine.get().get_status() == Engine.Status.QUALITY:
            quality = self.data.get("quality_task", {})
            completed = quality.get("completed_count", 0) if isinstance(quality, dict) else 0
            total = quality.get("total_count", 0) if isinstance(quality, dict) else 0
            percent = completed / max(1, total)
            self.ring.setValue(int(percent * 10000))
            quality_label = self._quality_status_label(quality)
            self.ring.setFormat(f"{quality_label}\n{percent * 100:.2f}%")
        else:
            # 空闲状态：如果有缓存数据，显示缓存的进度
            line = self.data.get("line", 0)
            total_line = self.data.get("total_line", 0)
            if line > 0 and total_line > 0:
                percent = min(1.0, max(0.0, line / total_line))
                self.ring.setValue(int(percent * 10000))
                self.ring.setFormat(f"{Localizer.get().translation_page_status_idle}\n{line}/{total_line}")
            else:
                self.ring.setValue(0)
                self.ring.setFormat(Localizer.get().translation_page_status_idle)

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
        head_shell = QWidget(self)
        head_shell_layout = QVBoxLayout(head_shell)
        head_shell_layout.setContentsMargins(0, 0, 0, 4)
        head_shell_layout.setSpacing(4)

        header = QWidget(head_shell)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(2)
        header_layout.addWidget(TitleLabel(Localizer.get().translation_page_header_title, header))
        description = CaptionLabel(
            Localizer.get().translation_page_header_description,
            header,
        )
        description.setWordWrap(True)
        header_layout.addWidget(description)
        head_shell_layout.addWidget(header)

        self.head_hbox_container = QWidget(self)
        self.head_hbox = QHBoxLayout(self.head_hbox_container)
        head_shell_layout.addWidget(self.head_hbox_container)
        parent.addWidget(head_shell)

        # 波形图
        self.waveform = WaveformWidget()
        self.waveform.set_matrix_size(100, 20)

        waveform_vbox_container = QWidget()
        waveform_vbox = QVBoxLayout(waveform_vbox_container)
        waveform_vbox.addStretch(1)
        waveform_vbox.addWidget(self.waveform)

        # 进度环
        self.ring = ProgressRing()
        self.ring.setRange(0, 10000)
        self.ring.setValue(0)
        self.ring.setTextVisible(True)
        self.ring.setStrokeWidth(12)
        self.ring.setFixedSize(140, 140)
        self.ring.setFormat(Localizer.get().translation_page_status_idle)

        ring_vbox_container = QWidget()
        ring_vbox = QVBoxLayout(ring_vbox_container)
        ring_vbox.addStretch(1)
        ring_vbox.addWidget(self.ring)

        # 添加控件
        self.head_hbox.addWidget(ring_vbox_container)
        self.head_hbox.addSpacing(8)
        self.head_hbox.addStretch(1)
        self.head_hbox.addWidget(waveform_vbox_container)
        self.head_hbox.addStretch(1)

    # 中部
    def add_widget_body(self, parent: QLayout, config: Config, window: FluentWindow) -> None:
        self.flow_container = QWidget(self)
        self.flow_layout = FlowLayout(self.flow_container, needAni = False)
        self.flow_layout.setSpacing(8)
        self.flow_layout.setHorizontalSpacing(8)
        self.flow_layout.setVerticalSpacing(8)
        self.flow_layout.setContentsMargins(0, 0, 0, 0)

        self.add_time_card(self.flow_layout, config, window)
        self.add_remaining_time_card(self.flow_layout, config, window)
        self.add_line_card(self.flow_layout, config, window)
        self.add_remaining_line_card(self.flow_layout, config, window)
        self.add_speed_card(self.flow_layout, config, window)
        self.add_token_card(self.flow_layout, config, window)
        self.add_task_card(self.flow_layout, config, window)

        self.container.addWidget(self.flow_container, 1)

    # 底部
    def add_widget_foot(self, parent: QLayout, config: Config, window: FluentWindow) -> None:
        self.command_bar_card = CommandBarCard()
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
        self.command_bar_card.add_widget(self.info_label)
        self.command_bar_card.add_spacing(4)
        self.command_bar_card.add_widget(self.indeterminate)

    # 累计时间
    def add_time_card(self, parent: QLayout, config: Config, window: FluentWindow) -> None:
        self.time = DashboardCard(
            parent = self,
            title = Localizer.get().translation_page_card_time,
            value = Localizer.get().none,
            unit = "",
        )
        parent.addWidget(self.time)

    # 剩余时间
    def add_remaining_time_card(self, parent: QLayout, config: Config, window: FluentWindow) -> None:
        self.remaining_time = DashboardCard(
            parent = self,
            title = Localizer.get().translation_page_card_remaining_time,
            value = Localizer.get().none,
            unit = "",
        )
        parent.addWidget(self.remaining_time)

    # 翻译行数
    def add_line_card(self, parent: QLayout, config: Config, window: FluentWindow) -> None:
        self.line_card = DashboardCard(
            parent = self,
            title = Localizer.get().translation_page_card_line,
            value = Localizer.get().none,
            unit = "",
        )
        parent.addWidget(self.line_card)

    # 剩余行数
    def add_remaining_line_card(self, parent: QLayout, config: Config, window: FluentWindow) -> None:
        self.remaining_line = DashboardCard(
            parent = self,
            title = Localizer.get().translation_page_card_remaining_line,
            value = Localizer.get().none,
            unit = "",
        )
        parent.addWidget(self.remaining_line)

    # 平均速度
    def add_speed_card(self, parent: QLayout, config: Config, window: FluentWindow) -> None:
        self.speed = DashboardCard(
            parent = self,
            title = Localizer.get().translation_page_card_speed,
            value = Localizer.get().none,
            unit = "",
        )
        parent.addWidget(self.speed)

    # 累计消耗
    def add_token_card(self, parent: QLayout, config: Config, window: FluentWindow) -> None:
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
    def add_task_card(self, parent: QLayout, config: Config, window: FluentWindow) -> None:
        self.task = DashboardCard(
            parent = self,
            title = Localizer.get().translation_page_card_task,
            value = Localizer.get().none,
            unit = "",
        )
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
