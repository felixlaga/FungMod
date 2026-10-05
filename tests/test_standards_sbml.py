"""SBML export and cross-engine trajectory checks for supported kinetic models."""

from __future__ import annotations

import numpy as np
import pytest

libsbml = pytest.importorskip("libsbml", reason="requires the optional 'standards' extra")

from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.simulation import SolverSettings
from fungal_model.core.units import Q_
from fungal_model.processes.assembly import AssembledModel, AssemblyReport, ModelAssemblyContext
from fungal_model.processes.homogeneous import (
    FirstOrderDecayProcess,
    HomogeneousMichaelisMentenProcess,
    MassActionProcess,
)
from fungal_model.resources import example_data_path
from fungal_model.standards import (
    SBML_EXPORTABLE_PROCESS_TYPES,
    SbmlExportError,
    cross_engine_trajectory_check,
    model_config_to_sbml,
    simulate_reference_sbml,
    to_sbml,
    write_sbml,
)
from fungal_model.standards.cross_engine import compile_kinetic_formula


def _parameter(symbol: str, value: float, units: str) -> Parameter:
    return Parameter(
        name=symbol,
        symbol=symbol,
        value=value,
        units=units,
        uncertainty=None,
        source="unit test",
        confidence_level="unknown",
        notes="",
    )


def _model(process, parameters) -> AssembledModel:
    context = ModelAssemblyContext()
    return AssembledModel(
        processes=(process,),
        parameters=ParameterSet(parameters),
        context=context,
        state_variables=tuple(process.state_variables),
        assumptions=(),
        validators=(),
        solver_settings=SolverSettings(),
        assembly_report=AssemblyReport(context=context),
    )


def _first_order() -> tuple[AssembledModel, dict]:
    process = FirstOrderDecayProcess(
        name="first order", substrate_state="A", rate_constant_symbol="k",
        state_units="millimolar", product_state="B",
    )
    model = _model(process, [_parameter("k", 0.05, "1/second")])
    return model, {"A": Q_(10.0, "millimolar"), "B": Q_(0.0, "millimolar")}


def _mass_action() -> tuple[AssembledModel, dict]:
    process = MassActionProcess(
        name="mass action", reactants={"A": 1.0}, products={"B": 1.0},
        state_units={"A": "millimolar", "B": "millimolar"},
        rate_constant_symbol="k", rate_constant_units="1/second", rate_units="millimolar/second",
    )
    model = _model(process, [_parameter("k", 0.03, "1/second")])
    return model, {"A": Q_(8.0, "millimolar"), "B": Q_(0.0, "millimolar")}


def _mm_vmax() -> tuple[AssembledModel, dict]:
    process = HomogeneousMichaelisMentenProcess(
        name="mm vmax", substrate_state="S", km_symbol="Km", rate_units="millimolar/second",
        substrate_units="millimolar", product_state="Prod", vmax_symbol="Vmax",
    )
    model = _model(process, [_parameter("Km", 3.0, "millimolar"), _parameter("Vmax", 0.4, "millimolar/second")])
    return model, {"S": Q_(10.0, "millimolar"), "Prod": Q_(0.0, "millimolar")}


def _mm_enzyme() -> tuple[AssembledModel, dict]:
    process = HomogeneousMichaelisMentenProcess(
        name="mm enzyme", substrate_state="S", km_symbol="Km", rate_units="millimolar/second",
        substrate_units="millimolar", product_state="Prod", enzyme_state="E",
        enzyme_units="nanomolar", kcat_symbol="kcat",
    )
    model = _model(
        process,
        [_parameter("Km", 3.0, "millimolar"), _parameter("kcat", 0.08, "millimolar/second/nanomolar")],
    )
    return model, {"S": Q_(10.0, "millimolar"), "Prod": Q_(0.0, "millimolar"), "E": Q_(5.0, "nanomolar")}


ALL_BUILDERS = {
    "first_order": _first_order,
    "mass_action": _mass_action,
    "mm_vmax": _mm_vmax,
    "mm_enzyme": _mm_enzyme,
}


def _error_count(document) -> int:
    document.checkConsistency()
    return sum(
        1
        for index in range(document.getNumErrors())
        if document.getError(index).getSeverity() >= libsbml.LIBSBML_SEV_ERROR
    )


@pytest.mark.parametrize("name", sorted(ALL_BUILDERS))
def test_export_is_valid_sbml(name: str) -> None:
    model, initial_state = ALL_BUILDERS[name]()
    xml = to_sbml(model, initial_state=initial_state, model_id=name)
    document = libsbml.readSBMLFromString(xml)
    assert document.getLevel() == 3 and document.getVersion() == 2
    assert _error_count(document) == 0
    sbml_model = document.getModel()
    assert sbml_model.getNumReactions() == 1
    assert sbml_model.getNumSpecies() == len(initial_state)


def test_michaelis_menten_kinetic_law_formula() -> None:
    model, initial_state = _mm_enzyme()
    xml = to_sbml(model, initial_state=initial_state)
    document = libsbml.readSBMLFromString(xml)
    reaction = document.getModel().getReaction(0)
    formula = libsbml.formulaToL3String(reaction.getKineticLaw().getMath())
    assert formula.replace(" ", "") == "kcat*E*S/(Km+S)"
    modifiers = [reaction.getModifier(i).getSpecies() for i in range(reaction.getNumModifiers())]
    assert modifiers == ["E"]


def test_write_sbml_creates_file(tmp_path) -> None:
    model, initial_state = _first_order()
    path = write_sbml(model, tmp_path / "model.xml", initial_state=initial_state)
    assert path.exists()
    document = libsbml.readSBMLFromString(path.read_text(encoding="utf-8"))
    assert document.getModel() is not None


def test_missing_initial_value_is_rejected() -> None:
    model, initial_state = _first_order()
    del initial_state["B"]
    with pytest.raises(SbmlExportError, match="Missing initial value"):
        to_sbml(model, initial_state=initial_state)


def test_config_path_export_first_order() -> None:
    xml = model_config_to_sbml(example_data_path("model_configs/toy_homogeneous_ab.yml"))
    document = libsbml.readSBMLFromString(xml)
    assert _error_count(document) == 0
    assert document.getModel().getNumReactions() >= 1


@pytest.mark.parametrize(
    "config, expected",
    [
        ("model_configs/toy_surface_dummy_non_pet.yml", "not SBML-exportable"),
        ("model_configs/toy_homogeneous_competitive_inhibition.yml", "rate modifiers"),
        ("model_configs/showcase_dynamic_thermodynamics.yml", "thermodynamic"),
    ],
)
def test_unsupported_models_are_rejected(config: str, expected: str) -> None:
    with pytest.raises(SbmlExportError, match=expected):
        model_config_to_sbml(example_data_path(config))


@pytest.mark.parametrize("name", sorted(ALL_BUILDERS))
def test_cross_engine_trajectories_agree(name: str) -> None:
    model, initial_state = ALL_BUILDERS[name]()
    comparison = cross_engine_trajectory_check(
        model, initial_state=initial_state, times=Q_(np.linspace(0.0, 120.0, 41), "second")
    )
    assert comparison.agrees(atol=1e-5), comparison.max_absolute_difference
    assert set(comparison.fungmod) == {spec.name for spec in model.state_variables}


def test_reference_simulator_rejects_unsupported_constructs() -> None:
    # An SBML document with a rate rule is outside the supported subset.
    document = libsbml.SBMLDocument(3, 2)
    model = document.createModel()
    compartment = model.createCompartment()
    compartment.setId("c")
    compartment.setConstant(True)
    compartment.setSize(1.0)
    species = model.createSpecies()
    species.setId("X")
    species.setCompartment("c")
    species.setInitialAmount(1.0)
    species.setHasOnlySubstanceUnits(True)
    species.setBoundaryCondition(False)
    species.setConstant(False)
    rule = model.createRateRule()
    rule.setVariable("X")
    rule.setMath(libsbml.parseL3Formula("-0.1 * X"))
    xml = libsbml.writeSBMLToString(document)
    with pytest.raises(SbmlExportError, match="rules"):
        simulate_reference_sbml(xml, times=np.linspace(0.0, 1.0, 3))


def test_exportable_process_types_are_stable() -> None:
    assert SBML_EXPORTABLE_PROCESS_TYPES == (
        "first_order_decay",
        "mass_action",
        "homogeneous_michaelis_menten",
    )


@pytest.mark.parametrize('builder,parameters', [
    (_first_order, [('k', 3.0, '1/minute')]),
    (_mass_action, [('k', 1.8, '1/minute')]),
    (_mm_vmax, [('Km', 0.003, 'molar'), ('Vmax', 24.0, 'millimolar/minute')]),
    (_mm_enzyme, [('Km', 0.003, 'molar'), ('kcat', 4.8e6, '1/minute')]),
])
def test_export_preserves_equivalent_parameter_units(builder, parameters):
    original, initial = builder()
    model = _model(original.processes[0], [_parameter(*p) for p in parameters])
    comparison = cross_engine_trajectory_check(
        model, initial_state=initial, times=Q_(np.linspace(0, 60, 21), 'second'),
    )
    assert comparison.agrees(atol=1e-5), comparison.max_absolute_difference


def test_export_preserves_mass_action_with_different_species_units():
    process = MassActionProcess(
        name='unit-scaled conversion', reactants={'A': 1}, products={'B': 1},
        state_units={'A': 'kilogram', 'B': 'gram'}, rate_constant_symbol='k',
        rate_constant_units='1/minute', rate_units='kilogram/minute',
    )
    model = _model(process, [_parameter('k', 3, '1/minute')])
    comparison = cross_engine_trajectory_check(
        model, initial_state={'A': Q_(1, 'kilogram'), 'B': Q_(0, 'gram')},
        times=Q_(np.linspace(0, 60, 21), 'second'),
    )
    assert comparison.agrees(atol=1e-4), comparison.max_absolute_difference


def test_reference_formula_compiler_covers_the_emitted_grammar() -> None:
    symbols = {"k", "A", "Km", "S"}
    rate = compile_kinetic_formula("-(k * A) / (Km + S) + 2 * S^2 - pow(S, 3) / 4e-1 - -S^-1", symbols)
    environment = {"k": 0.5, "A": 3.0, "Km": 0.25, "S": 2.0}
    expected = -(0.5 * 3.0) / (0.25 + 2.0) + 2 * 2.0**2 - 2.0**3 / 0.4 - -(2.0**-1)
    assert rate(environment) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("formula", "message"),
    [
        ("exp(S)", "unsupported operation"),
        ("k * B", "Unknown symbol 'B'"),
        ("k * (S", "unsupported operation"),
        ("k S", "unsupported operation"),
        ("", "unsupported operation"),
    ],
)
def test_reference_formula_compiler_rejects_what_fungmod_never_emits(formula: str, message: str) -> None:
    with pytest.raises(SbmlExportError, match=message):
        compile_kinetic_formula(formula, {"k", "S"})


def test_cross_engine_check_survives_libsedml_proxy_registration() -> None:
    # Importing libsedml re-registers the SWIG proxies shared with libsbml, so
    # kinetic-law AST nodes stop matching libsbml's AST_* constants. The reference
    # simulator therefore works from formula text and must keep agreeing here.
    pytest.importorskip("libsedml", reason="requires the optional 'standards' extra")
    model, initial_state = ALL_BUILDERS["mm_enzyme"]()
    comparison = cross_engine_trajectory_check(
        model, initial_state=initial_state, times=Q_(np.linspace(0.0, 120.0, 41), "second")
    )
    assert comparison.agrees(atol=1e-5), comparison.max_absolute_difference
