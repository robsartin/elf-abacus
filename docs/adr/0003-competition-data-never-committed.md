# 0003. Competition data is never committed

Status: Accepted (2026-11-18)

## Context
The repository is public. The Data page licenses the files "subject to Competition Rules",
which normally forbids redistribution, and the puzzles are only downloadable after accepting
those rules while signed in.

## Decision
Puzzle files go in `data/` and generated submissions in `submissions/`; both are excluded by
`.gitignore` (the authority for exactly which paths), with only `data/.gitkeep` tracked. Tests
that need puzzles use tiny hand-written fixtures, such as the worked example from the Data page,
never real rows.

## Alternatives rejected
- **Commit the data for convenience:** likely breaches the competition rules and cannot be
  undone once public, since history and forks keep it.
- **Private repository:** loses the open-source posture the project wants and the license in
  ADR 0004; ignoring the files is enough and keeps the repo public.
- **Download script in the repo:** needs the user's Kaggle credentials and accepted rules;
  copying the files by hand is a one-off step documented in `README.md`.
