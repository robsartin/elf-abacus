/* Native kernel for the pair search (see src/elf_abacus/solvers/pairkernel.py).
 *
 * Mirrors the NumPy reference exactly: for every value a of the sorted array A, the window of the
 * sorted array B whose pair value lies within `width` of the target is expanded, and each gap
 * (target - pair value) is looked up in the table of short signed sums. Nothing is stored except
 * the hits, so memory is independent of how many pairs are expanded.
 */
#include <stdint.h>

typedef int64_t i64;

enum { KIND_ADD = 0, KIND_SUB = 1, KIND_RSUB = 2 };

/* First index whose element does not satisfy "x < v" (incl = 0) or "x <= v" (incl = 1), found by
 * galloping out from `hint`. The sorted array A makes consecutive windows move monotonically, so
 * the previous answer is a close hint and the search touches a few cache lines, not log2(n). */
static i64 bound_from(const i64 *x, i64 n, i64 v, int incl, i64 hint) {
    i64 lo, hi, step = 1;
    if (hint > n) hint = n;
    if (hint < n && (incl ? x[hint] <= v : x[hint] < v)) {
        lo = hint + 1;
        hi = lo;
        while (hi < n && (incl ? x[hi] <= v : x[hi] < v)) {
            lo = hi + 1;
            hi += step;
            step <<= 1;
        }
        if (hi > n) hi = n;
    } else {
        hi = hint;
        i64 probe = hi - step;
        while (probe >= 0 && !(incl ? x[probe] <= v : x[probe] < v)) {
            hi = probe;
            step <<= 1;
            probe = hi - step;
        }
        lo = probe < 0 ? 0 : probe + 1;
    }
    while (lo < hi) {
        i64 mid = lo + ((hi - lo) >> 1);
        if (incl ? x[mid] <= v : x[mid] < v) lo = mid + 1; else hi = mid;
    }
    return lo;
}

static i64 lower_bound(const i64 *x, i64 n, i64 v) { return bound_from(x, n, v, 0, n >> 1); }

static inline i64 centre_of(int kind, i64 a, i64 target) {
    if (kind == KIND_ADD) return target - a;
    if (kind == KIND_SUB) return a - target;
    return target + a;
}

static inline i64 base_of(int kind, i64 a, i64 b) {
    if (kind == KIND_ADD) return a + b;
    if (kind == KIND_SUB) return a - b;
    return b - a;
}

i64 pair_count(const i64 *a, i64 na, const i64 *b, i64 nb, i64 target, int kind, i64 width) {
    i64 total = 0, plo = nb >> 1, phi = nb >> 1;
    for (i64 i = 0; i < na; i++) {
        i64 c = centre_of(kind, a[i], target);
        plo = bound_from(b, nb, c - width, 0, plo);
        phi = bound_from(b, nb, c + width, 1, phi);
        total += phi - plo;
    }
    return total;
}

/* Writes up to `cap` hits as (index in a, index in b, index in the short table) and returns the
 * number of hits found, which may exceed `cap`. */
i64 pair_hits(const i64 *a, i64 na, const i64 *b, i64 nb,
              const i64 *sv, const i64 *snt, i64 ns,
              i64 target, int kind, i64 width, i64 limit, i64 max_nterms,
              i64 *out_ia, i64 *out_ib, i64 *out_si, i64 cap) {
    i64 found = 0, lo = nb >> 1, hi = nb >> 1, sh = ns >> 1;
    for (i64 i = 0; i < na; i++) {
        i64 c = centre_of(kind, a[i], target);
        lo = bound_from(b, nb, c - width, 0, lo);
        hi = bound_from(b, nb, c + width, 1, hi);
        for (i64 j = lo; j < hi; j++) {
            i64 base = base_of(kind, a[i], b[j]);
            if (base < 1 || base > limit) continue;
            i64 gap = target - base;
            i64 s = sh = bound_from(sv, ns, gap, 0, sh); /* gaps move monotonically along a window */
            if (s == ns || sv[s] != gap || snt[s] > max_nterms) continue;
            if (found < cap) {
                out_ia[found] = i;
                out_ib[found] = j;
                out_si[found] = s;
            }
            found++;
        }
    }
    return found;
}
