import json
from pathlib import Path

import pytest

from crossword_tools import load_puzzle, validate


ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize(
    ("path", "expected_size"),
    [
        (
            ROOT / "puzzles" / "ai-generated" / "puzzle.json",
            "15x15",
        ),
        (
            ROOT / "puzzles" / "autocomplete" / "puzzle.json",
            "15x15",
        ),
        (
            ROOT / "puzzles" / "background-check" / "puzzle.json",
            "21x21",
        ),
    ],
)
def test_published_puzzles_are_valid(
    path: Path,
    expected_size: str,
) -> None:
    errors, summary = validate(load_puzzle(path))

    assert errors == []
    assert summary["size"] == expected_size
    assert summary["checked_cells"] == summary["open_cells"]


def test_sunday_word_count_limit_is_reported() -> None:
    separators = {3, 7, 11, 15}
    grid = [
        "".join(
            "#" if row in separators or column in separators else "A"
            for column in range(21)
        )
        for row in range(21)
    ]
    data = {
        "size": {"rows": 21, "columns": 21},
        "grid": grid,
        "clues": {"Across": [], "Down": []},
    }

    errors, summary = validate(data)

    assert summary["word_count"] > 140
    assert any("themed 21x21 maximum is 140" in error for error in errors)


def test_answer_mismatch_is_reported() -> None:
    data = json.loads(
        (ROOT / "puzzles" / "ai-generated" / "puzzle.json").read_text()
    )
    data["clues"]["Across"][0]["answer"] = "WRONG"

    errors, _ = validate(data)

    assert any("answer mismatch for 1-Across" in error for error in errors)
