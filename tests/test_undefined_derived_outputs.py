"""Generic derived diagnostics retain unknowns without masking invalid states."""
import csv
import json

import numpy as np
import pytest

from fungal_model.core.units import Q_
from fungal_model.results import SimulationResult
from fungal_model.results.result import _quantity_to_dict, _write_quantity_table
from tests.test_reaction_engine import build_first_order_engine


@pytest.mark.parametrize("values", [1.25, [1.25, -0.0], [[1.5, 0.0], [7.25, 1e-200]]])
def test_finite_derived_quantity_json_bytes_are_unchanged(values):
    quantity = Q_(values, "dimensionless")
    previous = json.dumps(_quantity_to_dict(quantity), sort_keys=True)
    current = json.dumps(_quantity_to_dict(quantity, undefined_as_none=True), sort_keys=True)
    assert current == previous


def test_undefined_generic_diagnostic_is_null_in_strict_json_and_blank_in_csv(tmp_path):
    ode = build_first_order_engine().simulate(
        initial_state={"A": Q_(1, "mol/L"), "B": Q_(0, "mol/L")},
        t_span=(Q_(0, "s"), Q_(2, "s")), t_eval=Q_([0, 1, 2], "s"))
    result = SimulationResult.from_ode_result(ode, derived_quantities={
        "normalized_signal": Q_([np.nan, .5, 1.], "dimensionless"),
        "normalized_signal_defined": Q_([False, True, True], "dimensionless"),
    })
    result.save(tmp_path)
    def reject_constant(value):
        raise AssertionError(f"Invalid JSON constant: {value}")
    saved = json.loads((tmp_path / "record.json").read_text(), parse_constant=reject_constant)
    assert saved["derived_quantities"]["normalized_signal"]["value"] == [None, .5, 1.]
    assert np.isnan(result.derived_quantities["normalized_signal"].magnitude[0])
    with (tmp_path / "derived_quantities.csv").open() as handle:
        rows = [row for row in csv.DictReader(handle) if row["name"] == "normalized_signal"]
    assert [row["value"] for row in rows] == ["", "0.5", "1.0"]


@pytest.mark.parametrize("kind", ["state", "rate", "state_rate"])
def test_invalid_states_and_rates_are_not_sanitized_as_missing_diagnostics(tmp_path, kind):
    quantity = Q_([np.nan], "mol/L")
    assert np.isnan(_quantity_to_dict(quantity)["value"][0])
    path = tmp_path / "invalid.csv"
    _write_quantity_table(path, Q_([0], "s"), {"invalid": quantity}, kind=kind)
    with path.open() as handle:
        assert next(csv.DictReader(handle))["value"] == "nan"
