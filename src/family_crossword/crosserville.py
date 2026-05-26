from __future__ import annotations

import os
import random
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .assemble import puzzle_from_grid_rows
from .clues import add_clues
from .exporters import write_outputs
from .grid import BLOCK, find_slots, generate_pattern, is_valid_pattern
from .input import load_context, normalize_candidates
from .model import Candidate, FilledPuzzle
from .solver import puzzle_selection_score

CROSSERVILLE_HOME_URL = "https://www.crosserville.com/"
CROSSERVILLE_SIGN_IN_URL = "https://www.crosserville.com/user/signIn"
CROSSERVILLE_BUILDER_URL = "https://www.crosserville.com/builder"
MAX_FILL_SECONDS_PER_PLACEMENT = 15.0


@dataclass
class CrosservilleAttempt:
    size: int
    attempt: int
    placed_words: list[str]
    blanks: int
    rows: list[str]
    clues: dict[tuple[int, str], str] | None = None
    error: str = ""


def generate_with_crosserville_from_file(
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
    puzzle, report = generate_with_crosserville(
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


def generate_with_crosserville(
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
        raise RuntimeError("Install Playwright and its browser runtime to use --backend crosserville.") from exc

    rng = random.Random(seed)
    started = time.monotonic()
    deadline = started + timeout_minutes * 60
    metadata = {
        "title": context.get("title") or "Family Crossword",
        "week_of": str(context.get("week_of") or ""),
        "author": "family-crossword via Crosserville",
        "seed": seed,
        "backend": "crosserville",
        "source": CROSSERVILLE_BUILDER_URL,
    }
    best: FilledPuzzle | None = None
    attempt_reports: list[dict[str, Any]] = []
    warnings: list[str] = []
    attempts_per_size = max(1, attempts // max(1, len(sizes)))

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        browser_context = browser.new_context(accept_downloads=True, viewport={"width": 1600, "height": 1000})
        try:
            _ensure_crosserville_session(browser_context)
            for size_index, size in enumerate(sizes):
                remaining_sizes = len(sizes) - size_index
                size_deadline = min(deadline, time.monotonic() + max(20.0, (deadline - time.monotonic()) / remaining_sizes))
                best_before_size = best
                for attempt in range(attempts_per_size):
                    if time.monotonic() >= size_deadline:
                        warnings.append(f"Stopped Crosserville {size}x{size} at its time budget.")
                        break
                    result = _run_crosserville_attempt(
                        browser_context,
                        size=size,
                        attempt=attempt,
                        candidates=_eligible_family_candidates(family_candidates, size, rng),
                        rng=rng,
                        metadata=metadata,
                        deadline=size_deadline,
                    )
                    attempt_reports.append(
                        {
                            "size": result.size,
                            "attempt": result.attempt,
                            "placed_words": result.placed_words,
                            "blanks": result.blanks,
                            "error": result.error,
                        }
                    )
                    if result.error or result.blanks:
                        continue
                    puzzle = puzzle_from_grid_rows(result.rows, metadata=metadata, family_candidates=family_candidates, clues=result.clues)
                    puzzle.score_report.update(
                        {
                            "selection_score": puzzle_selection_score(puzzle),
                            "size": size,
                            "preplaced_family_words": result.placed_words,
                        }
                    )
                    if best is None or puzzle_selection_score(puzzle) > puzzle_selection_score(best):
                        best = puzzle
                if best is not best_before_size:
                    break
                warnings.append(f"No complete Crosserville {size}x{size} puzzle found; shrinking.")
                if time.monotonic() >= deadline:
                    break
        finally:
            browser_context.close()
            browser.close()

    if best is None:
        raise RuntimeError("Crosserville could not produce a complete puzzle within the configured attempts/time.")

    warnings.extend(add_clues(best, model=model, use_ai=use_ai_clues, family_only=False, preserve_existing=True))
    report = {
        "status": "ok",
        "backend": "crosserville",
        "source": CROSSERVILLE_BUILDER_URL,
        "attempts": len(attempt_reports),
        "sizes": sizes,
        "chosen_size": best.size,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "warnings": warnings,
        "rejected_candidates": rejected_candidates or [],
        "score_report": best.score_report,
        "family_entries": [entry.answer for entry in best.family_entries],
        "crosserville_attempts": attempt_reports,
    }
    return best, report


def _run_crosserville_attempt(
    browser_context: Any,
    *,
    size: int,
    attempt: int,
    candidates: list[Candidate],
    rng: random.Random,
    metadata: dict[str, Any],
    deadline: float,
) -> CrosservilleAttempt:
    page = browser_context.new_page()
    template_path = ""
    placed_words: list[str] = []
    try:
        rows = _template_rows(size, rng, attempt, candidates)
        seeded_rows, placed_words = _place_family_words(rows, candidates, rng, attempt)
        template_path = _write_template_puz(seeded_rows, metadata)
        page.goto(CROSSERVILLE_BUILDER_URL, wait_until="load", timeout=60_000)
        _import_template(page, template_path)
        _run_crosserville_fill(page, min(deadline, time.monotonic() + MAX_FILL_SECONDS_PER_PLACEMENT))
        final_rows, clues = _export_puz(page)
        clues.update({key: value for key, value in _scrape_visible_clues(page, final_rows).items() if value})
        return CrosservilleAttempt(size=size, attempt=attempt, placed_words=placed_words, blanks=sum(row.count(".") for row in final_rows), rows=final_rows, clues=clues)
    except Exception as exc:
        return CrosservilleAttempt(size=size, attempt=attempt, placed_words=placed_words, blanks=size * size, rows=[], error=str(exc))
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


def _place_family_words(rows: list[str], candidates: list[Candidate], rng: random.Random, attempt: int) -> tuple[list[str], list[str]]:
    blocks = [[cell == BLOCK for cell in row] for row in rows]
    slots = find_slots(blocks)
    candidates_by_length: dict[int, list[Candidate]] = {}
    for candidate in candidates:
        candidates_by_length.setdefault(len(candidate.answer), []).append(candidate)
    for values in candidates_by_length.values():
        values.sort(key=lambda item: item.weight, reverse=True)

    grid = [list(row) for row in rows]
    slot_order = slots[:]
    rng.shuffle(slot_order)
    max_placements = _family_placement_budget(attempt, candidates)
    placed: list[str] = []
    used_answers: set[str] = set()

    for slot in slot_order:
        if len(placed) >= max_placements:
            break
        options = [
            candidate
            for candidate in candidates_by_length.get(slot.length, [])
            if candidate.answer not in used_answers and _word_fits_seeded_grid(grid, slot.cells, candidate.answer)
        ]
        if not options:
            continue
        priority_options = options[: min(4, len(options))]
        candidate = rng.choice(priority_options)
        for index, (row, col) in enumerate(slot.cells):
            grid[row][col] = candidate.answer[index]
        placed.append(candidate.answer)
        used_answers.add(candidate.answer)

    return ["".join(row) for row in grid], placed


def _family_placement_budget(attempt: int, candidates: list[Candidate]) -> int:
    if not candidates:
        return 0
    budgets = (8, 6, 5, 4, 3, 2, 1)
    return min(len(candidates), budgets[attempt % len(budgets)])


def _word_fits_seeded_grid(grid: list[list[str]], cells: tuple[tuple[int, int], ...], answer: str) -> bool:
    for index, (row, col) in enumerate(cells):
        cell = grid[row][col]
        if cell not in (".", answer[index]):
            return False
    return True


def _write_template_puz(rows: list[str], metadata: dict[str, Any]) -> str:
    import puz

    size = len(rows)
    puzzle = puz.Puzzle()
    puzzle.title = str(metadata.get("title") or "Family Crossword")
    puzzle.author = str(metadata.get("author") or "family-crossword")
    puzzle.width = size
    puzzle.height = size
    puzzle.solution = "".join(_grid_cell_to_puz_cell(cell) for row in rows for cell in row)
    puzzle.fill = puzzle.solution
    puzzle.clues = [""] * _count_slots(rows)
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=".puz")
    handle.close()
    puzzle.save(handle.name)
    return handle.name


def _grid_cell_to_puz_cell(cell: str) -> str:
    if cell == BLOCK:
        return "."
    if cell == ".":
        return " "
    return cell


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


def _ensure_crosserville_session(browser_context: Any) -> None:
    page = browser_context.new_page()
    try:
        page.goto(CROSSERVILLE_HOME_URL, wait_until="load", timeout=60_000)
        if page.locator('a[href="/builder"]').count():
            return

        email = os.getenv("CROSSERVILLE_EMAIL")
        password = os.getenv("CROSSERVILLE_PASSWORD")
        if not email or not password:
            raise RuntimeError("Set CROSSERVILLE_EMAIL and CROSSERVILLE_PASSWORD to use --backend crosserville.")

        page.goto(CROSSERVILLE_SIGN_IN_URL, wait_until="load", timeout=60_000)
        page.locator("#id_signInWithEmailBtn").click(force=True, timeout=10_000)
        page.locator("#id_signInEmail").fill(email, timeout=10_000)
        page.locator("#id_signInPassword").fill(password, timeout=10_000)
        page.locator("button#id_signInEmailBtn").click(timeout=10_000)
        page.wait_for_url(CROSSERVILLE_HOME_URL, timeout=20_000)
        if not page.locator('a[href="/builder"]').count():
            raise RuntimeError("Crosserville sign-in succeeded, but Grid Builder was not available.")
    finally:
        page.close()


def _import_template(page: Any, template_path: str) -> None:
    with page.expect_file_chooser(timeout=10_000) as chooser:
        page.locator("#id_importAcrossListPuz").evaluate("el => el.click()")
    chooser.value.set_files(template_path)
    page.locator("#id_gridControls").wait_for(state="visible", timeout=20_000)
    page.locator("#id_exportAcrossLitePuz").wait_for(state="attached", timeout=10_000)


def _run_crosserville_fill(page: Any, deadline: float) -> None:
    page.locator(".tab", has_text="Fill").click(timeout=10_000)
    find_fill = page.locator("#id_findFillBtn")
    find_fill.wait_for(state="visible", timeout=10_000)
    while time.monotonic() < deadline and not find_fill.is_enabled():
        page.wait_for_timeout(1_000)
    if not find_fill.is_enabled():
        raise RuntimeError("Crosserville Find Fill button is disabled.")
    find_fill.click(timeout=10_000)

    accept_fill = page.locator("#id_acceptFillBtn")
    while time.monotonic() < deadline:
        if accept_fill.is_visible() and accept_fill.is_enabled():
            accept_fill.click(timeout=10_000)
            return
        page.wait_for_timeout(1_000)
    _stop_crosserville_fill(page)
    raise TimeoutError("Timed out waiting for Crosserville fill results.")


def _stop_crosserville_fill(page: Any) -> None:
    stop_fill = page.locator("#id_stopFillBtn")
    try:
        if stop_fill.is_visible() and stop_fill.is_enabled():
            stop_fill.click(timeout=5_000)
    except Exception:
        return


def _export_puz(page: Any) -> tuple[list[str], dict[tuple[int, str], str]]:
    import puz

    if "disabled" in (page.locator("#id_exportAcrossLitePuz").get_attribute("class") or ""):
        raise RuntimeError("Crosserville did not enable Across Lite export.")
    page.locator("#id_exportAcrossLitePuz").evaluate("el => el.click()")
    page.locator("#id_exportPuzFileModal").wait_for(state="visible", timeout=10_000)
    with page.expect_download(timeout=20_000) as download_info:
        page.locator("#id_exportPuzCreateBtn").click(timeout=10_000)
    downloaded = download_info.value.path()
    puzzle = puz.read(downloaded)
    rows: list[str] = []
    for row_index in range(puzzle.height):
        row = puzzle.solution[row_index * puzzle.width : (row_index + 1) * puzzle.width]
        rows.append("".join(_puz_cell_to_grid_cell(cell) for cell in row))
    return rows, _puz_clues_by_entry(rows, puzzle.clues)


def _scrape_visible_clues(page: Any, rows: list[str]) -> dict[tuple[int, str], str]:
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(150)
    except Exception:
        pass
    grid_box = _crosserville_grid_box(page, len(rows))
    if not grid_box:
        return {}
    mapped: dict[tuple[int, str], str] = {}
    for number, direction, row, col in _numbered_slots(rows):
        click_count = 2 if direction == "down" else 1
        for _ in range(click_count):
            page.mouse.click(
                grid_box["x"] + (col + 0.5) * grid_box["cell"],
                grid_box["y"] + (row + 0.5) * grid_box["cell"],
            )
            page.wait_for_timeout(120)
        clue = _current_visible_clue(page, number, direction)
        if clue:
            mapped[(number, direction)] = clue
    return mapped


def _crosserville_grid_box(page: Any, size: int) -> dict[str, float] | None:
    selectors = ("#id_grid", "#id_crosswordGrid", "#id_gridSvg", ".crossword-grid", ".grid")
    for selector in selectors:
        try:
            box = page.locator(selector).first.bounding_box(timeout=500)
        except Exception:
            box = None
        if box and box["width"] > 120 and box["height"] > 120:
            edge = min(box["width"], box["height"])
            return {"x": box["x"], "y": box["y"], "cell": edge / size}
    try:
        box = page.evaluate(
            """size => {
                const candidates = [...document.querySelectorAll('body *')]
                  .map(el => {
                    const r = el.getBoundingClientRect();
                    return {x:r.x, y:r.y, width:r.width, height:r.height};
                  })
                  .filter(r => r.width >= 240 && r.height >= 240 && r.x < 850 && r.y < 450)
                  .filter(r => Math.abs(r.width - r.height) <= Math.max(20, r.width * 0.18))
                  .sort((a, b) => (b.width * b.height) - (a.width * a.height))[0];
                if (!candidates) return null;
                const edge = Math.min(candidates.width, candidates.height);
                return {x:candidates.x, y:candidates.y, cell: edge / size};
            }""",
            size,
        )
    except Exception:
        return None
    return box if isinstance(box, dict) else None


def _current_visible_clue(page: Any, number: int, direction: str) -> str:
    label = "Across" if direction == "across" else "Down"
    try:
        text = page.locator("body").inner_text(timeout=1_000)
    except Exception:
        return ""
    pattern = rf"{number}-{label}\s+\(\d+\)(.*?)(?:\n\s*(?:Slot Options|Slot Filter|Global Filters|Auto Fill|Find Slot Options|Exclude From)|$)"
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    lines = [line.strip() for line in match.group(1).splitlines() if line.strip()]
    for line in lines:
        if re.fullmatch(r"[A-Z ]+", line):
            continue
        if re.fullmatch(r"\(\d+\)", line):
            continue
        if line.startswith("Exclude "):
            continue
        if len(line) > 2:
            return line
    return ""


def _numbered_slots(rows: list[str]) -> list[tuple[int, str, int, int]]:
    blocks = [[cell == BLOCK for cell in row] for row in rows]
    slots: list[tuple[int, str, int, int]] = []
    number = 1
    size = len(rows)
    for row in range(size):
        for col in range(size):
            if blocks[row][col]:
                continue
            starts_across = (col == 0 or blocks[row][col - 1]) and col + 2 < size and not blocks[row][col + 1] and not blocks[row][col + 2]
            starts_down = (row == 0 or blocks[row - 1][col]) and row + 2 < size and not blocks[row + 1][col] and not blocks[row + 2][col]
            if starts_across:
                slots.append((number, "across", row, col))
            if starts_down:
                slots.append((number, "down", row, col))
            if starts_across or starts_down:
                number += 1
    return slots


def _puz_clues_by_entry(rows: list[str], clues: list[str]) -> dict[tuple[int, str], str]:
    blocks = [[cell == BLOCK for cell in row] for row in rows]
    clue_index = 0
    mapped: dict[tuple[int, str], str] = {}
    number = 1
    size = len(rows)
    for row in range(size):
        for col in range(size):
            if blocks[row][col]:
                continue
            starts_across = (col == 0 or blocks[row][col - 1]) and col + 2 < size and not blocks[row][col + 1] and not blocks[row][col + 2]
            starts_down = (row == 0 or blocks[row - 1][col]) and row + 2 < size and not blocks[row + 1][col] and not blocks[row + 2][col]
            if starts_across:
                mapped[(number, "across")] = clues[clue_index] if clue_index < len(clues) else ""
                clue_index += 1
            if starts_down:
                mapped[(number, "down")] = clues[clue_index] if clue_index < len(clues) else ""
                clue_index += 1
            if starts_across or starts_down:
                number += 1
    return mapped


def _puz_cell_to_grid_cell(cell: str) -> str:
    if cell == ".":
        return BLOCK
    if cell.isalpha():
        return cell.upper()
    return "."
