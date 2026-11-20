"""Meet-in-the-middle linear-chain search.

Every target is built as one short chain over a fixed *pool* of registers: a forward part of up
to two operations (``pool op pool [op pool]``) followed by signed additions of pool values. The
forward values and the signed sums are enumerated once per puzzle and matched against each target
with a sorted-array lookup, so finding a chain is a vectorised ``target - forward in sums`` test.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

import numpy as np

from elf_abacus.verifier import Puzzle

ADD, MUL, SUB, DIV = range(4)
SYMBOL = "+*-/"
OP2_ADD, OP2_MUL, OP2_SUBA, OP2_SUBB, OP2_DIVA, OP2_DIVB = range(6)
_TERM_BITS = 7


@dataclass(frozen=True)
class Forward:
    """Values reachable by a fixed number of forward operations, with a replayable code each."""

    vals: np.ndarray
    codes: np.ndarray


@dataclass(frozen=True)
class Sums:
    """Signed sums of pool values, sorted by value, each with its fewest-terms recipe."""

    vals: np.ndarray
    codes: np.ndarray
    nterms: np.ndarray


PAIR_ADD, PAIR_SUB, PAIR_RSUB = range(3)  # a + b, a - b, b - a
MAX_PAIRS = 4_000_000  # candidate pairs expanded per search, which bounds memory
PAIR_TERMS = (
    2  # tail terms a pair may add; also bounds the window searched around the target
)


@dataclass(frozen=True)
class Chain:
    level: int  # forward operations before the additive tail (0, 1, 2 or 3)
    code: int
    terms: list[tuple[int, int]]  # (sign, pool index), additions first
    cost: int
    second: tuple[int, int, int] | None = (
        None  # (pair kind, level, code) of a second forward value
    )


def _dedupe(vals: np.ndarray, *carried: np.ndarray) -> tuple[np.ndarray, ...]:
    _, first = np.unique(vals, return_index=True)
    return (vals[first], *(c[first] for c in carried))


def _second_op(prev: Forward, p: np.ndarray, limit: int) -> Forward:
    """Extend every value of `prev` by one more operation with a pool value."""
    v = prev.vals[:, None]
    r = p[None, :]
    k = np.arange(len(p), dtype=np.int64)
    safe_r = np.maximum(r, 1)
    safe_v = np.maximum(v, 1)
    second = [
        (OP2_ADD, v + r <= limit, v + r),
        (OP2_MUL, v <= limit // safe_r, v * np.where(v <= limit // safe_r, r, 0)),
        (OP2_SUBA, v > r, v - r),
        (OP2_SUBB, r > v, r - v),
        (OP2_DIVA, v % safe_r == 0, v // safe_r),
        (OP2_DIVB, r % safe_v == 0, r // safe_v),
    ]
    vals, codes = [], []
    for op, mask, value in second:
        rows, cols = np.nonzero(mask)
        vals.append(value[rows, cols])
        codes.append(((prev.codes[rows] * 8 + op) * 64) + k[cols])
    return Forward(*_dedupe(np.concatenate(vals), np.concatenate(codes)))


def build_forward(
    pool: list[int], limit: int, depth: int = 2, max_rows: int = 200_000
) -> tuple[Forward, ...]:
    """Forward sets with 0..`depth` operations over `pool`, values in 1..limit, sorted by value.

    A level is extended from at most `max_rows` evenly spaced values of the level below, which
    bounds the size of deep levels.
    """
    p = np.array(pool, dtype=np.int64)
    n = len(p)
    f0 = Forward(p.copy(), np.arange(n, dtype=np.int64))

    ii, jj = (a.ravel() for a in np.meshgrid(np.arange(n), np.arange(n), indexing="ij"))
    x, y = p[ii], p[jj]
    parts = [
        (ADD, (ii <= jj) & (x + y <= limit), x + y),
        (MUL, (ii <= jj) & (x <= limit // y), x * np.where(x <= limit // y, y, 0)),
        (SUB, x > y, x - y),
        (DIV, x % y == 0, x // y),
    ]
    vals, codes = [], []
    for op, mask, value in parts:
        vals.append(value[mask])
        codes.append((op * 64 + ii[mask]) * 64 + jj[mask])
    levels = [f0, Forward(*_dedupe(np.concatenate(vals), np.concatenate(codes)))]
    for _ in range(2, depth + 1):
        prev = levels[-1]
        if len(prev.vals) > max_rows:
            keep = np.linspace(0, len(prev.vals) - 1, max_rows).astype(np.int64)
            prev = Forward(prev.vals[keep], prev.codes[keep])
        levels.append(_second_op(prev, p, limit))
    return tuple(levels[: depth + 1])


def _apply1(op: int, a: int, b: int) -> int:
    return (a + b, a * b, a - b, a // b)[op]


def decode_forward(level: int, code: int, pool: list[int]) -> int:
    """Replay a forward code to its value (the reference the vectorised build must match)."""
    if level == 0:
        return pool[code]
    if level == 1:
        op, rest = divmod(code, 64 * 64)
        i, j = divmod(rest, 64)
        return _apply1(op, pool[i], pool[j])
    first, op2, k = code >> 9, (code >> 6) & 7, code & 63
    v, r = decode_forward(level - 1, first, pool), pool[k]
    return (v + r, v * r, v - r, r - v, v // r, r // v)[op2]


def build_sums(pool: list[int], max_terms: int) -> Sums:
    """All signed sums of at most `max_terms` pool values, deduplicated by value."""
    p = np.array(pool, dtype=np.int64)
    n = len(p)
    ids = np.arange(2 * n, dtype=np.int64)
    signed = np.where(ids % 2 == 0, p[ids // 2], -p[ids // 2])
    level_vals = np.zeros(1, dtype=np.int64)
    level_codes = np.zeros(1, dtype=np.int64)
    all_vals, all_codes, all_n = (
        [level_vals],
        [level_codes],
        [np.zeros(1, dtype=np.int64)],
    )
    for t in range(1, max_terms + 1):
        nv = (level_vals[:, None] + signed[None, :]).ravel()
        nc = ((level_codes[:, None] << _TERM_BITS) + ids[None, :]).ravel()
        level_vals, level_codes = _dedupe(nv, nc)
        all_vals.append(level_vals)
        all_codes.append(level_codes)
        all_n.append(np.full(len(level_vals), t, dtype=np.int64))
    vals, codes, nterms = (np.concatenate(a) for a in (all_vals, all_codes, all_n))
    order = np.lexsort((nterms, vals))
    vals, codes, nterms = vals[order], codes[order], nterms[order]
    keep = np.concatenate(([True], vals[1:] != vals[:-1]))
    return Sums(vals[keep], codes[keep], nterms[keep])


def decode_terms(code: int, nterms: int) -> list[tuple[int, int]]:
    """Signed pool indices of a sum code, in the order they were added."""
    terms = []
    for pos in range(nterms):
        ident = (code >> (_TERM_BITS * (nterms - 1 - pos))) & ((1 << _TERM_BITS) - 1)
        terms.append((1 if ident % 2 == 0 else -1, ident // 2))
    return terms


def _matches(fw: Forward, sums: Sums, target: int) -> tuple[np.ndarray, np.ndarray]:
    """Index pairs (forward, sum) with forward + sum == target, iterating the smaller set."""
    if len(fw.vals) <= len(sums.vals):
        wanted = target - fw.vals
        pos = np.searchsorted(sums.vals, wanted)
        pos[pos == len(sums.vals)] = len(sums.vals) - 1
        hit = np.nonzero(sums.vals[pos] == wanted)[0]
        return hit, pos[hit]
    wanted = target - sums.vals
    pos = np.searchsorted(fw.vals, wanted)
    pos[pos == len(fw.vals)] = len(fw.vals) - 1
    hit = np.nonzero(fw.vals[pos] == wanted)[0]
    return pos[hit], hit


def find_chain(
    target: int,
    pool: list[int],
    limit: int,
    forward: tuple[Forward, ...],
    sums: Sums,
    max_cost: int | None = None,
) -> Chain | None:
    """Cheapest legal chain costing less than `max_cost`, or None if there is none."""
    best: Chain | None = None
    bound = max_cost if max_cost is not None else 1 << 30
    for level, fw in enumerate(forward):
        if level >= bound:
            break
        f_idx, s_idx = _matches(fw, sums, target)
        if len(f_idx) == 0:
            continue
        costs = level + sums.nterms[s_idx]
        for h in np.argsort(costs, kind="stable")[:25]:
            cost = int(costs[h])
            if cost >= bound:
                break
            nterms = int(sums.nterms[s_idx[h]])
            terms = decode_terms(int(sums.codes[s_idx[h]]), nterms)
            terms.sort(key=lambda t: -t[0])  # additions first keeps every step positive
            running = int(fw.vals[f_idx[h]])
            legal = True
            for sign, idx in terms:
                running += sign * pool[idx]
                legal = legal and running <= limit
            if legal:
                best = Chain(level, int(fw.codes[f_idx[h]]), terms, cost)
                bound = cost
                break
    return best


def _pair_windows(
    a: np.ndarray, b: np.ndarray, target: int, kind: int, width: int
) -> tuple[np.ndarray, np.ndarray]:
    """For each a, the slice of sorted `b` whose pair value lies within `width` of the target."""
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


def find_pair(
    target: int,
    pool: list[int],
    limit: int,
    forward: tuple[Forward, ...],
    sums: Sums,
    max_cost: int | None = None,
    max_pairs: int = MAX_PAIRS,
) -> Chain | None:
    """Cheapest `a +/- b + tail` over two forward values, or None if none costs under `max_cost`.

    Two forward sets of a few operations each hold far more combinations than one forward set
    times a short sum, so a near-miss pair plus one or two pool terms usually exists. For every
    value of the smaller set only the window of the larger set that can land within the tail's
    reach of the target is expanded, then each candidate gap is looked up in the sums.
    """
    bound = max_cost if max_cost is not None else 1 << 30
    short = sums.nterms <= PAIR_TERMS
    width = int(sums.vals[short].max())
    best: Chain | None = None
    levels = sorted(
        ((la, lb) for la in range(len(forward)) for lb in range(la, len(forward))),
        key=lambda pair: pair[0] + pair[1],
    )
    for la, lb in levels:
        if la + lb + 1 >= bound:
            break
        small, large = forward[la], forward[lb]
        kinds = (PAIR_ADD, PAIR_SUB) if la == lb else (PAIR_ADD, PAIR_SUB, PAIR_RSUB)
        for kind in kinds:
            reach = width
            lo, hi = _pair_windows(small.vals, large.vals, target, kind, reach)
            while int((hi - lo).sum()) > max_pairs and reach > 0:
                reach //= 4  # a dense region: look only at pairs nearest the target
                lo, hi = _pair_windows(small.vals, large.vals, target, kind, reach)
            count = hi - lo
            total = int(count.sum())
            if total == 0:
                continue
            ia = np.repeat(np.arange(len(small.vals)), count)
            ib = lo[ia] + np.arange(total) - (np.cumsum(count) - count)[ia]
            av, bv = small.vals[ia], large.vals[ib]
            base = (
                av + bv
                if kind == PAIR_ADD
                else av - bv
                if kind == PAIR_SUB
                else bv - av
            )
            gap = target - base
            pos = np.minimum(np.searchsorted(sums.vals, gap), len(sums.vals) - 1)
            ok = (sums.vals[pos] == gap) & short[pos] & (base >= 1) & (base <= limit)
            hits = np.nonzero(ok)[0]
            for h in hits[np.argsort(sums.nterms[pos[hits]], kind="stable")[:25]]:
                cost = la + lb + 1 + int(sums.nterms[pos[h]])
                if cost >= bound:
                    break
                nterms = int(sums.nterms[pos[h]])
                terms = decode_terms(int(sums.codes[pos[h]]), nterms)
                terms.sort(key=lambda t: -t[0])
                running = int(base[h])
                legal = True
                for sign, idx in terms:
                    running += sign * pool[idx]
                    legal = legal and running <= limit
                if legal:
                    code_a, code_b = int(small.codes[ia[h]]), int(large.codes[ib[h]])
                    best = Chain(la, code_a, terms, cost, (kind, lb, code_b))
                    bound = cost
                    break
    return best


_SECOND_OPS = (
    lambda acc, rk: ["+", acc, rk, acc],
    lambda acc, rk: ["*", acc, rk, acc],
    lambda acc, rk: ["-", acc, rk, acc],
    lambda acc, rk: ["-", rk, acc, acc],
    lambda acc, rk: ["/", acc, rk, acc],
    lambda acc, rk: ["/", rk, acc, acc],
)


def _forward_ops(level: int, code: int, pool_regs: list[int], acc: int) -> list[list]:
    if level == 0:
        return []
    if level == 1:
        op, rest = divmod(code, 64 * 64)
        i, j = divmod(rest, 64)
        return [[SYMBOL[op], pool_regs[i], pool_regs[j], acc]]
    ops = _forward_ops(level - 1, code >> 9, pool_regs, acc)
    return [*ops, _SECOND_OPS[(code >> 6) & 7](acc, pool_regs[code & 63])]


def chain_program(
    chain: Chain, pool_regs: list[int], acc: int, tmp: int | None = None
) -> list[list]:
    """Instructions for `chain`, accumulating in register `acc` (pool registers are read-only).

    A pair chain builds its second forward value in `tmp` and then joins the two into `acc`.
    """
    ops = _forward_ops(chain.level, chain.code, pool_regs, acc)
    cur = pool_regs[chain.code] if chain.level == 0 else acc
    if chain.second is not None:
        if tmp is None:
            raise ValueError("a pair chain needs a temporary register")
        kind, level_b, code_b = chain.second
        ops += _forward_ops(level_b, code_b, pool_regs, tmp)
        other = pool_regs[code_b] if level_b == 0 else tmp
        if kind == PAIR_ADD:
            ops.append(["+", cur, other, acc])
        elif kind == PAIR_SUB:
            ops.append(["-", cur, other, acc])
        else:
            ops.append(["-", other, cur, acc])
        cur = acc
    for sign, idx in chain.terms:
        ops.append(["+" if sign > 0 else "-", cur, pool_regs[idx], acc])
        cur = acc
    return ops


def chain_result_reg(chain: Chain, pool_regs: list[int], acc: int) -> int:
    """Register holding the chain's value once its instructions have run."""
    if chain.level == 0 and not chain.terms and chain.second is None:
        return pool_regs[chain.code]
    return acc


@dataclass(frozen=True)
class Plan:
    """A target built by one chain, or by a forward chain plus a plan for the gap to the target."""

    first: Chain
    rest: Plan | None
    sign: int  # +1: first + rest, -1: first - rest
    cost: int

    def result_reg(self, pool_regs: list[int], accs: list[int]) -> int:
        """Register holding the target once the plan's instructions have run."""
        if self.rest is None:
            return chain_result_reg(self.first, pool_regs, accs[0])
        return accs[0]

    def program(self, pool_regs: list[int], accs: list[int]) -> list[list]:
        """Instructions, using one accumulator register per nesting level."""
        tmp = accs[1] if len(accs) > 1 else None
        ops = chain_program(self.first, pool_regs, accs[0], tmp)
        if self.rest is None:
            return ops
        ops += self.rest.program(pool_regs, accs[1:])
        a = chain_result_reg(self.first, pool_regs, accs[0])
        b = self.rest.result_reg(pool_regs, accs[1:])
        return ops + [["+" if self.sign > 0 else "-", a, b, accs[0]]]


def plan_target(
    target: int,
    pool: list[int],
    limit: int,
    forward: tuple[Forward, ...],
    sums: Sums,
    candidates: int = 8,
    max_cost: int | None = None,
    depth: int = 1,
    pairs: bool = True,
) -> Plan | None:
    """Cheapest plan: a direct chain, or a nearby forward value plus a plan for the gap.

    `depth` is how many chains may be nested: 1 allows a forward value plus one direct chain for
    the gap, 2 lets that gap use a residual too, and so on.
    """
    best: Plan | None = None
    direct = find_chain(target, pool, limit, forward, sums, max_cost)
    bound = max_cost if max_cost is not None else 1 << 30
    if direct is not None:
        best = Plan(direct, None, 1, direct.cost)
        bound = direct.cost
    if (
        pairs
    ):  # only the outermost call: a pair search is far costlier than a chain search
        pair = find_pair(target, pool, limit, forward, sums, bound)
        if pair is not None:
            best = Plan(pair, None, 1, pair.cost)
            bound = pair.cost
    near: list[tuple[int, int, int]] = []
    for level, fw in enumerate(forward):
        if level + 2 > bound - 1:
            continue
        pos = int(np.searchsorted(fw.vals, target))
        for idx in range(
            max(0, pos - candidates // 2), min(len(fw.vals), pos + candidates // 2)
        ):
            gap = abs(target - int(fw.vals[idx]))
            if gap:
                near.append((gap, level, idx))
    near.sort()
    for gap, level, idx in near[:candidates]:
        fw = forward[level]
        sub_bound = bound - level - 1
        if depth > 1:
            remainder = plan_target(
                gap, pool, limit, forward, sums, candidates, sub_bound, depth - 1, False
            )
        else:
            chain = find_chain(gap, pool, limit, forward, sums, max_cost=sub_bound)
            remainder = Plan(chain, None, 1, chain.cost) if chain else None
        if remainder is None:
            continue
        cost = level + remainder.cost + 1
        if cost >= bound:
            continue
        first = Chain(level, int(fw.codes[idx]), [], level)
        sign = 1 if target > int(fw.vals[idx]) else -1
        best, bound = Plan(first, remainder, sign, cost), cost
    return best


def make_pool(
    puzzle: Puzzle, size: int, rng: random.Random, reserve: int = 4
) -> tuple[list[int], list[int], list[list]]:
    """Pool values, their registers, and the instructions that build the random constants.

    Each constant is the sum, product or difference of two earlier pool values whose magnitude is
    closest to a log-uniformly drawn goal, so the pool spans every scale between the starting
    values and the cap. Signed sums over a pool of one scale can only reach a narrow window of
    each forward value; a spread pool widens it.
    """
    pool = list(dict.fromkeys(puzzle.starting_values))
    regs = {v: puzzle.starting_values.index(v) for v in pool}
    cap = min(puzzle.value_limit, max(max(pool), int(max(puzzle.targets) ** 0.5)))
    low = math.log(2)
    high = math.log(max(cap, 3))
    program: list[list] = []
    next_reg = len(puzzle.starting_values)
    stalls = 0
    wanted = max(1, size - len(pool))
    goals = [low + (high - low) * (k + rng.random()) / wanted for k in range(wanted)]
    rng.shuffle(goals)
    while len(pool) < size and next_reg < puzzle.registers - reserve and stalls < 50:
        goal = goals[(len(pool) - len(set(puzzle.starting_values)) + stalls) % wanted]
        best: tuple[float, int, str, int, int] | None = None
        for _ in range(60):
            a, b = rng.choice(pool), rng.choice(pool)
            op = rng.choice("+*-+")
            value = a + b if op == "+" else a * b if op == "*" else a - b
            if 1 <= value <= cap and value not in regs:
                miss = abs(math.log(value) - goal)
                if best is None or miss < best[0]:
                    best = (miss, value, op, a, b)
        if best is None:
            stalls += 1
            continue
        _, value, op, a, b = best
        program.append([op, regs[a], regs[b], next_reg])
        regs[value] = next_reg
        pool.append(value)
        next_reg += 1
    return pool, [regs[v] for v in pool], program


def solve(
    puzzle: Puzzle,
    pool_size: int = 40,
    max_terms: int = 4,
    seed: int = 0,
    depth: int = 3,
    nesting: int = 3,
    pairs: bool = True,
) -> list[list] | None:
    """Chain solver: a pool of constants, then one plan per target; None if a target has none."""
    if len(puzzle.starting_values) + nesting + 1 > puzzle.registers:
        return None
    pool, pool_regs, program = make_pool(
        puzzle, pool_size, random.Random(seed), reserve=nesting + 1
    )
    first_acc = len(puzzle.starting_values) + len(program)
    accs = list(range(first_acc, first_acc + nesting + 1))
    if accs[-1] >= puzzle.registers:
        return None
    forward = build_forward(pool, puzzle.value_limit, depth=depth, max_rows=100_000)
    sums = build_sums(pool, max_terms)
    covered = set(pool)
    for target in puzzle.targets:
        if target in covered:
            continue
        plan = plan_target(
            target, pool, puzzle.value_limit, forward, sums, depth=nesting, pairs=pairs
        )
        if plan is None:
            return None
        program += plan.program(pool_regs, accs)
        covered.add(target)
    return program
