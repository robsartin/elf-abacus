import pytest

from elf_abacus.portfolio import best_programs
from elf_abacus.verifier import InvalidProgram, Puzzle

PUZZLE = Puzzle("p1", [3], [1, 2, 5, 8], 9)
LONG = [["/", 0, 0, 1], ["-", 0, 1, 2], ["+", 0, 2, 3], ["+", 0, 3, 4], ["+", 0, 0, 5]]
SHORT = [["/", 0, 0, 1], ["-", 0, 1, 2], ["+", 0, 2, 3], ["+", 0, 3, 4]]
BROKEN = [["/", 0, 0, 1]]


def test_shouldKeepShortestWhenSeveralSolversAreValid():
    assert best_programs([PUZZLE], [{"p1": LONG}, {"p1": SHORT}]) == {"p1": SHORT}


def test_shouldSkipCandidateWhenItIsInvalid():
    assert best_programs([PUZZLE], [{"p1": BROKEN}, {"p1": LONG}]) == {"p1": LONG}


def test_shouldSkipSolverWhenItHasNoProgramForPuzzle():
    assert best_programs([PUZZLE], [{}, {"p1": LONG}]) == {"p1": LONG}


def test_shouldRaiseWhenNoCandidateIsValid():
    with pytest.raises(InvalidProgram, match="p1"):
        best_programs([PUZZLE], [{"p1": BROKEN}])
