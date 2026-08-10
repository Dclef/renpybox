from module.Extract.ReplaceGenerator import (
    clear_declined_candidates,
    declined_candidates_path,
    load_declined_candidates,
    record_declined_candidates,
)


def test_clear_declined_candidates_removes_existing_records(tmp_path):
    game_dir = tmp_path / "project"
    originals = {"TBD", "QUEST", "NOTICE"}
    assert record_declined_candidates(game_dir, "chinese", originals) == 3

    assert clear_declined_candidates(game_dir, "chinese") == 3
    assert not declined_candidates_path(game_dir, "chinese").exists()
    assert load_declined_candidates(game_dir, "chinese") == set()


def test_clear_declined_candidates_ignores_missing_file(tmp_path):
    game_dir = tmp_path / "project"

    assert clear_declined_candidates(game_dir, "chinese") == 0
    assert load_declined_candidates(game_dir, "chinese") == set()
