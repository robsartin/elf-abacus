"""Read puzzles and read, write and score submission CSVs."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from elf_abacus.verifier import InvalidProgram, Puzzle, verify

Program = list[list]


def load_puzzles(path: Path) -> list[Puzzle]:
    with Path(path).open(newline="") as f:
        return [
            Puzzle(
                id=row["id"],
                starting_values=json.loads(row["starting_values"]),
                targets=json.loads(row["targets"]),
                value_limit=int(row["value_limit"]),
                registers=int(row["registers"]),
            )
            for row in csv.DictReader(f)
        ]


def load_submission(path: Path) -> dict[str, Program]:
    programs: dict[str, Program] = {}
    with Path(path).open(newline="") as f:
        for row in csv.DictReader(f):
            if row["id"] in programs:
                raise InvalidProgram(f"duplicate id {row['id']}")
            programs[row["id"]] = json.loads(row["program"])
    return programs


def write_submission(path: Path, programs: dict[str, Program]) -> None:
    with Path(path).open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "program"])
        for puzzle_id, program in programs.items():
            writer.writerow([puzzle_id, json.dumps(program, separators=(",", ":"))])


def score_submission(puzzles: list[Puzzle], programs: dict[str, Program]) -> int:
    """Total instruction count; raises InvalidProgram if anything would be rejected."""
    expected = {p.id for p in puzzles}
    if missing := sorted(expected - programs.keys()):
        raise InvalidProgram(f"missing programs for {missing[:5]}")
    if extra := sorted(programs.keys() - expected):
        raise InvalidProgram(f"unexpected ids {extra[:5]}")
    total = 0
    for puzzle in puzzles:
        try:
            total += verify(puzzle, programs[puzzle.id])
        except InvalidProgram as err:
            raise InvalidProgram(f"{puzzle.id}: {err}") from err
    return total
