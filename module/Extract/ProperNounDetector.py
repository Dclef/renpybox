"""专有名词检测：用「语料统计 + 大小写位置证据」筛出真正的角色/地名/组织等专名。

背景：
    早期实现把「任何首字母大写的词」都当成术语候选，于是句首大写的普通词
    （What / Have / Don't / Like …）全部混进结果，一个中型项目能扫出几千条、
    去重后几百条噪音，真正有用的名字被埋在里面。

本模块只做判定，不做 IO，便于单测：
    1. 对语料做一次统计，记录每个词「句中大写 / 句首大写 / 小写」的出现次数；
    2. 单名候选要求「句中大写 ≥ N 次且从未以小写出现」，虚词/缩写词直接排除；
    3. 多词候选要求每个词都大写（内部允许 of/the/de 等连接词）且整体出现 ≥ N 次。
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Iterator, Sequence

# 句子结束/引用收尾字符：出现在这些字符之后的大写词视为「句首大写」，
# 句首大写不能证明是专名（"What are you doing?" 的 What）。
# 括号、引号、破折号同样开启新句，避免 "(Hopefully …" 被当成句中大写。
_SENTENCE_END_CHARS = frozenset(
    '.!?…"\'”’»:;()[]{}<>-—–*'
)

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’\-]*")

# Ren'Py 格式标签 {b}/{i}/{size=…}：判定句首时要先剥掉，
# 否则 "{b}Notice Board{/b}" 里的 Notice 会被当成句首大写，丢掉句中大写证据。
_RE_FORMAT_TAG = re.compile(r"\{[^{}]*\}")

# 短语内部允许出现的小写连接词（"Bank of China" / "de la Cruz"）。
CONNECTOR_WORDS = frozenset({"of", "the", "and", "de", "la", "da", "van", "von", "di", "du"})

# 虚词、代词、助动词、常见句首词：永远不可能是专名（专名同形词除外，见下）。
_STOPWORD_BASE = """
a about above across actually after afterwards again against ago ah aha all almost alone
along already also although always am among an and another any anybody anyone anything anyway
anywhere are aren around as at away aw aww
back bad be because been before behind being below best better between both but by
can cannot cant could couldnt
damn did didn do does doesn doing don done down during
each either else enough even ever every everybody everyone everything everywhere except
far few fine for from fuck
get gets getting go goes going gone gotta got had hadn has hasn have haven having he her here
hers herself hey hi him himself his hm hmm how however huh
i if ill im in into is isnt it its itself ive
just
keep kind know
last later least less let lets like likely little lol look
made make many may maybe me mean might mine more most much must mustn my myself
need neither never new next nice no nobody none nor not nothing now nowhere
of off often oh ok okay on once one only or other others otherwise ought our ours ourselves out
over own
people please plus pretty probably
quite
rather really right
said same say says see seems shall shant she should shouldn since so some somebody someone
something sometimes somewhere soon sorry still stop such sure
take than thank thanks that thats the their theirs them themselves then there theres these they
thing things think this those though through thus till to today together too took toward
ugh under until up upon us use
very
wait wanna want was wasn way we well were weren what whatever when where whether which while who
whom whose why will with within without wont would wouldn wow
yeah yes yet yo you your yours yourself yourselves
bam bang gasp laugh laughs sigh sighs sob sobs
dont didnt cant wont isnt arent wasnt werent
mom dad mum mother father bro sis dude man guys guy lady sir mister missus
mr mrs ms dr
hopefully honestly seriously actually basically obviously literally totally probably
possibly apparently definitely certainly clearly simply truly mostly nearly hardly
mmm mm mmh mhm uh um er erm aah aaah ahh oh ooh oops ow ouch phew psst shh shhh ssh
tsk tut whoa woah whoops yay yep yup nope nah meh hmph heh ha haha hahaha
boom crash thud groan groans moan moans pant pants sniff sniffs growl laughter
chuckle chuckles giggle giggles scream screams
"""

# 短语不允许以这些词开头：它们只是句首连词/语气词，被下个大写词带进短语。
_PHRASE_HEAD_BLOCKLIST = frozenset({
    "and", "but", "or", "so", "then", "plus", "also", "well", "alright", "okay", "ok",
    "oh", "ah", "hey", "hi", "hello", "yeah", "yes", "no", "wow", "ugh", "hmm", "mmm",
    "psst", "shh", "yo", "now", "still", "just", "even", "yet", "for", "with", "at",
    "in", "on", "of", "the", "a", "an", "to", "by", "from", "as", "if", "because",
})

# 语气词/拟声词的「骨架」：把连续重复字母折叠后落在这里的都是噪音。
_INTERJECTION_SKELETONS = frozenset({
    "a", "ah", "oh", "o", "m", "hm", "hmm", "mm", "uh", "eh", "ha", "he", "hi", "ho",
    "huh", "wow", "woah", "yes", "no", "yep", "nope", "sh", "shh", "psst", "tsk",
    "ugh", "ow", "ouch", "phew", "yay", "meh", "heh", "lol", "mmh", "mhm", "er", "erm",
    "aah", "uhh", "ehh", "yo", "hah",
})

# 常见缩合形式（don't / I'll / you're …），避免逐个手写。
_CONTRACTION_STEMS = (
    "i", "you", "he", "she", "it", "we", "they", "that", "there", "what", "who",
    "let", "how", "where", "when", "why", "this", "here", "one",
    "don", "doesn", "didn", "isn", "aren", "wasn", "weren", "can", "couldn",
    "won", "wouldn", "shouldn", "haven", "hasn", "hadn", "mustn", "ain",
)
_CONTRACTION_SUFFIXES = ("s", "m", "re", "ve", "ll", "d", "t")


def _build_stopwords() -> frozenset[str]:
    words = {word for word in _STOPWORD_BASE.split() if word}
    for stem in _CONTRACTION_STEMS:
        for suffix in _CONTRACTION_SUFFIXES:
            words.add(f"{stem}'{suffix}")
            words.add(f"{stem}’{suffix}")
    return frozenset(words)


STOPWORDS = _build_stopwords()

# 明显不是专名的纯大写喊叫/UI 词（全大写时额外排除，避免 "FREE" "SAVE" 混入）。
_UPPERCASE_NOISE = frozenset({
    "free", "save", "load", "quit", "exit", "start", "menu", "back", "next", "skip",
    "auto", "yes", "no", "ok", "okay", "wait", "stop", "help", "info", "on", "off",
})

# 尊称/称呼语：正文里几乎都以大写出现（"Your Majesty"、"Her Highness"），
# 但它们是对说话对象的称谓，不是作品设定里的术语，翻译时随句处理即可。
_HONORIFIC_NOISE = frozenset({
    "majesty", "highness", "sire", "madam", "madame", "mademoiselle", "milady",
    "mylord", "monsieur", "señor", "señora", "senor", "senora", "sama", "sama",
    "ojousama", "ojou", "onii", "onee", "sensei", "senpai", "kun", "chan",
})

# Common nouns that frequently look like proper nouns when capitalized in dialogue
# or UI text. Keep this list conservative; multi-word named entities are unaffected.
_COMMON_NON_TERM_SINGLE_WORDS = frozenset("""
button buttons inventory god gods
monday tuesday wednesday thursday friday saturday sunday
january february march april may june july august september october november december
christmas halloween easter
castle church cult group mayor prototype robot weights volcano vitamin octopus
king queen prince princess
""".split())


@dataclass
class WordEvidence:
    """单个词的证据统计。"""

    total: int = 0
    mid_capitalized: int = 0
    sentence_start: int = 0
    lowercase: int = 0
    forms: Counter = field(default_factory=Counter)

    @property
    def display(self) -> str:
        """出现次数最多的原始写法。"""
        if not self.forms:
            return ""
        return self.forms.most_common(1)[0][0]


@dataclass
class PhraseEvidence:
    """多词专名的证据统计。"""

    total: int = 0
    mid_capitalized: int = 0
    forms: Counter = field(default_factory=Counter)

    @property
    def display(self) -> str:
        if not self.forms:
            return ""
        return self.forms.most_common(1)[0][0]


def _normalize_token(token: str) -> str:
    """去掉所有格 's 与首尾连字符，返回用于统计的规范形。"""
    value = token.strip("-'’")
    lowered = value.casefold()
    if len(lowered) > 2 and (lowered.endswith("'s") or lowered.endswith("’s")):
        lowered = lowered[:-2]
    return lowered


def _clean_display(token: str) -> str:
    """把统计用的原始写法整理成可直接入词库的显示形式。"""
    value = str(token or "").strip().strip("-'’")
    if len(value) > 2 and (value.endswith("'s") or value.endswith("’s")):
        value = value[:-2]
    return value.strip("-'’")


def _is_sentence_start(line: str, position: int) -> bool:
    # 先剥掉 {b}/{i} 这类格式标签再判断：原文里 "{b}Notice Board{/b}"
    # 的 Notice 前面只有标签，删掉标签后才能正确认出它是句首。
    prefix = _RE_FORMAT_TAG.sub("", line[:position])
    if not prefix.strip():
        return True
    stripped = prefix.rstrip()
    if not stripped:
        return True
    return stripped[-1] in _SENTENCE_END_CHARS


def _is_capitalized(token: str) -> bool:
    return bool(token) and token[0].isupper()


def _collapse_repeats(word: str) -> str:
    """把连续重复字母折叠成单个（"Ahhhhh" → "Ah"，"Mmmmmm" → "M"）。"""
    result: list[str] = []
    for char in word:
        if result and result[-1] == char:
            continue
        result.append(char)
    return "".join(result)


def _is_interjection(word: str) -> bool:
    """判断是否为语气词/拟声词（含连续重复字母的写法）。"""
    if not word:
        return True
    if word in _INTERJECTION_SKELETONS:
        return True
    collapsed = _collapse_repeats(word).casefold()
    if collapsed in _INTERJECTION_SKELETONS:
        return True
    # 短词本身不能证明是拟声词：Ann / Lee 折叠后也只有两字母。
    # 只按已知语气词骨架判断，保留 Ai / Jo / Ed 等短专名。
    return False


def _is_stopword_casefold(word: str) -> bool:
    """判断规范化后的词是否属于虚词集合。"""
    if not word:
        return True
    if word in STOPWORDS:
        return True
    # 连字符断裂词（I-I / W-what）逐段判断。
    if "-" in word or "’" in word or "'" in word:
        parts = [
            part for part in re.split(r"[-'’]", word) if part
        ]
        if parts and all(part in STOPWORDS for part in parts):
            return True
        # 结巴写法（W-what / A-ah）：后半段是虚词，前半段只有一两个字母。
        if len(parts) == 2 and parts[1] in STOPWORDS and len(parts[0]) <= 2:
            return True
        # 拟声词连写（Ahhh-Cumming / Mmmm-Ahhhh）。
        if parts and all(_is_interjection(part) for part in parts):
            return True
    if _is_interjection(word):
        return True
    return False


class CorpusEvidence:
    """一次语料扫描得到的统计证据。"""

    def __init__(self, lines: Sequence[str]) -> None:
        self.lines: list[str] = []
        self.words: dict[str, WordEvidence] = {}
        self.phrases: dict[str, PhraseEvidence] = {}
        self.postings: dict[str, set[int]] = {}
        self._build(lines)

    # ---------------------------------------------------------------- build
    RE_INTERPOLATION = re.compile(r"\[[^\[\]]*\]")

    @classmethod
    def _parse_interpolation_spans(cls, line: str) -> list[tuple[int, int]]:
        """返回 Ren'Py 变量插值 [..] 的字符区间，统计时整段跳过。"""
        if "[" not in line:
            return []
        return [match.span() for match in cls.RE_INTERPOLATION.finditer(line)]

    @staticmethod
    def _in_blocked(position: int, spans: Sequence[tuple[int, int]]) -> bool:
        for start, end in spans:
            if start <= position < end:
                return True
        return False

    def _build(self, lines: Sequence[str]) -> None:
        for index, raw in enumerate(lines):
            line = str(raw or "")
            self.lines.append(line)
            if not line.strip():
                continue

            matches = list(_WORD_RE.finditer(line))
            # 变量插值 [tamiko] / [char_name] 里的词是小写变量名，不是正文用词；
            # 若把它们算进统计，真实角色名会凭空多出一堆「小写同形」证据。
            blocked = self._parse_interpolation_spans(line)
            tokens: list[tuple[str, str, bool, bool]] = []
            for match in matches:
                token = match.group(0)
                if blocked and self._in_blocked(match.start(), blocked):
                    continue
                normalized = _normalize_token(token)
                if not normalized:
                    continue
                sentence_start = _is_sentence_start(line, match.start())
                capitalized = _is_capitalized(token)
                tokens.append((token, normalized, capitalized, sentence_start))

                evidence = self.words.get(normalized)
                if evidence is None:
                    evidence = WordEvidence()
                    self.words[normalized] = evidence
                evidence.total += 1
                evidence.forms[token] += 1
                if capitalized:
                    if sentence_start:
                        evidence.sentence_start += 1
                    else:
                        evidence.mid_capitalized += 1
                else:
                    evidence.lowercase += 1

                self.postings.setdefault(normalized, set()).add(index)

            self._collect_phrases(line, tokens)

    def _collect_phrases(
        self,
        line: str,
        tokens: Sequence[tuple[str, str, bool, bool]],
    ) -> None:
        """收集连续大写词构成的多词专名（允许内部连接词）。"""
        run: list[tuple[str, str, bool, bool]] = []
        runs: list[list[tuple[str, str, bool, bool]]] = []
        for token in tokens:
            _, normalized, capitalized, _ = token
            if capitalized or (run and normalized in CONNECTOR_WORDS):
                run.append(token)
                continue
            if run:
                runs.append(run)
            run = []
        if run:
            runs.append(run)

        for run in runs:
            # 去掉首尾虚词："Bank of" 不是完整专名；句首大写的 The/And/But
            # 只是行首大写，不属于专名本身（"And Queen" → "Queen"）。
            while run and run[-1][1] in CONNECTOR_WORDS:
                run = run[:-1]
            while len(run) > 1 and _is_stopword_casefold(run[0][1]):
                run = run[1:]
            if len(run) < 2:
                continue
            if not run[0][2] or not run[-1][2]:
                continue
            # 只取最长窗口，不再产出所有子串：否则 "Tom Yum Pla" 会同时给出
            # "Tom Yum" 和 "Yum Pla" 这类残缺片段。
            size = min(len(run), 4)
            for offset in range(0, len(run) - size + 1):
                chunk = run[offset:offset + size]
                if not chunk[0][2] or not chunk[-1][2]:
                    continue
                key = " ".join(item[1] for item in chunk)
                phrase = self.phrases.get(key)
                if phrase is None:
                    phrase = PhraseEvidence()
                    self.phrases[key] = phrase
                phrase.total += 1
                phrase.forms[" ".join(item[0] for item in chunk)] += 1
                if not chunk[0][3]:
                    phrase.mid_capitalized += 1

    # ------------------------------------------------------------- queries
    def line_indexes_for(self, text: str) -> set[int]:
        """返回可能包含该候选的语料行下标（惰性取交集）。"""
        normalized_words = [
            _normalize_token(token)
            for token in _WORD_RE.findall(str(text or ""))
        ]
        sets = [
            self.postings.get(word, set())
            for word in normalized_words
            if word and word not in CONNECTOR_WORDS
        ]
        if not sets:
            return set()
        sets.sort(key=len)
        result = set(sets[0])
        for other in sets[1:]:
            result &= other
            if not result:
                return set()
        return result


class ProperNounDetector:
    """基于统计证据挑选专有名词候选。"""

    def __init__(
        self,
        *,
        min_single_hits: int = 2,
        min_phrase_hits: int = 2,
        include_all_uppercase: bool = False,
    ) -> None:
        self.min_single_hits = max(1, int(min_single_hits))
        self.min_phrase_hits = max(1, int(min_phrase_hits))
        self.include_all_uppercase = include_all_uppercase

    def detect(self, evidence: CorpusEvidence) -> list[str]:
        candidates: list[str] = []
        seen: set[str] = set()

        accepted_phrases: list[tuple[str, PhraseEvidence]] = []
        for phrase, stat in evidence.phrases.items():
            if not self._accept_phrase(phrase, stat):
                continue
            display = " ".join(
                part for part in (_clean_display(token) for token in stat.display.split()) if part
            )
            if not display:
                continue
            key = display.casefold()
            if key in seen:
                continue
            seen.add(key)
            accepted_phrases.append((display, stat))
            candidates.append(display)

        # 只出现在某个已收录短语内部的单字（"Glacier's Edge" → Glacier、
        # "Tom Yum Pla" → Tom）是被短语切下来的碎片，单独收录没有意义。
        fragment_budget: dict[str, int] = {}
        for display, stat in accepted_phrases:
            for word in _WORD_RE.findall(display):
                normalized = _normalize_token(word)
                if normalized:
                    fragment_budget[normalized] = fragment_budget.get(normalized, 0) + stat.total

        singles: list[str] = []
        for word, stat in evidence.words.items():
            if not self._accept_single(word, stat):
                continue
            if stat.total <= fragment_budget.get(word, 0):
                continue
            display = _clean_display(stat.display)
            if not display:
                continue
            key = display.casefold()
            if key in seen:
                continue
            seen.add(key)
            singles.append(display)

        return singles + candidates

    # ------------------------------------------------------------ acceptance
    def validate_names(
        self,
        names: Iterable[str],
        evidence: CorpusEvidence,
    ) -> list[str]:
        """校验外部来源（如 Character() 定义）给出的名字是否像专有名词。

        Ren'Py 里 `Character(...)` 的第一参数经常是旁白标签或角色身份
        （Mom / Soldier / Unknown / Everyone），它们不是术语；用语料证据
        过滤后只留下真正在正文里被当作名字使用的词。
        """
        kept: list[str] = []
        seen: set[str] = set()
        for raw_name in names:
            name = _clean_display(str(raw_name or ""))
            if not name:
                continue
            key = name.casefold()
            if key in seen:
                continue
            if not self._accept_name(name, evidence):
                continue
            seen.add(key)
            kept.append(name)
        return kept

    def _accept_name(self, name: str, evidence: CorpusEvidence) -> bool:
        if len(name) < 2 or len(name) > 48:
            return False
        # 带编号/变量/占位符的角色标签（"School Girls #1"）不是术语。
        if re.search(r"[#\[\]{}<>\d]", name):
            return False

        words = [_normalize_token(token) for token in _WORD_RE.findall(name)]
        if not words:
            return False
        meaningful = [word for word in words if word and word not in CONNECTOR_WORDS]
        if not meaningful:
            return False
        if any(_is_stopword_casefold(word) for word in meaningful):
            return False

        if len(words) > 1:
            phrase = evidence.phrases.get(" ".join(words))
            if phrase is not None and phrase.mid_capitalized >= 1:
                return True

        for word in meaningful:
            stat = evidence.words.get(word)
            if stat is None:
                continue
            # 小写同形出现过，说明这是普通名词（soldier / master / woman）。
            if stat.lowercase > 0:
                return False
            if stat.mid_capitalized >= 1:
                return True
        return False

    def _accept_single(self, word: str, stat: WordEvidence) -> bool:
        if word in _COMMON_NON_TERM_SINGLE_WORDS:
            return False
        if _is_stopword_casefold(word):
            return False
        if word.casefold() in _HONORIFIC_NOISE:
            return False
        if stat.mid_capitalized < self.min_single_hits:
            return False
        # 小写同形出现说明这是普通词（"may" vs "May"、"rose" vs "Rose"）。
        if stat.lowercase > 0:
            return False
        display = stat.display
        if display.isupper() and len(display) > 1:
            if not self.include_all_uppercase:
                return False
            if word in _UPPERCASE_NOISE:
                return False
        # 纯数字/带数字的标识符不在专名范围。
        if re.search(r"\d", display):
            return False
        return True

    def _accept_phrase(self, phrase: str, stat: PhraseEvidence) -> bool:
        if stat.total < self.min_phrase_hits:
            return False
        words = phrase.split()
        if len(words) < 2:
            return False
        meaningful = [word for word in words if word not in CONNECTOR_WORDS]
        if not meaningful:
            return False
        # 短语不能以句首连词/语气词开头（"And Leo"、"Alright Leo"），
        # 这类短语全部来自「句首大写词 + 后面的人名」。
        if words[0] in _PHRASE_HEAD_BLOCKLIST:
            return False
        # 每个实词都不能是虚词，否则就是整句句首大写拼出来的假短语。
        if any(_is_stopword_casefold(word) for word in meaningful):
            return False
        if _is_stopword_casefold(words[-1]):
            return False
        if len(words) > 4:
            return False
        # 复读短语（"Eat Eat"、"Fun Fun"、"Queen and Queen"）都是界面按钮、
        # 拟声或连接词拼接出的假短语，真正的专名不会重复同一个实词。
        if len({word.casefold() for word in meaningful}) == 1:
            return False
        # 只在句中出现过才算专名：全部出现在句首的短语多半是按钮文案
        # （"Main Menu"、"Continue Training"），不是作品里的专有名词。
        if stat.mid_capitalized < self.min_phrase_hits:
            return False
        display = stat.display
        if re.search(r"\d", display):
            return False
        # 整串全大写的短语几乎都来自歌词/喊叫（"PUSSY FEELS"、"GONNA HURT"），
        # 作品里的专有名词不会全大写书写。
        if len(display) > 1 and display.isupper() and not self.include_all_uppercase:
            return False
        return True


def iter_word_tokens(text: str) -> Iterator[str]:
    """对外暴露的分词助手（供调用方复用同一套正则）。"""
    for match in _WORD_RE.finditer(str(text or "")):
        yield match.group(0)
