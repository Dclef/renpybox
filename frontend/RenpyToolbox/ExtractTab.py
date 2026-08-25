"""
文本提取 JSON 页面
完整的 JSON 工作流：提取文本 → 导出 JSON → 人工翻译 → 导入 JSON → 应用到 tl
"""

from typing import Dict, List
from pathlib import Path

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFileDialog
from qfluentwidgets import (
    BodyLabel,
    PushButton,
    PrimaryPushButton,
    LineEdit,
    ProgressBar,
    InfoBar,
    FluentIcon,
    CardWidget,
    ComboBox,
    StrongBodyLabel,
    TitleLabel,
)

from base.Base import Base
from base.LogManager import LogManager
from module.Config import Config
from module.Localizer.Localizer import Localizer
from module.Text.SkipRules import should_skip_text
from module.Renpy.json_handler import JsonExporter, JsonImporter
from module.Renpy import renpy_extract as rx
from module.Extract.RenpyExtractor import RenpyExtractor




class ExtractTab(Base, QWidget):
    """文本提取标签页（离线）"""

    def __init__(self, object_name: str, parent=None):
        Base.__init__(self)
        QWidget.__init__(self, parent)
        self.setObjectName(object_name)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        title = TitleLabel(Localizer.get().extract_json_text_extraction_json, self)
        layout.addWidget(title)

        description = BodyLabel(
            Localizer.get().extract_json_complete_json_workflow_extract_export_json_translate,
            self,
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        layout.addWidget(self._create_basic_card())
        layout.addWidget(self._create_progress_card())
        layout.addWidget(self._create_json_card())
        layout.addWidget(self._create_official_card())

        layout.addStretch()

    def _create_basic_card(self) -> CardWidget:
        card = CardWidget(self)
        layout = QVBoxLayout(card)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel(Localizer.get().extract_json_game_file))
        self.game_file_edit = LineEdit()
        self.game_file_edit.setPlaceholderText(Localizer.get().extract_json_select_game_executable_exe)
        btn_browse = PushButton(Localizer.get().browse, icon=FluentIcon.FOLDER)
        btn_browse.clicked.connect(self._browse_game_file)
        row1.addWidget(self.game_file_edit, 1)
        row1.addWidget(btn_browse)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        self.btn_preview = PushButton(Localizer.get().extract_json_preview_file_count, icon=FluentIcon.SEARCH)
        self.btn_export = PrimaryPushButton(Localizer.get().extract_json_extract_export_json, icon=FluentIcon.DOWNLOAD)
        self.btn_preview.clicked.connect(self._preview)
        self.btn_export.clicked.connect(self._export)
        row2.addWidget(self.btn_preview)
        row2.addWidget(self.btn_export)
        row2.addStretch()
        layout.addLayout(row2)

        tip = QLabel(Localizer.get().extract_json_exported_json_stores_all_rpy_text_one)
        tip.setStyleSheet("color: gray; font-size: 11px;")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        return card

    def _create_progress_card(self) -> CardWidget:
        card = CardWidget(self)
        layout = QVBoxLayout(card)

        self.progress_bar = ProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel(Localizer.get().ready)
        self.status_label.setStyleSheet("color: gray;")
        layout.addWidget(self.status_label)

        return card

    def _create_json_card(self) -> CardWidget:
        """创建 JSON 导入导出卡片"""

        card = CardWidget(self)
        layout = QVBoxLayout(card)

        title_label = StrongBodyLabel(Localizer.get().extract_json_json_import_export, self)
        layout.addWidget(title_label)

        row = QHBoxLayout()
        btn_import = PushButton(Localizer.get().extract_json_import_json_apply_tl, icon=FluentIcon.SAVE)
        btn_import.clicked.connect(self._import_from_json)
        row.addWidget(btn_import)
        row.addStretch()
        layout.addLayout(row)

        tip = QLabel(Localizer.get().extract_json_translate_exported_json_then_import_tl_folder)
        tip.setStyleSheet("color: gray; font-size: 11px;")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        return card

    def _create_official_card(self) -> CardWidget:
        card = CardWidget(self)
        layout = QVBoxLayout(card)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel(Localizer.get().extract_json_tl_language))
        self.tl_combo = ComboBox()
        self.tl_combo.addItems(["chinese", "schinese", "tchinese", "japanese", "korean", "english"])
        self.tl_combo.setCurrentText("chinese")
        row1.addWidget(self.tl_combo)
        row1.addStretch()
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        btn_clean = PushButton(Localizer.get().extract_json_clean_tl_duplicates_empty_lines)
        btn_export_tl = PushButton(Localizer.get().extract_json_export_tl_json)
        btn_clean.clicked.connect(self._clean_tl)
        btn_export_tl.clicked.connect(self._export_tl_to_json)
        row2.addWidget(btn_clean)
        row2.addWidget(btn_export_tl)
        row2.addStretch()
        layout.addLayout(row2)

        return card

    # ===== 逻辑 =====
    def _browse_game_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            Localizer.get().extract_json_select_ren_py_game_executable,
            "",
            Localizer.get().extract_json_executable_files_exe,
        )
        if path:
            self.game_file_edit.setText(path)
            if hasattr(self, "exe_edit"):
                self.exe_edit.setText(path)

    def _preview(self):
        game_file = self.game_file_edit.text().strip()
        if not game_file:
            InfoBar.warning(Localizer.get().notice, Localizer.get().extract_json_select_game_file, parent=self)
            return
        if not Path(game_file).exists():
            InfoBar.error(Localizer.get().error, Localizer.get().extract_json_game_file_does_not_exist, parent=self)
            return

        tl_name = self.tl_combo.currentText().strip()

        self._begin(Localizer.get().extract_json_counting_files_text_entries)
        logger = LogManager.get()
        try:
            extractor = RenpyExtractor()
            entries = extractor.collect_entries(game_file, tl_name, ensure_official=True, force=False)
            
            # 按文件分组统计
            file_count: Dict[str, int] = {}
            for entry in entries:
                file_name = entry.get("file", "unknown")
                file_count[file_name] = file_count.get(file_name, 0) + 1
            
            total_files = len(file_count)
            total_entries = len(entries)
            
            logger.info(f"Extract preview: {total_entries} entries in {total_files} files")
            InfoBar.info(
                Localizer.get().extract_json_preview_results,
                Localizer.get().extract_json_found_text_entries_files_tl_all_entries.format(total_files=total_files, total_entries=total_entries, tl_name=tl_name),
                parent=self
            )
        except Exception as e:
            logger.error(f"Extract preview failed: {e}")
            InfoBar.error(
                Localizer.get().error,
                Localizer.get().extract_json_failed_count_entries.format(e=e),
                parent=self,
            )
        finally:
            self._end()

    def _export(self):
        game_file = self.game_file_edit.text().strip()
        if not game_file:
            InfoBar.warning(Localizer.get().notice, Localizer.get().extract_json_select_game_file, parent=self)
            return
        if not Path(game_file).exists():
            InfoBar.error(Localizer.get().error, Localizer.get().extract_json_game_file_does_not_exist, parent=self)
            return

        save_path, _ = QFileDialog.getSaveFileName(
            self,
            Localizer.get().extract_json_export_json_file,
            str(Path(game_file).with_suffix(".json")),
            Localizer.get().extract_json_json_files_json,
        )
        if not save_path:
            return

        self._begin(Localizer.get().extract_json_extracting_text_generating_json)
        logger = LogManager.get()
        try:
            extractor = RenpyExtractor()
            tl_name = self.tl_combo.currentText().strip()
            if extractor.export_to_json(game_file, tl_name, save_path, include_metadata=True, force_extract=True):
                logger.info(f"JSON exported: {save_path}")
                InfoBar.success(
                    Localizer.get().extract_json_success,
                    Localizer.get().extract_json_json_export_completed_tl_all_entries_written.format(tl_name=tl_name),
                    parent=self,
                )
            else:
                InfoBar.warning(
                    Localizer.get().notice,
                    Localizer.get().extract_json_no_text_extracted_export_skipped,
                    parent=self,
                )
        except Exception as e:
            logger.error(f"Export failed: {e}")
            InfoBar.error(
                Localizer.get().error,
                Localizer.get().extract_json_export_failed.format(e=e),
                parent=self,
            )
        finally:
            self._end()

    def _begin(self, msg: str):
        self.progress_bar.setValue(0)
        self.status_label.setText(msg)
        self.status_label.setStyleSheet("color: #0078d4;")

    def _end(self):
        self.progress_bar.setValue(100)
        self.status_label.setText(Localizer.get().complete)
        self.status_label.setStyleSheet("color: green;")

    # UI 不再承载日志
    def _log(self, message: str):
        LogManager.get().info(message)

    def _import_from_json(self):
        """从 JSON 导入并应用翻译"""
        game_file = self.game_file_edit.text().strip()
        if not game_file:
            InfoBar.warning(Localizer.get().notice, Localizer.get().extract_json_select_game_file, parent=self)
            return

        project = Path(game_file).parent
        game_folder = project / "game"
        if not game_folder.exists():
            InfoBar.error(
                Localizer.get().error,
                Localizer.get().extract_json_game_directory_not_found_select_correct_project,
                parent=self,
            )
            return

        json_path, _ = QFileDialog.getOpenFileName(
            self,
            Localizer.get().extract_json_select_json_file,
            str(project),
            Localizer.get().extract_json_json_files_json,
        )
        if not json_path:
            return

        try:
            self._begin(Localizer.get().extract_json_importing_translations_json)

            importer = JsonImporter()
            translations = importer.import_translations(json_path)
            if not translations:
                InfoBar.warning(
                    Localizer.get().notice,
                    Localizer.get().extract_json_no_usable_translation_entries_found_json_file,
                    parent=self,
                )
                return

            target_lang = self.tl_combo.currentText().strip()

            if importer.apply_translations(translations, str(project), target_language=target_lang, backup=True):
                total_files = len(translations)
                total_entries = sum(len(items) for items in translations.values())
                LogManager.get().info(f"已从 JSON 应用翻译: {total_files} 个文件, {total_entries} 条翻译")
                InfoBar.success(
                    Localizer.get().extract_json_success,
                    Localizer.get().extract_json_applied_tl_processed_translations_files.format(target_lang=target_lang, total_files=total_files, total_entries=total_entries),
                    parent=self,
                )
            else:
                InfoBar.error(Localizer.get().error, Localizer.get().extract_json_failed_apply_translations, parent=self)

        except Exception as e:
            LogManager.get().error(f"导入失败: {e}")
            InfoBar.error(
                Localizer.get().error,
                Localizer.get().extract_json_import_failed.format(e=e),
                parent=self,
            )
        finally:
            self._end()

    # ===== 官方提取相关 =====
    def _clean_tl(self):
        try:
            game_file = self.game_file_edit.text().strip()
            if not game_file:
                InfoBar.warning(Localizer.get().notice, Localizer.get().extract_json_select_game_file, parent=self)
                return
            project = Path(game_file).parent
            tl_dir = project / "game" / "tl" / self.tl_combo.currentText()
            if not tl_dir.exists():
                InfoBar.warning(
                    Localizer.get().notice,
                    Localizer.get().extract_json_tl_folder_not_found.format(tl_dir=tl_dir),
                    parent=self,
                )
                return
            config = Config().load()
            rx.remove_repeat_extracted_from_tl(
                str(tl_dir),
                is_py2=False,
                duplicate_action=getattr(config, "renpy_duplicate_string_action", "comment"),
            )
            LogManager.get().info(f"Cleaned TL duplicates in: {tl_dir}")
            InfoBar.success(Localizer.get().complete, Localizer.get().extract_json_tl_cleanup_complete, parent=self)
        except Exception as e:
            LogManager.get().error(f"TL 清理失败: {e}")
            InfoBar.error(
                Localizer.get().error,
                Localizer.get().extract_json_tl_cleanup_failed.format(e=e),
                parent=self,
            )

    def _export_tl_to_json(self):
        try:
            game_file = self.game_file_edit.text().strip()
            if not game_file:
                InfoBar.warning(Localizer.get().notice, Localizer.get().extract_json_select_game_file, parent=self)
                return
            project = Path(game_file).parent
            tl_dir = project / "game" / "tl" / self.tl_combo.currentText()
            if not tl_dir.exists():
                InfoBar.warning(
                    Localizer.get().notice,
                    Localizer.get().extract_json_tl_folder_not_found.format(tl_dir=tl_dir),
                    parent=self,
                )
                return
            data: Dict[str, List[Dict]] = {}
            skipped = 0
            for rpy in tl_dir.rglob("*.rpy"):
                items: List[Dict] = []
                with open(rpy, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
                i = 0
                while i < len(lines):
                    line = lines[i].rstrip("\n")
                    if line.startswith("    old ") and i + 1 < len(lines) and lines[i + 1].startswith("    new "):
                        original_text = line[len("    old "):].strip().strip("\"")
                        original_text = original_text.replace("\"", "").replace("\n", "")
                        if should_skip_text(original_text):
                            skipped += 1
                            i += 2
                            continue

                        translation_text = lines[i + 1][len("    new "):].strip().strip("\"")
                        translation_text = translation_text.replace("\"", "").replace("\n", "")

                        items.append({
                            "line": i + 1,
                            "original": original_text,
                            "translation": translation_text,
                            "type": "strings",
                            "status": "pending",
                        })
                        i += 2
                    else:
                        i += 1
                data[str(rpy.relative_to(tl_dir))] = items
            save_path, _ = QFileDialog.getSaveFileName(
                self,
                Localizer.get().extract_json_select_export_path,
                str(project / f"tl_{self.tl_combo.currentText()}.json"),
                Localizer.get().extract_json_json_files_json,
            )
            if not save_path:
                return
            exporter = JsonExporter()
            if exporter.export(data, save_path, include_metadata=True):
                total_files = len(data)
                total_entries = sum(len(items) for items in data.values())
                LogManager.get().info(f"TL JSON exported: {save_path} ({total_files} files, {total_entries} entries, skipped {skipped})")
                InfoBar.success(
                    Localizer.get().extract_json_success,
                    Localizer.get().extract_json_tl_export_completed_translations_files_written_one.format(total_files=total_files, total_entries=total_entries, skipped=skipped),
                    parent=self,
                )
            else:
                InfoBar.error(Localizer.get().error, Localizer.get().extract_json_tl_export_failed, parent=self)
        except Exception as e:
            LogManager.get().error(f"TL 导出失败: {e}")
            InfoBar.error(
                Localizer.get().error,
                Localizer.get().extract_json_tl_export_failed_2.format(e=e),
                parent=self,
            )
