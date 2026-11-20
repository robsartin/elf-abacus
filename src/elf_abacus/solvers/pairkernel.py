"""Window expansion and gap lookup for the pair search, in NumPy and (when a compiler exists) C.

The pair search (``chain.find_pair``) takes every value ``a`` of one sorted forward set, expands
the window of another sorted forward set whose pair value ``a +/- b`` lies within ``width`` of the
target, and looks each gap ``target - pair`` up in a table of short signed sums. That loop is the
hot spot, and NumPy must materialise every candidate pair to run it. ``src/elf_abacus/csrc/pairs.c``
runs the same loop without storing pairs; ``hits_numpy`` is the reference it must match.
Build and fallback rules are in ADR 0007.
"""

from __future__ import annotations

import ctypes
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

PAIR_ADD, PAIR_SUB, PAIR_RSUB = range(3)  # a + b, a - b, b - a
DEFAULT_HIT_CAP = 1 << 20

_SOURCE = Path(__file__).resolve().parent.parent / "csrc" / "pairs.c"
_I64P = ctypes.POINTER(ctypes.c_int64)


@dataclass(frozen=True)
class ShortSums:
    """The signed sums a pair's tail may use, sorted by value; `pos` indexes the full sums."""

    vals: np.ndarray
    nterms: np.ndarray
    pos: np.ndarray


@dataclass(frozen=True)
class LazyHits:
    """Hits whose first value is `op2` applied to `v[ia]` and pool entry `k` (never stored)."""

    ia: np.ndarray  # index into the extended set
    op: np.ndarray  # second operation, the OP2_* codes of chain.py
    k: np.ndarray  # pool index
    ib: np.ndarray  # index into the other set
    si: np.ndarray  # index into the short-sum table


@dataclass(frozen=True)
class PairHits:
    ia: np.ndarray  # index into the small set
    ib: np.ndarray  # index into the large set
    si: np.ndarray  # index into the short-sum table


def _windows(
    a: np.ndarray, b: np.ndarray, target: int, kind: int, width: int
) -> tuple[np.ndarray, np.ndarray]:
    if kind == PAIR_ADD:
        centre = target - a
    elif kind == PAIR_SUB:  # a - b near target  <=>  b near a - target
        centre = a - target
    else:  # b - a near target  <=>  b near target + a
        centre = target + a
    return (
        np.searchsorted(b, centre - width, "left"),
        np.searchsorted(b, centre + width, "right"),
    )


def window_count_numpy(
    a: np.ndarray, b: np.ndarray, target: int, kind: int, width: int
) -> int:
    lo, hi = _windows(a, b, target, kind, width)
    return int((hi - lo).sum())


def hits_numpy(
    a: np.ndarray,
    b: np.ndarray,
    short: ShortSums,
    target: int,
    kind: int,
    width: int,
    limit: int,
    max_nterms: int,
) -> PairHits:
    """Every (a, b, short sum) with `a op b + sum == target`, the pair value in 1..limit."""
    lo, hi = _windows(a, b, target, kind, width)
    count = hi - lo
    total = int(count.sum())
    empty = np.zeros(0, dtype=np.int64)
    if total == 0 or len(short.vals) == 0:
        return PairHits(empty, empty, empty)
    ia = np.repeat(np.arange(len(a)), count)
    ib = lo[ia] + np.arange(total) - (np.cumsum(count) - count)[ia]
    av, bv = a[ia], b[ib]
    base = av + bv if kind == PAIR_ADD else av - bv if kind == PAIR_SUB else bv - av
    gap = target - base
    si = np.minimum(np.searchsorted(short.vals, gap), len(short.vals) - 1)
    ok = (
        (short.vals[si] == gap)
        & (short.nterms[si] <= max_nterms)
        & (base >= 1)
        & (base <= limit)
    )
    hit = np.nonzero(ok)[0]
    return PairHits(ia[hit], ib[hit], si[hit])


# ---------------------------------------------------------------------------- native build


def _cache_dir() -> Path:
    override = os.environ.get("ELF_ABACUS_CACHE")
    if override:
        return Path(override)
    return Path.home() / ".cache" / "elf_abacus"


def _compile(source: Path, dest: Path) -> bool:
    compiler = shutil.which(os.environ.get("CC", "cc"))
    if compiler is None:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    flags = ["-O3", "-shared", "-fPIC"]
    if sys.platform == "darwin":
        flags += ["-undefined", "dynamic_lookup"]
    with tempfile.NamedTemporaryFile(
        dir=dest.parent, suffix=dest.suffix, delete=False
    ) as tmp:
        scratch = Path(tmp.name)
    try:
        result = subprocess.run(
            [compiler, *flags, str(source), "-o", str(scratch)],
            capture_output=True,
            timeout=120,
            check=False,
        )
        if result.returncode != 0:
            return False
        scratch.replace(
            dest
        )  # atomic, so workers racing to build never see a partial file
        return True
    except (OSError, subprocess.SubprocessError):
        return False
    finally:
        scratch.unlink(missing_ok=True)


def _load() -> ctypes.CDLL | None:
    if os.environ.get("ELF_ABACUS_NATIVE", "1") == "0" or not _SOURCE.exists():
        return None
    digest = hashlib.sha256(_SOURCE.read_bytes()).hexdigest()[:16]
    suffix = ".dylib" if sys.platform == "darwin" else ".so"
    lib_path = _cache_dir() / f"pairs-{digest}{suffix}"
    if not lib_path.exists() and not _compile(_SOURCE, lib_path):
        return None
    try:
        lib = ctypes.CDLL(str(lib_path))
    except OSError:
        return None
    i64 = ctypes.c_int64
    lib.pair_count.argtypes = [_I64P, i64, _I64P, i64, i64, ctypes.c_int, i64]
    lib.pair_count.restype = i64
    lib.pair_hits.argtypes = [
        _I64P,
        i64,
        _I64P,
        i64,
        _I64P,
        _I64P,
        i64,
        i64,
        ctypes.c_int,
        i64,
        i64,
        i64,
        _I64P,
        _I64P,
        _I64P,
        i64,
    ]
    lib.pair_hits.restype = i64
    lib.lazy_pair_hits.argtypes = [
        _I64P, i64, _I64P, i64, _I64P, i64, _I64P, _I64P, i64,
        i64, ctypes.c_int, i64, i64, i64,
        _I64P, _I64P, _I64P, _I64P, _I64P, i64,
    ]  # fmt: skip
    lib.lazy_pair_hits.restype = i64
    return lib


_LIB: ctypes.CDLL | None = None
_LIB_TRIED = False


def _lib() -> ctypes.CDLL | None:
    global _LIB, _LIB_TRIED
    if not _LIB_TRIED:
        _LIB, _LIB_TRIED = _load(), True
    return _LIB


def native_available() -> bool:
    return _lib() is not None


def _ptr(x: np.ndarray) -> Any:
    return x.ctypes.data_as(_I64P)


def _i64(x: np.ndarray) -> np.ndarray:
    return np.ascontiguousarray(x, dtype=np.int64)


def window_count_native(
    a: np.ndarray, b: np.ndarray, target: int, kind: int, width: int
) -> int:
    lib = _lib()
    if lib is None:
        raise RuntimeError("native pair kernel unavailable")
    a, b = _i64(a), _i64(b)
    return int(lib.pair_count(_ptr(a), len(a), _ptr(b), len(b), target, kind, width))


def hits_native(
    a: np.ndarray,
    b: np.ndarray,
    short: ShortSums,
    target: int,
    kind: int,
    width: int,
    limit: int,
    max_nterms: int,
    cap: int = DEFAULT_HIT_CAP,
) -> PairHits:
    """Same hits as `hits_numpy`, in the same order; at most `cap` of them are kept."""
    lib = _lib()
    if lib is None:
        raise RuntimeError("native pair kernel unavailable")
    a, b = _i64(a), _i64(b)
    sv, snt = _i64(short.vals), _i64(short.nterms)
    out = np.empty((3, cap), dtype=np.int64)
    found = int(
        lib.pair_hits(
            _ptr(a),
            len(a),
            _ptr(b),
            len(b),
            _ptr(sv),
            _ptr(snt),
            len(sv),
            target,
            kind,
            width,
            limit,
            max_nterms,
            _ptr(out[0]),
            _ptr(out[1]),
            _ptr(out[2]),
            cap,
        )
    )
    kept = min(found, cap)
    return PairHits(out[0, :kept].copy(), out[1, :kept].copy(), out[2, :kept].copy())


def lazy_hits_native(
    v: np.ndarray,
    pool: np.ndarray,
    b: np.ndarray,
    short: ShortSums,
    target: int,
    kind: int,
    width: int,
    limit: int,
    max_nterms: int,
    cap: int = DEFAULT_HIT_CAP,
) -> LazyHits:
    """Hits of `(v op2 pool) kind b` against the short sums, without storing the extended set."""
    lib = _lib()
    if lib is None:
        raise RuntimeError("native pair kernel unavailable")
    v, pool, b = _i64(v), _i64(pool), _i64(b)
    sv, snt = _i64(short.vals), _i64(short.nterms)
    out = np.empty((5, cap), dtype=np.int64)
    found = int(
        lib.lazy_pair_hits(
            _ptr(v), len(v), _ptr(pool), len(pool), _ptr(b), len(b),
            _ptr(sv), _ptr(snt), len(sv),
            target, kind, width, limit, max_nterms,
            *(_ptr(out[i]) for i in range(5)), cap,
        )
    )  # fmt: skip
    kept = min(found, cap)
    rows = [out[i, :kept].copy() for i in range(5)]
    return LazyHits(*rows)
