import numpy as np
import pytest

from elf_abacus.solvers.chain import (
    build_forward,
    build_sums,
    chain_program,
    decode_forward,
    decode_terms,
    find_chain,
    find_pair,
    find_product_pair,
    plan_target,
)
from elf_abacus.verifier import Puzzle, verify

POOL = [3, 4, 12]


def test_shouldContainEveryOneOpValueWhenBuildingFirstForwardSet():
    _, f1, _ = build_forward(POOL, 1000)
    assert {7, 12, 16, 36, 1, 8, 9, 15, 24, 144}.issubset(set(f1.vals.tolist()))
    assert {1, 3, 4}.issubset(set(f1.vals.tolist()))  # 4-3, 12/4, 12/3


@pytest.mark.parametrize("level", [0, 1, 2])
def test_shouldReplayEveryForwardCodeToItsValueWhenDecoding(level):
    forward = build_forward([5, 9, 22, 30], 10**6)[level]
    for value, code in zip(forward.vals.tolist(), forward.codes.tolist()):
        assert decode_forward(level, code, [5, 9, 22, 30]) == value


@pytest.mark.parametrize(
    "op2,expected", [(0, 15), (1, 36), (2, -9), (3, 9), (4, 0), (5, 4)]
)
def test_shouldApplyEachSecondOperationWhenDecodingHandBuiltCode(op2, expected):
    """pool [6, 3, 12]; first op 6-3 = 3; then combine 3 with 12 in each of the six ways."""
    first = (2 * 64 + 0) * 64 + 1
    assert decode_forward(2, (first * 8 + op2) * 64 + 2, [6, 3, 12]) == expected


def test_shouldKeepForwardValuesPositiveAndWithinLimitWhenBuilding():
    for forward in build_forward([5, 9, 22, 30], 500):
        assert forward.vals.min() >= 1
        assert forward.vals.max() <= 500


def test_shouldSortSumValuesAndStartAtZeroWhenBuildingSums():
    sums = build_sums([3, 4], 3)
    assert np.all(np.diff(sums.vals) > 0)
    zero = int(np.searchsorted(sums.vals, 0))
    assert sums.vals[zero] == 0 and sums.nterms[zero] == 0


def test_shouldReplaySumCodesToTheirValuesWhenDecodingTerms():
    pool = [3, 4, 12]
    sums = build_sums(pool, 3)
    for value, code, n in zip(
        sums.vals.tolist(), sums.codes.tolist(), sums.nterms.tolist()
    ):
        terms = decode_terms(code, n)
        assert len(terms) == n
        assert sum(sign * pool[idx] for sign, idx in terms) == value


def test_shouldUseFewestTermsWhenSeveralSumsShareAValue():
    sums = build_sums([3, 4], 4)
    seven = int(np.searchsorted(sums.vals, 7))
    assert (
        sums.vals[seven] == 7 and sums.nterms[seven] == 2
    )  # 3 + 4, not 4+4-... longer


def test_shouldBuildVerifiedProgramWhenTargetIsOneChainAway():
    pool = [776, 1324, 1429]
    target = 776 * 1324 + 1429  # f=1 product then one added term
    forward = build_forward(pool, 10**9)
    sums = build_sums(pool, 3)
    chain = find_chain(target, pool, 10**9, forward, sums)
    assert chain is not None and chain.cost == 2
    program = chain_program(chain, pool_regs=[0, 1, 2], acc=3)
    puzzle = Puzzle("p", pool, [target], 10**9)
    assert verify(puzzle, program) == 2


def test_shouldReturnNoneWhenTargetExceedsEveryReachableValue():
    pool = [2, 3]
    forward = build_forward(pool, 10)
    sums = build_sums(pool, 3)
    assert find_chain(1000, pool, 10, forward, sums) is None


def test_shouldCostNothingWhenTargetIsAlreadyInThePool():
    pool = [5, 9]
    chain = find_chain(9, pool, 100, build_forward(pool, 100), build_sums(pool, 3))
    assert chain is not None and chain.cost == 0
    assert chain_program(chain, pool_regs=[0, 1], acc=2) == []


def test_shouldStopSearchingWhenCostBoundIsAlreadyBeaten():
    pool = [776, 1324, 1429]
    target = 776 * 1324 + 1429
    forward = build_forward(pool, 10**9)
    sums = build_sums(pool, 3)
    assert find_chain(target, pool, 10**9, forward, sums, max_cost=2) is None
    assert find_chain(target, pool, 10**9, forward, sums, max_cost=3).cost == 2


def test_shouldSplitIntoTwoChainsWhenNoDirectChainExists():
    """149 = 10*10 + 7*7 needs two chains when only one signed term is allowed."""
    pool = [10, 7]
    forward = build_forward(pool, 10**6)
    sums = build_sums(pool, 1)
    assert find_chain(149, pool, 10**6, forward, sums) is None
    plan = plan_target(149, pool, 10**6, forward, sums)
    assert plan is not None and plan.cost == 3
    program = plan.program(pool_regs=[0, 1], accs=[2, 3])
    assert verify(Puzzle("p", pool, [149], 10**6), program) == 3


def test_shouldPreferTheDirectChainWhenItIsCheaper():
    pool = [776, 1324, 1429]
    target = 776 * 1324 + 1429
    forward = build_forward(pool, 10**9)
    sums = build_sums(pool, 3)
    plan = plan_target(target, pool, 10**9, forward, sums)
    assert plan is not None and plan.cost == 2 and plan.rest is None


def test_shouldProduceVerifiedProgramWhenSolvingARandomishPuzzle():
    from elf_abacus.solvers.chain import solve

    targets = [48611, 1020301, 7340111, 90210909, 523412345]
    puzzle = Puzzle("p", [7, 19, 40], targets, 10**9)
    program = solve(puzzle, pool_size=30, max_terms=3, seed=1)
    assert program is not None
    assert verify(puzzle, program) == len(program)


def test_shouldBeDeterministicWhenSolvingTwiceWithTheSameSeed():
    from elf_abacus.solvers.chain import solve

    puzzle = Puzzle("p", [7, 19, 40], [48611, 1020301, 7340111], 10**9)
    assert solve(puzzle, pool_size=12, max_terms=3, seed=5) == solve(
        puzzle, pool_size=12, max_terms=3, seed=5
    )


def test_shouldReturnNoneWhenThePoolCannotFitInTheRegisters():
    from elf_abacus.solvers.chain import solve

    puzzle = Puzzle("p", [7, 19, 40], [48611], 10**9, registers=4)
    assert solve(puzzle, pool_size=16, max_terms=3, seed=1) is None


def test_shouldReplayEveryDepthThreeCodeWhenDecoding():
    pool = [5, 9, 22, 30]
    forward = build_forward(pool, 10**7, depth=3)
    assert len(forward) == 4
    for value, code in zip(forward[3].vals.tolist(), forward[3].codes.tolist()):
        assert decode_forward(3, code, pool) == value


def test_shouldSortForwardValuesWhenBuildingAnyDepth():
    for forward in build_forward([5, 9, 22, 30], 10**7, depth=3):
        assert np.all(np.diff(forward.vals) > 0)


def test_shouldCapRowsExtendedWhenForwardLevelWouldBeHuge():
    forward = build_forward([5, 9, 22, 30, 41, 77], 10**9, depth=3, max_rows=50)
    assert len(forward[3].vals) <= 50 * 6 * 6


def test_shouldBuildVerifiedProgramWhenChainHasThreeForwardOperations():
    pool = [7, 19, 40, 101]
    forward = build_forward(pool, 10**9, depth=3)
    sums = build_sums(pool, 3)
    target = ((7 * 19 + 40) * 101 + 19) * 1  # three forward ops then one term
    chain = find_chain(target, pool, 10**9, forward, sums)
    assert chain is not None and chain.cost <= 4
    program = chain_program(chain, pool_regs=[0, 1, 2, 3], acc=4)
    assert verify(Puzzle("p", pool, [target], 10**9), program) == len(program)


def test_shouldSpreadPoolMagnitudesAcrossDecadesWhenTargetsAreLarge():
    import math
    import random

    from elf_abacus.solvers.chain import make_pool

    puzzle = Puzzle("p", [631, 889, 1205, 1563], [10**12, 5 * 10**12], 10**13)
    pool, regs, program = make_pool(puzzle, 30, random.Random(0))
    assert len(pool) == 30 and len(regs) == 30 and len(program) == 26
    decades = {int(math.log10(v)) for v in pool}
    assert len(decades) >= 5


def test_shouldNestResidualPlansWhenOneLevelIsNotEnough():
    """411 over pool [10, 7, 3] with one signed term needs a residual of a residual."""
    pool = [10, 7, 3]
    forward = build_forward(pool, 10**6)
    sums = build_sums(pool, 1)
    assert plan_target(411, pool, 10**6, forward, sums, depth=1, pairs=False) is None
    plan = plan_target(411, pool, 10**6, forward, sums, depth=2, pairs=False)
    assert plan is not None
    program = plan.program(pool_regs=[0, 1, 2], accs=[3, 4, 5])
    assert verify(Puzzle("p", pool, [411], 10**6), program) == plan.cost


PAIR_POOL = [776, 1324, 1429, 53]


def _pair_chain(target, **kwargs):
    forward = build_forward(PAIR_POOL, 10**12, depth=2)
    sums = build_sums(PAIR_POOL, 2)
    return find_pair(target, PAIR_POOL, 10**12, forward, sums, **kwargs)


def _replay(chain, target):
    program = chain_program(chain, pool_regs=[0, 1, 2, 3], acc=4, tmp=5)
    return verify(Puzzle("p", PAIR_POOL, [target], 10**12, registers=8), program)


@pytest.mark.parametrize("sign", [1, -1])
def test_shouldJoinTwoForwardValuesWhenTargetIsTheirSumOrDifference(sign):
    target = 776 * 1324 + sign * 1429 * 53
    chain = _pair_chain(target)
    assert chain is not None and chain.second is not None
    assert chain.cost == 3  # one op per product, one to join them
    assert _replay(chain, target) == 3


def test_shouldAddTailTermsWhenPairIsOffByAPoolValue():
    target = 776 * 1324 + 1429 * 53 + 776
    chain = _pair_chain(target)
    assert chain is not None and chain.second is not None
    assert chain.cost == 4
    assert _replay(chain, target) == 4


def test_shouldReturnNoPairWhenCostBoundIsAlreadyBeaten():
    target = 776 * 1324 + 1429 * 53
    assert _pair_chain(target, max_cost=3) is None
    assert _pair_chain(target, max_cost=4) is not None


def test_shouldReturnNoPairWhenNoTwoForwardValuesReachTheTarget():
    assert _pair_chain(10**11 + 7) is None


def test_shouldPlanAPairWhenNoNearestForwardValueLeadsToAResidual():
    """Residual planning with one candidate misses 776*1324 + 1429*53; a pair finds it."""
    target = 776 * 1324 + 1429 * 53
    forward = build_forward(PAIR_POOL, 10**12, depth=2)
    sums = build_sums(PAIR_POOL, 1)
    plan = plan_target(target, PAIR_POOL, 10**12, forward, sums, candidates=1, depth=1)
    assert plan is not None and plan.cost == 3
    program = plan.program(pool_regs=[0, 1, 2, 3], accs=[4, 5])
    puzzle = Puzzle("p", PAIR_POOL, [target], 10**12, registers=8)
    assert verify(puzzle, program) == 3


def test_shouldStillFindAnExactPairWhenThePairBudgetIsTiny():
    """A small budget narrows the window around the target but keeps exact pairs findable."""
    target = 776 * 1324 + 1429 * 53
    chain = _pair_chain(target, max_pairs=1)
    assert chain is not None and chain.cost == 3
    assert _replay(chain, target) == 3


@pytest.mark.parametrize("pairs", [True, False])
def test_shouldProduceVerifiedProgramWhenSolvingWithOrWithoutPairs(pairs):
    from elf_abacus.solvers.chain import solve

    puzzle = Puzzle("p", [7, 19, 40], [48611, 902113], 10**9)
    program = solve(puzzle, pool_size=12, seed=1, pairs=pairs)
    assert program is not None
    assert verify(puzzle, program) == len(program)


@pytest.mark.parametrize("rebuild_every", [1, 3])
def test_shouldProduceVerifiedProgramWhenPoolGrowsFromSolvedTargets(rebuild_every):
    from elf_abacus.solvers.chain import solve

    puzzle = Puzzle("p", [7, 19, 40], [48611, 902113, 55_000_001, 77_123_456], 10**9)
    program = solve(puzzle, pool_size=8, seed=1, grow=True, rebuild_every=rebuild_every)
    assert program is not None
    assert verify(puzzle, program) == len(program)


def test_shouldWriteSolvedTargetsToDistinctRegistersWhenPoolGrows():
    from elf_abacus.solvers.chain import solve

    puzzle = Puzzle("p", [7, 19, 40], [48611, 902113, 55_000_001], 10**9)
    program = solve(puzzle, pool_size=8, seed=1, grow=True, rebuild_every=1)
    assert program is not None
    regs = dict(enumerate(puzzle.starting_values))
    for op, i, j, d in program:
        a, b = regs[i], regs[j]
        regs[d] = {"+": a + b, "*": a * b, "-": a - b, "/": a // b if b else 0}[op]
    # every target still sits in some register at the end: none was overwritten
    assert all(t in regs.values() for t in puzzle.targets)

# a + (y * p) with y a forward value: the second term is one level deeper than any stored set
PRODUCT_TARGET = 776 + (776 * 1324 + 1429) * 53


def _product_chain(target, **kwargs):
    forward = build_forward(PAIR_POOL, 10**12, depth=2)
    sums = build_sums(PAIR_POOL, 2)
    return find_product_pair(target, PAIR_POOL, 10**12, forward, sums, **kwargs)


def test_shouldFindProductPairWhenTargetIsAPoolValuePlusAForwardValueTimesAPoolValue():
    pair = _pair_chain(
        PRODUCT_TARGET
    )  # no stored forward set is deep enough for cost 4
    assert pair is None or pair.cost > 4
    chain = _product_chain(PRODUCT_TARGET)
    assert chain is not None and chain.second is not None
    assert chain.cost == 4  # y costs 2, the product 1, the join 1
    assert _replay(chain, PRODUCT_TARGET) == 4


def test_shouldFindProductPairWhenTargetIsTheProductMinusAPoolValue():
    target = (776 * 1324 + 1429) * 53 - 1324
    chain = _product_chain(target)
    assert chain is not None
    assert _replay(chain, target) == chain.cost == 4


def test_shouldFindProductPairWhenTheSecondTermIsAQuotient():
    pool = [776, 1324, 1429, 53]
    forward = build_forward(pool, 10**12, depth=2)
    sums = build_sums(pool, 2)
    target = 1429 + (776 * 1324 * 53) // 53 + 1324  # y // 53 with y = 776*1324*53
    chain = find_product_pair(target, pool, 10**12, forward, sums)
    assert chain is not None
    program = chain_program(chain, pool_regs=[0, 1, 2, 3], acc=4, tmp=5)
    assert (
        verify(Puzzle("p", pool, [target], 10**12, registers=8), program) == chain.cost
    )


def test_shouldAddTailTermsWhenProductPairIsOffByAPoolValue():
    target = PRODUCT_TARGET + 1429
    chain = _product_chain(target)
    assert chain is not None and chain.cost == 5
    assert _replay(chain, target) == 5


def test_shouldReturnNoProductPairWhenCostBoundIsAlreadyBeaten():
    assert _product_chain(PRODUCT_TARGET, max_cost=4) is None
    assert _product_chain(PRODUCT_TARGET, max_cost=5) is not None


def test_shouldReturnNoProductPairWhenNothingReachesTheTarget():
    assert _product_chain(10**11 + 7) is None


def test_shouldPlanTheProductPairWhenItIsTheCheapestWay():
    forward = build_forward(PAIR_POOL, 10**12, depth=2)
    sums = build_sums(PAIR_POOL, 1)
    plan = plan_target(PRODUCT_TARGET, PAIR_POOL, 10**12, forward, sums, depth=1)
    assert plan is not None and plan.cost <= 4
    program = plan.program(pool_regs=[0, 1, 2, 3], accs=[4, 5])
    puzzle = Puzzle("p", PAIR_POOL, [PRODUCT_TARGET], 10**12, registers=8)
    assert verify(puzzle, program) == plan.cost
