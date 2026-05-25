from __future__ import annotations

import random

from family_crossword.crosserville import _place_family_words
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
