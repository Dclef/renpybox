from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from PyQt5.QtCore import QEvent, QObject, Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QListWidgetItem,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    CheckBox,
    FluentIcon as FIF,
    InfoBar,
    LineEdit,
    ListWidget,
    MessageBox,
    PillPushButton,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
    SearchLineEdit,
    SingleDirectionScrollArea,
    StrongBodyLabel,
    TitleLabel,
)

from base.Base import Base
from module.Config import Config
from module.Engine.Engine import Engine
from module.Engine.Translator.ProjectAssetsRepository import ProjectAssetsRepository
from module.Localizer.Localizer import Localizer
from module.PromptBuilder import PromptBuilder
from module.Workbench.AnalysisService import AnalysisResult, AnalysisServiceError, WorkbenchAnalysisService
from module.Workbench.CharacterScanner import CharacterScanner
from module.Workbench.WorkbenchData import (
    ANALYSIS_SCOPE_CURRENT,
    ANALYSIS_SCOPE_FULL,
    create_default_character_card,
    merge_character_card,
    merge_imported_character_cards,
    merge_imported_worldbook,
    normalize_analysis_scope,
    normalize_character_card,
    normalize_character_cards,
    normalize_text,
    normalize_text_list,
    normalize_worldbook,
    parse_workbench_exchange,
)
from widget.ThemeHelper import mark_toolbox_scroll_area, mark_toolbox_widget




class _WorkbenchSignals(QObject):
    """跨线程 UI 信号。"""

    analysis_success = pyqtSignal(object)
    analysis_failed = pyqtSignal(object)
    sync_success = pyqtSignal(object)
    sync_failed = pyqtSignal(str)


class RenpyWorkbenchPage(Base, QWidget):
    """角色 / 世界观工作台。"""

    def __init__(self, object_name: str, parent = None) -> None:
        Base.__init__(self)
        QWidget.__init__(self, parent)
        self.setObjectName(object_name)
        mark_toolbox_widget(self)

        self.window = parent
        self.analysis_service = WorkbenchAnalysisService()
        self.character_scanner = CharacterScanner()
        self.signals = _WorkbenchSignals()
        self.signals.analysis_success.connect(self._on_analysis_success)
        self.signals.analysis_failed.connect(self._on_analysis_failed)
        self.signals.sync_success.connect(self._on_sync_success)
        self.signals.sync_failed.connect(self._on_sync_failed)

        self._loading_ui = False
        self._analysis_running = False
        self._sync_running = False
        self._selected_character_id = ""
        self._analysis_source_summary = ""
        self._last_worldbook_raw = ""
        self._last_character_raw = ""
        self._config_snapshot: Config | None = None
        self._skip_next_show_refresh = True
        self._character_filter_mode = "all"

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(280)
        self._preview_timer.timeout.connect(self._refresh_prompt_preview)

        # 编辑保存去抖：字段变化合并后统一落盘，避免每次按键全量重建列表/预览。
        self._edit_save_timer = QTimer(self)
        self._edit_save_timer.setSingleShot(True)
        self._edit_save_timer.setInterval(300)
        self._edit_save_timer.timeout.connect(self._flush_pending_edits)
        self._pending_worldbook_fields: set[str] = set()
        self._pending_character_fields: set[str] = set()
        self._draft_ids: set[str] = set()
        self._visible_cards_by_id: dict[str, dict[str, Any]] = {}
        self._formal_cards_by_id: dict[str, dict[str, Any]] = {}
        self._draft_cards_by_id: dict[str, dict[str, Any]] = {}

        self._init_ui()
        self.subscribe(Base.Event.TRANSLATION_START, self._on_engine_state_changed)
        self.subscribe(Base.Event.TRANSLATION_UPDATE, self._on_engine_state_changed)
        self.subscribe(Base.Event.TRANSLATION_DONE, self._on_engine_state_changed)
        self.subscribe(Base.Event.TRANSLATION_STOP, self._on_engine_state_changed)
        self.refresh_from_config()

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget(self)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(24, 24, 24, 12)
        header_layout.setSpacing(10)
        header_layout.addWidget(TitleLabel(Localizer.get().workbench_character_worldbuilding_workbench))
        sub = CaptionLabel(Localizer.get().workbench_manage_worldbuilding_character_profiles_prompt_context_current)
        sub.setWordWrap(True)
        header_layout.addWidget(sub)
        root.addWidget(header)

        self.tab_group = QButtonGroup(self)
        self.tab_group.setExclusive(True)
        tab_row = QWidget(self)
        tab_layout = QHBoxLayout(tab_row)
        tab_layout.setContentsMargins(24, 0, 24, 12)
        tab_layout.setSpacing(8)

        self.tab_buttons: dict[str, PillPushButton] = {}
        self.panel_order = [
            ("overview", Localizer.get().workbench_overview),
            ("worldbook", Localizer.get().workbench_worldbuilding_2),
            ("characters", Localizer.get().workbench_character_cards),
            ("preview", Localizer.get().workbench_prompt_preview),
        ]
        for idx, (key, text) in enumerate(self.panel_order):
            button = PillPushButton(text, self)
            button.setCheckable(True)
            button.clicked.connect(lambda checked = False, value = key: self.switch_panel(value))
            self.tab_group.addButton(button)
            self.tab_buttons[key] = button
            tab_layout.addWidget(button)
            if idx == 0:
                button.setChecked(True)
        tab_layout.addStretch(1)
        root.addWidget(tab_row)

        self.stack = QStackedWidget(self)
        root.addWidget(self.stack, 1)

        self.stack.addWidget(self._wrap_scroll(self._build_overview_panel()))
        self.stack.addWidget(self._wrap_scroll(self._build_worldbook_panel()))
        self.stack.addWidget(self._wrap_scroll(self._build_character_panel()))
        self.stack.addWidget(self._wrap_scroll(self._build_preview_panel()))
        self.switch_panel("overview")

    def _wrap_scroll(self, content: QWidget) -> QWidget:
        """为面板包装滚动区域。"""
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll_area = SingleDirectionScrollArea(orient = Qt.Orientation.Vertical)
        scroll_area.setWidgetResizable(True)
        scroll_area.enableTransparentBackground()
        mark_toolbox_scroll_area(scroll_area)
        scroll_area.setWidget(content)
        layout.addWidget(scroll_area)
        return container

    def _create_card(self, title: str, description: str = "") -> tuple[CardWidget, QVBoxLayout]:
        """创建通用卡片。"""
        card = CardWidget(self)
        mark_toolbox_widget(card)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(StrongBodyLabel(title))
        if description:
            desc = CaptionLabel(description)
            desc.setWordWrap(True)
            layout.addWidget(desc)
        return card, layout

    def _create_preview_edit(self, placeholder: str = "") -> PlainTextEdit:
        """创建只读预览框。"""
        edit = PlainTextEdit(self)
        edit.setReadOnly(True)
        edit.setPlaceholderText(placeholder)
        edit.setMinimumHeight(120)
        return edit

    def switch_panel(self, key: str) -> None:
        """切换面板。"""
        keys = [name for name, _ in self.panel_order]
        if key not in keys:
            key = "overview"
        index = keys.index(key)
        self.stack.setCurrentIndex(index)
        button = self.tab_buttons.get(key)
        if button is not None:
            button.setChecked(True)

    def _build_overview_panel(self) -> QWidget:
        panel = QWidget(self)
        mark_toolbox_widget(panel, "toolboxScroll")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 12, 24, 24)
        layout.setSpacing(16)

        summary_card, summary_layout = self._create_card(
            Localizer.get().workbench_current_project_summary,
            Localizer.get().workbench_single_view_current_api_paths_workbench_state,
        )
        summary_grid = QGridLayout()
        summary_grid.setHorizontalSpacing(18)
        summary_grid.setVerticalSpacing(10)
        self.summary_labels: dict[str, BodyLabel] = {}
        summary_items = [
            ("platform", Localizer.get().workbench_current_api),
            ("model", Localizer.get().workbench_current_model),
            ("source_target", Localizer.get().workbench_language_pair),
            ("input_folder", Localizer.get().workbench_input_folder),
            ("output_folder", Localizer.get().workbench_output_folder),
            ("project_root", Localizer.get().workbench_project_folder),
            ("tl_folder", Localizer.get().workbench_tl_folder),
            ("worldbook", Localizer.get().workbench_worldbuilding_2),
            ("characters", Localizer.get().workbench_character_cards),
            ("drafts", Localizer.get().workbench_draft_status),
        ]
        for index, (key, text) in enumerate(summary_items):
            title = CaptionLabel(text)
            value = BodyLabel("—")
            value.setWordWrap(True)
            row = index // 2
            col = (index % 2) * 2
            summary_grid.addWidget(title, row, col)
            summary_grid.addWidget(value, row, col + 1)
            self.summary_labels[key] = value
        summary_layout.addLayout(summary_grid)
        layout.addWidget(summary_card)

        action_card, action_layout = self._create_card(
            Localizer.get().workbench_analysis_shortcuts,
            Localizer.get().workbench_generate_ai_drafts_demand_current_scope_then,
        )
        action_row = QHBoxLayout()
        action_row.setSpacing(10)
        self.btn_generate_current = PushButton(Localizer.get().workbench_generate_current_scope_drafts)
        self.btn_generate_current.clicked.connect(lambda: self._start_analysis("all", ANALYSIS_SCOPE_CURRENT))
        self.btn_generate_full = PushButton(Localizer.get().workbench_reanalyze_full_project)
        self.btn_generate_full.clicked.connect(lambda: self._start_analysis("all", ANALYSIS_SCOPE_FULL))
        self.btn_sync_characters = PushButton(Localizer.get().workbench_sync_character_names)
        self.btn_sync_characters.clicked.connect(self._start_sync_characters)
        self.btn_apply_all = PrimaryPushButton(Localizer.get().workbench_apply_all_and_enable)
        self.btn_apply_all.clicked.connect(self._apply_all_drafts)
        action_row.addWidget(self.btn_generate_current)
        action_row.addWidget(self.btn_generate_full)
        action_row.addWidget(self.btn_sync_characters)
        action_row.addWidget(self.btn_apply_all)
        action_row.addStretch(1)
        action_layout.addLayout(action_row)

        shortcut_row = QHBoxLayout()
        shortcut_row.setSpacing(10)
        self.btn_open_glossary = PushButton(Localizer.get().workbench_open_local_glossary)
        self.btn_open_glossary.clicked.connect(self._open_glossary_page)
        self.btn_open_preserve = PushButton(Localizer.get().workbench_open_do_not_translate_list)
        self.btn_open_preserve.clicked.connect(self._open_text_preserve_page)
        self.btn_open_prompt = PushButton(Localizer.get().workbench_open_custom_prompts)
        self.btn_open_prompt.clicked.connect(self._open_custom_prompt_page)
        shortcut_row.addWidget(self.btn_open_glossary)
        shortcut_row.addWidget(self.btn_open_preserve)
        shortcut_row.addWidget(self.btn_open_prompt)
        shortcut_row.addStretch(1)
        action_layout.addLayout(shortcut_row)

        exchange_row = QHBoxLayout()
        exchange_row.setSpacing(10)
        self.btn_import_drafts = PushButton(
            Localizer.get().workbench_import_as_drafts,
            icon = FIF.DOWNLOAD,
        )
        self.btn_import_drafts.clicked.connect(lambda: self._import_project_assets(False))
        self.btn_import_apply = PushButton(
            Localizer.get().workbench_import_apply_enable,
            icon = FIF.DOWNLOAD,
        )
        self.btn_import_apply.clicked.connect(lambda: self._import_project_assets(True))
        self.btn_export_assets = PushButton(
            Localizer.get().workbench_export_project_assets,
            icon = FIF.SAVE,
        )
        self.btn_export_assets.clicked.connect(self._export_project_assets)
        self.btn_clear_characters = PushButton(
            Localizer.get().workbench_clear_current_characters,
            icon = FIF.DELETE,
        )
        self.btn_clear_characters.clicked.connect(self._clear_current_project_characters)
        exchange_row.addWidget(self.btn_import_drafts)
        exchange_row.addWidget(self.btn_import_apply)
        exchange_row.addWidget(self.btn_export_assets)
        exchange_row.addWidget(self.btn_clear_characters)
        exchange_row.addStretch(1)
        action_layout.addLayout(exchange_row)

        self.overview_status_label = BodyLabel(Localizer.get().workbench_ready)
        self.overview_status_label.setWordWrap(True)
        action_layout.addWidget(self.overview_status_label)
        self.overview_hint_label = CaptionLabel("")
        self.overview_hint_label.setWordWrap(True)
        action_layout.addWidget(self.overview_hint_label)
        layout.addWidget(action_card)
        layout.addStretch(1)
        return panel

    def _build_worldbook_panel(self) -> QWidget:
        panel = QWidget(self)
        mark_toolbox_widget(panel, "toolboxScroll")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 12, 24, 24)
        layout.setSpacing(16)

        header_card, header_layout = self._create_card(
            Localizer.get().workbench_worldbuilding,
            Localizer.get().workbench_edit_approved_worldbuilding_left_review_ai_drafts,
        )
        self.worldbook_enable = CheckBox(Localizer.get().workbench_inject_worldbuilding_context)
        self.worldbook_enable.stateChanged.connect(self._on_worldbook_toggle_changed)
        header_layout.addWidget(self.worldbook_enable)
        layout.addWidget(header_card)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setObjectName("worldbookSplitter")
        # 对齐原型 3:2 分栏，避免拖拽时把任一侧收缩为不可用宽度。
        splitter.setChildrenCollapsible(False)

        official_card, official_layout = self._create_card(
            Localizer.get().workbench_approved_worldbuilding,
            Localizer.get().workbench_content_inserted_directly_generated_prompts,
        )
        # 允许在窗口收缩时继续压缩，避免最小窗口出现横向溢出。
        official_card.setMinimumWidth(240)
        official_form = QFormLayout()
        official_form.setLabelAlignment(Qt.AlignmentFlag.AlignTop)
        official_form.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        official_form.setHorizontalSpacing(14)
        official_form.setVerticalSpacing(12)
        self.worldbook_widgets: dict[str, QWidget] = {}
        worldbook_specs = [
            ("project_name", Localizer.get().workbench_project_name, False),
            ("genre", Localizer.get().workbench_genre, False),
            ("setting_summary", Localizer.get().workbench_setting_summary, True),
            ("era_background", Localizer.get().workbench_era_environment, True),
            ("tone_style", Localizer.get().workbench_tone_style, True),
            ("narrative_rules", Localizer.get().workbench_narrative_rules, True),
            ("format_rules", Localizer.get().workbench_formatting_rules, True),
            ("spoiler_notes", Localizer.get().workbench_spoiler_notes, True),
            ("reference_notes", Localizer.get().workbench_reference_notes, True),
        ]
        for field, label, multiline in worldbook_specs:
            if multiline:
                widget = PlainTextEdit(self)
                widget.setMinimumHeight(88)
                widget.textChanged.connect(lambda name = field: self._on_worldbook_field_changed(name))
            else:
                widget = LineEdit(self)
                widget.textChanged.connect(lambda text, name = field: self._on_worldbook_field_changed(name))
            self.worldbook_widgets[field] = widget
            official_form.addRow(BodyLabel(label), widget)
        official_layout.addLayout(official_form)
        splitter.addWidget(official_card)

        draft_card, draft_layout = self._create_card(
            Localizer.get().workbench_ai_draft_preview,
            Localizer.get().workbench_generated_content_remains_draft_until_you_apply,
        )
        draft_card.setMinimumWidth(180)
        draft_action_row = QHBoxLayout()
        draft_action_row.setSpacing(10)
        self.btn_world_current = PrimaryPushButton(Localizer.get().workbench_generate_current_scope)
        self.btn_world_current.clicked.connect(lambda: self._start_analysis("worldbook", ANALYSIS_SCOPE_CURRENT))
        self.btn_world_full = PushButton(Localizer.get().workbench_expand_reanalyze)
        self.btn_world_full.clicked.connect(lambda: self._start_analysis("worldbook", ANALYSIS_SCOPE_FULL))
        self.btn_apply_worldbook = PushButton(Localizer.get().workbench_apply_worldbuilding_draft)
        self.btn_apply_worldbook.clicked.connect(self._apply_worldbook_draft)
        draft_action_row.addWidget(self.btn_world_current)
        draft_action_row.addWidget(self.btn_world_full)
        draft_action_row.addWidget(self.btn_apply_worldbook)
        draft_action_row.addStretch(1)
        draft_layout.addLayout(draft_action_row)

        self.worldbook_draft_preview = self._create_preview_edit(Localizer.get().workbench_generated_worldbuilding_drafts_appear_here)
        self.worldbook_raw_preview = self._create_preview_edit(Localizer.get().workbench_if_parsing_fails_raw_model_response_appears)
        draft_layout.addWidget(BodyLabel(Localizer.get().workbench_structured_draft))
        draft_layout.addWidget(self.worldbook_draft_preview)
        draft_layout.addWidget(BodyLabel(Localizer.get().workbench_raw_response_error_preview))
        draft_layout.addWidget(self.worldbook_raw_preview)
        splitter.addWidget(draft_card)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        # 页面默认内容宽度约为 976px，按 3:2 给出稳定的首屏比例。
        splitter.setSizes([580, 390])
        layout.addWidget(splitter, 1)
        return panel

    def _build_character_panel(self) -> QWidget:
        panel = QWidget(self)
        mark_toolbox_widget(panel, "toolboxScroll")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 12, 24, 24)
        layout.setSpacing(16)

        header_card, header_layout = self._create_card(
            Localizer.get().workbench_character_card_workbench,
            Localizer.get().workbench_browse_characters_left_edit_approved_cards_center,
        )
        self.character_cards_enable = CheckBox(Localizer.get().workbench_inject_character_card_context)
        self.character_cards_enable.stateChanged.connect(self._on_character_cards_toggle_changed)
        header_layout.addWidget(self.character_cards_enable)

        action_row = QHBoxLayout()
        action_row.setSpacing(10)
        self.btn_character_batch = PushButton(Localizer.get().workbench_generate_all_character_cards)
        self.btn_character_batch.clicked.connect(lambda: self._start_analysis("characters", ANALYSIS_SCOPE_CURRENT))
        self.btn_character_current = PushButton(Localizer.get().workbench_regenerate_current_character)
        self.btn_character_current.clicked.connect(self._regenerate_current_character)
        self.btn_character_apply = PrimaryPushButton(Localizer.get().workbench_apply_current_and_enable)
        self.btn_character_apply.clicked.connect(self._apply_current_character_draft)
        self.btn_character_add = PushButton(Localizer.get().workbench_add_blank_character_card)
        self.btn_character_add.clicked.connect(self._add_character_card)
        self.btn_character_delete = PushButton(Localizer.get().workbench_delete_current_character)
        self.btn_character_delete.clicked.connect(self._delete_current_character)
        action_row.addWidget(self.btn_character_batch)
        action_row.addWidget(self.btn_character_current)
        action_row.addWidget(self.btn_character_apply)
        action_row.addWidget(self.btn_character_add)
        action_row.addWidget(self.btn_character_delete)
        action_row.addStretch(1)
        header_layout.addLayout(action_row)
        layout.addWidget(header_card)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setObjectName("characterSplitter")
        # 角色花名册和草稿预览需要保持可读宽度，禁止拖拽折叠。
        splitter.setChildrenCollapsible(False)

        roster_card, roster_layout = self._create_card(
            Localizer.get().workbench_character_list,
            Localizer.get().workbench_synced_character_candidates_added_here_review,
        )
        roster_card.setMinimumWidth(160)
        self.character_search_edit = SearchLineEdit(self)
        self.character_search_edit.setPlaceholderText(Localizer.get().workbench_search_characters)
        self.character_search_edit.textChanged.connect(self._apply_character_filters)
        roster_layout.addWidget(self.character_search_edit)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        self.character_filter_group = QButtonGroup(self)
        self.character_filter_group.setExclusive(True)
        self.character_filter_buttons: dict[str, PillPushButton] = {}
        for key, text in (
            ("all", Localizer.get().workbench_filter_all),
            ("pending", Localizer.get().workbench_filter_pending),
            ("applied", Localizer.get().workbench_filter_applied),
        ):
            button = PillPushButton(text, self)
            button.setCheckable(True)
            button.clicked.connect(
                lambda checked = False, value = key: self._set_character_filter(value)
            )
            self.character_filter_group.addButton(button)
            self.character_filter_buttons[key] = button
            filter_row.addWidget(button)
        self.character_filter_buttons["all"].setChecked(True)
        filter_row.addStretch(1)
        roster_layout.addLayout(filter_row)

        self.character_count_label = CaptionLabel("")
        roster_layout.addWidget(self.character_count_label)
        self.character_list = ListWidget(self)
        self.character_list.currentItemChanged.connect(self._on_character_item_changed)
        roster_layout.addWidget(self.character_list, 1)
        splitter.addWidget(roster_card)

        editor_card, editor_layout = self._create_card(
            Localizer.get().workbench_approved_character_card,
            Localizer.get().workbench_manual_edits_saved_immediately_current_project_assets,
        )
        editor_card.setMinimumWidth(220)
        editor_form = QFormLayout()
        editor_form.setLabelAlignment(Qt.AlignmentFlag.AlignTop)
        editor_form.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        editor_form.setHorizontalSpacing(14)
        editor_form.setVerticalSpacing(12)
        self.character_widgets: dict[str, QWidget] = {}
        char_specs = [
            ("name", Localizer.get().workbench_character_name, False),
            ("name_translation", Localizer.get().workbench_suggested_translation, False),
            ("aliases", Localizer.get().workbench_aliases, True),
            ("match_keywords", Localizer.get().workbench_match_keywords, True),
            ("identity", Localizer.get().workbench_identity, True),
            ("personality", Localizer.get().workbench_personality, True),
            ("speech_style", Localizer.get().workbench_speech_style, True),
            ("relationship_notes", Localizer.get().workbench_relationship_notes, True),
            ("prompt_notes", Localizer.get().workbench_translation_notes, True),
            ("sample_lines", Localizer.get().workbench_sample_lines, True),
        ]
        for field, label, multiline in char_specs:
            if multiline:
                widget = PlainTextEdit(self)
                widget.setMinimumHeight(78)
                widget.textChanged.connect(lambda name = field: self._on_character_field_changed(name))
            else:
                widget = LineEdit(self)
                widget.textChanged.connect(lambda text, name = field: self._on_character_field_changed(name))
            self.character_widgets[field] = widget
            editor_form.addRow(BodyLabel(label), widget)

        toggle_box = QWidget(self)
        toggle_layout = QHBoxLayout(toggle_box)
        toggle_layout.setContentsMargins(0, 0, 0, 0)
        toggle_layout.setSpacing(12)
        self.character_enabled_checkbox = CheckBox(Localizer.get().workbench_enable_character_card)
        self.character_enabled_checkbox.stateChanged.connect(lambda value: self._on_character_flag_changed("enabled", value))
        self.character_primary_checkbox = CheckBox(Localizer.get().workbench_mark_main_character)
        self.character_primary_checkbox.stateChanged.connect(lambda value: self._on_character_flag_changed("is_primary", value))
        toggle_layout.addWidget(self.character_enabled_checkbox)
        toggle_layout.addWidget(self.character_primary_checkbox)
        toggle_layout.addStretch(1)

        editor_layout.addWidget(toggle_box)
        editor_layout.addLayout(editor_form)
        splitter.addWidget(editor_card)

        draft_card, draft_layout = self._create_card(
            Localizer.get().workbench_character_draft_preview,
            Localizer.get().workbench_ai_generated_character_drafts_appear_here,
        )
        draft_card.setMinimumWidth(180)
        self.character_draft_preview = self._create_preview_edit(Localizer.get().workbench_select_character_view_draft_details)
        self.character_raw_preview = self._create_preview_edit(Localizer.get().workbench_if_parsing_fails_raw_model_response_appears_2)
        draft_layout.addWidget(BodyLabel(Localizer.get().workbench_structured_draft))
        draft_layout.addWidget(self.character_draft_preview)
        draft_layout.addWidget(BodyLabel(Localizer.get().workbench_raw_response_error_preview))
        draft_layout.addWidget(self.character_raw_preview)
        splitter.addWidget(draft_card)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 4)
        splitter.setStretchFactor(2, 3)
        # 对齐原型的 220px / flexible / 270px 三栏首屏布局。
        splitter.setSizes([220, 480, 270])
        layout.addWidget(splitter, 1)
        return panel

    def _build_preview_panel(self) -> QWidget:
        panel = QWidget(self)
        mark_toolbox_widget(panel, "toolboxScroll")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 12, 24, 24)
        layout.setSpacing(16)

        input_card, input_layout = self._create_card(
            Localizer.get().workbench_prompt_match_preview,
            Localizer.get().workbench_enter_sample_source_text_preview_matching_character,
        )
        self.preview_input_edit = PlainTextEdit(self)
        self.preview_input_edit.setPlaceholderText(Localizer.get().workbench_enter_one_more_lines_sample_source_text)
        self.preview_input_edit.setMinimumHeight(160)
        self.preview_input_edit.textChanged.connect(self._schedule_prompt_preview)
        input_layout.addWidget(self.preview_input_edit)
        self.preview_matched_label = BodyLabel(Localizer.get().workbench_no_sample_source_text_entered)
        self.preview_matched_label.setWordWrap(True)
        input_layout.addWidget(self.preview_matched_label)
        layout.addWidget(input_card)

        preview_card, preview_layout = self._create_card(
            Localizer.get().workbench_injected_context,
            Localizer.get().workbench_preview_how_workbench_context_inserted_final_prompt,
        )
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(12)
        self.preview_world_context = self._create_preview_edit(Localizer.get().workbench_worldbuilding_context_appears_here)
        self.preview_character_context = self._create_preview_edit(Localizer.get().workbench_matched_character_context_appears_here)
        self.preview_final_context = self._create_preview_edit(Localizer.get().workbench_final_injected_context_appears_here)
        grid.addWidget(BodyLabel(Localizer.get().workbench_worldbuilding_context), 0, 0)
        grid.addWidget(self.preview_world_context, 1, 0)
        grid.addWidget(BodyLabel(Localizer.get().workbench_character_context), 0, 1)
        grid.addWidget(self.preview_character_context, 1, 1)
        preview_layout.addLayout(grid)
        preview_layout.addWidget(BodyLabel(Localizer.get().workbench_final_injected_context))
        preview_layout.addWidget(self.preview_final_context)
        layout.addWidget(preview_card)
        layout.addStretch(1)
        return panel

    def _normalize_workbench_config(self, config: Config) -> bool:
        """规范化配置中的工作台数据。"""
        changed = False
        worldbook = normalize_worldbook(getattr(config, "renpy_workbench_worldbook_data", {}))
        if worldbook != getattr(config, "renpy_workbench_worldbook_data", {}):
            config.renpy_workbench_worldbook_data = worldbook
            changed = True

        worldbook_draft = normalize_worldbook(getattr(config, "renpy_workbench_generated_worldbook_draft", {}))
        if worldbook_draft != getattr(config, "renpy_workbench_generated_worldbook_draft", {}):
            config.renpy_workbench_generated_worldbook_draft = worldbook_draft
            changed = True

        cards = normalize_character_cards(getattr(config, "renpy_workbench_character_cards", []))
        if cards != getattr(config, "renpy_workbench_character_cards", []):
            config.renpy_workbench_character_cards = cards
            changed = True

        drafts = normalize_character_cards(getattr(config, "renpy_workbench_generated_character_drafts", []))
        if drafts != getattr(config, "renpy_workbench_generated_character_drafts", []):
            config.renpy_workbench_generated_character_drafts = drafts
            changed = True

        scope = normalize_analysis_scope(getattr(config, "renpy_workbench_last_analysis_scope", ANALYSIS_SCOPE_CURRENT))
        if scope != getattr(config, "renpy_workbench_last_analysis_scope", ANALYSIS_SCOPE_CURRENT):
            config.renpy_workbench_last_analysis_scope = scope
            changed = True

        return changed

    def _load_config(self) -> Config:
        """读取全局设置，并叠加当前输出项目的资产视图。"""
        config = Config().load()
        ProjectAssetsRepository.from_config(config).load_into_config(config)
        self._normalize_workbench_config(config)
        return config

    def _save_config(self, config: Config) -> None:
        """保存工作台拥有的正式资产和分析草稿。"""
        self._normalize_workbench_config(config)
        ProjectAssetsRepository.from_config(config).save_workbench_view(config)
        self._config_snapshot = config

    def _get_config_snapshot(self) -> Config:
        """返回页面当前项目快照，缺失时才读取磁盘。"""
        if self._config_snapshot is None:
            self._config_snapshot = self._load_config()
        return self._config_snapshot

    def refresh_from_config(self, config: Config | None = None) -> None:
        """从配置刷新整个页面。"""
        config = config or self._load_config()
        self._config_snapshot = config
        self._loading_ui = True
        try:
            self.worldbook_enable.setChecked(bool(getattr(config, "renpy_workbench_worldbook_enable", False)))
            self.character_cards_enable.setChecked(bool(getattr(config, "renpy_workbench_character_cards_enable", False)))

            worldbook = normalize_worldbook(getattr(config, "renpy_workbench_worldbook_data", {}))
            for field, widget in self.worldbook_widgets.items():
                value = worldbook.get(field, "")
                if isinstance(widget, PlainTextEdit):
                    widget.setPlainText(value)
                else:
                    widget.setText(value)

            cards = normalize_character_cards(getattr(config, "renpy_workbench_character_cards", []))
            drafts = normalize_character_cards(getattr(config, "renpy_workbench_generated_character_drafts", []))
            select_id = self._selected_character_id or (
                drafts[0]["id"] if drafts else (cards[0]["id"] if cards else "")
            )
            self._refresh_character_list(cards, drafts, select_id)
            self._refresh_character_editor(config)
            self._refresh_worldbook_draft_view(config)
            self._refresh_character_draft_view(config)
            self._refresh_summary(config)
            self._refresh_prompt_preview(config)
        finally:
            self._loading_ui = False
        self._refresh_action_state(config)

    def _refresh_summary(self, config: Config) -> None:
        """刷新摘要。"""
        platform = config.get_platform(config.activate_platform)
        not_configured = Localizer.get().workbench_not_configured
        not_set = Localizer.get().workbench_not_set
        platform_name = normalize_text(platform.get("name", "")) if platform else not_configured
        model_name = normalize_text(platform.get("model", "")) if platform else not_configured
        worldbook = normalize_worldbook(getattr(config, "renpy_workbench_worldbook_data", {}))
        cards = normalize_character_cards(getattr(config, "renpy_workbench_character_cards", []))
        drafts = normalize_character_cards(getattr(config, "renpy_workbench_generated_character_drafts", []))
        enabled_cards = sum(1 for card in cards if card.get("enabled", True))
        world_ready = (
            Localizer.get().workbench_enabled
            if getattr(config, "renpy_workbench_worldbook_enable", False) and any(worldbook.values())
            else Localizer.get().workbench_not_enabled
        )
        draft_scope = normalize_analysis_scope(getattr(config, "renpy_workbench_last_analysis_scope", ANALYSIS_SCOPE_CURRENT))
        has_worldbook_draft = any(normalize_worldbook(
            getattr(config, "renpy_workbench_generated_worldbook_draft", {})
        ).values())
        draft_text = Localizer.get().workbench_draft_summary.format(
            worldbook_status=(
                Localizer.get().available if has_worldbook_draft else Localizer.get().none
            ),
            draft_count=len(drafts),
            scope=(
                Localizer.get().current_scope
                if draft_scope == ANALYSIS_SCOPE_CURRENT
                else Localizer.get().full_project
            ),
        )
        resolved_project_root = self.analysis_service.resolve_project_root(config)

        summary = {
            "platform": platform_name or not_configured,
            "model": model_name or not_configured,
            "source_target": f"{config.source_language} -> {config.target_language}",
            "input_folder": normalize_text(config.input_folder) or not_set,
            "output_folder": normalize_text(config.output_folder) or not_set,
            "project_root": str(resolved_project_root) if resolved_project_root else (normalize_text(config.renpy_game_folder) or not_set),
            "tl_folder": normalize_text(config.renpy_tl_folder) or not_set,
            "worldbook": world_ready,
            "characters": Localizer.get().workbench_total_enabled.format(cards_count=len(cards), enabled_cards=enabled_cards),
            "drafts": draft_text,
        }
        for key, value in summary.items():
            label = self.summary_labels.get(key)
            if label is not None:
                label.setText(value)

        self.overview_hint_label.setText(
            self._analysis_source_summary or Localizer.get().workbench_no_ai_analysis_has_been_run_yet
        )

    def _refresh_worldbook_draft_view(self, config: Config) -> None:
        """刷新世界观草稿预览。"""
        draft = normalize_worldbook(getattr(config, "renpy_workbench_generated_worldbook_draft", {}))
        if any(draft.values()):
            lines = [
                Localizer.get().workbench_project_name_2.format(draft_get_project_name=draft.get('project_name', '')),
                Localizer.get().workbench_genre_2.format(draft_get_genre=draft.get('genre', '')),
                Localizer.get().workbench_setting_summary_2.format(draft_get_setting_summary=draft.get('setting_summary', '')),
                Localizer.get().workbench_era_environment_2.format(draft_get_era_background=draft.get('era_background', '')),
                Localizer.get().workbench_tone_style_2.format(draft_get_tone_style=draft.get('tone_style', '')),
                Localizer.get().workbench_narrative_rules_2.format(draft_get_narrative_rules=draft.get('narrative_rules', '')),
                Localizer.get().workbench_formatting_rules_2.format(draft_get_format_rules=draft.get('format_rules', '')),
                Localizer.get().workbench_spoiler_notes_2.format(draft_get_spoiler_notes=draft.get('spoiler_notes', '')),
                Localizer.get().workbench_reference_notes_preview.format(
                    reference_notes=draft.get("reference_notes", "")
                ),
            ]
            self.worldbook_draft_preview.setPlainText("\n\n".join(lines))
        else:
            self.worldbook_draft_preview.setPlainText("")
        self.worldbook_raw_preview.setPlainText(self._last_worldbook_raw)

    def _character_item_text(self, card: dict[str, Any], draft_ids: set[str]) -> str:
        """构建角色列表项显示文本。"""
        unnamed = Localizer.get().workbench_unnamed_character
        name = card.get("name", unnamed)
        suffix = []
        if card.get("is_primary", False):
            suffix.append(Localizer.get().workbench_main)
        if card.get("enabled", True) is False:
            suffix.append(Localizer.get().workbench_off)
        if card.get("id") in draft_ids:
            suffix.append(Localizer.get().workbench_draft)
        if suffix:
            return f"{name} [{' / '.join(suffix)}]"
        return name

    def _update_current_character_list_item(self) -> None:
        """增量刷新选中角色所在列表项的文本。"""
        card = self._visible_cards_by_id.get(self._selected_character_id)
        if card is None:
            return
        text = self._character_item_text(card, self._draft_ids)
        for row in range(self.character_list.count()):
            item = self.character_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == self._selected_character_id:
                if item.text() != text:
                    item.setText(text)
                break

    def _set_character_filter(self, mode: str) -> None:
        """切换角色列表筛选。"""
        if mode not in self.character_filter_buttons:
            mode = "all"
        self._character_filter_mode = mode
        button = self.character_filter_buttons.get(mode)
        if button is not None:
            button.setChecked(True)
        self._apply_character_filters()

    def _prepare_character_view(
        self,
        mode: str,
        selected_id: str = "",
        *,
        clear_search: bool = False,
    ) -> None:
        """在列表重建前预设筛选和选中项，不触发旧列表信号。"""
        if mode not in self.character_filter_buttons:
            mode = "all"
        self._character_filter_mode = mode
        self.character_filter_buttons[mode].setChecked(True)
        self._selected_character_id = normalize_text(selected_id)
        if clear_search:
            self.character_search_edit.blockSignals(True)
            try:
                self.character_search_edit.clear()
            finally:
                self.character_search_edit.blockSignals(False)

    def _apply_character_filters(self) -> None:
        """按搜索词和审核状态过滤角色，不重建列表。"""
        query = normalize_text(self.character_search_edit.text()).casefold()
        visible_items: list[QListWidgetItem] = []
        for row in range(self.character_list.count()):
            item = self.character_list.item(row)
            card_id = normalize_text(item.data(Qt.ItemDataRole.UserRole))
            card = self._visible_cards_by_id.get(card_id, {})
            search_text = "\n".join(
                [
                    normalize_text(card.get("name", "")),
                    normalize_text(card.get("name_translation", "")),
                    *normalize_text_list(card.get("aliases", [])),
                    *normalize_text_list(card.get("match_keywords", [])),
                ]
            ).casefold()
            matches_mode = (
                self._character_filter_mode == "all"
                or (
                    self._character_filter_mode == "pending"
                    and card_id in self._draft_ids
                )
                or (
                    self._character_filter_mode == "applied"
                    and card_id not in self._draft_ids
                )
            )
            visible = matches_mode and (query == "" or query in search_text)
            item.setHidden(not visible)
            if visible:
                visible_items.append(item)

        self.character_count_label.setText(
            Localizer.get().workbench_character_count.format(
                visible=len(visible_items),
                total=self.character_list.count(),
            )
        )
        current = self.character_list.currentItem()
        if current is not None and current.isHidden() is False:
            return
        if visible_items:
            self.character_list.setCurrentItem(visible_items[0])
        else:
            self.character_list.setCurrentItem(None)

    def _refresh_character_list(
        self,
        cards: list[dict[str, Any]],
        drafts: list[dict[str, Any]],
        select_id: str,
    ) -> None:
        """刷新角色列表。"""
        self._draft_ids = {draft.get("id") for draft in drafts}
        self._formal_cards_by_id = {card.get("id"): card for card in cards}
        self._draft_cards_by_id = {draft.get("id"): draft for draft in drafts}
        formal_by_id = {card.get("id"): card for card in cards}
        visible_cards = [
            formal_by_id.get(draft.get("id"), draft)
            for draft in drafts
        ]
        visible_cards.extend(
            card for card in cards if card.get("id") not in self._draft_ids
        )
        self._visible_cards_by_id = {card.get("id"): card for card in visible_cards}

        list_widget = self.character_list
        # 重建期间屏蔽选中信号，编辑器与按钮状态由 refresh_from_config 统一刷新。
        list_widget.blockSignals(True)
        try:
            list_widget.clear()
            for card in visible_cards:
                item = QListWidgetItem(self._character_item_text(card, self._draft_ids))
                item.setData(Qt.ItemDataRole.UserRole, card.get("id", ""))
                list_widget.addItem(item)

            self._apply_character_filters()
            visible_ids = {
                normalize_text(list_widget.item(row).data(Qt.ItemDataRole.UserRole))
                for row in range(list_widget.count())
                if list_widget.item(row).isHidden() is False
            }
            self._selected_character_id = select_id if select_id in visible_ids else ""
            if visible_ids == set():
                list_widget.setCurrentItem(None)
                return

            target_row = 0
            for row in range(list_widget.count()):
                item = list_widget.item(row)
                if item.data(Qt.ItemDataRole.UserRole) == self._selected_character_id:
                    target_row = row
                    break
                if self._selected_character_id == "" and item.isHidden() is False:
                    target_row = row
                    break
            list_widget.setCurrentRow(target_row)
            self._selected_character_id = normalize_text(
                list_widget.item(target_row).data(Qt.ItemDataRole.UserRole)
            )
        finally:
            list_widget.blockSignals(False)

    def _clear_character_editor(self) -> None:
        """清空角色编辑区。"""
        was_loading = self._loading_ui
        self._loading_ui = True
        try:
            for widget in self.character_widgets.values():
                if isinstance(widget, PlainTextEdit):
                    widget.setPlainText("")
                else:
                    widget.setText("")
            self.character_enabled_checkbox.setChecked(False)
            self.character_primary_checkbox.setChecked(False)
            self.character_draft_preview.setPlainText("")
            self.character_raw_preview.setPlainText(self._last_character_raw)
        finally:
            self._loading_ui = was_loading

    def _refresh_character_editor(self, config: Config) -> None:
        """根据当前选中角色刷新编辑器。"""
        current = self._formal_cards_by_id.get(self._selected_character_id)
        if current is None:
            self._clear_character_editor()
            self._refresh_character_draft_view(config)
            return

        was_loading = self._loading_ui
        self._loading_ui = True
        try:
            self.character_widgets["name"].setText(current.get("name", ""))
            self.character_widgets["name_translation"].setText(current.get("name_translation", ""))
            self.character_widgets["aliases"].setPlainText("\n".join(current.get("aliases", [])))
            self.character_widgets["match_keywords"].setPlainText("\n".join(current.get("match_keywords", [])))
            self.character_widgets["identity"].setPlainText(current.get("identity", ""))
            self.character_widgets["personality"].setPlainText(current.get("personality", ""))
            self.character_widgets["speech_style"].setPlainText(current.get("speech_style", ""))
            self.character_widgets["relationship_notes"].setPlainText(current.get("relationship_notes", ""))
            self.character_widgets["prompt_notes"].setPlainText(current.get("prompt_notes", ""))
            self.character_widgets["sample_lines"].setPlainText("\n".join(current.get("sample_lines", [])))
            self.character_enabled_checkbox.setChecked(bool(current.get("enabled", True)))
            self.character_primary_checkbox.setChecked(bool(current.get("is_primary", False)))
        finally:
            self._loading_ui = was_loading
        self._refresh_character_draft_view(config)

    def _refresh_character_draft_view(self, config: Config) -> None:
        """刷新角色草稿预览。"""
        draft = self._draft_cards_by_id.get(self._selected_character_id)
        if draft is None:
            self.character_draft_preview.setPlainText("")
        else:
            empty_value = Localizer.get().workbench_none
            lines = [
                Localizer.get().workbench_character_name_2.format(draft_get_name=draft.get('name', '')),
                Localizer.get().workbench_suggested_translation_2.format(draft_get_name_translation=draft.get('name_translation', '')),
                Localizer.get().workbench_aliases_preview.format(
                    aliases=Localizer.get().list_separator.join(draft.get("aliases", [])) or empty_value
                ),
                Localizer.get().workbench_match_keywords_preview.format(
                    keywords=Localizer.get().list_separator.join(draft.get("match_keywords", [])) or empty_value
                ),
                Localizer.get().workbench_identity_2.format(identity_or_empty_value=draft.get('identity', '') or empty_value),
                Localizer.get().workbench_personality_2.format(personality_or_empty_value=draft.get('personality', '') or empty_value),
                Localizer.get().workbench_speech_style_2.format(speech_style_or_empty_value=draft.get('speech_style', '') or empty_value),
                Localizer.get().workbench_relationship_notes_2.format(relationship_notes_or_empty_value=draft.get('relationship_notes', '') or empty_value),
                Localizer.get().workbench_translation_notes_2.format(prompt_notes_or_empty_value=draft.get('prompt_notes', '') or empty_value),
            ]
            samples = draft.get("sample_lines", [])
            if samples:
                lines.append(Localizer.get().workbench_sample_lines_2)
                lines.extend(f"- {line}" for line in samples)
            self.character_draft_preview.setPlainText("\n".join(lines))
        self.character_raw_preview.setPlainText(self._last_character_raw)

    def _refresh_action_state(self, config: Config | None = None) -> None:
        """刷新按钮状态。"""
        config = config or self._get_config_snapshot()
        platform = config.get_platform(config.activate_platform)
        api_format = platform.get("api_format") if isinstance(platform, dict) else None
        engine_busy = Engine.get().get_status() != Engine.Status.IDLE
        supported = api_format in WorkbenchAnalysisService.SUPPORTED_FORMATS
        analysis_ready = supported and not engine_busy and not self._analysis_running and not self._sync_running
        has_worldbook_draft = any(normalize_worldbook(getattr(config, "renpy_workbench_generated_worldbook_draft", {})).values())
        has_character_draft = self._selected_character_id in self._draft_ids
        has_any_draft = has_worldbook_draft or bool(self._draft_ids)

        for button in (
            self.btn_generate_current,
            self.btn_generate_full,
            self.btn_world_current,
            self.btn_world_full,
            self.btn_character_batch,
        ):
            button.setEnabled(analysis_ready)
        self.btn_character_current.setEnabled(analysis_ready and self._selected_character_id != "")

        self.btn_sync_characters.setEnabled(not engine_busy and not self._analysis_running and not self._sync_running)
        self.btn_apply_all.setEnabled(not self._analysis_running and not self._sync_running and has_any_draft)
        self.btn_apply_worldbook.setEnabled(not self._analysis_running and has_worldbook_draft)
        self.btn_character_apply.setEnabled(
            not self._analysis_running
            and not self._sync_running
            and has_character_draft
        )
        self.btn_character_add.setEnabled(not self._analysis_running and not self._sync_running)
        self.btn_character_delete.setEnabled(not self._analysis_running and not self._sync_running and self._selected_character_id != "")
        for button in (
            self.btn_import_drafts,
            self.btn_import_apply,
            self.btn_export_assets,
            self.btn_clear_characters,
        ):
            button.setEnabled(not self._analysis_running and not self._sync_running)

        if engine_busy:
            self.overview_status_label.setText(Localizer.get().workbench_translation_task_running_ai_generation_character_sync)
        elif supported is False:
            self.overview_status_label.setText(Localizer.get().workbench_current_api_does_not_support_ai_analysis)
        elif self._analysis_running:
            self.overview_status_label.setText(Localizer.get().workbench_ai_analysis_running_please_wait)
        elif self._sync_running:
            self.overview_status_label.setText(Localizer.get().workbench_character_sync_running_please_wait)

    def _on_worldbook_toggle_changed(self, state: int) -> None:
        """世界观开关变化。"""
        if self._loading_ui:
            return
        config = self._get_config_snapshot()
        config.renpy_workbench_worldbook_enable = bool(state)
        self._save_config(config)
        self._refresh_prompt_preview(config)
        self._refresh_summary(config)

    def _on_character_cards_toggle_changed(self, state: int) -> None:
        """角色卡开关变化。"""
        if self._loading_ui:
            return
        config = self._get_config_snapshot()
        config.renpy_workbench_character_cards_enable = bool(state)
        self._save_config(config)
        self._refresh_prompt_preview(config)
        self._refresh_summary(config)

    def _on_worldbook_field_changed(self, field: str) -> None:
        """世界观字段变化，去抖批量保存。"""
        if self._loading_ui:
            return
        self._pending_worldbook_fields.add(field)
        self._edit_save_timer.start()

    def _on_character_item_changed(self, current: QListWidgetItem, previous: QListWidgetItem) -> None:
        """角色列表选中变化。"""
        del previous
        if self._loading_ui:
            return
        if self._pending_character_fields:
            self._flush_pending_edits()
        if current is None:
            self._selected_character_id = ""
            self._clear_character_editor()
            self._refresh_action_state(self._get_config_snapshot())
            return
        self._selected_character_id = normalize_text(current.data(Qt.ItemDataRole.UserRole))
        config = self._get_config_snapshot()
        self._refresh_character_editor(config)
        self._refresh_action_state(config)

    def _flush_pending_edits(self) -> None:
        """把待保存的世界观/角色字段批量落盘，并刷新摘要与提示词预览。"""
        if self._loading_ui:
            return
        self._edit_save_timer.stop()
        worldbook_fields = self._pending_worldbook_fields
        character_fields = self._pending_character_fields
        self._pending_worldbook_fields = set()
        self._pending_character_fields = set()
        if not worldbook_fields and not character_fields:
            return

        config = self._get_config_snapshot()
        if worldbook_fields:
            worldbook = normalize_worldbook(getattr(config, "renpy_workbench_worldbook_data", {}))
            for field in worldbook_fields:
                widget = self.worldbook_widgets.get(field)
                if widget is None:
                    continue
                if isinstance(widget, PlainTextEdit):
                    worldbook[field] = widget.toPlainText().strip()
                else:
                    worldbook[field] = widget.text().strip()
            config.renpy_workbench_worldbook_data = worldbook

        if character_fields and self._selected_character_id != "":
            cards = normalize_character_cards(getattr(config, "renpy_workbench_character_cards", []))
            current_card: dict[str, Any] | None = None
            updated_cards: list[dict[str, Any]] = []
            for card in cards:
                if card.get("id") == self._selected_character_id:
                    for field in character_fields:
                        widget = self.character_widgets.get(field)
                        if widget is None:
                            continue
                        if field in ("aliases", "match_keywords", "sample_lines"):
                            card[field] = normalize_text_list(widget.toPlainText().splitlines())
                        elif isinstance(widget, PlainTextEdit):
                            card[field] = widget.toPlainText().strip()
                        else:
                            card[field] = widget.text().strip()
                    current_card = normalize_character_card(card)
                    updated_cards.append(current_card)
                else:
                    updated_cards.append(card)
            if current_card is not None:
                config.renpy_workbench_character_cards = updated_cards
                self._visible_cards_by_id[self._selected_character_id] = current_card
                self._formal_cards_by_id[self._selected_character_id] = current_card

        self._save_config(config)
        self._refresh_summary(config)
        self._update_current_character_list_item()
        self._refresh_prompt_preview(config)

    def _update_current_character_card(self, updater) -> None:
        """立即更新当前角色卡（用于开关类低频操作）。"""
        if self._loading_ui or self._selected_character_id == "":
            return
        config = self._get_config_snapshot()
        cards = normalize_character_cards(getattr(config, "renpy_workbench_character_cards", []))
        current_card: dict[str, Any] | None = None
        updated_cards: list[dict[str, Any]] = []
        for card in cards:
            if card.get("id") == self._selected_character_id:
                updater(card)
                current_card = normalize_character_card(card)
                updated_cards.append(current_card)
            else:
                updated_cards.append(card)
        if current_card is None:
            return
        config.renpy_workbench_character_cards = updated_cards
        self._save_config(config)
        self._visible_cards_by_id[self._selected_character_id] = current_card
        self._formal_cards_by_id[self._selected_character_id] = current_card
        self._update_current_character_list_item()
        self._refresh_summary(config)
        self._refresh_prompt_preview(config)

    def _on_character_field_changed(self, field: str) -> None:
        """角色字段变化，去抖批量保存；名称变化时立即更新列表项文本。"""
        if self._loading_ui or self._selected_character_id == "":
            return
        self._pending_character_fields.add(field)
        self._edit_save_timer.start()
        if field == "name":
            overlay = dict(self._visible_cards_by_id.get(self._selected_character_id, {}))
            widget = self.character_widgets.get("name")
            if widget is not None:
                overlay["name"] = widget.text().strip()
                self._visible_cards_by_id[self._selected_character_id] = overlay
                self._update_current_character_list_item()

    def _on_character_flag_changed(self, field: str, state: int) -> None:
        """角色布尔开关变化。"""
        def updater(card: dict[str, Any]) -> None:
            card[field] = bool(state)

        self._update_current_character_card(updater)

    def _add_character_card(self) -> None:
        """新增空白角色卡。"""
        config = self._get_config_snapshot()
        cards = normalize_character_cards(getattr(config, "renpy_workbench_character_cards", []))
        card = create_default_character_card(Localizer.get().workbench_character.format(len_cards=len(cards) + 1))
        cards.append(card)
        config.renpy_workbench_character_cards = cards
        self._save_config(config)
        self._prepare_character_view("applied", card["id"])
        self.refresh_from_config(config)

    def _delete_current_character(self) -> None:
        """删除当前角色卡。"""
        if self._selected_character_id == "":
            return
        config = self._get_config_snapshot()
        cards = [
            card
            for card in normalize_character_cards(getattr(config, "renpy_workbench_character_cards", []))
            if card.get("id") != self._selected_character_id
        ]
        drafts = [
            card
            for card in normalize_character_cards(getattr(config, "renpy_workbench_generated_character_drafts", []))
            if card.get("id") != self._selected_character_id
        ]
        config.renpy_workbench_character_cards = cards
        config.renpy_workbench_generated_character_drafts = drafts
        self._save_config(config)
        self._selected_character_id = cards[0]["id"] if cards else ""
        self.refresh_from_config(config)

    def _schedule_prompt_preview(self) -> None:
        """延迟刷新提示词预览。"""
        self._preview_timer.start()

    def _refresh_prompt_preview(self, config: Config | None = None) -> None:
        """刷新提示词预览。"""
        config = config or self._get_config_snapshot()
        prompt_builder = PromptBuilder(config)
        sample_text = self.preview_input_edit.toPlainText().strip()
        srcs = [line.strip() for line in sample_text.splitlines() if line.strip()]
        if srcs == [] and sample_text != "":
            srcs = [sample_text]

        world_context = prompt_builder.build_worldbook_context()
        character_context = prompt_builder.build_character_context(srcs, [])
        matched_cards = prompt_builder.match_character_cards(srcs, [])
        final_text = "\n\n".join(part for part in (world_context, character_context) if part)

        self.preview_world_context.setPlainText(world_context)
        self.preview_character_context.setPlainText(character_context)
        self.preview_final_context.setPlainText(final_text)
        if sample_text == "":
            self.preview_matched_label.setText(Localizer.get().workbench_no_sample_source_text_entered)
        else:
            names = [card.get("name", "") for card in matched_cards]
            self.preview_matched_label.setText(
                Localizer.get().workbench_matched_characters.format(
                    names=Localizer.get().list_separator.join(names) if names else Localizer.get().none
                )
            )

    def _start_analysis(self, mode: str, scope: str) -> None:
        """启动 AI 分析线程。"""
        if self._analysis_running:
            return
        if not Engine.get().try_set_status(Engine.Status.IDLE, Engine.Status.TESTING):
            self._refresh_action_state()
            return
        self._analysis_running = True
        try:
            self._refresh_action_state()
        except Exception:
            self._analysis_running = False
            Engine.get().release_status(Engine.Status.TESTING)
            raise
        self.overview_status_label.setText(Localizer.get().workbench_running_ai_analysis)
        scope = normalize_analysis_scope(scope)
        current_id = self._selected_character_id

        def task() -> None:
            success_payload: dict[str, Any] | None = None
            failure_payload: dict[str, Any] | None = None
            try:
                config = self._load_config()
                if mode == "all":
                    result = self.analysis_service.analyze_all(
                        config,
                        scope,
                        engine_reserved = True,
                    )
                elif mode == "worldbook":
                    result = self.analysis_service.generate_worldbook_only(
                        config,
                        scope,
                        engine_reserved = True,
                    )
                elif mode == "characters":
                    result = self.analysis_service.generate_character_only(
                        config,
                        scope,
                        engine_reserved = True,
                    )
                elif mode == "character_single":
                    result = self.analysis_service.generate_character_only(
                        config,
                        scope,
                        current_id,
                        engine_reserved = True,
                    )
                else:
                    raise AnalysisServiceError(Localizer.get().workbench_unknown_analysis_mode)
                success_payload = {
                    "mode": mode,
                    "scope": scope,
                    "result": result,
                    "card_id": current_id,
                }
            except AnalysisServiceError as exc:
                failure_payload = {
                    "mode": mode,
                    "scope": scope,
                    "message": str(exc),
                    "raw_response": exc.raw_response,
                }
            except Exception as exc:
                failure_payload = {
                    "mode": mode,
                    "scope": scope,
                    "message": str(exc),
                    "raw_response": "",
                }
            finally:
                Engine.get().release_status(Engine.Status.TESTING)

            if success_payload is not None:
                self.signals.analysis_success.emit(success_payload)
            else:
                self.signals.analysis_failed.emit(failure_payload or {
                    "mode": mode,
                    "scope": scope,
                    "message": Localizer.get().workbench_ai_analysis_failed_2,
                    "raw_response": "",
                })

        thread = threading.Thread(target = task, daemon = True)
        try:
            thread.start()
        except Exception:
            self._analysis_running = False
            Engine.get().release_status(Engine.Status.TESTING)
            self._refresh_action_state()
            raise

    def _on_analysis_success(self, payload: dict[str, Any]) -> None:
        """处理分析成功。"""
        self._analysis_running = False
        result: AnalysisResult = payload["result"]
        mode = payload["mode"]
        card_id = payload.get("card_id", "")
        config = self._load_config()
        config.renpy_workbench_last_analysis_scope = result.scope
        self._analysis_source_summary = Localizer.get().workbench_latest_analysis_source.format(source_summary=result.source_summary)

        if result.worldbook_draft:
            config.renpy_workbench_generated_worldbook_draft = normalize_worldbook(result.worldbook_draft)
            self._last_worldbook_raw = result.worldbook_raw

        if result.character_drafts:
            incoming = normalize_character_cards(result.character_drafts)
            if mode in ("all", "characters"):
                config.renpy_workbench_generated_character_drafts = incoming
            else:
                drafts = normalize_character_cards(getattr(config, "renpy_workbench_generated_character_drafts", []))
                merged: list[dict[str, Any]] = []
                incoming_map = {card.get("id"): card for card in incoming}
                consumed: set[str] = set()
                for draft in drafts:
                    draft_id = draft.get("id")
                    if draft_id in incoming_map:
                        merged.append(incoming_map[draft_id])
                        consumed.add(draft_id)
                    else:
                        merged.append(draft)
                for draft in incoming:
                    if draft.get("id") not in consumed:
                        merged.append(draft)
                config.renpy_workbench_generated_character_drafts = merged
            self._last_character_raw = "\n\n-----\n\n".join(result.character_raw)

        self._save_config(config)
        if result.character_drafts:
            self._prepare_character_view(
                "pending",
                card_id or incoming[0]["id"],
                clear_search = True,
            )
        elif card_id:
            self._selected_character_id = card_id
        self.refresh_from_config(config)
        self.overview_status_label.setText(Localizer.get().workbench_ai_drafts_ready_review_them_right_before)
        InfoBar.success(
            Localizer.get().complete,
            Localizer.get().workbench_ai_draft_generation_complete,
            parent = self,
        )

    def _on_analysis_failed(self, payload: dict[str, Any]) -> None:
        """处理分析失败。"""
        self._analysis_running = False
        mode = payload.get("mode", "")
        raw_response = normalize_text(payload.get("raw_response", ""))
        message = normalize_text(payload.get("message", Localizer.get().workbench_ai_analysis_failed))
        if mode == "worldbook" or "世界观" in message:
            self._last_worldbook_raw = raw_response
        else:
            self._last_character_raw = raw_response
        self.refresh_from_config(self._get_config_snapshot())
        self.overview_status_label.setText(message)
        InfoBar.error(Localizer.get().error, message, parent = self, duration = 5000)

    def _merge_candidates_into_cards(
        self,
        config: Config,
        candidate_cards: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], int]:
        """将扫描结果并入待确认的角色草稿。"""
        cards = normalize_character_cards(
            getattr(config, "renpy_workbench_generated_character_drafts", [])
        )
        card_map = {card.get("id"): card for card in cards}
        added = 0

        for seed in candidate_cards:
            normalized_seed = normalize_character_card(seed)
            target_id = normalized_seed.get("id")
            existing = card_map.get(target_id)
            if existing is None:
                card_map[target_id] = normalized_seed
                added += 1
                continue

            if normalize_text(existing.get("name_translation", "")) == "":
                existing["name_translation"] = normalized_seed.get("name_translation", "")
            existing["aliases"] = normalize_text_list(existing.get("aliases", []) + normalized_seed.get("aliases", []))
            existing["match_keywords"] = normalize_text_list(
                existing.get("match_keywords", []) + normalized_seed.get("match_keywords", [])
            )
            if normalize_text(existing.get("prompt_notes", "")) == "" and normalize_text(normalized_seed.get("prompt_notes", "")) != "":
                existing["prompt_notes"] = normalized_seed.get("prompt_notes", "")
            if existing.get("sample_lines", []) == [] and normalized_seed.get("sample_lines", []):
                existing["sample_lines"] = normalized_seed.get("sample_lines", [])
            card_map[target_id] = normalize_character_card(existing)

        merged_cards = list(card_map.values())
        merged_cards.sort(key = lambda card: normalize_text(card.get("name", "")).casefold())
        return merged_cards, added

    def _start_sync_characters(self) -> None:
        """启动角色同步。"""
        if self._sync_running:
            return
        self._sync_running = True
        self._refresh_action_state()
        self.overview_status_label.setText(Localizer.get().workbench_syncing_character_candidates)

        def task() -> None:
            try:
                config = self._load_config()
                items, source_summary = self.analysis_service.load_scope_items(config, ANALYSIS_SCOPE_CURRENT)
                candidates = self.character_scanner.build_candidates(config, items, self.analysis_service.resolve_project_root(config))
                candidate_cards = [candidate.as_card_seed() for candidate in candidates]
                merged_cards, added = self._merge_candidates_into_cards(config, candidate_cards)
                self.signals.sync_success.emit(
                    {
                        "drafts": merged_cards,
                        "added": added,
                        "source_summary": source_summary,
                    }
                )
            except Exception as exc:
                self.signals.sync_failed.emit(str(exc))

        threading.Thread(target = task, daemon = True).start()

    def _on_sync_success(self, payload: dict[str, Any]) -> None:
        """同步成功回调。"""
        self._sync_running = False
        config = self._load_config()
        merged_drafts, _ = self._merge_candidates_into_cards(
            config,
            payload["drafts"],
        )
        config.renpy_workbench_generated_character_drafts = merged_drafts
        self._save_config(config)
        self._analysis_source_summary = Localizer.get().workbench_character_sync_source.format(payload_get_source_summary=payload.get('source_summary', ''))
        if payload["drafts"]:
            self._prepare_character_view(
                "pending",
                payload["drafts"][0]["id"],
                clear_search = True,
            )
        self.refresh_from_config(config)
        added = payload.get("added", 0)
        sync_result = Localizer.get().workbench_character_sync_complete_new_drafts_ready_review.format(added=added)
        self.overview_status_label.setText(sync_result)
        InfoBar.success(Localizer.get().complete, sync_result, parent = self)

    def _on_sync_failed(self, message: str) -> None:
        """同步失败回调。"""
        self._sync_running = False
        self._refresh_action_state()
        self.overview_status_label.setText(message)
        InfoBar.error(Localizer.get().error, message, parent = self, duration = 5000)

    def _apply_worldbook_draft(self) -> None:
        """应用世界观草稿。"""
        config = self._get_config_snapshot()
        draft = normalize_worldbook(getattr(config, "renpy_workbench_generated_worldbook_draft", {}))
        if any(draft.values()) is False:
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.get().workbench_there_no_worldbuilding_draft_apply,
                parent = self,
            )
            return
        current = normalize_worldbook(getattr(config, "renpy_workbench_worldbook_data", {}))
        config.renpy_workbench_worldbook_data = {
            field: value or current.get(field, "")
            for field, value in draft.items()
        }
        config.renpy_workbench_worldbook_enable = True
        config.renpy_workbench_generated_worldbook_draft = {}
        self._save_config(config)
        self.refresh_from_config(config)
        InfoBar.success(
            Localizer.get().complete,
            Localizer.get().workbench_worldbuilding_draft_has_been_applied,
            parent = self,
        )

    def _apply_current_character_draft(self) -> None:
        """应用当前角色草稿。"""
        if self._selected_character_id == "":
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.get().workbench_select_character_first,
                parent = self,
            )
            return
        config = self._get_config_snapshot()
        drafts = normalize_character_cards(getattr(config, "renpy_workbench_generated_character_drafts", []))
        draft = next((card for card in drafts if card.get("id") == self._selected_character_id), None)
        if draft is None:
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.get().workbench_selected_character_has_no_draft_apply,
                parent = self,
            )
            return

        cards = normalize_character_cards(getattr(config, "renpy_workbench_character_cards", []))
        merged: list[dict[str, Any]] = []
        found = False
        for card in cards:
            if card.get("id") == self._selected_character_id:
                merged.append(merge_character_card(card, draft))
                found = True
            else:
                merged.append(card)
        if found is False:
            merged.append(normalize_character_card(draft))
        config.renpy_workbench_character_cards = merged
        config.renpy_workbench_character_cards_enable = True
        config.renpy_workbench_generated_character_drafts = [
            card
            for card in drafts
            if card.get("id") != self._selected_character_id
        ]
        remaining_drafts = list(config.renpy_workbench_generated_character_drafts)
        self._save_config(config)
        if remaining_drafts:
            self._prepare_character_view("pending", remaining_drafts[0]["id"])
        else:
            self._prepare_character_view("applied", self._selected_character_id)
        self.refresh_from_config(config)
        InfoBar.success(
            Localizer.get().complete,
            Localizer.get().workbench_character_draft_has_been_applied,
            parent = self,
        )

    def _apply_all_drafts(self) -> None:
        """应用全部草稿。"""
        config = self._get_config_snapshot()
        if self._apply_drafts_to_config(config) is False:
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.get().workbench_there_no_drafts_apply,
                parent = self,
            )
            return
        self._save_config(config)
        self._prepare_character_view("applied", self._selected_character_id)
        self.refresh_from_config(config)
        InfoBar.success(
            Localizer.get().complete,
            Localizer.get().workbench_all_drafts_have_been_applied,
            parent = self,
        )

    def _apply_drafts_to_config(self, config: Config) -> bool:
        """把配置中的全部草稿晋升为正式资产并启用。"""
        world_draft = normalize_worldbook(getattr(config, "renpy_workbench_generated_worldbook_draft", {}))
        char_drafts = normalize_character_cards(getattr(config, "renpy_workbench_generated_character_drafts", []))
        if any(world_draft.values()) is False and char_drafts == []:
            return False

        if any(world_draft.values()):
            current = normalize_worldbook(getattr(config, "renpy_workbench_worldbook_data", {}))
            config.renpy_workbench_worldbook_data = {
                field: value or current.get(field, "")
                for field, value in world_draft.items()
            }
            config.renpy_workbench_worldbook_enable = True

        cards = normalize_character_cards(getattr(config, "renpy_workbench_character_cards", []))
        card_map = {card.get("id"): card for card in cards}
        for draft in char_drafts:
            draft_id = draft.get("id")
            if draft_id in card_map:
                card_map[draft_id] = merge_character_card(card_map[draft_id], draft)
            else:
                card_map[draft_id] = normalize_character_card(draft)
        config.renpy_workbench_character_cards = list(card_map.values())
        config.renpy_workbench_character_cards_enable = True
        config.renpy_workbench_generated_worldbook_draft = {}
        config.renpy_workbench_generated_character_drafts = []
        return True

    def _merge_imported_cards_as_drafts(
        self,
        config: Config,
        incoming_cards: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """导入角色卡先进入草稿；部分字段基于已有正式卡补全。"""
        drafts = normalize_character_cards(
            getattr(config, "renpy_workbench_generated_character_drafts", [])
        )
        formal_cards = normalize_character_cards(
            getattr(config, "renpy_workbench_character_cards", [])
        )
        draft_ids = {card["id"] for card in drafts}
        draft_names = {card["name"].casefold() for card in drafts}
        formal_by_id = {card["id"]: card for card in formal_cards}
        formal_by_name = {card["name"].casefold(): card for card in formal_cards}

        for raw in incoming_cards:
            incoming = normalize_character_card(raw)
            if incoming["id"] in draft_ids or incoming["name"].casefold() in draft_names:
                continue
            base = formal_by_id.get(incoming["id"]) or formal_by_name.get(
                incoming["name"].casefold()
            )
            if base is not None:
                drafts.append(base)
                draft_ids.add(base["id"])
                draft_names.add(base["name"].casefold())

        return merge_imported_character_cards(drafts, incoming_cards)

    def _import_project_assets(self, apply_now: bool) -> None:
        """从 JSON 批量导入世界观和角色卡。"""
        self._flush_pending_edits()
        path, _ = QFileDialog.getOpenFileName(
            self,
            Localizer.get().workbench_select_import_file,
            "",
            Localizer.get().workbench_json_file_filter,
        )
        if path == "":
            return

        try:
            payload = json.loads(Path(path).read_text(encoding = "utf-8-sig"))
            worldbook, incoming_cards = parse_workbench_exchange(payload)
            config = self._get_config_snapshot()
            if worldbook:
                current_draft = getattr(
                    config,
                    "renpy_workbench_generated_worldbook_draft",
                    {},
                )
                config.renpy_workbench_generated_worldbook_draft = (
                    merge_imported_worldbook(current_draft, worldbook)
                )
            if incoming_cards:
                config.renpy_workbench_generated_character_drafts = (
                    self._merge_imported_cards_as_drafts(config, incoming_cards)
                )

            first_id = (
                normalize_character_card(incoming_cards[0])["id"]
                if incoming_cards
                else self._selected_character_id
            )
            if apply_now:
                self._apply_drafts_to_config(config)
                self._prepare_character_view("applied", first_id, clear_search = True)
            elif incoming_cards:
                self._prepare_character_view("pending", first_id, clear_search = True)

            self._save_config(config)
            self.refresh_from_config(config)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            InfoBar.error(
                Localizer.get().error,
                Localizer.get().workbench_import_failed.format(error=exc),
                parent = self,
                duration = 5000,
            )
            return

        message = (
            Localizer.get().workbench_import_applied
            if apply_now
            else Localizer.get().workbench_imported_as_drafts
        ).format(count=len(incoming_cards))
        InfoBar.success(Localizer.get().complete, message, parent = self)

    def _export_project_assets(self) -> None:
        """将当前项目工作台资料导出为 UTF-8 JSON。"""
        self._flush_pending_edits()
        path, _ = QFileDialog.getSaveFileName(
            self,
            Localizer.get().workbench_select_export_file,
            "RenpyBox_Workbench.json",
            Localizer.get().workbench_json_file_filter,
        )
        if path == "":
            return
        if Path(path).suffix.casefold() != ".json":
            path = f"{path}.json"

        config = self._get_config_snapshot()
        payload = {
            "schema_version": 1,
            "worldbook": normalize_worldbook(
                getattr(config, "renpy_workbench_worldbook_data", {})
            ),
            "character_cards": normalize_character_cards(
                getattr(config, "renpy_workbench_character_cards", [])
            ),
            "worldbook_draft": normalize_worldbook(
                getattr(config, "renpy_workbench_generated_worldbook_draft", {})
            ),
            "character_drafts": normalize_character_cards(
                getattr(config, "renpy_workbench_generated_character_drafts", [])
            ),
        }
        try:
            Path(path).write_text(
                json.dumps(payload, ensure_ascii = False, indent = 2) + "\n",
                encoding = "utf-8",
            )
        except OSError as exc:
            InfoBar.error(
                Localizer.get().error,
                Localizer.get().workbench_export_failed.format(error=exc),
                parent = self,
                duration = 5000,
            )
            return

        InfoBar.success(
            Localizer.get().complete,
            Localizer.get().workbench_export_complete.format(path=path),
            parent = self,
        )

    def _clear_current_project_characters(self) -> None:
        """清空当前项目的正式角色卡和待审核草稿。"""
        self._flush_pending_edits()
        config = self._get_config_snapshot()
        cards = normalize_character_cards(
            getattr(config, "renpy_workbench_character_cards", [])
        )
        drafts = normalize_character_cards(
            getattr(config, "renpy_workbench_generated_character_drafts", [])
        )
        if cards == [] and drafts == []:
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.get().workbench_no_characters_to_clear,
                parent = self,
            )
            return

        dialog = MessageBox(
            Localizer.get().confirm,
            Localizer.get().workbench_clear_current_characters_confirm.format(
                cards=len(cards),
                drafts=len(drafts),
            ),
            self,
        )
        dialog.yesButton.setText(Localizer.get().confirm)
        dialog.cancelButton.setText(Localizer.get().cancel)
        if not dialog.exec():
            return

        config.renpy_workbench_character_cards = []
        config.renpy_workbench_generated_character_drafts = []
        config.renpy_workbench_character_cards_enable = False
        self._save_config(config)
        self._prepare_character_view("all", "", clear_search = True)
        self.refresh_from_config(config)
        InfoBar.success(
            Localizer.get().complete,
            Localizer.get().workbench_current_characters_cleared,
            parent = self,
        )

    def _regenerate_current_character(self) -> None:
        """重生当前角色。"""
        scope = ANALYSIS_SCOPE_CURRENT
        config = self._get_config_snapshot()
        scope = normalize_analysis_scope(getattr(config, "renpy_workbench_last_analysis_scope", ANALYSIS_SCOPE_CURRENT))
        self._start_analysis("character_single", scope)

    def _navigate_page(self, attr_name: str, factory) -> None:
        """导航到目标页面。"""
        if not self.window:
            return
        if hasattr(self.window, attr_name) is False:
            setattr(self.window, attr_name, factory())
        page = getattr(self.window, attr_name)
        self.window.navigate_to_page(page)

    def _navigate_toolbox_page(self, key: str) -> None:
        """通过工具箱缓存打开共享工具页。"""
        if not self.window:
            return
        toolbox = getattr(self.window, "renpy_toolbox_page", None)
        if toolbox is None:
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.get().workbench_ren_py_toolbox_page_unavailable,
                parent=self,
            )
            return
        self.window.navigate_to_page(toolbox.get_tool_page(key))

    def _open_glossary_page(self) -> None:
        self._navigate_toolbox_page("local_glossary")

    def _open_text_preserve_page(self) -> None:
        self._navigate_toolbox_page("text_preserve")

    def _open_custom_prompt_page(self) -> None:
        from frontend.Setting.CustomPromptPage import CustomPromptPage

        self._navigate_page("custom_prompt_page", lambda: CustomPromptPage("custom_prompt_page", self.window))

    def _on_engine_state_changed(self, event: str, data: dict) -> None:
        """翻译状态变化时刷新按钮。"""
        del event
        del data
        self._refresh_action_state()

    def showEvent(self, event: QEvent) -> None:
        """页面显示时刷新状态。"""
        super().showEvent(event)
        if self._skip_next_show_refresh:
            self._skip_next_show_refresh = False
            self._refresh_action_state(self._get_config_snapshot())
            return
        self._flush_pending_edits()
        self.refresh_from_config()
