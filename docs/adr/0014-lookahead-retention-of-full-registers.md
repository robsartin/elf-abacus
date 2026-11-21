# 0014. Lookahead retention once the registers are full

Status: Proposed (2026-11-21)

Extends ADR 0008 and ADR 0013; it changes neither.

## Context
Under `grow`, solved targets and `keep_inner` intermediates take free registers first-come
first-kept. About 30 targets and their intermediates compete for roughly 16-24 free registers, so
mid-puzzle the file is full and every later target, however many still-unsolved targets sit near
it, is dropped.

## Decision
`solve(..., grow=True, retain=True)` evicts when full: `pick_victim` and `lookahead` in
`src/elf_abacus/solvers/relations.py` score a value by how many remaining unsolved targets lie
within 5% of it (the same closeness as `wanted_as_base`). A new target overwrites the lowest-scoring
non-starting pool value, oldest first among ties, but only when its own score is higher. The last
instruction of the plan writes into the victim's register, and the search sets are rebuilt at once
because they still name the evicted value. Wired into the router for many-target puzzles
(`ChainRun.retain`).

Measured on the `puzzles[::36][:28]` sample, pool 16, grow, relate, keep_inner, pairs on, totals:

| Variant | seed 0 | seed 1 |
|---|---|---|
| current best | 5,038 | 5,012 |
| `retain` | 4,965 (-1.4%) | 4,943 (-1.4%) |

The gain is just above the 0.5-1% seed noise; it agrees in sign and size on both seeds, and a
whole-set run is not done (ADR 0008's sample gains shrank by about half on the whole set).

## Alternatives rejected
- **Leaving first-come-first-kept:** costs the 1.4% above.
- **Not yet tried, so not rejected:** evicting intermediates as well, scoring by re-derivation
  cost, and weighting lookahead by distance or by tail/pair reach rather than relative closeness.
  Only the closeness score that `relate` already uses was measured.

## Consequences
Each eviction forces a rebuild of the forward and sum sets, a CPU cost that was not separately
measured; the sample runs took about 20 minutes with two workers for both variants. The code, not
this ADR, is the authority for the rules.
