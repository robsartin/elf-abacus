# 0002. The verifier is the oracle for every solver

Status: Accepted (2026-11-18)

## Context
Kaggle rejects the whole submission if any one of 1,000 programs is invalid, with no partial
credit. A solver bug that emits one illegal instruction therefore costs everything, and the
rules (positive integers, exact division, value limit, register bounds, size cap) are easy to
get subtly wrong. The rules are defined on the competition's Data and Evaluation pages; the
code is the authority for how we apply them.

## Decision
`src/elf_abacus/verifier.py` is the single replay implementation. Every solver output and every
submission file is checked through it before it is trusted. It returns the instruction count on
success and raises `InvalidProgram` with the failing instruction on any violation, so a solver
cannot silently proceed past an illegal step. It depends on the standard library only, so it
stays trivially auditable and importable anywhere (enforced in `tests/test_adrs.py`).

## Alternatives rejected
- **Solvers self-check as they build:** each solver would re-implement the rules, and a
  disagreement between solver and Kaggle's judge would go unnoticed until rejection.
- **Return `(valid, reason)` instead of raising:** callers can forget to check the flag; an
  exception cannot be ignored by accident.
- **Trust Kaggle's judge as the only check:** feedback is slow, rate-limited by daily
  submissions, and says nothing about which of 1,000 programs failed.
