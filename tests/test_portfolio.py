import pytest

from elf_abacus.portfolio import best_programs
from elf_abacus.verifier import InvalidProgram, Puzzle, verify

PUZZLE = Puzzle("p1", [3], [1, 2, 5, 8], 9)
LONG = [["/", 0, 0, 1], ["-", 0, 1, 2], ["+", 0, 2, 3], ["+", 0, 3, 4], ["+", 0, 0, 5]]
SHORT = [["/", 0, 0, 1], ["-", 0, 1, 2], ["+", 0, 2, 3], ["+", 0, 3, 4]]
BROKEN = [["/", 0, 0, 1]]


def test_shouldKeepShortestWhenSeveralSolversAreValid():
    assert best_programs([PUZZLE], [{"p1": LONG}, {"p1": SHORT}]) == {"p1": SHORT}


def test_shouldSkipCandidateWhenItIsInvalid():
    result = best_programs([PUZZLE], [{"p1": BROKEN}, {"p1": LONG}])
    assert verify(PUZZLE, result["p1"]) <= len(LONG)


def test_shouldSkipSolverWhenItHasNoProgramForPuzzle():
    result = best_programs([PUZZLE], [{}, {"p1": LONG}])
    assert verify(PUZZLE, result["p1"]) <= len(LONG)


def test_shouldRaiseWhenNoCandidateIsValid():
    with pytest.raises(InvalidProgram, match="p1"):
        best_programs([PUZZLE], [{"p1": BROKEN}])


def test_shouldOptimizeWinnerWhenItHasRemovableInstructions():
    padded = [["*", 0, 0, 9], *SHORT]
    result = best_programs([PUZZLE], [{"p1": padded}])
    assert len(result["p1"]) == len(SHORT)
    verify(PUZZLE, result["p1"])
