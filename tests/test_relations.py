import pytest

from elf_abacus.solvers.chain import build_forward, build_sums, solve
from elf_abacus.solvers.relations import plan_delta
from elf_abacus.verifier import Puzzle, verify

POOL = [3, 4, 12]
BASE = 1_000_003  # held in register 3, next to the pool registers 0..2
LIMIT = 10**12


def _sets():
    return build_forward(POOL, LIMIT, depth=2), build_sums(POOL, 3)


def _run(target, max_cost=None):
    forward, sums = _sets()
    return plan_delta(target, {BASE: 3}, POOL, LIMIT, forward, sums, max_cost=max_cost)


def _verified(plan, target):
    puzzle = Puzzle("p", [*POOL, BASE], [target], LIMIT)
    program = plan.program([0, 1, 2], [4, 5, 6, 7], dest=4)
    assert verify(puzzle, program) == len(program)
    return program


@pytest.mark.parametrize("gap, sign", [(19, 1), (-19, -1)])
def test_shouldPlanBasePlusOrMinusGapWhenAnAvailableBaseIsNearTheTarget(gap, sign):
    target = BASE + gap
    plan = _run(target)
    assert plan is not None
    assert plan.sign == sign
    program = _verified(plan, target)
    assert plan.cost == len(program)
    assert plan.cost <= 3  # 12 + 4 + 3 for the gap, one join with the base


def test_shouldReturnNoDeltaPlanWhenNoBaseIsAvailable():
    forward, sums = _sets()
    assert plan_delta(BASE + 19, {}, POOL, LIMIT, forward, sums) is None


def test_shouldReturnNoDeltaPlanWhenCostBoundIsAlreadyBeaten():
    assert _run(BASE + 19, max_cost=3) is None
    assert _run(BASE + 19, max_cost=4) is not None


def test_shouldSkipTheBaseWhenTargetEqualsIt():
    assert _run(BASE) is None


def test_shouldBuildFewerInstructionsWhenTargetsAreSmallStepsFromEachOther():
    starts = [7, 19, 40]
    base = 48_611_207
    targets = [base, base + 31, base + 70, base + 123]
    puzzle = Puzzle("p", starts, targets, 10**12)
    plain = solve(puzzle, pool_size=8, seed=1, pairs=False)
    related = solve(puzzle, pool_size=8, seed=1, pairs=False, relate=True)
    assert plain is not None and related is not None
    assert verify(puzzle, related) == len(related)
    assert len(related) < len(plain)


def test_shouldOverwriteOldestKeptTargetWhenMoreBasesThanFreeRegisters():
    base = 48_611_207
    targets = [base + 17 * k * (k + 3) for k in range(9)]
    puzzle = Puzzle("p", [7, 19, 40], targets, 10**12, registers=14)
    program = solve(puzzle, pool_size=6, seed=2, pairs=False, relate=True)
    assert program is not None
    assert verify(puzzle, program) == len(program)


def test_shouldKeepPlanDecisionsWhenNoTargetsAreRelated():
    puzzle = Puzzle("p", [7, 19, 40], [48611, 902113, 55_000_001], 10**9)
    plain = solve(puzzle, pool_size=8, seed=1, pairs=False)
    related = solve(puzzle, pool_size=8, seed=1, pairs=False, relate=True)
    assert related is not None and plain is not None
    assert len(related) == len(plain)


def test_shouldReportWhetherALaterTargetIsCloseWhenAskingIfWantedAsBase():
    from elf_abacus.solvers.relations import wanted_as_base

    assert wanted_as_base([100, 101, 5000], 0)
    assert not wanted_as_base([100, 101, 5000], 1)
    assert not wanted_as_base([100, 101, 5000], 2)
