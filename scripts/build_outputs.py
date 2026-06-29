#!/usr/bin/env python3
"""Build digital and print assets from canonical puzzle JSON."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import puz
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

try:
    from .validate import Entry, load_puzzle, number_grid, validate
except ImportError:  # Support direct execution from the repository root.
    from validate import Entry, load_puzzle, number_grid, validate


PAGE_WIDTH, PAGE_HEIGHT = LETTER
MARGIN = 54


def slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")


def clue_lookup(data: dict[str, Any]) -> dict[tuple[str, int], str]:
    return {
        (direction, int(item["number"])): str(item["clue"])
        for direction in ("Across", "Down")
        for item in data["clues"][direction]
    }


def wrap_text(text: str, font: str, size: float, width: float) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and stringWidth(candidate, font, size) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


def draw_grid(
    pdf: canvas.Canvas,
    grid: list[str],
    numbers: list[list[int | None]],
    *,
    left: float,
    top: float,
    size: float,
    show_answers: bool,
) -> None:
    height = len(grid)
    width = len(grid[0])
    cell = min(size / width, size / height)
    actual_width = width * cell
    actual_height = height * cell
    bottom = top - actual_height

    pdf.setStrokeColorRGB(0, 0, 0)
    pdf.setLineWidth(1.5)
    pdf.rect(left, bottom, actual_width, actual_height, stroke=1, fill=0)
    for row in range(height):
        for column in range(width):
            x = left + column * cell
            y = top - (row + 1) * cell
            if grid[row][column] == "#":
                pdf.setFillColorRGB(0, 0, 0)
                pdf.rect(x, y, cell, cell, stroke=0, fill=1)
                continue
            pdf.setFillColorRGB(1, 1, 1)
            pdf.rect(x, y, cell, cell, stroke=0, fill=1)
            pdf.setStrokeColorRGB(0, 0, 0)
            pdf.setLineWidth(0.45)
            pdf.rect(x, y, cell, cell, stroke=1, fill=0)
            number = numbers[row][column]
            if number is not None:
                pdf.setFillColorRGB(0, 0, 0)
                pdf.setFont("Helvetica", max(5.5, cell * 0.19))
                pdf.drawString(x + 1.5, y + cell - max(6.5, cell * 0.22), str(number))
            if show_answers:
                pdf.setFillColorRGB(0, 0, 0)
                pdf.setFont("Helvetica-Bold", cell * 0.48)
                letter = grid[row][column]
                letter_width = stringWidth(letter, "Helvetica-Bold", cell * 0.48)
                pdf.drawString(
                    x + (cell - letter_width) / 2,
                    y + cell * 0.28,
                    letter,
                )


def draw_page_footer(pdf: canvas.Canvas, page_number: int) -> None:
    pdf.setFont("Helvetica", 8)
    pdf.setFillColorRGB(0.35, 0.35, 0.35)
    pdf.drawCentredString(PAGE_WIDTH / 2, 24, str(page_number))


def draw_clue_pages(
    pdf: canvas.Canvas,
    entries: list[Entry],
    clues: dict[tuple[str, int], str],
    *,
    show_answers: bool,
    first_page_number: int,
    title: str,
) -> int:
    page_number = first_page_number
    y = 0.0
    current_direction = ""

    def new_page() -> None:
        nonlocal page_number, y
        if y:
            draw_page_footer(pdf, page_number)
            pdf.showPage()
            page_number += 1
        pdf.setTitle(title)
        pdf.setFont("Helvetica-Bold", 12)
        pdf.setFillColorRGB(0, 0, 0)
        pdf.drawString(MARGIN, PAGE_HEIGHT - MARGIN, title)
        y = PAGE_HEIGHT - MARGIN - 28

    new_page()
    for entry in entries:
        if entry.direction != current_direction:
            heading_height = 28
            if y - heading_height < MARGIN + 30:
                new_page()
            current_direction = entry.direction
            pdf.setFont("Helvetica-Bold", 11)
            pdf.drawString(MARGIN, y, current_direction.upper())
            y -= 24

        clue_text = f"{entry.number}  {clues[(entry.direction, entry.number)]}"
        clue_width = 395 if show_answers else PAGE_WIDTH - 2 * MARGIN
        lines = wrap_text(clue_text, "Helvetica", 10, clue_width)
        row_height = len(lines) * 13 + 10
        if y - row_height < MARGIN:
            new_page()
            pdf.setFont("Helvetica-Bold", 11)
            pdf.drawString(MARGIN, y, f"{current_direction.upper()} (CONTINUED)")
            y -= 24

        pdf.setFont("Helvetica", 10)
        for line in lines:
            pdf.drawString(MARGIN, y, line)
            y -= 13
        if show_answers:
            pdf.setFont("Helvetica-Bold", 10)
            pdf.drawRightString(PAGE_WIDTH - MARGIN, y + 13 * len(lines), entry.answer)
        y -= 10

    draw_page_footer(pdf, page_number)
    return page_number


def write_print_pdf(
    path: Path,
    data: dict[str, Any],
    entries: list[Entry],
    numbers: list[list[int | None]],
    *,
    show_answers: bool,
) -> None:
    grid = data["grid"]
    clues = clue_lookup(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(path), pagesize=LETTER, pageCompression=1)
    pdf.setTitle(data["title"])
    pdf.setAuthor(data["author"])
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(MARGIN, PAGE_HEIGHT - MARGIN, data["title"])
    pdf.setFont("Helvetica", 10)
    pdf.drawRightString(PAGE_WIDTH - MARGIN, PAGE_HEIGHT - MARGIN + 2, data["author"])
    draw_grid(
        pdf,
        grid,
        numbers,
        left=76.5,
        top=PAGE_HEIGHT - 90,
        size=459,
        show_answers=show_answers,
    )
    draw_page_footer(pdf, 1)
    pdf.showPage()
    draw_clue_pages(
        pdf,
        entries,
        clues,
        show_answers=show_answers,
        first_page_number=2,
        title=data["title"],
    )
    pdf.save()


def write_nyt_submission_pdf(
    path: Path,
    data: dict[str, Any],
    constructor: dict[str, str],
    entries: list[Entry],
    numbers: list[list[int | None]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(path), pagesize=LETTER, pageCompression=1)
    pdf.setTitle(data["title"])
    pdf.setAuthor(data["author"])

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(MARGIN, PAGE_HEIGHT - MARGIN, constructor["name"])
    pdf.setFont("Helvetica", 10)
    header_lines = [
        constructor["address"],
        f"{constructor['city']}, {constructor['state']} {constructor['postal_code']}",
        constructor["email"],
    ]
    y = PAGE_HEIGHT - MARGIN - 16
    for line in header_lines:
        pdf.drawString(MARGIN, y, line)
        y -= 14
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawRightString(PAGE_WIDTH - MARGIN, PAGE_HEIGHT - MARGIN, data["title"])
    pdf.setFont("Helvetica", 9)
    pdf.drawRightString(
        PAGE_WIDTH - MARGIN,
        PAGE_HEIGHT - MARGIN - 16,
        f"15 x 15 | {len(entries)} words",
    )
    draw_grid(
        pdf,
        data["grid"],
        numbers,
        left=76.5,
        top=PAGE_HEIGHT - 125,
        size=459,
        show_answers=True,
    )
    draw_page_footer(pdf, 1)
    pdf.showPage()
    draw_clue_pages(
        pdf,
        entries,
        clue_lookup(data),
        show_answers=True,
        first_page_number=2,
        title=f"{data['title']} — {data['author']}",
    )
    pdf.save()


def write_puz(path: Path, data: dict[str, Any], entries: list[Entry]) -> None:
    clues = clue_lookup(data)
    puzzle = puz.Puzzle()
    puzzle.width = data["size"]["columns"]
    puzzle.height = data["size"]["rows"]
    puzzle.title = data["title"]
    puzzle.author = data["author"]
    puzzle.copyright = data["copyright"]
    puzzle.solution = "".join(data["grid"]).replace("#", ".")
    puzzle.fill = "".join(
        "." if character == "#" else "-" for character in "".join(data["grid"])
    )
    puzzle.clues = [
        clues[(entry.direction, entry.number)]
        for entry in sorted(
            entries,
            key=lambda entry: (entry.number, entry.direction == "Down"),
        )
    ]
    puzzle.notes = str(data.get("theme", {}).get("summary", ""))
    path.parent.mkdir(parents=True, exist_ok=True)
    puzzle.save(str(path))


def write_ipuz(path: Path, data: dict[str, Any], entries: list[Entry]) -> None:
    clues = clue_lookup(data)
    numbers, _ = number_grid(data["grid"])
    puzzle_grid: list[list[str | int]] = []
    solution_grid: list[list[str]] = []
    for row, values in enumerate(data["grid"]):
        puzzle_row: list[str | int] = []
        solution_row: list[str] = []
        for column, value in enumerate(values):
            if value == "#":
                puzzle_row.append("#")
                solution_row.append("#")
            else:
                puzzle_row.append(numbers[row][column] or 0)
                solution_row.append(value)
        puzzle_grid.append(puzzle_row)
        solution_grid.append(solution_row)

    payload = {
        "version": "http://ipuz.org/v2",
        "kind": ["http://ipuz.org/crossword#1"],
        "title": data["title"],
        "author": data["author"],
        "copyright": data["copyright"],
        "dimensions": {
            "width": data["size"]["columns"],
            "height": data["size"]["rows"],
        },
        "puzzle": puzzle_grid,
        "solution": solution_grid,
        "clues": {
            direction: [
                [entry.number, clues[(direction, entry.number)]]
                for entry in entries
                if entry.direction == direction
            ]
            for direction in ("Across", "Down")
        },
        "notes": str(data.get("theme", {}).get("summary", "")),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("puzzle", help="Path to the canonical puzzle JSON")
    parser.add_argument(
        "--output",
        required=True,
        help="Directory for generated files",
    )
    parser.add_argument(
        "--format",
        action="append",
        choices=("puz", "ipuz", "test-pdf", "solution-pdf"),
        dest="formats",
        help="Output format; repeat to select several (default: all)",
    )
    parser.add_argument(
        "--constructor",
        help="Optional private constructor JSON for a submission PDF",
    )
    parser.add_argument(
        "--submission-output",
        help="Required output path when --constructor is supplied",
    )
    args = parser.parse_args()

    data = load_puzzle(Path(args.puzzle))
    errors, _ = validate(data)
    if errors:
        raise SystemExit("Puzzle is invalid:\n- " + "\n- ".join(errors))

    numbers, entries = number_grid(data["grid"])
    exports = Path(args.output)
    basename = slug(data["title"])
    formats = set(args.formats or ("puz", "ipuz", "test-pdf", "solution-pdf"))
    if "puz" in formats:
        write_puz(exports / f"{basename}.puz", data, entries)
    if "ipuz" in formats:
        write_ipuz(exports / f"{basename}.ipuz", data, entries)
    if "test-pdf" in formats:
        write_print_pdf(
            exports / f"{basename}_test_solve.pdf",
            data,
            entries,
            numbers,
            show_answers=False,
        )
    if "solution-pdf" in formats:
        write_print_pdf(
            exports / f"{basename}_solution.pdf",
            data,
            entries,
            numbers,
            show_answers=True,
        )

    if args.constructor:
        if not args.submission_output:
            parser.error("--submission-output is required with --constructor")
        private_path = Path(args.constructor)
        constructor = json.loads(private_path.read_text(encoding="utf-8"))
        write_nyt_submission_pdf(
            Path(args.submission_output),
            data,
            constructor,
            entries,
            numbers,
        )
    print(f"Built outputs for {data['title']}")


if __name__ == "__main__":
    main()
