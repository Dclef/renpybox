# -*- coding: utf-8 -*-
"""MaSuiteRunner - 封装“翻译套件”导出流程，供 UI 调用。

功能：
- 可选执行官方抽取（默认关闭）
- 加载禁翻表与已有翻译，用于过滤/回填
- 调用 MaExtractor 生成 Excel 与终极结构文件
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Optional, Tuple

from base.LogManager import LogManager
from module.Config import Config
from module.Extract.MaExtractor import MaExtractor, MaExtractorResult
from module.Extract.RenpyExtractor import RenpyExtractor
from module.Extract.EmojiReplacer import generate_emoji_replacement_sheets


class MaSuiteRunner:
    """面向 UI 的导出入口。"""

    OLD_LINE_RE = re.compile(r'^\s*old\s+(["\'])(?P<text>(?:\\.|(?!\1).)*?)\1\s*$', re.MULTILINE)
    NEW_LINE_RE = re.compile(r'^\s*new\s+(["\'])(?P<text>(?:\\.|(?!\1).)*?)\1\s*$', re.MULTILINE)

    def __init__(self, logger: Optional[LogManager] = None, renpy_extractor: Optional[RenpyExtractor] = None) -> None:
        self.logger = logger or LogManager.get()
        self.renpy_extractor = renpy_extractor or RenpyExtractor()

    def run(
        self,
        target_path: str | Path,
        tl_name: str,
        *,
        use_official: bool = False,
        exe_path: str | Path | None = None,
        gen_emoji: bool = False,
    ) -> Optional[MaExtractorResult]:
        """执行导出流程。

        Args:
            target_path: 游戏目录 / game 目录 / exe 路径
            tl_name: tl 语言名称
            use_official: 是否先跑一次官方抽取
            exe_path: 指定 exe（可空，自动寻找）
            gen_emoji: 是否生成 Emoji 替换表
        """
        project_root, auto_exe = self._resolve_project_root(target_path)
        config = Config().load()

        # 可选官方抽取
        if use_official:
            exe = self._pick_exe(exe_path, auto_exe, project_root)
            if exe is None:
                raise FileNotFoundError("开启官方抽取但未找到可执行文件，请手动选择 exe")
            self.logger.info(f"开始官方抽取: {exe}")
            self.renpy_extractor.official_extract(str(exe), tl_name, generate_empty=False, force=True)

        tl_dir = project_root / "game" / "tl" / tl_name
        preserve_set = self._load_preserve_set(config)
        existing_translations: Dict[str, str] = {}
        if tl_dir.exists():
            existing_translations = self._get_existing_translations(tl_dir)
        else:
            self.logger.info("未找到 tl 目录，跳过已有翻译回填，仅导出终极结构")

        exporter = MaExtractor(self.logger)
        result = exporter.run(project_root, tl_name, preserve_set, existing_translations, config)

        if result and gen_emoji:
            tl_dir = project_root / "game" / "tl" / tl_name
            emoji_dir = project_root / "translate" / "4_Emoji替换表"
            total, pre_path, post_path = generate_emoji_replacement_sheets(tl_dir, emoji_dir)
            result.emoji_replacements = total
            result.emoji_output_dir = emoji_dir
            self.logger.info(
                "生成 Emoji 替换表: %s 条 (%s, %s)",
                total,
                pre_path,
                post_path,
            )

        return result

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _resolve_project_root(self, target: str | Path) -> Tuple[Path, Optional[Path]]:
        path = Path(target).expanduser().resolve()
        exe_path: Optional[Path] = None

        base = path
        if path.is_file():
            exe_path = path
            base = path.parent

        if base.name.lower() == "game":
            base = base.parent

        game_dir = base / "game"
        if not game_dir.exists():
            raise FileNotFoundError(f"未找到 game 目录: {game_dir}")

        return base, exe_path

    def _pick_exe(
        self,
        explicit: str | Path | None,
        auto: Path | None,
        project_root: Path,
    ) -> Optional[Path]:
        if explicit:
            candidate = Path(explicit).expanduser().resolve()
            if candidate.exists():
                return candidate
        if auto and auto.exists():
            return auto
        return self._auto_find_exe(project_root)

    def _auto_find_exe(self, root: Path) -> Optional[Path]:
        for pattern in ("*.exe", "*.py"):
            candidates = [p for p in root.glob(pattern) if p.is_file()]
            if candidates:
                candidates.sort(key=lambda p: p.stat().st_size if p.exists() else 0, reverse=True)
                return candidates[0]
        return None

    def _load_preserve_set(self, config: Config) -> set[str]:
        """加载禁翻表集合（与 UnifiedExtractor 同步）。"""
        try:
            preserve_set = set()
            if config.text_preserve_enable and config.text_preserve_data:
                for item in config.text_preserve_data:
                    if isinstance(item, dict):
                        src = item.get("src", "").strip()
                        if src:
                            preserve_set.add(src)
                    elif isinstance(item, str) and item.strip():
                        preserve_set.add(item.strip())
            return preserve_set
        except Exception:
            return set()

    def _get_existing_translations(self, tl_dir: Path) -> Dict[str, str]:
        """提取 tl 中已翻译的 old/new 对，用于回填与过滤。"""
        translations: Dict[str, str] = {}
        if not tl_dir.exists():
            return translations

        for rpy_file in tl_dir.rglob("*.rpy"):
            try:
                lines = rpy_file.read_text(encoding="utf-8", errors="replace").split("\n")
            except Exception:
                continue

            i = 0
            while i < len(lines):
                line = lines[i]
                old_match = self.OLD_LINE_RE.match(line)
                if old_match:
                    old_text = old_match.group("text")
                    j = i + 1
                    while j < len(lines):
                        probe = lines[j].strip()
                        if not probe or probe.startswith("#"):
                            j += 1
                            continue
                        break

                    if j < len(lines):
                        new_line = lines[j]
                        new_match = self.NEW_LINE_RE.match(new_line)
                        if new_match:
                            new_text = new_match.group("text")
                            if new_text and new_text != old_text:
                                old_clean = old_text.replace('\\"', '"').replace("\\'", "'")
                                new_clean = new_text.replace('\\"', '"').replace("\\'", "'")
                                translations[old_clean] = new_clean
                            i = j
                i += 1

        return translations


__all__ = ["MaSuiteRunner"]
