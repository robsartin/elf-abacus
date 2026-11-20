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

static i64 lower_bound(const i64 *x, i64 n, i64 v) {
    i64 lo = 0, hi = n;
    while (lo < hi) {
        i64 mid = lo + ((hi - lo) >> 1);
        if (x[mid] < v) lo = mid + 1; else hi = mid;
    }
    return lo;
}

static i64 upper_bound(const i64 *x, i64 n, i64 v) {
    i64 lo = 0, hi = n;
    while (lo < hi) {
        i64 mid = lo + ((hi - lo) >> 1);
        if (x[mid] <= v) lo = mid + 1; else hi = mid;
    }
    return lo;
}

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
    i64 total = 0;
    for (i64 i = 0; i < na; i++) {
        i64 c = centre_of(kind, a[i], target);
        total += upper_bound(b, nb, c + width) - lower_bound(b, nb, c - width);
    }
    return total;
}

/* Writes up to `cap` hits as (index in a, index in b, index in the short table) and returns the
 * number of hits found, which may exceed `cap`. */
i64 pair_hits(const i64 *a, i64 na, const i64 *b, i64 nb,
              const i64 *sv, const i64 *snt, i64 ns,
              i64 target, int kind, i64 width, i64 limit, i64 max_nterms,
              i64 *out_ia, i64 *out_ib, i64 *out_si, i64 cap) {
    i64 found = 0;
    for (i64 i = 0; i < na; i++) {
        i64 c = centre_of(kind, a[i], target);
        i64 lo = lower_bound(b, nb, c - width), hi = upper_bound(b, nb, c + width);
        for (i64 j = lo; j < hi; j++) {
            i64 base = base_of(kind, a[i], b[j]);
            if (base < 1 || base > limit) continue;
            i64 gap = target - base;
            i64 s = lower_bound(sv, ns, gap);
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
