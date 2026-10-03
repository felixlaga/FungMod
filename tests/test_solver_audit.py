"""Real depletion regression and preservation of the retrospective evidence boundary."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from fungal_model.core.numerics import SolverSettings
from fungal_model.core.units import Q_
from fungal_model.research.gelain_culture import CultureBenchmarkError, parameters_from_records
from fungal_model.research.gelain_joint import load_joint_cultures
from fungal_model.research.gelain_models import simulate_candidate

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("solver_audit", ROOT/"scripts/run_solver_thermodynamic_audit.py")
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def case():
    condition = next(c for c in load_joint_cultures(ROOT) if c.design.condition_id == "gelain_2020_cellulose_20gl")
    record = json.loads((ROOT/"data/benchmarks/gelain_2020_v2/results/frozen_predictions/gelain_2020_cellulose_20gl_effective_correlated_assumption.json").read_text())
    return condition, record


def test_real_depletion_case_resolves_with_named_controls_and_retains_roundoff():
    condition, frozen = case()
    parameters = parameters_from_records(frozen["fit"]["parameters"])
    result = simulate_candidate(condition.design, condition.initial_activities, parameters, model="effective",
        hypothesis_source=frozen["fit"]["hypothesis_source"], solver_settings=runner.refined_controls(condition,"effective","BDF"))
    reference = simulate_candidate(condition.design, condition.initial_activities, parameters, model="effective",
        hypothesis_source=frozen["fit"]["hypothesis_source"], method="DOP853", rtol=1e-10, atol=1e-12)
    assert result.solver["minimum_state"] >= -1e-13
    assert result.solver["settings"]["max_step"]["value"] == .1
    np.testing.assert_allclose(result.values, reference.values, rtol=2e-6, atol=1e-8)
    assert result.maturity == "exploratory_software_tested"


def test_audit_rejects_holdout_leakage_and_changed_times_before_integration():
    condition, frozen = case()
    leaking = deepcopy(frozen)
    leaking["fit"]["training_conditions"].append(condition.design.condition_id)
    with pytest.raises(ValueError, match="held-out"):
        runner.replay_record(condition, leaking)
    frozen["times_h"][0] += 1
    with pytest.raises(ValueError, match="times"):
        runner.replay_record(condition, frozen)


def test_explicit_controls_reject_ambiguous_or_incomplete_tolerances():
    condition, frozen = case()
    args = dict(model="effective", hypothesis_source=frozen["fit"]["hypothesis_source"])
    parameters = parameters_from_records(frozen["fit"]["parameters"])
    with pytest.raises(CultureBenchmarkError, match="not both"):
        simulate_candidate(condition.design, condition.initial_activities, parameters, **args,
                           solver_settings=SolverSettings(), method="BDF")
    with pytest.raises(ValueError, match="exactly"):
        simulate_candidate(condition.design, condition.initial_activities, parameters, **args,
                           solver_settings=SolverSettings(atol={"substrate": Q_(1e-14, "g/L")}))


def test_audit_never_overwrites_an_existing_output(tmp_path):
    (tmp_path/"existing.txt").write_text("preserve")
    with pytest.raises(ValueError, match="empty"):
        runner.run(ROOT, tmp_path)
    assert (tmp_path/"existing.txt").read_text() == "preserve"
