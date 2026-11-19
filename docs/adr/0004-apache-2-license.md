# 0004. Apache License 2.0

Status: Accepted (2026-11-18)

## Context
Kaggle prize winners must publish a write-up and typically license their winning code under an
open license, and the author wants the code public from the start. `LICENSE` holds the text.

## Decision
Apache-2.0, declared in `LICENSE` and in `pyproject.toml`. Chosen for its explicit patent grant,
compatibility with Kaggle's usual winner-license expectations, and familiarity.

## Alternatives rejected
- **MIT:** also acceptable, but lacks the explicit patent grant for no offsetting benefit.
- **GPL family:** copyleft would hinder other competitors and reviewers from reusing ideas.
- **No license / all rights reserved:** public code without a license is not reusable, which
  defeats publishing it.
