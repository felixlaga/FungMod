"""PET plugin workflow helpers built on the generic configured runner."""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from fungal_model.core.units import Q_, require_quantity
from fungal_model.resources import example_data_path
from fungal_model.results import SimulationResult
from fungal_model.workflows import run_configured_model

from .loaders import pet_substrate_loader_registry

DATA = example_data_path()
DEFAULT_MODEL_CONFIG = example_data_path("model_configs/toy_surface_pet_plugin.yml")


@dataclass(frozen=True)
class PETSurfaceWorkflowConfig:
    """PET plugin convenience config that rewrites the generic model config."""

    model_config_path: Path = DEFAULT_MODEL_CONFIG
    substrate_path: Path = DATA / "substrates" / "pet_film.yml"
    enzyme_path: Path = DATA / "enzymes" / "petase_like.yml"
    fungus_path: Path = DATA / "fungi" / "toy_pet_fungus.yml"
    environment_path: Path = DATA / "environments" / "lab_30C_pH7.yml"
    geometry_path: Path = DATA / "geometries" / "well_mixed_100ml.yml"
    parameters_path: Path = DATA / "parameters" / "pet_surface_benchmark.yml"
    initial_pet_mass: Any = Q_(1.0e-4, "kilogram")
    initial_product_mass: Any = Q_(0.0, "kilogram")
    initial_enzyme: Any = Q_(1.0, "mole / liter")
    duration: Any = Q_(20.0, "second")
    n_time_points: int = 41

    @classmethod
    def default(cls) -> "PETSurfaceWorkflowConfig":
        return cls()


def run_pet_surface_integration(
    output_dir: str | Path,
    *,
    config: PETSurfaceWorkflowConfig | None = None,
) -> SimulationResult:
    """Run the PET plugin benchmark through the generic configured workflow."""

    warnings.warn(
        (
            "This PET plugin convenience helper is deprecated; call "
            "run_configured_model with pet_substrate_loader_registry() for new code."
        ),
        DeprecationWarning,
        stacklevel=2,
    )
    resolved_config = _write_resolved_model_config(
        Path(output_dir),
        config or PETSurfaceWorkflowConfig.default(),
    )
    return run_configured_model(
        resolved_config,
        output_dir=output_dir,
        substrate_registry=pet_substrate_loader_registry(),
    )


def _write_resolved_model_config(output_dir: Path, config: PETSurfaceWorkflowConfig) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    data = yaml.safe_load(config.model_config_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Model config {config.model_config_path} did not produce a mapping.")

    data["entities"]["substrates"][0]["path"] = str(config.substrate_path)
    data["entities"]["enzymes"][0]["path"] = str(config.enzyme_path)
    data["entities"]["fungus"]["path"] = str(config.fungus_path)
    data["entities"]["environment"]["path"] = str(config.environment_path)
    data["entities"]["geometry"]["path"] = str(config.geometry_path)
    data["parameters"][0]["path"] = str(config.parameters_path)
    data["initial_state"]["states"]["solid_polymer_amount"] = _quantity_mapping(
        config.initial_pet_mass,
        name="initial_pet_mass",
    )
    data["initial_state"]["states"]["released_product_amount"] = _quantity_mapping(
        config.initial_product_mass,
        name="initial_product_mass",
    )
    data["initial_state"]["states"]["free_catalyst_concentration"] = _quantity_mapping(
        config.initial_enzyme,
        name="initial_enzyme",
    )
    data["time"]["stop"] = _quantity_mapping(config.duration, name="duration")
    data["time"]["points"] = int(config.n_time_points)

    path = output_dir / "resolved_model_config.yml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def _quantity_mapping(value: Any, *, name: str) -> dict[str, Any]:
    quantity = require_quantity(value, name=name)
    return {
        "value": _jsonable_magnitude(quantity.magnitude),
        "units": str(quantity.units),
    }


def _jsonable_magnitude(value: Any) -> Any:
    array = np.asarray(value)
    if array.ndim == 0:
        return array.item()
    return array.tolist()


__all__ = ["PETSurfaceWorkflowConfig", "run_pet_surface_integration"]
