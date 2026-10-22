"""Driving-force enforcement, fixed solvent activity, dG0(T), and per-pool equilibrium residuals (WP1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from fungal_model import ConfiguredModelExecutionError, run_configured_model
from fungal_model.chemistry import (
    DetailedBalanceNetwork,
    DetailedBalanceReaction,
    ElementalComposition,
    MacrochemicalBalance,
    MacrochemicalSpecies,
)
from fungal_model.chemistry.thermodynamics import (
    ACTIVITY_BASIS_FIXED,
    DRIVING_FORCE_MATURITY,
    ENFORCEMENT_BLOCK,
    ENFORCEMENT_DRIVING_FORCE,
    TEMPERATURE_DEPENDENCE_CONSTANT_ENTHALPY,
    TEMPERATURE_DEPENDENCE_NONE,
    DynamicActivityParticipant,
    DynamicThermodynamicConstraint,
)
from fungal_model.core.kernels import KernelContext
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_
from fungal_model.solvers.compiled import KERNEL_QUANTITY_WRAPPED_THERMODYNAMIC
from tests.test_dynamic_thermodynamic_enforcement import _dynamic_config, _dynamic_validation, _write_config


SOURCE = "Artificial framework benchmark for thermodynamic driving-force tests."
GAS_CONSTANT = 8.31446261815324


def _parameter(symbol: str, value: float, units: str) -> Parameter:
    return Parameter(
        name=symbol,
        symbol=symbol,
        value=value,
        units=units,
        uncertainty=0.0,
        source=SOURCE,
        confidence_level="testing",
        notes="Artificial software-contract value; not biological evidence.",
        measurement_method="defined framework benchmark value",
    )


def _constraint(
    participants: tuple[DynamicActivityParticipant, ...],
    *,
    standard_delta_gibbs: float,
    mode: str = ENFORCEMENT_DRIVING_FORCE,
    temperature: float = 298.15,
    standard_concentration: tuple[float, str] = (1.0, "mole / liter"),
    minimum_activity: float = 1.0e-12,
    tolerance: float = 0.0,
    **extra: Any,
) -> DynamicThermodynamicConstraint:
    return DynamicThermodynamicConstraint(
        constraint_id="c",
        process_id="p",
        reaction_id="r",
        electron_balance_check_id="e",
        participants=participants,
        standard_energy_method="standard_delta_gibbs",
        standard_delta_gibbs=_parameter("delta_g_standard", standard_delta_gibbs, "joule / mole"),
        temperature=_parameter("temperature", temperature, "kelvin"),
        gas_constant=_parameter("gas_constant", GAS_CONSTANT, "joule / mole / kelvin"),
        standard_concentration=_parameter("c_standard", *standard_concentration),
        minimum_activity=_parameter("minimum_activity", minimum_activity, "dimensionless"),
        absolute_tolerance=_parameter("delta_g_tolerance", tolerance, "joule / mole"),
        provenance_refs=(SOURCE,),
        enforcement_mode=mode,
        **extra,
    )


AB = (
    DynamicActivityParticipant("A", "a", -1.0),
    DynamicActivityParticipant("B", "b", 1.0),
)


def _driving_force_config(*, stop_seconds: float = 60.0) -> dict[str, Any]:
    config = _dynamic_config(method="standard_delta_gibbs")
    config["thermodynamic_constraints"][0]["enforcement_mode"] = ENFORCEMENT_DRIVING_FORCE
    config["time"] = {
        "start": {"value": 0.0, "units": "second"},
        "stop": {"value": stop_seconds, "units": "second"},
        "points": int(stop_seconds) + 1,
    }
    return config


# --- configured path -------------------------------------------------------


def test_driving_force_relaxes_a_product_dominated_start_that_block_mode_freezes(
    tmp_path: Path,
) -> None:
    # Reactant at a trace above the activity floor: a forward law that vanishes at
    # exactly zero reactant gives r_net = 0 there (documented fixed point).
    initial = {
        "dissolved_substrate_amount": {"value": 1.0e-6, "units": "mM"},
        "released_product_amount": {"value": 1.0, "units": "mM"},
    }
    driving = _driving_force_config()
    driving["initial_state"]["states"] = dict(initial)
    result = run_configured_model(
        _write_config(tmp_path, driving, name="driving.yml"),
        output_dir=tmp_path / "driving_output",
    )
    a = result.state("dissolved_substrate_amount").to("mM").magnitude
    b = result.state("released_product_amount").to("mM").magnitude
    assert a[-1] == pytest.approx(0.5, abs=1.0e-3)
    assert b[-1] == pytest.approx(0.5, abs=1.0e-3)
    assert a + b == pytest.approx(np.full_like(a, 1.0 + 1.0e-6), rel=1.0e-7, abs=1.0e-7)
    rate = result.process_rates["a_to_b"].to("mM / second").magnitude
    assert rate[0] < 0.0
    assert abs(rate[-1]) < 1.0e-3

    prefix = "dynamic_thermodynamics.a_to_b_dynamic"
    blocked = result.derived_quantities[f"{prefix}.rate_blocked"].magnitude
    assert np.all(blocked == 0.0)
    delta_g = result.derived_quantities[f"{prefix}.delta_gibbs"].to("joule / mole").magnitude
    assert delta_g[0] > 0.0
    assert abs(delta_g[-1]) < 10.0
    validation = _dynamic_validation(result.validation_report())
    assert validation["passed"] is True
    assert validation["details"]["solver_time_enforcement"] == ENFORCEMENT_DRIVING_FORCE
    assert validation["details"]["recorded_blocked_count"] == 0
    kernel = result.solver_metadata["kernel"]["process_kernels"]["a_to_b"]
    assert kernel == KERNEL_QUANTITY_WRAPPED_THERMODYNAMIC
    constraint = result.assembly_report.to_dict()["dynamic_thermodynamic_constraints"][0]
    assert constraint["enforcement_mode"] == ENFORCEMENT_DRIVING_FORCE
    assert constraint["maturity"] == DRIVING_FORCE_MATURITY
    assert constraint["reverse_saturation"] == "not_represented"
    assert constraint["temperature_dependence"] == TEMPERATURE_DEPENDENCE_NONE
    assert any("Beard" in text for text in constraint["law_provenance"])
    names = {record["name"] for record in constraint["assumptions"]}
    assert "a_to_b_dynamic.driving_force_flux_force" in names

    block = _dynamic_config(method="standard_delta_gibbs")
    block["initial_state"]["states"] = dict(initial)
    block["time"] = driving["time"]
    frozen = run_configured_model(
        _write_config(tmp_path, block, name="block.yml"),
        output_dir=tmp_path / "block_output",
    )
    assert frozen.state("released_product_amount").to("mM").magnitude[-1] == pytest.approx(1.0)
    assert frozen.state("dissolved_substrate_amount").to("mM").magnitude[-1] == pytest.approx(1.0e-6)
    assert np.all(frozen.derived_quantities[f"{prefix}.rate_blocked"].magnitude == 1.0)


def test_configured_fixed_activity_and_temperature_dependence_round_trip(
    tmp_path: Path,
) -> None:
    config = _driving_force_config(stop_seconds=100.0)
    config["initial_state"]["states"]["dissolved_substrate_amount"] = {"value": 2.0, "units": "mM"}
    config["thermodynamic_constraints"][0]["activity_model"]["fixed_activities"] = {
        "product_species": {"value": 1.0, "source": "Declared unit-activity convention for the test product."}
    }
    config["thermodynamic_constraints"][0]["standard_energy"].update(
        {
            "standard_enthalpy": {
                **config["thermodynamic_constraints"][0]["standard_energy"]["standard_delta_gibbs"],
                "name": "artificial standard enthalpy",
                "symbol": "delta_h_standard_ab",
                "value": -5000.0,
            },
            "reference_temperature": {
                **config["thermodynamic_constraints"][0]["temperature"],
                "name": "reference temperature of the declared standard Gibbs energy",
                "symbol": "reference_temperature_ab",
                "value": 298.15,
            },
        }
    )
    result = run_configured_model(
        _write_config(tmp_path, config, name="fixed.yml"),
        output_dir=tmp_path / "fixed_output",
    )
    constraint = result.assembly_report.to_dict()["dynamic_thermodynamic_constraints"][0]
    fixed = [item for item in constraint["participants"] if item["species_id"] == "product_species"]
    assert len(fixed) == 1
    assert fixed[0]["state_name"] == ""
    assert fixed[0]["activity_basis"] == ACTIVITY_BASIS_FIXED
    assert fixed[0]["fixed_activity"] == pytest.approx(1.0)
    # The bound trajectory state is still integrated but ignored by the quotient;
    # the override is explicit on the participant and in the assumption record.
    assert fixed[0]["overridden_state_name"] == "released_product_amount"
    override = [item for item in constraint["assumptions"] if item["name"].endswith(".fixed_activity_participants")]
    assert len(override) == 1
    assert "product_species -> released_product_amount" in override[0]["known_limitations"]
    assert constraint["temperature_dependence"] == TEMPERATURE_DEPENDENCE_CONSTANT_ENTHALPY
    expected_standard = -5000.0 - 303.15 * (-5000.0 - 0.0) / 298.15
    validation = _dynamic_validation(result.validation_report())
    assert validation["details"]["standard_delta_gibbs"] == pytest.approx(expected_standard)
    activity = result.derived_quantities["dynamic_thermodynamics.a_to_b_dynamic.activity.product_species"]
    assert np.all(activity.magnitude == 1.0)
    # Equilibrium with the product fixed at unit activity: a_A = exp(dG0(T) / (R T)).
    expected_a = float(np.exp(expected_standard / (GAS_CONSTANT * 303.15)))
    a = result.state("dissolved_substrate_amount").to("mM").magnitude
    assert a[-1] == pytest.approx(expected_a, abs=1.0e-3)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda config: config["thermodynamic_constraints"][0].update(
                {"enforcement_mode": "reversible_haldane"}
            ),
            "unsupported enforcement_mode",
        ),
        (
            lambda config: config["thermodynamic_constraints"][0]["activity_model"].update(
                {"fixed_activities": {"water": {"value": 1.0, "source": "x"}}}
            ),
            "not participants of reaction",
        ),
        (
            lambda config: config["thermodynamic_constraints"][0]["activity_model"].update(
                {"fixed_activities": {"product_species": {"value": -1.0, "source": "x"}}}
            ),
            "finite positive activity",
        ),
        (
            lambda config: config["thermodynamic_constraints"][0]["activity_model"].update(
                {"fixed_activities": {"product_species": {"value": 1.0}}}
            ),
            "missing fields \\['source'\\]",
        ),
        (
            lambda config: config["thermodynamic_constraints"][0]["standard_energy"].update(
                {
                    "standard_enthalpy": {
                        **config["thermodynamic_constraints"][0]["standard_energy"]["standard_delta_gibbs"],
                        "symbol": "delta_h_standard_ab",
                    }
                }
            ),
            "needs both standard_enthalpy and reference_temperature",
        ),
    ],
)
def test_configured_driving_force_refusals(tmp_path: Path, mutate: Any, message: str) -> None:
    config = _driving_force_config()
    mutate(config)
    with pytest.raises(ConfiguredModelExecutionError, match=message):
        run_configured_model(_write_config(tmp_path, config))


# --- analytic identities ---------------------------------------------------


def test_net_rate_vanishes_at_equilibrium_and_flips_sign_across_it() -> None:
    constraint = _constraint(AB, standard_delta_gibbs=0.0)
    forward = Q_(0.05, "mole / liter / second")

    at_equilibrium, evaluation = constraint.enforce(forward, {"A": Q_(0.5, "mol/L"), "B": Q_(0.5, "mol/L")})
    assert abs(at_equilibrium.magnitude) < 1.0e-12
    assert evaluation.driving_force_factor == pytest.approx(0.0, abs=1.0e-15)
    assert evaluation.rate_blocked is False
    assert evaluation.to_dict()["driving_force_factor"] == pytest.approx(0.0, abs=1.0e-15)

    below, _ = constraint.enforce(forward, {"A": Q_(0.6, "mol/L"), "B": Q_(0.4, "mol/L")})
    above, _ = constraint.enforce(forward, {"A": Q_(0.4, "mol/L"), "B": Q_(0.6, "mol/L")})
    assert below.magnitude > 0.0
    assert above.magnitude < 0.0
    # Flux-force identity for a first-order forward law: r_fwd (1 - Q/K) = k (A - B/K).
    assert below.magnitude == pytest.approx(0.05 * (1.0 - 0.4 / 0.6))
    assert above.magnitude == pytest.approx(0.05 * (1.0 - 0.6 / 0.4))

    block = _constraint(AB, standard_delta_gibbs=0.0, mode=ENFORCEMENT_BLOCK)
    blocked, blocked_evaluation = block.enforce(forward, {"A": Q_(0.4, "mol/L"), "B": Q_(0.6, "mol/L")})
    assert blocked.magnitude == 0.0
    assert blocked_evaluation.rate_blocked is True
    assert "driving_force_factor" not in blocked_evaluation.to_dict()


def test_zero_forward_rate_gives_zero_and_overflow_is_refused() -> None:
    constraint = _constraint(AB, standard_delta_gibbs=0.0)
    zero, evaluation = constraint.enforce(
        Q_(0.0, "mole / liter / second"), {"A": Q_(0.0, "mol/L"), "B": Q_(1.0, "mol/L")}
    )
    assert zero.magnitude == 0.0
    assert evaluation.driving_force_factor < -1.0e11

    overflow = _constraint(AB, standard_delta_gibbs=2.0e6)
    state = {"A": Q_(1.0, "mol/L"), "B": Q_(1.0, "mol/L")}
    with pytest.raises(ValueError, match="exceeds 700"):
        overflow.evaluate(state)
    context = KernelContext(
        state_index={"A": 0, "B": 1},
        state_units={"A": "mole / liter", "B": "mole / liter"},
        time_units="second",
        parameters=ParameterSet([]),
    )
    factor = overflow.compile_rate_factor(context)
    assert factor is not None
    with pytest.raises(ValueError, match="exceeds 700"):
        factor(np.array([1.0, 1.0]))
    # The block gate never forms the exponential, so the same energy is representable there.
    assert _constraint(AB, standard_delta_gibbs=2.0e6, mode=ENFORCEMENT_BLOCK).evaluate(state).favorable is False


def test_rate_factor_gradient_matches_richardson_and_is_zero_under_the_floor() -> None:
    participants = (
        DynamicActivityParticipant("S", "s", -1.0),
        DynamicActivityParticipant("", "h2o", -1.0, fixed_activity=1.0, activity_source=SOURCE),
        DynamicActivityParticipant("P", "p", 2.0),
    )
    constraint = _constraint(
        participants,
        standard_delta_gibbs=-3000.0,
        standard_concentration=(1.0, "millimolar"),
        minimum_activity=1.0e-6,
    )
    context = KernelContext(
        state_index={"E": 0, "S": 1, "P": 2},
        state_units={"E": "mole / liter", "S": "mole / liter", "P": "millimolar"},
        time_units="second",
        parameters=ParameterSet([]),
    )
    factor = constraint.compile_rate_factor(context)
    assert factor is not None
    assert constraint.compile_feasibility(context) is None

    def richardson(state: np.ndarray, index: int) -> float:
        step = 1.0e-3 * abs(state[index])

        def central(h: float) -> float:
            upper, lower = state.copy(), state.copy()
            upper[index] += h
            lower[index] -= h
            return (factor(upper)[0] - factor(lower)[0]) / (2.0 * h)

        return (4.0 * central(step / 2.0) - central(step)) / 3.0

    for state in (np.array([0.2, 0.004, 3.0]), np.array([1.0, 2.0e-3, 0.5]), np.array([0.0, 7.0e-4, 90.0])):
        phi, gradient = factor(state)
        assert gradient is not None
        assert gradient[0] == 0.0
        for index in (1, 2):
            assert gradient[index] == pytest.approx(richardson(state, index), rel=1.0e-6, abs=1.0e-9)
        # Cross-check the factor itself against evaluate() on the quantity state.
        evaluation = constraint.evaluate({"S": Q_(state[1], "mol/L"), "P": Q_(state[2], "mM")})
        assert phi == pytest.approx(evaluation.driving_force_factor, rel=1.0e-12)
        assert evaluation.activities["h2o"] == 1.0

    # Below the floor (S / c0 < 1e-6) the activity is constant, so the gradient is exactly zero.
    floored = np.array([0.5, 1.0e-10, 1.0])
    phi_floored, gradient_floored = factor(floored)
    assert gradient_floored is not None
    assert gradient_floored[1] == 0.0
    nudged = floored.copy()
    nudged[1] = 2.0e-10
    assert factor(nudged)[0] == phi_floored
    assert gradient_floored[2] == pytest.approx(richardson(floored, 2), rel=1.0e-6)

    block = _constraint(
        participants,
        standard_delta_gibbs=-3000.0,
        standard_concentration=(1.0, "millimolar"),
        mode=ENFORCEMENT_BLOCK,
    )
    indicator = block.compile_rate_factor(context)
    assert indicator is not None
    assert indicator(np.array([0.0, 0.004, 3.0])) == (1.0, None)
    assert indicator(np.array([0.0, 1.0e-6, 300.0])) == (0.0, None)


def test_fixed_unit_water_activity_reproduces_the_biochemical_standard_state() -> None:
    # Audit case A: cellobiose + H2O -> 2 glucose, dG0 = -10 kJ/mol, 10 mM / 20 mM, 298.15 K.
    hydrolysis = _constraint(
        (
            DynamicActivityParticipant("cellobiose", "cb", -1.0),
            DynamicActivityParticipant("", "h2o", -1.0, fixed_activity=1.0, activity_source=SOURCE),
            DynamicActivityParticipant("glucose", "glc", 2.0),
        ),
        standard_delta_gibbs=-10000.0,
    )
    evaluation = hydrolysis.evaluate({"cellobiose": Q_(0.01, "mol/L"), "glucose": Q_(0.02, "mol/L")})
    assert evaluation.delta_gibbs == pytest.approx(-17979.5, abs=0.1)
    assert evaluation.activities == {"cellobiose": 0.01, "h2o": 1.0, "glucose": 0.02}
    as_state = _constraint(
        (
            DynamicActivityParticipant("cellobiose", "cb", -1.0),
            DynamicActivityParticipant("water", "h2o", -1.0),
            DynamicActivityParticipant("glucose", "glc", 2.0),
        ),
        standard_delta_gibbs=-10000.0,
    ).evaluate({"cellobiose": Q_(0.01, "mol/L"), "water": Q_(55.5, "mol/L"), "glucose": Q_(0.02, "mol/L")})
    assert as_state.delta_gibbs - evaluation.delta_gibbs == pytest.approx(
        -GAS_CONSTANT * 298.15 * np.log(55.5), rel=1.0e-9
    )
    record = hydrolysis.to_dict()
    assert record["participants"][1]["activity_basis"] == ACTIVITY_BASIS_FIXED
    assert record["participants"][1]["activity_source"] == SOURCE
    assert any(item["name"] == "c.fixed_activity_participants" for item in record["assumptions"])


def test_standard_gibbs_temperature_dependence_matches_the_closed_form() -> None:
    enthalpy, reference = -2500.0, 298.15
    for temperature in (278.15, 298.15, 338.15):
        constraint = _constraint(
            AB,
            standard_delta_gibbs=-15000.0,
            temperature=temperature,
            standard_enthalpy=_parameter("delta_h_standard", enthalpy, "joule / mole"),
            reference_temperature=_parameter("reference_temperature", reference, "kelvin"),
        )
        expected = enthalpy - temperature * (enthalpy - (-15000.0)) / reference
        assert constraint.standard_delta_gibbs_value() == pytest.approx(expected)
        assert constraint.reference_standard_delta_gibbs_value() == -15000.0
        evaluation = constraint.evaluate({"A": Q_(1.0, "mol/L"), "B": Q_(1.0, "mol/L")})
        assert evaluation.standard_delta_gibbs == pytest.approx(expected)
        assert evaluation.delta_gibbs == pytest.approx(expected)
        assert constraint.to_dict()["temperature_dependence"] == TEMPERATURE_DEPENDENCE_CONSTANT_ENTHALPY
    untransformed = _constraint(AB, standard_delta_gibbs=-15000.0, temperature=338.15)
    assert untransformed.standard_delta_gibbs_value() == -15000.0
    assert untransformed.to_dict()["temperature_dependence"] == TEMPERATURE_DEPENDENCE_NONE


def test_tolerance_only_flags_favorable_in_driving_force_mode() -> None:
    state = {"A": Q_(1.0, "mol/L"), "B": Q_(1.0, "mol/L")}
    forward = Q_(1.0, "mole / liter / second")
    driving = _constraint(AB, standard_delta_gibbs=-500.0, tolerance=1000.0)
    rate, evaluation = driving.enforce(forward, state)
    assert evaluation.favorable is False
    assert rate.magnitude == pytest.approx(-np.expm1(-500.0 / (GAS_CONSTANT * 298.15)))
    # Legacy block mode keeps its documented dead zone: the exergonic rate is blocked.
    block = _constraint(AB, standard_delta_gibbs=-500.0, tolerance=1000.0, mode=ENFORCEMENT_BLOCK)
    blocked, blocked_evaluation = block.enforce(forward, state)
    assert blocked.magnitude == 0.0 and blocked_evaluation.rate_blocked is True
    assert "dead zone" in block.to_dict()["assumptions"][0]["known_limitations"]


@pytest.mark.parametrize(
    ("build", "message"),
    [
        (
            lambda: _constraint(AB, standard_delta_gibbs=0.0, standard_enthalpy=_parameter("h", -1.0, "joule / mole")),
            "both standard_enthalpy and reference_temperature",
        ),
        (
            lambda: _constraint(AB, standard_delta_gibbs=0.0, mode="haldane"),
            "enforcement_mode must be one of",
        ),
        (
            lambda: _constraint(
                (AB[0], DynamicActivityParticipant("B", "b", 1.0, fixed_activity=1.0, activity_source=SOURCE)),
                standard_delta_gibbs=0.0,
            ),
            "must not bind a state name",
        ),
        (
            lambda: _constraint(
                (AB[0], DynamicActivityParticipant("", "b", 1.0, fixed_activity=0.0, activity_source=SOURCE)),
                standard_delta_gibbs=0.0,
            ),
            "finite positive activity",
        ),
        (
            lambda: _constraint(
                (AB[0], DynamicActivityParticipant("B", "b", 1.0, overridden_state_name="B")),
                standard_delta_gibbs=0.0,
            ),
            "only when its activity is fixed",
        ),
        (
            lambda: _constraint(
                (AB[0], DynamicActivityParticipant("", "b", 1.0, fixed_activity=1.0, activity_source=SOURCE, overridden_state_name="  ")),
                standard_delta_gibbs=0.0,
            ),
            "nonblank state name or None",
        ),
        (
            lambda: _constraint(
                (
                    DynamicActivityParticipant("", "a", -1.0, fixed_activity=1.0, activity_source=SOURCE),
                    DynamicActivityParticipant("", "b", 1.0, fixed_activity=1.0, activity_source=SOURCE),
                ),
                standard_delta_gibbs=0.0,
            ),
            "at least one trajectory participant",
        ),
    ],
)
def test_constraint_refusals(build: Any, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        build().validate()


def test_fixed_participant_without_source_is_a_provenance_error() -> None:
    from fungal_model.core.provenance import ProvenanceError

    with pytest.raises(ProvenanceError, match="activity_source"):
        _constraint(
            (AB[0], DynamicActivityParticipant("", "b", 1.0, fixed_activity=1.0)),
            standard_delta_gibbs=0.0,
        ).validate()


# --- detailed-balance equilibrium ------------------------------------------


def _species(name: str, formula: str, gibbs: float) -> MacrochemicalSpecies:
    return MacrochemicalSpecies(
        name,
        ElementalComposition.from_formula(formula, source=SOURCE),
        0,
        SOURCE,
        formation_gibbs=Parameter(name=name, symbol=name, value=gibbs, units="J/mol", source=SOURCE, uncertainty=None, confidence_level="testing", notes=""),
    )


def test_trace_pool_is_conserved_by_the_equilibrium_solver() -> None:
    balance = MacrochemicalBalance(
        "pools",
        (_species("A", "C2H4", 0.0), _species("B", "C2H4", -3000.0), _species("X", "C3H6", 0.0), _species("Y", "C3H6", 2000.0)),
        SOURCE,
        thermodynamic_conditions=SOURCE,
    )
    scale = Parameter(name="k", symbol="k", value=0.3, units="mol/L/s", source=SOURCE, uncertainty=None, confidence_level="testing", notes="")
    network = DetailedBalanceNetwork(
        balance=balance,
        reactions=(
            DetailedBalanceReaction("ab", {"A": 1}, {"B": 1}, scale, SOURCE),
            DetailedBalanceReaction("xy", {"X": 1}, {"Y": 1}, scale, SOURCE),
        ),
        temperature=_parameter("T", 298.15, "K"),
        gas_constant=_parameter("R", GAS_CONSTANT, "J/mol/K"),
        standard_concentration=_parameter("c0", 1.0, "mol/L"),
    )
    for trace in (1.0e-3, 1.0e-9, 1.0e-12):
        equilibrium = network.equilibrium(
            {"A": Q_(0.9, "mol/L"), "B": Q_(0.1, "mol/L"), "X": Q_(0.5 * trace, "mol/L"), "Y": Q_(0.5 * trace, "mol/L")}
        )
        x = equilibrium["concentrations"]["X"].magnitude
        y = equilibrium["concentrations"]["Y"].magnitude
        assert (x + y - trace) / trace == pytest.approx(0.0, abs=1.0e-8)
        assert y / x == pytest.approx(np.exp(-2000.0 / (GAS_CONSTANT * 298.15)), rel=1.0e-8)
        assert equilibrium["conservation_law_count"] == 2


def _single_reaction_network(members: tuple[MacrochemicalSpecies, ...], reactants: dict[str, int],
                             products: dict[str, int]) -> DetailedBalanceNetwork:
    balance = MacrochemicalBalance("signed invariants", members, SOURCE, thermodynamic_conditions=SOURCE)
    scale = Parameter(name="k", symbol="k", value=0.3, units="mol/L/s", source=SOURCE, uncertainty=None, confidence_level="testing", notes="")
    return DetailedBalanceNetwork(
        balance=balance,
        reactions=(DetailedBalanceReaction("r", reactants, products, scale, SOURCE),),
        temperature=_parameter("T", 298.15, "K"),
        gas_constant=_parameter("R", GAS_CONSTANT, "J/mol/K"),
        standard_concentration=_parameter("c0", 1.0, "mol/L"),
    )


@pytest.mark.parametrize("b0, c0", [(0.1, 0.1), (1.0e-3, 1.0e-3), (0.1, 0.2)])
def test_equilibrium_with_zero_signed_invariant_total_dissociation(b0: float, c0: float) -> None:
    """A <-> B + C conserves B - C, whose total is zero whenever B0 = C0.

    Review regression: scaling that residual by the signed total divided by
    zero and made a valid interior start raise. The scale must be positive for
    every invariant row, not only for nonnegative pool rows.
    """
    network = _single_reaction_network(
        (_species("A", "C4H8", 0.0), _species("B", "C2H4", -1000.0), _species("C", "C2H4", 500.0)), {"A": 1}, {"B": 1, "C": 1}
    )
    equilibrium = network.equilibrium({"A": Q_(1.0, "mol/L"), "B": Q_(b0, "mol/L"), "C": Q_(c0, "mol/L")})
    a, b, c = (equilibrium["concentrations"][name].magnitude for name in "ABC")
    assert b * c / a == pytest.approx(np.exp(500.0 / (GAS_CONSTANT * 298.15)), rel=1.0e-8)
    assert a + c == pytest.approx(1.0 + c0, rel=1.0e-10)
    assert b - c == pytest.approx(b0 - c0, abs=1.0e-10)
    assert equilibrium["conservation_law_count"] == 2
    assert equilibrium["maximum_scaled_residual"] <= 1.0e-10


@pytest.mark.parametrize("start", [(0.7, 0.3, 0.2, 0.2), (0.5, 0.5, 0.1, 0.1), (0.5, 0.5, 0.3, 0.3), (1.0, 1.0, 1.0e-3, 1.0e-3)])
def test_equilibrium_with_zero_signed_invariant_total_exchange(start: tuple[float, float, float, float]) -> None:
    """A + B <-> C + D conserves C - D, whose total is zero whenever C0 = D0."""
    network = _single_reaction_network(
        (_species("A", "CH2", 0.0), _species("B", "CH2", 0.0), _species("C", "CH2", -1000.0), _species("D", "CH2", 500.0)),
        {"A": 1, "B": 1},
        {"C": 1, "D": 1},
    )
    equilibrium = network.equilibrium({name: Q_(value, "mol/L") for name, value in zip("ABCD", start, strict=True)})
    a, b, c, d = (equilibrium["concentrations"][name].magnitude for name in "ABCD")
    assert c * d / (a * b) == pytest.approx(np.exp(500.0 / (GAS_CONSTANT * 298.15)), rel=1.0e-8)
    assert a + d == pytest.approx(start[0] + start[3], rel=1.0e-10)
    assert b + d == pytest.approx(start[1] + start[3], rel=1.0e-10)
    assert c - d == pytest.approx(start[2] - start[3], abs=1.0e-10)
    assert equilibrium["conservation_law_count"] == 3
    assert equilibrium["maximum_scaled_residual"] <= 1.0e-10
