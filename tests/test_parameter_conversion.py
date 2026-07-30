from __future__ import annotations

import math

import pytest

import fungal_model
from fungal_model import (
    PARAMETER_CONVERSION_REGISTRY_SCHEMA_VERSION,
    PINT_DECIMAL_PLACES_HALF_EVEN_12_V1,
    ParameterConversionError,
    ParameterConversionMethod,
    ParameterConversionRegistry,
    default_parameter_conversion_registry,
)


def test_default_conversion_registry_is_versioned_and_public() -> None:
    registry = default_parameter_conversion_registry()
    method = registry.resolve(PINT_DECIMAL_PLACES_HALF_EVEN_12_V1)

    assert registry.schema_version == PARAMETER_CONVERSION_REGISTRY_SCHEMA_VERSION
    assert method.version == "1.0.0"
    assert method.algorithm == "pint_unit_conversion"
    assert method.rounding_mode == "decimal_places_half_even"
    assert method.decimal_places == 12
    assert method.convert(
        0.13,
        source_units="s^(-1)",
        target_units="1 / minute",
    ) == 7.8
    assert (
        fungal_model.default_parameter_conversion_registry
        is default_parameter_conversion_registry
    )


@pytest.mark.parametrize(
    ("value", "source_units", "target_units", "message"),
    [
        (math.nan, "second", "minute", "finite float"),
        (1.0, "not_a_real_unit", "minute", "must parse"),
        (1.0, "second", "meter", "compatible dimensionality"),
        (1.0, "second", "second", "distinct source and target unit text"),
    ],
)
def test_conversion_method_rejects_unsafe_inputs(
    value: float,
    source_units: str,
    target_units: str,
    message: str,
) -> None:
    method = default_parameter_conversion_registry().resolve(
        PINT_DECIMAL_PLACES_HALF_EVEN_12_V1
    )

    with pytest.raises(ParameterConversionError, match=message):
        method.convert(
            value,
            source_units=source_units,
            target_units=target_units,
        )


def test_conversion_registry_rejects_unknown_or_duplicate_methods() -> None:
    method = ParameterConversionMethod(
        method_id=PINT_DECIMAL_PLACES_HALF_EVEN_12_V1,
        version="1.0.0",
        algorithm="pint_unit_conversion",
        rounding_mode="decimal_places_half_even",
        decimal_places=12,
    )

    with pytest.raises(ParameterConversionError, match="unique method"):
        ParameterConversionRegistry(
            schema_version=PARAMETER_CONVERSION_REGISTRY_SCHEMA_VERSION,
            methods=(method, method),
        )
    with pytest.raises(ParameterConversionError, match="not registered"):
        default_parameter_conversion_registry().resolve("unknown_conversion")
