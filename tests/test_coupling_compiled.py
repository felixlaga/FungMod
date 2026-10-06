"""Catalysed mass action and the fungal coupling model on the compiled core.

The process tests use abstract pools; the coupling tests reuse the artificial
benchmark fungus of ``tests/test_fungal_coupling.py`` (no organism, chemistry or
measurement is claimed).
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from fungal_model.core.kernels import KernelContext
from fungal_model.core.numerics import SolverSettings
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_
from fungal_model.fungi import Fungus, FungalCouplingModel, make_fungal_parameter_set
from fungal_model.fungi.coupling import SECRETION_COST_RATE_SYMBOL
from fungal_model.io import ProcessConfig
from fungal_model.processes import MassActionProcess, ModelBuilder, ProcessBuildContext, ProcessLibrary, ProcessRegistry
from fungal_model.solvers import ProcessODESolver, RunRequest
from tests.test_fungal_coupling import SOURCE, _model, _parameter

TEST_SOURCE = "Artificial catalysed mass-action benchmark; no physical claim."


def _p(symbol: str, value: float, units: str) -> Parameter:
    return Parameter(f"artificial {symbol}", symbol, value, units, None, TEST_SOURCE, "testing", "Artificial benchmark value.")


def catalysed(**kwargs) -> MassActionProcess:
    fields = dict(name="catalysed conversion", reactants={"A": 1.0}, products={"B": 1.0}, catalysts={"C": 1.0},
                  state_units={"A": "millimolar", "B": "millimolar", "C": "millimolar"}, rate_constant_symbol="k",
                  rate_constant_units="1 / millimolar / second", rate_units="millimolar / second", source=TEST_SOURCE)
    fields.update(kwargs)
    return MassActionProcess(**fields)


def test_catalysts_enter_the_rate_but_are_not_consumed() -> None:
    process = catalysed(catalysts={"C": 2.0})
    parameters = ParameterSet([_p("k", 0.3, "1 / millimolar ** 2 / second")])
    process = catalysed(catalysts={"C": 2.0}, rate_constant_units="1 / millimolar ** 2 / second")
    state = {"A": Q_(1.5, "millimolar"), "B": Q_(0.2, "millimolar"), "C": Q_(0.5, "millimolar")}
    rate = process.rate(state, Q_(0.0, "second"), parameters)
    assert rate.to("millimolar / second").magnitude == pytest.approx(0.3 * 1.5 * 0.5**2)
    contributions = process.contributions(rate)
    assert set(contributions) == {"A", "B"}  # the catalyst does not change
    assert contributions["A"].magnitude == pytest.approx(-rate.magnitude)
    assert {spec.name: spec.role for spec in process.required_state_variables} == {"A": "reactant", "C": "catalyst"}
    assert [spec.name for spec in process.changed_state_variables] == ["A", "B"]
    names = ("A", "B", "C")
    context = KernelContext(state_index={n: i for i, n in enumerate(names)}, state_units=dict.fromkeys(names, "molar"),
                            time_units="second", parameters=parameters)
    kernel = process.compile_rate(context)
    assert kernel is not None
    vector = np.array([1.5e-3, 2e-4, 5e-4])  # molar
    assert kernel(0.0, vector) == pytest.approx(0.3 * 1.5 * 0.5**2, rel=1e-12)


def test_autocatalysis_is_allowed_and_catalytic_reactants_are_refused() -> None:
    growth = catalysed(name="autocatalytic growth", reactants={"A": 1.0}, products={"C": 0.4}, catalysts={"C": 1.0})
    assert growth.catalysts == {"C": 1.0} and growth.products == {"C": 0.4}
    assert [spec.name for spec in growth.changed_state_variables] == ["A", "C"]
    with pytest.raises(ValueError, match="Catalysts cannot also be reactants"):
        catalysed(catalysts={"A": 1.0})
    with pytest.raises(ValueError, match="Missing state units"):
        catalysed(catalysts={"D": 1.0})


def test_catalysed_mass_action_integrates_to_the_analytic_solution() -> None:
    process = catalysed()
    model = ModelBuilder(process_library=ProcessRegistry([process]), requested_processes=(process.name,),
                         parameters=ParameterSet([_p("k", 0.3, "1 / millimolar / second")]),
                         solver_settings=SolverSettings(rtol=1e-10, atol=1e-13)).assemble()
    times = np.linspace(0.0, 10.0, 11)
    result = ProcessODESolver(model).run(RunRequest(
        initial_state={"A": Q_(2.0, "millimolar"), "B": Q_(0.0, "millimolar"), "C": Q_(0.5, "millimolar")},
        t_span=(Q_(0.0, "second"), Q_(10.0, "second")), t_eval=Q_(times, "second")))
    np.testing.assert_allclose(result.states["A"].magnitude, 2.0 * np.exp(-0.3 * 0.5 * times), rtol=1e-8)
    np.testing.assert_allclose(result.states["C"].magnitude, 0.5, rtol=1e-12)
    assert result.solver_metadata["kernel"]["quantity_wrapped_kernel_count"] == 0


def test_mass_action_factory_reads_catalysts_from_config() -> None:
    library = ProcessLibrary.default_foundation()
    context = ProcessBuildContext(state_units={"A": "millimolar", "B": "millimolar", "C": "millimolar"}, source=TEST_SOURCE)
    config = ProcessConfig(id="catalysed", process_type="mass_action",
                           states={"reactants": {"A": 1.0}, "products": {"B": 1.0}, "catalysts": {"C": 1.0}},
                           parameters={"rate_constant": "k", "rate_constant_units": "1 / millimolar / second",
                                       "rate_units": "millimolar / second"})
    built = library.build_processes(context, [config])[0]
    assert isinstance(built, MassActionProcess) and built.catalysts == {"C": 1.0}
    missing = ProcessBuildContext(state_units={"A": "millimolar", "B": "millimolar"})
    decision = library.factory_for("mass_action").can_build(missing, config)
    assert not decision.can_build and "state_units.C" in decision.missing_fields


def test_sbml_export_lists_catalysts_as_modifiers() -> None:
    libsbml = pytest.importorskip("libsbml", reason="requires the optional 'standards' extra")
    from fungal_model.standards import cross_engine_trajectory_check, to_sbml
    from tests.test_standards_sbml import _model as sbml_model
    from tests.test_standards_sbml import _parameter as sbml_parameter

    model = sbml_model(catalysed(), [sbml_parameter("k", 0.3, "1 / millimolar / second")])
    document = libsbml.readSBMLFromString(
        to_sbml(model, initial_state={"A": Q_(2.0, "millimolar"), "B": Q_(0.0, "millimolar"), "C": Q_(0.5, "millimolar")}))
    reaction = document.getModel().getReaction(0)
    assert [reaction.getModifier(i).getSpecies() for i in range(reaction.getNumModifiers())] == ["C"]
    assert "C" in reaction.getKineticLaw().getFormula()
    comparison = cross_engine_trajectory_check(
        model, initial_state={"A": Q_(2.0, "millimolar"), "B": Q_(0.0, "millimolar"), "C": Q_(0.5, "millimolar")},
        times=Q_(np.linspace(0.0, 10.0, 11), "second"))
    assert comparison.agrees(atol=1e-6), comparison.max_absolute_difference


# ---------------------------------------------------------------- coupling model


def _degradation_process() -> MassActionProcess:
    """The test fixture's degradation law (k_deg * substrate * enzyme) as a catalysed mass action."""

    return MassActionProcess(name="artificial extracellular depolymerization", reactants={"substrate": 1.0},
                             products={"product": 1.0}, catalysts={"enzyme": 1.0},
                             state_units={"substrate": "kilogram", "product": "kilogram", "enzyme": "mole / liter"},
                             rate_constant_symbol="k_deg", rate_constant_units="liter / mole / second",
                             rate_units="kilogram / second", source=SOURCE)


def _costed_model(*, cost: float = 2.0, maintenance: float = 0.005) -> FungalCouplingModel:
    """The benchmark coupling with a non-zero secretion cost and maintenance so every process acts."""

    base = _model()
    fungus: Fungus = base.fungus
    parameters = [p for p in fungus.parameters if p.symbol not in {"c_E", "m_B"}]
    parameters += [_parameter("secretion cost", "c_E", cost, "kilogram / (mole / liter)"),
                   _parameter("maintenance", "m_B", maintenance, "1 / second")]
    return replace(base, fungus=replace(fungus, parameters=make_fungal_parameter_set(parameters)))


INITIAL = {"substrate": Q_(1.0, "kilogram"), "product": Q_(0.0, "kilogram"), "enzyme": Q_(0.02, "mole / liter"),
           "active_biomass": Q_(0.1, "kilogram"), "inactive_biomass": Q_(0.0, "kilogram")}


def test_coupling_compiled_path_matches_the_legacy_engine() -> None:
    model = _costed_model()
    processes = model.compiled_processes([_degradation_process()])
    assert [process.name for process in processes] == [
        "artificial extracellular depolymerization", "fungal extracellular enzyme secretion", "extracellular enzyme decay",
        "enzyme secretion active biomass cost", "assimilable degradation-product uptake", "active biomass maintenance loss"]
    assert {reaction.name for reaction in model.reactions()} == {process.name for process in processes}
    derived = model.compiled_parameters().get(SECRETION_COST_RATE_SYMBOL)
    assert derived.quantity.to("1 / second").magnitude == pytest.approx(1.0e-4 * 2.0)
    assert derived.confidence_level == "testing" and "alpha_E" in str(derived.source) and "Not an independent" in derived.notes
    settings = SolverSettings(rtol=1e-10, atol=1e-13)
    times = Q_(np.linspace(0.0, 20.0, 41), "second")
    legacy = model.build_engine().simulate(initial_state=INITIAL, t_span=(Q_(0.0, "second"), Q_(20.0, "second")),
                                           t_eval=times, solver_settings=settings)
    compiled = model.simulate_compiled(degradation=[_degradation_process()], initial_state=INITIAL,
                                       t_span=(Q_(0.0, "second"), Q_(20.0, "second")), t_eval=times, solver_settings=settings)
    for name, units in (("substrate", "kilogram"), ("product", "kilogram"), ("enzyme", "mole / liter"),
                        ("active_biomass", "kilogram"), ("inactive_biomass", "kilogram")):
        np.testing.assert_allclose(compiled.states[name].to(units).magnitude, legacy.species[name].to(units).magnitude,
                                   rtol=1e-7, atol=1e-12)
    assert compiled.states["inactive_biomass"].magnitude[-1] > 0.0  # cost and maintenance acted
    assert compiled.solver_metadata["kernel"]["quantity_wrapped_kernel_count"] == 0
    assert compiled.solver_metadata["kernel"]["process_count"] == 6
    assert compiled.label == "exploratory"


def test_coupling_compiled_path_keeps_the_legacy_refusals() -> None:
    model = _costed_model()
    with pytest.raises(ValueError, match="at least one extracellular degradation process"):
        model.compiled_processes([])
    off_target = MassActionProcess(name="unrelated", reactants={"enzyme": 1.0}, products={}, state_units={"enzyme": "mole / liter"},
                                   rate_constant_symbol="delta_E", rate_constant_units="1 / second",
                                   rate_units="mole / liter / second", source=SOURCE)
    with pytest.raises(ValueError, match="must change the configured substrate and product"):
        model.compiled_processes([off_target])
    with pytest.raises(ValueError, match="matching extracellular enzyme capability"):
        _model(enzyme_class="unsupported enzyme").compiled_processes([_degradation_process()])
    reserved = ParameterSet([_parameter("degradation coefficient", "k_deg", 0.5, "liter / mole / second"),
                             _parameter("reserved", SECRETION_COST_RATE_SYMBOL, 1.0, "1 / second")])
    with pytest.raises(ValueError, match="reserved for the derived secretion cost"):
        _model(additional_parameters=reserved).compiled_parameters()


def test_zero_cost_and_maintenance_reduce_to_the_original_benchmark() -> None:
    model = _model()
    assert model.fungus.species_name == "Artificial benchmark fungus"
    result = model.simulate_compiled(degradation=[_degradation_process()], initial_state=INITIAL,
                                     t_span=(Q_(0.0, "second"), Q_(20.0, "second")))
    final = {name: float(values.magnitude[-1]) for name, values in result.states.items()}
    assert final["substrate"] < 1.0 and final["product"] > 0.0 and final["active_biomass"] > 0.1
    assert final["inactive_biomass"] == 0.0
    assert model.compiled_parameters().get(SECRETION_COST_RATE_SYMBOL).quantity.magnitude == 0.0
