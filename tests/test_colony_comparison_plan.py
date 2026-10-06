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
FROZEN_SHA256 = "e7a8706e85fef7739e96c7fe21d8aac0cbf2e4719201b1c203c9296d033066e4"
SHARED = {"Kv", "c_ext", "Dn", "a", "dn", "cu", "Di", "Da", "R0", "n0", "rho0"}


@pytest.fixture(scope="module")
def plan() -> dict:
    return json.loads(PLAN_PATH.read_text(encoding="utf-8"))


def test_plan_digest_is_the_frozen_one() -> None:
    assert hashlib.sha256(PLAN_PATH.read_bytes()).hexdigest() == FROZEN_SHA256


def test_plan_is_frozen_before_any_fit(plan) -> None:
    assert plan["status"].startswith("plan frozen 2026-10-06")
    assert plan["amendments"] == []
    assert "before the affected stage is run" in plan["amendment_rule"]
    assert not (PLAN_PATH.parent / "results").exists(), "no result may exist before stage 0 is built and recorded"


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
