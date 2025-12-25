"""
Ren'Py 源码翻译器 - 按照严格规则翻译游戏源代码

遵循三大原则：
1. 代码完整性铁律 - 只翻译文本字符串，保护所有代码结构
2. 翻译艺术性 - 信达雅的 R18 特化准则
3. 自适应智能菜单 - 检测选项提示信息并保留
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from base.LogManager import LogManager
from module.Text.SkipRules import should_skip_text


class LineType(Enum):
    """行类型分类"""
    CODE = auto()           # 纯代码行，不需翻译
    DIALOGUE = auto()       # 对话行 (角色 "台词")
    NARRATION = auto()      # 叙述行 ("文本")
    MENU_OPTION = auto()    # 菜单选项
    STRING_BLOCK = auto()   # strings 块中的 old/new
    COMMENT = auto()        # 注释行
    EMPTY = auto()          # 空行
    LABEL = auto()          # label 定义
    PYTHON = auto()         # python 块
    UNKNOWN = auto()        # 未知类型


@dataclass
class TranslationEntry:
    """待翻译条目"""
    line_number: int
    line_type: LineType
    original_line: str
    speaker: Optional[str]
    text: str
    # 菜单选项的额外信息
    menu_hints: Optional[str] = None  # (chg=...) 等提示
    menu_condition: Optional[str] = None  # if 条件
    # 保护标记
    protected_tags: List[str] = field(default_factory=list)  # {b}, [povname] 等
    # 翻译结果
    translated_text: Optional[str] = None
    # strings 块内：标记 old/new，old 不需要翻译
    string_is_old: bool = False
    
    @property
    def needs_translation(self) -> bool:
        """是否需要翻译"""
        if self.line_type == LineType.STRING_BLOCK and self.string_is_old:
            return False
        return self.line_type in (
            LineType.DIALOGUE,
            LineType.NARRATION,
            LineType.MENU_OPTION,
            LineType.STRING_BLOCK,
        )


class RenpySourceParser:
    """Ren'Py 源码解析器"""
    
    # 字符串前缀（支持 f-string/raw 等）
    STRING_PREFIX = r'(?:[fFrRuU]?)'
    
    # 正则模式
    # 对话行: 角色 "台词" / 角色"台词" / 角色 "台词" with xxx
    # 注意：角色名和引号之间的空格是可选的
    RE_DIALOGUE = re.compile(
        r'^(\s*)(?P<speaker>[a-zA-Z_]\w*)\s*'
        + STRING_PREFIX +
        r'(?P<quote>["\'])(?P<text>(?:\\.|[^\\])*?)(?P=quote)\s*'
        r'(?P<with>with\s+\w+)?(?P<trailing>.*)$'
    )
    
    # 叙述行: "文本" / "文本" with xxx
    RE_NARRATION = re.compile(
        r'^(\s*)'
        + STRING_PREFIX +
        r'(?P<quote>["\'])(?P<text>(?:\\.|[^\\])*?)(?P=quote)\s*'
        r'(?P<with>with\s+\w+)?(?P<trailing>.*)$'
    )
    
    # 菜单选项: "选项文本": / "选项文本" (hint): / "选项文本" if condition:
    RE_MENU_OPTION = re.compile(
        r'^(\s*)'
        + STRING_PREFIX +
        r'(?P<quote>["\'])(?P<text>(?:\\.|[^\\])*?)(?P=quote)\s*'
        r'(?P<hint>\([^)]*\))?\s*(?P<condition>if\s+.+)?:\s*$'
    )
    
    # strings 块的 old/new
    RE_STRING_OLD = re.compile(
        r'^(\s*)old\s+'
        + STRING_PREFIX +
        r'(?P<quote>["\'])(?P<text>(?:\\.|[^\\])*?)(?P=quote)(?P<trailing>.*)$'
    )
    RE_STRING_NEW = re.compile(
        r'^(\s*)new\s+'
        + STRING_PREFIX +
        r'(?P<quote>["\'])(?P<text>(?:\\.|[^\\])*?)(?P=quote)(?P<trailing>.*)$'
    )
    
    # ========== 新增：UI 文本模式 ==========
    # text "文本" / text _("文本") 语句
    RE_TEXT_STATEMENT = re.compile(
        r'^(\s*)text\s+(?:_\s*\(\s*)?'
        + STRING_PREFIX +
        r'(?P<quote>["\'])(?P<text>(?:\\.|[^\\])*?)(?P=quote)\s*\)?(?P<trailing>.*)$'
    )
    
    # textbutton "文本" / textbutton _("文本") 语句  
    RE_TEXTBUTTON = re.compile(
        r'^(\s*)textbutton\s+(?:_\s*\(\s*)?'
        + STRING_PREFIX +
        r'(?P<quote>["\'])(?P<text>(?:\\.|[^\\])*?)(?P=quote)\s*\)?(?P<trailing>.*)$'
    )
    
    # tooltip "文本" 属性
    RE_TOOLTIP = re.compile(
        r'tooltip\s+'
        + STRING_PREFIX +
        r'["\'](?P<text>(?:\\.|[^\\])*?)["\']'
    )
    
    # action 中的字符串参数 (如 AddToSet 参数)
    RE_ACTION_STRING = re.compile(
        r'action\s+.*?'
        + STRING_PREFIX +
        r'["\'](?P<text>(?:\\.|[^\\])*?)["\']'
    )
    
    # Character("名字") 定义
    RE_CHARACTER_DEF = re.compile(
        r'^(\s*)define\s+\w+\s*=\s*Character\s*\(\s*(?:_\s*\(\s*)?'
        + STRING_PREFIX +
        r'(?P<quote>["\'])(?P<text>(?:\\.|[^\\])*?)(?P=quote)\s*\)?\s*[,)]'
    )
    
    # 变量赋值中的字符串 (如 $ var = "文本")
    RE_VAR_ASSIGN = re.compile(
        r'^(\s*)\$?\s*[\w.]+\s*=\s*'
        + STRING_PREFIX +
        r'(?P<quote>["\'])(?P<text>(?:\\.|[^\\])*?)(?P=quote)(?P<trailing>.*)$'
    )
    
    # ========== 新增：renpy.notify 和字典字段模式 ==========
    # $renpy.notify("...") 语句
    RE_RENPY_NOTIFY = re.compile(
        r'renpy\.notify\s*\(\s*'
        + STRING_PREFIX +
        r'["\']+(?P<text>(?:[^"\'\\]|\\.)*)["\']+'
    )
    
    # 字典/列表中的 "name": "...", "description": "..." 等字段
    # 匹配 "key": "value" 模式
    RE_DICT_STRING_FIELD = re.compile(
        r'["\'](?:name|description|title|text|message|label|hint|tooltip|caption|content|summary|bio|info|note|prompt|dialog|dialogue|speech)["\']'
        r'\s*:\s*'
        + STRING_PREFIX +
        r'["\']+(?P<text>(?:[^"\'\\]|\\.)*)["\']+'
    )
    # ========================================
    
    # 代码关键字 - 这些行不应翻译
    CODE_KEYWORDS = {
        'label', 'jump', 'call', 'return', 'pass',
        'scene', 'show', 'hide', 'with', 'at',
        'play', 'stop', 'queue', 'voice',
        'python', 'init', 'default',
        'screen', 'style', 'transform', 'image',
        'if', 'elif', 'else', 'while', 'for',
        'menu', 'translate', 'nvl', 'window',
    }
    # 注意：从 CODE_KEYWORDS 移除了 'define' 和 '$'，因为它们可能包含需要翻译的文本
    
    # 不应翻译的属性关键字 - 这些属性后面的字符串通常是标识符/路径，不是用户可见文本
    NO_TRANSLATE_ATTRIBUTES = {
        # 标识符/引用类
        'id', 'style', 'style_prefix', 'style_suffix', 'style_group',
        'at', 'as', 'tag', 'layer', 'zorder',
        # 图片/资源路径类
        'background', 'foreground', 'hover_background', 'idle_background',
        'selected_background', 'insensitive_background',
        'thumb', 'thumb_shadow', 'thumb_offset',
        'base_bar', 'hover_bar', 'idle_bar',
        'left_bar', 'right_bar', 'top_bar', 'bottom_bar',
        'left_gutter', 'right_gutter', 'top_gutter', 'bottom_gutter',
        'add', 'image', 'icon', 'child',
        # 音频类
        'sound', 'hover_sound', 'activate_sound',
        # 动画/变换类
        'transform', 'hover', 'idle', 'selected', 'insensitive',
        # 技术属性类
        'action', 'hovered', 'unhovered', 'clicked', 'focus',
        'keysym', 'alternate', 'sensitive',
        'xpos', 'ypos', 'xanchor', 'yanchor', 'pos', 'anchor',
        'xsize', 'ysize', 'xysize', 'size',
        'xalign', 'yalign', 'align',
        'xoffset', 'yoffset', 'offset',
        'xmaximum', 'ymaximum', 'maximum',
        'xminimum', 'yminimum', 'minimum',
        'xfill', 'yfill', 'fill',
        'spacing', 'first_spacing',
        'box_reverse', 'box_wrap',
        'variant', 'properties',
    }
    
    # 文件扩展名模式 - 包含这些扩展名的字符串通常是资源路径
    FILE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg',
                       '.mp3', '.ogg', '.wav', '.opus', '.flac',
                       '.mp4', '.webm', '.ogv', '.avi', '.mkv',
                       '.ttf', '.otf', '.woff', '.woff2',
                       '.rpy', '.rpyc', '.rpa', '.json', '.txt'}
    
    # 保护的文本标签模式
    RE_PROTECTED_TAGS = re.compile(
        r'(\{[^}]+\}|\[[^\]]+\]|\\n|\\t|%[sd]|\{\w+\}|\[[\w.]+\])'
    )
    
    def __init__(self):
        self.logger = LogManager.get()
        self._in_python_block = False
        self._in_menu_block = False
        self._in_strings_block = False
        self._python_indent = 0
        self._menu_indent = 0
        self._strings_indent = 0
    
    def _should_skip_text(self, text: str) -> bool:
        """检查文本是否应该跳过翻译"""
        if should_skip_text(text):
            return True
        text_lower = (text or "").lower().strip()
        # 补充：一些通用资源/路径关键词
        for ext in self.FILE_EXTENSIONS:
            if ext in text_lower:
                return True
        return False
    
    def _is_no_translate_line(self, line: str) -> bool:
        """检查行是否包含不应翻译的属性"""
        stripped = line.strip()
        
        # 检查是否以不翻译的属性开头
        for attr in self.NO_TRANSLATE_ATTRIBUTES:
            # 匹配 "attr value" 或 "attr:" 格式
            if stripped.startswith(attr + ' ') or stripped.startswith(attr + ':'):
                return True
            # 检查 attr "value" 格式
            if re.match(rf'^{re.escape(attr)}\s+["\']', stripped):
                return True
        
        return False

    def parse_file(self, file_path: Path) -> List[TranslationEntry]:
        """解析单个 .rpy 文件，返回可翻译条目列表"""
        entries: List[TranslationEntry] = []
        
        try:
            content = file_path.read_text(encoding='utf-8')
        except Exception as e:
            self.logger.error(f"读取文件失败 {file_path}: {e}")
            return entries
        
        lines = content.split('\n')
        self._reset_state()
        
        for line_num, line in enumerate(lines, 1):
            line_entries = self._parse_line(line_num, line)
            if line_entries:
                if isinstance(line_entries, list):
                    entries.extend(line_entries)
                else:
                    entries.append(line_entries)
        
        return entries
    
    def _reset_state(self):
        """重置解析状态"""
        self._in_python_block = False
        self._in_menu_block = False
        self._in_strings_block = False
        self._python_indent = 0
        self._menu_indent = 0
        self._strings_indent = 0
    
    def _get_indent(self, line: str) -> int:
        """获取行缩进级别"""
        return len(line) - len(line.lstrip())
    
    def _parse_line(self, line_num: int, line: str) -> List[TranslationEntry]:
        """解析单行"""
        stripped = line.strip()
        indent = self._get_indent(line)
        
        # 空行
        if not stripped:
            return [TranslationEntry(
                line_number=line_num,
                line_type=LineType.EMPTY,
                original_line=line,
                speaker=None,
                text="",
            )]
        
        # 注释行
        if stripped.startswith('#'):
            return [TranslationEntry(
                line_number=line_num,
                line_type=LineType.COMMENT,
                original_line=line,
                speaker=None,
                text="",
            )]
        
        # 检查块状态退出
        self._check_block_exit(indent)
        
        # Python 块内 - 尝试提取可翻译文本
        if self._in_python_block:
            entries_list = []
            
            # 检查是否有 renpy.notify 调用
            for match in self.RE_RENPY_NOTIFY.finditer(line):
                text = match.group("text")
                if text.strip():
                    protected = self._extract_protected_tags(text)
                    entries_list.append(TranslationEntry(
                        line_number=line_num,
                        line_type=LineType.NARRATION,
                        original_line=line,
                        speaker=None,
                        text=text,
                        protected_tags=protected,
                    ))
            
            # 检查是否有字典字段 "name": "...", "description": "..." 等
            for match in self.RE_DICT_STRING_FIELD.finditer(line):
                text = match.group("text")
                if text.strip():
                    protected = self._extract_protected_tags(text)
                    entries_list.append(TranslationEntry(
                        line_number=line_num,
                        line_type=LineType.NARRATION,
                        original_line=line,
                        speaker=None,
                        text=text,
                        protected_tags=protected,
                    ))
            
            if entries_list:
                return entries_list
            
            # 没有可翻译内容，返回 Python 类型
            return [TranslationEntry(
                line_number=line_num,
                line_type=LineType.PYTHON,
                original_line=line,
                speaker=None,
                text="",
            )]
        
        # 检查是否进入新块
        if stripped.endswith(':'):
            first_word = stripped.split()[0] if stripped.split() else ''
            
            if first_word == 'python' or stripped.startswith('init python'):
                self._in_python_block = True
                self._python_indent = indent
                return [TranslationEntry(
                    line_number=line_num,
                    line_type=LineType.CODE,
                    original_line=line,
                    speaker=None,
                    text="",
                )]
            
            if first_word == 'menu':
                self._in_menu_block = True
                self._menu_indent = indent
                return [TranslationEntry(
                    line_number=line_num,
                    line_type=LineType.CODE,
                    original_line=line,
                    speaker=None,
                    text="",
                )]
            
            if stripped.startswith('translate ') and 'strings' in stripped:
                self._in_strings_block = True
                self._strings_indent = indent
                return [TranslationEntry(
                    line_number=line_num,
                    line_type=LineType.CODE,
                    original_line=line,
                    speaker=None,
                    text="",
                )]
        
        # 检查代码关键字
        first_word = stripped.split()[0] if stripped.split() else ''
        # 去掉可能的冒号
        first_word = first_word.rstrip(':')
        
        # 处理 $ 开头的内联 Python 语句
        if stripped.startswith('$'):
            entries_list = []
            
            # 检查是否有 renpy.notify 调用
            for match in self.RE_RENPY_NOTIFY.finditer(line):
                text = match.group("text")
                if text.strip():
                    protected = self._extract_protected_tags(text)
                    entries_list.append(TranslationEntry(
                        line_number=line_num,
                        line_type=LineType.NARRATION,
                        original_line=line,
                        speaker=None,
                        text=text,
                        protected_tags=protected,
                    ))
            
            # 检查是否有字典字段
            for match in self.RE_DICT_STRING_FIELD.finditer(line):
                text = match.group("text")
                if text.strip():
                    protected = self._extract_protected_tags(text)
                    entries_list.append(TranslationEntry(
                        line_number=line_num,
                        line_type=LineType.NARRATION,
                        original_line=line,
                        speaker=None,
                        text=text,
                        protected_tags=protected,
                    ))
            
            if entries_list:
                return entries_list
            
            # 没有可翻译内容，标记为代码
            return [TranslationEntry(
                line_number=line_num,
                line_type=LineType.CODE,
                original_line=line,
                speaker=None,
                text="",
            )]
        
        if first_word in self.CODE_KEYWORDS:
            return [TranslationEntry(
                line_number=line_num,
                line_type=LineType.CODE,
                original_line=line,
                speaker=None,
                text="",
            )]
        
        # strings 块中的 old/new
        if self._in_strings_block:
            match_old = self.RE_STRING_OLD.match(line)
            if match_old:
                text = match_old.group("text")
                protected = self._extract_protected_tags(text)
                return [TranslationEntry(
                    line_number=line_num,
                    line_type=LineType.STRING_BLOCK,
                    original_line=line,
                    speaker=None,
                    text=text,
                    protected_tags=protected,
                    string_is_old=True,
                )]
            
            match_new = self.RE_STRING_NEW.match(line)
            if match_new:
                # new 行通常是空的等待翻译，或者已有翻译
                text = match_new.group("text")
                return [TranslationEntry(
                    line_number=line_num,
                    line_type=LineType.STRING_BLOCK,
                    original_line=line,
                    speaker=None,
                    text=text,
                )]
        
        # 菜单选项
        if self._in_menu_block:
            match_option = self.RE_MENU_OPTION.match(line)
            if match_option:
                text = match_option.group("text")
                hints = match_option.group("hint")  # (chg=...) 等
                condition = match_option.group("condition")  # if xxx
                protected = self._extract_protected_tags(text)
                
                return [TranslationEntry(
                    line_number=line_num,
                    line_type=LineType.MENU_OPTION,
                    original_line=line,
                    speaker=None,
                    text=text,
                    menu_hints=hints,
                    menu_condition=condition,
                    protected_tags=protected,
                )]
        
        # 检查是否是不应翻译的属性行
        if self._is_no_translate_line(line):
            return [TranslationEntry(
                line_number=line_num,
                line_type=LineType.CODE,
                original_line=line,
                speaker=None,
                text="",
            )]
        
        # 对话行
        match_dialogue = self.RE_DIALOGUE.match(line)
        if match_dialogue:
            speaker = match_dialogue.group("speaker")
            text = match_dialogue.group("text")
            
            # 跳过不需要翻译的文本（如路径、标识符）
            if self._should_skip_text(text):
                return [TranslationEntry(
                    line_number=line_num,
                    line_type=LineType.CODE,
                    original_line=line,
                    speaker=None,
                    text="",
                )]
            
            protected = self._extract_protected_tags(text)
            
            return [TranslationEntry(
                line_number=line_num,
                line_type=LineType.DIALOGUE,
                original_line=line,
                speaker=speaker,
                text=text,
                protected_tags=protected,
            )]
        
        # 叙述行
        match_narration = self.RE_NARRATION.match(line)
        if match_narration:
            text = match_narration.group("text")
            
            # 跳过不需要翻译的文本（如路径、标识符）
            if self._should_skip_text(text):
                return [TranslationEntry(
                    line_number=line_num,
                    line_type=LineType.CODE,
                    original_line=line,
                    speaker=None,
                    text="",
                )]
            
            protected = self._extract_protected_tags(text)
            
            return [TranslationEntry(
                line_number=line_num,
                line_type=LineType.NARRATION,
                original_line=line,
                speaker=None,
                text=text,
                protected_tags=protected,
            )]
        
        # ========== 新增：UI 文本匹配 ==========
        # Character 定义
        match_character = self.RE_CHARACTER_DEF.match(line)
        if match_character:
            text = match_character.group("text")
            if text.strip():  # 有实际文本
                protected = self._extract_protected_tags(text)
                return [TranslationEntry(
                    line_number=line_num,
                    line_type=LineType.DIALOGUE,  # 当作对话类型处理
                    original_line=line,
                    speaker="Character",
                    text=text,
                    protected_tags=protected,
                )]
        
        # text 语句 - 注意要排除 "text who id 'who'" 这种格式
        match_text = self.RE_TEXT_STATEMENT.match(line)
        if match_text:
            text = match_text.group("text")
            # 跳过不需要翻译的文本
            if text.strip() and not self._should_skip_text(text):
                protected = self._extract_protected_tags(text)
                return [TranslationEntry(
                    line_number=line_num,
                    line_type=LineType.NARRATION,
                    original_line=line,
                    speaker=None,
                    text=text,
                    protected_tags=protected,
                )]
        
        # textbutton 语句
        match_textbutton = self.RE_TEXTBUTTON.match(line)
        if match_textbutton:
            text = match_textbutton.group("text")
            # 跳过不需要翻译的文本
            if text.strip() and not self._should_skip_text(text):
                protected = self._extract_protected_tags(text)
                return [TranslationEntry(
                    line_number=line_num,
                    line_type=LineType.MENU_OPTION,  # 当作菜单选项处理
                    original_line=line,
                    speaker=None,
                    text=text,
                    protected_tags=protected,
                )]
        
        # tooltip 属性 (在行内搜索)
        match_tooltip = self.RE_TOOLTIP.search(line)
        if match_tooltip:
            text = match_tooltip.group("text")
            # 跳过不需要翻译的文本
            if text.strip() and not self._should_skip_text(text):
                protected = self._extract_protected_tags(text)
                return [TranslationEntry(
                    line_number=line_num,
                    line_type=LineType.NARRATION,
                    original_line=line,
                    speaker=None,
                    text=text,
                    protected_tags=protected,
                )]
        
        # action 中的中文字符串
        match_action = self.RE_ACTION_STRING.search(line)
        if match_action:
            text = match_action.group("text")
            if text.strip():
                protected = self._extract_protected_tags(text)
                return TranslationEntry(
                    line_number=line_num,
                    line_type=LineType.NARRATION,
                    original_line=line,
                    speaker=None,
                    text=text,
                    protected_tags=protected,
                )
        
        # 变量赋值中的字符串
        match_var = self.RE_VAR_ASSIGN.match(line)
        if match_var:
            text = match_var.group("text")
            if text.strip():
                protected = self._extract_protected_tags(text)
                return TranslationEntry(
                    line_number=line_num,
                    line_type=LineType.NARRATION,
                    original_line=line,
                    speaker=None,
                    text=text,
                    protected_tags=protected,
                )
        
        # ========== 新增: renpy.notify 匹配 ==========
        match_notify = self.RE_RENPY_NOTIFY.search(line)
        if match_notify:
            text = match_notify.group("text")
            if text.strip():
                protected = self._extract_protected_tags(text)
                return TranslationEntry(
                    line_number=line_num,
                    line_type=LineType.NARRATION,
                    original_line=line,
                    speaker=None,
                    text=text,
                    protected_tags=protected,
                )
        
        # ========== 新增: 字典中的 name/description 等字段 ==========
        match_dict_field = self.RE_DICT_STRING_FIELD.search(line)
        if match_dict_field:
            text = match_dict_field.group("text")
            if text.strip():
                protected = self._extract_protected_tags(text)
                return TranslationEntry(
                    line_number=line_num,
                    line_type=LineType.NARRATION,
                    original_line=line,
                    speaker=None,
                    text=text,
                    protected_tags=protected,
                )
        # ==========================================
        
        # 未知类型 - 默认为代码
        return TranslationEntry(
            line_number=line_num,
            line_type=LineType.UNKNOWN,
            original_line=line,
            speaker=None,
            text="",
        )
    
    def _check_block_exit(self, current_indent: int):
        """检查是否退出块"""
        if self._in_python_block and current_indent <= self._python_indent:
            self._in_python_block = False
        
        if self._in_menu_block and current_indent <= self._menu_indent:
            self._in_menu_block = False
        
        if self._in_strings_block and current_indent <= self._strings_indent:
            self._in_strings_block = False
    
    def _extract_protected_tags(self, text: str) -> List[str]:
        """提取需要保护的标签"""
        return self.RE_PROTECTED_TAGS.findall(text)


class RenpySourceTranslator:
    """Ren'Py 源码翻译器"""
    
    def __init__(self):
        self.logger = LogManager.get()
        self.parser = RenpySourceParser()
        # 专有名词词典
        self.glossary: Dict[str, str] = {}
        # 已知角色名映射
        self.character_names: Dict[str, str] = {}
    
    def scan_directory(self, game_dir: Path, extensions: List[str] = None) -> Dict[Path, List[TranslationEntry]]:
        """扫描目录，返回所有可翻译条目"""
        if extensions is None:
            extensions = ['.rpy']
        
        results: Dict[Path, List[TranslationEntry]] = {}
        
        for ext in extensions:
            for file_path in game_dir.rglob(f'*{ext}'):
                # 跳过 tl 目录
                if 'tl' in file_path.parts:
                    continue
                
                entries = self.parser.parse_file(file_path)
                translatable = [e for e in entries if e.needs_translation and e.text.strip()]
                
                if translatable:
                    results[file_path] = translatable
        
        return results
    
    def scan_file(self, file_path: Path) -> List[TranslationEntry]:
        """扫描单个文件，返回可翻译条目"""
        if not file_path.exists():
            return []
        
        entries = self.parser.parse_file(file_path)
        translatable = [e for e in entries if e.needs_translation and e.text.strip()]
        return translatable
    
    def count_entries(self, game_dir: Path) -> Tuple[int, int, int]:
        """统计条目数量
        
        Returns:
            (total_files, total_entries, total_characters)
        """
        results = self.scan_directory(game_dir)
        
        total_files = len(results)
        total_entries = sum(len(entries) for entries in results.values())
        total_chars = sum(
            len(e.text) for entries in results.values() for e in entries
        )
        
        return total_files, total_entries, total_chars
    
    def build_translation_prompt(
        self,
        entries: List[TranslationEntry],
        target_lang: str = "简体中文",
        context_hint: str = "",
    ) -> str:
        """构建翻译提示词
        
        Args:
            entries: 待翻译条目
            target_lang: 目标语言
            context_hint: 上下文提示（如角色信息、剧情背景）
        """
        lines = []
        lines.append(f"请将以下 Ren'Py 游戏文本翻译成{target_lang}。")
        lines.append("")
        lines.append("**翻译规则：**")
        lines.append("1. 只翻译引号内的文本内容")
        lines.append("2. 保留所有特殊标签如 {b}, {i}, [name], \\n 等，不要翻译或删除")
        lines.append("3. R18 内容必须直接、露骨地翻译，不要委婉处理")
        lines.append("4. 翻译要通顺自然，符合中文表达习惯，杜绝翻译腔")
        lines.append("5. 保持角色语气和口癖的一致性")
        lines.append("6. 遇到文化梗或双关语，在译文后用 \\n（译者注：...）解释")
        lines.append("")
        
        if context_hint:
            lines.append(f"**背景信息：** {context_hint}")
            lines.append("")
        
        if self.glossary:
            lines.append("**专有名词对照：**")
            for orig, trans in self.glossary.items():
                lines.append(f"- {orig} → {trans}")
            lines.append("")
        
        lines.append("**待翻译文本：**")
        lines.append("```")
        
        for i, entry in enumerate(entries, 1):
            speaker_hint = f"[{entry.speaker}] " if entry.speaker else ""
            type_hint = ""
            if entry.line_type == LineType.MENU_OPTION:
                type_hint = "[选项] "
                if entry.menu_hints:
                    type_hint += f"{entry.menu_hints} "
            
            lines.append(f"{i}. {type_hint}{speaker_hint}{entry.text}")
        
        lines.append("```")
        lines.append("")
        lines.append("请按相同格式输出翻译结果，每行一条：")
        lines.append("```")
        lines.append("1. 翻译后的文本")
        lines.append("2. 翻译后的文本")
        lines.append("...")
        lines.append("```")
        
        return "\n".join(lines)
    
    def apply_translations(
        self,
        file_path: Path,
        entries: List[TranslationEntry],
        translations: List[str],
        backup: bool = True,
        bilingual_comparison: bool = False,
    ) -> str:
        """将翻译应用到文件
        
        Args:
            file_path: 源文件路径
            entries: 原始条目列表
            translations: 翻译结果列表
            backup: 是否备份原文件
            bilingual_comparison: 是否保留双语对照（注释原文）
            
        Returns:
            新文件内容
        """
        if len(entries) != len(translations):
            raise ValueError(f"条目数 ({len(entries)}) 与翻译数 ({len(translations)}) 不匹配")
        
        # 读取原文件
        content = file_path.read_text(encoding='utf-8')
        lines = content.split('\n')
        
        # 备份
        if backup:
            backup_path = file_path.with_suffix(file_path.suffix + '.bak')
            backup_path.write_text(content, encoding='utf-8')
        
        # 构建替换映射
        for entry, translation in zip(entries, translations):
            if not translation or not entry.text:
                continue
            
            line_idx = entry.line_number - 1
            if line_idx < 0 or line_idx >= len(lines):
                continue
            
            original_line = lines[line_idx]
            
            # 在原行中替换文本（保护引号和其他结构）
            new_line = self._replace_text_in_line(
                original_line,
                entry.text,
                translation,
            )
            
            if bilingual_comparison:
                # 保留原文作为注释
                # 获取缩进
                indent = original_line[:len(original_line) - len(original_line.lstrip())]
                # 组合：缩进 + # + 原文(去缩进) + 换行 + 新行
                lines[line_idx] = f"{indent}# {original_line.lstrip()}\n{new_line}"
            else:
                lines[line_idx] = new_line
        
        return '\n'.join(lines)
    
    def backup_source_file(self, file_path: Path, backup_root: Path, game_dir: Path):
        """备份源文件到外部目录，保持目录结构"""
        try:
            # 计算相对路径
            try:
                rel_path = file_path.relative_to(game_dir)
            except ValueError:
                # 如果不在 game_dir 下，直接用文件名
                rel_path = Path(file_path.name)
            
            dest_path = backup_root / rel_path
            
            # 创建父目录
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 复制文件
            dest_path.write_bytes(file_path.read_bytes())
            
        except Exception as e:
            self.logger.error(f"备份文件失败 {file_path} -> {backup_root}: {e}")

    def _replace_text_in_line(
        self,
        line: str,
        original_text: str,
        translated_text: str,
    ) -> str:
        """在行中替换文本，保持结构"""
        # 转义原文本中的特殊正则字符
        escaped_original = re.escape(original_text)
        
        # 尝试双引号替换
        pattern_double = f'"{escaped_original}"'
        if re.search(pattern_double, line):
            return re.sub(pattern_double, f'"{translated_text}"', line, count=1)
        
        # 尝试单引号替换
        pattern_single = f"'{escaped_original}'"
        if re.search(pattern_single, line):
            return re.sub(pattern_single, f"'{translated_text}'", line, count=1)
        
        # 如果都不匹配，尝试直接替换文本（作为后备）
        if original_text in line:
            return line.replace(original_text, translated_text, 1)
        
        # 无法替换，返回原行
        return line
    
    def set_glossary(self, glossary: Dict[str, str]):
        """设置专有名词词典"""
        self.glossary = glossary
    
    def set_character_names(self, names: Dict[str, str]):
        """设置角色名映射"""
        self.character_names = names
