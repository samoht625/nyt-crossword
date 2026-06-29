from scripts.serve import routed_path


def test_clean_puzzle_routes_use_the_site_document() -> None:
    assert routed_path("/puzzle/background-check") == "/index.html"
    assert routed_path("/puzzle/ai-generated/") == "/index.html"


def test_static_assets_are_not_rewritten() -> None:
    assert routed_path("/styles.css") == "/styles.css"
    assert routed_path("/puzzles/AI_Generated.puz") == "/puzzles/AI_Generated.puz"
    assert routed_path("/puzzle/not_valid") == "/puzzle/not_valid"
