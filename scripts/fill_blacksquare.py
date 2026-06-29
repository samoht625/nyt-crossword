#!/usr/bin/env python3
"""Try project grid patterns with Blacksquare's professional fill engine."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from blacksquare import DEFAULT_WORDLIST, Crossword, WordList

try:
    from . import construct
except ImportError:  # Support direct execution from the repository root.
    import construct


def seeded_grid(pattern: list[str]) -> list[list[str]]:
    grid = [
        ["#" if value == "#" else "?" for value in row]
        for row in pattern
    ]
    for (row, column), letter in construct.FIXED_LETTERS.items():
        grid[row][column] = letter
    return grid


def solution_rows(crossword: Crossword) -> list[str]:
    return [
        "".join(crossword[row, column].str for column in range(crossword.num_cols))
        .replace("█", "#")
        for row in range(crossword.num_rows)
    ]


def payload(crossword: Crossword, pattern: list[str], attempt: int) -> dict:
    entries = [
        {
            "direction": word.direction.value,
            "number": int(word.number),
            "answer": word.value,
        }
        for word in crossword.iterwords()
    ]
    return {
        "grid": solution_rows(crossword),
        "word_count": len(entries),
        "block_count": sum(row.count("#") for row in pattern),
        "attempt": attempt,
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
    parser.add_argument("--seed", type=int, default=701)
    parser.add_argument("--patterns", type=int, default=250)
    parser.add_argument("--pattern-json")
    parser.add_argument("--pattern-attempts", type=int, default=2_500)
    parser.add_argument("--blocks", type=int, default=44)
    parser.add_argument("--words", type=int, default=68)
    parser.add_argument("--max-nontheme-length", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--score-filter", type=float, default=0.9)
    parser.add_argument("--constructor-min-score", type=int, default=80)
    parser.add_argument("--common-only", action="store_true")
    parser.add_argument("--wordfreq-limit", type=int, default=100_000)
    parser.add_argument("--allow-word", action="append", default=[])
    parser.add_argument(
        "--word-list",
        choices=("spread", "hybrid", "curated"),
        default="spread",
    )
    args = parser.parse_args()

    construct.configure(
        construct.load_construction_spec(Path(args.config))
    )
    print("Loading topology lexicon ...", flush=True)
    topology_lexicon = construct.Lexicon(
        limit=args.wordfreq_limit,
        constructor_min_score=args.constructor_min_score,
        common_only=args.common_only,
    )
    if args.pattern_json:
        source = json.loads(Path(args.pattern_json).read_text())
        patterns = [
            [
                "".join("#" if value == "#" else "." for value in row)
                for row in source["grid"]
            ]
        ]
    else:
        patterns = construct.generate_patterns(
            args.seed,
            args.pattern_attempts,
            args.patterns,
            topology_lexicon,
            args.blocks,
            args.words,
            True,
            args.max_nontheme_length,
        )
    print(f"Generated {len(patterns)} patterns", flush=True)
    if args.word_list == "curated":
        fill_words = {
            word: topology_lexicon.scores[word]
            for words in topology_lexicon.by_length.values()
            for word in words
        }
        fill_score_filter = None
    else:
        allowed = set(topology_lexicon.scores)
        fill_words = {
            word: score
            for word, score in zip(
                DEFAULT_WORDLIST.words,
                DEFAULT_WORDLIST.scores,
                strict=True,
            )
            if args.word_list == "spread"
            or word in allowed
            or score >= 0.8
        }
        fill_score_filter = args.score_filter
    fill_words.update(
        {answer: 1.0 for answer in construct.THEME_ANSWERS}
    )
    fill_words.update(
        {word.upper(): 1.0 for word in args.allow_word}
    )
    fill_word_list = WordList(fill_words)

    rng = random.Random(args.seed)
    for index, pattern in enumerate(patterns, start=1):
        crossword = Crossword(
            grid=seeded_grid(pattern),
            symmetry=None,
            word_list=fill_word_list,
        )
        filled = crossword.fill(
            timeout=args.timeout,
            temperature=args.temperature + rng.random() * 0.25,
            score_filter=fill_score_filter,
            allow_repeats=False,
        )
        print(f"Pattern {index}/{len(patterns)}: solved={filled is not None}", flush=True)
        if filled is None:
            continue
        result = payload(filled, pattern, index)
        scratch = Path(args.output)
        scratch.mkdir(exist_ok=True)
        output = scratch / f"blacksquare-{args.seed}-{index}.json"
        output.write_text(json.dumps(result, indent=2) + "\n")
        print("\n".join(result["grid"]))
        print(f"Wrote {output}")
        return
    raise SystemExit("No Blacksquare fill found")


if __name__ == "__main__":
    main()
