from elf_abacus.crossover import (
    crossover,
    derivations,
    emit_in_priority_order,
    merge_derivations,
    refine_by_cost,
    search_orders,
)
from elf_abacus.verifier import Puzzle, verify

# starts 1, 2; targets 6 and 7. WASTEFUL builds 7 through the long chain 4, 5; CHEAP shares 3 and 4.
PUZZLE = Puzzle("p1", [1, 2], [6, 7], 100)
WASTEFUL = [
    ["+", 0, 1, 2],  # 3
    ["*", 2, 0, 3],  # 3 (again)
    ["+", 2, 2, 4],  # 6
    ["+", 1, 1, 5],  # 4
    ["+", 5, 0, 6],  # 5
    ["+", 6, 1, 7],  # 7
]
CHEAP = [
    ["+", 0, 1, 2],  # 3
    ["+", 1, 1, 3],  # 4
    ["+", 2, 2, 4],  # 6
    ["+", 3, 2, 5],  # 7
]


def test_shouldListEveryDistinctDerivationWhenProgramsDiffer():
    """derivations pools how each value was made across all candidate programs."""
    pool = derivations(PUZZLE, [WASTEFUL, CHEAP])
    assert pool[7] == {("+", 5, 2), ("+", 4, 3)}
    assert pool[6] == {("+", 3, 3)}


def test_shouldAdoptCheaperDerivationWhenAnotherCandidateHasIt():
    """merge_derivations moves 7 onto the candidate that shares 3 and 4."""
    pool = derivations(PUZZLE, [WASTEFUL, CHEAP])
    merged = merge_derivations(PUZZLE, WASTEFUL, pool)
    assert merged is not None
    assert len(merged) == 4


def test_shouldReturnProgramNoLongerThanBestInputWhenCrossingOver():
    """crossover output is verified and never longer than the best candidate."""
    result = crossover(PUZZLE, [WASTEFUL, CHEAP])
    assert verify(PUZZLE, result) <= len(CHEAP)


def test_shouldIgnoreCandidateWhenItDoesNotVerify():
    """A broken candidate cannot poison the derivation pool."""
    broken = [["-", 0, 1, 2]]
    result = crossover(PUZZLE, [broken, CHEAP])
    assert verify(PUZZLE, result) <= len(CHEAP)


def _prefers_four(plan):
    return 0 if 4 in plan else 1


def test_shouldPickCheaperPlanByCostWhenValueCountsTie():
    """refine_by_cost swaps between equal-size derivations when the supplied cost prefers one."""
    puzzle = Puzzle("p2", [1, 2], [5], 100)
    # 5 = 3 + 2 or 5 = 4 + 1; each needs one helper (3 = 1 + 2, 4 = 2 + 2), so both plans have 2 values.
    pool = {
        3: {("+", 1, 2)},
        4: {("+", 2, 2)},
        5: {("+", 3, 2), ("+", 4, 1)},
    }
    start = {3: ("+", 1, 2), 5: ("+", 3, 2)}
    best = refine_by_cost(puzzle, start, pool, _prefers_four, budget=50)
    assert 4 in best and best[5] == ("+", 4, 1)


def test_shouldKeepPlanWhenNoSwapLowersCost():
    """refine_by_cost never returns a plan costing more than its start."""
    puzzle = Puzzle("p2", [1, 2], [5], 100)
    pool = {3: {("+", 1, 2)}, 5: {("+", 3, 2)}}
    start = {3: ("+", 1, 2), 5: ("+", 3, 2)}
    best = refine_by_cost(puzzle, start, pool, len, budget=50)
    assert best == start


ORDER_PLAN = {3: ("+", 1, 2), 4: ("+", 2, 2), 7: ("+", 3, 4)}
ORDER_PUZZLE = Puzzle("p3", [1, 2], [7], 100)


def test_shouldEmitByPriorityWhenValuesAreIndependent():
    """emit_in_priority_order puts the lower-priority value first among ready values."""
    first = emit_in_priority_order(ORDER_PUZZLE, ORDER_PLAN, {3: 1, 4: 0, 7: 2}.get)
    second = emit_in_priority_order(ORDER_PUZZLE, ORDER_PLAN, {3: 0, 4: 1, 7: 2}.get)
    assert first[0][:2] == [
        "+",
        1,
    ]  # 2 + 2 = 4 first: both operands are starting register 1
    assert second[0] == ["+", 0, 1, 2]  # 1 + 2 = 3 first
    assert verify(ORDER_PUZZLE, first) == verify(ORDER_PUZZLE, second) == 3


def test_shouldKeepOperandsFirstWhenPriorityPutsConsumerEarly():
    """A consumer with the best priority still waits until its operands are emitted."""
    program = emit_in_priority_order(ORDER_PUZZLE, ORDER_PLAN, {3: 5, 4: 6, 7: 0}.get)
    assert verify(ORDER_PUZZLE, program) == 3
    assert program[-1][:3] in (["+", 2, 3], ["+", 3, 2])


def test_shouldNeverReturnWorseThanDefaultWhenSearchingOrders():
    """search_orders keeps the lowest-cost program seen, including the default emission."""
    best = search_orders(ORDER_PUZZLE, ORDER_PLAN, len, tries=5, seed=0)
    assert verify(ORDER_PUZZLE, best) == 3
