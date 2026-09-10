from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from fungal_model import run_configured_model


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("cross_source_study", ROOT / "scripts/run_cross_source_structural_test.py")
assert SPEC is not None and SPEC.loader is not None
study = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = study
SPEC.loader.exec_module(study)


def test_study_trajectory_matches_configured_source_law(tmp_path: Path) -> None:
    result = run_configured_model(
        ROOT / "data/model_configs/alvarez_gonzalez_2022_free_beta_glucosidase_comparison.yml",
        output_dir=tmp_path / "configured",
    )
    times = np.asarray(result.time.to("minute").magnitude)
    parameters = {"V_max": 19.72544, "K_m": 43.0, "K_p": 34.0}
    for observable, state in (("substrate", "cellobiose_concentration"), ("product", "glucose_concentration")):
        predicted = study.simulate(replace(study.SERIES[0], observable=observable), times, parameters)
        np.testing.assert_allclose(predicted, result.states[state].magnitude, rtol=2e-6, atol=1e-6)


def test_persibgl1_does_not_import_a_pnpg_constant() -> None:
    series = next(s for s in study.SERIES if s.key == "ariaeenejad_persibgl1")
    assert not hasattr(series, "fixed_km_mM")
    assert "not transferred" in series.notes
    assert "pNPG" in series.notes
    assert series.k_i_mM is None


def test_extended_fit_includes_the_feasible_base_fit() -> None:
    # Regression: this real series previously gave a worse extended optimum.
    series = next(s for s in study.SERIES if s.key == "alvarez_A70")
    base = study.fit(series, with_deactivation=False)
    extended = study.fit(series, with_deactivation=True, base_fit=base)
    assert extended["rmse"] <= base["rmse"] + 1e-8 * max(1.0, base["rmse"])
    assert extended["optimizer_attempts"][0]["start"] == {**base["fitted"], "k_d": 0.0}
    assert "bound_pinned_symbols" in extended
    assert "jacobian_condition_number" in extended
    assert extended["identifiability"] == "not_established_by_local_optimizer_diagnostics"


@pytest.mark.parametrize("failure", ["unsuccessful", "incomplete", "nonfinite"])
def test_study_refuses_bad_solver_results(monkeypatch, failure) -> None:
    result = SimpleNamespace(success=failure != "unsuccessful", message="test solver failure",
                             y=np.zeros((2, 2)))
    if failure == "incomplete":
        result.y = np.zeros((2, 1))
    if failure == "nonfinite":
        result.y[0, 0] = np.nan
    monkeypatch.setattr(study, "solve_ivp", lambda *args, **kwargs: result)
    with pytest.raises(study.StudyError, match="integration"):
        study.simulate(study.SERIES[0], np.array([0.0, 1.0]), {"V_max": 1.0, "K_m": 1.0, "K_p": 1.0})


def test_failed_optimizer_cannot_produce_a_fit(monkeypatch) -> None:
    failure = SimpleNamespace(success=False, message="evaluation limit", nfev=1,
                              x=np.ones(3), fun=np.ones(9), jac=np.ones((9, 3)))
    monkeypatch.setattr(study, "least_squares", lambda *args, **kwargs: failure)
    with pytest.raises(study.StudyError, match="no optimizer start converged"):
        study.fit(study.SERIES[0], with_deactivation=False)


def test_study_output_does_not_promote_training_improvement_to_a_mechanism(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(study, "SERIES", (study.SERIES[0],))

    def fake_fit(series, *, with_deactivation, base_fit=None):
        return {"fitted": {"V_max": 1.0, "K_m": 1.0, "K_p": 1.0, "k_d": 1.0},
                "rmse": 0.1 if with_deactivation else 10.0, "n_free": 4 if with_deactivation else 3}

    monkeypatch.setattr(study, "fit", fake_fit)
    summary = study.run(tmp_path)
    persisted = json.loads((tmp_path / "cross_source_summary.json").read_text())
    assert persisted == json.loads(json.dumps(summary))
    assert persisted["schema_version"] == "2.0.0"
    row = persisted["series"][study.SERIES[0].key]
    assert row["mechanism_conclusion"] == "not_established_by_training_fit"
    assert "deactivation_warranted" not in row
    assert "Every series here is fitted" in persisted["claim_boundary"]
