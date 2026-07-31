from __future__ import annotations

from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
SHOWCASE_PATH = ROOT / "data" / "showcases" / "five_fungal_beta_glucosidases.yml"

EXPECTED_PARAMETERS = {
    "aspergillus_fumigatus": (768.0, 1.77, 1.1),
    "chaetomium_globosum": (168.0, 0.95, 0.68),
    "emericella_nidulans": (87.0, 2.32, 1.83),
    "neurospora_crassa": (423.0, 2.95, 10.1),
    "penicillium_brasilianum": (520.0, 2.05, 2.3),
}


def _showcase() -> dict:
    loaded = yaml.safe_load(SHOWCASE_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_showcase_has_five_distinct_literature_reported_sources() -> None:
    showcase = _showcase()
    cases = showcase["cases"]

    assert showcase["kind"] == "fungmod_fungal_beta_glucosidase_showcase"
    assert showcase["maturity"] == "literature_reported_exploratory_model_input"
    assert showcase["provenance"]["primary_doi"] == "https://doi.org/10.1002/bit.22885"
    assert showcase["provenance"]["transcription_pmc"] == (
        "https://pmc.ncbi.nlm.nih.gov/articles/PMC3726394/"
    )
    assert len(cases) == 5
    assert len({case["id"] for case in cases}) == 5
    assert len({case["source_organism"] for case in cases}) == 5
    assert {case["id"] for case in cases} == set(EXPECTED_PARAMETERS)
    assert all(case["maturity"] == "literature_reported" for case in cases)
    assert all(case["source"] == "https://doi.org/10.1002/bit.22885" for case in cases)


@pytest.mark.parametrize(
    ("case_id", "expected"),
    EXPECTED_PARAMETERS.items(),
)
def test_showcase_parameter_transcription_is_exact(
    case_id: str,
    expected: tuple[float, float, float],
) -> None:
    cases = {case["id"]: case for case in _showcase()["cases"]}
    case = cases[case_id]

    assert case["kcat"]["value"] == pytest.approx(expected[0])
    assert case["km_cellobiose"]["value"] == pytest.approx(expected[1])
    assert case["ki_glucose"]["value"] == pytest.approx(expected[2])
    assert case["kcat"]["units"] == "1 / second"
    assert case["km_cellobiose"]["units"] == "millimole / liter"
    assert case["ki_glucose"]["units"] == "millimole / liter"


def test_showcase_keeps_scenario_assumptions_and_limitations_explicit() -> None:
    showcase = _showcase()
    scenario = showcase["scenario"]
    reaction = showcase["reaction"]
    combined_limitations = " ".join(reaction["limitations"]).lower()

    assert scenario["maturity"] == "explicit_exploratory_scenario"
    assert scenario["ranking_allowed"] is False
    assert "not reported" in scenario["beta_glucosidase_concentration"]["source"].lower()
    assert scenario["beta_glucosidase_concentration"]["value"] == pytest.approx(0.00001)
    assert scenario["initial_cellobiose"]["value"] == pytest.approx(10.0)
    assert scenario["temperature"]["value"] == pytest.approx(323.15)
    assert scenario["ph"]["value"] == pytest.approx(5.0)
    assert reaction["stoichiometric_product_yield"] == pytest.approx(2.0)
    assert reaction["process_type"] == "homogeneous_michaelis_menten"
    assert reaction["inhibition_modifier"] == "competitive_inhibition"
    assert "transglycosylation" in combined_limitations
    assert "whole-fungus" in combined_limitations
