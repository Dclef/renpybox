"""
YiJianFanyiPage - 一键翻译向导页面
向导式分步骤流程：每次只显示一个进度页面，完成后自动进入下一步
"""

import os
import uuid
from pathlib import Path
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFileDialog,
    QStackedWidget,
    QSizePolicy,
    QProgressDialog,
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
    ProgressBar,
    ProgressRing,
    TitleLabel,
    ComboBox,
    LineEdit,
    CheckBox,
    TransparentToolButton,
    isDarkTheme,
    StrongBodyLabel,
)

from base.Base import Base
from base.LogManager import LogManager
from widget.Separator import Separator
from widget.ItemCard import ItemCard
from widget.ThemeHelper import mark_toolbox_widget, mark_toolbox_scroll_area
from module.Extract.PatchGenerator import generate_patch
from module.Extract.UnifiedExtractor import UnifiedExtractor
from module.Renpy.ProjectPaths import (
    RenpyProjectPaths,
    source_script_counts,
)
from module.Project.ProjectStore import ProjectStore
from module.Engine.Translator.ProjectAssetsRepository import ProjectAssetsRepository
from module.Engine.Engine import Engine
from module.Config import Config
from module.Localizer.Localizer import Localizer
from frontend.RenpyToolbox.PackUnpackPage import DecompileWorker, UnpackWorker
from frontend.TranslationPage import TranslationPage




from frontend.RenpyToolbox.OneKeyNameService import OneKeyNameService
from frontend.RenpyToolbox.OneKeyWorkers import (
    ApplyTranslationWorker,
    _cache_item_identity as _cache_item_identity,
    _numbered_disk_identity as _numbered_disk_identity,
    ExtractionWorker,
    apply_translation_files_transactionally as apply_translation_files_transactionally,
    configure_incremental_translation_paths,
    configure_main_translation_paths,
    _remember_translation_run,
    configure_tl_translation_mode,
    merge_incremental_translation_cache as merge_incremental_translation_cache,
    preserve_incremental_translation_cache,
    resolve_translation_apply_paths,
)

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
        self._extraction_generation = 0
        self._preprocess_worker = None
        self.has_old_translation = False  # 是否检测到旧翻译
        self.incremental_mode = False     # 是否使用增量抽取
        # 一键翻译结束后，按需串起“自动补全漏翻”流程
        self._onekey_translation_started = False
        self._onekey_translation_completed = False
        self._onekey_request_id = ""
        self._onekey_run_id = None
        self._auto_hook_pending = False
        self._auto_hook_running = False
        self._incremental_dir = None
        self._incremental_output_dir = None
        self._apply_target_dir = None
        self._last_onekey_output_dir = None
        self._apply_running = False  # 防止“应用翻译到游戏”重入
        self._apply_worker = None
        self._apply_card = None
        self._apply_parent = None
        self._apply_project_paths = None
        self._apply_progress_dialog = None
        self._start_translation_after_extraction = False
        self._agent_direct_start = False
        # 自动 hook 临时把配置指向 game/tl；完成后恢复主输出，但保留
        # 最近运行清单指向 hook 缓存，供校对页继续载入。
        self._hook_restore_paths = None
        
        self._init_ui()
        self.subscribe(Base.Event.TRANSLATION_DONE, self._on_translation_done)
        self.subscribe(Base.Event.TRANSLATION_STOP, self._on_translation_stop)
        self.subscribe(
            Base.Event.TRANSLATION_START_RESULT,
            self._on_translation_start_result,
        )
    
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
            back_btn.setToolTip(Localizer.get().onekey_back_toolbox)
            back_btn.clicked.connect(self._exit_wizard)
        else:
            back_btn.setToolTip(Localizer.get().onekey_previous_step)
            # 使用 lambda 捕获当前 step 值
            back_btn.clicked.connect(lambda checked, s=step: self._go_previous_step(s))
        header_layout.addWidget(back_btn)
        
        title_label = TitleLabel(
            Localizer.get().onekey_step_5.format(step=step, title=title)
        )
        header_layout.addWidget(title_label)
        header_layout.addStretch(1)
        
        if step > 1:
            exit_btn = PushButton(Localizer.get().onekey_exit_wizard)
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
        page, layout = self._create_page_container(
            Localizer.get().onekey_select_game,
            1,
        )
        
        # 提示文字 - 更友好的说明
        tip_card = CardWidget()
        tip_layout = QVBoxLayout(tip_card)
        tip_layout.setContentsMargins(12, 12, 12, 12)
        tip_layout.setSpacing(6)
        
        tip_title = StrongBodyLabel(
            Localizer.get().onekey_quick_start
        )
        tip_layout.addWidget(tip_title)
        
        tip_text = CaptionLabel(
            Localizer.get().onekey_1_select_game_folder_contains_game_subfolder
        )
        tip_text.setStyleSheet("color: #666; line-height: 1.5;")
        tip_text.setWordWrap(True)
        tip_layout.addWidget(tip_text)
        layout.addWidget(tip_card)
        
        # 游戏路径输入框（支持直接粘贴）
        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        
        self.game_path_edit = LineEdit()
        self.game_path_edit.setPlaceholderText(
            Localizer.get().onekey_enter_paste_game_folder_path_example_d
        )
        self.game_path_edit.textChanged.connect(self._on_path_text_changed)
        path_row.addWidget(self.game_path_edit, 1)
        
        self.browse_btn = PushButton(Localizer.get().onekey_browse)
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
        
        self.old_trans_title = StrongBodyLabel(
            Localizer.get().onekey_existing_translation_detected
        )
        old_trans_layout.addWidget(self.old_trans_title)
        
        self.old_trans_desc = CaptionLabel(
            Localizer.get().onekey_game_already_has_translation_files_choose_how
        )
        self.old_trans_desc.setWordWrap(True)
        old_trans_layout.addWidget(self.old_trans_desc)

        # 选项文本采用“短标题 + 说明”两行布局，避免窗口较窄时勾选框文本重叠
        self.incremental_rb = CheckBox(
            Localizer.get().onekey_incremental_extraction_recommended
        )
        self.incremental_rb.setChecked(True)
        old_trans_layout.addWidget(self.incremental_rb)
        incremental_desc = CaptionLabel(
            Localizer.get().onekey_keep_existing_translations_extract_new_untranslated_entries
        )
        incremental_desc.setWordWrap(True)
        incremental_desc.setStyleSheet("padding-left: 28px; color: #666;")
        old_trans_layout.addWidget(incremental_desc)

        self.full_extract_rb = CheckBox(
            Localizer.get().onekey_full_extraction_start_over
        )
        self.full_extract_rb.setChecked(False)
        self.full_extract_rb.setToolTip(
            Localizer.get().onekey_backs_up_regenerates_tl_lang_existing_placeholders
        )
        old_trans_layout.addWidget(self.full_extract_rb)
        full_extract_desc = CaptionLabel(
            Localizer.get().onekey_back_up_old_translation_extract_everything_again
        )
        full_extract_desc.setWordWrap(True)
        full_extract_desc.setStyleSheet("padding-left: 28px; color: #666;")
        old_trans_layout.addWidget(full_extract_desc)
        
        tip_label = CaptionLabel(
            Localizer.get().onekey_tip_incremental_extraction_protects_existing_translations_use
        )
        tip_label.setWordWrap(True)
        old_trans_layout.addWidget(tip_label)

        self.auto_merge_cleanup_chk = CheckBox(
            Localizer.get().onekey_merge_automatically_remove_duplicates_after_extraction
        )
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

        options_title = StrongBodyLabel(
            Localizer.get().onekey_advanced_options
        )
        options_layout.addWidget(options_title)

        from module.Config import Config
        config = Config().load()

        self.inject_base_box_chk = CheckBox(
            Localizer.get().onekey_inject_ui_translation_pack_base_box
        )
        self.inject_base_box_chk.setChecked(getattr(config, "onekey_inject_base_box", False))
        self.inject_base_box_chk.setToolTip(
            Localizer.get().onekey_injects_bundled_ui_translations_start_save_settings
        )
        self.inject_base_box_chk.stateChanged.connect(self._on_inject_base_box_changed)
        options_layout.addWidget(self.inject_base_box_chk)

        self.verify_uppercase_chk = CheckBox(
            Localizer.get().onekey_review_untranslated_uppercase_abbreviations_uses_additional_quota
        )
        self.verify_uppercase_chk.setChecked(
            getattr(config, "renpy_verify_uppercase_candidates", True)
        )
        self.verify_uppercase_chk.stateChanged.connect(
            self._on_verify_uppercase_changed
        )
        options_layout.addWidget(self.verify_uppercase_chk)

        self.clear_declined_btn = PushButton(
            Localizer.get().onekey_clear_skipped_candidates,
            icon=FluentIcon.DELETE,
        )
        self.clear_declined_btn.clicked.connect(self._clear_declined_candidates)
        options_layout.addWidget(self.clear_declined_btn)

        layout.addWidget(options_card)

        layout.addSpacing(20)        # 语言设置（简化）
        layout.addWidget(
            SubtitleLabel(
                Localizer.get().onekey_translation_languages
            )
        )
        
        lang_row = QHBoxLayout()
        lang_row.setSpacing(20)
        
        # 源语言
        src_layout = QVBoxLayout()
        src_layout.setSpacing(4)
        src_layout.addWidget(
            CaptionLabel(Localizer.get().onekey_source_language)
        )
        self.src_lang_combo = ComboBox()
        self.src_lang_combo.addItems(
            [
                Localizer.get().direct_rpy_english,
                Localizer.get().direct_rpy_japanese,
                Localizer.get().direct_rpy_korean,
                Localizer.get().onekey_russian,
                Localizer.get().onekey_other,
            ]
        )
        self.src_lang_combo.setFixedWidth(150)
        src_layout.addWidget(self.src_lang_combo)
        lang_row.addLayout(src_layout)
        
        # 目标语言
        tgt_layout = QVBoxLayout()
        tgt_layout.setSpacing(4)
        tgt_layout.addWidget(
            CaptionLabel(Localizer.get().onekey_target_language)
        )
        self.tgt_lang_combo = ComboBox()
        self.tgt_lang_combo.addItems(
            [
                Localizer.get().direct_rpy_simplified_chinese,
                Localizer.get().direct_rpy_traditional_chinese,
                Localizer.get().direct_rpy_japanese,
                Localizer.get().direct_rpy_english,
            ]
        )
        self.tgt_lang_combo.setFixedWidth(150)
        tgt_layout.addWidget(self.tgt_lang_combo)
        lang_row.addLayout(tgt_layout)
        
        # TL 文件夹名（折叠/隐藏给高级用户）
        tl_layout = QVBoxLayout()
        tl_layout.setSpacing(4)
        tl_layout.addWidget(
            CaptionLabel(Localizer.get().onekey_tl_folder_name)
        )
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
        self.quick_tip_label = CaptionLabel(
            Localizer.get().onekey_click_extract_text_begin_existing_translations_preserved
        )
        self.quick_tip_label.setWordWrap(True)
        layout.addWidget(self.quick_tip_label)
        
        # 跳过抽取按钮（已有翻译时显示）
        self.skip_extract_btn = PushButton(
            Localizer.get().onekey_skip_extraction_translate
        )
        self.skip_extract_btn.clicked.connect(self._skip_to_translate)
        self.skip_extract_btn.setVisible(False)  # 默认隐藏，检测到翻译后显示
        next_row.addWidget(self.skip_extract_btn)
        
        self.step1_next_btn = PrimaryPushButton(
            Localizer.get().onekey_extract_text
        )
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
        
        selected_paths = RenpyProjectPaths.from_path(
            text,
            self.tl_folder_edit.text().strip() if hasattr(self, "tl_folder_edit") else "chinese",
        )
        if os.path.isdir(text):
            # 检查是否是有效的 Ren'Py 游戏目录
            game_subdir = str(selected_paths.game_dir) if selected_paths else os.path.join(text, "game")
            if os.path.isdir(game_subdir):
                self.game_dir = str(selected_paths.project_root if selected_paths else Path(text))
                self.game_path = self.game_dir
                self._sync_game_dir_to_config(self.game_dir)
                self.path_status_label.setText(
                    Localizer.get().onekey_valid_ren_py_game_folder_detected
                )
                self.path_status_label.setStyleSheet("color: #27ae60;")
                self.step1_next_btn.setEnabled(True)
                # 检测旧翻译
                self._check_old_translation(self.game_dir)
            else:
                self.path_status_label.setText(
                    Localizer.get().onekey_no_game_subfolder_found_may_not_ren
                )
                self.path_status_label.setStyleSheet("color: #e67e22;")
                # 仍然允许继续
                self.game_dir = str(selected_paths.project_root if selected_paths else Path(text))
                self.game_path = self.game_dir
                self._sync_game_dir_to_config(self.game_dir)
                self.step1_next_btn.setEnabled(True)
                self.old_translation_card.setVisible(False)
                self.has_old_translation = False
        elif os.path.isfile(text):
            self.game_dir = str(selected_paths.project_root if selected_paths else Path(text).parent)
            self.game_path = text
            self._sync_game_dir_to_config(self.game_dir)
            self.path_status_label.setText(
                Localizer.get().onekey_game_file_selected
            )
            self.path_status_label.setStyleSheet("color: #27ae60;")
            self.step1_next_btn.setEnabled(True)
            # 检测旧翻译
            self._check_old_translation(self.game_dir)
        else:
            self.path_status_label.setText(
                Localizer.get().onekey_path_does_not_exist
            )
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

        config = Config().load()
        # 设置 tl 目录路径
        tl_name = getattr(self, 'tl_folder_edit', None)
        tl_name = tl_name.text().strip() if tl_name else "chinese"
        if not tl_name:
            tl_name = "chinese"

        paths = RenpyProjectPaths.from_path(game_dir, tl_name)
        if paths is None:
            raise ValueError(f"无法解析项目目录：{game_dir}")
        ProjectStore.get().apply_resolved(
            config,
            paths,
            mutate = configure_tl_translation_mode,
        )

        # 确保输出目录存在
        paths.translation_output_dir.mkdir(parents = True, exist_ok = True)

        self.info(f"[配置] 输入目录: {config.input_folder}")
        self.info(f"[配置] 输出目录: {config.output_folder}")
    
    def _check_old_translation(self, game_dir):
        """检测是否有旧翻译"""
        tl_name = self.tl_folder_edit.text().strip() or "chinese"
        paths = RenpyProjectPaths.from_path(game_dir, tl_name)
        tl_dir = paths.tl_language_dir if paths is not None else Path(game_dir) / "game" / "tl" / tl_name
        
        if tl_dir.exists() and any(tl_dir.iterdir()):
            # 统计旧翻译文件数量
            rpy_count = len(list(tl_dir.rglob("*.rpy")))
            self.has_old_translation = True
            self.old_trans_title.setText(
                Localizer.get().onekey_existing_translation_detected_files.format(rpy_count=rpy_count)
            )
            self.old_trans_desc.setText(
                Localizer.get().onekey_translation_files_already_exist_tl_choose_how.format(tl_name=tl_name)
            )
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
        page, layout = self._create_page_container(
            Localizer.get().onekey_extract_text_2,
            2,
        )
        
        layout.addStretch(1)
        
        self.step2_status = TitleLabel(
            Localizer.get().onekey_ready_extract
        )
        self.step2_status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.step2_status)
        
        self.step2_desc = BodyLabel(
            Localizer.get().onekey_text_extracted_game_translation_files_when_finishes
        )
        self.step2_desc.setAlignment(Qt.AlignCenter)
        self.step2_desc.setWordWrap(True)
        layout.addWidget(self.step2_desc)
        
        layout.addStretch(1)
        
        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        
        # 重试按钮 (默认隐藏，失败后显示)
        self.step2_retry_btn = PushButton(
            Localizer.get().onekey_extract_again
        )
        self.step2_retry_btn.clicked.connect(self._retry_extraction)
        self.step2_retry_btn.setVisible(False)
        btn_row.addWidget(self.step2_retry_btn)

        self.step2_unpack_btn = PrimaryPushButton(
            Localizer.get().onekey_open_rpa_unpacker,
            icon=FluentIcon.ZIP_FOLDER,
        )
        self.step2_unpack_btn.clicked.connect(self._open_rpa_unpack)
        self.step2_unpack_btn.setVisible(False)
        btn_row.addWidget(self.step2_unpack_btn)
        
        # 跳过按钮 (失败时可跳过)
        self.step2_skip_btn = PushButton(
            Localizer.get().onekey_skip_step
        )
        self.step2_skip_btn.clicked.connect(self._go_step3)
        self.step2_skip_btn.setVisible(False)
        btn_row.addWidget(self.step2_skip_btn)
        
        # 下一步按钮 (默认隐藏，完成后显示)
        self.step2_next_btn = PrimaryPushButton(
            Localizer.get().onekey_next
        )
        self.step2_next_btn.clicked.connect(self._go_step3)
        self.step2_next_btn.setVisible(False)
        btn_row.addWidget(self.step2_next_btn)

        self.step2_merge_btn = PushButton(
            Localizer.get().onekey_merge_remove_duplicates
        )
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
        self.step2_unpack_btn.setVisible(False)
        self._go_step2()

    def _get_tool_page(self, key: str) -> QWidget:
        """从工具箱的集中缓存获取工具页。"""
        toolbox = getattr(self.window, "renpy_toolbox_page", None)
        if toolbox is None:
            raise RuntimeError("未找到 Ren'Py 工具箱页面")
        return toolbox.get_tool_page(key)

    def _open_rpa_unpack(self) -> None:
        """打开 RPA 解包页并带入当前项目的 game 目录。"""
        if self.window is None or not self.game_dir:
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.get().onekey_select_valid_game_folder_first,
                parent=self,
            )
            return

        page = self._get_tool_page("pack_unpack")

        if not page.set_game_directory(self.game_dir):
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.get().onekey_could_not_locate_game_s_game_folder,
                parent=self,
            )
            return

        self.window.navigate_to_page(page)

    def _on_auto_merge_cleanup_changed(self, state: int):
        """同步自动合并开关到配置"""
        try:
            from module.Config import Config
            config = Config().load()
            config.renpy_incremental_auto_merge_cleanup = bool(state)
            config.save()
        except Exception as exc:
            self.logger.warning(f"保存自动合并配置失败: {exc}")

    def _on_verify_uppercase_changed(self, state: int):
        """同步大写缩写二次确认开关到配置。"""
        try:
            from module.Config import Config

            config = Config().load()
            config.renpy_verify_uppercase_candidates = bool(state)
            config.save()
        except Exception as exc:
            self.logger.warning(f"保存大写缩写二次确认配置失败: {exc}")

    def _clear_declined_candidates(self):
        """确认后清除当前项目的判定不译清单。"""
        if not self.game_dir:
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.get().onekey_select_game_folder_first,
                parent=self,
            )
            return

        from qfluentwidgets import MessageBox
        from module.Extract.ReplaceGenerator import clear_declined_candidates

        msg_box = MessageBox(
            Localizer.get().onekey_clear_skipped_candidates_2,
            Localizer.get().onekey_these_terms_translated_again_during_next_run,
            self,
        )
        msg_box.yesButton.setText(Localizer.get().onekey_clear)
        msg_box.cancelButton.setText(Localizer.get().app_update_cancel)
        if not msg_box.exec():
            return

        tl_name = self.tl_folder_edit.text().strip() or "chinese"
        cleared = clear_declined_candidates(self.game_dir, tl_name)
        if cleared:
            InfoBar.success(
                Localizer.get().onekey_cleared,
                Localizer.get().onekey_cleared_skipped_candidates.format(cleared=cleared),
                parent=self,
            )
        else:
            InfoBar.info(
                Localizer.get().notice,
                Localizer.get().onekey_there_no_skipped_candidates,
                parent=self,
            )

    def _merge_incremental_dir(self):
        """合并增量目录并清理重复"""
        try:
            # 新流程必须先翻译到独立输出目录，再由“应用翻译”语义合并。
            # 禁止旧入口提前合并并删除仍作为翻译输入的 chinese_new。
            if self._incremental_output_dir:
                InfoBar.warning(
                    Localizer.get().onekey_finish_translation_first,
                    Localizer.get().onekey_incremental_content_has_not_been_applied_finish,
                    parent=self,
                )
                return
            if not self.game_dir:
                InfoBar.warning(
                    Localizer.get().notice,
                    Localizer.get().onekey_select_game_folder_first,
                    parent=self,
                )
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
                InfoBar.success(
                    Localizer.get().onekey_merge_completed,
                    Localizer.get().onekey_incremental_files_merged,
                    parent=self,
                )
            else:
                InfoBar.warning(
                    Localizer.get().onekey_merge_failed,
                    Localizer.get().onekey_incremental_files_merge_failed,
                    parent=self,
                )
        except Exception as exc:
            self.logger.error(f"合并失败: {exc}")
            InfoBar.error(
                Localizer.get().error,
                str(exc),
                parent=self,
            )
    
    # ==================== 进度三：术语表 ====================
    def _create_step3_page(self):
        """进度三：项目资产与术语表。"""
        page, layout = self._create_page_container(
            Localizer.get().onekey_terms_translation_context,
            3,
        )
        
        layout.addWidget(
            SubtitleLabel(
                Localizer.get().onekey_glossary_do_not_translate_list
            )
        )
        layout.addWidget(
            BodyLabel(
                Localizer.get().onekey_glossary_keeps_proper_names_consistent_while_do
            )
        )
        
        layout.addSpacing(16)
        
        self.glossary_info_label = BodyLabel(
            Localizer.get().onekey_looking_glossary_files_project
        )
        layout.addWidget(self.glossary_info_label)
        
        layout.addSpacing(16)
        
        btn_row = QHBoxLayout()
        self.open_glossary_btn = PushButton(
            Localizer.get().onekey_open_local_glossary
        )
        self.open_glossary_btn.setToolTip(
            Localizer.get().onekey_use_scan_term_candidates_local_glossary_find
        )
        self.open_glossary_btn.clicked.connect(self._open_local_glossary)
        btn_row.addWidget(self.open_glossary_btn)
        
        self.open_preserve_btn = PushButton(
            Localizer.get().onekey_open_do_not_translate_list
        )
        self.open_preserve_btn.clicked.connect(self._open_text_preserve)
        btn_row.addWidget(self.open_preserve_btn)
        
        self.scan_names_btn = PushButton(
            Localizer.get().onekey_extract_character_names
        )
        self.scan_names_btn.clicked.connect(self._scan_character_names)
        btn_row.addWidget(self.scan_names_btn)

        self.open_workbench_btn = PushButton(
            Localizer.get().onekey_open_character_world_workbench
        )
        self.open_workbench_btn.setToolTip(
            Localizer.get().onekey_manage_worldbook_character_cards_translation_creates_immutable
        )
        self.open_workbench_btn.clicked.connect(self._open_workbench_from_onekey)
        btn_row.addWidget(self.open_workbench_btn)
        
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.workbench_asset_status = BodyLabel(
            Localizer.get().onekey_loading_project_assets
        )
        self.workbench_asset_status.setWordWrap(True)
        layout.addWidget(self.workbench_asset_status)
        
        layout.addStretch(1)
        
        next_row = QHBoxLayout()
        next_row.addStretch(1)
        self.step3_next_btn = PrimaryPushButton(
            Localizer.get().onekey_next_start_translation
        )
        self.step3_next_btn.clicked.connect(self._go_step4)
        next_row.addWidget(self.step3_next_btn)
        layout.addLayout(next_row)
        
        self.step3_page = page
        self.stacked.addWidget(page)
    
    # ==================== 进度四：开始翻译 ====================
    def _create_step4_page(self):
        """进度四：开始翻译"""
        page, layout = self._create_page_container(
            Localizer.get().onekey_run_ai_translation,
            4,
        )
        
        layout.addWidget(
            SubtitleLabel(Localizer.get().onekey_ready_translate)
        )
        self.step4_status = BodyLabel(
            Localizer.get().onekey_translation_files_written_separate_folder_under_game
        )
        layout.addWidget(self.step4_status)
        
        layout.addSpacing(20)
        
        # 翻译按钮
        btn_row = QHBoxLayout()
        self.start_trans_btn = PrimaryPushButton(
            Localizer.get().onekey_start_translation
        )
        self.start_trans_btn.clicked.connect(self._on_start_translate_clicked)
        btn_row.addWidget(self.start_trans_btn)

        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        from module.Config import Config
        auto_hook_row = QHBoxLayout()
        self.auto_hook_supplement_chk = CheckBox(
            Localizer.get().onekey_recover_missed_text_after_translation_replace_text
        )
        self.auto_hook_supplement_chk.setChecked(
            getattr(Config().load(), "onekey_auto_hook_supplement", False)
        )
        self.auto_hook_supplement_chk.setToolTip(
            Localizer.get().onekey_disabled_default_when_enabled_second_pass_generates
        )
        self.auto_hook_supplement_chk.stateChanged.connect(self._on_auto_hook_supplement_changed)
        auto_hook_row.addWidget(self.auto_hook_supplement_chk)
        auto_hook_row.addStretch(1)
        layout.addLayout(auto_hook_row)
        
        layout.addStretch(1)
        
        # 底部按钮
        action_row = QHBoxLayout()
        action_row.addStretch(1)
        
        self.skip_trans_btn = PushButton(
            Localizer.get().onekey_skip_translation
        )
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
        page, layout = self._create_page_container(
            Localizer.get().onekey_review_export_post_process,
            5,
        )
        
        layout.addWidget(
            SubtitleLabel(
                Localizer.get().onekey_translation_complete
            )
        )
        layout.addWidget(
            BodyLabel(
                Localizer.get().onekey_you_can_now_review_complete_export_translation
            )
        )
        layout.addWidget(
            CaptionLabel(
                Localizer.get().onekey_if_text_still_untranslated_game_use_recover
            )
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
        flow_layout.setHorizontalSpacing(8)
        flow_layout.setVerticalSpacing(8)
        flow_layout.setContentsMargins(0, 0, 0, 0)
        
        # 工具卡片
        tools = [
            (
                Localizer.get().onekey_review_polish_export,
                Localizer.get().onekey_review_quality_reports_edit_selected_translations_export,
                self._tool_open_proofreading,
            ),
            (
                Localizer.get().onekey_recover_missed_text,
                Localizer.get().onekey_find_text_missing_tl_generate_replace_text,
                self._tool_hook_supplement,
            ),
            (
                Localizer.get().onekey_detect_repair_errors,
                Localizer.get().onekey_fix_indentation_formatting_issues,
                self._tool_fix_errors,
            ),
            (
                Localizer.get().onekey_set_default_language,
                Localizer.get().onekey_set_language_used_when_game_starts,
                self._tool_set_default_lang,
            ),
            (
                Localizer.get().onekey_add_language_switch,
                Localizer.get().onekey_inject_language_switching_button,
                self._tool_add_lang_switch,
            ),
            (
                Localizer.get().onekey_inject_fonts,
                Localizer.get().onekey_inject_bundled_font_pack,
                self._tool_replace_font,
            ),
            (
                Localizer.get().onekey_open_game_folder,
                Localizer.get().onekey_view_translation_results,
                self._tool_open_game_dir,
            ),
            (
                Localizer.get().onekey_export_language_patch,
                Localizer.get().onekey_export_tl_folder_zip_archive,
                self._tool_export_patch,
            ),
        ]
        
        for title, desc, func in tools:
            card = ItemCard(parent=self, title=title, description=desc, clicked=func)
            card.title_button.setToolTip(
                Localizer.get().onekey_open.format(title=title)
            )
            flow_layout.addWidget(card)
        
        scroll_layout.addWidget(flow_container)
        scroll_layout.addStretch(1)
        
        scroll_area.setWidget(scroll_widget)
        layout.addWidget(scroll_area)
        
        self.step5_page = page
        self.stacked.addWidget(page)

    # ==================== 逻辑处理 ====================
    
    def _select_game_dir(self):
        """浏览选择游戏目录"""
        dir_path = QFileDialog.getExistingDirectory(
            self,
            Localizer.get().onekey_select_game_folder,
            "",
        )
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
        
        paths = RenpyProjectPaths.from_path(
            game_dir,
            self.tl_folder_edit.text().strip() or "chinese",
        )
        if paths is None or not paths.game_dir.exists():
            return 'empty', Localizer.get().onekey_game_folder_not_found

        rpy_count, rpyc_count = source_script_counts(paths)
        rpa_count = len(list(paths.game_dir.glob("*.rpa")))
        
        if rpa_count > 0 and rpy_count == 0 and rpyc_count == 0:
            return 'need_unpack', Localizer.get().onekey_found_rpa_archives_must_unpacked.format(rpa_count=rpa_count)
        
        if rpyc_count > 0:
            return 'need_decompile', Localizer.get().onekey_found_rpyc_files_must_decompiled.format(rpyc_count=rpyc_count)
        
        if rpy_count > 0:
            return 'ready', Localizer.get().onekey_found_rpy_files_ready_extraction.format(rpy_count=rpy_count)
        
        return 'empty', Localizer.get().onekey_no_extractable_files_found

    def _show_step2_unpack_failure(self, message: str) -> None:
        """解包失败后的统一界面状态：可重试、可跳过、可转手动解包页。"""
        self.step2_page.progress_ring.setVisible(False)
        self.step2_status.setText(
            Localizer.get().onekey_unpack_failed
        )
        self.step2_desc.setText(message)
        self.step2_unpack_btn.setVisible(True)
        self.step2_unpack_btn.setEnabled(True)
        self.step2_retry_btn.setVisible(True)
        self.step2_skip_btn.setVisible(True)
        self.step2_retry_btn.setEnabled(True)
        self.step2_skip_btn.setEnabled(True)
        InfoBar.warning(
            Localizer.get().notice,
            Localizer.get().onekey_unpack_failed_check_game_files,
            parent=self,
        )

    def _show_step2_decompile_failure(self, message: str) -> None:
        """反编译失败后的统一界面状态。"""
        self.step2_page.progress_ring.setVisible(False)
        self.step2_status.setText(Localizer.get().onekey_decompilation_failed)
        self.step2_desc.setText(
            Localizer.get().onekey_possible_causes_game_uses_encryption_obfuscation_ren.format(
                decompile_msg=message,
            )
        )
        self.step2_retry_btn.setVisible(True)
        self.step2_skip_btn.setVisible(True)
        self.step2_retry_btn.setEnabled(True)
        self.step2_skip_btn.setEnabled(True)
        InfoBar.warning(
            Localizer.get().notice,
            Localizer.get().onekey_decompilation_failed_check_game_files,
            parent=self,
        )

    def _step2_context_is_current(self, generation: int, context: dict) -> bool:
        """确认回调仍属于当前页面、当前配置中的同一项目和语言。"""
        if generation != self._extraction_generation:
            return False

        project_key = str(context.get("project_key", "") or "")
        if not project_key:
            return False
        try:
            current_paths = RenpyProjectPaths.from_config(Config().load())
            page_paths = RenpyProjectPaths.from_path(
                self.game_dir,
                self.tl_folder_edit.text().strip() or "chinese",
            )
        except Exception:
            return False
        return bool(
            current_paths is not None
            and page_paths is not None
            and current_paths.project_key == project_key
            and page_paths.project_key == project_key
        )

    def _on_preprocess_progress(
        self,
        message: str,
        generation: int,
        context: dict,
    ) -> None:
        if self._step2_context_is_current(generation, context):
            self.step2_status.setText(message or "")

    def _start_unpack_worker(self, generation: int, context: dict) -> None:
        paths = RenpyProjectPaths.from_path(
            context["game_dir"],
            context["language"],
        )
        if paths is None:
            self._show_step2_unpack_failure(Localizer.get().onekey_game_folder_not_found)
            return

        worker = UnpackWorker(
            str(paths.game_dir),
            direct=True,
            script_only=False,
        )
        self._preprocess_worker = worker
        worker.progress.connect(
            lambda message, current=generation, snapshot=context: self._on_preprocess_progress(
                message,
                current,
                snapshot,
            )
        )
        worker.finished.connect(
            lambda result, current=generation, snapshot=context, source=worker: self._on_auto_unpack_finished(
                result,
                current,
                snapshot,
                source,
            )
        )
        worker.start()

    def _start_decompile_worker(self, generation: int, context: dict) -> None:
        worker = DecompileWorker(
            context["game_dir"],
            overwrite=False,
            fallback_unren_options="2x",
            use_unren=True,
        )
        self._preprocess_worker = worker
        worker.progress.connect(
            lambda message, current=generation, snapshot=context: self._on_preprocess_progress(
                message,
                current,
                snapshot,
            )
        )
        worker.finished.connect(
            lambda result, current=generation, snapshot=context, source=worker: self._on_auto_decompile_finished(
                result,
                current,
                snapshot,
                source,
            )
        )
        worker.start()

    def _on_auto_unpack_finished(
        self,
        result: dict,
        generation: int,
        context: dict,
        worker,
    ) -> None:
        if self._preprocess_worker is worker:
            self._preprocess_worker = None
        if not self._step2_context_is_current(generation, context):
            return

        result = result if isinstance(result, dict) else {}
        message = str(result.get("message", "") or "")
        if result.get("level") != "success":
            self._show_step2_unpack_failure(
                Localizer.get().onekey_unpack_failed_hint.format(unpack_msg=message)
            )
            return

        status, status_message = self._detect_game_status(context["game_dir"])
        if status in ("need_unpack", "empty"):
            self._show_step2_unpack_failure(
                Localizer.get().onekey_unpack_complete_no_scripts.format(
                    unpack_msg=message,
                )
            )
            return

        self.step2_desc.setText(message)
        self.step2_page.progress_bar.setValue(20)
        self._continue_step2(generation, context, status, status_message)

    def _on_auto_decompile_finished(
        self,
        result: dict,
        generation: int,
        context: dict,
        worker,
    ) -> None:
        if self._preprocess_worker is worker:
            self._preprocess_worker = None
        if not self._step2_context_is_current(generation, context):
            return

        result = result if isinstance(result, dict) else {}
        message = str(result.get("message", "") or "")
        if result.get("level") != "success":
            self._show_step2_decompile_failure(message)
            return

        status, status_message = self._detect_game_status(context["game_dir"])
        if status in ("need_decompile", "need_unpack", "empty"):
            self._show_step2_decompile_failure(status_message or message)
            return

        self.step2_desc.setText(message)
        self.step2_page.progress_bar.setValue(20)
        self._continue_step2(generation, context, status, status_message)

    def _go_step2(self):
        """进入步骤2并开始提取"""
        # 如果正在预处理或抽取，避免重复启动线程。
        if (
            self._preprocess_worker
            and self._preprocess_worker.isRunning()
        ) or (
            self.extraction_worker
            and self.extraction_worker.isRunning()
        ):
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.get().onekey_extraction_already_running_wait_finish,
                parent=self,
            )
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
        self.step2_unpack_btn.setVisible(False)
        self.step2_unpack_btn.setEnabled(False)
        self.step2_skip_btn.setVisible(False)
        self.step2_skip_btn.setEnabled(False)
        self.step2_merge_btn.setVisible(False)
        self.step2_merge_btn.setEnabled(False)
        self.step2_desc.setText(
            Localizer.get().onekey_extracting_text_game_creating_translation_files
        )
        self.step2_page.progress_bar.setValue(0)
        
        # 启动提取线程
        game_dir = self.game_dir
        tl_name = self.tl_folder_edit.text().strip() or "chinese"
        
        exe_guess = Path(game_dir) / "game.exe"
        exe_path = exe_guess if exe_guess.exists() else game_dir
        if self.game_path and os.path.isfile(self.game_path) and self.game_path.endswith(".exe"):
             exe_path = self.game_path
        
        paths = RenpyProjectPaths.from_path(game_dir, tl_name)
        self._extraction_generation += 1
        generation = self._extraction_generation
        context = {
            "game_dir": str(game_dir),
            "language": tl_name,
            "project_key": paths.project_key if paths is not None else "",
            "exe_path": exe_path,
            "incremental": bool(
                self.has_old_translation and self.incremental_rb.isChecked()
            ),
        }
        self.step2_status.setText(
            Localizer.get().onekey_checking_game_files
        )
        self.step2_page.progress_ring.setVisible(True)
        self.step2_page.progress_bar.setValue(5)

        self._continue_step2(generation, context)

    def _continue_step2(
        self,
        generation: int,
        context: dict,
        status: str | None = None,
        status_msg: str | None = None,
    ) -> None:
        """在同一项目快照内依次完成解包、反编译和文本提取。"""
        if not self._step2_context_is_current(generation, context):
            return

        if status is None:
            status, status_msg = self._detect_game_status(context["game_dir"])
        status_msg = str(status_msg or "")

        if status == 'need_unpack':
            self.step2_status.setText(
                Localizer.get().onekey_unpacking_rpa_archives
            )
            self.step2_desc.setText(
                status_msg
                + Localizer.get().onekey_running_rpa_unpacker_automatically
            )
            self.step2_page.progress_bar.setValue(10)

            self._start_unpack_worker(generation, context)
            return

        if status == 'need_decompile':
            self.step2_status.setText(
                Localizer.get().onekey_decompiling_rpyc_files
            )
            self.step2_desc.setText(
                status_msg
                + Localizer.get().onekey_running_decompiler_automatically
            )
            self.step2_page.progress_bar.setValue(10)

            self._start_decompile_worker(generation, context)
            return

        if status == 'empty':
            self.step2_page.progress_ring.setVisible(False)
            self.step2_status.setText(
                Localizer.get().onekey_game_files_not_found
            )
            self.step2_desc.setText(status_msg)
            self.step2_retry_btn.setVisible(True)
            self.step2_retry_btn.setEnabled(True)
            self.step2_skip_btn.setVisible(False)
            self.step2_skip_btn.setEnabled(False)
            return
        
        incremental = bool(context["incremental"])
        
        if incremental:
            self.step2_status.setText(
                Localizer.get().onekey_running_incremental_extraction
            )
        else:
            self.step2_status.setText(
                Localizer.get().onekey_extracting
            )
        self.step2_page.progress_ring.setVisible(True)
        
        self.extraction_worker = ExtractionWorker(
            self.unified_extractor,
            context["game_dir"],
            context["language"],
            context["exe_path"],
            incremental=incremental,
        )
        self.extraction_worker.progress.connect(
            lambda message, percent, current=generation: self._on_extract_progress(
                message,
                percent,
                current,
            )
        )
        self.extraction_worker.finished.connect(
            lambda success, message, result, current=generation, snapshot=context: self._on_extract_finished(
                success,
                message,
                result,
                current,
                snapshot,
            )
        )
        self.extraction_worker.start()

    def _on_extract_progress(self, msg, percent, generation=None):
        if generation is not None and generation != self._extraction_generation:
            return
        self.step2_status.setText(msg)
        self.step2_page.progress_bar.setValue(percent)
        
    def _on_extract_finished(
        self,
        success,
        msg,
        result=None,
        generation=None,
        context=None,
    ):
        if generation is not None and generation != self._extraction_generation:
            return

        game_dir = self.game_dir
        tl_name = self.tl_folder_edit.text().strip() or "chinese"
        if isinstance(context, dict):
            current_paths = RenpyProjectPaths.from_config(Config().load())
            page_paths = RenpyProjectPaths.from_path(game_dir, tl_name)
            project_key = str(context.get("project_key", "") or "")
            if (
                not project_key
                or current_paths is None
                or page_paths is None
                or current_paths.project_key != project_key
                or page_paths.project_key != project_key
            ):
                self._start_translation_after_extraction = False
                self._agent_direct_start = False
                self.extraction_worker = None
                self.step2_page.progress_ring.setVisible(False)
                self.step2_status.setText(
                    Localizer.get().onekey_project_changed_extract_again
                )
                self.step2_desc.setText(
                    Localizer.get().onekey_project_changed_extract_again
                )
                self.step2_retry_btn.setVisible(True)
                self.step2_retry_btn.setEnabled(True)
                return
            game_dir = str(context.get("game_dir", game_dir) or game_dir)
            tl_name = str(context.get("language", tl_name) or tl_name)

        self.step2_page.progress_ring.setVisible(False)
        if success:
            self.step2_status.setText(
                Localizer.get().onekey_extraction_complete
            )
            # 如果是增量抽取并且有单独的增量目录，显示更详细的信息
            if result and result.incremental_dir and result.incremental_dir.exists():
                detail_msg = (
                    Localizer.get().onekey_new_content_written_existing_translations_left_unchanged.format(msg=msg, name=result.incremental_dir.name)
                )
                self._incremental_dir = result.incremental_dir
                # 暂存目录需要保留到翻译完成；提前合并会删除它，
                # 导致翻译页面回退到完整的主语言目录。
                config = Config().load()
                apply_target, delta_output = configure_incremental_translation_paths(
                    config, game_dir, tl_name, result.incremental_dir
                )
                preserved_output = preserve_incremental_translation_cache(delta_output)
                delta_output.mkdir(parents=True, exist_ok=True)
                config.save()
                self._apply_target_dir = apply_target
                self._incremental_output_dir = delta_output
                self._last_onekey_output_dir = delta_output
                detail_msg += (
                    Localizer.get().onekey_incremental_input_incremental_output.format(name=result.incremental_dir.name, name_2=delta_output.name)
                )
                if preserved_output is not None:
                    detail_msg += (
                        Localizer.get().onekey_previous_incremental_cache_preserved_can_restored_manually.format(name=preserved_output.name)
                    )
            else:
                detail_msg = Localizer.get().onekey_placeholders_preserved_new_old_you_can_translate.format(msg=msg)
                self._incremental_dir = None
                self._incremental_output_dir = None
                self._apply_target_dir = None
                paths = RenpyProjectPaths.from_path(game_dir, tl_name)
                self._last_onekey_output_dir = (
                    paths.translation_output_dir if paths is not None else None
                )
            
            self.step2_desc.setText(detail_msg)
            self.step2_page.progress_bar.setValue(100)
            self.step2_next_btn.setVisible(True)
            self.step2_next_btn.setEnabled(True)
            self.step2_retry_btn.setVisible(True)
            self.step2_retry_btn.setEnabled(True)
            self.step2_skip_btn.setVisible(False)
            self.step2_skip_btn.setEnabled(False)
            self.step2_next_btn.setText(
                Localizer.get().onekey_start_translation_2
            )
            # 增量暂存目录是后续翻译输入，翻译前不能通过旧按钮直接合并或删除。
            self.step2_merge_btn.setVisible(False)
            self.step2_merge_btn.setEnabled(False)
            
            # 自动执行角色名和禁翻表扫描（仅第一次执行，避免重复卡顿）
            self._extract_character_names()
            
            InfoBar.success(
                Localizer.get().extract_json_success,
                Localizer.get().onekey_extraction_completed_character_names_variable_references_scanned,
                parent=self,
            )
            self._continue_agent_start_after_extraction()
        else:
            self.step2_status.setText(
                Localizer.get().onekey_extraction_failed
            )
            self.step2_desc.setText(
                Localizer.get().onekey_error_select_extract_again_if_still_fails.format(msg=msg)
            )
            self.step2_retry_btn.setVisible(True)
            self.step2_skip_btn.setVisible(True)
            self.step2_retry_btn.setEnabled(True)
            self.step2_skip_btn.setEnabled(True)
            self.step2_next_btn.setVisible(False)
            self.step2_next_btn.setEnabled(False)
            self.step2_merge_btn.setVisible(False)
            self.step2_merge_btn.setEnabled(False)
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.get().onekey_extraction_failed_you_can_try_again_skip,
                parent=self,
            )

    def _continue_agent_start_after_extraction(self) -> None:
        """Agent 发起的流程在提取成功后自动进入已有翻译确认。"""
        if not self._start_translation_after_extraction:
            return
        self._start_translation_after_extraction = False
        self._go_step4()
        QTimer.singleShot(0, self._on_start_translate_clicked)

    def _scan_character_names(self):
        """扫描角色候选并写入工作台，变量引用继续写入禁翻表。"""
        self._extract_character_names(force=True)
        InfoBar.success(
            Localizer.get().extract_json_success,
            Localizer.get().onekey_character_candidates_variable_references_scanned,
            parent=self,
        )

    def _extract_character_names(self, *, force: bool = False):
        """自动扫描角色候选、角色草稿和变量引用（识别逻辑在 OneKeyNameService）。"""
        OneKeyNameService.get().extract_character_names(
            self.game_dir,
            self.tl_folder_edit.text().strip(),
            force=force,
        )

    def _go_step3(self):
        self.current_step = 3
        self.stacked.setCurrentIndex(2)
        self._find_glossary_files()
        self._refresh_workbench_asset_status()

    def _refresh_workbench_asset_status(self) -> None:
        """显示与当前一键翻译项目绑定的工作台资产数量。"""
        label = getattr(self, "workbench_asset_status", None)
        if label is None:
            return
        try:
            config = Config().load()
            state = ProjectAssetsRepository.from_config(config).load(config)
            assets = state.assets
            candidates = state.analysis_candidates.get("items", [])
            character_drafts = state.analysis_candidates.get("character_drafts", [])
            if not isinstance(candidates, list):
                candidates = []
            if not isinstance(character_drafts, list):
                character_drafts = []
            label.setText(
                Localizer.get().onekey_project_assets_summary.format(
                    worldbook_status=(
                        Localizer.get().enabled
                        if assets.worldbook_enabled
                        else Localizer.get().disabled
                    ),
                    character_count=len(assets.character_cards),
                    glossary_count=len(assets.glossary),
                    preserve_count=len(assets.do_not_translate),
                    candidate_count=len(candidates),
                    draft_count=len(character_drafts),
                )
            )
        except Exception as exc:
            label.setText(
                Localizer.get().onekey_project_assets_currently_unavailable.format(exc=exc)
            )

    def _open_workbench_from_onekey(self) -> None:
        """从一键流程打开工作台，并先同步当前项目路径。"""
        try:
            if self.game_dir:
                self._sync_game_dir_to_config(self.game_dir)
            page = getattr(self.window, "renpy_workbench_page", None)
            if page is None and hasattr(self.window, "findChild"):
                page = self.window.findChild(QWidget, "renpy_workbench_page")
            if page is None:
                InfoBar.warning(
                    Localizer.get().notice,
                    Localizer.get().onekey_character_world_workbench_page_not_found,
                    parent = self,
                )
                return
            if hasattr(page, "refresh_from_config"):
                page.refresh_from_config()
            self.window.navigate_to_page(page)
        except Exception as exc:
            self.logger.error(f"打开工作台失败：{exc}")
            InfoBar.error(
                Localizer.get().error,
                Localizer.get().onekey_could_not_open_workbench.format(exc=exc),
                parent = self,
            )
        
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
            self.glossary_info_label.setText(
                Localizer.get().onekey_found.format(join_found_files=', '.join(found_files))
            )
        else:
            self.glossary_info_label.setText(
                Localizer.get().onekey_no_glossary_files_found_default_configuration_used
            )

    def _open_local_glossary(self):
        page = self._get_tool_page("local_glossary")
        self.window.navigate_to_page(page)

    def _open_text_preserve(self):
        page = self._get_tool_page("text_preserve")
        self.window.navigate_to_page(page)

    def _go_step4(self):
        self.current_step = 4
        self.stacked.setCurrentIndex(3)
        self._refresh_step4_state()

    def start_current_project(self, project_root: str, language: str) -> bool:
        """由 Agent 带入当前项目并启动提取，完成后继续进入翻译确认。"""
        engine = Engine.get()
        if (
            (
                getattr(self, "_preprocess_worker", None)
                and self._preprocess_worker.isRunning()
            )
            or
            (self.extraction_worker and self.extraction_worker.isRunning())
            or engine.get_status() != Engine.Status.IDLE
            or engine.has_stop_barrier()
            or engine.has_single_tasks()
            or bool(getattr(self, "_onekey_translation_started", False))
            or bool(getattr(self, "_onekey_request_id", ""))
            or bool(getattr(self, "_auto_hook_running", False))
            or bool(getattr(self, "_apply_running", False))
        ):
            return False
        root = str(project_root or "").strip()
        if not root:
            return False

        self._start_translation_after_extraction = True
        self._agent_direct_start = True
        self._onekey_translation_completed = False
        try:
            tl_blocked = self.tl_folder_edit.blockSignals(True)
            self.tl_folder_edit.setText(str(language or "chinese").strip() or "chinese")
            self.tl_folder_edit.blockSignals(tl_blocked)
            path_blocked = self.game_path_edit.blockSignals(True)
            self.game_path_edit.setText(root)
            self.game_path_edit.blockSignals(path_blocked)
            self._on_path_text_changed(root)
            if not self.step1_next_btn.isEnabled():
                self._start_translation_after_extraction = False
                self._agent_direct_start = False
                return False
            self._go_step2()
            return True
        except Exception:
            self._start_translation_after_extraction = False
            self._agent_direct_start = False
            raise

    def _invalidate_step2_run(self) -> None:
        """让仍在后台运行的旧步骤 2 结果失效。"""
        self._extraction_generation += 1
        self._start_translation_after_extraction = False
        self._agent_direct_start = False

    def hideEvent(self, event):
        """页面离开后不允许旧预处理结果继续启动后续任务。"""
        self._invalidate_step2_run()
        super().hideEvent(event)

    def showEvent(self, event):
        """从翻译面板返回本页时刷新第 4 步状态，避免显示“未翻译”的假象。"""
        super().showEvent(event)
        if self.current_step == 4:
            self._refresh_step4_state()
    
    def _on_start_translate_clicked(self):
        """检查配置后再进入翻译面板"""
        if not self._refresh_step4_ready():
            self._agent_direct_start = False
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.get().onekey_activate_translation_provider_configure_input_output_folders,
                parent=self,
            )
            return
        
        # 显示友好的目录说明
        from module.Config import Config
        from qfluentwidgets import MessageBox
        
        config = Config().load()
        # 一键翻译处理的是 game/tl/<语言>，不能沿用“源码翻译/补漏”页面的模式。
        configure_tl_translation_mode(config)
        config.save()
        
        # 根据主题选择样式颜色
        code_bg = "#2d2d2d" if isDarkTheme() else "#f5f5f5"
        hint_color = "#aaa" if isDarkTheme() else "#666"
        
        msg_box = MessageBox(
            Localizer.get().onekey_translation_folders,
            Localizer.get().onekey_b_input_folder_b_files_translate_br.format(code_bg=code_bg, input_folder=config.input_folder, output_folder=config.output_folder, hint_color=hint_color),
            self
        )
        msg_box.yesButton.setText(
            Localizer.get().direct_rpy_start_translation
        )
        msg_box.cancelButton.setText(Localizer.get().app_update_cancel)
        
        direct_start = self._agent_direct_start
        self._agent_direct_start = False
        if msg_box.exec():
            self._onekey_translation_started = not direct_start
            self._onekey_translation_completed = False
            self._auto_hook_pending = self.auto_hook_supplement_chk.isChecked()
            self._auto_hook_running = False
            self._open_legacy_translation_page(start_immediately=direct_start)

    def _on_auto_hook_supplement_changed(self, state):
        """保存一键翻译后的自动补漏开关。"""
        try:
            from module.Config import Config

            config = Config().load()
            config.onekey_auto_hook_supplement = bool(state)
            config.save()
        except Exception as e:
            self.logger.warning(f"保存自动补全漏翻配置失败: {e}")
        
    def _open_legacy_translation_page(self, *, start_immediately: bool = False):
        """打开传统翻译页面，保留续翻译能力"""
        try:
            if not self.window:
                raise RuntimeError("未找到主窗口，无法打开翻译面板")

            page = getattr(self.window, "translation_page", None)
            if page is None:
                page = TranslationPage("translation_page", self.window)
                self.window.translation_page = page
            self.window.navigate_to_page(page)
            if start_immediately:
                request_id = uuid.uuid4().hex
                self._onekey_request_id = request_id
                self._onekey_run_id = None
                if not page._request_translation_start(
                    Base.TranslationStatus.UNTRANSLATED,
                    self.window,
                    request_id=request_id,
                ):
                    self._reset_auto_hook_state()
        except Exception as e:
            self._reset_auto_hook_state()
            LogManager.get().error(f"打开传统翻译面板失败: {e}")
            InfoBar.error(
                Localizer.get().error,
                Localizer.get().onekey_could_not_open_translation_panel.format(e=e),
                parent=self,
            )
        
    def _go_step5(self):
        self.current_step = 5
        self.stacked.setCurrentIndex(4)
        self.step5_page.progress_bar.setValue(100)

    def _start_auto_hook_supplement(
        self,
        project_paths: RenpyProjectPaths | None = None,
    ):
        """主翻译完成后自动执行补全漏翻。"""
        try:
            from module.Config import Config

            if not self.game_dir and project_paths is None:
                self._reset_auto_hook_state()
                return

            if project_paths is not None:
                page_paths = RenpyProjectPaths.from_path(
                    self.game_dir,
                    project_paths.language,
                )
                config_paths = RenpyProjectPaths.from_config(Config().load())
                if (
                    page_paths is None
                    or config_paths is None
                    or page_paths.project_key != project_paths.project_key
                    or config_paths.project_key != project_paths.project_key
                ):
                    self._reset_auto_hook_state()
                    InfoBar.warning(
                        Localizer.get().notice,
                        Localizer.get().agent_project_changed,
                        parent=self,
                    )
                    return
                paths = project_paths
                tl_name = paths.language
            else:
                tl_name = self.tl_folder_edit.text().strip() or "chinese"
                paths = RenpyProjectPaths.from_path(self.game_dir, tl_name)
            if paths is None:
                raise RuntimeError("无法解析当前 Ren'Py 项目路径")
            project_root = paths.project_root
            tl_dir = paths.tl_language_dir
            if not tl_dir.exists():
                InfoBar.warning(
                    Localizer.get().notice,
                    Localizer.get().onekey_tl_folder_not_found_missed_text_recovery.format(tl_dir=tl_dir),
                    parent=self,
                )
                self._reset_auto_hook_state()
                return

            self._sync_game_dir_to_config(str(project_root))

            config = Config().load()
            previous_output = self._last_onekey_output_dir or paths.translation_output_dir
            previous_output = Path(previous_output)
            self._hook_restore_paths = (
                str(project_root),
                tl_name,
                str(previous_output),
            )
            _remember_translation_run(
                paths,
                output_folder = tl_dir,
                input_folder = tl_dir,
                application_target_dir = tl_dir,
                run_kind = "hook",
            )
            ProjectStore.get().apply_resolved(
                config,
                paths,
                input_folder = tl_dir,
                output_folder = tl_dir,
                mutate = lambda current: (
                    setattr(current, "renpy_hook_translate", True),
                    setattr(current, "renpy_source_translate", False),
                ),
            )

            self._auto_hook_running = True
            request_id = uuid.uuid4().hex
            self._onekey_request_id = request_id
            self._onekey_run_id = None

            self.emit(
                Base.Event.TRANSLATION_START,
                {
                    "request_id": request_id,
                    "config": config,
                    "status": Base.TranslationStatus.UNTRANSLATED,
                    "input_folder": str(tl_dir),
                    "output_folder": str(tl_dir),
                    "source_language": config.source_language,
                    "target_language": config.target_language,
                },
            )
        except Exception as e:
            self.logger.error(f"自动补全漏翻启动失败: {e}")
            InfoBar.error(
                Localizer.get().error,
                Localizer.get().onekey_could_not_start_missed_text_recovery.format(e=e),
                parent=self,
            )
            self._restore_paths_after_auto_hook()
            self._reset_auto_hook_state()

    def _reset_auto_hook_state(self):
        """重置自动补全漏翻相关状态。"""
        self._onekey_translation_started = False
        self._onekey_request_id = ""
        self._onekey_run_id = None
        self._auto_hook_pending = False
        self._auto_hook_running = False
        self._hook_restore_paths = None
        self._last_onekey_output_dir = None

    def _restore_paths_after_auto_hook(self) -> None:
        """恢复全局配置，并把最近运行清单指回 Hook 前的有效缓存。"""
        restore = self._hook_restore_paths
        self._hook_restore_paths = None
        if not restore:
            return
        try:
            from module.Config import Config

            config = Config().load()
            # 新版本保存 (项目根, 语言目录名, Hook 前输出目录)；兼容旧版
            # 只有两个元素的状态，避免页面对象在热更新后恢复时崩溃。
            project_root = restore[0]
            tl_name = restore[1]
            previous_output = (
                Path(restore[2])
                if len(restore) >= 3 and restore[2]
                else None
            )
            paths = configure_main_translation_paths(
                config,
                project_root,
                tl_name,
                remember_run = False,
            )
            if previous_output is None:
                previous_output = paths[1]
            # hook 只是自动补漏的临时运行模式；收尾后必须恢复普通翻译
            # 标志，避免下一次一键翻译继续沿用 hook/source 分支。
            config.renpy_hook_translate = False
            config.renpy_source_translate = False
            config.save()

            # Hook 会临时把清单写到 game/tl/<lang>。恢复时必须重新登记
            # Hook 前的主/增量缓存，否则校对页会优先载入 Hook 的空项目。
            output_name = previous_output.name.casefold()
            incremental_name = f"{str(tl_name).strip().casefold()}_new"
            run_kind = "incremental" if output_name == incremental_name else "translation"
            input_folder = (
                paths[0].parent / f"{str(tl_name).strip()}_new"
                if run_kind == "incremental"
                else paths[0]
            )
            restored_paths = RenpyProjectPaths.from_path(project_root, tl_name)
            if restored_paths is not None:
                _remember_translation_run(
                    restored_paths,
                    output_folder = previous_output,
                    input_folder = input_folder,
                    application_target_dir = restored_paths.application_target_dir,
                    run_kind = run_kind,
                )
        except Exception as exc:
            self.logger.warning(f"自动补全完成后恢复主路径失败: {exc}")

    def _on_translation_start_result(self, event, data):
        """只接收本次 Agent 一键启动请求的受理结果。"""
        del event
        payload = data if isinstance(data, dict) else {}
        request_id = str(payload.get("request_id", "") or "")
        if not self._onekey_request_id or request_id != self._onekey_request_id:
            return

        self._onekey_request_id = ""
        if payload.get("accepted") is True:
            self._onekey_run_id = payload.get("run_id")
            self._onekey_translation_started = True
            if getattr(self, "_auto_hook_running", False):
                InfoBar.success(
                    Localizer.get().direct_rpy_started,
                    Localizer.get().onekey_main_translation_complete_recovering_missed_text,
                    parent=self,
                )
            return

        self._onekey_translation_completed = False
        if getattr(self, "_auto_hook_running", False):
            self._restore_paths_after_auto_hook()
        self._reset_auto_hook_state()
        InfoBar.warning(
            Localizer.get().notice,
            Localizer.get().translator_running,
            parent=self,
        )

    def _on_translation_done(self, event, data):
        """监听翻译完成，按需接续 replace_text 补漏。"""
        payload = data if isinstance(data, dict) else {}
        failed = payload.get("success") is False or payload.get("stopped") is True

        if getattr(self, "_auto_hook_running", False):
            request_id = str(payload.get("request_id", "") or "")
            pending_request_id = str(
                getattr(self, "_onekey_request_id", "") or ""
            )
            run_id = getattr(self, "_onekey_run_id", None)
            if pending_request_id:
                if request_id != pending_request_id:
                    return
                self._onekey_request_id = ""
                self._onekey_run_id = payload.get("run_id")
            elif run_id is not None and payload.get("run_id") != run_id:
                return
            self._restore_paths_after_auto_hook()
            self._reset_auto_hook_state()
            if failed:
                InfoBar.warning(
                    Localizer.get().direct_rpy_stopped,
                    Localizer.get().onekey_missed_text_recovery_did_not_finish_main,
                    parent=self,
                )
            else:
                InfoBar.success(
                    Localizer.get().local_glossary_completed,
                    Localizer.get().onekey_missed_text_recovery_completed,
                    parent=self,
                )
            return

        pending_request_id = str(
            getattr(self, "_onekey_request_id", "") or ""
        )
        if pending_request_id:
            if str(payload.get("request_id", "") or "") != pending_request_id:
                return
            self._onekey_request_id = ""
            self._onekey_run_id = payload.get("run_id")
            self._onekey_translation_started = True
        elif (
            getattr(self, "_onekey_run_id", None) is not None
            and payload.get("run_id") != self._onekey_run_id
        ):
            return

        if self._onekey_translation_started and self._auto_hook_pending:
            # 主输出必须先由用户确认并应用到 game/tl，再扫描漏翻；否则全量
            # 输出尚未落地、增量输出尚未合并，都会以旧 TL 作为扫描依据。
            if failed:
                self._reset_auto_hook_state()
                return
            return

        if self._onekey_translation_started:
            self._onekey_translation_completed = not failed
            self._reset_auto_hook_state()
            self._refresh_step4_state()

    def _on_translation_stop(self, event, data):
        """翻译停止时清理一键翻译的自动补漏状态。"""
        if self._onekey_request_id or self._onekey_run_id is not None:
            # 关联运行等待带 run_id 的 TRANSLATION_DONE，不能被其它停止请求清理。
            return
        if self._onekey_translation_started or self._auto_hook_pending or self._auto_hook_running:
            if self._auto_hook_running:
                self._restore_paths_after_auto_hook()
            self._onekey_translation_completed = False
            self._reset_auto_hook_state()
            self._refresh_step4_state()

    def _translation_output_completed(self) -> bool:
        """翻译输出目录缓存已完成时为 True（用于向导重建后的兜底判断）。"""
        try:
            from module.Cache.CacheManager import CacheManager

            cfg = Config().load()
            output = str(getattr(cfg, "output_folder", "") or "")
            if not output:
                return False
            manager = CacheManager(service=False)
            manager.load_project_from_file(output)
            return (
                manager.get_project().get_status()
                == Base.TranslationStatus.TRANSLATED
            )
        except Exception:
            return False

    def _refresh_step4_state(self) -> None:
        """刷新第 4 步界面：翻译已完成时给出明确指引，否则走配置检查。"""
        if self._onekey_translation_completed or self._translation_output_completed():
            self._onekey_translation_completed = True
            self.step4_status.setText(
                Localizer.get().onekey_translation_complete_continue_post_processing_apply_game
            )
            self.step4_status.setStyleSheet("color: #27ae60;")
            self.start_trans_btn.setText(
                Localizer.get().onekey_translate_again
            )
            self.start_trans_btn.setEnabled(True)
            self.skip_trans_btn.setText(
                Localizer.get().onekey_continue_post_processing
            )
            return
        self.start_trans_btn.setText(
            Localizer.get().onekey_start_translation
        )
        self.skip_trans_btn.setText(
            Localizer.get().onekey_skip_translation
        )
        self._refresh_step4_ready()

    def _refresh_step4_ready(self) -> bool:
        """检查翻译前的必备配置"""
        from module.Config import Config
        cfg = Config().load()

        missing: list[str] = []
        input_dir = Path(cfg.input_folder) if cfg.input_folder else None
        output_dir = Path(cfg.output_folder) if cfg.output_folder else None

        if not input_dir or not input_dir.exists():
            missing.append(
                Localizer.get().onekey_input_folder_missing_does_not_exist
            )
        if not output_dir:
            missing.append(
                Localizer.get().onekey_output_folder_not_configured
            )
        elif input_dir and output_dir and input_dir.exists():
            try:
                if output_dir.resolve() == input_dir.resolve():
                    missing.append(
                        Localizer.get().onekey_input_output_folders_must_different
                    )
            except Exception:
                pass
        if output_dir and not output_dir.exists():
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                missing.append(
                    Localizer.get().onekey_output_folder_could_not_created
                )

        platform_ready = False
        if cfg.platforms:
            for p in cfg.platforms:
                if p.get("id") == cfg.activate_platform:
                    platform_ready = True
                    break
        if not platform_ready:
            missing.append(
                Localizer.get().onekey_no_translation_provider_active
            )

        ready = len(missing) == 0
        if ready:
            self.step4_status.setText(
                Localizer.get().onekey_ready_translate_2
            )
            self.step4_status.setStyleSheet("color: #27ae60;")
            self.start_trans_btn.setEnabled(True)
        else:
            self.step4_status.setText(
                Localizer.get().onekey_complete_following_setup_first
                + "\n".join(missing)
            )
            self.step4_status.setStyleSheet("color: #e67e22;")
            self.start_trans_btn.setEnabled(False)
        return ready
    
    def _go_previous_step(self, current_step: int):
        """返回上一步"""
        if (
            self._preprocess_worker
            and self._preprocess_worker.isRunning()
        ) or (
            self.extraction_worker
            and self.extraction_worker.isRunning()
        ):
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.get().onekey_extraction_already_running_wait_finish,
                parent=self,
            )
            return
        if current_step <= 1:
            # 步骤1返回到工具箱
            self._exit_wizard()
        else:
            # 返回上一步
            self.current_step = current_step - 1
            self.stacked.setCurrentIndex(current_step - 2)  # index 从 0 开始
        
    def _exit_wizard(self):
        """退出向导，返回工具箱页面"""
        self._invalidate_step2_run()
        if self.window:
            self.window.navigate_back_to_toolbox()
        
        # 重置状态（为下次使用做准备）
        self.current_step = 1
        self.stacked.setCurrentIndex(0)
        self._onekey_translation_completed = False
        self._start_translation_after_extraction = False
        self._agent_direct_start = False
        self.step1_next_btn.setEnabled(False)
        self.skip_extract_btn.setVisible(False)
        self.game_path = ""
        self.game_dir = ""
        self.game_path_edit.clear()
        self.path_status_label.setText("")
        self.old_translation_card.setVisible(False)
        self.has_old_translation = False
        
    # 工具函数
    def _tool_apply_translation(self, card, feedback_parent=None):
        """应用翻译：将输出目录的文件复制到 tl 目录"""
        from module.Config import Config
        from qfluentwidgets import MessageBox
        from pathlib import Path
        
        ui_parent = feedback_parent or self
        config = Config().load()

        tl_name = self.tl_folder_edit.text().strip() or "chinese"
        project_paths = (
            RenpyProjectPaths.from_path(self.game_dir, tl_name)
            if self.game_dir
            else RenpyProjectPaths.from_config(config, tl_name)
        )

        # 一键向导的项目路径优先于可变全局配置，避免其他页面改写
        # config.output_folder/input_folder 后把翻译应用到另一项目。
        incremental_output = self._incremental_output_dir
        if incremental_output:
            output_dir = Path(incremental_output)
            target_value = self._apply_target_dir or (
                project_paths.application_target_dir
                if project_paths is not None
                else None
            )
            input_dir = Path(target_value) if target_value else None
        elif project_paths is not None:
            output_dir = project_paths.translation_output_dir
            input_dir = project_paths.application_target_dir
        else:
            output_dir, input_dir = resolve_translation_apply_paths(
                config, None, None
            )
        
        if not output_dir.exists():
            InfoBar.error(
                Localizer.get().error,
                Localizer.get().onekey_output_folder_does_not_exist.format(output_dir=output_dir),
                parent=ui_parent,
            )
            return
        
        if input_dir is None or not input_dir.exists():
            InfoBar.error(
                Localizer.get().error,
                Localizer.get().onekey_target_folder_does_not_exist.format(input_dir=input_dir),
                parent=ui_parent,
            )
            return
        
        # 统计文件
        output_files = list(output_dir.rglob("*.rpy"))
        if not output_files:
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.get().onekey_output_folder_does_not_contain_translation_files,
                parent=ui_parent,
            )
            return
        
        # 确认对话框 - 根据主题选择样式颜色
        code_bg = "#2d2d2d" if isDarkTheme() else "#f5f5f5"
        warn_color = "#e67e22" if isDarkTheme() else "#d35400"
        
        msg_box = MessageBox(
            Localizer.get().onekey_confirm_translation_application,
            Localizer.get().onekey_b_apply_translation_game_b_br_br.format(code_bg=code_bg, output_dir=output_dir, input_dir=input_dir, output_files_count=len(output_files), warn_color=warn_color),
            ui_parent
        )
        msg_box.yesButton.setText(
            Localizer.get().onekey_apply_translation
        )
        msg_box.cancelButton.setText(Localizer.get().app_update_cancel)
        
        if not msg_box.exec():
            return
        
        # 防重入：应用进行中不允许再次触发（乱点会导致重复合并/卡死）。
        if getattr(self, "_apply_running", False):
            InfoBar.warning(
                Localizer.get().onekey_applying_translation,
                Localizer.get().onekey_translation_already_being_applied_please_wait,
                parent=ui_parent,
            )
            return
        self._apply_running = True
        if card is not None and hasattr(card, "setEnabled"):
            card.setEnabled(False)

        if incremental_output:
            # 增量文件只包含部分条目，必须通过语义合并写回，不能整文件覆盖主 TL。
            main_output = (
                project_paths.translation_output_dir
                if project_paths is not None
                else output_dir.parent / tl_name
            )
            staging_input = getattr(self, "_incremental_dir", None)
            worker = ApplyTranslationWorker(
                self.unified_extractor,
                incremental_mode=True,
                game_dir=self.game_dir,
                tl_name=tl_name,
                output_dir=output_dir,
                main_output=main_output,
                incremental_dir=staging_input,
                config=config,
            )
        else:
            # 全量翻译按批次应用；任一文件失败就恢复本批次已覆盖的目标。
            worker = ApplyTranslationWorker(
                self.unified_extractor,
                incremental_mode=False,
                output_dir=output_dir,
                input_dir=input_dir,
                output_files=output_files,
                config=config,
                project_root=(
                    project_paths.project_root if project_paths is not None else None
                ),
                project_language=(
                    project_paths.language if project_paths is not None else None
                ),
            )

        progress_dialog = QProgressDialog(
            Localizer.get().onekey_applying_translation_game,
            None,
            0,
            100,
            ui_parent,
        )
        progress_dialog.setWindowTitle(
            Localizer.get().onekey_apply_translation
        )
        progress_dialog.setWindowModality(Qt.ApplicationModal)
        progress_dialog.setCancelButton(None)
        progress_dialog.setMinimumDuration(0)
        progress_dialog.setValue(0)
        progress_dialog.show()

        # 用页面绑定方法接收信号，保证跨线程排队投递到 UI 线程。
        self._apply_card = card
        self._apply_parent = ui_parent
        self._apply_project_paths = project_paths
        self._apply_progress_dialog = progress_dialog
        worker.progress.connect(self._on_apply_progress)
        worker.finished.connect(self._on_apply_finished)
        self._apply_worker = worker
        worker.start()

    def _on_apply_progress(self, msg: str, pct: int) -> None:
        """后台进度信号：更新进度对话框（运行在 UI 线程）。"""
        dialog = getattr(self, "_apply_progress_dialog", None)
        if dialog is not None:
            dialog.setLabelText(str(msg))
            dialog.setValue(int(pct))

    def _on_apply_finished(self, success: bool, msg: str, payload: dict | None):
        """后台应用结束后回到 UI 线程：恢复入口、展示结果、接续 hook。"""
        card = getattr(self, "_apply_card", None)
        ui_parent = getattr(self, "_apply_parent", None)
        project_paths = getattr(self, "_apply_project_paths", None)
        progress_dialog = getattr(self, "_apply_progress_dialog", None)
        self._apply_running = False
        self._apply_worker = None
        self._apply_card = None
        self._apply_parent = None
        self._apply_project_paths = None
        self._apply_progress_dialog = None
        if card is not None and hasattr(card, "setEnabled"):
            card.setEnabled(True)
        if progress_dialog is not None:
            progress_dialog.close()

        if success:
            if payload:
                if payload.get("main_output"):
                    self._last_onekey_output_dir = Path(payload["main_output"])
                    self._incremental_dir = None
                    self._incremental_output_dir = None
                    self._apply_target_dir = None
                elif payload.get("count") is not None and project_paths is not None:
                    self._last_onekey_output_dir = project_paths.translation_output_dir
            InfoBar.success(
                Localizer.get().onekey_translation_applied,
                msg,
                duration=5000,
                parent=ui_parent,
            )
            if self._onekey_translation_started and self._auto_hook_pending:
                self._auto_hook_pending = False
                QTimer.singleShot(
                    0,
                    lambda paths=project_paths: self._start_auto_hook_supplement(
                        paths,
                    ),
                )
            elif self._onekey_translation_started:
                self._reset_auto_hook_state()
            return

        if payload and payload.get("warning"):
            InfoBar.warning(
                Localizer.get().notice,
                msg,
                parent=ui_parent,
            )
        else:
            InfoBar.error(
                Localizer.get().error,
                msg,
                parent=ui_parent,
            )

    def _tool_hook_supplement(self, card):
        """打开补全漏翻页面，并沿用当前项目上下文。"""
        try:
            if self.game_dir:
                self._sync_game_dir_to_config(self.game_dir)
            self.window.navigate_to_page(self._get_tool_page("hook_supplement"))
        except Exception as e:
            self.logger.error(f"打开补全翻译页面失败: {e}")
            InfoBar.error(
                Localizer.get().error,
                Localizer.get().onekey_could_not_open_missed_text_recovery.format(e=e),
                parent=self,
            )
    
    def _tool_fix_errors(self, card):
        """打开错误修复页面，并预填当前项目的 game 目录。"""
        try:
            page = self._get_tool_page("error_repair")
            if self.game_dir and hasattr(page, "game_dir_edit"):
                project_path = Path(self.game_dir)
                game_path = (
                    project_path
                    if project_path.name.casefold() == "game"
                    else project_path / "game"
                )
                page.game_dir_edit.setText(str(game_path))
            self.window.navigate_to_page(page)
        except Exception as exc:
            self.logger.error(f"打开错误修复页面失败: {exc}")
            InfoBar.error(
                Localizer.get().error,
                Localizer.get().onekey_could_not_open_error_repair.format(exc=exc),
                parent=self,
            )

    def _tool_set_default_lang(self, card):
        page = self._get_tool_page("set_default_language")
        if self.game_dir and hasattr(page, "project_dir_edit"):
            page.project_dir_edit.setText(self.game_dir)
        self.window.navigate_to_page(page)

    def _tool_add_lang_switch(self, card):
        page = self._get_tool_page("add_language")
        if self.game_dir and hasattr(page, "game_dir_edit"):
            project_path = Path(self.game_dir)
            game_dir = project_path if project_path.name.casefold() == "game" else project_path / "game"
            page.game_dir_edit.setText(str(game_dir))
        self.window.navigate_to_page(page)

    def _tool_replace_font(self, card):
        page = self._get_tool_page("font_replace")
        if self.game_dir and hasattr(page, "game_dir_edit"):
            page.game_dir_edit.setText(self.game_dir)
        self.window.navigate_to_page(page)

    def _tool_open_game_dir(self, card):
        if self.game_dir:
            os.startfile(self.game_dir)

    def _tool_open_proofreading(self, card):
        """打开检查与润色页面。"""
        del card
        if self.window is None:
            return
        page = self._get_tool_page("proofreading")
        self.window.navigate_to_page(page)
            
    def _tool_export_patch(self, card):
        """生成当前项目的漏翻补丁。"""
        try:
            if not self.game_dir:
                InfoBar.warning(
                    Localizer.get().notice,
                    Localizer.get().onekey_select_game_folder_first_2,
                    parent=self,
                )
                return
            tl_name = self.tl_folder_edit.text().strip() or "chinese"
            patch_path, missing_count = generate_patch(self.game_dir, tl_name)
            if patch_path is None:
                InfoBar.info(
                    Localizer.get().notice,
                    Localizer.get().onekey_no_missing_translations_found_patch_not_needed,
                    parent=self,
                )
                return
            InfoBar.success(
                Localizer.get().onekey_export_complete,
                Localizer.get().onekey_created_missing_translation_patch_entries.format(patch_path=patch_path, missing_count=missing_count),
                parent=self,
                duration=5000,
            )
        except Exception as exc:
            self.logger.error(f"导出语言补丁失败: {exc}")
            InfoBar.error(
                Localizer.get().error,
                Localizer.get().onekey_could_not_export_language_patch.format(exc=exc),
                parent=self,
            )
    
    def _tool_view_glossary(self, card):
        self._open_local_glossary()


# 兼容旧引用
OneKeyTranslatePage = YiJianFanyiPage
__all__ = ["YiJianFanyiPage", "OneKeyTranslatePage"]
