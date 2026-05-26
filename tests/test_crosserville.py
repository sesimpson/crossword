from __future__ import annotations

import random

from family_crossword.crosserville import _current_visible_clue, _numbered_slots, _place_family_words
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
