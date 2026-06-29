from pathlib import Path

import pytest

from scripts import construct


ROOT = Path(__file__).parents[1]


def test_construction_spec_configures_fixed_theme_letters() -> None:
    spec = construct.load_construction_spec(
        ROOT / "puzzles" / "ai-generated" / "construction.json"
    )

    construct.configure(spec)

    assert construct.SIZE == 15
    assert construct.FIXED_LETTERS[(2, 0)] == "W"
    assert construct.FIXED_LETTERS[(12, 14)] == "S"
    assert (5, 0) in construct.FIXED_BLOCKS


def test_construction_spec_rejects_conflicting_cells() -> None:
    with pytest.raises(ValueError, match="fixed block"):
        construct.configure(
            {
                "size": 5,
                "theme_placements": [
                    {
                        "direction": "Across",
                        "row": 1,
                        "column": 1,
                        "answer": "HELLO",
                    }
                ],
                "fixed_blocks": [[1, 1]],
            }
        )
