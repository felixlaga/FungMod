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
FROZEN_SHA256 = "8b368ac8d6b683f688907c0bb38d4b5a3d2730d29a7b8ca4c37d92db1e187c7e"
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


def test_plan_is_frozen_unrun_and_unamended(plan) -> None:
    assert plan["status"].startswith("plan frozen")
    assert plan["amendments"] == []
    assert not (PLAN_PATH.parent / "results").exists()


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
