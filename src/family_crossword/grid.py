from __future__ import annotations

import random
from collections import deque

from .model import Slot

BLOCK = "#"

TEMPLATES: dict[int, tuple[str, ...]] = {
    # Crosserville weekday template 13: balanced 10-13 letter theme slots.
    15: (
        ".....#.....#...",
        ".....#.....#...",
        "...........#...",
        "....#.....#....",
        "###...##.......",
        ".............##",
        "...#....##.....",
        "....#.....#....",
        ".....##....#...",
        "##.............",
        ".......##...###",
        "....#.....#....",
        "...#...........",
        "...#.....#.....",
        "...#.....#.....",
    ),
    9: (
        "###...###",
        "###...###",
        "##.....##",
        "...#.....",
        "....#....",
        ".....#...",
        "##.....##",
        "###...###",
        "###...###",
    ),
}

SECONDARY_TEMPLATES: dict[int, tuple[str, ...]] = {
    9: (
        "...##...#",
        "...#.....",
        ".........",
        "##...#...",
        "#...#...#",
        "...#...##",
        ".........",
        ".....#...",
        "#...##...",
    ),
}


def generate_pattern(
    size: int,
    rng: random.Random,
    attempt: int,
    *,
    target_lengths: list[int] | None = None,
) -> list[list[bool]]:
    if size in TEMPLATES and attempt % 5 == 0:
        return [[cell == BLOCK for cell in row] for row in TEMPLATES[size]]
    if size in SECONDARY_TEMPLATES and attempt % 11 == 0:
        return [[cell == BLOCK for cell in row] for row in SECONDARY_TEMPLATES[size]]
    if size <= 5 and attempt % 25 == 0:
        return [[False for _ in range(size)] for _ in range(size)]

    block_fraction = rng.uniform(0.22, 0.34)
    max_blocks = int(size * size * block_fraction)
    blocks = [[False for _ in range(size)] for _ in range(size)]
    protected, forced_blocks = _seed_family_slot(size, rng, target_lengths or [])
    for row, col in forced_blocks:
        mirror = (size - 1 - row, size - 1 - col)
        if (row, col) not in protected and mirror not in protected:
            blocks[row][col] = True
            blocks[mirror[0]][mirror[1]] = True
    coordinates = [(row, col) for row in range(size) for col in range(size)]
    rng.shuffle(coordinates)

    for row, col in coordinates:
        mirror = (size - 1 - row, size - 1 - col)
        if (row, col) in protected or mirror in protected:
            continue
        if count_blocks(blocks) >= max_blocks:
            break
        blocks[row][col] = True
        blocks[mirror[0]][mirror[1]] = True
        if not is_valid_pattern(blocks):
            blocks[row][col] = False
            blocks[mirror[0]][mirror[1]] = False

    return blocks


def _seed_family_slot(
    size: int,
    rng: random.Random,
    target_lengths: list[int],
) -> tuple[set[tuple[int, int]], set[tuple[int, int]]]:
    lengths = [length for length in target_lengths if 3 <= length <= size]
    rng.shuffle(lengths)
    for length in lengths[:8]:
        direction = rng.choice(("across", "down"))
        row = rng.randrange(size)
        col = rng.randrange(0, size - length + 1)
        if direction == "down":
            row, col = col, row
        cells = {
            (row, col + offset) if direction == "across" else (row + offset, col)
            for offset in range(length)
        }
        forced: set[tuple[int, int]] = set()
        before = (row, col - 1) if direction == "across" else (row - 1, col)
        after = (row, col + length) if direction == "across" else (row + length, col)
        for endpoint in (before, after):
            if 0 <= endpoint[0] < size and 0 <= endpoint[1] < size:
                forced.add(endpoint)
        mirror_cells = {(size - 1 - r, size - 1 - c) for r, c in cells}
        mirror_forced = {(size - 1 - r, size - 1 - c) for r, c in forced}
        if (cells | mirror_cells) & (forced | mirror_forced):
            continue
        return cells | mirror_cells, forced | mirror_forced
    return set(), set()


def count_blocks(blocks: list[list[bool]]) -> int:
    return sum(1 for row in blocks for cell in row if cell)


def is_rotationally_symmetric(blocks: list[list[bool]]) -> bool:
    size = len(blocks)
    return all(blocks[row][col] == blocks[size - 1 - row][size - 1 - col] for row in range(size) for col in range(size))


def is_valid_pattern(blocks: list[list[bool]]) -> bool:
    return (
        bool(blocks)
        and is_rotationally_symmetric(blocks)
        and _has_white_cells(blocks)
        and _all_slots_at_least_three(blocks)
        and _all_white_cells_checked(blocks)
        and _white_cells_connected(blocks)
    )


def find_slots(blocks: list[list[bool]]) -> list[Slot]:
    slots: list[Slot] = []
    slot_id = 0
    size = len(blocks)
    for row in range(size):
        col = 0
        while col < size:
            if blocks[row][col]:
                col += 1
                continue
            start = col
            while col < size and not blocks[row][col]:
                col += 1
            length = col - start
            if length >= 3:
                slots.append(Slot(slot_id, row, start, "across", length))
                slot_id += 1
    for col in range(size):
        row = 0
        while row < size:
            if blocks[row][col]:
                row += 1
                continue
            start = row
            while row < size and not blocks[row][col]:
                row += 1
            length = row - start
            if length >= 3:
                slots.append(Slot(slot_id, start, col, "down", length))
                slot_id += 1
    return slots


def assign_numbers(blocks: list[list[bool]]) -> dict[tuple[int, int], int]:
    numbers: dict[tuple[int, int], int] = {}
    number = 1
    size = len(blocks)
    for row in range(size):
        for col in range(size):
            if blocks[row][col]:
                continue
            starts_across = (col == 0 or blocks[row][col - 1]) and col + 2 < size and not blocks[row][col + 1] and not blocks[row][col + 2]
            starts_down = (row == 0 or blocks[row - 1][col]) and row + 2 < size and not blocks[row + 1][col] and not blocks[row + 2][col]
            if starts_across or starts_down:
                numbers[(row, col)] = number
                number += 1
    return numbers


def _has_white_cells(blocks: list[list[bool]]) -> bool:
    return any(not cell for row in blocks for cell in row)


def _all_slots_at_least_three(blocks: list[list[bool]]) -> bool:
    size = len(blocks)
    for row in range(size):
        run = 0
        for col in range(size + 1):
            if col < size and not blocks[row][col]:
                run += 1
            else:
                if 0 < run < 3:
                    return False
                run = 0
    for col in range(size):
        run = 0
        for row in range(size + 1):
            if row < size and not blocks[row][col]:
                run += 1
            else:
                if 0 < run < 3:
                    return False
                run = 0
    return True


def _all_white_cells_checked(blocks: list[list[bool]]) -> bool:
    size = len(blocks)
    for row in range(size):
        for col in range(size):
            if blocks[row][col]:
                continue
            horizontal = _run_length(blocks, row, col, 0, -1) + 1 + _run_length(blocks, row, col, 0, 1)
            vertical = _run_length(blocks, row, col, -1, 0) + 1 + _run_length(blocks, row, col, 1, 0)
            if horizontal < 3 or vertical < 3:
                return False
    return True


def _run_length(blocks: list[list[bool]], row: int, col: int, dr: int, dc: int) -> int:
    size = len(blocks)
    total = 0
    row += dr
    col += dc
    while 0 <= row < size and 0 <= col < size and not blocks[row][col]:
        total += 1
        row += dr
        col += dc
    return total


def _white_cells_connected(blocks: list[list[bool]]) -> bool:
    size = len(blocks)
    start = None
    white_count = 0
    for row in range(size):
        for col in range(size):
            if not blocks[row][col]:
                white_count += 1
                start = start or (row, col)
    if start is None:
        return False

    queue = deque([start])
    seen = {start}
    while queue:
        row, col = queue.popleft()
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = row + dr, col + dc
            if 0 <= nr < size and 0 <= nc < size and not blocks[nr][nc] and (nr, nc) not in seen:
                seen.add((nr, nc))
                queue.append((nr, nc))
    return len(seen) == white_count
