import json
from pathlib import Path

import pytest

from crossword_tools import load_puzzle, validate


ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize(
    "path",
    [
        ROOT / "puzzles" / "ai-generated" / "puzzle.json",
        ROOT / "puzzles" / "autocomplete" / "puzzle.json",
    ],
)
def test_published_puzzles_are_valid(path: Path) -> None:
    errors, summary = validate(load_puzzle(path))

    assert errors == []
    assert summary["size"] == "15x15"
    assert summary["checked_cells"] == summary["open_cells"]


def test_answer_mismatch_is_reported() -> None:
    data = json.loads(
        (ROOT / "puzzles" / "ai-generated" / "puzzle.json").read_text()
    )
    data["clues"]["Across"][0]["answer"] = "WRONG"

    errors, _ = validate(data)

    assert any("answer mismatch for 1-Across" in error for error in errors)
