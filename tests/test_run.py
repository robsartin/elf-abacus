from elf_abacus.router import ChainRun
from elf_abacus.run import _run_chain
from elf_abacus.verifier import Puzzle, verify


def _puzzle(registers: int) -> Puzzle:
    return Puzzle(
        "p",
        [1, 2, 3, 5, 7, 11],
        [101, 239, 377, 512, 689, 733, 851, 997],
        10**6,
        registers=registers,
    )


def test_shouldReturnProgramLegalForRealRegistersWhenPlannedOnVirtualOnes():
    puzzle = _puzzle(14)
    run = ChainRun(
        6, True, 0, grow=True, relate=True, keep_inner=True, retain=True, virtual=64
    )
    program = _run_chain(puzzle, run)
    assert program is not None
    verify(puzzle, program)
    assert all(r < puzzle.registers for ins in program for r in ins[1:])
