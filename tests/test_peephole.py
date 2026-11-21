import random

from elf_abacus.peephole import optimize
from elf_abacus.verifier import Puzzle, verify


def test_shouldDropInstructionWhenItsResultIsNeverUsedNorATarget():
    puzzle = Puzzle("p", [2, 3], [5], 1000)
    program = [["*", 0, 1, 2], ["+", 0, 1, 3]]
    out = optimize(puzzle, program)
    assert [ins[0] for ins in out] == ["+"]
    verify(puzzle, out)


def test_shouldDropRecomputationWhenValueAlreadyProduced():
    puzzle = Puzzle("p", [2, 3], [5, 10], 1000)
    program = [["+", 0, 1, 2], ["+", 1, 0, 3], ["+", 2, 3, 4]]
    out = optimize(puzzle, program)
    assert len(out) == 2
    verify(puzzle, out)


def test_shouldDropInstructionWhenTargetEqualsAStartingValue():
    puzzle = Puzzle("p", [2, 3], [3, 5], 1000)
    program = [["+", 0, 1, 2], ["*", 0, 1, 3]]
    out = optimize(puzzle, program)
    assert [ins[0] for ins in out] == ["+"]
    verify(puzzle, out)


def test_shouldDropHelperWhenConsumersHaveCheaperDerivations():
    # 4 = 1+3 only feeds 6 and 7, which 3+3 and 6+1 also reach.
    puzzle = Puzzle("p", [1, 2, 3], [6, 7], 1000)
    program = [["+", 0, 2, 3], ["+", 3, 1, 4], ["+", 3, 2, 5]]
    out = optimize(puzzle, program)
    assert len(out) == 2
    verify(puzzle, out)


def test_shouldReturnInputWhenNothingCanBeRemoved():
    puzzle = Puzzle("p", [2, 3], [5], 1000)
    program = [["+", 0, 1, 2]]
    assert optimize(puzzle, program) == program


def test_shouldFitRegistersWhenKeptValuesAreReallocated():
    puzzle = Puzzle("p", [2, 3], [5, 7, 12], 1000, registers=4)
    program = [["+", 0, 1, 2], ["*", 2, 2, 3], ["+", 0, 2, 3], ["+", 2, 3, 2]]
    out = optimize(puzzle, program)
    verify(puzzle, out)
    assert len(out) <= len(program)


def test_shouldNeverLengthenOrBreakRandomPrograms():
    rng = random.Random(7)
    for n in range(300):
        starts = [rng.randint(1, 9) for _ in range(3)]
        regs = dict(enumerate(starts))
        program = []
        for _ in range(rng.randint(1, 14)):
            i, j = rng.choice(list(regs)), rng.choice(list(regs))
            op = rng.choice("+*")
            d = rng.randint(0, 7)
            regs[d] = regs[i] + regs[j] if op == "+" else regs[i] * regs[j]
            program.append([op, i, j, d])
        produced = {regs[k] for k in regs}
        targets = sorted(rng.sample(sorted(produced), min(2, len(produced))))
        puzzle = Puzzle(f"r{n}", starts, targets, 10**30, registers=8)
        base = verify(puzzle, program)
        out = optimize(puzzle, program)
        assert verify(puzzle, out) <= base


def test_shouldKeepHelperWhenRemovingItWouldNotFitInRegisters():
    from elf_abacus import peephole

    puzzle = Puzzle("p", [1, 2, 3], [6, 7], 1000)
    program = [["+", 0, 2, 3], ["+", 3, 1, 4], ["+", 3, 2, 5]]
    nodes = peephole._build_dag(puzzle, program)
    roots = {nodes_index for nodes_index, n in enumerate(nodes) if n.value in (6, 7)}
    live = peephole._reachable(nodes, roots)
    kept = peephole._rederive(nodes, roots, live, fits=lambda _live: False)
    assert kept == live
