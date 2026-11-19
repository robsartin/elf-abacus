"""Quality gate for docs/adr: shape of every record, plus checks that ADR claims hold in code."""

import ast
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ADR_DIR = ROOT / "docs" / "adr"
ADRS = sorted(ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md"))
STATUS = re.compile(
    r"^Status: (Proposed|Accepted|Deprecated|Superseded by \d{4}|Amended)\b.*\(\d{4}-\d{2}-\d{2}\)$",
    re.MULTILINE,
)
REQUIRED_SLUGS = {
    "0001": "python-first",
    "0002": "verifier-is-the-oracle",
    "0003": "competition-data-never-committed",
    "0004": "apache-2-license",
}


def ids():
    return [p.name for p in ADRS]


@pytest.mark.parametrize("number,slug", REQUIRED_SLUGS.items())
def test_shouldHaveAdrFileWhenDecisionIsLoadBearing(number, slug):
    """Each load-bearing decision has its record."""
    assert (ADR_DIR / f"{number}-{slug}.md").is_file()


def test_shouldNumberAdrsSequentiallyWhenListedInOrder():
    numbers = [int(p.name[:4]) for p in ADRS]
    assert numbers == list(range(1, len(numbers) + 1))


@pytest.mark.parametrize("adr", ADRS, ids=ids())
def test_shouldHeadTitleWithItsFileNumberWhenAdrIsWritten(adr):
    first = adr.read_text().splitlines()[0]
    assert first.startswith(f"# {adr.name[:4]}. ")


@pytest.mark.parametrize("adr", ADRS, ids=ids())
def test_shouldDeclareDatedStatusWhenAdrIsWritten(adr):
    assert STATUS.search(adr.read_text())


@pytest.mark.parametrize("adr", ADRS, ids=ids())
@pytest.mark.parametrize("section", ["Context", "Decision", "Alternatives rejected"])
def test_shouldHaveRequiredSectionWhenAdrIsWritten(adr, section):
    assert re.search(rf"^## {section}$", adr.read_text(), re.MULTILINE)


@pytest.mark.parametrize("adr", ADRS, ids=ids())
def test_shouldGiveReasonForEachRejectedAlternativeWhenAdrIsWritten(adr):
    text = adr.read_text()
    block = text.split("## Alternatives rejected", 1)[1]
    bullets = re.findall(r"^- \*\*(.+?):?\*\*:? (.+)$", block, re.MULTILINE)
    assert bullets, "need at least one rejected alternative"
    assert all(len(reason.strip()) > 10 for _, reason in bullets)


@pytest.mark.parametrize("adr", ADRS, ids=ids())
def test_shouldPointCodeReferencesAtExistingPathsWhenAdrCitesCode(adr):
    """ADRs cite code as the authority, so the citation must not dangle."""
    cited = re.findall(
        r"`((?:src|tests|docs)/[\w./-]+|\.gitignore|LICENSE|pyproject\.toml)`",
        adr.read_text(),
    )
    missing = [c for c in cited if not (ROOT / c).exists()]
    assert not missing


def test_shouldKeepVerifierStdlibOnlyWhenAdr0002Claims():
    """ADR 0002: the oracle has no third-party dependencies."""
    tree = ast.parse((ROOT / "src/elf_abacus/verifier.py").read_text())
    mods = {
        n.module.split(".")[0]
        if isinstance(n, ast.ImportFrom)
        else a.name.split(".")[0]
        for n in ast.walk(tree)
        if isinstance(n, (ast.Import, ast.ImportFrom))
        for a in (n.names if isinstance(n, ast.Import) else [n])
    }
    import sys

    assert mods <= set(sys.stdlib_module_names)


def test_shouldIgnoreCompetitionDataWhenAdr0003Claims():
    for path in [
        "data/puzzles.csv",
        "data/practice_puzzles.csv",
        "submissions/sub.csv",
    ]:
        r = subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT, check=False)
        assert r.returncode == 0, f"{path} is not git-ignored"


def test_shouldDeclareApache2WhenAdr0004Claims():
    assert "Apache License" in (ROOT / "LICENSE").read_text()
    assert 'license = { text = "Apache-2.0" }' in (ROOT / "pyproject.toml").read_text()
