# Tido Crosswords

Reusable tools for constructing, validating, and exporting American-style
crosswords, plus a static site for puzzles by Thomas Carriero.

The repository currently includes two 15×15 puzzles:

- **Autocomplete** — reconstructed from the constructor's original solver PDF
- **AI Generated** — familiar expressions edited to literally generate `AI`

## Quick start

Install [uv](https://docs.astral.sh/uv/), then:

```sh
uv sync --extra dev
uv run pytest
uv run crossword-validate puzzles/ai-generated/puzzle.json
uv run crossword-export puzzles/ai-generated/puzzle.json \
  --output /tmp/ai-generated
```

Preview the portfolio and browser solver:

```sh
python3 -m http.server 8000 --directory web
```

Open http://localhost:8000. The site can solve either bundled puzzle or any
standard Across Lite `.puz` selected from the device. Solving happens entirely
in the browser, and progress is stored locally.

## Repository layout

```text
puzzles/                 Canonical grids, clues, and construction specs
scripts/                 Tool implementations and compatibility entry points
src/crossword_tools/     Installable Python API and CLI package
tests/                   Validation, export, configuration, and site checks
web/                     Self-contained static portfolio and puzzle player
docs/                    Formats, architecture, and construction workflow
```

Canonical `puzzle.json` files are the source of truth. Files in
`web/puzzles/` are generated `.puz` artifacts committed only so the static site
works without a build service. Other exports and scratch candidates are
ignored.

## Construction tools

Install the construction dependencies:

```sh
uv sync --extra dev --extra construction
```

Generate patterns and try the built-in fill engine:

```sh
uv run crossword-construct \
  --config puzzles/ai-generated/construction.json \
  --output scratch

uv run crossword-fill \
  --config puzzles/ai-generated/construction.json \
  --output scratch
```

The optional Blacksquare adapter is available with `uv sync --all-extras` and
the `crossword-fill-blacksquare` command. Construction downloads the
MIT-licensed [Crossword Nexus collaborative word
list](https://github.com/Crossword-Nexus/collaborative-word-list) into
`.cache/` on first use.

## Add a puzzle

1. Create `puzzles/<slug>/puzzle.json` using `docs/puzzle-format.md`.
2. Add `construction.json` if the pattern/fill tools should lock theme entries.
3. Run `uv run crossword-validate puzzles/<slug>/puzzle.json`.
4. Generate the site asset:
   `uv run crossword-export puzzles/<slug>/puzzle.json --output web/puzzles --format puz`.
5. Add the puzzle to `web/puzzles.json`.
6. Run `uv run pytest` and preview the site over HTTP.

Never place contact details, submission forms, constructor profiles, or
unreviewed scratch fills in the repository. See `docs/architecture.md` for the
canonical/generated boundary.

## License

The software is available under the [MIT License](LICENSE). Puzzle grids,
clues, themes, and puzzle-specific notes are copyright Thomas Carriero and are
not covered by the software license; see [puzzles/LICENSE.md](puzzles/LICENSE.md).
