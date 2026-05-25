from family_crossword.input import clean_answer, normalize_candidates


def test_clean_answer_removes_non_letters() -> None:
    assert clean_answer("Lake House!") == "LAKEHOUSE"


def test_normalize_candidates_accepts_strings_and_objects() -> None:
    candidates, rejected = normalize_candidates(
        {
            "people": [{"answer": "Aunt June", "priority": 9, "tags": ["visit"]}],
            "places": ["Lake House"],
            "events": ["it"],
        },
        max_length=10,
    )

    assert [candidate.answer for candidate in candidates] == ["AUNTJUNE", "AUNT", "JUNE", "LAKEHOUSE", "LAKE", "HOUSE"]
    assert candidates[0].priority == 9
    assert candidates[0].tags == ("visit",)
    assert rejected[0]["reason"].startswith("answer shorter")
