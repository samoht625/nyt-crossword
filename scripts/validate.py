#!/usr/bin/env python3
"""Validate the canonical crossword against NYT-style daily rules."""

from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Entry:
    direction: str
    number: int
    row: int
    column: int
    answer: str
    cells: tuple[tuple[int, int], ...]

    @property
    def length(self) -> int:
        return len(self.answer)


def load_puzzle(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Puzzle source must be a JSON object")
    return data


def number_grid(grid: list[str]) -> tuple[list[list[int | None]], list[Entry]]:
    height = len(grid)
    width = len(grid[0]) if grid else 0
    numbers: list[list[int | None]] = [[None] * width for _ in range(height)]
    starts: dict[tuple[int, int], int] = {}
    next_number = 1

    for row in range(height):
        for column in range(width):
            if grid[row][column] == "#":
                continue
            starts_across = (
                (column == 0 or grid[row][column - 1] == "#")
                and column + 1 < width
                and grid[row][column + 1] != "#"
            )
            starts_down = (
                (row == 0 or grid[row - 1][column] == "#")
                and row + 1 < height
                and grid[row + 1][column] != "#"
            )
            if starts_across or starts_down:
                starts[(row, column)] = next_number
                numbers[row][column] = next_number
                next_number += 1

    entries: list[Entry] = []
    for direction in ("Across", "Down"):
        for (row, column), number in starts.items():
            dr, dc = (0, 1) if direction == "Across" else (1, 0)
            previous_row, previous_column = row - dr, column - dc
            if (
                0 <= previous_row < height
                and 0 <= previous_column < width
                and grid[previous_row][previous_column] != "#"
            ):
                continue
            cells: list[tuple[int, int]] = []
            current_row, current_column = row, column
            while (
                0 <= current_row < height
                and 0 <= current_column < width
                and grid[current_row][current_column] != "#"
            ):
                cells.append((current_row, current_column))
                current_row += dr
                current_column += dc
            if len(cells) < 2:
                continue
            entries.append(
                Entry(
                    direction=direction,
                    number=number,
                    row=row,
                    column=column,
                    answer="".join(grid[r][c] for r, c in cells),
                    cells=tuple(cells),
                )
            )

    entries.sort(key=lambda entry: (entry.direction != "Across", entry.number))
    return numbers, entries


def validate(
    data: dict[str, Any],
    *,
    require_symmetry: bool = True,
    require_checked: bool = True,
) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    expected_height = data.get("size", {}).get("rows")
    expected_width = data.get("size", {}).get("columns")
    raw_grid = data.get("grid")

    if not isinstance(raw_grid, list) or not all(
        isinstance(row, str) for row in raw_grid
    ):
        return ["grid must be an array of strings"], {}

    grid = [row.upper() for row in raw_grid]
    height = len(grid)
    width = len(grid[0]) if grid else 0
    if height != expected_height or width != expected_width:
        errors.append(
            f"grid is {height}x{width}; metadata says "
            f"{expected_height}x{expected_width}"
        )
    if any(len(row) != width for row in grid):
        errors.append("grid rows have inconsistent lengths")
        return errors, {}
    if any(character != "#" and not character.isalpha() for row in grid for character in row):
        errors.append("grid contains characters other than A-Z and #")

    if require_symmetry:
        for row in range(height):
            for column in range(width):
                opposite = grid[height - 1 - row][width - 1 - column]
                if (grid[row][column] == "#") != (opposite == "#"):
                    errors.append(
                        f"block symmetry fails at row {row + 1}, column {column + 1}"
                    )
                    break
            if errors and errors[-1].startswith("block symmetry"):
                break

    open_cells = {
        (row, column)
        for row in range(height)
        for column in range(width)
        if grid[row][column] != "#"
    }
    if open_cells:
        seen = {next(iter(open_cells))}
        queue = deque(seen)
        while queue:
            row, column = queue.popleft()
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                neighbor = row + dr, column + dc
                if neighbor in open_cells and neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
        if seen != open_cells:
            errors.append("white squares are not all connected")
    else:
        errors.append("grid contains no white squares")

    numbers, entries = number_grid(grid)
    cell_directions: dict[tuple[int, int], set[str]] = {
        cell: set() for cell in open_cells
    }
    for entry in entries:
        if entry.length < 3:
            errors.append(
                f"{entry.number}-{entry.direction} is only {entry.length} letters"
            )
        for cell in entry.cells:
            cell_directions[cell].add(entry.direction)
    unchecked = [
        (row + 1, column + 1)
        for (row, column), directions in cell_directions.items()
        if directions != {"Across", "Down"}
    ]
    if require_checked and unchecked:
        errors.append(f"{len(unchecked)} cells are not fully checked: {unchecked[:8]}")

    if height == width == 15 and len(entries) > 78:
        errors.append(f"word count is {len(entries)}; themed 15x15 maximum is 78")
    answers = [entry.answer for entry in entries]
    duplicates = sorted({answer for answer in answers if answers.count(answer) > 1})
    if duplicates:
        errors.append(f"duplicate answers: {', '.join(duplicates)}")

    clue_entries: dict[tuple[str, int], dict[str, Any]] = {}
    clues = data.get("clues", {})
    for direction in ("Across", "Down"):
        direction_clues = clues.get(direction, []) if isinstance(clues, dict) else []
        if not isinstance(direction_clues, list):
            errors.append(f"{direction} clues must be an array")
            continue
        for clue in direction_clues:
            if not isinstance(clue, dict):
                errors.append(f"{direction} clue is not an object")
                continue
            key = direction, clue.get("number")
            if key in clue_entries:
                errors.append(f"duplicate clue for {key[1]}-{direction}")
            clue_entries[key] = clue

    for entry in entries:
        key = entry.direction, entry.number
        clue = clue_entries.get(key)
        if clue is None:
            errors.append(f"missing clue for {entry.number}-{entry.direction}")
            continue
        if clue.get("answer", "").upper() != entry.answer:
            errors.append(
                f"answer mismatch for {entry.number}-{entry.direction}: "
                f"{clue.get('answer')} != {entry.answer}"
            )
        if not str(clue.get("clue", "")).strip():
            errors.append(f"empty clue for {entry.number}-{entry.direction}")

    expected_keys = {(entry.direction, entry.number) for entry in entries}
    for direction, number in clue_entries.keys() - expected_keys:
        errors.append(f"orphan clue for {number}-{direction}")

    theme_answers = {
        str(item.get("answer", "")).upper()
        for item in data.get("theme", {}).get("entries", [])
        if isinstance(item, dict)
    }
    missing_theme = sorted(theme_answers - set(answers))
    if missing_theme:
        errors.append(f"theme answers missing from grid: {', '.join(missing_theme)}")

    summary = {
        "size": f"{height}x{width}",
        "word_count": len(entries),
        "block_count": sum(row.count("#") for row in grid),
        "checked_cells": len(open_cells) - len(unchecked),
        "open_cells": len(open_cells),
        "across_count": sum(entry.direction == "Across" for entry in entries),
        "down_count": sum(entry.direction == "Down" for entry in entries),
        "theme_entries_found": len(theme_answers & set(answers)),
        "numbered_grid": numbers,
    }
    return errors, summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("puzzle", help="Path to the canonical puzzle JSON")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--allow-asymmetric", action="store_true")
    parser.add_argument("--allow-unchecked", action="store_true")
    args = parser.parse_args()

    try:
        data = load_puzzle(Path(args.puzzle))
        errors, summary = validate(
            data,
            require_symmetry=not args.allow_asymmetric,
            require_checked=not args.allow_unchecked,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error

    if args.as_json:
        print(json.dumps({"valid": not errors, "errors": errors, **summary}, indent=2))
    else:
        if errors:
            for error in errors:
                print(f"ERROR: {error}")
        else:
            checked_note = (
                ", all cells checked"
                if summary["checked_cells"] == summary["open_cells"]
                else ""
            )
            print(
                "VALID: "
                f"{summary['size']}, {summary['word_count']} words, "
                f"{summary['block_count']} blocks{checked_note}"
            )
    raise SystemExit(bool(errors))


if __name__ == "__main__":
    main()
