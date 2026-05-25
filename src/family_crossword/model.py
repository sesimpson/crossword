from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Direction = Literal["across", "down"]


@dataclass(frozen=True)
class Candidate:
    answer: str
    clue_hint: str = ""
    priority: int = 5
    tags: tuple[str, ...] = ()
    source: str = "generic"
    is_family: bool = False

    @property
    def weight(self) -> int:
        if self.is_family:
            return 10_000 + self.priority * 250 + len(self.answer) * 20
        return max(1, self.priority) * 10 + len(self.answer)


@dataclass(frozen=True)
class Slot:
    id: int
    row: int
    col: int
    direction: Direction
    length: int

    @property
    def cells(self) -> tuple[tuple[int, int], ...]:
        if self.direction == "across":
            return tuple((self.row, self.col + offset) for offset in range(self.length))
        return tuple((self.row + offset, self.col) for offset in range(self.length))


@dataclass
class Entry:
    number: int
    row: int
    col: int
    direction: Direction
    answer: str
    clue: str
    source: str
    is_family: bool
    clue_hint: str = ""
    tags: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "row": self.row,
            "col": self.col,
            "direction": self.direction,
            "answer": self.answer,
            "clue": self.clue,
            "source": self.source,
            "is_family": self.is_family,
            "clue_hint": self.clue_hint,
            "tags": list(self.tags),
        }


@dataclass
class FilledPuzzle:
    size: int
    grid: list[list[str]]
    entries: list[Entry]
    metadata: dict[str, Any]
    score_report: dict[str, Any] = field(default_factory=dict)

    @property
    def family_entries(self) -> list[Entry]:
        return [entry for entry in self.entries if entry.is_family]

    def grid_rows(self) -> list[str]:
        return ["".join(row) for row in self.grid]
