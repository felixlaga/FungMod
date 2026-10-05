"""Check provenance and prevent simulations/initial conditions becoming observations."""
from __future__ import annotations

import csv
import importlib.util
import io
from pathlib import Path

import pytest
import yaml

from fungal_model.data import load_dataset_candidate_review, load_experiment_dataset

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("prepare_public_data", ROOT / "scripts/prepare_public_experimental_data.py")
assert SPEC and SPEC.loader
extractor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(extractor)


def test_committed_extractions_reproduce_from_pinned_source_bytes() -> None:
    for path, expected in extractor.prepare(ROOT).items():
        assert (ROOT / path).read_bytes() == expected, path


def test_source_corruption_fails_before_extraction(tmp_path: Path) -> None:
    import json

    root = tmp_path / extractor.INTAKE
    root.mkdir(parents=True)
    (root / "source").write_bytes(b"changed")
    (root / "manifest.json").write_text(json.dumps({"files": [
        {"path": "source", "bytes": 7, "sha256": "0" * 64},
    ]}))
    with pytest.raises(ValueError, match="checksum mismatch"):
        extractor.prepare(tmp_path)


@pytest.mark.parametrize("substrate,concentration", extractor.CASES)
def test_culture_datasets_load_with_unknown_errors_and_no_initial_observations(substrate, concentration) -> None:
    path = ROOT / extractor.LITERATURE / f"gelain_2020_{substrate}_{concentration}gl.yml"
    dataset = load_experiment_dataset(path)
    metadata = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert dataset.validate().passed
    assert dataset.maturity == "literature_processed"
    assert dataset.system.organism == "Trichoderma harzianum P49P11"
    assert {s.measurement_id for s in dataset.measurements} == {"biomass", "substrate"}
    for series in dataset.measurements:
        assert [point.time for point in series.points] == extractor.TIMES[1:]
        assert all(point.uncertainty is None for point in series.points)
        assert series.value_units == "gram / liter"
        assert "unknown" in series.uncertainty_type
    assert metadata["validation"]["allow_missing_uncertainty"] is True
    assert metadata["preprocessing"]["raw_data_available"] is False
    assert "independent external validation" in metadata["preprocessing"]["notes"]


def test_all_recorded_values_have_source_cells_but_no_invented_replicates() -> None:
    raw = (ROOT / extractor.INTAKE / "gelain_2020/recorded_values.csv").read_text(encoding="utf-8")
    rows = list(csv.DictReader(io.StringIO(raw)))
    assert len(rows) == 162
    assert sum(r["record_role"] == "published_mean" for r in rows) == 144
    assert sum(r["record_role"] == "source_initial_condition" for r in rows) == 18
    assert all(r["replicate_id"] == r["uncertainty"] == "" for r in rows)
    assert all(r["source_cell"] and r["source_sheet"] == "Plan1" for r in rows)
    assert not any("data.xlsx" in r["source_file"] for r in rows)
    # Keep real reported reversals and zeros, not artificial monotone curves.
    selected = {float(r["time_h"]): float(r["value"]) for r in rows
                if r["condition_id"] == "gelain_2020_cellulose_10gl" and r["observable"] == "substrate"}
    assert selected[96] > selected[72]
    assert {r["source_units"] for r in rows if r["observable"] == "cellulase_activity"} == {"FPU/L"}


def test_secretome_is_preserved_as_endpoint_spectral_abundance() -> None:
    path = ROOT / extractor.INTAKE / "novy_2021/proteins_all.csv"
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 232
    assert rows[0]["TRIRE2"] == "123989"
    assert float(rows[0]["NBSK"]) == pytest.approx(737.66)
    assert "time" not in rows[0]
    assert "secretion_rate" not in rows[0]


def test_candidate_review_remains_ingestion_only() -> None:
    review = load_dataset_candidate_review(
        ROOT / "data/experiments/candidate_reviews/gelain_2020_t_harzianum_review.yml"
    )
    assert review.validate().passed
    assert review.status == "approved_for_ingestion"
    assert "data ingestion only" in review.notes


def test_readiness_documentation_preserves_source_and_prediction_boundaries() -> None:
    intake = (ROOT / extractor.INTAKE / "README.md").read_text(encoding="utf-8")
    readiness = (ROOT / "docs/paper-readiness.md").read_text(encoding="utf-8")
    assert "144 published mean values" in intake
    assert "18 initial-condition entries" in intake
    assert "normalized total spectra" in intake
    assert "data.xlsx" in intake and "simulations" in intake
    assert "not yet a validated general predictor" in readiness
    assert "retrospective, within-study" in readiness
    assert "No unknowns are" in readiness
    assert "paper-readiness.md" in (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
