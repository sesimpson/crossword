from family_crossword.grid import assign_numbers, find_slots, is_rotationally_symmetric, is_valid_pattern


def test_all_white_grid_is_valid_checked_and_numbered() -> None:
    blocks = [[False for _ in range(5)] for _ in range(5)]

    assert is_rotationally_symmetric(blocks)
    assert is_valid_pattern(blocks)
    assert len(find_slots(blocks)) == 10
    assert assign_numbers(blocks)[(0, 0)] == 1


def test_two_letter_slot_is_invalid() -> None:
    blocks = [
        [False, False, True],
        [False, False, True],
        [True, True, True],
    ]

    assert not is_valid_pattern(blocks)
