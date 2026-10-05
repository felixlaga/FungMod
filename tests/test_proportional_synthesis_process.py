"""Generic producer-proportional synthesis: unit-aware law, compiled kernel, factory and config path.

The cases are deliberately non-biological (a dissolved catalyst pool forming a
product in millimolar units) and biological (an activity pool in assay units
produced by biomass), so the law is exercised on materially different chemistry
and units without any organism- or enzyme-specific branch.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from fungal_model.core.kernels import KernelContext
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_
from fungal_model.processes import (
    ModelBuilder,
    ProcessBuildContext,
    ProcessLibrary,
    ProcessRegistry,
    ProportionalSynthesisFactory,
    ProportionalSynthesisProcess,
)
from fungal_model.io import ProcessConfig
from fungal_model.solvers import ProcessODESolver, RunRequest
from fungal_model.workflows import run_configured_model

ROOT = Path(__file__).resolve().parents[1]
TOY_CONFIG = ROOT / "data" / "model_configs" / "toy_proportional_synthesis_dissolved.yml"
SOURCE = "Artificial test values; no organism or enzyme claim."


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


def _induced_process(**overrides):
    fields = {
        "name": "induced synthesis",
        "producer_state": "P",
        "producer_units": "millimolar",
        "product_state": "Q",
        "product_units": "millimolar",
        "rate_units": "millimolar / second",
        "specific_rate_symbol": "q",
        "inducer_state": "I",
        "inducer_units": "millimolar",
        "induction_half_saturation_symbol": "K_I",
        "source": SOURCE,
    }
    fields.update(overrides)
    return ProportionalSynthesisProcess(**fields)


def _state(**values):
    return {name: Q_(value, "millimolar") for name, value in values.items()}


def test_induced_law_matches_closed_form_and_only_forms_the_product() -> None:
    process = _induced_process()
    parameters = ParameterSet([_parameter("q", 0.5, "1 / second"), _parameter("K_I", 2.0, "millimolar")])
    rate = process.rate(_state(P=4.0, I=2.0, Q=0.0), Q_(0.0, "second"), parameters)
    assert rate.to("millimolar / second").magnitude == pytest.approx(0.5 * 4.0 * 2.0 / (2.0 + 2.0))
    contributions = process.contributions(rate)
    assert set(contributions) == {"Q"}
    assert contributions["Q"].to("millimolar / second").magnitude == pytest.approx(rate.magnitude)
    assert process.rate(_state(P=4.0, I=0.0, Q=0.0), Q_(0.0, "second"), parameters).magnitude == 0.0
    assert process.rate(_state(P=0.0, I=2.0, Q=0.0), Q_(0.0, "second"), parameters).magnitude == 0.0


def test_constitutive_law_omits_induction_and_rejects_partial_inducer_fields() -> None:
    process = _induced_process(inducer_state=None, inducer_units=None, induction_half_saturation_symbol=None)
    assert not process.induced
    parameters = ParameterSet([_parameter("q", 0.25, "1 / second")])
    rate = process.rate(_state(P=2.0, Q=0.0), Q_(0.0, "second"), parameters)
    assert rate.to("millimolar / second").magnitude == pytest.approx(0.5)
    with pytest.raises(ValueError, match="together"):
        _induced_process(induction_half_saturation_symbol=None)
    with pytest.raises(ValueError, match="distinct"):
        _induced_process(product_state="P")


def test_unit_aware_law_rejects_negative_states_and_invalid_constants() -> None:
    process = _induced_process()
    good = ParameterSet([_parameter("q", 0.5, "1 / second"), _parameter("K_I", 2.0, "millimolar")])
    with pytest.raises(ValueError, match="must be non-negative"):
        process.rate(_state(P=-1.0, I=1.0, Q=0.0), Q_(0.0, "second"), good)
    with pytest.raises(ValueError, match="must be non-negative"):
        process.rate(_state(P=1.0, I=-1.0, Q=0.0), Q_(0.0, "second"), good)
    bad_half_saturation = ParameterSet([_parameter("q", 0.5, "1 / second"), _parameter("K_I", 0.0, "millimolar")])
    with pytest.raises(ValueError, match="must be positive"):
        process.rate(_state(P=1.0, I=1.0, Q=0.0), Q_(0.0, "second"), bad_half_saturation)
    negative_rate = ParameterSet([_parameter("q", -0.5, "1 / second"), _parameter("K_I", 2.0, "millimolar")])
    with pytest.raises(ValueError, match="must be non-negative"):
        process.rate(_state(P=1.0, I=1.0, Q=0.0), Q_(0.0, "second"), negative_rate)


def test_compiled_kernel_matches_unit_aware_law_across_mixed_units() -> None:
    """Biomass in g/L producing an assay activity in FPU/L with hour-based constants."""

    process = ProportionalSynthesisProcess(
        name="activity production",
        producer_state="X",
        producer_units="gram / liter",
        product_state="F",
        product_units="filter_paper_unit / liter",
        rate_units="filter_paper_unit / liter / hour",
        specific_rate_symbol="qF",
        inducer_state="S",
        inducer_units="gram / liter",
        induction_half_saturation_symbol="K_ind",
        source=SOURCE,
    )
    parameters = ParameterSet(
        [_parameter("qF", 6.0, "filter_paper_unit / gram / hour"), _parameter("K_ind", 0.5, "gram / liter")]
    )
    context = KernelContext(
        state_index={"S": 0, "X": 1, "F": 2},
        state_units={"S": "milligram / milliliter", "X": "kilogram / meter ** 3", "F": "filter_paper_unit / milliliter"},
        time_units="minute",
        parameters=parameters,
    )
    kernel = process.compile_rate(context)
    assert kernel is not None
    for state in (np.array([2.0, 1.5, 0.0]), np.array([0.2, 0.3, 4.0]), np.array([0.0, 1.0, 1.0])):
        expected = process.rate(
            {"S": Q_(state[0], "milligram / milliliter"), "X": Q_(state[1], "kilogram / meter ** 3"), "F": Q_(state[2], "filter_paper_unit / milliliter")},
            Q_(0.0, "minute"),
            parameters,
        ).to("filter_paper_unit / liter / hour").magnitude
        assert kernel(0.0, state) == pytest.approx(expected, rel=1e-12)
    with pytest.raises(ValueError, match="must be non-negative"):
        kernel(0.0, np.array([1.0, -1.0, 0.0]))
    with pytest.raises(ValueError, match="must be positive"):
        process.compile_rate(
            KernelContext(
                state_index=context.state_index,
                state_units=context.state_units,
                time_units="minute",
                parameters=ParameterSet([_parameter("qF", 6.0, "filter_paper_unit / gram / hour"), _parameter("K_ind", 0.0, "gram / liter")]),
            )
        )


def test_compiled_solve_matches_analytic_solution_with_constant_producer_and_inducer() -> None:
    process = _induced_process()
    parameters = ParameterSet([_parameter("q", 0.5, "1 / second"), _parameter("K_I", 2.0, "millimolar")])
    model = ModelBuilder(
        process_library=ProcessRegistry([process]),
        requested_processes=("proportional_synthesis",),
        parameters=parameters,
        allow_unsourced_for_testing=True,
    ).assemble()
    times = np.linspace(0.0, 10.0, 11)
    result = ProcessODESolver(model).run(
        RunRequest(
            initial_state={"P": Q_(4.0, "millimolar"), "I": Q_(2.0, "millimolar"), "Q": Q_(0.0, "millimolar")},
            t_span=(Q_(0.0, "second"), Q_(10.0, "second")),
            t_eval=Q_(times, "second"),
        )
    )
    expected = 0.5 * 4.0 * 2.0 / (2.0 + 2.0) * times
    np.testing.assert_allclose(result.states["Q"].to("millimolar").magnitude, expected, rtol=1e-7, atol=1e-10)
    np.testing.assert_allclose(result.states["P"].to("millimolar").magnitude, 4.0)
    np.testing.assert_allclose(result.states["I"].to("millimolar").magnitude, 2.0)
    assert result.solver_metadata["kernel"]["process_kernels"] == {"induced synthesis": "numeric"}


def test_factory_builds_both_forms_and_fails_closed_on_partial_induction() -> None:
    factory = ProportionalSynthesisFactory()
    context = ProcessBuildContext(state_units={"P": "millimolar", "I": "millimolar", "Q": "millimolar"})
    induced = ProcessConfig(
        id="induced",
        process_type="proportional_synthesis",
        states={"producer": "P", "inducer": "I", "product": "Q"},
        parameters={"specific_rate": "q", "induction_half_saturation": "K_I", "rate_units": "millimolar / second"},
    )
    assert factory.can_build(context, induced).can_build
    built = factory.build(context, induced)
    assert isinstance(built, ProportionalSynthesisProcess) and built.induced
    constitutive = ProcessConfig(
        id="constitutive",
        process_type="proportional_synthesis",
        states={"producer": "P", "product": "Q"},
        parameters={"specific_rate": "q", "rate_units": "millimolar / second"},
    )
    assert not factory.build(context, constitutive).induced
    partial = ProcessConfig(
        id="partial",
        process_type="proportional_synthesis",
        states={"producer": "P", "inducer": "I", "product": "Q"},
        parameters={"specific_rate": "q", "rate_units": "millimolar / second"},
    )
    decision = factory.can_build(context, partial)
    assert not decision.can_build
    assert "states.inducer_requires_parameters.induction_half_saturation" in decision.incompatible_entities
    assert "proportional_synthesis" in ProcessLibrary.default_foundation().factory_types()


def test_toy_config_runs_through_the_configured_workflow(tmp_path: Path) -> None:
    result = run_configured_model(TOY_CONFIG, output_dir=tmp_path / "bundle")
    assert all(item["passed"] for item in result.validation_report())
    kernels = result.solver_metadata["kernel"]["process_kernels"]
    assert kernels == {"induced_product_formation": "numeric", "inducer_loss": "numeric"}
    times = np.asarray(result.time.to("second").magnitude)
    inducer = np.asarray(result.states["inducer_concentration"].to("millimolar").magnitude)
    np.testing.assert_allclose(inducer, np.exp(-0.05 * times), rtol=1e-6, atol=1e-9)
    product = np.asarray(result.states["product_concentration"].to("millimolar").magnitude)
    # Closed form: q P int_0^t I/(K+I) dt with I = exp(-k t), P constant.
    k, kind, q, p = 0.05, 0.5, 0.02, 2.0
    expected = q * p / k * np.log((kind + 1.0) / (kind + np.exp(-k * times)))
    np.testing.assert_allclose(product, expected, rtol=1e-6, atol=1e-8)
