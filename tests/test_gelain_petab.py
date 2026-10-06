"""The Gelain cross-solver reproduction: frozen plan, exported problem and recorded results."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("libsbml", reason="requires the optional 'standards' extra")

from fungal_model.research import gelain_petab

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / gelain_petab.PLAN_PATH
RESULTS = ROOT / gelain_petab.RESULTS_PATH
FROZEN_SHA256 = "a0f8abe9561ad1936a2ef06055cd7af8a04cf4902008790d0a14c3cb58f3184a"


@pytest.fixture(scope="module")
def plan() -> dict:
    return json.loads(PLAN_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def problem(tmp_path_factory):
    return gelain_petab.build_problem(ROOT, tmp_path_factory.mktemp("gelain_petab") / "petab")


def test_plan_digest_is_the_frozen_one() -> None:
    assert hashlib.sha256(PLAN_PATH.read_bytes()).hexdigest() == FROZEN_SHA256


def test_plan_sources_still_carry_their_frozen_digests(plan) -> None:
    digests = gelain_petab.verify_sources(ROOT, plan)
    assert set(digests) == {"criticism_plan", "bayesian_plan", "observations", "reference_fit"}
    assert plan["amendments"] == []
    assert plan["status"].startswith("plan frozen")


def test_exported_problem_matches_the_plan_and_lints(problem, plan) -> None:
    export = problem.export
    lines = export.measurements.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "observableId\tsimulationConditionId\tmeasurement\ttime"
    assert len(lines) - 1 == plan["problem"]["observations"] == 96
    parameters = [line.split("\t") for line in export.parameters.read_text(encoding="utf-8").splitlines()[1:]]
    assert [row[0] for row in parameters] == [f"gelain_hydrolysis_{s}" for s in ("k_h", "Kh", "Y", "kd", "K_ind", "qF", "kF", "qB", "kB")]
    assert {row[2] for row in parameters} == {"log10"} and {row[6] for row in parameters} == {"1"}
    header, *rows = [line.split("\t") for line in export.conditions.read_text(encoding="utf-8").splitlines()]
    assert header[:2] == ["conditionId", "conditionName"] and "cellulose_concentration" in header
    loading = header.index("cellulose_concentration")
    assert [(row[0], float(row[loading])) for row in rows] == [
        ("gelain_2020_cellulose_10gl", 10.0), ("gelain_2020_cellulose_20gl", 20.0), ("gelain_2020_cellulose_30gl", 30.0),
    ]
    assert problem.observable_ids == tuple(f"observable_{name}" for name in plan["problem"]["observables"])
    pytest.importorskip("petab", reason="requires petab for validation")
    import petab.v1 as petab_v1

    assert petab_v1.lint_problem(petab_v1.Problem.from_yaml(str(export.problem_yaml))) is False


def test_fungmod_objective_on_the_exported_problem_is_the_stage_a_objective(problem, plan) -> None:
    """The PEtab objective at the nominal values reproduces twice the recorded least-squares cost."""

    fit = gelain_petab.reference_fit(ROOT, plan)
    assert problem.fungmod_objective() == pytest.approx(2.0 * fit["cost"], rel=1e-7)
    metadata = json.loads((problem.export.directory / "problem_metadata.json").read_text(encoding="utf-8"))
    assert metadata["plan_sha256"] == FROZEN_SHA256
    assert metadata["reference_objective"] == pytest.approx(2.0 * fit["cost"])
    predictor = problem.fungmod_predictor()
    seconds = np.array([8.0, 96.0]) * 3600.0
    predicted = predictor("gelain_2020_cellulose_10gl", seconds)
    assert set(predicted) == set(problem.observable_ids)
    assert predicted["observable_substrate"][0] < 10.0


def test_recorded_results_cite_the_plan_and_their_gates_are_consistent(plan) -> None:
    comparison_path = RESULTS / "comparison.json"
    if not comparison_path.exists():
        pytest.skip("no COPASI reproduction recorded yet")
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    assert comparison["plan_sha256"] == FROZEN_SHA256
    gates = plan["gates"]
    simulation, optimum = comparison["simulation_gate"], comparison["optimum_gate"]
    assert simulation["passed"] == (
        simulation["worst_abs_difference_over_sigma"] <= gates["simulation_agreement"]["max_abs_difference_over_sigma"]
        and simulation["objective_relative_difference"] <= gates["simulation_agreement"]["objective_relative_difference"]
    )
    assert optimum["passed"] == (optimum["relative_difference"] <= gates["optimum_agreement"]["objective_relative_difference"])
    expected = "copasi_improves" if optimum["copasi_improves"] else ("reproduced" if simulation["passed"] and optimum["passed"] else "not_reproduced")
    assert comparison["outcome"] == expected
    assert comparison["settings"]["as_planned"] is True
    assert len(optimum["start_objectives"]) == plan["copasi"]["random_starts"]
    reproduction = json.loads((RESULTS / "copasi" / "copasi_reproduction.json").read_text(encoding="utf-8"))
    assert reproduction["best"]["objective"] == optimum["copasi_best_objective"]
    assert all(row["weight"] == pytest.approx(1.0 / row["sigma"] ** 2) for row in reproduction["weights"])
    assert (RESULTS / "report.md").read_text(encoding="utf-8").startswith("# Gelain 2020 cross-solver reproduction")


def test_copasi_reproduces_the_problem_from_the_nominal_values(tmp_path) -> None:
    from fungal_model.standards.copasi import copasi_available

    if not copasi_available():
        pytest.skip("requires the optional 'copasi' extra")
    comparison = gelain_petab.run_reproduction(ROOT, output_dir=tmp_path, starts=0, seed=1)
    assert comparison["settings"]["as_planned"] is False
    assert comparison["simulation_gate"]["passed"], comparison["simulation_gate"]
    assert comparison["optimum_gate"]["local_fit_objective"] <= comparison["optimum_gate"]["reference_objective"] * 1.001
