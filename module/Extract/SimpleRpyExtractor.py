"""简洁的 Ren'Py 翻译文件提取器

专门用于解析已提取的 tl/.rpy 翻译文件，无需运行官方抽取命令。
适用于游戏翻译已经提取到 tl 目录的场景。

主要功能：
1. 解析 old "xxx" / new "xxx" 字符串翻译对
2. 解析 translate <lang> <id>: 块中的对话翻译
3. 支持多种文件格式（.rpy, .txt）
4. 过滤垃圾数据（代码标识符、资源文件名等）
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from base.LogManager import LogManager
from module.Text.SkipRules import should_skip_text


class SimpleRpyExtractor:
    """简洁的 RPY 翻译提取器，直接解析已有翻译文件"""

    # 工具生成的钩子文件，不应该被提取或翻译
    HOOK_FILES = {
        'hook_add_change_language_entrance.rpy',
        'hook_add_change_language_entrance.rpyc',
        'hook_extract.rpy',
        'hook_extract.rpyc',
        'hook_unrpa.rpy',
        'hook_unrpa.rpyc',
        'set_default_language_at_startup.rpy',
        'set_default_language_at_startup.rpyc',
        # 缺失补丁（仅作为生成 replace_text 的中间文件，不应参与“已抽取覆盖”统计）
        'miss_ready_replace.rpy',
    }

    # 系统文件，通常不需要翻译
    SYSTEM_FILES = {'common.rpy', 'common.rpyc'}

    BUILTIN_UI_DIRS = {"base_box"}
    BUILTIN_UI_FILES = {
        "common.rpy",
        "common_box.rpy",
        "screens_box.rpy",
        "style_box.rpy",
    }

    # 匹配源文件注释 # game/xxx.rpy:123
    COMMENT_PATTERN = re.compile(r'#\s*game/(.+?):(\d+)', re.IGNORECASE)

    # 匹配 translate 块头
    TRANSLATE_BLOCK_PATTERN = re.compile(r'^\s*translate\s+(\w+)\s+(\w+)\s*:\s*$')

    # 匹配 translate strings 块头
    TRANSLATE_STRINGS_PATTERN = re.compile(r'^\s*translate\s+(\w+)\s+strings\s*:\s*$')

    # 匹配 old "xxx"
    OLD_PATTERN = re.compile(r'^\s*old\s+"(.*)"\s*$')

    # 匹配 new "xxx"
    NEW_PATTERN = re.compile(r'^\s*new\s+"(.*)"\s*$')

    def __init__(self) -> None:
        self.logger = LogManager.get()

    def extract_from_directory(
        self,
        tl_dir: Path,
        tl_name: str,
        *,
        skip_system_files: bool = True,
        filter_garbage: bool = True,
    ) -> List[Dict]:
        """
        从 tl 目录提取所有翻译条目

        Args:
            tl_dir: tl 语言目录路径 (如 game/tl/chinese)
            tl_name: 语言名称 (如 chinese)
            skip_system_files: 是否跳过系统文件 (common.rpy等)
            filter_garbage: 是否过滤垃圾数据

        Returns:
            翻译条目列表，每个条目包含:
            - file: 相对文件路径
            - line: 行号
            - original: 原文
            - translation: 译文
            - type: 类型 (strings/dialogue)
            - identifier: 翻译块标识符 (可选)
            - source_file: 源文件路径 (可选)
            - source_line: 源文件行号 (可选)
        """
        if not tl_dir.exists():
            self.logger.warning(f"tl 目录不存在: {tl_dir}")
            return []

        entries: List[Dict] = []
        
        for rpy_file in sorted(tl_dir.rglob("*.rpy")):
            # 跳过钩子文件
            if rpy_file.name in self.HOOK_FILES:
                self.logger.debug(f"跳过钩子文件: {rpy_file}")
                continue

            # 跳过系统文件
            if skip_system_files and rpy_file.name in self.SYSTEM_FILES:
                self.logger.debug(f"跳过系统文件: {rpy_file}")
                continue

            # 跳过内置 UI / 字体模板文件
            if self._is_builtin_ui_file(rpy_file):
                self.logger.debug(f"跳过内置 UI 文件: {rpy_file}")
                continue

            try:
                rel_path = rpy_file.relative_to(tl_dir).as_posix()
            except ValueError:
                rel_path = rpy_file.name

            file_entries = self._parse_rpy_file(rpy_file, tl_name, rel_path)
            
            # 过滤垃圾数据
            if filter_garbage:
                file_entries = [
                    e for e in file_entries 
                    if not self._should_skip(e.get("original", ""))
                ]
            
            entries.extend(file_entries)

        self.logger.info(f"从 {tl_dir} 提取了 {len(entries)} 条翻译条目")
        return entries

    def extract_from_files(
        self,
        file_paths: List[Path],
        tl_name: str = "chinese",
        *,
        filter_garbage: bool = True,
    ) -> List[Dict]:
        """
        从指定的文件列表提取翻译条目

        Args:
            file_paths: 文件路径列表
            tl_name: 语言名称
            filter_garbage: 是否过滤垃圾数据

        Returns:
            翻译条目列表
        """
        entries: List[Dict] = []
        
        for file_path in file_paths:
            if not file_path.exists():
                self.logger.warning(f"文件不存在: {file_path}")
                continue

            if self._is_builtin_ui_file(file_path):
                self.logger.debug(f"跳过内置 UI 文件: {file_path}")
                continue

            file_entries = self._parse_rpy_file(file_path, tl_name, str(file_path))
            
            if filter_garbage:
                file_entries = [
                    e for e in file_entries 
                    if not self._should_skip(e.get("original", ""))
                ]
            
            entries.extend(file_entries)

        self.logger.info(f"从 {len(file_paths)} 个文件提取了 {len(entries)} 条翻译条目")
        return entries

    def _is_builtin_ui_file(self, path: Path) -> bool:
        """检测是否为工具内置的 UI/字体模板文件"""
        name = path.name.lower()
        if name in self.BUILTIN_UI_FILES:
            return True
        parent = path.parent.name.lower()
        return parent in self.BUILTIN_UI_DIRS

    def _parse_rpy_file(self, file_path: Path, tl_name: str, rel_path: str) -> List[Dict]:
        """解析单个 rpy/txt 文件"""
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            self.logger.warning(f"读取文件失败 {file_path}: {e}")
            return []

        lines = content.splitlines()
        entries: List[Dict] = []

        # 状态变量
        in_strings_block = False
        in_dialogue_block = False
        current_identifier = ""
        pending_source_file: Optional[str] = None
        pending_source_line: Optional[int] = None
        block_source_file: Optional[str] = None
        block_source_line: Optional[int] = None

        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # 解析源文件注释
            comment_match = self.COMMENT_PATTERN.match(stripped)
            if comment_match:
                captured_path = comment_match.group(1).replace("\\", "/")
                if captured_path.startswith("game/"):
                    captured_path = captured_path[5:]
                try:
                    captured_line = int(comment_match.group(2))
                except ValueError:
                    captured_line = None

                if in_strings_block or in_dialogue_block:
                    block_source_file = captured_path
                    block_source_line = captured_line
                else:
                    pending_source_file = captured_path
                    pending_source_line = captured_line
                i += 1
                continue

            # 检测 translate xxx strings: 块
            strings_match = self.TRANSLATE_STRINGS_PATTERN.match(line)
            if strings_match:
                lang = strings_match.group(1)
                if lang == tl_name:
                    in_strings_block = True
                    in_dialogue_block = False
                    current_identifier = ""
                    block_source_file = pending_source_file
                    block_source_line = pending_source_line
                else:
                    in_strings_block = False
                pending_source_file = None
                pending_source_line = None
                i += 1
                continue

            # 检测 translate xxx identifier: 块
            block_match = self.TRANSLATE_BLOCK_PATTERN.match(line)
            if block_match:
                lang = block_match.group(1)
                identifier = block_match.group(2)
                if lang == tl_name and identifier != "strings":
                    in_dialogue_block = True
                    in_strings_block = False
                    current_identifier = identifier
                    block_source_file = pending_source_file
                    block_source_line = pending_source_line
                else:
                    in_dialogue_block = False
                    if identifier != "strings":
                        in_strings_block = False
                pending_source_file = None
                pending_source_line = None
                i += 1
                continue

            # 在 strings 块内解析 old/new 对
            if in_strings_block:
                old_match = self.OLD_PATTERN.match(line)
                if old_match:
                    original = self._unescape_string(old_match.group(1))
                    translation = ""

                    # 查找对应的 new
                    j = i + 1
                    while j < len(lines):
                        next_line = lines[j].strip()
                        if not next_line or next_line.startswith("#"):
                            j += 1
                            continue
                        new_match = self.NEW_PATTERN.match(lines[j])
                        if new_match:
                            translation = self._unescape_string(new_match.group(1))
                        break

                    entries.append({
                        "file": rel_path,
                        "line": i + 1,
                        "original": original,
                        "translation": translation,
                        "type": "strings",
                        "identifier": current_identifier,
                        "source_file": block_source_file,
                        "source_line": block_source_line,
                    })
                    
                    i = j + 1 if j > i else i + 1
                    continue

            # 在 dialogue 块内解析对话
            if in_dialogue_block:
                # 对话格式通常是: # "原文" 或 character "原文"
                # 后面跟着翻译行: character "译文" 或 "译文"
                # 这里简化处理，主要处理 old/new 格式
                old_match = self.OLD_PATTERN.match(line)
                if old_match:
                    original = self._unescape_string(old_match.group(1))
                    translation = ""

                    j = i + 1
                    while j < len(lines):
                        next_line = lines[j].strip()
                        if not next_line or next_line.startswith("#"):
                            j += 1
                            continue
                        new_match = self.NEW_PATTERN.match(lines[j])
                        if new_match:
                            translation = self._unescape_string(new_match.group(1))
                        break

                    entries.append({
                        "file": rel_path,
                        "line": i + 1,
                        "original": original,
                        "translation": translation,
                        "type": "dialogue",
                        "identifier": current_identifier,
                        "source_file": block_source_file,
                        "source_line": block_source_line,
                    })

                    i = j + 1 if j > i else i + 1
                    continue

            # 非块内的 old/new 对也处理（某些格式）
            old_match = self.OLD_PATTERN.match(line)
            if old_match:
                original = self._unescape_string(old_match.group(1))
                translation = ""

                j = i + 1
                while j < len(lines):
                    next_line = lines[j].strip()
                    if not next_line or next_line.startswith("#"):
                        j += 1
                        continue
                    new_match = self.NEW_PATTERN.match(lines[j])
                    if new_match:
                        translation = self._unescape_string(new_match.group(1))
                    break

                entries.append({
                    "file": rel_path,
                    "line": i + 1,
                    "original": original,
                    "translation": translation,
                    "type": "strings",
                    "identifier": "",
                    "source_file": pending_source_file,
                    "source_line": pending_source_line,
                })

                i = j + 1 if j > i else i + 1
                continue

            i += 1

        return entries

    def _unescape_string(self, text: str) -> str:
        """反转义字符串"""
        return (
            text
            .replace("\\n", "\n")
            .replace('\\"', '"')
            .replace("\\\\", "\\")
        )

    def _should_skip(self, text: str) -> bool:
        """判断文本是否应该跳过"""
        return should_skip_text(text)

    @staticmethod
    def find_tl_directory(project_dir: Path, tl_name: str) -> Optional[Path]:
        """
        从项目目录查找 tl 语言目录

        Args:
            project_dir: 项目根目录
            tl_name: 语言名称

        Returns:
            tl 语言目录路径，如果不存在返回 None
        """
        # 标准路径: project/game/tl/<lang>
        tl_dir = project_dir / "game" / "tl" / tl_name
        if tl_dir.exists():
            return tl_dir

        # 备用路径: project/tl/<lang>
        alt_tl_dir = project_dir / "tl" / tl_name
        if alt_tl_dir.exists():
            return alt_tl_dir

        return None

    @staticmethod
    def guess_project_dir_from_tl(tl_dir: Path) -> Optional[Path]:
        """
        从 tl 目录反推项目根目录

        Args:
            tl_dir: tl 语言目录 (如 game/tl/chinese)

        Returns:
            项目根目录，如果无法推断返回 None
        """
        # 检查是否是 game/tl/<lang> 格式
        if tl_dir.parent.name == "tl" and tl_dir.parent.parent.name == "game":
            return tl_dir.parent.parent.parent
        
        # 检查是否是 tl/<lang> 格式
        if tl_dir.parent.name == "tl":
            return tl_dir.parent.parent

        return None

    @staticmethod
    def resolve_game_path(target_path: str | Path) -> Tuple[Path, Path]:
        """
        解析游戏路径，获取游戏可执行文件和项目目录

        Args:
            target_path: 游戏可执行文件或项目目录

        Returns:
            (exe_path, project_dir) 元组
        """
        path = Path(target_path).resolve()
        
        # 如果是 exe 文件
        if path.is_file() and path.suffix.lower() == ".exe":
            return path, path.parent
        
        # 如果是目录，尝试找到 exe
        if path.is_dir():
            # 查找最大的 exe 文件（通常是主程序）
            candidates = list(path.glob("*.exe"))
            if candidates:
                candidates.sort(key=lambda p: p.stat().st_size if p.exists() else 0, reverse=True)
                return candidates[0], path
            return path, path  # 没有 exe，返回目录本身
        
        raise FileNotFoundError(f"路径不存在或不是有效的游戏路径: {target_path}")

    @staticmethod
    def get_game_dir(target_path: str | Path) -> Path:
        """
        获取游戏的 game 目录

        Args:
            target_path: 游戏可执行文件或项目目录

        Returns:
            game 目录路径
        """
        _, project_dir = SimpleRpyExtractor.resolve_game_path(target_path)
        game_dir = project_dir / "game"
        if game_dir.exists():
            return game_dir
        return project_dir
