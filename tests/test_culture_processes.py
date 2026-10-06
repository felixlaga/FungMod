"""Generic resource-limited culture processes: kernels, refusals, factories and parity with the opt-in classes.

Every direct process test uses abstract dissolved pools (resource, cells,
nutrient, acceptor, product) in millimolar and hours; nothing here names an
organism, a substrate chemistry or a measured value.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from fungal_model.core.kernels import KernelContext
from fungal_model.core.numerics import SolverSettings
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_
from fungal_model.io import ProcessConfig, load_model_config
from fungal_model.fungi.respiration import COMPILED_ENGINE, NATIVE_ENGINE
from fungal_model.processes import (
    COSTED_SECRETION_PROCESS_TYPE,
    DILUTION_EXCHANGE_PROCESS_TYPE,
    GAS_TRANSFER_PROCESS_TYPE,
    RESOURCE_LIMITED_GROWTH_PROCESS_TYPE,
    RESOURCE_LIMITED_MAINTENANCE_PROCESS_TYPE,
    CostedSecretionProcess,
    DilutionExchangeProcess,
    GasTransferProcess,
    ModelBuilder,
    ProcessBuildContext,
    ProcessLibrary,
    ProcessRegistry,
    ResourceLimitedGrowthProcess,
    ResourceLimitedMaintenanceProcess,
)
from fungal_model.solvers import ProcessODESolver, RunRequest
from fungal_model.workflows.configured_model import ConfiguredInputLoader, ConfiguredProcessAssembler, require_runnable_config
from tests.test_degrading_culture import model as degrading_model
from tests.test_degrading_culture import state as degrading_state
from tests.test_respiration import culture as respiring_culture
from tests.test_respiration import parameter as respiring_parameter
from tests.test_respiration import state as respiring_state

ROOT = Path(__file__).resolve().parents[1]
TOY_CONFIG = ROOT / "data" / "model_configs" / "toy_resource_limited_chemostat.yml"
SOURCE = "Artificial kernel benchmark; no organism, chemistry or measurement is claimed."
POOLS = {"substrate_state": "resource", "biomass_state": "cells", "nutrient_state": "nutrient", "oxidant_state": "acceptor"}
SYMBOLS = {
    "true_yield_symbol": "Y",
    "maintenance_demand_symbol": "m",
    "uptake_capacity_symbol": "q",
    "substrate_half_saturation_symbol": "K_r",
    "nutrient_half_saturation_symbol": "K_n",
    "oxidant_half_saturation_symbol": "K_a",
}
UNITS = {"concentration_units": "millimolar", "time_units": "hour"}


def _parameter(symbol: str, value: float, units: str) -> Parameter:
    return Parameter(f"artificial {symbol}", symbol, value, units, None, SOURCE, "testing", "Artificial benchmark value.")


def parameters(**overrides: float) -> ParameterSet:
    values = {"Y": (0.4, "dimensionless"), "m": (0.01, "1 / hour"), "q": (0.5, "1 / hour"), "K_r": (0.2, "millimolar"),
              "K_n": (0.05, "millimolar"), "K_a": (0.01, "millimolar"), "f": (0.3, "dimensionless"),
              "y_s": (2.0, "dimensionless"), "D": (0.05, "1 / hour"), "c_feed": (5.0, "millimolar"),
              "kLa": (10.0, "1 / hour"), "c_sat": (0.25, "millimolar")}
    for symbol, value in overrides.items():
        values[symbol] = (value, values[symbol][1])
    return ParameterSet([_parameter(symbol, value, units) for symbol, (value, units) in values.items()])


def growth(**kwargs) -> ResourceLimitedGrowthProcess:
    fields = dict(name="growth", stoichiometry={"resource": -2.5, "cells": 1.0, "nutrient": -0.2, "acceptor": -1.0},
                  allocation_fraction_symbol="f", source=SOURCE, **POOLS, **SYMBOLS, **UNITS)
    fields.update(kwargs)
    return ResourceLimitedGrowthProcess(**fields)


def maintenance(**kwargs) -> ResourceLimitedMaintenanceProcess:
    fields = dict(name="maintenance", stoichiometry={"resource": -1.0, "acceptor": -6.0}, source=SOURCE, **POOLS, **SYMBOLS, **UNITS)
    fields.update(kwargs)
    return ResourceLimitedMaintenanceProcess(**fields)


def secretion(**kwargs) -> CostedSecretionProcess:
    fields = dict(name="secretion", stoichiometry={"resource": -0.5, "nutrient": -0.3, "acceptor": -2.0, "product": 1.0},
                  allocation_fraction_symbol="f", secretion_yield_symbol="y_s", source=SOURCE, **POOLS, **SYMBOLS, **UNITS)
    fields.update(kwargs)
    return CostedSecretionProcess(**fields)


def exchanges(**kwargs):
    dilution = DilutionExchangeProcess(name="dilution", pool_state="resource", dilution_rate_symbol="D", feed_symbol="c_feed",
                                       source=SOURCE, **UNITS, **kwargs)
    transfer = GasTransferProcess(name="transfer", pool_state="resource", transfer_rate_symbol="kLa", saturation_symbol="c_sat",
                                  source=SOURCE, **UNITS, **kwargs)
    return dilution, transfer


STATE_NAMES = ("resource", "cells", "nutrient", "acceptor", "product", "ledger")


def _context(state_units: str, parameter_set: ParameterSet) -> KernelContext:
    return KernelContext(state_index={name: index for index, name in enumerate(STATE_NAMES)},
                         state_units=dict.fromkeys(STATE_NAMES, state_units), time_units="hour", parameters=parameter_set)


@pytest.mark.parametrize("state_units,scale", [("millimolar", 1.0), ("mole / liter", 1e-3)])
@pytest.mark.parametrize("builder", [growth, maintenance, secretion, lambda: exchanges()[0], lambda: exchanges()[1]])
def test_kernels_match_unit_aware_rates_on_abstract_pools(builder, state_units, scale) -> None:
    process = builder()
    parameter_set = parameters()
    kernel = process.compile_rate(_context(state_units, parameter_set))
    assert kernel is not None
    rng = np.random.default_rng(7)
    for _ in range(25):
        vector = rng.uniform(0.0, 1.0, len(STATE_NAMES)) * scale  # state vector in `state_units`
        state = {name: Q_(value, state_units) for name, value in zip(STATE_NAMES, vector, strict=True)}
        expected = process.rate(state, Q_(0.0, "hour"), parameter_set).to(process.rate_units).magnitude
        assert kernel(0.0, vector) == pytest.approx(float(expected), rel=1e-12, abs=1e-18)
    # Contributions are the declared stoichiometry times the rate (plus the ledgers).
    contributions = process.contributions(Q_(2.0, process.rate_units))
    for name, coefficient in getattr(process, "stoichiometry", {}).items():
        assert contributions[name].magnitude == pytest.approx(2.0 * coefficient)


def test_growth_and_secretion_share_one_post_maintenance_budget() -> None:
    parameter_set = parameters()
    state = {name: Q_(value, "millimolar") for name, value in zip(STATE_NAMES, (0.8, 0.3, 0.4, 0.2, 0.0, 0.0), strict=True)}
    rates = {name: process.rate(state, Q_(0.0, "hour"), parameter_set).magnitude
             for name, process in (("growth", growth()), ("maintenance", maintenance()), ("secretion", secretion()))}
    capacity = 0.5 * 0.8 / (0.2 + 0.8) * 0.2 / (0.01 + 0.2)
    budget = (capacity - 0.01) * 0.4 / (0.05 + 0.4) * 0.3  # per unit cells, times the cell pool
    assert rates["maintenance"] == pytest.approx(0.01 * 0.3)
    assert rates["growth"] == pytest.approx(0.7 * 0.4 * budget)
    assert rates["secretion"] == pytest.approx(0.3 * 2.0 * budget)
    # Without an allocation symbol the whole budget forms cells.
    assert growth(allocation_fraction_symbol=None).rate(state, Q_(0.0, "hour"), parameter_set).magnitude == pytest.approx(0.4 * budget)
    # Below the maintenance demand nothing grows and maintenance is capped by the capacity.
    starved = dict(state, resource=Q_(1e-4, "millimolar"))
    assert growth().rate(starved, Q_(0.0, "hour"), parameter_set).magnitude == 0.0
    assert secretion().rate(starved, Q_(0.0, "hour"), parameter_set).magnitude == 0.0
    assert maintenance().rate(starved, Q_(0.0, "hour"), parameter_set).magnitude < 0.01 * 0.3


def test_exchange_processes_integrate_to_the_analytic_mixed_steady_state() -> None:
    dilution, transfer = exchanges(ledger_state="ledger")
    model = ModelBuilder(process_library=ProcessRegistry([dilution, transfer]), requested_processes=("dilution", "transfer"),
                         parameters=parameters(), solver_settings=SolverSettings(rtol=1e-10, atol=1e-13)).assemble()
    times = np.linspace(0.0, 2.0, 21)
    result = ProcessODESolver(model).run(RunRequest(
        initial_state={"resource": Q_(1.0, "millimolar"), "ledger": Q_(0.0, "millimolar")},
        t_span=(Q_(0.0, "hour"), Q_(2.0, "hour")), t_eval=Q_(times, "hour")))
    total = 0.05 + 10.0
    steady = (0.05 * 5.0 + 10.0 * 0.25) / total
    expected = steady + (1.0 - steady) * np.exp(-total * times)
    np.testing.assert_allclose(result.states["resource"].magnitude, expected, rtol=1e-8)
    np.testing.assert_allclose(result.states["ledger"].magnitude, expected - 1.0, rtol=1e-8, atol=1e-12)
    assert result.solver_metadata["kernel"]["quantity_wrapped_kernel_count"] == 0


def test_processes_refuse_invalid_declarations_and_states() -> None:
    with pytest.raises(ValueError, match="four distinct states"):
        growth(nutrient_state="resource")
    with pytest.raises(ValueError, match="needs a stoichiometry"):
        maintenance(stoichiometry={})
    with pytest.raises(ValueError, match="finite and non-zero"):
        maintenance(stoichiometry={"resource": 0.0})
    with pytest.raises(ValueError, match="extent ledger state"):
        growth(extent_state="cells")
    with pytest.raises(ValueError, match="boundary ledger state"):
        DilutionExchangeProcess(name="d", pool_state="resource", dilution_rate_symbol="D", feed_symbol="c_feed",
                                ledger_state="resource", **UNITS)
    state = {name: Q_(0.1, "millimolar") for name in STATE_NAMES}
    with pytest.raises(ValueError, match="must lie in"):
        growth().rate(state, Q_(0.0, "hour"), parameters(f=1.5))
    with pytest.raises(ValueError, match="must be positive"):
        secretion().rate(state, Q_(0.0, "hour"), parameters(y_s=0.0))
    with pytest.raises(ValueError, match="must be positive"):
        maintenance().rate(state, Q_(0.0, "hour"), parameters(K_r=0.0))
    with pytest.raises(ValueError, match="must be non-negative"):
        growth().rate(dict(state, resource=Q_(-0.1, "millimolar")), Q_(0.0, "hour"), parameters())
    with pytest.raises(ValueError, match="must be non-negative"):
        exchanges()[0].rate(state, Q_(0.0, "hour"), parameters(D=-1.0))
    with pytest.raises(ValueError, match="must be non-negative"):
        exchanges()[1].rate(state, Q_(0.0, "hour"), parameters(c_sat=-1.0))


def _config(process_type: str, **fields) -> ProcessConfig:
    return ProcessConfig(id=f"toy_{process_type}", process_type=process_type, **fields)


CLOSURE_STATES = {"substrate": "resource", "biomass": "cells", "nutrient": "nutrient", "oxidant": "acceptor"}
CLOSURE_PARAMETERS = {"true_yield": "Y", "maintenance_demand": "m", "uptake_capacity": "q", "substrate_half_saturation": "K_r",
                      "nutrient_half_saturation": "K_n", "oxidant_half_saturation": "K_a", "time_units": "hour"}


def test_factories_build_the_closure_and_exchanges_from_config() -> None:
    library = ProcessLibrary.default_foundation()
    context = ProcessBuildContext(state_units=dict.fromkeys(STATE_NAMES, "millimolar"), source=SOURCE)
    configs = [
        _config(RESOURCE_LIMITED_GROWTH_PROCESS_TYPE, states={**CLOSURE_STATES, "extent": "ledger"},
                parameters={**CLOSURE_PARAMETERS, "allocation_fraction": "f"},
                stoichiometry={"resource": -2.5, "cells": 1.0, "nutrient": -0.2, "acceptor": -1.0}),
        _config(RESOURCE_LIMITED_MAINTENANCE_PROCESS_TYPE, states=CLOSURE_STATES, parameters=CLOSURE_PARAMETERS,
                stoichiometry={"resource": -1.0, "acceptor": -6.0}),
        _config(COSTED_SECRETION_PROCESS_TYPE, states=CLOSURE_STATES,
                parameters={**CLOSURE_PARAMETERS, "allocation_fraction": "f", "secretion_yield": "y_s"},
                stoichiometry={"resource": -0.5, "nutrient": -0.3, "acceptor": -2.0, "product": 1.0}),
        _config(DILUTION_EXCHANGE_PROCESS_TYPE, states={"pool": "resource", "ledger": "ledger"},
                parameters={"dilution_rate": "D", "feed": "c_feed", "time_units": "hour"}),
        _config(GAS_TRANSFER_PROCESS_TYPE, states={"pool": "acceptor"},
                parameters={"transfer_rate": "kLa", "saturation": "c_sat", "time_units": "hour"}),
    ]
    processes = library.build_processes(context, configs)
    assert [type(process) for process in processes] == [
        ResourceLimitedGrowthProcess, ResourceLimitedMaintenanceProcess, CostedSecretionProcess, DilutionExchangeProcess, GasTransferProcess]
    built_growth = processes[0]
    assert isinstance(built_growth, ResourceLimitedGrowthProcess)
    assert built_growth.extent_state == "ledger" and built_growth.allocation_fraction_symbol == "f"
    assert built_growth.stoichiometry == {"resource": -2.5, "cells": 1.0, "nutrient": -0.2, "acceptor": -1.0}
    assert built_growth.concentration_units == "millimolar" and built_growth.source == SOURCE
    built_secretion = processes[2]
    assert isinstance(built_secretion, CostedSecretionProcess)
    assert built_secretion.secretion_yield_symbol == "y_s"
    built_dilution = processes[3]
    assert isinstance(built_dilution, DilutionExchangeProcess)
    assert built_dilution.ledger_state == "ledger" and built_dilution.coefficient_symbol == "D"
    built_transfer = processes[4]
    assert isinstance(built_transfer, GasTransferProcess)
    assert built_transfer.ledger_state is None and built_transfer.target_symbol == "c_sat"
    # Every built process compiles to a numeric kernel in the assembled model.
    model = ModelBuilder(process_library=ProcessRegistry(processes), requested_processes=tuple(p.name for p in processes),
                         parameters=parameters()).assemble()
    compiled = ProcessODESolver(model).compile(RunRequest(
        initial_state={name: Q_(0.1, "millimolar") for name in STATE_NAMES}, t_span=(Q_(0.0, "hour"), Q_(1.0, "hour"))))
    assert compiled.summary()["quantity_wrapped_kernel_count"] == 0
    assert compiled.summary()["process_count"] == 5


def test_factories_report_missing_fields_instead_of_guessing() -> None:
    library = ProcessLibrary.default_foundation()
    context = ProcessBuildContext(state_units={"resource": "millimolar", "cells": "millimolar", "nutrient": "millimolar"})
    partial = _config(RESOURCE_LIMITED_GROWTH_PROCESS_TYPE, states=CLOSURE_STATES,
                      parameters={key: value for key, value in CLOSURE_PARAMETERS.items() if key != "uptake_capacity"})
    decision = library.factory_for(RESOURCE_LIMITED_GROWTH_PROCESS_TYPE).can_build(context, partial)
    assert not decision.can_build
    assert set(decision.missing_fields) >= {"stoichiometry", "parameters.uptake_capacity", "state_units.acceptor"}
    with pytest.raises(ValueError, match="cannot build"):
        library.factory_for(RESOURCE_LIMITED_GROWTH_PROCESS_TYPE).build(context, partial)
    mismatched = ProcessBuildContext(state_units={**dict.fromkeys(STATE_NAMES, "millimolar"), "cells": "gram / liter"})
    complete = _config(RESOURCE_LIMITED_MAINTENANCE_PROCESS_TYPE, states=CLOSURE_STATES, parameters=CLOSURE_PARAMETERS,
                       stoichiometry={"resource": -1.0})
    with pytest.raises(ValueError, match="share the units"):
        library.factory_for(RESOURCE_LIMITED_MAINTENANCE_PROCESS_TYPE).build(mismatched, complete)
    exchange = _config(GAS_TRANSFER_PROCESS_TYPE, states={"pool": "acceptor"}, parameters={"transfer_rate": "kLa", "time_units": "hour"})
    decision = library.factory_for(GAS_TRANSFER_PROCESS_TYPE).can_build(context, exchange)
    assert set(decision.missing_fields) == {"parameters.saturation", "state_units.acceptor"}


def test_packaged_toy_chemostat_config_runs_through_the_configured_workflow() -> None:
    config = load_model_config(TOY_CONFIG)
    require_runnable_config(config)
    assert [process.process_type for process in config.processes] == [
        RESOURCE_LIMITED_GROWTH_PROCESS_TYPE, RESOURCE_LIMITED_MAINTENANCE_PROCESS_TYPE, COSTED_SECRETION_PROCESS_TYPE,
        DILUTION_EXCHANGE_PROCESS_TYPE, GAS_TRANSFER_PROCESS_TYPE]
    assert config.processes[0].stoichiometry["cell_concentration"] == 1.0
    assert "stoichiometry" in config.processes[0].to_dict() and "stoichiometry" not in config.processes[3].to_dict()
    inputs = ConfiguredInputLoader().load(config)
    model = ConfiguredProcessAssembler().assemble(config, inputs).model
    result = ProcessODESolver(model).run(RunRequest(initial_state=inputs.initial_state, t_span=inputs.t_span, t_eval=inputs.t_eval))
    assert result.solver_metadata["kernel"]["quantity_wrapped_kernel_count"] == 0
    cells = result.states["cell_concentration"].magnitude
    product = result.states["product_concentration"].magnitude
    assert cells[-1] > cells[0] and product[-1] > 0.0
    extent = result.states["growth_extent"].magnitude
    np.testing.assert_allclose(extent, cells - cells[0], rtol=1e-6, atol=1e-10)  # only growth changes the cell pool
    assert result.states["acceptor_concentration"].magnitude.min() > 0.0


@pytest.mark.parametrize("chemostat", [False, True])
def test_resource_limited_culture_compiled_path_matches_the_native_right_hand_side(chemostat) -> None:
    overrides = {}
    if chemostat:
        overrides = dict(dilution_rate=respiring_parameter("D", .03, "1/h"), gas_transfer_rate=respiring_parameter("kla", 15, "1/h"),
                         feed={"S": Q_(.05, "mol/L"), "N": Q_(.02, "mol/L"), "O": Q_(0, "mol/L")})
    culture = respiring_culture(**overrides)
    assert [process.name for process in culture.compiled_processes()] == [
        "growth", "maintenance", "dilution:S", "dilution:X", "dilution:N", "dilution:O", "gas_transfer:O"]
    assert set(parameter.symbol for parameter in culture.compiled_parameters()) == {
        "Y", "m", "qmax", "ks", "kn", "ko", "D", "kla", "Osat", "feed:S", "feed:X", "feed:N", "feed:O"}
    assert culture.compiled_parameters().get("feed:X").quantity.magnitude == 0.0
    settings = SolverSettings(rtol=1e-10, atol=1e-13)
    times = Q_(np.linspace(0, 40, 81), "h")
    native = culture.simulate(initial_state=respiring_state(), times=times, solver_settings=settings)
    compiled = culture.simulate_compiled(initial_state=respiring_state(), times=times, solver_settings=settings)
    for name in culture.names:
        np.testing.assert_allclose(compiled.concentrations[name].magnitude, native.concentrations[name].magnitude, rtol=1e-6, atol=1e-11)
    for name in native.cumulative_boundary_exchange:
        np.testing.assert_allclose(compiled.cumulative_boundary_exchange[name].magnitude,
                                   native.cumulative_boundary_exchange[name].magnitude, rtol=1e-6, atol=1e-11)
        np.testing.assert_allclose(compiled.cumulative_reaction_exchange[name].magnitude,
                                   native.cumulative_reaction_exchange[name].magnitude, rtol=1e-6, atol=1e-11)
    np.testing.assert_allclose(compiled.specific_growth_rate.magnitude, native.specific_growth_rate.magnitude, rtol=1e-6, atol=1e-12)
    assert max(compiled.diagnostics["maximum_absolute_balance_residual_mol_L"].values()) < 1e-10
    assert compiled.diagnostics["engine"] == COMPILED_ENGINE and native.diagnostics["engine"] == NATIVE_ENGINE
    assert compiled.diagnostics["jacobian"] == "finite_difference_by_backend" and native.diagnostics["jacobian"] == "analytic piecewise"
    kernel = compiled.diagnostics["kernel"]
    assert kernel["state_count"] == 10 and kernel["process_count"] == 7 and kernel["quantity_wrapped_kernel_count"] == 0
    assert compiled.provenance == native.provenance


@pytest.mark.parametrize("alternative,dilution", [(False, 0.0), (True, 0.02)])
def test_degrading_culture_compiled_path_matches_the_native_right_hand_side(alternative, dilution) -> None:
    culture = degrading_model(alternative=alternative, dilution=dilution)
    assert [process.name for process in culture.compiled_processes()][:5] == list(culture.processes)
    symbols = set(parameter.symbol for parameter in culture.compiled_parameters())
    assert {"Y", "m", "q", "ks", "kn", "ko", "f", "kh", "kp", "kd", "secretion_yield", "D", "kla", "osat"} <= symbols
    assert {f"feed:{name}" for name in culture.names} <= symbols
    assert culture.compiled_parameters().get("secretion_yield").quantity.magnitude == pytest.approx(2.0)
    settings = SolverSettings(rtol=1e-10, atol=1e-13)
    times = Q_(np.linspace(0, 120, 121), "h")
    native = culture.simulate(initial_state=degrading_state(), times=times, solver_settings=settings)
    compiled = culture.simulate_compiled(initial_state=degrading_state(), times=times, solver_settings=settings)
    for name in culture.names:
        np.testing.assert_allclose(compiled.concentrations[name].magnitude, native.concentrations[name].magnitude, rtol=1e-6, atol=1e-11)
    for name in culture.processes:
        np.testing.assert_allclose(compiled.process_rates[name].magnitude, native.process_rates[name].magnitude, rtol=1e-6, atol=1e-11)
    for name in native.cumulative_boundary_exchange:
        np.testing.assert_allclose(compiled.cumulative_boundary_exchange[name].magnitude,
                                   native.cumulative_boundary_exchange[name].magnitude, rtol=1e-6, atol=1e-11)
    assert max(compiled.diagnostics["maximum_absolute_balance_residual_mol_L"].values()) < 1e-10
    assert compiled.diagnostics["minimum_pool_mol_L"] > -1e-12
    kernel = compiled.diagnostics["kernel"]
    assert kernel["state_count"] == 19 and kernel["process_count"] == 13 and kernel["quantity_wrapped_kernel_count"] == 0
    assert compiled.diagnostics["engine"] == COMPILED_ENGINE and compiled.diagnostics["maturity"] == native.diagnostics["maturity"]


def test_compiled_representation_refuses_colliding_parameter_symbols() -> None:
    culture = respiring_culture(nitrogen_half_saturation=respiring_parameter("ks", .0001, "mol/L"))
    with pytest.raises(ValueError, match="used twice"):
        culture.compiled_parameters()
    # The processes refuse the collision too: one symbol cannot serve two requirements.
    with pytest.raises(ValueError, match="Duplicate parameter requirement"):
        culture.simulate_compiled(initial_state=respiring_state(), times=Q_([0, 1], "h"))
