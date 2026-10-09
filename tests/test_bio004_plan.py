"""The BIO-004 plan for six new mechanisms: implementation status and law-form evidence remain machine-checkable."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from fungal_model.validation.bio_readiness import validate_bio_mechanism_proposal_file

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "foundation_progress" / "BIO_004_NEW_MECHANISMS_PLAN.md"
PROPOSALS = ROOT / "foundation_progress" / "proposals"
EXPECTED = {
    "BIO_004_ADSORBED_ENZYME_HYDROLYSIS.yml": "M1",
    "BIO_004_SOLUBLE_SUBSTRATE_UPTAKE.yml": "M2",
    "BIO_004_DISSOLVED_OXYGEN_BALANCE.yml": "M3",
    "BIO_004_PROTON_BALANCE_PH.yml": "M4",
    "BIO_004_CHAIN_END_SYNERGY.yml": "M5",
    "BIO_004_PEROXIDE_DRIVEN_OXIDATIVE_CLEAVAGE.yml": "M6",
}
VERIFICATION_PREFIXES = ("checked", "re-check", "unverified")


def _proposal(name: str) -> dict:
    return yaml.safe_load((PROPOSALS / name).read_text(encoding="utf-8"))


def test_the_plan_lists_exactly_the_bio004_proposals() -> None:
    on_disk = {path.name for path in PROPOSALS.glob("BIO_004_*.yml")}
    assert on_disk == set(EXPECTED)
    plan = PLAN.read_text(encoding="utf-8")
    for name, mechanism in EXPECTED.items():
        assert f"| {mechanism} | `proposals/{name}` |" in plan


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_each_proposal_passes_bio_readiness(name: str) -> None:
    report = validate_bio_mechanism_proposal_file(PROPOSALS / name)
    assert report.passed, [(issue.field, issue.message) for issue in report.issues]


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_each_proposal_limits_promotion_to_software_tests(name: str) -> None:
    proposal = _proposal(name)
    assert proposal["validation_status"] == "software_tested"
    assert proposal["mechanism_sources"]
    assert proposal["milestone_id"] == "BIO-004"
    assert proposal["plan_section"].startswith("foundation_progress/BIO_004_NEW_MECHANISMS_PLAN.md")
    assert f"({EXPECTED[name]})" in proposal["plan_section"]
    assert any("not calibration or independent empirical validation" in item for item in proposal["limitations"])


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_every_candidate_source_states_its_verification(name: str) -> None:
    sources = _proposal(name)["candidate_sources"]
    assert sources
    for source in sources:
        assert source["verification"].startswith(VERIFICATION_PREFIXES), source
        assert source["supports"].strip()
        if "doi" in source:
            assert source["doi"].startswith("10."), source


def test_no_proposal_defines_an_imposed_synergy_or_boost_factor() -> None:
    for name in EXPECTED:
        symbols = {str(parameter["symbol"]).lower() for parameter in _proposal(name)["parameters"]}
        assert not any("synergy" in symbol or "boost" in symbol or "efficiency" in symbol for symbol in symbols)
