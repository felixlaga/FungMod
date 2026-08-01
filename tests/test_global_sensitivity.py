from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_
from fungal_model.uncertainty import ParameterUncertaintySpec, global_sensitivity


def parameter(*, name: str, symbol: str, value: float, units: str = "dimensionless") -> Parameter:
    return Parameter(
        name=name,
        symbol=symbol,
        value=value,
        units=units,
        uncertainty=0.0,
        source="Artificial global-sensitivity benchmark value; no physical or biological claim.",
        confidence_level="testing",
        notes="Defined only for software verification.",
        measurement_method="analytical benchmark definition",
    )


def ishigami_inputs() -> tuple[ParameterSet, list[ParameterUncertaintySpec]]:
    base = ParameterSet(
        [
            parameter(name="Ishigami x1", symbol="x1", value=0.0),
            parameter(name="Ishigami x2", symbol="x2", value=0.0),
            parameter(name="Ishigami x3", symbol="x3", value=0.0),
        ]
    )
    specs = [
        ParameterUncertaintySpec(
            symbol=symbol,
            distribution="uniform",
            lower_bound=parameter(name=f"{symbol} lower", symbol=f"{symbol}_lower", value=-np.pi),
            upper_bound=parameter(name=f"{symbol} upper", symbol=f"{symbol}_upper", value=np.pi),
            source="Ishigami artificial benchmark uniform input definition on [-pi, pi].",
        )
        for symbol in ("x1", "x2", "x3")
    ]
    return base, specs


def ishigami_prediction(parameters: ParameterSet):
    x1 = parameters.require_quantity("x1", "dimensionless").magnitude
    x2 = parameters.require_quantity("x2", "dimensionless").magnitude
    x3 = parameters.require_quantity("x3", "dimensionless").magnitude
    return Q_(np.sin(x1) + 7.0 * np.sin(x2) ** 2 + 0.1 * x3**4 * np.sin(x1), "dimensionless")


def test_global_sensitivity_recovers_ishigami_first_and_total_order_indices(tmp_path: Path) -> None:
    base, specs = ishigami_inputs()

    result = global_sensitivity(
        base_parameters=base,
        uncertainty_specs=specs,
        predict_scalar=ishigami_prediction,
        output_units="dimensionless",
        n_base_samples=8192,
        random_seed=731,
        n_bootstrap=128,
        bootstrap_seed=991,
    )

    by_symbol = {entry.symbol: entry for entry in result.indices}
    assert by_symbol["x1"].first_order == pytest.approx(0.314, abs=0.05)
    assert by_symbol["x2"].first_order == pytest.approx(0.442, abs=0.05)
    assert by_symbol["x3"].first_order == pytest.approx(0.0, abs=0.05)
    assert by_symbol["x1"].total_order == pytest.approx(0.558, abs=0.05)
    assert by_symbol["x2"].total_order == pytest.approx(0.442, abs=0.05)
    assert by_symbol["x3"].total_order == pytest.approx(0.244, abs=0.05)
    assert all(entry.first_order_interval is not None for entry in result.indices)
    assert result.n_model_evaluations == 8192 * 5
    assert result.method_sources["first_order"].endswith("10.1016/j.cpc.2009.09.018")
    assert result.to_dict()["total_order_ranking"][0] == "x1"

    result.save(tmp_path)
    assert (tmp_path / "global_sensitivity.json").is_file()


def test_global_sensitivity_is_reproducible_and_does_not_clip_estimates() -> None:
    base, specs = ishigami_inputs()
    first = global_sensitivity(
        base_parameters=base,
        uncertainty_specs=specs,
        predict_scalar=ishigami_prediction,
        output_units="dimensionless",
        n_base_samples=64,
        random_seed=17,
    )
    second = global_sensitivity(
        base_parameters=base,
        uncertainty_specs=specs,
        predict_scalar=ishigami_prediction,
        output_units="dimensionless",
        n_base_samples=64,
        random_seed=17,
    )

    assert first.to_dict() == second.to_dict()
    assert any(
        entry.first_order < 0.0 or entry.first_order > 1.0
        for entry in first.indices
    )


def test_global_sensitivity_rejects_zero_output_variance() -> None:
    base, specs = ishigami_inputs()

    with pytest.raises(ValueError, match="variance is not positive"):
        global_sensitivity(
            base_parameters=base,
            uncertainty_specs=specs,
            predict_scalar=lambda parameters: Q_(1.0, "dimensionless"),
            output_units="dimensionless",
            n_base_samples=8,
            random_seed=1,
        )


def test_global_sensitivity_reports_exact_failed_design_row() -> None:
    base, specs = ishigami_inputs()

    def failing_prediction(parameters: ParameterSet):
        del parameters
        raise RuntimeError("intentional benchmark failure")

    with pytest.raises(RuntimeError, match="A row 0.*intentional benchmark failure"):
        global_sensitivity(
            base_parameters=base,
            uncertainty_specs=specs,
            predict_scalar=failing_prediction,
            output_units="dimensionless",
            n_base_samples=8,
            random_seed=1,
        )


def test_global_sensitivity_rejects_duplicate_uncertainty_symbols() -> None:
    base, specs = ishigami_inputs()

    with pytest.raises(ValueError, match="must be unique"):
        global_sensitivity(
            base_parameters=base,
            uncertainty_specs=[specs[0], specs[0]],
            predict_scalar=ishigami_prediction,
            output_units="dimensionless",
            n_base_samples=8,
            random_seed=1,
        )
