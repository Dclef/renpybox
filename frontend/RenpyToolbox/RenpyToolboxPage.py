"""Ren'Py 工具箱入口页。"""

import importlib
import json
import os
from pathlib import Path

from PyQt5.QtCore import QEvent, QTimer, Qt
from PyQt5.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    FlowLayout,
    FluentIcon,
    IconWidget,
    InfoBar,
    SearchLineEdit,
    SingleDirectionScrollArea,
    StrongBodyLabel,
    TitleLabel,
)

from base.Base import Base
from base.LogManager import LogManager
from frontend.RenpyToolbox.ToolRegistry import (
    FLOW,
    GROUP_TITLES,
    GROUP_TITLES_EN,
    TOOL_SPECS,
    ToolSpec,
    get_group_title,
)
from module.Cache.CacheManager import CacheManager
from module.Config import Config
from module.Localizer.Localizer import Localizer
from module.Renpy.ProjectPaths import (
    RenpyProjectPaths,
    read_run_manifest,
    resolve_translation_output,
)
from widget.ItemCard import ItemCard
from widget.ThemeHelper import mark_toolbox_scroll_area, mark_toolbox_widget


class RenpyToolboxPage(Base, QWidget):
    """集中展示 Ren'Py 翻译流程和辅助工具。"""

    def __init__(self, object_name: str, parent=None):
        Base.__init__(self)
        QWidget.__init__(self, parent)
        self.setObjectName(object_name)
        mark_toolbox_widget(self)

        self.window = parent
        self._page_cache: dict[str, QWidget] = {}
        self._spec_by_key = {spec.key: spec for spec in TOOL_SPECS}
        self._cards: dict[str, ItemCard] = {}
        self._section_titles: dict[str, StrongBodyLabel] = {}
        self._section_headers: dict[str, QWidget] = {}
        self._section_count_labels: dict[str, CaptionLabel] = {}
        self._section_containers: dict[str, QWidget] = {}
        self._flow_layouts: dict[str, FlowLayout] = {}
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(100)
        self._resize_timer.timeout.connect(self._update_card_widths)

        self._init_ui()

    def _init_ui(self) -> None:
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setSpacing(16)
        self.main_layout.setContentsMargins(24, 24, 24, 24)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(16)
        header_text = QWidget(self)
        header_text_layout = QVBoxLayout(header_text)
        header_text_layout.setContentsMargins(0, 0, 0, 0)
        header_text_layout.setSpacing(2)
        self.title = TitleLabel(Localizer.get().app_renpy_toolbox_page, header_text)
        title_font = self.title.font()
        title_font.setPixelSize(18)
        title_font.setBold(True)
        self.title.setFont(title_font)
        header_text_layout.addWidget(self.title)
        self.header_description = CaptionLabel(
            Localizer.get().toolbox_page_header_description,
            header_text,
        )
        self.header_description.setWordWrap(True)
        header_text_layout.addWidget(self.header_description)
        header_layout.addWidget(header_text, 1)
        header_layout.addStretch(1)

        self.search_edit = SearchLineEdit(self)
        self.search_edit.setPlaceholderText(Localizer.get().toolbox_search_tools)
        self.search_edit.setMinimumWidth(220)
        self.search_edit.setMaximumWidth(320)
        self.search_edit.textChanged.connect(self._filter_cards)
        header_layout.addWidget(self.search_edit)
        self.main_layout.addLayout(header_layout)

        self.scroll_area = SingleDirectionScrollArea(
            orient=Qt.Orientation.Vertical,
            parent=self,
        )
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.enableTransparentBackground()
        mark_toolbox_scroll_area(self.scroll_area)

        scroll_widget = QWidget(self.scroll_area)
        mark_toolbox_widget(scroll_widget, "toolboxScroll")
        self.scroll_layout = QVBoxLayout(scroll_widget)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(20)

        for group in GROUP_TITLES:
            self._create_flow_section(group, get_group_title(group))
        self._create_empty_state(scroll_widget)
        self.scroll_layout.addStretch(0)

        self.scroll_area.setWidget(scroll_widget)
        self.main_layout.addWidget(self.scroll_area, 1)
        self._create_tool_cards()

    def _create_empty_state(self, parent: QWidget) -> None:
        self.empty_state = QWidget(parent)
        self.empty_state.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(self.empty_state)
        layout.setContentsMargins(0, 32, 0, 32)
        layout.setSpacing(8)
        layout.addStretch(1)

        icon = IconWidget(FluentIcon.SEARCH_MIRROR, self.empty_state)
        icon.setFixedSize(48, 48)
        icon_effect = QGraphicsOpacityEffect(icon)
        icon_effect.setOpacity(0.4)
        icon.setGraphicsEffect(icon_effect)
        layout.addWidget(icon, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.empty_title = BodyLabel(
            Localizer.get().toolbox_no_matching_tools,
            self.empty_state,
        )
        layout.addWidget(self.empty_title, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.empty_description = CaptionLabel(
            Localizer.get().toolbox_try_another_keyword_clear_search_box,
            self.empty_state,
        )
        layout.addWidget(
            self.empty_description,
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )
        layout.addStretch(1)

        self.empty_state.setVisible(False)
        self.scroll_layout.addWidget(self.empty_state, 1)

    def _create_flow_section(self, group: str, title: str) -> None:
        header = QWidget(self)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)
        title_label = StrongBodyLabel(title, header)
        header_layout.addWidget(title_label)
        header_layout.addStretch(1)
        count_label = CaptionLabel("", header)
        count_label.setObjectName("toolboxGroupCount")
        header_layout.addWidget(count_label)
        self.scroll_layout.addWidget(header)

        container = QWidget(self)
        mark_toolbox_widget(container, "toolboxFlow")
        layout = FlowLayout(container, needAni=False, isTight=True)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(12)
        layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.addWidget(container)

        self._section_titles[group] = title_label
        self._section_headers[group] = header
        self._section_count_labels[group] = count_label
        self._section_containers[group] = container
        self._flow_layouts[group] = layout

    def _create_tool_cards(self) -> None:
        has_pending_translation = self._check_pending_translation()
        project_ready = self._has_project()
        has_numbered_flow_cards = any(
            spec.group == FLOW and spec.key != "continue_translation"
            for spec in TOOL_SPECS
        )
        workflow_step = 0

        for spec in TOOL_SPECS:
            if spec.key == "continue_translation" and not has_pending_translation:
                continue
            if spec.group == FLOW and spec.key != "continue_translation":
                workflow_step += 1

            title = spec.localized_title()
            description = spec.localized_description()
            card = ItemCard(
                parent=self,
                title=title,
                description=description,
                icon=spec.icon,
                step=workflow_step if spec.group == FLOW and spec.key != "continue_translation" else 0,
                project_ready=project_ready or not spec.requires_project,
                reserve_step_space=(
                    spec.group == FLOW
                    and spec.key == "continue_translation"
                    and has_numbered_flow_cards
                ),
                clicked=lambda widget, current=spec: self._open_tool(current, widget),
            )
            card._open_tooltip = Localizer.get().onekey_open.format(title=title)
            card._project_requirement = Localizer.get().toolbox_select_game_folder_first
            card.project_requirement_label.setText(card._project_requirement)
            card.set_project_ready(project_ready or not spec.requires_project)
            self._flow_layouts[spec.group].addWidget(card)
            self._cards[spec.key] = card

        strings = Localizer.get()
        for group, count_label in self._section_count_labels.items():
            count = sum(
                1
                for key, spec in self._spec_by_key.items()
                if spec.group == group and key in self._cards
            )
            count_label.setText(strings.toolbox_group_count.format(COUNT=count))

        self._filter_cards(self.search_edit.text())

    def _filter_cards(self, text: str) -> None:
        """按工具信息即时过滤卡片，并隐藏空分组。"""
        query = text.strip().casefold()
        group_visible = {group: False for group in GROUP_TITLES}
        card_visible = {}

        for key, card in self._cards.items():
            spec = self._spec_by_key[key]
            search_text = " ".join(
                (
                    spec.title,
                    spec.title_en,
                    spec.description,
                    spec.description_en,
                    GROUP_TITLES[spec.group],
                    GROUP_TITLES_EN[spec.group],
                    *spec.keywords,
                )
            ).casefold()
            visible = not query or query in search_text
            card_visible[key] = visible
            group_visible[spec.group] = group_visible[spec.group] or visible

        self.empty_state.setVisible(not any(card_visible.values()))

        for group, visible in group_visible.items():
            self._section_headers[group].setVisible(visible)
            self._section_titles[group].setVisible(visible)
            self._section_containers[group].setVisible(visible)

        for key, visible in card_visible.items():
            self._cards[key].setVisible(visible)

        self._sync_section_heights()
        for group, visible in group_visible.items():
            if not visible:
                continue
            self._flow_layouts[group].invalidate()
            self._section_containers[group].updateGeometry()
        self.scroll_layout.invalidate()
        self.scroll_layout.activate()
        for group, visible in group_visible.items():
            if visible:
                self._flow_layouts[group].activate()
        self._resize_timer.start()

    def resizeEvent(self, event: QEvent) -> None:
        super().resizeEvent(event)
        self._resize_timer.start()

    def _update_card_widths(self) -> None:
        width = self.scroll_area.viewport().contentsRect().width()
        if width <= 0:
            return

        columns = max(1, (width + 12) // 272)
        # FlowLayout 用 QRect.right()（包含式坐标）判断换行，需预留 1px。
        card_width = max(1, (width - 12 * (columns - 1) - 1) // columns)
        for card in self._cards.values():
            card.setFixedWidth(card_width)

        self._sync_section_heights()
        for group, container in self._section_containers.items():
            self._flow_layouts[group].invalidate()
            container.updateGeometry()
            self._flow_layouts[group].activate()
        self.scroll_layout.invalidate()
        self.scroll_layout.activate()

    def _sync_section_heights(self) -> None:
        if not self.isVisible():
            return

        for group, container in self._section_containers.items():
            if not container.isVisible():
                continue
            width = container.contentsRect().width()
            if width > 0:
                container.setFixedHeight(self._flow_layouts[group].heightForWidth(width))

    def _has_project(self) -> bool:
        try:
            paths = RenpyProjectPaths.from_config(Config().load())
            return paths is not None and paths.game_dir.is_dir()
        except Exception:
            return False

    def _refresh_project_cards(self) -> None:
        project_ready = self._has_project()
        for key, card in self._cards.items():
            spec = self._spec_by_key[key]
            card.set_project_ready(project_ready or not spec.requires_project)

    def _construct_page(self, spec: ToolSpec) -> QWidget:
        page_cls = spec.page_cls
        if page_cls is None:
            if not spec.lazy_import:
                raise ValueError(
                    Localizer.get().toolbox_tool_has_no_configured_page.format(key=spec.key)
                )
            module_name, class_name = spec.lazy_import.rsplit(":", 1)
            page_cls = getattr(importlib.import_module(module_name), class_name)

        if spec.object_name:
            return page_cls(spec.object_name, self.window)
        return page_cls(self.window)

    def get_tool_page(self, key: str) -> QWidget:
        """获取工具页单例，供一键流程和工作台复用。"""
        spec = self._spec_by_key.get(key)
        if spec is None:
            raise KeyError(Localizer.get().toolbox_unknown_tool.format(key=key))

        page = self._page_cache.get(key)
        if page is None:
            page = self._construct_page(spec)
            mark_toolbox_widget(page)
            self._page_cache[key] = page
        return page

    def _open_tool(self, spec: ToolSpec, card: ItemCard | None = None) -> None:
        try:
            if spec.requires_project and not self._has_project():
                InfoBar.warning(
                    Localizer.get().toolbox_game_folder_not_selected,
                    Localizer.get().toolbox_select_game_folder_one_click_translation_first,
                    parent=self,
                )
                return
            if spec.handler:
                getattr(self, spec.handler)(card)
                return

            page = self.get_tool_page(spec.key)
            self.window.navigate_to_page(page)
        except Exception as exc:
            title = spec.localized_title()
            LogManager.get().error(f"打开{spec.title}页面失败: {exc}")
            InfoBar.error(
                Localizer.get().toolbox_failed_open,
                Localizer.get().toolbox_could_not_open.format(title=title, exc=exc),
                parent=self,
            )

    def _get_one_key_translate_page(self) -> QWidget:
        return self.get_tool_page("one_key_translate")

    def _open_one_key_translate(self, card: ItemCard | None) -> None:
        del card
        self.window.navigate_to_page(self._get_one_key_translate_page())

    def _open_apply_translation(self, card: ItemCard | None) -> None:
        """从工具箱直接应用最近一次翻译结果。"""
        page = self._get_one_key_translate_page()

        if not page.game_dir:
            config = Config().load()
            paths = RenpyProjectPaths.from_config(config)
            if paths is not None:
                page.game_dir = str(paths.project_root)
                page.tl_folder_edit.blockSignals(True)
                page.tl_folder_edit.setText(paths.language)
                page.tl_folder_edit.blockSignals(False)

                manifest = read_run_manifest(paths)
                if manifest and str(manifest.get("run_kind", "")).casefold() == "incremental":
                    page._incremental_output_dir = manifest.get("output_folder") or None
                    page._incremental_dir = manifest.get("input_folder") or None
                    page._apply_target_dir = manifest.get("application_target_dir") or None

        page._tool_apply_translation(card, feedback_parent=self)

    def _open_continue_translation(self, card: ItemCard | None) -> None:
        del card
        try:
            page = getattr(self.window, "translation_page", None)
            if page is None:
                from frontend.TranslationPage import TranslationPage

                page = TranslationPage("translation_page", self.window)
                self.window.translation_page = page
            mark_toolbox_widget(page)
            self.window.navigate_to_page(page)
        except Exception as exc:
            LogManager.get().error(f"打开翻译面板失败: {exc}")
            InfoBar.error(
                Localizer.get().error,
                Localizer.get().toolbox_failed_open_translation_panel.format(exc=exc),
                parent=self,
            )

    def _check_pending_translation(self) -> bool:
        """检查是否存在尚未完成的翻译任务。"""
        try:
            output_path = resolve_translation_output(Config().load())
            output_folder = str(output_path) if output_path is not None else ""
            if not output_folder or not os.path.isdir(output_folder):
                return False

            cache_dir = Path(output_folder) / "cache"
            items_file = cache_dir / "items.json"
            sqlite_file = cache_dir / "cache.db"

            if items_file.exists():
                with items_file.open("r", encoding="utf-8") as file:
                    items = json.load(file)

                def is_untranslated(item) -> bool:
                    if not isinstance(item, dict):
                        return False
                    status = item.get("status", 0)
                    if status == 0 or str(status).upper() == "UNTRANSLATED":
                        return True
                    try:
                        return (
                            Base.normalize_translation_status(status)
                            == Base.TranslationStatus.UNTRANSLATED
                        )
                    except (TypeError, ValueError):
                        return False

                if any(is_untranslated(item) for item in items):
                    return True

            if sqlite_file.exists():
                cache_manager = CacheManager(service=False)
                cache_manager.load_items_from_file(output_folder)
                return any(
                    item.get_status() == Base.TranslationStatus.UNTRANSLATED
                    for item in cache_manager.get_items()
                )
            return False
        except Exception:
            return False

    def showEvent(self, event: QEvent) -> None:
        super().showEvent(event)
        self._refresh_project_cards()
        # 紧凑流式布局在父页隐藏时会暂时把全部子项视为不可见。
        # 等页面真正显示后再恢复过滤状态并重排，避免返回时卡片区塌陷。
        QTimer.singleShot(0, self._restore_card_layout)
        QTimer.singleShot(0, self._update_card_widths)

    def _restore_card_layout(self) -> None:
        self._filter_cards(self.search_edit.text())
