"""Exact replay of Elf Calculator programs: the oracle every solver is checked against."""

from __future__ import annotations

from dataclasses import dataclass

MAX_INSTRUCTIONS = 4096


class InvalidProgram(Exception):
    """The program breaks a calculator rule or misses a target."""


@dataclass(frozen=True)
class Puzzle:
    id: str
    starting_values: list[int]
    targets: list[int]
    value_limit: int
    registers: int = 48


def _apply(op: str, a: int, b: int) -> int:
    if op == "+":
        return a + b
    if op == "-":
        if a <= b:
            raise InvalidProgram(f"subtraction must stay positive: {a} - {b}")
        return a - b
    if op == "*":
        return a * b
    if op == "/":
        if a % b:
            raise InvalidProgram(f"division must be exact: {a} / {b}")
        return a // b
    raise InvalidProgram(f"unknown operator {op!r}")


def verify(puzzle: Puzzle, program: list[list]) -> int:
    """Replay `program`; return its instruction count or raise InvalidProgram."""
    if len(program) > MAX_INSTRUCTIONS:
        raise InvalidProgram(f"more than {MAX_INSTRUCTIONS} instructions")
    regs: dict[int, int] = dict(enumerate(puzzle.starting_values))
    needed = set(puzzle.targets) - set(regs.values())
    for n, ins in enumerate(program):
        if len(ins) != 4:
            raise InvalidProgram(f"instruction {n} malformed: {ins!r}")
        op, i, j, d = ins
        for r in (i, j, d):
            if (
                not isinstance(r, int)
                or isinstance(r, bool)
                or not 0 <= r < puzzle.registers
            ):
                raise InvalidProgram(f"instruction {n}: register {r!r} out of range")
        for r in (i, j):
            if r not in regs:
                raise InvalidProgram(f"instruction {n}: register {r} undefined")
        value = _apply(op, regs[i], regs[j])
        if value > puzzle.value_limit:
            raise InvalidProgram(
                f"instruction {n}: {value} exceeds value_limit {puzzle.value_limit}"
            )
        regs[d] = value
        needed.discard(value)
    if needed:
        raise InvalidProgram(f"target {min(needed)} never produced")
    return len(program)
