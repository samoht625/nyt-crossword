import json
from pathlib import Path

import puz


ROOT = Path(__file__).parents[1]


def test_spa_fallback_matches_index() -> None:
    web = ROOT / "web"
    assert (web / "404.html").read_text() == (web / "index.html").read_text()


def test_site_manifest_points_to_valid_puzzles() -> None:
    web = ROOT / "web"
    manifest = json.loads((web / "puzzles.json").read_text())

    assert {item["slug"] for item in manifest} == {
        "ai-generated",
        "autocomplete",
        "background-check",
    }
    for item in manifest:
        puzzle_path = web / item["file"]
        assert puzzle_path.is_file()
        puzzle = puz.read(str(puzzle_path))
        assert puzzle.title == item["title"]
        assert f"{puzzle.width}×{puzzle.height}" == item["size"]
