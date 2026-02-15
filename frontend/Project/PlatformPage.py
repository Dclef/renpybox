import os
import json
from functools import partial

from PyQt5.QtWidgets import QWidget
from PyQt5.QtWidgets import QLayout
from PyQt5.QtWidgets import QVBoxLayout
from qfluentwidgets import Action
from qfluentwidgets import RoundMenu
from qfluentwidgets import FluentIcon
from qfluentwidgets import FluentWindow
from qfluentwidgets import DropDownPushButton
from qfluentwidgets import PrimaryDropDownPushButton

from base.Base import Base
from module.Config import Config
from module.Localizer.Localizer import Localizer
from widget.FlowCard import FlowCard
from frontend.Project.PlatformEditPage import PlatformEditPage
from frontend.Project.ArgsEditPage import ArgsEditPage
from base.PathHelper import get_resource_path

class PlatformPage(QWidget, Base):

    def __init__(self, text: str, window: FluentWindow) -> None:
        super().__init__(window)
        self.setObjectName(text.replace(" ", "-"))

        # 载入配置
        config = Config().load()
        if config.platforms == None:
            config.platforms = self.load_default_platforms()
            config.save()
        elif self.ensure_default_platforms(config.platforms):
            config.save()

        # 设置主容器
        self.vbox = QVBoxLayout(self)
        self.vbox.setSpacing(8)
        self.vbox.setContentsMargins(24, 24, 24, 24) # 左、上、右、下

        # 添加控件
        self.add_widget(self.vbox, config, window)

        # 填充
        self.vbox.addStretch(1)

        # 完成事件
        self.subscribe(Base.Event.PLATFORM_TEST_DONE, self.platform_test_done)

    # 执行接口测试
    def platform_test_start(self, id: int, widget: FlowCard, window: FluentWindow) -> None:
        self.emit(Base.Event.PLATFORM_TEST_START, {
            "id": id,
        })

    # 接口测试完成
    def platform_test_done(self, event: str, data: dict) -> None:
        self.emit(Base.Event.APP_TOAST_SHOW, {
            "type": Base.ToastType.SUCCESS if data.get("result", True) else Base.ToastType.ERROR,
            "message": data.get("result_msg", "")
        })

    # 加载默认平台数据
    def load_default_platforms(self) -> list[dict]:
        platforms:list[dict[str, str | list[str]]] = []

        platforms_path = get_resource_path("resource", "platforms", Localizer.get_app_language().lower())

        if not os.path.exists(platforms_path):
            print(f"Warning: Platforms path not found: {platforms_path}")
            return []

        for path in [file.path for file in os.scandir(platforms_path) if file.is_file() and file.name.endswith(".json")]:
            with open(path, "r", encoding = "utf-8-sig") as reader:
                platforms.append(json.load(reader))

        # 重设 id 以避免 id 不连续的问题
        for i, platform in enumerate(sorted(platforms, key = lambda x: x.get('id'))):
            platform["id"] = i

        return sorted(platforms, key = lambda x: x.get('id'))

    # 补全默认平台（用于旧配置升级）
    def ensure_default_platforms(self, platforms: list[dict]) -> bool:
        if not isinstance(platforms, list):
            return False

        changed = False
        defaults = self.load_default_platforms()
        existing_formats = {str(item.get("api_format", "")) for item in platforms}

        # 统一旧命名（Deel API / DeepL API）为 DeepL
        for item in platforms:
            if str(item.get("api_format", "")) != str(Base.APIFormat.DEEPL):
                continue
            name = str(item.get("name", "")).strip()
            if name in ("Deel API", "DeepL API"):
                item["name"] = "DeepL"
                changed = True

        # 旧配置中没有 DeepL / DeepLX 时，自动补齐到默认列表
        for fmt in (Base.APIFormat.DEEPL, Base.APIFormat.DEEPLX):
            if str(fmt) in existing_formats:
                continue
            template = next((item for item in defaults if str(item.get("api_format", "")) == str(fmt)), None)
            if template is None:
                continue

            cloned = {
                k: (v.copy() if isinstance(v, list) else v)
                for k, v in template.items()
            }
            platforms.append(cloned)
            existing_formats.add(str(fmt))
            changed = True

        if not changed:
            return False

        # 非自定义接口在前，自定义接口在后；并重新连续编号 id
        def is_custom(item: dict) -> bool:
            name = str(item.get("name", "")).strip().lower()
            return name.startswith("自定义") or name.startswith("custom")

        platforms.sort(key = lambda x: (1 if is_custom(x) else 0, x.get("id", 0)))
        for i, item in enumerate(platforms):
            item["id"] = i

        return True

    # 添加接口
    def add_platform(self, item: dict, widget: FlowCard, window: FluentWindow) -> None:
        # 载入配置
        config = Config().load()

        # 添加指定条目
        item["id"] = len(config.platforms)
        config.platforms.append(item)

        # 保存配置文件
        config.save()

        # 更新控件
        self.update_custom_platform_widgets(widget, window)

    # 删除接口
    def delete_platform(self, id: int, widget: FlowCard, window: FluentWindow) -> None:
        # 载入配置
        config = Config().load()

        # 删除指定条目
        for i, platform in enumerate(config.platforms):
            if platform.get('id') == id:
                del config.platforms[i]

                # 修正激活接口的ID
                if config.activate_platform == i:
                    config.activate_platform = 0
                elif config.activate_platform > i:
                    config.activate_platform = config.activate_platform - 1
                break

        # 修正条目id
        for i, platform in enumerate(sorted(config.platforms, key = lambda x: x.get('id'))):
            config.platforms[i]["id"] = i

        # 保存配置文件
        config.save()

        # 更新控件
        self.update_custom_platform_widgets(widget, window)

    # 激活接口
    def activate_platform(self, id: int, widget: FlowCard, window: FluentWindow) -> None:
        config = Config().load()
        config.activate_platform = id
        config.save()

        # 更新控件
        self.update_custom_platform_widgets(widget, window)

    # 显示编辑接口对话框
    def show_api_edit_page(self, id: int, widget: FlowCard, window: FluentWindow) -> None:
        PlatformEditPage(id, window).exec()

        # 激活接口
        config = Config().load()
        config.activate_platform = id
        config.save()

        # 更新控件
        self.update_custom_platform_widgets(widget, window)

    # 显示编辑参数对话框
    def show_args_edit_page(self, id: int, widget: FlowCard, window: FluentWindow) -> None:
        ArgsEditPage(id, window).exec()

    # 更新自定义平台控件
    def update_custom_platform_widgets(self, widget: FlowCard, window: FluentWindow) -> None:
        config = Config().load()
        platforms = sorted(config.platforms, key = lambda x: x.get("id", 0))

        widget.take_all_widgets()
        for item in platforms:
            if item.get("id", 0) != config.activate_platform:
                drop_down_push_button = DropDownPushButton(item.get('name'))
            else:
                drop_down_push_button = PrimaryDropDownPushButton(item.get('name'))
            drop_down_push_button.setFixedWidth(192)
            drop_down_push_button.setContentsMargins(4, 0, 4, 0) # 左、上、右、下
            widget.add_widget(drop_down_push_button)

            menu = RoundMenu("", drop_down_push_button)
            menu.addAction(
                Action(
                    FluentIcon.EXPRESSIVE_INPUT_ENTRY,
                    Localizer.get().platform_page_api_activate,
                    triggered = partial(self.activate_platform, item.get("id", 0), widget, window),
                )
            )
            menu.addSeparator()
            menu.addAction(
                Action(
                    FluentIcon.EDIT,
                    Localizer.get().platform_page_api_edit,
                    triggered = partial(self.show_api_edit_page, item.get("id", 0), widget, window),
                )
            )
            menu.addSeparator()
            menu.addAction(
                Action(
                    FluentIcon.DEVELOPER_TOOLS,
                    Localizer.get().platform_page_api_args,
                    triggered = partial(self.show_args_edit_page, item.get("id", 0), widget, window),
                )
            )
            menu.addSeparator()
            menu.addAction(
                Action(
                    FluentIcon.SEND,
                    Localizer.get().platform_page_api_test,
                    triggered = partial(self.platform_test_start, item.get("id", 0), widget, window),
                )
            )
            menu.addSeparator()
            menu.addAction(
                Action(
                    FluentIcon.DELETE,
                    Localizer.get().platform_page_api_delete,
                    triggered = partial(self.delete_platform, item.get("id", 0), widget, window),
                )
            )
            drop_down_push_button.setMenu(menu)

    # 添加控件
    def add_widget(self, parent: QLayout, config: Config, window: FluentWindow) -> None:

        def init(widget: FlowCard) -> None:
            # 添加新增按钮
            add_button = DropDownPushButton(Localizer.get().add)
            add_button.setIcon(FluentIcon.ADD_TO)
            add_button.setContentsMargins(4, 0, 4, 0)
            widget.add_widget_to_head(add_button)

            menu = RoundMenu("", add_button)
            platforms = self.load_default_platforms()
            for i, item in enumerate(platforms):
                menu.addAction(Action(item.get('name'), triggered = partial(self.add_platform, item, widget, window)))
                menu.addSeparator() if i < len(platforms) - 1 else None
            add_button.setMenu(menu)

            # 更新控件
            self.update_custom_platform_widgets(widget, window)

        self.flow_card = FlowCard(
            parent = self,
            title = Localizer.get().platform_page_widget_add_title,
            description = Localizer.get().platform_page_widget_add_content,
            init = init,
        )
        parent.addWidget(self.flow_card)
