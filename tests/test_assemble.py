from family_crossword.assemble import puzzle_from_grid_rows
from family_crossword.model import Candidate


def test_puzzle_from_grid_rows_marks_family_entries() -> None:
    puzzle = puzzle_from_grid_rows(
        ["DOG", "ARE", "TEN"],
        metadata={"title": "Assemble"},
        family_candidates=[Candidate("DOG", source="people", is_family=True)],
    )

    assert puzzle.size == 3
    assert "DOG" in [entry.answer for entry in puzzle.family_entries]
    assert puzzle.score_report["family_count"] == 1
