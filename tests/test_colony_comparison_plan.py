"""The De Ligne 2019 colony comparison plan (COLONY-001) is a frozen contract.

Changing it requires a dated amendment inside the file, a new digest here and a
ledger entry, all before any stage that the change affects is run.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "data/benchmarks/de_ligne_2019_colony/plan.json"
DATASET_DIR = ROOT / "data/experiments/literature/de_ligne_2019_colony_growth"
PANEL_TABLE = ROOT / "data/experiments/source_intake/de_ligne_2019/digitized_panels.csv"
FROZEN_SHA256 = "2ce70b6b21b2d254f4d01d3fb5ec1523442299f2ed6ce2853c270fab712acd9d"
SHARED = {"Kv", "c_ext", "Dn", "a", "dn", "cu", "Di", "R0", "n0", "rho0"}


@pytest.fixture(scope="module")
def plan() -> dict:
    return json.loads(PLAN_PATH.read_text(encoding="utf-8"))


def test_plan_digest_is_the_frozen_one() -> None:
    assert hashlib.sha256(PLAN_PATH.read_bytes()).hexdigest() == FROZEN_SHA256


def test_plan_is_frozen_before_any_fit(plan) -> None:
    assert plan["status"].startswith("plan frozen 2026-10-06")
    assert [(entry["date"], entry["previous_sha256"][:8]) for entry in plan["amendments"]] == [
        ("2026-10-06", "e7a8706e"),
        ("2026-10-06", "ea6e2e72"),
        ("2026-10-06", "ca0e016c"),
    ]
    assert "detection density" in plan["amendments"][0]["reason"]
    assert "active translocation" in plan["amendments"][1]["reason"]
    assert "dish" in plan["amendments"][2]["reason"]
    assert plan["observation_operators"]["detection_density"] == {
        "value": 1.0,
        "units": "1 / millimeter",
        "meaning": plan["observation_operators"]["detection_density"]["meaning"],
    }
    assert "before the affected stage is run" in plan["amendment_rule"]
    results = PLAN_PATH.parent / "results"
    if results.exists():
        # Only stage 0 (software checks, no fit) may be recorded under this plan so far,
        # with the records that amendments 2 and 3 superseded kept as their evidence.
        assert sorted(path.name for path in results.iterdir()) == [
            "stage_0",
            "stage_0_superseded_ca0e016c",
            "stage_0_superseded_ea6e2e72",
        ]
        chain = {FROZEN_SHA256, *(entry["previous_sha256"] for entry in plan["amendments"])}
        for inputs_path in sorted(results.rglob("inputs.json")):
            inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
            assert inputs["plan_sha256"] in chain, inputs_path


def test_plan_pins_the_committed_dataset(plan) -> None:
    for name, digest in plan["data"]["dataset_sha256"].items():
        assert hashlib.sha256((DATASET_DIR / name).read_bytes()).hexdigest() == digest, name
    assert hashlib.sha256(PANEL_TABLE.read_bytes()).hexdigest() == plan["data"]["panel_table_sha256"]
    assert plan["data"]["row_rules"]["panel_disagreement"].startswith("excluded")


def test_parameters_have_roles_bounds_and_no_source_values(plan) -> None:
    parameters = {item["symbol"]: item for item in plan["model"]["parameters"]}
    assert {symbol for symbol, item in parameters.items() if item["role"] == "shared"} == SHARED
    assert {symbol for symbol, item in parameters.items() if item["role"] == "environment_scaled"} == {"v", "b"}
    assert parameters["phi_c"]["role"] == "per_condition" and parameters["phi_c"]["upper"] == 1.0
    for item in parameters.values():
        assert item["lower"] < item["upper"], item["symbol"]
        assert item["units"] and item["meaning"], item["symbol"]
        assert "value" not in item and "start" not in item, item["symbol"]
    assert "not measured constants" in plan["model"]["parameter_source"]


def test_hold_outs_cover_every_level_once(plan) -> None:
    held_out = [tuple(pair) for pair in plan["stage_C_held_out"]["held_out_conditions"]]
    assert sorted(temperature for temperature, _ in held_out) == [15, 20, 25, 30]
    assert sorted(humidity for _, humidity in held_out) == [65, 70, 75, 80]
    assert plan["stage_C_held_out"]["procedure"].find("nothing is refitted") >= 0


def test_operators_rules_and_exclusions_are_declared(plan) -> None:
    operators = plan["observation_operators"]
    assert "convex hull" in operators["mycelial_area"] and "outside the inoculum disc" in operators["tip_count"]
    rules = plan["decision_rules"]
    assert set(rules) >= {"R1_reproduces", "R2_transfers", "R3_identified", "R4_coverage", "outcome_vocabulary"}
    assert len(rules["outcome_vocabulary"]) == 4
    assert any("within-study transfer" in claim for claim in plan["excluded_claims"])
    assert plan["geometry"]["symmetry"].startswith("axisymmetric")
    assert plan["error_model"]["type"] == "per_series_linear_sd"
    assert "Rosso and Robinson 2001" in " ".join(plan["stage_0_software"]["items"])


def test_documentation_cites_the_frozen_digest() -> None:
    page = (ROOT / "docs/colony-comparison.md").read_text(encoding="utf-8")
    assert FROZEN_SHA256 in page
    assert "no fit has been run" in page
    ledger = (ROOT / "progress.md").read_text(encoding="utf-8")
    assert FROZEN_SHA256 in ledger


def test_amendment_2_removes_the_active_term_and_guards_grid_convergence(plan) -> None:
    symbols = {item["symbol"] for item in plan["model"]["parameters"]}
    assert "Da" not in symbols
    translocation = next(process for process in plan["model"]["processes"] if process["name"] == "translocation")
    assert "no active term" in translocation["law"]
    guard = plan["geometry"]["well_posedness_guard"]
    assert guard["max_relative_difference"] == 0.02
    assert any("stage A optimum" in item for item in guard["applies_to"])
    assert any("stage C prediction" in item for item in guard["applies_to"])
    assert plan["geometry"]["symmetry_check"]["max_relative_difference"] == 0.03
    assert "not grid converged" in plan["decision_rules"]["R0_grid_converged"]
    superseded = PLAN_PATH.parent / "results" / "stage_0_superseded_ea6e2e72"
    if superseded.exists():
        checks = json.loads((superseded / "checks.json").read_text(encoding="utf-8"))
        assert checks["grid"]["passed"] is False and checks["symmetry"]["passed"] is False
        assert checks["solver"]["passed"] is True
        assert checks["plan_sha256"].startswith("ea6e2e72")


def test_amendment_3_puts_the_wall_at_the_dish_and_reads_the_window_apart(plan) -> None:
    geometry = plan["geometry"]
    assert geometry["domain"]["radius_mm"] == 45.0 and geometry["domain"]["cells"] == 450
    assert geometry["domain"]["cell_mm"] == 0.1 and "declared assumption" in geometry["domain"]["reason"]
    assert geometry["window"]["side_mm"] == 40.0
    check = geometry["symmetry_check"]
    assert check["cartesian_cells"] * check["cartesian_cell_mm"] == geometry["window"]["side_mm"]
    assert check["max_tip_fraction_beyond_window"] == 0.001 and check["minimum_hours"] == 8
    assert "symmetry_threshold" not in geometry
    assert "900 cells" in geometry["well_posedness_guard"]["definition"]
    reason = plan["amendments"][2]["reason"]
    assert "recorded before any cartesian result at a finer cell" in reason
    assert "No model term, parameter, bound, operator, hold-out, stage or decision rule changed." in reason
    superseded = PLAN_PATH.parent / "results" / "stage_0_superseded_ca0e016c"
    if superseded.exists():
        checks = json.loads((superseded / "checks.json").read_text(encoding="utf-8"))
        assert checks["grid"]["passed"] is True and checks["solver"]["passed"] is True
        assert checks["symmetry"]["passed"] is False
        assert checks["plan_sha256"].startswith("ca0e016c")
