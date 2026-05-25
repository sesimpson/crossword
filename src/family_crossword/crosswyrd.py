from __future__ import annotations

import random
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .assemble import puzzle_from_grid_rows
from .clues import add_clues
from .exporters import write_outputs
from .grid import BLOCK, generate_pattern, is_valid_pattern
from .input import load_context, normalize_candidates
from .model import Candidate, FilledPuzzle
from .solver import puzzle_selection_score

CROSSWYRD_URL = "https://crosswyrd.app/builder"


@dataclass
class CrosswyrdAttempt:
    size: int
    attempt: int
    placed_words: list[str]
    blanks: int
    rows: list[str]
    error: str = ""


def generate_with_crosswyrd_from_file(
    input_path: str | Path,
    out_dir: str | Path,
    *,
    sizes: list[int],
    attempts: int,
    timeout_minutes: float,
    seed: int | None = None,
    model: str | None = None,
    use_ai_clues: bool = True,
    headless: bool = True,
) -> FilledPuzzle:
    context = load_context(input_path)
    family_candidates, rejected = normalize_candidates(context, max_length=max(sizes))
    puzzle, report = generate_with_crosswyrd(
        context,
        family_candidates=family_candidates,
        rejected_candidates=rejected,
        sizes=sizes,
        attempts=attempts,
        timeout_minutes=timeout_minutes,
        seed=seed,
        model=model,
        use_ai_clues=use_ai_clues,
        headless=headless,
    )
    write_outputs(puzzle, out_dir, report=report)
    return puzzle


def generate_with_crosswyrd(
    context: dict[str, Any],
    *,
    family_candidates: list[Candidate],
    rejected_candidates: list[dict[str, str]] | None = None,
    sizes: list[int],
    attempts: int,
    timeout_minutes: float,
    seed: int | None = None,
    model: str | None = None,
    use_ai_clues: bool = True,
    headless: bool = True,
) -> tuple[FilledPuzzle, dict[str, Any]]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Install Playwright and its browser runtime to use --backend crosswyrd.") from exc

    rng = random.Random(seed)
    started = time.monotonic()
    deadline = started + timeout_minutes * 60
    metadata = {
        "title": context.get("title") or "Family Crossword",
        "week_of": str(context.get("week_of") or ""),
        "author": "family-crossword via Crosswyrd",
        "seed": seed,
        "backend": "crosswyrd",
        "source": CROSSWYRD_URL,
    }
    best: FilledPuzzle | None = None
    attempt_reports: list[dict[str, Any]] = []
    warnings: list[str] = []
    attempts_per_size = max(1, attempts // max(1, len(sizes)))

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        try:
            for size_index, size in enumerate(sizes):
                remaining_sizes = len(sizes) - size_index
                size_deadline = min(deadline, time.monotonic() + max(20.0, (deadline - time.monotonic()) / remaining_sizes))
                for attempt in range(attempts_per_size):
                    if time.monotonic() >= size_deadline:
                        warnings.append(f"Stopped Crosswyrd {size}x{size} at its time budget.")
                        break
                    max_placements = _placement_budget(attempt)
                    result = _run_crosswyrd_attempt(
                        browser,
                        size=size,
                        attempt=attempt,
                        candidates=_eligible_family_candidates(family_candidates, size, rng),
                        max_placements=max_placements,
                        rng=rng,
                        metadata=metadata,
                        deadline=size_deadline,
                    )
                    attempt_reports.append(
                        {
                            "size": result.size,
                            "attempt": result.attempt,
                            "placed_words": result.placed_words,
                            "max_placements": max_placements,
                            "blanks": result.blanks,
                            "error": result.error,
                        }
                    )
                    if result.error or result.blanks:
                        continue
                    puzzle = puzzle_from_grid_rows(result.rows, metadata=metadata, family_candidates=family_candidates)
                    puzzle.score_report.update(
                        {
                            "placed_word_bank_words": result.placed_words,
                            "selection_score": puzzle_selection_score(puzzle),
                            "size": size,
                        }
                    )
                    if best is None or puzzle_selection_score(puzzle) > puzzle_selection_score(best):
                        best = puzzle
                if best is not None:
                    break
                warnings.append(f"No complete Crosswyrd {size}x{size} puzzle found; shrinking.")
                if time.monotonic() >= deadline:
                    break
        finally:
            browser.close()

    if best is None:
        raise RuntimeError("Crosswyrd could not produce a complete puzzle within the configured attempts/time.")

    warnings.extend(add_clues(best, model=model, use_ai=use_ai_clues))
    report = {
        "status": "ok",
        "backend": "crosswyrd",
        "source": CROSSWYRD_URL,
        "attempts": len(attempt_reports),
        "sizes": sizes,
        "chosen_size": best.size,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "warnings": warnings,
        "rejected_candidates": rejected_candidates or [],
        "score_report": best.score_report,
        "family_entries": [entry.answer for entry in best.family_entries],
        "crosswyrd_attempts": attempt_reports,
    }
    return best, report


def _run_crosswyrd_attempt(
    browser: Any,
    *,
    size: int,
    attempt: int,
    candidates: list[Candidate],
    max_placements: int,
    rng: random.Random,
    metadata: dict[str, Any],
    deadline: float,
) -> CrosswyrdAttempt:
    page = browser.new_page(viewport={"width": 1600, "height": 1000}, accept_downloads=True)
    template_path = ""
    try:
        rows = _template_rows(size, rng, attempt, candidates)
        template_path = _write_blank_template_puz(rows, metadata)
        page.goto(CROSSWYRD_URL, wait_until="networkidle", timeout=60_000)
        _dismiss_welcome(page)
        _select_initial_grid(page)
        page.locator('input[accept=".puz"]').first.set_input_files(template_path)
        page.wait_for_timeout(3_000)
        _open_word_bank(page)
        _add_word_bank_words(page, candidates[:28])
        placed = _place_word_bank_words(page, candidates[:28], rng, deadline, max_placements=max_placements)
        _click_auto_fill(page)
        _wait_for_autofill(page, deadline)
        final_rows = _read_grid_rows(page)
        return CrosswyrdAttempt(size=size, attempt=attempt, placed_words=placed, blanks=sum(row.count(".") for row in final_rows), rows=final_rows)
    except Exception as exc:
        return CrosswyrdAttempt(size=size, attempt=attempt, placed_words=[], blanks=size * size, rows=[], error=str(exc))
    finally:
        page.close()
        if template_path:
            Path(template_path).unlink(missing_ok=True)


def _eligible_family_candidates(candidates: list[Candidate], size: int, rng: random.Random) -> list[Candidate]:
    eligible = [candidate for candidate in candidates if 3 <= len(candidate.answer) <= size]
    eligible.sort(key=lambda candidate: candidate.weight, reverse=True)
    priority = eligible[:18]
    rest = eligible[18:]
    rng.shuffle(rest)
    return priority + rest[:18]


def _template_rows(size: int, rng: random.Random, attempt: int, candidates: list[Candidate]) -> list[str]:
    if attempt % 7 == 6:
        return ["." * size for _ in range(size)]
    target_lengths = [len(candidate.answer) for candidate in candidates]
    for offset in range(40):
        blocks = generate_pattern(size, rng, attempt + offset, target_lengths=target_lengths)
        if is_valid_pattern(blocks):
            return ["".join(BLOCK if cell else "." for cell in row) for row in blocks]
    return ["." * size for _ in range(size)]


def _write_blank_template_puz(rows: list[str], metadata: dict[str, Any]) -> str:
    import puz

    size = len(rows)
    puzzle = puz.Puzzle()
    puzzle.title = str(metadata.get("title") or "Family Crossword")
    puzzle.author = str(metadata.get("author") or "family-crossword")
    puzzle.width = size
    puzzle.height = size
    puzzle.solution = "".join("." if cell == BLOCK else " " for row in rows for cell in row)
    puzzle.fill = puzzle.solution
    puzzle.clues = [""] * _count_slots(rows)
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=".puz")
    handle.close()
    puzzle.save(handle.name)
    return handle.name


def _count_slots(rows: list[str]) -> int:
    total = 0
    size = len(rows)
    for row in range(size):
        for col in range(size):
            if rows[row][col] == BLOCK:
                continue
            starts_across = (col == 0 or rows[row][col - 1] == BLOCK) and col + 2 < size and rows[row][col + 1] != BLOCK and rows[row][col + 2] != BLOCK
            starts_down = (row == 0 or rows[row - 1][col] == BLOCK) and row + 2 < size and rows[row + 1][col] != BLOCK and rows[row + 2][col] != BLOCK
            total += int(starts_across) + int(starts_down)
    return total


def _dismiss_welcome(page: Any) -> None:
    button = page.get_by_role("button", name="Let's go!")
    if button.count():
        button.click(timeout=5_000)
        page.wait_for_timeout(400)


def _select_initial_grid(page: Any) -> None:
    if page.get_by_text("Select a Grid", exact=True).count():
        page.get_by_role("button", name="Blank Grid").click(timeout=5_000)
        page.wait_for_timeout(400)


def _open_word_bank(page: Any) -> None:
    page.locator('button[role="tab"]').filter(has_text="Word Bank").click(timeout=5_000)
    page.wait_for_timeout(300)


def _add_word_bank_words(page: Any, candidates: list[Candidate]) -> None:
    input_box = page.locator('input[placeholder="Write a word"]')
    add_button = page.get_by_text("Add Word", exact=True)
    for candidate in candidates:
        input_box.fill(candidate.answer)
        add_button.click(timeout=5_000)
        page.wait_for_timeout(120)


def _placement_budget(attempt: int) -> int:
    budgets = (8, 5, 3, 2, 1, 0)
    return budgets[attempt % len(budgets)]


def _place_word_bank_words(
    page: Any,
    candidates: list[Candidate],
    rng: random.Random,
    deadline: float,
    *,
    max_placements: int,
) -> list[str]:
    placed: list[str] = []
    if max_placements <= 0:
        return placed
    for candidate in candidates:
        if time.monotonic() >= deadline:
            break
        if len(placed) >= max_placements:
            break
        item_box = _word_bank_item_box(page, candidate.answer)
        if not item_box:
            continue
        page.mouse.click(item_box["x"] + item_box["width"] / 2, item_box["y"] + item_box["height"] / 2)
        page.wait_for_timeout(250)
        options = page.locator(".tile--option")
        option_count = options.count()
        if option_count <= 0:
            page.keyboard.press("Escape")
            continue
        option_index = rng.randrange(option_count)
        box = options.nth(option_index).bounding_box()
        if not box:
            continue
        page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.wait_for_timeout(700)
        if candidate.answer in _read_grid_words(page):
            placed.append(candidate.answer)
    return placed


def _word_bank_item_box(page: Any, answer: str) -> dict[str, float] | None:
    return page.evaluate(
        """(answer) => {
          const items = Array.from(document.querySelectorAll('.word-bank-list-container .MuiListItem-root'));
          for (const item of items) {
            const label = item.querySelector('.MuiListItemText-root')?.textContent?.trim();
            const button = item.querySelector('.MuiListItemButton-root');
            if (label === answer && button && !button.className.includes('Mui-disabled')) {
              const rect = button.getBoundingClientRect();
              return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
            }
          }
          return null;
        }""",
        answer,
    )


def _click_auto_fill(page: Any) -> None:
    button = page.locator("button").filter(has_text="Auto-Fill")
    if button.count() == 1 and button.is_enabled():
        button.click(timeout=5_000)


def _wait_for_autofill(page: Any, deadline: float) -> None:
    previous = None
    stable_ticks = 0
    while time.monotonic() < deadline:
        rows = _read_grid_rows(page)
        blanks = sum(row.count(".") for row in rows)
        signature = "\n".join(rows)
        if blanks == 0:
            return
        if signature == previous:
            stable_ticks += 1
        else:
            stable_ticks = 0
            previous = signature
        if stable_ticks >= 12:
            return
        page.wait_for_timeout(1_000)


def _read_grid_rows(page: Any) -> list[str]:
    return page.evaluate(
        """() => Array.from(document.querySelectorAll('.puzzle-row')).map(row =>
          Array.from(row.querySelectorAll('.tile')).map(tile => {
            if (tile.className.includes('tile--black')) return '#';
            const clone = tile.cloneNode(true);
            clone.querySelectorAll('.tile-number').forEach(n => n.remove());
            const text = clone.textContent.trim().replace(/[^A-Z]/g, '');
            return text || '.';
          }).join('')
        )"""
    )


def _read_grid_words(page: Any) -> set[str]:
    rows = _read_grid_rows(page)
    words: set[str] = set()
    for row in rows:
        words.update(part for part in row.split(BLOCK) if len(part) >= 3 and "." not in part)
    for col in range(len(rows)):
        column = "".join(row[col] for row in rows)
        words.update(part for part in column.split(BLOCK) if len(part) >= 3 and "." not in part)
    return words
