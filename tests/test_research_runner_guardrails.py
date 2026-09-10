from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]


def _runner(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_stage2_stops_before_predicting_from_a_failed_fit(monkeypatch, tmp_path):
    runner = _runner("run_alvarez_gonzalez_2022_stage2_calibration")
    monkeypatch.setattr(runner, "calibrate_configured_model", lambda **kwargs: SimpleNamespace(success=False))
    monkeypatch.setattr(runner, "_predict", lambda *args: pytest.fail("Failed fit reached prediction"))
    with pytest.raises(RuntimeError, match="did not converge"):
        runner.run(tmp_path)
    assert not (tmp_path / "stage2_summary.json").exists()


def test_hypothesis_integrator_matches_current_configured_trajectory():
    runner = _runner("run_alvarez_gonzalez_2022_mechanism_hypotheses")
    assert runner.verify_against_configured_model() <= runner.VERIFY_TOLERANCE


@pytest.mark.parametrize("target", ["fit_on_training", "fit_exponent"])
def test_hypothesis_runner_rejects_failed_optimization(monkeypatch, target):
    runner = _runner("run_alvarez_gonzalez_2022_mechanism_hypotheses")
    monkeypatch.setattr(runner, "least_squares", lambda *args, **kwargs: SimpleNamespace(
        success=False, x=np.ones(4), fun=np.ones(9), message="evaluation limit"))
    with pytest.raises(RuntimeError, match="did not converge"):
        if target == "fit_on_training":
            runner.fit_on_training(free_kd=False)
        else:
            runner.fit_exponent("B20", {"V_max": 1.0, "K_m": 1.0, "K_p": 1.0, "k_d": 0.0})


def test_hypothesis_report_cannot_emit_fixed_biological_verdicts(monkeypatch, tmp_path):
    runner = _runner("run_alvarez_gonzalez_2022_mechanism_hypotheses")
    monkeypatch.setattr(runner, "verify_against_configured_model", lambda: 0.0)
    monkeypatch.setattr(runner, "fit_on_training", lambda **kwargs: (
        {"V_max": 1.0, "K_m": 1.0, "K_p": 1.0, "k_d": 0.0}, 0.1))
    monkeypatch.setattr(runner, "held_out_errors", lambda *args: {"A70": 1.0, "B20": 1.0, "B70": 1.0})
    monkeypatch.setattr(runner, "fit_exponent", lambda *args: 0.5)
    monkeypatch.setattr(runner, "simulate", lambda initial, times, *args: np.full(len(times), initial))
    monkeypatch.setattr(sys, "argv", ["study", "--output-dir", str(tmp_path)])
    runner.main()
    report = json.loads((tmp_path / "mechanism_hypotheses.json").read_text())
    assert report["schema_version"] == "2.0.0"
    assert all(h["verdict"] == "not_established_by_exploratory_comparison" for h in report["hypotheses"].values())
    assert report["hypotheses"]["first_order_deactivation"]["with_deactivation"]["half_life_min"] is None
