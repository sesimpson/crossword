from __future__ import annotations

import argparse
import os
from pathlib import Path

from .crosserville import generate_with_crosserville_from_file
from .generator import generate_from_file


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="family-crossword")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="Generate weekly family crossword artifacts.")
    generate.add_argument("--input", required=True, help="Normalized weekly YAML/JSON context file.")
    generate.add_argument("--out", required=True, help="Output directory for puzzle artifacts.")
    generate.add_argument("--sizes", default="13,11,9", help="Comma-separated grid sizes to try, in preference order.")
    generate.add_argument("--attempts", type=int, default=2000, help="Total search attempts split across sizes.")
    generate.add_argument("--timeout-minutes", type=float, default=20, help="Maximum generation time.")
    generate.add_argument("--seed", type=int, default=None, help="Optional deterministic random seed.")
    generate.add_argument("--model", default=os.getenv("OPENAI_MODEL"), help="OpenAI model for clue generation.")
    generate.add_argument("--no-ai-clues", action="store_true", help="Use deterministic fallback clues only.")
    generate.add_argument("--backend", choices=["local", "crosserville"], default="local", help="Generation backend.")
    generate.add_argument("--show-browser", action="store_true", help="Show the Crosserville browser while generating.")

    args = parser.parse_args(argv)
    if args.command == "generate":
        sizes = [int(size.strip()) for size in args.sizes.split(",") if size.strip()]
        kwargs = {
            "sizes": sizes,
            "attempts": args.attempts,
            "timeout_minutes": args.timeout_minutes,
            "seed": args.seed,
            "model": args.model,
            "use_ai_clues": not args.no_ai_clues,
        }
        if args.backend == "crosserville":
            puzzle = generate_with_crosserville_from_file(
                Path(args.input),
                Path(args.out),
                headless=not args.show_browser,
                **kwargs,
            )
        else:
            puzzle = generate_from_file(
                Path(args.input),
                Path(args.out),
                **kwargs,
            )
        print(
            f"Generated {puzzle.size}x{puzzle.size} crossword with "
            f"{len(puzzle.family_entries)} family entries at {Path(args.out)}"
        )


if __name__ == "__main__":
    main()
