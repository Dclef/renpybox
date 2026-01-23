import json
import os
from datetime import datetime

from PyQt5.QtCore import QSize
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QAbstractItemView
from PyQt5.QtWidgets import QHBoxLayout
from PyQt5.QtWidgets import QLayout
from PyQt5.QtWidgets import QListWidgetItem
from PyQt5.QtWidgets import QVBoxLayout
from PyQt5.QtWidgets import QWidget
from qfluentwidgets import CardWidget
from qfluentwidgets import CheckBox
from qfluentwidgets import FlowLayout
from qfluentwidgets import InfoBar
from qfluentwidgets import InfoBarPosition
from qfluentwidgets import ListWidget
from qfluentwidgets import MessageBoxBase
from qfluentwidgets import PushButton
from qfluentwidgets import StrongBodyLabel

from base.Base import Base
from module.Cache.CacheItem import CacheItem
from module.Config import Config
from module.Localizer.Localizer import Localizer
from module.ResultChecker import ResultChecker
from module.ResultChecker import WarningType
from widget.Separator import Separator

class FilterDialog(MessageBoxBase):
    """筛选对话框"""

    NO_WARNING_TAG = "NO_WARNING"

    KEY_WARNING_TYPES = "warning_types"
    KEY_STATUSES = "statuses"
    KEY_FILE_PATHS = "file_paths"
    KEY_GLOSSARY_TERMS = "glossary_terms"

    def __init__(
        self,
        items: list[CacheItem],
        warning_map: dict[int, list[WarningType]],
        result_checker: ResultChecker,
        config: Config,
        parent: QWidget,
    ) -> None:
        super().__init__(parent)
        self.items = [i for i in items if i.get_status() not in (Base.TranslationStatus.EXCLUDED, Base.TranslationStatus.DUPLICATED)]
        self.warning_map = warning_map
        self.result_checker = result_checker
        self.config = config
        self.glossary_error_map: dict[tuple[str, str], list[CacheItem]] = {}
        self._build_glossary_error_map()
        self._init_ui()

    def _init_ui(self) -> None:
        self.widget.setMinimumWidth(680)
        self.viewLayout.setSpacing(16)
        self.viewLayout.setContentsMargins(24, 24, 24, 24)

        self.status_checkboxes = {}
        status_types = [
            (Base.TranslationStatus.UNTRANSLATED, Localizer.get().proofreading_page_status_none),
            (Base.TranslationStatus.TRANSLATED, Localizer.get().proofreading_page_status_processed),
            (Base.TranslationStatus.TRANSLATED_IN_PAST, Localizer.get().proofreading_page_status_processed_in_past),
        ]

        self.status_card, status_layout, _ = self._create_section_card(
            Localizer.get().proofreading_page_filter_status
        )

        for status, label in status_types:
            cb = CheckBox(label)
            cb.setChecked(True)
            cb.setFixedWidth(160)
            self.status_checkboxes[status] = cb
            status_layout.addWidget(cb)

        self.viewLayout.addWidget(self.status_card)

        self.warning_checkboxes = {}
        warning_types = [
            (self.NO_WARNING_TAG, Localizer.get().proofreading_page_filter_no_warning),
            (WarningType.KANA, Localizer.get().proofreading_page_warning_kana),
            (WarningType.HANGEUL, Localizer.get().proofreading_page_warning_hangeul),
            (WarningType.TEXT_PRESERVE, Localizer.get().proofreading_page_warning_text_preserve),
            (WarningType.SIMILARITY, Localizer.get().proofreading_page_warning_similarity),
            (WarningType.GLOSSARY, Localizer.get().proofreading_page_warning_glossary),
            (WarningType.RETRY_THRESHOLD, Localizer.get().proofreading_page_warning_retry),
        ]

        self.warning_card, warning_layout, warning_head_layout = self._create_section_card(
            Localizer.get().proofreading_page_filter_warning_type
        )

        self.btn_export = PushButton(Localizer.get().proofreading_page_filter_export)
        self.btn_export.setToolTip(Localizer.get().proofreading_page_filter_export_tooltip)
        self.btn_export.clicked.connect(self._export_filtered_items)
        warning_head_layout.addWidget(self.btn_export)

        for warning_type, label in warning_types:
            cb = CheckBox(label)
            cb.setChecked(True)
            cb.setFixedWidth(160)
            self.warning_checkboxes[warning_type] = cb
            warning_layout.addWidget(cb)

        self.viewLayout.addWidget(self.warning_card)

        self.term_checkboxes = {}
        self.term_card, term_layout, term_head_layout = self._create_section_card(
            Localizer.get().proofreading_page_filter_glossary_terms,
            is_flow=False,
        )

        btn_select_all_terms = PushButton(Localizer.get().proofreading_page_filter_select_all)
        btn_deselect_all_terms = PushButton(Localizer.get().proofreading_page_filter_clear)
        for btn in (btn_select_all_terms, btn_deselect_all_terms):
            term_head_layout.addWidget(btn)

        btn_select_all_terms.clicked.connect(self._select_all_terms)
        btn_deselect_all_terms.clicked.connect(self._deselect_all_terms)

        self.term_list = ListWidget()
        self.term_list.setFixedHeight(220)
        self.term_list.setSelectionMode(QAbstractItemView.NoSelection)
        self.term_list.setFocusPolicy(Qt.NoFocus)
        self.term_list.itemClicked.connect(self._on_term_item_clicked)

        list_style = """
            ListWidget {
                background: transparent;
                border: 1px solid rgba(0, 0, 0, 0.08);
                border-radius: 6px;
                outline: none;
            }
            ListWidget::item {
                background: transparent;
                border: none;
                padding-left: 4px;
                margin: 2px 4px;
                border-radius: 4px;
            }
            ListWidget::item:hover {
                background: rgba(0, 0, 0, 0.04);
            }
            ListWidget::item:selected {
                background: transparent;
            }
        """
        self.term_list.setStyleSheet(list_style)

        self.term_empty_label = StrongBodyLabel(Localizer.get().proofreading_page_filter_no_glossary_error)
        self.term_empty_label.setAlignment(Qt.AlignCenter)
        self.term_empty_label.hide()

        term_layout.addWidget(self.term_list)
        term_layout.addWidget(self.term_empty_label)

        self._init_term_list()
        self.viewLayout.addWidget(self.term_card)

        self.file_list = ListWidget()
        self.file_list.setFixedHeight(280)
        self.file_list.setSelectionMode(QAbstractItemView.NoSelection)
        self.file_list.setFocusPolicy(Qt.NoFocus)

        self.file_list.setStyleSheet(list_style)

        file_paths = sorted(set(item.get_file_path() for item in self.items))
        self.file_checkboxes = {}

        for path in file_paths:
            display_name = path.split("/")[-1] if "/" in path else path.split("\\")[-1] if "\\" in path else path

            list_item = QListWidgetItem()
            list_item.setSizeHint(QSize(0, 36))
            list_item.setData(Qt.UserRole, path)
            self.file_list.addItem(list_item)

            cb = CheckBox(display_name)
            cb.setChecked(True)
            cb.setToolTip(path)
            cb.setAttribute(Qt.WA_TransparentForMouseEvents)
            self.file_list.setItemWidget(list_item, cb)
            self.file_checkboxes[path] = cb

        self.file_list.itemClicked.connect(self._on_file_item_clicked)

        self.file_card, file_layout, file_head_layout = self._create_section_card(
            Localizer.get().proofreading_page_filter_file,
            is_flow = False
        )

        btn_select_all = PushButton(Localizer.get().proofreading_page_filter_select_all)
        btn_deselect_all = PushButton(Localizer.get().proofreading_page_filter_clear)
        for btn in (btn_select_all, btn_deselect_all):
            file_head_layout.addWidget(btn)

        btn_select_all.clicked.connect(self._select_all_files)
        btn_deselect_all.clicked.connect(self._deselect_all_files)

        self.file_list.setMinimumWidth(600)
        file_layout.addWidget(self.file_list)

        self.viewLayout.addWidget(self.file_card)

        self.yesButton.setText(Localizer.get().confirm)
        self.cancelButton.setText(Localizer.get().cancel)

    def _create_section_card(self, title: str, is_flow: bool = True) -> tuple[CardWidget, QLayout, QHBoxLayout]:
        card = CardWidget(self.widget)
        card.setBorderRadius(4)

        root = QVBoxLayout(card)
        root.setContentsMargins(16, 16, 16, 16)

        head_container = QWidget(card)
        head_layout = QHBoxLayout(head_container)
        head_layout.setContentsMargins(0, 0, 0, 0)
        head_layout.setSpacing(8)

        text_container = QWidget(head_container)
        text_layout = QVBoxLayout(text_container)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(4)

        title_label = StrongBodyLabel(title, card)
        text_layout.addWidget(title_label)

        head_layout.addWidget(text_container)
        head_layout.addStretch(1)

        root.addWidget(head_container)
        root.addWidget(Separator(card))

        content_container = QWidget(card)
        if is_flow:
            content_layout = FlowLayout(content_container, needAni = False)
            content_layout.setContentsMargins(0, 0, 0, 0)
            content_layout.setSpacing(8)
        else:
            content_layout = QVBoxLayout(content_container)
            content_layout.setContentsMargins(0, 0, 0, 0)
            content_layout.setSpacing(0)

        root.addWidget(content_container)

        return card, content_layout, head_layout

    def _build_glossary_error_map(self) -> None:
        for item in self.items:
            if WarningType.GLOSSARY not in self.warning_map.get(id(item), []):
                continue
            for term in self.result_checker.get_failed_glossary_terms(item):
                self.glossary_error_map.setdefault(term, []).append(item)

    def _init_term_list(self) -> None:
        self.term_list.clear()
        self.term_checkboxes = {}

        terms = sorted(self.glossary_error_map.keys())
        if not terms:
            self.term_list.hide()
            self.term_empty_label.show()
            return

        self.term_list.show()
        self.term_empty_label.hide()

        for src, dst in terms:
            display_name = f"{src} -> {dst}"
            list_item = QListWidgetItem()
            list_item.setSizeHint(QSize(0, 36))
            list_item.setData(Qt.UserRole, (src, dst))
            self.term_list.addItem(list_item)

            cb = CheckBox(display_name)
            cb.setChecked(True)
            cb.setToolTip(display_name)
            cb.setAttribute(Qt.WA_TransparentForMouseEvents)
            self.term_list.setItemWidget(list_item, cb)
            self.term_checkboxes[(src, dst)] = cb

    def _on_term_item_clicked(self, item: QListWidgetItem) -> None:
        widget = self.term_list.itemWidget(item)
        if isinstance(widget, CheckBox):
            widget.setChecked(not widget.isChecked())

    def _select_all_terms(self) -> None:
        for cb in self.term_checkboxes.values():
            cb.setChecked(True)

    def _deselect_all_terms(self) -> None:
        for cb in self.term_checkboxes.values():
            cb.setChecked(False)

    def _on_file_item_clicked(self, item: QListWidgetItem) -> None:
        widget = self.file_list.itemWidget(item)
        if isinstance(widget, CheckBox):
            widget.setChecked(not widget.isChecked())

    def _select_all_files(self) -> None:
        for cb in self.file_checkboxes.values():
            cb.setChecked(True)

    def _deselect_all_files(self) -> None:
        for cb in self.file_checkboxes.values():
            cb.setChecked(False)

    def _filter_items(self, options: dict) -> list[CacheItem]:
        warning_types = options.get(self.KEY_WARNING_TYPES)
        statuses = options.get(self.KEY_STATUSES)
        file_paths = options.get(self.KEY_FILE_PATHS)
        glossary_terms = options.get(self.KEY_GLOSSARY_TERMS)

        filtered = []
        for item in self.items:
            if item.get_status() in (Base.TranslationStatus.EXCLUDED, Base.TranslationStatus.DUPLICATED):
                continue

            item_warnings = self.warning_map.get(id(item), [])
            if warning_types is not None:
                if item_warnings and not any(e in warning_types for e in item_warnings):
                    continue
                if not item_warnings and self.NO_WARNING_TAG not in warning_types:
                    continue

            if glossary_terms is not None:
                if WarningType.GLOSSARY not in item_warnings:
                    continue
                failed_terms = self.result_checker.get_failed_glossary_terms(item)
                if not any(term in glossary_terms for term in failed_terms):
                    continue

            if statuses is not None and item.get_status() not in statuses:
                continue

            if file_paths is not None and item.get_file_path() not in file_paths:
                continue

            filtered.append(item)

        return filtered

    def _export_filtered_items(self) -> None:
        options = self.get_filter_options()
        items = self._filter_items(options)
        if not items:
            InfoBar.warning(
                title=Localizer.get().alert,
                content=Localizer.get().alert_no_data,
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self.window(),
            )
            return

        output_dir = self.config.output_folder
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(output_dir, f"proofreading_filter_report_{timestamp}.json")

        report = []
        for item in items:
            warnings = self.warning_map.get(id(item), [])
            report.append(
                {
                    "file_path": item.get_file_path(),
                    "status": item.get_status().value,
                    "warnings": [w.value for w in warnings],
                    "src": item.get_src(),
                    "dst": item.get_dst(),
                }
            )

        try:
            with open(output_path, "w", encoding="utf-8") as writer:
                json.dump(report, writer, ensure_ascii=False, indent=2)

            InfoBar.success(
                title=Localizer.get().proofreading_page_filter_export_success,
                content=output_path,
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self.window(),
            )
        except Exception:
            InfoBar.error(
                title=Localizer.get().proofreading_page_filter_export_failed,
                content=output_path,
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self.window(),
            )

    def get_filter_options(self) -> dict:
        selected_warnings = {e for e, cb in self.warning_checkboxes.items() if cb.isChecked()}
        selected_statuses = {s for s, cb in self.status_checkboxes.items() if cb.isChecked()}
        selected_files = {path for path, cb in self.file_checkboxes.items() if cb.isChecked()}
        selected_terms = None

        if WarningType.GLOSSARY in selected_warnings and self.term_checkboxes:
            selected_terms = {term for term, cb in self.term_checkboxes.items() if cb.isChecked()}
            if len(selected_terms) == len(self.term_checkboxes):
                selected_terms = None

        return {
            self.KEY_WARNING_TYPES: selected_warnings if len(selected_warnings) < len(self.warning_checkboxes) else None,
            self.KEY_STATUSES: selected_statuses if len(selected_statuses) < len(self.status_checkboxes) else None,
            self.KEY_FILE_PATHS: selected_files if len(selected_files) < len(self.file_checkboxes) else None,
            self.KEY_GLOSSARY_TERMS: selected_terms,
        }

    def set_filter_options(self, options: dict) -> None:
        warning_types = options.get(self.KEY_WARNING_TYPES)
        status_types = options.get(self.KEY_STATUSES)
        file_paths = options.get(self.KEY_FILE_PATHS)
        glossary_terms = options.get(self.KEY_GLOSSARY_TERMS)

        for warning, cb in self.warning_checkboxes.items():
            cb.setChecked(warning_types is None or warning in warning_types)

        for status, cb in self.status_checkboxes.items():
            cb.setChecked(status_types is None or status in status_types)

        for path, cb in self.file_checkboxes.items():
            cb.setChecked(file_paths is None or path in file_paths)

        for term, cb in self.term_checkboxes.items():
            cb.setChecked(glossary_terms is None or term in glossary_terms)
