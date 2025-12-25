"""Helpers for Ren'Py text extraction (official + runtime)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Tuple

from base.PathHelper import get_resource_path
from base.LogManager import LogManager
from module.Renpy.json_handler import JsonExporter
from module.Text.SkipRules import should_skip_text
from utils.call_game_python import (
    get_game_path_from_game_dir,
    get_py_path,
    get_python_path_from_game_path,
)
from utils.string_tool import encode_say_string


class RenpyExtractor:
    """High level wrapper around renpy-translator's extraction workflow."""

    HOOK_RUNTIME = "hook_extract.rpy"
    MISS_FILE_PREFIXES = ("miss_ready_replace",)

    def __init__(self) -> None:
        self.logger = LogManager.get()
        # Use PathHelper so packaged builds can find bundled hooks.
        self.hooks_dir = Path(get_resource_path("resource", "hooks"))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def official_extract(
        self,
        target_path: str | Path,
        tl_name: str,
        *,
        generate_empty: bool = False,
        force: bool = False,
    ) -> Path:
        """Run Ren'Py's built-in translate command to populate tl/<lang>/.

        Args:
            target_path: Game executable (.exe) or project directory containing the exe.
            tl_name: Target language name (matches tl/<lang>/ directory).
            generate_empty: Whether to pass --empty to Ren'Py.
            force: Re-run even if tl directory already exists.

        Returns:
            Path to the generated tl/<lang>/ directory.
        """

        exe, project = self._resolve_game_exe(target_path)
        tl_dir = project / "game" / "tl" / tl_name

        if tl_dir.exists():
            if not force:
                self.logger.info(f"官方抽取已存在: {tl_dir}")
                return tl_dir
            # force 时保留已有翻译，仅清理空的 translate 块，避免旧文件报错
            cleaned = self._remove_empty_translate_blocks(tl_dir, tl_name)
            if cleaned:
                self.logger.info(f"清理旧翻译中的空 translate 块: {cleaned} 个")

        python_path = get_python_path_from_game_path(str(exe))
        if not python_path:
            raise FileNotFoundError("未找到 Ren'Py 内置 python.exe，请确认游戏是否完整解包")

        py_path = get_py_path(str(exe))
        py_file = Path(py_path)
        if not py_file.exists():
            raise FileNotFoundError(
                f"未找到启动脚本: {py_file}. 如果游戏未生成同名 .py，请先运行启动器生成。"
            )

        tl_dir.mkdir(parents=True, exist_ok=True)

        command: List[str] = [
            str(python_path),
            "-O",
            str(py_file),
            str(project),
            "translate",
            tl_name,
        ]
        if generate_empty:
            command.append("--empty")

        moved_files = []
        try:
            # 避免官方抽取被“中间文件”干扰（例如 miss_ready_replace.rpy 是生成 replace_text 的工作文件）
            moved_files = self._temporarily_hide_tool_files(tl_dir)

            self.logger.info(f"执行官方抽取: {' '.join(command)}")
            result = subprocess.run(
                command,
                cwd=str(project),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
        finally:
            self._restore_hidden_files(moved_files)
        if result.stdout:
            self.logger.info(result.stdout.strip())
        if result.returncode != 0:
            # 提供更详细的错误信息
            error_msg = f"官方抽取失败，退出码 {result.returncode}"
            if result.stdout:
                # 检查是否是已存在翻译的错误
                if "already exists" in result.stdout:
                    error_msg = "官方抽取失败：检测到重复的翻译条目。请尝试删除 tl 文件夹后重试。"
                else:
                    # 截取最后几行错误信息
                    lines = result.stdout.strip().split('\n')
                    last_lines = lines[-5:] if len(lines) > 5 else lines
                    error_msg += f"\n{chr(10).join(last_lines)}"
            raise RuntimeError(error_msg)

        return tl_dir

    def _temporarily_hide_tool_files(self, tl_dir: Path) -> List[Tuple[Path, Path]]:
        """Temporarily move tool-generated intermediate files away from tl/<lang> before official extract."""
        moved: List[Tuple[Path, Path]] = []
        if not tl_dir.exists():
            return moved

        candidates: List[Path] = []
        try:
            for file_path in tl_dir.rglob("*"):
                if not file_path.is_file():
                    continue
                name_lower = file_path.name.lower()
                if any(name_lower.startswith(prefix) for prefix in self.MISS_FILE_PREFIXES):
                    candidates.append(file_path)
        except Exception:
            return moved

        # Rename after collecting to avoid interfering with rglob iteration.
        for src in candidates:
            try:
                dst = src.with_name(src.name + ".renpybox_hidden")
                if dst.exists():
                    dst.unlink(missing_ok=True)
                src.replace(dst)
                moved.append((dst, src))
            except Exception:
                continue

        if moved:
            self.logger.info(f"官方抽取前临时隐藏 {len(moved)} 个中间文件（避免重复翻译冲突）")
        return moved

    def _restore_hidden_files(self, moved_files: List[Tuple[Path, Path]]) -> None:
        """Restore files moved by _temporarily_hide_tool_files()."""
        for hidden, original in moved_files:
            try:
                if hidden.exists() and not original.exists():
                    hidden.replace(original)
                elif hidden.exists() and original.exists():
                    # Prefer keeping original; delete hidden to avoid duplicates.
                    hidden.unlink(missing_ok=True)
            except Exception:
                continue

    def runtime_extract(
        self,
        target_path: str | Path,
        tl_name: str,
        *,
        generate_empty: bool = False,
        timeout: int = 300,
    ) -> Path:
        """Inject runtime hook, launch game, and build tl files from JSON."""

        exe, project = self._resolve_game_exe(target_path)
        game_dir = project / "game"
        hook_source = self.hooks_dir / self.HOOK_RUNTIME
        if not hook_source.exists():
            raise FileNotFoundError(f"缺少运行时 Hook: {hook_source}")

        hook_target = game_dir / self.HOOK_RUNTIME
        shutil.copy2(hook_source, hook_target)
        self.logger.info(f"已注入运行时 Hook: {hook_target}")

        json_path = project / "extraction_hooked.json"
        if json_path.exists():
            json_path.unlink()

        finish_flag = project / "extract_runtime.finish"
        if finish_flag.exists():
            finish_flag.unlink()

        self.logger.info(f"启动游戏进行运行时提取: {exe}")
        proc = subprocess.Popen([str(exe)], cwd=str(project))

        start = time.time()
        while True:
            if json_path.exists() and json_path.stat().st_size > 0:
                break
            if proc.poll() is not None and not json_path.exists():
                raise RuntimeError("游戏已退出但未生成 extraction_hooked.json")
            if time.time() - start > timeout:
                proc.terminate()
                raise TimeoutError("等待 extraction_hooked.json 超时")
            time.sleep(1)

        with json_path.open("r", encoding="utf-8") as f:
            mapping = json.load(f)

        self.logger.info("运行时 JSON 捕获完成，开始生成 tl 文件")
        tl_dir = self._write_runtime_tl(project, tl_name, mapping, generate_empty)

        # 清理
        json_path.unlink(missing_ok=True)
        for extra in [hook_target, hook_target.with_suffix(".rpyc")]:
            extra.unlink(missing_ok=True)
        finish_flag.touch()
        self.logger.info(f"运行时提取完成: {tl_dir}")
        return tl_dir

    def collect_entries(
        self,
        target_path: str | Path,
        tl_name: str,
        *,
        ensure_official: bool = False,
        force: bool = False,
    ) -> List[Dict]:
        """Return parsed translation entries from tl/<lang>.

        If ensure_official is True, run official extraction beforehand.
        """

        exe, project = self._resolve_game_exe(target_path)
        if ensure_official:
            self.official_extract(exe, tl_name, force=force)
        return self._parse_tl_directory(project, tl_name)

    def export_to_json(
        self,
        target_path: str | Path,
        tl_name: str,
        output_path: str | Path,
        *,
        include_metadata: bool = True,
        force_extract: bool = False,
    ) -> bool:
        """Run official extract (if needed) and export to structured JSON."""

        entries = self.collect_entries(
            target_path,
            tl_name,
            ensure_official=True,
            force=force_extract,
        )
        data: Dict[str, List[Dict]] = {}
        for entry in entries:
            if self.should_skip_text(entry.get("original", "")):
                continue
            data.setdefault(entry["file"], []).append(entry)

        if not data:
            self.logger.warning("未发现任何翻译条目，JSON 导出跳过")
            return False

        exporter = JsonExporter()
        return exporter.export(data, str(output_path), include_metadata=include_metadata)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _resolve_game_exe(self, target_path: str | Path) -> Tuple[Path, Path]:
        path = Path(target_path).resolve()
        if path.is_file() and path.suffix.lower() == ".exe":
            return path, path.parent
        if path.is_dir():
            exe = self._auto_find_exe(path)
            if exe:
                return exe, exe.parent
        raise FileNotFoundError("请提供 Ren'Py 游戏可执行文件或其所在目录")

    def _auto_find_exe(self, directory: Path) -> Path | None:
        candidates = list(directory.glob("*.exe"))
        if not candidates:
            return None
        candidates.sort(key=lambda p: p.stat().st_size if p.exists() else 0, reverse=True)
        return candidates[0]

    def _remove_empty_translate_blocks(self, tl_dir: Path, tl_name: str) -> int:
        """移除空的 translate <lang> strings: 块，避免官方抽取报错。"""
        pattern = re.compile(r'^(\s*)translate\s+' + re.escape(tl_name) + r'\s+strings\s*:\s*$')
        removed = 0

        for rpy_file in tl_dir.rglob("*.rpy"):
            try:
                lines = rpy_file.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception as exc:
                self.logger.warning(f"读取翻译文件失败 {rpy_file}: {exc}")
                continue

            new_lines = []
            i = 0
            changed = False

            while i < len(lines):
                match = pattern.match(lines[i])
                if match:
                    base_indent = len(match.group(1))
                    block: list[str] = []
                    j = i + 1
                    while j < len(lines):
                        line_j = lines[j]
                        if not line_j.strip():
                            block.append(line_j)
                            j += 1
                            continue
                        indent = len(line_j) - len(line_j.lstrip(" "))
                        if indent > base_indent:
                            block.append(line_j)
                            j += 1
                            continue
                        break

                    has_content = False
                    for blk in block:
                        stripped = blk.strip()
                        if not stripped or stripped.startswith("#"):
                            continue
                        if stripped.startswith(("old ", "new ")):
                            has_content = True
                            break
                        has_content = True
                        break

                    if not has_content:
                        removed += 1
                        changed = True
                        i = j
                        continue

                    new_lines.extend(lines[i:j])
                    i = j
                    continue

                new_lines.append(lines[i])
                i += 1

            if changed:
                rpy_file.write_text("\n".join(new_lines), encoding="utf-8")

        return removed

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
    }

    BUILTIN_UI_DIRS = {"base_box"}
    BUILTIN_UI_FILES = {
        "common.rpy",
        "common_box.rpy",
        "screens_box.rpy",
        "style_box.rpy",
    }

    COMMENT_PATTERN = re.compile(r'#\s*game/(.+?):(\d+)', re.IGNORECASE)

    def _parse_tl_directory(self, project: Path, tl_name: str) -> List[Dict]:
        tl_dir = project / "game" / "tl" / tl_name
        if not tl_dir.exists():
            return []

        entries: List[Dict] = []
        for tl_file in sorted(tl_dir.rglob("*.rpy")):
            if self._is_builtin_ui_file(tl_file):
                self.logger.debug(f"跳过内置 UI 文件: {tl_file}")
                continue
            # 跳过工具生成的钩子文件
            if tl_file.name in self.HOOK_FILES:
                self.logger.debug(f"跳过钩子文件: {tl_file}")
                continue
                
            rel = tl_file.relative_to(project / "game" / "tl" / tl_name).as_posix()
            try:
                lines = tl_file.read_text(encoding="utf-8", errors="ignore").splitlines()
            except Exception as exc:
                self.logger.warning(f"读取翻译文件失败 {tl_file}: {exc}")
                continue

            in_block = False
            current_identifier = None
            block_source_file: str | None = None
            block_source_line: int | None = None
            pending_source_file: str | None = None
            pending_source_line: int | None = None
            idx = 0
            while idx < len(lines):
                raw = lines[idx]
                stripped = raw.strip()

                match = self.COMMENT_PATTERN.match(stripped)
                if match:
                    captured_path = match.group(1).replace("\\", "/")
                    if captured_path.startswith("game/"):
                        captured_path = captured_path[5:]
                    try:
                        captured_line = int(match.group(2))
                    except ValueError:
                        captured_line = None

                    if in_block:
                        block_source_file = captured_path
                        block_source_line = captured_line
                    else:
                        pending_source_file = captured_path
                        pending_source_line = captured_line
                    idx += 1
                    continue

                if stripped.startswith("translate ") and stripped.endswith(":"):
                    parts = stripped.split()
                    if len(parts) >= 3 and parts[0] == "translate" and parts[1] == tl_name:
                        current_identifier = parts[2].rstrip(":")
                        in_block = True
                        block_source_file = pending_source_file
                        block_source_line = pending_source_line
                        pending_source_file = None
                        pending_source_line = None
                    else:
                        in_block = False
                        block_source_file = None
                        block_source_line = None
                        pending_source_file = None
                        pending_source_line = None
                    idx += 1
                    continue

                if in_block and stripped.startswith("old "):
                    original = self._extract_quoted(stripped)
                    translation = ""

                    lookahead = idx + 1
                    while lookahead < len(lines):
                        candidate = lines[lookahead].strip()
                        if candidate.startswith("new "):
                            translation = self._extract_quoted(candidate)
                            break
                        if candidate.startswith("old ") or candidate.startswith("translate "):
                            lookahead -= 1
                            break
                        lookahead += 1

                    if self.should_skip_text(original):
                        if lookahead >= idx + 1:
                            idx = lookahead + 1
                        else:
                            idx += 1
                        continue

                    entries.append(
                        {
                            "file": rel,
                            "line": idx + 1,
                            "identifier": current_identifier or "",
                            "original": original,
                            "translation": translation,
                            "source_file": block_source_file,
                            "source_line": block_source_line,
                            "type": "strings",
                        }
                    )

                    if lookahead >= idx + 1:
                        idx = lookahead + 1
                    else:
                        idx += 1
                    continue

                idx += 1

        self.logger.info(f"解析 tl/{tl_name}，共 {len(entries)} 条记录")
        return entries

    def _extract_quoted(self, line: str) -> str:
        if "\"" in line:
            first = line.find('"')
            last = line.rfind('"')
            if first != -1 and last > first:
                return line[first + 1:last].replace('\\"', '"').replace('\\n', '\n')
        return line

    def _write_runtime_tl(
        self,
        project: Path,
        tl_name: str,
        mapping: Dict[str, List[List]],
        generate_empty: bool,
    ) -> Path:
        tl_dir = project / "game" / "tl" / tl_name
        tl_dir.mkdir(parents=True, exist_ok=True)

        for filename, entries in mapping.items():
            entries.sort(key=lambda item: item[3] if len(item) > 3 else 0)

            if filename.startswith("game/"):
                rel = Path(filename[5:])
            else:
                rel = Path(filename)

            target = tl_dir / rel
            target = target.with_suffix('.rpy')
            target.parent.mkdir(parents=True, exist_ok=True)

            existing_ids = set()
            existing_lines = []
            if target.exists():
                existing_lines = target.read_text(encoding="utf-8", errors="ignore").splitlines()
                for line in existing_lines:
                    marker = f"translate {tl_name} "
                    if line.startswith(marker):
                        existing_ids.add(line[len(marker):].rstrip(':'))

            with target.open('a', encoding='utf-8') as f:
                if not existing_lines:
                    header = [
                        "# Generated by RenpyBox runtime extract",
                        f"# Source: {filename}",
                        "",
                    ]
                    f.write('\n'.join(header))
                for identifier, who, what, linenumber in entries:
                    if identifier in existing_ids:
                        continue
                    who_prefix = f"{who} " if who else ""
                    encoded = encode_say_string(str(what)) if what is not None else ""
                    f.write(f"\n# game/{filename}:{linenumber}\n")
                    f.write(f"translate {tl_name} {identifier}:\n\n")
                    f.write(f"    # {who_prefix}\"{encoded}\"\n")
                    if generate_empty:
                        f.write(f"    {who_prefix}\"\"\n")
                    else:
                        f.write(f"    {who_prefix}\"{encoded}\"\n")
                f.write("\n")

        return tl_dir

    def _is_builtin_ui_file(self, path: Path) -> bool:
        """跳过内置 UI / 字体模板文件"""
        name = path.name.lower()
        if name in self.BUILTIN_UI_FILES:
            return True
        parent = path.parent.name.lower()
        return parent in self.BUILTIN_UI_DIRS

    @staticmethod
    def should_skip_text(text: str) -> bool:
        # Basic skip rules
        if should_skip_text(text):
            return True
            
        # Check against Text Preserve list from Config
        try:
            from module.Config import Config
            # Load config to get latest rules
            config = Config().load()
            if config.text_preserve_enable and config.text_preserve_data:
                candidate = text.strip()
                for item in config.text_preserve_data:
                    src = ""
                    if isinstance(item, dict):
                        src = item.get("src", "")
                    elif isinstance(item, str):
                        src = item
                    
                    if src and src == candidate:
                        return True
        except Exception:
            pass
            
        return False
