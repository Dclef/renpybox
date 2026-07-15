# -*- coding: utf-8
import io
import random
import sys
import os
import threading
import time
import re
import traceback
import pathlib
import ast

from module.Text.SkipRules import is_path_like, is_resource_name, should_skip_text
from utils.call_game_python import is_python2_from_game_dir
from utils.string_tool import remove_upprintable_chars, EncodeBracketContent, EncodeBrackets, replace_all_blank, \
    replace_unescaped_quotes
from base.LogManager import LogManager

log = LogManager.get()

extract_threads = []

# ========== 新增：特殊模式正则表达式 ==========
# renpy.notify() 调用中的文本
RE_RENPY_NOTIFY = re.compile(
    r'renpy\.notify\s*\(\s*["\']+((?:[^"\'\\]|\\.)*)["\']+'
)

# 字典/列表中的常见需翻译字段
# 匹配 "key": "value" 或 'key': 'value' 模式
RE_DICT_STRING_FIELD = re.compile(
    r'["\'](?:name|description|title|text|message|label|hint|tooltip|caption|content|summary|info|note|prompt|dialog|dialogue|speech)["\']'
    r'\s*:\s*["\']+((?:[^"\'\\]|\\.)*)["\']+'
)
RE_RELAXED_ENGLISH_SOURCE_LINE = re.compile(
    r'^(?!.*#)(?!\s*translate\s+\w+\b)(?=.*\b[A-Za-z]{3,}\b).*$',
    re.IGNORECASE,
)
RE_RELAXED_DOUBLE_QUOTED = re.compile(r'"((?:\\.|[^"\\])*)"')
RE_RELAXED_ENGLISH_WORD = re.compile(r'\b[A-Za-z]{3,}\b')
RE_RELAXED_FUNCTION_CALL_PREFIX = re.compile(r'[A-Za-z_][A-Za-z0-9_\.]*\($')
# ============================================

# 检测字符串是否包含中文字符（或其他CJK字符）
def contains_cjk(s):
    """检测字符串是否包含中日韩文字符"""
    for char in s:
        # CJK统一汉字范围
        if '\u4e00' <= char <= '\u9fff':
            return True
        # CJK扩展A
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

lock = threading.Lock()

num = 0
get_extracted_threads = []
get_extracted_lock = threading.Lock()
get_extracted_set_list = []

# 常见 UI 文本白名单（短词也强制保留）
UI_KEYWORDS = {
    'start', 'save', 'load', 'settings', 'options', 'config', 'pref',
    'yes', 'no', 'ok', 'back', 'return', 'skip', 'auto', 'menu', 'history',
    'gallery', 'about', 'quit', 'continue', 'retry', 'next', 'previous',
    'exit', 'resume', 'language', 'help', 'pause', 'new', 'game', 'main',
    'title', 'music', 'sound', 'voice', 'play', 'stop', 'on', 'off',
    'q', 'a', 'adv', 'nvl', 'all', 'none'
}

BUILTIN_UI_DIRS = {"base_box"}
BUILTIN_UI_FILES = {
    "common.rpy",
    "screens.rpy",
    "common_box.rpy",
    "screens_box.rpy",
    "style_box.rpy",
}


def is_builtin_ui_file(path: str, tl_dir: str | None = None) -> bool:
    """检查是否为内置 UI/字体包文件（base_box 目录及常见模板文件）。"""
    try:
        name = os.path.basename(path).lower()
        if name in BUILTIN_UI_FILES:
            return True
        check_path = path
        if tl_dir:
            try:
                check_path = os.path.relpath(path, tl_dir)
            except Exception:
                check_path = path
        parts = [p for p in re.split(r"[\\\\/]+", str(check_path)) if p]
        return any(part.lower() in BUILTIN_UI_DIRS for part in parts)
    except Exception:
        return False


def is_ui_keyword(text: str) -> bool:
    """判断是否为常见 UI 关键词（忽略大小写和首尾空白）"""
    return text.strip().lower() in UI_KEYWORDS


def iter_relaxed_single_quoted_literals(line_content: str):
    """遍历双引号外、可独立成立的单引号文本。"""
    control_match = re.match(r'^\s*(?:if|elif|while)\b.*?:\s*(.*)$', line_content)
    if control_match:
        scan_line = control_match.group(1)
        if not scan_line or scan_line.lstrip().startswith('#'):
            return
    else:
        scan_line = line_content

    in_double_quote = False
    quote_start = None
    escaped = False

    for index, char in enumerate(scan_line):
        if escaped:
            escaped = False
            continue
        if char == '\\':
            escaped = True
            continue
        if char == '"' and quote_start is None:
            in_double_quote = not in_double_quote
            continue
        if char != "'" or in_double_quote:
            continue

        prev_char = scan_line[index - 1] if index > 0 else ''
        next_char = scan_line[index + 1] if index + 1 < len(scan_line) else ''
        if prev_char.isalpha() and next_char.isalpha():
            continue

        if quote_start is None:
            if not next_char or next_char.isspace() or next_char in ",:)]}":
                continue
            if prev_char.isalnum() or (prev_char and prev_char in "_)]}\""):
                continue
            quote_start = index
            continue

        if not prev_char or prev_char.isspace() or prev_char in "([{,:":
            continue
        if next_char.isalnum() or next_char == '_':
            continue
        yield scan_line[quote_start + 1:index]
        quote_start = None

def extract_relaxed_english_line_literals(line_content: str, filter_length: int) -> set[str]:
    """按宽松英文行规则补抓引号文本。

    说明：
    - 对应用户提供的规则：`^(?!.*#)^(?!.*translate schinese)(?=.*\\b[A-Za-z]{3,}\\b).*$`
    - 实现时将 `translate schinese` 泛化为 `translate <lang>` 头
    - 只提取引号内容，不把整行代码直接当作文本
    """
    stripped = line_content.strip()
    if not stripped:
        return set()
    if RE_RELAXED_ENGLISH_SOURCE_LINE.match(stripped) is None:
        return set()

    result = set()

    def maybe_add_candidate(text: str):
        candidate = text.strip()
        if not candidate:
            return
        if RE_RELAXED_ENGLISH_WORD.search(candidate) is None:
            return

        cmp_text = candidate.lower()
        if is_path_or_dir_string(cmp_text) or is_resource_filename(cmp_text):
            return
        if should_skip_text(candidate):
            return
        if re.search(r'\[\s*\w+\.\w+.*?\]', candidate):
            return

        effective_filter_length = filter_length
        if contains_cjk(candidate):
            effective_filter_length = max(2, filter_length // 3)
        if not is_ui_keyword(candidate):
            if len(replace_all_blank(candidate)) < effective_filter_length:
                return

        result.add(text)

    for match in RE_RELAXED_DOUBLE_QUOTED.finditer(line_content):
        prefix = line_content[:match.start()].rstrip()
        if RE_RELAXED_FUNCTION_CALL_PREFIX.search(prefix):
            continue
        text = replace_unescaped_quotes(match.group(1))
        text = text.replace("\\'", "'")
        maybe_add_candidate(text)

    for text in iter_relaxed_single_quoted_literals(line_content):
        text = replace_unescaped_quotes(text)
        text = text.replace("\\'", "'")
        maybe_add_candidate(text)

    return result


class ExtractTlThread(threading.Thread):
    def __init__(self, p, is_py2, is_remove_repeat_only = False):
        threading.Thread.__init__(self)
        self.p = p
        self.is_py2 = is_py2
        self.is_remove_repeat_only = is_remove_repeat_only

    def run(self):
        if not self.is_remove_repeat_only:
            extracted = ExtractFromFile(self.p, False, 9999, False, self.is_py2)
        else:
            remove_repeat_for_file(self.p)
            f = io.open(self.p, 'r', encoding='utf-8')
            _lines = f.readlines()
            f.close()
            f = io.open(self.p, 'w', encoding='utf-8')
            _lines = get_remove_consecutive_empty_lines(_lines)
            f.writelines(_lines)
            f.close()
            extracted = None
        get_extracted_lock.acquire()
        get_extracted_set_list.append((self.p, extracted))
        get_extracted_lock.release()


def remove_repeat_extracted_from_tl(tl_dir, is_py2, cross_file_dedup=True):
    """
    去除 tl 目录中的重复翻译条目
    
    Args:
        tl_dir: 翻译目录路径
        is_py2: 是否为 Python 2 版本的游戏
        cross_file_dedup: 是否进行跨文件去重（默认开启）
    """
    p = tl_dir
    if p[len(p) - 1] != '/' and p[len(p) - 1] != '\\':
        p = p + '/'
    paths = os.walk(p, topdown=False)
    global get_extracted_threads
    global get_extracted_set_list
    global get_extracted_lock
    cnt = 0
    get_extracted_set_list.clear()
    
    # 收集所有 rpy 文件路径
    rpy_files = []
    for path, dir_lst, file_lst in paths:
        for file_name in file_lst:
            i = os.path.join(path, file_name)
            if not file_name.endswith("rpy"):
                continue
            if is_builtin_ui_file(i, p):
                continue
            rpy_files.append(i)
    
    # 第一步：对每个文件执行去重（单文件内去重）和提取
    # 注意：这一步会修改文件内容，必须先执行
    for file_path in rpy_files:
        t = ExtractTlThread(file_path, is_py2)
        get_extracted_threads.append(t)
        cnt = cnt + 1
        t.start()
    
    while True:
        threads_len = len(get_extracted_threads)
        if threads_len > 0:
            for t in get_extracted_threads:
                if t.is_alive():
                    t.join()
                get_extracted_threads.remove(t)
        else:
            break

    # 第二步：收集所有文件中的 old/new 对，用于跨文件去重
    # 同时收集 dialogue 块中的原文，用于删除 strings 中的冗余
    global_old_entries = {}  # {old_text: [(file_path, first_occurrence_line), ...]}
    block_originals = set()  # Legacy scan result; intentionally excluded from strings de-duplication.
    
    if cross_file_dedup:
        for file_path in rpy_files:
            try:
                with io.open(file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                in_dialogue_block = False
                for idx, line in enumerate(lines):
                    line_stripped = line.strip()
                    
                    # 检查是否进入/离开 dialogue 块
                    if line_stripped.startswith('translate ') and line_stripped.endswith(':'):
                        if 'strings:' not in line_stripped:
                            in_dialogue_block = True
                        else:
                            in_dialogue_block = False
                        continue
                    
                    # 如果在 dialogue 块中，提取原文（通常在注释中）
                    if in_dialogue_block:
                        if line_stripped.startswith('#'):
                            # 提取双引号中的内容，一行可能有多个（如名字+对白），都提取
                            matches = re.findall(r'"((?:\\.|[^"])*)"', line_stripped)
                            for m in matches:
                                txt = m.replace('\\"', '"').replace("\\'", "'")
                                block_originals.add(txt)
                        # 如果遇到非空且非注释且无缩进的行，说明块可能结束了（虽然 translate 块通常有缩进，但这作为防御）
                        if line_stripped and not line.startswith(' ') and not line_stripped.startswith('#'):
                            in_dialogue_block = False

                    # 收集 strings 块中的 old 条目
                    if line_stripped.startswith('old '):
                        # 提取 old 文本内容
                        old_text = line_stripped.strip()
                        # 去除 old "..." 的外层引号和 old 前缀
                        m = re.match(r'old\s+"((?:\\.|[^"])*)"', old_text)
                        if m:
                            content = m.group(1).replace('\\"', '"').replace("\\'", "'")
                            if content not in global_old_entries:
                                global_old_entries[content] = []
                            global_old_entries[content].append((file_path, idx))
                        else:
                            # 尝试匹配单引号
                            m = re.match(r"old\s+'((?:\\.|[^'])*)'", old_text)
                            if m:
                                content = m.group(1).replace("\\'", "'")
                                if content not in global_old_entries:
                                    global_old_entries[content] = []
                                global_old_entries[content].append((file_path, idx))
            except Exception:
                continue
    
    # 第三步：跨文件去重
    if cross_file_dedup:
        duplicates_to_remove = {}  # {file_path: set(line_indices_to_remove)}
        
        for old_text, occurrences in global_old_entries.items():
            # 情况1：如果该文本已经存在于 dialogue 翻译块中，删除 strings 中的所有条目
            # 情况2：strings 中出现多次，保留第一次
            if len(occurrences) > 1:
                # 保留第一次出现，其余标记为待删除
                for file_path, line_idx in occurrences[1:]:
                    if file_path not in duplicates_to_remove:
                        duplicates_to_remove[file_path] = set()
                    # 标记 old 行 (new 行将在删除阶段动态查找)
                    duplicates_to_remove[file_path].add(line_idx)
        
        # 执行跨文件去重删除
        for file_path, lines_to_remove in duplicates_to_remove.items():
            try:
                with io.open(file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                # 删除标记的行（置空）
                modified = False
                # 倒序处理，虽然对于置空操作不是严格必须的，但习惯上更好
                sorted_indices = sorted(list(lines_to_remove), reverse=True)
                
                for idx in sorted_indices:
                    if 0 <= idx < len(lines):
                        # 删除 old 行
                        lines[idx] = ''
                        modified = True
                        
                        # 向后寻找并删除对应的 new 行 (包括中间的注释和空行)
                        next_idx = idx + 1
                        while next_idx < len(lines):
                            next_line_stripped = lines[next_idx].strip()
                            if next_line_stripped.startswith('new '):
                                lines[next_idx] = ''
                                break
                            elif next_line_stripped.startswith('#') or next_line_stripped == '':
                                # 如果是注释或空行，也一并删除
                                lines[next_idx] = ''
                                next_idx += 1
                            else:
                                # 遇到其他内容（如新的 block 或其他指令），停止
                                break
                
                if modified:
                    # 清理连续空行后写回
                    lines = get_remove_consecutive_empty_lines(lines)
                    with io.open(file_path, 'w', encoding='utf-8') as f:
                        f.writelines(lines)
            except Exception as e:
                log.warning(f'跨文件去重失败 {file_path}: {e}')
    
    get_extracted_set_list.clear()
    return

def get_remove_consecutive_empty_lines(lines):
    last_line_empty = False
    new_lines = []
    for line in lines:
        if line.strip() == '':
            if not last_line_empty:
                new_lines.append(line)
            last_line_empty = True
        else:
            new_lines.append(line)
            last_line_empty = False
    return new_lines


def remove_repeat_for_file(p):
    """
    移除单个文件内的重复翻译条目
    
    去重逻辑：
    1. 在同一文件内，相同的 old/new 对只保留第一次出现
    2. 移除空的 translate 块
    3. 清理连续空行
    """
    try:
        f = io.open(p, 'r', encoding='utf-8')
        lines = f.readlines()
        f.close()
    except Exception as e:
        log.error(f'读取文件失败 {p}: {e}')
        return
    
    # 使用 (old_text, new_text) 元组作为唯一标识
    exist_pairs = set()
    is_removed = False
    is_empty_translate = True
    start_translate_block_line = -1
    lines_to_remove = set()
    
    i = 0
    while i < len(lines):
        line = lines[i].rstrip('\n')
        
        # 检测 translate 块的开始/结束
        if (line.startswith('translate ') and line.endswith('strings:')) or i == len(lines) - 1:
            if start_translate_block_line != -1:
                if is_empty_translate:
                    # 移除空的 translate 块
                    end_idx = i if i < len(lines) - 1 else i + 1
                    for idx in range(start_translate_block_line, end_idx):
                        lines_to_remove.add(idx)
                    is_removed = True
                is_empty_translate = True
            start_translate_block_line = i
            i += 1
            continue
        
        # 检测 old/new 对
        if line.strip().startswith('old '):
            old_text = line.strip()
            
            # 创建唯一标识 - 只使用 old_text，忽略 translation 以避免同一原文有多个不同翻译条目
            # 优先保留文件前面的条目（通常是原有翻译），后面的（通常是新提取的）将被视为重复
            pair_key = old_text
            
            # 寻找对应的 new 行
            new_line_idx = -1
            scan_idx = i + 1
            while scan_idx < len(lines):
                scan_line = lines[scan_idx].strip()
                if scan_line.startswith('new '):
                    new_line_idx = scan_idx
                    break
                elif scan_line.startswith('old ') or scan_line.startswith('translate '):
                    # 遇到下一个块的开始，说明当前块没有 new
                    break
                scan_idx += 1

            if pair_key in exist_pairs:
                # 重复条目，标记删除
                # 同时删除前面可能的注释行
                if i > 0 and lines[i - 1].lstrip().startswith('#'):
                    lines_to_remove.add(i - 1)
                lines_to_remove.add(i)
                
                # 如果找到了对应的 new 行，删除它以及中间的杂项
                if new_line_idx != -1:
                    for k in range(i + 1, new_line_idx + 1):
                        lines_to_remove.add(k)
                
                is_removed = True
            else:
                exist_pairs.add(pair_key)
                is_empty_translate = False
            
            # 移动到下一个 block
            if new_line_idx != -1:
                i = new_line_idx + 1
            else:
                i += 1
            continue
        
        # 检测非空内容
        if len(line) > 4 and not line.lstrip().startswith('#'):
            if not line.startswith('    old "old:') and not line.startswith('    new "new:'):
                is_empty_translate = False
        
        i += 1
    
    # 执行删除
    if is_removed and lines_to_remove:
        for idx in sorted(lines_to_remove, reverse=True):
            if 0 <= idx < len(lines):
                lines[idx] = ''
        
        lines = get_remove_consecutive_empty_lines(lines)
        try:
            f = io.open(p, 'w', encoding='utf-8')
            f.writelines(lines)
            f.close()
        except Exception as e:
            log.error(f'写入文件失败 {p}: {e}')


class extractThread(threading.Thread):
    def __init__(self, threadID, p, tl_name, dirs, tl_dir, is_open_filter, filter_length, is_gen_empty,
                 is_skip_underline):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.p = p
        self.tl_name = tl_name
        self.dirs = dirs
        self.tl_dir = tl_dir
        self.is_open_filter = is_open_filter
        self.filter_length = filter_length
        self.is_gen_empty = is_gen_empty
        self.is_skip_underline = is_skip_underline

    def run(self):
        try:
            if self.tl_dir is not None and os.path.exists(self.tl_dir):
                self.tl_dir = self.tl_dir.rstrip('/')
                self.tl_dir = self.tl_dir.rstrip('\\')
                if self.tl_name is not None and len(self.tl_name) > 0:
                    ori_tl = os.path.basename(self.tl_dir)
                    # 当传入的是 tl 目录本身时（未包含语言子目录），自动创建 tl/<lang>
                    if ori_tl.lower() == "tl":
                        self.tl_dir = os.path.join(self.tl_dir, self.tl_name)
                    else:
                        self.tl_dir = self.tl_dir[:-len(ori_tl)] + self.tl_name
                if not os.path.exists(self.tl_dir):
                    os.makedirs(self.tl_dir, exist_ok=True)
                log.info(self.tl_dir + ' begin extract!')
                ExtractAllFilesInDir(self.tl_dir, self.is_open_filter, self.filter_length, self.is_gen_empty,
                                     self.is_skip_underline)
            else:
                if self.p is not None:
                    self.p = self.p.replace('\\', '/')
                    log.info(self.p + ' begin extract!')
                    ExtractWriteFile(self.p, self.tl_name, self.is_open_filter, self.filter_length, self.is_gen_empty,
                                     set(), self.is_skip_underline)
                    remove_repeat_for_file(self.p)
                if self.dirs is not None:
                    global_e = set()
                    for _dir in self.dirs:
                        _dir = _dir.replace('\\', '/')
                        _dir = _dir.rstrip('/')
                        log.info(_dir + ' begin extract!')
                        paths = os.walk(_dir, topdown=False)
                        for path, dir_lst, file_lst in paths:
                            for file_name in file_lst:
                                i = os.path.join(path, file_name)
                                if not file_name.endswith("rpy"):
                                    continue
                                ret_e = ExtractWriteFile(i, self.tl_name, self.is_open_filter, self.filter_length,
                                                         self.is_gen_empty, global_e, self.is_skip_underline)
                                remove_repeat_for_file(i)
                                global_e = global_e | ret_e

        except Exception as e:
            msg = traceback.format_exc()
            log.error(msg)


def is_path_or_dir_string(_string):
    """兼容旧接口：委托统一的路径检测规则。"""
    return is_path_like(_string)


def is_resource_filename(_string):
    """兼容旧接口：委托统一的资源名检测规则。"""
    return is_resource_name(_string)


def ExtractFromFile(p, is_open_filter, filter_length, is_skip_underline, is_py2, skip_translate_block=False, remove_duplicates=True):
    if remove_duplicates:
        remove_repeat_for_file(p)
    e = set()
    # 仅去重路径需要写权限；静态补充抽取只读取游戏源码，必须兼容只读文件。
    open_mode = 'r+' if remove_duplicates else 'r'
    f = io.open(p, open_mode, encoding='utf-8')
    _read = f.read()
    f.close()
    # print(_read)
    _read_line = _read.split('\n')
    is_in_condition_switch = False
    is_in__p = False
    is_in_translate_block = False
    translate_block_indent = 0
    p_content = ''
    for index, line_content in enumerate(_read_line):
        indent_level = len(line_content) - len(line_content.lstrip(' '))
        stripped_line = line_content.strip()

        if skip_translate_block:
            # 先检查是否离开 translate 块
            if is_in_translate_block:
                if stripped_line and indent_level <= translate_block_indent:
                    is_in_translate_block = False
                else:
                    # 仍在 translate 块中，直接跳过
                    continue

            # 进入 translate 块：translate xxx strings:
            if stripped_line.startswith('translate ') and stripped_line.endswith('strings:'):
                is_in_translate_block = True
                translate_block_indent = indent_level
                continue

        # ========== 新增：特殊模式提取 ==========
        def is_valid_special_text(text, filter_len):
            # 1. 检查是否包含技术性插值 [xx.xx]
            if re.search(r'\[\s*\w+\.\w+.*?\]', text):
                return False
            # 2. 检查长度 (UI关键词除外)
            if not is_ui_keyword(text):
                effective_len = filter_len
                if contains_cjk(text):
                    effective_len = max(2, filter_len // 3)
                if len(text) < effective_len:
                    return False
            return True

        # 提取 renpy.notify() 中的文本
        notify_matches = RE_RENPY_NOTIFY.findall(line_content)
        for notify_text in notify_matches:
            if notify_text.strip():
                notify_text = replace_unescaped_quotes(notify_text)
                notify_text = notify_text.replace("\\'", "'")
                if is_valid_special_text(notify_text, filter_length):
                    e.add(notify_text)
        
        # 提取字典字段中的文本 (name, description 等)
        dict_matches = RE_DICT_STRING_FIELD.findall(line_content)
        for dict_text in dict_matches:
            if dict_text.strip():
                dict_text = replace_unescaped_quotes(dict_text)
                dict_text = dict_text.replace("\\'", "'")
                if is_valid_special_text(dict_text, filter_length):
                    e.add(dict_text)
        # ==========================================

        if 'ConditionSwitch(' in line_content:
            if not line_content.strip().endswith(')'):
                is_in_condition_switch = True
            continue
        if _read_line[-1] == ')':
            is_in_condition_switch = False
            continue
        if is_in_condition_switch:
            continue

        cmp_line_content = remove_upprintable_chars(stripped_line)
        if cmp_line_content.startswith('#') or len(stripped_line) == 0:
            continue

        # 宽松英文行补抓：只补抓该行里的引号文本，用于兜住常规规则漏掉的场景。
        if is_open_filter:
            for extra_text in extract_relaxed_english_line_literals(line_content, filter_length):
                e.add(extra_text)

        if '_p("""' in line_content:
            is_in__p = True
            position = line_content.find('_p("""')
            p_content = line_content[position:] + '\n'
            continue

        if is_in__p:
            sep = '\n'
            if is_py2:
                sep = '\\n'
            p_content = p_content + line_content + sep
            if line_content.endswith('""")'):
                p_content = p_content.rstrip(sep)
                if is_py2:
                    p_content = p_content.strip()[6:-4]
                    p_content = p_content.rstrip('\n').replace('\n', '\\n')
                # log_print(p_content)
                if filter_length != 9999:
                    log.debug(f'Found _p() in {p}:{index + 1}')
                e.add(p_content)
                is_in__p = False
                p_content = ''
            continue

        if is_open_filter:
            if cmp_line_content.startswith('label '):
                continue
            if line_content.strip().startswith('default '):
                continue
        # log.debug(line_content)
        is_menu_option = bool(re.match(r'^\s*"[^"]*"\s*(?:\([^)]*\)|\s+if\s+.*)?\s*:\s*$', line_content))
        is_add = False
        d = EncodeBracketContent(line_content, '"', '"')
        if 'oriList' in d.keys() and len(d['oriList']) > 0:
            for i in d['oriList']:
                if len(i) > 2:
                    strip_i = ''.join(i)
                    d2 = EncodeBrackets(i)

                    for j in (d2['en_1']):
                        strip_i = strip_i.replace(j, '')
                    for j in (d2['en_2']):
                        strip_i = strip_i.replace(j, '')
                    for j in (d2['en_3']):
                        strip_i = strip_i.replace(j, '')

                    diff_len = len(i) - len(strip_i)
                    _strip_i = replace_all_blank(strip_i)
                    cmp_i = i.lower().strip('"')
                    skip = False
                    if cmp_i.startswith('#'):
                        skip = True
                    # 只要有下划线就不提取，但如果包含中文字符则仍然提取
                    if is_skip_underline and strip_i.find('_') > -1 and not contains_cjk(strip_i):
                        skip = True
                    # if not line_content.strip().startswith('text ') or line_content.strip().find(i) != 5:
                    #     skip = True
                    if is_path_or_dir_string(cmp_i):
                        skip = True
                    # 跳过资源文件名
                    if is_resource_filename(cmp_i):
                        skip = True
                    if skip and not is_ui_keyword(strip_i.strip('"')):
                        continue
                    i = i[1:-1]
                    i = replace_unescaped_quotes(i)
                    i = i.replace("\\'", "'")
                    # 检查是否包含技术性插值 [xx.xx]
                    has_tech_interpolation = bool(re.search(r'\[\s*\w+\.\w+.*?\]', strip_i))
                    
                    if not has_tech_interpolation and (is_open_filter or is_ui_keyword(strip_i.strip('"'))):
                        # 如果包含中文字符，放宽长度限制（中文一个字相当于多个英文字符）
                        effective_filter_length = filter_length
                        if contains_cjk(strip_i):
                            effective_filter_length = max(2, filter_length // 3)  # 中文长度限制降为1/3
                        if not is_menu_option and not is_ui_keyword(strip_i.strip('"')):
                            if len(_strip_i) < effective_filter_length:
                                continue
                        e.add(i)
                        is_add = True
                    else:
                        e.add(i)
                        is_add = True
        if is_add:
            continue
        single_quote_line = d.get('encoded', line_content)
        control_match = re.match(r'^\s*(?:if|elif|while)\b.*?:\s*(.*)$', single_quote_line)
        if control_match:
            single_quote_line = control_match.group(1)
            if not single_quote_line or single_quote_line.lstrip().startswith('#'):
                continue
        d = EncodeBracketContent(single_quote_line, "'", "'")
        if 'oriList' in d.keys() and len(d['oriList']) > 0:
            for i in d['oriList']:
                if len(i) > 2:
                    strip_i = ''.join(i)
                    d2 = EncodeBrackets(i)

                    for j in (d2['en_1']):
                        strip_i = strip_i.replace(j, '')
                    for j in (d2['en_2']):
                        strip_i = strip_i.replace(j, '')
                    for j in (d2['en_3']):
                        strip_i = strip_i.replace(j, '')

                    diff_len = len(i) - len(strip_i)
                    _strip_i = replace_all_blank(strip_i)
                    cmp_i = i.lower().strip("'")
                    skip = False
                    if cmp_i.startswith('#'):
                        skip = True
                    # 只要有下划线就不提取，但如果包含中文字符则仍然提取
                    if is_skip_underline and _strip_i.find('_') > -1 and not contains_cjk(strip_i):
                        skip = True
                    # if not line_content.strip().startswith('text ') or line_content.strip().find(i) != 5:
                    #     skip = True
                    if is_path_or_dir_string(cmp_i):
                        skip = True
                    # 跳过资源文件名
                    if is_resource_filename(cmp_i):
                        skip = True
                    if skip and not is_ui_keyword(strip_i.strip("'")):
                        continue
                    i = i[1:-1]
                    i = replace_unescaped_quotes(i)
                    i = i.replace("\\'", "'")
                    # 检查是否包含技术性插值 [xx.xx]
                    has_tech_interpolation = bool(re.search(r'\[\s*\w+\.\w+.*?\]', strip_i))

                    if not has_tech_interpolation and (is_open_filter or is_ui_keyword(strip_i.strip("'"))):
                        # 如果包含中文字符，放宽长度限制（中文一个字相当于多个英文字符）
                        effective_filter_length = filter_length
                        if contains_cjk(strip_i):
                            effective_filter_length = max(2, filter_length // 3)  # 中文长度限制降为1/3
                        if not is_ui_keyword(strip_i.strip("'")):
                            if len(_strip_i) < effective_filter_length:
                                continue
                        e.add(i)
                    else:
                        e.add(i)
    return e


def CreateEmptyFileIfNotExsit(p):
    if (p[len(p) - 1] != '/' and p[len(p) - 1] != '\\'):
        p = p + '/'

    normalized_p = p.replace("\\", "/").rstrip("/")
    tl_name = ""
    tl_idx = normalized_p.rfind("/tl/")
    if tl_idx != -1:
        tl_name = normalized_p[tl_idx + 4:].split("/", 1)[0].strip().lower()

    source_root = os.path.abspath(os.path.join(p, "..", ".."))
    paths = os.walk(source_root, topdown=False)

    for path, dir_lst, file_lst in paths:
        for file_name in file_lst:
            i = os.path.join(path, file_name)
            rel_path = os.path.relpath(i, source_root)
            rel_norm = rel_path.replace("\\", "/").lstrip("/")
            first_part = rel_norm.split("/", 1)[0].strip().lower() if rel_norm else ""
            if first_part == "tl" or (tl_name and first_part == tl_name):
                continue
            if (file_name.endswith("rpy") == False):
                continue
            if is_builtin_ui_file(i):
                continue
            target = os.path.join(p, rel_path)
            targetDir = os.path.dirname(target)
            if os.path.exists(targetDir) == False:
                pathlib.Path(targetDir).mkdir(parents=True, exist_ok=True)
            if os.path.isfile(target) == False:
                open(target, 'w').close()


def WriteExtracted(p, extractedSet, is_open_filter, filter_length, is_gen_empty, is_skip_underline, is_py2):
    # Load Text Preserve config
    from module.Config import Config
    config = Config().load()
    preserve_set = set()
    if config.text_preserve_enable:
        for item in config.text_preserve_data:
            if isinstance(item, dict):
                preserve_set.add(item.get("src", "").strip())
            elif isinstance(item, str):
                preserve_set.add(item.strip())

    if (p[len(p) - 1] != '/' and p[len(p) - 1] != '\\'):
        p = p + '/'
    index = p.rfind('tl\\')
    if index == -1:
        index = p.rfind('tl/')
    if (index == -1):
        log.warning(p + ' no tl found!')
        return
    index2 = p.find('\\', index + 3)
    if index2 == -1:
        index2 = p.find('/', index + 3)
    if (index2 == -1):
        log.warning(p + ' no tl found2!')
        return
    tl = p[index + 3:index2]
    tl_lower = tl.lower()
    paths = os.walk(p, topdown=False)
    for path, dir_lst, file_lst in paths:
        for file_name in file_lst:
            i = os.path.join(path, file_name)
            if (file_name.endswith("rpy") == False):
                continue
            if is_builtin_ui_file(i, p):
                continue
            rel_path = os.path.relpath(i, p)
            rel_norm = rel_path.replace("\\", "/").lstrip("/")
            first_part = rel_norm.split("/", 1)[0].strip().lower() if rel_norm else ""
            if first_part == "tl" or first_part == tl_lower:
                continue
            target = os.path.normpath(os.path.join(p, '..', '..', rel_path))
            if os.path.isfile(target) == False:
                log.warning(target + " not exists skip!")
                continue

            e = ExtractFromFile(target, is_open_filter, filter_length, is_skip_underline, is_py2, True)
            eDiff = e - extractedSet
            
            # Filter preserved text
            if preserve_set:
                eDiff = {x for x in eDiff if x.strip() not in preserve_set}
            
            # 使用统一的 should_skip_text 进行最终过滤（逻辑）
            eDiff = {x for x in eDiff if not should_skip_text(x)}
            
            if len(eDiff) > 0:
                f = io.open(i, 'a+', encoding='utf-8')
                f.write('\ntranslate ' + tl + ' strings:\n\n')
                for j in eDiff:
                    if not j.startswith('_p("""') and not j.endswith('""")'):
                        j = '"' + j + '"'
                    if not is_gen_empty:
                        writeData = '    old ' + j + '\n    new ' + j + '\n'
                    else:
                        writeData = '    old ' + j + '\n    new ' + '""' + '\n'
                    f.write(writeData + '\n')
                f.close()
            extractedSet = e | extractedSet
            log.info(target + ' extract success!')


def GetHeaderPath(p):
    dic = dict()
    index = p.rfind('game/')
    if index == -1:
        index = p.rfind('game//')
    if index == -1:
        dic['header'] = ''
        return dic
    header = p[:index]
    if os.path.exists(header + 'renpy'):
        dic['header'] = header + 'game/'
        dirname = os.path.dirname(p) + '/'
        subPath = dirname[len(header) + len('game/'):]
        dic['subPath'] = subPath
        dic['fileName'] = os.path.basename(p)
        return dic
    else:
        dic['header'] = ''
        return dic


def ExtractWriteFile(p, tl_name, is_open_filter, filter_length, is_gen_empty, global_e, is_skip_underline):
    dic = GetHeaderPath(p)
    header = dic['header']
    if (header == ''):
        log.warning(p + ' not in game path!')
        return set()
    subPath = dic['subPath']
    fileName = dic['fileName']
    targetDir = header + 'tl/' + tl_name + '/' + subPath
    target = targetDir + fileName
    if (os.path.exists(targetDir) == False):
        try:
            os.makedirs(targetDir)
        except FileExistsError:
            pass
    if (os.path.isfile(target) == False):
        open(target, 'w').close()
    is_py2 = is_python2_from_game_dir(targetDir.rstrip('/').rstrip('\\') + '/../../../')
    e = ExtractFromFile(p, is_open_filter, filter_length, is_skip_underline, is_py2, True)
    extractedSet = ExtractFromFile(target, False, 9999, is_skip_underline, is_py2)
    eDiff = e - extractedSet
    
    # 使用统一的 should_skip_text 进行最终过滤（逻辑）
    eDiff = {x for x in eDiff if not should_skip_text(x)}
    
    if len(eDiff) > 0:
        f = io.open(target, 'a+', encoding='utf-8')
        f.write('\ntranslate ' + tl_name + ' strings:\n\n')
        for j in eDiff:
            if j in global_e:
                continue
            if not j.startswith('_p("""') and not j.endswith('""")'):
                j = '"' + j + '"'
            if not is_gen_empty:
                writeData = '    old ' + j + '\n    new ' + j + '\n'
            else:
                writeData = '    old ' + j + '\n    new ' + '""' + '\n'
            f.write(writeData + '\n')
        f.close()
    global_e = global_e | e
    global_e = global_e | extractedSet
    log.info(target + ' extracted success!')
    return global_e


def collect_static_menu_strings(game_dir):
    """Collect menu-choice text and prefer its first real source location."""
    from pathlib import Path

    root = Path(game_dir)
    source_root = root / "game" if (root / "game").is_dir() else root
    result = {}
    # 菜单项既可能带选择参数，也可能由 `if` 条件保护；两种形式都必须
    # 进入 strings 翻译，否则同文对话块会让菜单文本被误判为已覆盖。
    menu_choice_re = re.compile(
        r'^\s*(?P<quote>["\'])(?P<text>(?:\\.|(?!(?P=quote)).)*)'
        r'(?P=quote)\s*(?:\([^)]*\))?\s*(?:if\s+.+?)?\s*:\s*(?:#.*)?$'
    )
    if not source_root.is_dir():
        return result
    for source_file in sorted(source_root.rglob("*.rpy"), key=lambda item: item.as_posix()):
        relative = source_file.relative_to(source_root)
        if relative.parts and relative.parts[0].lower() == "tl":
            continue
        try:
            lines = source_file.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue
        for line in lines:
            match = menu_choice_re.match(line)
            if not match:
                continue
            quote = match.group("quote")
            raw = match.group("text")
            try:
                text = ast.literal_eval(f"{quote}{raw}{quote}")
            except Exception:
                text = raw.replace('\\"', '"').replace("\\'", "'")
            if text:
                result.setdefault(text, relative.as_posix())
    return result


def collect_static_source_strings(game_dir, is_open_filter=True, filter_length=4, is_skip_underline=False):
    """收集可写入 translate strings 的静态源码文本，同文仅保留排序后的首次出现。"""
    from pathlib import Path

    root = Path(game_dir)
    source_root = root / "game" if (root / "game").is_dir() else root
    candidates = {}
    if not source_root.is_dir():
        return candidates

    is_py2 = is_python2_from_game_dir(str(source_root))
    menu_map = collect_static_menu_strings(game_dir)
    menu_candidates = set(menu_map)
    for source_file in sorted(source_root.rglob("*.rpy"), key=lambda item: item.as_posix()):
        try:
            relative = source_file.relative_to(source_root)
        except ValueError:
            continue
        if relative.parts and relative.parts[0].lower() == "tl":
            continue
        try:
            # 源码扫描不可调用带写入前处理的旧接口，避免修改游戏原文。
            texts = ExtractFromFile(
                str(source_file), is_open_filter, filter_length, is_skip_underline,
                is_py2, True, False,
            )
        except Exception:
            continue
        # 菜单选项必须使用 strings 翻译；即使同文先作为对话出现，也应以
        # 真实菜单位置为准，并保留简短选项文本。
        for text in sorted(texts):
            text = text.replace('\\"', '"').replace("\\'", "'")
            if text and not should_skip_text(text):
                candidates.setdefault(text, relative.as_posix())
    candidates.update(menu_map)
    return candidates


def ExtractAllFilesInDir(dirName, is_open_filter, filter_length, is_gen_empty, is_skip_underline):
    is_py2 = is_python2_from_game_dir(dirName + '/../../../')
    CreateEmptyFileIfNotExsit(dirName)
    WriteExtracted(dirName, set(), is_open_filter, filter_length, is_gen_empty, is_skip_underline, is_py2)
    log.info('start removing repeated extraction, please waiting...')
    remove_repeat_extracted_from_tl(dirName, is_py2)
    cnt = 0
    get_extracted_set_list.clear()
    p = dirName
    if p[len(p) - 1] != '/' and p[len(p) - 1] != '\\':
        p = p + '/'
    paths = os.walk(p, topdown=False)
    for path, dir_lst, file_lst in paths:
        for file_name in file_lst:
            i = os.path.join(path, file_name)
            if file_name.endswith("rpy") == False:
                continue
            if is_builtin_ui_file(i, p):
                continue
            t = ExtractTlThread(i, is_py2, True)
            get_extracted_threads.append(t)
            cnt = cnt + 1
            t.start()
    while True:
        threads_len = len(get_extracted_threads)
        if threads_len > 0:
            for t in get_extracted_threads:
                if t.is_alive():
                    t.join()
                get_extracted_threads.remove(t)
        else:
            break
    get_extracted_set_list.clear()
