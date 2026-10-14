import copy

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    Action,
    CaptionLabel,
    FluentIcon,
    FluentWindow,
    RoundMenu,
    SingleDirectionScrollArea,
    StrongBodyLabel,
    TitleLabel,
)

from base.Base import Base
from frontend.Project.ArgsEditPage import ArgsEditPage
from frontend.Project.PlatformEditPage import PlatformEditPage
from frontend.Project.PlatformGroupCard import PlatformGroupCard
from frontend.Project.PlatformHeaderCard import PlatformHeaderCard
from frontend.Project.PlatformItemCard import PlatformItemCard
from module.Config import Config
from module.Localizer.Localizer import Localizer
from module.Project.PlatformDefaults import (
    load_default_platforms,
    normalize_platforms,
)
from module.Project.PlatformNaming import (
    deduplicate_platform_name as _deduplicate_platform_name,
)
from module.Secret.SecretStore import (
    CREDENTIAL_ID_FIELD,
    LEGACY_CREDENTIAL_ID_FIELD,
    SecretStore,
)
from widget.ThemeHelper import mark_app_page


PLATFORM_GROUPS = ("local", "machine", "online", "custom")


def infer_group(platform: dict) -> str:
    """根据旧接口配置推断展示分组，不修改原配置。"""
    api_format = str(platform.get("api_format", ""))

    if api_format in Base.MACHINE_API_FORMATS:
        return "machine"

    if api_format == Base.APIFormat.SAKURALLM:
        return "local"

    api_url = str(platform.get("api_url", "")).lower()
    if any(host in api_url for host in ("127.0.0.1", "localhost", "0.0.0.0", "[::1]")):
        return "local"

    name = str(platform.get("name", "")).strip().lower()
    if name.startswith("自定义") or name.startswith("custom"):
        return "custom"

    return "online"


def resolve_group(platform: dict) -> str:
    group = platform.get("group")
    return group if group in PLATFORM_GROUPS else infer_group(platform)


def deduplicate_platform_name(name: str, platforms: list[dict]) -> str:
    """按精确名称匹配，为重复接口名追加递增数字后缀。

    实现在 ``module/Project/PlatformNaming.py``：Electron 端新增接口
    （``POST /api/platforms``）必须用同一规则，避免两端行为漂移。
    """
    return _deduplicate_platform_name(name, platforms)


class PlatformPage(QWidget, Base):

    def __init__(self, text: str, window: FluentWindow) -> None:
        super().__init__(window)
        self.setObjectName(text.replace(" ", "-"))
        mark_app_page(self)
        self.window = window
        self.item_cards: dict[int, PlatformItemCard] = {}
        self.item_groups: dict[int, str] = {}

        # 载入配置
        config = Config().load()
        if config.platforms == None:
            config.platforms = self.load_default_platforms()
            # 首次加载默认平台时，顺便做一轮字段归一化，避免旧布尔字段残留。
            self.ensure_default_platforms(config.platforms)
            config.save(strict = True)
        elif self.ensure_default_platforms(config.platforms):
            config.save(strict = True)

        # 设置主容器
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(24, 24, 24, 24)  # 左、上、右、下

        header = QWidget(self)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 4)
        header_layout.setSpacing(2)
        title = TitleLabel(Localizer.get().app_platform_page, header)
        title_font = title.font()
        title_font.setPixelSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        header_layout.addWidget(title)
        header_layout.addWidget(
            CaptionLabel(Localizer.get().platform_page_header_description, header)
        )
        self.root.addWidget(header)

        self.content = QWidget(self)
        self.vbox = QVBoxLayout(self.content)
        self.vbox.setSpacing(8)
        self.vbox.setContentsMargins(0, 0, 0, 0)

        self.scroll_area = SingleDirectionScrollArea(
            self,
            orient=Qt.Orientation.Vertical,
        )
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.content)
        self.scroll_area.enableTransparentBackground()
        self.root.addWidget(self.scroll_area)

        # 添加控件
        self.add_widget(self.vbox)

        # 填充
        self.vbox.addStretch(1)

        # 完成事件
        self.subscribe(Base.Event.PLATFORM_TEST_DONE, self.platform_test_done)

    # 执行接口测试
    def platform_test_start(self, id: int) -> None:
        self.emit(Base.Event.PLATFORM_TEST_START, {
            "id": id,
        })

    # 接口测试完成
    def platform_test_done(self, event: str, data: dict) -> None:
        self.emit(Base.Event.APP_TOAST_SHOW, {
            "type": Base.ToastType.SUCCESS if data.get("result", True) else Base.ToastType.ERROR,
            "message": data.get("result_msg", ""),
        })

    # 加载默认平台数据
    def load_default_platforms(self) -> list[dict]:
        """默认接口模板；实现收口在 ``module/Project/PlatformDefaults.py``。

        Electron 端启动播种与「从旧版导入」使用同一份模板与归一化规则，
        两端行为不能漂移。
        """
        return load_default_platforms()

    # 补全默认平台（用于旧配置升级）
    def ensure_default_platforms(self, platforms: list[dict]) -> bool:
        return normalize_platforms(platforms, defaults = self.load_default_platforms())

    # 添加接口
    def add_platform(self, item: dict) -> None:
        config = Config().load()

        item = copy.deepcopy(item)
        item["id"] = len(config.platforms)
        item.pop(CREDENTIAL_ID_FIELD, None)
        item.pop(LEGACY_CREDENTIAL_ID_FIELD, None)
        SecretStore.ensure_platform_identity(item, preserve_legacy = False)
        item["name"] = deduplicate_platform_name(
            str(item.get("name", "")),
            config.platforms,
        )
        config.platforms.append(item)
        config.save(strict = True)

        self.rebuild_all()

    # 删除接口
    def delete_platform(self, id: int) -> None:
        config = Config().load()
        original_platforms = copy.deepcopy(config.platforms)
        original_activate_platform = config.activate_platform
        original_agent_platform = config.agent_platform
        removed_platform = None

        for platform in config.platforms:
            if platform.get("id") == id:
                removed_platform = platform
                break

        if removed_platform is None:
            return

        config.platforms.remove(removed_platform)

        if not config.platforms:
            config.activate_platform = 0
        elif config.activate_platform == id:
            config.activate_platform = 0
        elif config.activate_platform > id:
            config.activate_platform -= 1

        if config.agent_platform == id:
            config.agent_platform = -1
        elif config.agent_platform > id:
            config.agent_platform -= 1

        # 修正条目 id
        for i, platform in enumerate(sorted(config.platforms, key=lambda x: x.get("id"))):
            platform["id"] = i

        # 先严格持久化平台删除，再清理其稳定身份凭据。即使凭据库清理失败，
        # 也只会留下 UUID 不可达的孤儿项，不会让磁盘中仍存在的平台丢失 Key。
        try:
            config.save(strict = True)
        except Exception:
            config.platforms = original_platforms
            config.activate_platform = original_activate_platform
            config.agent_platform = original_agent_platform
            raise
        if not SecretStore.get().clear_keys(removed_platform):
            self.emit(Base.Event.APP_TOAST_SHOW, {
                "type": Base.ToastType.ERROR,
                "message": Localizer.get().platform_edit_page_api_key_clear_failed,
            })
        self.rebuild_all()

    # 激活接口
    def activate_platform(self, id: int) -> None:
        config = Config().load()
        config.activate_platform = id
        config.save()

        self.refresh_active()

    # 显示编辑接口对话框
    def show_api_edit_page(self, id: int) -> None:
        PlatformEditPage(id, self.window).exec()

        self.refresh_item(id)
        self.refresh_active()

    # 显示编辑参数对话框
    def show_args_edit_page(self, id: int) -> None:
        ArgsEditPage(id, self.window).exec()

    def rebuild_all(self) -> None:
        """在增删接口后重建四个分组中的条目卡。"""
        config = Config().load()
        platforms = sorted(config.platforms, key=lambda x: x.get("id", 0))

        for group_card in self.group_cards.values():
            group_card.take_all_widgets()
        self.item_cards.clear()
        self.item_groups.clear()

        for platform in platforms:
            platform_id = int(platform.get("id", 0))
            group = resolve_group(platform)
            item_card = PlatformItemCard(platform, self.group_cards[group])
            item_card.activate_requested.connect(self.activate_platform)
            item_card.edit_requested.connect(self.show_api_edit_page)
            item_card.args_requested.connect(self.show_args_edit_page)
            item_card.test_requested.connect(self.platform_test_start)
            item_card.delete_requested.connect(self.delete_platform)
            self.group_cards[group].add_widget(item_card)
            self.item_cards[platform_id] = item_card
            self.item_groups[platform_id] = group

        for group_card in self.group_cards.values():
            group_card.set_count_visible()
        self.empty_state.setVisible(not platforms)
        self.refresh_active(config)

    def refresh_active(self, config: Config | None = None) -> None:
        """仅刷新条目激活态与顶部说明。"""
        config = config or Config().load()
        active_platform = config.get_platform(config.activate_platform)

        for platform_id, item_card in self.item_cards.items():
            item_card.set_active(
                active_platform is not None and platform_id == config.activate_platform
            )

        active_name = (
            str(active_platform.get("name", ""))
            if active_platform is not None
            else None
        )
        self.header_card.set_active_name(active_name)

    def refresh_item(self, id: int) -> None:
        """编辑后原位更新单个条目卡。"""
        config = Config().load()
        platform = config.get_platform(id)
        item_card = self.item_cards.get(id)
        if platform is None or item_card is None:
            return

        group = resolve_group(platform)
        old_group = self.item_groups[id]
        if group != old_group:
            self.group_cards[old_group].flow_layout.removeWidget(item_card)
            self.group_cards[group].add_widget(item_card)
            self.item_groups[id] = group
            self.group_cards[old_group].set_count_visible()
            self.group_cards[group].set_count_visible()

        item_card.update_info(platform)

    # 添加页面控件
    def add_widget(self, parent: QLayout) -> None:
        localizer = Localizer.get()

        self.header_card = PlatformHeaderCard(self)
        parent.addWidget(self.header_card)

        add_menu = RoundMenu("", self.header_card.add_button)
        platforms = self.load_default_platforms()
        for i, item in enumerate(platforms):
            add_menu.addAction(Action(
                str(item.get("name", "")),
                triggered=lambda _checked=False, preset=item: self.add_platform(preset),
            ))
            if i < len(platforms) - 1:
                add_menu.addSeparator()
        self.header_card.add_button.setMenu(add_menu)

        self.group_cards = {
            "local": PlatformGroupCard(
                self,
                localizer.platform_page_group_local_title,
                localizer.platform_page_group_local_content,
                FluentIcon.CONNECT,
            ),
            "machine": PlatformGroupCard(
                self,
                localizer.platform_page_group_machine_title,
                localizer.platform_page_group_machine_content,
                FluentIcon.LANGUAGE,
            ),
            "online": PlatformGroupCard(
                self,
                localizer.platform_page_group_online_title,
                localizer.platform_page_group_online_content,
                FluentIcon.CLOUD,
            ),
            "custom": PlatformGroupCard(
                self,
                localizer.platform_page_group_custom_title,
                localizer.platform_page_group_custom_content,
                FluentIcon.ASTERISK,
            ),
        }
        for group_card in self.group_cards.values():
            parent.addWidget(group_card)

        self.empty_state = QWidget(self)
        empty_layout = QVBoxLayout(self.empty_state)
        empty_layout.setContentsMargins(0, 32, 0, 32)
        empty_layout.setSpacing(8)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        empty_title = StrongBodyLabel(localizer.platform_page_empty_title, self.empty_state)
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_title)

        empty_content = CaptionLabel(localizer.platform_page_empty_content, self.empty_state)
        empty_content.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_content.setTextColor(QColor(96, 96, 96), QColor(160, 160, 160))
        empty_layout.addWidget(empty_content)
        parent.addWidget(self.empty_state)

        self.rebuild_all()
