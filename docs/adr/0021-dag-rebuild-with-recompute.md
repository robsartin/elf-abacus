# 0021. DAG rebuild with recompute

Status: Accepted (2026-11-27)

A post-pass that rebuilds values of a finished program from other values anywhere in it, accepting
the result by compiled length. The mechanism is `src/elf_abacus/dagopt.py`; the code, not this
ADR, is the authority for its details. The measurement quoted below is a dated sample, not a
standing figure.

## Context
The peephole (ADR 0012, `src/elf_abacus/peephole.py`) already rebuilds a value from a pair of
other live values, with up to two fresh helpers, and drops what dies. But `peephole.optimize`
accepts a rewrite only when the smaller DAG still allocates to the real register file without
recomputation. On the longest programs (about 380 instructions, 48 registers) that test rejects
rewrites whose saving would survive recompilation with recompute (ADR 0016). The window
superoptimiser (ADRs 0018, 0019) is blind to operand pairs far apart in the program, and crossover
(ADR 0020) only pools derivations across files.

## Decision
- Run the peephole's own DAG rewrites (`_rederive`, `_rederive_with_helpers`, `_rederive_multi`)
  with the register-fit test removed, so a value may be rebuilt from any pair of values produced
  anywhere in the program.
- Write the shrunk DAG with one register per value and compile it to the real register file with
  `peephole.rematerialize`, in both emission orders.
- Compiled length is the score of record: keep the result only if it is shorter than the input,
  and verify it with the verifier (ADR 0002). The input is returned otherwise.
- CLI: `python -m elf_abacus.dagopt`, like the other post-passes.

## Result
On the 100 longest programs of the window-6 superoptimised best file (33,108 instructions) the
pass saved 73 (0.22%), improving 36 programs, at about 24 CPU seconds per program. Run the window
superoptimiser again after it, since re-allocation changes which windows are redundant.

## Alternatives rejected
- **A new search over arbitrary operand pairs**: the peephole's rewrites already enumerate one-op and helper derivations over every live value; the missing piece was the acceptance test, not the move set.
- **Accept by DAG size**: a smaller DAG can compile longer under register pressure, so DAG size is not the score; only compiled length is.
- **Keep the register-fit test and widen the moves**: the fit test is what rejected these savings, so widening the moves behind it cannot recover them.
