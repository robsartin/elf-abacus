import pytest

from elf_abacus import run
from elf_abacus.router import ChainRun, features, route
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
            pool_size=16,
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
    assert {(c.pool_size, c.pairs) for c in plan.chains} == {(16, True)}


def test_shouldKeepFullChainPortfolioWhenFewTargets():
    plan = route(SMALL, seeds=3)
    assert plan.horner
    assert {(c.pool_size, c.pairs) for c in plan.chains} == {
        (n, p) for n in (24, 32, 40) for p in (True, False)
    }
    assert all(c.seed == 0 for c in plan.chains)


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
    assert seen == [0, 1]


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
        lambda puzzle, seeds: Route(
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
