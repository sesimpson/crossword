from __future__ import annotations

import random
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from .grid import BLOCK, assign_numbers, find_slots
from .model import Candidate, Entry, FilledPuzzle, Slot


@dataclass
class SolveResult:
    puzzle: FilledPuzzle | None
    attempts: int
    rejected_patterns: int
    warnings: list[str]


class TimeoutBudget:
    def __init__(self, seconds: float) -> None:
        self.deadline = time.monotonic() + seconds

    def expired(self) -> bool:
        return time.monotonic() >= self.deadline


def fill_pattern(
    blocks: list[list[bool]],
    candidates: Iterable[Candidate],
    rng: random.Random,
    *,
    metadata: dict,
    max_nodes: int = 2_500,
    prefer_family_slots: bool = True,
    forced_candidate: Candidate | None = None,
) -> FilledPuzzle | None:
    slots = find_slots(blocks)
    if not slots:
        return None

    by_length: dict[int, list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        by_length[len(candidate.answer)].append(candidate)
    indexes: dict[int, dict[tuple[int, str], set[int]]] = {}
    for values in by_length.values():
        rng.shuffle(values)
        values.sort(key=lambda item: item.weight, reverse=True)
        family_values = [candidate for candidate in values if candidate.is_family]
        generic_pool = [candidate for candidate in values if not candidate.is_family]
        if len(generic_pool) > 4_000:
            generic_pool = rng.sample(generic_pool, 4_000)
        rng.shuffle(generic_pool)
        generic_values = generic_pool[:4_000]
        values[:] = family_values + generic_values
    for length, values in by_length.items():
        index: dict[tuple[int, str], set[int]] = defaultdict(set)
        for candidate_index, candidate in enumerate(values):
            for position, letter in enumerate(candidate.answer):
                index[(position, letter)].add(candidate_index)
        indexes[length] = index

    grid: list[list[str]] = [[BLOCK if cell else "" for cell in row] for row in blocks]
    assignments: dict[int, Candidate] = {}
    used_answers: set[str] = set()
    nodes = 0

    def solve() -> bool:
        nonlocal nodes
        nodes += 1
        if nodes > max_nodes:
            return False
        if len(assignments) == len(slots):
            return True

        slot, options = _choose_slot(slots, assignments, by_length, indexes, grid, used_answers, prefer_family_slots=prefer_family_slots)
        if slot is None:
            return False
        for candidate in options:
            placed = _place_candidate(grid, slot, candidate)
            if placed is None:
                continue
            assignments[slot.id] = candidate
            used_answers.add(candidate.answer)
            if solve():
                return True
            used_answers.remove(candidate.answer)
            del assignments[slot.id]
            for row, col, previous in placed:
                grid[row][col] = previous
        return False

    solved = False
    if forced_candidate is not None:
        forced_slots = [slot for slot in slots if slot.length == len(forced_candidate.answer)]
        rng.shuffle(forced_slots)
        for forced_slot in forced_slots:
            placed = _place_candidate(grid, forced_slot, forced_candidate)
            if placed is None:
                continue
            assignments[forced_slot.id] = forced_candidate
            used_answers.add(forced_candidate.answer)
            if solve():
                solved = True
                break
            used_answers.remove(forced_candidate.answer)
            del assignments[forced_slot.id]
            for row, col, previous in placed:
                grid[row][col] = previous
    else:
        solved = solve()

    if not solved:
        return None

    numbers = assign_numbers(blocks)
    entries: list[Entry] = []
    for slot in slots:
        candidate = assignments[slot.id]
        number = numbers.get((slot.row, slot.col), 0)
        entries.append(
            Entry(
                number=number,
                row=slot.row,
                col=slot.col,
                direction=slot.direction,
                answer=candidate.answer,
                clue="",
                source=candidate.source,
                is_family=candidate.is_family,
                clue_hint=candidate.clue_hint,
                tags=candidate.tags,
            )
        )

    family_entries = [entry for entry in entries if entry.is_family]
    weekly_entries = [entry for entry in family_entries if entry.source != "people"]
    score_report = {
        "family_count": len(family_entries),
        "family_score": sum(assignments[slot.id].weight for slot in slots if assignments[slot.id].is_family),
        "weekly_count": len(weekly_entries),
        "family_source_count": len({entry.source for entry in family_entries}),
        "entry_count": len(entries),
        "block_count": sum(1 for row in blocks for cell in row if cell),
        "search_nodes": nodes,
    }
    return FilledPuzzle(size=len(blocks), grid=grid, entries=sorted(entries, key=lambda e: (e.number, e.direction)), metadata=metadata, score_report=score_report)


def puzzle_selection_score(puzzle: FilledPuzzle) -> float:
    family_score = float(puzzle.score_report.get("family_score", 0))
    family_count = float(puzzle.score_report.get("family_count", 0))
    weekly_count = float(puzzle.score_report.get("weekly_count", 0))
    family_source_count = float(puzzle.score_report.get("family_source_count", 0))
    density = family_count / max(1, float(puzzle.score_report.get("entry_count", 1)))
    return family_score + family_count * 5_000 + weekly_count * 1_000 + family_source_count * 250 + density * 1_000 + puzzle.size * 2


def _choose_slot(
    slots: list[Slot],
    assignments: dict[int, Candidate],
    by_length: dict[int, list[Candidate]],
    indexes: dict[int, dict[tuple[int, str], set[int]]],
    grid: list[list[str]],
    used_answers: set[str],
    *,
    prefer_family_slots: bool,
) -> tuple[Slot | None, list[Candidate]]:
    best_slot: Slot | None = None
    best_options: list[Candidate] | None = None
    best_key: tuple[int, int, int] | None = None
    for slot in slots:
        if slot.id in assignments:
            continue
        options = _matching_options(by_length.get(slot.length, []), indexes.get(slot.length, {}), grid, slot, used_answers)
        if not options:
            return None, []
        family_options = sum(1 for candidate in options if candidate.is_family)
        if prefer_family_slots:
            key = (0 if family_options else 1, len(options), -family_options)
        else:
            key = (len(options), 0 if family_options else 1, -family_options)
        if best_key is None or key < best_key:
            best_slot = slot
            best_options = options
            best_key = key
    return best_slot, best_options or []


def _matching_options(
    candidates: list[Candidate],
    index: dict[tuple[int, str], set[int]],
    grid: list[list[str]],
    slot: Slot,
    used_answers: set[str],
    *,
    generic_limit: int = 180,
) -> list[Candidate]:
    possible: set[int] | None = None
    for position, (row, col) in enumerate(slot.cells):
        letter = grid[row][col]
        if not letter:
            continue
        matches = index.get((position, letter), set())
        possible = set(matches) if possible is None else possible & matches
        if not possible:
            return []
    if possible is None:
        possible_iterable = range(len(candidates))
    else:
        possible_iterable = sorted(possible)

    family: list[Candidate] = []
    generic: list[Candidate] = []
    for candidate_index in possible_iterable:
        candidate = candidates[candidate_index]
        if candidate.answer in used_answers or not _fits(grid, slot, candidate.answer):
            continue
        if candidate.is_family:
            family.append(candidate)
        elif len(generic) < generic_limit:
            generic.append(candidate)
        if len(generic) >= generic_limit and family:
            break
    return family + generic


def _fits(grid: list[list[str]], slot: Slot, answer: str) -> bool:
    return all(grid[row][col] in ("", answer[index]) for index, (row, col) in enumerate(slot.cells))


def _place_candidate(grid: list[list[str]], slot: Slot, candidate: Candidate) -> list[tuple[int, int, str]] | None:
    if not _fits(grid, slot, candidate.answer):
        return None
    changed: list[tuple[int, int, str]] = []
    for index, (row, col) in enumerate(slot.cells):
        previous = grid[row][col]
        if previous == "":
            changed.append((row, col, previous))
            grid[row][col] = candidate.answer[index]
    return changed
