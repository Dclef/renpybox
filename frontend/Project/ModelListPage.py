from functools import partial

import openai
import anthropic
from google import genai
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget
from PyQt5.QtWidgets import QLayout
from PyQt5.QtWidgets import QVBoxLayout
from qfluentwidgets import CaptionLabel
from qfluentwidgets import FluentWindow
from qfluentwidgets import MessageBoxBase
from qfluentwidgets import SearchLineEdit
from qfluentwidgets import SingleDirectionScrollArea

from base.Base import Base
from module.Secret.SecretStore import SecretStore
from module.Config import Config
from module.Localizer.Localizer import Localizer
from widget.FlowCard import FlowCard
from widget.QuietPillButton import QuietPillButton

class ModelListPage(MessageBoxBase, Base):

    def __init__(self, id: int, window: FluentWindow) -> None:
        super().__init__(window)

        # 初始化
        self.id: int = id
        self.filter: str = ""
        self.models: list[str] = None
        self.model_buttons: list[QuietPillButton] = []
        self.no_match_label: CaptionLabel | None = None

        # 载入并保存默认配置
        config = Config().load().save()

        # 设置框体
        self.widget.setFixedSize(960, 720)
        self.yesButton.setText(Localizer.get().close)
        self.cancelButton.hide()

        # 设置主布局
        self.viewLayout.setContentsMargins(0, 0, 0, 0)

        # 设置滚动器
        self.scroller = SingleDirectionScrollArea(self, orient = Qt.Orientation.Vertical)
        self.scroller.setWidgetResizable(True)
        self.scroller.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.viewLayout.addWidget(self.scroller)

        # 设置滚动控件
        self.vbox_parent = QWidget(self)
        self.vbox_parent.setStyleSheet("QWidget { background: transparent; }")
        self.vbox = QVBoxLayout(self.vbox_parent)
        self.vbox.setSpacing(8)
        self.vbox.setContentsMargins(24, 24, 24, 24) # 左、上、右、下
        self.scroller.setWidget(self.vbox_parent)

        # 添加控件
        self.add_widget(self.vbox, config, window)

        # 填充
        self.vbox.addStretch(1)

    # 点击事件
    def clicked(self, widget: QuietPillButton) -> None:
        config = Config().load()
        platform = config.get_platform(self.id)
        platform["model"] = widget.text().strip()
        config.set_platform(platform)
        config.save()

        # 关闭窗口
        self.close()

    # 过滤输入变化事件
    def filter_text_changed(self, text: str) -> None:
        self.filter = text.strip()
        self._apply_filter()

    # 获取模型
    def get_models(self, api_url: str, api_key: str, api_format: Base.APIFormat) -> list[str]:
        result: list[str] = []

        try:
            if api_format == Base.APIFormat.GOOGLE:
                client = genai.Client(
                    api_key = api_key,
                )
                result = [model.name for model in client.models.list()]
            elif api_format == Base.APIFormat.ANTHROPIC:
                client = anthropic.Anthropic(
                    api_key = api_key,
                    base_url = api_url,
                )
                models = client.models.list()
                items = getattr(models, "data", models)
                result = [getattr(model, "id", "") for model in items if getattr(model, "id", "")]
            elif api_format == Base.APIFormat.DEEPL:
                result = ["deepl-v2"]
            elif api_format == Base.APIFormat.DEEPLX:
                result = ["deeplx-translate"]
            else:
                client = openai.OpenAI(
                    base_url = api_url,
                    api_key = api_key,
                )
                models = client.models.list()
                items = getattr(models, "data", models)
                result = [getattr(model, "id", "") for model in items if getattr(model, "id", "")]
        except Exception as e:
            self.debug(Localizer.get().model_list_page_fail, e)
            self.emit(Base.Event.APP_TOAST_SHOW, {
                "type": Base.ToastType.WARNING,
                "message": Localizer.get().model_list_page_fail,
            })
            return []

        return sorted({m for m in result if isinstance(m, str) and m.strip()})

    # 更新子控件
    def update_sub_widgets(self, widget: FlowCard) -> None:
        if self.models is None:
            platform: dict = Config().load().get_platform(self.id)
            self.models = self.get_models(
                platform.get('api_url'),
                SecretStore.get().resolve_keys(platform)[0],
                platform.get('api_format'),
            )

        if not self.model_buttons:
            widget.flow_layout.isTight = True
            for model in self.models:
                pilled_button = QuietPillButton(model)
                pilled_button.setFixedWidth(432)
                pilled_button.clicked.connect(partial(self.clicked, pilled_button))
                widget.add_widget(pilled_button)
                self.model_buttons.append(pilled_button)

            self.no_match_label = CaptionLabel(Localizer.get().alert_no_data, widget.flow_container)
            widget.add_widget(self.no_match_label)

        self._apply_filter()

    def _apply_filter(self) -> None:
        """只隐藏不匹配项，保留按钮对象和当前选中状态。"""
        keyword = self.filter.casefold()
        matched = 0
        for button in self.model_buttons:
            visible = keyword in button.text().casefold()
            button.setVisible(visible)
            matched += int(visible)
        if self.no_match_label is not None:
            self.no_match_label.setVisible(matched == 0)
        if getattr(self, "flow_card", None) is not None:
            self.flow_card.flow_layout.invalidate()
            self.flow_card.flow_container.updateGeometry()

    # 模型名称
    def add_widget(self, parent: QLayout, config: Config, window: FluentWindow) -> None:
        def init(widget: FlowCard) -> None:
            self.flow_card = widget
            self.filter_edit = SearchLineEdit(widget)
            self.filter_edit.setPlaceholderText(Localizer.get().filter)
            self.filter_edit.setFixedWidth(280)
            self.filter_edit.textChanged.connect(self.filter_text_changed)
            widget.add_widget_to_head(self.filter_edit)

            # 更新子控件
            self.update_sub_widgets(widget)

        self.flow_card = FlowCard(
            parent = self,
            title = Localizer.get().model_list_page_title,
            description = Localizer.get().model_list_page_content,
            init = init,
        )
        parent.addWidget(self.flow_card)
