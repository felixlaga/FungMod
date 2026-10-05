"""Diprotic pH-dependent Michaelis-Menten process (SABIO-RK kinetic-law type 24 form).

The law is checked against a verbatim transcription of the deposited formula
and exercised on artificial values; the sourced BGL1A case lives in
``test_bgl1a_ph_response_case.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from scipy.integrate import solve_ivp

from fungal_model.core.kernels import KernelContext
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_
from fungal_model.entities import Environment
from fungal_model.io import ProcessConfig
from fungal_model.kinetics import (
    EnvironmentalValidityWarning,
    diprotic_ionization_factor,
    ph_dependent_michaelis_constant,
    ph_dependent_turnover,
)
from fungal_model.processes import (
    ModelBuilder,
    PHIonizationMichaelisMentenFactory,
    PHIonizationMichaelisMentenProcess,
    ProcessBuildContext,
    ProcessLibrary,
    ProcessRegistry,
)
from fungal_model.solvers import ProcessODESolver, RunRequest
from fungal_model.workflows import run_configured_model

ROOT = Path(__file__).resolve().parents[1]
TOY_CONFIG = ROOT / "data" / "model_configs" / "toy_ph_ionization_dissolved.yml"
SOURCE = "Artificial ionization test values; no enzyme claim."
CONSTANTS = {"k0": 1.5, "Km0": 2.0, "pKe1": 4.2, "pKe2": 7.9, "pKes1": 3.8, "pKes2": 7.4}


def deposited_law(E: float, S: float, pH: float, k0: float, Km0: float, pKe1: float, pKe2: float, pKes1: float, pKes2: float) -> float:
    """Verbatim transcription of the SABIO-RK Michaelis-Menten (pH-dependent) formula string."""

    return (
        E
        * ((k0) / ((10 ** (pKes1 - pH) + 1) * (10 ** (pH - pKes2) + 1)))
        * S
        / (
            ((k0) / ((10 ** (pKes1 - pH) + 1) * (10 ** (pH - pKes2) + 1)))
            / (((k0) / (Km0)) / ((10 ** (pKe1 - pH) + 1) * (10 ** (pH - pKe2) + 1)))
            + S
        )
    )


def _parameter(symbol: str, value: float, units: str) -> Parameter:
    return Parameter(
        name=f"artificial {symbol}",
        symbol=symbol,
        value=value,
        units=units,
        uncertainty=None,
        source=SOURCE,
        confidence_level="testing",
        notes=SOURCE,
    )


def _parameters(**overrides: float) -> ParameterSet:
    values = {**CONSTANTS, **overrides}
    return ParameterSet(
        [
            _parameter("k0", values["k0"], "1 / second"),
            _parameter("Km0", values["Km0"], "millimolar"),
            _parameter("pKe1", values["pKe1"], "dimensionless"),
            _parameter("pKe2", values["pKe2"], "dimensionless"),
            _parameter("pKes1", values["pKes1"], "dimensionless"),
            _parameter("pKes2", values["pKes2"], "dimensionless"),
            _parameter("pH_lo", 4.0, "dimensionless"),
            _parameter("pH_hi", 8.0, "dimensionless"),
        ]
    )


def _process(**overrides) -> PHIonizationMichaelisMentenProcess:
    fields = {
        "name": "conversion",
        "substrate_state": "S",
        "enzyme_state": "E",
        "product_state": "P",
        "substrate_units": "millimolar",
        "enzyme_units": "millimolar",
        "rate_units": "millimolar / second",
        "turnover_symbol": "k0",
        "michaelis_constant_symbol": "Km0",
        "free_enzyme_lower_pk_symbol": "pKe1",
        "free_enzyme_upper_pk_symbol": "pKe2",
        "complex_lower_pk_symbol": "pKes1",
        "complex_upper_pk_symbol": "pKes2",
        "minimum_ph_symbol": "pH_lo",
        "maximum_ph_symbol": "pH_hi",
        "source": SOURCE,
    }
    fields.update(overrides)
    return PHIonizationMichaelisMentenProcess(**fields)


def _environment(ph: float) -> Environment:
    return Environment(name="assay", temperature=Q_(303.15, "kelvin"), ph=Q_(ph, "dimensionless"), source="test")


def _state(substrate: float, enzyme: float, product: float = 0.0):
    return {"S": Q_(substrate, "millimolar"), "E": Q_(enzyme, "millimolar"), "P": Q_(product, "millimolar")}


@pytest.mark.parametrize("ph", [4.0, 5.0, 6.1, 7.5, 8.0])
def test_rate_and_effective_constants_match_the_deposited_formula(ph: float) -> None:
    process = _process()
    parameters = _parameters()
    environment = _environment(ph)
    rate = process.rate(_state(3.0, 0.02), Q_(0.0, "second"), parameters, environment)
    assert rate.to("millimolar / second").magnitude == pytest.approx(deposited_law(0.02, 3.0, ph, **CONSTANTS), rel=1e-12)
    constants = process.effective_constants(parameters=parameters, environment=environment)
    complex_factor = (10 ** (CONSTANTS["pKes1"] - ph) + 1) * (10 ** (ph - CONSTANTS["pKes2"]) + 1)
    free_factor = (10 ** (CONSTANTS["pKe1"] - ph) + 1) * (10 ** (ph - CONSTANTS["pKe2"]) + 1)
    assert constants["ph"] == pytest.approx(ph)
    assert constants["complex_ionization_factor"] == pytest.approx(complex_factor)
    assert constants["free_enzyme_ionization_factor"] == pytest.approx(free_factor)
    assert constants["turnover_at_ph"].to("1 / second").magnitude == pytest.approx(CONSTANTS["k0"] / complex_factor)
    assert constants["michaelis_constant_at_ph"].to("millimolar").magnitude == pytest.approx(
        CONSTANTS["Km0"] * free_factor / complex_factor
    )


def test_kinetics_helpers_expose_the_ionization_factors_and_require_ordered_pkas() -> None:
    factor = diprotic_ionization_factor(ph=Q_(6.0, "dimensionless"), lower_pk=Q_(4.0, "dimensionless"), upper_pk=Q_(8.0, "dimensionless"))
    assert factor.magnitude == pytest.approx((10 ** (4.0 - 6.0) + 1) * (10 ** (6.0 - 8.0) + 1))
    turnover = ph_dependent_turnover(
        turnover=Q_(2.0, "1 / second"),
        ph=Q_(6.0, "dimensionless"),
        complex_lower_pk=Q_(4.0, "dimensionless"),
        complex_upper_pk=Q_(8.0, "dimensionless"),
    )
    assert turnover.to("1 / second").magnitude == pytest.approx(2.0 / factor.magnitude)
    km = ph_dependent_michaelis_constant(
        michaelis_constant=Q_(3.0, "millimolar"),
        ph=Q_(6.0, "dimensionless"),
        free_enzyme_lower_pk=Q_(5.0, "dimensionless"),
        free_enzyme_upper_pk=Q_(7.0, "dimensionless"),
        complex_lower_pk=Q_(4.0, "dimensionless"),
        complex_upper_pk=Q_(8.0, "dimensionless"),
    )
    free_factor = (10 ** (5.0 - 6.0) + 1) * (10 ** (6.0 - 7.0) + 1)
    assert km.to("millimolar").magnitude == pytest.approx(3.0 * free_factor / factor.magnitude)
    with pytest.raises(ValueError, match="lower_pk < upper_pk"):
        diprotic_ionization_factor(ph=Q_(6.0, "dimensionless"), lower_pk=Q_(8.0, "dimensionless"), upper_pk=Q_(4.0, "dimensionless"))
    with pytest.raises(ValueError, match="must be positive"):
        ph_dependent_michaelis_constant(
            michaelis_constant=Q_(0.0, "millimolar"),
            ph=Q_(6.0, "dimensionless"),
            free_enzyme_lower_pk=Q_(5.0, "dimensionless"),
            free_enzyme_upper_pk=Q_(7.0, "dimensionless"),
            complex_lower_pk=Q_(4.0, "dimensionless"),
            complex_upper_pk=Q_(8.0, "dimensionless"),
        )


def test_environment_ph_is_required_and_invalid_inputs_fail_closed() -> None:
    process = _process()
    parameters = _parameters()
    with pytest.raises(ValueError, match="environment entity with pH"):
        process.rate(_state(1.0, 0.01), Q_(0.0, "second"), parameters, None)
    with pytest.raises(ValueError, match="does not define pH"):
        process.rate(_state(1.0, 0.01), Q_(0.0, "second"), parameters, Environment(name="no pH", temperature=Q_(300.0, "kelvin"), source="t"))
    with pytest.raises(ValueError, match="lower_pk < upper_pk"):
        process.rate(_state(1.0, 0.01), Q_(0.0, "second"), _parameters(pKes1=7.9, pKes2=3.8), _environment(6.0))
    with pytest.raises(ValueError, match="must be non-negative"):
        process.rate(_state(-1.0, 0.01), Q_(0.0, "second"), parameters, _environment(6.0))
    with pytest.raises(ValueError, match="must be non-negative"):
        process.rate(_state(1.0, -0.01), Q_(0.0, "second"), parameters, _environment(6.0))
    with pytest.raises(ValueError, match="together"):
        _process(maximum_ph_symbol=None)
    with pytest.raises(ValueError, match="distinct"):
        _process(enzyme_state="S")


def test_ph_outside_the_measured_range_warns_but_still_evaluates_the_law() -> None:
    process = _process()
    parameters = _parameters()
    with pytest.warns(EnvironmentalValidityWarning, match="above pH 8.0"):
        rate = process.rate(_state(3.0, 0.02), Q_(0.0, "second"), parameters, _environment(9.0))
    assert rate.to("millimolar / second").magnitude == pytest.approx(deposited_law(0.02, 3.0, 9.0, **CONSTANTS), rel=1e-12)


def test_compiled_kernel_matches_the_unit_aware_law_across_mixed_units() -> None:
    process = _process(product_coefficients={"P": 2.0})
    parameters = _parameters()
    environment = _environment(5.3)
    context = KernelContext(
        state_index={"S": 0, "E": 1, "P": 2},
        state_units={"S": "molar", "E": "micromolar", "P": "millimolar"},
        time_units="hour",
        parameters=parameters,
        environment=environment,
    )
    kernel = process.compile_rate(context)
    assert kernel is not None
    for substrate, enzyme in ((0.5, 1.0), (3.0, 0.2), (0.0, 1.0)):
        expected = process.rate(_state(substrate * 1000.0, enzyme * 1e-3), Q_(0.0, "second"), parameters, environment)
        assert kernel(0.0, np.array([substrate, enzyme, 0.0])) == pytest.approx(
            expected.to("millimolar / second").magnitude, rel=1e-12
        )
    with pytest.raises(ValueError, match="must be non-negative"):
        kernel(0.0, np.array([1.0, -1.0, 0.0]))
    contributions = process.contributions(Q_(0.3, "millimolar / second"))
    assert contributions["S"].magnitude == pytest.approx(-0.3)
    assert contributions["P"].magnitude == pytest.approx(0.6)
    assert set(contributions) == {"S", "P"}


def test_compiled_solve_matches_an_independent_integration_of_the_deposited_law() -> None:
    process = _process()
    parameters = _parameters()
    environment = _environment(6.5)
    model = ModelBuilder(
        process_library=ProcessRegistry([process]),
        requested_processes=("ph_ionization_michaelis_menten",),
        parameters=parameters,
        environment=environment,
        allow_unsourced_for_testing=True,
    ).assemble()
    times = np.linspace(0.0, 400.0, 21)
    result = ProcessODESolver(model).run(
        RunRequest(
            initial_state=_state(4.0, 0.01),
            t_span=(Q_(0.0, "second"), Q_(400.0, "second")),
            t_eval=Q_(times, "second"),
        )
    )
    reference = solve_ivp(
        lambda t, y: [-deposited_law(0.01, y[0], 6.5, **CONSTANTS), deposited_law(0.01, y[0], 6.5, **CONSTANTS)],
        (0.0, 400.0),
        [4.0, 0.0],
        t_eval=times,
        rtol=1e-10,
        atol=1e-12,
    )
    np.testing.assert_allclose(result.states["S"].to("millimolar").magnitude, reference.y[0], rtol=1e-5, atol=1e-7)
    np.testing.assert_allclose(result.states["P"].to("millimolar").magnitude, reference.y[1], rtol=1e-5, atol=1e-7)
    np.testing.assert_allclose(result.states["E"].to("millimolar").magnitude, 0.01)
    assert result.solver_metadata["kernel"]["process_kernels"] == {"conversion": "numeric"}


def test_factory_builds_the_process_and_fails_closed_on_partial_inputs() -> None:
    factory = PHIonizationMichaelisMentenFactory()
    context = ProcessBuildContext(state_units={"S": "millimolar", "E": "millimolar", "P": "millimolar"}, source=SOURCE)
    parameters = {
        "turnover": "k0",
        "michaelis_constant": "Km0",
        "free_enzyme_lower_pk": "pKe1",
        "free_enzyme_upper_pk": "pKe2",
        "complex_lower_pk": "pKes1",
        "complex_upper_pk": "pKes2",
        "rate_units": "millimolar / second",
    }
    complete = ProcessConfig(
        id="conversion",
        process_type="ph_ionization_michaelis_menten",
        states={"substrate": "S", "enzyme": "E", "product": "P"},
        parameters=parameters,
    )
    assert factory.can_build(context, complete).can_build
    built = factory.build(context, complete)
    assert isinstance(built, PHIonizationMichaelisMentenProcess)
    assert built.minimum_ph_symbol is None
    missing = ProcessConfig(
        id="missing",
        process_type="ph_ionization_michaelis_menten",
        states={"substrate": "S"},
        parameters={"turnover": "k0", "rate_units": "millimolar / second"},
    )
    decision = factory.can_build(context, missing)
    assert not decision.can_build
    assert {"states.enzyme", "parameters.michaelis_constant", "parameters.complex_upper_pk"} <= set(decision.missing_fields)
    partial = ProcessConfig(
        id="partial",
        process_type="ph_ionization_michaelis_menten",
        states={"substrate": "S", "enzyme": "E"},
        parameters={**parameters, "minimum_ph": "pH_lo"},
    )
    decision = factory.can_build(context, partial)
    assert not decision.can_build
    assert "parameters.minimum_ph_and_maximum_ph_must_be_given_together" in decision.incompatible_entities
    assert "ph_ionization_michaelis_menten" in ProcessLibrary.default_foundation().factory_types()


def test_toy_config_runs_through_the_configured_workflow(tmp_path: Path) -> None:
    result = run_configured_model(TOY_CONFIG, output_dir=tmp_path / "bundle")
    assert all(item["passed"] for item in result.validation_report())
    assert result.solver_metadata["kernel"]["process_kernels"] == {"ph_dependent_conversion": "numeric"}
    initial_rate = result.process_rates["ph_dependent_conversion"].to("millimolar / second").magnitude[0]
    assert initial_rate == pytest.approx(deposited_law(0.01, 2.0, 7.0, 0.5, 1.0, 4.0, 8.0, 4.5, 7.5), rel=1e-9)
    substrate = np.asarray(result.states["substrate_concentration"].to("millimolar").magnitude)
    product = np.asarray(result.states["product_concentration"].to("millimolar").magnitude)
    np.testing.assert_allclose(substrate + product, 2.0, rtol=1e-9)
    assert substrate[-1] < substrate[0]
    metadata = json.loads((tmp_path / "bundle" / "configured_metadata.json").read_text(encoding="utf-8"))
    laws = metadata["configured_process_laws"]
    assert laws[0]["type"] == "ph_ionization_michaelis_menten"
    assert laws[0]["environment_value"] == "ph"
    assert laws[0]["maturity"] == "configured_ph_response_law"
    assumptions = json.loads((tmp_path / "bundle" / "assumptions.json").read_text(encoding="utf-8"))
    assert any(item["name"] == "diprotic ionization pH dependence of Michaelis-Menten constants" for item in assumptions)
