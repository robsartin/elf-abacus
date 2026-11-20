import numpy as np
import pytest

from elf_abacus.solvers import pairkernel
from elf_abacus.solvers.pairkernel import (
    PAIR_ADD,
    PAIR_RSUB,
    PAIR_SUB,
    ShortSums,
    hits_numpy,
    window_count_numpy,
)

needs_native = pytest.mark.skipif(
    not pairkernel.native_available(), reason="no C compiler: NumPy fallback only"
)
KINDS = [PAIR_ADD, PAIR_SUB, PAIR_RSUB]


def _random_case(seed: int):
    rng = np.random.default_rng(seed)
    a = np.unique(rng.integers(1, 5000, size=int(rng.integers(5, 300))))
    b = np.unique(rng.integers(1, 5000, size=int(rng.integers(5, 600))))
    short_vals = np.unique(rng.integers(-60, 60, size=40))
    nterms = rng.integers(0, 3, size=len(short_vals)).astype(np.int64)
    short = ShortSums(short_vals, nterms, np.arange(len(short_vals)) * 3 + 1)
    return a, b, short, int(rng.integers(1, 9000))


def test_shouldCountEveryWindowedPairWhenCountingNumpyReference():
    a = np.array([1, 5, 9])
    b = np.array([2, 4, 6, 8, 10])
    # a + b within 1 of 10: (1: b in 8..10 -> 8,10), (5: b in 4..6 -> 4,6), (9: b in 0..2 -> 2)
    assert window_count_numpy(a, b, 10, PAIR_ADD, 1) == 5


@needs_native
@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("seed", range(8))
def test_shouldMatchNumpyWindowCountWhenRandomInputs(kind, seed):
    a, b, _, target = _random_case(seed)
    for width in (0, 3, 40, 400):
        native = pairkernel.window_count_native(a, b, target, kind, width)
        assert native == window_count_numpy(a, b, target, kind, width)


@needs_native
@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("seed", range(8))
def test_shouldMatchNumpyHitsInScanOrderWhenRandomInputs(kind, seed):
    a, b, short, target = _random_case(seed)
    for limit, max_nterms in ((10**9, 2), (4000, 1), (10**9, 0)):
        want = hits_numpy(a, b, short, target, kind, 60, limit, max_nterms)
        got = pairkernel.hits_native(a, b, short, target, kind, 60, limit, max_nterms)
        np.testing.assert_array_equal(got.ia, want.ia)
        np.testing.assert_array_equal(got.ib, want.ib)
        np.testing.assert_array_equal(got.si, want.si)


@needs_native
def test_shouldStopStoringButKeepCountingWhenHitCapIsExceeded():
    a = np.arange(1, 200)
    b = np.arange(1, 200)
    short = ShortSums(np.arange(-5, 6), np.zeros(11, dtype=np.int64), np.arange(11))
    full = pairkernel.hits_native(a, b, short, 150, PAIR_ADD, 5, 10**9, 2)
    capped = pairkernel.hits_native(a, b, short, 150, PAIR_ADD, 5, 10**9, 2, cap=10)
    assert len(capped.ia) == 10
    np.testing.assert_array_equal(capped.ia, full.ia[:10])


def test_shouldReturnNoHitsWhenWindowsAreEmpty():
    a, b, short, _ = _random_case(1)
    got = hits_numpy(a, b, short, 10**12, PAIR_ADD, 5, 10**9, 2)
    assert len(got.ia) == 0


@needs_native
@pytest.mark.parametrize(
    "target", [987_654, 31_415_926, 5_000_000_011, 777_777_777_777]
)
def test_shouldFindTheSameChainWhenPairSearchRunsNativeOrNumpy(target):
    from elf_abacus.solvers.chain import build_forward, build_sums, find_pair

    pool = [3, 7, 19, 44, 101, 250, 640, 1500, 4100, 9000, 23000, 61000]
    limit = 10**15
    forward = build_forward(pool, limit, depth=2)
    sums = build_sums(pool, 3)
    want = find_pair(target, pool, limit, forward, sums, native=False)
    got = find_pair(target, pool, limit, forward, sums, native=True)
    assert got == want
