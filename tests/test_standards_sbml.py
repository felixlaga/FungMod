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
from fungal_model.processes.physiology import ProportionalSynthesisProcess
from fungal_model.processes.surface import CoefficientBinding
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


def _synthesis() -> tuple[AssembledModel, dict]:
    process = ProportionalSynthesisProcess(
        name="induced synthesis", producer_state="P", producer_units="gram/liter",
        product_state="E", product_units="millimolar", rate_units="millimolar/second",
        specific_rate_symbol="q", inducer_state="I", inducer_units="gram/liter",
        induction_half_saturation_symbol="K_I",
    )
    model = _model(
        process,
        [_parameter("q", 0.002, "millimolar/second/(gram/liter)"), _parameter("K_I", 0.5, "gram/liter")],
    )
    return model, {"P": Q_(3.0, "gram/liter"), "I": Q_(2.0, "gram/liter"), "E": Q_(0.0, "millimolar")}


def _bound_yield(yield_value: float = 0.35) -> tuple[AssembledModel, dict]:
    """``S -> Y P + (1 - Y) W`` with the coefficients bound to the parameter ``Y``."""

    process = HomogeneousMichaelisMentenProcess(
        name="split conversion", substrate_state="S", km_symbol="Km", rate_units="millimolar/second",
        substrate_units="millimolar", vmax_symbol="Vmax",
        product_coefficients={"P": yield_value, "W": 1.0 - yield_value},
        product_coefficient_bindings={"P": CoefficientBinding("Y"), "W": CoefficientBinding("Y", complement=True)},
    )
    model = _model(
        process,
        [
            _parameter("Km", 3.0, "millimolar"),
            _parameter("Vmax", 0.4, "millimolar/second"),
            _parameter("Y", yield_value, "dimensionless"),
        ],
    )
    return model, {"S": Q_(10.0, "millimolar"), "P": Q_(0.0, "millimolar"), "W": Q_(0.0, "millimolar")}


def _assay_decay() -> tuple[AssembledModel, dict]:
    process = FirstOrderDecayProcess(
        name="activity loss", substrate_state="activity", rate_constant_symbol="k",
        state_units="filter_paper_unit / liter",
    )
    model = _model(process, [_parameter("k", 0.02, "1/second")])
    return model, {"activity": Q_(120.0, "filter_paper_unit / liter")}


ALL_BUILDERS = {
    "first_order": _first_order,
    "mass_action": _mass_action,
    "mm_vmax": _mm_vmax,
    "mm_enzyme": _mm_enzyme,
    "synthesis": _synthesis,
    "bound_yield": _bound_yield,
    "assay_decay": _assay_decay,
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
    # A process with parameter-bound product coefficients exports one reaction per bound product.
    assert sbml_model.getNumReactions() == (3 if name == "bound_yield" else 1)
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
        "proportional_synthesis",
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


def _reaction_formulas(xml: str) -> dict[str, str]:
    model = libsbml.readSBMLFromString(xml).getModel()
    return {
        model.getReaction(i).getId(): libsbml.formulaToL3String(model.getReaction(i).getKineticLaw().getMath())
        for i in range(model.getNumReactions())
    }


def test_induced_synthesis_exports_as_a_source_reaction_with_modifiers():
    model, initial = _synthesis()
    xml = to_sbml(model, initial_state=initial, model_id="synthesis")
    sbml_model = libsbml.readSBMLFromString(xml).getModel()
    reaction = sbml_model.getReaction(0)
    assert reaction.getNumReactants() == 0 and reaction.getNumProducts() == 1
    assert {reaction.getModifier(i).getSpecies() for i in range(reaction.getNumModifiers())} == {"P", "I"}
    assert _reaction_formulas(xml)[reaction.getId()] == "q * P * I / (K_I + I)"
    seconds = np.linspace(0.0, 30.0, 7)
    reference = simulate_reference_sbml(xml, times=seconds)
    expected = 0.002 * 3.0 * 2.0 / (0.5 + 2.0) * seconds
    assert np.allclose(reference["E"], expected, rtol=1e-8, atol=1e-10)
    assert np.allclose(reference["P"], 3.0) and np.allclose(reference["I"], 2.0)


def test_bound_product_coefficients_stay_symbolic_in_the_export():
    model, initial = _bound_yield(0.35)
    xml = to_sbml(model, initial_state=initial, model_id="bound")
    formulas = _reaction_formulas(xml)
    assert set(formulas) == {
        "split_conversion__reaction_0",
        "split_conversion__P__reaction_0",
        "split_conversion__W__reaction_0",
    }
    assert formulas["split_conversion__P__reaction_0"] == "Y * (Vmax * S / (Km + S))"
    assert formulas["split_conversion__W__reaction_0"] == "(1 - Y) * (Vmax * S / (Km + S))"
    sbml_model = libsbml.readSBMLFromString(xml).getModel()
    main = sbml_model.getReaction("split_conversion__reaction_0")
    assert main.getNumProducts() == 0 and main.getReactant(0).getSpecies() == "S"
    split = sbml_model.getReaction("split_conversion__P__reaction_0")
    assert split.getProduct(0).getStoichiometry() == 1.0
    assert [split.getModifier(i).getSpecies() for i in range(split.getNumModifiers())] == ["S"]
    comparison = cross_engine_trajectory_check(
        model, initial_state=initial, times=Q_(np.linspace(0, 60, 13), "second")
    )
    assert comparison.agrees(atol=1e-7), comparison.max_absolute_difference

    # Changing Y in the SBML alone reproduces FungMod rebuilt with the new coefficients.
    rebuilt, _ = _bound_yield(0.8)
    changed = xml.replace('value="0.35"', 'value="0.8"')
    assert changed != xml
    seconds = np.linspace(0, 60, 13)
    reference = simulate_reference_sbml(changed, times=seconds)
    result = rebuilt.run(
        initial_state=initial, t_span=(Q_(0, "second"), Q_(60, "second")), t_eval=Q_(seconds, "second"), label="y"
    )
    for name in ("S", "P", "W"):
        assert np.allclose(reference[name], result.state(name).to("millimolar").magnitude, rtol=1e-7, atol=1e-9)


def test_bound_coefficient_export_refuses_a_coefficient_that_disagrees_with_its_parameter():
    process = HomogeneousMichaelisMentenProcess(
        name="split conversion", substrate_state="S", km_symbol="Km", rate_units="millimolar/second",
        substrate_units="millimolar", vmax_symbol="Vmax",
        product_coefficients={"P": 0.35, "W": 0.65},
        product_coefficient_bindings={"P": CoefficientBinding("Y"), "W": CoefficientBinding("Y", complement=True)},
    )
    model = _model(
        process,
        [_parameter("Km", 3.0, "millimolar"), _parameter("Vmax", 0.4, "millimolar/second"), _parameter("Y", 0.5, "dimensionless")],
    )
    initial = {"S": Q_(10.0, "millimolar"), "P": Q_(0.0, "millimolar"), "W": Q_(0.0, "millimolar")}
    with pytest.raises(SbmlExportError, match="evaluates to"):
        to_sbml(model, initial_state=initial, model_id="bound")
    missing = _model(process, [_parameter("Km", 3.0, "millimolar"), _parameter("Vmax", 0.4, "millimolar/second")])
    with pytest.raises(SbmlExportError, match="does not carry"):
        to_sbml(missing, initial_state=initial, model_id="bound")


def test_bindings_must_name_product_states():
    with pytest.raises(ValueError, match="unknown: Q"):
        HomogeneousMichaelisMentenProcess(
            name="split", substrate_state="S", km_symbol="Km", rate_units="millimolar/second",
            substrate_units="millimolar", vmax_symbol="Vmax", product_coefficients={"P": 1.0},
            product_coefficient_bindings={"Q": CoefficientBinding("Y")},
        )


def test_assay_units_export_as_named_dimensionless_definitions():
    model, initial = _assay_decay()
    xml = to_sbml(model, initial_state=initial, model_id="assay")
    sbml_model = libsbml.readSBMLFromString(xml).getModel()
    species = sbml_model.getSpecies("activity")
    definition = sbml_model.getUnitDefinition(species.getSubstanceUnits())
    assert definition.getName() == "filter_paper_unit / liter"
    kinds = {definition.getUnit(i).getKind() for i in range(definition.getNumUnits())}
    assert libsbml.UNIT_KIND_DIMENSIONLESS in kinds and libsbml.UNIT_KIND_METRE in kinds
    assert "filter_paper_unit" in sbml_model.getNotesString()
    assert "no SI equivalent is implied" in sbml_model.getNotesString()
    comparison = cross_engine_trajectory_check(
        model, initial_state=initial, times=Q_(np.linspace(0, 100, 11), "second")
    )
    # Activity values are of order 100 FPU/L; FungMod integrates at rtol 1e-8.
    assert comparison.agrees(atol=1e-5), comparison.max_absolute_difference


def test_export_without_assay_units_has_no_unit_caveat():
    model, initial = _first_order()
    xml = to_sbml(model, initial_state=initial, model_id="plain")
    assert "no SI equivalent" not in libsbml.readSBMLFromString(xml).getModel().getNotesString()


def test_names_as_ids_option_repeats_identifiers_as_parameter_names():
    process = FirstOrderDecayProcess(
        name="decay", substrate_state="A", rate_constant_symbol="k", state_units="millimolar",
    )
    parameter = Parameter(
        name="first-order loss constant (descriptive)", symbol="k", value=0.1, units="1/second",
        uncertainty=None, source="unit test", confidence_level="unknown", notes="",
    )
    model = _model(process, [parameter])
    initial = {"A": Q_(1.0, "millimolar")}
    default = libsbml.readSBMLFromString(to_sbml(model, initial_state=initial)).getModel()
    assert default.getParameter("k").getName() == "first-order loss constant (descriptive)"
    renamed = libsbml.readSBMLFromString(to_sbml(model, initial_state=initial, names_as_ids=True)).getModel()
    assert renamed.getParameter("k").getName() == "k"
