"""Mechanism-law records have checked equation locations, scopes and integrity."""

from pathlib import Path
import hashlib
import pytest
import yaml
from fungal_model.provenance import load_mechanism_source, validate_mechanism_source_links

ROOT = Path(__file__).resolve().parents[1]
SOURCES = sorted((ROOT / "data/mechanism_sources").glob("*/source.yml"))


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.parent.name)
def test_frozen_source_records(path):
    record = load_mechanism_source(path)
    assert "law_form" in record["supports"]
    assert record["limitations"]
    for equation in record["equations"]:
        assert equation["location"] and equation["interpretation"]


def test_promoted_mechanism_requires_checked_law_form():
    with pytest.raises(ValueError, match="mechanism_sources"):
        validate_mechanism_source_links({"validation_status": "software_tested"}, root=ROOT)
    validate_mechanism_source_links(
        {"validation_status": "source_supported", "mechanism_sources": [str(SOURCES[0].relative_to(ROOT))]}, root=ROOT
    )


def test_source_artifact_integrity_and_scope(tmp_path):
    record = yaml.safe_load(SOURCES[0].read_text())
    artifact = tmp_path / "extract.txt"
    artifact.write_text("Equation transcription")
    record["artifacts"] = [{"path": "extract.txt", "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}]
    source = tmp_path / "source.yml"
    source.write_text(yaml.safe_dump(record))
    load_mechanism_source(source)
    artifact.write_text("Changed")
    with pytest.raises(ValueError, match="digest"):
        load_mechanism_source(source)
    record["artifacts"][0]["path"] = "../extract.txt"
    source.write_text(yaml.safe_dump(record))
    with pytest.raises(ValueError, match="inside"):
        load_mechanism_source(source)


@pytest.mark.parametrize("field", ["id", "location", "expression", "interpretation", "assumptions", "validity", "limitations"])
def test_source_null_or_blank_evidence_is_not_checked(field, tmp_path):
    record = yaml.safe_load(SOURCES[0].read_text())
    if field in {"assumptions", "validity", "limitations"}:
        record[field] = [None, ""]
    else:
        record["equations"][0][field] = None
    path = tmp_path / "source.yml"
    path.write_text(yaml.safe_dump(record))
    with pytest.raises(ValueError):
        load_mechanism_source(path)


def test_mapping_enforcement_cannot_bypass_promoted_source_gate():
    from fungal_model.validation.bio_readiness import enforce_bio_mechanism_proposal, BioReadinessValidationError
    proposal = yaml.safe_load((ROOT / "foundation_progress/proposals/BIO_004_PROTON_BALANCE_PH.yml").read_text())
    enforce_bio_mechanism_proposal(proposal)
    proposal.pop("mechanism_sources")
    with pytest.raises(BioReadinessValidationError, match="mechanism_sources"):
        enforce_bio_mechanism_proposal(proposal)
