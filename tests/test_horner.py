import random

import pytest

from elf_abacus.solvers.horner import decompose, solve
from elf_abacus.verifier import Puzzle, verify


def recompose(top, digits, radix):
    value = top
    for e in digits:
        value = value * radix + e
    return value


@pytest.mark.parametrize("radix", [8, 32, 64])
def test_shouldRecomposeToTargetWhenDecomposingAnyInteger(radix):
    rng = random.Random(1)
    for _ in range(500):
        target = rng.randrange(1, 10**18)
        top, digits = decompose(target, radix)
        assert recompose(top, digits, radix) == target


@pytest.mark.parametrize("radix", [8, 32, 64])
def test_shouldKeepDigitsWithinSignedHalfRadixWhenDecomposing(radix):
    half = radix // 2
    rng = random.Random(2)
    for _ in range(500):
        top, digits = decompose(rng.randrange(1, 10**18), radix)
        assert 1 <= top <= half
        assert all(-half < e <= half for e in digits)


def test_shouldReturnNoDigitsWhenTargetFitsInTopDigit():
    assert decompose(7, 32) == (7, [])


def test_shouldProduceVerifiedProgramWhenTargetsAreLarge():
    rng = random.Random(3)
    targets = sorted(rng.randrange(10**6, 10**15) for _ in range(12))
    puzzle = Puzzle("p", [7, 19, 40], targets, 2 * 10**15)
    program = solve(puzzle)
    assert program is not None
    assert verify(puzzle, program) == len(program)


def test_shouldCostNothingForTargetsAlreadyInStartingValues():
    puzzle = Puzzle("p", [5, 9], [5, 9], 100)
    assert solve(puzzle) == []


def test_shouldReturnNoneWhenNoDigitTableFitsInRegisters():
    puzzle = Puzzle("p", [3], [1, 2, 5, 8], 9, registers=2)
    assert solve(puzzle) is None


def test_shouldReturnNoneWhenEveryTableOverflowsValueLimit():
    puzzle = Puzzle("p", [3], [4, 6], 5)
    assert solve(puzzle) is None
