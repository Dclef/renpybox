from __future__ import annotations

import threading
from typing import Any

from PyQt5.QtCore import QEvent, QObject, Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QButtonGroup,
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
    InfoBar,
    LineEdit,
    ListWidget,
    PillPushButton,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
    SingleDirectionScrollArea,
    StrongBodyLabel,
    TitleLabel,
)

from base.Base import Base
from module.Config import Config
from module.Engine.Engine import Engine
from module.PromptBuilder import PromptBuilder
from module.Workbench.AnalysisService import AnalysisResult, AnalysisServiceError, WorkbenchAnalysisService
from module.Workbench.CharacterScanner import CharacterScanner
from module.Workbench.WorkbenchData import (
    ANALYSIS_SCOPE_CURRENT,
    ANALYSIS_SCOPE_FULL,
    create_default_character_card,
    merge_character_card,
    normalize_analysis_scope,
    normalize_character_card,
    normalize_character_cards,
    normalize_text,
    normalize_text_list,
    normalize_worldbook,
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

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(280)
        self._preview_timer.timeout.connect(self._refresh_prompt_preview)

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
        header_layout.addWidget(TitleLabel("角色 / 世界观工作台"))
        sub = CaptionLabel("在这里统一维护世界观、人设和提示词上下文，并可手动触发 AI 生成草稿。")
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
            ("overview", "概览"),
            ("worldbook", "世界观"),
            ("characters", "角色卡"),
            ("preview", "提示词预览"),
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
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
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
            "当前项目摘要",
            "这里聚合当前接口、路径、工作台状态和草稿状态，作为主入口总览。",
        )
        summary_grid = QGridLayout()
        summary_grid.setHorizontalSpacing(18)
        summary_grid.setVerticalSpacing(10)
        self.summary_labels: dict[str, BodyLabel] = {}
        summary_items = [
            ("platform", "当前接口"),
            ("model", "当前模型"),
            ("source_target", "语言方向"),
            ("input_folder", "输入目录"),
            ("output_folder", "输出目录"),
            ("project_root", "项目目录"),
            ("tl_folder", "TL 目录"),
            ("worldbook", "世界观"),
            ("characters", "角色卡"),
            ("drafts", "草稿状态"),
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
            "分析与跳转",
            "默认手动触发 AI 生成；支持先当前范围，再扩展到全项目重分析。",
        )
        action_row = QHBoxLayout()
        action_row.setSpacing(10)
        self.btn_generate_current = PrimaryPushButton("生成当前范围草稿")
        self.btn_generate_current.clicked.connect(lambda: self._start_analysis("all", ANALYSIS_SCOPE_CURRENT))
        self.btn_generate_full = PushButton("扩展到全项目重分析")
        self.btn_generate_full.clicked.connect(lambda: self._start_analysis("all", ANALYSIS_SCOPE_FULL))
        self.btn_sync_characters = PushButton("同步角色名")
        self.btn_sync_characters.clicked.connect(self._start_sync_characters)
        self.btn_apply_all = PushButton("应用全部草稿")
        self.btn_apply_all.clicked.connect(self._apply_all_drafts)
        action_row.addWidget(self.btn_generate_current)
        action_row.addWidget(self.btn_generate_full)
        action_row.addWidget(self.btn_sync_characters)
        action_row.addWidget(self.btn_apply_all)
        action_row.addStretch(1)
        action_layout.addLayout(action_row)

        shortcut_row = QHBoxLayout()
        shortcut_row.setSpacing(10)
        self.btn_open_glossary = PushButton("打开本地词库")
        self.btn_open_glossary.clicked.connect(self._open_glossary_page)
        self.btn_open_preserve = PushButton("打开禁翻表")
        self.btn_open_preserve.clicked.connect(self._open_text_preserve_page)
        self.btn_open_prompt = PushButton("打开自定义提示词")
        self.btn_open_prompt.clicked.connect(self._open_custom_prompt_page)
        shortcut_row.addWidget(self.btn_open_glossary)
        shortcut_row.addWidget(self.btn_open_preserve)
        shortcut_row.addWidget(self.btn_open_prompt)
        shortcut_row.addStretch(1)
        action_layout.addLayout(shortcut_row)

        self.overview_status_label = BodyLabel("等待操作")
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
            "世界观设定",
            "左侧维护正式世界观，右侧查看 AI 草稿与原始响应预览。",
        )
        self.worldbook_enable = CheckBox("启用世界观上下文注入")
        self.worldbook_enable.stateChanged.connect(self._on_worldbook_toggle_changed)
        header_layout.addWidget(self.worldbook_enable)
        layout.addWidget(header_card)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        official_card, official_layout = self._create_card("正式世界观", "这些内容会直接进入提示词构建。")
        official_form = QFormLayout()
        official_form.setLabelAlignment(Qt.AlignmentFlag.AlignTop)
        official_form.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        official_form.setHorizontalSpacing(14)
        official_form.setVerticalSpacing(12)
        self.worldbook_widgets: dict[str, QWidget] = {}
        worldbook_specs = [
            ("project_name", "项目名", False),
            ("genre", "类型", False),
            ("setting_summary", "背景摘要", True),
            ("era_background", "时代与环境", True),
            ("tone_style", "整体语气", True),
            ("narrative_rules", "叙事规则", True),
            ("format_rules", "格式规则", True),
            ("spoiler_notes", "剧透备注", True),
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

        draft_card, draft_layout = self._create_card("AI 草稿预览", "生成成功后只进入草稿区，确认后再应用。")
        draft_action_row = QHBoxLayout()
        draft_action_row.setSpacing(10)
        self.btn_world_current = PrimaryPushButton("生成当前范围")
        self.btn_world_current.clicked.connect(lambda: self._start_analysis("worldbook", ANALYSIS_SCOPE_CURRENT))
        self.btn_world_full = PushButton("扩展重分析")
        self.btn_world_full.clicked.connect(lambda: self._start_analysis("worldbook", ANALYSIS_SCOPE_FULL))
        self.btn_apply_worldbook = PushButton("应用世界观草稿")
        self.btn_apply_worldbook.clicked.connect(self._apply_worldbook_draft)
        draft_action_row.addWidget(self.btn_world_current)
        draft_action_row.addWidget(self.btn_world_full)
        draft_action_row.addWidget(self.btn_apply_worldbook)
        draft_action_row.addStretch(1)
        draft_layout.addLayout(draft_action_row)

        self.worldbook_draft_preview = self._create_preview_edit("生成后在这里查看世界观草稿。")
        self.worldbook_raw_preview = self._create_preview_edit("解析失败时，这里会显示模型原始响应。")
        draft_layout.addWidget(BodyLabel("结构化草稿"))
        draft_layout.addWidget(self.worldbook_draft_preview)
        draft_layout.addWidget(BodyLabel("原始响应 / 错误预览"))
        draft_layout.addWidget(self.worldbook_raw_preview)
        splitter.addWidget(draft_card)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)
        return panel

    def _build_character_panel(self) -> QWidget:
        panel = QWidget(self)
        mark_toolbox_widget(panel, "toolboxScroll")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 12, 24, 24)
        layout.setSpacing(16)

        header_card, header_layout = self._create_card(
            "角色卡工作台",
            "左侧角色列表，中间正式角色卡，右侧 AI 草稿与原始响应。",
        )
        self.character_cards_enable = CheckBox("启用角色卡上下文注入")
        self.character_cards_enable.stateChanged.connect(self._on_character_cards_toggle_changed)
        header_layout.addWidget(self.character_cards_enable)

        action_row = QHBoxLayout()
        action_row.setSpacing(10)
        self.btn_character_batch = PrimaryPushButton("整批生成角色卡")
        self.btn_character_batch.clicked.connect(lambda: self._start_analysis("characters", ANALYSIS_SCOPE_CURRENT))
        self.btn_character_current = PushButton("重生当前角色")
        self.btn_character_current.clicked.connect(self._regenerate_current_character)
        self.btn_character_apply = PushButton("应用当前角色草稿")
        self.btn_character_apply.clicked.connect(self._apply_current_character_draft)
        self.btn_character_add = PushButton("新增空白角色卡")
        self.btn_character_add.clicked.connect(self._add_character_card)
        self.btn_character_delete = PushButton("删除当前角色")
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

        roster_card, roster_layout = self._create_card("角色列表", "同步角色名后，会把候选角色预填到这里。")
        self.character_list = ListWidget(self)
        self.character_list.currentItemChanged.connect(self._on_character_item_changed)
        roster_layout.addWidget(self.character_list, 1)
        splitter.addWidget(roster_card)

        editor_card, editor_layout = self._create_card("正式角色卡", "手工修改后会立即写入配置。")
        editor_form = QFormLayout()
        editor_form.setLabelAlignment(Qt.AlignmentFlag.AlignTop)
        editor_form.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        editor_form.setHorizontalSpacing(14)
        editor_form.setVerticalSpacing(12)
        self.character_widgets: dict[str, QWidget] = {}
        char_specs = [
            ("name", "角色名", False),
            ("name_translation", "推荐译名", False),
            ("aliases", "别名", True),
            ("match_keywords", "匹配关键词", True),
            ("identity", "身份", True),
            ("personality", "性格", True),
            ("speech_style", "说话风格", True),
            ("relationship_notes", "关系备注", True),
            ("prompt_notes", "翻译提示", True),
            ("sample_lines", "代表台词", True),
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
        self.character_enabled_checkbox = CheckBox("启用此角色卡")
        self.character_enabled_checkbox.stateChanged.connect(lambda value: self._on_character_flag_changed("enabled", value))
        self.character_primary_checkbox = CheckBox("标记为主要角色")
        self.character_primary_checkbox.stateChanged.connect(lambda value: self._on_character_flag_changed("is_primary", value))
        toggle_layout.addWidget(self.character_enabled_checkbox)
        toggle_layout.addWidget(self.character_primary_checkbox)
        toggle_layout.addStretch(1)

        editor_layout.addWidget(toggle_box)
        editor_layout.addLayout(editor_form)
        splitter.addWidget(editor_card)

        draft_card, draft_layout = self._create_card("角色草稿预览", "AI 生成的人设草稿会显示在这里。")
        self.character_draft_preview = self._create_preview_edit("选择角色后，这里显示草稿详情。")
        self.character_raw_preview = self._create_preview_edit("解析失败时，这里显示模型原始响应。")
        draft_layout.addWidget(BodyLabel("结构化草稿"))
        draft_layout.addWidget(self.character_draft_preview)
        draft_layout.addWidget(BodyLabel("原始响应 / 错误预览"))
        draft_layout.addWidget(self.character_raw_preview)
        splitter.addWidget(draft_card)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 4)
        splitter.setStretchFactor(2, 3)
        layout.addWidget(splitter, 1)
        return panel

    def _build_preview_panel(self) -> QWidget:
        panel = QWidget(self)
        mark_toolbox_widget(panel, "toolboxScroll")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 12, 24, 24)
        layout.setSpacing(16)

        input_card, input_layout = self._create_card(
            "提示词命中预览",
            "输入样例原文后，会实时显示命中的角色卡和最终注入片段。",
        )
        self.preview_input_edit = PlainTextEdit(self)
        self.preview_input_edit.setPlaceholderText("在这里输入一段样例原文，支持多行。")
        self.preview_input_edit.setMinimumHeight(160)
        self.preview_input_edit.textChanged.connect(self._schedule_prompt_preview)
        input_layout.addWidget(self.preview_input_edit)
        self.preview_matched_label = BodyLabel("未输入样例原文。")
        self.preview_matched_label.setWordWrap(True)
        input_layout.addWidget(self.preview_matched_label)
        layout.addWidget(input_card)

        preview_card, preview_layout = self._create_card("注入结果", "这里展示工作台上下文如何进入真实提示词构建。")
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(12)
        self.preview_world_context = self._create_preview_edit("世界观块将在这里显示。")
        self.preview_character_context = self._create_preview_edit("命中角色块将在这里显示。")
        self.preview_final_context = self._create_preview_edit("最终注入片段将在这里显示。")
        grid.addWidget(BodyLabel("世界观块"), 0, 0)
        grid.addWidget(self.preview_world_context, 1, 0)
        grid.addWidget(BodyLabel("角色块"), 0, 1)
        grid.addWidget(self.preview_character_context, 1, 1)
        preview_layout.addLayout(grid)
        preview_layout.addWidget(BodyLabel("最终注入片段"))
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
        """读取并规范化配置。"""
        config = Config().load()
        if self._normalize_workbench_config(config):
            config.save()
        return config

    def _save_config(self, config: Config) -> None:
        """统一保存配置。"""
        self._normalize_workbench_config(config)
        config.save()

    def refresh_from_config(self) -> None:
        """从配置刷新整个页面。"""
        config = self._load_config()
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
            select_id = self._selected_character_id or (cards[0]["id"] if cards else "")
            if select_id == "" and drafts:
                select_id = drafts[0]["id"]
            self._refresh_character_list(cards, drafts, select_id)
            self._refresh_worldbook_draft_view(config)
            self._refresh_character_draft_view(config)
            self._refresh_summary(config)
            self._refresh_prompt_preview()
        finally:
            self._loading_ui = False
        self._refresh_action_state()

    def _refresh_summary(self, config: Config) -> None:
        """刷新摘要。"""
        platform = config.get_platform(config.activate_platform)
        platform_name = normalize_text(platform.get("name", "")) if platform else "未配置"
        model_name = normalize_text(platform.get("model", "")) if platform else "未配置"
        worldbook = normalize_worldbook(getattr(config, "renpy_workbench_worldbook_data", {}))
        cards = normalize_character_cards(getattr(config, "renpy_workbench_character_cards", []))
        drafts = normalize_character_cards(getattr(config, "renpy_workbench_generated_character_drafts", []))
        enabled_cards = sum(1 for card in cards if card.get("enabled", True))
        world_ready = "已启用" if getattr(config, "renpy_workbench_worldbook_enable", False) and any(worldbook.values()) else "未启用"
        draft_scope = normalize_analysis_scope(getattr(config, "renpy_workbench_last_analysis_scope", ANALYSIS_SCOPE_CURRENT))
        draft_text = f"世界观草稿：{'有' if any(normalize_worldbook(getattr(config, 'renpy_workbench_generated_worldbook_draft', {})).values()) else '无'}"
        draft_text += f"；角色草稿：{len(drafts)} 张；最近范围：{'当前范围' if draft_scope == ANALYSIS_SCOPE_CURRENT else '全项目'}"

        summary = {
            "platform": platform_name or "未配置",
            "model": model_name or "未配置",
            "source_target": f"{config.source_language} -> {config.target_language}",
            "input_folder": normalize_text(config.input_folder) or "未设置",
            "output_folder": normalize_text(config.output_folder) or "未设置",
            "project_root": normalize_text(config.renpy_game_folder) or "未设置",
            "tl_folder": normalize_text(config.renpy_tl_folder) or "未设置",
            "worldbook": world_ready,
            "characters": f"共 {len(cards)} 张，启用 {enabled_cards} 张",
            "drafts": draft_text,
        }
        for key, value in summary.items():
            label = self.summary_labels.get(key)
            if label is not None:
                label.setText(value)

        self.overview_hint_label.setText(self._analysis_source_summary or "当前尚未执行 AI 分析。")

    def _refresh_worldbook_draft_view(self, config: Config) -> None:
        """刷新世界观草稿预览。"""
        draft = normalize_worldbook(getattr(config, "renpy_workbench_generated_worldbook_draft", {}))
        if any(draft.values()):
            lines = [
                f"项目名：{draft.get('project_name', '')}",
                f"类型：{draft.get('genre', '')}",
                f"背景摘要：{draft.get('setting_summary', '')}",
                f"时代与环境：{draft.get('era_background', '')}",
                f"整体语气：{draft.get('tone_style', '')}",
                f"叙事规则：{draft.get('narrative_rules', '')}",
                f"格式规则：{draft.get('format_rules', '')}",
                f"剧透备注：{draft.get('spoiler_notes', '')}",
            ]
            self.worldbook_draft_preview.setPlainText("\n\n".join(lines))
        else:
            self.worldbook_draft_preview.setPlainText("")
        self.worldbook_raw_preview.setPlainText(self._last_worldbook_raw)

    def _refresh_character_list(
        self,
        cards: list[dict[str, Any]],
        drafts: list[dict[str, Any]],
        select_id: str,
    ) -> None:
        """刷新角色列表。"""
        self.character_list.clear()
        draft_ids = {draft.get("id") for draft in drafts}
        for card in cards:
            item = QListWidgetItem(card.get("name", "未命名角色"))
            item.setData(Qt.ItemDataRole.UserRole, card.get("id", ""))
            suffix = []
            if card.get("is_primary", False):
                suffix.append("主")
            if card.get("enabled", True) is False:
                suffix.append("关")
            if card.get("id") in draft_ids:
                suffix.append("草稿")
            if suffix:
                item.setText(f"{card.get('name', '未命名角色')} [{' / '.join(suffix)}]")
            self.character_list.addItem(item)

        self._selected_character_id = select_id if any(card.get("id") == select_id for card in cards) else ""
        if self.character_list.count() == 0:
            self._clear_character_editor()
            return

        target_row = 0
        for row in range(self.character_list.count()):
            item = self.character_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == self._selected_character_id:
                target_row = row
                break
        self.character_list.setCurrentRow(target_row)

    def _clear_character_editor(self) -> None:
        """清空角色编辑区。"""
        for widget in self.character_widgets.values():
            if isinstance(widget, PlainTextEdit):
                widget.setPlainText("")
            else:
                widget.setText("")
        self.character_enabled_checkbox.setChecked(False)
        self.character_primary_checkbox.setChecked(False)
        self.character_draft_preview.setPlainText("")
        self.character_raw_preview.setPlainText(self._last_character_raw)

    def _refresh_character_editor(self, config: Config) -> None:
        """根据当前选中角色刷新编辑器。"""
        cards = normalize_character_cards(getattr(config, "renpy_workbench_character_cards", []))
        current = next((card for card in cards if card.get("id") == self._selected_character_id), None)
        if current is None:
            self._clear_character_editor()
            return

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
            self._loading_ui = False
        self._refresh_character_draft_view(config)

    def _refresh_character_draft_view(self, config: Config) -> None:
        """刷新角色草稿预览。"""
        drafts = normalize_character_cards(getattr(config, "renpy_workbench_generated_character_drafts", []))
        draft = next((card for card in drafts if card.get("id") == self._selected_character_id), None)
        if draft is None:
            self.character_draft_preview.setPlainText("")
        else:
            lines = [
                f"角色名：{draft.get('name', '')}",
                f"推荐译名：{draft.get('name_translation', '')}",
                f"别名：{'、'.join(draft.get('aliases', [])) or '暂无'}",
                f"匹配关键词：{'、'.join(draft.get('match_keywords', [])) or '暂无'}",
                f"身份：{draft.get('identity', '') or '暂无'}",
                f"性格：{draft.get('personality', '') or '暂无'}",
                f"说话风格：{draft.get('speech_style', '') or '暂无'}",
                f"关系备注：{draft.get('relationship_notes', '') or '暂无'}",
                f"翻译提示：{draft.get('prompt_notes', '') or '暂无'}",
            ]
            samples = draft.get("sample_lines", [])
            if samples:
                lines.append("代表台词：")
                lines.extend(f"- {line}" for line in samples)
            self.character_draft_preview.setPlainText("\n".join(lines))
        self.character_raw_preview.setPlainText(self._last_character_raw)

    def _refresh_action_state(self) -> None:
        """刷新按钮状态。"""
        config = self._load_config()
        platform = config.get_platform(config.activate_platform)
        api_format = platform.get("api_format") if isinstance(platform, dict) else None
        engine_busy = Engine.get().get_status() != Engine.Status.IDLE
        supported = api_format in WorkbenchAnalysisService.SUPPORTED_FORMATS
        analysis_ready = supported and not engine_busy and not self._analysis_running and not self._sync_running
        has_worldbook_draft = any(normalize_worldbook(getattr(config, "renpy_workbench_generated_worldbook_draft", {})).values())
        has_character_draft = any(
            card.get("id") == self._selected_character_id
            for card in normalize_character_cards(getattr(config, "renpy_workbench_generated_character_drafts", []))
        )
        has_any_draft = has_worldbook_draft or bool(getattr(config, "renpy_workbench_generated_character_drafts", []))

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
        self.btn_character_apply.setEnabled(not self._analysis_running and has_character_draft)
        self.btn_character_add.setEnabled(not self._analysis_running and not self._sync_running)
        self.btn_character_delete.setEnabled(not self._analysis_running and not self._sync_running and self._selected_character_id != "")

        if engine_busy:
            self.overview_status_label.setText("当前翻译任务运行中，AI 生成与角色同步已暂时禁用。")
        elif supported is False:
            self.overview_status_label.setText("当前接口不支持 AI 分析。请切换到 OpenAI / Google / Anthropic / SakuraLLM 类接口。")
        elif self._analysis_running:
            self.overview_status_label.setText("AI 分析进行中，请稍候。")
        elif self._sync_running:
            self.overview_status_label.setText("角色同步进行中，请稍候。")

    def _on_worldbook_toggle_changed(self, state: int) -> None:
        """世界观开关变化。"""
        if self._loading_ui:
            return
        config = self._load_config()
        config.renpy_workbench_worldbook_enable = bool(state)
        self._save_config(config)
        self._refresh_prompt_preview()
        self._refresh_summary(config)

    def _on_character_cards_toggle_changed(self, state: int) -> None:
        """角色卡开关变化。"""
        if self._loading_ui:
            return
        config = self._load_config()
        config.renpy_workbench_character_cards_enable = bool(state)
        self._save_config(config)
        self._refresh_prompt_preview()
        self._refresh_summary(config)

    def _on_worldbook_field_changed(self, field: str) -> None:
        """世界观字段变化。"""
        if self._loading_ui:
            return
        config = self._load_config()
        worldbook = normalize_worldbook(getattr(config, "renpy_workbench_worldbook_data", {}))
        widget = self.worldbook_widgets.get(field)
        if widget is None:
            return
        if isinstance(widget, PlainTextEdit):
            worldbook[field] = widget.toPlainText().strip()
        else:
            worldbook[field] = widget.text().strip()
        config.renpy_workbench_worldbook_data = worldbook
        self._save_config(config)
        self._refresh_summary(config)
        self._refresh_prompt_preview()

    def _on_character_item_changed(self, current: QListWidgetItem, previous: QListWidgetItem) -> None:
        """角色列表选中变化。"""
        del previous
        if current is None:
            self._selected_character_id = ""
            self._clear_character_editor()
            self._refresh_action_state()
            return
        self._selected_character_id = normalize_text(current.data(Qt.ItemDataRole.UserRole))
        config = self._load_config()
        self._refresh_character_editor(config)
        self._refresh_action_state()

    def _update_current_character_card(self, updater) -> None:
        """更新当前角色卡。"""
        if self._loading_ui or self._selected_character_id == "":
            return
        config = self._load_config()
        cards = normalize_character_cards(getattr(config, "renpy_workbench_character_cards", []))
        updated_cards: list[dict[str, Any]] = []
        for card in cards:
            if card.get("id") == self._selected_character_id:
                updater(card)
                updated_cards.append(normalize_character_card(card))
            else:
                updated_cards.append(card)
        config.renpy_workbench_character_cards = updated_cards
        self._save_config(config)
        self._refresh_summary(config)
        self._refresh_prompt_preview()
        self._refresh_character_list(updated_cards, normalize_character_cards(config.renpy_workbench_generated_character_drafts), self._selected_character_id)
        self._refresh_character_editor(config)

    def _on_character_field_changed(self, field: str) -> None:
        """角色字段变化。"""
        def updater(card: dict[str, Any]) -> None:
            widget = self.character_widgets[field]
            if field in ("aliases", "match_keywords", "sample_lines"):
                card[field] = normalize_text_list(widget.toPlainText().splitlines())
            elif isinstance(widget, PlainTextEdit):
                card[field] = widget.toPlainText().strip()
            else:
                card[field] = widget.text().strip()

        self._update_current_character_card(updater)

    def _on_character_flag_changed(self, field: str, state: int) -> None:
        """角色布尔开关变化。"""
        def updater(card: dict[str, Any]) -> None:
            card[field] = bool(state)

        self._update_current_character_card(updater)

    def _add_character_card(self) -> None:
        """新增空白角色卡。"""
        config = self._load_config()
        cards = normalize_character_cards(getattr(config, "renpy_workbench_character_cards", []))
        card = create_default_character_card(f"角色{len(cards) + 1}")
        cards.append(card)
        config.renpy_workbench_character_cards = cards
        self._save_config(config)
        self._selected_character_id = card["id"]
        self.refresh_from_config()

    def _delete_current_character(self) -> None:
        """删除当前角色卡。"""
        if self._selected_character_id == "":
            return
        config = self._load_config()
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
        self.refresh_from_config()

    def _schedule_prompt_preview(self) -> None:
        """延迟刷新提示词预览。"""
        self._preview_timer.start()

    def _refresh_prompt_preview(self) -> None:
        """刷新提示词预览。"""
        config = self._load_config()
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
            self.preview_matched_label.setText("未输入样例原文。")
        else:
            names = [card.get("name", "") for card in matched_cards]
            self.preview_matched_label.setText(
                f"命中角色：{'、'.join(names) if names else '无'}"
            )

    def _start_analysis(self, mode: str, scope: str) -> None:
        """启动 AI 分析线程。"""
        if self._analysis_running:
            return
        self._analysis_running = True
        self._refresh_action_state()
        self.overview_status_label.setText("正在执行 AI 分析…")
        scope = normalize_analysis_scope(scope)
        current_id = self._selected_character_id

        def task() -> None:
            try:
                config = self._load_config()
                if mode == "all":
                    result = self.analysis_service.analyze_all(config, scope)
                elif mode == "worldbook":
                    result = self.analysis_service.generate_worldbook_only(config, scope)
                elif mode == "characters":
                    result = self.analysis_service.generate_character_only(config, scope)
                elif mode == "character_single":
                    result = self.analysis_service.generate_character_only(config, scope, current_id)
                else:
                    raise AnalysisServiceError("未知的分析模式。")
                self.signals.analysis_success.emit(
                    {
                        "mode": mode,
                        "scope": scope,
                        "result": result,
                        "card_id": current_id,
                    }
                )
            except AnalysisServiceError as exc:
                self.signals.analysis_failed.emit(
                    {
                        "mode": mode,
                        "scope": scope,
                        "message": str(exc),
                        "raw_response": exc.raw_response,
                    }
                )
            except Exception as exc:
                self.signals.analysis_failed.emit(
                    {
                        "mode": mode,
                        "scope": scope,
                        "message": str(exc),
                        "raw_response": "",
                    }
                )

        threading.Thread(target = task, daemon = True).start()

    def _on_analysis_success(self, payload: dict[str, Any]) -> None:
        """处理分析成功。"""
        self._analysis_running = False
        result: AnalysisResult = payload["result"]
        mode = payload["mode"]
        card_id = payload.get("card_id", "")
        config = self._load_config()
        config.renpy_workbench_last_analysis_scope = result.scope
        self._analysis_source_summary = f"最近分析来源：{result.source_summary}"

        if result.worldbook_draft:
            config.renpy_workbench_generated_worldbook_draft = normalize_worldbook(result.worldbook_draft)
            self._last_worldbook_raw = result.worldbook_raw

        if result.character_drafts:
            if mode in ("all", "characters"):
                config.renpy_workbench_generated_character_drafts = normalize_character_cards(result.character_drafts)
            else:
                drafts = normalize_character_cards(getattr(config, "renpy_workbench_generated_character_drafts", []))
                merged: list[dict[str, Any]] = []
                incoming = normalize_character_cards(result.character_drafts)
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
        if card_id:
            self._selected_character_id = card_id
        self.refresh_from_config()
        self.overview_status_label.setText("AI 草稿已生成，请在右侧预览并决定是否应用。")
        InfoBar.success("完成", "AI 草稿生成完成。", parent = self)

    def _on_analysis_failed(self, payload: dict[str, Any]) -> None:
        """处理分析失败。"""
        self._analysis_running = False
        mode = payload.get("mode", "")
        raw_response = normalize_text(payload.get("raw_response", ""))
        message = normalize_text(payload.get("message", "AI 分析失败"))
        if mode == "worldbook" or "世界观" in message:
            self._last_worldbook_raw = raw_response
        else:
            self._last_character_raw = raw_response
        self.refresh_from_config()
        self.overview_status_label.setText(message)
        InfoBar.error("错误", message, parent = self, duration = 5000)

    def _merge_candidates_into_cards(
        self,
        config: Config,
        candidate_cards: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], int]:
        """将候选角色并入正式角色卡。"""
        cards = normalize_character_cards(getattr(config, "renpy_workbench_character_cards", []))
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
        self.overview_status_label.setText("正在同步角色候选…")

        def task() -> None:
            try:
                config = self._load_config()
                items, source_summary = self.analysis_service.load_scope_items(config, ANALYSIS_SCOPE_CURRENT)
                candidates = self.character_scanner.build_candidates(config, items, self.analysis_service.resolve_project_root(config))
                candidate_cards = [candidate.as_card_seed() for candidate in candidates]
                merged_cards, added = self._merge_candidates_into_cards(config, candidate_cards)
                self.signals.sync_success.emit(
                    {
                        "cards": merged_cards,
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
        config.renpy_workbench_character_cards = payload["cards"]
        self._save_config(config)
        self._analysis_source_summary = f"角色同步来源：{payload.get('source_summary', '')}"
        if self._selected_character_id == "" and payload["cards"]:
            self._selected_character_id = payload["cards"][0]["id"]
        self.refresh_from_config()
        self.overview_status_label.setText(f"角色同步完成，共新增 {payload.get('added', 0)} 张角色卡。")
        InfoBar.success("完成", f"角色同步完成，新增 {payload.get('added', 0)} 张角色卡。", parent = self)

    def _on_sync_failed(self, message: str) -> None:
        """同步失败回调。"""
        self._sync_running = False
        self._refresh_action_state()
        self.overview_status_label.setText(message)
        InfoBar.error("错误", message, parent = self, duration = 5000)

    def _apply_worldbook_draft(self) -> None:
        """应用世界观草稿。"""
        config = self._load_config()
        draft = normalize_worldbook(getattr(config, "renpy_workbench_generated_worldbook_draft", {}))
        if any(draft.values()) is False:
            InfoBar.warning("提示", "当前没有可应用的世界观草稿。", parent = self)
            return
        config.renpy_workbench_worldbook_data = draft
        config.renpy_workbench_worldbook_enable = True
        self._save_config(config)
        self.refresh_from_config()
        InfoBar.success("完成", "世界观草稿已应用。", parent = self)

    def _apply_current_character_draft(self) -> None:
        """应用当前角色草稿。"""
        if self._selected_character_id == "":
            InfoBar.warning("提示", "请先选择一个角色。", parent = self)
            return
        config = self._load_config()
        drafts = normalize_character_cards(getattr(config, "renpy_workbench_generated_character_drafts", []))
        draft = next((card for card in drafts if card.get("id") == self._selected_character_id), None)
        if draft is None:
            InfoBar.warning("提示", "当前角色没有可应用的草稿。", parent = self)
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
        self._save_config(config)
        self.refresh_from_config()
        InfoBar.success("完成", "当前角色草稿已应用。", parent = self)

    def _apply_all_drafts(self) -> None:
        """应用全部草稿。"""
        config = self._load_config()
        world_draft = normalize_worldbook(getattr(config, "renpy_workbench_generated_worldbook_draft", {}))
        char_drafts = normalize_character_cards(getattr(config, "renpy_workbench_generated_character_drafts", []))
        if any(world_draft.values()) is False and char_drafts == []:
            InfoBar.warning("提示", "当前没有可应用的草稿。", parent = self)
            return

        if any(world_draft.values()):
            config.renpy_workbench_worldbook_data = world_draft
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
        self._save_config(config)
        self.refresh_from_config()
        InfoBar.success("完成", "全部草稿已应用。", parent = self)

    def _regenerate_current_character(self) -> None:
        """重生当前角色。"""
        scope = ANALYSIS_SCOPE_CURRENT
        config = self._load_config()
        scope = normalize_analysis_scope(getattr(config, "renpy_workbench_last_analysis_scope", ANALYSIS_SCOPE_CURRENT))
        self._start_analysis("character_single", scope)

    def _navigate_page(self, attr_name: str, factory) -> None:
        """导航到目标页面。"""
        if not self.window:
            return
        if hasattr(self.window, attr_name) is False:
            setattr(self.window, attr_name, factory())
        page = getattr(self.window, attr_name)
        if hasattr(self.window, "navigate_to_page"):
            self.window.navigate_to_page(page)
        elif hasattr(self.window, "switchTo"):
            self.window.switchTo(page)

    def _open_glossary_page(self) -> None:
        from frontend.RenpyToolbox.LocalGlossaryPage import LocalGlossaryPage

        self._navigate_page("local_glossary_page", lambda: LocalGlossaryPage("local-glossary", self.window))

    def _open_text_preserve_page(self) -> None:
        from frontend.RenpyToolbox.TextPreservePage import TextPreservePage

        self._navigate_page("text_preserve_page", lambda: TextPreservePage("text-preserve", self.window))

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
        self.refresh_from_config()
