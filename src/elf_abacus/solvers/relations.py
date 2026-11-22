"""Relations between targets: a target is often an earlier target plus or minus a small gap.

Targets of the shared and mixed families sit a few hundred to a few million away from an earlier
target, so keeping that earlier target in a register and building only the gap is much cheaper
than building the target from scratch. The gap is itself planned by the ordinary chain planner.
"""

from __future__ import annotations

from dataclasses import dataclass

from elf_abacus.solvers.chain import Forward, Plan, Sums, plan_target

NEAREST = 4  # bases tried per target, nearest first


@dataclass(frozen=True)
class DeltaPlan:
    """target = base +/- gap, where the gap is built by an ordinary plan."""

    base_reg: int
    sign: int  # +1: base + gap, -1: base - gap
    gap: Plan
    cost: int

    def program(self, pool_regs: list[int], accs: list[int], dest: int) -> list[list]:
        """Instructions that leave the target in `dest`; the base register is only read."""
        ops = self.gap.program(pool_regs, accs)
        gap_reg = self.gap.result_reg(pool_regs, accs)
        return [*ops, ["+" if self.sign > 0 else "-", self.base_reg, gap_reg, dest]]


def plan_delta(
    target: int,
    bases: dict[int, int],
    pool: list[int],
    limit: int,
    forward: tuple[Forward, ...],
    sums: Sums,
    max_cost: int | None = None,
    depth: int = 1,
) -> DeltaPlan | None:
    """Cheapest `base +/- gap` over the nearest available bases, or None if none beats `max_cost`."""
    bound = max_cost if max_cost is not None else 1 << 30
    best: DeltaPlan | None = None
    near = sorted((abs(target - v), v) for v in bases if v != target)
    for gap, value in near[:NEAREST]:
        if bound <= 1:
            break
        plan = plan_target(
            gap,
            pool,
            limit,
            forward,
            sums,
            max_cost=bound - 1,
            depth=depth,
            pairs=False,
        )
        if plan is None:
            continue
        cost = plan.cost + 1
        if cost >= bound:
            continue
        sign = 1 if target > value else -1
        best, bound = DeltaPlan(bases[value], sign, plan, cost), cost
    return best


def wanted_as_base(targets: list[int], index: int, closeness: float = 0.05) -> bool:
    """Whether some later target is within `closeness` (relative) of targets[index]."""
    t = targets[index]
    return any(abs(u - t) < u * closeness for u in targets[index + 1 :])


def lookahead(value: int, remaining: list[int], closeness: float = 0.05) -> int:
    """How many of the `remaining` targets lie within `closeness` (relative) of `value`."""
    return sum(1 for u in remaining if abs(u - value) < u * closeness)


def pick_victim(
    pool: list[int], protected: int, remaining: list[int], candidate: int
) -> int | None:
    """Index of the pool value to overwrite with `candidate`, or None to leave it unkept.

    The first `protected` entries (the starting values) are never chosen. The victim is the value
    with the lowest lookahead, oldest first among ties, and only if the candidate's is higher.
    """
    best: tuple[int, int] | None = None
    for index in range(protected, len(pool)):
        score = lookahead(pool[index], remaining)
        if best is None or score < best[0]:
            best = (score, index)
    if best is None or lookahead(candidate, remaining) <= best[0]:
        return None
    return best[1]
