import types

import pytest

from module.Extract.UnifiedExtractor import UnifiedExtractor


def _extractor() -> UnifiedExtractor:
    extractor = UnifiedExtractor.__new__(UnifiedExtractor)
    extractor.logger = types.SimpleNamespace(
        debug=lambda *args, **kwargs: None,
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
    )
    return extractor


def _write_fixture(source, target) -> None:
    source.mkdir(parents=True)
    target.mkdir(parents=True)
    source.joinpath("strings.rpy").write_text(
        'translate chinese strings:\n\n'
        '    old "Reusable"\n'
        '    new "旧译文"\n\n'
        '    old "Source placeholder"\n'
        '    new "原文占位译文"\n\n'
        '    old "Conflict"\n'
        '    new "旧冲突"\n\n'
        '    old "Already"\n'
        '    new "相同译文"\n',
        encoding="utf-8",
    )
    target.joinpath("strings.rpy").write_text(
        'translate chinese strings:\n\n'
        '    old "Reusable"\n'
        '    new ""\n\n'
        '    old "Source placeholder"\n'
        '    new "Source placeholder"\n\n'
        '    old "Conflict"\n'
        '    new "新人工译文"\n\n'
        '    old "Already"\n'
        '    new "相同译文"\n\n'
        '    old "Unmatched"\n'
        '    new ""\n',
        encoding="utf-8",
    )


def test_translation_reuse_preview_is_read_only_and_reports_conflicts(tmp_path):
    source = tmp_path / "old"
    target = tmp_path / "new"
    _write_fixture(source, target)
    before = target.joinpath("strings.rpy").read_text(encoding="utf-8")

    result = _extractor().preview_translation_reuse(source, target)

    assert result.source_translations == 4
    assert result.target_entries == 5
    assert result.matched_entries == 4
    assert result.reusable_entries == 2
    assert result.applied_entries == 0
    assert result.already_reused == 1
    assert result.conflicts == 1
    assert result.unmatched_entries == 1
    assert target.joinpath("strings.rpy").read_text(encoding="utf-8") == before


def test_translation_reuse_applies_only_empty_entries_and_creates_backup(tmp_path):
    source = tmp_path / "old"
    target = tmp_path / "new"
    _write_fixture(source, target)
    original = target.joinpath("strings.rpy").read_text(encoding="utf-8")
    extractor = _extractor()

    result = extractor.reuse_translations(source, target)

    output = target.joinpath("strings.rpy").read_text(encoding="utf-8")
    assert result.applied_entries == 2
    assert result.backup_path is not None
    assert result.backup_path.joinpath("strings.rpy").read_text(encoding="utf-8") == original
    assert 'new "旧译文"' in output
    assert 'new "原文占位译文"' in output
    assert 'new "新人工译文"' in output
    assert 'new "旧冲突"' not in output

    second = extractor.reuse_translations(source, target)
    assert second.applied_entries == 0
    assert second.reusable_entries == 0
    assert second.backup_path is None


def test_translation_reuse_rejects_same_or_missing_directories(tmp_path):
    target = tmp_path / "tl"
    target.mkdir()
    extractor = _extractor()

    with pytest.raises(ValueError, match="不能相同"):
        extractor.preview_translation_reuse(target, target)
    with pytest.raises(FileNotFoundError, match="旧译文目录不存在"):
        extractor.preview_translation_reuse(tmp_path / "missing", target)


def test_translation_reuse_places_game_backup_outside_active_game_tree(tmp_path):
    source = tmp_path / "old"
    project = tmp_path / "project"
    target = project / "game" / "tl" / "chinese"
    _write_fixture(source, target)

    result = _extractor().reuse_translations(source, target)

    assert result.backup_path is not None
    assert result.backup_path.parent == project
    assert result.backup_path.name.startswith("tl_backup_chinese_reuse_")
    assert result.backup_path.joinpath("strings.rpy").is_file()
