"""Verified post-pass: shrink a finished program without changing which targets it produces.

Every value is an exact integer, so the program is really a DAG over distinct values.
We rebuild that DAG (dropping recomputations), keep only what the targets need,
and re-allocate registers; the verifier is the oracle for the result (ADR 0002).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass

from elf_abacus.verifier import InvalidProgram, Puzzle, verify

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


def _rederive_with_helper(
    nodes: list[_Node],
    roots: set[int],
    live: set[int],
    limit: int,
    fits: Callable[[set[int]], bool],
) -> set[int] | None:
    """One rewrite that nets a saving: a single-consumer helper u is dropped by rebuilding its
    consumer w as x op n, where n is a new value made in one step from live values.

    Returns the new live set (nodes mutated), or None when no such rewrite exists.
    """
    index = _pair_index(nodes, live)
    for u in sorted(live, reverse=True):
        if nodes[u].op is None or u in roots:
            continue
        consumers = [w for w in live if nodes[w].op and u in (nodes[w].a, nodes[w].b)]
        if len(consumers) != 1:
            continue
        w = consumers[0]
        v = nodes[w].value
        pool = {nodes[n].value: n for n in live if n != u}
        for x_value, x in pool.items():
            for op, n_value, x_first in _consumer_forms(v, x_value):
                if n_value <= 0 or n_value in pool or n_value > limit:
                    continue
                if n_value == nodes[u].value:
                    continue
                for made_op, p, q in index.get(n_value, ()):
                    if u in (p, q) or w in (p, q) or x == w:
                        continue
                    if w in _reachable(nodes, {x, p, q}):
                        continue
                    saved = (nodes[w].op, nodes[w].a, nodes[w].b)
                    nodes.append(_Node(n_value, made_op, p, q))
                    n = len(nodes) - 1
                    nodes[w].op = op
                    nodes[w].a, nodes[w].b = (x, n) if x_first else (n, x)
                    reach = _reachable(nodes, roots)
                    if len(reach) < len(live) and fits(reach):
                        return reach
                    nodes.pop()
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
    while (
        more := _rederive_with_helper(
            nodes, roots, live, puzzle.value_limit, lambda k: allocate(k) is not None
        )
    ) is not None:
        live = _rederive(nodes, roots, more, lambda keep: allocate(keep) is not None)
    candidate = allocate(live)
    if candidate is None or len(candidate) >= len(program):
        return program
    try:
        verify(puzzle, candidate)
    except InvalidProgram:
        return program
    return candidate
