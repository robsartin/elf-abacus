# 0011. Build near-duplicate targets as an earlier target plus or minus a gap

Status: Accepted (2026-11-20)

Extends ADR 0008 (pool growth); it does not change it.

## Context
Some real puzzles are not independent. On `puzzles.csv`, 1,358 of 26,902 targets (5%) lie within
0.1% of an earlier target, 2,899 (11%) within 1%. The practice set, which carries family labels,
says where this comes from: targets are sorted, so some are close by chance (1.7% within 0.1% of an
earlier one in the independent family), against 10.9% in shared and 3.8% in mixed (multiplicative
1.6%). The excess, about 3% of real targets, is the related set. Gaps in the shared family are a
few hundred to a few thousand against targets of 10^7-10^12, so the gap is far cheaper to build
than the target. On a sample of related targets the planner needed 591 instructions for the gaps
(plus the join) against 1,229 for the targets themselves.

Other relations are rare on the real set: an exact multiple of another target or a start value
above 1,000 for 38 targets, a common factor above 10^6 for 138, a quotient for 50. They are not
worth a solver.

ADR 0008's pool growth already uses solved targets as free terms, but only in the 3-4 registers
left beside the accumulators, so it reaches the first few (smallest) targets only.

## Decision
`solve(..., relate=True)` (`src/elf_abacus/solvers/relations.py`) keeps in a register every
target that a later target is close to, in the registers above the accumulators, oldest
overwritten first. For each target it also plans `base +/- gap` for the nearest kept bases, the
gap built by the ordinary planner, and uses that plan when it is cheaper than the plain one.
`ChainRun.relate` selects it per run.

## Alternatives rejected
- **Rely on pool growth alone:** growth spends registers on the smallest targets, not on the ones
  that have close neighbours; at equal pool size relate beat it by 1.5% on both seeds.
- **Multiple, quotient and common-factor plans:** under 0.5% of targets have such a relation, so
  the search time would buy almost nothing.
- **Relate to every earlier target through the pool:** needs a register per target; there are 48.
- **Retain only the immediately previous target:** targets are sorted, but the neighbour is often
  two or three back, and the ring of kept bases costs nothing extra.

## Consequences
On the 28-puzzle sample, pairs on, pool 36 with growth: relate 6,200 against 6,295 without
(seed 0) and 6,224 against 6,320 (seed 1), -1.5% both. At pool 40 the gain is -0.8% and -0.9%,
inside the noise of a single run. Against pool 40 with growth, the baseline route, pool 36 with
growth and relate is -2.8% and -2.4%, at 1.4-1.7x the time; part of that is the pool size, since
36 with growth alone is -1.3% and -0.9%. The whole set was not run. Per-target costs and the
counts are in the session notes, not here.

Finding: `run.solve_one` did not pass `grow` to the chain solver before this change, so the
route's growth setting reached nobody; the sample numbers above read `grow` straight from
`chain.solve`.
