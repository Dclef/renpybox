"""
Ren'Py 代码格式化工具
规范化缩进（Tab 转空格）、移除行尾空格
注意：不改变代码结构，只做安全的格式化操作
"""

from pathlib import Path

from base.LogManager import LogManager
from module.File.AtomicWrite import atomic_write_text


class Formatter:
    """代码格式化器"""

    def __init__(self, indent: int = 4, line_width: int = 80):
        """
        Args:
            indent: Tab 转换为的空格数
            line_width: 最大行宽（仅供参考，不强制折行）
        """
        self.logger = LogManager.get()
        self.indent = indent
        self.line_width = line_width
        # 最近一次 format_folder 的失败文件（相对或绝对路径字符串）
        self.last_failed_files: list[str] = []
        # 最近一次 format_folder 实际写盘数（与 success_count「成功处理」区分）
        self.last_modified_count: int = 0

    def format_file(
        self,
        file_path: str,
        preserve_comments: bool = True,
        fix_indent: bool = True,
        remove_trailing: bool = True,
        encoding: str = "utf-8"
    ) -> bool:
        """
        格式化单个文件（安全模式，不改变代码结构）

        Args:
            file_path: 文件路径
            preserve_comments: 是否保留注释（始终保留，参数仅为 Qt 控件占位）
            fix_indent: 是否将 Tab 转为空格
            remove_trailing: 是否移除行尾空格
            encoding: 文件编码

        Returns:
            是否成功（含无需修改的文件）
        """
        del preserve_comments  # 始终保留注释，不实现删除
        self._last_file_modified = False
        try:
            with open(file_path, "r", encoding=encoding, errors="ignore") as f:
                content = f.read()

            original_content = content

            # Tab 转空格（只转换行首 Tab，不动字符串内 Tab）
            if fix_indent:
                content = self._convert_tabs_to_spaces(content)

            # 移除行尾空格（但保留换行符）
            if remove_trailing:
                content = self._remove_trailing_whitespace(content)

            # 只有内容有变化才原子写回
            if content != original_content:
                atomic_write_text(Path(file_path), content, encoding=encoding)
                self._last_file_modified = True
                self.logger.info(f"格式化完成: {file_path}")
            else:
                self.logger.info(f"无需格式化: {file_path}")

            return True

        except Exception as e:
            self.logger.error(f"格式化失败 {file_path}: {e}")
            return False

    def _convert_tabs_to_spaces(self, content: str) -> str:
        """
        将 Tab 转换为空格，保持缩进结构
        只转换行首的 Tab
        """
        lines = content.split('\n')
        result = []

        for line in lines:
            if not line:
                result.append(line)
                continue

            # 计算行首的 Tab 和空格
            leading = ''
            rest_start = 0
            for i, char in enumerate(line):
                if char == '\t':
                    leading += ' ' * self.indent
                    rest_start = i + 1
                elif char == ' ':
                    leading += ' '
                    rest_start = i + 1
                else:
                    break

            # 重组行
            result.append(leading + line[rest_start:])

        return '\n'.join(result)

    def _remove_trailing_whitespace(self, content: str) -> str:
        """
        移除每行末尾的空格和 Tab，但保留换行符
        """
        lines = content.split('\n')
        result = [line.rstrip(' \t') for line in lines]
        return '\n'.join(result)

    def format_folder(
        self,
        folder_path: str,
        preserve_comments: bool = True,
        fix_indent: bool = True,
        remove_trailing: bool = True,
        encoding: str = "utf-8"
    ) -> int:
        """
        批量格式化文件夹

        Returns:
            成功处理文件数（含无需修改的文件，不是「改动数」）
        """
        from module.Tool.LexicalFs import iter_rpy_files_lexical

        rpy_files = iter_rpy_files_lexical(folder_path)
        success_count = 0
        modified_count = 0
        failed: list[str] = []

        self.logger.info(f"找到 {len(rpy_files)} 个 .rpy 文件")

        for file_path in rpy_files:
            if self.format_file(
                str(file_path),
                preserve_comments,
                fix_indent,
                remove_trailing,
                encoding
            ):
                success_count += 1
                if getattr(self, "_last_file_modified", False):
                    modified_count += 1
            else:
                failed.append(str(file_path))

        self.last_failed_files = failed
        self.last_modified_count = modified_count
        self.logger.info(f"格式化完成: {success_count}/{len(rpy_files)} 个文件")
        return success_count

    def remove_trailing_whitespace(self, folder_path: str) -> int:
        """
        移除行尾空格

        Args:
            folder_path: 文件夹路径

        Returns:
            处理文件数
        """
        from module.Tool.LexicalFs import iter_rpy_files_lexical

        rpy_files = iter_rpy_files_lexical(folder_path)
        processed = 0

        for file_path in rpy_files:
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                new_content = self._remove_trailing_whitespace(content)

                if new_content != content:
                    atomic_write_text(Path(file_path), new_content, encoding="utf-8")
                    processed += 1

            except Exception:
                pass

        self.logger.info(f"移除行尾空格: {processed} 个文件")
        return processed
