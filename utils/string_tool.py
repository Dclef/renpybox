"""常用字符串小工具。保持旧接口名称，便于兼容历史调用。"""

import collections
import re
import string
from typing import Iterable, List


def remove_upprintable_chars(s: str) -> str:
    """去掉不可打印字符。"""
    return "".join(x for x in s if x.isprintable())


def split_strings(strings: Iterable[str], max_length: int = 5000) -> List[List[str]]:
    """按最大长度分段，保持输入顺序。"""
    result: List[List[str]] = []
    current: List[str] = []
    current_len = 0

    for text in strings:
        text_len = len(text)
        if current_len + text_len <= max_length:
            current.append(text)
            current_len += text_len
        else:
            if current:
                result.append(current)
            current = [text]
            current_len = text_len

    if current:
        result.append(current)
    return result


def EncodeBracketContent(s: str, bracketLeft: str, bracketRight: str, isAddSpace: bool = False) -> dict:
    """把成对括号内容替换为占位符，返回编码结果及原始片段列表。"""
    start = -1
    end = 0
    cnt = 0
    i = 0
    dic = dict()
    dic["ori"] = s
    oriList = []
    if (bracketLeft != bracketRight):
        matchLeftCnt = 0
        matchRightCnt = 0
        while True:
            _len = len(s)
            if (i >= _len):
                if (matchLeftCnt != matchRightCnt and start != -1):
                    i = start + 1
                    matchLeftCnt = 0
                    matchRightCnt = 0
                    continue
                break
            if (s[i] == bracketLeft):
                matchLeftCnt = matchLeftCnt + 1
                if (i == 0):
                    start = i
                else:
                    if (s[i - 1] == '\\'):
                        i = i + 1
                        continue
                    else:
                        if (matchLeftCnt == (matchRightCnt + 1)):
                            start = i
            if (s[i] == bracketRight and matchLeftCnt > 0):
                if (i == 0):
                    continue
                else:
                    if (s[i - 1] == '\\'):
                        i = i + 1
                        continue
                    else:
                        matchRightCnt = matchRightCnt + 1
                        if (start != -1):
                            if (matchLeftCnt == matchRightCnt):
                                end = i
            if (start != -1 and end > start):
                if (matchLeftCnt != matchRightCnt):
                    continue
                replace = ''
                if (isAddSpace):
                    replace = ' ' + bracketLeft + str(cnt) + bracketRight + ' '
                else:
                    replace = bracketLeft + str(cnt) + bracketRight
                ori = s[start:end + 1]
                oriList.append(ori)
                s = s[:start] + replace + s[end + 1:]
                i = start + len(replace) - 1
                cnt = cnt + 1
                start = -1
                end = 0
            i = i + 1
        dic['cnt'] = cnt
        dic['encoded'] = s
        dic['oriList'] = oriList
        return dic
    else:
        while True:
            _len = len(s)
            if (i >= _len):
                break
            if (s[i] == bracketLeft):
                if (i == 0):
                    start = i
                else:
                    if (s[i - 1] == '\\'):
                        i = i + 1
                        continue
                    else:
                        if (start >= end and i - start > 1):
                            end = i
                        else:
                            start = i
            if (start != -1 and end > start):
                replace = bracketLeft + str(cnt) + bracketRight
                ori = s[start:end + 1]
                oriList.append(ori)
                s = s[:start] + replace + s[end + 1:]
                i = start + len(replace) - 1
                cnt = cnt + 1
                start = -1
                end = 0
            i = i + 1
        dic['cnt'] = cnt
        dic['encoded'] = s
        dic['oriList'] = oriList
    return dic


def DecodeBracketContent(s: str, bracketLeft: str, bracketRight: str, l: list[str]) -> dict:
    """根据占位符列表反向还原括号内容。"""
    start = -1
    end = 0
    cnt = 0
    i = 0
    dic = dict()
    dic["ori"] = s
    oriList = []
    while True:
        _len = len(s)
        if (i >= _len):
            break
        if (s[i] == bracketLeft):
            if (i == 0):
                start = i
            else:
                if (s[i - 1] == '\\'):
                    i = i + 1
                    continue
                else:
                    start = i
        if (s[i] == bracketRight):
            if (i == 0):
                i = i + 1
                continue
            else:
                if (s[i - 1] == '\\'):
                    i = i + 1
                    continue
                else:
                    if (start != -1):
                        end = i
        if (start != -1 and end > start):
            ori = s[start:end + 1]
            index = int(ori[1:len(ori) - 1])
            replace = l[index]
            oriList.append(ori)
            s = s[:start] + replace + s[end + 1:]
            i = start + len(replace) - 1
            cnt = cnt + 1
            start = -1
            end = 0
        i = i + 1
    dic['cnt'] = cnt
    dic['decoded'] = s
    dic['oriList'] = oriList
    return dic


def EncodeBrackets(s: str) -> dict:
    """依次编码 <{}>[] 三种括号，便于占位保护。"""
    dic = dict()
    d = EncodeBracketContent(s, '<', '>')
    # print(d['encoded'])
    d2 = EncodeBracketContent(d['encoded'], '{', '}')
    # print(d2['encoded'],d2['oriList'])
    d3 = EncodeBracketContent(d2['encoded'], '[', ']')
    # print(d3['encoded'],d3['oriList'])
    dic['encoded'] = d3['encoded']
    dic['en_1'] = d['oriList']
    dic['en_1_cnt'] = d['cnt']
    dic['en_2'] = d2['oriList']
    dic['en_2_cnt'] = d2['cnt']
    dic['en_3'] = d3['oriList']
    dic['en_3_cnt'] = d3['cnt']
    return dic


def DecodeBrackets(s: str, en_1: list[str], en_2: list[str], en_3: list[str]) -> dict:
    """反向还原 EncodeBrackets 的结果。"""
    dic = dict()
    d4 = DecodeBracketContent(s, '[', ']', en_3)
    d5 = DecodeBracketContent(d4['decoded'], '{', '}', en_2)
    d6 = DecodeBracketContent(d5['decoded'], '<', '>', en_1)
    dic['decoded'] = d6["decoded"]
    dic['de_4'] = d4['oriList']
    dic['de_4_cnt'] = d4['cnt']
    dic['de_5'] = d5['oriList']
    dic['de_5_cnt'] = d5['cnt']
    dic['de_6'] = d6['oriList']
    dic['de_6_cnt'] = d6['cnt']
    return dic


def isAllPunctuations(s: str) -> bool:
    """判断字符串是否全部由标点组成。"""
    punc = string.punctuation
    return all(ch in punc for ch in s)


def encode_say_string(s: str) -> str:
    """为 Ren'Py 文本做基础转义。"""
    s = s.replace("\\", "\\\\")
    s = s.replace("\n", "\\n")
    s = s.replace("\"", "\\\"")
    return re.sub(r"(?<= ) ", "\\ ", s)


def replace_all_blank(value: str) -> str:
    """移除所有非字母数字及下划线。"""
    return re.sub(r"\W+", "", value).replace("_", "")


def replace_unescaped_quotes(text: str) -> str:
    """为未转义的双引号加反斜杠。"""
    return re.sub(r'(?<!\\)"', r'\\"', text)


def tail(filename: str, n: int) -> collections.deque[str]:
    """读取文件末尾 n 行。"""
    with open(filename, "r", encoding="utf-8") as file:
        return collections.deque(file, maxlen=n)
