"""
批量修正页面 - 完整实现
基于 LinguaGacha 的 BatchCorrectionPage 移植；业务委托 AssetSuiteOps。
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
from base.BaseLanguage import BaseLanguage
from base.LogManager import LogManager
from module.Config import Config
from module.Localizer.Localizer import Localizer
from module.Tool.AssetSuiteOps import (
    BATCH_WORKBOOK_NAME,
    FILE_NAME_BLACKLIST,
    FILE_NAME_WHITELIST,
    AssetSuiteError,
    apply_batch_corrections,
    export_batch_correction_workbook,
)
from widget.EmptyCard import EmptyCard
from widget.CommandBarCard import CommandBarCard
from widget.ThemeHelper import mark_toolbox_widget, mark_toolbox_scroll_area


class BatchCorrectionPage(Base, QWidget):
    """批量修正页面 - 完整功能实现"""

    FILE_NAME_WHITELIST = FILE_NAME_WHITELIST
    FILE_NAME_BLACKLIST = FILE_NAME_BLACKLIST

    def __init__(self, object_name: str, parent=None):
        Base.__init__(self)
        QWidget.__init__(self, parent)
        self.setObjectName(object_name)
        mark_toolbox_widget(self)

        self.window = parent
        self.input_folder = ""
        self.output_folder = ""
        self.translation_root = ""
        self.workbook_path = ""

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(24, 24, 24, 24)

        title_card = EmptyCard(
            title=Localizer.localize("批量修正", "Batch Corrections"),
            description=Localizer.localize(
                "根据翻译完成时生成的结果检查文件中的数据，对可能存在的翻译错误进行批量修正，然后原地写入译文文件<br><br>"
                "<b>工作流程：</b><br>"
                "• 从输入文件夹的翻译结果检查文件中提取可能需要修正的数据<br>"
                "• 检查提取出的数据，并根据实际情况对需要修正的条目进行修正<br>"
                "• 将修正后的数据注入选定译文目录（原地写入，每个文件生成 .bak）",
                "Use result-check files to review possible translation errors in Excel, then apply the corrections in place under the selected translation root.",
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
            title=Localizer.localize("第一步 - 生成修正数据", "Step 1 - Generate Correction Data"),
            description=Localizer.localize(
                "从结果检查文件中提取可能包含翻译错误的数据<br>"
                "然后自动在输出文件夹内生成用于编辑的数据文件 <b>批量修正.xlsx</b>",
                "Extract possible translation errors from result-check files and create an editable <b>批量修正.xlsx</b> workbook.",
            ),
            init=init,
        )

    def _create_step2_card(self) -> EmptyCard:
        def init(widget: EmptyCard) -> None:
            btn = PushButton(FluentIcon.SAVE_AS, Localizer.get().inject)
            btn.clicked.connect(self._step_02_clicked)
            widget.add_widget(btn)

        return EmptyCard(
            title=Localizer.localize("第二步 - 注入修正数据", "Step 2 - Apply Corrections"),
            description=Localizer.localize(
                "检查数据文件中的内容，确认无误后关闭文件，开始注入<br><br>"
                "<b>请注意：</b><br>"
                "• 除<b>修正列</b>以外，不要修改数据文件内的其他数据<br>"
                "• 注入会原地修改选定译文目录中的文件，并在首次写入前创建 .bak<br>"
                "• 部分格式的译文文件名中会包含类似 .zh 的语言后缀，在注入前请从文件名中移除语言后缀以正确匹配数据",
                "Review and close the workbook, then apply its corrections in place. Edit only the correction column, remove language suffixes such as .zh when needed, and expect .bak backups before the first write.",
            ),
            init=init,
        )

    def _step_01_clicked(self):
        try:
            if not self.input_folder:
                self.input_folder = QFileDialog.getExistingDirectory(
                    self, Localizer.localize("选择包含结果检查文件的输入文件夹", "Select the Folder Containing Result-check Files"), ""
                )
                if not self.input_folder:
                    return

            if not self.output_folder:
                self.output_folder = QFileDialog.getExistingDirectory(
                    self, Localizer.localize("选择输出文件夹", "Select Output Folder"), self.input_folder
                )
                if not self.output_folder:
                    return

            LogManager.get().info(f"开始生成批量修正数据：{self.input_folder}")
            output_path = Path(self.output_folder) / BATCH_WORKBOOK_NAME
            confirm = False
            if output_path.exists():
                answer = QMessageBox.question(
                    self,
                    Localizer.get().notice,
                    Localizer.localize(
                        "修正工作簿已存在，继续将先备份再覆盖：\n{path}\n是否继续？",
                        "The correction workbook already exists and will be backed up before overwriting:\n{path}\nContinue?",
                    ).format(path=output_path),
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if answer != QMessageBox.Yes:
                    return
                confirm = True

            result = export_batch_correction_workbook(
                self.input_folder,
                self.output_folder,
                english=Localizer.get_app_language() == BaseLanguage.Enum.EN,
                confirm_overwrite=confirm,
            )
            self.workbook_path = result["path"]
            warnings = result.get("warnings") or []
            detail = Localizer.localize(
                "已生成修正数据文件（共 {count} 条数据）\n{path}",
                "Generated a correction workbook with {count} entries.\n{path}",
            ).format(count=result["count"], path=result["path"])
            if result.get("backup_path"):
                detail += Localizer.localize("\n备份：{path}", "\nBackup: {path}").format(path=result["backup_path"])
            if warnings:
                detail += "\n" + "\n".join(warnings[:5])
            tone = InfoBar.warning if warnings else InfoBar.success
            tone(
                Localizer.localize("部分完成", "Partially Complete") if warnings else Localizer.localize("任务完成", "Task Complete"),
                detail,
                parent=self,
            )
            for warning in warnings:
                LogManager.get().warning(warning)
        except AssetSuiteError as exc:
            InfoBar.warning(Localizer.get().notice, str(exc), parent=self)
        except Exception as e:
            LogManager.get().error(f"生成修正数据失败: {e}")
            InfoBar.error(
                Localizer.get().error,
                Localizer.localize("生成修正数据失败: {error}", "Failed to generate correction data: {error}").format(error=e),
                parent=self,
            )

    def _step_02_clicked(self):
        try:
            if not self.workbook_path:
                if not self.output_folder:
                    self.output_folder = QFileDialog.getExistingDirectory(
                        self, Localizer.localize("选择包含批量修正.xlsx的输出文件夹", "Select the Folder Containing 批量修正.xlsx"), ""
                    )
                    if not self.output_folder:
                        return
                self.workbook_path = str(Path(self.output_folder) / BATCH_WORKBOOK_NAME)

            if not Path(self.workbook_path).exists():
                InfoBar.warning(
                    Localizer.get().notice,
                    Localizer.localize("未找到批量修正.xlsx文件，请先执行步骤一", "批量修正.xlsx was not found. Run step 1 first."),
                    parent=self,
                )
                return

            if not self._ensure_translation_root():
                InfoBar.info(Localizer.get().notice, Localizer.localize("已取消注入操作。", "The apply operation was cancelled."), parent=self)
                return

            LogManager.get().info("开始注入修正数据")
            result = apply_batch_corrections(
                self.workbook_path,
                self.translation_root,
                confirm=True,
            )
            warnings = result.get("warnings") or []
            unmatched = result.get("unmatched") or []
            applied = result.get("applied_changes", 0)
            detail = result.get("message") or ""
            if unmatched:
                details = "\n".join(
                    Localizer.localize("{path}（未匹配 {count} 项）：{reason}", "{path} ({count} unmatched): {reason}").format(
                        path=item.get("path"), count=len(item.get("items") or []), reason=item.get("reason") or ""
                    )
                    for item in unmatched[:5]
                )
                detail += "\n" + details
                LogManager.get().warning(f"有未应用修正。\n{details}")
            if result.get("backups"):
                detail += Localizer.localize("\n备份：\n", "\nBackups:\n") + "\n".join(result["backups"][:5])
            if warnings:
                detail += "\n" + "\n".join(warnings[:5])
                for warning in warnings:
                    LogManager.get().warning(warning)
            if result.get("level") == "error":
                tone = InfoBar.error
                title = Localizer.get().error
            elif result.get("partial") or warnings or unmatched or not applied:
                tone = InfoBar.warning
                title = Localizer.localize("部分完成", "Partially Complete") if applied else Localizer.get().notice
            else:
                tone = InfoBar.success
                title = Localizer.localize("注入完成", "Corrections Applied")
            tone(title, detail, parent=self)
        except AssetSuiteError as exc:
            InfoBar.warning(Localizer.get().notice, str(exc), parent=self)
        except Exception as e:
            LogManager.get().error(f"注入修正数据失败: {e}")
            InfoBar.error(
                Localizer.get().error,
                Localizer.localize("注入修正数据失败: {error}", "Failed to apply correction data: {error}").format(error=e),
                parent=self,
            )

    def _ensure_translation_root(self) -> bool:
        if not self.translation_root or not Path(self.translation_root).is_dir():
            default_root = ""
            try:
                config = Config().load()
                default_root = config.renpy_tl_folder or config.renpy_game_folder or ""
            except Exception:
                pass

            folder = QFileDialog.getExistingDirectory(
                self,
                Localizer.localize("选择翻译文件所在目录（通常为 tl/<语言> 目录）", "Select the Translation Folder (usually tl/<language>)"),
                default_root,
            )
            if not folder:
                return False
            self.translation_root = folder
            LogManager.get().info(f"已选择译文目录: {folder}")

        answer = QMessageBox.question(
            self,
            Localizer.get().notice,
            Localizer.localize(
                "将使用工作簿中的修正原地修改译文目录，并在首次写入前创建 .bak：\n工作簿：{workbook}\n译文目录：{root}\n请关闭 Excel。是否继续？",
                "Apply workbook corrections in place, creating .bak backups before the first write:\nWorkbook: {workbook}\nTranslation folder: {root}\nClose Excel before continuing. Continue?",
            ).format(workbook=self.workbook_path, root=self.translation_root),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return answer == QMessageBox.Yes
