"""Pattern generation and lexicon-backed fill CLI."""

from scripts.construct import (
    FillSolver,
    Lexicon,
    configure,
    generate_patterns,
    get_slots,
    load_construction_spec,
    main,
)

__all__ = [
    "FillSolver",
    "Lexicon",
    "configure",
    "generate_patterns",
    "get_slots",
    "load_construction_spec",
    "main",
]


if __name__ == "__main__":
    main()
