"""The Gelain model-criticism plan is a frozen contract.

Changing it requires a dated amendment inside the file, a new digest here and a
ledger entry, all before any fit that the change affects is run.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "data/benchmarks/gelain_2020_criticism/plan.json"
FROZEN_SHA256 = "6849c8b3355d7c2f0906e8be0a3c18bab1b5c54926289573fd4e6090dc42eb86"
COMMON_SYMBOLS = {"k_h", "Kh", "Y", "kd", "K_ind", "qF", "kF", "qB", "kB"}
EXPECTED_PARAMETER_COUNTS = {
    "M0_baseline": 9,
    "M1_induction_state": 10,
    "M2_soluble_product_pool": 13,
    "M3_conversion_dependent_accessibility": 10,
}


@pytest.fixture(scope="module")
def plan() -> dict:
    return json.loads(PLAN_PATH.read_text(encoding="utf-8"))


def test_plan_digest_is_the_frozen_one() -> None:
    assert hashlib.sha256(PLAN_PATH.read_bytes()).hexdigest() == FROZEN_SHA256


def test_plan_is_frozen_and_its_amendment_log_is_dated(plan) -> None:
    assert plan["status"].startswith("plan frozen")
    assert [(entry["date"], entry["previous_sha256"][:8]) for entry in plan["amendments"]] == [("2026-10-05", "8b368ac8"), ("2026-10-05", "9bb36f8d")]
    assert "walkers_rule" in plan["stage_B_posterior"]["sampler"]
    assert "error_model_fields" in plan["shared_structure"]


def test_recorded_results_cite_a_digest_in_the_plan_amendment_chain(plan) -> None:
    """A result cites the plan version it ran under: the current digest or one the amendment log records."""

    results = PLAN_PATH.parent / "results"
    if not results.exists():
        pytest.skip("no results recorded under the plan yet")
    chain = {FROZEN_SHA256, *(entry["previous_sha256"] for entry in plan["amendments"])}
    for inputs_path in sorted(results.rglob("inputs.json")):
        inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
        assert inputs["plan_sha256"] in chain, inputs_path
    for frozen_path in sorted(results.rglob("frozen_predictions/*.json")):
        frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
        assert frozen["plan_sha256"] in chain, frozen_path


def test_plan_data_digests_match_the_frozen_sources(plan) -> None:
    def digest(relative: str) -> str:
        return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()

    assert plan["data"]["source_sha256"] == digest(plan["data"]["source"])
    assert plan["baseline_provenance"]["v2_plan_sha256"] == digest("data/benchmarks/gelain_2020_v2/plan.json")
    assert plan["baseline_provenance"]["bayesian_plan_sha256"] == digest("data/benchmarks/gelain_2020_bayesian/plan.json")
    assert plan["data"]["observations"] == 96 and len(plan["data"]["conditions"]) == 3


def test_every_model_declares_bounded_positive_parameters_and_flags_additions(plan) -> None:
    assert set(plan["models"]) == set(EXPECTED_PARAMETER_COUNTS)
    for name, model in plan["models"].items():
        parameters = model["parameters"]
        assert len(parameters) == EXPECTED_PARAMETER_COUNTS[name], name
        symbols = [p["symbol"] for p in parameters]
        assert len(set(symbols)) == len(symbols), name
        assert COMMON_SYMBOLS <= set(symbols), name
        for parameter in parameters:
            assert 0 < parameter["lower"] < parameter["upper"], (name, parameter["symbol"])
            assert parameter["units"] and parameter["role"], (name, parameter["symbol"])
            if parameter["symbol"] not in COMMON_SYMBOLS:
                assert parameter.get("new") is True and parameter["meaning"], (name, parameter["symbol"])
        assert model["mechanism"] and model["composition"]
        assert isinstance(model["new_code_required"], bool)


def test_decision_rules_and_claim_boundaries_are_declared(plan) -> None:
    rules = plan["decision_rules"]
    assert {"R1_holdout_support", "R2_adequacy", "R3_identification", "R4_coverage"} <= set(rules)
    assert len(rules["outcome_vocabulary"]) == 4
    reporting = plan["reporting"]
    assert reporting["must_report_failures"] is True
    assert "biological validation" in reporting["claims_excluded"]
    assert plan["stage_B_posterior"]["identifiability"] == {
        "identified_max_width_fraction": 0.25,
        "weak_max_width_fraction": 0.75,
        "bound_contact_fraction": 0.02,
        "credible_mass": 0.95,
    }


def test_recorded_stage_b_results_are_internally_consistent(plan) -> None:
    """Every recorded posterior cites the plan chain, labels unconverged chains provisional and digests its files."""

    stage_b = PLAN_PATH.parent / "results" / "stage_b"
    recorded = sorted(path for path in stage_b.glob("*/verdicts.json")) if stage_b.exists() else []
    if not recorded:
        pytest.skip("no stage B posterior recorded yet")
    chain = {FROZEN_SHA256, *(entry["previous_sha256"] for entry in plan["amendments"])}
    vocabulary = set(plan["decision_rules"]["outcome_vocabulary"]) | {"baseline (R1 and R3 do not apply)", "not scored (stage A screen not recorded)"}
    for verdicts_path in recorded:
        folder = verdicts_path.parent
        verdicts = json.loads(verdicts_path.read_text(encoding="utf-8"))
        calibration = json.loads((folder / "bayesian_calibration.json").read_text(encoding="utf-8"))
        inputs = json.loads((folder / "inputs.json").read_text(encoding="utf-8"))
        artifacts = json.loads((folder / "artifacts.json").read_text(encoding="utf-8"))
        assert inputs["plan_sha256"] in chain, folder
        assert verdicts["provisional"] == (not calibration["converged"]), folder
        assert verdicts["outcome"] in vocabulary, verdicts["outcome"]
        for name, digest in artifacts.items():
            if name == "artifacts.json":
                continue
            assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == digest, (folder, name)
