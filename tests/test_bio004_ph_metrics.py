"""pH reductions preserve signed titrant and explicitly absent thresholds."""

from pathlib import Path
import json
import numpy as np
import pytest
from fungal_model.api.ph_metrics import trajectory_metrics
from fungal_model.workflows import run_configured_model

ROOT = Path(__file__).resolve().parents[1]


def test_threshold_interpolation_and_signed_titrant():
    rows = [
        {"time": t, "time_units": "hour", "pH": p, "titrant": ledger, "titrant_units": "mol/L"}
        for t, p, ledger in [(0, 6, 0), (1, 7, -0.1), (2, 8, -0.2)]
    ]
    metrics = {
        row["metric_name"]: row
        for row in trajectory_metrics(
            rows,
            {"ph": "pH", "ledger_titrant": "titrant"},
            medium_rows=[{"quantity": "ph_threshold", "value": 6.5, "units": "dimensionless"}],
        )
    }
    assert metrics["time_to_stated_ph_threshold"]["value"] == 0.5
    assert metrics["total_signed_titrant"]["value"] == -0.2
    absent = trajectory_metrics(rows, {"ph": "pH"})
    assert absent[-1]["status"] == "unknown"
    never = trajectory_metrics(
        rows, {"ph": "pH"}, medium_rows=[{"quantity": "ph_threshold", "value": 9, "units": "dimensionless"}]
    )
    assert never[-1]["status"] == "not_reached"
    assert trajectory_metrics(rows, {}) == []


def test_configured_ph_reports_analytical_proton_balance(tmp_path):
    result = run_configured_model(ROOT / "data/model_configs/toy_buffered_ph.yml", output_dir=tmp_path)
    rows = json.loads((tmp_path / "mechanism_metrics.json").read_text())
    metrics = {r["metric_name"]: r for r in rows}
    assert metrics["proton_balance_max_absolute_residual"]["value"] < 1e-8
    assert metrics["final_ph"]["value"] == pytest.approx(float(result.states["ph"].magnitude[-1]))
    assert np.isfinite(metrics["final_ph"]["value"])


def test_reusing_configured_output_removes_obsolete_mechanism_metrics(tmp_path):
    run_configured_model(ROOT / "data/model_configs/toy_buffered_ph.yml", output_dir=tmp_path)
    assert (tmp_path / "mechanism_metrics.json").exists()
    run_configured_model(ROOT / "data/model_configs/toy_homogeneous_ab.yml", output_dir=tmp_path)
    assert not (tmp_path / "mechanism_metrics.json").exists()
    assert not (tmp_path / "mechanism_metrics.csv").exists()
