"""SED-ML export and COMBINE archive generation for supported kinetic models."""

from __future__ import annotations

import zipfile

import pytest

libsbml = pytest.importorskip("libsbml", reason="requires the optional 'standards' extra")
libsedml = pytest.importorskip("libsedml", reason="requires the optional 'standards' extra")

from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.simulation import SolverSettings
from fungal_model.core.units import Q_
from fungal_model.processes.assembly import AssembledModel, AssemblyReport, ModelAssemblyContext
from fungal_model.processes.homogeneous import FirstOrderDecayProcess, HomogeneousMichaelisMentenProcess
from fungal_model.resources import example_data_path
from fungal_model.standards import (
    DEFAULT_KISAO_ID,
    SbmlExportError,
    model_config_to_combine_archive,
    to_sbml,
    to_sedml,
    write_combine_archive,
)


def _parameter(symbol: str, value: float, units: str) -> Parameter:
    return Parameter(
        name=symbol, symbol=symbol, value=value, units=units, uncertainty=None,
        source="unit test", confidence_level="unknown", notes="",
    )


def _model(process, parameters) -> AssembledModel:
    context = ModelAssemblyContext()
    return AssembledModel(
        processes=(process,), parameters=ParameterSet(parameters), context=context,
        state_variables=tuple(process.state_variables), assumptions=(), validators=(),
        solver_settings=SolverSettings(), assembly_report=AssemblyReport(context=context),
    )


def _mm_model() -> tuple[AssembledModel, dict]:
    process = HomogeneousMichaelisMentenProcess(
        name="mm", substrate_state="S", km_symbol="Km", rate_units="millimolar/second",
        substrate_units="millimolar", product_state="Prod", vmax_symbol="Vmax",
    )
    model = _model(process, [_parameter("Km", 3.0, "millimolar"), _parameter("Vmax", 0.4, "millimolar/second")])
    return model, {"S": Q_(10.0, "millimolar"), "Prod": Q_(0.0, "millimolar")}


def _first_order_model() -> tuple[AssembledModel, dict]:
    process = FirstOrderDecayProcess(
        name="fo", substrate_state="A", rate_constant_symbol="k", state_units="millimolar", product_state="B",
    )
    model = _model(process, [_parameter("k", 0.05, "1/second")])
    return model, {"A": Q_(10.0, "millimolar"), "B": Q_(0.0, "millimolar")}


def _sedml_errors(document) -> int:
    log = document.getErrorLog()
    return sum(
        1 for i in range(log.getNumErrors())
        if log.getError(i).getSeverity() >= libsedml.LIBSEDML_SEV_ERROR
    )


def test_sedml_is_valid_and_describes_time_course() -> None:
    model, initial_state = _mm_model()
    sbml = to_sbml(model, initial_state=initial_state, model_id="mm")
    sedml = to_sedml(sbml, output_end_time=Q_(120.0, "second"), number_of_steps=40, model_source="model.xml")
    document = libsedml.readSedMLFromString(sedml)

    assert document.getLevel() == 1 and document.getVersion() == 4
    assert _sedml_errors(document) == 0
    assert document.getNumModels() == 1
    assert document.getModel(0).getSource() == "model.xml"
    assert document.getNumTasks() == 1
    simulation = document.getSimulation(0)
    assert simulation.getOutputEndTime() == 120.0
    assert simulation.getNumberOfSteps() == 40
    assert simulation.getAlgorithm().getKisaoID() == DEFAULT_KISAO_ID
    # one data generator for time + one per species (S, Prod)
    assert document.getNumDataGenerators() == 3


def test_sedml_species_targets_match_sbml_ids() -> None:
    model, initial_state = _first_order_model()
    sbml = to_sbml(model, initial_state=initial_state, model_id="fo")
    # Hold the document reference: libsbml's getModel() returns a pointer owned
    # by the document, so a chained readSBMLFromString(...).getModel() would
    # dangle once the temporary document is garbage-collected.
    sbml_document = libsbml.readSBMLFromString(sbml)
    sbml_model = sbml_document.getModel()
    species_ids = {sbml_model.getSpecies(i).getId() for i in range(sbml_model.getNumSpecies())}
    sedml = to_sedml(sbml, output_end_time=Q_(60.0, "second"), number_of_steps=10)
    document = libsedml.readSedMLFromString(sedml)
    targets = [
        document.getDataGenerator(i).getVariable(j).getTarget()
        for i in range(document.getNumDataGenerators())
        for j in range(document.getDataGenerator(i).getNumVariables())
        if document.getDataGenerator(i).getVariable(j).getTarget()
    ]
    for species_id in species_ids:
        assert any(f"'{species_id}'" in t or f'"{species_id}"' in t for t in targets), species_id


def test_sedml_rejects_nonpositive_steps() -> None:
    model, initial_state = _first_order_model()
    sbml = to_sbml(model, initial_state=initial_state)
    with pytest.raises(SbmlExportError, match="number_of_steps"):
        to_sedml(sbml, output_end_time=Q_(60.0, "second"), number_of_steps=0)


def test_combine_archive_bundles_sbml_and_sedml(tmp_path) -> None:
    model, initial_state = _mm_model()
    path = write_combine_archive(
        model, tmp_path / "experiment.omex", initial_state=initial_state,
        output_end_time=Q_(120.0, "second"), number_of_steps=40,
    )
    assert path.exists() and path.stat().st_size > 0

    # Verify the archive as a plain ZIP (an .omex is a ZIP with an OMEX manifest).
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        assert {"manifest.xml", "model.xml", "simulation.sedml"} <= names
        sbml_back = archive.read("model.xml").decode("utf-8")
        sedml_back = archive.read("simulation.sedml").decode("utf-8")

    assert libsbml.readSBMLFromString(sbml_back).getModel() is not None
    assert _sedml_errors(libsedml.readSedMLFromString(sedml_back)) == 0


def test_config_to_combine_archive_defaults_from_config(tmp_path) -> None:
    path = model_config_to_combine_archive(
        example_data_path("model_configs/toy_homogeneous_ab.yml"),
        tmp_path / "toy.omex",
    )
    assert path.exists()
    with zipfile.ZipFile(path) as archive:
        assert {"model.xml", "simulation.sedml"} <= set(archive.namelist())


def test_combine_archive_refuses_unsupported_model(tmp_path) -> None:
    with pytest.raises(SbmlExportError):
        model_config_to_combine_archive(
            example_data_path("model_configs/toy_surface_dummy_non_pet.yml"),
            tmp_path / "surface.omex",
        )
