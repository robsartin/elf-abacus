import random

from elf_abacus.dagopt import dag_shrink, main
from elf_abacus.io import load_submission, write_submission
from elf_abacus.verifier import Puzzle, verify


def test_shouldWriteShrunkSubmissionWhenCliRuns(tmp_path):
    program = [
        ["+", 0, 1, 2],
        ["*", 0, 1, 3],
        ["+", 3, 3, 4],
        ["+", 4, 4, 5],
        ["+", 5, 3, 6],
    ]
    (tmp_path / "puzzles.csv").write_text(
        "id,starting_values,targets,value_limit,registers\n"
        'p,"[2, 3]","[5, 6, 30]",1000000,8\n'
    )
    write_submission(tmp_path / "in.csv", {"p": program})

    main(
        [
            "--puzzles",
            str(tmp_path / "puzzles.csv"),
            "--out",
            str(tmp_path / "out.csv"),
            str(tmp_path / "in.csv"),
        ]
    )

    assert len(load_submission(tmp_path / "out.csv")["p"]) == 3


def test_shouldReplaceDetourWithOneOperationWhenPairLivesElsewhere():
    """30 is built by three doublings; 5 * 6 over two values made earlier is one step."""
    puzzle = Puzzle("p", [2, 3], [5, 6, 30], 10**6, registers=8)
    program = [
        ["+", 0, 1, 2],  # 5
        ["*", 0, 1, 3],  # 6
        ["+", 3, 3, 4],  # 12
        ["+", 4, 4, 5],  # 24
        ["+", 5, 3, 6],  # 30
    ]
    verify(puzzle, program)

    out = dag_shrink(puzzle, program)

    assert len(out) == 3
    verify(puzzle, out)


def test_shouldReturnInputWhenProgramIsInvalid():
    puzzle = Puzzle("p", [2, 3], [99], 1000, registers=6)
    program = [["+", 0, 1, 2]]
    assert dag_shrink(puzzle, program) == program


def test_shouldReturnInputWhenNothingShrinks():
    puzzle = Puzzle("p", [2, 3], [5, 10], 1000, registers=6)
    program = [["+", 0, 1, 2], ["+", 2, 2, 3]]
    assert dag_shrink(puzzle, program) == program


def test_shouldStayValidAndNeverGrowWhenRandomProgramsAreShrunk():
    rng = random.Random(7)
    for _ in range(40):
        puzzle = Puzzle("r", [3, 5, 7], [], 10**6, registers=6)
        regs = dict(enumerate(puzzle.starting_values))
        program: list[list] = []
        for _ in range(rng.randint(4, 10)):
            op = rng.choice("+*")
            i, j, d = rng.choice(list(regs)), rng.choice(list(regs)), rng.randrange(6)
            value = regs[i] + regs[j] if op == "+" else regs[i] * regs[j]
            if value > puzzle.value_limit:
                continue
            program.append([op, i, j, d])
            regs[d] = value
        if not program:
            continue
        puzzle = Puzzle("r", [3, 5, 7], list(regs.values()), 10**6, registers=6)
        out = dag_shrink(puzzle, program)
        assert verify(puzzle, out) <= len(program)
