from elf_abacus.crossover import (
    crossover,
    derivations,
    merge_derivations,
    refine_by_cost,
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
