import json
from pathlib import Path

import puz


ROOT = Path(__file__).parents[1]


def test_site_manifest_points_to_valid_puzzles() -> None:
    web = ROOT / "web"
    manifest = json.loads((web / "puzzles.json").read_text())

    assert {item["slug"] for item in manifest} == {
        "ai-generated",
        "autocomplete",
    }
    for item in manifest:
        puzzle_path = web / item["file"]
        assert puzzle_path.is_file()
        assert puz.read(str(puzzle_path)).title == item["title"]
