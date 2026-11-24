import dataclasses
import itertools

import pytest

from elf_abacus.peephole import one_op_from, rematerialize
from elf_abacus.verifier import InvalidProgram, Puzzle, verify

VALUES = [5, 6, 7, 9, 11]


def _wide_puzzle(registers: int) -> tuple[Puzzle, list[list]]:
    """Five helper values, every pairwise product a target: too wide for a small register file."""
    targets = [a * b for a, b in itertools.combinations(VALUES, 2)]
    puzzle = Puzzle("wide", [2, 3], targets, 10**6, registers=registers)
    program = [["+", 0, 1, 2], ["*", 0, 1, 3], ["+", 0, 2, 4], ["+", 1, 3, 5]]
    program.append(["+", 2, 3, 6])
    regs = [2, 3, 4, 5, 6]
    nxt = 7
    for i, j in itertools.combinations(regs, 2):
        program.append(["*", i, j, nxt])
        nxt += 1
    return puzzle, program


@pytest.mark.parametrize("registers", [5])
def test_shouldFitProgramWhenPeakLiveSetExceedsRealRegisters(registers):
    wide, program = _wide_puzzle(40)
    real = dataclasses.replace(wide, registers=registers)
    verify(wide, program)
    with pytest.raises(InvalidProgram):
        verify(
            real, program
        )  # positive control: the virtual program is illegal for 5 registers

    out = rematerialize(real, program, virtual_registers=40)

    assert out is not None
    assert verify(real, out) == len(out)
    assert len(out) == len(program) + 1  # one helper value is recomputed once


def test_shouldMatchPlainAllocationWhenProgramAlreadyFits():
    wide, program = _wide_puzzle(40)
    out = rematerialize(wide, program, virtual_registers=40)
    assert out is not None
    assert len(out) == len(program)


def test_shouldReturnNoneWhenStartingValuesCannotBeRecomputed():
    wide, program = _wide_puzzle(40)
    tiny = dataclasses.replace(wide, registers=2)
    assert rematerialize(tiny, program, virtual_registers=40) is None


@pytest.mark.parametrize(
    ("resident", "want", "expected_op"),
    [
        ({3, 4}, 7, "+"),
        ({10, 3}, 7, "-"),
        ({7, 2}, 14, "*"),
        ({20, 5}, 4, "/"),
    ],
)
def test_shouldFindOneOpExpressionWhenResidentValuesCombineToTarget(
    resident, want, expected_op
):
    found = one_op_from(resident, want)
    assert found is not None
    op, a, b = found
    assert op == expected_op
    assert {"+": a + b, "-": a - b, "*": a * b, "/": a // b}[op] == want


def test_shouldReturnNoneWhenNoResidentPairProducesValue():
    assert one_op_from({3, 5}, 100) is None
