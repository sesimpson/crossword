import random

from family_crossword.model import Candidate, FilledPuzzle
from family_crossword.solver import fill_pattern, puzzle_selection_score


def test_solver_prefers_family_entries_and_is_deterministic() -> None:
    blocks = [[False for _ in range(5)] for _ in range(5)]
    candidates = [
        Candidate("ABCDE", priority=10, source="people", is_family=True),
        Candidate("FGHIJ", source="generic"),
        Candidate("KLMNO", source="generic"),
        Candidate("PQRST", source="generic"),
        Candidate("UVWXY", source="generic"),
        Candidate("AFKPU", source="generic"),
        Candidate("BGLQV", source="generic"),
        Candidate("CHMRW", source="generic"),
        Candidate("DINSX", source="generic"),
        Candidate("EJOTY", source="generic"),
    ]

    puzzle = fill_pattern(blocks, candidates, random.Random(7), metadata={"title": "Test"})

    assert puzzle is not None
    assert puzzle.grid_rows() == ["ABCDE", "FGHIJ", "KLMNO", "PQRST", "UVWXY"]
    assert puzzle.score_report["family_count"] == 1


def test_selection_score_prefers_weekly_context_when_family_count_matches() -> None:
    names_only = FilledPuzzle(
        size=11,
        grid=[],
        entries=[],
        metadata={},
        score_report={"family_count": 4, "family_score": 50_000, "weekly_count": 0, "family_source_count": 1, "entry_count": 40},
    )
    week_rich = FilledPuzzle(
        size=15,
        grid=[],
        entries=[],
        metadata={},
        score_report={"family_count": 4, "family_score": 49_500, "weekly_count": 3, "family_source_count": 4, "entry_count": 70},
    )

    assert puzzle_selection_score(week_rich) > puzzle_selection_score(names_only)
