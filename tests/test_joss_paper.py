"""The JOSS paper draft: format, required sections, citations and length (PAPER-003)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "paper" / "joss" / "paper.md"
BIBLIOGRAPHY = ROOT / "paper" / "joss" / "paper.bib"
REQUIRED_SECTIONS = (
    "Summary",
    "Statement of need",
    "State of the field",
    "Software design",
    "Research impact statement",
    "AI usage disclosure",
    "References",
)


def _split() -> tuple[dict, str]:
    text = PAPER.read_text(encoding="utf-8")
    _, front, body = text.split("---", 2)
    return yaml.safe_load(front), body


def _prose(body: str) -> str:
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    body = body.split("\n# References")[0]
    return re.sub(r"\[@[^\]]+\]", "", body)


def test_front_matter_names_the_author_and_the_bibliography() -> None:
    front, _ = _split()
    assert front["title"].startswith("FungMod:")
    assert front["bibliography"] == "paper.bib"
    assert [author["name"] for author in front["authors"]] == ["Felix Laga"]
    affiliations = {item["index"] for item in front["affiliations"]}
    assert all(author["affiliation"] in affiliations for author in front["authors"])
    citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    assert all(author["orcid"] in citation for author in front["authors"])


def test_the_required_sections_appear_in_order() -> None:
    _, body = _split()
    headings = re.findall(r"^# (.+)$", body, flags=re.M)
    positions = [headings.index(name) for name in REQUIRED_SECTIONS]
    assert positions == sorted(positions)


def test_every_citation_resolves_and_every_entry_is_cited() -> None:
    _, body = _split()
    cited = set(re.findall(r"@([A-Za-z0-9_]+)", " ".join(re.findall(r"\[@[^\]]+\]", body))))
    entries = set(re.findall(r"^@\w+\{([^,]+),", BIBLIOGRAPHY.read_text(encoding="utf-8"), flags=re.M))
    assert cited == entries


def test_the_length_is_within_the_journal_range() -> None:
    _, body = _split()
    words = re.findall(r"[A-Za-z0-9][^\s]*", _prose(body))
    assert 750 <= len(words) <= 1750


def test_the_paper_reports_no_research_results() -> None:
    _, body = _split()
    prose = _prose(body)
    # The results of the case studies belong to their plans and READMEs, not to the software paper.
    assert not re.search(r"\d+(\.\d+)?\s*percent", prose)
    assert "posterior median" not in prose and "held-out error" not in prose
