"""Regression tests for the two defects found by the DOCS-001 audit."""

from __future__ import annotations

from collections import Counter

import pytest

from fungal_model import review_source_proposal, source_proposal
from fungal_model.registry import load_registry
from fungal_model.resources import default_registry_path
from fungal_model.screening import assess_modelability
from fungal_model.screening.modelability import PROCESS_ENVIRONMENT_CONDITIONS


@pytest.fixture(scope="module")
def registry():
    return load_registry(default_registry_path())


def test_parameters_of_one_type_get_distinct_proposed_symbols() -> None:
    proposal = source_proposal(provider="sabiork", reaction_id="618")
    for record in proposal.reaction_records:
        symbols = Counter(parameter.proposed_symbol for parameter in record.parameters)
        assert max(symbols.values()) == 1, (record.entry_id, symbols)
    entry = next(record for record in proposal.reaction_records if record.entry_id == "38522")
    assert {"pka_pke1", "pka_pke2", "pka_pkes1", "pka_pkes2"} <= {p.proposed_symbol for p in entry.parameters}
    # Symbols whose parameter name adds nothing keep their previous form.
    assert "ph" in {p.proposed_symbol for p in entry.parameters}
    assert "Km_cellobiose" in {p.proposed_symbol for p in entry.parameters}


def test_the_whole_reaction_618_proposal_can_be_reviewed() -> None:
    proposal = source_proposal(provider="sabiork", reaction_id="618")
    result = review_source_proposal(proposal, curator="regression test")
    assert type(result).__name__ == "CurationResult"


def test_a_ranged_ph_blocks_the_ionization_law_in_preflight(registry) -> None:
    ranged = registry.get_environment("toy_lab_environment")
    assert ranged.conditions["ph"].kind == "range"
    for mode in ("exploratory", "scientific"):
        report = assess_modelability(
            fungus_id="phanerochaete_chrysosporium_k3",
            substrate_id="cellobiose",
            environment_id="toy_lab_environment",
            registry=registry,
            mode=mode,
        )
        assert report.status != "modelable"
        items = [item for item in report.incompatible if item.item_type == "environment_condition"]
        assert [item.item_id for item in items] == ["toy_lab_environment:ph"]
        assert "needs one value per run" in items[0].message


def test_an_exact_ph_keeps_the_ionization_case_modelable(registry) -> None:
    report = assess_modelability(
        fungus_id="phanerochaete_chrysosporium_k3",
        substrate_id="cellobiose",
        environment_id="tsukada_2008_bgl1a_assay_30c_ph5",
        registry=registry,
        mode="exploratory",
    )
    assert report.status == "modelable"
    assert not [item for item in report.incompatible if item.item_type == "environment_condition"]


def test_laws_declare_the_conditions_preflight_checks() -> None:
    assert PROCESS_ENVIRONMENT_CONDITIONS["ph_ionization_michaelis_menten"] == ("ph",)
    assert PROCESS_ENVIRONMENT_CONDITIONS["thermal_inactivation"] == ("temperature",)


def test_processes_without_environment_reads_are_unaffected(registry) -> None:
    # The homogeneous Michaelis-Menten case reads no environment condition, so a
    # ranged pH environment does not add an environment-condition item.
    report = assess_modelability(
        fungus_id="sabiork_beta_glucosidase_source",
        substrate_id="cellobiose",
        environment_id="toy_lab_environment",
        registry=registry,
        mode="exploratory",
    )
    assert not [item for item in report.incompatible if item.item_type == "environment_condition"]
