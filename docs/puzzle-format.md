# Canonical puzzle format

A puzzle source is a UTF-8 JSON object with these fields:

- `title`, `author`, and `copyright`
- `size.rows` and `size.columns`
- `grid`: one uppercase string per row; `#` marks a block
- `clues.Across` and `clues.Down`: ordered clue objects containing `number`,
  `answer`, and `clue`

Optional metadata includes `intended_difficulty`, `theme`, and `source_notes`.
`theme.entries` may record answers, base phrases, clues, and roles such as
`themer` or `revealer`.

The answer in each clue object intentionally duplicates letters from `grid`.
This makes sources readable during editing; `crossword-validate` rejects any
disagreement.

## Invariants

The default validator enforces rectangular dimensions, A–Z letters, connected
white cells, rotational block symmetry, entries of at least three letters,
fully checked cells, unique answers, complete clue coverage, and valid theme
references. Use `--allow-asymmetric` or `--allow-unchecked` only for puzzle
types that deliberately relax those conventions.

Run validation after every source edit:

```sh
uv run crossword-validate puzzles/<slug>/puzzle.json
```
