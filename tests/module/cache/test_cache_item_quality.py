import json
from types import SimpleNamespace

import pytest

from base.Base import Base
from frontend.Proofreading.ProofreadingPage import ProofreadingPage
from module.Cache.CacheItem import CacheItem
from module.File.TRANS.TRANS import TRANS


def test_polished_is_an_item_only_completed_status() -> None:
    status = Base.TranslationStatus.POLISHED

    assert Base.is_item_status(status)
    assert Base.is_item_completed(status)
    assert Base.is_item_proofreadable(status)
    assert not Base.is_item_polishable(status)
    assert not Base.is_project_status(status)

    with pytest.raises(ValueError, match="Invalid cache item status"):
        CacheItem(status=Base.TranslationStatus.TRANSLATING)


def test_quality_result_round_trips_through_cache_serialization() -> None:
    item = CacheItem(
        src="source",
        dst="translation",
        status=Base.TranslationStatus.TRANSLATED,
        metadata={"trace_id": "kept"},
    )

    item.set_quality_result("polished", CacheItem.QualityOrigin.POLISHER)
    payload = json.loads(json.dumps(item.asdict(), ensure_ascii=False))
    restored = CacheItem.from_dict(payload)

    assert restored.get_dst() == "polished"
    assert restored.get_status() == Base.TranslationStatus.POLISHED
    assert restored.get_quality_origin() == CacheItem.QualityOrigin.POLISHER
    assert restored.get_metadata()["trace_id"] == "kept"


def test_reset_translation_clears_quality_metadata_only() -> None:
    item = CacheItem(
        dst="polished",
        status=Base.TranslationStatus.POLISHED,
        retry_count=2,
        metadata={
            "quality_origin": CacheItem.QualityOrigin.PROOFREADER.value,
            "translation_retry": {"schema_version": 1, "attempt": 2},
            "trace_id": "kept",
        },
    )

    item.reset_translation()

    assert item.get_dst() == ""
    assert item.get_status() == Base.TranslationStatus.UNTRANSLATED
    assert item.get_retry_count() == 0
    assert item.get_quality_origin() is None
    assert item.get_metadata() == {"trace_id": "kept"}


def test_manual_edit_does_not_downgrade_polished_item() -> None:
    item = CacheItem(dst="translated", status=Base.TranslationStatus.TRANSLATED)
    item.set_quality_result("polished", CacheItem.QualityOrigin.POLISHER)
    page = SimpleNamespace(is_readonly=False, _recheck_item=lambda _: None)

    ProofreadingPage._on_cell_edited(page, item, "manually edited")

    assert item.get_dst() == "manually edited"
    assert item.get_status() == Base.TranslationStatus.POLISHED
    assert item.get_quality_origin() is None


def test_translation_copy_commits_only_when_original_state_is_unchanged() -> None:
    item = CacheItem(dst="old", status=Base.TranslationStatus.POLISHED)
    item.set_quality_origin(CacheItem.QualityOrigin.POLISHER)
    expected = item.get_translation_state()
    working = CacheItem.from_dict(item.asdict())
    working.reset_translation(clear_dst=False)
    working.set_dst("new")
    working.set_status(Base.TranslationStatus.TRANSLATED)

    assert item.commit_translation_from(working, expected)
    assert item.get_dst() == "new"
    assert item.get_status() == Base.TranslationStatus.TRANSLATED
    assert item.get_quality_origin() is None

    stale_expected = item.get_translation_state()
    stale_working = CacheItem.from_dict(item.asdict())
    stale_working.set_dst("model result")
    item.set_dst("user edit")

    assert not item.commit_translation_from(stale_working, stale_expected)
    assert item.get_dst() == "user edit"


def test_trans_deduplication_reuses_polished_translation(tmp_path) -> None:
    output_path = tmp_path / "output"
    rel_path = "project.trans"
    temp_path = output_path / "cache" / "temp" / rel_path
    temp_path.parent.mkdir(parents=True)
    temp_path.write_text(
        json.dumps(
            {
                "project": {
                    "gameEngine": "",
                    "files": {
                        "script.txt": {
                            "tags": [[], []],
                            "data": [["same", ""], ["same", ""]],
                            "context": [[], []],
                            "parameters": [[], []],
                        }
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    common = {
        "src": "same",
        "tag": "script.txt",
        "file_type": CacheItem.FileType.TRANS,
        "file_path": rel_path,
        "extra_field": {"tag": [], "context": [], "parameter": []},
    }
    polished = CacheItem(
        **common,
        row=0,
        dst="polished translation",
        status=Base.TranslationStatus.POLISHED,
    )
    duplicated = CacheItem(
        **common,
        row=1,
        status=Base.TranslationStatus.DUPLICATED,
    )
    config = SimpleNamespace(
        input_folder=str(tmp_path / "input"),
        output_folder=str(output_path),
        source_language=None,
        target_language=None,
        deduplication_in_trans=True,
    )

    TRANS(config).write_to_path([polished, duplicated])

    written = json.loads((output_path / rel_path).read_text(encoding="utf-8"))
    assert duplicated.get_dst() == "polished translation"
    assert written["project"]["files"]["script.txt"]["data"][1][1] == "polished translation"
