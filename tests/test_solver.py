import random

from family_crossword.model import Candidate
from family_crossword.solver import fill_pattern


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
