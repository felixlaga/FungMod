from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from fungal_model import run_configured_model
from fungal_model.api.report import write_virtual_experiment_report
from fungal_model.chemistry.stoichiometry import (
    ElementalComposition,
    StoichiometricReactionMetadata,
    StoichiometricTerm,
)
from fungal_model.chemistry.thermodynamics import GibbsFreeEnergyEstimate
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_
from fungal_model.core.validators import (
    ValidationResult,
    validate_charge_balance,
    validate_condition_specific_gibbs_feasibility,
    validate_electron_balance,
    validate_elemental_balance,
    validate_entropy_production_rate,
    validate_non_negative,
    validate_reaction_quotient_gibbs_feasibility,
)
from fungal_model.io import ValidatorRegistry, load_model_config
from fungal_model.results import SimulationResult
from fungal_model.core.simulation import SolverSettings
from fungal_model.workflows import ConfiguredModelExecutionError


def test_elemental_balance_reports_residuals_for_balanced_synthetic_reaction() -> None:
    reaction = _reaction(
        name="synthetic X2 split",
        reactants=(_term("X2_pool", 1.0, formula="X2"),),
        products=(_term("X_pool", 2.0, formula="X"),),
    )

    validation = validate_elemental_balance(reaction)

    assert validation.passed
    assert validation.to_dict()["status"] == "passed"
    assert validation.details["residuals"]["X"]["residual_value"] == pytest.approx(0.0)
    assert validation.details["residual_units"] == "atom equivalents per reaction event"
    assert validation.details["provenance_refs"]


def test_elemental_balance_fails_for_unbalanced_unrelated_synthetic_reaction() -> None:
    reaction = _reaction(
        name="synthetic Y2 loss",
        reactants=(_term("Y2_pool", 1.0, formula="Y2"),),
        products=(_term("Y_pool", 1.0, formula="Y"),),
    )

    validation = validate_elemental_balance(reaction)

    assert not validation.passed
    assert validation.to_dict()["status"] == "failed"
    assert validation.details["max_abs_residual"] == pytest.approx(1.0)


def test_missing_composition_is_inconclusive_not_passed() -> None:
    reaction = _reaction(
        name="missing composition",
        reactants=(StoichiometricTerm(species="unknown_left", coefficient=1.0),),
        products=(_term("known_right", 1.0, formula="Z"),),
    )

    validation = validate_elemental_balance(reaction)

    assert not validation.passed
    assert validation.to_dict()["status"] == "inconclusive"
    assert validation.details["missing_metadata"] == [{"species": "unknown_left", "field": "composition"}]


def test_charge_and_electron_balance_use_only_explicit_metadata() -> None:
    charge_balanced = _reaction(
        name="synthetic charge transfer",
        reactants=(_term("left_ion", 1.0, formula="Q", charge=-1.0),),
        products=(_term("right_ion", 1.0, formula="Q", charge=-1.0),),
    )
    electron_unbalanced = _reaction(
        name="synthetic electron mismatch",
        reactants=(_term("reduced_pool", 1.0, formula="R", electron_equivalents=1.0),),
        products=(_term("oxidized_pool", 1.0, formula="R", electron_equivalents=2.0),),
    )

    charge = validate_charge_balance(charge_balanced)
    electron = validate_electron_balance(electron_unbalanced)

    assert charge.passed
    assert charge.details["residual_value"] == pytest.approx(0.0)
    assert not electron.passed
    assert electron.to_dict()["status"] == "failed"
    assert electron.details["residual_value"] == pytest.approx(1.0)


def test_missing_charge_or_electron_metadata_is_inconclusive() -> None:
    reaction = _reaction(
        name="missing scalar metadata",
        reactants=(_term("left_pool", 1.0, formula="M"),),
        products=(_term("right_pool", 1.0, formula="M"),),
    )

    charge = validate_charge_balance(reaction)
    electron = validate_electron_balance(reaction)

    assert charge.to_dict()["status"] == "inconclusive"
    assert electron.to_dict()["status"] == "inconclusive"
    assert not charge.passed
    assert not electron.passed


def test_condition_specific_gibbs_validator_reports_favorable_and_unfavorable_estimates() -> None:
    favorable = _gibbs_estimate(-5.0)
    unfavorable = _gibbs_estimate(2.0)

    favorable_result = validate_condition_specific_gibbs_feasibility(favorable)
    unfavorable_result = validate_condition_specific_gibbs_feasibility(unfavorable)

    assert favorable_result.passed
    assert favorable_result.details["residual_value"] == pytest.approx(-5000.0)
    assert favorable_result.details["dynamic_reaction_quotient"] == "not_evaluated"
    assert not unfavorable_result.passed
    assert unfavorable_result.to_dict()["status"] == "failed"
    assert unfavorable_result.details["residual_value"] == pytest.approx(2000.0)


def test_reaction_quotient_gibbs_validator_applies_rt_ln_q_and_entropy() -> None:
    validation = validate_reaction_quotient_gibbs_feasibility(
        standard_estimate=_gibbs_estimate(-1.0),
        reaction_quotient=_parameter(symbol="Q_reaction", value=2.0, units="dimensionless"),
        temperature=_parameter(symbol="T_dynamic", value=298.15, units="kelvin"),
    )

    expected_rt_ln_q = 8.31446261815324 * 298.15 * 0.6931471805599453
    expected_delta_g = -1000.0 + expected_rt_ln_q

    assert not validation.passed
    assert validation.to_dict()["status"] == "failed"
    assert validation.details["rt_ln_q"] == pytest.approx(expected_rt_ln_q)
    assert validation.details["residual_value"] == pytest.approx(expected_delta_g)
    assert validation.details["entropy_production_per_mole"] == pytest.approx(
        -expected_delta_g / 298.15
    )
    assert validation.details["dynamic_reaction_quotient"] == "explicit_parameter"
    assert validation.details["activity_model"] == "caller_supplied_dimensionless_reaction_quotient"


def test_reaction_quotient_gibbs_validator_reports_favorable_q_case() -> None:
    validation = validate_reaction_quotient_gibbs_feasibility(
        standard_estimate=_gibbs_estimate(-5.0),
        reaction_quotient=_parameter(symbol="Q_reaction", value=1.0, units="dimensionless"),
        temperature=_parameter(symbol="T_dynamic", value=298.15, units="kelvin"),
    )

    assert validation.passed
    assert validation.details["residual_value"] == pytest.approx(-5000.0)
    assert validation.details["entropy_production_per_mole"] == pytest.approx(5000.0 / 298.15)


def test_entropy_production_rate_validator_reports_positive_explicit_metadata() -> None:
    validation = validate_entropy_production_rate(
        condition_specific_delta_gibbs=_parameter(symbol="dG_condition", value=-10.0, units="kilojoule / mole"),
        reaction_extent_rate=_parameter(symbol="xi_dot", value=2.0, units="millimole / second"),
        temperature=_parameter(symbol="T_entropy_rate", value=298.15, units="kelvin"),
    )

    expected_rate = 20.0 / 298.15

    assert validation.passed
    assert validation.to_dict()["status"] == "passed"
    assert validation.details["entropy_production_rate"] == pytest.approx(expected_rate)
    assert validation.details["entropy_production_rate_units"] == "joule / second / kelvin"
    assert validation.details["condition_specific_delta_gibbs"] == pytest.approx(-10000.0)
    assert validation.details["reaction_extent_rate"] == pytest.approx(0.002)
    assert validation.details["solver_time_enforcement"] == "not_evaluated"
    assert "No inferred activities" in validation.details["unsupported_scope"]


def test_entropy_production_rate_validator_fails_negative_explicit_metadata() -> None:
    validation = validate_entropy_production_rate(
        condition_specific_delta_gibbs=_parameter(symbol="dG_condition", value=5.0, units="kilojoule / mole"),
        reaction_extent_rate=_parameter(symbol="xi_dot", value=1.0, units="millimole / second"),
        temperature=_parameter(symbol="T_entropy_rate", value=298.15, units="kelvin"),
    )

    assert not validation.passed
    assert validation.to_dict()["status"] == "failed"
    assert validation.details["entropy_production_rate"] == pytest.approx(-5.0 / 298.15)


def test_entropy_production_rate_validator_rejects_invalid_temperature_and_units() -> None:
    nonpositive_temperature = validate_entropy_production_rate(
        condition_specific_delta_gibbs=_parameter(symbol="dG_condition", value=-5.0, units="kilojoule / mole"),
        reaction_extent_rate=_parameter(symbol="xi_dot", value=1.0, units="millimole / second"),
        temperature=_parameter(symbol="T_entropy_rate", value=0.0, units="kelvin"),
    )
    invalid_extent_units = validate_entropy_production_rate(
        condition_specific_delta_gibbs=_parameter(symbol="dG_condition", value=-5.0, units="kilojoule / mole"),
        reaction_extent_rate=_parameter(symbol="xi_dot", value=1.0, units="meter"),
        temperature=_parameter(symbol="T_entropy_rate", value=298.15, units="kelvin"),
    )

    assert not nonpositive_temperature.passed
    assert nonpositive_temperature.details["invalid_metadata"] == ["temperature_nonpositive"]
    assert not invalid_extent_units.passed
    assert invalid_extent_units.details["error_type"] == "UnitError"
    assert "incompatible" in invalid_extent_units.message


def test_entropy_production_rate_validator_reports_missing_quantity_as_inconclusive() -> None:
    validation = validate_entropy_production_rate(
        condition_specific_delta_gibbs=_parameter(symbol="dG_condition", value=None, units="kilojoule / mole"),
        reaction_extent_rate=_parameter(symbol="xi_dot", value=1.0, units="millimole / second"),
        temperature=_parameter(symbol="T_entropy_rate", value=298.15, units="kelvin"),
    )

    assert not validation.passed
    assert validation.to_dict()["status"] == "inconclusive"
    assert validation.details["missing_metadata"] == ["condition_specific_delta_gibbs"]


def test_reaction_quotient_gibbs_validator_rejects_nonpositive_q() -> None:
    validation = validate_reaction_quotient_gibbs_feasibility(
        standard_estimate=_gibbs_estimate(-5.0),
        reaction_quotient=_parameter(symbol="Q_reaction", value=0.0, units="dimensionless"),
        temperature=_parameter(symbol="T_dynamic", value=298.15, units="kelvin"),
    )

    assert not validation.passed
    assert validation.to_dict()["status"] == "failed"
    assert validation.details["invalid_metadata"] == ["reaction_quotient_nonpositive"]


def test_unknown_condition_specific_gibbs_is_inconclusive() -> None:
    validation = validate_condition_specific_gibbs_feasibility(_gibbs_estimate(None))

    assert not validation.passed
    assert validation.to_dict()["status"] == "inconclusive"
    assert validation.details["missing_metadata"] == ["delta_gibbs"]


def test_static_thermodynamic_validator_reports_provenance_failure() -> None:
    estimate = GibbsFreeEnergyEstimate(
        reaction_name="unsourced synthetic static reaction",
        delta_gibbs=Parameter(
            name="unsourced condition-specific delta G",
            symbol="dG_static",
            value=-1.0,
            units="kilojoule / mole",
            uncertainty=None,
            source=None,
            confidence_level="unknown",
            notes="Deliberately unsourced Phase 2 validator test value.",
            measurement_method=None,
        ),
        conditions=ParameterSet([_parameter(symbol="T_static", value=298.15, units="kelvin")]),
        source=None,
    )

    validation = validate_condition_specific_gibbs_feasibility(estimate)

    assert not validation.passed
    assert validation.to_dict()["status"] == "failed"
    assert validation.details["error_type"] == "ProvenanceError"


def test_validator_registry_loads_static_balance_and_thermodynamic_validators() -> None:
    registry = ValidatorRegistry.default()
    elemental = registry.load(
        {
            "validator_type": "elemental_balance",
            "reaction": _reaction_config(
                reactants=[{"species": "A2_pool", "coefficient": 1.0, "formula": "A2"}],
                products=[{"species": "A_pool", "coefficient": 2.0, "formula": "A"}],
            ),
        }
    )
    thermo = registry.load(
        {
            "validator_type": "thermodynamic_metadata",
            "estimate": _gibbs_config(-3.0),
        }
    )
    reaction_quotient = registry.load(
        {
            "validator_type": "reaction_quotient_thermodynamic_metadata",
            "estimate": _gibbs_config(-5.0),
            "reaction_quotient": _parameter_config(symbol="Q_configured", value=1.0, units="dimensionless"),
            "temperature": _parameter_config(symbol="T_configured_dynamic", value=298.15, units="kelvin"),
        }
    )
    entropy_rate = registry.load(
        {
            "validator_type": "entropy_production_rate_metadata",
            "condition_specific_delta_gibbs": _parameter_config(
                symbol="dG_entropy_rate",
                value=-5.0,
                units="kilojoule / mole",
            ),
            "reaction_extent_rate": _parameter_config(
                symbol="xi_dot_configured",
                value=1.0,
                units="millimole / second",
            ),
            "temperature": _parameter_config(symbol="T_configured_entropy_rate", value=298.15, units="kelvin"),
        }
    )

    assert elemental(object()).to_dict()["status"] == "passed"
    assert thermo(object()).to_dict()["status"] == "passed"
    assert reaction_quotient(object()).to_dict()["status"] == "passed"
    assert entropy_rate(object()).to_dict()["status"] == "passed"


def test_exploratory_config_records_inconclusive_static_validator(tmp_path: Path) -> None:
    config = _configured_static_validator_config(mode="exploratory")
    config["validators"].append(
        {
            "id": "missing_static_composition",
            "validator_type": "elemental_balance",
            "reaction": {
                "name": "configured missing composition",
                "source": "Configured static validation fixture.",
                "reactants": [{"species": "left_pool", "coefficient": 1.0}],
                "products": [
                    {
                        "species": "right_pool",
                        "coefficient": 1.0,
                        "formula": "N",
                        "composition_source": "Configured static validation fixture.",
                    }
                ],
            },
        }
    )
    config_path = _write_config(tmp_path, config)
    output_dir = tmp_path / "exploratory_output"

    result = run_configured_model(config_path, output_dir=output_dir)

    static_validation = [row for row in result.validation_report() if row["name"] == "elemental_balance"][0]
    validators_json = json.loads((output_dir / "validators.json").read_text(encoding="utf-8"))
    assert static_validation["status"] == "inconclusive"
    assert static_validation["passed"] is False
    assert validators_json["summary"]["status_counts"]["inconclusive"] == 1
    assert validators_json["summary"]["passed"] is False
    assert (output_dir / "output_manifest.json").exists()


def test_configured_reaction_quotient_validator_writes_thermodynamic_summary(tmp_path: Path) -> None:
    config = _configured_static_validator_config(mode="exploratory")
    config["validators"].append(
        {
            "id": "explicit_q_gibbs",
            "validator_type": "reaction_quotient_thermodynamic_metadata",
            "estimate": _gibbs_config(-5.0),
            "reaction_quotient": _parameter_config(symbol="Q_configured", value=1.0, units="dimensionless"),
            "temperature": _parameter_config(symbol="T_configured_dynamic", value=298.15, units="kelvin"),
        }
    )
    output_dir = tmp_path / "thermodynamic_summary_output"

    result = run_configured_model(_write_config(tmp_path, config), output_dir=output_dir)

    thermodynamic_validation = [
        row
        for row in result.validation_report()
        if row["name"] == "reaction_quotient_thermodynamic_feasibility"
    ][0]
    summary = json.loads((output_dir / "thermodynamic_summary.json").read_text(encoding="utf-8"))
    with (output_dir / "thermodynamic_summary.csv").open(newline="", encoding="utf-8") as handle:
        csv_rows = list(csv.DictReader(handle))
    manifest = json.loads((output_dir / "output_manifest.json").read_text(encoding="utf-8"))
    assert thermodynamic_validation["status"] == "passed"
    assert summary["kind"] == "configured_thermodynamic_summary"
    assert summary["count"] == 1
    assert summary["has_reaction_quotient_gibbs"] is True
    assert summary["has_solver_time_enforcement"] is False
    assert "No inferred activity model" in summary["unsupported_scope"]
    assert summary["rows"][0]["gibbs_equation"] == "delta_g = delta_g_standard + R*T*ln(Q)"
    assert summary["rows"][0]["entropy_production_per_mole"] == pytest.approx(5000.0 / 298.15)
    assert summary["rows"][0]["delta_gibbs"] == pytest.approx(-5000.0)
    assert summary["rows"][0]["residual_value"] == pytest.approx(-5000.0)
    assert csv_rows[0]["name"] == "reaction_quotient_thermodynamic_feasibility"
    assert csv_rows[0]["gibbs_equation"] == "delta_g = delta_g_standard + R*T*ln(Q)"
    assert float(csv_rows[0]["entropy_production_per_mole"]) == pytest.approx(5000.0 / 298.15)
    assert float(csv_rows[0]["delta_gibbs"]) == pytest.approx(-5000.0)
    assert float(csv_rows[0]["residual_value"]) == pytest.approx(-5000.0)
    assert "thermodynamic_summary.json" in manifest["files"]
    assert "thermodynamic_summary.csv" in manifest["files"]

    report_path = write_virtual_experiment_report(
        table_dir=output_dir,
        output_dir=output_dir / "report",
        include_html=True,
        include_index=True,
    )
    report = report_path.read_text(encoding="utf-8")
    html = report_path.with_suffix(".html").read_text(encoding="utf-8")
    index = report_path.with_name("index.html").read_text(encoding="utf-8")

    assert "## Explicit thermodynamic diagnostics" in report
    assert "existing configured-output `thermodynamic_summary.json` and `thermodynamic_summary.csv`" in report
    assert "do not independently infer, recompute, or revalidate activities" in report
    assert "this report does not apply that enforcement" in report
    assert "`reaction_quotient_thermodynamic_feasibility`" in report
    assert "delta_gibbs=-5000.0 joule / mole" in report
    assert "delta_g = delta_g_standard + R*T*ln(Q)" in report
    assert "solver-time enforcement `False`" in report
    assert "No inferred activity model" in report
    assert 'href="../thermodynamic_summary.json"' in html
    assert 'href="../thermodynamic_summary.csv"' in html
    assert 'href="../thermodynamic_summary.json"' in index
    assert 'href="../thermodynamic_summary.csv"' in index
    assert "empirically validated" not in report.lower()
    assert "calibrated against observations" not in report.lower()


def test_configured_entropy_production_rate_validator_writes_thermodynamic_summary(tmp_path: Path) -> None:
    config = _configured_static_validator_config(mode="exploratory")
    config["validators"].append(
        {
            "id": "explicit_entropy_rate",
            "validator_type": "entropy_production_rate_metadata",
            "condition_specific_delta_gibbs": _parameter_config(
                symbol="dG_entropy_rate_configured",
                value=-10.0,
                units="kilojoule / mole",
            ),
            "reaction_extent_rate": _parameter_config(
                symbol="xi_dot_configured",
                value=2.0,
                units="millimole / second",
            ),
            "temperature": _parameter_config(symbol="T_entropy_rate_configured", value=298.15, units="kelvin"),
        }
    )
    output_dir = tmp_path / "entropy_rate_summary_output"

    result = run_configured_model(_write_config(tmp_path, config), output_dir=output_dir)

    entropy_rate_validation = [
        row
        for row in result.validation_report()
        if row["name"] == "entropy_production_rate_metadata"
    ][0]
    summary = json.loads((output_dir / "thermodynamic_summary.json").read_text(encoding="utf-8"))
    with (output_dir / "thermodynamic_summary.csv").open(newline="", encoding="utf-8") as handle:
        csv_rows = list(csv.DictReader(handle))
    manifest = json.loads((output_dir / "output_manifest.json").read_text(encoding="utf-8"))

    assert entropy_rate_validation["status"] == "passed"
    assert summary["has_entropy_production_rate"] is True
    assert summary["has_entropy_budget"] is True
    assert summary["entropy_budget_units"] == "joule / second / kelvin"
    assert summary["entropy_budget_total"] == pytest.approx(20.0 / 298.15)
    assert summary["entropy_budget_minimum"] == pytest.approx(20.0 / 298.15)
    assert summary["entropy_budget_negative_count"] == 0
    assert summary["entropy_budget_evaluated_count"] == 1
    assert summary["entropy_budget_status"] == "non_negative"
    assert "not treated as zero" in summary["entropy_budget_limitations"]
    assert summary["has_solver_time_enforcement"] is False
    assert "concentration model" in summary["unsupported_scope"]
    assert summary["rows"][0]["entropy_equation"] == (
        "entropy_production_rate = -condition_specific_delta_gibbs * "
        "reaction_extent_rate / temperature"
    )
    assert summary["rows"][0]["entropy_production_rate"] == pytest.approx(20.0 / 298.15)
    assert summary["rows"][0]["residual_value"] == pytest.approx(20.0 / 298.15)
    assert summary["rows"][0]["residual_units"] == "joule / second / kelvin"
    assert summary["rows"][0]["delta_gibbs"] == ""
    assert summary["rows"][0]["delta_gibbs_units"] == ""
    assert csv_rows[0]["name"] == "entropy_production_rate_metadata"
    assert float(csv_rows[0]["entropy_production_rate"]) == pytest.approx(20.0 / 298.15)
    assert float(csv_rows[0]["residual_value"]) == pytest.approx(20.0 / 298.15)
    assert csv_rows[0]["residual_units"] == "joule / second / kelvin"
    assert csv_rows[0]["delta_gibbs"] == ""
    assert csv_rows[0]["delta_gibbs_units"] == ""
    assert csv_rows[0]["solver_time_enforcement"] == "not_evaluated"
    assert "entropy_budget_total" not in csv_rows[0]
    assert "thermodynamic_summary.json" in manifest["files"]
    assert "thermodynamic_summary.csv" in manifest["files"]


def test_configured_entropy_budget_reports_mixed_explicit_rate_rows(tmp_path: Path) -> None:
    config = _configured_static_validator_config(mode="exploratory")
    config["validators"].extend(
        [
            {
                "id": "positive_explicit_entropy_rate",
                "validator_type": "entropy_production_rate_metadata",
                "condition_specific_delta_gibbs": _parameter_config(
                    symbol="dG_entropy_rate_positive",
                    value=-10.0,
                    units="kilojoule / mole",
                ),
                "reaction_extent_rate": _parameter_config(
                    symbol="xi_dot_positive",
                    value=2.0,
                    units="millimole / second",
                ),
                "temperature": _parameter_config(symbol="T_entropy_rate_positive", value=298.15, units="kelvin"),
            },
            {
                "id": "negative_explicit_entropy_rate",
                "validator_type": "entropy_production_rate_metadata",
                "condition_specific_delta_gibbs": _parameter_config(
                    symbol="dG_entropy_rate_negative",
                    value=5.0,
                    units="kilojoule / mole",
                ),
                "reaction_extent_rate": _parameter_config(
                    symbol="xi_dot_negative",
                    value=1.0,
                    units="millimole / second",
                ),
                "temperature": _parameter_config(symbol="T_entropy_rate_negative", value=298.15, units="kelvin"),
            },
            {
                "id": "missing_explicit_entropy_rate",
                "validator_type": "entropy_production_rate_metadata",
                "condition_specific_delta_gibbs": _parameter_config(
                    symbol="dG_entropy_rate_missing",
                    value=None,
                    units="kilojoule / mole",
                ),
                "reaction_extent_rate": _parameter_config(
                    symbol="xi_dot_missing",
                    value=1.0,
                    units="millimole / second",
                ),
                "temperature": _parameter_config(symbol="T_entropy_rate_missing", value=298.15, units="kelvin"),
            },
        ]
    )
    output_dir = tmp_path / "entropy_budget_summary_output"

    result = run_configured_model(_write_config(tmp_path, config), output_dir=output_dir)

    entropy_rows = [
        row
        for row in result.validation_report()
        if row["name"] == "entropy_production_rate_metadata"
    ]
    summary = json.loads((output_dir / "thermodynamic_summary.json").read_text(encoding="utf-8"))
    with (output_dir / "thermodynamic_summary.csv").open(newline="", encoding="utf-8") as handle:
        csv_rows = list(csv.DictReader(handle))

    assert [row["status"] for row in entropy_rows] == ["passed", "failed", "inconclusive"]
    assert summary["count"] == 3
    assert summary["has_entropy_production_rate"] is True
    assert summary["has_entropy_budget"] is True
    assert summary["entropy_budget_scope"].startswith("Aggregate over explicit configured")
    assert summary["entropy_budget_units"] == "joule / second / kelvin"
    assert summary["entropy_budget_total"] == pytest.approx(15.0 / 298.15)
    assert summary["entropy_budget_minimum"] == pytest.approx(-5.0 / 298.15)
    assert summary["entropy_budget_negative_count"] == 1
    assert summary["entropy_budget_evaluated_count"] == 2
    assert summary["entropy_budget_status"] == "negative_entropy_production_rate_detected"
    assert "does not infer thermodynamic quantities" in summary["entropy_budget_limitations"]
    assert len(csv_rows) == 3
    assert all("entropy_budget_status" not in row for row in csv_rows)


def test_strict_config_rejects_failed_static_validator(tmp_path: Path) -> None:
    config = _configured_static_validator_config(mode="strict")
    config["validators"].append(
        {
            "id": "unbalanced_static_elemental_validator",
            "validator_type": "elemental_balance",
            "reaction": _reaction_config(
                reactants=[{"species": "B2_pool", "coefficient": 1.0, "formula": "B2"}],
                products=[{"species": "B_pool", "coefficient": 1.0, "formula": "B"}],
            ),
        }
    )
    config_path = _write_config(tmp_path, config)

    with pytest.raises(ConfiguredModelExecutionError) as error:
        run_configured_model(config_path, output_dir=tmp_path / "strict_output")

    assert error.value.report.stage == "result_validation"
    failed = error.value.report.details["failed_validations"][0]
    assert failed["name"] == "elemental_balance"
    assert failed["status"] == "failed"


def test_configured_species_reaction_metadata_records_passed_assembly_checks(tmp_path: Path) -> None:
    config = _configured_static_validator_config(mode="exploratory")
    config.update(
        _static_balance_sections(
            reaction_id="synthetic_split",
            product_coefficient=1.0,
            checks=["elemental", "charge", "electron"],
            species_metadata={
                "x2_pool": {"formula": "X", "charge": 0.0, "electron_equivalents": 0.0},
                "x_pool": {"formula": "X", "charge": 0.0, "electron_equivalents": 0.0},
            },
        )
    )
    output_dir = tmp_path / "assembly_output"

    result = run_configured_model(_write_config(tmp_path, config), output_dir=output_dir)

    assembly_checks = _assembly_balance_checks(result.validation_report())
    validators_json = json.loads((output_dir / "validators.json").read_text(encoding="utf-8"))
    assert {row["name"] for row in assembly_checks} == {
        "elemental_balance",
        "charge_balance",
        "electron_balance",
    }
    assert {row["status"] for row in assembly_checks} == {"passed"}
    assert all(row["details"]["assembly_time"] is True for row in assembly_checks)
    assert all(row["details"]["reaction_id"] == "synthetic_split" for row in assembly_checks)
    assert all(row["details"]["binding"]["verified"] is True for row in assembly_checks)
    assert validators_json["summary"]["status_counts"]["passed"] >= 4


def test_model_config_exposes_static_balance_metadata_schema_sections(tmp_path: Path) -> None:
    config = _configured_static_validator_config(mode="exploratory")
    config.update(
        _static_balance_sections(
            reaction_id="schema_split",
            product_coefficient=1.0,
            checks=["elemental", "charge"],
            species_metadata={
                "x2_pool": {"formula": "X", "charge": 0.0},
                "x_pool": {"formula": "X", "charge": 0.0},
            },
        )
    )

    loaded = load_model_config(_write_config(tmp_path, config))

    assert loaded.chemistry_metadata is not None
    assert {species.id for species in loaded.chemistry_metadata.species} == {"x2_pool", "x_pool"}
    assert loaded.reaction_metadata[0].id == "schema_split"
    assert loaded.reaction_metadata[0].products[0].coefficient == pytest.approx(1.0)
    assert loaded.balance_checks[0].process_id == "reference_conversion"
    assert loaded.balance_checks[0].checks == ("elemental", "charge")
    assert loaded.balance_checks[0].state_species is not None


def test_exploratory_assembly_check_records_inconclusive_missing_composition(tmp_path: Path) -> None:
    config = _configured_static_validator_config(mode="exploratory")
    config.update(
        _static_balance_sections(
            reaction_id="missing_composition_split",
            product_coefficient=1.0,
            checks=["elemental"],
            required=False,
            species_metadata={
                "x2_pool": {},
                "x_pool": {"formula": "X"},
            },
        )
    )
    output_dir = tmp_path / "exploratory_missing_output"

    result = run_configured_model(_write_config(tmp_path, config), output_dir=output_dir)

    assembly_check = _assembly_balance_checks(result.validation_report())[0]
    validators_json = json.loads((output_dir / "validators.json").read_text(encoding="utf-8"))
    assert assembly_check["status"] == "inconclusive"
    assert assembly_check["passed"] is False
    assert assembly_check["details"]["missing_metadata"] == [
        {"species": "x2_pool", "field": "composition"}
    ]
    assert validators_json["summary"]["status_counts"]["inconclusive"] == 1
    assert (output_dir / "output_manifest.json").exists()


def test_scientific_required_binding_rejects_unrelated_balanced_reaction(tmp_path: Path) -> None:
    config = _configured_static_validator_config(mode="scientific")
    config.update(
        _static_balance_sections(
            reaction_id="unrelated_balanced_split",
            product_coefficient=2.0,
            checks=["elemental"],
            state_species={
                "source_amount": {"species": "a_pool", "role": "reactant"},
                "product_amount": {"species": "b_pool", "role": "product"},
            },
            species_metadata={
                "a_pool": {"formula": "A"},
                "b_pool": {"formula": "B"},
                "x2_pool": {"formula": "X2"},
                "x_pool": {"formula": "X"},
            },
        )
    )

    with pytest.raises(ConfiguredModelExecutionError) as error:
        run_configured_model(_write_config(tmp_path, config), output_dir=tmp_path / "unrelated_output")

    blocking = error.value.report.details["blocking_static_balance_checks"][0]
    failure_reasons = {
        failure["reason"]
        for failure in blocking["details"]["binding"]["failures"]
    }
    assert error.value.report.stage == "model_assembly"
    assert blocking["status"] == "inconclusive"
    assert "species_missing_from_reaction" in failure_reasons
    assert "reaction_species_not_bound_to_process" in failure_reasons


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    [
        ("missing_process", "missing_process_reference"),
        ("unknown_process", "unknown_process_reference"),
        ("duplicated_state", "duplicate_state_mapping"),
        ("contradictory_role", "declared_role_contradiction"),
    ],
)
def test_scientific_required_binding_rejects_invalid_process_mappings(
    tmp_path: Path,
    mutation: str,
    expected_reason: str,
) -> None:
    config = _configured_static_validator_config(mode="scientific")
    config.update(
        _static_balance_sections(
            reaction_id="invalid_binding_reaction",
            product_coefficient=1.0,
            checks=["elemental"],
            species_metadata={
                "x2_pool": {"formula": "X"},
                "x_pool": {"formula": "X"},
            },
        )
    )
    check = config["balance_checks"][0]
    if mutation == "missing_process":
        check.pop("process_id")
    elif mutation == "unknown_process":
        check["process_id"] = "not_assembled"
    elif mutation == "duplicated_state":
        check["state_species"] = [
            {"state": "source_amount", "species": "x2_pool", "role": "reactant"},
            {"state": "source_amount", "species": "x_pool", "role": "product"},
        ]
    elif mutation == "contradictory_role":
        check["state_species"]["source_amount"]["role"] = "product"

    with pytest.raises(ConfiguredModelExecutionError) as error:
        run_configured_model(_write_config(tmp_path, config), output_dir=tmp_path / mutation)

    blocking = error.value.report.details["blocking_static_balance_checks"][0]
    reasons = {
        failure["reason"]
        for failure in blocking["details"]["binding"]["failures"]
    }
    assert error.value.report.stage == "model_assembly"
    assert expected_reason in reasons


def test_scientific_required_assembly_check_blocks_unbalanced_reaction(tmp_path: Path) -> None:
    config = _configured_static_validator_config(mode="scientific")
    config.update(
        _static_balance_sections(
            reaction_id="unbalanced_split",
            product_coefficient=1.0,
            checks=["elemental"],
            species_metadata={
                "x2_pool": {"formula": "X2"},
                "x_pool": {"formula": "X"},
            },
        )
    )
    output_dir = tmp_path / "scientific_unbalanced_output"

    with pytest.raises(ConfiguredModelExecutionError) as error:
        run_configured_model(_write_config(tmp_path, config), output_dir=output_dir)

    assert error.value.report.stage == "model_assembly"
    assert "static_balance_checks" in error.value.report.missing_capabilities
    blocking = error.value.report.details["blocking_static_balance_checks"][0]
    assert blocking["name"] == "elemental_balance"
    assert blocking["status"] == "failed"
    assert blocking["details"]["max_abs_residual"] == pytest.approx(1.0)
    assert not (output_dir / "output_manifest.json").exists()


def test_strict_required_assembly_check_blocks_missing_reaction_metadata(tmp_path: Path) -> None:
    config = _configured_static_validator_config(mode="strict")
    config["balance_checks"] = [
        {
            "id": "missing_reaction_balance",
            "reaction_id": "not_declared",
            "checks": ["elemental"],
            "required": True,
        }
    ]

    with pytest.raises(ConfiguredModelExecutionError) as error:
        run_configured_model(_write_config(tmp_path, config), output_dir=tmp_path / "strict_missing_output")

    blocking = error.value.report.details["blocking_static_balance_checks"][0]
    assert error.value.report.stage == "model_assembly"
    assert blocking["status"] == "inconclusive"
    assert blocking["details"]["missing_metadata"] == ["reaction_metadata.not_declared"]


def test_product_map_process_binding_records_product_map_evidence(tmp_path: Path) -> None:
    config = _configured_mm_product_map_config()
    output_dir = tmp_path / "mm_product_map_output"

    result = run_configured_model(_write_config(tmp_path, config), output_dir=output_dir)

    assembly_checks = _assembly_balance_checks(result.validation_report())
    binding = assembly_checks[0]["details"]["binding"]
    assembly_report = result.assembly_report.to_dict()
    assert assembly_checks[0]["name"] == "elemental_balance"
    assert assembly_checks[0]["status"] == "passed"
    assert binding["verified"] is True
    assert binding["process_type"] == "homogeneous_michaelis_menten"
    assert binding["mapped_process_stoichiometry"] == {
        "product_species": 2.0,
        "substrate_species": -1.0,
    }
    assert binding["product_map"]["id"] == "split_product_map"
    assert binding["product_map"]["data"]["products"] == {"product_amount": 2.0}
    assert assembly_report["static_balance_checks"][0]["details"]["binding"]["verified"] is True


def test_result_serialization_preserves_status_rich_validation(tmp_path: Path) -> None:
    validation = ValidationResult(
        name="synthetic_static_check",
        passed=False,
        status="inconclusive",
        severity="error",
        required=True,
        message="Synthetic inconclusive check.",
        details={"residual_name": "synthetic_residual", "missing_metadata": ["composition"]},
    )
    result = SimulationResult(
        time=Q_([0.0, 1.0], "second"),
        states={"pool": Q_([1.0, 0.9], "kilogram")},
        parameters=ParameterSet(),
        assumptions=(),
        solver_settings=SolverSettings(),
        validation_results=(validation,),
        name="status_rich_serialization",
        label="toy",
    )

    result.save(tmp_path)

    report = json.loads((tmp_path / "validation_report.json").read_text(encoding="utf-8"))
    assert report[0]["status"] == "inconclusive"
    assert report[0]["severity"] == "error"
    assert report[0]["required"] is True
    assert report[0]["details"]["missing_metadata"] == ["composition"]


def test_existing_validator_boolean_compatibility_is_preserved() -> None:
    result = type("FakeResult", (), {"species": {"pool": Q_([1.0, 0.0], "kilogram")}})()

    validation = validate_non_negative(result)

    assert validation.passed is True
    assert validation.to_dict()["passed"] is True
    assert validation.to_dict()["status"] == "passed"


def _term(
    species: str,
    coefficient: float,
    *,
    formula: str,
    charge: float | None = None,
    electron_equivalents: float | None = None,
) -> StoichiometricTerm:
    return StoichiometricTerm(
        species=species,
        coefficient=coefficient,
        composition=ElementalComposition.from_formula(
            formula,
            source="Synthetic Phase 2 static balance fixture; no scientific claim.",
        ),
        charge=charge,
        charge_source=None if charge is None else "Synthetic Phase 2 charge fixture; no scientific claim.",
        electron_equivalents=electron_equivalents,
        electron_source=(
            None
            if electron_equivalents is None
            else "Synthetic Phase 2 electron-equivalent fixture; no scientific claim."
        ),
    )


def _reaction(
    *,
    name: str,
    reactants: tuple[StoichiometricTerm, ...],
    products: tuple[StoichiometricTerm, ...],
) -> StoichiometricReactionMetadata:
    return StoichiometricReactionMetadata(
        name=name,
        reactants=reactants,
        products=products,
        source="Synthetic Phase 2 static reaction fixture; no scientific claim.",
    )


def _parameter(*, symbol: str, value: float | None, units: str) -> Parameter:
    return Parameter(
        name=f"{symbol} synthetic metadata value",
        symbol=symbol,
        value=value,
        units=units,
        uncertainty=0.0 if value is not None else None,
        source="Synthetic Phase 2 static metadata fixture; no scientific claim.",
        confidence_level="medium",
        notes="Synthetic value used only to test static validation plumbing.",
        measurement_method="defined fixture value",
        validity_range="static validator unit tests",
    )


def _gibbs_estimate(value_kj_per_mol: float | None) -> GibbsFreeEnergyEstimate:
    return GibbsFreeEnergyEstimate(
        reaction_name="synthetic condition-specific static reaction",
        delta_gibbs=_parameter(symbol="dG_static", value=value_kj_per_mol, units="kilojoule / mole"),
        conditions=ParameterSet([_parameter(symbol="T_static", value=298.15, units="kelvin")]),
        source="Synthetic Phase 2 Gibbs fixture; no scientific claim.",
        notes="Condition-specific static sign check only; no dynamic reaction quotient is supplied.",
    )


def _reaction_config(*, reactants: list[dict[str, Any]], products: list[dict[str, Any]]) -> dict[str, Any]:
    source = "Configured synthetic Phase 2 static reaction fixture; no scientific claim."
    return {
        "name": "configured synthetic static reaction",
        "source": source,
        "reactants": [
            {**term, "composition_source": source}
            for term in reactants
        ],
        "products": [
            {**term, "composition_source": source}
            for term in products
        ],
    }


def _gibbs_config(value_kj_per_mol: float | None) -> dict[str, Any]:
    source = "Configured synthetic Phase 2 Gibbs fixture; no scientific claim."
    return {
        "reaction_name": "configured synthetic condition-specific reaction",
        "source": source,
        "delta_gibbs": {
            "name": "configured condition-specific delta G",
            "symbol": "dG_configured",
            "value": value_kj_per_mol,
            "units": "kilojoule / mole",
            "uncertainty": 0.0 if value_kj_per_mol is not None else None,
            "source": source,
            "confidence_level": "medium",
            "notes": "Configured synthetic value used only for static validator tests.",
            "measurement_method": "defined fixture value",
            "validity_range": "configured static validator tests",
        },
        "conditions": {
            "parameters": [
                {
                    "name": "configured condition temperature",
                    "symbol": "T_configured",
                    "value": 298.15,
                    "units": "kelvin",
                    "uncertainty": 0.0,
                    "source": source,
                    "confidence_level": "medium",
                    "notes": "Configured condition value for static validator tests.",
                    "measurement_method": "defined fixture value",
                    "validity_range": "configured static validator tests",
                }
            ]
        },
    }


def _parameter_config(*, symbol: str, value: float | None, units: str) -> dict[str, Any]:
    source = "Configured synthetic Phase 2 Gibbs fixture; no scientific claim."
    return {
        "name": f"configured {symbol}",
        "symbol": symbol,
        "value": value,
        "units": units,
        "uncertainty": 0.0 if value is not None else None,
        "source": source,
        "confidence_level": "medium",
        "notes": "Configured synthetic value used only for validator tests.",
        "measurement_method": "defined fixture value",
        "validity_range": "configured validator tests",
    }


def _configured_static_validator_config(*, mode: str) -> dict[str, Any]:
    return {
        "kind": "model_config",
        "name": f"{mode} static validator reference",
        "mode": mode,
        "maturity": "scientific" if mode in {"scientific", "strict"} else "exploratory",
        "entities": {},
        "parameters": [
            {
                "id": "reference_parameters",
                "parameters": [
                    {
                        "name": "reference first-order conversion constant",
                        "symbol": "k_reference",
                        "value": 0.1,
                        "units": "1 / second",
                        "uncertainty": 0.0,
                        "source": "Controlled reference dataset for static validator checks.",
                        "confidence_level": "high",
                        "notes": "Reference value for configured static validator checks.",
                        "measurement_method": "defined reference value",
                        "validity_range": "controlled reference domain",
                    }
                ],
            }
        ],
        "processes": [
            {
                "id": "reference_conversion",
                "process_type": "first_order",
                "states": {"source": "source_amount", "product": "product_amount"},
                "parameters": {"rate_constant": "k_reference"},
                "assumptions": ["reference software process"],
            }
        ],
        "initial_state": {
            "states": {
                "source_amount": {"value": 1.0, "units": "kilogram"},
                "product_amount": {"value": 0.0, "units": "kilogram"},
            }
        },
        "time": {
            "start": {"value": 0.0, "units": "second"},
            "stop": {"value": 1.0, "units": "second"},
            "points": 3,
        },
        "validators": [
            {
                "id": "non_negative_states",
                "validator_type": "non_negative",
                "species": ["source_amount", "product_amount"],
            }
        ],
        "outputs": {},
    }


def _configured_mm_product_map_config() -> dict[str, Any]:
    source = "Controlled reference dataset for configured static balance checks."
    return {
        "kind": "model_config",
        "name": "exploratory product map binding reference",
        "mode": "exploratory",
        "maturity": "exploratory",
        "entities": {
            "product_maps": [
                {
                    "id": "split_product_map",
                    "loader": "stoichiometric",
                    "data": {
                        "kind": "product_map",
                        "name": "controlled split product map",
                        "product_map_type": "stoichiometric",
                        "reactants": {"substrate_amount": 1.0},
                        "products": {"product_amount": 2.0},
                        "maturity": "exploratory",
                        "provenance": {"source": source},
                    },
                }
            ]
        },
        "parameters": [
            {
                "id": "mm_reference_parameters",
                "parameters": [
                    {
                        "name": "reference Michaelis constant",
                        "symbol": "Km_reference",
                        "value": 1.0,
                        "units": "mole / liter",
                        "uncertainty": 0.0,
                        "source": source,
                        "confidence_level": "high",
                        "notes": "Reference value for configured static balance checks.",
                        "measurement_method": "defined reference value",
                        "validity_range": "controlled reference domain",
                    },
                    {
                        "name": "reference maximum rate",
                        "symbol": "Vmax_reference",
                        "value": 0.1,
                        "units": "mole / liter / second",
                        "uncertainty": 0.0,
                        "source": source,
                        "confidence_level": "high",
                        "notes": "Reference value for configured static balance checks.",
                        "measurement_method": "defined reference value",
                        "validity_range": "controlled reference domain",
                    },
                ],
            }
        ],
        "processes": [
            {
                "id": "mm_split",
                "process_type": "homogeneous_michaelis_menten",
                "states": {"substrate": "substrate_amount", "product": "product_amount"},
                "parameters": {
                    "km": "Km_reference",
                    "vmax": "Vmax_reference",
                    "rate_units": "mole / liter / second",
                },
                "product_map": "split_product_map",
                "assumptions": ["reference software process"],
            }
        ],
        "initial_state": {
            "states": {
                "substrate_amount": {"value": 1.0, "units": "mole / liter"},
                "product_amount": {"value": 0.0, "units": "mole / liter"},
            }
        },
        "time": {
            "start": {"value": 0.0, "units": "second"},
            "stop": {"value": 1.0, "units": "second"},
            "points": 3,
        },
        "validators": [
            {
                "id": "non_negative_states",
                "validator_type": "non_negative",
                "species": ["substrate_amount", "product_amount"],
            }
        ],
        "outputs": {},
        "chemistry_metadata": {
            "species": {
                "substrate_species": {
                    "name": "substrate_species",
                    "formula": "X2",
                    "source": source,
                    "composition_source": source,
                },
                "product_species": {
                    "name": "product_species",
                    "formula": "X",
                    "source": source,
                    "composition_source": source,
                },
            }
        },
        "reaction_metadata": [
            {
                "id": "mm_split_reaction",
                "name": "mm_split_reaction",
                "source": source,
                "reactants": [{"species": "substrate_species", "coefficient": 1.0}],
                "products": [{"species": "product_species", "coefficient": 2.0}],
            }
        ],
        "balance_checks": [
            {
                "id": "mm_split_balance",
                "process_id": "mm_split",
                "reaction_id": "mm_split_reaction",
                "checks": ["elemental"],
                "required": True,
                "state_species": {
                    "substrate_amount": {"species": "substrate_species", "role": "reactant"},
                    "product_amount": {"species": "product_species", "role": "product"},
                },
            }
        ],
    }


def _static_balance_sections(
    *,
    reaction_id: str,
    product_coefficient: float,
    checks: list[str],
    species_metadata: dict[str, dict[str, Any]],
    process_id: str = "reference_conversion",
    state_species: dict[str, Any] | None = None,
    required: bool = True,
) -> dict[str, Any]:
    source = "Controlled reference dataset for configured static balance checks."
    mappings = state_species or {
        "source_amount": {"species": "x2_pool", "role": "reactant"},
        "product_amount": {"species": "x_pool", "role": "product"},
    }
    return {
        "chemistry_metadata": {
            "species": {
                species_id: {
                    "name": species_id,
                    "source": source,
                    "composition_source": source,
                    "charge_source": source,
                    "electron_source": source,
                    **metadata,
                }
                for species_id, metadata in species_metadata.items()
            }
        },
        "reaction_metadata": [
            {
                "id": reaction_id,
                "name": reaction_id,
                "source": source,
                "reactants": [{"species": "x2_pool", "coefficient": 1.0}],
                "products": [{"species": "x_pool", "coefficient": product_coefficient}],
            }
        ],
        "balance_checks": [
            {
                "id": f"{reaction_id}_balance",
                "process_id": process_id,
                "reaction_id": reaction_id,
                "checks": checks,
                "required": required,
                "state_species": mappings,
            }
        ],
    }


def _assembly_balance_checks(report: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in report
        if row["details"].get("assembly_time") is True
    ]


def _write_config(tmp_path: Path, config: dict[str, Any]) -> Path:
    path = tmp_path / "model.yml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path
