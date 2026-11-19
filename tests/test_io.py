import csv
import json

import pytest

from elf_abacus.io import (
    load_puzzles,
    load_submission,
    score_submission,
    write_submission,
)
from elf_abacus.verifier import InvalidProgram, Puzzle

PROGRAM = [["/", 0, 0, 1], ["-", 0, 1, 2], ["+", 0, 2, 3], ["+", 0, 3, 4]]


def puzzles_csv(tmp_path, rows):
    path = tmp_path / "puzzles.csv"
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "starting_values", "targets", "value_limit", "registers"])
        w.writerows(rows)
    return path


def test_shouldParsePuzzleFieldsWhenLoadingPuzzlesCsv(tmp_path):
    path = puzzles_csv(tmp_path, [["p1", "[3]", "[1, 2, 5, 8]", "9", "48"]])
    assert load_puzzles(path) == [Puzzle("p1", [3], [1, 2, 5, 8], 9, 48)]


def test_shouldRoundTripProgramsWhenWritingThenLoadingSubmission(tmp_path):
    path = tmp_path / "sub.csv"
    write_submission(path, {"p1": PROGRAM})
    assert load_submission(path) == {"p1": PROGRAM}


def test_shouldWriteIdProgramHeaderWhenWritingSubmission(tmp_path):
    path = tmp_path / "sub.csv"
    write_submission(path, {"p1": PROGRAM})
    header, row = path.read_text().splitlines()
    assert header == "id,program"
    assert json.loads(next(csv.reader([row]))[1]) == PROGRAM


def test_shouldSumInstructionCountsWhenSubmissionIsValid(tmp_path):
    puzzles = [Puzzle("p1", [3], [1, 2, 5, 8], 9), Puzzle("p2", [3], [1, 2, 5, 8], 9)]
    assert score_submission(puzzles, {"p1": PROGRAM, "p2": PROGRAM}) == 8


def test_shouldRejectWhenPuzzleHasNoProgram():
    puzzles = [Puzzle("p1", [3], [1, 2, 5, 8], 9), Puzzle("p2", [3], [1, 2, 5, 8], 9)]
    with pytest.raises(InvalidProgram, match="missing.*p2"):
        score_submission(puzzles, {"p1": PROGRAM})


def test_shouldRejectWhenSubmissionHasUnknownId():
    puzzles = [Puzzle("p1", [3], [1, 2, 5, 8], 9)]
    with pytest.raises(InvalidProgram, match="unexpected.*zz"):
        score_submission(puzzles, {"p1": PROGRAM, "zz": PROGRAM})


def test_shouldNameThePuzzleWhenItsProgramIsInvalid():
    puzzles = [Puzzle("p1", [3], [1, 2, 5, 8], 9)]
    with pytest.raises(InvalidProgram, match="p1"):
        score_submission(puzzles, {"p1": PROGRAM[:2]})


def test_shouldRejectWhenSubmissionRepeatsAnId(tmp_path):
    path = tmp_path / "sub.csv"
    row = json.dumps(PROGRAM)
    path.write_text(f'id,program\np1,"{row.replace(chr(34), chr(34) * 2)}"\n' * 1)
    with path.open("a") as f:
        f.write(f'p1,"{row.replace(chr(34), chr(34) * 2)}"\n')
    with pytest.raises(InvalidProgram, match="duplicate.*p1"):
        load_submission(path)
