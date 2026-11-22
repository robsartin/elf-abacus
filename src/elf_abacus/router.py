"""Choose which solvers to run on a puzzle from cheap features, and how much search to spend."""

from __future__ import annotations

from dataclasses import dataclass

from elf_abacus.verifier import Puzzle

# From the per-variant win table in ADR 0010: with this many targets the largest pool with pair
# search won ~every puzzle, and the other five chain variants only added time.
BIG_TARGETS = 15
BIG_VIRTUAL = (
    300  # registers the later seeds plan on; recompiled into the real file afterwards
)
BIG_POOL = 10  # ADR 0015: smaller pools beat 16 once grow + relate + keep_inner are on
# Random 60-bit targets with few starting values (ADR 0010 round five): pool 20 with two seeds beat
# pool 10 / the 16-24 fallback by ~5% on the six-puzzle sweep, at ~3 minutes per run.
HUGE_TARGET_BITS = 54
HUGE_POOL = 20
HUGE_SEEDS = (0, 1)
SMALL_GROW_POOLS = (6, 8, 10)
SMALL_GROW_SEEDS = (0, 1)
# Few starting values and a value limit just above the top target leave pool 10 too small to
# reach the first target at all; the whole puzzle then falls to Horner (~460 instructions against
# ~380 for these larger pools). Tried only after every primary run fails.
BIG_FALLBACK_POOLS = (16, 24)
SMALL_FALLBACK_POOL = (
    24  # no-grow run kept as insurance; the grown runs may fail outright
)


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
    grow: bool = False
    relate: bool = False
    keep_inner: bool = False
    retain: bool = False
    virtual: int = (
        0  # plan on this many registers, then recompile into the real file (0: off)
    )


@dataclass(frozen=True)
class Route:
    horner: bool
    chains: tuple[ChainRun, ...]
    fallback: tuple[
        ChainRun, ...
    ] = ()  # tried in order only if `chains` all find nothing


def features(puzzle: Puzzle) -> Features:
    top = max(puzzle.targets)
    return Features(
        targets=len(puzzle.targets),
        starts=len(puzzle.starting_values),
        limit_bits=puzzle.value_limit.bit_length(),
        max_target_bits=top.bit_length(),
        limit_ratio=puzzle.value_limit / top,
    )


def route(puzzle: Puzzle, seeds: int = 3, seed_offset: int = 0) -> Route:
    """Big puzzles get `seeds` runs of the strongest chain; small ones a few small grown pools."""
    if features(puzzle).targets >= BIG_TARGETS:
        pool, run_seeds = BIG_POOL, tuple(range(seed_offset, seed_offset + seeds))
        if min(puzzle.targets) >= 2**HUGE_TARGET_BITS:
            pool, run_seeds = HUGE_POOL, tuple(s + seed_offset for s in HUGE_SEEDS)
        return Route(
            True,
            tuple(
                ChainRun(
                    pool,
                    True,
                    seed,
                    grow=True,
                    relate=True,
                    keep_inner=True,
                    retain=True,
                    virtual=BIG_VIRTUAL if seed else 0,
                )
                for seed in run_seeds
            ),
            fallback=tuple(
                ChainRun(
                    n, True, 0, grow=True, relate=True, keep_inner=True, retain=True
                )
                for n in BIG_FALLBACK_POOLS
            ),
        )
    grown = tuple(
        ChainRun(n, True, seed, grow=True, relate=True, keep_inner=True)
        for seed in SMALL_GROW_SEEDS
        for n in SMALL_GROW_POOLS
    )
    return Route(True, (ChainRun(SMALL_FALLBACK_POOL, True, 0), *grown))
