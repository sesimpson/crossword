from __future__ import annotations

import random
import sys
import time
from pathlib import Path
from typing import Any

from .clues import add_clues
from .exporters import write_outputs
from .grid import generate_pattern, is_valid_pattern
from .input import load_context, normalize_candidates
from .model import Candidate, FilledPuzzle
from .solver import fill_pattern, puzzle_selection_score
from .wordlists import load_generic_candidates


def generate_from_file(
    input_path: str | Path,
    out_dir: str | Path,
    *,
    sizes: list[int],
    attempts: int,
    timeout_minutes: float,
    seed: int | None = None,
    model: str | None = None,
    use_ai_clues: bool = True,
    generic_candidates: list[Candidate] | None = None,
) -> FilledPuzzle:
    context = load_context(input_path)
    max_size = max(sizes)
    family_candidates, rejected = normalize_candidates(context, max_length=max_size)
    generic = generic_candidates if generic_candidates is not None else load_generic_candidates(max_size)
    puzzle, report = generate_puzzle(
        context,
        family_candidates=family_candidates,
        generic_candidates=generic,
        rejected_candidates=rejected,
        sizes=sizes,
        attempts=attempts,
        timeout_minutes=timeout_minutes,
        seed=seed,
        model=model,
        use_ai_clues=use_ai_clues,
    )
    write_outputs(puzzle, out_dir, report=report)
    return puzzle


def generate_puzzle(
    context: dict[str, Any],
    *,
    family_candidates: list[Candidate],
    generic_candidates: list[Candidate],
    rejected_candidates: list[dict[str, str]] | None = None,
    sizes: list[int],
    attempts: int,
    timeout_minutes: float,
    seed: int | None = None,
    model: str | None = None,
    use_ai_clues: bool = True,
) -> tuple[FilledPuzzle, dict[str, Any]]:
    if not sizes:
        raise ValueError("At least one grid size is required.")
    if attempts < 1:
        raise ValueError("attempts must be at least 1.")

    rng = random.Random(seed)
    started = time.monotonic()
    deadline = started + timeout_minutes * 60
    best: FilledPuzzle | None = None
    total_attempts = 0
    rejected_patterns = 0
    warnings: list[str] = []

    metadata = {
        "title": context.get("title") or "Family Crossword",
        "week_of": str(context.get("week_of") or ""),
        "author": "family-crossword",
        "seed": seed,
    }

    all_candidates = _merge_candidates(family_candidates, generic_candidates)
    attempts_per_size = max(1, attempts // len(sizes))

    for size_index, size in enumerate(sizes):
        size_candidates = [candidate for candidate in all_candidates if len(candidate.answer) <= size]
        remaining_sizes = len(sizes) - size_index
        size_deadline = min(deadline, time.monotonic() + max(5.0, (deadline - time.monotonic()) / remaining_sizes))
        size_best_at_start = best
        print(
            f"Searching {size}x{size}: up to {attempts_per_size} attempts, "
            f"{max(0.0, size_deadline - time.monotonic()):.1f}s budget",
            file=sys.stderr,
            flush=True,
        )
        for attempt in range(attempts_per_size):
            if time.monotonic() >= size_deadline:
                warnings.append(f"Stopped {size}x{size} at its time budget.")
                break
            total_attempts += 1
            target_lengths = [len(candidate.answer) for candidate in family_candidates if len(candidate.answer) <= size]
            blocks = generate_pattern(size, rng, attempt, target_lengths=target_lengths)
            if not is_valid_pattern(blocks):
                rejected_patterns += 1
                continue
            puzzle = None
            if size <= 9:
                for forced in _family_force_order(family_candidates, size, rng):
                    if time.monotonic() >= size_deadline:
                        break
                    puzzle = fill_pattern(
                        blocks,
                        size_candidates,
                        rng,
                        metadata=metadata,
                        max_nodes=700,
                        prefer_family_slots=False,
                        forced_candidate=forced,
                    )
                    if puzzle is not None:
                        break
            if puzzle is None:
                puzzle = fill_pattern(
                    blocks,
                    size_candidates,
                    rng,
                    metadata=metadata,
                    max_nodes=_node_cap_for_size(size, family_pass=True),
                    prefer_family_slots=True,
                )
            if puzzle is None:
                puzzle = fill_pattern(
                    blocks,
                    size_candidates,
                    rng,
                    metadata=metadata,
                    max_nodes=_node_cap_for_size(size, family_pass=False),
                    prefer_family_slots=False,
                )
            if puzzle is None:
                continue
            puzzle.score_report.update({"size": size, "selection_score": puzzle_selection_score(puzzle)})
            if best is None or puzzle_selection_score(puzzle) > puzzle_selection_score(best):
                best = puzzle
        if best is size_best_at_start:
            print(f"No complete {size}x{size} puzzle found; shrinking.", file=sys.stderr, flush=True)
        else:
            print(
                f"Best after {size}x{size}: {best.size}x{best.size}, "
                f"{best.score_report.get('family_count', 0)} family entries",
                file=sys.stderr,
                flush=True,
            )
        if time.monotonic() >= deadline:
            warnings.append("Generation stopped at global timeout; using best complete puzzle found.")
            break

    if best is None:
        raise RuntimeError("Could not generate a complete crossword. Add more weekly/fill candidates or increase attempts.")

    clue_warnings = add_clues(best, model=model, use_ai=use_ai_clues)
    warnings.extend(clue_warnings)

    report = {
        "status": "ok",
        "attempts": total_attempts,
        "attempts_per_size": attempts_per_size,
        "sizes": sizes,
        "chosen_size": best.size,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "warnings": warnings,
        "rejected_patterns": rejected_patterns,
        "rejected_candidates": rejected_candidates or [],
        "score_report": best.score_report,
        "family_entries": [entry.answer for entry in best.family_entries],
    }
    return best, report


def _merge_candidates(family_candidates: list[Candidate], generic_candidates: list[Candidate]) -> list[Candidate]:
    merged: list[Candidate] = []
    seen: set[str] = set()
    for candidate in sorted(family_candidates, key=lambda item: item.weight, reverse=True) + generic_candidates:
        if candidate.answer in seen:
            continue
        seen.add(candidate.answer)
        merged.append(candidate)
    return merged


def _family_force_order(family_candidates: list[Candidate], size: int, rng: random.Random) -> list[Candidate]:
    eligible = [candidate for candidate in family_candidates if 3 <= len(candidate.answer) <= size]
    eligible.sort(key=lambda item: item.weight, reverse=True)
    priority = eligible[:12]
    rest = eligible[12:]
    rng.shuffle(rest)
    return priority + rest[:8]


def _node_cap_for_size(size: int, *, family_pass: bool) -> int:
    if size >= 13:
        return 140 if family_pass else 80
    if size >= 11:
        return 260 if family_pass else 140
    return 1_200 if family_pass else 400
