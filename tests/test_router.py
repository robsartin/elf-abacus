import pytest

from elf_abacus import run
from elf_abacus.router import BIG_VIRTUAL, ChainRun, features, route
from elf_abacus.verifier import Puzzle, verify

BIG = Puzzle("big", [4, 22], list(range(1000, 1040)), 10**12)
SMALL = Puzzle("small", [3, 5], [8, 15, 40, 100], 1000)


def test_shouldReportPuzzleFeaturesWhenGivenAPuzzle():
    f = features(Puzzle("p", [3, 5], [8, 16], 100))
    assert (f.targets, f.starts, f.limit_bits, f.max_target_bits) == (2, 2, 7, 5)
    assert f.limit_ratio == pytest.approx(100 / 16)


def test_shouldRouteBigPuzzleToLargestPoolChainOnlyWhenManyTargets():
    plan = route(BIG, seeds=1)
    assert plan.horner
    assert plan.chains == (
        ChainRun(
            pool_size=10,
            pairs=True,
            seed=0,
            grow=True,
            relate=True,
            keep_inner=True,
            retain=True,
        ),
    )


def test_shouldAddOneSeedPerBudgetUnitWhenPuzzleIsBig():
    plan = route(BIG, seeds=3)
    assert [c.seed for c in plan.chains] == [0, 1, 2]
    assert {(c.pool_size, c.pairs) for c in plan.chains} == {(10, True)}


def test_shouldPlanOnVirtualRegistersWhenBigPuzzleSeedIsNotTheFirst():
    plan = route(BIG, seeds=3)
    assert [c.virtual for c in plan.chains] == [0, BIG_VIRTUAL, BIG_VIRTUAL]


def test_shouldRunGrowRelateKeepInnerSmallPoolsWhenFewTargets():
    plan = route(SMALL, seeds=3)
    assert plan.horner
    grown = [c for c in plan.chains if c.grow]
    assert {c.pool_size for c in grown} == {6, 8, 10}
    assert {c.seed for c in grown} == {0, 1}
    assert all(c.pairs and c.relate and c.keep_inner for c in grown)


def test_shouldKeepACheapNoGrowFallbackWhenFewTargets():
    plan = route(SMALL, seeds=3)
    assert ChainRun(pool_size=24, pairs=True, seed=0) in plan.chains


def test_shouldSolveSmallPuzzleThroughRouterWhenRunning():
    results = run.solve_one(SMALL)
    assert results["horner"] is not None
    verify(SMALL, results["horner"])
    assert set(results) == {"horner", "chain"}


def test_shouldRunOneChainPerSeedWhenSolvingBigPuzzle(monkeypatch):
    seen = []
    monkeypatch.setattr(
        run.chain, "solve", lambda puzzle, **kw: seen.append(kw["seed"]) or None
    )
    monkeypatch.setattr(run.horner, "solve", lambda puzzle: None)
    run.solve_one(BIG, seeds=2)
    assert seen[:2] == [0, 1]


def test_shouldRouteLargerGrownPoolsAsFallbackWhenPuzzleIsBig():
    plan = route(BIG, seeds=1)
    assert [c.pool_size for c in plan.fallback] == [16, 24]
    assert all(c.grow and c.relate and c.keep_inner and c.retain for c in plan.fallback)


def test_shouldHaveNoFallbackWhenFewTargets():
    assert route(SMALL, seeds=1).fallback == ()


def test_shouldRunFallbackOnlyWhenPrimaryChainsFindNothing(monkeypatch):
    pools = []

    def fake_solve(puzzle, **kw):
        pools.append(kw["pool_size"])
        return [["+", 0, 1, 2]] if kw["pool_size"] == 16 else None

    monkeypatch.setattr(run.chain, "solve", fake_solve)
    monkeypatch.setattr(run.horner, "solve", lambda puzzle: None)
    monkeypatch.setattr(run, "verify", lambda puzzle, program: None)
    results = run.solve_one(BIG, seeds=2)
    assert pools == [10, 10, 16]
    assert results["chain"] == [["+", 0, 1, 2]]


def test_shouldSkipFallbackWhenPrimaryChainSucceeds(monkeypatch):
    pools = []

    def fake_solve(puzzle, **kw):
        pools.append(kw["pool_size"])
        return [["+", 0, 1, 2]]

    monkeypatch.setattr(run.chain, "solve", fake_solve)
    monkeypatch.setattr(run.horner, "solve", lambda puzzle: None)
    monkeypatch.setattr(run, "verify", lambda puzzle, program: None)
    run.solve_one(BIG, seeds=1)
    assert pools == [10]


def test_shouldPassGrowRelateAndKeepInnerToTheChainSolverWhenRunningARoute(monkeypatch):
    from elf_abacus import run
    from elf_abacus.router import Route
    from elf_abacus.verifier import Puzzle

    seen = []

    def fake_solve(puzzle, **kwargs):
        seen.append(kwargs)

    monkeypatch.setattr(run.chain, "solve", fake_solve)
    monkeypatch.setattr(
        run,
        "route",
        lambda puzzle, seeds, seed_offset: Route(
            False, (ChainRun(36, True, 1, grow=True, relate=True, keep_inner=True),)
        ),
    )
    run.solve_one(Puzzle("p", [3], [5], 100))
    assert seen == [
        {
            "pool_size": 36,
            "pairs": True,
            "seed": 1,
            "grow": True,
            "relate": True,
            "keep_inner": True,
            "retain": False,
        }
    ]


HUGE = Puzzle("huge", [4, 22], [2**55 + k for k in range(32)], 2**60)


@pytest.mark.parametrize("seeds", [1, 3])
def test_shouldRouteTwoPoolTwentySeedsWhenEveryTargetIsAtLeast2To54(seeds):
    plan = route(HUGE, seeds=seeds)
    assert plan.horner
    assert [(c.pool_size, c.seed) for c in plan.chains] == [(20, 0), (20, 1)]
    assert all(
        c.pairs and c.grow and c.relate and c.keep_inner and c.retain
        for c in plan.chains
    )
    assert [c.pool_size for c in plan.fallback] == [16, 24]


def test_shouldKeepPoolTenRouteWhenSmallestTargetIsBelow2To54():
    top = Puzzle("p", [4, 22], [2**54 - 1, *range(2**55, 2**55 + 31)], 2**60)
    assert [c.pool_size for c in route(top, seeds=1).chains] == [10]


def test_shouldStartSeedsAtTheOffsetWhenSeedOffsetIsGiven():
    plan = route(BIG, seeds=3, seed_offset=10)
    assert [c.seed for c in plan.chains] == [10, 11, 12]
    assert [c.virtual for c in plan.chains] == [BIG_VIRTUAL] * 3
