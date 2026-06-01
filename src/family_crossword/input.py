from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from .model import Candidate

ANSWER_RE = re.compile(r"[^A-Za-z]+")
DEFAULT_CATEGORIES = (
    "people",
    "places",
    "events",
    "weekly_terms",
    "activities",
    "family_lore",
    "inside_jokes",
    "books",
    "news_items",
)
DERIVED_STOPWORDS = {
    "AND",
    "ARE",
    "BOOK",
    "FOR",
    "FROM",
    "HAS",
    "HER",
    "HIS",
    "INTO",
    "ITS",
    "LET",
    "ME",
    "MOM",
    "MORE",
    "MY",
    "NOT",
    "NEW",
    "OF",
    "ON",
    "OR",
    "PLEASE",
    "THE",
    "THIS",
    "TO",
    "TWO",
    "VERY",
    "WITH",
    "YOU",
    "YOUR",
    "GET",
    "DAD",
}


def clean_answer(value: str) -> str:
    return ANSWER_RE.sub("", value).upper()


def load_context(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    raw = source.read_text(encoding="utf-8")
    if source.suffix.lower() == ".json":
        data = json.loads(raw)
    else:
        data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ValueError("Weekly context must be a JSON/YAML object.")
    return data


def normalize_candidates(
    data: dict[str, Any],
    *,
    max_length: int,
    min_length: int = 3,
) -> tuple[list[Candidate], list[dict[str, str]]]:
    candidates: list[Candidate] = []
    rejected: list[dict[str, str]] = []
    seen: set[str] = set()

    for category in DEFAULT_CATEGORIES:
        items = data.get(category, [])
        if items is None:
            continue
        if not isinstance(items, list):
            rejected.append({"source": category, "answer": str(items), "reason": "category is not a list"})
            continue

        for item in items:
            candidate, reason = _candidate_from_item(item, category, min_length, max_length)
            if candidate is None:
                rejected.append({"source": category, "answer": _raw_answer(item), "reason": reason})
                long_parent, _ = _candidate_from_item(item, category, min_length, 10_000)
                if long_parent is not None:
                    for derived in _derived_candidates(item, category, long_parent, min_length, max_length):
                        if derived.answer in seen:
                            continue
                        seen.add(derived.answer)
                        candidates.append(derived)
                continue
            if candidate.answer in seen:
                rejected.append({"source": category, "answer": candidate.answer, "reason": "duplicate"})
                continue
            seen.add(candidate.answer)
            candidates.append(candidate)
            for derived in _derived_candidates(item, category, candidate, min_length, max_length):
                if derived.answer in seen:
                    continue
                seen.add(derived.answer)
                candidates.append(derived)

    return candidates, rejected


def _candidate_from_item(
    item: Any,
    category: str,
    min_length: int,
    max_length: int,
) -> tuple[Candidate | None, str]:
    if isinstance(item, str):
        raw_answer = item
        clue_hint = ""
        priority = 5
        tags: tuple[str, ...] = ()
    elif isinstance(item, dict):
        raw_answer = str(item.get("answer") or item.get("name") or item.get("title") or "")
        clue_hint = str(item.get("clue_hint") or item.get("hint") or "")
        priority = _coerce_priority(item.get("priority", 5))
        raw_tags = item.get("tags") or []
        tags = tuple(str(tag) for tag in raw_tags) if isinstance(raw_tags, list) else (str(raw_tags),)
    else:
        return None, "item is not a string or object"

    answer = clean_answer(raw_answer)
    if len(answer) < min_length:
        return None, f"answer shorter than {min_length} letters after cleaning"
    if len(answer) > max_length:
        return None, f"answer longer than max grid size {max_length}"

    return (
        Candidate(
            answer=answer,
            clue_hint=clue_hint,
            priority=priority,
            tags=tags,
            source=category,
            is_family=True,
        ),
        "",
    )


def _coerce_priority(value: Any) -> int:
    try:
        return max(1, min(10, int(value)))
    except (TypeError, ValueError):
        return 5


def _raw_answer(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("answer") or item.get("name") or item.get("title") or item)
    return str(item)


def _derived_candidates(
    item: Any,
    category: str,
    parent: Candidate,
    min_length: int,
    max_length: int,
) -> list[Candidate]:
    raw = _raw_answer(item)
    tokens = [clean_answer(token) for token in re.findall(r"[A-Za-z]+", raw)]
    derived: list[Candidate] = []
    for token in tokens:
        if token == parent.answer or token in DERIVED_STOPWORDS or not (min_length <= len(token) <= max_length):
            continue
        derived.append(
            Candidate(
                answer=token,
                clue_hint=parent.clue_hint or f"Part of {raw}",
                priority=max(1, parent.priority - 1),
                tags=parent.tags + ("derived",),
                source=category,
                is_family=True,
            )
        )
    return derived
