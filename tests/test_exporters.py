import json
import random

import puz

from family_crossword.clues import add_clues
from family_crossword.exporters import write_outputs
from family_crossword.model import Candidate
from family_crossword.solver import fill_pattern


def test_exports_json_ipuz_and_puz(tmp_path) -> None:
    blocks = [[False for _ in range(5)] for _ in range(5)]
    candidates = [
        Candidate("ABCDE", source="generic"),
        Candidate("FGHIJ", source="generic"),
        Candidate("KLMNO", source="generic"),
        Candidate("PQRST", source="generic"),
        Candidate("UVWXY", source="generic"),
        Candidate("AFKPU", source="generic"),
        Candidate("BGLQV", source="generic"),
        Candidate("CHMRW", source="generic"),
        Candidate("DINSX", source="generic"),
        Candidate("EJOTY", source="generic"),
    ]
    puzzle = fill_pattern(blocks, candidates, random.Random(1), metadata={"title": "Export Test"})
    assert puzzle is not None
    add_clues(puzzle, use_ai=False)

    write_outputs(puzzle, tmp_path, report={"status": "ok"})

    site_payload = json.loads((tmp_path / "puzzle.json").read_text())
    ipuz_payload = json.loads((tmp_path / "puzzle.ipuz").read_text())
    loaded_puz = puz.read(str(tmp_path / "puzzle.puz"))

    assert site_payload["schema_version"] == 1
    assert ipuz_payload["dimensions"] == {"width": 5, "height": 5}
    assert loaded_puz.width == 5
    assert loaded_puz.height == 5
