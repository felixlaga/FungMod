"""First config-driven PET surface integration workflow."""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from fungal_model.core.errors import MissingParameterError
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.provenance import UnknownParameterError
from fungal_model.core.simulation import SimulationEngine
from fungal_model.core.units import Q_
from fungal_model.core.validators import validate_mass_balance, validate_non_negative
from fungal_model.io import (
    export_json,
    load_enzyme,
    load_environment,
    load_fungus,
    load_geometry,
    load_parameter_set,
    load_substrate,
)
from fungal_model.kinetics.surface_kinetics import PETSurfaceHydrolysisRateLaw
from fungal_model.plugins.pet import pet_substrate_loader_registry
from fungal_model.processes import (
    AssemblyReport,
    ModelAssemblyContext,
    ModelBuilder,
    ParameterIssue,
    ProcessRegistry,
)
from fungal_model.results import SimulationResult

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data"


@dataclass(frozen=True)
class PETSurfaceWorkflowConfig:
    """Config paths and initial conditions for the first integration workflow."""

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
        return cls(substrate_path=DATA / "substrates" / "pet_film.yml")


def run_pet_surface_integration(
    output_dir: str | Path,
    *,
    config: PETSurfaceWorkflowConfig | None = None,
) -> SimulationResult:
    """Run the first registry-assembled PET surface workflow."""

    warnings.warn(
        (
            "This substrate-specific integration workflow is deprecated; use "
            "the generic configured-model API for new workflow code."
        ),
        DeprecationWarning,
        stacklevel=2,
    )
    config = config or PETSurfaceWorkflowConfig.default()
    substrate = load_substrate(
        config.substrate_path,
        registry=pet_substrate_loader_registry(),
    )
    enzyme = load_enzyme(config.enzyme_path)
    fungus = load_fungus(config.fungus_path)
    environment = load_environment(config.environment_path)
    geometry = load_geometry(config.geometry_path)
    parameters = load_parameter_set(config.parameters_path)

    try:
        substrate.require_accessible_surface_area()
    except UnknownParameterError as exc:
        report = AssemblyReport(
            context=ModelAssemblyContext(
                fungus=fungus,
                substrates=(substrate,),
                enzymes=(enzyme,),
                environment=environment,
                geometry=geometry,
                requested_processes=("surface_catalysis",),
            ),
            missing_parameters=(
                ParameterIssue(
                    symbol="A_accessible",
                    process_name="PET surface catalysis workflow",
                    expected_units="meter ** 2",
                    reason="unknown_value",
                    message=str(exc),
                    supplied_units="meter ** 2",
                ),
            ),
        )
        raise MissingParameterError("Workflow assembly failed: missing PET accessible surface.", report=report) from exc

    rate_law = PETSurfaceHydrolysisRateLaw(
        pet=substrate,
        enzyme="E",
        pet_mass="PET",
        adsorption_symbol="K_ads",
        surface_rate_symbol="k_surface",
        rate_units="kilogram / second",
        enzyme_units="mole / liter",
    )
    process = rate_law.as_generic_process(product_state="hydrolysate")
    model = ModelBuilder(
        fungus=fungus,
        substrates=[substrate],
        enzymes=[enzyme],
        environment=environment,
        geometry=geometry,
        process_library=ProcessRegistry([process]),
        requested_processes=("surface_catalysis",),
        parameters=parameters,
    ).assemble()

    engine = SimulationEngine(
        reactions=[process.as_reaction()],
        parameters=parameters,
        species_units={
            "PET": "kilogram",
            "hydrolysate": "kilogram",
            "E": "mole / liter",
        },
        assumptions=list(model.assumptions),
    )
    time_eval = Q_(
        np.linspace(0.0, float(config.duration.to("second").magnitude), config.n_time_points),
        "second",
    )
    raw = engine.simulate(
        initial_state={
            "PET": config.initial_pet_mass,
            "hydrolysate": config.initial_product_mass,
            "E": config.initial_enzyme,
        },
        t_span=(Q_(0.0, "second"), config.duration),
        t_eval=time_eval,
    )
    validations = [
        validate_non_negative(raw),
        validate_mass_balance(raw, conserved_weights={"PET": 1.0, "hydrolysate": 1.0}),
    ]
    process_rates = _process_rate_trajectory(process, raw, parameters)
    result = SimulationResult.from_ode_result(
        raw,
        validation_results=validations,
        process_rates={"surface_catalysis": process_rates},
        assembly_report=model.assembly_report,
        name="pet_surface_integration",
        label="toy",
    )
    output = Path(output_dir)
    result.save(output, mass_balance_weights={"PET": 1.0, "hydrolysate": 1.0})
    export_json(
        {
            "substrate_path": str(config.substrate_path),
            "enzyme_path": str(config.enzyme_path),
            "fungus_path": str(config.fungus_path),
            "environment_path": str(config.environment_path),
            "geometry_path": str(config.geometry_path),
            "parameters_path": str(config.parameters_path),
        },
        output / "input_configs.json",
    )
    export_json(substrate.to_dict(), output / "substrate.json")
    export_json(enzyme.to_dict(), output / "enzyme.json")
    export_json(fungus.to_dict(), output / "fungus.json")
    export_json(environment.to_dict(), output / "environment.json")
    export_json(geometry.to_dict(), output / "geometry.json")
    return result


def _process_rate_trajectory(process: Any, raw: Any, parameters: ParameterSet):
    values = []
    for index in range(len(raw.time.magnitude)):
        time = Q_(raw.time.magnitude[index], raw.time.units)
        state = {
            name: Q_(quantity.magnitude[index], quantity.units)
            for name, quantity in raw.species.items()
        }
        values.append(process.rate(state, time, parameters).to("kilogram / second").magnitude)
    return Q_(np.asarray(values, dtype=float), "kilogram / second")


__all__ = ["PETSurfaceWorkflowConfig", "run_pet_surface_integration"]
