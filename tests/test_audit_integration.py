"""AUDIT-001 integration: the audit's new laws reach the public factory path and the compiled core.

Each case starts from the shipped framework benchmark
``toy_homogeneous_competitive_inhibition.yml`` (artificial states and
parameters, not scientific data), swaps or adds one modifier, writes the config
to a temporary file and runs it through :func:`run_configured_model`, so the
modifier is built by ``processes/factories.py`` and integrated by the compiled
core with the compiled Jacobian (``solver.jacobian: compiled``).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from fungal_model import run_configured_model
from fungal_model.core.numerics import JACOBIAN_COMPILED
from fungal_model.io.model_config import load_model_config
from fungal_model.processes import ProcessLibrary, default_foundation_factories
from fungal_model.solvers.compiled import (
    JACOBIAN_ANALYTIC,
    JACOBIAN_COMPILED_LABEL,
    JACOBIAN_FINITE_DIFFERENCE,
    KERNEL_NUMERIC,
)
from fungal_model.workflows.configured_model import ConfiguredInputLoader, ConfiguredProcessAssembler

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "data" / "model_configs" / "toy_homogeneous_competitive_inhibition.yml"
PROCESS_ID = "generic_competitive_conversion"
MIXED_SOURCE = "Cornish-Bowden A. 2012. Fundamentals of Enzyme Kinetics, 4th ed. Wiley-Blackwell."
SOLVER_BLOCK = {"method": "BDF", "rtol": 1e-10, "jacobian": JACOBIAN_COMPILED}
# Artificial cardinal water activities for the framework benchmark only.
AW_MIN, AW_OPT, AW_MAX = 0.90, 0.97, 1.0
ENVIRONMENT_WATER_ACTIVITY = 0.98  # data/environments/lab_30C_pH7.yml


def _benchmark() -> dict[str, Any]:
    data = yaml.safe_load(BENCHMARK.read_text(encoding="utf-8"))
    data["solver"] = dict(SOLVER_BLOCK)
    return data


def _run(tmp_path: Path, data: dict[str, Any], name: str):
    path = tmp_path / f"{name}.yml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return run_configured_model(path, output_dir=tmp_path / f"{name}_output")


def _metadata(tmp_path: Path, name: str) -> dict[str, Any]:
    return json.loads((tmp_path / f"{name}_output" / "configured_metadata.json").read_text(encoding="utf-8"))


def _benchmark_parameter(symbol: str, value: float, units: str, name: str) -> dict[str, Any]:
    return {
        "name": name,
        "symbol": symbol,
        "value": value,
        "units": units,
        "uncertainty": 0.0,
        "source": "FungMod AUDIT-001 integration benchmark.",
        "confidence_level": "testing",
        "notes": "Artificial value for framework verification only; not biological evidence.",
        "measurement_method": "defined benchmark value",
        "validity_range": "framework tests only",
    }


def _process(data: dict[str, Any]) -> dict[str, Any]:
    (process,) = data["processes"]
    return process


def _with_cardinal_water_activity(data: dict[str, Any]) -> dict[str, Any]:
    data = copy.deepcopy(data)
    data["parameters"][0]["parameters"].extend(
        [
            _benchmark_parameter("aw_min_benchmark", AW_MIN, "dimensionless", "benchmark minimum water activity"),
            _benchmark_parameter("aw_opt_benchmark", AW_OPT, "dimensionless", "benchmark optimum water activity"),
            _benchmark_parameter("aw_max_benchmark", AW_MAX, "dimensionless", "benchmark maximum water activity"),
        ]
    )
    # Without the inhibition modifier no process reads the inhibitor pool.
    del data["initial_state"]["states"]["inhibitor_pool"]
    for validator in data["validators"]:
        if "species" in validator:
            validator["species"] = [name for name in validator["species"] if name != "inhibitor_pool"]
    process = _process(data)
    process["modifiers"] = [
        {
            "type": "water_activity_cardinal_rosso",
            "minimum_water_activity": "aw_min_benchmark",
            "optimum_water_activity": "aw_opt_benchmark",
            "maximum_water_activity": "aw_max_benchmark",
            "source": "Rosso and Robinson 2001 Int J Food Microbiol 63:265 (form only; benchmark values).",
        }
    ]
    return data


def _cm2(x: float, x_min: float, x_opt: float, x_max: float) -> float:
    """Rosso et al. 1993 CM_2, written out independently of the package."""

    numerator = (x - x_max) * (x - x_min) ** 2
    denominator = (x_opt - x_min) * ((x_opt - x_min) * (x - x_opt) - (x_opt - x_max) * (x_opt + x_min - 2.0 * x))
    return numerator / denominator


def _michaelis_menten_rate(substrate: np.ndarray, *, vmax: float = 0.2, km: float = 0.5) -> np.ndarray:
    return vmax * substrate / (km + substrate)


def test_new_factories_and_laws_are_registered() -> None:
    types = set(ProcessLibrary.default_foundation().factory_types())
    assert {"endogenous_maintenance", "site_binding_surface_catalysis"} <= types
    assert len(types) == len(default_foundation_factories())


def test_mixed_inhibition_through_the_factory_matches_the_competitive_law_and_is_compiled(tmp_path: Path) -> None:
    competitive = _benchmark()
    mixed = copy.deepcopy(competitive)
    _process(mixed)["modifiers"] = [
        {
            "type": "mixed_inhibition",
            "substrate_state": "substrate_pool",
            "michaelis_constant": "K_m_competitive",
            "inhibitors": [
                {"state": "inhibitor_pool", "mechanism": "competitive", "competitive_constant": "K_i_competitive"}
            ],
            "primary_source": MIXED_SOURCE,
            "maturity": "literature_backed_software_tested",
        }
    ]
    reference = _run(tmp_path, competitive, "competitive")
    result = _run(tmp_path, mixed, "mixed")

    kernel = result.solver_metadata["kernel"]
    assert kernel["jacobian"] == JACOBIAN_COMPILED_LABEL
    assert kernel["process_kernels"][PROCESS_ID] == KERNEL_NUMERIC
    assert kernel["jacobian_kernels"][PROCESS_ID] == JACOBIAN_ANALYTIC
    assert result.solver_metadata["success"] is True
    # A purely competitive inhibitor in the general law is the competitive law.
    for state in ("substrate_pool", "product_pool", "inhibitor_pool"):
        np.testing.assert_allclose(
            result.state(state).to("mole / liter").magnitude,
            reference.state(state).to("mole / liter").magnitude,
            rtol=1e-8,
            atol=1e-12,
        )
    substrate = result.state("substrate_pool").to("mole / liter").magnitude
    rate = result.process_rates[PROCESS_ID].to("mole / liter / second").magnitude
    km, ki, inhibitor = 0.5, 0.25, 0.5
    expected = 0.2 * substrate / (km * (1.0 + inhibitor / ki) + substrate)
    np.testing.assert_allclose(rate, expected, rtol=1e-10)
    (row,) = _metadata(tmp_path, "mixed")["configured_process_modifiers"]
    assert row["type"] == "mixed_inhibition"
    assert row["maturity"] == "literature_backed_software_tested"
    assert "Cornish-Bowden" in row["law_source"]
    assert row["primary_source"] == MIXED_SOURCE


def test_mixed_inhibition_still_requires_a_michaelis_menten_base(tmp_path: Path) -> None:
    data = _benchmark()
    process = _process(data)
    process["modifiers"] = [
        {
            "type": "mixed_inhibition",
            "substrate_state": "substrate_pool",
            "michaelis_constant": "K_m_wrong_symbol",
            "inhibitors": [
                {"state": "inhibitor_pool", "mechanism": "competitive", "competitive_constant": "K_i_competitive"}
            ],
            "primary_source": MIXED_SOURCE,
            "maturity": "literature_backed_software_tested",
        }
    ]
    with pytest.raises(Exception, match="michaelis_constant must exactly match"):
        _run(tmp_path, data, "mismatched")


def test_cardinal_water_activity_through_the_factory_scales_the_compiled_rate(tmp_path: Path) -> None:
    result = _run(tmp_path, _with_cardinal_water_activity(_benchmark()), "water_activity")

    kernel = result.solver_metadata["kernel"]
    assert kernel["jacobian"] == JACOBIAN_COMPILED_LABEL
    assert kernel["process_kernels"][PROCESS_ID] == KERNEL_NUMERIC
    assert kernel["jacobian_kernels"][PROCESS_ID] in {JACOBIAN_ANALYTIC, JACOBIAN_FINITE_DIFFERENCE}
    gamma = _cm2(ENVIRONMENT_WATER_ACTIVITY, AW_MIN, AW_OPT, AW_MAX)
    assert gamma == pytest.approx(0.0128 / 0.014, rel=1e-12)
    substrate = result.state("substrate_pool").to("mole / liter").magnitude
    rate = result.process_rates[PROCESS_ID].to("mole / liter / second").magnitude
    np.testing.assert_allclose(rate, gamma * _michaelis_menten_rate(substrate), rtol=1e-10)
    # The modifier's own parameters and limitation reach the assembled process.
    path = tmp_path / "water_activity.yml"
    config = load_model_config(path)
    model = ConfiguredProcessAssembler().assemble(config, ConfiguredInputLoader().load(config)).model
    (process,) = model.processes
    required = {requirement.symbol: requirement.units for requirement in process.required_parameters}
    for symbol in ("aw_min_benchmark", "aw_opt_benchmark", "aw_max_benchmark"):
        assert required[symbol] == "dimensionless"
    assert any("Rosso-Robinson cardinal model" in text for text in process.validity.limitations)
    (row,) = _metadata(tmp_path, "water_activity")["configured_process_modifiers"]
    assert row["environment_value"] == "water_activity"
    assert row["maturity"] == "literature_backed_software_tested"
    assert "Rosso" in row["law_source"] and "Rosso-Robinson" in row["limitation"]


def test_two_water_activity_laws_need_the_explicit_stacking_opt_in(tmp_path: Path) -> None:
    data = _with_cardinal_water_activity(_benchmark())
    data["parameters"][0]["parameters"].append(
        _benchmark_parameter("aw_threshold_benchmark", 0.85, "dimensionless", "benchmark water activity threshold")
    )
    _process(data)["modifiers"].append(
        {"type": "water_activity_threshold", "minimum_water_activity": "aw_threshold_benchmark"}
    )
    with pytest.raises(Exception, match="allow_stacked_condition_laws"):
        _run(tmp_path, data, "stacked_refused")

    quoted = copy.deepcopy(data)
    _process(quoted)["allow_stacked_condition_laws"] = "true"
    with pytest.raises(Exception, match="must be a boolean"):
        _run(tmp_path, quoted, "stacked_quoted")

    _process(data)["allow_stacked_condition_laws"] = True
    result = _run(tmp_path, data, "stacked_allowed")
    assert result.solver_metadata["success"] is True


def test_driving_force_mode_records_its_factor_series_and_assumptions(tmp_path: Path) -> None:
    from fungal_model.kinetics.arrhenius import UNIVERSAL_GAS_CONSTANT
    from tests.test_dynamic_thermodynamic_enforcement import _dynamic_config, _write_config
    from tests.test_thermodynamic_driving_force import _driving_force_config

    driving = run_configured_model(
        _write_config(tmp_path, _driving_force_config(stop_seconds=20.0), name="driving.yml"),
        output_dir=tmp_path / "driving_output",
    )
    prefix = "dynamic_thermodynamics.a_to_b_dynamic"
    factor = driving.derived_quantities[f"{prefix}.driving_force_factor"].to("dimensionless").magnitude
    delta_g = driving.derived_quantities[f"{prefix}.delta_gibbs"].to("joule / mole").magnitude
    rt = float(UNIVERSAL_GAS_CONSTANT.value) * 303.15  # temperature_ab of the shared fixture
    np.testing.assert_allclose(factor, -np.expm1(delta_g / rt), rtol=1e-12, atol=1e-15)
    assert driving.solver_metadata["kernel"]["process_kernels"]["a_to_b"] == "numeric_thermodynamic"
    assert any(item.name.endswith(".driving_force_flux_force") for item in driving.assumptions)
    validation = next(
        item for item in driving.validation_results if item.name == "dynamic_thermodynamic_feasibility"
    )
    assert "driving-force factor" in validation.message

    block = run_configured_model(
        _write_config(tmp_path, _dynamic_config(method="standard_delta_gibbs"), name="block.yml"),
        output_dir=tmp_path / "block_output",
    )
    assert f"{prefix}.driving_force_factor" not in block.derived_quantities
