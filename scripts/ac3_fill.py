#!/usr/bin/env python3
"""Fill candidate grids with AC-3 propagation and MRV backtracking."""

from __future__ import annotations

import argparse
import json
import random
import time
from collections import defaultdict, deque
from pathlib import Path

try:
    from . import construct
except ImportError:  # Support direct execution from the repository root.
    import construct


class AC3Solver:
    def __init__(
        self,
        pattern: list[str],
        lexicon: construct.Lexicon,
        *,
        seed: int,
        timeout: float,
        node_limit: int,
        good_words: set[str] | None = None,
        marginal_budget: int | None = None,
    ) -> None:
        self.pattern = pattern
        self.lexicon = lexicon
        self.rng = random.Random(seed)
        self.deadline = time.monotonic() + timeout
        self.node_limit = node_limit
        self.good_words = good_words
        self.marginal_budget = marginal_budget
        self.nodes = 0
        self.best_depth = 0
        self.slots = construct.get_slots(pattern)
        self.crossings: dict[tuple[int, int], tuple[int, int]] = {}
        self.neighbors: dict[int, set[int]] = defaultdict(set)

        cell_slots: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
        for slot in self.slots:
            for position, cell in enumerate(slot.cells):
                cell_slots[cell].append((slot.index, position))
        for values in cell_slots.values():
            if len(values) != 2:
                raise ValueError("Every open cell must belong to two entries")
            (first, first_position), (second, second_position) = values
            self.crossings[first, second] = first_position, second_position
            self.crossings[second, first] = second_position, first_position
            self.neighbors[first].add(second)
            self.neighbors[second].add(first)

        self.domains: list[set[str]] = []
        for slot in self.slots:
            fixed_pattern = "".join(
                construct.FIXED_LETTERS.get(cell, ".") for cell in slot.cells
            )
            domain = set(lexicon.matching(fixed_pattern))
            if not domain:
                raise ValueError(
                    f"No candidates for {slot.direction} at "
                    f"{slot.row + 1},{slot.column + 1}: {fixed_pattern}"
                )
            self.domains.append(domain)

    def revise(
        self,
        domains: list[set[str]],
        first: int,
        second: int,
    ) -> bool:
        first_position, second_position = self.crossings[first, second]
        allowed_letters = {
            word[second_position] for word in domains[second]
        }
        revised = {
            word
            for word in domains[first]
            if word[first_position] in allowed_letters
        }
        if revised == domains[first]:
            return False
        domains[first] = revised
        return True

    def propagate(self, domains: list[set[str]]) -> bool:
        queue = deque(self.crossings)
        while True:
            while queue:
                first, second = queue.popleft()
                if not self.revise(domains, first, second):
                    continue
                if not domains[first]:
                    return False
                queue.extend(
                    (neighbor, first)
                    for neighbor in self.neighbors[first]
                    if neighbor != second
                )

            singletons: dict[tuple[int, str], int] = {}
            changed: set[int] = set()
            for index, domain in enumerate(domains):
                if len(domain) != 1:
                    continue
                word = next(iter(domain))
                key = len(word), word
                if key in singletons:
                    return False
                singletons[key] = index
            for index, domain in enumerate(domains):
                if len(domain) == 1:
                    continue
                taken = {
                    word
                    for (length, word), _ in singletons.items()
                    if length == self.slots[index].length
                }
                revised = domain - taken
                if not revised:
                    return False
                if revised != domain:
                    domains[index] = revised
                    changed.add(index)
            if not changed:
                return True
            for index in changed:
                queue.extend(
                    (neighbor, index) for neighbor in self.neighbors[index]
                )

    def choose_slot(self, domains: list[set[str]]) -> int:
        return min(
            (index for index, domain in enumerate(domains) if len(domain) > 1),
            key=lambda index: (
                sum(word in self.good_words for word in domains[index])
                if self.good_words is not None
                else 0,
                len(domains[index]),
                -len(self.neighbors[index]),
                -self.slots[index].length,
            ),
        )

    def ordered_values(self, index: int, domains: list[set[str]]) -> list[str]:
        values: list[tuple[float, str]] = []
        slot = self.slots[index]
        for word in domains[index]:
            support = 0.0
            for neighbor in self.neighbors[index]:
                position, neighbor_position = self.crossings[index, neighbor]
                support += sum(
                    candidate[neighbor_position] == word[position]
                    for candidate in domains[neighbor]
                )
            score = self.lexicon.scores.get(word, 0.0) * 100 + support
            if self.good_words is not None and word in self.good_words:
                score += 1_000_000
            score += self.rng.random()
            values.append((score, word))
        values.sort(reverse=True)
        return [word for _, word in values]

    def search(self, domains: list[set[str]]) -> list[set[str]] | None:
        if self.nodes >= self.node_limit or time.monotonic() >= self.deadline:
            return None
        self.nodes += 1
        if (
            self.good_words is not None
            and self.marginal_budget is not None
            and sum(not (domain & self.good_words) for domain in domains)
            > self.marginal_budget
        ):
            return None
        solved_count = sum(len(domain) == 1 for domain in domains)
        self.best_depth = max(self.best_depth, solved_count)
        if solved_count == len(domains):
            return domains

        index = self.choose_slot(domains)
        for word in self.ordered_values(index, domains):
            next_domains = [set(domain) for domain in domains]
            next_domains[index] = {word}
            if self.propagate(next_domains):
                if (
                    self.good_words is not None
                    and self.marginal_budget is not None
                    and sum(
                        not (domain & self.good_words)
                        for domain in next_domains
                    )
                    > self.marginal_budget
                ):
                    continue
                result = self.search(next_domains)
                if result is not None:
                    return result
            if self.nodes >= self.node_limit or time.monotonic() >= self.deadline:
                return None
        return None

    def solve(self) -> list[str] | None:
        domains = [set(domain) for domain in self.domains]
        if not self.propagate(domains):
            return None
        if (
            self.good_words is not None
            and self.marginal_budget is not None
            and sum(not (domain & self.good_words) for domain in domains)
            > self.marginal_budget
        ):
            return None
        result = self.search(domains)
        if result is None:
            return None
        words = [next(iter(domain)) for domain in result]
        grid = [
            ["#" if value == "#" else "." for value in row]
            for row in self.pattern
        ]
        for slot, word in zip(self.slots, words, strict=True):
            for (row, column), letter in zip(slot.cells, word, strict=True):
                if grid[row][column] not in (".", letter):
                    raise ValueError("Conflicting solved letters")
                grid[row][column] = letter
        return ["".join(row) for row in grid]


def payload(
    rows: list[str],
    pattern: list[str],
    solver: AC3Solver,
) -> dict[str, object]:
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
        "word_count": len(entries),
        "block_count": sum(row.count("#") for row in pattern),
        "nodes": solver.nodes,
        "marginal_entries": [
            entry["answer"]
            for entry in entries
            if solver.good_words is not None
            and entry["answer"] not in solver.good_words
        ],
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
    parser.add_argument("--seed", type=int, default=839)
    parser.add_argument("--patterns", type=int, default=300)
    parser.add_argument("--start-pattern", type=int, default=1)
    parser.add_argument("--pattern-json")
    parser.add_argument("--pattern-attempts", type=int, default=4_000)
    parser.add_argument("--blocks", type=int, default=42)
    parser.add_argument("--words", type=int, default=76)
    parser.add_argument("--max-nontheme-length", type=int, default=8)
    parser.add_argument("--seconds", type=float, default=20)
    parser.add_argument("--node-limit", type=int, default=500_000)
    parser.add_argument("--wordfreq-limit", type=int, default=120_000)
    parser.add_argument("--constructor-min-score", type=int, default=75)
    parser.add_argument("--common-only", action="store_true")
    parser.add_argument("--marginal-budget", type=int)
    args = parser.parse_args()

    construct.configure(
        construct.load_construction_spec(Path(args.config))
    )
    quality_lexicon = construct.Lexicon(
        limit=args.wordfreq_limit,
        constructor_min_score=args.constructor_min_score,
        common_only=True,
    )
    if args.marginal_budget is None:
        lexicon = (
            quality_lexicon
            if args.common_only
            else construct.Lexicon(
                limit=args.wordfreq_limit,
                constructor_min_score=args.constructor_min_score,
                common_only=False,
            )
        )
        good_words = None
    else:
        lexicon = construct.Lexicon(
            limit=args.wordfreq_limit,
            constructor_min_score=args.constructor_min_score,
            common_only=False,
        )
        good_words = set(quality_lexicon.scores)
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
            quality_lexicon,
            args.blocks,
            args.words,
            True,
            args.max_nontheme_length,
        )
    print(f"Generated {len(patterns)} patterns", flush=True)
    scratch = Path(args.output)
    scratch.mkdir(exist_ok=True)

    for index, pattern in enumerate(patterns, start=1):
        if index < args.start_pattern:
            continue
        try:
            solver = AC3Solver(
                pattern,
                lexicon,
                seed=args.seed + index * 997,
                timeout=args.seconds,
                node_limit=args.node_limit,
                good_words=good_words,
                marginal_budget=args.marginal_budget,
            )
            rows = solver.solve()
        except ValueError as error:
            print(f"Pattern {index}: invalid ({error})", flush=True)
            continue
        print(
            f"Pattern {index}/{len(patterns)}: solved={rows is not None} "
            f"depth={solver.best_depth}/{len(solver.slots)} nodes={solver.nodes}",
            flush=True,
        )
        if rows is None:
            continue
        result = payload(rows, pattern, solver)
        output = scratch / f"ac3-{args.seed}-{index}.json"
        output.write_text(json.dumps(result, indent=2) + "\n")
        print("\n".join(rows))
        print(f"Wrote {output}")
        return
    raise SystemExit("No AC-3 fill found")


if __name__ == "__main__":
    main()
