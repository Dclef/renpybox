"""
姓名字段提取页面 - 完整实现
基于 LinguaGacha 的 NameFieldExtractionPage 移植
"""
import re
import time
from pathlib import Path

from PyQt5.QtGui import QDesktopServices
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QFileDialog
from qfluentwidgets import (
    PushButton,
    InfoBar,
    MessageBox,
    FluentIcon,
    SingleDirectionScrollArea,
    TransparentPushButton,
)

from base.Base import Base
from base.LogManager import LogManager
from widget.EmptyCard import EmptyCard
from widget.CommandBarCard import CommandBarCard
from widget.ThemeHelper import mark_toolbox_widget, mark_toolbox_scroll_area


class NameExtractionPage(Base, QWidget):
    """姓名字段提取页面 - 完整功能实现"""
    
    # Ren'Py 角色定义正则表达式
    # 匹配: define character_name = Character("显示名")
    RE_RENPY_CHARACTER = re.compile(
        r'define\s+(\w+)\s*=\s*Character\s*\(\s*["\']([^"\']+)["\']',
        re.MULTILINE
    )
    
    # 匹配带 name 字段的 JSON 格式
    # 用于 VNTextPatch 或 SExtractor 导出的格式
    RE_JSON_NAME_FIELD = re.compile(r'"name"\s*:\s*"([^"]+)"')

    def __init__(self, object_name: str, parent=None):
        Base.__init__(self)
        QWidget.__init__(self, parent)
        self.setObjectName(object_name)
        mark_toolbox_widget(self)
        
        self.window = parent
        self.input_folder = ""
        self.output_folder = ""
        self.extracted_names = {}  # {原文姓名: 上下文}
        
        self._init_ui()

    def _init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(24, 24, 24, 24)

        # 标题卡片
        title_card = EmptyCard(
            title="姓名字段提取",
            description=(
                "将从输入文件夹中所有符合条件的文件中提取角色姓名字段，自动生成对应的术语表数据<br><br>"
                "<b>请注意：</b>此功能不能提取正文内的术语，不能代替 KeywordGacha 工具<br><br>"
                "<b>支持格式：</b><br>"
                "• Ren'Py 导出游戏文本（.rpy）<br>"
                "• VNTextPatch 或 SExtractor 导出带 name 字段的游戏文本（.json）"
            ),
            init=None,
        )
        layout.addWidget(title_card)

        # 创建滚动区域
        scroll_area = SingleDirectionScrollArea(orient=Qt.Orientation.Vertical)
        scroll_area.setWidgetResizable(True)
        scroll_area.enableTransparentBackground()
        mark_toolbox_scroll_area(scroll_area)

        scroll_widget = QWidget()
        mark_toolbox_widget(scroll_widget, "toolboxScroll")
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(12)

        # 添加步骤卡片
        scroll_layout.addWidget(self._create_step1_card())
        scroll_layout.addWidget(self._create_step2_card())
        scroll_layout.addStretch(1)
        
        scroll_area.setWidget(scroll_widget)
        layout.addWidget(scroll_area)

        # 底部命令栏
        self.command_bar_card = CommandBarCard()
        layout.addWidget(self.command_bar_card)
        self.command_bar_card.add_stretch(1)
        
        wiki_btn = TransparentPushButton(FluentIcon.HELP, "帮助文档")
        wiki_btn.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl("https://github.com/dclef/RenpyBox/wiki")
        ))
        self.command_bar_card.add_widget(wiki_btn)

    def _create_step1_card(self) -> EmptyCard:
        """创建步骤一卡片"""
        def init(widget: EmptyCard) -> None:
            btn = PushButton(FluentIcon.PLAY, "开始")
            btn.clicked.connect(self._step_01_clicked)
            widget.add_widget(btn)

        return EmptyCard(
            title="第一步 - 提取数据",
            description=(
                "提取姓名字段及与其相关的上下文，发送至翻译器进行翻译<br>"
                "（如果不需要翻译，可以直接执行第二步生成术语表）"
            ),
            init=init,
        )

    def _create_step2_card(self) -> EmptyCard:
        """创建步骤二卡片"""
        def init(widget: EmptyCard) -> None:
            btn = PushButton(FluentIcon.SAVE_AS, "生成")
            btn.clicked.connect(self._step_02_clicked)
            widget.add_widget(btn)

        return EmptyCard(
            title="第二步 - 生成术语表",
            description=(
                "从提取的姓名数据中生成术语表<br>"
                "然后生成对应的术语表数据，检查生成的术语表数据是否正确"
            ),
            init=init,
        )

    def _step_01_clicked(self):
        """第一步：提取姓名字段"""
        try:
            # 选择输入文件夹
            if not self.input_folder:
                self.input_folder = QFileDialog.getExistingDirectory(
                    self, "选择包含 Ren'Py 脚本的输入文件夹", ""
                )
                if not self.input_folder:
                    return
            
            LogManager.get().info(f"开始提取姓名字段：{self.input_folder}")
            
            name_src_dict: dict[str, str] = {}
            input_path = Path(self.input_folder)
            
            # 扫描 .rpy 文件
            rpy_files = list(input_path.rglob("*.rpy"))
            for rpy_file in rpy_files:
                try:
                    with open(rpy_file, "r", encoding="utf-8") as f:
                        content = f.read()
                        
                        # 查找角色定义
                        matches = self.RE_RENPY_CHARACTER.findall(content)
                        for var_name, display_name in matches:
                            # 获取上下文（定义所在行及后续几行）
                            lines = content.split("\n")
                            for i, line in enumerate(lines):
                                if f"define {var_name}" in line:
                                    # 提取定义行及后续 3 行作为上下文
                                    context = "\n".join(lines[i:min(i+4, len(lines))])
                                    if display_name not in name_src_dict or len(context) > len(name_src_dict.get(display_name, "")):
                                        name_src_dict[display_name] = context
                                    break
                except Exception as e:
                    LogManager.get().warning(f"读取文件失败 {rpy_file.name}: {e}")
                    continue
            
            # 扫描 .json 文件（带 name 字段）
            json_files = list(input_path.rglob("*.json"))
            for json_file in json_files:
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        content = f.read()
                        
                        # 查找 name 字段
                        matches = self.RE_JSON_NAME_FIELD.findall(content)
                        for name in matches:
                            if name and name not in name_src_dict:
                                name_src_dict[name] = f"[从 {json_file.name} 提取]"
                except Exception as e:
                    LogManager.get().warning(f"读取文件失败 {json_file.name}: {e}")
                    continue
            
            # 有效性检查
            if len(name_src_dict) == 0:
                InfoBar.warning("提示", "未找到任何角色姓名定义，请检查输入文件夹", parent=self)
                return
            
            # 保存提取结果
            self.extracted_names = name_src_dict
            
            LogManager.get().info(f"提取完成，找到 {len(name_src_dict)} 个角色姓名")
            InfoBar.success(
                "提取完成", 
                f"找到 {len(name_src_dict)} 个角色姓名\n"
                f"如需翻译，请配置翻译引擎后使用翻译功能\n"
                f"否则可直接执行第二步生成术语表",
                parent=self
            )
            
            # 显示提取的姓名列表（前10个）
            preview = "\n".join(list(name_src_dict.keys())[:10])
            if len(name_src_dict) > 10:
                preview += f"\n... 还有 {len(name_src_dict) - 10} 个"
            LogManager.get().info(f"提取的姓名：\n{preview}")
            
        except Exception as e:
            LogManager.get().error(f"提取姓名字段失败: {e}")
            InfoBar.error("错误", f"提取姓名字段失败: {e}", parent=self)

    def _step_02_clicked(self):
        """第二步：生成术语表"""
        try:
            # 检查是否已提取姓名
            if not self.extracted_names:
                InfoBar.warning("提示", "请先执行步骤一提取姓名字段", parent=self)
                return
            
            # 选择输出文件
            if not self.output_folder:
                default_path = str(Path(self.input_folder or ".") / "glossary_names.txt")
            else:
                default_path = str(Path(self.output_folder) / "glossary_names.txt")
            
            output_file, _ = QFileDialog.getSaveFileName(
                self, "保存术语表文件", default_path,
                "文本文件 (*.txt);;JSON文件 (*.json);;所有文件 (*.*)"
            )
            if not output_file:
                return
            
            LogManager.get().info(f"开始生成术语表：{output_file}")
            
            # 生成术语表格式
            # 格式：原文 -> 译文 #备注
            glossary_lines = []
            for src_name, context in self.extracted_names.items():
                # 默认译文与原文相同（用户需要手动修改）
                dst_name = src_name
                info = "角色姓名"
                glossary_lines.append(f"{src_name} -> {dst_name} #{info}")
            
            # 保存术语表
            output_path = Path(output_file)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("\n".join(glossary_lines))
            
            LogManager.get().info(f"术语表已生成: {output_path}")
            InfoBar.success(
                "任务完成", 
                f"已生成术语表文件（共 {len(glossary_lines)} 个条目）\n{output_path}\n\n"
                f"请手动编辑文件，将 -> 右侧修改为正确的译文",
                parent=self
            )
            
            # 显示术语表预览（前5个）
            preview = "\n".join(glossary_lines[:5])
            if len(glossary_lines) > 5:
                preview += f"\n... 还有 {len(glossary_lines) - 5} 个"
            LogManager.get().info(f"术语表预览：\n{preview}")
            
        except Exception as e:
            LogManager.get().error(f"生成术语表失败: {e}")
            InfoBar.error("错误", f"生成术语表失败: {e}", parent=self)

    def _parse_glossary_from_translations(self, translations: dict[str, str]) -> dict[str, str]:
        """从翻译结果中解析术语表（如果姓名已被翻译）"""
        # 尝试从翻译结果中提取【姓名】格式
        glossary = {}
        for src, dst in translations.items():
            # 提取【】或[]中的内容
            src_match = re.search(r'[【\[]([^】\]]+)[】\]]', src)
            dst_match = re.search(r'[【\[]([^】\]]+)[】\]]', dst)
            
            if src_match and dst_match:
                src_name = src_match.group(1)
                dst_name = dst_match.group(1)
                if src_name and dst_name:
                    glossary[src_name] = dst_name
        
        return glossary
