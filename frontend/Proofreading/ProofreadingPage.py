import re
import threading
import time

from PyQt5.QtCore import Qt
from PyQt5.QtCore import QTimer
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtGui import QShowEvent
from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import QLayout
from PyQt5.QtWidgets import QVBoxLayout
from PyQt5.QtWidgets import QWidget
from qfluentwidgets import Action
from qfluentwidgets import CaptionLabel
from qfluentwidgets import FluentIcon
from qfluentwidgets import FluentWindow
from qfluentwidgets import IndeterminateProgressRing
from qfluentwidgets import MessageBox
from qfluentwidgets import ToolTipFilter
from qfluentwidgets import ToolTipPosition

from base.Base import Base
from frontend.Proofreading.FilterDialog import FilterDialog
from frontend.Proofreading.PaginationBar import PaginationBar
from frontend.Proofreading.ProofreadingTableWidget import ProofreadingTableWidget
from module.Cache.CacheItem import CacheItem
from module.Cache.CacheManager import CacheManager
from module.Config import Config
from module.Engine.Engine import Engine
from module.File.FileManager import FileManager
from module.Localizer.Localizer import Localizer
from module.ResultChecker import ResultChecker
from module.ResultChecker import WarningType
from widget.CommandBarCard import CommandBarCard
from widget.SearchCard import SearchCard

class ProofreadingPage(QWidget, Base):
    """校对任务主页面"""

    items_loaded = pyqtSignal(list)
    translate_done = pyqtSignal(object, bool)
    save_done = pyqtSignal(bool)
    export_done = pyqtSignal(bool, str)
    warnings_batch_updated = pyqtSignal(int, object)
    warnings_check_done = pyqtSignal(int)

    def __init__(self, text: str, window: FluentWindow) -> None:
        super().__init__(window)
        self.setObjectName(text.replace(" ", "-"))

        self.window = window
        self.items: list[CacheItem] = []
        self.filtered_items: list[CacheItem] = []
        self.warning_map: dict[int, list[WarningType]] = {}
        self.result_checker: ResultChecker | None = None
        self.is_readonly: bool = False
        self.config: Config | None = None
        self.filter_options: dict = {}
        self.search_keyword: str = ""
        self.search_is_regex: bool = False
        self.search_match_indices: list[int] = []
        self.search_current_match: int = -1
        self._warning_check_id: int = 0

        self.root = QVBoxLayout(self)
        self.root.setSpacing(8)
        self.root.setContentsMargins(24, 24, 24, 24)

        self.add_widget_body(self.root, window)
        self.add_widget_foot(self.root, window)

        self.subscribe(Base.Event.TRANSLATION_START, self._on_engine_status_changed)
        self.subscribe(Base.Event.TRANSLATION_UPDATE, self._on_engine_status_changed)
        self.subscribe(Base.Event.TRANSLATION_DONE, self._on_engine_status_changed)
        self.subscribe(Base.Event.TRANSLATION_STOP, self._on_engine_status_changed)

        self.items_loaded.connect(self._on_items_loaded_ui)
        self.translate_done.connect(self._on_translate_done_ui)
        self.save_done.connect(self._on_save_done_ui)
        self.export_done.connect(self._on_export_done_ui)
        self.warnings_batch_updated.connect(self._on_warnings_batch_updated_ui)
        self.warnings_check_done.connect(self._on_warnings_check_done_ui)

        self._indeterminate_start_time: float = 0.0
        self._indeterminate_hide_timer: QTimer | None = None

    def add_widget_body(self, parent: QLayout, window: FluentWindow) -> None:
        self.table_widget = ProofreadingTableWidget()
        self.table_widget.cell_edited.connect(self._on_cell_edited)
        self.table_widget.retranslate_clicked.connect(self._on_retranslate_clicked)
        self.table_widget.copy_src_clicked.connect(self._on_copy_src_clicked)
        self.table_widget.copy_dst_clicked.connect(self._on_copy_dst_clicked)
        self.table_widget.set_items([], {})

        parent.addWidget(self.table_widget, 1)

    def add_widget_foot(self, parent: QLayout, window: FluentWindow) -> None:
        self.search_card = SearchCard(self)
        self.search_card.setVisible(False)
        parent.addWidget(self.search_card)

        self.search_card.on_back_clicked(lambda w: self._on_search_back_clicked())
        self.search_card.on_prev_clicked(lambda w: self._on_search_prev_clicked())
        self.search_card.on_next_clicked(lambda w: self._on_search_next_clicked())
        self.search_card.on_search_triggered(lambda w: self._do_search())

        self.command_bar_card = CommandBarCard()
        parent.addWidget(self.command_bar_card)

        self.command_bar_card.set_minimum_width(640)

        self.btn_load = self.command_bar_card.add_action(
            Action(FluentIcon.DOWNLOAD, Localizer.get().proofreading_page_load, triggered = self._on_load_clicked)
        )

        action_save = Action(FluentIcon.SAVE, Localizer.get().proofreading_page_save, triggered = self._on_save_clicked)
        action_save.setShortcut("Ctrl+S")
        self.btn_save = self.command_bar_card.add_action(action_save)
        self.btn_save.installEventFilter(ToolTipFilter(self.btn_save, 300, ToolTipPosition.TOP))
        self.btn_save.setToolTip(Localizer.get().proofreading_page_save_tooltip)
        self.btn_save.setEnabled(False)

        self.command_bar_card.add_separator()
        self.btn_export = self.command_bar_card.add_action(
            Action(FluentIcon.SHARE, Localizer.get().proofreading_page_export, triggered = self._on_export_clicked)
        )
        self.btn_export.installEventFilter(ToolTipFilter(self.btn_export, 300, ToolTipPosition.TOP))
        self.btn_export.setToolTip(Localizer.get().proofreading_page_export_tooltip)
        self.btn_export.setEnabled(False)

        self.command_bar_card.add_separator()
        self.btn_search = self.command_bar_card.add_action(
            Action(FluentIcon.SEARCH, Localizer.get().proofreading_page_search, triggered = self._on_search_clicked)
        )
        self.btn_search.setEnabled(False)

        self.btn_filter = self.command_bar_card.add_action(
            Action(FluentIcon.FILTER, Localizer.get().proofreading_page_filter, triggered = self._on_filter_clicked)
        )
        self.btn_filter.setEnabled(False)

        self.command_bar_card.add_separator()

        self.pagination_bar = PaginationBar()
        self.pagination_bar.page_changed.connect(self._on_page_changed)
        self.command_bar_card.add_widget_to_command_bar(self.pagination_bar)
        self.command_bar_card.add_stretch(1)

        self.info_label = CaptionLabel("", self)
        self.info_label.setTextColor(QColor(96, 96, 96), QColor(160, 160, 160))
        self.info_label.hide()

        self.indeterminate = IndeterminateProgressRing()
        self.indeterminate.setFixedSize(16, 16)
        self.indeterminate.setStrokeWidth(3)
        self.indeterminate.hide()

        self.command_bar_card.add_widget(self.info_label)
        self.command_bar_card.add_spacing(4)
        self.command_bar_card.add_widget(self.indeterminate)

    def _on_load_clicked(self) -> None:
        self.indeterminate_show(Localizer.get().proofreading_page_indeterminate_loading)
        self.load_data()

    def load_data(self) -> None:
        def task() -> None:
            try:
                self.config = Config().load()
                cache_manager = CacheManager(service = False)
                cache_manager.load_items_from_file(self.config.output_folder)
                items = cache_manager.get_items()
                items = [i for i in items if i.get_src().strip()]

                if not items:
                    self.emit(Base.Event.APP_TOAST_SHOW, {
                        "type": Base.ToastType.WARNING,
                        "message": Localizer.get().proofreading_page_no_cache,
                    })
                    self.items_loaded.emit([])
                    return

                self.items = items
                self.warning_map = {}
                self.result_checker = ResultChecker(self.config, items)
                self.filter_options = {}
                self._warning_check_id += 1
                check_id = self._warning_check_id

                self.items_loaded.emit(items)
                self._start_warning_check(items, self.result_checker, check_id)

            except Exception as e:
                self.error(f"{Localizer.get().proofreading_page_load_failed}", e)
                self.emit(Base.Event.APP_TOAST_SHOW, {
                    "type": Base.ToastType.ERROR,
                    "message": Localizer.get().proofreading_page_load_failed,
                })
                self.items_loaded.emit([])

        threading.Thread(target = task, daemon = True).start()

    def _start_warning_check(self, items: list[CacheItem], checker: ResultChecker, check_id: int) -> None:
        def task() -> None:
            batch: dict[int, list[WarningType]] = {}
            batch_size = 200
            for idx, item in enumerate(items):
                warnings = checker.check_single_item(item)
                if warnings:
                    batch[id(item)] = warnings

                if len(batch) >= batch_size:
                    self.warnings_batch_updated.emit(check_id, batch)
                    batch = {}

                if idx % 2000 == 0:
                    time.sleep(0)

            if batch:
                self.warnings_batch_updated.emit(check_id, batch)
            self.warnings_check_done.emit(check_id)

        threading.Thread(target = task, daemon = True).start()

    def _on_warnings_batch_updated_ui(self, check_id: int, batch: dict[int, list[WarningType]]) -> None:
        if check_id != self._warning_check_id or not batch:
            return

        self.warning_map.update(batch)

        for row in range(self.table_widget.rowCount()):
            item = self.table_widget.get_item_at_row(row)
            if not item:
                continue
            warnings = batch.get(id(item))
            if warnings is not None:
                self.table_widget.update_row_status(row, warnings)

    def _on_warnings_check_done_ui(self, check_id: int) -> None:
        if check_id != self._warning_check_id:
            return

        warning_types = self.filter_options.get(FilterDialog.KEY_WARNING_TYPES)
        glossary_terms = self.filter_options.get(FilterDialog.KEY_GLOSSARY_TERMS)
        if warning_types is not None or glossary_terms is not None:
            self._apply_filter()

    def _on_items_loaded_ui(self, items: list[CacheItem]) -> None:
        self.indeterminate_hide()

        if items:
            self._apply_filter()
        else:
            self.table_widget.set_items([], {})
            self.pagination_bar.reset()

        self._check_engine_status()

    def _on_filter_clicked(self) -> None:
        if not self.items:
            self.emit(Base.Event.APP_TOAST_SHOW, {
                "type": Base.ToastType.WARNING,
                "message": Localizer.get().proofreading_page_no_cache,
            })
            return

        if not self.config:
            return

        checker = self.result_checker or ResultChecker(self.config, self.items)
        dialog = FilterDialog(self.items, self.warning_map, checker, self.config, self.window)
        dialog.set_filter_options(self.filter_options)

        if dialog.exec():
            self.filter_options = dialog.get_filter_options()
            self._apply_filter()

    def _apply_filter(self) -> None:
        warning_types = self.filter_options.get(FilterDialog.KEY_WARNING_TYPES)
        statuses = self.filter_options.get(FilterDialog.KEY_STATUSES)
        file_paths = self.filter_options.get(FilterDialog.KEY_FILE_PATHS)
        glossary_terms = self.filter_options.get(FilterDialog.KEY_GLOSSARY_TERMS)

        filtered = []
        for item in self.items:
            if item.get_status() in (Base.TranslationStatus.EXCLUDED, Base.TranslationStatus.DUPLICATED):
                continue

            if warning_types is not None:
                item_warnings = self.warning_map.get(id(item), [])
                if item_warnings and not any(e in warning_types for e in item_warnings):
                    continue
                if not item_warnings and FilterDialog.NO_WARNING_TAG not in warning_types:
                    continue

            if glossary_terms is not None:
                item_warnings = self.warning_map.get(id(item), [])
                if WarningType.GLOSSARY not in item_warnings:
                    continue
                checker = self.result_checker or ResultChecker(self.config, [item])
                failed_terms = checker.get_failed_glossary_terms(item)
                if not any(term in glossary_terms for term in failed_terms):
                    continue

            if statuses is not None and item.get_status() not in statuses:
                continue

            if file_paths is not None and item.get_file_path() not in file_paths:
                continue

            filtered.append(item)

        self.filtered_items = filtered
        self.pagination_bar.set_total(len(filtered))
        self.pagination_bar.set_page(1)
        self._render_page(1)

        self.search_match_indices = []
        self.search_current_match = -1
        self.search_card.clear_match_info()

    def _on_search_clicked(self) -> None:
        self.search_card.setVisible(True)
        self.command_bar_card.setVisible(False)
        self.search_card.get_line_edit().setFocus()

    def _on_search_back_clicked(self) -> None:
        self.search_keyword = ""
        self.search_is_regex = False
        self.search_match_indices = []
        self.search_current_match = -1
        self.search_card.clear_match_info()
        self.search_card.setVisible(False)
        self.command_bar_card.setVisible(True)

    def _do_search(self) -> None:
        keyword = self.search_card.get_keyword()
        if not keyword:
            self.search_match_indices = []
            self.search_current_match = -1
            self.search_card.clear_match_info()
            return

        is_regex = self.search_card.is_regex_mode()
        if is_regex:
            is_valid, error_msg = self.search_card.validate_regex()
            if not is_valid:
                self.emit(Base.Event.APP_TOAST_SHOW, {
                    "type": Base.ToastType.ERROR,
                    "message": f"{Localizer.get().search_regex_invalid}: {error_msg}",
                })
                return

        self.search_keyword = keyword
        self.search_is_regex = is_regex

        self._build_match_indices()

        if not self.search_match_indices:
            self.search_card.set_match_info(0, 0)
            self.emit(Base.Event.APP_TOAST_SHOW, {
                "type": Base.ToastType.WARNING,
                "message": Localizer.get().search_no_match,
            })
            return

        self.search_current_match = 0
        self._jump_to_match()

    def _build_match_indices(self) -> None:
        self.search_match_indices = []

        if not self.search_keyword:
            return

        keyword = self.search_keyword
        is_regex = self.search_is_regex

        if is_regex:
            try:
                pattern = re.compile(keyword, re.IGNORECASE)
            except re.error:
                return
        else:
            keyword_lower = keyword.lower()

        for idx, item in enumerate(self.filtered_items):
            src = item.get_src()
            dst = item.get_dst()

            if is_regex:
                if pattern.search(src) or pattern.search(dst):
                    self.search_match_indices.append(idx)
            else:
                if keyword_lower in src.lower() or keyword_lower in dst.lower():
                    self.search_match_indices.append(idx)

    def _on_search_prev_clicked(self) -> None:
        if not self.search_match_indices:
            self._do_search()
            return

        self.search_current_match -= 1
        if self.search_current_match < 0:
            self.search_current_match = len(self.search_match_indices) - 1
        self._jump_to_match()

    def _on_search_next_clicked(self) -> None:
        if not self.search_match_indices:
            self._do_search()
            return

        self.search_current_match += 1
        if self.search_current_match >= len(self.search_match_indices):
            self.search_current_match = 0
        self._jump_to_match()

    def _jump_to_match(self) -> None:
        if not self.search_match_indices or self.search_current_match < 0:
            return

        total = len(self.search_match_indices)
        current = self.search_current_match + 1
        self.search_card.set_match_info(current, total)

        item_index = self.search_match_indices[self.search_current_match]
        page_size = self.pagination_bar.get_page_size()
        target_page = (item_index // page_size) + 1

        current_page = self.pagination_bar.get_page()
        if target_page != current_page:
            self.pagination_bar.set_page(target_page)
            self._render_page(target_page)

        row_in_page = item_index % page_size
        self.table_widget.select_row(row_in_page)

    def _on_page_changed(self, page: int) -> None:
        self._render_page(page)

    def _render_page(self, page_num: int) -> None:
        page_size = self.pagination_bar.get_page_size()
        start_idx = (page_num - 1) * page_size
        end_idx = start_idx + page_size

        page_items = self.filtered_items[start_idx:end_idx]
        page_warning_map = {id(item): self.warning_map.get(id(item), []) for item in page_items}

        self.table_widget.set_items(page_items, page_warning_map)

    def _on_cell_edited(self, item: CacheItem, new_dst: str) -> None:
        if self.is_readonly:
            return

        item.set_dst(new_dst)

        if new_dst and item.get_status() not in (Base.TranslationStatus.TRANSLATED, Base.TranslationStatus.TRANSLATED_IN_PAST):
            item.set_status(Base.TranslationStatus.TRANSLATED)

        self._recheck_item(item)

    def _recheck_item(self, item: CacheItem) -> None:
        if not self.config:
            return

        checker = ResultChecker(self.config, [item])
        warnings = checker.check_single_item(item)

        if warnings:
            self.warning_map[id(item)] = warnings
        else:
            self.warning_map.pop(id(item), None)

        row = self.table_widget.find_row_by_item(item)
        if row >= 0:
            self.table_widget.update_row_status(row, warnings)

    def _on_copy_src_clicked(self, item: CacheItem) -> None:
        clipboard = QApplication.clipboard()
        clipboard.setText(item.get_src())

        self.emit(Base.Event.APP_TOAST_SHOW, {
            "type": Base.ToastType.SUCCESS,
            "message": Localizer.get().proofreading_page_copy_src_done,
        })

    def _on_copy_dst_clicked(self, item: CacheItem) -> None:
        clipboard = QApplication.clipboard()
        clipboard.setText(item.get_dst())

        self.emit(Base.Event.APP_TOAST_SHOW, {
            "type": Base.ToastType.SUCCESS,
            "message": Localizer.get().proofreading_page_copy_dst_done,
        })

    def _on_retranslate_clicked(self, item: CacheItem) -> None:
        if self.is_readonly or not self.config:
            return

        message_box = MessageBox(
            Localizer.get().confirm,
            Localizer.get().proofreading_page_retranslate_confirm,
            self.window
        )
        message_box.yesButton.setText(Localizer.get().confirm)
        message_box.cancelButton.setText(Localizer.get().cancel)

        if not message_box.exec():
            return

        row = self.table_widget.find_row_by_item(item)
        if row >= 0:
            self.table_widget.set_row_loading(row, True)

        item.set_status(Base.TranslationStatus.UNTRANSLATED)
        item.set_retry_count(0)

        Engine.get().translate_single_item(
            item = item,
            config = self.config,
            callback = lambda i, s: self.translate_done.emit(i, s)
        )

    def _on_translate_done_ui(self, item: CacheItem, success: bool) -> None:
        row = self.table_widget.find_row_by_item(item)
        if row < 0:
            return

        self.table_widget.set_row_loading(row, False)

        if success:
            self.table_widget.update_row_dst(row, item.get_dst())
            self._recheck_item(item)

            self.emit(Base.Event.APP_TOAST_SHOW, {
                "type": Base.ToastType.SUCCESS,
                "message": Localizer.get().proofreading_page_retranslate_success,
            })
        else:
            item.set_status(Base.TranslationStatus.TRANSLATED)
            self.emit(Base.Event.APP_TOAST_SHOW, {
                "type": Base.ToastType.ERROR,
                "message": Localizer.get().proofreading_page_retranslate_failed,
            })

    def _on_save_clicked(self) -> None:
        self.indeterminate_show(Localizer.get().proofreading_page_indeterminate_saving)
        self.save_data()

    def save_data(self) -> None:
        if self.is_readonly or not self.config or not self.items:
            self.indeterminate_hide()
            return

        config = self.config
        items = self.items

        def task() -> None:
            try:
                cache_manager = CacheManager(service = False)
                cache_manager.set_items(items)
                cache_manager.load_project_from_file(config.output_folder)
                cache_manager.save_to_file(
                    project = cache_manager.get_project(),
                    items = items,
                    output_folder = config.output_folder
                )
                self.save_done.emit(True)
            except Exception as e:
                self.error(f"{Localizer.get().proofreading_page_save_failed}", e)
                self.save_done.emit(False)

        threading.Thread(target = task, daemon = True).start()

    def _on_save_done_ui(self, success: bool) -> None:
        pending_export = getattr(self, "_pending_export", False)
        self._pending_export = False

        if pending_export:
            if success:
                self.indeterminate_show(Localizer.get().proofreading_page_indeterminate_exporting)
                self.export_data()
            else:
                self.indeterminate_hide()
                self.emit(Base.Event.APP_TOAST_SHOW, {
                    "type": Base.ToastType.ERROR,
                    "message": Localizer.get().proofreading_page_save_failed,
                })
        else:
            self.indeterminate_hide()
            if success:
                self.emit(Base.Event.APP_TOAST_SHOW, {
                    "type": Base.ToastType.SUCCESS,
                    "message": Localizer.get().proofreading_page_save_success,
                })
            else:
                self.emit(Base.Event.APP_TOAST_SHOW, {
                    "type": Base.ToastType.ERROR,
                    "message": Localizer.get().proofreading_page_save_failed,
                })

    def _on_export_clicked(self) -> None:
        message_box = MessageBox(
            Localizer.get().confirm,
            Localizer.get().proofreading_page_export_confirm,
            self.window
        )
        message_box.yesButton.setText(Localizer.get().confirm)
        message_box.cancelButton.setText(Localizer.get().cancel)

        if not message_box.exec():
            return

        self._pending_export = True
        self.indeterminate_show(Localizer.get().proofreading_page_indeterminate_saving)
        self.save_data()

    def export_data(self) -> None:
        if not self.config or not self.items:
            self.export_done.emit(False, "")
            return

        config = self.config
        items = self.items

        def task() -> None:
            try:
                FileManager(config).write_to_path(items)
                self.export_done.emit(True, "")
            except Exception as e:
                self.error("Export failed", e)
                self.export_done.emit(False, str(e))

        threading.Thread(target = task, daemon = True).start()

    def _on_export_done_ui(self, success: bool, error_msg: str) -> None:
        self.indeterminate_hide()
        if success:
            self.emit(Base.Event.APP_TOAST_SHOW, {
                "type": Base.ToastType.SUCCESS,
                "message": Localizer.get().proofreading_page_export_success,
            })
        else:
            self.emit(Base.Event.APP_TOAST_SHOW, {
                "type": Base.ToastType.ERROR,
                "message": error_msg or Localizer.get().proofreading_page_export_failed,
            })

    def _on_engine_status_changed(self, event: Base.Event, data: dict) -> None:
        self._check_engine_status()

    def _check_engine_status(self) -> None:
        engine_status = Engine.get().get_status()
        is_busy = engine_status in (Engine.Status.TRANSLATING, Engine.Status.STOPPING)

        if is_busy and self.items:
            self.items = []
            self.filtered_items = []
            self.warning_map = {}
            self.result_checker = None
            self._warning_check_id += 1
            self.table_widget.set_items([], {})
            self.pagination_bar.reset()

        has_items = bool(self.items)

        self.btn_load.setEnabled(not is_busy)

        can_operate = not is_busy and has_items
        self.btn_save.setEnabled(can_operate)
        self.btn_export.setEnabled(can_operate)
        self.btn_search.setEnabled(can_operate)
        self.btn_filter.setEnabled(can_operate)

        if is_busy != self.is_readonly:
            self.is_readonly = is_busy
            self.table_widget.set_readonly(is_busy)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._check_engine_status()

    def indeterminate_show(self, msg: str) -> None:
        if self._indeterminate_hide_timer is not None:
            self._indeterminate_hide_timer.stop()
            self._indeterminate_hide_timer = None

        if not self.indeterminate.isVisible():
            self._indeterminate_start_time = time.time()

        self.indeterminate.show()
        self.info_label.show()
        self.info_label.setText(msg)

    def indeterminate_hide(self) -> None:
        if not self.indeterminate.isVisible():
            return

        min_display_ms = 1500
        elapsed_ms = (time.time() - self._indeterminate_start_time) * 1000
        remaining_ms = min_display_ms - elapsed_ms

        if remaining_ms > 0:
            self._indeterminate_hide_timer = QTimer()
            self._indeterminate_hide_timer.setSingleShot(True)
            self._indeterminate_hide_timer.timeout.connect(self._do_indeterminate_hide)
            self._indeterminate_hide_timer.start(int(remaining_ms))
        else:
            self._do_indeterminate_hide()

    def _do_indeterminate_hide(self) -> None:
        self._indeterminate_hide_timer = None
        self.indeterminate.hide()
        self.info_label.hide()
        self.info_label.setText("")
