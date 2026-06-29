"""Canonical puzzle validation API and CLI."""

from scripts.validate import Entry, load_puzzle, main, number_grid, validate

__all__ = ["Entry", "load_puzzle", "number_grid", "validate", "main"]


if __name__ == "__main__":
    main()
