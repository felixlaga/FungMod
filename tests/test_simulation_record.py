from __future__ import annotations

import json

from fungal_model.core.simulation import SimulationRecord
from fungal_model.core.units import Q_
from fungal_model.core.validators import validate_mass_balance, validate_non_negative
from tests.test_reaction_engine import build_first_order_engine


def test_simulation_record_saves_required_sections(tmp_path) -> None:
    result = build_first_order_engine().simulate(
        initial_state={"A": Q_(1.0, "mole / liter"), "B": Q_(0.0, "mole / liter")},
        t_span=(Q_(0, "second"), Q_(1, "second")),
    )
    validations = [
        validate_non_negative(result).to_dict(),
        validate_mass_balance(result, conserved_weights={"A": 1.0, "B": 1.0}).to_dict(),
    ]
    record = SimulationRecord.from_result(result, validation_summary=validations)
    path = tmp_path / "simulation_record.json"

    record.to_json(path)
    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["timestamp"]
    assert data["model_version"]
    assert data["parameters"]["parameters"]
    assert data["assumptions"]
    assert data["solver_settings"]
    assert data["results_summary"]
    assert data["validation_summary"]["validations"]

