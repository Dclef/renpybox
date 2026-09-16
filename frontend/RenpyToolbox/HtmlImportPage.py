"""
网页 / AI 翻译向导

三步工作流（面向新手）：
1. 选 game/tl/<语言> 目录，提取待翻译文本成 TXT（每行一条，带行号清单）；
2. 把 TXT 交给 AI 或 Google 网页翻译，得到译文 TXT；
3. 选译文 TXT，按行号回填 new 字段，生成翻译完成的 TL 目录。

只处理官方抽取结果；带 renpybox: replace-only 标记的补充抽取条目不参与。
旧的 HTML/TXT/Excel 互转高级功能折叠在底部，默认隐藏。
"""

import json
import os
from pathlib import Path
from typing import List

from bs4 import BeautifulSoup
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFileDialog,
)
from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    PushButton,
    PrimaryPushButton,
    LineEdit,
    CheckBox,
    ComboBox,
    InfoBar,
    FluentIcon,
    StrongBodyLabel,
    TitleLabel,
    CaptionLabel,
    SingleDirectionScrollArea,
)

from base.Base import Base
from base.LogManager import LogManager
from module.Localizer.Localizer import Localizer
from widget.ThemeHelper import mark_toolbox_widget, mark_toolbox_scroll_area, set_text_role


class HtmlImportPage(Base, QWidget):
    """网页 / AI 翻译向导（原 HTML 导入工具）"""

    def __init__(self, object_name: str, parent=None):
        Base.__init__(self)
        QWidget.__init__(self, parent)
        self.setObjectName(object_name)
        self.logger = LogManager.get()
        self._init_ui()

    # ==================== UI ====================
    def _init_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = SingleDirectionScrollArea(orient=Qt.Orientation.Vertical)
        scroll.setWidgetResizable(True)
        scroll.enableTransparentBackground()
        mark_toolbox_scroll_area(scroll)

        container = QWidget()
        mark_toolbox_widget(container, "toolboxScroll")
        layout = QVBoxLayout(container)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        title = TitleLabel(
            Localizer.localize("网页 / AI 翻译向导", "Web / AI Translation Wizard"), self
        )
        layout.addWidget(title)

        desc = BodyLabel(
            Localizer.localize(
                "把一键翻译抽取后的 game/tl/<语言> 目录变成 TXT，交给 AI 或 Google 网页翻译，"
                "再一键回填生成翻译完成的 TL 目录。全程只需三步。",
                "Turn the game/tl/<language> folder from extraction into a TXT, translate it "
                "with AI or Google web translation, then write it back to a finished TL folder. "
                "Three steps, no manual editing.",
            ),
            self,
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        layout.addWidget(self._build_step1_card())
        layout.addWidget(self._build_step2_card())
        layout.addWidget(self._build_step3_card())

        # 高级：旧的 HTML/TXT/Excel 互转，折叠隐藏
        self._advanced_toggle = PushButton(
            Localizer.localize("高级：HTML / TXT / Excel 互转", "Advanced: HTML / TXT / Excel conversion"),
            self,
        )
        self._advanced_toggle.setFlat(True)
        self._advanced_toggle.clicked.connect(self._toggle_advanced)
        layout.addWidget(self._advanced_toggle)

        self._advanced_widget = QWidget(self)
        adv_layout = QVBoxLayout(self._advanced_widget)
        adv_layout.setContentsMargins(0, 0, 0, 0)
        adv_layout.setSpacing(12)
        adv_layout.addWidget(self._build_html_to_txt_card())
        adv_layout.addWidget(self._build_txt_to_html_card())
        adv_layout.addWidget(self._build_excel_to_txt_card())
        self._advanced_widget.setVisible(False)
        layout.addWidget(self._advanced_widget)

        layout.addStretch(1)
        scroll.setWidget(container)
        outer.addWidget(scroll)

    def _toggle_advanced(self):
        self._advanced_widget.setVisible(not self._advanced_widget.isVisible())

    # --- 步骤卡片 ---
    def _step_card(self, step_no: int, title_zh: str, title_en: str, hint_zh: str, hint_en: str) -> tuple:
        card = CardWidget(self)
        v = QVBoxLayout(card)
        v.setContentsMargins(16, 12, 16, 16)
        v.setSpacing(10)

        head = StrongBodyLabel(
            Localizer.localize(f"第 {step_no} 步：{title_zh}", f"Step {step_no}: {title_en}"), self
        )
        v.addWidget(head)
        hint = CaptionLabel(Localizer.localize(hint_zh, hint_en), self)
        hint.setWordWrap(True)
        set_text_role(hint)
        v.addWidget(hint)
        return card, v

    def _path_row(self, label_zh: str, label_en: str, placeholder_zh: str, placeholder_en: str, browse_slot) -> tuple:
        row = QHBoxLayout()
        row.addWidget(QLabel(Localizer.localize(label_zh, label_en), self))
        edit = LineEdit(self)
        edit.setPlaceholderText(Localizer.localize(placeholder_zh, placeholder_en))
        row.addWidget(edit, 1)
        btn = PushButton(Localizer.get().browse, self, icon=FluentIcon.FOLDER)
        btn.clicked.connect(browse_slot)
        row.addWidget(btn)
        return row, edit

    def _build_step1_card(self) -> CardWidget:
        card, v = self._step_card(
            1,
            "提取待翻译文本",
            "Extract pending text",
            "选择一键翻译抽取后的 game/tl/<语言> 目录（例如 game/tl/chinese）。"
            "只会提取官方抽取产生、还没翻译的条目，补充抽取的内容不参与。",
            "Pick the game/tl/<language> folder produced by extraction (e.g. game/tl/chinese). "
            "Only untranslated official entries are exported; supplemental entries are skipped.",
        )

        row, self.step1_tl_edit = self._path_row(
            "TL 目录:", "TL Folder:",
            "例如 D:/Games/MyGame/game/tl/chinese",
            "e.g. D:/Games/MyGame/game/tl/chinese",
            self._browse_step1_tl,
        )
        v.addLayout(row)

        row2, self.step1_txt_edit = self._path_row(
            "输出 TXT:", "Output TXT:",
            "默认 <TL目录>/pending_translate.txt，可留空",
            "Default <TL folder>/pending_translate.txt, leave blank to auto-fill",
            self._browse_step1_txt,
        )
        v.addLayout(row2)

        self.step1_btn = PrimaryPushButton(
            Localizer.localize("① 提取成 TXT", "① Extract to TXT"), self, icon=FluentIcon.UP
        )
        self.step1_btn.clicked.connect(self._run_step1)
        v.addWidget(self.step1_btn)
        return card

    def _build_step2_card(self) -> CardWidget:
        card, v = self._step_card(
            2,
            "拿去翻译",
            "Translate the TXT",
            "把上一步生成的 TXT 整段粘贴给 AI，或上传到 Google 网页翻译。"
            "要求：每行一条译文，顺序与原文一致，行数不能少。翻完保存成新的 TXT。",
            "Paste the TXT from step 1 to an AI, or upload it to Google web translation. "
            "Keep one translation per line, in the same order, with no fewer lines. "
            "Save the result as a new TXT.",
        )
        hint2 = CaptionLabel(
            Localizer.localize(
                "提示：这一步在本工具之外完成，工具不调用任何翻译 API。",
                "Note: this step happens outside this tool; no translation API is called here.",
            ),
            self,
        )
        hint2.setWordWrap(True)
        set_text_role(hint2)
        v.addWidget(hint2)
        return card

    def _build_step3_card(self) -> CardWidget:
        card, v = self._step_card(
            3,
            "回填生成翻译完成的 TL",
            "Write back to a finished TL",
            "选第 1 步生成的行号清单（.manifest.json）和第 2 步翻好的译文 TXT，"
            "回填到新的 TL 目录，不会覆盖原目录。",
            "Pick the manifest (.manifest.json) from step 1 and the translated TXT from step 2. "
            "The result is written to a new TL folder; the original is left untouched.",
        )

        row, self.step3_manifest_edit = self._path_row(
            "行号清单:", "Manifest:",
            "第 1 步生成的 pending_translate.manifest.json",
            "The pending_translate.manifest.json from step 1",
            self._browse_step3_manifest,
        )
        v.addLayout(row)

        row2, self.step3_translated_edit = self._path_row(
            "译文 TXT:", "Translated TXT:",
            "第 2 步翻好的 TXT，每行一条译文",
            "The translated TXT from step 2, one per line",
            self._browse_step3_translated,
        )
        v.addLayout(row2)

        row3, self.step3_output_edit = self._path_row(
            "输出 TL 目录:", "Output TL Folder:",
            "默认在原 TL 同级生成 <语言>_translated，可留空",
            "Default: a <language>_translated folder next to the original",
            self._browse_step3_output,
        )
        v.addLayout(row3)

        self.step3_btn = PrimaryPushButton(
            Localizer.localize("③ 回填生成", "③ Write back"), self, icon=FluentIcon.SAVE
        )
        self.step3_btn.clicked.connect(self._run_step3)
        v.addWidget(self.step3_btn)
        return card

    # ==================== 槽函数 ====================
    def _browse_dir(self, title_zh: str, title_en: str) -> str:
        return QFileDialog.getExistingDirectory(
            self, Localizer.localize(title_zh, title_en), ""
        )

    def _browse_save_txt(self, title_zh: str, title_en: str) -> str:
        path, _ = QFileDialog.getSaveFileName(
            self, Localizer.localize(title_zh, title_en), "",
            Localizer.localize("文本文件 (*.txt)", "Text Files (*.txt)"),
        )
        if path and not path.lower().endswith(".txt"):
            path += ".txt"
        return path

    def _browse_open_file(self, title_zh: str, title_en: str, filt_zh: str, filt_en: str) -> str:
        path, _ = QFileDialog.getOpenFileName(
            self, Localizer.localize(title_zh, title_en), "",
            Localizer.localize(filt_zh, filt_en),
        )
        return path

    def _browse_step1_tl(self):
        path = self._browse_dir("选择 TL 目录", "Select TL Folder")
        if path:
            self.step1_tl_edit.setText(path)
            if not self.step1_txt_edit.text().strip():
                self.step1_txt_edit.setText(str(Path(path) / "pending_translate.txt"))

    def _browse_step1_txt(self):
        path = self._browse_save_txt("选择输出 TXT 路径", "Select Output TXT Path")
        if path:
            self.step1_txt_edit.setText(path)

    def _browse_step3_manifest(self):
        path = self._browse_open_file(
            "选择行号清单", "Select Manifest",
            "清单文件 (*.manifest.json)", "Manifest (*.manifest.json)",
        )
        if path:
            self.step3_manifest_edit.setText(path)

    def _browse_step3_translated(self):
        path = self._browse_open_file(
            "选择译文 TXT", "Select Translated TXT",
            "文本文件 (*.txt)", "Text Files (*.txt)",
        )
        if path:
            self.step3_translated_edit.setText(path)

    def _browse_step3_output(self):
        path = self._browse_dir("选择输出 TL 目录", "Select Output TL Folder")
        if path:
            self.step3_output_edit.setText(path)

    # ==================== 工作流 ====================
    def _run_step1(self):
        tl_dir = self.step1_tl_edit.text().strip()
        if not tl_dir:
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.localize("请先选择 TL 目录", "Select a TL folder first."),
                parent=self,
            )
            return
        if not os.path.isdir(tl_dir):
            InfoBar.error(
                Localizer.get().error,
                Localizer.localize("TL 目录不存在", "The TL folder does not exist."),
                parent=self,
            )
            return

        txt_path = self.step1_txt_edit.text().strip() or str(Path(tl_dir) / "pending_translate.txt")
        try:
            from module.Extract.TlTextExporter import extract_pending_from_tl
            count, manifest = extract_pending_from_tl(tl_dir, txt_path)
            if count == 0:
                InfoBar.info(
                    Localizer.get().notice,
                    Localizer.localize(
                        "没有待翻译的条目（可能已全部翻译，或只有补充抽取内容）。",
                        "Nothing to translate (already translated, or only supplemental entries).",
                    ),
                    parent=self,
                )
                return
            # 自动把清单路径带进第 3 步，减少新手操作
            self.step3_manifest_edit.setText(str(manifest))
            InfoBar.success(
                Localizer.get().complete,
                Localizer.localize(
                    "已提取 {count} 条到 {txt_path}，请进入第 2 步翻译。",
                    "Extracted {count} entries to {txt_path}. Go to step 2 to translate.",
                ).format(count=count, txt_path=txt_path),
                parent=self,
            )
        except Exception as e:
            self.logger.error(f"提取待翻译文本失败: {e}")
            InfoBar.error(
                Localizer.get().error,
                Localizer.localize("提取失败: {e}", "Extraction failed: {e}").format(e=e),
                parent=self,
            )

    def _run_step3(self):
        manifest_path = self.step3_manifest_edit.text().strip()
        translated_path = self.step3_translated_edit.text().strip()
        if not manifest_path or not translated_path:
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.localize(
                    "请先选行号清单和译文 TXT",
                    "Select the manifest and the translated TXT first.",
                ),
                parent=self,
            )
            return
        if not os.path.isfile(manifest_path):
            InfoBar.error(
                Localizer.get().error,
                Localizer.localize("行号清单不存在", "The manifest file does not exist."),
                parent=self,
            )
            return
        if not os.path.isfile(translated_path):
            InfoBar.error(
                Localizer.get().error,
                Localizer.localize("译文 TXT 不存在", "The translated TXT does not exist."),
                parent=self,
            )
            return

        output_dir = self.step3_output_edit.text().strip()
        if not output_dir:
            # 默认在原 TL 同级生成 <语言>_translated
            # manifest 的 file 字段指向 tl/<lang>/...，从清单推原 TL 根
            try:
                import json as _json
                manifest = _json.loads(Path(manifest_path).read_text(encoding="utf-8"))
                first_file = Path(manifest[0]["file"])
                # 上溯到 tl/<lang>
                tl_lang_dir = first_file.parent
                while tl_lang_dir.parent.name.lower() != "tl" and tl_lang_dir != tl_lang_dir.parent:
                    tl_lang_dir = tl_lang_dir.parent
                output_dir = str(tl_lang_dir.parent / f"{tl_lang_dir.name}_translated")
            except Exception:
                output_dir = str(Path(manifest_path).parent / "translated_tl")

        try:
            from module.Extract.TlTextExporter import apply_translations_to_tl
            filled, out_dir = apply_translations_to_tl(manifest_path, translated_path, output_dir)
            InfoBar.success(
                Localizer.get().complete,
                Localizer.localize(
                    "已回填 {filled} 条译文，翻译完成的 TL 在：{out_dir}",
                    "Wrote back {filled} translations. Finished TL is at: {out_dir}",
                ).format(filled=filled, out_dir=out_dir),
                parent=self,
            )
        except Exception as e:
            self.logger.error(f"回填译文失败: {e}")
            InfoBar.error(
                Localizer.get().error,
                Localizer.localize("回填失败: {e}", "Write-back failed: {e}").format(e=e),
                parent=self,
            )

    def _build_html_to_txt_card(self) -> CardWidget:
        card = CardWidget(self)
        v_layout = QVBoxLayout(card)
        v_layout.setContentsMargins(16, 12, 16, 16)
        v_layout.setSpacing(10)

        title = StrongBodyLabel(Localizer.localize("HTML → TXT", "HTML → TXT"), self)
        v_layout.addWidget(title)

        # 输入
        input_row = QHBoxLayout()
        input_row.addWidget(QLabel(Localizer.localize("HTML 文件:", "HTML File:")))
        self.html_input_edit = LineEdit()
        self.html_input_edit.setPlaceholderText(
            Localizer.localize(
                "选择包含 <h6> 节点的 HTML 文件",
                "Select an HTML file containing <h6> elements",
            )
        )
        input_row.addWidget(self.html_input_edit, 1)
        btn_browse_html = PushButton(Localizer.get().browse, icon=FluentIcon.FOLDER)
        btn_browse_html.clicked.connect(self._browse_html_file)
        input_row.addWidget(btn_browse_html)
        v_layout.addLayout(input_row)

        # 输出
        output_row = QHBoxLayout()
        output_row.addWidget(QLabel(Localizer.localize("输出 TXT:", "Output TXT:")))
        self.html_output_edit = LineEdit()
        self.html_output_edit.setPlaceholderText(
            Localizer.localize(
                "默认与输入同名，可留空",
                "Leave blank to use the input file name",
            )
        )
        output_row.addWidget(self.html_output_edit, 1)
        btn_browse_txt = PushButton(Localizer.get().browse, icon=FluentIcon.FOLDER)
        btn_browse_txt.clicked.connect(self._browse_txt_output)
        output_row.addWidget(btn_browse_txt)
        v_layout.addLayout(output_row)

        self.html_pairs_check = CheckBox(
            Localizer.localize(
                "输出 原文→译文 对照（需 HTML 含 data payload）",
                "Export original→translation pairs (requires data payload in HTML)",
            )
        )
        v_layout.addWidget(self.html_pairs_check)

        convert_btn = PrimaryPushButton(
            Localizer.localize("执行导出", "Export"), icon=FluentIcon.DOWNLOAD
        )
        convert_btn.clicked.connect(self._convert_html_to_txt)
        v_layout.addWidget(convert_btn)

        return card

    def _build_excel_to_txt_card(self) -> CardWidget:
        """Excel → TXT"""
        card = CardWidget(self)
        v_layout = QVBoxLayout(card)
        v_layout.setContentsMargins(16, 12, 16, 16)
        v_layout.setSpacing(10)

        title = StrongBodyLabel(Localizer.localize("Excel → TXT", "Excel → TXT"), self)
        v_layout.addWidget(title)

        # 选择 Excel
        row1 = QHBoxLayout()
        row1.addWidget(QLabel(Localizer.localize("Excel 文件:", "Excel File:")))
        self.excel_input_edit = LineEdit()
        self.excel_input_edit.setPlaceholderText(
            Localizer.localize(
                "选择由本工具导出的 Excel（包含 原文/译文 列）",
                "Select an Excel file exported by this tool (with Original/Translation columns)",
            )
        )
        row1.addWidget(self.excel_input_edit, 1)
        btn_browse_excel = PushButton(Localizer.get().browse, icon=FluentIcon.FOLDER)
        btn_browse_excel.clicked.connect(self._browse_excel_input)
        row1.addWidget(btn_browse_excel)
        v_layout.addLayout(row1)

        # 输出 TXT
        row2 = QHBoxLayout()
        row2.addWidget(QLabel(Localizer.localize("输出 TXT:", "Output TXT:")))
        self.excel_txt_output_edit = LineEdit()
        self.excel_txt_output_edit.setPlaceholderText(
            Localizer.localize(
                "默认与 Excel 同名，可留空",
                "Leave blank to use the Excel file name",
            )
        )
        row2.addWidget(self.excel_txt_output_edit, 1)
        btn_browse_excel_txt = PushButton(Localizer.get().browse, icon=FluentIcon.FOLDER)
        btn_browse_excel_txt.clicked.connect(self._browse_excel_txt_output)
        row2.addWidget(btn_browse_excel_txt)
        v_layout.addLayout(row2)

        # 选择导出列
        row3 = QHBoxLayout()
        row3.addWidget(QLabel(Localizer.localize("导出列:", "Export Column:")))
        self.excel_column_combo = ComboBox()
        self.excel_column_combo.addItem(
            Localizer.localize("译文", "Translation"), userData="译文"
        )
        self.excel_column_combo.addItem(
            Localizer.localize("原文", "Original"), userData="原文"
        )
        row3.addWidget(self.excel_column_combo, 1)
        v_layout.addLayout(row3)

        export_btn = PrimaryPushButton(
            Localizer.localize("导出 TXT", "Export TXT"), icon=FluentIcon.SAVE
        )
        export_btn.clicked.connect(self._convert_excel_to_txt)
        v_layout.addWidget(export_btn)

        return card

    def _build_txt_to_html_card(self) -> CardWidget:
        card = CardWidget(self)
        v_layout = QVBoxLayout(card)
        v_layout.setContentsMargins(16, 12, 16, 16)
        v_layout.setSpacing(10)

        title = StrongBodyLabel(Localizer.localize("TXT → HTML", "TXT → HTML"), self)
        v_layout.addWidget(title)

        # 输入
        txt_row = QHBoxLayout()
        txt_row.addWidget(QLabel(Localizer.localize("TXT 文件:", "TXT File:")))
        self.txt_input_edit = LineEdit()
        self.txt_input_edit.setPlaceholderText(
            Localizer.localize(
                "每行一条文本，将转换为 <h6> 节点",
                "Each line becomes an <h6> element",
            )
        )
        txt_row.addWidget(self.txt_input_edit, 1)
        btn_browse_txt_in = PushButton(Localizer.get().browse, icon=FluentIcon.FOLDER)
        btn_browse_txt_in.clicked.connect(self._browse_txt_input)
        txt_row.addWidget(btn_browse_txt_in)
        v_layout.addLayout(txt_row)

        # 输出
        html_row = QHBoxLayout()
        html_row.addWidget(QLabel(Localizer.localize("输出 HTML:", "Output HTML:")))
        self.txt_output_edit = LineEdit()
        self.txt_output_edit.setPlaceholderText(
            Localizer.localize(
                "默认与输入同名，可留空",
                "Leave blank to use the input file name",
            )
        )
        html_row.addWidget(self.txt_output_edit, 1)
        btn_browse_html_out = PushButton(Localizer.get().browse, icon=FluentIcon.FOLDER)
        btn_browse_html_out.clicked.connect(self._browse_html_output)
        html_row.addWidget(btn_browse_html_out)
        v_layout.addLayout(html_row)

        self.wrap_data_check = CheckBox(
            Localizer.localize(
                "写入附加数据（保留原文/译文结构）",
                "Include additional data (preserve the original/translation structure)",
            )
        )
        v_layout.addWidget(self.wrap_data_check)

        convert_btn = PrimaryPushButton(
            Localizer.localize("生成 HTML", "Generate HTML"), icon=FluentIcon.UP
        )
        convert_btn.clicked.connect(self._convert_txt_to_html)
        v_layout.addWidget(convert_btn)

        return card

    # --- 槽函数 ---
    def _browse_html_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            Localizer.localize("选择 HTML 文件", "Select HTML File"),
            "",
            Localizer.localize(
                "HTML 文件 (*.html *.htm)", "HTML Files (*.html *.htm)"
            ),
        )
        if path:
            self.html_input_edit.setText(path)

    def _browse_txt_output(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            Localizer.localize("选择输出 TXT 路径", "Select Output TXT Path"),
            "",
            Localizer.localize("文本文件 (*.txt)", "Text Files (*.txt)"),
        )
        if path:
            if not path.lower().endswith(".txt"):
                path += ".txt"
            self.html_output_edit.setText(path)

    def _browse_txt_input(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            Localizer.localize("选择 TXT 文件", "Select TXT File"),
            "",
            Localizer.localize("文本文件 (*.txt)", "Text Files (*.txt)"),
        )
        if path:
            self.txt_input_edit.setText(path)

    def _browse_html_output(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            Localizer.localize("选择输出 HTML 路径", "Select Output HTML Path"),
            "",
            Localizer.localize(
                "HTML 文件 (*.html *.htm)", "HTML Files (*.html *.htm)"
            ),
        )
        if path:
            if not path.lower().endswith((".html", ".htm")):
                path += ".html"
            self.txt_output_edit.setText(path)

    def _browse_excel_input(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            Localizer.localize("选择 Excel 文件", "Select Excel File"),
            "",
            Localizer.localize("Excel 文件 (*.xlsx)", "Excel Files (*.xlsx)"),
        )
        if path:
            self.excel_input_edit.setText(path)

    def _browse_excel_txt_output(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            Localizer.localize("选择输出 TXT 路径", "Select Output TXT Path"),
            "",
            Localizer.localize("文本文件 (*.txt)", "Text Files (*.txt)"),
        )
        if path:
            if not path.lower().endswith(".txt"):
                path += ".txt"
            self.excel_txt_output_edit.setText(path)

    def _convert_html_to_txt(self):
        html_path = self.html_input_edit.text().strip()
        if not html_path:
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.localize("请先选择 HTML 文件", "Select an HTML file first."),
                parent=self,
            )
            return
        if not os.path.isfile(html_path):
            InfoBar.error(
                Localizer.get().error,
                Localizer.localize("HTML 文件不存在", "The HTML file does not exist."),
                parent=self,
            )
            return

        output_path = self.html_output_edit.text().strip()
        if not output_path:
            root, _ = os.path.splitext(html_path)
            output_path = root + ".txt"

        want_pairs = self.html_pairs_check.isChecked()
        try:
            if want_pairs:
                pairs = self._read_html_translation_pairs(html_path)
                if not pairs:
                    raise ValueError(
                        Localizer.localize(
                            "HTML 中未找到 data payload，无法输出对照格式。",
                            "No data payload found in HTML; cannot export pairs.",
                        )
                    )
                lines = [f"{orig}\t{cur}" for orig, cur in pairs]
            else:
                lines = self._read_html_strings(html_path)
            if not lines:
                raise ValueError(
                    Localizer.localize(
                        "未在 HTML 中找到 <h6> 节点，请确认文件格式。",
                        "No <h6> elements were found in the HTML file. Check the file format.",
                    )
                )
            with open(output_path, "w", encoding="utf-8") as writer:
                writer.write("\n".join(lines))
            InfoBar.success(
                Localizer.get().complete,
                Localizer.localize(
                    "已导出到 {output_path}", "Exported to {output_path}"
                ).format(output_path=output_path),
                parent=self,
            )
        except Exception as e:
            self.logger.error(f"HTML 导出失败: {e}")
            InfoBar.error(
                Localizer.get().error,
                Localizer.localize("导出失败: {e}", "Export failed: {e}").format(e=e),
                parent=self,
            )

    def _convert_txt_to_html(self):
        txt_path = self.txt_input_edit.text().strip()
        if not txt_path:
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.localize("请先选择 TXT 文件", "Select a TXT file first."),
                parent=self,
            )
            return
        if not os.path.isfile(txt_path):
            InfoBar.error(
                Localizer.get().error,
                Localizer.localize("TXT 文件不存在", "The TXT file does not exist."),
                parent=self,
            )
            return

        output_path = self.txt_output_edit.text().strip()
        if not output_path:
            root, _ = os.path.splitext(txt_path)
            output_path = root + ".html"

        try:
            with open(txt_path, "r", encoding="utf-8") as reader:
                lines = [line.rstrip("\n") for line in reader]
            if not lines:
                raise ValueError(
                    Localizer.localize("TXT 文件为空", "The TXT file is empty.")
                )

            html = self._build_html_content(lines, keep_data=self.wrap_data_check.isChecked())
            with open(output_path, "w", encoding="utf-8") as writer:
                writer.write(html)
            InfoBar.success(
                Localizer.get().complete,
                Localizer.localize(
                    "已生成 HTML：{output_path}", "HTML generated: {output_path}"
                ).format(output_path=output_path),
                parent=self,
            )
        except Exception as e:
            self.logger.error(f"TXT 转 HTML 失败: {e}")
            InfoBar.error(
                Localizer.get().error,
                Localizer.localize("生成失败: {e}", "Generation failed: {e}").format(e=e),
                parent=self,
            )

    def _convert_excel_to_txt(self):
        try:
            from openpyxl import load_workbook
        except Exception:
            InfoBar.error(
                Localizer.get().error,
                Localizer.localize(
                    "未安装 openpyxl，无法读取 Excel",
                    "openpyxl is not installed, so Excel files cannot be read.",
                ),
                parent=self,
            )
            return

        excel_path = self.excel_input_edit.text().strip()
        if not excel_path:
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.localize("请先选择 Excel 文件", "Select an Excel file first."),
                parent=self,
            )
            return
        if not os.path.isfile(excel_path):
            InfoBar.error(
                Localizer.get().error,
                Localizer.localize("Excel 文件不存在", "The Excel file does not exist."),
                parent=self,
            )
            return

        output_path = self.excel_txt_output_edit.text().strip()
        if not output_path:
            root, _ = os.path.splitext(excel_path)
            output_path = root + ".txt"

        target_col_name = self.excel_column_combo.currentData()

        try:
            book = load_workbook(excel_path)
            lines: list[str] = []
            for sheet_name in book.sheetnames:
                if sheet_name in ("元数据", "Metadata"):
                    continue
                sheet = book[sheet_name]
                if sheet.max_row == 0 or sheet.max_column == 0:
                    continue
                headers = [str(c.value).strip() if c.value is not None else "" for c in sheet[1]]
                # 兼容别名
                alias_map = {
                    "原文": {
                        "原文",
                        "original",
                        "原文（勿修改此列）",
                        "Source (Do Not Edit)",
                    },
                    "译文": {
                        "译文",
                        "translation",
                        "译文（勿修改此列）",
                        "Translation (Do Not Edit)",
                    },
                }
                col_index = None
                for idx, name in enumerate(headers):
                    if name.lower() in {v.lower() for v in alias_map.get(target_col_name, {target_col_name})}:
                        col_index = idx
                        break
                if col_index is None:
                    continue
                for row in sheet.iter_rows(min_row=2, values_only=True):
                    val = row[col_index] if col_index < len(row) else None
                    if val is None:
                        continue
                    text = str(val).strip()
                    if text:
                        lines.append(text)

            if not lines:
                InfoBar.warning(
                    Localizer.get().notice,
                    Localizer.localize(
                        "未在 Excel 中找到可导出的内容",
                        "No exportable content was found in the Excel file.",
                    ),
                    parent=self,
                )
                return

            with open(output_path, "w", encoding="utf-8") as writer:
                writer.write("\n".join(lines))
            InfoBar.success(
                Localizer.get().complete,
                Localizer.localize(
                    "已导出 {count} 行到 {output_path}",
                    "Exported {count} row(s) to {output_path}",
                ).format(count=len(lines), output_path=output_path),
                parent=self,
            )
        except Exception as e:
            LogManager.get().error(f"Excel → TXT 导出失败: {e}")
            InfoBar.error(
                Localizer.get().error,
                Localizer.localize("导出失败: {e}", "Export failed: {e}").format(e=e),
                parent=self,
            )

    # --- 工具函数 ---
    @staticmethod
    def _read_html_strings(path: str) -> List[str]:
        """读取 HTML 中的可见文本行。

        优先解析 <div id="data"> 中的 payload（JSON，含 line/original/target/current），
        用 original 作为行内容键，保证浏览器翻译后仍能按原文映射回原 rpy 行号。
        无 payload 时退化为读取 <h6>/<p>/<div> 可见文本。
        """
        with open(path, "r", encoding="utf-8") as reader:
            soup = BeautifulSoup(reader, "html.parser")

        # 优先：带 payload 的结构化 HTML（本工具 TXT→HTML 生成）
        payload = HtmlImportPage._read_html_payload(soup)
        if payload is not None:
            return payload

        strings = [tag.get_text() for tag in soup.find_all("h6")]
        if not strings:  # 兼容其它标签
            strings = [tag.get_text() for tag in soup.find_all(["p", "div"])]
        return [s.replace("\r", "").strip() for s in strings if s and s.strip()]

    @staticmethod
    def _read_html_payload(soup: BeautifulSoup) -> List[str] | None:
        """从 <div id="data"> 解析 payload，返回按行号排序的译文列表；无则返回 None。"""
        data_div = soup.find("div", id="data")
        if data_div is None:
            return None
        raw = (data_div.string or data_div.get_text() or "").strip()
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except (ValueError, TypeError):
            # 兼容旧版 str(list_of_dict) 写入
            try:
                import ast
                payload = ast.literal_eval(raw)
            except (ValueError, SyntaxError):
                return None
        if not isinstance(payload, list):
            return None

        # 浏览器翻译后：original 保持不变，current 被改为译文。
        # 用 original 作为行内容键回填，行号用 line 字段保证顺序。
        entries = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            line_no = item.get("line")
            current = item.get("current")
            original = item.get("original")
            # 优先 current（翻译后），其次 target，再次 original
            text = current if (current and str(current).strip()) else (
                original if (original and str(original).strip()) else ""
            )
            entries.append((line_no if isinstance(line_no, int) else 0, str(text)))
        entries.sort(key=lambda pair: pair[0])
        return [text for _line, text in entries]

    @staticmethod
    def _read_html_translation_pairs(path: str) -> List[tuple]:
        """读取 HTML 中的 (original, current) 对照，供回填 rpy 用。

        返回 [(original, current), ...]，按行号排序；无 payload 时返回空列表。
        """
        with open(path, "r", encoding="utf-8") as reader:
            soup = BeautifulSoup(reader, "html.parser")
        data_div = soup.find("div", id="data")
        if data_div is None:
            return []
        raw = (data_div.string or data_div.get_text() or "").strip()
        if not raw:
            return []
        try:
            payload = json.loads(raw)
        except (ValueError, TypeError):
            try:
                import ast
                payload = ast.literal_eval(raw)
            except (ValueError, SyntaxError):
                return []
        if not isinstance(payload, list):
            return []

        pairs = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            line_no = item.get("line")
            original = item.get("original") or ""
            current = item.get("current") or item.get("target") or original
            pairs.append((
                line_no if isinstance(line_no, int) else 0,
                str(original),
                str(current),
            ))
        pairs.sort(key=lambda triple: triple[0])
        return [(orig, cur) for _line, orig, cur in pairs]

    @staticmethod
    def _build_html_content(lines: List[str], keep_data: bool) -> str:
        soup = BeautifulSoup("<html><head><meta charset='utf-8'></head><body></body></html>", "html.parser")
        body = soup.body

        data_payload = []
        for idx, text in enumerate(lines):
            text = text or ""
            h6 = soup.new_tag("h6")
            h6.string = text
            body.append(h6)
            if keep_data:
                data_payload.append(
                    {
                        "line": idx,
                        "original": text,
                        "target": text,
                        "current": text,
                    }
                )

        if keep_data and data_payload:
            data_div = soup.new_tag("div", id="data", style="display: none;")
            # 用 JSON 写入，保证读回时可被 json.loads 解析（str(list) 不可移植）。
            data_div.string = json.dumps(data_payload, ensure_ascii=False)
            body.append(data_div)

        return str(soup)
