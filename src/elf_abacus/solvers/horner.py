"""Signed-digit Horner solver with anchor reuse.

Builds a shared table of digits 1..m and the radix R = 2m, then writes a number as
((top*R + e1)*R + e2)... with signed digits |e| <= m, two instructions per digit. Each target is
built either directly or as an earlier value (a starting value or a retained target) plus or
minus a small delta that is itself built this way, whichever is cheaper. Tries every table size
and anchor-slot count that fits in the registers and keeps the shortest verified program.
"""

from __future__ import annotations

from collections.abc import Sequence

from elf_abacus.verifier import InvalidProgram, Puzzle, verify

DEFAULT_ANCHOR_SLOTS = (0, 2, 4, 8, 12, 16)


def decompose(target: int, radix: int) -> tuple[int, list[int]]:
    """Split `target` into a top digit in 1..radix/2 and signed digits, most significant first."""
    half = radix // 2
    digits: list[int] = []
    while target > half:
        e = target % radix
        if e > half:
            e -= radix
        target = (target - e) // radix
        digits.append(e)
    digits.reverse()
    return target, digits


def _chain_cost(n: int, radix: int) -> int:
    """Instructions to build `n` by Horner (0 when n is itself a table digit)."""
    _, digits = decompose(n, radix)
    return len(digits) + sum(1 for e in digits if e)


class _Builder:
    def __init__(self, puzzle: Puzzle, half: int, slots: int) -> None:
        self.puzzle = puzzle
        self.half = half
        self.radix = 2 * half
        self.slots = slots
        self.program: list[list] = []
        self.regs: dict[int, int] = {}  # value -> register, for the digit table
        self.anchors: dict[
            int, int
        ] = {}  # value -> register, for reusable earlier values
        self.next_reg = len(puzzle.starting_values)
        self.covered = set(puzzle.starting_values)

    def _new_reg(self) -> int:
        if self.next_reg >= self.puzzle.registers:
            raise IndexError
        self.next_reg += 1
        return self.next_reg - 1

    def _emit(self, op: str, i: int, j: int) -> int:
        dest = self._new_reg()
        self.program.append([op, i, j, dest])
        return dest

    def build(self) -> list[list] | None:
        pending = [t for t in self.puzzle.targets if t not in self.covered]
        if not pending:
            return []
        try:
            self._build_table()
            self.acc = self._new_reg()
            ring = [self._new_reg() for _ in range(self.slots)]
        except IndexError:
            return None
        for r, v in enumerate(self.puzzle.starting_values):
            self.anchors.setdefault(v, r)
        age = 0
        for target in pending:
            if target in self.covered:
                continue
            dest = ring[age % self.slots] if self.slots else self.acc
            self._build_target(target, dest)
            if self.slots:
                self.anchors = {v: r for v, r in self.anchors.items() if r != dest}
                self.anchors[target] = dest
                age += 1
        return self.program

    def _build_table(self) -> None:
        for r, v in enumerate(self.puzzle.starting_values):
            self.regs.setdefault(v, r)
        if 1 not in self.regs:
            self.regs[1] = self._emit("/", 0, 0)
        for d in range(2, self.half + 1):
            if d not in self.regs:
                self.regs[d] = self._emit("+", self.regs[d - 1], self.regs[1])
        self.covered.update(range(1, self.half + 1))
        self.r_reg = self._emit("+", self.regs[self.half], self.regs[self.half])
        self.covered.add(self.radix)

    def _chain(self, n: int, dest: int) -> list[list]:
        """Horner ops for n > half, accumulating in acc and finishing in `dest`."""
        top, digits = decompose(n, self.radix)
        ops: list[list] = []
        value = top
        for k, e in enumerate(digits):
            ops.append(
                ["*", self.regs[top] if k == 0 else self.acc, self.r_reg, self.acc]
            )
            value *= self.radix
            self.covered.add(value)
            if e:
                ops.append(
                    ["+" if e > 0 else "-", self.acc, self.regs[abs(e)], self.acc]
                )
                value += e
                self.covered.add(value)
        ops[-1][3] = dest
        return ops

    def _build_target(self, target: int, dest: int) -> None:
        best_cost = _chain_cost(target, self.radix)
        best_anchor = None
        for value, reg in self.anchors.items():
            delta = abs(target - value)
            cost = 1 + (0 if delta <= self.half else _chain_cost(delta, self.radix))
            if cost < best_cost:
                best_cost, best_anchor = cost, (value, reg, delta)
        if best_anchor is None:
            self.program.extend(self._chain(target, dest))
            return
        value, reg, delta = best_anchor
        if delta <= self.half:
            src = self.regs[delta]
        else:
            self.program.extend(self._chain(delta, self.acc))
            src = self.acc
        self.program.append(["+" if target > value else "-", reg, src, dest])


def solve(
    puzzle: Puzzle, anchor_slots: Sequence[int] = DEFAULT_ANCHOR_SLOTS
) -> list[list] | None:
    """Shortest verified program over all table sizes and anchor-slot counts, or None."""
    best: list[list] | None = None
    for slots in anchor_slots:
        for half in range(1, puzzle.registers - len(puzzle.starting_values)):
            program = _Builder(puzzle, half, slots).build()
            if program is None or (best is not None and len(program) >= len(best)):
                continue
            try:
                verify(puzzle, program)
            except InvalidProgram:
                continue
            best = program
    return best
