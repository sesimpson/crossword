# Weekly Family Crossword Generator

Generate a family-heavy US-style crossword from a normalized weekly context file, then export site-ready JSON plus `.ipuz` and Across Lite `.puz` files.

```bash
family-crossword generate \
  --input examples/weekly_context.yml \
  --out dist/crossword \
  --sizes 13,11,9 \
  --attempts 2000 \
  --timeout-minutes 20
```

The generator is designed for GitHub Actions and a downstream family website deploy. It does not automate Crosserville; Crosserville can still be used manually to review imported `.puz` files.

## Crosswyrd Backend

The default backend is local. To use Crosswyrd as a black-box autofill engine:

```bash
family-crossword generate \
  --backend crosswyrd \
  --input examples/weekly_context.yml \
  --out dist/crosswyrd \
  --sizes 13,11,9 \
  --attempts 12 \
  --timeout-minutes 8 \
  --no-ai-clues
```

This backend opens [Crosswyrd](https://crosswyrd.app/builder), imports exact-size blank `.puz` templates, adds family entries to the Word Bank, places as many valid family words as it can, runs Auto-Fill, and retries with different templates/placement budgets. It backs off from many forced family words to fewer forced words so weekly runs can still publish a filled puzzle.

Install the browser runtime before using it locally or in CI:

```bash
python -m playwright install chromium
```

## Inputs

The CLI expects YAML or JSON with normalized family context:

```yaml
week_of: 2026-05-24
title: Family Crossword
people:
  - answer: Campbell
    clue_hint: Family surname
    priority: 10
places:
  - answer: Lake House
    clue_hint: Summer gathering spot
events:
  - answer: Picnic
    clue_hint: Weekend plan
inside_jokes: []
books: []
news_items: []
```

Entries can be strings or objects. Object fields:

- `answer`: required unless the object has `name` or `title`
- `clue_hint`: optional context for AI clue generation
- `priority`: optional integer, higher means the solver tries harder to include it
- `tags`: optional list of labels

Answers are normalized to uppercase A-Z crossword fill. Spaces and punctuation are removed.

## Outputs

The output directory contains:

- `puzzle.json`: embeddable website payload with grid, entries, metadata, and score report
- `puzzle.ipuz`: standards-friendly crossword JSON
- `puzzle.puz`: Across Lite binary export via [`puzpy`](https://pypi.org/project/puzpy/)
- `report.json`: generation attempts, warnings, rejected input answers, and chosen score

## AI Clues

If `OPENAI_API_KEY` and `OPENAI_MODEL` are set, the CLI asks the OpenAI Responses API for concise crossword-style clues. The implementation uses the current Responses API shape documented at [OpenAI Responses API](https://platform.openai.com/docs/api-reference/responses), including the `model`, `input`, `instructions`, and `text` fields.

If either variable is missing, generation still succeeds with deterministic fallback clues.

## GitHub Actions

`.github/workflows/weekly-crossword.yml` runs weekly and uploads generated artifacts. The workflow assumes the broader family system has already produced a normalized context file. Override these environment variables in the workflow or calling pipeline:

- `CROSSWORD_INPUT`: default `examples/weekly_context.yml`
- `CROSSWORD_OUTPUT`: default `dist/crossword`
- `CROSSWORD_SIZES`: default `13,11,9`
- `CROSSWORD_ATTEMPTS`: default `2000`
- `CROSSWORD_TIMEOUT_MINUTES`: default `20`
- `CROSSWORD_BACKEND`: default `local`, set to `crosswyrd` for browser-backed generation
