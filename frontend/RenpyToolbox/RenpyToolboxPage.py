"""
Ren'Py 工具箱页 - 统一的 Ren'Py 翻译与工具页面
参考 LinguaGacha 的卡片式设计，提供：一键翻译、文本提取、工具百宝箱
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QVBoxLayout
from qfluentwidgets import (
    FlowLayout,
    SingleDirectionScrollArea,
    FluentIcon,
    qconfig,
    TitleLabel,
)
from base.Base import Base
from base.LogManager import LogManager
from widget.ItemCard import ItemCard
from widget.ThemeHelper import mark_toolbox_widget, mark_toolbox_scroll_area
from frontend.RenpyToolbox.OneKeyTranslatePage import YiJianFanyiPage
from frontend.RenpyTranslationPage import RenpyTranslationPage
from frontend.RenpyToolbox.FormatterPage import FormatterPage
from frontend.RenpyToolbox.ErrorRepairPage import ErrorRepairPage
from frontend.RenpyToolbox.FontReplacePage import FontReplacePage
from frontend.RenpyToolbox.PackUnpackPage import PackUnpackPage
from frontend.RenpyToolbox.AndroidBuildPage import AndroidBuildPage
from frontend.RenpyToolbox.AddLanguageEntrancePage import AddLanguageEntrancePage
from frontend.RenpyToolbox.SetDefaultLanguagePage import SetDefaultLanguagePage
from frontend.RenpyToolbox.LocalGlossaryPage import LocalGlossaryPage
from frontend.RenpyToolbox.MaSuitePage import MaSuitePage
from frontend.RenpyToolbox.TextPreservePage import TextPreservePage
from frontend.RenpyToolbox.SourceTranslatePage import SourceTranslatePage
from frontend.Proofreading.ProofreadingPage import ProofreadingPage


class RenpyToolboxPage(Base, QWidget):
    """Ren'Py 工具箱主页面 - 卡片式导航"""

    def __init__(self, object_name: str, parent=None):
        # 先初始化 Base，才能使用事件等功能
        Base.__init__(self)
        QWidget.__init__(self, parent)
        self.setObjectName(object_name)
        mark_toolbox_widget(self)
        
        # 保存父窗口引用（用于页面跳转）
        self.window = parent

        # 初始化 UI
        self._init_ui()

    def _goto_widget(self, title: str, widget):
        """统一跳转逻辑：使用 navigate_to_page 避免添加到侧边栏。"""
        if widget is None:
            return
        # 优先使用 navigate_to_page（不添加到侧边栏）
        if hasattr(self.window, "navigate_to_page"):
            self.window.navigate_to_page(widget)
            return
        # 退回 stackedWidget
        if hasattr(self.window, "stackedWidget"):
            if widget not in [self.window.stackedWidget.widget(i) for i in range(self.window.stackedWidget.count())]:
                self.window.stackedWidget.addWidget(widget)
            self.window.stackedWidget.setCurrentWidget(widget)

    def _init_ui(self):
        """初始化界面"""
        # 主布局
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setSpacing(8)
        self.main_layout.setContentsMargins(24, 24, 24, 24)

        # 标题 - 使用 qfluentwidgets 组件以支持主题
        self.title = TitleLabel("🎮 Ren'Py 工具箱")
        self.main_layout.addWidget(self.title)

        # 创建滚动区域
        scroll_area = SingleDirectionScrollArea(orient=Qt.Orientation.Vertical)
        scroll_area.setWidgetResizable(True)
        scroll_area.enableTransparentBackground()
        mark_toolbox_scroll_area(scroll_area)

        # 滚动区域内容容器
        scroll_widget = QWidget()
        mark_toolbox_widget(scroll_widget, "toolboxScroll")
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(0, 0, 0, 0)

        # 流式布局容器
        flow_container = QWidget()
        mark_toolbox_widget(flow_container, "toolboxFlow")
        self.flow_layout = FlowLayout(flow_container, needAni=False)
        self.flow_layout.setSpacing(8)
        self.flow_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.addWidget(flow_container)
        scroll_layout.addStretch(1)

        scroll_area.setWidget(scroll_widget)
        self.main_layout.addWidget(scroll_area)

        # 添加工具卡片
        self._create_tool_cards()
        
        # 监听主题变化
        qconfig.themeChanged.connect(self._on_theme_changed)
    
    def _on_theme_changed(self):
        """主题切换时更新样式"""
        # 标题颜色会自动跟随主题，不需要特殊处理
        pass

    def _mark_toolbox_widget(self, widget: QWidget | None):
        """为子页面标记工具箱主题属性，确保背景和字体同步切换"""
        if widget is None:
            return
        mark_toolbox_widget(widget)

    def _create_tool_cards(self):
        """创建工具卡片，避免重复条目"""
        # 检查是否有未完成的翻译任务
        has_pending_translation = self._check_pending_translation()
        
        card_specs = []
        
        # 如果有未完成的翻译，优先显示"继续翻译"
        if has_pending_translation:
            card_specs.append(
                ("🔄 继续翻译", "检测到上次未完成的翻译任务，点击继续", self._open_continue_translation)
            )
        
        card_specs.extend([
            ("⭐ 一键翻译", "小白推荐：选择游戏目录 → 自动抽取 → 开始翻译", self._open_one_key_translate),
            ("📄 直接翻译RPY", "直接翻译 tl/*.rpy 文件（高级用户）", self._open_direct_rpy_translate),
            ("源码翻译", "直接翻译 game/*.rpy 源码，无需 tl 目录", self._open_source_translate),
            ("翻译抽取到TL", "高级：官方抽取、运行时抽取等", self._open_extract_to_tl),
            ("错误校对", "基于缓存进行校对、筛选与重译", self._open_proofreading_task),
            ("📚 本地词库", "管理术语表，统一专有名词翻译", self._open_local_glossary),
            ("🚫 禁翻表", "管理不需要翻译的文本（变量、代码等）", self._open_text_preserve),
            ("终极结构导出", "Excel & translate_names/others.rpy 输出", self._open_ma_suite),
            ("错误修复", "扫描并修复常见的脚本错误", self._open_error_repair),
            ("代码格式化", "格式化 .rpy 文件，保持代码整洁", self._open_formatter),
            ("字体注入", "一键注入预置字体包（tl/<lang>/base_box + tl/<lang>/fonts）", self._open_font_replace),
            ("解包/打包", "解包 RPA 文件或打包游戏资源", self._open_pack_unpack),
            ("安卓打包", "安装 SDK / 生成签名 / 构建 APK", self._open_android_build),
            ("添加语言入口", "向游戏添加语言切换功能", self._open_add_language_entrance),
            ("设置默认语言", "设置游戏启动时的默认语言", self._open_set_default_language),
        ])

        for title, description, handler in card_specs:
            self.flow_layout.addWidget(
                ItemCard(
                    parent=self,
                    title=title,
                    description=description,
                    clicked=handler,
                )
            )
    
    def _check_pending_translation(self) -> bool:
        """检查是否有未完成的翻译任务"""
        try:
            from module.Config import Config
            from pathlib import Path
            import os
            
            config = Config().load()
            output_folder = config.output_folder
            
            if not output_folder or not os.path.isdir(output_folder):
                return False
            
            # 检查缓存目录是否存在
            cache_dir = Path(output_folder) / "cache"
            items_file = cache_dir / "items.json"
            
            if items_file.exists():
                import json
                with open(items_file, "r", encoding="utf-8") as f:
                    items = json.load(f)
                    # 检查是否有未翻译的条目
                    untranslated = sum(1 for item in items if item.get("status", 0) == 0)
                    if untranslated > 0:
                        return True
            return False
        except Exception:
            return False

    # ===== 卡片点击事件 =====
    def _open_one_key_translate(self, card):
        """打开一键翻译页面（简化版 V2）"""
        if not hasattr(self.window, 'one_key_translate_page'):
            self.window.one_key_translate_page = YiJianFanyiPage("yi-jian-fanyi", self.window)
            self._mark_toolbox_widget(self.window.one_key_translate_page)
        
        if hasattr(self.window, "navigate_to_page"):
            self.window.navigate_to_page(self.window.one_key_translate_page)
        else:
            self._goto_widget("一键翻译", self.window.one_key_translate_page)
    
    def _open_continue_translation(self, card):
        """继续上次未完成的翻译"""
        self._open_translation_panel(card)
    
    def _open_direct_rpy_translate(self, card):
        """打开直接翻译RPY页面"""
        try:
            from frontend.RenpyToolbox.DirectRpyTranslatePage import DirectRpyTranslatePage
            if not hasattr(self.window, 'direct_rpy_translate_page'):
                self.window.direct_rpy_translate_page = DirectRpyTranslatePage("direct-rpy-translate", self.window)
                self._mark_toolbox_widget(self.window.direct_rpy_translate_page)
            self._goto_widget("直接翻译RPY", self.window.direct_rpy_translate_page)
        except Exception as e:
            from qfluentwidgets import InfoBar
            LogManager.get().error(f"打开直接翻译RPY页面失败: {e}")
            InfoBar.error("错误", f"打开页面失败: {e}", parent=self)

    def _open_source_translate(self, card):
        """打开源码翻译页面"""
        try:
            if not hasattr(self.window, 'source_translate_page'):
                self.window.source_translate_page = SourceTranslatePage("source-translate", self.window)
                self._mark_toolbox_widget(self.window.source_translate_page)
            self._goto_widget("源码翻译", self.window.source_translate_page)
        except Exception as e:
            from qfluentwidgets import InfoBar
            from base.LogManager import LogManager
            LogManager.get().error(f"打开源码翻译页面失败: {e}")
            InfoBar.error("错误", f"打开页面失败: {e}", parent=self)

    def _open_translation_panel(self, card):
        """打开主翻译页面，支持继续翻译"""
        try:
            if hasattr(self.window, 'translation_page'):
                page = self.window.translation_page
            else:
                from frontend.TranslationPage import TranslationPage
                page = TranslationPage("translation_page", self.window)
                self.window.translation_page = page
                self._mark_toolbox_widget(page)

            if hasattr(self.window, "navigate_to_page"):
                self.window.navigate_to_page(page)
            else:
                self._goto_widget("开始翻译", page)
        except Exception as e:
            from qfluentwidgets import InfoBar
            LogManager.get().error(f"打开翻译面板失败: {e}")
            InfoBar.error("错误", f"打开翻译面板失败: {e}", parent=self)

    def _open_local_glossary(self, card):
        """打开本地词库页面"""
        if not hasattr(self.window, 'local_glossary_page'):
            self.window.local_glossary_page = LocalGlossaryPage("local-glossary", self.window)
            self._mark_toolbox_widget(self.window.local_glossary_page)
        self._goto_widget("本地词库", self.window.local_glossary_page)

    def _open_text_preserve(self, card):
        """打开禁翻表页面"""
        if not hasattr(self.window, 'text_preserve_page'):
            self.window.text_preserve_page = TextPreservePage("text-preserve", self.window)
            self._mark_toolbox_widget(self.window.text_preserve_page)
        self._goto_widget("禁翻表", self.window.text_preserve_page)

    def _open_proofreading_task(self, card):
        """打开校对任务页面"""
        if not hasattr(self.window, 'proofreading_page'):
            self.window.proofreading_page = ProofreadingPage("proofreading_page", self.window)
            self._mark_toolbox_widget(self.window.proofreading_page)
        self._goto_widget("校对任务", self.window.proofreading_page)

    def _open_ma_suite(self, card):
        """打开翻译套件页面"""
        if not hasattr(self.window, 'ma_suite_page'):
            self.window.ma_suite_page = MaSuitePage("ma-suite", self.window)
            self._mark_toolbox_widget(self.window.ma_suite_page)
        self._goto_widget("翻译套件", self.window.ma_suite_page)

    def _open_extract_to_tl(self, card):
        """打开翻译抽取到TL页面"""
        if not hasattr(self.window, 'renpy_translation_page'):
            self.window.renpy_translation_page = RenpyTranslationPage(self.window)
            self._mark_toolbox_widget(self.window.renpy_translation_page)
        self._goto_widget("翻译抽取到TL", self.window.renpy_translation_page)

    def _open_formatter(self, card):
        """打开代码格式化页面"""
        if not hasattr(self.window, 'formatter_page'):
            self.window.formatter_page = FormatterPage("formatter", self.window)
            self._mark_toolbox_widget(self.window.formatter_page)
        self._goto_widget("代码格式化", self.window.formatter_page)

    def _open_error_repair(self, card):
        """打开错误修复页面"""
        if not hasattr(self.window, 'error_repair_page'):
            self.window.error_repair_page = ErrorRepairPage("error-repair", self.window)
            self._mark_toolbox_widget(self.window.error_repair_page)
        self._goto_widget("错误修复", self.window.error_repair_page)

    def _open_font_replace(self, card):
        """打开字体替换页面"""
        if not hasattr(self.window, 'font_replace_page'):
            self.window.font_replace_page = FontReplacePage("font-replace", self.window)
            self._mark_toolbox_widget(self.window.font_replace_page)
        self._goto_widget("字体替换", self.window.font_replace_page)

    def _open_pack_unpack(self, card):
        """打开解包/打包页面"""
        if not hasattr(self.window, 'pack_unpack_page'):
            self.window.pack_unpack_page = PackUnpackPage("pack-unpack", self.window)
        self._goto_widget("解包打包", self.window.pack_unpack_page)

    def _open_android_build(self, card):
        """打开安卓打包页面"""
        if not hasattr(self.window, 'android_build_page'):
            self.window.android_build_page = AndroidBuildPage("android-build", self.window)
            self._mark_toolbox_widget(self.window.android_build_page)
        self._goto_widget("安卓打包", self.window.android_build_page)

    def _open_add_language_entrance(self, card):
        """打开添加语言入口页面"""
        if not hasattr(self.window, 'add_language_page'):
            self.window.add_language_page = AddLanguageEntrancePage("add-language", self.window)
        self._goto_widget("添加语言入口", self.window.add_language_page)

    def _open_set_default_language(self, card):
        """打开设置默认语言页面"""
        if not hasattr(self.window, 'set_default_language_page'):
            self.window.set_default_language_page = SetDefaultLanguagePage("set-default-language", self.window)
        self._goto_widget("设置默认语言", self.window.set_default_language_page)
