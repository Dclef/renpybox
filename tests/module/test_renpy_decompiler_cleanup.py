from pathlib import Path

import pytest

from module.Tool.RenpyDecompiler import RenpyDecompiler, remove_decompiled_rpyc


def test_remove_decompiled_rpyc_only_removes_matching_source_files(tmp_path) -> None:
    game_dir = tmp_path / "game"
    source_dir = game_dir / "chapter"
    source_dir.mkdir(parents=True)
    (source_dir / "script.rpy").write_text("label start:\n    pass\n", encoding="utf-8")
    matching = source_dir / "script.rpyc"
    matching.write_bytes(b"compiled")
    unmatched = source_dir / "extra.rpyc"
    unmatched.write_bytes(b"compiled")

    tl_dir = game_dir / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    (tl_dir / "script.rpy").write_text("translate chinese start:\n    pass\n", encoding="utf-8")
    translated = tl_dir / "script.rpyc"
    translated.write_bytes(b"compiled")

    assert remove_decompiled_rpyc(game_dir) == 1
    assert not matching.exists()
    assert unmatched.exists()
    assert translated.exists()


def test_resource_variant_matches_embedded_python_major() -> None:
    assert RenpyDecompiler._resource_variant_for_python_major(2) == "unrpyc_python_v1"
    assert RenpyDecompiler._resource_variant_for_python_major(3) == "unrpyc_python_v2"


def test_unknown_python_major_stops_before_decompilation() -> None:
    with pytest.raises(RuntimeError, match="无法识别游戏内置 Python 主版本"):
        RenpyDecompiler._resource_variant_for_python_major(None)


def test_bundled_unrpyc_versions_are_pinned() -> None:
    root = Path(__file__).parents[2]
    v1 = (root / "resource" / "unrpyc_python_v1" / "unrpyc.py").read_text(encoding="utf-8")
    v2 = (root / "resource" / "unrpyc_python_v2" / "unrpyc.py").read_text(encoding="utf-8")
    assert "__version__ = 'v1.3.2'" in v1
    assert "__version__ = 'v2.0.3'" in v2


def test_v1_does_not_fold_child_atl_into_has_statement() -> None:
    root = Path(__file__).parents[2]
    source = (
        root
        / "resource"
        / "unrpyc_python_v1"
        / "decompiler"
        / "sl2decompiler.py"
    ).read_text(encoding="utf-8")
    assert "child_atl_transform = None" in source
    assert "and child_atl_transform is None" in source
