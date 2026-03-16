"""RPA pack/unpack helper.

Notes:
- 解包优先使用外部工具：游戏自带 python + unren_rpatool（UnRen 风格），
  或系统/unpacked 内置的 unrpa/rpatool。
- 打包使用 rpatool，采用“先创建再逐个追加”的方式以兼容 Windows 命令行长度限制。
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
import sys
from typing import Iterator, List, Tuple
import re

from base.LogManager import LogManager
from base.PathHelper import get_resource_path
from module.Tool.rpatool_core import RenPyArchive


class Packer:
    # 记录当前会话内各游戏目录最稳定的 UnRen 版本，避免同一项目重复先撞错脚本。
    UNREN_COMPAT_CACHE: dict[str, str] = {}

    def __init__(self) -> None:
        self.logger = LogManager.get()
        # Base project directory (oldcatporject/)
        self.base_dir = Path(__file__).resolve().parents[2]
        self.root_dir = self.base_dir.parent
        self.resource_dir = Path(get_resource_path("resource"))

    def _get_unren_cache_key(self, root_dir: Path) -> str:
        return str(root_dir.resolve()).replace("\\", "/").lower()

    def _get_cached_unren_preference(self, root_dir: Path) -> str | None:
        return __class__.UNREN_COMPAT_CACHE.get(self._get_unren_cache_key(root_dir))

    def _set_cached_unren_preference(self, root_dir: Path, unren_bat: Path) -> None:
        name = unren_bat.name.lower()
        if "legacy" in name:
            value = "legacy"
        elif "current" in name:
            value = "current"
        else:
            return
        __class__.UNREN_COMPAT_CACHE[self._get_unren_cache_key(root_dir)] = value

    def _creationflags_no_window(self) -> int:
        if os.name != "nt":
            return 0
        try:
            return subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
        except Exception:
            return 0

    def _format_progress_bar(self, current: int, total: int, width: int = 20) -> str:
        if total <= 0:
            return f"[{'-' * width}] {current}/0"
        filled = int(width * current / total)
        percent = int(current * 100 / total)
        return f"[{'#' * filled}{'-' * (width - filled)}] {current}/{total} ({percent}%)"

    def _get_game_python(self, game_root_dir: Path) -> Path | None:
        try:
            from utils.call_game_python import get_python_path_from_game_dir
        except Exception:
            return None

        root = str(game_root_dir.resolve()).replace("\\", "/")
        if not root.endswith("/"):
            root += "/"

        python_path = get_python_path_from_game_dir(root)
        if not python_path:
            return None

        python_exe = Path(python_path)
        return python_exe if python_exe.exists() else None

    def _which_unrpa(self) -> str | None:
        return shutil.which("unrpa")

    def _local_rpatool(self) -> Path | None:
        # 优先使用 PathHelper 定位（支持 PyInstaller 打包后的路径）
        rpatool_path = get_resource_path("resource", "tools", "rpatool")
        if Path(rpatool_path).exists():
            self.logger.debug(f"找到 rpatool: {rpatool_path}")
            return Path(rpatool_path)
        
        # 兜底：尝试旧的路径查找方式
        candidates = [
            self.base_dir / "resource" / "tools" / "rpatool",
            self.root_dir / "renpy-translator-main" / "rpatool",
        ]
        for p in candidates:
            if p.exists():
                self.logger.debug(f"找到 rpatool (fallback): {p}")
                return p
        
        self.logger.warning("未找到 rpatool")
        return None

    def _read_renpy_version(self, root_dir: Path) -> str | None:
        version_file = root_dir / "renpy" / "version.txt"
        if not version_file.is_file():
            return None
        try:
            text = version_file.read_text(encoding="utf-8", errors="ignore").strip()
        except Exception:
            try:
                text = version_file.read_text(errors="ignore").strip()
            except Exception:
                return None
        if not text:
            return None
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        return lines[0] if lines else None

    def _detect_renpy_major(self, root_dir: Path) -> int | None:
        version = self._read_renpy_version(root_dir)
        if version:
            match = re.search(r"(\d+)(?:\.\d+)?", version)
            if match:
                try:
                    return int(match.group(1))
                except Exception:
                    pass

        # version.txt 缺失时，退回到游戏内置 Python 版本做推断：
        # Python 2 基本对应 Ren'Py 7，Python 3 基本对应 Ren'Py 8。
        python_major = self._detect_embedded_python_major(root_dir)
        if python_major == 2:
            return 7
        if python_major and python_major >= 3:
            return 8
        return None

    def _detect_embedded_python_major(self, root_dir: Path) -> int | None:
        python_exe = self._get_game_python(root_dir)
        if not python_exe:
            return None

        python_path = str(python_exe).replace("\\", "/").lower()
        if "/py2-" in python_path or "python2" in python_path:
            return 2
        if "/py3-" in python_path or "python3" in python_path:
            return 3

        try:
            result = subprocess.run(
                [str(python_exe), "-c", "import sys; print(sys.version_info[0])"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=5,
                creationflags=self._creationflags_no_window(),
            )
            if result.returncode == 0:
                value = (result.stdout or "").strip()
                if value in ("2", "3"):
                    return int(value)
        except Exception as exc:
            self.logger.debug(f"检测游戏内置 Python 主版本失败: {exc}")

        return None

    def _select_unren_bats(self, root_dir: Path) -> tuple[list[Path], int | None]:
        major = self._detect_renpy_major(root_dir)
        legacy_res = Path(get_resource_path("resource", "UnRen-legacy.bat"))
        current_res = Path(get_resource_path("resource", "UnRen-current.bat"))
        legacy = legacy_res if legacy_res.exists() else (self.base_dir / "dist" / "UnRen-legacy.bat")
        current = current_res if current_res.exists() else (self.base_dir / "dist" / "UnRen-current.bat")
        candidates: list[Path] = []
        cached = self._get_cached_unren_preference(root_dir)

        def add_candidate(path: Path) -> None:
            if path.exists() and path not in candidates:
                candidates.append(path)

        if cached == "legacy":
            add_candidate(legacy)
            add_candidate(current)
            return candidates, major

        if cached == "current":
            add_candidate(current)
            add_candidate(legacy)
            return candidates, major

        if major is None:
            # 真正无法识别时，先尝试 legacy，再尝试 current。
            # 对 Ren'Py 7 项目更稳妥，同时保留 8 的自动兜底。
            add_candidate(legacy)
            add_candidate(current)
            return candidates, major

        if major >= 8:
            add_candidate(current)
            add_candidate(legacy)
            return candidates, major

        add_candidate(legacy)
        add_candidate(current)
        return candidates, major

    def _get_unren_script_version_label(self, unren_bat: Path, major: int | None) -> str:
        """返回更准确的 UnRen 版本标签。"""
        name = unren_bat.name.lower()

        if major is not None:
            return f"游戏 Ren'Py {major}"

        if "current" in name:
            return "Ren'Py 8+"
        if "legacy" in name:
            return "Ren'Py <= 7"

        return "Ren'Py 未知版本"

    def _run_unren_bat(
        self,
        unren_bat: Path,
        game_root: Path,
        *,
        options: str,
        lang: str,
        timeout_s: int | None,
    ) -> subprocess.CompletedProcess[str] | None:
        if os.name != "nt":
            return None
        if not unren_bat.is_file():
            return None
        try:
            return subprocess.run(
                ["cmd.exe", "/c", str(unren_bat), str(game_root), lang],
                cwd=str(game_root),
                input=f"{options}\n",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=timeout_s,
                creationflags=self._creationflags_no_window(),
            )
        except Exception as exc:
            self.logger.warning(f"UnRen 启动失败: {exc}")
            return None

    def unpack_all_unren_bat(
        self,
        game_dir: str,
        *,
        lang: str = "zh",
        options: str = "6x",
        purpose: str = "解包",
        timeout_s: int | None = None,
    ) -> Tuple[bool, List[str]]:
        """Fallback via UnRen-legacy/current.bat (no window, no prompts)."""
        game_path = Path(game_dir).resolve()
        if not game_path.exists() or not game_path.is_dir():
            raise FileNotFoundError(f"目录不存在: {game_path}")

        game_root = game_path.parent
        unren_bats, major = self._select_unren_bats(game_root)
        if not unren_bats:
            return False, ["UnRen 脚本不可用"]

        cached = self._get_cached_unren_preference(game_root)
        if cached is not None:
            self.logger.info(f"命中 UnRen 兼容缓存: {cached}")

        last_lines: list[str] = []
        for index, unren_bat in enumerate(unren_bats):
            version_label = self._get_unren_script_version_label(unren_bat, major)
            if cached is not None and index == 0:
                version_label = f"{version_label}, 兼容缓存"
            if index == 0:
                self.logger.info(f"UnRen {purpose}: {unren_bat.name} ({version_label})")
            else:
                self.logger.warning(f"UnRen {purpose} 重试: {unren_bat.name} ({version_label})")

            result = self._run_unren_bat(
                unren_bat,
                game_root,
                options=options,
                lang=lang,
                timeout_s=timeout_s,
            )
            if result is None:
                last_lines = ["UnRen 启动失败"]
                continue

            output = (result.stdout or "").strip()
            lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
            detected_version = None
            if lines:
                ansi_re = re.compile(r"\x1b\[[0-9;]*m")
                for line in lines:
                    clean = ansi_re.sub("", line)
                    m = re.search(r"Ren'Py version found:\s*(\S+)", clean)
                    if not m:
                        m = re.search(r"检测到 Ren'Py 版本：\s*(\S+)", clean)
                    if m:
                        detected_version = m.group(1)
                        break
            if detected_version:
                self.logger.info(f"UnRen 检测到 Ren'Py 版本: {detected_version}")

            ok = result.returncode == 0
            if not ok and output:
                success_markers = ("Operation completed.", "操作完成。", "操作完成")
                if any(marker in output for marker in success_markers):
                    ok = True

            if ok:
                self._set_cached_unren_preference(game_root, unren_bat)
                return True, lines

            last_lines = lines
            if index + 1 < len(unren_bats):
                next_bat = unren_bats[index + 1]
                self.logger.warning(f"{unren_bat.name} 执行失败，准备切换到 {next_bat.name}")

        return False, last_lines

    def unpack_all_unren(
        self,
        game_dir: str,
        *,
        script_only: bool = False,
        remove_archives: bool = False,
    ) -> Tuple[int, List[str]]:
        """
        Unpack archives using the game's own python + Ren'Py loader (UnRen style).

        This does not launch the game process and can handle encrypted archives
        in many cases (because it relies on Ren'Py's loader).
        """
        game_path = Path(game_dir).resolve()
        if not game_path.exists():
            raise FileNotFoundError(f"目录不存在: {game_path}")
        if not game_path.is_dir():
            raise NotADirectoryError(f"不是目录: {game_path}")

        game_root = game_path.parent
        python_exe = self._get_game_python(game_root)
        if not python_exe:
            raise FileNotFoundError("无法定位游戏自带 python.exe（请确认选择的是 game 目录，且上级目录存在 lib/.../python.exe）")

        script_path = Path(get_resource_path("resource", "tools", "unren_rpatool.py"))
        if not script_path.exists():
            raise FileNotFoundError(f"缺少资源: {script_path}")

        cmd = [str(python_exe), str(script_path)]
        if remove_archives:
            cmd.append("-r")
        if script_only:
            cmd.append("--script-only")
        cmd.append(str(game_path))

        self.logger.info(f"UnRen 直接解包: {game_path}")

        archive_candidates = self.find_rpa_files(str(game_path))
        total_archives = len(archive_candidates)

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        lines: List[str] = []
        unpacked = 0
        result = None
        try:
            result = subprocess.Popen(
                cmd,
                cwd=str(game_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="ignore",
                env=env,
                creationflags=self._creationflags_no_window(),
            )

            if result.stdout:
                for raw_line in result.stdout:
                    line = raw_line.strip()
                    if not line:
                        continue
                    lines.append(line)

                    if re.search(r"(?i)\bUnpacking\b", line):
                        unpacked += 1
                        bar = self._format_progress_bar(unpacked, total_archives) if total_archives else ""
                        if bar:
                            self.logger.info(f"进度 {bar} {line}")
                        else:
                            self.logger.info(f"{line} (已解包 {unpacked})")
                    elif "There are no archives" in line:
                        self.logger.info("未找到归档文件")
            if result:
                result.wait()
        finally:
            # 清理 UnRen 执行后可能产生的缓存目录（与 UnRen 行为一致）
            try:
                pycache_dir = game_path / "__pycache__"
                if pycache_dir.exists() and pycache_dir.is_dir():
                    shutil.rmtree(pycache_dir, ignore_errors=True)
            except Exception:
                pass

        output = "\n".join(lines)
        if unpacked == 0 and output:
            unpacked = len(re.findall(r"(?i)\bUnpacking\b", output))

        if not result or result.returncode != 0:
            tail = "\n".join(lines[-50:]) if lines else ""
            code = getattr(result, "returncode", None)
            raise RuntimeError(tail or f"unren_rpatool exited with code {code}")

        if total_archives:
            bar = self._format_progress_bar(unpacked, total_archives)
            self.logger.info(f"解包完成 {bar}")
        else:
            self.logger.info(f"UnRen 直接解包完成: {unpacked} 个归档文件")

        return unpacked, lines

    def find_rpa_files(self, game_dir: str) -> List[Path]:
        p = Path(game_dir)
        return sorted(p.glob("*.rpa"))

    def unpack_all(
        self,
        game_dir: str,
        output_root: str | None = None,
        script_only: bool | None = None,
        overwrite_existing: bool | None = None,
        max_threads: int | None = None,
    ) -> Tuple[int, List[str]]:
        """
        Unpack all .rpa files in the given `game_dir`.

        Strategy:
        - Prefer external tools when possible: `unrpa` CLI or bundled `rpatool`.

        Returns:
            (unpacked_count, messages)
        """
        unrpa = self._which_unrpa()
        rpatool = self._local_rpatool()
        msgs: List[str] = []

        files = self.find_rpa_files(game_dir)

        unpacked = 0
        if not (unrpa or rpatool):
            msgs.append("未检测到 unrpa 或 rpatool，无法解包。")
            return unpacked, msgs

        if not files:
            msg = "未找到任何 .rpa 文件"
            self.logger.info(msg)
            msgs.append(msg)
            return unpacked, msgs

        total_files = len(files)
        self.logger.info(f"找到 {total_files} 个 RPA 文件，开始解包")

        for index, rpa in enumerate(files, start=1):
            out_dir = Path(output_root) if output_root else (Path(game_dir) / "unpacked_rpa" / rpa.stem)
            out_dir.mkdir(parents=True, exist_ok=True)
            try:
                bar = self._format_progress_bar(index, total_files)
                self.logger.info(f"进度 {bar} 解包: {rpa.name}")
                if unrpa:
                    cmd = [unrpa, "-mp", str(out_dir), str(rpa)]
                    subprocess.run(
                        cmd,
                        check=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        creationflags=self._creationflags_no_window(),
                    )
                else:
                    cmd = [sys.executable, str(rpatool), "-x", "-o", str(out_dir), str(rpa)]
                    subprocess.run(
                        cmd,
                        check=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        creationflags=self._creationflags_no_window(),
                    )
                unpacked += 1
                self.logger.info(f"完成: {rpa.name}")
            except subprocess.CalledProcessError as e:
                output = e.stdout.decode(errors='ignore') if getattr(e, 'stdout', None) else str(e)
                msg = f"解包失败 {rpa}: {output.strip()}"
                msgs.append(msg)
                self.logger.error(msg)

        self.logger.info(f"解包完成: {unpacked}/{total_files}")
        return unpacked, msgs

    def pack_from_dir(
        self,
        source_dir: str,
        out_rpa: str,
        progress_callback=None,
        stop_check=None,
    ) -> None:
        """
        Pack a directory back to .rpa using rpatool_core (direct python call).

        Args:
            source_dir: Directory to pack
            out_rpa: Output .rpa file path
            progress_callback: Optional callback(current, total, filename) for progress
            stop_check: Optional callable returning True to abort
        """
        # Import locally to avoid top-level dependency issues and ensure it's loaded when needed
        # from module.Tool.rpatool_core import RenPyArchive

        # Handle long paths on Windows for source directory
        abs_source = os.path.abspath(source_dir)
        if os.name == 'nt' and not abs_source.startswith('\\\\?\\'):
            abs_source = '\\\\?\\' + abs_source
            
        src = Path(abs_source)
        
        # Fallback check if the long path somehow fails or original was intended
        if not src.exists():
             # Try original path just in case
             src = Path(source_dir)
             if not src.exists():
                raise FileNotFoundError(f"源目录不存在: {source_dir}")

        if progress_callback:
            progress_callback(0, 0, "正在扫描文件...")

        # Resolve output path early to exclude it from scanning
        out_path_resolved = Path(out_rpa).resolve()
        # Handle long paths on Windows for output file check
        if os.name == 'nt' and not str(out_path_resolved).startswith('\\\\?\\'):
             # We use the long path version for comparison if the system uses it, 
             # but pathlib resolution might be tricky. 
             # Simplest is to compare resolved paths.
             pass

        files: List[Path] = []
        try:
            for entry in src.rglob('*'):
                if stop_check and stop_check():
                    raise RuntimeError("打包已取消")
                if entry.is_file():
                    # Exclude the output file itself if it's inside the source directory
                    if entry.resolve() == out_path_resolved:
                        continue

                    files.append(entry)
                    if progress_callback and len(files) % 200 == 0:
                        progress_callback(0, 0, f"已发现 {len(files)} 个文件...")
        except RuntimeError:
            raise
        except Exception as scan_err:
            raise RuntimeError(f"扫描目录失败: {scan_err}")

        if not files:
            raise RuntimeError("源目录为空，未找到可打包的文件")

        total_files = len(files)
        if progress_callback:
            progress_callback(0, total_files, f"共找到 {total_files} 个文件，开始打包...")
        self.logger.info(f"打包 RPA: {source_dir} -> {out_rpa} (共 {total_files} 个文件)")

        out_path = Path(out_rpa).resolve()
        # Handle long paths on Windows for output file
        if os.name == 'nt' and not str(out_path).startswith('\\\\?\\'):
            out_path = Path('\\\\?\\' + str(out_path))

        out_path.parent.mkdir(parents=True, exist_ok=True)
        if out_path.exists():
            out_path.unlink()

        # Create archive object (RPAv3 default)
        archive = RenPyArchive(version=3, verbose=False)

        # 自动检测是否需要保留根目录名
        # 只要源目录名不是 'game'，就默认保留目录名作为前缀
        # 这样打包 'images' 会生成 'images/xxx'，打包 'videos' 会生成 'videos/xxx'
        src_name = src.name
        should_prepend_root = src_name.lower() != 'game'

        processed = 0
        for p in files:
            if stop_check and stop_check():
                self.logger.info("打包被用户取消")
                if out_path.exists():
                    out_path.unlink()
                raise RuntimeError("打包已取消")

            rel = str(p.relative_to(src)).replace('\\', '/')
            
            # 如果需要保留根目录名，则添加前缀
            if should_prepend_root:
                rel = f"{src_name}/{rel}"

            # Add file path to archive (lazy load via modified rpatool_core)
            try:
                archive.add_file_path(rel, str(p))
            except Exception as e:
                self.logger.error(f"添加文件失败 {rel}: {e}")
                raise

            processed += 1
            if progress_callback and processed % 100 == 0:
                progress_callback(processed, total_files, rel)

        self.logger.info("正在写入 RPA 文件...")
        if progress_callback:
            # 计算预估大小
            total_size_mb = sum(p.stat().st_size for p in files) / (1024 * 1024)
            progress_callback(total_files, total_files, f"正在写入 RPA ({total_size_mb:.1f} MB)，请稍候...")

        try:
            archive.save(str(out_path))
        except Exception as e:
            if out_path.exists():
                out_path.unlink()
            raise RuntimeError(f"保存 RPA 失败: {e}")

        self.logger.info(f"RPA 打包完成: {out_rpa}")




