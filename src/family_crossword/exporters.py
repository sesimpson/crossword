from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .grid import BLOCK
from .model import FilledPuzzle


def write_outputs(puzzle: FilledPuzzle, out_dir: str | Path, *, report: dict[str, Any]) -> None:
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    (target / "puzzle.json").write_text(json.dumps(_site_payload(puzzle), indent=2) + "\n", encoding="utf-8")
    (target / "puzzle.ipuz").write_text(json.dumps(_ipuz_payload(puzzle), indent=2) + "\n", encoding="utf-8")
    (target / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    _write_puz(puzzle, target / "puzzle.puz")


def _site_payload(puzzle: FilledPuzzle) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "metadata": puzzle.metadata,
        "size": puzzle.size,
        "grid": puzzle.grid_rows(),
        "entries": [entry.to_json() for entry in puzzle.entries],
        "score_report": puzzle.score_report,
    }


def _ipuz_payload(puzzle: FilledPuzzle) -> dict[str, Any]:
    across = [[entry.number, entry.clue] for entry in puzzle.entries if entry.direction == "across"]
    down = [[entry.number, entry.clue] for entry in puzzle.entries if entry.direction == "down"]
    puzzle_grid: list[list[int | str]] = []
    for row_index, row in enumerate(puzzle.grid):
        puzzle_row: list[int | str] = []
        for col_index, cell in enumerate(row):
            if cell == BLOCK:
                puzzle_row.append("#")
            else:
                number = next((entry.number for entry in puzzle.entries if entry.row == row_index and entry.col == col_index), 0)
                puzzle_row.append(number)
        puzzle_grid.append(puzzle_row)

    return {
        "version": "http://ipuz.org/v2",
        "kind": ["http://ipuz.org/crossword#1"],
        "title": puzzle.metadata.get("title", "Family Crossword"),
        "author": puzzle.metadata.get("author", "family-crossword"),
        "dimensions": {"width": puzzle.size, "height": puzzle.size},
        "puzzle": puzzle_grid,
        "solution": puzzle.grid,
        "clues": {"Across": across, "Down": down},
    }


def _write_puz(puzzle: FilledPuzzle, path: Path) -> None:
    import puz

    puz_file = puz.Puzzle()
    puz_file.title = str(puzzle.metadata.get("title", "Family Crossword"))
    puz_file.author = str(puzzle.metadata.get("author", "family-crossword"))
    puz_file.copyright = str(puzzle.metadata.get("copyright", ""))
    puz_file.width = puzzle.size
    puz_file.height = puzzle.size
    puz_file.solution = "".join(cell if cell != BLOCK else "." for row in puzzle.grid for cell in row)
    puz_file.fill = "".join("-" if cell != BLOCK else "." for row in puzzle.grid for cell in row)
    puz_file.clues = [entry.clue for entry in sorted(puzzle.entries, key=lambda item: (item.number, item.direction == "down"))]
    puz_file.notes = json.dumps({"week_of": puzzle.metadata.get("week_of"), "family_count": puzzle.score_report.get("family_count")})
    puz_file.save(str(path))
