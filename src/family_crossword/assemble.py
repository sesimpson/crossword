from __future__ import annotations

from typing import Any

from .grid import BLOCK, assign_numbers, find_slots
from .model import Candidate, Entry, FilledPuzzle


def puzzle_from_grid_rows(
    rows: list[str],
    *,
    metadata: dict[str, Any],
    family_candidates: list[Candidate],
    clues: dict[tuple[int, str], str] | None = None,
) -> FilledPuzzle:
    blocks = [[cell == BLOCK for cell in row] for row in rows]
    numbers = assign_numbers(blocks)
    family_by_answer = {candidate.answer: candidate for candidate in family_candidates}
    entries: list[Entry] = []
    grid = [list(row) for row in rows]

    for slot in find_slots(blocks):
        answer = "".join(rows[row][col] for row, col in slot.cells)
        candidate = family_by_answer.get(answer)
        entries.append(
            Entry(
                number=numbers.get((slot.row, slot.col), 0),
                row=slot.row,
                col=slot.col,
                direction=slot.direction,
                answer=answer,
                clue=(clues or {}).get((numbers.get((slot.row, slot.col), 0), slot.direction), ""),
                source=candidate.source if candidate else "crosserville",
                is_family=candidate is not None,
                clue_hint=candidate.clue_hint if candidate else "",
                tags=candidate.tags if candidate else (),
            )
        )

    family_entries = [entry for entry in entries if entry.is_family]
    score_report = {
        "family_count": len(family_entries),
        "family_score": sum(family_by_answer[entry.answer].weight for entry in family_entries),
        "entry_count": len(entries),
        "block_count": sum(1 for row in rows for cell in row if cell == BLOCK),
    }
    return FilledPuzzle(
        size=len(rows),
        grid=grid,
        entries=sorted(entries, key=lambda entry: (entry.number, entry.direction)),
        metadata=metadata,
        score_report=score_report,
    )
