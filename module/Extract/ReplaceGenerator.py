"""Utilities for constructing Ren'Py replace_text hooks from extracted data.

**优化后的流程（一键操作）：**
1. 一键生成缺失补丁：
   - 用「正则」扫描源码，得到全量候选文本
   - 读取 tl 目录，得到已抽取覆盖的文本
   - 对比差集 → 自动生成 miss_ready_replace.rpy
2. 翻译 miss_ready_replace.rpy 中的 old/new 对
3. 生成 Replace 钩子：读取 miss_ready_replace.rpy 的已翻译内容，生成 replace_text 脚本
"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import List, Optional, Sequence, Set, Tuple

from base.LogManager import LogManager
from module.Extract.SimpleRpyExtractor import SimpleRpyExtractor
from module.Text.SkipRules import should_skip_text

Pair = Tuple[str, str]

# 文件名（缺失补丁）
MISS_RPY = "miss_ready_replace.rpy"
LEGACY_MISS_TXT = "miss_ready_replace.txt"
MISS_DIR = "miss"
REGEX_CACHE = "regex_extracted.json"  # 正则提取缓存
REGEX_CACHE_VERSION = 2


def _get_miss_candidates(tl_dir: Path) -> List[Path]:
    """Return candidate miss file paths in priority order (new → legacy)."""
    miss_dir = tl_dir / MISS_DIR
    return [
        miss_dir / MISS_RPY,
        tl_dir / MISS_RPY,
        miss_dir / LEGACY_MISS_TXT,
        tl_dir / LEGACY_MISS_TXT,
    ]


def _resolve_miss_path(tl_dir: Path) -> Optional[Path]:
    """Resolve the miss file path if it exists (auto-migrates legacy .txt → .rpy)."""
    for candidate in _get_miss_candidates(tl_dir):
        if not candidate.exists():
            continue

        # Legacy: rename/copy .txt to .rpy so it can be translated by TL tools.
        if candidate.suffix.lower() == ".txt":
            migrated = candidate.with_suffix(".rpy")
            if migrated.exists():
                return migrated

            try:
                candidate.replace(migrated)
                return migrated
            except Exception:
                try:
                    content = candidate.read_text(encoding="utf-8", errors="replace")
                    migrated.write_text(content, encoding="utf-8")
                    return migrated
                except Exception:
                    return candidate

        return candidate

    return None


def _escape_string(value: str) -> str:
    """Escape a Python string literal for inclusion inside double quotes."""
    return (
        value.replace("\\", "\\\\")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "\\n")
        .replace('"', '\\"')
    )


def _get_game_dir(target_path: str | Path) -> Path:
    """获取 game 目录"""
    return SimpleRpyExtractor.get_game_dir(target_path)


# ===================== 正则提取（全量扫描）=====================

def _collect_source_rpy_files(game_dir: Path) -> Tuple[List[Path], int, int]:
    """Collect .rpy files to scan (excluding tl/) and return (files, count, max_mtime_ns)."""
    tl_dir = game_dir / "tl"
    tl_resolved: Optional[Path] = None
    if tl_dir.exists():
        try:
            tl_resolved = tl_dir.resolve()
        except Exception:
            tl_resolved = None

    rpy_files: List[Path] = []
    file_count = 0
    max_mtime_ns = 0

    for dirpath, dirnames, filenames in os.walk(game_dir):
        current = Path(dirpath)
        if tl_resolved is not None:
            try:
                current_resolved = current.resolve()
            except Exception:
                current_resolved = current

            # 跳过 tl 目录（翻译目录）
            if current_resolved == tl_resolved or str(current_resolved).startswith(str(tl_resolved) + os.sep):
                continue

        for filename in filenames:
            if not filename.lower().endswith((".rpy", ".rpym")):
                continue
            p = Path(dirpath) / filename
            # 跳过引擎级公共文件，避免误报
            if p.name.lower() in ("common.rpy", "common.rpym"):
                continue

            rpy_files.append(p)
            file_count += 1
            try:
                max_mtime_ns = max(max_mtime_ns, p.stat().st_mtime_ns)
            except Exception:
                pass

    return rpy_files, file_count, max_mtime_ns


def _try_load_regex_cache(cache_path: Path, *, file_count: int, max_mtime_ns: int) -> Optional[Set[str]]:
    try:
        if not cache_path.exists():
            return None
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        if data.get("version") != REGEX_CACHE_VERSION:
            return None
        if data.get("file_count") != file_count or data.get("max_mtime_ns") != max_mtime_ns:
            return None
        strings = data.get("strings")
        if not isinstance(strings, list):
            return None
        return {str(s) for s in strings if s}
    except Exception:
        return None


def _save_regex_cache(cache_path: Path, *, file_count: int, max_mtime_ns: int, strings: Set[str]) -> None:
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": REGEX_CACHE_VERSION,
            "file_count": file_count,
            "max_mtime_ns": max_mtime_ns,
            "strings": sorted(strings),
        }
        cache_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except Exception:
        return


def _unescape(text: str) -> str:
    """反转义字符串"""
    return (
        text
        .replace('\\"', '"')
        .replace("\\'", "'")
        .replace('\\\\', '\\')
        .replace('\\n', '\n')
        .strip()
    )


def _strip_format_tags(text: str) -> str:
    """去除 Ren'Py 格式标签，如 {b}Iku{/b} → Iku"""
    if not text:
        return ""
    # 去除所有 {xxx} 和 {/xxx} 标签
    cleaned = re.sub(r'\{/?[^}]+\}', '', text)
    return cleaned.strip()


def _is_character_name(text: str) -> bool:
    """判断是否像角色名 - 简单过滤，保留更多候选"""
    if not text:
        return False
    
    # 去掉格式标签
    cleaned = re.sub(r'\{[^}]+\}', '', text).strip()
    if not cleaned:
        return False
    
    # 排除单字符（如 "A", "I", "Q"）
    if len(cleaned) <= 1:
        return False
    
    # 排除太长的（超过 40 字符不像名字）
    if len(cleaned) > 40:
        return False
    
    # 排除明显是代码/变量的
    if '_' in cleaned:  # 蛇形命名
        return False
    if cleaned.startswith('[') or cleaned.endswith(']'):  # 变量插值
        return False
    if cleaned.startswith('{') or cleaned.endswith('}'):  # 标签
        return False
    if '.' in cleaned and not cleaned.endswith('.'):  # 属性访问（但允许 "Mr."）
        return False
    if '(' in cleaned or ')' in cleaned:  # 函数调用
        return False
    
    # 检查是否包含非 ASCII 字符（日文、中文等名字）
    has_non_ascii = any(ord(c) > 127 for c in cleaned)
    if has_non_ascii:
        # 非 ASCII 名字：不过长，不含数字和特殊符号
        if len(cleaned) <= 15 and not re.search(r'[\d!@#$%^&*()+=\[\]{}|\\:";\'<>,./]', cleaned):
            return True
        return False
    
    # 英文名字必须首字母大写
    if not cleaned[0].isupper():
        return False
    
    # 检查是否是名字格式（允许字母、空格、连字符、撇号、符号#和数字）
    if re.match(r'^[A-Z][a-zA-Z\-\'\s#\d\.]+$', cleaned):
        return True
    
    return False


def extract_names_from_game(game_dir: Path) -> Set[str]:
    """从游戏源码中提取角色名（用于术语库）。
    
    扫描多种来源：
    1. Character() 定义
    2. textbutton/text 控件中的短文本
    
    返回清理后的纯文本名字（不含格式标签）。
    """
    logger = LogManager.get()
    names: Set[str] = set()
    
    tl_dir = game_dir / "tl"
    
    for dirpath, dirnames, filenames in os.walk(game_dir):
        current = Path(dirpath).resolve()
        if tl_dir.exists() and (current == tl_dir.resolve() or 
            str(current).startswith(str(tl_dir.resolve()) + os.sep)):
            continue
        for filename in filenames:
            if filename.endswith(".rpy"):
                rpy_path = Path(dirpath) / filename
                try:
                    content = rpy_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                
                # 1. 从 Character() 定义提取
                for pattern in [
                    r'Character\s*\(\s*(["\'])((?:\\\1|.)*?)\1',
                    r'define\s+\w+\s*=\s*Character\s*\(\s*(["\'])((?:\\\1|.)*?)\1',
                ]:
                    for match in re.finditer(pattern, content, re.IGNORECASE):
                        text = _unescape(match.group(2))
                        if text and _is_character_name(text):
                            clean_name = _strip_format_tags(text)
                            if clean_name:
                                names.add(clean_name)
                
                # 2. 从 textbutton/text 控件提取
                for pattern in [
                    r'\b(?:text|textbutton)\s+(["\'])((?:\\\1|.)*?)\1',
                ]:
                    for match in re.finditer(pattern, content, re.IGNORECASE):
                        text = _unescape(match.group(2))
                        if _is_character_name(text):
                            clean_name = _strip_format_tags(text)
                            if clean_name:
                                names.add(clean_name)
    
    logger.debug(f"从源码提取到 {len(names)} 个角色名")
    return names


def _extract_all_strings_regex(game_dir: Path, *, cache_path: Optional[Path] = None) -> Set[str]:
    """使用的正则方法扫描源码，提取所有可翻译字符串。
    
    这个方法比 AST 更"暴力"，能捕获一些非标准写法。
    """
    logger = LogManager.get()
    all_strings: Set[str] = set()

    rpy_files, file_count, max_mtime_ns = _collect_source_rpy_files(game_dir)

    if cache_path is not None:
        cached = _try_load_regex_cache(cache_path, file_count=file_count, max_mtime_ns=max_mtime_ns)
        if cached is not None:
            logger.debug(f"正则扫描：命中缓存 {cache_path} ({len(cached)} 条)")
            return cached

    logger.debug(f"正则扫描：找到 {len(rpy_files)} 个源码文件")

    # 多行 define/default = { ... } / [ ... ] 的开始行
    multiline_block_start_re = re.compile(
        r'^\s*(?:define|default)\s+\w+\s*=\s*([\{\[])\s*(?:#.*)?$',
        re.IGNORECASE,
    )
    multiline_block_start_dollar_re = re.compile(
        r'^\s*\$\s*\w+\s*=\s*([\{\[])\s*(?:#.*)?$',
        re.IGNORECASE,
    )

    def bracket_delta_outside_strings(line: str, open_ch: str, close_ch: str) -> int:
        """Count bracket delta (+open/-close) outside quoted strings and outside comments."""
        delta = 0
        quote: Optional[str] = None
        escaped = False
        for ch in line:
            if quote is not None:
                if escaped:
                    escaped = False
                    continue
                if ch == "\\":
                    escaped = True
                    continue
                if ch == quote:
                    quote = None
                continue

            if ch in ("'", '"'):
                quote = ch
                escaped = False
                continue

            if ch == "#":
                break

            if ch == open_ch:
                delta += 1
            elif ch == close_ch:
                delta -= 1
        return delta
    
    for rpy_path in rpy_files:
        try:
            content = rpy_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        
        # === 的正则规则 ===
        
        # 1. 角色定义
        for pattern in [
            r'Character\s*\(\s*(["\'])((?:\\\1|.)*?)\1',
            r'define\s+\w+\s*=\s*Character\s*\(\s*(["\'])((?:\\\1|.)*?)\1',
        ]:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                text = _unescape(match.group(2))
                if text and len(text) > 0:
                    all_strings.add(text)
        
        # 2. 文本控件
        for pattern in [
            r'\btext\s+(["\'])((?:\\\1|.)*?)\1\s*:',
            r'\b(?:text|textbutton|show\s+text)\s+(["\'])((?:\\\1|.)*?)\1',
            r'renpy\.input\s*\(\s*(["\'])((?:\\\1|.)*?)\1',
            r'renpy\.notify\s*\(\s*(["\'])((?:\\\1|.)*?)\1',
            r'_\(\s*(["\'])((?:\\\1|.)*?)\1\s*\)',  # gettext 风格 _(...)
        ]:
            for match in re.finditer(pattern, content, re.IGNORECASE | re.MULTILINE):
                text = _unescape(match.group(2) if len(match.groups()) >= 2 else "")
                if text and len(text) > 0:
                    all_strings.add(text)
        
        # 3. tooltip
        for match in re.finditer(r'\btooltip\s*\(\s*(["\'])((?:\\\1|.)*?)\1', content, re.IGNORECASE):
            text = _unescape(match.group(2))
            if text:
                all_strings.add(text)
        
        # 4. 逐行扫描：变量赋值、f-string、多行 define/default 字典/列表等
        multiline_block: Optional[dict] = None  # {"open": "{", "close": "}", "kind": "dict|list", "depth": int}
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            # 多行 define/default 字典/列表：把分散在多行的字符串也纳入候选（常见于 location/daytime 这类表）。
            if multiline_block is not None:
                if multiline_block["kind"] == "dict":
                    # 仅抓 value（冒号后面的字符串），避免把 key（如 'night'）误当成可翻译文本
                    for match in re.finditer(r':\s*(["\'])((?:\\\1|.)*?)\1', line):
                        text = _unescape(match.group(2))
                        if text and len(text) > 1:
                            all_strings.add(text)
                else:
                    for match in re.finditer(r'(["\'])((?:\\\1|.)*?)\1', line):
                        text = _unescape(match.group(2))
                        if text and len(text) > 1:
                            all_strings.add(text)

                multiline_block["depth"] += bracket_delta_outside_strings(
                    line, multiline_block["open"], multiline_block["close"]
                )
                if multiline_block["depth"] <= 0:
                    multiline_block = None
            
            # 变量赋值中的字符串
            if re.search(r'(default|define)\s+\w+\s*=\s*', line) or re.search(r'\$\s*\w+\s*=\s*', line):
                for match in re.finditer(r'(["\'])((?:\\\1|.)*?)\1', line):
                    text = _unescape(match.group(2))
                    if text and len(text) > 1:  # 忽略单字符
                        all_strings.add(text)
            
            # f-string（需要 replace_text 钩子）
            if ('f"' in line or "f'" in line) and '_.(' not in line:
                for match in re.finditer(r'f(["\'])((?:\\\1|.)*?)\1', line):
                    text = _unescape(match.group(2))
                    if text and len(text) > 1:
                        all_strings.add(text)

            # 进入多行字典/列表块（只在当前不处于 block 时触发）
            if multiline_block is None:
                m = multiline_block_start_re.match(line) or multiline_block_start_dollar_re.match(line)
                if m:
                    open_ch = m.group(1)
                    close_ch = "}" if open_ch == "{" else "]"
                    depth = bracket_delta_outside_strings(line, open_ch, close_ch)
                    if depth > 0:
                        multiline_block = {
                            "open": open_ch,
                            "close": close_ch,
                            "kind": "dict" if open_ch == "{" else "list",
                            "depth": depth,
                        }

        # 5. 三引号多行字符串（简单捕获）
        for match in re.finditer(r'"""(.*?)"""', content, re.DOTALL):
            text = _unescape(match.group(1))
            if text and len(text) > 1:
                all_strings.add(text)
    
    logger.debug(f"正则扫描：共提取 {len(all_strings)} 个候选字符串")

    if cache_path is not None:
        _save_regex_cache(cache_path, file_count=file_count, max_mtime_ns=max_mtime_ns, strings=all_strings)

    return all_strings


def _get_tl_covered_strings(target_path: str | Path, tl_name: str) -> Set[str]:
    """读取 tl 目录中“已覆盖”的原文集合（自动排除 miss_ready_replace 等中间文件）。"""
    logger = LogManager.get()
    game_dir = _get_game_dir(target_path)
    tl_dir = game_dir / "tl" / tl_name

    if not tl_dir.exists():
        return set()

    try:
        extractor = SimpleRpyExtractor()
        entries = extractor.extract_from_directory(tl_dir, tl_name, filter_garbage=False)
        originals = {e.get("original", "") for e in entries if e.get("original")}
        logger.debug(f"tl 覆盖：已读取 {len(originals)} 条原文")
        return originals
    except Exception as e:
        logger.warning(f"读取 tl 覆盖失败: {e}")
        return set()


# ===================== 缺失补丁相关（一键操作）=====================

def _filter_valid_strings(strings: Set[str]) -> Set[str]:
    """过滤无效字符串 - 只过滤明显是代码的内容，保留可能需要翻译的文本"""
    result = set()

    # 常见全局变量访问（persistent/config/store/renpy）直接跳过
    renpy_store_pattern = re.compile(r'\b(?:persistent|store|config|renpy)\.[\w\.]+\b', re.IGNORECASE)
    pascal_case_pattern = re.compile(r'^[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+$')

    # UI/占位符停用词，避免进 miss
    # 只保留极少数占位/路径类停用词，放行常见 UI 文本（例如 Back/Save/Load 等）
    UI_STOPWORDS = {
        "save-file",
        "save-file:",
        "manual download links:",
        "manual links",
        "save location",
        "save location:",
        "by [my_name]",
        "[config.version] save",
    }
    
    # 只过滤明显是代码/内部标识符的模式
    code_patterns = [
        r'^[\d\s\-\+\*\/\=\.\,\:\;\(\)\[\]\{\}\"\']+$',  # 纯符号/数字（不含字母）
        r'^(gui|config|renpy|persistent)\.',  # 配置变量
        r'^(scene|event|label|screen|init|python|define|default)_\w+$',  # 内部标识符
        r'^[a-z][a-z0-9]*_[a-z0-9_]+$',  # snake_case 变量名（如 bath_room）
        r'^\w+\s*\([^)]*\)\s*$',  # 函数调用
        r'SetVariable|SetField|Function|Return|Jump|Show|Hide|Play|Stop',  # Ren'Py 函数
        r'^\.mp4$|^\.txt$|^\.rpy$|^\.png$|^\.jpg$',  # 文件扩展名
        r'\.txt$|\.rpy$',  # 以扩展名结尾
        r'^movies?/',  # 路径
        r'^images?/',  # 路径
        r'^#[0-9a-fA-F]{6}',  # 颜色代码
        r'^action\s+\[',  # action 代码
        r'^\s*,\s*None',  # 代码片段
        r'^text_size|^text_outlines|^text_text_align|^text_line_spacing',  # 样式代码
        r'^absolute\(|^Transform\(|^Dissolve\(',  # 函数
        r'^\(\s*\d',  # 以 ( 数字开头的元组
    ]
    
    compiled_patterns = [re.compile(p, re.IGNORECASE) for p in code_patterns]
    
    for s in strings:
        if not s:
            continue
        
        s = s.strip()

        # 基础过滤：太短
        if len(s) <= 1:
            continue

        # 持久化/全局变量访问样式（包含中间的点号）不需要翻译
        if renpy_store_pattern.search(s):
            continue

        # 逻辑表达式残片（含 and/or/not 与括号），无大写/CJK，视为代码
        if (
            not re.search(r'[\u4e00-\u9fff\u3040-\u30ff]', s)
            and not re.search(r'[A-Z]', s)
            and re.search(r'\b(and|or|not)\b', s.lower())
            and ('(' in s or ')' in s)
        ):
            continue

        # 冒号残片（如 ": persistent.xxx,"）跳过
        cleaned_for_colon = s.strip()
        if cleaned_for_colon.startswith((":","：")) or cleaned_for_colon.endswith((",", "，")):
            if re.match(r'^[:：]\s*[\w\.\[\], ]+$', cleaned_for_colon) or re.match(r'^[\w\.\[\] ]+[,，]\s*$', cleaned_for_colon):
                continue

        # 跳过匹配代码模式的
        skip = False
        for pattern in compiled_patterns:
            if pattern.search(s):
                skip = True
                break
        if skip:
            continue

        # PascalCase 无空格、无 CJK，长度较长的多段单词，视为代码常量/标识符
        if pascal_case_pattern.match(s) and not re.search(r'[\u4e00-\u9fff\u3040-\u30ff]', s):
            continue
        
        # 跳过纯小写+下划线的标识符（如 my_room, bath_room）
        if re.match(r'^[a-z][a-z0-9_]*$', s) and '_' in s:
            continue
        
        # 跳过纯变量插值（如 [var_name]）
        if re.match(r'^\[[a-z_][a-z0-9_\.]*\]$', s, re.IGNORECASE):
            continue

        # 跳过包含变量占位或 URL 的
        if re.search(r'\[[^\]]+\]', s):
            continue
        if "http://" in s.lower() or "https://" in s.lower():
            continue

        # 跳过明显的代码片段/占位符
        if '+' in s and '_' in s:
            continue
        if re.search(r'\w+\s*\([^)]*\)', s):  # 函数调用样式
            continue
        if s.strip().startswith('(') and s.strip().endswith(')') and len(s.strip()) <= 20:
            continue
        if s.strip().startswith('<') and s.strip().endswith('>'):
            continue
        
        # 去除格式标签后分析
        cleaned = re.sub(r'\{[^}]+\}', '', s).strip()
        
        # 跳过清理后为空的（纯格式标签）
        if not cleaned:
            continue
        
        # 跳过清理后只剩符号/数字的
        if re.match(r'^[\d\s\-\+\*\/\=\.\,\:\;\!\?\%\$\#\@\(\)\[\]]+$', cleaned):
            continue

        # 停用词过滤（UI/占位符/前缀符号）
        lower_clean = cleaned.lower()
        if lower_clean in UI_STOPWORDS:
            continue
        # 前缀停用词
        if any(lower_clean.startswith(word) for word in ("save-file", "manual download links", "manual links")):
            continue
        # 以项目符号开头的音乐/致谢行
        if lower_clean.strip().startswith("• "):
            continue

        # should_skip_text 终极过滤
        if should_skip_text(cleaned):
            continue
        
        result.add(s)
    
    return result


def generate_miss_rpy_auto(target_path: str | Path, tl_name: str) -> Tuple[Path | None, int, int, int, Set[str]]:
    """【一键操作】自动生成缺失补丁。
    
    内部流程：
    1. 用正则扫描源码 → 全量候选
    2. 读取 tl 覆盖 → 已抽取覆盖
    3. 差集 → 缺失文本 → 写入 miss_ready_replace.rpy
    
    Returns:
        (miss 文件路径或 None, 缺失条目数, 正则扫描总数, tl覆盖数)
    """
    logger = LogManager.get()
    game_dir = _get_game_dir(target_path)
    tl_dir = game_dir / "tl" / tl_name
    tl_dir.mkdir(parents=True, exist_ok=True)
    miss_dir = tl_dir / MISS_DIR
    miss_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. 正则全量扫描
    logger.info("正在使用正则扫描源码...")
    regex_all = _extract_all_strings_regex(game_dir, cache_path=miss_dir / REGEX_CACHE)
    regex_filtered = _filter_valid_strings(regex_all)
    
    # 2. tl 覆盖（已抽取的文本）
    logger.info("正在读取 tl 已覆盖文本...")
    tl_covered = _get_tl_covered_strings(target_path, tl_name)

    # 2b. replace_text_auto 覆盖（已通过 hook 替换的文本）
    hook_path = tl_dir / "replace_text_auto.rpy"
    if hook_path.exists():
        try:
            hook_originals = {old for old, _ in _parse_existing_replace_pairs(hook_path)}
        except Exception:
            hook_originals = set()
        if hook_originals:
            tl_covered |= hook_originals
            logger.info(f"已识别 replace_text_auto 覆盖: {len(hook_originals)} 条")
    
    # 3. 计算差集
    missing = regex_filtered - tl_covered
    
    logger.info(f"扫描统计: 正则={len(regex_filtered)}, tl覆盖={len(tl_covered)}, 缺失={len(missing)}")
    
    if not missing:
        logger.info("✓ 未发现缺失文本，tl 已完全覆盖")
        # 删除旧的 miss 文件（如果有）
        for candidate in _get_miss_candidates(tl_dir):
            try:
                if candidate.exists():
                    candidate.unlink()
            except Exception:
                pass
        return None, 0, len(regex_filtered), len(tl_covered)
    
    # 4. 加载术语库，预填翻译
    glossary_map = _load_glossary_map()
    
    # 5. 写入 miss.rpy
    lines = [
        "# ============================================",
        "# 官方抽取遗漏的文本（自动检测）",
        "# 请翻译下面的 new 字段，然后使用「生成 Replace 钩子」",
        "# ============================================",
        "",
        f"translate {tl_name} strings:",
        "",
    ]
    
    auto_filled = 0
    for orig in sorted(missing):
        escaped_orig = _escape_string(orig)
        # 尝试从术语库获取翻译
        trans = glossary_map.get(orig, orig)
        escaped_trans = _escape_string(trans)
        if trans != orig:
            auto_filled += 1
        lines.append(f'    old "{escaped_orig}"')
        lines.append(f'    new "{escaped_trans}"')
        lines.append("")
    
    miss_path = _resolve_miss_path(tl_dir) or (miss_dir / MISS_RPY)
    miss_path.parent.mkdir(parents=True, exist_ok=True)
    miss_path.write_text("\n".join(lines), encoding="utf-8")
    
    if auto_filled > 0:
        logger.info(f"✓ 已生成缺失补丁: {miss_path} ({len(missing)} 条，其中 {auto_filled} 条已从术语库填充)")
    else:
        logger.info(f"✓ 已生成缺失补丁: {miss_path} ({len(missing)} 条)")
    
    # 识别缺失文本中的角色名，并清理格式标签
    detected_names = set()
    for text in missing:
        if _is_character_name(text):
            # 清理格式标签，得到纯文本名字
            clean_name = _strip_format_tags(text)
            if clean_name and not should_skip_text(clean_name):
                detected_names.add(clean_name)
    
    return miss_path, len(missing), len(regex_filtered), len(tl_covered), detected_names


def add_names_to_glossary(names: Set[str], auto_classify: bool = True) -> int:
    """将提取的文本添加到术语库（如果不存在），并可选使用 NER 自动分类。
    
    Args:
        names: 文本集合（会自动清理格式标签）
        auto_classify: 是否使用 NER 自动分类（默认 True）
        
    Returns:
        新增的条目数
    """
    if not names:
        return 0
    
    logger = LogManager.get()
    
    try:
        from module.Config import Config
        config = Config().load()
        glossary_data = getattr(config, "glossary_data", None) or []
        # 移除旧的自动提取条目（避免累积垃圾）
        manual_entries = []
        for item in glossary_data:
            if isinstance(item, dict):
                info = (item.get("info", "") or item.get("comment", "")).lower()
                if "自动提取" in info:
                    continue
            manual_entries.append(item)

        # 已有的原文（支持 dict 和 list 两种格式），同时清理格式标签后比较
        existing = set()
        for item in manual_entries:
            if isinstance(item, dict):
                src = item.get("src", "")
                existing.add(src)
                existing.add(_strip_format_tags(src))  # 也添加清理后的版本
            elif isinstance(item, (list, tuple)) and item:
                existing.add(item[0])
                existing.add(_strip_format_tags(item[0]))

        # 准备新条目
        new_entries = []
        for name in sorted(names):
            # 清理格式标签
            clean_name = _strip_format_tags(name)
            if not clean_name or should_skip_text(clean_name):
                continue
            # 检查清理后的名字是否已存在
            if clean_name not in existing:
                new_entries.append(clean_name)
                existing.add(clean_name)  # 避免同一批次重复添加
        
        if not new_entries:
            return 0
        
        # 使用 NER 分类（如果启用）
        entry_types = {}
        if auto_classify:
            entry_types = _classify_entries_with_ner(new_entries)
        
        # 添加到术语库
        for clean_name in new_entries:
            entry_type = entry_types.get(clean_name, "")  # 空字符串表示未分类
            manual_entries.append({
                "src": clean_name,
                "dst": "",
                "comment": "(自动提取)",
                "type": entry_type
            })
        
        config.glossary_data = manual_entries
        config.save()
        
        classified_count = sum(1 for t in entry_types.values() if t)
        logger.info(f"✓ 已将 {len(new_entries)} 个条目添加到术语库（NER 分类 {classified_count} 条）")
        
        return len(new_entries)
    except Exception as e:
        logger.error(f"添加条目到术语库失败: {e}")
        return 0


def _classify_entries_with_ner(entries: List[str]) -> dict:
    """使用 NER 对条目进行分类。
    
    Returns:
        {条目: 类别} 映射
    """
    if not entries:
        return {}
    
    logger = LogManager.get()
    result = {}
    
    try:
        # 尝试使用 spacy 进行 NER
        try:
            import spacy
            try:
                nlp = spacy.load("en_core_web_sm")
            except OSError:
                nlp = spacy.load("en_core_web_md") if spacy.util.is_package("en_core_web_md") else None
            
            if nlp:
                # NER 标签到术语库类别的映射
                ner_to_type = {
                    "PERSON": "角色",
                    "ORG": "组织",
                    "GPE": "地名",
                    "LOC": "地名",
                    "FAC": "地名",  # 设施
                    "EVENT": "其他",
                    "WORK_OF_ART": "WORK_OF_ART",
                    "PRODUCT": "物品",
                    "NORP": "NORP",  # 国籍/宗教/政治团体
                }
                
                for entry in entries:
                    doc = nlp(entry)
                    if doc.ents:
                        # 取第一个实体的标签
                        label = doc.ents[0].label_
                        if label in ner_to_type:
                            result[entry] = ner_to_type[label]
                
                logger.debug(f"NER 分类完成，识别 {len(result)} 条")
                return result
        except ImportError:
            pass
        
        # 回退：使用简单规则分类
        for entry in entries:
            entry_type = _rule_based_classify(entry)
            if entry_type:
                result[entry] = entry_type
        
        return result
    except Exception as e:
        logger.warning(f"NER 分类失败: {e}")
        return {}


def _rule_based_classify(text: str) -> str:
    """基于规则的简单分类"""
    if not text:
        return ""
    
    text_lower = text.lower()
    
    # 地点关键词
    place_keywords = ['room', 'house', 'hall', 'street', 'park', 'forest', 'garden',
                      'shop', 'store', 'bank', 'castle', 'tower', 'cave', 'island',
                      'village', 'town', 'city', 'school', 'church', 'temple', 'spa',
                      'onsen', 'square', 'chamber', 'place']
    if any(kw in text_lower for kw in place_keywords):
        return "地名"
    
    # 物品关键词
    item_keywords = ['book', 'shelf', 'memory', 'recorder', 'service']
    if any(kw in text_lower for kw in item_keywords):
        return "物品"
    
    # 带称呼后缀的通常是角色
    name_suffixes = ['-chan', '-san', '-kun', '-sama', '-sensei', ' chan', ' san']
    if any(text_lower.endswith(suf) for suf in name_suffixes):
        return "角色"
    
    # Miss/Mr/Mrs 开头的是角色
    if re.match(r'^(Miss|Mr\.?|Mrs\.?|Ms\.?)\s+', text, re.IGNORECASE):
        return "角色"
    
    return ""


def scan_missing_and_update_glossary(target_path: str | Path, tl_name: str) -> Tuple[Path | None, int, int]:
    """【完整流程】扫描缺失并反补术语库。
    
    流程：
    1. 扫描缺失文本 → 生成 miss_ready_replace.rpy
    2. 从缺失文本中识别角色名 → 反补到术语库
    
    Returns:
        (miss 文件路径, 缺失条目数, 新增角色名数)
    """
    logger = LogManager.get()
    
    # 1. 生成缺失补丁
    result = generate_miss_rpy_auto(target_path, tl_name)
    miss_path, miss_count, regex_count, tl_count, detected_names = result
    
    # 2. 把识别到的角色名反补到术语库
    added_names = 0
    if detected_names:
        logger.info(f"从缺失文本中识别到 {len(detected_names)} 个可能的角色名")
        added_names = add_names_to_glossary(detected_names)
    
    return miss_path, miss_count, added_names


def _load_glossary_map() -> dict:
    """加载术语库，返回 {原文: 译文} 映射"""
    try:
        from module.Config import Config
        config = Config().load()
        glossary_data = getattr(config, "glossary_data", []) or []
        result = {}
        for item in glossary_data:
            if isinstance(item, dict):
                src = item.get("src", "")
                dst = item.get("dst", "")
                if src and dst:
                    result[src] = dst
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                if item[0] and item[1]:
                    result[item[0]] = item[1]
        return result
    except Exception:
        return {}


def sync_miss_rpy_with_glossary(game_dir: str | Path, tl_name: str) -> int:
    """同步术语库翻译到 miss.rpy。
    
    当用户在术语库中添加/修改翻译后调用此函数，
    自动更新 miss.rpy 中对应条目的 new 字段。
    
    Returns:
        更新的条目数
    """
    logger = LogManager.get()
    tl_dir = Path(game_dir) / "tl" / tl_name
    miss_path = _resolve_miss_path(tl_dir)
    
    if not miss_path or not miss_path.exists():
        return 0
    
    content = miss_path.read_text(encoding="utf-8")
    glossary_map = _load_glossary_map()
    
    if not glossary_map:
        return 0
    
    # 解析并更新
    old_pattern = re.compile(r'^(\s*)old\s+"(.*)"\s*$')
    new_pattern = re.compile(r'^(\s*)new\s+"(.*)"\s*$')
    
    lines = content.split("\n")
    updated_count = 0
    i = 0
    
    while i < len(lines):
        old_match = old_pattern.match(lines[i])
        if old_match and i + 1 < len(lines):
            new_match = new_pattern.match(lines[i + 1])
            if new_match:
                indent = old_match.group(1)
                orig_escaped = old_match.group(2)
                current_trans_escaped = new_match.group(2)
                
                # 反转义
                orig = orig_escaped.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")
                current_trans = current_trans_escaped.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")
                
                # 检查术语库是否有翻译
                if orig in glossary_map:
                    glossary_trans = glossary_map[orig]
                    # 只有当术语库翻译与当前不同时才更新
                    if glossary_trans != current_trans and glossary_trans != orig:
                        new_escaped = _escape_string(glossary_trans)
                        lines[i + 1] = f'{indent}new "{new_escaped}"'
                        updated_count += 1
                
                i += 2
                continue
        i += 1
    
    if updated_count > 0:
        miss_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"✓ 已同步 {updated_count} 条术语库翻译到 miss.rpy")
    
    return updated_count


# ===================== Replace 钩子相关 =====================

def parse_miss_rpy(game_dir: str | Path, tl_name: str) -> List[Pair]:
    """解析 miss.rpy，提取已翻译的条目（原文 != 译文）。
    
    Returns:
        [(原文, 译文), ...] 列表
    """
    tl_dir = Path(game_dir) / "tl" / tl_name
    miss_path = _resolve_miss_path(tl_dir)
    
    if not miss_path or not miss_path.exists():
        return []
    
    content = miss_path.read_text(encoding="utf-8")
    
    # 解析 old/new 对
    pairs: List[Pair] = []
    old_pattern = re.compile(r'^\s*old\s+"(.*)"\s*$')
    new_pattern = re.compile(r'^\s*new\s+"(.*)"\s*$')
    
    lines = content.split("\n")
    i = 0
    while i < len(lines):
        old_match = old_pattern.match(lines[i])
        if old_match and i + 1 < len(lines):
            new_match = new_pattern.match(lines[i + 1])
            if new_match:
                orig = old_match.group(1)
                trans = new_match.group(1)
                # 反转义
                orig = orig.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")
                trans = trans.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")
                # 只添加已翻译的（原文 != 译文）
                if orig and trans and orig != trans:
                    pairs.append((orig, trans))
                i += 2
                continue
        i += 1
    
    return pairs


def render_replace_script(
    pairs: Sequence[Pair],
    *,
    function_name: str = "replace_text",
    target_name: str = "s",
    assign_to_config: bool = True,
) -> str:
    """Render a Ren'Py script that defines a ``replace_text`` hook."""

    # 归一化/去重：同一个 original 只保留最后一次出现的翻译
    merged: dict[str, str] = {}
    for original, translation in pairs:
        if not original or not translation or original == translation:
            continue
        merged[str(original)] = str(translation)

    # 兼容：很多 UI 字符串会带 {b}/{color} 等标签，但运行时可能被剥离后再进入 replace_text。
    # 因此自动补一份“去标签”的映射，保证两种形态都能命中。
    expanded: dict[str, str] = dict(merged)
    for original, translation in list(merged.items()):
        if "{" not in original or "}" not in original:
            continue
        stripped_old = _strip_format_tags(original)
        stripped_new = _strip_format_tags(translation)
        if not stripped_old or not stripped_new or stripped_old == stripped_new:
            continue
        # 不覆盖已有的无标签映射（如果用户手工指定了更精确的版本）
        expanded.setdefault(stripped_old, stripped_new)

    # 长字符串优先，避免 "Back" 先替换导致 "Back home" 失效这类问题
    normalized_pairs: List[Pair] = sorted(
        expanded.items(),
        key=lambda it: (-len(it[0]), it[0]),
    )

    lines: List[str] = [
        "# Auto-generated replace_text hook",
        "# 用于替换官方抽取无法覆盖的文本",
        "",
        "init python early:",
    ]
    lines.append(f"    def {function_name}({target_name}):")
    lines.append(f"        if not isinstance({target_name}, str):")
    lines.append(f"            return {target_name}")
    
    if not normalized_pairs:
        lines.append(f"        return {target_name}")
    else:
        lines.append(f"        result = {target_name}")
        for original, translation in normalized_pairs:
            escaped_old = _escape_string(original)
            escaped_new = _escape_string(translation)
            lines.append(f'        result = result.replace("{escaped_old}", "{escaped_new}")')
        lines.append("        return result")

    if assign_to_config:
        lines.append("")
        lines.append(f"    config.replace_text = {function_name}")

    lines.append("")
    return "\n".join(lines)


def _parse_existing_replace_pairs(path: Path) -> List[Pair]:
    """Parse existing `replace_text_auto.rpy` and return (old, new) pairs.

    This is best-effort and only supports the tool-generated format:
    `result = result.replace("old", "new")`.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    # Match the exact tool-generated `result.replace("...", "...")` lines.
    pattern = re.compile(
        r'result\s*=\s*result\.replace\(\s*"(?P<old>(?:\\.|[^"\\])*)"\s*,\s*"(?P<new>(?:\\.|[^"\\])*)"\s*\)'
    )

    def unescape_literal(s: str) -> str:
        return s.replace("\\n", "\n").replace('\\"', '"').replace("\\'", "'").replace("\\\\", "\\")

    pairs: List[Pair] = []
    for m in pattern.finditer(text):
        old = unescape_literal(m.group("old"))
        new = unescape_literal(m.group("new"))
        if old and new and old != new:
            pairs.append((old, new))
    return pairs


def write_replace_script(
    output_path: str | Path,
    pairs: Sequence[Pair],
    *,
    merge_existing: bool = True,
    **kwargs,
) -> Path:
    """Write a rendered replace hook to ``output_path`` and return the path.

    By default it merges existing `replace_text_auto.rpy` mappings so re-generating the hook
    won't drop previously translated replacements.
    """

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    merged: dict[str, str] = {}
    if merge_existing and output.exists():
        for old, new in _parse_existing_replace_pairs(output):
            merged[old] = new

    for old, new in pairs:
        if old and new and old != new:
            merged[str(old)] = str(new)

    script = render_replace_script(list(merged.items()), **kwargs)
    output.write_text(script, encoding="utf-8")
    return output


def generate_replace_from_miss(target_path: str | Path, tl_name: str) -> Tuple[Path | None, int]:
    """从 miss.rpy 生成 replace 钩子。
    
    读取 miss.rpy 中已翻译的条目，生成 replace_text_auto.rpy。
    
    Returns:
        (输出路径或 None, 条目数量)
    """
    logger = LogManager.get()
    game_dir = _get_game_dir(target_path)
    tl_dir = game_dir / "tl" / tl_name
    
    pairs = parse_miss_rpy(game_dir, tl_name)
    
    if not pairs:
        logger.info("未找到已翻译的缺失条目，请先翻译 miss.rpy")
        return None, 0
    
    output_path = tl_dir / "replace_text_auto.rpy"
    write_replace_script(output_path, pairs)
    
    logger.info(f"已生成 replace 钩子: {output_path} ({len(pairs)} 条)")
    return output_path, len(pairs)


# ===================== 状态检查（给 UI 用）=====================

def check_miss_rpy_status(target_path: str | Path, tl_name: str) -> dict:
    """检查 miss.rpy 的状态。
    
    Returns:
        {
            "exists": bool,          # miss.rpy 是否存在
            "total_count": int,      # 总条目数
            "translated_count": int, # 已翻译条目数
            "path": str | None       # 文件路径
        }
    """
    game_dir = _get_game_dir(target_path)
    tl_dir = game_dir / "tl" / tl_name
    miss_path = _resolve_miss_path(tl_dir)

    # hook 文件（生成后可不再保留 miss 文件）
    hook_path = tl_dir / "replace_text_auto.rpy"
    hook_exists = hook_path.exists()

    # 归档文件（避免 Ren'Py 运行时报重复翻译）
    archived_path: Optional[Path] = None
    for base in (tl_dir / MISS_DIR, tl_dir):
        try:
            found = sorted(base.glob("miss_ready_replace.done*.txt"))
        except Exception:
            found = []
        if found:
            archived_path = found[0]
            break
    
    if not miss_path or not miss_path.exists():
        return {
            "exists": False,
            "total_count": 0,
            "translated_count": 0,
            "path": None,
            "hook_exists": hook_exists,
            "hook_path": str(hook_path) if hook_exists else None,
            "archived_exists": bool(archived_path is not None),
            "archived_path": str(archived_path) if archived_path is not None else None,
        }
    
    content = miss_path.read_text(encoding="utf-8")
    
    # 计算总条目和已翻译条目
    old_pattern = re.compile(r'^\s*old\s+"(.*)"\s*$')
    new_pattern = re.compile(r'^\s*new\s+"(.*)"\s*$')
    
    total = 0
    translated = 0
    lines = content.split("\n")
    
    i = 0
    while i < len(lines):
        old_match = old_pattern.match(lines[i])
        if old_match and i + 1 < len(lines):
            new_match = new_pattern.match(lines[i + 1])
            if new_match:
                total += 1
                orig = old_match.group(1)
                trans = new_match.group(1)
                if orig != trans:
                    translated += 1
                i += 2
                continue
        i += 1
    
    return {
        "exists": True,
        "total_count": total,
        "translated_count": translated,
        "path": str(miss_path),
        "hook_exists": hook_exists,
        "hook_path": str(hook_path) if hook_exists else None,
        "archived_exists": bool(archived_path is not None),
        "archived_path": str(archived_path) if archived_path is not None else None,
    }


def archive_miss_file(target_path: str | Path, tl_name: str) -> Path | None:
    """Archive miss_ready_replace.rpy to a non-.rpy file to avoid Ren'Py duplicate-translation errors.

    After generating `replace_text_auto.rpy`, this intermediate file is no longer needed at runtime.

    Returns:
        Archived path, or None if no active miss file exists.
    """
    game_dir = _get_game_dir(target_path)
    tl_dir = game_dir / "tl" / tl_name
    miss_path = _resolve_miss_path(tl_dir)

    if not miss_path or not miss_path.exists():
        return None

    name_lower = miss_path.name.lower()
    if not name_lower.startswith("miss_ready_replace"):
        return None

    archive_dir = miss_path.parent
    archive_dir.mkdir(parents=True, exist_ok=True)

    archive_path = archive_dir / f"{miss_path.stem}.done.txt"
    if archive_path.exists():
        # Avoid overwrite if user keeps historical files.
        import time

        ts = time.strftime("%Y%m%d_%H%M%S")
        archive_path = archive_dir / f"{miss_path.stem}.done.{ts}.txt"

    try:
        miss_path.replace(archive_path)
    except Exception:
        try:
            content = miss_path.read_text(encoding="utf-8", errors="replace")
            archive_path.write_text(content, encoding="utf-8")
            miss_path.unlink(missing_ok=True)
        except Exception:
            return None

    return archive_path

