# Construction workflow

Construction specs keep puzzle-specific constraints out of the reusable
engine. All coordinates are one-based:

```json
{
  "size": 15,
  "theme_placements": [
    {
      "direction": "Across",
      "row": 3,
      "column": 1,
      "answer": "FIFTEENLETTERS"
    }
  ],
  "fixed_blocks": [[6, 1]],
  "fixed_open": [[1, 1]]
}
```

Theme placements also imply fixed open cells and fixed letters. A cell cannot
appear in both `fixed_blocks` and either an open or letter constraint.

Pattern and fill searches write candidates to the directory passed with
`--output`; use the ignored `scratch/` directory. Candidate JSON is temporary.
After human review, copy the selected grid and authored clues into canonical
`puzzle.json`, validate it, and discard the search output.

The lexicon combines word frequency data, the Crossword Nexus collaborative
word list, names, curated additions, and a blocklist. Scores help search order;
they do not replace human review of every entry and crossing.
