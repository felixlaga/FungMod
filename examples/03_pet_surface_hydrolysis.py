"""Stage 4 benchmark: surface-limited PET hydrolysis by fixed enzyme.

This example uses artificial benchmark values to exercise the heterogeneous
surface model. It is not a fitted PET degradation prediction and should not be
read as a literature-calibrated degradation rate.
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
from fungal_model.core.simulation import SimulationEngine, SimulationRecord
from fungal_model.core.units import Q_
from fungal_model.core.validators import validate_mass_balance, validate_non_negative
from fungal_model.kinetics.surface_kinetics import (
    PETSurfaceHydrolysisRateLaw,
    pet_surface_hydrolysis_assumption,
)
from fungal_model.results import SimulationResult as StandardSimulationResult
from fungal_model.substrates.pet import PETSubstrate, make_pet_parameter_set


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
        source="Artificial Stage 4 benchmark value; no physical or literature-calibrated claim.",
        confidence_level="testing",
        notes=notes,
        measurement_method="defined benchmark value",
    )


def build_pet() -> PETSubstrate:
    return PETSubstrate(
        geometry_type="film",
        parameters=make_pet_parameter_set(
            [
                benchmark_parameter(
                    name="toy PET geometric surface area",
                    symbol="A_surface",
                    value=0.25,
                    units="meter ** 2",
                    notes="Artificial film area used to exercise surface-area dependence.",
                ),
                benchmark_parameter(
                    name="toy PET roughness factor",
                    symbol="r_rough",
                    value=1.2,
                    units="dimensionless",
                    notes="Artificial roughness factor used to derive accessible surface area.",
                ),
                benchmark_parameter(
                    name="toy PET crystallinity fraction",
                    symbol="chi_c",
                    value=0.35,
                    units="dimensionless",
                    notes="Artificial crystallinity used only for the benchmark accessible-area calculation.",
                ),
            ]
        ),
        notes="Artificial Stage 4 PET surface hydrolysis benchmark substrate.",
    )


def build_engine(pet: PETSubstrate) -> SimulationEngine:
    parameters = ParameterSet(
        [
            benchmark_parameter(
                name="toy PET adsorption equilibrium constant",
                symbol="K_ads",
                value=1.0,
                units="liter / mole",
                notes="Artificial Langmuir adsorption constant for benchmark coverage.",
            ),
            benchmark_parameter(
                name="toy PET surface hydrolysis constant",
                symbol="k_surface",
                value=2.0e-7,
                units="kilogram / meter ** 2 / second",
                notes="Artificial surface hydrolysis constant for benchmark dynamics.",
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
        name="PET surface hydrolysis to lumped mass-equivalent products",
        reactants={"PET": 1.0},
        products={"hydrolysate": 1.0},
        rate_law=rate_law,
        rate_units="kilogram / second",
        assumptions=rate_law.assumptions,
        source="Stage 4 modelling assumption: Langmuir coverage times accessible PET surface area.",
        notes="The product state is a mass-equivalent lump, not resolved MHET/BHET/TPA/EG chemistry.",
    )
    return SimulationEngine(
        reactions=[reaction],
        parameters=parameters,
        species_units={
            "PET": "kilogram",
            "hydrolysate": "kilogram",
            "E": "mole / liter",
        },
        assumptions=[pet_surface_hydrolysis_assumption(), *pet.assumptions],
    )


def run(output_dir: Path = ROOT / "outputs" / "example_03_pet_surface_hydrolysis") -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    pet = build_pet()
    engine = build_engine(pet)
    result = engine.simulate(
        initial_state={
            "PET": Q_(1.0e-4, "kilogram"),
            "hydrolysate": Q_(0.0, "kilogram"),
            "E": Q_(1.0, "mole / liter"),
        },
        t_span=(Q_(0.0, "second"), Q_(600.0, "second")),
        t_eval=Q_(np.linspace(0.0, 600.0, 301), "second"),
    )
    validations = [
        validate_non_negative(result),
        validate_mass_balance(result, conserved_weights={"PET": 1.0, "hydrolysate": 1.0}),
    ]
    validation_data = [validation.to_dict() for validation in validations]

    SimulationRecord.from_result(result, validation_summary=validation_data).to_json(
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
    StandardSimulationResult.from_ode_result(
        result,
        validation_results=validations,
        name="example_03_pet_surface_hydrolysis",
        label="toy",
    ).save(output_dir, mass_balance_weights={"PET": 1.0, "hydrolysate": 1.0})

    time_seconds = result.time.to("second").magnitude
    plt.figure(figsize=(7, 4))
    plt.plot(time_seconds, result.species["PET"].to("kilogram").magnitude, label="PET")
    plt.plot(
        time_seconds,
        result.species["hydrolysate"].to("kilogram").magnitude,
        label="hydrolysate mass equivalent",
    )
    plt.xlabel("time (s)")
    plt.ylabel("mass (kg)")
    plt.title("Stage 4 PET surface hydrolysis benchmark")
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / "masses.png", dpi=200)
    plt.close()

    print(f"Saved example outputs to {output_dir}")


if __name__ == "__main__":
    run()
