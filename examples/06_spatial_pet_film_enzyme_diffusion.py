"""Stage 8 benchmark: 1D PET film with enzyme diffusion.

This example uses the Stage 8 reaction-diffusion engine. A fixed enzyme
concentration is imposed at the left boundary of a 1D film, enzyme diffuses
through the domain, and local PET surface hydrolysis proceeds according to the
Stage 4 surface model.

All numerical values are artificial software-validation values. They are not
literature-calibrated PET degradation or enzyme diffusion parameters.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

MPL_CACHE = Path("/private/tmp/fungmod-matplotlib")
MPL_CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPL_CACHE))

import matplotlib.pyplot as plt

from fungal_model.chemistry.reactions import Reaction
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_
from fungal_model.core.validators import validate_non_negative
from fungal_model.kinetics.surface_kinetics import PETSurfaceHydrolysisRateLaw
from fungal_model.results import SimulationResult as StandardSimulationResult
from fungal_model.substrates.pet import PETSubstrate, make_pet_parameter_set
from fungal_model.transport.geometry import BoundaryCondition, BoundaryConditions1D, UniformGrid1D
from fungal_model.transport.reaction_diffusion import (
    ReactionDiffusionEngine1D,
    ReactionDiffusionRecord,
)
from fungal_model.validation.spatial import validate_no_flux_spatial_integral_conserved


def benchmark_parameter(
    *,
    name: str,
    symbol: str,
    value,
    units: str,
    notes: str,
) -> Parameter:
    return Parameter(
        name=name,
        symbol=symbol,
        value=value,
        units=units,
        uncertainty=0.0 if value is not None else None,
        source="Artificial Stage 8 spatial benchmark value; no physical or literature-calibrated claim.",
        confidence_level="testing",
        notes=notes,
        measurement_method="defined benchmark value",
    )


def build_grid() -> UniformGrid1D:
    return UniformGrid1D(
        length=benchmark_parameter(
            name="toy PET film thickness domain length",
            symbol="L_film",
            value=1.0e-3,
            units="meter",
            notes="Artificial 1D spatial domain length for the Stage 8 benchmark.",
        ),
        n_cells=30,
    )


def build_pet() -> PETSubstrate:
    return PETSubstrate(
        geometry_type="film",
        parameters=make_pet_parameter_set(
            [
                benchmark_parameter(
                    name="toy per-cell accessible PET surface area",
                    symbol="A_accessible",
                    value=1.0e-4,
                    units="meter ** 2",
                    notes=(
                        "Artificial per-cell accessible surface area for the "
                        "Stage 8 local surface hydrolysis benchmark."
                    ),
                )
            ]
        ),
        notes="Artificial Stage 8 per-cell PET film substrate metadata.",
    )


def build_engine(grid: UniformGrid1D, pet: PETSubstrate) -> ReactionDiffusionEngine1D:
    parameters = ParameterSet(
        [
            benchmark_parameter(
                name="toy enzyme diffusion coefficient",
                symbol="D_E",
                value=1.0e-10,
                units="meter ** 2 / second",
                notes="Artificial enzyme diffusion coefficient for Stage 8 benchmark.",
            ),
            benchmark_parameter(
                name="toy PET adsorption equilibrium constant",
                symbol="K_ads",
                value=1.0e6,
                units="liter / mole",
                notes="Artificial Langmuir adsorption constant for spatial benchmark.",
            ),
            benchmark_parameter(
                name="toy PET surface hydrolysis constant",
                symbol="k_surface",
                value=1.0e-9,
                units="kilogram / meter ** 2 / second",
                notes="Artificial surface hydrolysis constant for spatial benchmark.",
            ),
        ]
    )
    rate_law = PETSurfaceHydrolysisRateLaw(
        pet=pet,
        enzyme="E",
        pet_mass="PET",
        adsorption_symbol="K_ads",
        surface_rate_symbol="k_surface",
        rate_units="kilogram / second",
        enzyme_units="mole / liter",
    )
    reaction = Reaction(
        name="local PET hydrolysis by diffusing enzyme",
        reactants={"PET": 1.0},
        products={"hydrolysate": 1.0},
        rate_law=rate_law,
        rate_units="kilogram / second",
        assumptions=rate_law.assumptions,
        source="Stage 8 benchmark coupling local surface PET hydrolysis to enzyme diffusion.",
        notes="Each cell uses the PET metadata accessible area as a per-cell benchmark area.",
    )
    return ReactionDiffusionEngine1D(
        grid=grid,
        field_units={
            "PET": "kilogram",
            "hydrolysate": "kilogram",
            "E": "mole / liter",
        },
        boundary_conditions={
            "PET": BoundaryConditions1D.no_flux(),
            "hydrolysate": BoundaryConditions1D.no_flux(),
            "E": BoundaryConditions1D(
                left=BoundaryCondition("fixed_value", Q_(1.0e-6, "mole / liter")),
                right=BoundaryCondition("no_flux"),
            ),
        },
        parameters=parameters,
        reactions=[reaction],
        diffusion_symbols={"PET": None, "hydrolysate": None, "E": "D_E"},
        assumptions=rate_law.assumptions,
    )


def run(output_dir: Path = ROOT / "outputs" / "example_06_spatial_pet_film_enzyme_diffusion") -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    grid = build_grid()
    pet = build_pet()
    engine = build_engine(grid, pet)
    result = engine.simulate(
        initial_fields={
            "PET": Q_(np.full(grid.n_cells, 1.0e-6), "kilogram"),
            "hydrolysate": Q_(np.zeros(grid.n_cells), "kilogram"),
            "E": Q_(np.zeros(grid.n_cells), "mole / liter"),
        },
        t_span=(Q_(0.0, "second"), Q_(2000.0, "second")),
        t_eval=Q_(np.linspace(0.0, 2000.0, 201), "second"),
    )
    combined_mass = result.fields["PET"] + result.fields["hydrolysate"].to("kilogram")
    mass_adapter = type(
        "SpatialMassAdapter",
        (),
        {
            "fields": {"PET_plus_hydrolysate": combined_mass},
            "grid": result.grid,
        },
    )()
    validations = [
        validate_non_negative(type("SpatialNonNegativeAdapter", (), {"species": result.fields})()),
        validate_no_flux_spatial_integral_conserved(
            mass_adapter,
            field="PET_plus_hydrolysate",
            relative_tolerance=Q_(1e-8, "dimensionless"),
        ),
    ]
    validation_data = [validation.to_dict() for validation in validations]

    ReactionDiffusionRecord.from_result(result, validation_summary=validation_data).to_json(
        output_dir / "simulation_record.json"
    )
    (output_dir / "substrate.json").write_text(
        json.dumps(pet.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "validation_report.json").write_text(
        json.dumps(validation_data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "assumptions.json").write_text(
        json.dumps([assumption.to_dict() for assumption in result.assumptions], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    StandardSimulationResult.from_reaction_diffusion_result(
        result,
        validation_results=validations,
        name="example_06_spatial_pet_film_enzyme_diffusion",
        label="toy",
    ).save(output_dir)

    x_mm = grid.coordinates.to("millimeter").magnitude
    time_seconds = result.time.to("second").magnitude
    fig, axes = plt.subplots(2, 1, figsize=(7, 7), sharex=False)
    enzyme_image = axes[0].imshow(
        result.fields["E"].to("mole / liter").magnitude,
        aspect="auto",
        origin="lower",
        extent=[x_mm[0], x_mm[-1], time_seconds[0], time_seconds[-1]],
    )
    axes[0].set_ylabel("time (s)")
    axes[0].set_title("Diffusing enzyme concentration (mol/L)")
    fig.colorbar(enzyme_image, ax=axes[0], label="mol/L")
    axes[1].plot(x_mm, result.field_at_final_time("PET").to("kilogram").magnitude, label="PET")
    axes[1].plot(
        x_mm,
        result.field_at_final_time("hydrolysate").to("kilogram").magnitude,
        label="hydrolysate",
    )
    axes[1].set_xlabel("position (mm)")
    axes[1].set_ylabel("mass per cell (kg)")
    axes[1].legend()
    fig.suptitle("Stage 8 1D PET film with enzyme diffusion")
    fig.tight_layout()
    fig.savefig(output_dir / "spatial_pet_film.png", dpi=200)
    plt.close(fig)

    print(f"Saved example outputs to {output_dir}")


if __name__ == "__main__":
    run()
