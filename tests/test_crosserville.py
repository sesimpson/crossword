from __future__ import annotations

import random

from family_crossword.crosserville import (
    _answers_by_entry,
    _current_visible_clue,
    _fill_seconds,
    _family_template_score,
    _numbered_slots,
    _place_family_words,
    _template_rows,
)
from family_crossword.model import Candidate


def test_place_family_words_uses_compatible_slots_only() -> None:
    rows = [
        "....#..",
        "....#..",
        "#######",
        ".......",
        "#######",
        "....#..",
        "....#..",
    ]
    candidates = [
        Candidate("ABLE", priority=10, is_family=True),
        Candidate("BETA", priority=8, is_family=True),
        Candidate("SEVENS", priority=9, is_family=True),
    ]

    seeded_rows, placed = _place_family_words(rows, candidates, random.Random(4), attempt=0)

    assert placed
    assert "SEVENS" not in placed
    assert all(len(word) == 4 for word in placed)
    assert len(seeded_rows) == len(rows)


def test_numbered_slots_and_visible_clue_parser() -> None:
    rows = [
        "DOG",
        "ARE",
        "TEN",
    ]
    assert _numbered_slots(rows)[:4] == [
        (1, "across", 0, 0),
        (1, "down", 0, 0),
        (2, "down", 0, 1),
        (3, "down", 0, 2),
    ]

    class FakeLocator:
        def inner_text(self, timeout=0):
            return "30-Across (5)\nBELAY\n(30)\nFasten, as a ship's rope\nSlot Options"

    class FakePage:
        def locator(self, selector):
            return FakeLocator()

    assert _current_visible_clue(FakePage(), 30, "across") == "Fasten, as a ship's rope"


def test_answers_by_entry_matches_numbered_slots() -> None:
    rows = [
        "DOG",
        "ARE",
        "TEN",
    ]

    assert _answers_by_entry(rows)[:4] == [
        (1, "across", "DOG"),
        (1, "down", "DAT"),
        (2, "down", "ORE"),
        (3, "down", "GEN"),
    ]


def test_family_template_score_prefers_candidate_length_matches() -> None:
    five_letter_grid = ["....."] * 5
    seven_letter_grid = ["......."] * 7
    candidates = [
        Candidate("DINNER", priority=10, is_family=True),
        Candidate("OVERDUE", priority=10, is_family=True),
    ]

    assert _family_template_score(seven_letter_grid, candidates) > _family_template_score(five_letter_grid, candidates)


def test_dense_family_seed_sets_get_longer_fill_budget(monkeypatch) -> None:
    monkeypatch.setenv("CROSSWORD_FILL_SECONDS", "12")
    monkeypatch.setenv("CROSSWORD_DENSE_FILL_SECONDS", "80")

    assert _fill_seconds(["NICO", "SHAWN"]) == 12
    assert _fill_seconds(["NICO", "SHAWN", "BYRON", "DINNER", "OVERDUE"]) == 80


def test_template_rows_rotates_ranked_crosserville_patterns() -> None:
    first = ["....."] * 5
    second = ["...#.", "...#.", ".....", ".#...", ".#..."]
    candidates = [Candidate("PIANO", priority=8, is_family=True)]

    rows_0, source_0 = _template_rows(5, random.Random(1), 0, candidates, [first, second])
    rows_1, source_1 = _template_rows(5, random.Random(1), 1, candidates, [first, second])

    assert rows_0 != rows_1
    assert source_0 == "crosserville-template-rank-1"
    assert source_1 == "crosserville-template-rank-2"
