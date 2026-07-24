from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget
from PyQt5.QtWidgets import QLayout
from PyQt5.QtWidgets import QVBoxLayout
from qfluentwidgets import FluentWindow
from qfluentwidgets import SingleDirectionScrollArea

from base.Base import Base
from frontend.Setting.TranslationSettingsBinding import OUTPUT_PROTOCOL_VALUES
from frontend.Setting.TranslationSettingsBinding import choice_index
from frontend.Setting.TranslationSettingsBinding import normalize_output_protocol_controls
from frontend.Setting.TranslationSettingsBinding import set_output_protocol
from frontend.Setting.TranslationSettingsBinding import set_single_line_translation
from module.Config import Config
from module.Localizer.Localizer import Localizer
from widget.ComboBoxCard import ComboBoxCard
from widget.SpinCard import SpinCard
from widget.SwitchButtonCard import SwitchButtonCard

class ExpertSettingsPage(QWidget, Base):

    def __init__(self, text: str, window: FluentWindow) -> None:
        super().__init__(window)
        self.setObjectName(text.replace(" ", "-"))
        self.single_line_translation_card = None
        self.output_protocol_card = None

        # 载入并保存默认配置
        config = Config().load()
        normalize_output_protocol_controls(config)
        config.save()

        # 设置容器
        self.root = QVBoxLayout(self)
        self.root.setSpacing(8)
        self.root.setContentsMargins(6, 24, 6, 24) # 左、上、右、下

        # 创建滚动区域的内容容器
        scroll_area_vbox_widget = QWidget()
        scroll_area_vbox = QVBoxLayout(scroll_area_vbox_widget)
        scroll_area_vbox.setContentsMargins(18, 0, 18, 0)

        # 创建滚动区域
        scroll_area = SingleDirectionScrollArea(orient = Qt.Orientation.Vertical)
        scroll_area.setWidget(scroll_area_vbox_widget)
        scroll_area.setWidgetResizable(True)
        scroll_area.enableTransparentBackground()

        # 将滚动区域添加到父布局
        self.root.addWidget(scroll_area)

        # 添加控件
        self.add_widget_preceding_lines_threshold(scroll_area_vbox, config, window)
        self.add_widget_preceding_disable_on_local(scroll_area_vbox, config, window)
        self.add_widget_single_line_translation(scroll_area_vbox, config, window)
        self.add_widget_output_protocol(scroll_area_vbox, config, window)
        self.add_widget_asset_regex(scroll_area_vbox, config, window)
        self.add_widget_asset_prompt_token_budget(scroll_area_vbox, config, window)
        self.add_widget_asset_prompt_max_items(scroll_area_vbox, config, window)
        self.add_widget_clean_ruby(scroll_area_vbox, config, window)
        self.add_widget_deduplication_in_trans(scroll_area_vbox, config, window)
        self.add_widget_deduplication_in_bilingual(scroll_area_vbox, config, window)
        self.add_widget_write_translated_name_fields_to_file(scroll_area_vbox, config, window)
        self.add_widget_auto_process_prefix_suffix_preserved_text(scroll_area_vbox, config, window)
        self.add_widget_sakura_jsonline_retry_enable(scroll_area_vbox, config, window)
        self.add_widget_result_checker_retry_count_threshold(scroll_area_vbox, config, window)

        # 填充
        scroll_area_vbox.addStretch(1)

    # 参考上文行数阈值
    def add_widget_preceding_lines_threshold(self, parent: QLayout, config: Config, window: FluentWindow) -> None:

        def init(widget: SpinCard) -> None:
            widget.get_spin_box().setRange(0, 9999999)
            widget.get_spin_box().setValue(config.preceding_lines_threshold)

        def value_changed(widget: SpinCard) -> None:
            config = Config().load()
            config.preceding_lines_threshold = widget.get_spin_box().value()
            config.save()

        parent.addWidget(
            SpinCard(
                title = Localizer.get().expert_settings_page_preceding_lines_threshold,
                description = Localizer.get().expert_settings_page_preceding_lines_threshold_desc,
                init = init,
                value_changed = value_changed,
            )
        )

    # 本地接口禁用参考上文
    def add_widget_preceding_disable_on_local(self, parent: QLayout, config: Config, window: FluentWindow) -> None:

        def init(widget: SwitchButtonCard) -> None:
            widget.get_switch_button().setChecked(
                config.enable_preceding_on_local
            )

        def checked_changed(widget: SwitchButtonCard) -> None:
            config = Config().load()
            config.enable_preceding_on_local = widget.get_switch_button().isChecked()
            config.save()

        parent.addWidget(
            SwitchButtonCard(
                title = Localizer.get().expert_settings_page_preceding_disable_on_local,
                description = Localizer.get().expert_settings_page_preceding_disable_on_local_desc,
                init = init,
                checked_changed = checked_changed,
            )
        )

    # 单行翻译模式
    def add_widget_single_line_translation(self, parent: QLayout, config: Config, window: FluentWindow) -> None:

        def init(widget: SwitchButtonCard) -> None:
            widget.get_switch_button().setChecked(
                config.single_line_translation_enable
            )

        def checked_changed(widget: SwitchButtonCard) -> None:
            config = Config().load()
            set_single_line_translation(
                config,
                widget.get_switch_button().isChecked(),
            )
            config.save()
            self.sync_output_protocol_controls(config)

        self.single_line_translation_card = SwitchButtonCard(
            title = Localizer.get().expert_settings_page_single_line_translation,
            description = Localizer.get().expert_settings_page_single_line_translation_desc,
            init = init,
            checked_changed = checked_changed,
        )
        parent.addWidget(self.single_line_translation_card)

    @staticmethod
    def output_protocol_labels() -> tuple[str, ...]:
        localizer = Localizer.get()
        return (
            localizer.translation_output_protocol_structured,
            localizer.translation_output_protocol_jsonline,
            localizer.translation_output_protocol_single_text,
        )

    def sync_output_protocol_controls(self, config: Config) -> None:
        if self.single_line_translation_card is not None:
            switch = self.single_line_translation_card.get_switch_button()
            switch.blockSignals(True)
            switch.setChecked(config.single_line_translation_enable)
            switch.blockSignals(False)

        if self.output_protocol_card is not None:
            combo_box = self.output_protocol_card.get_combo_box()
            combo_box.blockSignals(True)
            combo_box.setCurrentIndex(
                choice_index(config.translation_output_protocol, OUTPUT_PROTOCOL_VALUES)
            )
            combo_box.blockSignals(False)

    # 翻译输出协议
    def add_widget_output_protocol(self, parent: QLayout, config: Config, window: FluentWindow) -> None:

        def init(widget: ComboBoxCard) -> None:
            widget.get_combo_box().setCurrentIndex(
                choice_index(config.translation_output_protocol, OUTPUT_PROTOCOL_VALUES)
            )

        def current_changed(widget: ComboBoxCard) -> None:
            config = Config().load()
            set_output_protocol(
                config,
                OUTPUT_PROTOCOL_VALUES[widget.get_combo_box().currentIndex()],
            )
            config.save()
            self.sync_output_protocol_controls(config)

        self.output_protocol_card = ComboBoxCard(
            title = Localizer.get().translation_output_protocol_title,
            description = Localizer.get().translation_output_protocol_desc,
            items = list(self.output_protocol_labels()),
            init = init,
            current_changed = current_changed,
        )
        parent.addWidget(self.output_protocol_card)

    # 项目资产是否按正则匹配
    def add_widget_asset_regex(self, parent: QLayout, config: Config, window: FluentWindow) -> None:
        def init(widget: SwitchButtonCard) -> None:
            widget.get_switch_button().setChecked(config.asset_regex_enable)

        def checked_changed(widget: SwitchButtonCard) -> None:
            current = Config().load()
            current.asset_regex_enable = widget.get_switch_button().isChecked()
            current.save()

        parent.addWidget(
            SwitchButtonCard(
                title = Localizer.get().translation_asset_regex_title,
                description = Localizer.get().translation_asset_regex_desc,
                init = init,
                checked_changed = checked_changed,
            )
        )

    # 每批项目资产的提示词 token 预算
    def add_widget_asset_prompt_token_budget(self, parent: QLayout, config: Config, window: FluentWindow) -> None:
        def init(widget: SpinCard) -> None:
            widget.get_spin_box().setRange(1, 9999999)
            widget.get_spin_box().setValue(config.asset_prompt_token_budget)

        def value_changed(widget: SpinCard) -> None:
            current = Config().load()
            current.asset_prompt_token_budget = widget.get_spin_box().value()
            current.save()

        parent.addWidget(
            SpinCard(
                title = Localizer.get().translation_asset_token_budget_title,
                description = Localizer.get().translation_asset_token_budget_desc,
                init = init,
                value_changed = value_changed,
            )
        )

    # 每批项目资产的最大条目数
    def add_widget_asset_prompt_max_items(self, parent: QLayout, config: Config, window: FluentWindow) -> None:
        def init(widget: SpinCard) -> None:
            widget.get_spin_box().setRange(1, 9999999)
            widget.get_spin_box().setValue(config.asset_prompt_max_items)

        def value_changed(widget: SpinCard) -> None:
            current = Config().load()
            current.asset_prompt_max_items = widget.get_spin_box().value()
            current.save()

        parent.addWidget(
            SpinCard(
                title = Localizer.get().translation_asset_max_items_title,
                description = Localizer.get().translation_asset_max_items_desc,
                init = init,
                value_changed = value_changed,
            )
        )

    # 清理原文中的注音文本
    def add_widget_clean_ruby(self, parent: QLayout, config: Config, window: FluentWindow) -> None:

        def init(widget: SwitchButtonCard) -> None:
            widget.get_switch_button().setChecked(
                config.clean_ruby
            )

        def checked_changed(widget: SwitchButtonCard) -> None:
            config = Config().load()
            config.clean_ruby = widget.get_switch_button().isChecked()
            config.save()

        parent.addWidget(
            SwitchButtonCard(
                title = Localizer.get().expert_settings_page_clean_ruby,
                description = Localizer.get().expert_settings_page_clean_ruby_desc,
                init = init,
                checked_changed = checked_changed,
            )
        )

    # T++ 项目文件中对重复文本去重
    def add_widget_deduplication_in_trans(self, parent: QLayout, config: Config, window: FluentWindow) -> None:

        def init(widget: SwitchButtonCard) -> None:
            widget.get_switch_button().setChecked(
                config.deduplication_in_trans
            )

        def checked_changed(widget: SwitchButtonCard) -> None:
            config = Config().load()
            config.deduplication_in_trans = widget.get_switch_button().isChecked()
            config.save()

        parent.addWidget(
            SwitchButtonCard(
                title = Localizer.get().expert_settings_page_deduplication_in_trans,
                description = Localizer.get().expert_settings_page_deduplication_in_trans_desc,
                init = init,
                checked_changed = checked_changed,
            )
        )

    # 双语输出文件中原文与译文一致的文本只输出一次
    def add_widget_deduplication_in_bilingual(self, parent: QLayout, config: Config, window: FluentWindow) -> None:

        def init(widget: SwitchButtonCard) -> None:
            widget.get_switch_button().setChecked(
                config.deduplication_in_bilingual
            )

        def checked_changed(widget: SwitchButtonCard) -> None:
            config = Config().load()
            config.deduplication_in_bilingual = widget.get_switch_button().isChecked()
            config.save()

        parent.addWidget(
            SwitchButtonCard(
                title = Localizer.get().expert_settings_page_deduplication_in_bilingual,
                description = Localizer.get().expert_settings_page_deduplication_in_bilingual_desc,
                init = init,
                checked_changed = checked_changed,
            )
        )

    # 将姓名字段译文写入译文文件
    def add_widget_write_translated_name_fields_to_file(self, parent: QLayout, config: Config, window: FluentWindow) -> None:

        def init(widget: SwitchButtonCard) -> None:
            widget.get_switch_button().setChecked(
                config.write_translated_name_fields_to_file
            )

        def checked_changed(widget: SwitchButtonCard) -> None:
            config = Config().load()
            config.write_translated_name_fields_to_file = widget.get_switch_button().isChecked()
            config.save()

        parent.addWidget(
            SwitchButtonCard(
                title = Localizer.get().expert_settings_page_write_translated_name_fields_to_file,
                description = Localizer.get().expert_settings_page_write_translated_name_fields_to_file_desc,
                init = init,
                checked_changed = checked_changed,
            )
        )

    # 自动处理前后缀的保护文本段
    def add_widget_auto_process_prefix_suffix_preserved_text(self, parent: QLayout, config: Config, window: FluentWindow) -> None:

        def init(widget: SwitchButtonCard) -> None:
            widget.get_switch_button().setChecked(
                config.auto_process_prefix_suffix_preserved_text
            )

        def checked_changed(widget: SwitchButtonCard) -> None:
            config = Config().load()
            config.auto_process_prefix_suffix_preserved_text = widget.get_switch_button().isChecked()
            config.save()

        parent.addWidget(
            SwitchButtonCard(
                title = Localizer.get().expert_settings_page_auto_process_prefix_suffix_preserved_text,
                description = Localizer.get().expert_settings_page_auto_process_prefix_suffix_preserved_text_desc,
                init = init,
                checked_changed = checked_changed,
            )
        )

    # Sakura JSONLINE 解析失败时格式化重试
    def add_widget_sakura_jsonline_retry_enable(self, parent: QLayout, config: Config, window: FluentWindow) -> None:

        def init(widget: SwitchButtonCard) -> None:
            widget.get_switch_button().setChecked(
                config.sakura_jsonline_retry_enable
            )

        def checked_changed(widget: SwitchButtonCard) -> None:
            config = Config().load()
            config.sakura_jsonline_retry_enable = widget.get_switch_button().isChecked()
            config.save()

        parent.addWidget(
            SwitchButtonCard(
                title = Localizer.get().expert_settings_page_sakura_jsonline_retry_enable,
                description = Localizer.get().expert_settings_page_sakura_jsonline_retry_enable_desc,
                init = init,
                checked_changed = checked_changed,
            )
        )

    # 结果检查 - 重试次数达到阈值
    def add_widget_result_checker_retry_count_threshold(self, parent: QLayout, config: Config, window: FluentWindow) -> None:

        def init(widget: SwitchButtonCard) -> None:
            widget.get_switch_button().setChecked(
                config.result_checker_retry_count_threshold
            )

        def checked_changed(widget: SwitchButtonCard) -> None:
            config = Config().load()
            config.result_checker_retry_count_threshold = widget.get_switch_button().isChecked()
            config.save()

        parent.addWidget(
            SwitchButtonCard(
                title = Localizer.get().expert_settings_page_result_checker_retry_count_threshold,
                description = Localizer.get().expert_settings_page_result_checker_retry_count_threshold_desc,
                init = init,
                checked_changed = checked_changed,
            )
        )
