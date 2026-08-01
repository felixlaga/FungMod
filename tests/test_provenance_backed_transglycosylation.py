from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import yaml

from fungal_model import example_data_path, run_configured_model
from fungal_model.validation.bio_readiness import validate_bio_mechanism_proposal_file


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "data/model_configs/phanerochaete_bgl1b_cellobiose_transglycosylation.yml"
PROPOSAL = ROOT / "foundation_progress/proposals/BIO_003_SUBSTRATE_TRANSGLYCOSYLATION.yml"
SOURCE = "https://doi.org/10.1007/s00253-006-0526-z"
MATURITY = "literature_backed_software_tested"


def test_transglycosylation_proposal_passes_biology_readiness_gate() -> None:
    report = validate_bio_mechanism_proposal_file(PROPOSAL)
    proposal = yaml.safe_load(PROPOSAL.read_text(encoding="utf-8"))

    assert report.passed, report.to_dict()
    assert proposal["mechanism_id"] == "substrate_transglycosylation"
    assert proposal["validation_status"] == "software_tested"
    assert "S^2/Km_t" in proposal["mathematical_law"]
    assert "whole-organism physiology" in " ".join(proposal["not_in_scope"])
    assert proposal["primary_provenance"]["url"] == (
        "https://doi.org/10.1016/j.carres.2004.09.019"
    )
    assert proposal["example_parameter_provenance"]["url"] == SOURCE


def test_bgl1b_config_preserves_reported_parameters_and_scenario_boundary() -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    parameters = {
        parameter["symbol"]: (parameter["value"], parameter["uncertainty"], parameter["units"])
        for parameter_set in config["parameters"]
        for parameter in parameter_set["parameters"]
    }

    assert parameters == {
        "BGL1B_Km_h": (0.218, 0.017, "millimolar"),
        "BGL1B_kcat_h": (16.4, 0.4, "1 / second"),
        "BGL1B_Km_t": (3.20, 0.69, "millimolar"),
        "BGL1B_kcat_t": (8.77, 1.65, "1 / second"),
    }
    assert {process["branch"] for process in config["processes"]} == {
        "hydrolysis",
        "transglycosylation",
    }
    assert all(process["primary_source"] == SOURCE for process in config["processes"])
    assert all(process["maturity"] == MATURITY for process in config["processes"])
    assert "scenario choices, not source assay values" in config["provenance"]["notes"]
    assert "not whole-fungus behavior" in config["provenance"]["validity_range"]


def test_bgl1b_config_runs_both_competing_branches_with_conservation(tmp_path: Path) -> None:
    output_dir = tmp_path / "bgl1b"

    result = run_configured_model(CONFIG, output_dir=output_dir)

    substrate = np.asarray(result.states["cellobiose_concentration"].magnitude, dtype=float)
    glucose = np.asarray(result.states["glucose_concentration"].magnitude, dtype=float)
    transfer_product = np.asarray(
        result.states["cellobiose_derived_trisaccharide_concentration"].magnitude,
        dtype=float,
    )
    hydrolysis_rate = np.asarray(result.process_rates["bgl1b_cellobiose_hydrolysis"].magnitude)
    transfer_rate = np.asarray(
        result.process_rates["bgl1b_cellobiose_substrate_transfer"].magnitude
    )
    glucose_equivalents = 2.0 * substrate + glucose + 3.0 * transfer_product

    assert substrate[-1] < substrate[0]
    assert glucose[-1] > 0.0
    assert transfer_product[-1] > 0.0
    assert transfer_rate[0] > hydrolysis_rate[0]
    assert transfer_rate[-1] < hydrolysis_rate[-1]
    assert glucose_equivalents == pytest.approx(np.full_like(glucose_equivalents, 20.0), abs=1.0e-8)
    assert all(item["passed"] for item in result.validation_report())

    metadata = json.loads((output_dir / "configured_metadata.json").read_text(encoding="utf-8"))
    laws = metadata["configured_process_laws"]
    assert {row["branch"] for row in laws} == {"hydrolysis", "transglycosylation"}
    assert all(row["primary_source"] == SOURCE for row in laws)
    assert all(row["maturity"] == MATURITY for row in laws)
    assert all("r_t = E*kcat_t" in row["equation"] for row in laws)
    assert all("whole-fungus physiology" in row["limitation"] for row in laws)


def test_packaged_bgl1b_config_runs_outside_checkout(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)

    result = run_configured_model(
        example_data_path("model_configs/phanerochaete_bgl1b_cellobiose_transglycosylation.yml"),
        output_dir=tmp_path / "packaged_bgl1b",
    )

    assert result.states["cellobiose_derived_trisaccharide_concentration"][-1].magnitude > 0.0
