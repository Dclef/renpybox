"""专名检测器：把「句首大写」「界面按钮」「语气词」从术语候选里剔掉。"""

from __future__ import annotations

from module.Extract.ProperNounDetector import (
    CorpusEvidence,
    ProperNounDetector,
    iter_word_tokens,
)


def detect(lines, **kwargs):
    return ProperNounDetector(**kwargs).detect(CorpusEvidence(lines))


def test_detector_keeps_names_used_mid_sentence():
    lines = [
        "Leo: I saw Alice yesterday.",
        "She said Alice was gone.",
        "What did Alice do?",
    ]
    result = detect(lines)
    assert "Alice" in result
    assert "Leo" not in result  # 只作为说话人前缀出现，没有句中大写证据


def test_detector_drops_sentence_start_words():
    # 句首大写的普通词没有句中大写证据，必须被剔除。
    lines = [
        "What are you doing here?",
        "What a day.",
        "Anyway, what now?",
    ]
    result = detect(lines)
    assert "What" not in result
    assert "Anyway" not in result


def test_detector_drops_words_that_also_appear_lowercase():
    # 小写同形出现说明它是普通词，而不是专名。
    lines = [
        "Watch out, the mayor is coming.",
        "Mayor is late again.",
        "Mayor said nothing.",
    ]
    result = detect(lines)
    assert "Mayor" not in result


def test_detector_drops_interjections():
    lines = [
        "Hmm. I don't know.",
        "He said Hmm and left.",
    ]
    result = detect(lines)
    assert "Hmm" not in result


def test_detector_ignores_variable_interpolation():
    # [alice] 是 Ren'Py 变量插值，里面的词不算正文用词。
    lines = [
        "She looked at [alice] and smiled.",
        "[alice] nodded.",
    ]
    result = detect(lines)
    assert "alice" not in result


def test_detector_keeps_multiword_phrase_used_mid_sentence():
    lines = [
        "We went to the East Square at noon.",
        "The East Square was empty.",
    ]
    result = detect(lines)
    assert "East Square" in result


def test_detector_drops_button_like_phrases():
    # 只在句首出现的连续大写词多半是按钮/标题文案。
    lines = [
        "Continue Training",
        "Continue Training",
    ]
    result = detect(lines)
    assert "Continue Training" not in result


def test_detector_drops_all_caps_phrases():
    lines = [
        "He yelled PIECE OF SHIT at me.",
        "So I said PIECE OF SHIT back.",
    ]
    result = detect(lines)
    assert "PIECE OF SHIT" not in result


def test_detector_treats_format_tags_as_transparent():
    # {b}Notice Board{/b} 的 Notice 前面只有格式标签，属于句中大写。
    lines = [
        "And place them on the {b}Notice Board{/b} in front of the palace.",
        "There's a free book available at the {b}Notice Board{/b}.",
        "This is the {b}The Knighting ceremony{/b}.",
        "I haven't seen her since the Knighting ceremony.",
        "The Knighting ceremony...",
    ]
    result = detect(lines)
    assert "Notice Board" in result


def test_detector_drops_honorifics():
    lines = [
        "Yes, Your Majesty is wise.",
        "We serve His Majesty loyally.",
        "Your Majesty, please.",
    ]
    result = detect(lines)
    assert "Majesty" not in result


def test_detector_drops_numeric_and_symbol_tokens():
    lines = [
        "That was Robot 3000 again.",
        "Robot 3000 is here.",
    ]
    result = detect(lines)
    assert "Robot 3000" not in result


def test_iter_word_tokens_matches_detector_tokenizer():
    # 调用方用同一套正则做倒排索引，必须与检测器分词一致。
    assert list(iter_word_tokens("Tom-Yum and Leo's")) == ["Tom-Yum", "and", "Leo's"]


def test_detector_keeps_short_and_repeated_letter_names():
    names = ["Ann", "Lee", "Ai", "Jo", "Ed", "Yu", "Bo", "Al"]
    lines = [
        line
        for name in names
        for line in (f"I spoke with {name} yesterday.", f"We waited for {name} outside.")
    ]
    assert set(names).issubset(detect(lines))
    assert "Ann Lee" in detect(["I called Ann Lee yesterday.", "We waited for Ann Lee outside."])


def test_detector_still_drops_stretched_interjections():
    for sound in ("Ahhhhh", "Mmmmm", "Hmmm", "Uhhh", "Shhhh", "Oooo"):
        assert sound not in detect([f"He said {sound} quietly.", f"She said {sound} too."])
