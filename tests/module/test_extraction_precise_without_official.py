from types import SimpleNamespace

from module.Extract import UnifiedExtractor as unified_extractor_module  # noqa: F401
from module.Extract.UnifiedExtractor import UnifiedExtractor
from module.Renpy import renpy_extract as rx


def _config(monkeypatch, *, mode: str = "precise") -> SimpleNamespace:
    config = SimpleNamespace(
        extract_use_official=True,
        extract_use_custom=True,
        extract_supplement_mode=mode,
        text_preserve_enable=False,
        onekey_inject_base_box=False,
        extract_export_excel=False,
        renpy_filter_suspicious_bool_expr=False,
        renpy_incremental_include_untranslated=False,
    )
    monkeypatch.setattr("module.Extract.UnifiedExtractor.Config.load", lambda _self: config)
    monkeypatch.setattr(rx, "is_python2_from_game_dir", lambda _path: False)
    return config


def test_precise_supplement_extracts_dialogue_when_official_did_not_run(tmp_path, monkeypatch):
    """没有 exe 时官方抽取不会执行，精准补充模式必须退回全量，否则纯对话项目抽出 0 条。"""
    _config(monkeypatch)
    monkeypatch.setattr(UnifiedExtractor, "_post_process", lambda *_args: None)
    source = tmp_path / "game" / "script.rpy"
    source.parent.mkdir()
    source.write_text(
        'label start:\n'
        '    e "Hello there, agent pipeline."\n'
        '    e "This dialogue must survive precise mode."\n',
        encoding="utf-8",
    )

    extractor = UnifiedExtractor(SimpleNamespace())
    result = extractor.extract_regular(tmp_path, "chinese", None)

    assert result.success, result.message
    written = (tmp_path / "game" / "tl" / "chinese" / "script.rpy").read_text(encoding="utf-8")
    assert 'old "Hello there, agent pipeline."' in written
    assert 'old "This dialogue must survive precise mode."' in written


def test_precise_supplement_skips_dialogue_when_official_succeeded(tmp_path, monkeypatch):
    """官方抽取已经覆盖对话时，精准模式保持只补 UI，避免重复条目。"""
    _config(monkeypatch)
    monkeypatch.setattr(UnifiedExtractor, "_post_process", lambda *_args: None)
    source = tmp_path / "game" / "script.rpy"
    source.parent.mkdir()
    source.write_text(
        'label start:\n'
        '    e "Dialogue covered by official extraction."\n'
        'screen hud():\n'
        '    text "HUD label only custom extraction sees."\n',
        encoding="utf-8",
    )
    tl_dir = tmp_path / "game" / "tl" / "chinese"

    def official(_exe, _language, **_kwargs):
        tl_dir.mkdir(parents=True, exist_ok=True)
        (tl_dir / "script.rpy").write_text(
            'translate chinese strings:\n'
            '    old "Dialogue covered by official extraction."\n'
            '    new ""\n',
            encoding="utf-8",
        )

    extractor = UnifiedExtractor(SimpleNamespace(official_extract=official))
    result = extractor.extract_regular(tmp_path, "chinese", "game.exe")

    assert result.success, result.message
    written = (tl_dir / "script.rpy").read_text(encoding="utf-8")
    assert 'old "HUD label only custom extraction sees."' in written
