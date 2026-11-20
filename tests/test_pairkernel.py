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


def _lazy_reference(v, pool, b, short, target, kind, width, limit, max_nterms):
    """Brute force: every (a value, b index, short index) of a = op(v, r) over all ops."""
    table = {int(x): i for i, x in enumerate(short.vals)}
    found = []
    for x in v.tolist():
        for r in pool:
            for a in (
                x + r if x + r <= limit else None,
                x * r if x * r <= limit else None,
                x - r if x > r else None,
                r - x if r > x else None,
                x // r if x % r == 0 else None,
                r // x if r % x == 0 else None,
            ):
                if a is None:
                    continue
                for ib, y in enumerate(b.tolist()):
                    base = (
                        a + y
                        if kind == PAIR_ADD
                        else a - y
                        if kind == PAIR_SUB
                        else y - a
                    )
                    gap = target - base
                    si = table.get(gap)
                    if (
                        si is not None
                        and 1 <= base <= limit
                        and abs(gap) <= width
                        and short.nterms[si] <= max_nterms
                    ):
                        found.append((a, ib, si))
    return sorted(found)


@needs_native
@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("seed", range(6))
def test_shouldMatchBruteForceWhenExtendingForwardValuesLazily(kind, seed):
    rng = np.random.default_rng(100 + seed)
    pool = [int(x) for x in rng.integers(2, 40, size=6)]
    v = np.unique(rng.integers(1, 600, size=60))
    b = np.unique(rng.integers(1, 800, size=25))
    short_vals = np.unique(rng.integers(-30, 30, size=25))
    nt = rng.integers(0, 3, size=len(short_vals)).astype(np.int64)
    short = ShortSums(short_vals, nt, np.arange(len(short_vals)))
    target = int(rng.integers(50, 900))
    got = pairkernel.lazy_hits_native(
        v, np.array(pool), b, short, target, kind, 30, 10**6, 2
    )
    reproduced = []
    for iv, op, k, ib, si in zip(got.ia, got.op, got.k, got.ib, got.si):
        x, r = int(v[iv]), pool[k]
        value = (x + r, x * r, x - r, r - x, x // r, r // x)[op]
        reproduced.append((value, int(ib), int(si)))
    want = _lazy_reference(v, pool, b, short, target, kind, 30, 10**6, 2)
    assert sorted(reproduced) == want


@needs_native
def test_shouldFindAHitWhenAnExtendedValueMeetsTheTargetExactly():
    """v=10 with pool 3 gives 13 (x+r); 13 + 7 = 20 with the empty tail (a short sum of 0)."""
    short = ShortSums(np.array([0]), np.array([0]), np.array([0]))
    got = pairkernel.lazy_hits_native(
        np.array([10]), np.array([3]), np.array([7]), short, 20, PAIR_ADD, 2, 10**6, 2
    )
    assert (int(got.ia[0]), int(got.op[0]), int(got.k[0])) == (0, 0, 0)


@needs_native
def test_shouldJoinALazilyExtendedValueToAForwardValueWhenTargetNeedsOneMoreOperation():
    from elf_abacus.solvers.chain import (
        build_forward,
        build_sums,
        chain_program,
        find_pair_lazy,
    )
    from elf_abacus.verifier import Puzzle, verify

    pool = [776, 1324, 1429, 53]
    target = ((776 * 1324 + 53) * 1429) + 53  # three forward ops, then + a pool value
    forward = build_forward(pool, 10**12, depth=2)
    sums = build_sums(pool, 2)
    chain = find_pair_lazy(target, pool, 10**12, forward, sums)
    assert chain is not None and chain.level == 3 and chain.second is not None
    assert chain.cost <= 4
    program = chain_program(chain, pool_regs=[0, 1, 2, 3], acc=4, tmp=5)
    assert (
        verify(Puzzle("p", pool, [target], 10**12, registers=8), program) == chain.cost
    )
