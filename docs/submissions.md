# Submissions log

The submission CSVs are never committed: their programs embed puzzle targets from the licensed
competition data (ADR 0003). This file records which submission was chosen, when, and how it was made.
Kaggle is the authority for the scores; the local scorer matched it exactly every time checked.

## Recipe

1. Run the solver: `python -m elf_abacus --workers 24 --seed-offset N --out submissions/run-N.csv`
   (about 2.5 to 5 hours on 28 cores; each offset is a fresh set of constant pools).
2. Keep the shortest verified program per puzzle across every file so far:
   `python -m elf_abacus.portfolio --out submissions/best.csv <previous best> submissions/run-N.csv`
   (add `--polish` to also re-run the slow peephole pass over every winner).
3. Submit only if the printed total is below the current best:
   `.venv/bin/kaggle competitions submit -c santa-2026 -f submissions/best.csv -m "<message>"`.

## History (2026-11-20 onwards)

| Date | Kaggle score | What changed |
|---|---|---|
| 2026-11-20 | 218,127 | PR #9 solver, best-of with the earlier file |
| 2026-11-21 | 194,304 | pool-10 route, peephole, pair-helper rewrite, fallback pools for five puzzles |
| 2026-11-21 | 188,783 | rerun of the 60 large-target puzzles |
| 2026-11-21 | 188,254 | pool-20 route for 60-bit-target puzzles |
| 2026-11-21 | 186,213 | multi-helper peephole |
| 2026-11-22 | 185,613 | virtual-register seeds on 110 puzzles |
| 2026-11-22 | 185,608 | one more virtual-register puzzle |
| 2026-11-22 | 181,729 | whole-set virtual-register run (seeds 0 to 2), best-of with the above |
| 2026-11-23 | 180,032 | `--seed-offset 3` run (seeds 3 to 5), best-of |
| 2026-11-24 | 179,209 | `--seed-offset 6` run (seeds 6 to 8), best-of |
| 2026-11-25 | 178,625 | `--seed-offset 9` run on 64 virtual registers, best-of |

Each whole-set run alone scored 181,800 to 182,750, so the gain comes from taking the best of several
runs per puzzle, and it halves with each new run (about 1,700, 800, then 600 points).

## Tried and not worth merging (2026-11-24)

Peephole multi-consumer rewrite (-52 instructions), cost-aware rematerialisation (-0.4% on a sample),
beam search over target steps (worse than best-of-seeds at equal CPU), and a value-limit-tight attack
(the group is the 60-bit puzzles; no variant survives best-of). See ADR 0017 for the last.
