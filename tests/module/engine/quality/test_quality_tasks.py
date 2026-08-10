from __future__ import annotations

import pytest

from base.Base import Base
from base.BaseLanguage import BaseLanguage
from module.Cache.CacheItem import CacheItem
from module.Config import Config
from module.Engine.Quality.PolisherTask import PolisherTask
from module.Engine.Quality.ProofreadTask import ProofreadTask
from module.Engine.Quality._common import (
    QualityItemSnapshot,
    QualityPromptBuilder,
    collect_constraints,
)
from module.Engine.TaskRequester import TaskRequester
from module.Engine.Translator.TranslationTaskContext import (
    ProjectAssets,
    TranslationTaskContext,
)
from module.ResultChecker import WarningType


class QueueRequester:
    def __init__(self, responses: list[object]) -> None:
        self.responses = list(responses)
        self.calls: list[list[dict[str, str]]] = []

    def request(self, messages: list[dict[str, str]]):
        self.calls.append(messages)
        response = self.responses.pop(0)
        if isinstance(response, tuple):
            return response
        return False, "", response, 3, 5


@pytest.mark.parametrize(
    ("task_type", "protocol", "expected_shape"),
    (
        (PolisherTask, Config.OUTPUT_PROTOCOL_STRUCTURED, "json_object"),
        (PolisherTask, Config.OUTPUT_PROTOCOL_JSONLINE, "none"),
        (ProofreadTask, Config.OUTPUT_PROTOCOL_JSONLINE, "none"),
    ),
)
def test_quality_task_declares_request_shape(
    monkeypatch,
    task_type,
    protocol: str,
    expected_shape: str,
) -> None:
    context = make_context(protocol = protocol)
    requester = TaskRequester(
        Config(),
        {
            "api_key": ["test-key"],
            "api_url": "https://example.invalid",
            "api_format": Base.APIFormat.OPENAI,
            "model": "test-model",
            "thinking": False,
        },
        0,
    )
    observed: list[str] = []

    def request(messages, *, response_shape = "none"):
        observed.append(response_shape)
        return False, "", "ok", 1, 1

    monkeypatch.setattr(requester, "request", request)
    task = task_type(context, requester = requester)

    outcome = task._request([{"role": "user", "content": "test"}])

    assert outcome.ok is True
    assert observed == [expected_shape]


def make_context(
    *,
    protocol: str = Config.OUTPUT_PROTOCOL_JSONLINE,
    source_language: BaseLanguage.Enum = BaseLanguage.Enum.EN,
) -> TranslationTaskContext:
    config = Config(
        source_language = source_language,
        target_language = BaseLanguage.Enum.ZH,
        translation_output_protocol = protocol,
    )
    assets = ProjectAssets.from_dict({
        "revision": 3,
        "worldbook": {
            "enabled": True,
            "data": {"setting_summary": "A quiet fantasy town"},
        },
        "glossary": {
            "enabled": True,
            "items": [
                {"source": "Alice", "target": "爱丽丝", "origin": "LOCAL"},
                {"source": "Sword", "target": "剑", "origin": "LOCAL"},
            ],
        },
        "do_not_translate": {
            "enabled": True,
            "items": [{"source": "Ren'Py"}],
        },
    })
    return TranslationTaskContext.from_config(
        config,
        assets,
        prompt = {
            "mode": Config.PROMPT_MODE_COMMON,
            "resolved_base": "",
            "style_id": Config.STYLE_NONE,
            "resolved_style": "",
            "protocol": protocol,
            "protocol_version": 1,
        },
        created_at = "2026-07-24T08:00:00+00:00",
    )


def translated_item(source: str, translation: str) -> CacheItem:
    return CacheItem(
        src = source,
        dst = translation,
        status = Base.TranslationStatus.TRANSLATED,
    )


def test_polisher_reorders_strict_indices_and_only_consumes_translated() -> None:
    context = make_context()
    first = translated_item("Alice finds Sword {w}", "爱丽丝找到了剑 {w}")
    second = translated_item("Open the door.", "打开门。")
    already_polished = translated_item("Wait.", "等等。")
    already_polished.set_quality_result("请稍等。", CacheItem.QualityOrigin.PROOFREADER)
    requester = QueueRequester([
        '{"request_index":1,"text":"把门打开。"}\n'
        '{"request_index":0,"text":"爱丽丝寻得了剑 {w}"}',
    ])

    result = PolisherTask(context, requester = requester).run(
        [first, already_polished, second]
    )

    assert result.total_count == 3
    assert result.eligible_count == 2
    assert result.updated_count == 2
    assert result.skipped_count == 1
    assert result.failed_count == 0
    assert result.input_tokens == 3
    assert result.output_tokens == 5
    assert first.get_dst() == "爱丽丝寻得了剑 {w}"
    assert first.get_status() == Base.TranslationStatus.POLISHED
    assert first.get_quality_origin() == CacheItem.QualityOrigin.POLISHER
    assert second.get_dst() == "把门打开。"
    assert already_polished.get_dst() == "请稍等。"
    assert already_polished.get_quality_origin() == CacheItem.QualityOrigin.PROOFREADER
    assert '"request_index": 0' in requester.calls[0][1]["content"]
    assert '"current_translation"' in requester.calls[0][1]["content"]


def test_polisher_rejects_missing_index_without_any_writeback() -> None:
    context = make_context()
    first = translated_item("Alice finds Sword.", "爱丽丝找到了剑。")
    second = translated_item("Open the door.", "打开门。")
    requester = QueueRequester([
        '{"request_index":0,"text":"爱丽丝寻得了剑。"}',
    ])

    result = PolisherTask(context, requester = requester).run([first, second])

    assert result.updated_count == 0
    assert result.failed_count == 2
    assert {failure.reason for failure in result.failures} == {"INDEXED_RESPONSE_INVALID"}
    assert first.get_dst() == "爱丽丝找到了剑。"
    assert first.get_status() == Base.TranslationStatus.TRANSLATED
    assert first.get_quality_origin() is None
    assert second.get_dst() == "打开门。"
    assert second.get_status() == Base.TranslationStatus.TRANSLATED


def test_polisher_validates_each_aligned_record_before_individual_writeback() -> None:
    context = make_context()
    invalid = translated_item("Alice finds Sword {w}", "爱丽丝找到了剑 {w}")
    valid = translated_item("Open the door.", "打开门。")
    requester = QueueRequester([
        '{"request_index":0,"text":"爱丽丝找到武器。"}\n'
        '{"request_index":1,"text":"把门打开。"}',
    ])

    result = PolisherTask(context, requester = requester).run([invalid, valid])

    assert result.updated_count == 1
    assert result.failed_count == 1
    assert "PROTECTED_MARKER_MISMATCH" in result.failures[0].reason
    assert "MISSING_TERM:Sword->剑" in result.failures[0].reason
    assert invalid.get_dst() == "爱丽丝找到了剑 {w}"
    assert invalid.get_status() == Base.TranslationStatus.TRANSLATED
    assert invalid.get_quality_origin() is None
    assert valid.get_dst() == "把门打开。"
    assert valid.get_status() == Base.TranslationStatus.POLISHED


def test_polisher_uses_structured_protocol_from_context() -> None:
    context = make_context(protocol = Config.OUTPUT_PROTOCOL_STRUCTURED)
    item = translated_item("Open the door.", "打开门。")
    requester = QueueRequester([
        '{"translations":[{"request_index":0,"text":"把门打开。"}],"new_glossary":[]}',
    ])

    task = PolisherTask(context, requester = requester)
    result = task.run([item])

    assert task.runtime_config.translation_output_protocol == Config.OUTPUT_PROTOCOL_STRUCTURED
    assert context.prompt["protocol"] == Config.OUTPUT_PROTOCOL_STRUCTURED
    assert result.updated_count == 1


def test_polisher_falls_back_from_single_text_to_indexed_jsonline() -> None:
    context = make_context(protocol = Config.OUTPUT_PROTOCOL_SINGLE_TEXT)
    item = translated_item("Open the door.", "打开门。")
    requester = QueueRequester([
        '{"request_index":0,"text":"把门打开。"}',
    ])

    task = PolisherTask(context, requester = requester)
    result = task.run([item])

    assert task.protocol == Config.OUTPUT_PROTOCOL_JSONLINE
    assert task.runtime_config.translation_output_protocol == Config.OUTPUT_PROTOCOL_JSONLINE
    assert context.prompt["protocol"] == Config.OUTPUT_PROTOCOL_SINGLE_TEXT
    assert result.updated_count == 1


def test_proofread_retries_validation_once_then_writes_proofreader_origin() -> None:
    context = make_context()
    item = translated_item("Take Sword {w}", "拿起剑 {w}")
    requester = QueueRequester(["拿起武器", "请拿起剑 {w}"])

    result = ProofreadTask(context, requester = requester).run(
        [item],
        warning_map = {id(item): [WarningType.GLOSSARY, WarningType.TEXT_PRESERVE]},
    )

    assert len(requester.calls) == 2
    assert result.updated_count == 1
    assert result.failed_count == 0
    assert result.input_tokens == 6
    assert result.output_tokens == 10
    assert item.get_dst() == "请拿起剑 {w}"
    assert item.get_status() == Base.TranslationStatus.POLISHED
    assert item.get_quality_origin() == CacheItem.QualityOrigin.PROOFREADER
    assert '"GLOSSARY"' in requester.calls[0][1]["content"]
    assert "previous revision failed" in requester.calls[1][1]["content"]


def test_proofread_failure_after_two_attempts_preserves_polished_state_and_metadata() -> None:
    context = make_context()
    item = translated_item("Take Sword {w}", "拿起剑 {w}")
    item.set_quality_result("拿起剑 {w}", CacheItem.QualityOrigin.POLISHER)
    requester = QueueRequester(["拿起武器", ""])

    result = ProofreadTask(context, requester = requester).run([item])

    assert len(requester.calls) == ProofreadTask.MAX_ATTEMPTS
    assert result.updated_count == 0
    assert result.failed_count == 1
    assert result.failures[0].attempts == 2
    assert item.get_dst() == "拿起剑 {w}"
    assert item.get_status() == Base.TranslationStatus.POLISHED
    assert item.get_quality_origin() == CacheItem.QualityOrigin.POLISHER


def test_proofread_processes_translated_and_polished_but_skips_other_statuses() -> None:
    context = make_context()
    translated = translated_item("Open the door.", "打开门。")
    polished = translated_item("Close the door.", "关门。")
    polished.set_quality_result("把门关上。", CacheItem.QualityOrigin.POLISHER)
    untranslated = CacheItem(src = "Wait.")
    requester = QueueRequester(["请把门打开。", "请把门关上。"])

    result = ProofreadTask(context, requester = requester).run(
        [translated, untranslated, polished]
    )

    assert len(requester.calls) == 2
    assert result.eligible_count == 2
    assert result.updated_count == 2
    assert result.skipped_count == 1
    assert untranslated.get_status() == Base.TranslationStatus.UNTRANSLATED
    assert translated.get_quality_origin() == CacheItem.QualityOrigin.PROOFREADER
    assert polished.get_quality_origin() == CacheItem.QualityOrigin.PROOFREADER


def test_proofread_rejects_obvious_source_language_residue_before_writeback() -> None:
    context = make_context(source_language = BaseLanguage.Enum.JA)
    item = translated_item("こんにちは", "你好")
    requester = QueueRequester(["こんにちは", "你好呀"])

    result = ProofreadTask(context, requester = requester).run([item])

    assert len(requester.calls) == 2
    assert result.updated_count == 1
    assert item.get_dst() == "你好呀"
    assert item.get_quality_origin() == CacheItem.QualityOrigin.PROOFREADER


def test_proofread_rejects_structured_response_in_single_text_mode() -> None:
    context = make_context()
    item = translated_item("Open the door.", "打开门。")
    requester = QueueRequester([
        '{"request_index":0,"text":"把门打开。"}',
        "把门打开。",
    ])

    result = ProofreadTask(context, requester = requester).run([item])

    assert len(requester.calls) == 2
    assert result.updated_count == 1
    assert item.get_dst() == "把门打开。"


def test_quality_tasks_reject_mutable_config_instead_of_sharing_it() -> None:
    config = Config()

    for task_type in (PolisherTask, ProofreadTask):
        try:
            task_type(config, requester = QueueRequester([]))
        except TypeError as exc:
            assert "TranslationTaskContext" in str(exc)
        else:
            raise AssertionError("quality task accepted mutable Config")


def test_quality_constraints_keep_character_terms_independent_and_dnt_wins() -> None:
    context = TranslationTaskContext.from_config(
        Config(source_language = BaseLanguage.Enum.EN, target_language = BaseLanguage.Enum.ZH),
        ProjectAssets.from_dict({
            "character_cards": {
                "enabled": True,
                "items": [{"name": "Alice", "name_translation": "爱丽丝"}],
            },
            "glossary": {
                "enabled": True,
                "items": [
                    {"source": "Ren'Py", "target": "引擎", "origin": "LOCAL"},
                    {"source": "Sword", "target": "剑", "origin": "LOCAL"},
                ],
            },
            "do_not_translate": {
                "enabled": True,
                "items": [{"source": "Ren'Py"}],
            },
        }),
        created_at = "2026-07-24T08:00:00+00:00",
    )

    speaker_item = CacheItem(src = "Alice [Sword] uses Ren'Py", name_src = "Alice")
    constraints = collect_constraints(context, speaker_item.get_src())

    assert constraints.required_terms == (("Alice", "爱丽丝"),)
    assert constraints.do_not_translate == ("Ren'Py",)

    metadata_item = translated_item("Hello.", "你好。")
    metadata_item.set_name_src("Alice")
    snapshot = QualityItemSnapshot.from_item(
        metadata_item,
        request_index = 0,
        item_index = 0,
    )
    messages = QualityPromptBuilder(context).build_proofread_prompt(
        snapshot,
        error_types = ("USER_SELECTED",),
    )
    assert "Alice" in messages[0]["content"]
    assert "爱丽丝" in messages[0]["content"]
