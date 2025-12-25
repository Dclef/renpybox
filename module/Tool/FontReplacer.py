"""
Ren'Py 字体替换工具
替换游戏中的字体引用，生成翻译语言的 GUI 字体
"""

import io
import json
import os
import re
import shutil
import sys
import time
from typing import List, Tuple, Optional, Dict
from pathlib import Path

from base.LogManager import LogManager


class FontReplacer:
    """字体替换器"""

    FONT_SUFFIXES = (".ttf", ".otf", ".ttc", ".otc")
    BACKUP_DIR_NAME = "fonts_backup"
    MAX_BACKUPS = 3  # 保留的最大备份数量

    def __init__(self):
        self.logger = LogManager.get()
        # 模板文件路径
        self.template_path = self._get_template_path()

    def _get_template_path(self) -> str:
        """获取字体样式模板路径"""
        # 尝试多个可能的位置
        candidates = [
            os.path.join(os.path.dirname(__file__), "..", "..", "resource", "templates", "font_style_template.txt"),
            os.path.join(os.path.dirname(__file__), "..", "..", "dist", "font_style_template.txt"),
            os.path.join(os.getcwd(), "resource", "templates", "font_style_template.txt"),
            "font_style_template.txt",
        ]
        for path in candidates:
            if os.path.isfile(path):
                return os.path.abspath(path)
        return candidates[0]  # 默认返回第一个

    def _resolve_game_dir(self, game_dir: str) -> Path:
        """解析并返回实际的 game 目录路径（允许传入项目根目录或直接传入 game 目录）。

        如果传入的是项目根目录（包含 game 子目录），函数会返回 project_root/game。
        如果传入的路径本身就是 game 目录，会直接返回该路径。
        否则，按原样返回 Path(game_dir)。
        """
        try:
            p = Path(game_dir)
            if p.is_file():
                p = p.parent

            # 如果已经是 game 目录
            if p.name.lower() == "game" and p.is_dir():
                return p

            # 如果有 game 子目录
            candidate = p / "game"
            if candidate.exists() and candidate.is_dir():
                return candidate

            # 在父路径中寻找 game 目录
            for parent in p.parents:
                cand = parent / "game"
                if cand.exists() and cand.is_dir():
                    return cand

            # 未找到，返回传入路径（可能是 game 目录的别名）
            return p
        except Exception:
            return Path(game_dir)

    # ========== 备份与恢复功能 ==========

    def create_backup(self, game_dir: str, source_font: str = None) -> Tuple[bool, str, str]:
        """
        创建字体备份
        
        Args:
            game_dir: game 目录路径
            source_font: 替换源字体名（用于备份清单）
            
        Returns:
            (是否成功, 消息, 备份目录名)
        """
        try:
            game_path = self._resolve_game_dir(game_dir)
            backup_root = game_path / self.BACKUP_DIR_NAME
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            backup_dir = backup_root / f"backup_{timestamp}"
            
            # 创建备份目录
            backup_dir.mkdir(parents=True, exist_ok=True)
            
            # 发现所有字体文件
            font_files = self.discover_font_files(game_path)
            if not font_files:
                self.logger.warning("未发现字体文件，跳过备份")
                return True, "未发现字体文件", ""
            
            # 备份字体文件
            backed_up_files = []
            for rel_path, abs_path in font_files:
                try:
                    dest = backup_dir / "original" / rel_path
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(abs_path, dest)
                    backed_up_files.append({
                        "rel_path": rel_path,
                        "original_path": abs_path,
                        "backup_path": str(dest),
                        "size": os.path.getsize(abs_path),
                    })
                except Exception as e:
                    self.logger.warning(f"备份文件失败 {rel_path}: {e}")
            
            # 生成备份清单
            manifest = {
                "timestamp": timestamp,
                "source_font": source_font,
                "game_dir": str(game_path),
                "files": backed_up_files,
                "status": "success",
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            
            manifest_path = backup_dir / "fonts_manifest.json"
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"字体备份完成: {backup_dir} ({len(backed_up_files)} 个文件)")
            
            # 清理旧备份
            self._cleanup_old_backups(backup_root)
            
            return True, f"备份完成，共 {len(backed_up_files)} 个文件", f"backup_{timestamp}"
            
        except Exception as e:
            self.logger.error(f"创建字体备份失败: {e}")
            return False, str(e), ""

    def list_backups(self, game_dir: str) -> List[Dict]:
        """
        列出所有可用备份
        
        Args:
            game_dir: game 目录路径
            
        Returns:
            备份信息列表 [{timestamp, file_count, created_at}, ...]
        """
        backups = []
        try:
            game_path = self._resolve_game_dir(game_dir)
            backup_root = game_path / self.BACKUP_DIR_NAME
            if not backup_root.exists():
                return backups
            
            for backup_dir in sorted(backup_root.iterdir(), reverse=True):
                if not backup_dir.is_dir() or not backup_dir.name.startswith("backup_"):
                    continue
                
                manifest_path = backup_dir / "fonts_manifest.json"
                if manifest_path.exists():
                    try:
                        with open(manifest_path, "r", encoding="utf-8") as f:
                            manifest = json.load(f)
                        backups.append({
                            "name": backup_dir.name,
                            "timestamp": manifest.get("timestamp", ""),
                            "file_count": len(manifest.get("files", [])),
                            "created_at": manifest.get("created_at", ""),
                            "source_font": manifest.get("source_font", ""),
                        })
                    except Exception:
                        backups.append({
                            "name": backup_dir.name,
                            "timestamp": backup_dir.name.replace("backup_", ""),
                            "file_count": 0,
                            "created_at": "",
                            "source_font": "",
                        })
        except Exception as e:
            self.logger.error(f"列出备份失败: {e}")
        
        return backups

    def restore_backup(self, game_dir: str, backup_name: str) -> Tuple[bool, str]:
        """
        从备份恢复字体
        
        Args:
            game_dir: game 目录路径
            backup_name: 备份目录名 (如 "backup_20251210_100000")
            
        Returns:
            (是否成功, 消息)
        """
        try:
            game_path = self._resolve_game_dir(game_dir)
            backup_dir = game_path / self.BACKUP_DIR_NAME / backup_name
            
            if not backup_dir.exists():
                return False, f"备份目录不存在: {backup_name}"
            
            manifest_path = backup_dir / "fonts_manifest.json"
            if not manifest_path.exists():
                return False, "备份清单不存在"
            
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            
            files = manifest.get("files", [])
            restored_count = 0
            
            for file_info in files:
                rel_path = file_info.get("rel_path")
                backup_path = backup_dir / "original" / rel_path
                target_path = game_path / rel_path
                
                if not backup_path.exists():
                    self.logger.warning(f"备份文件不存在: {backup_path}")
                    continue
                
                try:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(backup_path, target_path)
                    restored_count += 1
                except Exception as e:
                    self.logger.warning(f"恢复文件失败 {rel_path}: {e}")
            
            self.logger.info(f"字体恢复完成: {restored_count}/{len(files)} 个文件")
            return True, f"恢复完成，共 {restored_count} 个文件"
            
        except Exception as e:
            self.logger.error(f"恢复备份失败: {e}")
            return False, str(e)

    def _cleanup_old_backups(self, backup_root: Path) -> None:
        """清理过期备份，只保留最近 MAX_BACKUPS 个"""
        try:
            if not backup_root.exists():
                return
            
            backup_dirs = sorted(
                [d for d in backup_root.iterdir() if d.is_dir() and d.name.startswith("backup_")],
                key=lambda x: x.name,
                reverse=True
            )
            
            # 删除超出数量的备份
            for old_backup in backup_dirs[self.MAX_BACKUPS:]:
                try:
                    shutil.rmtree(old_backup)
                    self.logger.info(f"清理旧备份: {old_backup.name}")
                except Exception as e:
                    self.logger.warning(f"清理旧备份失败 {old_backup}: {e}")
        except Exception as e:
            self.logger.warning(f"清理旧备份失败: {e}")

    def safe_replace_font(
        self,
        game_dir: str,
        source_font_path: str,
        original_fonts: List[str] = None,
        create_backup: bool = True,
    ) -> Tuple[bool, str, Dict]:
        """
        安全地替换字体（带备份功能）
        
        Args:
            game_dir: game 目录路径
            source_font_path: 新字体文件路径
            original_fonts: 要替换的原字体名列表（如果为空则替换所有）
            create_backup: 是否创建备份
            
        Returns:
            (是否成功, 消息, 详情 {backup_name, replaced_count, ...})
        """
        details = {
            "backup_name": "",
            "replaced_files": 0,
            "replaced_count": 0,
        }
        
        try:
            # 1. 创建备份（解析 game 目录）
            game_path = self._resolve_game_dir(game_dir)
            if create_backup:
                success, msg, backup_name = self.create_backup(str(game_path), source_font_path)
                if not success:
                    return False, f"备份失败: {msg}", details
                details["backup_name"] = backup_name
            
            # 2. 复制新字体到 game/fonts
            font_name = Path(source_font_path).name
            dest_path = self.ensure_font_in_game(str(game_path), source_font_path, font_name)
            if not dest_path:
                # 备份恢复
                if create_backup and details["backup_name"]:
                    self.restore_backup(game_dir, details["backup_name"])
                return False, "复制字体文件失败", details
            
            new_font_ref = f"fonts/{font_name}"
            
            # 3. 替换字体引用
            if original_fonts:
                fonts_to_replace = original_fonts
            else:
                fonts_to_replace = self.scan_fonts(str(game_path))
            
            total_files = 0
            total_replacements = 0
            
            for old_font in fonts_to_replace:
                f_count, r_count = self.replace_in_folder(
                    str(game_path), old_font, new_font_ref, encoding="utf-8"
                )
                total_files += f_count
                total_replacements += r_count
            
            details["replaced_files"] = total_files
            details["replaced_count"] = total_replacements
            
            self.logger.info(
                f"字体替换完成: {total_files} 个文件, {total_replacements} 处替换"
            )
            
            return True, f"替换完成，共 {total_replacements} 处", details
            
        except Exception as e:
            self.logger.error(f"安全替换字体失败: {e}")
            # 尝试恢复
            if create_backup and details.get("backup_name"):
                self.restore_backup(game_dir, details["backup_name"])
            return False, str(e), details

    def replace_in_file(
        self,
        file_path: str,
        original_font: str,
        target_font: str,
        encoding: str = "utf-8"
    ) -> Tuple[bool, int]:
        """
        在单个文件中替换字体

        Args:
            file_path: 文件路径
            original_font: 原字体名
            target_font: 目标字体名
            encoding: 文件编码

        Returns:
            (是否成功, 替换次数)
        """
        try:
            with open(file_path, "r", encoding=encoding, errors="ignore") as f:
                content = f.read()

            # 替换字体引用
            # 支持格式: font="xxx.ttf", FontGroup("xxx"), style font_name "xxx"
            patterns = [
                (r'font\s*=\s*["\']' + re.escape(original_font) + r'["\']',
                 f'font="{target_font}"'),
                (r'FontGroup\s*\(\s*["\']' + re.escape(original_font) + r'["\']',
                 f'FontGroup("{target_font}"'),
                (r'style\s+\w+\s+font_name\s+["\']' + re.escape(original_font) + r'["\']',
                 f'style font_name "{target_font}"'),
            ]

            new_content = content
            total_replacements = 0

            for pattern, replacement in patterns:
                new_content, count = re.subn(pattern, replacement, new_content)
                total_replacements += count

            if total_replacements > 0:
                with open(file_path, "w", encoding=encoding) as f:
                    f.write(new_content)
                self.logger.info(f"替换字体: {file_path} ({total_replacements} 处)")

            return True, total_replacements

        except Exception as e:
            self.logger.error(f"替换字体失败 {file_path}: {e}")
            return False, 0

    def replace_in_folder(
        self,
        folder_path: str,
        original_font: str,
        target_font: str,
        encoding: str = "utf-8",
        file_extensions: List[str] = None
    ) -> Tuple[int, int]:
        """
        批量替换文件夹中的字体

        Args:
            folder_path: 文件夹路径
            original_font: 原字体名
            target_font: 目标字体名
            encoding: 文件编码
            file_extensions: 文件扩展名列表 (默认 [".rpy", ".rpym"])

        Returns:
            (成功文件数, 总替换次数)
        """
        if file_extensions is None:
            file_extensions = [".rpy", ".rpym"]

        success_count = 0
        total_replacements = 0

        base_dir = Path(self._resolve_game_dir(folder_path))
        for ext in file_extensions:
            files = list(base_dir.rglob(f"*{ext}"))
            self.logger.info(f"找到 {len(files)} 个 {ext} 文件")

            for file_path in files:
                success, count = self.replace_in_file(
                    str(file_path),
                    original_font,
                    target_font,
                    encoding
                )
                if success and count > 0:
                    success_count += 1
                    total_replacements += count

        self.logger.info(f"字体替换完成: {success_count} 个文件, {total_replacements} 处替换")
        return success_count, total_replacements

    def scan_fonts(self, folder_path: str) -> List[str]:
        """
        扫描文件夹中使用的所有字体

        Args:
            folder_path: 文件夹路径

        Returns:
            字体名称列表
        """
        fonts = set()
        rpy_files = list(Path(self._resolve_game_dir(folder_path)).rglob("*.rpy"))

        for file_path in rpy_files:
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                # 常见字体引用模式
                patterns = [
                    r'font\s*=\s*["\']([^"\']+)["\']',
                    r'FontGroup\s*\(\s*["\']([^"\']+)["\']',
                    r'style\s+\w+\s+font\s*=\s*["\']([^"\']+)["\']',
                    r'style\.[^\s]+\s*\[\s*["\']font["\']\s*\]\s*=\s*["\']([^"\']+)["\']',
                ]

                for pattern in patterns:
                    matches = re.findall(pattern, content)
                    fonts.update(matches)

            except Exception:
                continue

        return sorted(fonts)

    def discover_font_files(self, folder_path: str) -> List[Tuple[str, str]]:
        """枚举 game 目录中的字体文件，返回 (相对路径, 绝对路径) 列表"""
        results: List[Tuple[str, str]] = []
        base_path = Path(self._resolve_game_dir(folder_path))
        if not base_path.exists():
            return results

        seen = set()
        candidate_dirs = [base_path / "fonts", base_path / "gui", base_path]

        for directory in candidate_dirs:
            if not directory.exists():
                continue
            try:
                for suffix in self.FONT_SUFFIXES:
                    for file_path in directory.rglob(f"*{suffix}"):
                        if not file_path.is_file():
                            continue
                        rel_path = file_path.relative_to(base_path)
                        rel_key = str(rel_path).replace("\\", "/")
                        if rel_key in seen:
                            continue
                        seen.add(rel_key)
                        results.append((rel_key, str(file_path)))
            except Exception:
                continue

        results.sort(key=lambda item: item[0].lower())
        return results

    def get_translation_languages(self, game_dir: str) -> List[str]:
        """
        获取所有翻译语言列表
        
        Args:
            game_dir: game 目录路径
            
        Returns:
            语言代码列表 (如 ['schinese', 'english'])
        """
        languages = []
        tl_dir = Path(self._resolve_game_dir(game_dir)) / "tl"
        if tl_dir.exists():
            for item in tl_dir.iterdir():
                if item.is_dir() and not item.name.startswith('.'):
                    languages.append(item.name)
        return sorted(languages)

    def get_builtin_font_path(self) -> Optional[str]:
        """返回内置字体 SourceHanSansLite.ttf 的路径（若存在）"""
        try:
            project_root = Path(__file__).resolve().parents[3]
        except IndexError:
            project_root = Path(__file__).resolve().parent

        candidates = [
            project_root / "resource" / "SourceHanSansLite.ttf",
            Path(getattr(sys, "_MEIPASS", "")) / "resource" / "SourceHanSansLite.ttf"
            if getattr(sys, "_MEIPASS", None) else None,
            Path(os.getcwd()) / "resource" / "SourceHanSansLite.ttf",
        ]

        for path in candidates:
            if path and path.is_file():
                return str(path)

        return None

    def ensure_font_in_game(
        self,
        game_dir: str,
        source_path: Optional[str],
        dest_filename: Optional[str] = None,
    ) -> Optional[str]:
        """确保字体文件复制到 game/fonts 目录，返回目标路径"""
        if not source_path:
            return None

        try:
            game_path = self._resolve_game_dir(game_dir)
            fonts_dir = Path(game_path) / "fonts"
            fonts_dir.mkdir(parents=True, exist_ok=True)

            source = Path(source_path)
            if not source.is_file():
                self.logger.warning(f"字体源文件不存在: {source_path}")
                return None

            dest_name = dest_filename or source.name
            dest = fonts_dir / dest_name

            # 如果源文件已在目标位置则无需复制
            if source.resolve() == dest.resolve() and dest.exists():
                self.logger.info(f"字体文件已在目标目录: {dest}")
                return str(dest)

            shutil.copy(source, dest)
            self.logger.info(f"复制字体文件: {source} -> {dest}")
            return str(dest)

        except Exception as e:
            self.logger.error(f"复制字体文件失败: {e}")
            return None

    # ========== 预置字体包部署 ==========

    def deploy_builtin_font_pack(self, game_dir: str, tl_name: str = "base_box") -> tuple[bool, str]:
        """
        将仓库内置的字体与 GUI 方案复制到目标 game 目录下的 tl/{tl_name}/base_box，
        并将字体复制到 tl/{tl_name}/fonts。

        Args:
            game_dir: 项目根目录或 game 目录
            tl_name: 目标翻译目录名（默认 base_box）
        """
        try:
            game_path = self._resolve_game_dir(game_dir)

            # 定位内置资源，优先 resource，再回退 dist
            def _find_root(start: Path) -> Path | None:
                for parent in [start] + list(start.parents):
                    if (parent / "resource").exists():
                        return parent
                return None

            root = _find_root(Path(__file__).resolve())
            if root is None:
                return False, "未找到 resource 目录，无法部署内置字体包"

            base_src_candidates = [
                root / "resource" / "base_box",
                root / "dist" / "base_box",
                root / "dist" / "base_ma",
            ]
            fonts_src_candidates = [
                root / "resource" / "fonts",
                root / "dist" / "fonts",
            ]

            base_src = next((p for p in base_src_candidates if p.exists()), None)
            fonts_src = next((p for p in fonts_src_candidates if p.exists()), None)
            if base_src is None or fonts_src is None:
                missing = "base_box/base_ma" if base_src is None else "fonts"
                return False, f"资源缺失: {missing}"

            # 目标目录
            tl_dir = game_path / "tl" / tl_name
            dest_base_dir = tl_dir / "base_box"
            dest_fonts_dir = tl_dir / "fonts"
            dest_base_dir.mkdir(parents=True, exist_ok=True)
            dest_fonts_dir.mkdir(parents=True, exist_ok=True)

            # 复制内置 base 包内容并替换语言标识/路径
            for src_file in base_src.glob("*.rpy"):
                content = src_file.read_text(encoding="utf-8")
                # 支持旧模板（schinese 占位）和新版 {tl_name} 占位
                content = content.replace("translate schinese", f"translate {tl_name}")
                content = content.replace("tl/schinese", f"tl/{tl_name}")

                default_font_path = f"tl/{tl_name}/fonts/SourceHanSansCN-Bold.ttf"
                content = content.replace("{tl_name}", tl_name)
                content = content.replace("{font_path}", default_font_path)
                content = content.replace("{is_rtl_enabled}", "False")
                (dest_base_dir / src_file.name).write_text(content, encoding="utf-8")

            # 复制字体到 tl/{tl_name}/fonts
            copied = 0
            for font_file in fonts_src.iterdir():
                if font_file.suffix.lower() in __class__.FONT_SUFFIXES and font_file.is_file():
                    shutil.copy(font_file, dest_fonts_dir / font_file.name)
                    copied += 1

            return True, f"字体包部署完成: base_box({dest_base_dir}), fonts({copied} 个)"
        except Exception as e:
            self.logger.error(f"部署内置字体包失败: {e}")
            return False, str(e)

    # ========== GUI 字体生成 ==========
    
    def gen_gui_fonts(
        self,
        game_path: str,
        tl_name: str,
        font_path: str,
        is_rtl: bool = False
    ) -> bool:
        """
        为翻译语言生成 GUI 字体文件
        
        通过 Hook 方式替换字体，无需修改原始文件
        
        Args:
            game_path: game 目录路径
            tl_name: 翻译语言名 (如 "schinese", "tchinese")
            font_path: 字体文件路径
            is_rtl: 是否启用 RTL (从右到左) 布局
            
        Returns:
            是否成功
        """
        try:
            # 解析传入路径，支持项目根或 game 目录
            game_path_resolved = str(self._resolve_game_dir(game_path))
            # 目标 gui.rpy 路径
            tl_dir = os.path.join(game_path_resolved, 'tl', tl_name)
            gui_path = os.path.join(tl_dir, 'gui.rpy')
            
            # 确保 tl 目录存在
            os.makedirs(tl_dir, exist_ok=True)
            
            python_begin_line = f'translate {tl_name} python:'
            
            # 检查是否已存在 gui.rpy
            append_mode = False
            if os.path.isfile(gui_path):
                with io.open(gui_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                if python_begin_line in content:
                    append_mode = True
            
            result = False
            if append_mode:
                # 更新现有文件中的字体配置
                result = self._update_gui_font(gui_path, tl_name, font_path, is_rtl)
            else:
                # 创建新的 gui.rpy
                result = self._create_gui_font(game_path_resolved, tl_name, font_path, is_rtl, gui_path)
            
            # 同时替换该语言目录下的 {font} 标签
            if result:
                font_filename = os.path.basename(font_path)
                self.replace_font_in_translation(tl_dir, font_filename)
                
            return result
                
        except Exception as e:
            self.logger.error(f"生成 GUI 字体失败: {e}")
            return False
    
    def _update_gui_font(
        self, 
        gui_path: str, 
        tl_name: str, 
        font_path: str, 
        is_rtl: bool
    ) -> bool:
        """更新现有 gui.rpy 中的字体配置"""
        try:
            with io.open(gui_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            updated = False
            font_filename = os.path.basename(font_path)
            new_font_line = f'    tl_font_dic["{tl_name}"] = "fonts/{font_filename}", {str(is_rtl)}\n'
            
            for idx, line in enumerate(lines):
                if 'tl_font_dic[' in line and tl_name in line:
                    lines[idx] = new_font_line
                    updated = True
                    break
            
            if not updated:
                # 找到合适位置插入
                for idx, line in enumerate(lines):
                    if 'tl_font_dic[' in line:
                        lines.insert(idx + 1, new_font_line)
                        updated = True
                        break
            
            if updated:
                with io.open(gui_path, 'w', encoding='utf-8') as f:
                    f.writelines(lines)
                self.logger.info(f"更新 GUI 字体配置: {gui_path}")
                return True
            else:
                self.logger.warning(f"未找到字体配置位置: {gui_path}")
                return False
                
        except Exception as e:
            self.logger.error(f"更新 GUI 字体配置失败: {e}")
            return False
    
    def _create_gui_font(
        self, 
        game_path: str, 
        tl_name: str, 
        font_path: str, 
        is_rtl: bool,
        gui_path: str
    ) -> bool:
        """创建新的 gui.rpy"""
        try:
            # 确保 fonts 目录存在
            fonts_dir = os.path.join(game_path, 'fonts')
            os.makedirs(fonts_dir, exist_ok=True)
            
            # 复制字体文件
            font_filename = os.path.basename(font_path)
            dest_font_path = os.path.join(fonts_dir, font_filename)
            
            if os.path.isfile(font_path):
                try:
                    shutil.copy(font_path, dest_font_path)
                    self.logger.info(f"复制字体文件: {font_path} -> {dest_font_path}")
                except Exception as e:
                    self.logger.warning(f"复制字体文件失败: {e}")
            else:
                self.logger.warning(f"字体文件不存在: {font_path}")
            
            # 读取模板
            if not os.path.isfile(self.template_path):
                self.logger.error(f"模板文件不存在: {self.template_path}")
                return False
                
            with io.open(self.template_path, 'r', encoding='utf-8') as f:
                template = f.read()
            
            # 替换占位符
            template = template.replace('{tl_name}', tl_name)
            template = template.replace('{font_path}', 'fonts/' + font_filename)
            template = template.replace('{is_rtl_enabled}', 'True' if is_rtl else 'False')
            
            # 写入 gui.rpy
            with io.open(gui_path, 'w', encoding='utf-8') as f:
                f.write(template)
                f.write('\n')
            
            self.logger.info(f"GUI 字体文件已生成: {gui_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"创建 GUI 字体文件失败: {e}")
            return False
    
    def gen_gui_fonts_from_tl_path(
        self,
        tl_path: str,
        font_path: str,
        is_rtl: bool = False
    ) -> bool:
        """
        从 tl 子目录路径生成 GUI 字体
        
        Args:
            tl_path: tl 目录下的子目录路径 (如 game/tl/schinese)
            font_path: 字体文件路径
            is_rtl: 是否启用 RTL
            
        Returns:
            是否成功
        """
        try:
            # 解析路径获取 game 目录和 tl_name
            path = tl_path.replace('\\', '/')
            
            # 查找 tl 目录位置
            tl_idx = path.rfind('/tl/')
            if tl_idx == -1:
                tl_idx = path.find('tl/')
                if tl_idx == -1:
                    self.logger.error(f"无法解析 tl 路径: {tl_path}")
                    return False
            
            # 获取 game 路径
            game_path = path[:tl_idx] if tl_idx > 0 else './'
            
            # 获取 tl_name
            rest = path[tl_idx + 3:]  # 跳过 'tl/'
            if '/' in rest:
                tl_name = rest[:rest.index('/')]
            else:
                tl_name = rest
            
            if not tl_name:
                self.logger.error(f"无法解析翻译语言名: {tl_path}")
                return False
            
            # 解析实际 game 目录
            game_path = str(self._resolve_game_dir(game_path))
            self.logger.info(f"解析路径: game={game_path}, tl_name={tl_name}")
            return self.gen_gui_fonts(game_path, tl_name, font_path, is_rtl)
            
        except Exception as e:
            self.logger.error(f"从 tl 路径生成 GUI 字体失败: {e}")
            return False
    
    def replace_font_in_translation(
        self,
        tl_folder: str,
        font_name: str
    ) -> int:
        """
        替换翻译文件中的 {font} 标签内容
        
        Args:
            tl_folder: tl 语言目录路径
            font_name: 新字体文件名
            
        Returns:
            替换的文件数
        """
        replaced_count = 0
        
        # 兼容性处理：如果 tl_folder 是 Path 对象，转换为字符串
        tl_folder_path = Path(tl_folder)
        if not tl_folder_path.exists():
            self.logger.warning(f"翻译目录不存在: {tl_folder}")
            return 0

        for rpy_file in tl_folder_path.rglob("*.rpy"):
            try:
                # 跳过 gui.rpy (因为这是我们生成的 Hook 文件)
                if rpy_file.name == 'gui.rpy':
                    continue

                with io.open(rpy_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                modified = False
                is_multiline = False
                
                for idx, line in enumerate(lines):
                    # 跳过多行字符串 (简单的状态机处理，可能不完美但够用)
                    stripped = line.strip()
                    if stripped.startswith('old _p("""'):
                        is_multiline = True
                    if is_multiline:
                        if stripped.endswith('""")'):
                            is_multiline = False
                        continue
                    
                    # 检查 {font} 标签
                    if '{font' not in line:
                        continue
                    
                    # 跳过注释和 old 行 (这是关键，防止修改原文备份)
                    if stripped.startswith('#') or stripped.startswith('old '):
                        continue
                    
                    # 替换 {font=xxx} 中的字体
                    new_line = self._replace_font_content(line, f'fonts/{font_name}')
                    if new_line != line:
                        lines[idx] = new_line
                        modified = True
                
                if modified:
                    with io.open(rpy_file, 'w', encoding='utf-8') as f:
                        f.writelines(lines)
                    replaced_count += 1
                    self.logger.info(f"替换字体标签: {rpy_file.name}")
                    
            except Exception as e:
                self.logger.error(f"处理文件失败 {rpy_file}: {e}")
        
        if replaced_count > 0:
            self.logger.info(f"替换字体标签完成，共 {replaced_count} 个文件")
        return replaced_count
    
    def _replace_font_content(self, text: str, new_font: str) -> str:
        """替换 {font=xxx} 标签中的字体路径"""
        # 使用非贪婪匹配来查找 {font=...} ... {/font}
        # 注意：这里假设嵌套的 font 标签可能不被完美支持，但对于大多数 Ren'Py 文本是足够的
        
        # 1. 替换 {font=...} 标签本身
        # pattern = r'\{font\s*=\s*.*?\}'
        # return re.sub(pattern, f'{{font={new_font}}}', text)
        
        # 为了更精确，只替换成对出现的标签中的定义部分
        # 逻辑：找到所有 {font=xxx}...{/font} 结构，替换其中的 font=xxx 为 font=new_font
        
        def replacer(m):
            # m.group(0) 是整个 {font=...}...{/font}
            # 我们只替换开头的 {font=...}
            return re.sub(r'\{font\s*=\s*.*?\}', f'{{font={new_font}}}', m.group(0))
            
        pattern = r'\{font\s*=\s*.*?\}.*?\{/font\}'
        return re.sub(pattern, replacer, text)
