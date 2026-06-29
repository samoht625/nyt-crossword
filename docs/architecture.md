# Architecture

## Sources and generated files

Each `puzzles/<slug>/puzzle.json` is canonical. It contains the complete
solution and clue answers so validation and every export are deterministic.
Edit that file first; never reverse-edit `.puz`, IPUZ, or PDF output.

`puzzles/<slug>/construction.json` is optional construction input. It records
theme placements and cells that the pattern generator must keep open or
blocked. Coordinates are one-based for readability.

`web/puzzles/*.puz` is the only generated output committed to Git. Those files
are runtime assets for the static site and must be regenerated whenever their
canonical puzzle changes.

## Tool layers

- `scripts/validate.py` owns the canonical schema checks and grid numbering.
- `scripts/build_outputs.py` exports `.puz`, IPUZ, and print PDFs.
- `scripts/construct.py` owns lexicon scoring, symmetric pattern generation,
  and the original backtracking fill engine.
- `scripts/ac3_fill.py` supplies the preferred AC-3/MRV fill engine.
- `scripts/fill_blacksquare.py` is an optional third-party fill adapter.
- `src/crossword_tools/` provides the stable import and CLI surface while the
  scripts remain directly executable for compatibility.

The site has no backend or build step. `web/puzzles.json` supplies gallery
metadata, `web/puz.js` parses Across Lite files, and `web/app.js` owns both the
gallery and solver state.

## Privacy boundary

The public repository must not contain constructor addresses, emails,
submission forms, private PDFs, or raw construction attempts. Keep those in a
different directory or repository. `.gitignore` blocks the historical local
locations, but staged files must still be reviewed before every commit.
