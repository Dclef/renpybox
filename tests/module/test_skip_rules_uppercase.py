from module.Text.SkipRules import (
    KEEP_AS_IS_UPPERCASE,
    RE_UPPERCASE_ACRONYM_CANDIDATE,
)


def _is_frozen(text: str) -> bool:
    return bool(
        RE_UPPERCASE_ACRONYM_CANDIDATE.fullmatch(text)
        and text in KEEP_AS_IS_UPPERCASE
    )


def test_ambiguous_and_unreachable_uppercase_terms_are_not_frozen():
    removed = {"SMS", "KPI", "MVP", "FAQ", "VIP", "ID", "TV", "3D", "4G", "5G"}

    assert not any(_is_frozen(text) for text in removed)


def test_common_technical_and_game_acronyms_remain_frozen():
    kept = {"USB", "NPC", "HP", "DLC"}

    assert all(_is_frozen(text) for text in kept)


def test_every_frozen_term_matches_uppercase_candidate_shape():
    assert all(
        RE_UPPERCASE_ACRONYM_CANDIDATE.fullmatch(text)
        for text in KEEP_AS_IS_UPPERCASE
    )
