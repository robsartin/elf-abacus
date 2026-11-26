import random

from elf_abacus.superopt import shrink_window, superoptimize
from elf_abacus.verifier import Puzzle, verify


def test_shouldDropDeadInstructionWhenWindowResultIsNeverRead():
    """A window whose first instruction feeds nothing shrinks to the second alone."""
    puzzle = Puzzle("p", [3, 5], [15], 1000, registers=6)
    program = [["+", 0, 1, 2], ["*", 0, 1, 3]]
    out = shrink_window(puzzle, program, 0, 2)
    assert out is not None and len(out) == 1 and out[0][0] == "*"
    verify(puzzle, out)


def test_shouldFindOneInstructionWhenThreeStepsDetourToTheSameValue():
    """x = (p + p) - p + q is just p + q; the window search finds the direct form."""
    puzzle = Puzzle("p", [4, 6], [10], 1000, registers=6)
    program = [["+", 0, 0, 2], ["-", 2, 0, 2], ["+", 2, 1, 3]]
    out = shrink_window(puzzle, program, 0, 3)
    assert out is not None and len(out) < 3
    verify(puzzle, out)


def test_shouldReturnNoneWhenNoShorterWindowExists():
    """A minimal program has no shorter equivalent."""
    puzzle = Puzzle("p", [2, 3], [5, 10], 1000, registers=6)
    program = [["+", 0, 1, 2], ["+", 2, 2, 3]]
    assert shrink_window(puzzle, program, 0, 2) is None


def test_shouldKeepRegistersReadLaterWhenWindowIsRewritten():
    """A register the rest of the program reads keeps its value after the rewrite."""
    puzzle = Puzzle("p", [4, 6], [16], 1000, registers=6)
    program = [
        ["+", 0, 0, 2],
        ["-", 2, 0, 2],
        ["+", 2, 1, 3],
        ["+", 3, 1, 4],
    ]
    out = shrink_window(puzzle, program, 0, 3)
    assert out is not None
    verify(puzzle, out)
    assert len(out) < len(program)


def test_shouldStayValidWhenRandomProgramsAreSuperoptimized():
    """Over random valid programs every result verifies and is never longer (soundness property)."""
    rng = random.Random(7)
    for _ in range(25):
        starts = [rng.randint(2, 9) for _ in range(3)]
        regs: dict[int, int] = dict(enumerate(starts))
        program: list[list] = []
        for _ in range(8):
            i, j = rng.sample(sorted(regs), 2)
            op = rng.choice("+-*")
            if op == "-" and regs[i] <= regs[j]:
                op = "+"
            d = rng.randint(0, 7)
            regs[d] = {
                "+": regs[i] + regs[j],
                "-": regs[i] - regs[j],
                "*": regs[i] * regs[j],
            }[op]
            program.append([op, i, j, d])
        puzzle = Puzzle("r", starts, [regs[program[-1][3]]], 10**9, registers=8)
        verify(puzzle, program)
        out = superoptimize(puzzle, program)
        assert len(out) <= len(program)
        verify(puzzle, out)


def test_shouldFindShorterProgramWhenWindowInstructionsAreNotAdjacent():
    """With windows of 2, only moving the second detour step next to the first can shrink this."""
    puzzle = Puzzle("p", [4, 6, 9], [81, 12], 1000, registers=8)
    program = [["+", 0, 0, 3], ["*", 2, 2, 4], ["+", 3, 0, 5]]
    out = superoptimize(puzzle, program, max_window=2)
    verify(puzzle, out)
    assert len(out) == 2


def test_shouldReturnInputWhenProgramIsInvalid():
    """An invalid input is returned untouched rather than rewritten."""
    puzzle = Puzzle("p", [2, 3], [99], 1000, registers=6)
    program = [["+", 0, 1, 2]]
    assert superoptimize(puzzle, program) == program


def test_shouldNeverLengthenWhenProgramIsAlreadyShortest():
    """A one-instruction program comes back identical."""
    puzzle = Puzzle("p", [2, 3], [5], 1000, registers=6)
    program = [["+", 0, 1, 2]]
    assert superoptimize(puzzle, program) == program


def test_shouldWriteShorterSubmissionWhenRunFromTheCommandLine(tmp_path, capsys):
    """The command line reads a submission, shrinks each program and writes the result."""
    from elf_abacus.io import load_submission, write_submission
    from elf_abacus.superopt import main

    puzzles = tmp_path / "puzzles.csv"
    puzzles.write_text(
        'id,starting_values,targets,value_limit,registers\np1,"[3, 5]",[15],1000,6\n'
    )
    write_submission(tmp_path / "in.csv", {"p1": [["+", 0, 1, 2], ["*", 0, 1, 3]]})
    out = tmp_path / "out.csv"
    argv = ["--puzzles", str(puzzles), "--out", str(out), "--workers", "1"]
    main([*argv, str(tmp_path / "in.csv")])
    assert len(load_submission(out)["p1"]) == 1
    assert "2 -> 1" in capsys.readouterr().out


def test_shouldShrinkAtLeastAsMuchAsEitherPassWhenAlternatedToFixpoint():
    """A repeated value (peephole) and a three-step detour (window search) both go in one call."""
    from elf_abacus.peephole import optimize
    from elf_abacus.superopt import superoptimize_fixpoint

    puzzle = Puzzle("p", [4, 6], [10, 20], 1000, registers=8)
    program = [
        ["+", 0, 0, 2],
        ["-", 2, 0, 2],
        ["+", 2, 1, 3],
        ["+", 0, 1, 4],
        ["+", 4, 3, 5],
    ]
    verify(puzzle, program)
    out = superoptimize_fixpoint(puzzle, program)
    verify(puzzle, out)
    assert len(out) <= len(superoptimize(puzzle, program))
    assert len(out) <= len(optimize(puzzle, program))
    assert len(out) < len(program)


def test_shouldReturnInputWhenFixpointProgramIsInvalid():
    """An invalid input comes back untouched from the alternating driver too."""
    from elf_abacus.superopt import superoptimize_fixpoint

    puzzle = Puzzle("p", [2, 3], [99], 1000, registers=6)
    program = [["+", 0, 1, 2]]
    assert superoptimize_fixpoint(puzzle, program) == program


def test_shouldStillFindHelperRouteWhenNeededValueIsUnreachableInOneStep():
    """40 is no single step from [4, 6]; the search must build the helper 10 first (guards the
    blocked-need helper pruning: helpers are offered only for needs with no direct route)."""
    puzzle = Puzzle("p", [4, 6], [40], 1000, registers=8)
    program = [["+", 0, 1, 2], ["+", 2, 2, 3], ["+", 3, 3, 4]]
    verify(puzzle, program)
    out = shrink_window(puzzle, program, 0, 3)
    assert out is not None and len(out) == 2
    verify(puzzle, out)
