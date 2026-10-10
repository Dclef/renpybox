"""
姓名字段提取页面 - 完整实现
业务委托 AssetSuiteOps；支持 TXT 与 JSON 真实导出。
"""
from pathlib import Path

from PyQt5.QtGui import QDesktopServices
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QFileDialog, QMessageBox
from qfluentwidgets import (
    PushButton,
    InfoBar,
    FluentIcon,
    SingleDirectionScrollArea,
    TransparentPushButton,
)

from base.Base import Base
from base.LogManager import LogManager
from module.Localizer.Localizer import Localizer
from module.Tool.AssetSuiteOps import AssetSuiteError, export_name_glossary, extract_character_names
from widget.EmptyCard import EmptyCard
from widget.CommandBarCard import CommandBarCard
from widget.ThemeHelper import mark_toolbox_widget, mark_toolbox_scroll_area


class NameExtractionPage(Base, QWidget):
    """姓名字段提取页面 - 完整功能实现"""

    def __init__(self, object_name: str, parent=None):
        Base.__init__(self)
        QWidget.__init__(self, parent)
        self.setObjectName(object_name)
        mark_toolbox_widget(self)

        self.window = parent
        self.input_folder = ""
        self.output_folder = ""
        self.extracted_entries: list[dict] = []

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(24, 24, 24, 24)

        title_card = EmptyCard(
            title=Localizer.localize("姓名字段提取", "Name Extraction"),
            description=Localizer.localize(
                "将从输入文件夹中所有符合条件的文件中提取角色姓名字段，自动生成对应的术语表数据<br><br>"
                "<b>请注意：</b>此功能不能提取正文内的术语，不能代替 KeywordGacha 工具<br><br>"
                "<b>支持格式：</b><br>"
                "• Ren'Py 导出游戏文本（.rpy）<br>"
                "• VNTextPatch 或 SExtractor 导出带 name 字段的游戏文本（.json）",
                "Extract character names from Ren'Py .rpy files and VNTextPatch or SExtractor .json files, then create glossary data. This does not extract terms from dialogue text.",
            ),
            init=None,
        )
        layout.addWidget(title_card)

        scroll_area = SingleDirectionScrollArea(orient=Qt.Orientation.Vertical)
        scroll_area.setWidgetResizable(True)
        scroll_area.enableTransparentBackground()
        mark_toolbox_scroll_area(scroll_area)

        scroll_widget = QWidget()
        mark_toolbox_widget(scroll_widget, "toolboxScroll")
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(12)

        scroll_layout.addWidget(self._create_step1_card())
        scroll_layout.addWidget(self._create_step2_card())
        scroll_layout.addStretch(1)

        scroll_area.setWidget(scroll_widget)
        layout.addWidget(scroll_area)

        self.command_bar_card = CommandBarCard()
        layout.addWidget(self.command_bar_card)
        self.command_bar_card.add_stretch(1)

        wiki_btn = TransparentPushButton(FluentIcon.HELP, Localizer.get().wiki)
        wiki_btn.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl("https://github.com/dclef/RenpyBox/wiki")
        ))
        self.command_bar_card.add_widget(wiki_btn)

    def _create_step1_card(self) -> EmptyCard:
        def init(widget: EmptyCard) -> None:
            btn = PushButton(FluentIcon.PLAY, Localizer.get().start)
            btn.clicked.connect(self._step_01_clicked)
            widget.add_widget(btn)

        return EmptyCard(
            title=Localizer.localize("第一步 - 提取数据", "Step 1 - Extract Names"),
            description=Localizer.localize(
                "提取姓名字段及与其相关的上下文<br>"
                "（如果不需要翻译，可以直接执行第二步生成术语表）",
                "Extract names and their context. You can continue directly to step 2 when translation is not required.",
            ),
            init=init,
        )

    def _create_step2_card(self) -> EmptyCard:
        def init(widget: EmptyCard) -> None:
            btn = PushButton(FluentIcon.SAVE_AS, Localizer.get().generate)
            btn.clicked.connect(self._step_02_clicked)
            widget.add_widget(btn)

        return EmptyCard(
            title=Localizer.localize("第二步 - 生成术语表", "Step 2 - Generate Glossary"),
            description=Localizer.localize(
                "从提取的姓名数据中生成术语表（TXT 或 JSON）",
                "Generate a glossary from the extracted names as TXT or JSON, then review the resulting entries.",
            ),
            init=init,
        )

    def _step_01_clicked(self):
        try:
            if not self.input_folder:
                self.input_folder = QFileDialog.getExistingDirectory(
                    self, Localizer.localize("选择包含 Ren'Py 脚本的输入文件夹", "Select the Folder Containing Ren'Py Scripts"), ""
                )
                if not self.input_folder:
                    return

            LogManager.get().info(f"开始提取姓名字段：{self.input_folder}")
            result = extract_character_names(self.input_folder)
            warnings = result.get("warnings") or []
            for warning in warnings:
                LogManager.get().warning(warning)
            if result.get("empty"):
                InfoBar.warning(
                    Localizer.get().notice,
                    Localizer.localize("未找到任何角色姓名定义，请检查输入文件夹", "No character-name definitions were found. Check the input folder.")
                    + ("\n" + "\n".join(warnings[:5]) if warnings else ""),
                    parent=self,
                )
                return

            self.extracted_entries = list(result.get("entries") or [])
            tone = InfoBar.warning if warnings else InfoBar.success
            tone(
                Localizer.localize("部分完成", "Partially Complete") if warnings else Localizer.localize("提取完成", "Extraction Complete"),
                Localizer.localize(
                    "找到 {count} 个角色姓名\n可直接执行第二步生成术语表",
                    "Found {count} character name(s). Continue to step 2 to generate the glossary.",
                ).format(count=result.get("count", 0))
                + ("\n" + "\n".join(warnings[:5]) if warnings else ""),
                parent=self,
            )
            preview = "\n".join(item["src"] for item in self.extracted_entries[:10])
            if len(self.extracted_entries) > 10:
                preview += f"\n... 还有 {len(self.extracted_entries) - 10} 个"
            LogManager.get().info(f"提取的姓名：\n{preview}")
        except AssetSuiteError as exc:
            InfoBar.warning(Localizer.get().notice, str(exc), parent=self)
        except Exception as e:
            LogManager.get().error(f"提取姓名字段失败: {e}")
            InfoBar.error(
                Localizer.get().error,
                Localizer.localize("提取姓名字段失败: {error}", "Name extraction failed: {error}").format(error=e),
                parent=self,
            )

    def _step_02_clicked(self):
        try:
            if not self.extracted_entries:
                InfoBar.warning(
                    Localizer.get().notice,
                    Localizer.localize("请先执行步骤一提取姓名字段", "Run step 1 to extract names first."),
                    parent=self,
                )
                return

            if not self.output_folder:
                default_path = str(Path(self.input_folder or ".") / "glossary_names.txt")
            else:
                default_path = str(Path(self.output_folder) / "glossary_names.txt")

            output_file, selected_filter = QFileDialog.getSaveFileName(
                self,
                Localizer.localize("保存术语表文件", "Save Glossary File"),
                default_path,
                Localizer.localize(
                    "文本文件 (*.txt);;JSON文件 (*.json);;所有文件 (*.*)",
                    "Text Files (*.txt);;JSON Files (*.json);;All Files (*.*)",
                ),
            )
            if not output_file:
                return

            fmt = "json" if output_file.lower().endswith(".json") or "JSON" in (selected_filter or "").upper() else "txt"
            if fmt == "json" and not output_file.lower().endswith(".json"):
                output_file += ".json"
            if fmt == "txt" and not output_file.lower().endswith(".txt"):
                output_file += ".txt"

            confirm_overwrite = False
            if Path(output_file).exists():
                answer = QMessageBox.question(
                    self,
                    Localizer.get().notice,
                    Localizer.localize(
                        "术语表已存在，继续将先备份再覆盖：\n{path}\n是否继续？",
                        "The glossary already exists and will be backed up before overwriting:\n{path}\nContinue?",
                    ).format(path=output_file),
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if answer != QMessageBox.Yes:
                    return
                confirm_overwrite = True

            LogManager.get().info(f"开始生成术语表：{output_file}")
            result = export_name_glossary(
                self.extracted_entries,
                format=fmt,
                output_file=output_file,
                confirm_overwrite=confirm_overwrite,
            )
            self.output_folder = str(Path(output_file).parent)
            InfoBar.success(
                Localizer.localize("任务完成", "Task Complete"),
                Localizer.localize(
                    "已生成术语表文件（共 {count} 个条目）\n{path}\n\n请手动编辑文件，将译文修改为正确译名",
                    "Generated a glossary with {count} entries.\n{path}\n\nEdit the file and replace the destination text with the correct translation.",
                ).format(count=result["count"], path=result.get("path") or output_file),
                parent=self,
            )
        except AssetSuiteError as exc:
            InfoBar.warning(Localizer.get().notice, str(exc), parent=self)
        except Exception as e:
            LogManager.get().error(f"生成术语表失败: {e}")
            InfoBar.error(
                Localizer.get().error,
                Localizer.localize("生成术语表失败: {error}", "Glossary generation failed: {error}").format(error=e),
                parent=self,
            )
