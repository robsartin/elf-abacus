import pytest

from elf_abacus import crossover as crossover_module
from elf_abacus.crossover import (
    crossover,
    derivations,
    emit_in_priority_order,
    main,
    merge_derivations,
    refine_by_cost,
    search_orders,
)
from elf_abacus.io import load_submission, write_submission
from elf_abacus.verifier import InvalidProgram, Puzzle, verify

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


def _first_is_four(program):
    return 0 if program[0] == ["+", 1, 1, 2] else 1


def _first_is_three(program):
    return 0 if program[0] == ["+", 0, 1, 2] else 1


def test_shouldFindBetterOrderWhenAPerturbedEmissionCostsLess():
    """The default emits 3 first; a cost preferring 4 first must be reached by a perturbed order."""
    best = search_orders(ORDER_PUZZLE, ORDER_PLAN, _first_is_four, tries=40, seed=0)
    assert _first_is_four(best) == 0
    assert verify(ORDER_PUZZLE, best) == 3


def test_shouldKeepDefaultOrderWhenNoPerturbedEmissionCostsLess():
    """search_orders never returns something costing more than the default emission."""
    default = search_orders(ORDER_PUZZLE, ORDER_PLAN, _first_is_three, tries=0, seed=0)
    best = search_orders(ORDER_PUZZLE, ORDER_PLAN, _first_is_three, tries=40, seed=0)
    assert _first_is_three(default) == 0
    assert best == default


def test_shouldRaiseWhenNoCandidateFitsTheRegisterFile(monkeypatch):
    """When nothing compiles to the real register file and no input fits either, it says so."""
    monkeypatch.setattr(crossover_module, "rematerialize", lambda *args: None)
    monkeypatch.setattr(
        crossover_module,
        "verify",
        lambda puzzle, program: (
            verify(puzzle, program) if puzzle.registers > 2 else _reject()
        ),
    )
    tiny = Puzzle("p1", [1, 2], [6, 7], 100, registers=2)
    with pytest.raises(InvalidProgram, match="fits"):
        crossover(tiny, [CHEAP])


def _reject():
    raise InvalidProgram("does not fit")


def _write_puzzles(path, rows):
    header = "id,starting_values,targets,value_limit,registers\n"
    path.write_text(header + "".join(f"{r}\n" for r in rows))


P1_ROW = 'p1,"[1, 2]","[6, 7]",100,48'
P2_ROW = 'p2,"[1, 2]","[6, 7]",100,48'


def test_shouldWriteCrossedProgramsWhenRunFromTheCommandLine(tmp_path, capsys):
    puzzles = tmp_path / "puzzles.csv"
    _write_puzzles(puzzles, [P1_ROW])
    write_submission(tmp_path / "a.csv", {"p1": WASTEFUL})
    write_submission(tmp_path / "b.csv", {"p1": CHEAP})
    out = tmp_path / "out.csv"
    main(
        ["--puzzles", str(puzzles), "--out", str(out)]
        + [str(tmp_path / "a.csv"), str(tmp_path / "b.csv")]
    )
    result = load_submission(out)
    assert verify(PUZZLE, result["p1"]) <= len(CHEAP)
    assert str(len(result["p1"])) in capsys.readouterr().out


def test_shouldFailBeforeSearchingWhenAPuzzleHasNoCandidate(tmp_path):
    """A gap in the inputs is reported up front, not after hours of search."""
    puzzles = tmp_path / "puzzles.csv"
    _write_puzzles(puzzles, [P1_ROW, P2_ROW])
    write_submission(tmp_path / "a.csv", {"p1": CHEAP})
    out = tmp_path / "out.csv"
    with pytest.raises(SystemExit, match="p2"):
        main(["--puzzles", str(puzzles), "--out", str(out), str(tmp_path / "a.csv")])
    assert not out.exists()
