from __future__ import annotations

import numpy as np
import pytest

from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.provenance import ProvenanceError
from fungal_model.core.units import UnitError
from fungal_model.uncertainty import (
    LocalSensitivitySpec,
    ParameterUncertaintySpec,
    local_sensitivity,
    run_monte_carlo,
)


def parameter(
    *,
    name: str,
    symbol: str,
    value,
    units: str,
) -> Parameter:
    return Parameter(
        name=name,
        symbol=symbol,
        value=value,
        units=units,
        uncertainty=0.0 if value is not None else None,
        source="Artificial Stage 11 uncertainty/sensitivity benchmark value; no physical claim.",
        confidence_level="testing",
        notes="Used only for uncertainty utility tests.",
        measurement_method="defined benchmark value",
    )


def base_parameters(k_value: float = 2.0) -> ParameterSet:
    return ParameterSet(
        [
            parameter(name="test slope", symbol="k", value=k_value, units="1 / second"),
            parameter(name="test duration", symbol="t", value=3.0, units="second"),
        ]
    )


def scalar_prediction(parameters: ParameterSet):
    return {
        "y": parameters.require_quantity("k", "1 / second")
        * parameters.require_quantity("t", "second")
    }


def scalar_quantity(parameters: ParameterSet):
    return scalar_prediction(parameters)["y"]


def test_monte_carlo_uniform_uncertainty_is_reproducible() -> None:
    spec = ParameterUncertaintySpec(
        symbol="k",
        distribution="uniform",
        lower_bound=parameter(name="lower k", symbol="k_low", value=1.0, units="1 / second"),
        upper_bound=parameter(name="upper k", symbol="k_high", value=3.0, units="1 / second"),
        source="Artificial Stage 11 uniform uncertainty test.",
    )

    first = run_monte_carlo(
        base_parameters=base_parameters(),
        uncertainty_specs=[spec],
        predict=scalar_prediction,
        n_samples=32,
        random_seed=123,
    )
    second = run_monte_carlo(
        base_parameters=base_parameters(),
        uncertainty_specs=[spec],
        predict=scalar_prediction,
        n_samples=32,
        random_seed=123,
    )

    assert first.n_successful == 32
    assert first.failures == ()
    assert np.allclose(first.sampled_parameter_values["k"], second.sampled_parameter_values["k"])
    assert first.summary["y"]["q_mc_median"].units == first.predictions["y"].units


def test_wider_input_uncertainty_produces_wider_output_interval() -> None:
    narrow = ParameterUncertaintySpec(
        symbol="k",
        distribution="normal",
        standard_deviation=parameter(name="narrow k std", symbol="sigma_k_narrow", value=0.01, units="1 / second"),
        source="Artificial Stage 11 narrow normal uncertainty test.",
    )
    wide = ParameterUncertaintySpec(
        symbol="k",
        distribution="normal",
        standard_deviation=parameter(name="wide k std", symbol="sigma_k_wide", value=1.0, units="1 / second"),
        source="Artificial Stage 11 wide normal uncertainty test.",
    )

    narrow_result = run_monte_carlo(
        base_parameters=base_parameters(),
        uncertainty_specs=[narrow],
        predict=scalar_prediction,
        n_samples=512,
        random_seed=1,
    )
    wide_result = run_monte_carlo(
        base_parameters=base_parameters(),
        uncertainty_specs=[wide],
        predict=scalar_prediction,
        n_samples=512,
        random_seed=1,
    )

    narrow_width = (
        narrow_result.summary["y"]["q_mc_upper"]
        - narrow_result.summary["y"]["q_mc_lower"]
    ).to("dimensionless").magnitude
    wide_width = (
        wide_result.summary["y"]["q_mc_upper"]
        - wide_result.summary["y"]["q_mc_lower"]
    ).to("dimensionless").magnitude

    assert wide_width > narrow_width


def test_uncertainty_spec_requires_source() -> None:
    spec = ParameterUncertaintySpec(
        symbol="k",
        distribution="normal",
        standard_deviation=parameter(name="k std", symbol="sigma_k", value=0.1, units="1 / second"),
        source="",
    )

    with pytest.raises(ProvenanceError):
        spec.validate(base_parameters())


def test_uncertainty_units_are_enforced() -> None:
    spec = ParameterUncertaintySpec(
        symbol="k",
        distribution="normal",
        standard_deviation=parameter(name="bad k std", symbol="sigma_k", value=0.1, units="meter"),
        source="Artificial Stage 11 bad-unit uncertainty test.",
    )

    with pytest.raises(UnitError):
        spec.validate(base_parameters())


def test_local_sensitivity_reports_normalized_ranking() -> None:
    specs = [
        LocalSensitivitySpec(
            symbol="k",
            source="Artificial Stage 11 k sensitivity test.",
        ),
        LocalSensitivitySpec(
            symbol="t",
            source="Artificial Stage 11 t sensitivity test.",
        ),
    ]

    result = local_sensitivity(
        base_parameters=base_parameters(),
        sensitivity_specs=specs,
        predict_scalar=scalar_quantity,
        output_units="dimensionless",
    )

    sensitivities = {entry.symbol: entry.normalized_sensitivity for entry in result.entries}
    assert sensitivities["k"] == pytest.approx(1.0)
    assert sensitivities["t"] == pytest.approx(1.0)
    assert set(result.to_dict()["ranking"]) == {"k", "t"}


def test_local_sensitivity_rejects_zero_base_for_relative_step() -> None:
    spec = LocalSensitivitySpec(
        symbol="k",
        source="Artificial Stage 11 zero-base sensitivity test.",
    )

    with pytest.raises(ValueError):
        local_sensitivity(
            base_parameters=base_parameters(k_value=0.0),
            sensitivity_specs=[spec],
            predict_scalar=scalar_quantity,
            output_units="dimensionless",
        )
