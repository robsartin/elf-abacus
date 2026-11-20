"""Choose which solvers to run on a puzzle from cheap features, and how much search to spend."""

from __future__ import annotations

from dataclasses import dataclass

from elf_abacus.verifier import Puzzle

# From the per-variant win table in ADR 0010: with this many targets the largest pool with pair
# search won ~every puzzle, and the other five chain variants only added time.
BIG_TARGETS = 15
BIG_POOL = 40
SMALL_POOLS = (24, 32, 40)


@dataclass(frozen=True)
class Features:
    targets: int
    starts: int
    limit_bits: int
    max_target_bits: int
    limit_ratio: float


@dataclass(frozen=True)
class ChainRun:
    pool_size: int
    pairs: bool
    seed: int


@dataclass(frozen=True)
class Route:
    horner: bool
    chains: tuple[ChainRun, ...]


def features(puzzle: Puzzle) -> Features:
    top = max(puzzle.targets)
    return Features(
        targets=len(puzzle.targets),
        starts=len(puzzle.starting_values),
        limit_bits=puzzle.value_limit.bit_length(),
        max_target_bits=top.bit_length(),
        limit_ratio=puzzle.value_limit / top,
    )


def route(puzzle: Puzzle, seeds: int = 3) -> Route:
    """Big puzzles get `seeds` runs of the strongest chain; small ones the cheap full portfolio."""
    if features(puzzle).targets >= BIG_TARGETS:
        return Route(
            True, tuple(ChainRun(BIG_POOL, True, seed) for seed in range(seeds))
        )
    return Route(
        True,
        tuple(ChainRun(n, pairs, 0) for pairs in (True, False) for n in SMALL_POOLS),
    )
