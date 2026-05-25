from __future__ import annotations

import pytest

from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.provenance import ProvenanceError, UnknownParameterError
from fungal_model.core.units import Q_


def sourced_parameter() -> Parameter:
    return Parameter(
        name="first-order benchmark rate constant",
        symbol="k",
        value=0.1,
        units="1 / second",
        uncertainty=0.0,
        source="Analytical software benchmark; no physical claim.",
        confidence_level="testing",
        notes="Used to verify numerical integration and provenance plumbing.",
        measurement_method="defined benchmark value",
    )


def test_missing_source_raises_without_testing_flag() -> None:
    parameter = Parameter(
        name="unsourced parameter",
        symbol="u",
        value=1.0,
        units="meter",
        uncertainty=None,
        source=None,
        confidence_level="unknown",
        notes="Deliberately missing source.",
        measurement_method=None,
    )
    parameters = ParameterSet([parameter])

    with pytest.raises(ProvenanceError):
        parameters.validate()

    parameters.validate(allow_unsourced_for_testing=True)


def test_unknown_parameter_is_explicit() -> None:
    parameter = Parameter(
        name="unknown PET surface rate",
        symbol="k_surface",
        value=None,
        units="mole / meter ** 2 / second",
        uncertainty=None,
        source="Known missing value for model design.",
        confidence_level="unknown",
        notes="Unknown by design; must not be guessed.",
        measurement_method=None,
    )
    parameters = ParameterSet([parameter])

    parameters.validate(require_values=False)
    with pytest.raises(UnknownParameterError):
        parameters.validate(require_values=True)


def test_parameter_quantity_and_compatible_units() -> None:
    parameter = Parameter(
        name="amount concentration",
        symbol="C",
        value=Q_(1000, "millimole / liter"),
        units="mole / liter",
        uncertainty=Q_(1, "millimole / liter"),
        source="Unit conversion test.",
        confidence_level="testing",
        notes="Tests conversion into declared units.",
        measurement_method="software test",
    )

    assert parameter.quantity is not None
    assert parameter.quantity.magnitude == pytest.approx(1.0)
    assert parameter.uncertainty_quantity is not None
    assert parameter.uncertainty_quantity.magnitude == pytest.approx(0.001)


def test_parameter_set_json_roundtrip(tmp_path) -> None:
    parameters = ParameterSet([sourced_parameter()])
    path = tmp_path / "parameters.json"

    parameters.to_json(path)
    loaded = ParameterSet.from_json(path)

    assert loaded.get("k").quantity is not None
    assert loaded.get("k").quantity.magnitude == pytest.approx(0.1)
    assert loaded.get("k").source == "Analytical software benchmark; no physical claim."

