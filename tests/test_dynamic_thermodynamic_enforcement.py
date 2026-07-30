from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from fungal_model import ConfiguredModelExecutionError, load_model_config, run_configured_model


ROOT = Path(__file__).resolve().parents[1]
BASE_CONFIG = ROOT / "data" / "model_configs" / "toy_homogeneous_ab.yml"
SOURCE = "Artificial framework benchmark for dynamic thermodynamic enforcement tests."


def test_dynamic_standard_gibbs_constraint_blocks_unfavorable_forward_rate(
    tmp_path: Path,
) -> None:
    config = _dynamic_config(method="standard_delta_gibbs")
    constrained_path = _write_config(tmp_path, config, name="constrained.yml")
    constrained = run_configured_model(
        constrained_path,
        output_dir=tmp_path / "constrained_output",
    )

    unconstrained_config = _dynamic_config(method="standard_delta_gibbs")
    unconstrained_config.pop("thermodynamic_constraints")
    unconstrained = run_configured_model(
        _write_config(tmp_path, unconstrained_config, name="unconstrained.yml"),
        output_dir=tmp_path / "unconstrained_output",
    )

    constrained_a = constrained.state("dissolved_substrate_amount").to("mM").magnitude
    constrained_b = constrained.state("released_product_amount").to("mM").magnitude
    unconstrained_a = unconstrained.state("dissolved_substrate_amount").to("mM").magnitude
    assert constrained_a[-1] == pytest.approx(0.5, abs=2.0e-3)
    assert constrained_b[-1] == pytest.approx(0.5, abs=2.0e-3)
    assert constrained_a[-1] > unconstrained_a[-1] + 0.1
    assert constrained_a + constrained_b == pytest.approx(
        np.ones_like(constrained_a),
        rel=1.0e-7,
        abs=1.0e-7,
    )
    assert constrained.process_rates["a_to_b"].to("mM / second").magnitude[-1] == pytest.approx(0.0)

    prefix = "dynamic_thermodynamics.a_to_b_dynamic"
    quotient = constrained.derived_quantities[f"{prefix}.reaction_quotient"].magnitude
    delta_g = constrained.derived_quantities[f"{prefix}.delta_gibbs"].to(
        "joule / mole"
    ).magnitude
    blocked = constrained.derived_quantities[f"{prefix}.rate_blocked"].magnitude
    assert quotient[0] < 1.0
    assert quotient[-1] >= 1.0
    assert delta_g[0] < 0.0
    assert delta_g[-1] >= 0.0
    assert blocked[-1] == pytest.approx(1.0)

    validation = _dynamic_validation(constrained.validation_report())
    assert validation["passed"] is True
    assert validation["details"]["recorded_blocked_count"] > 0
    assert validation["details"]["activity_model"] == (
        "ideal_dilute_concentration_ratio_with_explicit_floor"
    )
    assert validation["details"]["solver_time_enforcement"] == (
        "block_unfavorable_forward_rate"
    )
    solver_summary = constrained.solver_metadata["dynamic_thermodynamics"]
    assert solver_summary["enabled"] is True
    assert solver_summary["constraint_count"] == 1
    assert solver_summary["rhs_enforcement"] == (
        "active_for_every_process_rate_evaluation"
    )

    output_dir = tmp_path / "constrained_output"
    summary = json.loads(
        (output_dir / "thermodynamic_summary.json").read_text(encoding="utf-8")
    )
    with (output_dir / "thermodynamic_summary.csv").open(
        newline="",
        encoding="utf-8",
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert summary["has_dynamic_reaction_quotient"] is True
    assert summary["has_electron_balance_binding"] is True
    assert summary["has_solver_time_enforcement"] is True
    assert summary["has_redox_standard_energy"] is False
    assert rows[-1]["name"] == "dynamic_thermodynamic_feasibility"
    assert rows[-1]["constraint_id"] == "a_to_b_dynamic"


def test_dynamic_redox_constraint_derives_standard_gibbs_and_enforces(
    tmp_path: Path,
) -> None:
    config = _dynamic_config(method="redox_potential")
    path = _write_config(tmp_path, config)
    loaded = load_model_config(path)
    result = run_configured_model(path, output_dir=tmp_path / "redox_output")

    assert loaded.thermodynamic_constraints[0].id == "a_to_b_dynamic"
    validation = _dynamic_validation(result.validation_report())
    assert validation["passed"] is True
    assert validation["details"]["standard_energy_method"] == "redox_potential"
    assert validation["details"]["standard_delta_gibbs"] == pytest.approx(
        -964.8533212
    )
    summary = json.loads(
        (tmp_path / "redox_output" / "thermodynamic_summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary["has_redox_standard_energy"] is True
    constraint = result.assembly_report.to_dict()[
        "dynamic_thermodynamic_constraints"
    ][0]
    assert constraint["standard_energy_method"] == "redox_potential"
    assert constraint["standard_redox_potential"]["units"] == "volt"
    assert constraint["electron_transfer_number"]["units"] == "dimensionless"
    assert constraint["faraday_constant"]["units"] == "coulomb / mole"


def test_dynamic_constraint_requires_passing_bound_electron_balance(
    tmp_path: Path,
) -> None:
    config = _dynamic_config(method="standard_delta_gibbs")
    config["chemistry_metadata"]["species"]["product_species"][
        "electron_equivalents"
    ] = 1.0

    with pytest.raises(
        ConfiguredModelExecutionError,
        match="requires a passing electron/redox check",
    ) as error:
        run_configured_model(_write_config(tmp_path, config))

    assert error.value.report.stage == "model_assembly"
    assert error.value.report.missing_capabilities == (
        "dynamic_thermodynamic_constraints",
    )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda config: config["reaction_metadata"][0][
                "electron_transfer_number"
            ].update({"value": 1.0}),
            "exactly match the explicit reaction metadata binding",
        ),
        (
            lambda config: config["balance_checks"][0].update(
                {"checks": ["electron"]}
            ),
            "requires its bound balance check to request the explicit 'redox'",
        ),
    ],
)
def test_dynamic_redox_constraint_requires_explicit_transfer_and_redox_binding(
    tmp_path: Path,
    mutate: Any,
    message: str,
) -> None:
    config = _dynamic_config(method="redox_potential")
    mutate(config)

    with pytest.raises(ConfiguredModelExecutionError, match=message):
        run_configured_model(_write_config(tmp_path, config))


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda config: config["thermodynamic_constraints"][0][
                "activity_model"
            ].update({"type": "inferred_activity"}),
            "unsupported activity_model.type",
        ),
        (
            lambda config: config["thermodynamic_constraints"][0]["temperature"].update(
                {"source": ""}
            ),
            "source must be nonblank",
        ),
        (
            lambda config: config["thermodynamic_constraints"][0]["temperature"].update(
                {"value": True}
            ),
            "value must be a finite numeric scalar",
        ),
        (
            lambda config: config["thermodynamic_constraints"][0].update(
                {"process_id": "not_assembled"}
            ),
            "unknown assembled process",
        ),
        (
            lambda config: config["initial_state"]["states"][
                "dissolved_substrate_amount"
            ].update({"units": "kilogram"}),
            "incompatible",
        ),
    ],
)
def test_dynamic_constraint_rejects_unsupported_or_missing_inputs(
    tmp_path: Path,
    mutate: Any,
    message: str,
) -> None:
    config = _dynamic_config(method="standard_delta_gibbs")
    mutate(config)

    with pytest.raises(ConfiguredModelExecutionError, match=message) as error:
        run_configured_model(_write_config(tmp_path, config))

    assert error.value.report.stage in {"configured_input_loading", "model_assembly"}


def _dynamic_config(*, method: str) -> dict[str, Any]:
    config = yaml.safe_load(BASE_CONFIG.read_text(encoding="utf-8"))
    config["name"] = f"toy dynamic thermodynamic {method} benchmark"
    config["time"] = {
        "start": {"value": 0.0, "units": "second"},
        "stop": {"value": 20.0, "units": "second"},
        "points": 41,
    }
    config["initial_state"]["states"] = {
        "dissolved_substrate_amount": {"value": 1.0, "units": "mM"},
        "released_product_amount": {"value": 0.0, "units": "mM"},
    }
    config["chemistry_metadata"] = {
        "species": {
            "substrate_species": {
                "name": "substrate_species",
                "electron_equivalents": 2.0,
                "electron_source": SOURCE,
                "source": SOURCE,
            },
            "product_species": {
                "name": "product_species",
                "electron_equivalents": 2.0,
                "electron_source": SOURCE,
                "source": SOURCE,
            },
        }
    }
    config["reaction_metadata"] = [
        {
            "id": "a_to_b_reaction",
            "name": "a_to_b_reaction",
            "source": SOURCE,
            "reactants": [
                {
                    "species": "substrate_species",
                    "state_name": "dissolved_substrate_amount",
                    "coefficient": 1.0,
                }
            ],
            "products": [
                {
                    "species": "product_species",
                    "state_name": "released_product_amount",
                    "coefficient": 1.0,
                }
            ],
        }
    ]
    if method == "redox_potential":
        config["reaction_metadata"][0]["electron_transfer_number"] = {
            "value": 2.0,
            "source": SOURCE,
        }
    config["balance_checks"] = [
        {
            "id": "a_to_b_electron_balance",
            "process_id": "a_to_b",
            "reaction_id": "a_to_b_reaction",
            "checks": ["redox" if method == "redox_potential" else "electron"],
            "required": True,
            "state_species": {
                "dissolved_substrate_amount": {
                    "species": "substrate_species",
                    "role": "reactant",
                },
                "released_product_amount": {
                    "species": "product_species",
                    "role": "product",
                },
            },
        }
    ]
    if method == "standard_delta_gibbs":
        standard_energy = {
            "method": method,
            "standard_delta_gibbs": _parameter(
                name="artificial standard Gibbs energy",
                symbol="delta_g_standard_ab",
                value=0.0,
                units="joule / mole",
            ),
        }
    elif method == "redox_potential":
        standard_energy = {
            "method": method,
            "standard_redox_potential": _parameter(
                name="artificial standard cell potential",
                symbol="e_standard_ab",
                value=0.005,
                units="volt",
            ),
            "electron_transfer_number": _parameter(
                name="artificial electron transfer number",
                symbol="n_e_ab",
                value=2.0,
                units="dimensionless",
            ),
            "faraday_constant": _parameter(
                name="Faraday constant",
                symbol="faraday_constant",
                value=96485.33212,
                units="coulomb / mole",
                source="2019 SI definition and CODATA Faraday constant.",
            ),
        }
    else:
        raise AssertionError(f"Unsupported test method {method!r}.")
    config["thermodynamic_constraints"] = [
        {
            "id": "a_to_b_dynamic",
            "process_id": "a_to_b",
            "reaction_id": "a_to_b_reaction",
            "electron_balance_check_id": "a_to_b_electron_balance",
            "enforcement_mode": "block_unfavorable_forward_rate",
            "standard_energy": standard_energy,
            "temperature": _parameter(
                name="test temperature",
                symbol="temperature_ab",
                value=303.15,
                units="kelvin",
            ),
            "gas_constant": _parameter(
                name="molar gas constant",
                symbol="gas_constant",
                value=8.31446261815324,
                units="joule / mole / kelvin",
                source="2019 SI definition and CODATA exact molar gas constant.",
            ),
            "activity_model": {
                "type": "ideal_dilute_concentration_ratio_with_explicit_floor",
                "standard_concentration": _parameter(
                    name="standard concentration",
                    symbol="c_standard_ab",
                    value=1.0,
                    units="mM",
                ),
                "minimum_activity": _parameter(
                    name="explicit numerical activity floor",
                    symbol="minimum_activity_ab",
                    value=1.0e-12,
                    units="dimensionless",
                ),
            },
            "absolute_tolerance": _parameter(
                name="dynamic Gibbs sign tolerance",
                symbol="delta_g_tolerance_ab",
                value=0.0,
                units="joule / mole",
            ),
            "provenance_refs": [
                "Artificial framework benchmark reaction metadata.",
                "Explicit test-only activity and thermodynamic parameter records.",
            ],
        }
    ]
    return config


def _parameter(
    *,
    name: str,
    symbol: str,
    value: float,
    units: str,
    source: str = SOURCE,
) -> dict[str, Any]:
    return {
        "name": name,
        "symbol": symbol,
        "value": value,
        "units": units,
        "uncertainty": 0.0,
        "source": source,
        "confidence_level": "testing",
        "notes": "Artificial software-contract value; not biological evidence.",
        "measurement_method": "defined framework benchmark value",
        "validity_range": "framework tests only",
    }


def _dynamic_validation(report: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [
        row
        for row in report
        if row["name"] == "dynamic_thermodynamic_feasibility"
    ]
    assert len(rows) == 1
    return rows[0]


def _write_config(
    tmp_path: Path,
    config: dict[str, Any],
    *,
    name: str = "dynamic.yml",
) -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path
