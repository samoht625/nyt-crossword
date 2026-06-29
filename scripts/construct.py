#!/usr/bin/env python3
"""Search for a clean 15x15 fill around the locked theme entries.

This is a construction aid, not the canonical puzzle source. Successful
candidates are written under scratch/ for human review before promotion to
puzzle/puzzle.json.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import time
import urllib.request
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Any

from wordfreq import top_n_list, zipf_frequency
from z3 import And, Bool, BoolVal, Not, Or, PbEq, Solver, is_true, sat


SIZE = 15
THEME_PLACEMENTS: tuple[tuple[str, int, int, str], ...] = ()
THEME_ANSWERS: set[str] = set()
FIXED_LETTERS: dict[tuple[int, int], str] = {}
FIXED_BLOCKS: set[tuple[int, int]] = set()
FIXED_OPEN: set[tuple[int, int]] = set()


def load_construction_spec(path: Path) -> dict[str, Any]:
    """Load and validate a reusable construction specification."""
    with path.open(encoding="utf-8") as handle:
        spec = json.load(handle)
    if not isinstance(spec, dict):
        raise ValueError("Construction spec must be a JSON object")
    return spec


def configure(spec: dict[str, Any]) -> None:
    """Configure the construction engine from one-based puzzle coordinates."""
    global SIZE, THEME_PLACEMENTS, THEME_ANSWERS
    global FIXED_LETTERS, FIXED_BLOCKS, FIXED_OPEN

    size = spec.get("size", 15)
    if isinstance(size, dict):
        rows, columns = size.get("rows"), size.get("columns")
        if rows != columns:
            raise ValueError("Construction currently requires a square grid")
        size = rows
    if not isinstance(size, int) or size < 3:
        raise ValueError("size must be an integer of at least 3")

    placements: list[tuple[str, int, int, str]] = []
    for item in spec.get("theme_placements", []):
        if not isinstance(item, dict):
            raise ValueError("theme_placements entries must be objects")
        direction = str(item.get("direction", "")).title()
        if direction not in {"Across", "Down"}:
            raise ValueError(f"Invalid theme direction: {direction!r}")
        row = int(item["row"]) - 1
        column = int(item["column"]) - 1
        answer = re.sub(r"[^A-Za-z]", "", str(item["answer"])).upper()
        if not answer:
            raise ValueError("Theme answers must contain letters")
        placements.append((direction, row, column, answer))

    fixed_blocks = {
        (int(cell[0]) - 1, int(cell[1]) - 1)
        for cell in spec.get("fixed_blocks", [])
    }
    fixed_open = {
        (int(cell[0]) - 1, int(cell[1]) - 1)
        for cell in spec.get("fixed_open", [])
    }
    fixed_letters: dict[tuple[int, int], str] = {}
    for direction, row, column, answer in placements:
        dr, dc = (0, 1) if direction == "Across" else (1, 0)
        for offset, letter in enumerate(answer):
            cell = row + dr * offset, column + dc * offset
            if not (0 <= cell[0] < size and 0 <= cell[1] < size):
                raise ValueError(f"Theme answer extends beyond the grid: {answer}")
            previous = fixed_letters.setdefault(cell, letter)
            if previous != letter:
                raise ValueError(f"Conflicting theme letters at {cell}")

    all_cells = fixed_blocks | fixed_open | fixed_letters.keys()
    if any(not (0 <= row < size and 0 <= column < size) for row, column in all_cells):
        raise ValueError("Fixed cell lies beyond the grid")
    if fixed_blocks & (fixed_open | fixed_letters.keys()):
        raise ValueError("A fixed block cannot also be open or contain a letter")

    SIZE = size
    THEME_PLACEMENTS = tuple(placements)
    THEME_ANSWERS = {placement[3] for placement in placements}
    FIXED_LETTERS = fixed_letters
    FIXED_BLOCKS = fixed_blocks
    FIXED_OPEN = fixed_open
WORDLIST_URL = (
    "https://raw.githubusercontent.com/Crossword-Nexus/"
    "collaborative-word-list/main/xwordlist.dict"
)

# Common crossword-valid entries that frequency corpora sometimes omit or
# rank oddly. Every one still requires human review if it appears in a fill.
EXTRA_WORDS = {
    "AHA",
    "AHI",
    "AKA",
    "APB",
    "APR",
    "ASAP",
    "ATM",
    "CEO",
    "CIA",
    "CNN",
    "DNA",
    "DVD",
    "EBOOK",
    "EMT",
    "EPA",
    "ETA",
    "FAQ",
    "FBI",
    "GPS",
    "HBO",
    "HIV",
    "HTML",
    "IRS",
    "ISBN",
    "JFK",
    "LASER",
    "MRI",
    "NASA",
    "NBA",
    "NCAA",
    "NFL",
    "NHL",
    "NPR",
    "NYC",
    "OKAY",
    "PBS",
    "PDF",
    "RNA",
    "RSVP",
    "SCUBA",
    "SUV",
    "TLC",
    "TNT",
    "TVA",
    "UFO",
    "UNESCO",
    "USB",
    "USPS",
    "VIP",
    "WHO",
    "WIFI",
    "WWW",
    "YOUTUBE",
}

# Entries that are common in raw web text but unsuitable for this puzzle.
BLOCKLIST = {
    "ANKYLOSE",
    "ANUS",
    "ASS",
    "ASSES",
    "ASAHI",
    "ASSAD",
    "ASUS",
    "ATERGO",
    "BIKS",
    "BITCH",
    "BOOBS",
    "CUM",
    "DEPP",
    "DAMN",
    "DICK",
    "DICKS",
    "EIRENE",
    "EGAN",
    "FAG",
    "FAGS",
    "FUCK",
    "FUCKED",
    "FUCKER",
    "FUCKING",
    "GODDAMN",
    "GIGA",
    "HAMAS",
    "HARA",
    "HELLA",
    "HOE",
    "HOES",
    "ISIS",
    "IRAM",
    "INS",
    "INAWORD",
    "ITMAYBE",
    "IAEA",
    "JIZZ",
    "KUNT",
    "LANKA",
    "LIGA",
    "LUMIA",
    "MAS",
    "MILF",
    "NAM",
    "NAZI",
    "NAZIS",
    "NIGGA",
    "NIGGER",
    "PENIS",
    "PGRATED",
    "PORN",
    "PUSSY",
    "RAPE",
    "RAPED",
    "RAPER",
    "RAPES",
    "RAPIST",
    "RAMTOUGH",
    "SAID",
    "SAY",
    "SACRA",
    "SERIE",
    "SHIPTO",
    "SMES",
    "SMILEAT",
    "SHIT",
    "SHITS",
    "SLUT",
    "SLUTS",
    "TITS",
    "TVA",
    "TBH",
    "TBOND",
    "TAE",
    "TEL",
    "TENU",
    "TEX",
    "THA",
    "THISWAY",
    "TRIS",
    "TRI",
    "TWAT",
    "VAGINA",
    "WINN",
    "WHORE",
    "WORD",
    "UMAR",
    "USGS",
    "PROG",
    "DEMS",
    "DEM",
    "DIR",
    "EINE",
    "EST",
    "ANAL",
    "DAESH",
    "ECIG",
    "EDS",
    "HINTAT",
    "IOT",
    "LOS",
    "MIS",
    "NIPPLES",
    "NSAIDS",
    "POR",
    "THO",
}

# High-frequency tokens that are not acceptable standalone crossword answers.
NOISY_TOKENS = {
    "AAA",
    "AAAA",
    "AAAAA",
    "BBB",
    "CCC",
    "DDD",
    "EEE",
    "FFF",
    "GGG",
    "HHH",
    "III",
    "IIII",
    "JJJ",
    "KKK",
    "LLL",
    "MMM",
    "NNN",
    "OOO",
    "PPP",
    "QQQ",
    "RRR",
    "SSS",
    "TTT",
    "UUU",
    "VVV",
    "WWW",
    "XXX",
    "YYY",
    "ZZZ",
}

NAME_WORD_ALLOWLIST = {
    "BAKER",
    "BANKS",
    "BELL",
    "BERRY",
    "BILL",
    "BLACK",
    "BROWN",
    "BUSH",
    "CAROL",
    "CARTER",
    "COLE",
    "COOK",
    "CROSS",
    "DALE",
    "DAWN",
    "DEAN",
    "EARL",
    "ECHO",
    "FAITH",
    "FAWN",
    "FIELDS",
    "FOX",
    "GLASS",
    "GRAY",
    "GRACE",
    "GREEN",
    "HALL",
    "HARRY",
    "HILL",
    "HOPE",
    "HUNTER",
    "IVY",
    "JAY",
    "JOY",
    "KING",
    "LAKE",
    "LANCE",
    "MARK",
    "MASON",
    "MAX",
    "MAY",
    "MILES",
    "NICK",
    "NORTH",
    "PARK",
    "PAT",
    "PENNY",
    "PETER",
    "PRICE",
    "RAY",
    "REED",
    "RICE",
    "RIVERS",
    "ROBIN",
    "ROSE",
    "RUBY",
    "SAGE",
    "SHARP",
    "SHORT",
    "SKIP",
    "SNOW",
    "SOUTH",
    "STAN",
    "STONE",
    "SWEET",
    "VICTOR",
    "WARD",
    "WEST",
    "WHITE",
    "WILL",
    "WOOD",
    "WRIGHT",
    "YOUNG",
}

COMMON_ONLY_BLOCKLIST = {
    "AMA",
    "AMORE",
    "BHT",
    "CAL",
    "CONF",
    "DKS",
    "EMS",
    "ESP",
    "ESPN",
    "GTA",
    "HAE",
    "HEO",
    "HLP",
    "IEEE",
    "IND",
    "IOS",
    "IRA",
    "ISPS",
    "MLS",
    "MRE",
    "MRT",
    "MANN",
    "NEB",
    "NHL",
    "NHS",
    "NSA",
    "OJS",
    "PSA",
    "RPM",
    "RSO",
    "SHRI",
    "SMS",
    "SNA",
    "SRI",
    "SSS",
    "TDS",
    "TSA",
    "TSP",
    "USAID",
    "WHA",
}

QUALITY_ALLOWLIST = {
    "ACHE",
    "BOG",
    "BURR",
    "EPIGRAM",
    "EWES",
    "INANE",
    "LARIATS",
    "PEWS",
    "RHINE",
    "SASHAYS",
    "WRIT",
}


def load_first_names() -> frozenset[str]:
    values: set[str] = set()
    for filename in ("dist.female.first", "dist.male.first"):
        try:
            lines = files("names").joinpath(filename).read_text().splitlines()
        except (FileNotFoundError, ModuleNotFoundError):
            continue
        values.update(line.split()[0].upper() for line in lines if line.split())
    return frozenset(values)


FIRST_NAMES = load_first_names()


def load_last_names() -> frozenset[str]:
    try:
        lines = files("names").joinpath("dist.all.last").read_text().splitlines()
    except (FileNotFoundError, ModuleNotFoundError):
        return frozenset()
    return frozenset(line.split()[0].upper() for line in lines if line.split())


LAST_NAMES = load_last_names()
PERSON_NAMES = FIRST_NAMES | LAST_NAMES


@dataclass(frozen=True)
class Slot:
    index: int
    direction: str
    row: int
    column: int
    cells: tuple[tuple[int, int], ...]

    @property
    def length(self) -> int:
        return len(self.cells)


def runs(line: str, target: str = ".") -> list[int]:
    return [len(match.group()) for match in re.finditer(re.escape(target) + "+", line)]


def valid_open_runs(line: str, max_length: int = 9) -> bool:
    lengths = runs(line)
    return bool(lengths) and all(3 <= length <= max_length for length in lengths)


def allowed_rows() -> list[str]:
    rows: list[str] = []
    for mask in range(1 << SIZE):
        line = "".join("#" if mask & (1 << column) else "." for column in range(SIZE))
        block_count = line.count("#")
        if not 2 <= block_count <= 6:
            continue
        if not valid_open_runs(line, max_length=8):
            continue
        if "#####" in line:
            continue
        rows.append(line)
    return rows


def rotate_row(row: str) -> str:
    return row[::-1]


def get_slots(grid: list[str]) -> list[Slot]:
    slots: list[Slot] = []
    for row in range(SIZE):
        column = 0
        while column < SIZE:
            if grid[row][column] == "#":
                column += 1
                continue
            start = column
            while column < SIZE and grid[row][column] != "#":
                column += 1
            cells = tuple((row, value) for value in range(start, column))
            slots.append(Slot(len(slots), "Across", row, start, cells))
    for column in range(SIZE):
        row = 0
        while row < SIZE:
            if grid[row][column] == "#":
                row += 1
                continue
            start = row
            while row < SIZE and grid[row][column] != "#":
                row += 1
            cells = tuple((value, column) for value in range(start, row))
            slots.append(Slot(len(slots), "Down", start, column, cells))
    return slots


def connected(grid: list[str]) -> bool:
    open_cells = {
        (row, column)
        for row in range(SIZE)
        for column in range(SIZE)
        if grid[row][column] != "#"
    }
    if not open_cells:
        return False
    seen = {next(iter(open_cells))}
    queue = deque(seen)
    while queue:
        row, column = queue.popleft()
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            neighbor = (row + dr, column + dc)
            if neighbor in open_cells and neighbor not in seen:
                seen.add(neighbor)
                queue.append(neighbor)
    return seen == open_cells


def pattern_score(grid: list[str]) -> tuple[int, int, int, int, int, int]:
    slots = get_slots(grid)
    lengths = Counter(slot.length for slot in slots)
    block_count = sum(row.count("#") for row in grid)
    non_theme_lengths = [
        slot.length
        for slot in slots
        if not (
            any(
                slot.direction == direction
                and slot.row == row
                and slot.column == column
                and slot.length == len(answer)
                for direction, row, column, answer in THEME_PLACEMENTS
            )
        )
    ]
    long_penalty = sum(max(0, length - 8) ** 2 for length in non_theme_lengths)
    cheaters = 0
    for row in range(SIZE):
        for column in range(SIZE):
            if grid[row][column] != "#":
                continue
            opposite = grid[SIZE - 1 - row][SIZE - 1 - column]
            if opposite != "#":
                cheaters += 1
    return (
        long_penalty,
        max(non_theme_lengths),
        lengths[3],
        abs(len(slots) - 70),
        abs(block_count - 36),
        cheaters,
    )


def vertical_masks(column: int, lexicon: "Lexicon") -> list[int]:
    masks: list[int] = []
    for mask in range(1 << SIZE):
        if any(
            bool(mask & (1 << row)) != should_block
            for row in range(SIZE)
            if (should_block := (
                True
                if (row, column) in FIXED_BLOCKS
                else False
                if (row, column) in FIXED_LETTERS
                or (row, column) in FIXED_OPEN
                else None
            ))
            is not None
        ):
            continue
        valid = True
        row = 0
        while row < SIZE:
            if mask & (1 << row):
                row += 1
                continue
            start = row
            while row < SIZE and not mask & (1 << row):
                row += 1
            if not 3 <= row - start <= 11:
                valid = False
                break
            pattern = "".join(
                FIXED_LETTERS.get((value, column), ".")
                for value in range(start, row)
            )
            if not lexicon.matching(pattern):
                valid = False
                break
        if valid:
            masks.append(mask)
    return masks


def generate_patterns(
    seed: int,
    attempts: int,
    limit: int,
    lexicon: "Lexicon",
    block_count: int,
    word_count: int,
    lexical_prefilter: bool = True,
    max_non_theme_length: int = 0,
) -> list[list[str]]:
    blocks = [
        [Bool(f"block_{row}_{column}") for column in range(SIZE)]
        for row in range(SIZE)
    ]
    solver = Solver()
    solver.set("random_seed", seed)
    solver.set("timeout", 10_000)

    # Standard 180-degree rotational symmetry.
    for row in range(SIZE):
        for column in range(SIZE):
            solver.add(
                blocks[row][column]
                == blocks[SIZE - 1 - row][SIZE - 1 - column]
            )

    # Lock the theme cells, side entries, and required boundary blocks.
    for row, column in FIXED_LETTERS.keys() | FIXED_OPEN:
        solver.add(blocks[row][column] == BoolVal(False))
    for row, column in FIXED_BLOCKS:
        solver.add(blocks[row][column] == BoolVal(True))

    if max_non_theme_length:
        theme_cell_sets: list[set[tuple[int, int]]] = []
        for direction, row, column, answer in THEME_PLACEMENTS:
            dr, dc = (0, 1) if direction == "Across" else (1, 0)
            theme_cell_sets.append(
                {
                    (row + dr * offset, column + dc * offset)
                    for offset in range(len(answer))
                }
            )
        window_size = max_non_theme_length + 1
        for row in range(SIZE):
            for start in range(SIZE - window_size + 1):
                cells = {(row, column) for column in range(start, start + window_size)}
                if not any(cells <= theme_cells for theme_cells in theme_cell_sets):
                    solver.add(Or(*[blocks[r][c] for r, c in cells]))
        for column in range(SIZE):
            for start in range(SIZE - window_size + 1):
                cells = {(row, column) for row in range(start, start + window_size)}
                if not any(cells <= theme_cells for theme_cells in theme_cell_sets):
                    solver.add(Or(*[blocks[r][c] for r, c in cells]))

    if lexical_prefilter:
        # Every possible vertical entry containing fixed theme letters must
        # have at least one candidate in the constructor lexicon.
        for column in range(SIZE):
            masks = vertical_masks(column, lexicon)
            if not masks:
                return []
            solver.add(
                Or(
                    *[
                        And(
                            *[
                                blocks[row][column]
                                == BoolVal(bool(mask & (1 << row)))
                                for row in range(SIZE)
                            ]
                        )
                        for mask in masks
                    ]
                )
            )

    # Every open cell must be part of at least three consecutive open cells
    # both Across and Down. This rules out one- and two-letter entries.
    for row in range(SIZE):
        for column in range(SIZE):
            horizontal_windows = []
            vertical_windows = []
            for start in range(column - 2, column + 1):
                if 0 <= start and start + 2 < SIZE:
                    horizontal_windows.append(
                        And(
                            *[
                                Not(blocks[row][value])
                                for value in range(start, start + 3)
                            ]
                        )
                    )
            for start in range(row - 2, row + 1):
                if 0 <= start and start + 2 < SIZE:
                    vertical_windows.append(
                        And(
                            *[
                                Not(blocks[value][column])
                                for value in range(start, start + 3)
                            ]
                        )
                    )
            solver.add(
                Or(blocks[row][column], Or(*horizontal_windows))
            )
            solver.add(
                Or(blocks[row][column], Or(*vertical_windows))
            )

    if block_count:
        solver.add(
            PbEq(
                [
                    (blocks[row][column], 1)
                    for row in range(SIZE)
                    for column in range(SIZE)
                ],
                block_count,
            )
        )

    starts = []
    for row in range(SIZE):
        for column in range(SIZE):
            across_start = Bool(f"across_start_{row}_{column}")
            down_start = Bool(f"down_start_{row}_{column}")
            solver.add(
                across_start
                == And(
                    Not(blocks[row][column]),
                    BoolVal(column == 0)
                    if column == 0
                    else blocks[row][column - 1],
                )
            )
            solver.add(
                down_start
                == And(
                    Not(blocks[row][column]),
                    BoolVal(row == 0) if row == 0 else blocks[row - 1][column],
                )
            )
            starts.extend((across_start, down_start))
    if word_count:
        solver.add(PbEq([(start, 1) for start in starts], word_count))

    patterns: dict[
        tuple[str, ...],
        tuple[tuple[int, int, int, int, int, int], list[str]],
    ] = {}
    for _ in range(min(attempts, 20_000)):
        if solver.check() != sat:
            break
        model = solver.model()
        grid = [
            "".join(
                "#" if is_true(model.eval(blocks[row][column])) else "."
                for column in range(SIZE)
            )
            for row in range(SIZE)
        ]
        key = tuple(grid)
        solver.add(
            Or(
                *[
                    blocks[row][column]
                    != BoolVal(grid[row][column] == "#")
                    for row in range(SIZE)
                    for column in range(SIZE)
                ]
            )
        )
        slots = get_slots(grid)
        if not connected(grid):
            continue
        if sum(slot.length == 3 for slot in slots) > 30:
            continue
        patterns[key] = (pattern_score(grid), grid)
        if len(patterns) >= max(limit * 10, 100):
            break

    ranked = sorted(patterns.values(), key=lambda pair: pair[0])
    return [grid for _, grid in ranked[:limit]]


class Lexicon:
    def __init__(
        self,
        limit: int = 300_000,
        constructor_min_score: int = 25,
        common_only: bool = False,
    ) -> None:
        words: set[str] = set(EXTRA_WORDS) - BLOCKLIST - NOISY_TOKENS
        if common_only:
            words -= COMMON_ONLY_BLOCKLIST
        words |= THEME_ANSWERS
        constructor_scores: dict[str, float] = {}

        cache_path = Path(".cache/xwordlist.dict")
        if not cache_path.exists():
            cache_path.parent.mkdir(exist_ok=True)
            print(f"Downloading MIT-licensed constructor list from {WORDLIST_URL}")
            with urllib.request.urlopen(WORDLIST_URL, timeout=30) as response:
                cache_path.write_bytes(response.read())
        for line in cache_path.read_text(errors="ignore").splitlines():
            try:
                raw_word, raw_score = line.rsplit(";", 1)
                score = int(raw_score)
            except ValueError:
                continue
            word = raw_word.strip().upper()
            if (
                score < constructor_min_score
                or not word.isalpha()
                or not 3 <= len(word) <= SIZE
            ):
                continue
            if word in BLOCKLIST or word in NOISY_TOKENS:
                continue
            if common_only:
                if word in COMMON_ONLY_BLOCKLIST:
                    continue
                if (
                    word not in NAME_WORD_ALLOWLIST
                    and word not in QUALITY_ALLOWLIST
                    and (
                        word in FIRST_NAMES
                        or (
                            word in LAST_NAMES
                            and zipf_frequency(word.lower(), "en") < 3.5
                        )
                    )
                ):
                    continue
                if (
                    len(word) <= 4
                    and not set(word) & set("AEIOU")
                    and word not in {"CRY", "DRY", "FLY", "GYM", "MY", "PLY", "PRY", "SHY", "SKY", "SLY", "SPY", "STY", "THY", "TRY", "WHY", "WRY"}
                ):
                    continue
            corpus_score = zipf_frequency(word.lower(), "en")
            common_floor = {
                3: 3.5,
                4: 3.0,
                5: 2.8,
                6: 2.6,
                7: 2.4,
                8: 2.3,
            }.get(len(word), 0.0)
            if (
                common_only
                and word not in EXTRA_WORDS
                and word not in THEME_ANSWERS
                and word not in QUALITY_ALLOWLIST
                and corpus_score < common_floor
            ):
                continue
            short_minimum = {3: 3.45, 4: 3.2, 5: 3.0}.get(len(word))
            short_score_fallback = {3: 70, 4: 65, 5: 60}.get(len(word))
            if (
                short_minimum is not None
                and word not in EXTRA_WORDS
                and corpus_score < short_minimum
                and score < short_score_fallback
            ):
                continue
            words.add(word)
            constructor_scores[word] = max(
                constructor_scores.get(word, 0.0),
                score / 20,
            )

        for token in top_n_list("en", limit, ascii_only=True) if limit else ():
            word = token.upper()
            if not word.isalpha() or not 3 <= len(word) <= SIZE:
                continue
            if word in BLOCKLIST or word in NOISY_TOKENS:
                continue
            if common_only:
                if word in COMMON_ONLY_BLOCKLIST:
                    continue
                if (
                    word not in NAME_WORD_ALLOWLIST
                    and word not in QUALITY_ALLOWLIST
                    and (
                        word in FIRST_NAMES
                        or (
                            word in LAST_NAMES
                            and zipf_frequency(word.lower(), "en") < 3.5
                        )
                    )
                ):
                    continue
                if (
                    len(word) <= 4
                    and not set(word) & set("AEIOU")
                    and word not in {"CRY", "DRY", "FLY", "GYM", "MY", "PLY", "PRY", "SHY", "SKY", "SLY", "SPY", "STY", "THY", "TRY", "WHY", "WRY"}
                ):
                    continue
            if re.search(r"(.)\1\1", word):
                continue
            if common_only:
                minimum = {
                    3: 3.5,
                    4: 3.0,
                    5: 2.8,
                    6: 2.6,
                    7: 2.4,
                    8: 2.3,
                }.get(len(word), 2.3)
            else:
                minimum = 3.45 if len(word) == 3 else 3.0 if len(word) == 4 else 2.6
            if (
                word not in QUALITY_ALLOWLIST
                and zipf_frequency(token, "en") < minimum
            ):
                continue
            words.add(word)

        self.by_length: dict[int, tuple[str, ...]] = {}
        self.scores: dict[str, float] = {}
        self.index: dict[tuple[int, int, str], frozenset[str]] = {}

        grouped: dict[int, list[str]] = defaultdict(list)
        for word in words:
            grouped[len(word)].append(word)
            corpus_score = zipf_frequency(word.lower(), "en")
            constructor_score = constructor_scores.get(word, 0.0)
            score = (
                max(corpus_score, min(constructor_score, corpus_score + 0.75))
                if common_only
                else max(corpus_score, constructor_score)
            )
            if word in EXTRA_WORDS:
                score = max(score, 3.3)
            if word in THEME_ANSWERS:
                score = 9.0
            self.scores[word] = score

        mutable_index: dict[tuple[int, int, str], set[str]] = defaultdict(set)
        for length, values in grouped.items():
            values.sort(key=lambda word: (-self.scores[word], word))
            self.by_length[length] = tuple(values)
            for word in values:
                for position, letter in enumerate(word):
                    mutable_index[(length, position, letter)].add(word)
        self.index = {
            key: frozenset(values) for key, values in mutable_index.items()
        }

    @lru_cache(maxsize=100_000)
    def matching(self, pattern: str) -> tuple[str, ...]:
        constrained = [
            (position, letter)
            for position, letter in enumerate(pattern)
            if letter != "."
        ]
        if not constrained:
            return self.by_length.get(len(pattern), ())
        sets = [
            self.index.get((len(pattern), position, letter), frozenset())
            for position, letter in constrained
        ]
        if not sets:
            return ()
        matches = set(min(sets, key=len))
        for values in sets:
            matches.intersection_update(values)
            if not matches:
                return ()
        return tuple(
            sorted(
                matches,
                key=lambda word: (-self.scores[word], word),
            )
        )


class FillSolver:
    def __init__(
        self,
        grid: list[str],
        lexicon: Lexicon,
        seed: int,
        node_limit: int,
        timeout: float,
    ) -> None:
        self.grid = grid
        self.lexicon = lexicon
        self.rng = random.Random(seed)
        self.node_limit = node_limit
        self.deadline = time.monotonic() + timeout
        self.nodes = 0
        self.slots = get_slots(grid)
        self.letters: list[list[str]] = [
            ["#" if cell == "#" else "." for cell in row] for row in grid
        ]
        for (row, column), letter in FIXED_LETTERS.items():
            self.letters[row][column] = letter

        self.cell_slots: dict[tuple[int, int], list[int]] = defaultdict(list)
        for slot in self.slots:
            for cell in slot.cells:
                self.cell_slots[cell].append(slot.index)
        self.neighbors: dict[int, set[int]] = defaultdict(set)
        for indices in self.cell_slots.values():
            for index in indices:
                self.neighbors[index].update(value for value in indices if value != index)

        self.assigned: dict[int, str] = {}
        self.used: set[str] = set()
        self.best_depth = 0

    def pattern(self, slot: Slot) -> str:
        return "".join(self.letters[row][column] for row, column in slot.cells)

    def candidates(self, slot: Slot) -> list[str]:
        pattern = self.pattern(slot)
        if "." not in pattern:
            if pattern in self.used or pattern not in self.lexicon.scores:
                return []
            return [pattern]
        return [
            word
            for word in self.lexicon.matching(pattern)
            if word not in self.used
        ]

    def choose_slot(self) -> tuple[Slot | None, list[str]]:
        best_slot: Slot | None = None
        best_candidates: list[str] = []
        best_key: tuple[int, int, int] | None = None
        for slot in self.slots:
            if slot.index in self.assigned:
                continue
            candidates = self.candidates(slot)
            if not candidates:
                return slot, []
            open_crossings = sum(
                neighbor not in self.assigned for neighbor in self.neighbors[slot.index]
            )
            key = (len(candidates), -open_crossings, -slot.length)
            if best_key is None or key < best_key:
                best_key = key
                best_slot = slot
                best_candidates = candidates
        return best_slot, best_candidates

    def order_candidates(self, slot: Slot, candidates: list[str]) -> list[str]:
        # Limit very broad early choices to strong vocabulary. Random jitter
        # gives different seeds meaningfully different fills.
        if len(candidates) > 800:
            candidates = candidates[:800]

        scored: list[tuple[float, str]] = []
        for word in candidates:
            score = self.lexicon.scores.get(word, 0.0) * 5
            score += len(set(word)) * 0.08
            score += self.rng.random() * 1.2
            # Prefer letters that leave many options at unfilled crossings.
            for position, cell in enumerate(slot.cells):
                for neighbor_index in self.cell_slots[cell]:
                    if neighbor_index == slot.index or neighbor_index in self.assigned:
                        continue
                    neighbor = self.slots[neighbor_index]
                    neighbor_position = neighbor.cells.index(cell)
                    options = self.lexicon.index.get(
                        (neighbor.length, neighbor_position, word[position]),
                        frozenset(),
                    )
                    score += min(len(options), 500) / 500
            scored.append((score, word))
        scored.sort(reverse=True)
        return [word for _, word in scored]

    def place(self, slot: Slot, word: str) -> list[tuple[int, int]]:
        changed: list[tuple[int, int]] = []
        for (row, column), letter in zip(slot.cells, word, strict=True):
            if self.letters[row][column] == ".":
                self.letters[row][column] = letter
                changed.append((row, column))
            elif self.letters[row][column] != letter:
                raise AssertionError("Conflicting placement")
        self.assigned[slot.index] = word
        self.used.add(word)
        return changed

    def remove(self, slot: Slot, word: str, changed: list[tuple[int, int]]) -> None:
        del self.assigned[slot.index]
        self.used.remove(word)
        for row, column in changed:
            if any(
                index in self.assigned
                for index in self.cell_slots[(row, column)]
            ):
                continue
            if (row, column) in FIXED_LETTERS:
                continue
            self.letters[row][column] = "."

    def forward_valid(self, slot: Slot) -> bool:
        for neighbor_index in self.neighbors[slot.index]:
            if neighbor_index in self.assigned:
                continue
            if not self.candidates(self.slots[neighbor_index]):
                return False
        return True

    def search(self) -> bool:
        if self.nodes >= self.node_limit or time.monotonic() >= self.deadline:
            return False
        self.nodes += 1
        self.best_depth = max(self.best_depth, len(self.assigned))
        if len(self.assigned) == len(self.slots):
            return True

        slot, candidates = self.choose_slot()
        if slot is None:
            return True
        if not candidates:
            return False

        for word in self.order_candidates(slot, candidates):
            changed = self.place(slot, word)
            if self.forward_valid(slot) and self.search():
                return True
            self.remove(slot, word, changed)
            if self.nodes >= self.node_limit or time.monotonic() >= self.deadline:
                return False
        return False

    def solution_rows(self) -> list[str]:
        return ["".join(row) for row in self.letters]


def fixed_letter_patterns(grid: list[str]) -> list[tuple[Slot, str]]:
    letters: list[list[str]] = [
        ["#" if cell == "#" else "." for cell in row] for row in grid
    ]
    for (row, column), letter in FIXED_LETTERS.items():
        letters[row][column] = letter
    return [
        (
            slot,
            "".join(letters[row][column] for row, column in slot.cells),
        )
        for slot in get_slots(grid)
    ]


def lexical_pattern_score(
    grid: list[str],
    lexicon: Lexicon,
) -> tuple[int, float, int, tuple[int, int, int, int, int, int]]:
    zeroes = 0
    scarcity = 0.0
    constrained_slots = 0
    for slot, pattern in fixed_letter_patterns(grid):
        if "." not in pattern or set(pattern) == {"."}:
            continue
        constrained_slots += 1
        count = len(lexicon.matching(pattern))
        if count == 0:
            zeroes += 1
        scarcity += 1 / max(count, 1)
    return zeroes, scarcity, -constrained_slots, pattern_score(grid)


def candidate_payload(grid: list[str], solver: FillSolver) -> dict[str, object]:
    rows = solver.solution_rows()
    entries = []
    for slot in solver.slots:
        answer = "".join(rows[row][column] for row, column in slot.cells)
        entries.append(
            {
                "direction": slot.direction,
                "row": slot.row + 1,
                "column": slot.column + 1,
                "answer": answer,
            }
        )
    return {
        "grid": rows,
        "word_count": len(solver.slots),
        "block_count": sum(row.count("#") for row in grid),
        "nodes": solver.nodes,
        "entries": entries,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        required=True,
        help="Path to a construction.json file with one-based coordinates",
    )
    parser.add_argument("--output", default="scratch")
    parser.add_argument("--seed", type=int, default=625)
    parser.add_argument("--pattern-attempts", type=int, default=5_000)
    parser.add_argument("--patterns", type=int, default=250)
    parser.add_argument("--blocks", type=int, default=40)
    parser.add_argument("--words", type=int, default=72)
    parser.add_argument("--max-nontheme-length", type=int, default=0)
    parser.add_argument("--skip-topology-lexicon", action="store_true")
    parser.add_argument("--node-limit", type=int, default=300_000)
    parser.add_argument("--seconds", type=float, default=8.0)
    parser.add_argument("--wordfreq-limit", type=int, default=300_000)
    parser.add_argument("--constructor-min-score", type=int, default=25)
    parser.add_argument("--common-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    configure(load_construction_spec(Path(args.config)))
    print("Loading ranked English lexicon ...")
    lexicon = Lexicon(
        limit=args.wordfreq_limit,
        constructor_min_score=args.constructor_min_score,
        common_only=args.common_only,
    )
    print(
        "Lexicon sizes:",
        " ".join(
            f"{length}:{len(words)}"
            for length, words in sorted(lexicon.by_length.items())
        ),
    )
    patterns = generate_patterns(
        args.seed,
        args.pattern_attempts,
        args.patterns,
        lexicon,
        args.blocks,
        args.words,
        not args.skip_topology_lexicon,
        args.max_nontheme_length,
    )
    print(f"Generated {len(patterns)} candidate patterns")
    if not patterns:
        raise SystemExit(1)

    if args.dry_run:
        for index, grid in enumerate(patterns[:10], start=1):
            print(
                f"\nPattern {index}: score={pattern_score(grid)} "
                f"words={len(get_slots(grid))} "
                f"blocks={sum(row.count('#') for row in grid)}"
            )
            print("\n".join(grid))
        return

    patterns.sort(key=lambda grid: lexical_pattern_score(grid, lexicon))

    scratch = Path(args.output)
    scratch.mkdir(exist_ok=True)
    for index, grid in enumerate(patterns, start=1):
        lexical_score = lexical_pattern_score(grid, lexicon)
        if lexical_score[0]:
            print(
                f"Pattern {index}/{len(patterns)}: skipped "
                f"({lexical_score[0]} fixed-letter slots have no candidates)"
            )
            continue
        solver = FillSolver(
            grid,
            lexicon,
            seed=args.seed + index * 997,
            node_limit=args.node_limit,
            timeout=args.seconds,
        )
        solved = solver.search()
        print(
            f"Pattern {index}/{len(patterns)}: solved={solved} "
            f"depth={solver.best_depth}/{len(solver.slots)} nodes={solver.nodes}"
        )
        if not solved:
            continue
        payload = candidate_payload(grid, solver)
        output = scratch / f"candidate-{args.seed}-{index}.json"
        output.write_text(json.dumps(payload, indent=2) + "\n")
        print("\n".join(payload["grid"]))
        print(f"Wrote {output}")
        return

    raise SystemExit("No fill found")


if __name__ == "__main__":
    main()
