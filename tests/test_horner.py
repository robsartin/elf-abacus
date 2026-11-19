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


CLUSTERED = Puzzle(
    "clustered",
    [5, 9, 22, 30, 32],
    [
        3000000011123, 3000000011910, 3000000012321, 3000000012838, 3000000013695,
        3000000014512, 700000000000517, 700000000001209, 700000000001388,
        700000000002014, 700000000002419, 700000000003233,
    ],
    10**15,
)  # fmt: skip


def test_shouldBuildClusteredTargetsFromEarlierOnesWhenTheyDifferByLittle():
    """Direct Horner needs 159 instructions here (anchors reach 75); require under 90."""
    program = solve(CLUSTERED)
    assert program is not None
    assert verify(CLUSTERED, program) < 90
