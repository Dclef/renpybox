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
    def __init__(self) -> None:
        self.logger = LogManager.get()
        # Base project directory (oldcatporject/)
        self.base_dir = Path(__file__).resolve().parents[2]
        self.root_dir = self.base_dir.parent
        self.resource_dir = Path(get_resource_path("resource"))

    def _creationflags_no_window(self) -> int:
        if os.name != "nt":
            return 0
        try:
            return subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
        except Exception:
            return 0

    def _run_unren_forall(
        self,
        game_root: Path,
        *,
        options: str,
        lang: str = "zh",
        timeout_s: int | None = None,
    ) -> subprocess.CompletedProcess[str] | None:
        """Run bundled UnRen-forall.bat in headless automation mode."""
        if os.name != "nt":
            return None
        unren_bat = Path(get_resource_path("resource", "UnRen-forall.bat"))
        if not unren_bat.is_file():
            return None

        env = os.environ.copy()
        env["UNREN_AUTORUN"] = options
        env["UNREN_NO_PAUSE"] = "1"
        env["UNREN_NO_UPDATE"] = "1"

        try:
            return subprocess.run(
                ["cmd.exe", "/c", str(unren_bat), str(game_root), lang],
                cwd=str(game_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="ignore",
                env=env,
                timeout=timeout_s,
                creationflags=self._creationflags_no_window(),
            )
        except Exception as exc:
            self.logger.warning(f"UnRen-forall 运行失败: {exc}")
            return None

    def unpack_all_unren_forall(
        self,
        game_dir: str,
        *,
        lang: str = "zh",
        timeout_s: int | None = None,
        use_alternative: bool = False,
    ) -> tuple[bool, list[str]]:
        """Fallback unpack via UnRen-forall.bat (no window, no prompts)."""
        game_path = Path(game_dir).resolve()
        if not game_path.exists() or not game_path.is_dir():
            raise FileNotFoundError(f"目录不存在: {game_path}")

        game_root = game_path.parent
        options = "7x" if use_alternative else "1x"
        result = self._run_unren_forall(game_root, options=options, lang=lang, timeout_s=timeout_s)
        if result is None:
            return False, ["UnRen-forall 不可用或启动失败"]
        output = (result.stdout or "").strip()
        lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
        return result.returncode == 0, lines

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
        result = None
        try:
            result = subprocess.run(
                cmd,
                cwd=str(game_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=self._creationflags_no_window(),
            )
        finally:
            # 清理 UnRen 执行后可能产生的缓存目录（与 UnRen-forall.bat 行为一致）
            try:
                pycache_dir = game_path / "__pycache__"
                if pycache_dir.exists() and pycache_dir.is_dir():
                    shutil.rmtree(pycache_dir, ignore_errors=True)
            except Exception:
                pass

        raw = (getattr(result, "stdout", None) or b"") if result else b""
        try:
            output = raw.decode("utf-8", errors="ignore")
        except Exception:
            output = raw.decode(errors="ignore")

        lines = [line.strip() for line in output.splitlines() if line.strip()]
        if not result or result.returncode != 0:
            tail = "\n".join(lines[-50:]) if lines else ""
            code = getattr(result, "returncode", None)
            raise RuntimeError(tail or f"unren_rpatool exited with code {code}")

        unpacked = len(re.findall(r"(?i)\\bUnpacking\\b", output))
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

        for rpa in files:
            out_dir = Path(output_root) if output_root else (Path(game_dir) / "unpacked_rpa" / rpa.stem)
            out_dir.mkdir(parents=True, exist_ok=True)
            try:
                self.logger.info(f"解包: {rpa} -> {out_dir}")
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
            except subprocess.CalledProcessError as e:
                output = e.stdout.decode(errors='ignore') if getattr(e, 'stdout', None) else str(e)
                msg = f"解包失败 {rpa}: {output.strip()}"
                msgs.append(msg)
                self.logger.error(msg)

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
