"""
翻译引擎管理 - 高速批量翻译
通过 API 快速处理 JSON 翻译数据，专注于翻译速度和批处理
"""

import concurrent.futures
import copy
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFileDialog
from qfluentwidgets import (
    PushButton,
    PrimaryPushButton,
    InfoBar,
    FluentIcon,
    LineEdit,
    ComboBox,
    ProgressBar,
    CardWidget,
    SpinBox,
    DoubleSpinBox,
    SwitchButton,
)

from base.Base import Base
from base.Base import Base as BaseClass
from base.LogManager import LogManager
from module.Cache.CacheItem import CacheItem
from module.Config import Config
from module.Engine.Engine import Engine
from module.Engine.TaskRequester import TaskRequester
from module.PromptBuilder import PromptBuilder
from module.Response.ResponseDecoder import ResponseDecoder
from module.TextProcessor import TextProcessor
from module.Renpy.json_handler import JsonExporter, JsonImporter


def calculate_max_workers(config: Config, platform: dict) -> int:
    """
    计算最大并发数（复用主翻译页面的逻辑）
    
    Args:
        config: 配置对象
        platform: 平台配置
        
    Returns:
        max_workers 并发数
    """
    import re
    import httpx
    
    max_workers: int = config.max_workers
    rpm_threshold: int = config.rpm_threshold
    
    # 检测是否为本地模型
    api_url = platform.get('api_url', '')
    local_flag = bool(re.search(
        r"^http[s]*://localhost|^http[s]*://\d+\.\d+\.\d+\.\d+",
        api_url,
        flags=re.IGNORECASE,
    ))
    
    # 当 max_workers = 0 时，只有本地模型才尝试探测 /slots（llama.cpp 风格）
    if max_workers == 0 and local_flag:
        try:
            response = httpx.get(
                re.sub(r"/v1$", "", api_url) + "/slots",
                timeout=3,
            )
            response.raise_for_status()
            response_json = response.json()
            if isinstance(response_json, list) and len(response_json) > 0:
                max_workers = len(response_json)
        except Exception:
            pass

    if max_workers == 0 and rpm_threshold == 0:
        max_workers = 8 if local_flag else 2
    elif max_workers > 0 and rpm_threshold == 0:
        max_workers = max(1, max_workers)
    elif max_workers == 0 and rpm_threshold > 0:
        per_second = max(1, rpm_threshold // 60)
        safe_cap = 8 if local_flag else 3
        max_workers = min(per_second, safe_cap)

    return max(1, max_workers)


class TranslationWorker(QThread):
    """翻译工作线程 - 使用统一的翻译任务逻辑"""
    progress = pyqtSignal(int, int, str)  # 当前, 总数, 消息
    finished = pyqtSignal(bool, str)  # 成功, 消息
    text_translated = pyqtSignal(dict)  # 包含原文、译文和定位信息

    def __init__(self, items: List[dict], platform: dict, params: dict, config: Config):
        super().__init__()
        self.items = items
        self.params = params
        self.platform = copy.deepcopy(platform or {})
        self.config = config
        self.should_stop = False
        self.logger = LogManager.get()

        # 根据用户参数覆盖平台默认参数
        if isinstance(self.params.get('model'), str):
            self.platform['model'] = self.params['model']
        if 'temperature' in self.params:
            self.platform['temperature'] = float(self.params['temperature'])
            self.platform['temperature_custom_enable'] = True
        if 'top_p' in self.params:
            self.platform['top_p'] = float(self.params['top_p'])
            self.platform['top_p_custom_enable'] = True

    def run(self):
        """执行翻译"""
        try:
            translated_count = self._translate_batch_unified()
            
            if self.should_stop:
                self.finished.emit(False, "翻译已被手动停止")
            else:
                self.finished.emit(True, f"翻译完成，共 {translated_count} 条")
        except Exception as e:
            LogManager.get().error(f"翻译失败: {e}")
            self.finished.emit(False, f"翻译失败: {e}")

    def stop(self):
        """停止翻译"""
        self.should_stop = True

    def _translate_batch_unified(self) -> int:
        """使用统一的翻译逻辑（复用 PromptBuilder、TextProcessor、ResponseDecoder）
        
        支持并发翻译，使用与主翻译页面相同的 max_workers 设置
        """
        if not self.items:
            return 0

        batch_size = max(1, int(self.params.get('batch_size', 10)))
        total = len(self.items)
        translated_count = 0
        
        # 计算并发数（使用与主翻译页面相同的逻辑）
        max_workers = calculate_max_workers(self.config, self.platform)
        self.logger.info(f"翻译并发数: {max_workers}")

        prompt_builder = PromptBuilder(self.config)
        
        # 将所有 items 分成 batches
        batches = []
        for i in range(0, total, batch_size):
            batches.append(self.items[i:i + batch_size])
        
        total_batches = len(batches)
        completed_batches = 0
        results_lock = __import__('threading').Lock()
        
        def translate_single_batch(batch_idx: int, batch: List[dict]) -> List[dict]:
            """翻译单个批次"""
            results = []
            
            if self.should_stop:
                # 返回原文
                for entry in batch:
                    results.append({
                        'original': entry.get('original'),
                        'translated': entry.get('original'),
                        'file': entry.get('file'),
                        'index': entry.get('index'),
                        'original_raw': entry.get('original_raw'),
                    })
                return results
            
            try:
                # 每个批次创建独立的 requester（避免线程安全问题）
                requester = TaskRequester(self.config, self.platform, batch_idx)
                
                # 将 dict 项转换为 CacheItem 并进行预处理
                cache_items: List[CacheItem] = []
                processors: List[TextProcessor] = []
                item_mapping: List[dict] = []

                for entry in batch:
                    original = entry.get('original', '')
                    if not original.strip():
                        continue
                    
                    cache_item = CacheItem(
                        src=original,
                        dst="",
                        text_type=CacheItem.TextType.RENPY,
                        file_type=CacheItem.FileType.RENPY,
                    )
                    cache_items.append(cache_item)
                    item_mapping.append(entry)
                    
                    processor = TextProcessor(self.config, cache_item)
                    processors.append(processor)

                if not cache_items:
                    for entry in batch:
                        results.append({
                            'original': entry.get('original'),
                            'translated': entry.get('original'),
                            'file': entry.get('file'),
                            'index': entry.get('index'),
                            'original_raw': entry.get('original_raw'),
                        })
                    return results

                # 收集预处理后的原文
                srcs: List[str] = []
                samples: List[str] = []
                for processor in processors:
                    processor.pre_process()
                    srcs.extend(processor.srcs)
                    samples.extend(processor.samples)

                if not srcs:
                    for entry in batch:
                        results.append({
                            'original': entry.get('original'),
                            'translated': entry.get('original'),
                            'file': entry.get('file'),
                            'index': entry.get('index'),
                            'original_raw': entry.get('original_raw'),
                        })
                    return results

                # 生成提示词
                if self.platform.get('api_format') != Base.APIFormat.SAKURALLM:
                    messages, _ = prompt_builder.generate_prompt(srcs, samples, [], False)
                else:
                    messages, _ = prompt_builder.generate_prompt_sakura(srcs)

                # 发送翻译请求
                skip, _, response_text, input_tokens, output_tokens = requester.request(messages)

                if skip or not response_text:
                    raise RuntimeError("翻译结果为空")

                # 解析结果
                source_text_dict = {str(idx): src for idx, src in enumerate(srcs)}
                dsts, _ = ResponseDecoder().decode(response_text, source_text_dict)

                # 后处理
                dsts_copy = dsts.copy() if dsts else []
                
                for idx, (cache_item, processor, entry) in enumerate(zip(cache_items, processors, item_mapping)):
                    length = len(processor.srcs)
                    
                    if dsts_copy and length > 0:
                        dsts_for_item = []
                        for _ in range(length):
                            if dsts_copy:
                                dsts_for_item.append(dsts_copy.pop(0))
                            else:
                                dsts_for_item.append("")
                        _, translated = processor.post_process(dsts_for_item)
                    else:
                        translated = entry.get('original', '')

                    results.append({
                        'original': entry.get('original'),
                        'translated': translated,
                        'file': entry.get('file'),
                        'index': entry.get('index'),
                        'original_raw': entry.get('original_raw'),
                    })

                self.logger.debug(f"批次 {batch_idx + 1} 完成，输入 {input_tokens} tokens，输出 {output_tokens} tokens")

            except Exception as e:
                self.logger.error(f"翻译批次 {batch_idx + 1} 失败: {e}")
                for entry in batch:
                    results.append({
                        'original': entry.get('original'),
                        'translated': entry.get('original'),
                        'file': entry.get('file'),
                        'index': entry.get('index'),
                        'original_raw': entry.get('original_raw'),
                    })
            
            return results
        
        # 使用线程池并发执行
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有批次任务
            future_to_batch = {
                executor.submit(translate_single_batch, idx, batch): (idx, batch)
                for idx, batch in enumerate(batches)
            }
            
            # 收集结果
            for future in concurrent.futures.as_completed(future_to_batch):
                if self.should_stop:
                    break
                
                batch_idx, batch = future_to_batch[future]
                try:
                    batch_results = future.result()
                    
                    # 发送翻译结果
                    for payload in batch_results:
                        self.text_translated.emit(payload)
                        translated_count += 1
                    
                    # 更新进度
                    with results_lock:
                        completed_batches += 1
                        processed = min(completed_batches * batch_size, total)
                        self.progress.emit(
                            processed, 
                            total, 
                            f"正在翻译 ({completed_batches}/{total_batches} 批, {max_workers} 并发)..."
                        )
                        
                except Exception as e:
                    self.logger.error(f"获取批次 {batch_idx + 1} 结果失败: {e}")

        return translated_count


class TranslateEngineTab(Base, QWidget):
    """翻译引擎管理标签页"""

    def __init__(self, parent=None):
        Base.__init__(self)
        QWidget.__init__(self, parent)
        
        self.window = parent  # 保存父窗口引用用于返回导航

        self.logger = LogManager.get()
        self.worker = None
        self.platform_map: Dict[int, dict] = {}
        self.current_input_path: Optional[str] = None
        self.auto_save_path: Optional[str] = None
        self._last_auto_save: float = 0.0
        self.pending_items: List[dict] = []
        self.auto_save_enabled: bool = False
        self._init_ui()
        # 监听 Engine 事件，统一按钮状态
        self.subscribe(Base.Event.TRANSLATION_DONE, self._on_engine_done)
        self.subscribe(Base.Event.TRANSLATION_STOP, self._on_engine_stop)
        self.subscribe(Base.Event.TRANSLATION_UPDATE, self._on_engine_update)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._load_engine_options()

    def _init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        layout.setSpacing(20)

        from qfluentwidgets import TitleLabel, BodyLabel, CaptionLabel, TransparentToolButton
        
        # 顶部：返回按钮 + 标题
        header = QHBoxLayout()
        self.back_btn = TransparentToolButton(FluentIcon.RETURN)
        self.back_btn.setToolTip("返回")
        self.back_btn.clicked.connect(self._go_back)
        header.addWidget(self.back_btn)
        
        title = TitleLabel("⚡ 翻译引擎管理")
        header.addWidget(title)
        header.addStretch(1)
        layout.addLayout(header)

        # 添加功能说明 - 指导用户直接翻译 RPY
        description = CaptionLabel("💡 用于翻译导出的 JSON 文件。推荐使用「直接翻译 RPY」功能直接翻译游戏。")
        description.setWordWrap(True)
        layout.addWidget(description)

        layout.addWidget(self._create_file_card())
        layout.addWidget(self._create_engine_card())
        layout.addWidget(self._create_params_card())
        layout.addWidget(self._create_progress_card())
        layout.addWidget(self._create_action_card())

        layout.addStretch()
    
    def _go_back(self):
        """返回上一页"""
        if hasattr(self, 'window') and self.window:
            # 尝试使用导航返回
            if hasattr(self.window, 'navigate_back'):
                self.window.navigate_back()
            elif hasattr(self.window, 'stackedWidget'):
                # 回到工具箱页面
                for i in range(self.window.stackedWidget.count()):
                    widget = self.window.stackedWidget.widget(i)
                    # 兼容旧版 RenpyToolkitPage 和新版 renpy_toolbox_page
                    if widget.objectName() in ("RenpyToolkitPage", "renpy_toolbox_page"):
                        self.window.stackedWidget.setCurrentWidget(widget)
                        break

    def _create_file_card(self) -> CardWidget:
        """创建文件选择卡片"""
        from qfluentwidgets import SubtitleLabel, BodyLabel
        
        card = CardWidget(self)
        l = QVBoxLayout(card)

        title = SubtitleLabel("📁 文件选择")
        l.addWidget(title)

        # JSON 文件
        row1 = QHBoxLayout()
        row1.addWidget(BodyLabel("JSON 文件:"))
        self.json_file_edit = LineEdit()
        self.json_file_edit.setPlaceholderText("选择待翻译的 JSON 文件")
        btn_browse = PushButton("浏览", icon=FluentIcon.FOLDER)
        btn_browse.clicked.connect(self._browse_json)
        row1.addWidget(self.json_file_edit, 1)
        row1.addWidget(btn_browse)
        l.addLayout(row1)

        # 目标语言
        row2 = QHBoxLayout()
        row2.addWidget(BodyLabel("目标语言:"))
        self.target_lang_combo = ComboBox()
        self.target_lang_combo.addItems([
            "简体中文", "繁体中文", "英语", "日语", "韩语"
        ])
        self.target_lang_combo.setCurrentText("简体中文")
        row2.addWidget(self.target_lang_combo, 1)
        l.addLayout(row2)

        return card

    def _create_engine_card(self) -> CardWidget:
        """创建引擎选择卡片"""
        from qfluentwidgets import BodyLabel, CaptionLabel
        
        card = CardWidget(self)
        l = QVBoxLayout(card)

        # 接口选择
        row1 = QHBoxLayout()
        row1.addWidget(BodyLabel("接口:"))
        self.engine_combo = ComboBox()
        self.engine_combo.currentIndexChanged.connect(self._on_engine_changed)
        row1.addWidget(self.engine_combo, 1)
        l.addLayout(row1)

        # 模型选择
        row2 = QHBoxLayout()
        row2.addWidget(BodyLabel("模型:"))
        self.model_combo = ComboBox()
        self.model_combo.currentTextChanged.connect(self._on_model_combo_changed)
        row2.addWidget(self.model_combo, 1)
        l.addLayout(row2)

        # 自定义模型输入
        row3 = QHBoxLayout()
        row3.addWidget(BodyLabel("自定义模型:"))
        self.model_input = LineEdit()
        self.model_input.setPlaceholderText("可选，覆盖下拉选择的模型名称")
        row3.addWidget(self.model_input, 1)
        l.addLayout(row3)

        self.api_info_label = CaptionLabel("")
        self.api_info_label.setWordWrap(True)
        l.addWidget(self.api_info_label)

        tip = CaptionLabel("提示：请先在接口管理页面配置 API 接口和密钥")
        tip.setStyleSheet("color: orange;")
        tip.setWordWrap(True)
        l.addWidget(tip)

        self._load_engine_options()

        return card

    def _load_engine_options(self):
        """从配置加载可用的 API 接口列表"""
        try:
            config = Config().load()
        except Exception as e:
            self.logger.error(f"加载接口配置失败: {e}")
            config = None

        platforms = []
        active_id = None
        if config is not None:
            platforms = config.platforms or []
            active_id = getattr(config, "activate_platform", None)

        current_selection = self.engine_combo.currentData()

        self.platform_map.clear()
        self.engine_combo.blockSignals(True)
        self.engine_combo.clear()

        for platform in sorted(platforms, key=lambda x: x.get('id', 0)):
            platform_id = platform.get('id')
            name = platform.get('name') or f"接口 {platform_id}"
            index = self.engine_combo.count()
            # 使用关键字参数确保第二个参数作为 userData，而非 icon
            self.engine_combo.addItem(name, userData=platform_id)
            self.platform_map[platform_id] = platform

        if self.platform_map:
            self.engine_combo.setEnabled(True)
            target_id = current_selection if current_selection in self.platform_map else active_id
            if target_id in self.platform_map:
                target_index = self.engine_combo.findData(target_id)
                if target_index != -1:
                    self.engine_combo.setCurrentIndex(target_index)
                else:
                    self.engine_combo.setCurrentIndex(0)
            else:
                self.engine_combo.setCurrentIndex(0)
            info_text = "已加载接口配置，请确保密钥可用。"
        else:
            self.engine_combo.addItem("未配置接口")
            self.engine_combo.setEnabled(False)
            self.model_combo.clear()
            self.model_combo.setEnabled(False)
            self.model_input.clear()
            self.model_input.setEnabled(False)
            info_text = "未检测到可用接口，请在接口管理页添加并保存配置。"

        self.engine_combo.blockSignals(False)
        self.api_info_label.setText(info_text)
        if self.platform_map:
            self.model_combo.setEnabled(True)
            self.model_input.setEnabled(True)
            self._on_engine_changed(self.engine_combo.currentIndex())

    def _on_engine_changed(self, index: int):
        """接口选择变化时刷新模型与参数"""
        # 跳过分隔符项
        data = self.engine_combo.currentData()
        if data == "__separator__":
            # 选中分隔符时，跳到下一个有效项
            if index + 1 < self.engine_combo.count():
                self.engine_combo.setCurrentIndex(index + 1)
            elif index > 0:
                self.engine_combo.setCurrentIndex(index - 1)
            return
        
        platform = self._get_selected_platform()
        self.model_combo.blockSignals(True)
        self.model_combo.clear()

        if not platform:
            self.model_combo.clear()
            if hasattr(self, 'model_input'):
                self.model_input.clear()
            self.api_info_label.setText("未配置接口，请先在接口管理页添加接口。")
            self.model_combo.blockSignals(False)
            return

        model = platform.get('model')
        if isinstance(model, list):
            for item in model:
                self.model_combo.addItem(str(item))
            if model:
                self.model_combo.setCurrentIndex(0)
        elif isinstance(model, str) and model:
            self.model_combo.addItem(model)
            self.model_combo.setCurrentIndex(0)
        else:
            self.model_combo.clear()
            if hasattr(self, 'model_input'):
                self.model_input.clear()

        self.model_combo.blockSignals(False)

        api_url = platform.get('api_url', '')
        name = platform.get('name', '未命名接口')
        self.api_info_label.setText(f"当前接口：{name}（{api_url}）")

        # 同步自定义输入框
        if self.model_combo.count() > 0:
            current_text = self.model_combo.currentText()
            self.model_input.blockSignals(True)
            self.model_input.setText(current_text)
            self.model_input.blockSignals(False)
        else:
            self.model_input.clear()

        # 同步默认参数，避免超出控件取值范围
        temperature = platform.get('temperature')
        if temperature is not None:
            try:
                self.temperature_spin.setValue(max(self.temperature_spin.minimum(),
                                                   min(self.temperature_spin.maximum(), float(temperature))))
            except Exception:
                pass

        top_p = platform.get('top_p')
        if top_p is not None:
            try:
                self.top_p_spin.setValue(max(self.top_p_spin.minimum(),
                                             min(self.top_p_spin.maximum(), float(top_p))))
            except Exception:
                pass

    def _get_selected_platform(self) -> Optional[dict]:
        """获取当前选中的平台配置"""
        data = self.engine_combo.currentData()
        if data is None:
            return None
        return self.platform_map.get(data)

    def _on_model_combo_changed(self, text: str):
        """下拉选择变化时同步到自定义输入框"""
        if not hasattr(self, "model_input"):
            return
        if self.model_input.hasFocus():
            return
        self.model_input.blockSignals(True)
        self.model_input.setText(text)
        self.model_input.blockSignals(False)

    def _create_params_card(self) -> CardWidget:
        """创建参数卡片"""
        from qfluentwidgets import SubtitleLabel, BodyLabel
        
        card = CardWidget(self)
        l = QVBoxLayout(card)

        title = SubtitleLabel("⚙️ 翻译参数")
        l.addWidget(title)

        # 批次大小
        row1 = QHBoxLayout()
        row1.addWidget(BodyLabel("批次大小:"))
        self.batch_size_spin = SpinBox()
        self.batch_size_spin.setRange(1, 50)
        self.batch_size_spin.setValue(10)
        row1.addWidget(self.batch_size_spin)
        row1.addWidget(BodyLabel("条/批次"))
        row1.addStretch()
        l.addLayout(row1)

        # Temperature
        row2 = QHBoxLayout()
        row2.addWidget(BodyLabel("Temperature:"))
        self.temperature_spin = DoubleSpinBox()
        self.temperature_spin.setRange(0.0, 2.0)
        self.temperature_spin.setValue(0.3)
        self.temperature_spin.setSingleStep(0.1)
        row2.addWidget(self.temperature_spin)
        row2.addStretch()
        l.addLayout(row2)

        # Top P
        row3 = QHBoxLayout()
        row3.addWidget(BodyLabel("Top P:"))
        self.top_p_spin = DoubleSpinBox()
        self.top_p_spin.setRange(0.0, 1.0)
        self.top_p_spin.setValue(0.95)
        self.top_p_spin.setSingleStep(0.05)
        row3.addWidget(self.top_p_spin)
        row3.addStretch()
        l.addLayout(row3)

        # 自动保存
        row4 = QHBoxLayout()
        self.auto_save_switch = SwitchButton()
        self.auto_save_switch.setChecked(True)
        row4.addWidget(BodyLabel("自动保存翻译结果:"))
        row4.addWidget(self.auto_save_switch)
        row4.addStretch()
        l.addLayout(row4)

        return card

    def _create_progress_card(self) -> CardWidget:
        """创建进度卡片"""
        from qfluentwidgets import CaptionLabel
        
        card = CardWidget(self)
        l = QVBoxLayout(card)

        self.progress_bar = ProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        l.addWidget(self.progress_bar)

        self.status_label = CaptionLabel("等待开始翻译…")
        l.addWidget(self.status_label)

        return card

    def _create_action_card(self) -> CardWidget:
        """创建操作按钮卡片"""
        card = CardWidget(self)
        l = QHBoxLayout(card)

        self.btn_start = PrimaryPushButton("开始翻译", icon=FluentIcon.PLAY)
        self.btn_stop = PushButton("停止", icon=FluentIcon.CANCEL)
        self.btn_export = PushButton("导出结果", icon=FluentIcon.DOWNLOAD)

        self.btn_start.clicked.connect(self._start_translation)
        self.btn_stop.clicked.connect(self._stop_translation)
        self.btn_export.clicked.connect(self._export_result)

        self.btn_stop.setEnabled(False)
        self.btn_export.setEnabled(False)

        l.addWidget(self.btn_start)
        l.addWidget(self.btn_stop)
        l.addWidget(self.btn_export)
        l.addStretch()

        return card

    # ===== 事件处理 =====

    def _browse_json(self):
        """浏览 JSON 文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择 JSON 文件", "", "JSON 文件 (*.json)"
        )
        if file_path:
            self.json_file_edit.setText(file_path)

    def _start_translation(self):
        """开始翻译（使用 Engine 流程）"""
        json_file = self.json_file_edit.text().strip()
        if not json_file:
            InfoBar.warning("提示", "请选择 JSON 文件", parent=self)
            return
        if not Path(json_file).exists():
            InfoBar.error("错误", "JSON 文件不存在", parent=self)
            return

        platform = self._get_selected_platform()
        if not platform:
            InfoBar.warning("提示", "未检测到有效的接口配置，请先在接口管理中添加接口。", parent=self)
            return

        # 读取 JSON（用于导出/复用，翻译由 Engine 处理）
        try:
            importer = JsonImporter()
            self.translations = importer.import_translations(str(json_file))
            if not self.translations or len(self.translations) == 0:
                InfoBar.warning("提示", "JSON 文件中没有可翻译的内容", parent=self)
                return
        except Exception as e:
            LogManager.get().error(f"读取 JSON 失败: {e}")
            InfoBar.error("错误", f"读取 JSON 失败: {e}", parent=self)
            return

        # 加载配置并覆盖与本页相关的字段
        try:
            config = Config().load()
            config.input_folder = str(Path(json_file).parent)
            config.output_folder = str(Path(json_file).parent / "output_engine")
            config.activate_platform = platform.get("id", config.activate_platform)
            config.platforms = config.platforms or []
            
            # 确保输出目录存在
            Path(config.output_folder).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.logger.error(f"加载配置失败: {e}")
            InfoBar.error("错误", f"加载配置失败: {e}", parent=self)
            return

        # 更新 UI 状态
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.btn_export.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_label.setText("翻译中...")
        self.status_label.setStyleSheet("color: #0078d4;")

        # 触发 Engine 翻译事件
        # 使用正确的事件触发方式，让 Translator 类处理实际的翻译逻辑
        self.emit(Base.Event.TRANSLATION_START, {
            "config": config,
            "status": Base.TranslationStatus.UNTRANSLATED,
        })

        InfoBar.success("已开始", "翻译任务已启动，进度请查看日志面板", parent=self)

    def _stop_translation(self):
        """停止翻译"""
        self.emit(Base.Event.TRANSLATION_STOP, {})
        self.btn_stop.setEnabled(False)
        self.status_label.setText("正在停止...")
        InfoBar.info("提示", "已请求停止翻译（Engine）", parent=self)

    def _export_result(self):
        """导出翻译结果"""
        if not hasattr(self, 'translations') or not self.translations:
            InfoBar.warning("提示", "没有可导出的翻译结果", parent=self)
            return

        save_path, _ = QFileDialog.getSaveFileName(
            self, "保存翻译结果", "", "JSON 文件 (*.json)"
        )
        if not save_path:
            return

        try:
            exporter = JsonExporter()
            if exporter.export(self.translations, save_path, include_metadata=True):
                LogManager.get().info(f"翻译结果已导出: {save_path}")
                InfoBar.success("成功", f"翻译结果已导出到:\n{save_path}", parent=self)
            else:
                InfoBar.error("错误", "导出失败", parent=self)
        except Exception as e:
            LogManager.get().error(f"导出失败: {e}")
            InfoBar.error("错误", f"导出失败: {e}", parent=self)

    def _on_progress(self, current: int, total: int, message: str):
        """进度更新"""
        if total > 0:
            ratio = max(0.0, min(1.0, current / total))
            self.progress_bar.setValue(int(ratio * 100))
        self.status_label.setText(message)

    def _on_text_translated(self, payload: dict):
        """单条文本翻译完成"""
        original = payload.get('original')
        translated = payload.get('translated')
        file_name = payload.get('file')
        index = payload.get('index')

        if file_name in self.translations and isinstance(index, int):
            file_items = self.translations[file_name]
            if 0 <= index < len(file_items):
                file_items[index]['translation'] = translated

        if self.auto_save_enabled:
            self._incremental_save(file_name, index, translated)

    def _on_finished(self, success: bool, message: str):
        """翻译完成"""
        self.progress_bar.setValue(100)
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.btn_export.setEnabled(True)

    # ===== Engine 事件回调（统一进度） =====

    def _on_engine_done(self, event, data):
        self.progress_bar.setValue(100)
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.btn_export.setEnabled(True)
        self.status_label.setText("翻译完成！")
        self.status_label.setStyleSheet("color: green;")
        InfoBar.success("完成", "Engine 翻译完成", parent=self)

    def _on_engine_stop(self, event, data):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)

    def _on_engine_update(self, event, extras):
        if not isinstance(extras, dict):
            return
        total = extras.get("total_line", 0) or 0
        current = extras.get("line", 0) or 0
        if total > 0:
            ratio = max(0.0, min(1.0, current / total))
            self.progress_bar.setValue(int(ratio * 100))
        self.status_label.setText(f"翻译中… {current}/{total}")

    # ===== 自动保存辅助 =====

    def _reset_auto_save_state(self):
        """清理自动保存状态"""
        self.auto_save_path = None
        self._last_auto_save = 0.0

    def _prepare_auto_save(self, json_file: str):
        """准备自动保存副本"""
        try:
            source_path = Path(json_file)
            if source_path.stem.endswith("_autosave"):
                autosave_path = source_path
            else:
                autosave_path = source_path.with_name(f"{source_path.stem}_autosave.json")
            exporter = JsonExporter()
            if not exporter.export(self.translations, str(autosave_path), include_metadata=True):
                raise RuntimeError("初始导出失败")

            self.auto_save_path = str(autosave_path)
            self._last_auto_save = time.time()
            if source_path == autosave_path:
                self.logger.info(f"自动保存启用，复用现有文件: {self.auto_save_path}")
                InfoBar.info("自动保存启用", f"继续写入已有自动保存：\n{self.auto_save_path}", parent=self)
            else:
                self.logger.info(f"自动保存启用，副本路径: {self.auto_save_path}")
                InfoBar.info("自动保存启用", f"翻译结果将实时写入副本：\n{self.auto_save_path}", parent=self)
        except Exception as e:
            self.logger.error(f"准备自动保存失败: {e}")
            InfoBar.warning("提示", f"无法启用自动保存：{e}", parent=self)
            self.auto_save_enabled = False
            self._reset_auto_save_state()

    def _incremental_save(self, _: str, __: Optional[int], ___: Optional[str]):
        """将翻译结果写入自动保存文件（节流写入）。"""
        if not (self.auto_save_enabled and self.auto_save_path):
            return

        now = time.time()
        if now - self._last_auto_save < 1.0:
            return

        try:
            exporter = JsonExporter()
            if not exporter.export(self.translations, self.auto_save_path, include_metadata=True):
                raise RuntimeError("写入失败")
            self._last_auto_save = now
        except Exception as e:
            self.logger.error(f"自动保存失败: {e}")
            InfoBar.warning("提示", f"自动保存失败：{e}", parent=self)
            self.auto_save_enabled = False

    def _finalize_auto_save(self):
        """翻译完成时刷新自动保存文件"""
        if not (self.auto_save_enabled and self.auto_save_path):
            return
        try:
            exporter = JsonExporter()
            if not exporter.export(self.translations, self.auto_save_path, include_metadata=True):
                raise RuntimeError("写入失败")
        except Exception as e:
            self.logger.error(f"自动保存最终写入失败: {e}")
