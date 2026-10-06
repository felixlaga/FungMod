"""COLONY-001 stage 0: the plan's data, error model, model and observables, with no fit."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from fungal_model.core.numerics import SolverSettings
from fungal_model.core.units import Q_
from fungal_model.research import colony_comparison as study

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def plan() -> dict:
    return study.load_plan(ROOT)


def test_load_plan_verifies_the_pinned_dataset_digests(tmp_path: Path, plan: dict) -> None:
    assert plan["_sha256"] == study.file_digest(ROOT / study.PLAN_PATH)
    root = tmp_path
    for relative in (study.PLAN_PATH, study.PANEL_TABLE):
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_bytes((ROOT / relative).read_bytes())
    directory = root / plan["data"]["directory"]
    directory.mkdir(parents=True)
    for name in plan["data"]["dataset_sha256"]:
        (directory / name).write_bytes((ROOT / plan["data"]["directory"] / name).read_bytes())
    tampered = directory / next(iter(plan["data"]["dataset_sha256"]))
    tampered.write_text(tampered.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
    with pytest.raises(study.ColonyComparisonError, match="digest"):
        study.load_plan(root)


def test_observations_follow_the_row_rules_and_cover_every_condition(plan: dict) -> None:
    for species in plan["data"]["species_order"]:
        observations = study.load_observations(ROOT, plan, species)
        assert len(observations) == 32
        for key, series in observations.items():
            assert key == series.key and series.species == species
            assert all(1 <= hour <= 62 for hour in series.hours)
            assert len(series.hours) == len(set(series.hours)) >= 55 - len(series.excluded)
            assert all("panel_disagreement" not in flags for flags in series.flags)
            assert all(reason == "panel_disagreement" for _, reason in series.excluded)
            assert all(value >= 0.0 for value in series.values)
            assert all(sd is None or sd >= 0.0 for sd in series.standard_deviations)


def test_error_models_fit_readable_rows_and_pool_short_series(plan: dict) -> None:
    observations = study.load_observations(ROOT, plan, "c_puteana")
    models = study.fit_error_models(observations, plan)
    minimum = plan["error_model"]["minimum_readable_rows"]
    assert set(models) == set(observations)
    for key, model in models.items():
        assert np.isfinite(model.s0) and np.isfinite(model.s1)
        assert model.pooled == (model.readable_rows < minimum)
        assert (model.pooled_rows > 0) == model.pooled
        series = observations[key]
        floor = np.asarray(series.digitization_uncertainties)
        sigma = model.sigma(np.asarray(series.values), floor)
        assert np.all(sigma >= floor) and np.all(np.isfinite(sigma))
    # A synthetic series recovers its own linear law exactly.
    base = observations[("area", 20, 75)]
    ys = np.asarray(base.values[:20])
    synthetic = study.ConditionObservations(
        "c_puteana", "area", 20, 75, base.hours[:20], tuple(ys), tuple(0.1 + 0.2 * ys), base.digitization_uncertainties[:20],
        tuple(() for _ in ys), (),
    )
    fitted = study.fit_error_models({synthetic.key: synthetic}, plan)[synthetic.key]
    assert fitted.s0 == pytest.approx(0.1) and fitted.s1 == pytest.approx(0.2) and not fitted.pooled


def test_plan_model_builds_on_both_geometries_with_the_inoculum_only(plan: dict) -> None:
    values = dict(study.STAGE_0_CHECK_VALUES)
    study.check_within_bounds(plan, values)
    with pytest.raises(study.ColonyComparisonError, match="outside the plan's bounds"):
        study.check_within_bounds(plan, {**values, "v": 100.0})
    with pytest.raises(study.ColonyComparisonError, match="missing"):
        study.check_within_bounds(plan, {symbol: value for symbol, value in values.items() if symbol != "Da"})
    scaled = study.scaled_values(values, 0.5)
    assert scaled["v"] == values["v"] * 0.5 and scaled["b"] == values["b"] * 0.5 and scaled["Kv"] == values["Kv"]
    with pytest.raises(study.ColonyComparisonError, match="phi"):
        study.scaled_values(values, 1.5)
    for geometry, cells in (("axisymmetric", 50), ("cartesian", 40)):
        model = study.colony_model(plan, values, geometry=geometry, cells=cells)
        compiled = model.compile()
        assert {process.name for process in model.processes} == {
            "extension", "motion", "branching", "anastomosis", "tip_death", "uptake", "translocation"
        }
        assert sorted(parameter.symbol for parameter in model.parameters) == sorted(("v", "b") + tuple(s for s in study.SHARED_SYMBOLS if s not in ("R0", "n0", "rho0")))
        assert all(parameter.confidence_level == "testing" for parameter in model.parameters)
        fields = study.initial_fields(model, plan, values)
        disc_mm = plan["geometry"]["inoculum"]["radius_mm"]
        reserve = np.asarray(fields["reserve"].magnitude)
        assert reserve.max() == values["R0"] and np.asarray(fields["internal"].magnitude).max() == 0.0
        occupied = model.grid.cell_measures[reserve > 0].sum() * 1e6
        assert occupied == pytest.approx(np.pi * disc_mm**2, rel=0.05 if geometry == "axisymmetric" else 0.2)
        assert compiled.initial_state(fields).shape == (4 * model.grid.cell_count,)
    with pytest.raises(study.ColonyComparisonError, match="cell count"):
        study.colony_grid(plan, geometry="cartesian")


def test_observables_start_at_the_disc_and_the_plan_solver_is_declared(plan: dict) -> None:
    values = {**study.STAGE_0_CHECK_VALUES, "v": 1.0, "b": 1.0, "n0": 20.0, "rho0": 20.0, "R0": 200.0}
    result = study.simulate_condition(
        plan, values, 1.0, hours=[1, 2, 3], cells=60, solver=SolverSettings(method="BDF", rtol=1e-6, atol=1e-9)
    )
    observed = study.observables(result, plan)
    assert observed["time_h"].tolist() == [0.0, 1.0, 2.0, 3.0]
    disc_area_cm2 = np.pi * plan["geometry"]["inoculum"]["radius_mm"] ** 2 / 100.0
    assert observed["mycelial_area_cm2"][0] == pytest.approx(disc_area_cm2)
    assert observed["tip_count"][0] == 0.0 and observed["tip_count"][-1] > 0.0
    assert np.all(np.diff(observed["mycelial_area_cm2"]) >= 0.0)
    primary = study.plan_solver(plan)
    assert primary.method == "LSODA" and study.plan_solver(plan, "check").method == "BDF"
    assert result.maturity == "exploratory"


def test_stage_0_records_checks_that_cite_the_plan(tmp_path: Path, plan: dict) -> None:
    messages: list[str] = []
    summary = study.run_stage_0(
        ROOT, tmp_path, hours=[1, 2], radial_cells=40, cartesian_cells=16, log=messages.append
    )
    output = tmp_path / "stage_0"
    inputs = json.loads((output / "inputs.json").read_text(encoding="utf-8"))
    assert inputs["plan_sha256"] == plan["_sha256"] and inputs["as_declared"] is False
    assert inputs["check_values"] == study.STAGE_0_CHECK_VALUES
    checks = json.loads((output / "checks.json").read_text(encoding="utf-8"))
    assert checks["plan_sha256"] == plan["_sha256"]
    assert set(checks["grid"]["relative_differences"]) == {"tip_count", "mycelial_area_cm2"}
    assert checks["symmetry"]["status"] == "run" and checks["symmetry"]["cartesian_cells"] == 16
    assert isinstance(checks["grid"]["passed"], bool) and isinstance(checks["solver"]["passed"], bool)
    errors = json.loads((output / "error_models.json").read_text(encoding="utf-8"))
    assert set(errors["series"]) == set(plan["data"]["species_order"])
    assert len(errors["series"]["r_solani"]) == 32
    assert summary["checks"]["timing"]["seconds_per_condition"] > 0.0
    assert any("grid check" in message for message in messages)
    skipped = study.run_stage_0(ROOT, tmp_path / "skip", hours=[1], radial_cells=40, cartesian_cells=None)
    assert skipped["checks"]["symmetry"]["status"] == "not run"
    assert Q_(1.0, "centimeter ** 2").to("millimeter ** 2").magnitude == 100.0
