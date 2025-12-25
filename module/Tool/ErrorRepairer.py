"""
Ren'Py 错误修复工具
检查并修复常见语法错误，支持深度 Lint 检查
"""

import io
import os
import re
import subprocess
from typing import List, Dict, Tuple, Optional
from pathlib import Path

from base.LogManager import LogManager
from utils.call_game_python import get_python_path_from_game_path, get_py_path


class ErrorRepairer:
    """错误修复器"""

    def __init__(self):
        self.logger = LogManager.get()
        self.errors_found = []

    def check_file(
        self,
        file_path: str,
        check_syntax: bool = True,
        check_indent: bool = True,
        check_quotes: bool = True,
        encoding: str = "utf-8"
    ) -> List[Dict[str, any]]:
        """
        检查单个文件

        Args:
            file_path: 文件路径
            check_syntax: 是否检查语法
            check_indent: 是否检查缩进
            check_quotes: 是否检查引号匹配
            encoding: 文件编码

        Returns:
            错误列表 [{"line": 行号, "type": 错误类型, "message": 错误信息}, ...]
        """
        errors = []

        try:
            with open(file_path, "r", encoding=encoding, errors="ignore") as f:
                lines = f.readlines()

            for line_num, line in enumerate(lines, 1):
                # 语法检查
                if check_syntax:
                    # 检查 label 后是否有冒号
                    if line.strip().startswith("label ") and not line.strip().endswith(":"):
                        errors.append({
                            "line": line_num,
                            "type": "syntax",
                            "message": "label 语句缺少冒号",
                            "content": line.strip()
                        })

                    # 检查 if/elif/else/menu 后是否有冒号
                    if re.match(r'^\s*(if|elif|else|menu|while|for)\s', line) and \
                       not line.strip().endswith(":"):
                        errors.append({
                            "line": line_num,
                            "type": "syntax",
                            "message": "控制流语句缺少冒号",
                            "content": line.strip()
                        })

                # 缩进检查
                if check_indent:
                    # 检查是否使用 Tab
                    if "\t" in line:
                        errors.append({
                            "line": line_num,
                            "type": "indent",
                            "message": "使用了 Tab 而非空格缩进",
                            "content": line.strip()
                        })

                # 引号匹配检查
                if check_quotes:
                    # 统计引号数量
                    double_quotes = line.count('"') - line.count('\\"')
                    single_quotes = line.count("'") - line.count("\\'")

                    if double_quotes % 2 != 0:
                        errors.append({
                            "line": line_num,
                            "type": "quotes",
                            "message": "双引号不匹配",
                            "content": line.strip()
                        })

                    if single_quotes % 2 != 0:
                        errors.append({
                            "line": line_num,
                            "type": "quotes",
                            "message": "单引号不匹配",
                            "content": line.strip()
                        })

        except Exception as e:
            self.logger.error(f"检查文件失败 {file_path}: {e}")

        return errors

    def check_folder(
        self,
        folder_path: str,
        check_syntax: bool = True,
        check_indent: bool = True,
        check_quotes: bool = True,
        encoding: str = "utf-8"
    ) -> Dict[str, List[Dict]]:
        """
        批量检查文件夹

        Args:
            folder_path: 文件夹路径
            check_syntax: 是否检查语法
            check_indent: 是否检查缩进
            check_quotes: 是否检查引号匹配
            encoding: 文件编码

        Returns:
            {文件路径: 错误列表}
        """
        all_errors = {}
        rpy_files = list(Path(folder_path).rglob("*.rpy"))

        self.logger.info(f"检查 {len(rpy_files)} 个 .rpy 文件")

        for file_path in rpy_files:
            errors = self.check_file(
                str(file_path),
                check_syntax,
                check_indent,
                check_quotes,
                encoding
            )

            if errors:
                all_errors[str(file_path)] = errors

        total_errors = sum(len(errs) for errs in all_errors.values())
        self.logger.info(f"检查完成: 发现 {total_errors} 个错误")

        return all_errors

    def auto_fix_file(
        self,
        file_path: str,
        fix_indent: bool = True,
        fix_quotes: bool = False,
        encoding: str = "utf-8"
    ) -> Tuple[bool, int]:
        """
        自动修复文件

        Args:
            file_path: 文件路径
            fix_indent: 是否修复缩进
            fix_quotes: 是否尝试修复引号 (危险操作)
            encoding: 文件编码

        Returns:
            (是否成功, 修复数量)
        """
        try:
            with open(file_path, "r", encoding=encoding, errors="ignore") as f:
                lines = f.readlines()

            new_lines = []
            fix_count = 0

            for line in lines:
                new_line = line

                # 修复缩进: Tab 转空格
                if fix_indent and "\t" in line:
                    new_line = new_line.replace("\t", "    ")
                    fix_count += 1

                # 修复引号 (简单替换: 中文引号转英文引号)
                if fix_quotes:
                    if """ in new_line or """ in new_line:
                        new_line = new_line.replace(""", '"').replace(""", '"')
                        fix_count += 1
                    if "'" in new_line or "'" in new_line:
                        new_line = new_line.replace("'", "'").replace("'", "'")
                        fix_count += 1

                new_lines.append(new_line)

            # 写回文件
            if fix_count > 0:
                with open(file_path, "w", encoding=encoding) as f:
                    f.writelines(new_lines)
                self.logger.info(f"修复完成: {file_path} ({fix_count} 处)")

            return True, fix_count

        except Exception as e:
            self.logger.error(f"修复失败 {file_path}: {e}")
            return False, 0

    def export_error_report(self, errors: Dict[str, List[Dict]], output_path: str):
        """
        导出错误报告为 Excel

        Args:
            errors: 错误字典 {文件路径: 错误列表}
            output_path: 输出路径
        """
        try:
            import openpyxl
            from openpyxl import Workbook

            wb = Workbook()
            ws = wb.active
            ws.title = "Error Report"

            # 写入表头
            headers = ["文件", "行号", "错误类型", "错误信息", "内容"]
            ws.append(headers)

            # 写入数据
            for file_path, file_errors in errors.items():
                for error in file_errors:
                    ws.append([
                        os.path.basename(file_path),
                        error.get("line", 0),
                        error.get("type", ""),
                        error.get("message", ""),
                        error.get("content", "")
                    ])

            wb.save(output_path)
            self.logger.info(f"错误报告已导出: {output_path}")

        except Exception as e:
            self.logger.error(f"导出错误报告失败: {e}")

    # ========== 深度 Lint 检查 (调用 Ren'Py 内置 lint) ==========
    
    def exec_renpy_lint(self, game_path: str) -> Optional[str]:
        """
        执行 Ren'Py 内置 lint 命令
        
        Args:
            game_path: 游戏可执行文件路径 (.exe)
            
        Returns:
            错误输出内容，如果无错误则返回 None
        """
        try:
            python_path = get_python_path_from_game_path(game_path)
            py_path = get_py_path(game_path)
            game_dir = os.path.dirname(game_path)
            
            if not python_path or not os.path.isfile(python_path):
                self.logger.error(f"找不到游戏 Python: {python_path}")
                return None
                
            if not os.path.isfile(py_path):
                self.logger.error(f"找不到游戏 .py 文件: {py_path}")
                return None
            
            # 错误输出文件
            error_output = os.path.join(game_dir, "lint_errors.txt")
            
            # 构建 lint 命令
            command = f'"{python_path}" -O "{py_path}" "{game_dir}" lint'
            
            self.logger.info(f"执行 Lint 命令: {command}")
            
            # 执行命令
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                creationflags=0x08000000 if os.name == 'nt' else 0,  # CREATE_NO_WINDOW
                cwd=game_dir
            )
            
            # 合并 stdout 和 stderr
            output = (result.stdout or "") + (result.stderr or "")
            
            if output.strip():
                # 保存到文件
                with open(error_output, "w", encoding="utf-8") as f:
                    f.write(output)
                self.logger.info(f"Lint 结果已保存到: {error_output}")
                return output
            else:
                self.logger.info("Lint 检查完成，未发现错误")
                return None
                
        except Exception as e:
            self.logger.error(f"执行 Lint 失败: {e}")
            return None
    
    def parse_lint_errors(self, lint_output: str) -> List[Dict]:
        """
        解析 Lint 输出内容
        
        Args:
            lint_output: lint 命令的输出
            
        Returns:
            错误列表
        """
        errors = []
        
        if not lint_output:
            return errors
            
        for line in lint_output.split('\n'):
            line = line.strip()
            if not line:
                continue
                
            error_info = {"raw": line}
            
            # 解析常见错误格式: "file.rpy", line X: error message
            if ', line ' in line:
                try:
                    # 提取文件名
                    idx = line.index(', line ')
                    file_part = line[:idx]
                    if ' ' in file_part:
                        file_part = file_part[file_part.index(' ') + 1:]
                    error_info["file"] = file_part.strip('"')
                    
                    # 提取行号
                    rest = line[idx + len(', line '):]
                    if ':' in rest:
                        line_num = rest[:rest.index(':')]
                        error_info["line"] = int(line_num.strip())
                        error_info["message"] = rest[rest.index(':') + 1:].strip()
                    
                except Exception:
                    pass
            
            # 解析翻译重复错误
            elif line.startswith('Exception: A translation for '):
                error_info["type"] = "duplicate_translation"
                if 'already exists at ' in line:
                    idx = line.rindex('already exists at ')
                    location = line[idx + len('already exists at '):].rstrip('.')
                    if ':' in location:
                        file_part, line_part = location.rsplit(':', 1)
                        error_info["file"] = file_part.strip()
                        try:
                            error_info["line"] = int(line_part.strip())
                        except ValueError:
                            pass
                error_info["message"] = line
            
            # 标记错误类型
            if 'is not terminated with a newline' in line:
                error_info["type"] = "unterminated_string"
            elif 'end of line expected' in line:
                error_info["type"] = "syntax_error"
            elif 'expects a non-empty block' in line:
                error_info["type"] = "empty_block"
            elif 'unknown statement' in line:
                error_info["type"] = "unknown_statement"
            elif 'expected statement' in line:
                error_info["type"] = "expected_statement"
            elif 'Could not parse string' in line:
                error_info["type"] = "parse_error"
                
            errors.append(error_info)
            
        return errors
    
    def fix_by_lint(self, game_path: str, max_iterations: int = 16) -> Tuple[bool, int]:
        """
        通过 Lint 检查自动修复错误（递归修复）
        
        Args:
            game_path: 游戏可执行文件路径
            max_iterations: 最大迭代次数
            
        Returns:
            (是否成功, 修复的文件数)
        """
        total_fixed = 0
        game_dir = os.path.dirname(game_path)
        
        for iteration in range(max_iterations):
            self.logger.info(f"开始第 {iteration + 1}/{max_iterations} 轮 Lint 检查...")
            
            # 执行 lint
            lint_output = self.exec_renpy_lint(game_path)
            
            if not lint_output:
                self.logger.info("没有更多错误，修复完成!")
                break
                
            # 解析错误
            errors = self.parse_lint_errors(lint_output)
            
            if not errors:
                self.logger.info("没有可解析的错误，修复完成!")
                break
            
            fixed_in_round = 0
            processed_files = set()
            
            for error in errors:
                file_path = error.get("file")
                line_num = error.get("line")
                error_type = error.get("type", "")
                
                if not file_path or not line_num:
                    continue
                    
                # 构建完整路径
                if not os.path.isabs(file_path):
                    file_path = os.path.join(game_dir, file_path)
                    
                if not os.path.isfile(file_path):
                    self.logger.warning(f"文件不存在: {file_path}")
                    continue
                
                # 避免重复处理同一文件的同一行
                key = f"{file_path}:{line_num}"
                if key in processed_files:
                    continue
                processed_files.add(key)
                
                # 尝试修复
                if self._fix_single_lint_error(file_path, line_num, error_type):
                    fixed_in_round += 1
                    total_fixed += 1
            
            if fixed_in_round == 0:
                self.logger.info("本轮没有修复任何错误，停止迭代")
                break
                
            self.logger.info(f"第 {iteration + 1} 轮修复了 {fixed_in_round} 个错误")
        
        return True, total_fixed
    
    def _fix_single_lint_error(self, file_path: str, line_num: int, error_type: str) -> bool:
        """
        修复单个 Lint 错误
        
        Args:
            file_path: 文件路径
            line_num: 错误行号 (1-based)
            error_type: 错误类型
            
        Returns:
            是否修复成功
        """
        try:
            with io.open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            if line_num < 1 or line_num > len(lines):
                return False
                
            idx = line_num - 1  # 转为 0-based
            original_line = lines[idx]
            
            self.logger.info(f"修复 {file_path} 第 {line_num} 行: {original_line.strip()[:50]}...")
            
            # 根据错误类型修复
            if error_type == "duplicate_translation":
                # 重复翻译：删除 old/new 对
                if lines[idx].strip().startswith('old ') and idx + 1 < len(lines) and lines[idx + 1].strip().startswith('new '):
                    lines[idx] = ''
                    lines[idx + 1] = ''
                    if idx > 0 and lines[idx - 1].strip().startswith('#'):
                        lines[idx - 1] = ''
                elif lines[idx].strip().startswith('new ') and idx > 0 and lines[idx - 1].strip().startswith('old '):
                    lines[idx] = ''
                    lines[idx - 1] = ''
                    if idx > 1 and lines[idx - 2].strip().startswith('#'):
                        lines[idx - 2] = ''
                        
            elif error_type in ("unknown_statement", "expected_statement"):
                # 未知语句：替换为空行
                lines[idx] = '\n'
                
            elif error_type in ("unterminated_string", "parse_error"):
                # 字符串未结束：替换为空字符串
                if lines[idx].strip().startswith('translate'):
                    lines[idx] = '\n'
                else:
                    lines[idx] = '    ""\n'
                    
            else:
                # 默认：替换为空字符串
                lines[idx] = '    ""\n'
            
            # 移除连续空行
            lines = self._remove_consecutive_empty_lines(lines)
            
            # 写回文件
            with io.open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
                
            return True
            
        except Exception as e:
            self.logger.error(f"修复错误失败 {file_path}:{line_num} - {e}")
            return False
    
    def _remove_consecutive_empty_lines(self, lines: List[str]) -> List[str]:
        """移除连续的空行，最多保留一个"""
        result = []
        prev_empty = False
        
        for line in lines:
            is_empty = not line.strip()
            if is_empty and prev_empty:
                continue
            result.append(line)
            prev_empty = is_empty
            
        return result
