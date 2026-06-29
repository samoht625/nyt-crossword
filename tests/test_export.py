from pathlib import Path

import puz

from crossword_tools import load_puzzle, number_grid
from crossword_tools.export import write_ipuz, write_puz


ROOT = Path(__file__).parents[1]


def test_puz_and_ipuz_exports(tmp_path: Path) -> None:
    data = load_puzzle(ROOT / "puzzles" / "ai-generated" / "puzzle.json")
    _, entries = number_grid(data["grid"])
    puz_path = tmp_path / "puzzle.puz"
    ipuz_path = tmp_path / "puzzle.ipuz"

    write_puz(puz_path, data, entries)
    write_ipuz(ipuz_path, data, entries)

    exported = puz.read(str(puz_path))
    assert exported.title == data["title"]
    assert exported.author == data["author"]
    assert exported.solution == "".join(data["grid"]).replace("#", ".")
    assert '"solution"' in ipuz_path.read_text()
