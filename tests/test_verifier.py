import pytest

from elf_abacus.verifier import InvalidProgram, Puzzle, verify

WORKED = Puzzle(
    id="example_0001", starting_values=[3], targets=[1, 2, 5, 8], value_limit=9
)
WORKED_PROGRAM = [["/", 0, 0, 1], ["-", 0, 1, 2], ["+", 0, 2, 3], ["+", 0, 3, 4]]


def test_shouldReturnInstructionCountWhenProgramCoversAllTargets():
    """Worked example from the Data page scores 4."""
    assert verify(WORKED, WORKED_PROGRAM) == 4


def test_shouldCountStartingValuesAsCoveredWhenTargetIsAlreadyPresent():
    puzzle = Puzzle("p", [3, 4], [3, 7], 10)
    assert verify(puzzle, [["+", 0, 1, 2]]) == 1


def test_shouldCountEveryInstructionEvenWhenItRunsAfterAllTargetsCovered():
    assert verify(WORKED, WORKED_PROGRAM + [["+", 0, 0, 5]]) == 5


def test_shouldKeepTargetCoveredWhenItsRegisterIsOverwritten():
    program = [
        ["/", 0, 0, 1],
        ["-", 0, 1, 2],
        ["+", 0, 2, 3],
        ["+", 0, 3, 4],
        ["-", 4, 0, 1],
    ]
    assert verify(WORKED, program) == 5


def bad(program, puzzle=WORKED, match=None):
    with pytest.raises(InvalidProgram, match=match):
        verify(puzzle, program)


def test_shouldRejectWhenTargetNeverCovered():
    bad(WORKED_PROGRAM[:3], match="target 8")


def test_shouldRejectWhenSourceRegisterUndefined():
    bad([["+", 0, 9, 1]], match="undefined")


@pytest.mark.parametrize("reg", [-1, 48])
def test_shouldRejectWhenRegisterIndexOutOfRange(reg):
    bad([["+", 0, 0, reg]], match="range")


def test_shouldRejectWhenSubtractionIsNotStrictlyPositive():
    bad([["-", 0, 0, 1]], match="positive")


def test_shouldRejectWhenDivisionIsInexact():
    puzzle = Puzzle("p", [3, 2], [1], 10)
    bad([["/", 0, 1, 2]], puzzle, match="exact")


def test_shouldRejectWhenResultExceedsValueLimit():
    bad([["*", 0, 0, 1], ["+", 1, 0, 2]], match="limit")


def test_shouldRejectWhenOperatorUnknown():
    bad([["%", 0, 0, 1]], match="operator")


def test_shouldRejectWhenInstructionMalformed():
    bad([["+", 0, 0]], match="malformed")


def test_shouldRejectWhenProgramExceedsInstructionLimit():
    puzzle = Puzzle("p", [1], [2], 4)
    bad([["+", 0, 0, 1], ["/", 1, 1, 2]] * 2049, puzzle, match="4096")
