"""
RPA pack/unpack helper.

Notes:
- 解包优先通过注入 `hook_unrpa.rpy` 并启动游戏来导出文件，可选使用外部工具
  (`unrpa` 或 `rpatool`) 作为兜底。
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
        self.hooks_dir = self.resource_dir / "hooks"

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
        *,
        prefer_hook: bool = True,
        allow_external_fallback: bool = True,
    ) -> Tuple[int, List[str]]:
        """
        Unpack all .rpa files in the given `game_dir`.

        Strategy:
        - Prefer external tools when possible: `unrpa` CLI or bundled `rpatool`.
        - If external tools are not available or fail for all archives, try a
          Ren'Py in-game hook fallback (inject `hook_unrpa.rpy` then attempt to
          locate and launch the game automatically). This mirrors renpy-translator-main.

        Returns:
            (unpacked_count, messages)
        """
        unrpa = self._which_unrpa()
        rpatool = self._local_rpatool()
        msgs: List[str] = []

        files = self.find_rpa_files(game_dir)

        if prefer_hook:
            self.logger.info(f"通过 Hook 解包: {game_dir}")
            try:
                hook_msgs = self._hook_unpack(
                    game_dir,
                    script_only=script_only,
                    overwrite_existing=overwrite_existing,
                    max_threads=max_threads,
                )
                for m in hook_msgs:
                    self.logger.info(m)
                msgs.extend(hook_msgs)
                if files:
                    msgs.append(f"检测到 {len(files)} 个 .rpa，Hook 将在游戏运行时写出文件。")
                    self.logger.info(f"检测到 {len(files)} 个 .rpa，Hook 将在游戏运行时写出文件。")
                else:
                    msgs.append("未检测到 .rpa，但已注入 Hook，可手动运行游戏确认。")
                    self.logger.info("未检测到 .rpa，但已注入 Hook，可手动运行游戏确认。")
                return 0, msgs
            except Exception as hook_err:
                msg = f"Hook 解包失败: {hook_err}"
                msgs.append(msg)
                self.logger.error(msg)
                if not allow_external_fallback:
                    return 0, msgs

        unpacked = 0
        if not (unrpa or rpatool):
            if not prefer_hook:
                msgs.append("未检测到 unrpa 或 rpatool，且未启用 Hook。无法解包。")
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
                    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                else:
                    cmd = [sys.executable, str(rpatool), "-x", "-o", str(out_dir), str(rpa)]
                    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                unpacked += 1
            except subprocess.CalledProcessError as e:
                output = e.stdout.decode(errors='ignore') if getattr(e, 'stdout', None) else str(e)
                msg = f"解包失败 {rpa}: {output.strip()}"
                msgs.append(msg)
                self.logger.error(msg)

        return unpacked, msgs

    def _hook_unpack(
        self,
        game_dir: str,
        *,
        script_only: bool | None,
        overwrite_existing: bool | None,
        max_threads: int | None,
    ) -> List[str]:
        """
        Try to use the in-game hook logic to dump files from RPA.
        Steps:
        - Copy hook_unrpa.rpy into the `game_dir`.
        - Try to locate a sibling .exe to launch the game.
        - Launch the game and wait briefly for a marker file to change.
        This is a best-effort helper to mirror renpy-translator-main behavior.
        """
        msgs: List[str] = []
        hooks_dir = self.hooks_dir
        hook_file = hooks_dir / "hook_unrpa.rpy"
        if not hook_file.exists():
            # Fallback in case resource_dir was mis-resolved
            hook_file = Path(get_resource_path("resource", "hooks", "hook_unrpa.rpy"))
        dest = Path(game_dir) / "hook_unrpa.rpy"
        if not hook_file.exists():
            raise FileNotFoundError(f"缺少资源: {hook_file}")
        # Backup and write with adjusted options
        try:
            text = hook_file.read_text(encoding="utf-8")
            # Adjust options if requested
            if script_only is not None:
                text = re.sub(r"(?m)^\s*SCRIPT_ONLY\s*=\s*(True|False)\s*$",
                              f"    SCRIPT_ONLY = {str(bool(script_only))}", text)
            if overwrite_existing is not None:
                # SKIP_IF_EXIST is True by default; invert overwrite
                skip = not bool(overwrite_existing)
                text = re.sub(r"(?m)^\s*SKIP_IF_EXIST\s*=\s*(True|False)\s*$",
                              f"    SKIP_IF_EXIST = {str(skip)}", text)
            if max_threads is not None and max_threads > 0:
                text = re.sub(r"(?m)^\s*MAX_UNPACK_THREADS\s*=\s*\d+\s*$",
                              f"    MAX_UNPACK_THREADS = {int(max_threads)}", text)
            if dest.exists():
                backup = dest.with_suffix(dest.suffix + ".bak")
                shutil.copy2(dest, backup)
            dest.write_text(text, encoding="utf-8")
            msgs.append(f"已注入 Hook: {dest}")
        except Exception as ie:
            raise RuntimeError(f"复制 Hook 失败: {ie}")

        # Create finish flag under exe dir
        exe_dir = Path(game_dir).parent
        finish_flag = exe_dir / "unpack.finish"
        try:
            finish_flag.write_text("waiting", encoding="utf-8")
            self.logger.debug(f"写入标记文件: {finish_flag}")
        except Exception:
            pass

        # Try to find a candidate exe and launch
        exe_candidates = list(exe_dir.glob("*.exe"))
        if not exe_candidates:
            msgs.append("未找到可执行文件，已仅完成 Hook 注入。请手动启动游戏以触发解包。")
            return msgs

        # Prefer the largest exe (usually the main game exe)
        exe_candidates.sort(key=lambda p: p.stat().st_size if p.exists() else 0, reverse=True)
        exe = exe_candidates[0]
        msgs.append(f"尝试启动游戏: {exe}")
        try:
            subprocess.Popen([str(exe)], cwd=str(exe_dir))
        except Exception as le:
            msgs.append(f"自动启动失败: {le}。请手动运行游戏以触发解包。")
            return msgs

        # We do not hard-block waiting here; renpy-translator uses a UI loop
        # that watches for the flag removal and pid file. We log guidance.
        msgs.append("已启动游戏并注入 Hook。完成后将自动在游戏目录下写出文件。")
        msgs.append("若需要覆盖已存在文件，请修改 hook_unrpa.rpy 中 SKIP_IF_EXIST。")
        return msgs

    def remove_hook_files(self, game_dir: str) -> List[str]:
        """
        删除 game 目录下的 hook 文件（hook_unrpa.rpy, hook_unrpa.rpyc 等）。
        解包完成后应调用此方法清理 hook 文件，防止打包后自动解压。
        
        Returns:
            删除的文件列表
        """
        removed: List[str] = []
        hook_patterns = [
            'hook_unrpa.rpy',
            'hook_unrpa.rpyc',
            'hook_extract.rpy',
            'hook_extract.rpyc',
            'hook_add_change_language_entrance.rpy',
            'hook_add_change_language_entrance.rpyc',
        ]
        game_path = Path(game_dir)
        for pattern in hook_patterns:
            hook_file = game_path / pattern
            if hook_file.exists():
                try:
                    hook_file.unlink()
                    removed.append(str(hook_file))
                    self.logger.info(f"已删除 Hook 文件: {hook_file}")
                except Exception as e:
                    self.logger.warning(f"删除 Hook 文件失败 {hook_file}: {e}")
        return removed

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
        hook_base_names = {
            'hook_unrpa',
            'hook_extract',
            'hook_add_change_language_entrance',
        }
        hook_file_names = {f"{name}.rpy" for name in hook_base_names} | {f"{name}.rpyc" for name in hook_base_names}
        hook_extensions = {'.rpy', '.rpyc'}
        try:
            for entry in src.rglob('*'):
                if stop_check and stop_check():
                    raise RuntimeError("打包已取消")
                if entry.is_file():
                    # Exclude the output file itself if it's inside the source directory
                    if entry.resolve() == out_path_resolved:
                        continue

                    # Exclude hook files
                    entry_name_lower = entry.name.lower()
                    entry_stem_lower = entry.stem.lower()
                    entry_suffix_lower = entry.suffix.lower()
                    if (
                        entry_name_lower in hook_file_names
                        or (entry_stem_lower in hook_base_names and entry_suffix_lower in hook_extensions)
                    ):
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
