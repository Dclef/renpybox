"""
文本提取 JSON 页面
完整的 JSON 工作流：提取文本 → 导出 JSON → 人工翻译 → 导入 JSON → 应用到 tl
"""

from typing import Dict, List
import json
from pathlib import Path

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFileDialog
from qfluentwidgets import (
    PushButton,
    PrimaryPushButton,
    LineEdit,
    ProgressBar,
    InfoBar,
    FluentIcon,
    CardWidget,
    ComboBox,
)

from base.Base import Base
from base.LogManager import LogManager
from module.Text.SkipRules import should_skip_text
from module.Renpy.json_handler import JsonExporter, JsonImporter
from module.Renpy import renpy_extract as rx
from module.Extract.RenpyExtractor import RenpyExtractor


class ExtractTab(Base, QWidget):
    """文本提取标签页（离线）"""

    def __init__(self, parent=None):
        Base.__init__(self)
        QWidget.__init__(self, parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        title = QLabel("📝 文本提取 JSON")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(title)

        description = QLabel("💡 完整的 JSON 翻译工作流：提取 → 导出 JSON → 人工翻译 → 导入 → 应用到 tl")
        description.setStyleSheet("color: gray; font-size: 12px; margin-bottom: 10px;")
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
        row1.addWidget(QLabel("游戏文件:"))
        self.game_file_edit = LineEdit()
        self.game_file_edit.setPlaceholderText("选择游戏可执行文件 (.exe)")
        btn_browse = PushButton("浏览", icon=FluentIcon.FOLDER)
        btn_browse.clicked.connect(self._browse_game_file)
        row1.addWidget(self.game_file_edit, 1)
        row1.addWidget(btn_browse)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        self.btn_preview = PushButton("预览文件数", icon=FluentIcon.SEARCH)
        self.btn_export = PrimaryPushButton("提取并导出 JSON", icon=FluentIcon.DOWNLOAD)
        self.btn_preview.clicked.connect(self._preview)
        self.btn_export.clicked.connect(self._export)
        row2.addWidget(self.btn_preview)
        row2.addWidget(self.btn_export)
        row2.addStretch()
        layout.addLayout(row2)

        tip = QLabel("说明：导出的 JSON 会将所有 .rpy 文本写入单个文件，按文件路径分组条目")
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

        self.status_label = QLabel("等待操作…")
        self.status_label.setStyleSheet("color: gray;")
        layout.addWidget(self.status_label)

        return card

    def _create_json_card(self) -> CardWidget:
        """创建 JSON 导入导出卡片"""

        card = CardWidget(self)
        layout = QVBoxLayout(card)

        title_label = QLabel("📤 JSON 导入/导出")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title_label)

        row = QHBoxLayout()
        btn_import = PushButton("📥 从 JSON 导入并应用到 tl", icon=FluentIcon.SAVE)
        btn_import.clicked.connect(self._import_from_json)
        row.addWidget(btn_import)
        row.addStretch()
        layout.addLayout(row)

        tip = QLabel("说明：导出后在 JSON 中完成翻译，然后导入并应用到 tl 目录。结构为 {\"translations\": {file: [...]}}。")
        tip.setStyleSheet("color: gray; font-size: 11px;")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        return card

    def _create_official_card(self) -> CardWidget:
        card = CardWidget(self)
        layout = QVBoxLayout(card)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("tl 语言:"))
        self.tl_combo = ComboBox()
        self.tl_combo.addItems(["chinese", "schinese", "tchinese", "japanese", "korean", "english"])
        self.tl_combo.setCurrentText("chinese")
        row1.addWidget(self.tl_combo)
        row1.addStretch()
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        btn_clean = PushButton("清理 tl 重复与空行")
        btn_export_tl = PushButton("提取 tl→JSON")
        btn_clean.clicked.connect(self._clean_tl)
        btn_export_tl.clicked.connect(self._export_tl_to_json)
        row2.addWidget(btn_clean)
        row2.addWidget(btn_export_tl)
        row2.addStretch()
        layout.addLayout(row2)

        return card

    # ===== 逻辑 =====
    def _browse_game_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 Ren'Py 游戏可执行文件", "", "可执行文件 (*.exe)")
        if path:
            self.game_file_edit.setText(path)
            if hasattr(self, "exe_edit"):
                self.exe_edit.setText(path)

    def _preview(self):
        game_file = self.game_file_edit.text().strip()
        if not game_file:
            InfoBar.warning("提示", "请选择游戏文件", parent=self)
            return
        if not Path(game_file).exists():
            InfoBar.error("错误", "游戏文件不存在", parent=self)
            return

        tl_name = self.tl_combo.currentText().strip()

        self._begin("正在统计文件和文本数量…")
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
                "预览结果", 
                f"发现 {total_files} 个文件，共 {total_entries} 条文本 (tl/{tl_name})\n所有条目将写入单个 JSON，使用文件名作为键区分来源", 
                parent=self
            )
        except Exception as e:
            logger.error(f"Extract preview failed: {e}")
            InfoBar.error("错误", f"统计失败: {e}", parent=self)
        finally:
            self._end()

    def _export(self):
        game_file = self.game_file_edit.text().strip()
        if not game_file:
            InfoBar.warning("提示", "请选择游戏文件", parent=self)
            return
        if not Path(game_file).exists():
            InfoBar.error("错误", "游戏文件不存在", parent=self)
            return

        save_path, _ = QFileDialog.getSaveFileName(
            self, "导出 JSON 文件", str(Path(game_file).with_suffix(".json")), "JSON 文件 (*.json)"
        )
        if not save_path:
            return

        self._begin("正在提取文本并生成 JSON…")
        logger = LogManager.get()
        try:
            extractor = RenpyExtractor()
            tl_name = self.tl_combo.currentText().strip()
            if extractor.export_to_json(game_file, tl_name, save_path, include_metadata=True, force_extract=True):
                logger.info(f"JSON exported: {save_path}")
                InfoBar.success("成功", f"JSON 导出成功 (tl/{tl_name})\n所有条目写入同一个文件，按文件名分组", parent=self)
            else:
                InfoBar.warning("提示", "未提取到任何文本或导出被跳过", parent=self)
        except Exception as e:
            logger.error(f"Export failed: {e}")
            InfoBar.error("错误", f"导出失败: {e}", parent=self)
        finally:
            self._end()

    def _begin(self, msg: str):
        self.progress_bar.setValue(0)
        self.status_label.setText(msg)
        self.status_label.setStyleSheet("color: #0078d4;")

    def _end(self):
        self.progress_bar.setValue(100)
        self.status_label.setText("完成")
        self.status_label.setStyleSheet("color: green;")

    # UI 不再承载日志
    def _log(self, message: str):
        LogManager.get().info(message)

    def _import_from_json(self):
        """从 JSON 导入并应用翻译"""
        game_file = self.game_file_edit.text().strip()
        if not game_file:
            InfoBar.warning("提示", "请选择游戏文件", parent=self)
            return

        project = Path(game_file).parent
        game_folder = project / "game"
        if not game_folder.exists():
            InfoBar.error("错误", "未找到 game/ 目录，请选择正确的项目", parent=self)
            return

        json_path, _ = QFileDialog.getOpenFileName(
            self, "选择 JSON 文件", str(project), "JSON 文件 (*.json)"
        )
        if not json_path:
            return

        try:
            self._begin("正在从 JSON 导入并应用翻译…")

            importer = JsonImporter()
            translations = importer.import_translations(json_path)
            if not translations:
                InfoBar.warning("提示", "JSON 中未找到可用的翻译条目", parent=self)
                return

            target_lang = self.tl_combo.currentText().strip()

            if importer.apply_translations(translations, str(project), target_language=target_lang, backup=True):
                total_files = len(translations)
                total_entries = sum(len(items) for items in translations.values())
                LogManager.get().info(f"已从 JSON 应用翻译: {total_files} 个文件, {total_entries} 条翻译")
                InfoBar.success("成功", f"已应用到 tl/{target_lang}\n处理了 {total_files} 个文件，{total_entries} 条翻译", parent=self)
            else:
                InfoBar.error("错误", "应用翻译失败", parent=self)

        except Exception as e:
            LogManager.get().error(f"导入失败: {e}")
            InfoBar.error("错误", f"导入失败: {e}", parent=self)
        finally:
            self._end()

    # ===== 官方提取相关 =====
    def _clean_tl(self):
        try:
            game_file = self.game_file_edit.text().strip()
            if not game_file:
                InfoBar.warning("提示", "请选择游戏文件", parent=self)
                return
            project = Path(game_file).parent
            tl_dir = project / "game" / "tl" / self.tl_combo.currentText()
            if not tl_dir.exists():
                InfoBar.warning("提示", f"未找到 tl 目录: {tl_dir}", parent=self)
                return
            rx.remove_repeat_extracted_from_tl(str(tl_dir), is_py2=False)
            LogManager.get().info(f"Cleaned TL duplicates in: {tl_dir}")
            InfoBar.success("完成", "tl 清理完成", parent=self)
        except Exception as e:
            LogManager.get().error(f"TL 清理失败: {e}")
            InfoBar.error("错误", f"TL 清理失败: {e}", parent=self)

    def _export_tl_to_json(self):
        try:
            game_file = self.game_file_edit.text().strip()
            if not game_file:
                InfoBar.warning("提示", "请选择游戏文件", parent=self)
                return
            project = Path(game_file).parent
            tl_dir = project / "game" / "tl" / self.tl_combo.currentText()
            if not tl_dir.exists():
                InfoBar.warning("提示", f"未找到 tl 目录: {tl_dir}", parent=self)
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
                self, "选择导出路径", str(project / f"tl_{self.tl_combo.currentText()}.json"), "JSON 文件 (*.json)"
            )
            if not save_path:
                return
            exporter = JsonExporter()
            if exporter.export(data, save_path, include_metadata=True):
                total_files = len(data)
                total_entries = sum(len(items) for items in data.values())
                LogManager.get().info(f"TL JSON exported: {save_path} ({total_files} files, {total_entries} entries, skipped {skipped})")
                InfoBar.success("成功", f"TL 导出成功\n{total_files} 个文件，{total_entries} 条翻译，均写入同一个 JSON\n跳过 {skipped} 条资源/占位符", parent=self)
            else:
                InfoBar.error("错误", "TL 导出失败", parent=self)
        except Exception as e:
            LogManager.get().error(f"TL 导出失败: {e}")
            InfoBar.error("错误", f"TL 导出失败: {e}", parent=self)
