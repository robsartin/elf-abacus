"""Signed-digit Horner solver.

Builds a shared table of digits 1..m and the radix R = 2m, then writes each target as
((top*R + e1)*R + e2)... with signed digits |e| <= m. Costs two instructions per digit and
one table build shared by every target. Tries every table size that fits in the registers
and keeps the shortest program that the verifier accepts.
"""

from __future__ import annotations

from elf_abacus.verifier import InvalidProgram, Puzzle, verify


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


def _build(puzzle: Puzzle, half: int) -> list[list] | None:
    """Program for table size `half`, or None when it does not fit in the registers."""
    start = len(puzzle.starting_values)
    reg_of: dict[int, int] = {}
    for r, v in enumerate(puzzle.starting_values):
        reg_of.setdefault(v, r)
    program: list[list] = []
    next_reg = start

    def emit(op: str, i: int, j: int) -> int:
        nonlocal next_reg
        if next_reg >= puzzle.registers:
            raise IndexError
        program.append([op, i, j, next_reg])
        next_reg += 1
        return next_reg - 1

    covered = set(puzzle.starting_values)
    pending = [t for t in puzzle.targets if t not in covered]
    if not pending:
        return []
    try:
        if 1 not in reg_of:
            reg_of[1] = emit("/", 0, 0)
        for d in range(2, half + 1):
            if d not in reg_of:
                reg_of[d] = emit("+", reg_of[d - 1], reg_of[1])
        covered.update(range(1, half + 1))
        radix = 2 * half
        r_reg = emit("+", reg_of[half], reg_of[half])
    except IndexError:
        return None
    if next_reg >= puzzle.registers:
        return None
    acc = next_reg
    covered.add(radix)
    for target in pending:
        if target in covered:
            continue
        top, digits = decompose(target, radix)
        value = top
        for k, e in enumerate(digits):
            program.append(["*", reg_of[top] if k == 0 else acc, r_reg, acc])
            value *= radix
            covered.add(value)
            if e:
                program.append(["+" if e > 0 else "-", acc, reg_of[abs(e)], acc])
                value += e
                covered.add(value)
    return program


def solve(puzzle: Puzzle) -> list[list] | None:
    """Shortest verified Horner program over all table sizes, or None if none is valid."""
    best: list[list] | None = None
    for half in range(1, puzzle.registers - len(puzzle.starting_values)):
        program = _build(puzzle, half)
        if program is None or (best is not None and len(program) >= len(best)):
            continue
        try:
            verify(puzzle, program)
        except InvalidProgram:
            continue
        best = program
    return best
