"""Verified post-pass: shrink a finished program without changing which targets it produces.

Every value is an exact integer, so the program is really a DAG over distinct values.
We rebuild that DAG (dropping recomputations), keep only what the targets need,
and re-allocate registers; the verifier is the oracle for the result (ADR 0002).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from elf_abacus.verifier import MAX_INSTRUCTIONS, InvalidProgram, Puzzle, verify

Program = list[list]


@dataclass
class _Node:
    value: int
    op: str | None = None  # None for starting values
    a: int = -1  # operand node ids
    b: int = -1


def _build_dag(puzzle: Puzzle, program: Program) -> list[_Node]:
    """Distinct-value nodes in first-production order; later recomputations vanish."""
    nodes: list[_Node] = []
    by_value: dict[int, int] = {}
    regs: dict[int, int] = {}
    for reg, value in enumerate(puzzle.starting_values):
        if value not in by_value:
            by_value[value] = len(nodes)
            nodes.append(_Node(value))
        regs[reg] = by_value[value]
    for op, i, j, d in program:
        x, y = regs[i], regs[j]
        a, b = nodes[x].value, nodes[y].value
        value = {"+": a + b, "-": a - b, "*": a * b, "/": a // b if b else 0}[op]
        if value not in by_value:
            by_value[value] = len(nodes)
            nodes.append(_Node(value, op, x, y))
        regs[d] = by_value[value]
    return nodes


def _reachable(nodes: list[_Node], roots: set[int]) -> set[int]:
    seen: set[int] = set()
    stack = list(roots)
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        if nodes[n].op is not None:
            stack += (nodes[n].a, nodes[n].b)
    return seen


def _alternatives(
    nodes: list[_Node], w: int, candidates: dict[int, int]
) -> Iterator[tuple[str, int, int]]:
    """Other ways to make nodes[w].value from `candidates` (value -> node id), acyclic only."""
    v = nodes[w].value
    for x_value, x in candidates.items():
        pairs = [("+", v - x_value), ("-", x_value - v)]
        if x_value and v % x_value == 0:
            pairs.append(("*", v // x_value))
        if x_value % v == 0:
            pairs.append(("/", x_value // v))
        for op, y_value in pairs:
            y = candidates.get(y_value)
            if y is None or x == w or y == w:
                continue
            if w in _reachable(nodes, {x}) or w in _reachable(nodes, {y}):
                continue
            yield op, x, y


def _rederive(
    nodes: list[_Node],
    roots: set[int],
    live: set[int],
    fits: Callable[[set[int]], bool] = lambda _live: True,
) -> set[int]:
    """Drop non-target nodes whose consumers can be rebuilt from other live values."""
    changed = True
    while changed:
        changed = False
        for u in sorted(live, reverse=True):
            if nodes[u].op is None or u in roots:
                continue
            consumers = [
                w for w in live if u in (nodes[w].a, nodes[w].b) and nodes[w].op
            ]
            pool = {nodes[n].value: n for n in live if n != u}
            saved = {w: (nodes[w].op, nodes[w].a, nodes[w].b) for w in consumers}
            ok = True
            for w in consumers:
                alt = next(_alternatives(nodes, w, pool), None)
                if alt is None:
                    ok = False
                    break
                nodes[w].op, nodes[w].a, nodes[w].b = alt
            reach = _reachable(nodes, roots) if ok else live
            if ok and len(reach) < len(live) and fits(reach):
                live = reach
                changed = True
                break
            for w, (op, a, b) in saved.items():
                nodes[w].op, nodes[w].a, nodes[w].b = op, a, b
    return live


def _pair_index(
    nodes: list[_Node], live: set[int]
) -> dict[int, list[tuple[str, int, int]]]:
    """Value -> a few (op, a, b) over live nodes making it in one step, for values not live."""
    index: dict[int, list[tuple[str, int, int]]] = {}
    items = [(nodes[n].value, n) for n in live]
    present = {value for value, _ in items}
    for av, a in items:
        for bv, b in items:
            made = [("+", av + bv), ("*", av * bv)]
            if av > bv:
                made.append(("-", av - bv))
            if bv and av % bv == 0:
                made.append(("/", av // bv))
            for op, value in made:
                if value not in present:
                    slot = index.setdefault(value, [])
                    if len(slot) < 3:
                        slot.append((op, a, b))
    return index


def _consumer_forms(v: int, x: int) -> Iterator[tuple[str, int, bool]]:
    """Ways v = x op n (n first operand when the flag is False): (op, n value, x first)."""
    if v > x:
        yield "+", v - x, True
        yield "-", v + x, False
    if x > v:
        yield "-", x - v, True
    if x and v % x == 0:
        yield "*", v // x, True
    if x % v == 0:
        yield "/", x // v, True
    yield "/", v * x, False


def _private_chain(
    nodes: list[_Node], roots: set[int], consumers: dict[int, list[int]], w: int
) -> set[int]:
    """Non-target operation nodes that die if w stops reading its operands (w itself stays)."""
    dead: set[int] = set()
    changed = True
    while changed:
        changed = False
        stack = [nodes[w].a, nodes[w].b]
        seen: set[int] = set()
        while stack:
            n = stack.pop()
            if n in seen or n == w:
                continue
            seen.add(n)
            if n in dead:
                stack += (nodes[n].a, nodes[n].b)
            elif (
                nodes[n].op is not None
                and n not in roots
                and all(c in dead or c == w for c in consumers[n])
            ):
                dead.add(n)
                changed = True
                stack += (nodes[n].a, nodes[n].b)
    return dead


_Plan = tuple[list[tuple[int, str, int, int]], str, tuple[int, int]]


def _rebuilds(
    nodes: list[_Node],
    w: int,
    pool: dict[int, int],
    index: dict[int, list[tuple[str, int, int]]],
    blocked: set[int],
    limit: int,
    new_values: int,
    reaches: Callable[[int], set[int]],
) -> Iterator[_Plan]:
    """Ways to rebuild nodes[w] from `pool` plus exactly `new_values` new values.

    A plan is (new nodes as (value, op, a, b) with -1 / -2 naming the first / second new node
    in w's operands, w's new op, w's new operands). Operands never lead back to w, and the pair
    behind a new value avoids `blocked`.
    """
    v = nodes[w].value

    def usable(p: int, q: int) -> bool:
        return not (p in blocked or q in blocked or w in (p, q)) and not (
            w in reaches(p) or w in reaches(q)
        )

    for x_value, x in pool.items():
        for op, n_value, x_first in _consumer_forms(v, x_value):
            if new_values == 0:
                y = pool.get(n_value)
                if y is not None:
                    yield [], op, (x, y) if x_first else (y, x)
            elif n_value > 0 and n_value not in pool and n_value <= limit:
                if new_values == 1:
                    for made_op, p, q in index.get(n_value, ()):
                        if usable(p, q):
                            yield (
                                [(n_value, made_op, p, q)],
                                op,
                                ((x, -1) if x_first else (-1, x)),
                            )
                    continue
                for y_value, y in pool.items():
                    for op2, c_value, y_first in _consumer_forms(n_value, y_value):
                        if c_value <= 0 or c_value > limit or c_value in pool:
                            continue
                        if c_value == n_value:
                            continue
                        for made_op, p, q in index.get(c_value, ()):
                            if usable(p, q):
                                yield (
                                    [
                                        (c_value, made_op, p, q),
                                        (
                                            n_value,
                                            op2,
                                            *((y, -1) if y_first else (-1, y)),
                                        ),
                                    ],
                                    op,
                                    ((x, -2) if x_first else (-2, x)),
                                )


def _rederive_with_helpers(
    nodes: list[_Node],
    roots: set[int],
    live: set[int],
    limit: int,
    fits: Callable[[set[int]], bool],
    new_values: int = 1,
) -> set[int] | None:
    """One rewrite that nets a saving: rebuild a node w from other live values plus at most
    `new_values` new ones, so that the chain of helpers private to w dies and outweighs them.

    Returns the new live set (nodes mutated), or None when no such rewrite exists.
    """
    index = _pair_index(nodes, live)
    consumers: dict[int, list[int]] = {n: [] for n in live}
    for w in live:
        if nodes[w].op:
            for operand in {nodes[w].a, nodes[w].b}:
                consumers[operand].append(w)
    memo: dict[int, set[int]] = {}

    def reaches(n: int) -> set[int]:
        if n not in memo:
            memo[n] = _reachable(nodes, {n})
        return memo[n]

    for w in sorted(live, reverse=True):
        if nodes[w].op is None:
            continue
        dead = _private_chain(nodes, roots, consumers, w)
        if len(dead) <= new_values:
            continue
        pool = {
            nodes[n].value: n
            for n in live
            if n not in dead and n != w and w not in reaches(n)
        }
        for new, op, (a, b) in _rebuilds(
            nodes, w, pool, index, dead, limit, new_values, reaches
        ):
            saved = (nodes[w].op, nodes[w].a, nodes[w].b)
            base = len(nodes)

            def real(ref: int, base: int = base) -> int:
                return base - 1 - ref if ref < 0 else ref

            for value, made_op, p, q in new:
                nodes.append(_Node(value, made_op, real(p), real(q)))
            nodes[w].op, nodes[w].a, nodes[w].b = op, real(a), real(b)
            reach = _reachable(nodes, roots)
            if len(reach) < len(live) and fits(reach):
                return reach
            del nodes[base:]
            nodes[w].op, nodes[w].a, nodes[w].b = saved
    return None


def _depth_first_order(nodes: list[_Node], keep: set[int]) -> list[int]:
    """Operands-first order that finishes each subtree before starting the next (low pressure)."""
    order: list[int] = []
    done: set[int] = set()

    def visit(n: int) -> None:
        if n in done or nodes[n].op is None:
            return
        done.add(n)
        first, second = sorted((nodes[n].a, nodes[n].b), key=lambda m: -_size(nodes, m))
        visit(first)
        visit(second)
        order.append(n)

    for n in sorted(keep, reverse=True):
        visit(n)
    return order


def _size(nodes: list[_Node], n: int) -> int:
    return len(_reachable(nodes, {n}))


def _topological_order(nodes: list[_Node], keep: set[int]) -> list[int]:
    """Operands first, ties broken by node id (original production order)."""
    order: list[int] = []
    done: set[int] = set()
    ready = [n for n in sorted(keep) if nodes[n].op is not None]
    pending = set(ready)
    while pending:
        for n in ready:
            if n in pending and all(
                nodes[m].op is None or m in done for m in (nodes[n].a, nodes[n].b)
            ):
                pending.discard(n)
                done.add(n)
                order.append(n)
                break
    return order


def _emit(
    puzzle: Puzzle, nodes: list[_Node], keep: set[int], order: list[int] | None = None
) -> Program | None:
    """Linear-scan register allocation over kept nodes; None if > registers."""
    starts = [i for i, nd in enumerate(nodes) if nd.op is None]
    if order is None:
        order = _topological_order(nodes, keep)
    last_use: dict[int, int] = {}
    for step, n in enumerate(order):
        last_use[nodes[n].a] = step
        last_use[nodes[n].b] = step
    reg_of: dict[int, int] = {}
    free = set(range(puzzle.registers))
    for reg, value in enumerate(puzzle.starting_values):
        start = next(s for s in starts if nodes[s].value == value)
        reg_of.setdefault(start, reg)
        free.discard(reg)
    # registers holding duplicate starting values or never-read starts are free at once
    held = set(reg_of.values())
    for reg in range(len(puzzle.starting_values)):
        if reg not in held:
            free.add(reg)
    for s in starts:
        if s in reg_of and s not in last_use:
            free.add(reg_of.pop(s))
    out: Program = []
    for step, n in enumerate(order):
        node = nodes[n]
        ra, rb = reg_of[node.a], reg_of[node.b]
        for operand in {node.a, node.b}:
            if last_use[operand] == step:
                free.add(reg_of[operand])
        if not free:
            return None
        dest = min(free)
        free.discard(dest)
        reg_of[n] = dest
        out.append([node.op, ra, rb, dest])
        if n not in last_use:
            free.add(dest)
            del reg_of[n]
    return out


def optimize(puzzle: Puzzle, program: Program) -> Program:
    """Equivalent program that is never longer; the input itself if no rewrite verifies."""
    try:
        verify(puzzle, program)
    except InvalidProgram:
        return program
    nodes = _build_dag(puzzle, program)
    by_value = {node.value: n for n, node in enumerate(nodes)}
    roots = {by_value[t] for t in puzzle.targets}

    def allocate(keep: set[int]) -> Program | None:
        return _emit(puzzle, nodes, keep) or _emit(
            puzzle, nodes, keep, _depth_first_order(nodes, keep)
        )

    live = _rederive(
        nodes, roots, _reachable(nodes, roots), lambda keep: allocate(keep) is not None
    )

    def fits(keep: set[int]) -> bool:
        return allocate(keep) is not None

    while True:
        more = None
        for new_values in (0, 1, 2):
            more = _rederive_with_helpers(
                nodes, roots, live, puzzle.value_limit, fits, new_values
            )
            if more is not None:
                break
        if more is None:
            break
        live = _rederive(nodes, roots, more, fits)
    candidate = allocate(live)
    if candidate is None or len(candidate) >= len(program):
        return program
    try:
        verify(puzzle, candidate)
    except InvalidProgram:
        return program
    return candidate


def _allocate_with_recompute(
    puzzle: Puzzle, nodes: list[_Node], order: list[int]
) -> Program | None:
    """Register allocation that recomputes a value instead of failing when registers run out.

    Walks `order` (operands first). When no register is free, the resident computed value whose
    next use is furthest away is overwritten; if it is needed again it is recomputed then, from
    operands that are themselves recomputed if they were overwritten too. Starting values cannot
    be recomputed, so they are never overwritten while still needed. None if even that fails.
    """
    consumers: dict[int, list[int]] = {}
    for n in order:
        for operand in {nodes[n].a, nodes[n].b}:
            consumers.setdefault(operand, []).append(n)
    position = {n: step for step, n in enumerate(order)}
    reg_of: dict[int, int] = {}
    free = set(range(puzzle.registers))
    for reg, value in enumerate(puzzle.starting_values):
        start = next(
            i for i, nd in enumerate(nodes) if nd.op is None and nd.value == value
        )
        if start not in reg_of:
            reg_of[start] = reg
            free.discard(reg)
    held = set(reg_of.values())
    free.update(r for r in range(len(puzzle.starting_values)) if r not in held)
    out: Program = []
    produced: set[int] = set()

    def needed(x: int, memo: dict[int, bool]) -> bool:
        """x is read by a step still to run, or by a value that would have to be recomputed."""
        if x not in memo:
            memo[x] = False
            memo[x] = any(
                c not in produced or (c not in reg_of and needed(c, memo))
                for c in consumers.get(x, ())
            )
        return memo[x]

    def release_dead() -> None:
        memo: dict[int, bool] = {}
        for x in list(reg_of):
            if not needed(x, memo):
                free.add(reg_of.pop(x))

    def next_use(x: int) -> int:
        return min(
            (position[c] for c in consumers.get(x, ()) if c not in produced),
            default=1 << 30,
        )

    def claim(pinned: set[int]) -> int | None:
        if free:
            reg = min(free)
            free.discard(reg)
            return reg
        victims = [x for x in reg_of if x not in pinned and nodes[x].op is not None]
        if not victims:
            return None
        # furthest next use first; among ties, the one whose operands are still resident
        victim = max(
            victims,
            key=lambda x: (
                next_use(x),
                -((nodes[x].a not in reg_of) + (nodes[x].b not in reg_of)),
            ),
        )
        return reg_of.pop(victim)

    def ensure(x: int, pinned: set[int]) -> bool:
        if x in reg_of:
            return True
        node = nodes[x]
        if node.op is None:
            return False
        pin = pinned | {node.a, node.b}
        if not (ensure(node.a, pin) and ensure(node.b, pin)):
            return False
        ra, rb = reg_of[node.a], reg_of[node.b]
        dest = claim(pin)
        if dest is None:
            return False
        out.append([node.op, ra, rb, dest])
        reg_of[x] = dest
        release_dead()
        return len(out) <= MAX_INSTRUCTIONS

    for n in order:
        node = nodes[n]
        operands = {node.a, node.b}
        if not all(ensure(x, operands) for x in operands):
            return None
        ra, rb = reg_of[node.a], reg_of[node.b]
        produced.add(n)
        reg_of[n] = -1  # reserved: the result is about to exist
        for x in operands:
            if not needed(x, {}):
                free.add(reg_of.pop(x))
        dest = claim({x for x in (*operands, n) if x in reg_of})
        if dest is None:
            return None
        out.append([node.op, ra, rb, dest])
        reg_of[n] = dest
        release_dead()
        if len(out) > MAX_INSTRUCTIONS:
            return None
    return out


def rematerialize(
    puzzle: Puzzle, program: Program, virtual_registers: int
) -> Program | None:
    """Compile a program written for `virtual_registers` registers into `puzzle.registers`.

    The program only has to be valid on a puzzle with the larger register file. Its value DAG is
    pruned to what the targets need and re-allocated with recomputation (see
    `_allocate_with_recompute`), trying production order and depth-first order. Returns the
    shortest verified result, or None if no order fits.
    """
    virtual = dataclasses.replace(puzzle, registers=virtual_registers)
    try:
        verify(virtual, program)
    except InvalidProgram:
        return None
    nodes = _build_dag(virtual, program)
    by_value = {node.value: n for n, node in enumerate(nodes)}
    keep = _reachable(nodes, {by_value[t] for t in puzzle.targets})
    best: Program | None = None
    for order in (_topological_order(nodes, keep), _depth_first_order(nodes, keep)):
        candidate = _allocate_with_recompute(puzzle, nodes, order)
        if candidate is None or (best is not None and len(candidate) >= len(best)):
            continue
        try:
            verify(puzzle, candidate)
        except InvalidProgram:
            continue
        best = candidate
    return best
