from family_crossword.generator import generate_puzzle
from family_crossword.model import Candidate


def test_generate_puzzle_can_use_small_size_fixture() -> None:
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

    puzzle, report = generate_puzzle(
        {"title": "Fixture", "week_of": "2026-05-24"},
        family_candidates=[candidates[0]],
        generic_candidates=candidates[1:],
        sizes=[5],
        attempts=1,
        timeout_minutes=1,
        seed=11,
        use_ai_clues=False,
    )

    assert puzzle.size == 5
    assert report["chosen_size"] == 5
    assert report["family_entries"] == ["ABCDE"]
