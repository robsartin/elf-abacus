# Submissions log

The submission CSVs are never committed: their programs embed puzzle targets from the licensed
competition data (ADR 0003). This file records which submission was chosen, when, and how it was made.
Kaggle is the authority for the scores; the local scorer matched it exactly every time checked.

## Recipe

1. Run the solver: `python -m elf_abacus --workers 24 --seed-offset N --out submissions/run-N.csv`
   (about 2.5 to 5 hours on 28 cores; prints nothing until done; each offset is a fresh set of
   constant pools).
2. Keep the shortest verified program per puzzle across every file so far:
   `python -m elf_abacus.portfolio --out submissions/best.csv <all previous files> submissions/run-N.csv`
   (add `--polish` to also re-run the slow peephole pass over every winner).
3. Cross the files over (ADR 0020): `python -m elf_abacus.crossover --puzzles data/puzzles.csv
   --workers 24 --out submissions/cross.csv submissions/*.csv`. Give it every file, not just the best.
4. Run the window superoptimiser last (ADRs 0018, 0019):
   `python -m elf_abacus.superopt --window 6 --workers 12 --puzzles data/puzzles.csv --out submissions/best-s.csv <file>`
   (window 4 first is cheap; window 6 is about 33 CPU-minutes over the whole set).
5. Merge the results with portfolio again, then submit only if the printed total is below the current best:
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
| 2026-11-25 | 178,457 | window superoptimiser (window 4) over the best file |
| 2026-11-25 | 178,415 | best-of over every file, including the superoptimised one |
| 2026-11-26 | 177,988 | `--seed-offset 12` run, best-of, superoptimiser |
| 2026-11-26 | 177,975 | window 6 superoptimiser |
| 2026-11-26 | 177,135 | crossover with emission-order search (about -825 on its own), then window 6 |

Each whole-set run alone scored 181,800 to 182,750, so the gain comes from taking the best of several
runs per puzzle, and it shrinks with each new run (about 1,700, 800, 600, then 400 points). Later
gains came from recombining existing files (crossover) and local search (superoptimiser) instead.

## Tried and not worth merging (2026-11-24)

Peephole multi-consumer rewrite (-52 instructions), cost-aware rematerialisation (-0.4% on a sample),
beam search over target steps (worse than best-of-seeds at equal CPU), and a value-limit-tight attack
(the group is the 60-bit puzzles; no variant survives best-of). See ADR 0017 for the last.

## Tried and not worth merging (2026-11-25 to 2026-11-26)

Variance-targeted reseeding, knob diversity as a best-of source, random rematerialisation restarts,
meet-in-the-middle finishing, a "large basis, two operations per target" generator (impossible by
counting: about 5.8 target bits per instruction), peephole rebuild with both operands new (0 gain),
pressure-aware rescheduling (at most 0.3%), a superoptimiser and peephole fixpoint (no gain), and
virtual register files of 128 or more (64 is best).
