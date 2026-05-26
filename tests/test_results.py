from __future__ import annotations

import csv
import json

from fungal_model.core.units import Q_
from fungal_model.core.validators import ValidationResult, validate_mass_balance, validate_non_negative
from fungal_model.results import SimulationResult
from tests.test_reaction_engine import build_first_order_engine


def test_standard_result_saves_reports_tables_and_plots(tmp_path) -> None:
    ode_result = build_first_order_engine().simulate(
        initial_state={"A": Q_(1.0, "mole / liter"), "B": Q_(0.0, "mole / liter")},
        t_span=(Q_(0, "second"), Q_(2, "second")),
        t_eval=Q_([0.0, 1.0, 2.0], "second"),
    )
    validations = [
        validate_non_negative(ode_result),
        validate_mass_balance(ode_result, conserved_weights={"A": 1.0, "B": 1.0}),
    ]
    standard = SimulationResult.from_ode_result(
        ode_result,
        validation_results=validations,
        process_rates={"A_to_B": Q_([0.1, 0.09, 0.08], "mole / liter / second")},
        name="first_order_standard_result_test",
        label="toy",
    )

    standard.save(tmp_path, mass_balance_weights={"A": 1.0, "B": 1.0})

    expected_files = [
        "record.json",
        "model_assembly_report.json",
        "assumptions.json",
        "parameters.csv",
        "validation_report.json",
        "solver_report.json",
        "state_trajectories.csv",
        "process_rates.csv",
        "derived_quantities.csv",
        "figures/state_trajectories.png",
        "figures/process_rates.png",
        "figures/mass_balance.png",
        "logs/warnings.txt",
        "logs/provenance_report.md",
    ]
    for relative_path in expected_files:
        assert (tmp_path / relative_path).exists(), relative_path

    record = json.loads((tmp_path / "record.json").read_text(encoding="utf-8"))
    assert record["states"]["A"]["units"] == "mole / liter"
    assert record["process_rates"]["A_to_B"]["units"] == "mole / liter / second"
    assert record["validation_report"][0]["name"] == "non_negative"

    validation_report = json.loads((tmp_path / "validation_report.json").read_text(encoding="utf-8"))
    assert validation_report[1]["name"] == "mass_balance"

    rows = list(csv.DictReader((tmp_path / "state_trajectories.csv").open(encoding="utf-8")))
    assert rows
    assert rows[0]["time_units"] == "second"
    assert rows[0]["units"] == "mole / liter"


def test_standard_result_state_and_rate_accessors() -> None:
    ode_result = build_first_order_engine().simulate(
        initial_state={"A": Q_(1.0, "mole / liter"), "B": Q_(0.0, "mole / liter")},
        t_span=(Q_(0, "second"), Q_(1, "second")),
        t_eval=Q_([0.0, 1.0], "second"),
    )
    standard = SimulationResult.from_ode_result(
        ode_result,
        process_rates={"loss": Q_([0.1, 0.09], "mole / liter / second")},
    )

    assert standard.state("A").units == Q_(1, "mole / liter").units
    assert standard.rate("loss").units == Q_(1, "mole / liter / second").units


def test_failed_validation_still_saves_report(tmp_path) -> None:
    ode_result = build_first_order_engine().simulate(
        initial_state={"A": Q_(1.0, "mole / liter"), "B": Q_(0.0, "mole / liter")},
        t_span=(Q_(0, "second"), Q_(1, "second")),
        t_eval=Q_([0.0, 1.0], "second"),
    )
    failed = ValidationResult(
        name="deliberate_failure",
        passed=False,
        message="Saved even when validation fails.",
        details={"severity": "error"},
    )
    standard = SimulationResult.from_ode_result(ode_result, validation_results=[failed])

    standard.save(tmp_path)

    report = json.loads((tmp_path / "validation_report.json").read_text(encoding="utf-8"))
    assert report[0]["passed"] is False
    assert report[0]["message"] == "Saved even when validation fails."
