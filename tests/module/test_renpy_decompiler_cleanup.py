from module.Tool.RenpyDecompiler import remove_decompiled_rpyc


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