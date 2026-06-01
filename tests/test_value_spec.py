from __future__ import annotations

import pytest
import numpy as np

from fungal_model.registry import ValueSpec, ValueSpecError


def test_exact_value_converts_to_quantity() -> None:
    spec = ValueSpec(kind="exact", value=303.15, units="kelvin", source="test")

    quantity = spec.to_quantity()

    assert spec.is_exact
    assert quantity.to("kelvin").magnitude == pytest.approx(303.15)


def test_range_validates_and_samples_inside_bounds() -> None:
    spec = ValueSpec(kind="range", lower=0.1, upper=10.0, units="meter ** 2 / gram")

    validation = spec.validate(nonnegative=True)
    sample = spec.sample(np.random.default_rng(17))

    assert validation.passed
    assert spec.is_uncertain
    assert 0.1 <= sample.to("meter ** 2 / gram").magnitude <= 10.0


def test_invalid_range_lower_greater_than_upper_fails() -> None:
    spec = ValueSpec(kind="range", lower=2.0, upper=1.0, units="meter")

    validation = spec.validate()

    assert not validation.passed
    assert any(issue["field"] == "range" for issue in validation.details["issues"])


def test_uniform_distribution_samples_inside_bounds() -> None:
    spec = ValueSpec(
        kind="distribution",
        distribution="uniform",
        parameters={"lower": 1.0, "upper": 2.0},
        units="second",
    )

    sample = spec.sample(np.random.default_rng(11))

    assert 1.0 <= sample.to("second").magnitude <= 2.0


def test_loguniform_distribution_samples_positive_values_inside_bounds() -> None:
    spec = ValueSpec(
        kind="distribution",
        distribution="loguniform",
        parameters={"lower": 1.0e-9, "upper": 1.0e-6},
        units="kilogram / meter ** 2 / second",
    )

    validation = spec.validate(nonnegative=True)
    sample = spec.sample(np.random.default_rng(19))

    assert validation.passed
    assert 1.0e-9 <= sample.to("kilogram / meter ** 2 / second").magnitude <= 1.0e-6


def test_unknown_cannot_sample() -> None:
    spec = ValueSpec(kind="unknown", units="meter", source="not measured")

    with pytest.raises(ValueSpecError, match="cannot be sampled"):
        spec.sample(np.random.default_rng(1))


def test_unknown_cannot_convert_to_quantity() -> None:
    spec = ValueSpec(kind="unknown", units="meter", source="not measured")

    with pytest.raises(ValueSpecError, match="cannot be converted"):
        spec.to_quantity()


def test_not_applicable_requires_notes() -> None:
    spec = ValueSpec(kind="not_applicable", units=None)

    validation = spec.validate()

    assert not validation.passed
    assert any(issue["field"] == "notes" for issue in validation.details["issues"])


def test_nonnegative_validation_rejects_negative_values() -> None:
    exact = ValueSpec(kind="exact", value=-1.0, units="meter")
    range_spec = ValueSpec(kind="range", lower=-1.0, upper=1.0, units="meter")
    distribution = ValueSpec(
        kind="distribution",
        distribution="uniform",
        parameters={"lower": -1.0, "upper": 1.0},
        units="meter",
    )

    assert not exact.validate(nonnegative=True).passed
    assert not range_spec.validate(nonnegative=True).passed
    assert not distribution.validate(nonnegative=True).passed


def test_fixed_rng_seed_gives_reproducible_samples() -> None:
    spec = ValueSpec(kind="range", lower=0.0, upper=1.0, units="dimensionless")

    sample_a = spec.sample(np.random.default_rng(101))
    sample_b = spec.sample(np.random.default_rng(101))

    assert sample_a.magnitude == pytest.approx(sample_b.magnitude)
