# 0015. Retune the router's pool sizes for grown chains

Status: Accepted (2026-11-21)

Amends the route ADR 0010 chose (it does not edit it): ADR 0010 and 0013 picked pool 16 and the
old no-grow portfolio before `grow` + `relate` + `keep_inner` existed together. The constants are
in `src/elf_abacus/router.py`; the code, not this ADR, is the authority for the route.

## Context
Pool size was tuned for plain chains. With growth, relations and kept intermediates (ADRs 0008,
0011, 0013) the pool only seeds the first targets and later ones are served by the grown registers,
so a smaller pool may now win. Few-target puzzles (under 15 targets, 141 of 1,000, about 3.5% of the
score) still ran the old six no-grow variants, never the new config.

## Decision
- Many-target puzzles: three seeds of the grown chain at pool 10 instead of 16.
- Few-target puzzles: Horner, one no-grow pool-24 run as insurance, and grown chains at pools
  6, 8 and 10 with seeds 0 and 1. Pools 4 and 6 fail outright on some puzzles, so the fallbacks stay.

## Evidence
Scratch harness, one chain run per cell, totals of instructions (lower is better), `pairs` on.

Many-target, 12 puzzles (`big` subsample, every 72nd): pool 16 2,589 / 2,578 / 2,557 (seeds 0-2);
pool 10 2,515 / 2,541 / 2,556; pool 12 2,553; pool 8 2,564 (seed 0 only). Best of three seeds:
pool 16 2,536, pool 10 2,486 (-2.0%); two pool-10 seeds (2,490) beat three pool-16 seeds while
spending 45% less CPU (2,142 vs 3,878 cpu-s). No pool 8-16 run failed to solve a puzzle, and
Horner never won on these; the pool-24 fallback for failures is therefore not added (the best-of
already includes Horner, which always solves).

Few-target, 36 puzzles (every 4th): old six-variant portfolio plus Horner 1,910; one grown pool-8
run 1,386; pools 24/16/12/10 1,710/1,526/1,434/1,407; pools 4 and 6 solve all but 1-6 puzzles
but win the tiny ones. The chosen route (Horner, pool 24, pools 6/8/10 x seeds 0/1) totals 1,302
(-31.8%); about 1.1% of the whole score by extrapolation. Horner still wins a few 2-4 target puzzles.

## Alternatives rejected
- **Keep pool 16 for many targets:** 2% worse at best of three seeds and slower per run.
- **Pool 8 or 12 for many targets:** 2,564 and 2,553 single-seed, no better than pool 10 within
  the seed noise (about 1%), pool 8 the slowest on the hardest puzzle.
- **A pool-24 fallback when the pool-10 runs fail:** no pool 8-16 run failed in the sample, and
  Horner already guarantees a program.
- **Pool 4 in the few-target route:** 1,298 vs 1,302 with it, inside the noise, and it fails
  on 2 to 6 of 36 puzzles.

## Consequences
The sample is small (12 and 36 puzzles) and seed noise is 0.5-1%, so the whole-set gain is an
estimate; a full run is the check. Not tried: per-feature pool choice (targets, starts, limit bits)
beyond the two-way split, since on the 12-puzzle win table the winners were scattered across pools 8 to 16 with no visible link to
target count, starting values or limit bits; 12 puzzles cannot rule a feature out.

## Amendment 2026-11-21: grown fallback for failing big puzzles

On five 32-target puzzles with a value limit within about 5% of the top target, the pool-10 run
fails at the first target and the puzzle fell back to Horner at about 560 instructions. `Route.fallback`
(`src/elf_abacus/router.py`) now runs grown pool 16 then pool 24 only while no verified chain program
exists, and `run.solve_one` honours it. Measured at about 400 instructions on three of the five,
at 3 to 7 minutes of CPU per affected puzzle. The larger excess is the roughly 124 puzzles with limit
ratio near 1.0 that do succeed but average about 370 instructions; that is untouched.
Negative results from the same round, not adopted: pool 8 is no better than 10, pools 6 and 4 fail on
the hardest many-target puzzles, rebuild cadence 2 gains 0.4%, evicting pool constants costs 3.4%,
and distance-weighted retention scoring is identical to the baseline.
