from __future__ import annotations

import json
import os
from typing import Any

from .model import FilledPuzzle


def add_clues(
    puzzle: FilledPuzzle,
    *,
    model: str | None = None,
    use_ai: bool = True,
    family_only: bool = False,
    preserve_existing: bool = False,
) -> list[str]:
    warnings: list[str] = []
    target_entries = [entry for entry in puzzle.entries if not family_only or entry.is_family]
    if use_ai and os.getenv("OPENAI_API_KEY") and model:
        try:
            clues = _generate_openai_clues(puzzle, model=model, family_only=family_only)
            for entry in target_entries:
                fallback = fallback_clue(entry.answer, entry.clue_hint, entry.is_family)
                existing = entry.clue.strip() if preserve_existing and not entry.is_family else ""
                entry.clue = clues.get(_entry_key(entry.number, entry.direction), existing or fallback)
            return warnings
        except Exception as exc:
            warnings.append(f"AI clue generation failed: {exc}")

    if use_ai and os.getenv("OPENAI_API_KEY") and not model:
        warnings.append("OPENAI_API_KEY is set but OPENAI_MODEL/--model is missing; using fallback clues.")

    for entry in target_entries:
        if entry.is_family and entry.clue_hint:
            entry.clue = fallback_clue(entry.answer, entry.clue_hint, entry.is_family)
            continue
        if preserve_existing and entry.clue.strip():
            continue
        entry.clue = fallback_clue(entry.answer, entry.clue_hint, entry.is_family)
    return warnings


def fallback_clue(answer: str, clue_hint: str = "", is_family: bool = False) -> str:
    if clue_hint:
        return clue_hint
    if is_family:
        return "Family-themed answer"
    return "Clue pending"


def _generate_openai_clues(puzzle: FilledPuzzle, *, model: str, family_only: bool = False) -> dict[str, str]:
    from openai import OpenAI

    payload = {
        "title": puzzle.metadata.get("title"),
        "week_of": puzzle.metadata.get("week_of"),
        "entries": [
            {
                "key": _entry_key(entry.number, entry.direction),
                "number": entry.number,
                "direction": entry.direction,
                "answer": entry.answer,
                "source": entry.source,
                "is_family": entry.is_family,
                "clue_hint": entry.clue_hint,
                "tags": list(entry.tags),
            }
            for entry in puzzle.entries
            if not family_only or entry.is_family
        ],
    }
    schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "clues": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "key": {"type": "string"},
                        "clue": {"type": "string"},
                    },
                    "required": ["key", "clue"],
                },
            }
        },
        "required": ["clues"],
    }
    client = OpenAI()
    response = client.responses.create(
        model=model,
        instructions=(
            "Write concise, fair, crossword-style clues. Do not reveal private context beyond the supplied hint. "
            "For family entries, use the hint if present. For generic fill, use ordinary dictionary-style clues."
        ),
        input=json.dumps(payload),
        text={
            "format": {
                "type": "json_schema",
                "name": "crossword_clues",
                "schema": schema,
                "strict": True,
            }
        },
    )
    raw_text = getattr(response, "output_text", None)
    if not raw_text:
        raw_text = response.output[0].content[0].text
    parsed = json.loads(raw_text)
    return {item["key"]: item["clue"] for item in parsed.get("clues", [])}


def _entry_key(number: int, direction: str) -> str:
    return f"{number}-{direction}"
