"""Finite-chain software checks, synthetic cellulose-like and xylan-like systems."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from fungal_model.core.kernels import KernelContext
from fungal_model.core.numerics import SolverSettings
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_
from fungal_model.processes import ModelBuilder, ProcessRegistry
from fungal_model.processes.chain_scission import ChainScissionProcess, chain_observables, chain_scission_processes
from fungal_model.screening.synergy import degree_of_synergy, run_synergy_counterfactuals
from fungal_model.solvers import ProcessODESolver, RunRequest
from fungal_model.io.model_config import load_model_config
from fungal_model.workflows.configured_model import ConfiguredInputLoader, ConfiguredProcessAssembler

SOURCE = "Synthetic software benchmark; not scientific measurements."
ROOT = Path(__file__).resolve().parents[1]


def parameter(symbol, value, units):
    return Parameter(symbol, symbol, value, units, None, SOURCE, "testing", SOURCE)


def system(label="cellulose", fragment=2, threshold=4):
    chains = {i: f"{label}_{i}" for i in range(1, 13)}
    processes = []
    for mode in ("endo", "exo"):
        processes.extend(
            chain_scission_processes(
                name=mode,
                chain_states=chains,
                mode=mode,
                solid_min_length=threshold,
                enzyme_state=f"E_{mode}",
                kcat_symbol=f"k_{mode}",
                km_symbol=f"K_{mode}",
                accessible_fraction_symbol="Fa",
                state_units="millimolar",
                enzyme_units="millimolar",
                source=SOURCE,
                exo_fragment_length=fragment if mode == "exo" else None,
            )
        )
    parameters = ParameterSet(
        [
            parameter("k_endo", 0.15, "1/s"),
            parameter("k_exo", 1, "1/s"),
            parameter("K_endo", 1, "millimolar"),
            parameter("K_exo", 2, "millimolar"),
            parameter("Fa", 1, "dimensionless"),
        ]
    )
    model = ModelBuilder(
        process_library=ProcessRegistry(processes),
        parameters=parameters,
        solver_settings=SolverSettings(rtol=1e-9, atol=1e-11),
    ).assemble()
    initial = {name: Q_(1 if length == 12 else 0, "millimolar") for length, name in chains.items()}
    initial.update(E_endo=Q_(0.1, "millimolar"), E_exo=Q_(0.1, "millimolar"))
    return model, initial, chains


@pytest.mark.parametrize("label,fragment,threshold", [("cellulose", 2, 4), ("xylan", 1, 3)])
def test_exact_material_chain_ends_and_software_generality(label, fragment, threshold):
    model, initial, chains = system(label, fragment, threshold)
    result = model.run(initial_state=initial, t_span=(Q_(0, "s"), Q_(60, "s")), t_eval=Q_(np.linspace(0, 60, 31), "s"))
    observables = chain_observables(result.states, chains, solid_min_length=threshold)
    np.testing.assert_allclose(observables["material_equivalents"].magnitude, 12, rtol=1e-10)
    np.testing.assert_allclose(
        (observables["solid_equivalents"] + observables["soluble_equivalents"]).magnitude, 12, rtol=1e-10
    )
    assert observables["soluble_equivalents"].magnitude[-1] > 0
    assert "software_tested" in model.processes[0].validity.labels


def test_chain_end_exhaustion_is_exact_not_a_fitted_loss():
    model, initial, chains = system()
    for process in model.processes:
        changes = process.contributions(Q_(1, "millimolar/s"))
        mass = sum(i * changes.get(n, Q_(0, "millimolar/s")) for i, n in chains.items())
        assert mass.magnitude == 0
        end_change = sum(changes.get(n, Q_(0, "millimolar/s")) for i, n in chains.items() if i >= 4)
        if process.mode == "exo":
            assert end_change.magnitude == (-1 if process.parent_length in (4, 5) else 0)
    central = next(p for p in model.processes if p.mode == "endo" and p.parent_length == 8 and p.fragment_length == 4)
    assert central.contributions(Q_(1, "millimolar/s"))[chains[4]].magnitude == 2


def test_source_equations_are_recovered_by_channel_sum():
    model, _, chains = system()
    state = {n: Q_(i / 20, "millimolar") for i, n in chains.items()}
    state.update(E_endo=Q_(0.1, "millimolar"), E_exo=Q_(0.1, "millimolar"))
    s = sum((i - 1) * i / 20 for i in range(4, 13))
    ends = sum(i / 20 for i in range(4, 13))
    for mode, k, km, denominator in [("endo", 0.15, 1, s), ("exo", 1, 2, ends)]:
        total = {n: 0.0 for n in chains.values()}
        for p in model.processes:
            if p.mode == mode:
                for n, v in p.contributions(p.rate(state, Q_(0, "s"), model.parameters)).items():
                    total[n] += v.magnitude
        if mode == "endo":
            for i in range(4, 13):
                expected = k * 0.1 * (2 * sum(j / 20 for j in range(i + 1, 13)) - (i - 1) * i / 20) / (km + denominator)
                assert total[chains[i]] == pytest.approx(expected)
            for i in (1, 2, 3):
                assert total[chains[i]] == pytest.approx(2 * k * 0.1 * ends / (km + denominator))
        else:
            assert total[chains[2]] == pytest.approx(k * 0.1 * (ends + 4 / 20) / (km + denominator))
            assert total[chains[3]] == pytest.approx(k * 0.1 * 5 / 20 / (km + denominator))


def test_compiled_gradients_match_quantity_path_and_finite_difference_with_mixed_units():
    model, _, _ = system()
    for process in [model.processes[0], model.processes[-1]]:
        names = [s.name for s in process.state_variables]
        context = KernelContext(
            {n: i for i, n in enumerate(names)}, dict.fromkeys(names, "molar"), "hour", model.parameters
        )
        vector = np.linspace(0.0001, 0.001, len(names))
        state = {n: Q_(v, "molar") for n, v in zip(names, vector)}
        kernel = process.compile_rate(context)
        gradient = process.compile_jacobian(context)
        assert kernel(0, vector) == pytest.approx(process.rate(state, Q_(0, "s"), model.parameters).magnitude)
        expected = []
        for i in range(len(names)):
            up, down = vector.copy(), vector.copy()
            up[i] += 1e-8
            down[i] -= 1e-8
            expected.append((kernel(0, up) - kernel(0, down)) / 2e-8)
        np.testing.assert_allclose(gradient(0, vector), expected, rtol=1e-6, atol=1e-8)


def test_structural_synergy_emerges_and_single_member_is_one():
    model, initial, chains = system()

    def run(members):
        init = dict(initial)
        for member in ("endo", "exo"):
            if member not in members:
                init[f"E_{member}"] = Q_(0, "millimolar")
        return model.run(initial_state=init, t_span=(Q_(0, "s"), Q_(30, "s")), t_eval=Q_([0, 30], "s"))

    def observable(result):
        return chain_observables(result.states, chains, solid_min_length=4)["soluble_equivalents"]

    synergy = run_synergy_counterfactuals(members=["endo", "exo"], run=run, observable=observable, max_members=2)
    assert not synergy.defined[0]
    assert synergy.degree_of_synergy[-1] > 1
    alone = run_synergy_counterfactuals(members=["exo"], run=run, observable=observable, max_members=1)
    assert alone.degree_of_synergy[-1] == pytest.approx(1)


def test_synergy_three_members_uses_singletons_never_leave_one_out():
    calls = []

    def run(members):
        calls.append(members)
        return Q_(10 if len(members) == 3 else 4 if len(members) == 2 else 1, "millimolar")

    result = run_synergy_counterfactuals(members=["a", "b", "c"], run=run, observable=lambda x: x, max_members=3)
    assert result.degree_of_synergy == pytest.approx(10 / 3)
    assert len(calls) == 7
    assert all(v.magnitude == 4 for v in result.leave_one_out_increments.values())
    undefined = degree_of_synergy(full_increment=Q_([0, 1], "molar"), individual_increments=[Q_([0, 0], "molar")])
    assert not undefined.defined.any() and np.isnan(undefined.degree_of_synergy).all()
    with pytest.raises(ValueError, match="max_members"):
        run_synergy_counterfactuals(members=["a", "b"], run=run, observable=lambda x: x, max_members=1)
    with pytest.raises(ValueError, match="shape"):
        degree_of_synergy(full_increment=Q_([1, 2], "molar"), individual_increments=[Q_(1, "molar")])


def test_configured_example_has_native_kernels_and_material_validation():
    config = load_model_config(ROOT / "data/model_configs/toy_chain_scission.yml")
    inputs = ConfiguredInputLoader().load(config)
    model = ConfiguredProcessAssembler().assemble(config, inputs).model
    request = RunRequest(initial_state=inputs.initial_state, t_span=inputs.t_span, t_eval=inputs.t_eval)
    solver = ProcessODESolver(model)
    assert solver.compile(request).summary()["analytic_jacobian_count"] == len(model.processes)
    assert all(v.passed for v in solver.run(request).validation_results)


def test_missing_chain_or_source_is_refused():
    kwargs = dict(
        name="bad",
        chain_states={1: "a", 4: "b"},
        parent_length=4,
        fragment_length=2,
        mode="exo",
        solid_min_length=4,
        enzyme_state="E",
        kcat_symbol="k",
        km_symbol="K",
        accessible_fraction_symbol="Fa",
        state_units="molar",
        enzyme_units="molar",
        source=SOURCE,
    )
    with pytest.raises(ValueError, match="every integer"):
        ChainScissionProcess(**kwargs)
    kwargs["source"] = ""
    with pytest.raises(ValueError, match="source"):
        ChainScissionProcess(**kwargs)


def test_parameter_changes_do_not_modify_embedded_constants():
    model, initial, _ = system()
    process = model.processes[-1]
    baseline = process.rate(initial, Q_(0, "s"), model.parameters)
    params = ParameterSet([replace(p, value=p.value * 2) if p.symbol == "k_exo" else p for p in model.parameters])
    assert process.rate(initial, Q_(0, "s"), params).magnitude == pytest.approx(2 * baseline.magnitude)


def test_single_channel_requires_complete_population_and_reports_observables():
    chains = {i: f"C{i}" for i in range(1, 5)}
    process = ChainScissionProcess(
        name="single_exo", chain_states=chains, parent_length=4, fragment_length=2, mode="exo",
        solid_min_length=4, enzyme_state="E", kcat_symbol="k", km_symbol="K",
        accessible_fraction_symbol="Fa", state_units="mM", enzyme_units="mM", source=SOURCE,
    )
    assert {spec.name for spec in process.required_state_variables} == {*chains.values(), "E"}
    parameters = ParameterSet([parameter("k", 1, "1/s"), parameter("K", 1, "mM"), parameter("Fa", 1, "dimensionless")])
    model = ModelBuilder(process_library=ProcessRegistry([process]), parameters=parameters).assemble()
    initial = {name: Q_(int(i == 4), "mM") for i, name in chains.items()}
    initial["E"] = Q_(1, "mM")
    result = model.run(initial_state=initial, t_span=(Q_(0, "s"), Q_(1, "s")), t_eval=Q_([0, 1], "s"))
    observed = process.derived_quantities(result.states, parameters)
    np.testing.assert_allclose(observed["material_equivalents"].magnitude, 4)
    np.testing.assert_array_equal(result.states["C1"].magnitude, 0)
    np.testing.assert_array_equal(result.states["C3"].magnitude, 0)


@pytest.mark.parametrize("field,value", [("solid_min_length", 3.5), ("parent_length", 4.0), ("fragment_length", 2.5), ("solid_min_length", True)])
def test_structural_lengths_cannot_be_fractional_or_boolean(field, value):
    kwargs = dict(name="invalid_structure", chain_states={i: f"C{i}" for i in range(1, 5)},
        parent_length=4, fragment_length=2, mode="exo", solid_min_length=4, enzyme_state="E",
        kcat_symbol="k", km_symbol="K", accessible_fraction_symbol="Fa",
        state_units="mM", enzyme_units="mM", source=SOURCE)
    kwargs[field] = value
    with pytest.raises(ValueError, match="integer"):
        ChainScissionProcess(**kwargs)


def test_chain_numerical_overflow_fails_closed():
    from fungal_model.kinetics.chain_scission import chain_scission_rate_and_gradient
    with pytest.raises(ValueError, match="numerical range"):
        chain_scission_rate_and_gradient(enzyme=1e300, chains=np.array([1e300]),
            weights=np.array([1.]), parent_index=0, kcat=1e300, km=1., accessible_fraction=1.)
