# -*- coding: utf-8 -*-
"""一键翻译第 4 步“翻译已完成”状态回归测试。"""

from types import SimpleNamespace

from frontend.RenpyToolbox.OneKeyTranslatePage import YiJianFanyiPage


def test_step4_refresh_shows_completed_state():
    status_texts = []
    start_texts = []
    skip_texts = []
    start_enabled = []
    page = SimpleNamespace(
        _onekey_translation_completed=True,
        _translation_output_completed=lambda: False,
        step4_status=SimpleNamespace(
            setText=status_texts.append,
            setStyleSheet=lambda value: None,
        ),
        start_trans_btn=SimpleNamespace(
            setText=start_texts.append,
            setEnabled=start_enabled.append,
        ),
        skip_trans_btn=SimpleNamespace(setText=skip_texts.append),
    )

    YiJianFanyiPage._refresh_step4_state(page)

    assert "翻译已完成" in status_texts[-1]
    assert start_texts[-1] == "重新翻译"
    assert skip_texts[-1] == "进入后续处理 →"
    assert start_enabled[-1] is True


def test_step4_refresh_falls_back_to_ready_check_when_not_completed():
    status_texts = []
    start_texts = []
    skip_texts = []
    ready_calls = []
    page = SimpleNamespace(
        _onekey_translation_completed=False,
        _translation_output_completed=lambda: False,
        step4_status=SimpleNamespace(
            setText=status_texts.append,
            setStyleSheet=lambda value: None,
        ),
        start_trans_btn=SimpleNamespace(
            setText=start_texts.append,
            setEnabled=lambda value: None,
        ),
        skip_trans_btn=SimpleNamespace(setText=skip_texts.append),
        _refresh_step4_ready=lambda: ready_calls.append(True) or True,
    )

    YiJianFanyiPage._refresh_step4_state(page)

    assert ready_calls == [True]
    assert start_texts[-1] == "🚀 开始翻译"
    assert skip_texts[-1] == "跳过翻译 →"
