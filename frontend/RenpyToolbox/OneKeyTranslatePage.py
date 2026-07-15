"""
YiJianFanyiPage - 一键翻译向导页面
向导式分步骤流程：每次只显示一个进度页面，完成后自动进入下一步
"""

import os
import shutil
import time
from pathlib import Path
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFileDialog,
    QStackedWidget,
    QSizePolicy,
)
from qfluentwidgets import (
    FlowLayout,
    SingleDirectionScrollArea,
    CardWidget,
    SubtitleLabel,
    CaptionLabel,
    BodyLabel,
    PrimaryPushButton,
    PushButton,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    ProgressBar,
    ProgressRing,
    TitleLabel,
    ComboBox,
    LineEdit,
    CheckBox,
    qconfig,
    TransparentToolButton,
    isDarkTheme,
    StrongBodyLabel,
)

from base.Base import Base
from base.LogManager import LogManager
from base.PathHelper import get_resource_path
from widget.Separator import Separator
from widget.ItemCard import ItemCard
from widget.ThemeHelper import mark_toolbox_widget, mark_toolbox_scroll_area
from module.Extract.PatchGenerator import generate_patch
from module.Extract.UnifiedExtractor import UnifiedExtractor
from module.Renpy import renpy_extract as rx
from frontend.TranslationPage import TranslationPage


def configure_incremental_translation_paths(config, game_dir, tl_name, incremental_dir):
    """Point translation at the extracted delta while preserving the main TL target."""
    project_root = Path(game_dir)
    main_tl_dir = project_root / "game" / "tl" / tl_name
    delta_dir = Path(incremental_dir)
    output_dir = project_root / "RenpyBox_Translation" / f"{tl_name}_new"
    config.input_folder = str(delta_dir)
    config.output_folder = str(output_dir)
    return main_tl_dir, output_dir


def resolve_translation_apply_paths(config, incremental_output=None, incremental_target=None):
    """仅在增量输出有效时使用增量目标，避免复用页面时串用旧目录。"""
    if incremental_output:
        return Path(incremental_output), Path(incremental_target)
    return Path(config.output_folder), Path(config.input_folder)

# Worker Thread for Extraction
class ExtractionWorker(QThread):
    progress = pyqtSignal(str, int) # message, percent
    finished = pyqtSignal(bool, str, object) # success, message, result (ExtractionResult)
    
    def __init__(self, unified_extractor, game_dir, tl_name, exe_path, incremental=False, output_to_separate_folder=True):
        super().__init__()
        self.unified_extractor = unified_extractor
        self.game_dir = game_dir
        self.tl_name = tl_name
        self.exe_path = exe_path
        self.incremental = incremental  # 增量模式：保留已有翻译
        self.output_to_separate_folder = output_to_separate_folder  # 增量输出到单独文件夹
        
    def run(self):
        try:
            # 设置进度回调
            self.unified_extractor.set_progress_callback(
                lambda msg, pct: self.progress.emit(msg, pct)
            )
            
            if self.incremental:
                # 增量模式：使用统一提取器的增量抽取
                result = self.unified_extractor.extract_incremental(
                    self.game_dir,
                    self.tl_name,
                    self.exe_path,
                    use_official=bool(self.exe_path),
                    output_to_separate_folder=self.output_to_separate_folder
                )
            else:
                # 常规模式：使用统一提取器的完整抽取
                result = self.unified_extractor.extract_regular(
                    self.game_dir,
                    self.tl_name,
                    self.exe_path,
                    use_official=bool(self.exe_path)
                )
            
            self.finished.emit(result.success, result.message, result)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.finished.emit(False, str(e), None)
        finally:
            self.unified_extractor.set_progress_callback(None)

class YiJianFanyiPage(Base, QWidget):
    """一键翻译页面 - 向导式分步骤流程"""
    
    def __init__(self, object_name: str = "yi-jian-fanyi", parent=None):
        Base.__init__(self)
        QWidget.__init__(self, parent)
        self.setObjectName(object_name)
        mark_toolbox_widget(self)
        
        self.window = parent
        self.game_path = ""
        self.game_dir = ""
        self.renpy_version = ""
        self.current_step = 1
        self.unified_extractor = UnifiedExtractor()
        self.extraction_worker = None
        self.has_old_translation = False  # 是否检测到旧翻译
        self.incremental_mode = False     # 是否使用增量抽取
        self._ner_model = None            # 懒加载的 NER 模型
        self._ner_model_loaded = False
        # 一键翻译结束后，按需串起“自动补全漏翻”流程
        self._onekey_translation_started = False
        self._auto_hook_pending = False
        self._auto_hook_running = False
        self._incremental_dir = None
        self._incremental_output_dir = None
        self._apply_target_dir = None
        
        self._init_ui()
        self.subscribe(Base.Event.TRANSLATION_DONE, self._on_translation_done)
        self.subscribe(Base.Event.TRANSLATION_STOP, self._on_translation_stop)
    
    def _init_ui(self):
        """初始化界面"""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setSpacing(0)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        
        # 使用 QStackedWidget 切换不同进度页面
        self.stacked = QStackedWidget()
        self.main_layout.addWidget(self.stacked)
        
        # 创建各个进度页面
        self._create_step1_page()  # 前期设置
        self._create_step2_page()  # 提取进度
        self._create_step3_page()  # 术语表
        self._create_step4_page()  # 开始翻译
        self._create_step5_page()  # 后续处理
        
        # 显示第一步
        self.stacked.setCurrentIndex(0)
    
    def _create_page_container(self, title: str, step: int) -> tuple:
        """创建页面容器，返回 (page, content_layout)"""
        page = QWidget()
        mark_toolbox_widget(page)
        page_layout = QVBoxLayout(page)
        page_layout.setSpacing(12)
        page_layout.setContentsMargins(24, 24, 24, 24)
        
        # 顶部：标题 + 退出按钮
        header = QWidget()
        header.setStyleSheet("background: transparent;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        # 返回按钮
        back_btn = TransparentToolButton(FluentIcon.RETURN)
        if step == 1:
            back_btn.setToolTip("返回工具箱")
            back_btn.clicked.connect(self._exit_wizard)
        else:
            back_btn.setToolTip("返回上一步")
            # 使用 lambda 捕获当前 step 值
            back_btn.clicked.connect(lambda checked, s=step: self._go_previous_step(s))
        header_layout.addWidget(back_btn)
        
        title_label = TitleLabel(f"步骤 {step}/5：{title}")
        header_layout.addWidget(title_label)
        header_layout.addStretch(1)
        
        if step > 1:
            exit_btn = PushButton("退出向导")
            exit_btn.clicked.connect(self._exit_wizard)
            header_layout.addWidget(exit_btn)
        
        page_layout.addWidget(header)
        
        # 分割线
        page_layout.addWidget(Separator(page))
        
        # 内容区域（滚动容器，避免非全屏时控件挤压重叠）
        content_scroll = SingleDirectionScrollArea(orient=Qt.Orientation.Vertical)
        content_scroll.setWidgetResizable(True)
        content_scroll.enableTransparentBackground()
        mark_toolbox_scroll_area(content_scroll)

        content = QWidget()
        mark_toolbox_widget(content, "toolboxScroll")
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(16)
        content_scroll.setWidget(content)
        page_layout.addWidget(content_scroll, 1)
        
        # 底部：进度条
        page_layout.addWidget(Separator(page))
        
        bottom = QWidget()
        bottom.setStyleSheet("background: transparent;")
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(0, 8, 0, 0)
        bottom_layout.setSpacing(4)
        
        status_row = QWidget()
        status_row.setStyleSheet("background: transparent;")
        status_layout = QHBoxLayout(status_row)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(8)
        
        # 进度环
        progress_ring = ProgressRing()
        progress_ring.setFixedSize(20, 20)
        progress_ring.setVisible(False)
        status_layout.addWidget(progress_ring)
        
        # 状态文本
        status_label = CaptionLabel("")
        status_layout.addWidget(status_label)
        status_layout.addStretch(1)
        
        bottom_layout.addWidget(status_row)
        
        # 进度条
        progress_bar = ProgressBar()
        progress_bar.setValue(int((step - 1) / 5 * 100))
        bottom_layout.addWidget(progress_bar)
        
        page_layout.addWidget(bottom)
        
        # 保存引用
        page.progress_ring = progress_ring
        page.status_label = status_label
        page.progress_bar = progress_bar
        page.content_scroll = content_scroll

        return page, content_layout
    
    # ==================== 进度一：前期设置 ====================
    def _create_step1_page(self):
        """进度一：前期设置 - 简洁友好的小白UI"""
        page, layout = self._create_page_container("选择游戏", 1)
        
        # 提示文字 - 更友好的说明
        tip_card = CardWidget()
        tip_layout = QVBoxLayout(tip_card)
        tip_layout.setContentsMargins(12, 12, 12, 12)
        tip_layout.setSpacing(6)
        
        tip_title = StrongBodyLabel("💡 小白指南")
        tip_layout.addWidget(tip_title)
        
        tip_text = CaptionLabel(
            "1. 选择游戏目录（包含 game 文件夹的那个）\n"
            "2. 点击「开始提取文本」自动抽取翻译\n"
            "3. 完成后点击「开始翻译」即可\n"
            "💬 如果之前翻译过，会自动保留已有翻译"
        )
        tip_text.setStyleSheet("color: #666; line-height: 1.5;")
        tip_text.setWordWrap(True)
        tip_layout.addWidget(tip_text)
        layout.addWidget(tip_card)
        
        # 游戏路径输入框（支持直接粘贴）
        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        
        self.game_path_edit = LineEdit()
        self.game_path_edit.setPlaceholderText("输入或粘贴游戏目录路径，例如: D:\\Games\\MyGame")
        self.game_path_edit.textChanged.connect(self._on_path_text_changed)
        path_row.addWidget(self.game_path_edit, 1)
        
        self.browse_btn = PushButton("浏览...")
        self.browse_btn.clicked.connect(self._select_game_dir)
        path_row.addWidget(self.browse_btn)
        
        layout.addLayout(path_row)
        
        # 状态提示
        self.path_status_label = CaptionLabel("")
        layout.addWidget(self.path_status_label)
        
        # 旧翻译检测提示卡片（默认隐藏）
        self.old_translation_card = CardWidget()
        self.old_translation_card.setVisible(False)
        self.old_translation_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        old_trans_layout = QVBoxLayout(self.old_translation_card)
        old_trans_layout.setContentsMargins(12, 12, 12, 12)
        old_trans_layout.setSpacing(8)
        
        self.old_trans_title = StrongBodyLabel("🔍 检测到已有翻译")
        old_trans_layout.addWidget(self.old_trans_title)
        
        self.old_trans_desc = CaptionLabel("该游戏已有翻译文件，请选择处理方式：")
        self.old_trans_desc.setWordWrap(True)
        old_trans_layout.addWidget(self.old_trans_desc)

        # 选项文本采用“短标题 + 说明”两行布局，避免窗口较窄时勾选框文本重叠
        self.incremental_rb = CheckBox("增量抽取（推荐）")
        self.incremental_rb.setChecked(True)
        old_trans_layout.addWidget(self.incremental_rb)
        incremental_desc = CaptionLabel("保留已有翻译，抽取新增内容 + 未翻译占位")
        incremental_desc.setWordWrap(True)
        incremental_desc.setStyleSheet("padding-left: 28px; color: #666;")
        old_trans_layout.addWidget(incremental_desc)

        self.full_extract_rb = CheckBox("完整抽取（重做全量）")
        self.full_extract_rb.setChecked(False)
        self.full_extract_rb.setToolTip("会把 tl/<lang> 备份后重新生成，占位会被重置，慎用")
        old_trans_layout.addWidget(self.full_extract_rb)
        full_extract_desc = CaptionLabel("备份旧翻译后重新抽取全部内容，仅在需要推倒重做时使用")
        full_extract_desc.setWordWrap(True)
        full_extract_desc.setStyleSheet("padding-left: 28px; color: #666;")
        old_trans_layout.addWidget(full_extract_desc)
        
        tip_label = CaptionLabel("小提示：默认选择增量抽取，避免覆盖已有翻译；完整抽取只在重做全量时使用。")
        tip_label.setWordWrap(True)
        old_trans_layout.addWidget(tip_label)

        self.auto_merge_cleanup_chk = CheckBox("抽取后自动合并并清理重复")
        try:
            from module.Config import Config
            auto_merge_enabled = getattr(Config().load(), "renpy_incremental_auto_merge_cleanup", True)
        except Exception:
            auto_merge_enabled = False
        self.auto_merge_cleanup_chk.setChecked(auto_merge_enabled)
        self.auto_merge_cleanup_chk.stateChanged.connect(self._on_auto_merge_cleanup_changed)
        old_trans_layout.addWidget(self.auto_merge_cleanup_chk)
        
        # 互斥逻辑
        self.incremental_rb.stateChanged.connect(lambda state: self.full_extract_rb.setChecked(not state) if state else None)
        self.full_extract_rb.stateChanged.connect(lambda state: self.incremental_rb.setChecked(not state) if state else None)
        
        layout.addWidget(self.old_translation_card)

        # 高级选项
        options_card = CardWidget()
        options_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        options_layout = QVBoxLayout(options_card)
        options_layout.setContentsMargins(12, 12, 12, 12)
        options_layout.setSpacing(6)

        options_title = StrongBodyLabel("高级选项")
        options_layout.addWidget(options_title)

        from module.Config import Config
        config = Config().load()

        self.inject_base_box_chk = CheckBox("注入 UI 翻译包（base_box）")
        self.inject_base_box_chk.setChecked(getattr(config, "onekey_inject_base_box", False))
        self.inject_base_box_chk.setToolTip(
            "自动注入预置的 UI 翻译（开始、保存、设置等）。\n"
            "如果你已有自定义 UI 翻译，请取消勾选。"
        )
        self.inject_base_box_chk.stateChanged.connect(self._on_inject_base_box_changed)
        options_layout.addWidget(self.inject_base_box_chk)

        layout.addWidget(options_card)

        layout.addSpacing(20)        # 语言设置（简化）
        layout.addWidget(SubtitleLabel("翻译语言设置"))
        
        lang_row = QHBoxLayout()
        lang_row.setSpacing(20)
        
        # 源语言
        src_layout = QVBoxLayout()
        src_layout.setSpacing(4)
        src_layout.addWidget(CaptionLabel("游戏原语言"))
        self.src_lang_combo = ComboBox()
        self.src_lang_combo.addItems(["英语", "日语", "韩语", "俄语", "其他"])
        self.src_lang_combo.setFixedWidth(150)
        src_layout.addWidget(self.src_lang_combo)
        lang_row.addLayout(src_layout)
        
        # 目标语言
        tgt_layout = QVBoxLayout()
        tgt_layout.setSpacing(4)
        tgt_layout.addWidget(CaptionLabel("翻译成"))
        self.tgt_lang_combo = ComboBox()
        self.tgt_lang_combo.addItems(["简体中文", "繁体中文", "日语", "英语"])
        self.tgt_lang_combo.setFixedWidth(150)
        tgt_layout.addWidget(self.tgt_lang_combo)
        lang_row.addLayout(tgt_layout)
        
        # TL 文件夹名（折叠/隐藏给高级用户）
        tl_layout = QVBoxLayout()
        tl_layout.setSpacing(4)
        tl_layout.addWidget(CaptionLabel("TL 文件夹名"))
        self.tl_folder_edit = LineEdit()
        self.tl_folder_edit.setText("chinese")
        self.tl_folder_edit.setFixedWidth(120)
        self.tl_folder_edit.textChanged.connect(self._on_tl_name_changed)
        tl_layout.addWidget(self.tl_folder_edit)
        lang_row.addLayout(tl_layout)
        
        lang_row.addStretch(1)
        layout.addLayout(lang_row)
        
        layout.addStretch(1)

        # 下一步按钮
        next_row = QHBoxLayout()
        next_row.addStretch(1)
        
        # 轻量说明：一步到位
        self.quick_tip_label = CaptionLabel("直接点击“开始提取文本”即可，完成后进入翻译。如果已有翻译，默认会保留。")
        self.quick_tip_label.setWordWrap(True)
        layout.addWidget(self.quick_tip_label)
        
        # 跳过抽取按钮（已有翻译时显示）
        self.skip_extract_btn = PushButton("跳过抽取，直接翻译 →")
        self.skip_extract_btn.clicked.connect(self._skip_to_translate)
        self.skip_extract_btn.setVisible(False)  # 默认隐藏，检测到翻译后显示
        next_row.addWidget(self.skip_extract_btn)
        
        self.step1_next_btn = PrimaryPushButton("开始提取文本 →")
        self.step1_next_btn.clicked.connect(self._go_step2)
        self.step1_next_btn.setEnabled(False)
        next_row.addWidget(self.step1_next_btn)
        layout.addLayout(next_row)
        
        self.step1_page = page
        self.stacked.addWidget(page)
    
    def _skip_to_translate(self):
        """跳过抽取，直接进入翻译步骤"""
        # 直接跳到步骤4（翻译）
        self.current_step = 4
        self.stacked.setCurrentIndex(3)
        self._refresh_step4_ready()
        self.step4_page.progress_bar.setValue(60)  # 60% 进度
    
    def _on_path_text_changed(self, text):
        """路径输入框文本变化时验证"""
        text = text.strip()
        if not text:
            self.path_status_label.setText("")
            self.step1_next_btn.setEnabled(False)
            self.old_translation_card.setVisible(False)
            self.has_old_translation = False
            return
        
        if os.path.isdir(text):
            # 检查是否是有效的 Ren'Py 游戏目录
            game_subdir = os.path.join(text, "game")
            if os.path.isdir(game_subdir):
                self.game_dir = text
                self.game_path = text
                self._sync_game_dir_to_config(text)
                self.path_status_label.setText("✓ 检测到有效的 Ren'Py 游戏目录")
                self.path_status_label.setStyleSheet("color: #27ae60;")
                self.step1_next_btn.setEnabled(True)
                # 检测旧翻译
                self._check_old_translation(text)
            else:
                self.path_status_label.setText("⚠ 目录中未找到 game 文件夹，可能不是 Ren'Py 游戏")
                self.path_status_label.setStyleSheet("color: #e67e22;")
                # 仍然允许继续
                self.game_dir = text
                self.game_path = text
                self._sync_game_dir_to_config(text)
                self.step1_next_btn.setEnabled(True)
                self.old_translation_card.setVisible(False)
                self.has_old_translation = False
        elif os.path.isfile(text):
            self.game_dir = os.path.dirname(text)
            self.game_path = text
            self._sync_game_dir_to_config(self.game_dir)
            self.path_status_label.setText("✓ 已选择游戏文件")
            self.path_status_label.setStyleSheet("color: #27ae60;")
            self.step1_next_btn.setEnabled(True)
            # 检测旧翻译
            self._check_old_translation(self.game_dir)
        else:
            self.path_status_label.setText("✗ 路径不存在")
            self.path_status_label.setStyleSheet("color: #e74c3c;")
            self.step1_next_btn.setEnabled(False)
            self.old_translation_card.setVisible(False)
            self.has_old_translation = False
    
    def _on_inject_base_box_changed(self, state):
        """更新 base_box 注入开关"""
        from module.Config import Config
        config = Config().load()
        config.onekey_inject_base_box = bool(state)
        config.save()

    def _sync_game_dir_to_config(self, game_dir):
        """同步游戏目录到配置文件，包括输入/输出目录"""
        from module.Config import Config
        from pathlib import Path
        
        config = Config().load()
        config.renpy_game_folder = game_dir
        config.renpy_project_path = game_dir
        
        # 设置 tl 目录路径
        tl_name = getattr(self, 'tl_folder_edit', None)
        tl_name = tl_name.text().strip() if tl_name else "chinese"
        if not tl_name:
            tl_name = "chinese"
        
        tl_dir = Path(game_dir) / "game" / "tl" / tl_name
        config.renpy_tl_folder = str(tl_dir)
        
        # 输入：tl 目录（待翻译文件）
        config.input_folder = str(tl_dir)
        
        # 输出：游戏根目录下的独立文件夹（不会被 Ren'Py 引擎识别）
        output_base = Path(game_dir) / "RenpyBox_Translation"
        config.output_folder = str(output_base / tl_name)
        
        # 确保输出目录存在
        Path(config.output_folder).mkdir(parents=True, exist_ok=True)
        
        # 保存输出根目录，用于后续显示
        if not hasattr(config, 'renpybox_output_root'):
            # 动态添加属性（如果配置类不支持，可以忽略）
            try:
                config.renpybox_output_root = str(output_base)
            except:
                pass
        
        config.save()
        
        self.info(f"[配置] 输入目录: {config.input_folder}")
        self.info(f"[配置] 输出目录: {config.output_folder}")
    
    def _check_old_translation(self, game_dir):
        """检测是否有旧翻译"""
        tl_name = self.tl_folder_edit.text().strip() or "chinese"
        tl_dir = Path(game_dir) / "game" / "tl" / tl_name
        
        if tl_dir.exists() and any(tl_dir.iterdir()):
            # 统计旧翻译文件数量
            rpy_count = len(list(tl_dir.rglob("*.rpy")))
            self.has_old_translation = True
            self.old_trans_title.setText(f"🔍 检测到已有翻译 ({rpy_count} 个文件)")
            self.old_trans_desc.setText(f"该游戏在 tl/{tl_name} 中已有翻译文件，请选择处理方式：")
            self.old_translation_card.setVisible(True)
            self.incremental_rb.setChecked(True)
            self.full_extract_rb.setChecked(False)
            # 显示跳过按钮
            self.skip_extract_btn.setVisible(True)
        else:
            self.has_old_translation = False
            self.old_translation_card.setVisible(False)
            # 隐藏跳过按钮
            self.skip_extract_btn.setVisible(False)
    
    def _on_tl_name_changed(self, text):
        """TL 文件夹名变化时重新检测旧翻译并同步配置"""
        if self.game_dir:
            self._check_old_translation(self.game_dir)
            # 同步更新配置中的 tl 目录
            self._sync_game_dir_to_config(self.game_dir)
    
    # ==================== 进度二：提取进度 ====================
    def _create_step2_page(self):
        """进度二：提取进度"""
        page, layout = self._create_page_container("提取文本", 2)
        
        layout.addStretch(1)
        
        self.step2_status = TitleLabel("准备开始提取...")
        self.step2_status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.step2_status)
        
        self.step2_desc = BodyLabel("正在从游戏中提取文本并生成翻译文件，请稍候。完成后点击“开始翻译”进入下一步，随时可重新抽取。")
        self.step2_desc.setAlignment(Qt.AlignCenter)
        self.step2_desc.setWordWrap(True)
        layout.addWidget(self.step2_desc)
        
        layout.addStretch(1)
        
        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        
        # 重试按钮 (默认隐藏，失败后显示)
        self.step2_retry_btn = PushButton("重新抽取")
        self.step2_retry_btn.clicked.connect(self._retry_extraction)
        self.step2_retry_btn.setVisible(False)
        btn_row.addWidget(self.step2_retry_btn)
        
        # 跳过按钮 (失败时可跳过)
        self.step2_skip_btn = PushButton("跳过此步骤")
        self.step2_skip_btn.clicked.connect(self._go_step3)
        self.step2_skip_btn.setVisible(False)
        btn_row.addWidget(self.step2_skip_btn)
        
        # 下一步按钮 (默认隐藏，完成后显示)
        self.step2_next_btn = PrimaryPushButton("下一步 →")
        self.step2_next_btn.clicked.connect(self._go_step3)
        self.step2_next_btn.setVisible(False)
        btn_row.addWidget(self.step2_next_btn)

        self.step2_merge_btn = PushButton("合并并清理重复")
        self.step2_merge_btn.clicked.connect(self._merge_incremental_dir)
        self.step2_merge_btn.setVisible(False)
        btn_row.addWidget(self.step2_merge_btn)
        
        btn_row.addStretch(1)
        layout.addLayout(btn_row)
        
        self.step2_page = page
        self.stacked.addWidget(page)
    
    def _retry_extraction(self):
        """重试提取"""
        self.step2_retry_btn.setVisible(False)
        self.step2_skip_btn.setVisible(False)
        self._go_step2()

    def _on_auto_merge_cleanup_changed(self, state: int):
        """同步自动合并开关到配置"""
        try:
            from module.Config import Config
            config = Config().load()
            config.renpy_incremental_auto_merge_cleanup = bool(state)
            config.save()
        except Exception as exc:
            self.logger.warning(f"保存自动合并配置失败: {exc}")

    def _merge_incremental_dir(self):
        """合并增量目录并清理重复"""
        try:
            # 新流程必须先翻译到独立输出目录，再由“应用翻译”语义合并。
            # 禁止旧入口提前合并并删除仍作为翻译输入的 chinese_new。
            if self._incremental_output_dir:
                InfoBar.warning(
                    "请先完成翻译",
                    "当前增量内容尚未应用，请完成翻译后点击“应用翻译到游戏”。",
                    parent=self,
                )
                return
            if not self.game_dir:
                InfoBar.warning("提示", "请先选择游戏目录", parent=self)
                return
            tl_name = self.tl_folder_edit.text().strip() or "chinese"
            incremental_dir = Path(self.game_dir) / "game" / "tl" / f"{tl_name}_new"
            result = self.unified_extractor.merge_incremental_folder(
                self.game_dir,
                tl_name,
                incremental_dir,
                clean_duplicates=True,
            )
            if result.success:
                InfoBar.success("合并完成", result.message, parent=self)
            else:
                InfoBar.warning("合并失败", result.message, parent=self)
        except Exception as exc:
            self.logger.error(f"合并失败: {exc}")
            InfoBar.error("错误", str(exc), parent=self)
    
    # ==================== 进度三：术语表 ====================
    def _create_step3_page(self):
        """进度三：术语表"""
        page, layout = self._create_page_container("术语表设置", 3)
        
        layout.addWidget(SubtitleLabel("术语表与禁翻表"))
        layout.addWidget(BodyLabel("术语表可以帮助你统一专有名词的翻译，禁翻表可以防止翻译不需要翻译的内容。本地词库页还支持手动扫描术语候选。"))
        
        layout.addSpacing(16)
        
        self.glossary_info_label = BodyLabel("正在查找项目中的术语表...")
        layout.addWidget(self.glossary_info_label)
        
        layout.addSpacing(16)
        
        btn_row = QHBoxLayout()
        self.open_glossary_btn = PushButton("📂 打开本地词库管理")
        self.open_glossary_btn.setToolTip("可在本地词库页手动执行“扫描术语候选”，补齐角色名之外的正文专名")
        self.open_glossary_btn.clicked.connect(self._open_local_glossary)
        btn_row.addWidget(self.open_glossary_btn)
        
        self.open_preserve_btn = PushButton("🚫 打开禁翻表管理")
        self.open_preserve_btn.clicked.connect(self._open_text_preserve)
        btn_row.addWidget(self.open_preserve_btn)
        
        self.scan_names_btn = PushButton("🔍 自动提取角色名")
        self.scan_names_btn.clicked.connect(self._scan_character_names)
        btn_row.addWidget(self.scan_names_btn)
        
        btn_row.addStretch(1)
        layout.addLayout(btn_row)
        
        layout.addStretch(1)
        
        next_row = QHBoxLayout()
        next_row.addStretch(1)
        self.step3_next_btn = PrimaryPushButton("下一步 (开始翻译) →")
        self.step3_next_btn.clicked.connect(self._go_step4)
        next_row.addWidget(self.step3_next_btn)
        layout.addLayout(next_row)
        
        self.step3_page = page
        self.stacked.addWidget(page)
    
    # ==================== 进度四：开始翻译 ====================
    def _create_step4_page(self):
        """进度四：开始翻译"""
        page, layout = self._create_page_container("执行翻译", 4)
        
        layout.addWidget(SubtitleLabel("准备翻译"))
        self.step4_status = BodyLabel(
            "翻译文件将输出到游戏根目录下的独立文件夹，不会被引擎识别。\n"
            "完成后可在「后续处理」中应用到游戏。"
        )
        layout.addWidget(self.step4_status)
        
        layout.addSpacing(20)
        
        # 翻译按钮
        btn_row = QHBoxLayout()
        self.start_trans_btn = PrimaryPushButton("🚀 开始翻译")
        self.start_trans_btn.clicked.connect(self._on_start_translate_clicked)
        btn_row.addWidget(self.start_trans_btn)

        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        from module.Config import Config
        auto_hook_row = QHBoxLayout()
        self.auto_hook_supplement_chk = CheckBox("翻译完成后自动补全漏翻（replace_text）")
        self.auto_hook_supplement_chk.setChecked(
            getattr(Config().load(), "onekey_auto_hook_supplement", False)
        )
        self.auto_hook_supplement_chk.setToolTip(
            "默认关闭。\n"
            "开启后，主翻译完成会自动再跑一轮补全漏翻，生成/翻译 replace_text_auto.rpy。"
        )
        self.auto_hook_supplement_chk.stateChanged.connect(self._on_auto_hook_supplement_changed)
        auto_hook_row.addWidget(self.auto_hook_supplement_chk)
        auto_hook_row.addStretch(1)
        layout.addLayout(auto_hook_row)
        
        layout.addStretch(1)
        
        # 底部按钮
        action_row = QHBoxLayout()
        action_row.addStretch(1)
        
        self.skip_trans_btn = PushButton("跳过翻译 →")
        self.skip_trans_btn.clicked.connect(self._go_step5)
        action_row.addWidget(self.skip_trans_btn)
        
        action_row.addStretch(1)
        layout.addLayout(action_row)
        
        self.step4_page = page
        self.stacked.addWidget(page)
        # 初始化一次检查状态
        self._refresh_step4_ready()
    
    # ==================== 进度五：后续处理 ====================
    def _create_step5_page(self):
        """进度五：后续处理"""
        page, layout = self._create_page_container("完成", 5)
        
        layout.addWidget(SubtitleLabel("🎉 翻译流程结束"))
        layout.addWidget(BodyLabel("你可以使用以下工具进行后续处理："))
        layout.addWidget(
            CaptionLabel("如果切换到中文后仍有漏翻文本，优先使用“补全漏翻”生成 replace_text_auto.rpy。")
        )
        
        # 创建滚动区域
        scroll_area = SingleDirectionScrollArea(orient=Qt.Orientation.Vertical)
        scroll_area.setWidgetResizable(True)
        scroll_area.enableTransparentBackground()
        mark_toolbox_scroll_area(scroll_area)
        
        scroll_widget = QWidget()
        mark_toolbox_widget(scroll_widget, "toolboxScroll")
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        
        flow_container = QWidget()
        mark_toolbox_widget(flow_container, "toolboxFlow")
        flow_layout = FlowLayout(flow_container, needAni=False)
        flow_layout.setSpacing(8)
        flow_layout.setContentsMargins(0, 0, 0, 0)
        
        # 工具卡片
        tools = [
            ("补全漏翻", "扫描 tl 未覆盖的文本并生成 replace_text_auto.rpy", self._tool_hook_supplement),
            ("应用翻译到游戏", "将翻译结果复制到游戏 tl 目录", self._tool_apply_translation),
            ("检测/修复报错", "修复缩进和格式问题", self._tool_fix_errors),
            ("设置默认语言", "设置游戏启动时的默认语言", self._tool_set_default_lang),
            ("添加语言切换", "注入语言切换按钮", self._tool_add_lang_switch),
            ("批量注入字体", "注入预置字体包", self._tool_replace_font),
            ("打开游戏目录", "查看翻译结果", self._tool_open_game_dir),
            ("导出语言补丁", "导出 tl 目录为 zip", self._tool_export_patch),
        ]
        
        for title, desc, func in tools:
            flow_layout.addWidget(
                ItemCard(parent=self, title=title, description=desc, clicked=func)
            )
        
        scroll_layout.addWidget(flow_container)
        scroll_layout.addStretch(1)
        
        scroll_area.setWidget(scroll_widget)
        layout.addWidget(scroll_area)
        
        self.step5_page = page
        self.stacked.addWidget(page)

    # ==================== 逻辑处理 ====================
    
    def _select_game_dir(self):
        """浏览选择游戏目录"""
        dir_path = QFileDialog.getExistingDirectory(self, "选择游戏目录", "")
        if dir_path:
            self.game_path_edit.setText(dir_path)
    
    def _detect_game_status(self, game_dir: str) -> tuple:
        """
        检测游戏状态，返回 (status, message)
        
        status:
            - 'ready': 已有 rpy 文件，可直接提取
            - 'need_decompile': 只有 rpyc 文件，需要反编译
            - 'need_unpack': 有 rpa 文件，需要解包
            - 'mixed': 混合状态
            - 'empty': 无可用文件
        """
        from pathlib import Path
        
        game_path = Path(game_dir) / "game"
        if not game_path.exists():
            return 'empty', '未找到 game 目录'
        
        rpy_count = len(list(game_path.rglob("*.rpy")))
        rpyc_count = len(list(game_path.rglob("*.rpyc")))
        rpa_count = len(list(game_path.glob("*.rpa")))
        
        if rpa_count > 0 and rpy_count == 0 and rpyc_count == 0:
            return 'need_unpack', f'检测到 {rpa_count} 个 RPA 包，需要解包'
        
        if rpy_count == 0 and rpyc_count > 0:
            return 'need_decompile', f'检测到 {rpyc_count} 个 RPYC 文件，需要反编译'
        
        if rpy_count > 0 and rpyc_count > 0:
            return 'mixed', f'检测到 {rpy_count} 个 RPY 和 {rpyc_count} 个 RPYC 文件'
        
        if rpy_count > 0:
            return 'ready', f'检测到 {rpy_count} 个 RPY 文件，可直接提取'
        
        return 'empty', '未检测到可提取的文件'
    
    def _auto_decompile(self, game_dir: str) -> tuple:
        """
        自动执行反编译
        
        Returns:
            (success, message)
        """
        unren_error = None
        try:
            from pathlib import Path
            from module.Tool.Packer import Packer

            game_path = Path(game_dir)
            if game_path.name.lower() != "game":
                game_path = game_path / "game"

            ok, _lines = Packer().unpack_all_unren_bat(
                str(game_path),
                lang="zh",
                options="2x",
                purpose="反编译",
                timeout_s=60 * 60,
            )
            if ok:
                return True, "反编译完成 (UnRen)"
        except Exception as unren_exc:
            unren_error = unren_exc

        try:
            from module.Tool.RenpyDecompiler import RenpyDecompiler

            decompiler = RenpyDecompiler()
            decompiler.decompile(game_dir, overwrite=False)
            
            return True, "反编译完成 (unrpyc v2)"
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            if unren_error:
                return False, f"反编译失败（UnRen 失败：{unren_error}）：{e}"
            return False, f"反编译失败（可能版本不兼容/加密/脚本特殊）：{e}"
        
    def _go_step2(self):
        """进入步骤2并开始提取"""
        # 如果正在抽取中，避免重复启动线程
        if self.extraction_worker and self.extraction_worker.isRunning():
            InfoBar.warning("提示", "抽取正在进行中，请等待完成后再操作。", parent=self)
            return

        # 每次重新抽取都建立全新的路径上下文，不能沿用上一次项目的增量目标。
        self._incremental_dir = None
        self._incremental_output_dir = None
        self._apply_target_dir = None

        self.current_step = 2
        self.stacked.setCurrentIndex(1)

        # 抽取开始时，禁用“开始翻译/下一步”等按钮，避免在抽取过程中误点
        self.step2_next_btn.setVisible(False)
        self.step2_next_btn.setEnabled(False)
        self.step2_retry_btn.setVisible(False)
        self.step2_retry_btn.setEnabled(False)
        self.step2_skip_btn.setVisible(False)
        self.step2_skip_btn.setEnabled(False)
        self.step2_merge_btn.setVisible(False)
        self.step2_merge_btn.setEnabled(False)
        self.step2_desc.setText("正在从游戏中提取文本并生成翻译文件，请稍候。")
        self.step2_page.progress_bar.setValue(0)
        
        # 启动提取线程
        game_dir = self.game_dir
        tl_name = self.tl_folder_edit.text().strip() or "chinese"
        
        exe_guess = Path(game_dir) / "game.exe"
        exe_path = exe_guess if exe_guess.exists() else game_dir
        if self.game_path and os.path.isfile(self.game_path) and self.game_path.endswith(".exe"):
             exe_path = self.game_path
        
        # ===== 新增：游戏预处理检测 =====
        self.step2_status.setText("🔍 检测游戏状态...")
        self.step2_page.progress_ring.setVisible(True)
        self.step2_page.progress_bar.setValue(5)
        
        status, status_msg = self._detect_game_status(game_dir)
        
        if status == 'need_decompile':
            self.step2_status.setText("🔨 正在反编译 RPYC 文件...")
            self.step2_desc.setText(status_msg + "\n正在自动执行反编译，请稍候...")
            self.step2_page.progress_bar.setValue(10)
            
            # 执行反编译
            success, decompile_msg = self._auto_decompile(game_dir)
            
            if not success:
                self.step2_page.progress_ring.setVisible(False)
                self.step2_status.setText("✗ 反编译失败")
                self.step2_desc.setText(
                    f"{decompile_msg}\n\n"
                    "可能的原因：\n"
                    "• 游戏使用了加密/混淆\n"
                    "• Ren'Py 版本不兼容\n"
                    "• 缺少游戏的 Python 运行时\n\n"
                    "建议：尝试使用其他反编译工具或联系开发者"
                )
                self.step2_retry_btn.setVisible(True)
                self.step2_skip_btn.setVisible(True)
                self.step2_retry_btn.setEnabled(True)
                self.step2_skip_btn.setEnabled(True)
                InfoBar.warning("提示", "反编译失败，请检查游戏文件", parent=self)
                return
            
            self.step2_desc.setText(decompile_msg)
            self.step2_page.progress_bar.setValue(20)
        
        elif status == 'need_unpack':
            self.step2_page.progress_ring.setVisible(False)
            self.step2_status.setText("📦 需要解包 RPA")
            self.step2_desc.setText(
                f"{status_msg}\n\n"
                "请先使用「RPA 解包」功能解包游戏资源，\n"
                "或者使用 rpatool 等工具手动解包后再试。"
            )
            self.step2_retry_btn.setVisible(True)
            self.step2_skip_btn.setVisible(True)
            self.step2_retry_btn.setEnabled(True)
            self.step2_skip_btn.setEnabled(True)
            InfoBar.warning("提示", "请先解包 RPA 资源", parent=self)
            return
        
        elif status == 'empty':
            self.step2_page.progress_ring.setVisible(False)
            self.step2_status.setText("✗ 未找到游戏文件")
            self.step2_desc.setText(status_msg)
            self.step2_retry_btn.setVisible(True)
            self.step2_retry_btn.setEnabled(True)
            self.step2_skip_btn.setVisible(False)
            self.step2_skip_btn.setEnabled(False)
            return
        
        # ===== 继续正常的提取流程 =====
        # 检测是否使用增量模式
        incremental = self.has_old_translation and self.incremental_rb.isChecked()
        
        if incremental:
            self.step2_status.setText("🔄 增量抽取中...")
        else:
            self.step2_status.setText("正在提取...")
        self.step2_page.progress_ring.setVisible(True)
        
        self.extraction_worker = ExtractionWorker(self.unified_extractor, game_dir, tl_name, exe_path, incremental=incremental)
        self.extraction_worker.progress.connect(self._on_extract_progress)
        self.extraction_worker.finished.connect(self._on_extract_finished)
        self.extraction_worker.start()
        
    def _on_extract_progress(self, msg, percent):
        self.step2_status.setText(msg)
        self.step2_page.progress_bar.setValue(percent)
        
    def _on_extract_finished(self, success, msg, result=None):
        self.step2_page.progress_ring.setVisible(False)
        if success:
            self.step2_status.setText("✓ 提取完成")
            
            # 如果是增量抽取并且有单独的增量目录，显示更详细的信息
            if result and result.incremental_dir and result.incremental_dir.exists():
                detail_msg = (
                    f"{msg}\n\n"
                    f"💡 新增内容已输出到单独文件夹：{result.incremental_dir.name}/\n"
                    f"原有翻译保持不变，可分别处理新增内容。"
                )
                self._incremental_dir = result.incremental_dir
                # Keep the staging directory until it has been translated.  Merging
                # here deletes it and makes the translation page fall back to the
                # complete main language directory.
                from module.Config import Config
                tl_name = self.tl_folder_edit.text().strip() or "chinese"
                config = Config().load()
                apply_target, delta_output = configure_incremental_translation_paths(
                    config, self.game_dir, tl_name, result.incremental_dir
                )
                shutil.rmtree(str(delta_output), ignore_errors=True)
                delta_output.mkdir(parents=True, exist_ok=True)
                config.save()
                self._apply_target_dir = apply_target
                self._incremental_output_dir = delta_output
                detail_msg += (
                    f"\n增量翻译输入：{result.incremental_dir.name}/"
                    f"\n增量翻译输出：{delta_output.name}/"
                )
            else:
                detail_msg = f'{msg}\n已保留占位（new==old），可直接进入翻译。需要更新术语/禁翻后可再次点击"重新抽取"。'
                self._incremental_dir = None
                self._incremental_output_dir = None
                self._apply_target_dir = None
            
            self.step2_desc.setText(detail_msg)
            self.step2_page.progress_bar.setValue(100)
            self.step2_next_btn.setVisible(True)
            self.step2_next_btn.setEnabled(True)
            self.step2_retry_btn.setVisible(True)
            self.step2_retry_btn.setEnabled(True)
            self.step2_skip_btn.setVisible(False)
            self.step2_skip_btn.setEnabled(False)
            self.step2_next_btn.setText("开始翻译 →")
            # 增量暂存目录是后续翻译输入，翻译前不能通过旧按钮直接合并或删除。
            self.step2_merge_btn.setVisible(False)
            self.step2_merge_btn.setEnabled(False)
            
            # 自动执行角色名和禁翻表扫描（仅第一次执行，避免重复卡顿）
            self._extract_character_names()
            
            InfoBar.success("成功", "提取完成，已自动扫描角色名和变量引用", parent=self)
        else:
            self.step2_status.setText("✗ 提取遇到问题")
            self.step2_desc.setText(f'错误信息：{msg}\n\n建议先点"重新抽取"。如仍失败，可跳过直接翻译，或检查路径/权限后再试。')
            self.step2_retry_btn.setVisible(True)
            self.step2_skip_btn.setVisible(True)
            self.step2_retry_btn.setEnabled(True)
            self.step2_skip_btn.setEnabled(True)
            self.step2_next_btn.setVisible(False)
            self.step2_next_btn.setEnabled(False)
            self.step2_merge_btn.setVisible(False)
            self.step2_merge_btn.setEnabled(False)
            InfoBar.warning("提示", "提取过程遇到问题，你可以重试或跳过", parent=self)

    def _scan_character_names(self):
        """扫描游戏目录下的角色名并添加到术语表，变量引用添加到禁翻表"""
        self._extract_character_names(force=True)
        InfoBar.success("成功", "已扫描角色名(→术语表)和变量引用(→禁翻表)", parent=self)

    def _extract_character_names(self, *, force: bool = False):
        """自动扫描并填充术语表（角色名）和禁翻表（变量引用）"""
        if not self.game_dir:
            return
            
        game_path = Path(self.game_dir) / "game"
        if not game_path.exists():
            return
            
        import re
        from module.Text.SkipRules import should_skip_text
        from module.Config import Config
        from module.Extract.ReplaceGenerator import extract_names_from_game
        
        # 匹配: Character("Name") 或 Character(_("Name"))
        RE_CHARACTER_CALL = re.compile(
            r'Character\s*\(\s*(?:_\(\s*)?(["\'])((?:\\\1|.)*?)\1',
            re.MULTILINE
        )
        
        # 匹配对话/文本中的变量引用: [variable_name]
        RE_VARIABLE_IN_TEXT = re.compile(r'\[(\w+)\]')

        found_names = set()
        found_preserves = set()  # 用于存储变量引用
        
        config = Config().load()
        cache_key = str(game_path.resolve())
        auto_cache = dict(getattr(config, "glossary_auto_scan_cache", {}) or {})

        if not force and cache_key in auto_cache:
            LogManager.get().info(
                "Skip character scan: already scanned for %s", cache_key
            )
            return

        try:
            # === 新增：从 textbutton/text 控件提取角色名 ===
            try:
                extra_names = extract_names_from_game(game_path)
                for name in extra_names:
                    if not should_skip_text(name):
                        found_names.add(name)
                LogManager.get().debug(f"从 UI 控件提取到 {len(extra_names)} 个角色名")
            except Exception as e:
                LogManager.get().warning(f"从 UI 控件提取角色名失败: {e}")
            
            for rpy_file in game_path.rglob("*.rpy"):
                try:
                    content = rpy_file.read_text(encoding="utf-8", errors="ignore")
                    
                    # 1. 扫描 Character() 定义 → 术语表
                    matches = RE_CHARACTER_CALL.findall(content)
                    for quote, raw_name in matches:
                        name_str = raw_name.replace('\\"', '"').replace("\\'", "'").replace("\\\\", "\\").strip()
                        if not name_str:
                            continue
                        
                        # 跳过变量引用形式的角色名 (如 [player_name])
                        if name_str.startswith('[') and name_str.endswith(']'):
                            found_preserves.add(name_str)
                            continue
                            
                        if not self._looks_like_character_name(name_str):
                            continue
                            
                        # 正常角色名放入术语表
                        if not should_skip_text(name_str):
                            found_names.add(name_str)
                    
                    # 2. 扫描对话文本中的变量引用 [xxx] → 禁翻表
                    # 这些变量引用会嵌入在对话中，需要保护
                    var_matches = RE_VARIABLE_IN_TEXT.findall(content)
                    for var_name in var_matches:
                        # 保存带括号的形式
                        found_preserves.add(f"[{var_name}]")
                        
                except Exception:
                    pass
        except Exception:
            pass
            
        updated_entries = self._update_config(found_names, found_preserves, config)

        auto_cache[cache_key] = time.time()
        config.glossary_auto_scan_cache = auto_cache
        config.save()

    @staticmethod
    def _clean_text_for_type(text: str) -> str:
        """去除格式标签/空白，便于分类"""
        if not text:
            return ""
        import re
        cleaned = re.sub(r"\{/?[^}]+\}", "", text)
        return cleaned.replace("\u3000", " ").strip()

    @staticmethod
    def _should_ignore_extracted_name(text: str) -> bool:
        """过滤明显无效的候选（如单字母 A/Q/变量样式）"""
        if not text:
            return True
        if len(text) <= 1:
            return True
        # 单字母 + 可选标点（A. / Q. / A）
        import re
        if re.fullmatch(r"[A-Za-z](?:\.|!|\?)?", text):
            return True
        # 过短且包含点/下划线通常是变量或占位
        if len(text) <= 3 and any(ch in text for ch in ".:_"):
            return True
        return False

    @staticmethod
    def _categorize_term(text: str, default: str = "") -> str:
        """基于 LocalGlossary 的关键词规则做简易分类"""
        if not text:
            return default
        t = text.strip()
        lower = t.lower()
        place_keywords = [
            "city", "village", "town", "forest", "mountain", "hill", "park", "garden",
            "school", "academy", "college", "campus", "church", "temple", "shrine",
            "castle", "tower", "dungeon", "cave", "ruins", "harbor", "port", "station",
            "beach", "island", "lake", "river", "bridge", "street", "road", "avenue",
            "hotel", "inn", "bar", "cafe", "shop", "market", "library"
        ]
        item_keywords = [
            "sword", "blade", "dagger", "bow", "gun", "rifle", "pistol", "armor", "shield",
            "ring", "necklace", "amulet", "bracelet", "crown", "helmet", "boots", "gloves",
            "potion", "elixir", "herb", "scroll", "book", "map", "key", "card", "ticket",
            "coin", "gem", "crystal", "stone", "orb", "staff", "wand", "medal"
        ]
        if any(k in lower for k in place_keywords):
            return "地名"
        if any(k in lower for k in item_keywords):
            return "物品"
        words = t.split()
        if words and all(w[:1].isupper() for w in words if w):
            return default or ""
        return default

    def _find_ner_model_path(self) -> Path | None:
        """查找本地 NER 模型路径（resource/Models/ner 下），兼容打包路径."""
        candidates: list[Path] = []
        candidate_roots = [
            Path(get_resource_path("resource", "Models", "ner")),
            (Path(".") / "resource" / "Models" / "ner").resolve(),
            (Path(__file__).resolve().parents[2] / "resource" / "Models" / "ner").resolve(),
        ]
        for model_root in candidate_roots:
            if not model_root.exists():
                continue
            for p in model_root.iterdir():
                if p.is_dir() and (p / "meta.json").exists():
                    candidates.append(p)
        if not candidates:
            return None
        candidates.sort()
        return candidates[0]

    def _load_ner_model(self):
        """懒加载 spaCy NER 模型，失败则返回 None"""
        if self._ner_model_loaded:
            return self._ner_model
        self._ner_model_loaded = True
        try:
            import spacy
        except Exception:
            self._ner_model = None
            return None
        model_path = self._find_ner_model_path()
        if not model_path:
            self._ner_model = None
            return None
        try:
            self._ner_model = spacy.load(
                str(model_path),
                exclude=["parser", "tagger", "lemmatizer", "attribute_ruler", "tok2vec"],
            )
        except Exception:
            self._ner_model = None
        return self._ner_model

    def _ner_guess_type(self, text: str, default: str = "") -> str:
        """使用 NER 预测类别（角色/地名/组织/物品），失败则返回默认"""
        nlp = self._load_ner_model()
        if not nlp:
            return default
        label_map = {
            "PER": "角色",
            "PERSON": "角色",
            "PER_NO": "角色",
            "LOC": "地名",
            "GPE": "地名",
            "ORG": "组织",
            "FAC": "地名",
            "PRODUCT": "物品",
            "ITEM": "物品",
        }
        try:
            doc = nlp(text)
            for ent in doc.ents:
                mapped = label_map.get(ent.label_)
                if mapped:
                    return mapped
        except Exception:
            return default
        return default

    def _update_config(self, found_names, found_preserves, config):
        """更新配置文件，返回是否写入新数据"""
        updated = False

        # 更新术语表
        if found_names:
            existing_src = set()
            if config.glossary_data:
                for item in config.glossary_data:
                    if isinstance(item, dict):
                        existing_src.add(item.get("src", ""))
                    elif isinstance(item, str):
                        existing_src.add(item)

            new_entries = []
            for name in found_names:
                cleaned = self._clean_text_for_type(name)
                if not cleaned or cleaned in existing_src:
                    continue
                if self._should_ignore_extracted_name(cleaned):
                    continue
                type_guess = self._ner_guess_type(cleaned, default="") or self._categorize_term(cleaned, default="")
                new_entries.append({
                    "src": cleaned,
                    "dst": "",
                    "info": "角色名 (自动提取)",
                    "type": type_guess
                })

            if new_entries:
                if not config.glossary_data:
                    config.glossary_data = []
                config.glossary_data.extend(new_entries)
                config.glossary_enable = True
                updated = True
                
        # 更新禁翻表
        if found_preserves:
            existing_preserve = set()
            if config.text_preserve_data:
                for item in config.text_preserve_data:
                    if isinstance(item, dict):
                        existing_preserve.add(item.get("src", ""))
                    elif isinstance(item, str):
                        existing_preserve.add(item)
                        
            new_preserves = []
            for text in found_preserves:
                if text not in existing_preserve:
                    new_preserves.append({"src": text})
                    
            if new_preserves:
                if not config.text_preserve_data:
                    config.text_preserve_data = []
                config.text_preserve_data.extend(new_preserves)
                config.text_preserve_enable = True
                updated = True
                
        return updated

    @staticmethod
    def _looks_like_character_name(name: str) -> bool:
        if not name:
            return False
        if any(char.isupper() for char in name):
            return True
        if any(ord(char) > 127 and char.isalpha() for char in name):
            return True
        return False
            
    def _go_step3(self):
        self.current_step = 3
        self.stacked.setCurrentIndex(2)
        self._find_glossary_files()
        
    def _find_glossary_files(self):
        found_files = []
        if self.game_dir:
            patterns = ["glossary.json", "glossary.xlsx", "glossary.txt", "blacklist.json", "blacklist.txt"]
            for pattern in patterns:
                if os.path.exists(os.path.join(self.game_dir, pattern)):
                    found_files.append(pattern)
                if os.path.exists(os.path.join(self.game_dir, "game", pattern)):
                    found_files.append(f"game/{pattern}")
        
        if found_files:
            self.glossary_info_label.setText(f"找到文件: {', '.join(found_files)}")
        else:
            self.glossary_info_label.setText("未找到术语表文件，将使用默认配置。")

    def _open_local_glossary(self):
        if hasattr(self.window, "navigate_to_page"):
            from frontend.RenpyToolbox.LocalGlossaryPage import LocalGlossaryPage
            page = LocalGlossaryPage("local-glossary", self.window)
            self.window.navigate_to_page(page)

    def _open_text_preserve(self):
        if hasattr(self.window, "navigate_to_page"):
            from frontend.RenpyToolbox.TextPreservePage import TextPreservePage
            page = TextPreservePage("text-preserve", self.window)
            self.window.navigate_to_page(page)

    def _scan_character_names(self):
        """扫描游戏目录下的角色名并添加到术语表，变量引用添加到禁翻表"""
        self._extract_character_names(force=True)
        InfoBar.success("成功", "已扫描角色名(→术语表)和变量引用(→禁翻表)", parent=self)
            
    def _go_step4(self):
        self.current_step = 4
        self.stacked.setCurrentIndex(3)
        self._refresh_step4_ready()
    
    def _on_start_translate_clicked(self):
        """检查配置后再进入翻译面板"""
        if not self._refresh_step4_ready():
            InfoBar.warning("提示", "请先在接口设置激活翻译平台，并在项目设置填写输入/输出目录。", parent=self)
            return
        
        # 显示友好的目录说明
        from module.Config import Config
        from qfluentwidgets import MessageBox
        
        config = Config().load()
        
        # 根据主题选择样式颜色
        code_bg = "#2d2d2d" if isDarkTheme() else "#f5f5f5"
        hint_color = "#aaa" if isDarkTheme() else "#666"
        
        msg_box = MessageBox(
            "📁 翻译目录说明",
            f"<b>输入目录</b>（待翻译文件）：<br>"
            f"<code style='background:{code_bg};padding:2px 4px;'>{config.input_folder}</code><br><br>"
            f"<b>输出目录</b>（翻译结果）：<br>"
            f"<code style='background:{code_bg};padding:2px 4px;'>{config.output_folder}</code><br><br>"
            f"<p style='color:{hint_color};'><i>💡 输出目录位于游戏根目录下，不会被 Ren'Py 引擎识别。<br>"
            f"翻译完成后，可在「后续处理」中应用到游戏。</i></p>",
            self
        )
        msg_box.yesButton.setText("开始翻译")
        msg_box.cancelButton.setText("取消")
        
        if msg_box.exec():
            self._onekey_translation_started = True
            self._auto_hook_pending = self.auto_hook_supplement_chk.isChecked()
            self._auto_hook_running = False
            self._open_legacy_translation_page()

    def _on_auto_hook_supplement_changed(self, state):
        """保存一键翻译后的自动补漏开关。"""
        try:
            from module.Config import Config

            config = Config().load()
            config.onekey_auto_hook_supplement = bool(state)
            config.save()
        except Exception as e:
            self.logger.warning(f"保存自动补全漏翻配置失败: {e}")
        
    def _open_legacy_translation_page(self):
        """打开传统翻译页面，保留续翻译能力"""
        try:
            if not self.window:
                raise RuntimeError("未找到主窗口，无法打开翻译面板")

            # 优先复用主窗口已有的 translation_page
            if hasattr(self.window, "translation_page") and self.window.translation_page:
                page = self.window.translation_page
                # 使用 switchTo 方法切换，比 navigate_to_page 更快
                if hasattr(self.window, "switchTo"):
                    self.window.switchTo(page)
                    return
            else:
                page = TranslationPage("translation_page", self.window)
                self.window.translation_page = page

            if hasattr(self.window, "navigate_to_page"):
                self.window.navigate_to_page(page)
            elif hasattr(self.window, "stackedWidget"):
                stack = self.window.stackedWidget
                widgets = [stack.widget(i) for i in range(stack.count())]
                if page not in widgets:
                    stack.addWidget(page)
                stack.setCurrentWidget(page)
            else:
                page.show()
        except Exception as e:
            LogManager.get().error(f"打开传统翻译面板失败: {e}")
            InfoBar.error("错误", f"打开传统翻译面板失败: {e}", parent=self)
        
    def _go_step5(self):
        self.current_step = 5
        self.stacked.setCurrentIndex(4)
        self.step5_page.progress_bar.setValue(100)

    def _start_auto_hook_supplement(self):
        """主翻译完成后自动执行补全漏翻。"""
        try:
            from module.Config import Config

            if not self.game_dir:
                self._reset_auto_hook_state()
                return

            project_root = Path(self.game_dir)
            tl_name = self.tl_folder_edit.text().strip() or "chinese"
            tl_dir = project_root / "game" / "tl" / tl_name
            if not tl_dir.exists():
                InfoBar.warning("提示", f"未找到 tl 目录，已跳过自动补全：{tl_dir}", parent=self)
                self._reset_auto_hook_state()
                return

            self._sync_game_dir_to_config(self.game_dir)

            config = Config().load()
            config.input_folder = str(tl_dir)
            config.output_folder = str(tl_dir)
            config.renpy_game_folder = str(project_root)
            config.renpy_tl_folder = str(tl_dir)
            config.renpy_hook_translate = True
            config.renpy_source_translate = False

            self._auto_hook_running = True

            self.emit(
                Base.Event.TRANSLATION_START,
                {
                    "config": config,
                    "status": Base.TranslationStatus.UNTRANSLATED,
                    "input_folder": str(tl_dir),
                    "output_folder": str(tl_dir),
                    "source_language": config.source_language,
                    "target_language": config.target_language,
                },
            )
            InfoBar.success("已开始", "主翻译完成，正在自动补全漏翻…", parent=self)
        except Exception as e:
            self.logger.error(f"自动补全漏翻启动失败: {e}")
            InfoBar.error("错误", f"自动补全漏翻启动失败: {e}", parent=self)
            self._reset_auto_hook_state()

    def _reset_auto_hook_state(self):
        """重置自动补全漏翻相关状态。"""
        self._onekey_translation_started = False
        self._auto_hook_pending = False
        self._auto_hook_running = False

    def _on_translation_done(self, event, data):
        """监听翻译完成，按需接续 replace_text 补漏。"""
        if self._auto_hook_running:
            self._reset_auto_hook_state()
            InfoBar.success("完成", "自动补全漏翻完成", parent=self)
            return

        if self._onekey_translation_started and self._auto_hook_pending:
            self._auto_hook_pending = False
            QTimer.singleShot(0, self._start_auto_hook_supplement)
            return

        if self._onekey_translation_started:
            self._reset_auto_hook_state()

    def _on_translation_stop(self, event, data):
        """翻译停止时清理一键翻译的自动补漏状态。"""
        if self._onekey_translation_started or self._auto_hook_pending or self._auto_hook_running:
            self._reset_auto_hook_state()
    
    def _refresh_step4_ready(self) -> bool:
        """检查翻译前的必备配置"""
        from module.Config import Config
        cfg = Config().load()

        missing: list[str] = []
        input_dir = Path(cfg.input_folder) if cfg.input_folder else None
        output_dir = Path(cfg.output_folder) if cfg.output_folder else None

        if not input_dir or not input_dir.exists():
            missing.append("输入目录未设置或不存在")
        if not output_dir:
            missing.append("输出目录未设置")
        elif input_dir and output_dir and input_dir.exists():
            try:
                if output_dir.resolve() == input_dir.resolve():
                    missing.append("输入/输出目录不能相同")
            except Exception:
                pass
        if output_dir and not output_dir.exists():
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                missing.append("输出目录无法创建")

        platform_ready = False
        if cfg.platforms:
            for p in cfg.platforms:
                if p.get("id") == cfg.activate_platform:
                    platform_ready = True
                    break
        if not platform_ready:
            missing.append("未激活翻译接口（请在接口设置启用平台）")

        ready = len(missing) == 0
        if ready:
            self.step4_status.setText("✔ 已准备好翻译，可直接开始。")
            self.step4_status.setStyleSheet("color: #27ae60;")
            self.start_trans_btn.setEnabled(True)
        else:
            self.step4_status.setText("⚠ 需先完成配置：\n" + "\n".join(missing))
            self.step4_status.setStyleSheet("color: #e67e22;")
            self.start_trans_btn.setEnabled(False)
        return ready
    
    def _go_previous_step(self, current_step: int):
        """返回上一步"""
        if current_step <= 1:
            # 步骤1返回到工具箱
            self._exit_wizard()
        else:
            # 返回上一步
            self.current_step = current_step - 1
            self.stacked.setCurrentIndex(current_step - 2)  # index 从 0 开始
        
    def _exit_wizard(self):
        """退出向导，返回工具箱页面"""
        # 先返回工具箱页面
        returned = False
        if hasattr(self, 'window') and self.window:
            if hasattr(self.window, 'stackedWidget'):
                for i in range(self.window.stackedWidget.count()):
                    widget = self.window.stackedWidget.widget(i)
                    # 兼容旧版 RenpyToolkitPage 和新版 renpy_toolbox_page
                    if widget.objectName() in ("RenpyToolkitPage", "renpy_toolbox_page"):
                        self.window.stackedWidget.setCurrentWidget(widget)
                        returned = True
                        break
        
        # 重置状态（为下次使用做准备）
        self.current_step = 1
        self.stacked.setCurrentIndex(0)
        self.step1_next_btn.setEnabled(False)
        self.skip_extract_btn.setVisible(False)
        self.game_path = ""
        self.game_dir = ""
        self.game_path_edit.clear()
        self.path_status_label.setText("")
        self.old_translation_card.setVisible(False)
        self.has_old_translation = False
        
    # 工具函数
    def _tool_apply_translation(self, card):
        """应用翻译：将输出目录的文件复制到 tl 目录"""
        from module.Config import Config
        import shutil
        from qfluentwidgets import MessageBox
        from pathlib import Path
        
        config = Config().load()
        
        # 验证路径
        incremental_output = self._incremental_output_dir
        output_dir, input_dir = resolve_translation_apply_paths(
            config, incremental_output, self._apply_target_dir
        )
        
        if not output_dir.exists():
            InfoBar.error("错误", f"输出目录不存在：{output_dir}", parent=self)
            return
        
        if not input_dir.exists():
            InfoBar.error("错误", f"目标目录不存在：{input_dir}", parent=self)
            return
        
        # 统计文件
        output_files = list(output_dir.rglob("*.rpy"))
        if not output_files:
            InfoBar.warning("提示", "输出目录中没有翻译文件（.rpy）", parent=self)
            return
        
        # 确认对话框 - 根据主题选择样式颜色
        code_bg = "#2d2d2d" if isDarkTheme() else "#f5f5f5"
        warn_color = "#e67e22" if isDarkTheme() else "#d35400"
        
        msg_box = MessageBox(
            "确认应用翻译",
            f"<b>即将应用翻译到游戏</b><br><br>"
            f"<b>源目录：</b><br><code style='background:{code_bg};padding:2px 4px;'>{output_dir}</code><br><br>"
            f"<b>目标目录：</b><br><code style='background:{code_bg};padding:2px 4px;'>{input_dir}</code><br><br>"
            f"<b>文件数量：</b>{len(output_files)} 个<br><br>"
            f"<p style='color:{warn_color};'><i>⚠️ 这将覆盖目标目录中的同名文件！<br>"
            f"建议先备份原始文件。</i></p>",
            self
        )
        msg_box.yesButton.setText("应用翻译")
        msg_box.cancelButton.setText("取消")
        
        if not msg_box.exec():
            return
        
        # Apply translated incremental files through the semantic merger.  A
        # delta file contains only selected entries and must never overwrite the
        # complete target file byte-for-byte.
        if incremental_output:
            try:
                tl_name = self.tl_folder_edit.text().strip() or "chinese"
                merge_result = self.unified_extractor.merge_incremental_folder(
                    self.game_dir,
                    tl_name,
                    output_dir,
                    clean_duplicates=True,
                )
                if not merge_result.success:
                    InfoBar.warning("合并失败", merge_result.message, parent=self)
                    return
                staging_input = getattr(self, "_incremental_dir", None)
                if staging_input and Path(staging_input).exists():
                    shutil.rmtree(str(staging_input), ignore_errors=True)
                self._incremental_dir = None
                self._incremental_output_dir = None
                self._apply_target_dir = None
                InfoBar.success("应用成功", merge_result.message, duration=5000, parent=self)
                return
            except Exception as e:
                self.logger.error(f"应用增量翻译失败: {e}")
                InfoBar.error("错误", f"应用增量翻译失败：{e}", parent=self)
                return

        # Full translation mode keeps the legacy whole-file copy behavior.
        try:
            success_count = 0
            failed_files = []
            
            for file in output_files:
                try:
                    # 计算相对路径
                    rel_path = file.relative_to(output_dir)
                    target_file = input_dir / rel_path
                    
                    # 确保目标目录存在
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    
                    # 复制文件
                    shutil.copy2(file, target_file)
                    success_count += 1
                    
                except Exception as e:
                    failed_files.append((file.name, str(e)))
            
            # 显示结果
            if failed_files:
                msg = f"应用完成：成功 {success_count} 个，失败 {len(failed_files)} 个\n\n失败文件：\n"
                msg += "\n".join([f"- {name}: {err}" for name, err in failed_files[:5]])
                if len(failed_files) > 5:
                    msg += f"\n... 还有 {len(failed_files) - 5} 个"
                InfoBar.warning("部分成功", msg, duration=5000, parent=self)
            else:
                InfoBar.success(
                    "应用成功",
                    f"已成功应用 {success_count} 个翻译文件到游戏目录！\n"
                    f"现在可以启动游戏查看翻译效果。",
                    duration=5000,
                    parent=self
                )
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            InfoBar.error("错误", f"应用翻译失败：{e}", parent=self)

    def _tool_hook_supplement(self, card):
        """打开补全漏翻页面，并沿用当前项目上下文。"""
        try:
            from module.Config import Config
            from frontend.RenpyToolbox.HookSupplementPage import HookSupplementPage

            config = Config().load()
            if self.game_dir:
                self._sync_game_dir_to_config(self.game_dir)
                config = Config().load()

            if not hasattr(self.window, "hook_supplement_page"):
                self.window.hook_supplement_page = HookSupplementPage("hook-supplement", self.window)

            if hasattr(self.window, "navigate_to_page"):
                self.window.navigate_to_page(self.window.hook_supplement_page)
            elif hasattr(self.window, "stackedWidget"):
                if self.window.hook_supplement_page not in [
                    self.window.stackedWidget.widget(i)
                    for i in range(self.window.stackedWidget.count())
                ]:
                    self.window.stackedWidget.addWidget(self.window.hook_supplement_page)
                self.window.stackedWidget.setCurrentWidget(self.window.hook_supplement_page)
            else:
                InfoBar.info("提示", "已准备好补全翻译参数，请从工具箱打开“补全翻译”", parent=self)
        except Exception as e:
            self.logger.error(f"打开补全翻译页面失败: {e}")
            InfoBar.error("错误", f"打开补全翻译页面失败: {e}", parent=self)
    
    def _tool_fix_errors(self, card):
        # ... (Keep existing implementation or simplify)
        InfoBar.info("提示", "功能调用", parent=self)

    def _tool_set_default_lang(self, card):
        if hasattr(self.window, "navigate_to_page"):
            from frontend.RenpyToolbox.SetDefaultLanguagePage import SetDefaultLanguagePage
            # 传入项目目录（game 目录的上级）
            project_dir = self.game_dir if self.game_dir else None
            page = SetDefaultLanguagePage("set-default-language", self.window, project_dir=project_dir)
            self.window.navigate_to_page(page)

    def _tool_add_lang_switch(self, card):
        if hasattr(self.window, "navigate_to_page"):
            from frontend.RenpyToolbox.AddLanguageEntrancePage import AddLanguageEntrancePage
            # 传入 game 目录（不是 tl 目录）
            game_dir = str(Path(self.game_dir) / "game") if self.game_dir else None
            page = AddLanguageEntrancePage("add-language-entrance", self.window, game_dir=game_dir)
            self.window.navigate_to_page(page)

    def _tool_replace_font(self, card):
        if hasattr(self.window, "navigate_to_page"):
            from frontend.RenpyToolbox.FontReplacePage import FontReplacePage
            page = FontReplacePage("font-replace", self.window)
            self.window.navigate_to_page(page)

    def _tool_open_game_dir(self, card):
        if self.game_dir:
            os.startfile(self.game_dir)
            
    def _tool_export_patch(self, card):
        # ...
        pass
    
    def _tool_view_glossary(self, card):
        self._open_local_glossary()


# 兼容旧引用
OneKeyTranslatePage = YiJianFanyiPage
__all__ = ["YiJianFanyiPage", "OneKeyTranslatePage"]
