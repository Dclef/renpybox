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
    block_originals = set()  # {dialogue_original_text}
    
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
            if old_text in block_originals:
                for file_path, line_idx in occurrences:
                    if file_path not in duplicates_to_remove:
                        duplicates_to_remove[file_path] = set()
                    duplicates_to_remove[file_path].add(line_idx)
                continue

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
                    self.tl_dir = self.tl_dir[:-len(ori_tl)] + self.tl_name
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


def ExtractFromFile(p, is_open_filter, filter_length, is_skip_underline, is_py2, skip_translate_block=False):
    remove_repeat_for_file(p)
    e = set()
    f = io.open(p, 'r+', encoding='utf-8')
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
                        if not is_ui_keyword(strip_i.strip('"')):
                            if len(_strip_i) < effective_filter_length:
                                continue
                        e.add(i)
                        is_add = True
                    else:
                        e.add(i)
                        is_add = True
        if is_add:
            continue
        d = EncodeBracketContent(line_content, "'", "'")
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
    paths = os.walk(p + '/../../', topdown=False)

    for path, dir_lst, file_lst in paths:
        for file_name in file_lst:
            i = os.path.join(path, file_name)
            if (i[len(p + '/../../'):][:3] == 'tl\\'):
                continue
            if (file_name.endswith("rpy") == False):
                continue
            if is_builtin_ui_file(i):
                continue
            target = p + i[len(p + '/../../'):]
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
    paths = os.walk(p, topdown=False)
    for path, dir_lst, file_lst in paths:
        for file_name in file_lst:
            i = os.path.join(path, file_name)
            if (file_name.endswith("rpy") == False):
                continue
            if is_builtin_ui_file(i, p):
                continue
            target = p + '../../' + i[len(p):]
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
