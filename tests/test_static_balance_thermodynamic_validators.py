from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from fungal_model import run_configured_model
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
    validate_non_negative,
)
from fungal_model.io import ValidatorRegistry
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

    assert elemental(object()).to_dict()["status"] == "passed"
    assert thermo(object()).to_dict()["status"] == "passed"


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


def _configured_static_validator_config(*, mode: str) -> dict[str, Any]:
    return {
        "kind": "model_config",
        "name": f"{mode} static validator reference",
        "mode": mode,
        "maturity": "scientific" if mode == "strict" else "exploratory",
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


def _write_config(tmp_path: Path, config: dict[str, Any]) -> Path:
    path = tmp_path / "model.yml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path
