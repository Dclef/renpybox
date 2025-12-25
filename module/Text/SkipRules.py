"""Shared text skipping/whitelist rules for Ren'Py extraction & translation.

本模块提供统一的文本过滤规则，用于：
1. 提取阶段：判断哪些文本应该被提取翻译
2. 翻译阶段：判断哪些文本应该跳过不翻译

优化说明 (v2.0):
- 整合脚本的过滤逻辑
- 增强对代码标识符、路径、资源名的检测
- 支持 CJK 字符（中日韩文本）
- 提供 filter_extracted_strings 统一接口
"""

from __future__ import annotations

import re
from typing import Iterable, List, Set, Tuple, Optional

# ============================================================
# 正则表达式模式
# ============================================================

# 资源文件扩展名（音频/视频/图片/字体/存档）
_RESOURCE_EXTENSIONS = (
    # 音频
    'mp3', 'wav', 'ogg', 'opus', 'm4a', 'flac', 'aac', 'wma',
    # 视频
    'mp4', 'mkv', 'webm', 'avi', 'mov', 'wmv', 'flv',
    # 图片
    'png', 'jpg', 'jpeg', 'webp', 'bmp', 'gif', 'tga', 'dds', 'psd', 'ico', 'svg',
    # 字体
    'ttf', 'otf', 'woff', 'woff2',
    # Ren'Py 相关
    'rpa', 'rpyc', 'rpy',
    # 其他
    'json', 'xml', 'yaml', 'yml', 'txt', 'csv', 'ini', 'cfg',
)

# 匹配资源文件名
_RESOURCE_NAME_PATTERN = re.compile(
    r"^[\w\-. ]+\.(?:" + "|".join(_RESOURCE_EXTENSIONS) + r")$",
    re.IGNORECASE,
)

# 匹配短文件名 (foo.txt / name.ext)
_FILENAME_PATTERN = re.compile(r"^[a-z0-9_\-]+\.[a-z0-9]{2,5}$", re.IGNORECASE)

# 匹配纯数字或数字+符号
_PURE_NUMBER_PATTERN = re.compile(r"^[\d\s\.\,\-\+\:\;\%\$\#\@\!\?\*\/\\\(\)\[\]\{\}]+$")

# 匹配代码风格的标识符 (snake_case, camelCase, PascalCase)
_CODE_IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

# 匹配 Ren'Py 内部标记
_RENPY_INTERNAL_PATTERN = re.compile(
    r"^(?:old:|new:|#|nvl |extend |call |jump |label |screen |transform |style |image )",
    re.IGNORECASE
)

# 匹配 Ren'Py 持久化/全局变量访问（persistent.xxx / store.xxx 等）
_RENPY_STORE_PATTERN = re.compile(r"\b(?:persistent|store|config|renpy)\.[\w\.]+\b", re.IGNORECASE)

# 常见 UI 关键词（全小写也应视为可翻译文本）
_UI_KEYWORDS = {
    'start', 'save', 'load', 'settings', 'options', 'config', 'pref',
    'yes', 'no', 'ok', 'back', 'return', 'skip', 'auto', 'menu', 'history',
    'gallery', 'about', 'quit', 'continue', 'retry', 'next', 'previous',
    'exit', 'resume', 'language', 'help', 'pause', 'new', 'game', 'main',
    'title', 'music', 'sound', 'voice', 'play', 'stop', 'on', 'off'
}


def _strip(text: str | None) -> str:
    return (text or "").strip()


def _contains_cjk(text: str) -> bool:
    """检测字符串是否包含中日韩文字符"""
    for char in text:
        # CJK 统一汉字
        if '\u4e00' <= char <= '\u9fff':
            return True
        # CJK 扩展 A
        if '\u3400' <= char <= '\u4dbf':
            return True
        # 日文平假名
        if '\u3040' <= char <= '\u309f':
            return True
        # 日文片假名
        if '\u30a0' <= char <= '\u30ff':
            return True
        # 韩文音节
        if '\uac00' <= char <= '\ud7af':
            return True
    return False


def _contains_translatable_text(text: str) -> bool:
    """
    检测字符串是否包含可翻译的文本内容
    
    基于脚本的核心逻辑：
    1. 移除标签和占位符后检查
    2. 必须包含英文字母或CJK字符
    3. 英文文本需要有大写字母（区分标识符）
    """
    # 移除标签和占位符后检查（逻辑）
    temp = re.sub(r'\{.*?\}', '', text)
    temp = re.sub(r'\[.*?\]', '', temp)
    temp = temp.strip()
    
    if not temp:
        return False

    # 常见 UI 关键词（全小写也应通过）
    if temp.lower() in _UI_KEYWORDS:
        return True
    
    # 包含 CJK 字符 - 直接通过
    if _contains_cjk(temp):
        return True
    
    # 检查是否包含英文字母（逻辑：必须有字母）
    has_alpha = any(c.isalpha() for c in temp)
    if not has_alpha:
        return False  # 没有字母的不是可翻译文本
    
    # 核心逻辑：要求有大写字母（区分正常文本和标识符）
    has_upper = any(c.isupper() for c in temp)
    has_space = ' ' in temp
    
    # 有空格的英文短语很可能是需要翻译的（如 "hello world"）
    if has_space:
        return True
    
    # 有大写字母的词很可能是句子或名字
    if has_upper:
        return True
    
    # 纯小写无空格的可能是标识符，不翻译
    return False


def is_resource_name(text: str | None) -> bool:
    """
    检测是否为资源文件名（不应翻译）
    
    基于脚本的逻辑：检测字符串中是否包含资源文件扩展名
    """
    candidate = _strip(text)
    if not candidate:
        return False
    
    # 完整匹配资源文件名模式
    if _RESOURCE_NAME_PATTERN.match(candidate):
        return True
    
    # 逻辑：字符串中包含资源扩展名也应该跳过
    lower = candidate.lower()
    for ext in _RESOURCE_EXTENSIONS:
        if f'.{ext}' in lower:
            return True
    
    return False


def is_path_like(text: str | None) -> bool:
    """检测是否为路径或文件名格式"""
    candidate = _strip(text)
    if not candidate:
        return False
    lower = candidate.lower()
    # 包含路径分隔符
    if "/" in candidate or "\\" in candidate:
        return True
    # 包含盘符 (C:, D:)
    if ":" in candidate and " " not in candidate:
        return True
    # 短文件名格式
    if _FILENAME_PATTERN.match(lower):
        return True
    # 检测常见资源路径前缀
    path_prefixes = ('images/', 'audio/', 'music/', 'sound/', 'video/', 'gui/', 'fonts/')
    if any(lower.startswith(p) or ('/' + p) in lower for p in path_prefixes):
        return True
    return False


def is_code_identifier(text: str | None) -> bool:
    """检测是否为代码标识符（变量名、函数名等）"""
    candidate = _strip(text)
    if not candidate:
        return False
    
    # 包含 CJK 字符的不是代码标识符
    if _contains_cjk(candidate):
        return False
    
    # 检查是否符合标识符模式
    if not _CODE_IDENTIFIER_PATTERN.match(candidate):
        return False
    
    # 纯大写可能是常量，但也可能是需要翻译的缩写
    if candidate.isupper() and len(candidate) <= 4:
        return False  # 短的大写词如 "OK", "NO" 可能需要翻译
    
    # snake_case 或包含数字的标识符
    if '_' in candidate:
        return True
    
    # 纯小写且没有空格的长词可能是标识符
    if candidate.islower() and len(candidate) > 8:
        return True
    
    # camelCase 或 PascalCase 检测
    # 如果中间有大写字母（不只是开头），很可能是驼峰命名
    if len(candidate) > 1 and any(c.isupper() for c in candidate[1:]):
        # 但如果有空格，则不是
        if ' ' not in candidate:
            return True
    
    return False


def is_renpy_internal(text: str | None) -> bool:
    """检测是否为 Ren'Py 内部标记"""
    candidate = _strip(text)
    if not candidate:
        return False
    
    # 检测 Ren'Py 内部标记模式
    if _RENPY_INTERNAL_PATTERN.match(candidate):
        return True
    
    # 检测 Ren'Py 特殊格式
    if candidate.startswith('#') and not _contains_cjk(candidate):
        return True
    
    return False


def is_pure_punctuation_or_number(text: str | None) -> bool:
    """检测是否为纯标点符号或数字"""
    candidate = _strip(text)
    if not candidate:
        return True
    return bool(_PURE_NUMBER_PATTERN.match(candidate))


def is_placeholder_or_tag(text: str | None) -> bool:
    """检测占位符/标签/标识符是否应该跳过"""
    candidate = _strip(text)
    if not candidate:
        return True
    
    # Ren'Py 内部标记
    if is_renpy_internal(candidate):
        return True
    
    # 纯标点符号或数字
    if is_pure_punctuation_or_number(candidate):
        return True

    # 括号包裹的占位符检测（逻辑）
    # 跳过 [] 或 {} 包裹且没有空格和闭合标签的
    if (candidate.startswith('[') and candidate.endswith(']')) or \
       (candidate.startswith('{') and candidate.endswith('}')):
        if '{/' in candidate or ' ' in candidate:
            pass  # 可能是格式化文本，保留
        else:
            return True

    # 代码标识符检测
    if is_code_identifier(candidate):
        return True

    # 脚本逻辑增强：检测无意义的纯 ASCII 小写字符串
    has_uppercase = any(c.isupper() for c in candidate)
    has_cjk = _contains_cjk(candidate)
    has_only_ascii_letters = all(c.isascii() for c in candidate if c.isalpha())
    
    # 如果只有 ASCII 字母且没有大写，很可能是变量名/标识符
    if has_only_ascii_letters and not has_cjk and not has_uppercase:
        # 有空格的可能是正常文本
        if ' ' not in candidate:
            # 包含下划线或数字的是标识符
            if '_' in candidate or any(c.isdigit() for c in candidate):
                return True
            # 纯小写且是有效标识符的较长字符串
            if len(candidate) > 3 and candidate.isidentifier():
                return True

    return False


def should_skip_text(text: str | None, extra_checks: Iterable = ()) -> bool:
    """
    统一的跳过规则，用于提取和翻译阶段
    
    过滤顺序（参考脚本）：
    1. 空字符串
    2. 资源文件路径/文件名
    3. 占位符和标签
    4. 不包含可翻译内容
    5. 额外自定义检查
    """
    candidate = _strip(text)
    if not candidate:
        return True
    
    # 1. 资源文件检测（优先检测扩展名）
    if is_resource_name(candidate):
        return True
    if is_path_like(candidate):
        return True

    # 额外过滤：明显是持久化/全局变量访问（不应翻译）
    if _RENPY_STORE_PATTERN.search(candidate):
        return True

    # 额外过滤：纯 ASCII 且包含下划线或点号的标识符样式（如 func_name、obj.method）
    if _contains_translatable_text(candidate) is False:
        return True
    if ' ' not in candidate and not _contains_cjk(candidate):
        if '_' in candidate:
            return True
        # 形如 xxx.yyy（无空格）也视为代码/函数名
        if candidate.count('.') >= 1:
            parts = [p for p in candidate.split('.') if p]
            if parts and all(p.isalnum() for p in parts):
                return True
    
    # 2. 占位符和标签检测
    if is_placeholder_or_tag(candidate):
        return True
    
    # 3. 核心逻辑：检查是否包含可翻译内容
    if not _contains_translatable_text(candidate):
        return True
    
    # 4. 额外自定义检查
    for fn in extra_checks or ():
        try:
            if fn(candidate):
                return True
        except Exception:
            continue
    
    return False


# ============================================================
# 统一过滤接口（兼容脚本）
# ============================================================

def filter_extracted_strings(
    strings: List[str],
    preserve_set: Optional[Set[str]] = None,
    extra_checks: Iterable = (),
) -> Tuple[List[str], List[str]]:
    """
    对提取的字符串列表进行统一过滤。
    
    整合了脚本的 filter_extracted_strings 逻辑，
    使用统一的 should_skip_text 规则进行判断。
    
    Args:
        strings: 待过滤的字符串列表
        preserve_set: 保留文本集合（禁止翻译的文本）
        extra_checks: 额外的检查函数列表
        
    Returns:
        Tuple[filtered_list, deleted_list]:
        - filtered_list: 应该翻译的字符串列表（去重排序）
        - deleted_list: 被过滤掉的字符串列表
    """
    filtered_list = []
    deleted_list = []
    preserve_set = preserve_set or set()
    
    for string in strings:
        if not string or not string.strip():
            deleted_list.append(string)
            continue
            
        # 检查是否在保留列表中
        if string.strip() in preserve_set:
            deleted_list.append(string)
            continue
        
        # 使用统一规则判断是否跳过
        if should_skip_text(string, extra_checks):
            deleted_list.append(string)
            continue
        
        # 额外检查：是否包含可翻译内容
        if not _contains_translatable_text(string):
            deleted_list.append(string)
            continue
        
        filtered_list.append(string)
    
    # 去重并排序
    unique_filtered = sorted(list(set(filtered_list)))
    return unique_filtered, deleted_list


def get_skip_reason(text: str | None) -> Optional[str]:
    """
    获取文本被跳过的原因（用于调试和日志）。
    
    Args:
        text: 待检查的文本
        
    Returns:
        跳过原因字符串，如果不应该跳过则返回 None
    """
    candidate = _strip(text)
    if not candidate:
        return "空字符串"
    if is_renpy_internal(candidate):
        return "Ren'Py 内部标记"
    if is_pure_punctuation_or_number(candidate):
        return "纯标点/数字"
    if is_resource_name(candidate):
        return "资源文件名"
    if is_path_like(candidate):
        return "路径格式"
    if is_code_identifier(candidate):
        return "代码标识符"
    if is_placeholder_or_tag(candidate):
        return "占位符/标签"
    if not _contains_translatable_text(candidate):
        return "无可翻译内容"
    return None

