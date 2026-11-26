# 0020. Crossover of candidate programs

Status: Accepted (2026-11-26)

Best-of keeps one whole program per puzzle. Crossover lets each value come from whichever
candidate derived it most cheaply. The mechanism is `src/elf_abacus/crossover.py`; the code, not
this ADR, is the authority for its constants and search details. The number is 0020 because 0018
and 0019 belong to the window superoptimiser PR; this ADR is independent of it.

## Context
Every whole-set seed run, router variant and post-pass produces a full candidate file. Best-of
(`portfolio`) picks the shortest program per puzzle and throws the rest away, yet two candidates
for one puzzle usually share most values and differ in how a few were built. A shorter program
often exists that mixes their derivations. By the time this was built, new seed sets were giving
only a few hundred points each, so recombining existing files was the cheapest remaining lever.

## Decision
- Build each candidate's value DAG (`peephole._build_dag`, register names erased) and pool every
  derivation `value -> (op, left, right)` seen in any verified candidate for the puzzle.
- Pick one derivation per needed value by local search over the shared pool, minimising the number
  of distinct values computed, starting from the shortest few candidates (`BASES`).
- Compile the merged plan to the real register file with `rematerialize` and `optimize`
  (ADRs 0012, 0016). Compiled length, not plan size, is the score of record, because a smaller
  plan can need more recomputation.
- Search emission orders of the merged plan (`ORDER_TRIES` perturbed orders, scored by compiled
  length). This was the large gain: the plan was already good, but its order decided how much
  recomputation the 48-register file forced.
- Verify every output with the verifier (ADR 0002) and never emit something longer than the best
  input.

## Result
Over 27 candidate files the whole-set total fell from 177,988 to 177,163 (-825). Refining the plan
by compiled length, as opposed to ordering its emission, added nothing measurable.

## Alternatives rejected
- **More best-of only**: cannot combine derivations across candidates; it is the baseline this
  beats.
- **Minimise plan size and compile once**: plan size and compiled length disagree under register
  pressure, which is exactly where the gain was.
- **Exhaustive or ILP selection over the pool**: not tried. The reasoning is that the compile step
  is the true cost and an ILP cannot see it, and that local search plus order tries already reached
  the gain; a later experiment could still test it.
- **Pooling inside one candidate only**: no new information; the gain comes from candidates that
  planned differently.

## Consequences
- More candidate files make it better, so it runs last among the whole-set steps that generate
  programs and before the window superoptimiser, which then polishes locally.
- Candidate programs that fail verification are skipped, not trusted. A file that cannot be parsed
  at all still stops the run, and so does a puzzle that no file covers (reported before any search).
