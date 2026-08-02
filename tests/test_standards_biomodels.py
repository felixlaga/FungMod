"""BioModels-ready deposit for the SABIO-RK Reaction 618 beta-glucosidase case."""

from __future__ import annotations

import zipfile

import numpy as np
import pytest

libsbml = pytest.importorskip("libsbml", reason="requires the optional 'standards' extra")

from fungal_model.core.units import Q_
from fungal_model.standards import (
    REACTION_618_MODEL_ID,
    build_reaction_618_model,
    cross_engine_trajectory_check,
    write_biomodels_deposit,
)


def _resources(element) -> set[str]:
    found: set[str] = set()
    for i in range(element.getNumCVTerms()):
        term = element.getCVTerm(i)
        for j in range(term.getNumResources()):
            found.add(term.getResourceURI(j))
    return found


def test_build_reaction_618_model_has_expected_structure() -> None:
    model, initial_state = build_reaction_618_model()
    assert {spec.name for spec in model.state_variables} == {"cellobiose", "glucose", "beta_glucosidase"}
    assert set(initial_state) == {"cellobiose", "glucose", "beta_glucosidase"}
    symbols = {p.symbol for p in model.parameters}
    assert symbols == {"Km_cellobiose", "kcat_cellobiose"}
    assert model.parameters.get("Km_cellobiose").value == 15.3
    assert model.parameters.get("kcat_cellobiose").value == 0.13


def test_deposit_is_valid_annotated_sbml(tmp_path) -> None:
    deposit = write_biomodels_deposit(tmp_path / "deposit")
    assert deposit.sbml_model.exists()
    assert deposit.combine_archive.name == f"{REACTION_618_MODEL_ID}.omex"
    assert deposit.readme.exists()

    document = libsbml.readSBMLFromString(deposit.sbml_model.read_text(encoding="utf-8"))
    document.checkConsistency()
    errors = sum(
        1 for i in range(document.getNumErrors())
        if document.getError(i).getSeverity() >= libsbml.LIBSBML_SEV_ERROR
    )
    assert errors == 0

    model = document.getModel()
    # MIRIAM annotations present with the curated identifiers.
    assert "https://identifiers.org/CHEBI:17057" in _resources(model.getSpecies("cellobiose"))
    assert "https://identifiers.org/CHEBI:15903" in _resources(model.getSpecies("glucose"))
    enzyme = _resources(model.getSpecies("beta_glucosidase"))
    assert "https://identifiers.org/ec-code:3.2.1.21" in enzyme
    assert "https://identifiers.org/uniprot:Q8L7J2" in enzyme
    reaction = _resources(model.getReaction(0))
    assert "https://identifiers.org/kegg.reaction:R00026" in reaction
    assert "https://identifiers.org/pubmed:19587102" in _resources(model)

    # SBO terms present.
    assert model.getSpecies("cellobiose").getSBOTerm() == 247
    assert model.getReaction(0).getKineticLaw().getSBOTerm() == 29
    assert model.getParameter("Km_cellobiose").getSBOTerm() == 27
    assert model.getParameter("kcat_cellobiose").getSBOTerm() == 25


def test_deposit_combine_archive_bundles_model_and_simulation(tmp_path) -> None:
    deposit = write_biomodels_deposit(tmp_path / "deposit")
    with zipfile.ZipFile(deposit.combine_archive) as archive:
        assert {"manifest.xml", "model.xml", "simulation.sedml"} <= set(archive.namelist())


def test_deposit_model_round_trips_through_sbml(tmp_path) -> None:
    model, initial_state = build_reaction_618_model()
    comparison = cross_engine_trajectory_check(
        model, initial_state=initial_state, times=Q_(np.linspace(0.0, 3600.0, 25), "second")
    )
    assert comparison.agrees(atol=1e-4), comparison.max_absolute_difference
