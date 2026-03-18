"""Helpers for Ren'Py text extraction (official + runtime)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

from base.LogManager import LogManager
from base.PathHelper import get_resource_path
from module.Renpy.renpy_tl_core import TlStmtKind, escape_tl_string
from module.Renpy.renpy_tl_io import RenpyTlItemExtractor
from module.Renpy.renpy_tl_core import parse_tl_document
from module.Renpy.json_handler import JsonExporter
from module.Text.SkipRules import should_skip_text
from utils.call_game_python import (
    get_game_path_from_game_dir,
    get_py_path,
    get_python_path_from_game_path,
)
from utils.string_tool import encode_say_string


class RenpyExtractor:
    """High level wrapper around renpy-translator's extraction workflow.

    Supports both official extraction and EXE runtime hook extraction.
    """

    HOOK_RUNTIME = "zz_renpybox_runtime_extract.rpy"
    HOOK_RESULT = "extraction_hooked.json"
    MISS_FILE_PREFIXES = ("miss_ready_replace",)

    def __init__(self) -> None:
        self.logger = LogManager.get()

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
        progress_callback: Callable[[str], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> Path:
        """Inject runtime hook, launch game, and build tl files from JSON."""
        exe, project = self._resolve_game_exe(target_path)
        game_dir = project / "game"
        if not game_dir.exists():
            raise FileNotFoundError(f"未找到 game 目录: {game_dir}")
        normalized_tl_name = (tl_name or "").strip() or "chinese"
        target_tl_dir = game_dir / "tl" / normalized_tl_name
        target_tl_dir.mkdir(parents=True, exist_ok=True)

        hook_source = Path(
            get_resource_path("resource", "hooks", "hook_runtime_extract.rpy")
        )
        if not hook_source.exists():
            raise FileNotFoundError(f"未找到运行时 hook 脚本: {hook_source}")

        hook_target = game_dir / self.HOOK_RUNTIME
        hook_compiled = hook_target.with_suffix(".rpyc")
        result_path = project / self.HOOK_RESULT

        if should_stop and should_stop():
            raise RuntimeError("运行时 HOOK 抽取已取消")

        self._cleanup_runtime_files(hook_target, hook_compiled, result_path)
        shutil.copyfile(hook_source, hook_target)
        self._report_progress(
            progress_callback,
            f"已注入运行时 hook，目标目录：{target_tl_dir}，准备启动游戏 EXE",
        )

        creationflags = 0x08000000 if os.name == "nt" else 0
        launch_env = os.environ.copy()
        launch_env["RENPYBOX_TL_NAME"] = normalized_tl_name
        # 避免 Ren'Py 把字符串更新写到“当前语言目录”而不是用户指定目录。
        launch_env.pop("RENPY_UPDATE_STRINGS", None)
        process = subprocess.Popen(
            [str(exe)],
            cwd = str(project),
            env = launch_env,
            stdout = subprocess.DEVNULL,
            stderr = subprocess.DEVNULL,
            creationflags = creationflags,
        )

        try:
            self._report_progress(progress_callback, f"正在运行 EXE：{exe.name}")
            self._wait_for_runtime_result(
                result_path,
                process,
                timeout = timeout,
                progress_callback = progress_callback,
                should_stop = should_stop,
            )
            try:
                process.wait(timeout = 10)
            except Exception:
                pass

            runtime_data = self._load_runtime_mapping(result_path, project)
            self._report_progress(progress_callback, "运行时抽取完成，正在写入 tl 目录")
            tl_dir = self._write_runtime_tl(project, normalized_tl_name, runtime_data, generate_empty)
            self._report_progress(progress_callback, f"已写入 tl 目录：{tl_dir}")
            return tl_dir
        finally:
            self._cleanup_runtime_files(hook_target, hook_compiled, result_path)
            self._terminate_process(process)

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

    def _report_progress(
        self,
        callback: Callable[[str], None] | None,
        message: str,
    ) -> None:
        if callback is None:
            return
        try:
            callback(message)
        except Exception:
            return

    def _wait_for_runtime_result(
        self,
        result_path: Path,
        process: subprocess.Popen,
        *,
        timeout: int,
        progress_callback: Callable[[str], None] | None,
        should_stop: Callable[[], bool] | None,
    ) -> None:
        start_time = time.monotonic()
        last_notice = -1
        exited_without_output_at: float | None = None

        while True:
            if should_stop and should_stop():
                self._terminate_process(process)
                raise RuntimeError("运行时 HOOK 抽取已取消")

            if result_path.exists():
                try:
                    if result_path.stat().st_size > 0:
                        return
                except OSError:
                    pass

            if process.poll() is not None and not result_path.exists():
                if exited_without_output_at is None:
                    exited_without_output_at = time.monotonic()
                elif time.monotonic() - exited_without_output_at >= 3:
                    raise RuntimeError(
                        f"游戏进程已退出，但未生成 {self.HOOK_RESULT}。"
                    )
            else:
                exited_without_output_at = None

            elapsed = int(time.monotonic() - start_time)
            if elapsed > 0 and elapsed % 10 == 0 and elapsed != last_notice:
                last_notice = elapsed
                self._report_progress(
                    progress_callback,
                    f"等待运行时抽取结果… {elapsed}s",
                )

            if time.monotonic() - start_time > timeout:
                self._terminate_process(process)
                raise TimeoutError(
                    f"运行时 HOOK 抽取超时（{timeout}s），未等到 {self.HOOK_RESULT}"
                )

            time.sleep(0.5)

    def _load_runtime_mapping(
        self,
        result_path: Path,
        project: Path,
    ) -> Dict[str, Dict[str, List[List[Any]]]]:
        last_error: Exception | None = None

        for _ in range(10):
            try:
                payload = json.loads(result_path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    raise RuntimeError("运行时抽取结果格式无效")

                dialogues_payload = payload.get("dialogues")
                strings_payload = payload.get("strings")

                # Backward compatibility with the old flat-only dialogue payload.
                if not isinstance(dialogues_payload, dict) and not isinstance(strings_payload, dict):
                    dialogues_payload = payload
                    strings_payload = {}

                dialogues = self._normalize_runtime_dialogues(dialogues_payload, project)
                strings = self._normalize_runtime_strings(strings_payload, project)

                if not dialogues and not strings:
                    raise RuntimeError("运行时 HOOK 未抽取到任何可翻译文本")

                total_dialogues = sum(len(v) for v in dialogues.values())
                total_strings = sum(len(v) for v in strings.values())
                self.logger.info(
                    "运行时 HOOK 共抽取 "
                    f"{total_dialogues} 条对白 / {total_strings} 条字符串，"
                    f"覆盖 {len(set(dialogues) | set(strings))} 个脚本文件"
                )
                return {
                    "dialogues": dialogues,
                    "strings": strings,
                }
            except Exception as exc:
                last_error = exc
                time.sleep(0.5)

        raise RuntimeError(f"读取运行时抽取结果失败: {last_error}")

    def _normalize_runtime_dialogues(
        self,
        payload: Any,
        project: Path,
    ) -> Dict[str, List[List[Any]]]:
        mapping: Dict[str, List[List[Any]]] = {}
        if not isinstance(payload, dict):
            return mapping

        for raw_filename, raw_entries in payload.items():
            if not isinstance(raw_filename, str) or not isinstance(raw_entries, list):
                continue

            filename = self._normalize_runtime_filename(raw_filename, project)
            if filename == "":
                continue

            entries: List[List[Any]] = []
            for raw_entry in raw_entries:
                if not isinstance(raw_entry, (list, tuple)) or len(raw_entry) < 4:
                    continue

                identifier = str(raw_entry[0] or "").strip()
                if identifier == "":
                    continue

                who_raw = raw_entry[1]
                if who_raw is None or isinstance(who_raw, str):
                    who = who_raw
                else:
                    who = str(who_raw)

                what = raw_entry[2]
                if what is None:
                    what = ""
                elif not isinstance(what, str):
                    what = str(what)

                try:
                    linenumber = int(raw_entry[3])
                except Exception:
                    linenumber = 0

                entries.append([identifier, who, what, linenumber])

            if entries:
                mapping.setdefault(filename, []).extend(entries)

        return mapping

    def _normalize_runtime_strings(
        self,
        payload: Any,
        project: Path,
    ) -> Dict[str, List[List[Any]]]:
        mapping: Dict[str, List[List[Any]]] = {}
        if not isinstance(payload, dict):
            return mapping

        for raw_filename, raw_entries in payload.items():
            if not isinstance(raw_filename, str) or not isinstance(raw_entries, list):
                continue

            filename = self._normalize_runtime_filename(raw_filename, project)
            if filename == "":
                continue

            entries: List[List[Any]] = []
            for raw_entry in raw_entries:
                if isinstance(raw_entry, str):
                    original = raw_entry
                    translation = raw_entry
                elif isinstance(raw_entry, (list, tuple)) and len(raw_entry) >= 1:
                    original = raw_entry[0]
                    translation = raw_entry[1] if len(raw_entry) >= 2 else raw_entry[0]
                else:
                    continue

                if original is None:
                    continue
                if not isinstance(original, str):
                    original = str(original)
                if original == "":
                    continue

                if translation is None:
                    translation = original
                elif not isinstance(translation, str):
                    translation = str(translation)

                entries.append([original, translation])

            if entries:
                mapping.setdefault(filename, []).extend(entries)

        return mapping

    def _normalize_runtime_filename(self, filename: str, project: Path) -> str:
        text = str(filename or "").replace("\\", "/").strip()
        if text == "":
            return ""

        if text.startswith("game/"):
            return text

        lower = text.lower()
        marker = "/game/"
        index = lower.find(marker)
        if index >= 0:
            return "game/" + text[index + len(marker):]

        try:
            path = Path(text)
            if path.is_absolute():
                try:
                    rel = path.resolve().relative_to(project.resolve())
                    return str(rel).replace("\\", "/")
                except Exception:
                    return path.name.replace("\\", "/")
        except Exception:
            pass

        return text.lstrip("./")

    def _cleanup_runtime_files(
        self,
        hook_target: Path,
        hook_compiled: Path,
        result_path: Path,
    ) -> None:
        for path in (hook_target, hook_compiled, result_path):
            try:
                path.unlink(missing_ok = True)
            except Exception:
                continue

    def _terminate_process(self, process: subprocess.Popen | None) -> None:
        if process is None or process.poll() is not None:
            return

        try:
            process.terminate()
        except Exception:
            return

        try:
            process.wait(timeout = 2)
        except Exception:
            return

    # 工具生成的脚本/中间文件，不应该被提取或翻译
    HOOK_FILES = {
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
    INTERNAL_TL_DIRS = {"_filtered_suspicious"}

    COMMENT_PATTERN = re.compile(r'#\s*game/(.+?):(\d+)', re.IGNORECASE)

    def _parse_tl_directory(self, project: Path, tl_name: str) -> List[Dict]:
        tl_dir = project / "game" / "tl" / tl_name
        if not tl_dir.exists():
            return []

        entries: List[Dict] = []
        for tl_file in sorted(tl_dir.rglob("*.rpy")):
            try:
                rel_parts = [part.lower() for part in tl_file.relative_to(tl_dir).parts[:-1]]
                if any(part in self.INTERNAL_TL_DIRS for part in rel_parts):
                    continue
            except Exception:
                pass
            if self._is_builtin_ui_file(tl_file):
                self.logger.debug(f"跳过内置 UI 文件: {tl_file}")
                continue
            # 跳过工具生成的钩子文件
            if tl_file.name in self.HOOK_FILES:
                self.logger.debug(f"跳过钩子文件: {tl_file}")
                continue

            rel = tl_file.relative_to(project / "game" / "tl" / tl_name).as_posix()
            file_entries = self._parse_tl_file_ast(tl_file, rel, tl_name)
            if file_entries is None:
                file_entries = self._parse_tl_file_legacy(tl_file, rel, tl_name)
            entries.extend(file_entries)

        self.logger.info(f"解析 tl/{tl_name}，共 {len(entries)} 条记录")
        return entries

    def _parse_tl_file_ast(self, tl_file: Path, rel: str, tl_name: str) -> List[Dict] | None:
        """使用 AST 解析单个 tl 文件，失败返回 None。"""
        try:
            text = tl_file.read_text(encoding="utf-8", errors="ignore")
        except Exception as exc:
            self.logger.warning(f"读取翻译文件失败 {tl_file}: {exc}")
            return []

        try:
            lines = text.splitlines()
            doc = parse_tl_document(lines)
            extractor = RenpyTlItemExtractor()
            items = extractor.extract(doc, rel)
            if not items:
                return []

            meta_by_line = self._collect_meta_by_line(doc)
            entries: List[Dict] = []
            for item in items:
                src = item.get_src()
                if self.should_skip_text(src):
                    continue

                extra = item.get_extra_field()
                extra_dict = extra if isinstance(extra, dict) else {}
                renpy = extra_dict.get("renpy", {}) if isinstance(extra_dict.get("renpy"), dict) else {}
                block = renpy.get("block", {}) if isinstance(renpy.get("block"), dict) else {}
                label = block.get("label") if isinstance(block.get("label"), str) else ""
                lang = block.get("lang") if isinstance(block.get("lang"), str) else ""
                if tl_name and lang and lang != tl_name:
                    continue
                kind = str(block.get("kind") or "")
                entry_type = "strings" if kind == "STRINGS" else "dialogue"

                template_line = item.get_row()
                source_file, source_line = meta_by_line.get(template_line, (None, None))

                entries.append(
                    {
                        "file": rel,
                        "line": template_line,
                        "identifier": label,
                        "original": src,
                        "translation": item.get_dst(),
                        "source_file": source_file,
                        "source_line": source_line,
                        "type": entry_type,
                    }
                )
            return entries
        except Exception:
            return None

    def _collect_meta_by_line(self, doc) -> dict[int, tuple[str | None, int | None]]:
        """根据 META 注释收集源文件定位信息（按模板行号映射）。"""
        pattern = re.compile(r"^game/(.+?):(\d+)$")
        meta_by_line: dict[int, tuple[str | None, int | None]] = {}
        for block in doc.blocks:
            last_meta: tuple[str | None, int | None] = (None, None)
            for stmt in block.statements:
                if stmt.stmt_kind == TlStmtKind.META:
                    content = stmt.code.strip()
                    match = pattern.match(content)
                    if match:
                        captured_path = match.group(1).replace("\\", "/")
                        if captured_path.startswith("game/"):
                            captured_path = captured_path[5:]
                        try:
                            captured_line = int(match.group(2))
                        except ValueError:
                            captured_line = None
                        last_meta = (captured_path, captured_line)
                    continue

                if stmt.stmt_kind == TlStmtKind.TEMPLATE and last_meta[0] is not None:
                    meta_by_line.setdefault(stmt.line_no, last_meta)
        return meta_by_line

    def _parse_tl_file_legacy(self, tl_file: Path, rel: str, tl_name: str) -> List[Dict]:
        """保留旧正则解析逻辑，作为 AST 失败的回退路径。"""
        try:
            lines = tl_file.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception as exc:
            self.logger.warning(f"读取翻译文件失败 {tl_file}: {exc}")
            return []

        entries: List[Dict] = []
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
        runtime_data: Dict[str, Dict[str, List[List[Any]]]],
        generate_empty: bool,
    ) -> Path:
        tl_dir = project / "game" / "tl" / tl_name
        tl_dir.mkdir(parents=True, exist_ok=True)

        dialogues_by_file = runtime_data.get("dialogues", {}) or {}
        strings_by_file = runtime_data.get("strings", {}) or {}

        for filename in sorted(set(dialogues_by_file) | set(strings_by_file)):
            dialogue_entries = list(dialogues_by_file.get(filename, []) or [])
            string_entries = list(strings_by_file.get(filename, []) or [])
            dialogue_entries.sort(key=lambda item: item[3] if len(item) > 3 else 0)

            if filename.startswith("game/"):
                rel = Path(filename[5:])
            else:
                rel = Path(filename)

            target = (tl_dir / rel).with_suffix(".rpy")
            target.parent.mkdir(parents=True, exist_ok=True)

            existing_lines: List[str] = []
            if target.exists():
                existing_lines = target.read_text(encoding="utf-8", errors="ignore").splitlines()

            existing_ids = self._collect_existing_dialogue_ids(existing_lines, tl_name)
            existing_strings = self._collect_existing_string_originals(existing_lines)
            append_lines: List[str] = []

            if not existing_lines:
                append_lines.extend(
                    [
                        "# Generated by RenpyBox runtime extract",
                        f"# Source: {filename}",
                        "",
                    ]
                )

            for identifier, who, what, linenumber in dialogue_entries:
                if identifier in existing_ids:
                    continue
                existing_ids.add(identifier)

                who_prefix = f"{who} " if who else ""
                encoded = encode_say_string(str(what)) if what is not None else ""
                append_lines.append(f"# game/{filename}:{linenumber}")
                append_lines.append(f"translate {tl_name} {identifier}:")
                append_lines.append("")
                append_lines.append(f"    # {who_prefix}\"{encoded}\"")
                if generate_empty:
                    append_lines.append(f"    {who_prefix}\"\"")
                else:
                    append_lines.append(f"    {who_prefix}\"{encoded}\"")
                append_lines.append("")

            pending_strings: List[tuple[str, str]] = []
            for original, translation in string_entries:
                if original in existing_strings:
                    continue
                existing_strings.add(original)
                if generate_empty:
                    pending_strings.append((original, ""))
                else:
                    pending_strings.append((original, translation if translation is not None else original))

            if pending_strings:
                append_lines.append(f"translate {tl_name} strings:")
                append_lines.append("")
                for original, translation in pending_strings:
                    append_lines.append(f'    old "{escape_tl_string(str(original))}"')
                    append_lines.append(f'    new "{escape_tl_string(str(translation))}"')
                    append_lines.append("")

            if not append_lines:
                continue

            with target.open("a", encoding="utf-8", newline="\n") as writer:
                if existing_lines:
                    writer.write("\n")
                    if existing_lines[-1].strip():
                        writer.write("\n")
                writer.write("\n".join(append_lines).rstrip() + "\n")

        return tl_dir

    def _collect_existing_dialogue_ids(self, lines: List[str], tl_name: str) -> set[str]:
        existing_ids: set[str] = set()
        marker = f"translate {tl_name} "
        for line in lines:
            if not line.startswith(marker):
                continue
            identifier = line[len(marker):].rstrip(":").strip()
            if identifier and identifier != "strings":
                existing_ids.add(identifier)
        return existing_ids

    def _collect_existing_string_originals(self, lines: List[str]) -> set[str]:
        originals: set[str] = set()
        for line in lines:
            stripped = line.strip()
            if not stripped.startswith("old "):
                continue
            extracted = self._extract_quoted(stripped)
            if extracted != "":
                originals.add(extracted)
        return originals

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
