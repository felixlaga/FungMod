"""Stage 12 example 4: fungus secretes PET-active enzyme without growth.

This benchmark introduces fungal enzyme secretion while deliberately excluding
growth from PET hydrolysis products. Hydrolysate accumulates as an extracellular
product pool, active biomass pays secretion and maintenance costs, and no
assimilation reaction is present.

All numerical values are artificial software-validation values. They are not
literature-calibrated fungal or PET degradation parameters.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np

from stage12_common import ROOT, load_example_module

SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

MPL_CACHE = Path("/private/tmp/fungmod-matplotlib")
MPL_CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPL_CACHE))

import matplotlib.pyplot as plt

from fungal_model.chemistry.reactions import Reaction
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.simulation import SimulationEngine, SimulationRecord
from fungal_model.core.units import Q_
from fungal_model.core.validators import (
    ValidationResult,
    validate_mass_balance,
    validate_non_negative,
)
from fungal_model.fungi import (
    BiomassMaintenanceRateLaw,
    EnzymeDecayRateLaw,
    EnzymeProductionCostRateLaw,
    EnzymeSecretionRateLaw,
)
from fungal_model.kinetics.surface_kinetics import PETSurfaceHydrolysisRateLaw

STAGE6_SOURCE = load_example_module(
    "05_fungal_enzyme_secretion_and_growth.py",
    "stage12_source_fungal_enzyme_secretion_no_growth",
)


def build_engine(pet, fungus) -> SimulationEngine:
    surface_parameters = ParameterSet(
        [
            STAGE6_SOURCE.benchmark_parameter(
                name="toy PET adsorption equilibrium constant",
                symbol="K_ads",
                value=1.0e6,
                units="liter / mole",
                notes="Artificial adsorption constant to make the no-growth benchmark visible.",
            ),
            STAGE6_SOURCE.benchmark_parameter(
                name="toy PET surface hydrolysis constant",
                symbol="k_surface",
                value=1.0e-8,
                units="kilogram / meter ** 2 / second",
                notes="Artificial surface hydrolysis constant.",
            ),
        ]
    )
    parameters = ParameterSet([*fungus.parameters, *surface_parameters])
    pet_hydrolysis = PETSurfaceHydrolysisRateLaw(
        pet=pet,
        enzyme="E",
        pet_mass="PET",
        adsorption_symbol="K_ads",
        surface_rate_symbol="k_surface",
        rate_units="kilogram / second",
        enzyme_units="mole / liter",
    )
    secretion = EnzymeSecretionRateLaw(
        active_biomass="B_active",
        secretion_symbol="alpha_E",
        rate_units="mole / liter / second",
    )
    secretion_cost = EnzymeProductionCostRateLaw(
        active_biomass="B_active",
        secretion_symbol="alpha_E",
        secretion_cost_symbol="c_E",
        enzyme_rate_units="mole / liter / second",
        biomass_rate_units="kilogram / second",
    )
    decay = EnzymeDecayRateLaw(
        enzyme="E",
        decay_symbol="delta_E",
        rate_units="mole / liter / second",
        enzyme_units="mole / liter",
    )
    maintenance = BiomassMaintenanceRateLaw(
        active_biomass="B_active",
        maintenance_symbol="m_B",
        rate_units="kilogram / second",
    )
    reactions = [
        Reaction(
            name="PET hydrolysis by secreted enzyme without assimilation",
            reactants={"PET": 1.0},
            products={"hydrolysate": 1.0},
            rate_law=pet_hydrolysis,
            rate_units="kilogram / second",
            assumptions=pet_hydrolysis.assumptions,
            source="Stage 12 example 4 coupling PET surface hydrolysis to secreted fungal enzyme.",
            notes="Hydrolysate is not assimilated in this example.",
        ),
        Reaction(
            name="active biomass enzyme secretion",
            reactants={},
            products={"E": 1.0},
            rate_law=secretion,
            rate_units="mole / liter / second",
            assumptions=secretion.assumptions,
            source="Stage 12 example 4 enzyme secretion.",
        ),
        Reaction(
            name="enzyme secretion active biomass cost",
            reactants={"B_active": 1.0},
            products={"B_dead": 1.0},
            rate_law=secretion_cost,
            rate_units="kilogram / second",
            assumptions=secretion_cost.assumptions,
            source="Stage 12 example 4 enzyme cost.",
        ),
        Reaction(
            name="extracellular enzyme decay",
            reactants={"E": 1.0},
            products={},
            rate_law=decay,
            rate_units="mole / liter / second",
            assumptions=decay.assumptions,
            source="Stage 12 example 4 enzyme decay.",
        ),
        Reaction(
            name="active biomass maintenance",
            reactants={"B_active": 1.0},
            products={"B_dead": 1.0},
            rate_law=maintenance,
            rate_units="kilogram / second",
            assumptions=maintenance.assumptions,
            source="Stage 12 example 4 maintenance.",
        ),
    ]
    assumptions = []
    for item in [*fungus.assumptions, *pet.assumptions, *[a for r in reactions for a in r.assumptions]]:
        if item.name not in {assumption.name for assumption in assumptions}:
            assumptions.append(item)
    return SimulationEngine(
        reactions=reactions,
        parameters=parameters,
        species_units={
            "PET": "kilogram",
            "hydrolysate": "kilogram",
            "E": "mole / liter",
            "B_active": "kilogram",
            "B_dormant": "kilogram",
            "B_dead": "kilogram",
        },
        assumptions=assumptions,
    )


def validate_no_growth(result) -> ValidationResult:
    active = result.species["B_active"].to("kilogram").magnitude
    initial = float(active[0])
    maximum = float(np.max(active))
    return ValidationResult(
        name="no_positive_growth_without_assimilation",
        passed=maximum <= initial,
        message=(
            "Active biomass did not increase because no assimilation reaction was present."
            if maximum <= initial
            else "Active biomass increased despite no assimilation reaction."
        ),
        details={
            "initial_active_biomass_kg": initial,
            "maximum_active_biomass_kg": maximum,
            "final_active_biomass_kg": float(active[-1]),
        },
    )


def run(output_dir: Path = ROOT / "outputs" / "stage12_04_fungal_enzyme_secretion") -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    pet = STAGE6_SOURCE.build_pet()
    fungus = STAGE6_SOURCE.build_fungus()
    engine = build_engine(pet, fungus)
    result = engine.simulate(
        initial_state={
            "PET": Q_(1.0e-4, "kilogram"),
            "hydrolysate": Q_(0.0, "kilogram"),
            "E": Q_(0.0, "mole / liter"),
            "B_active": Q_(1.0e-3, "kilogram"),
            "B_dormant": Q_(0.0, "kilogram"),
            "B_dead": Q_(0.0, "kilogram"),
        },
        t_span=(Q_(0.0, "second"), Q_(1000.0, "second")),
        t_eval=Q_(np.linspace(0.0, 1000.0, 501), "second"),
    )
    validations = [
        validate_non_negative(result),
        validate_mass_balance(result, closed_system=False),
        validate_no_growth(result),
    ]
    validation_data = [validation.to_dict() for validation in validations]
    SimulationRecord.from_result(result, validation_summary=validation_data).to_json(
        output_dir / "simulation_record.json"
    )
    (output_dir / "substrate.json").write_text(
        json.dumps(pet.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "fungus.json").write_text(
        json.dumps(fungus.to_dict(), indent=2, sort_keys=True) + "\n",
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

    time_seconds = result.time.to("second").magnitude
    fig, axes = plt.subplots(3, 1, figsize=(7, 8), sharex=True)
    axes[0].plot(time_seconds, result.species["PET"].to("kilogram").magnitude, label="PET")
    axes[0].plot(
        time_seconds,
        result.species["hydrolysate"].to("kilogram").magnitude,
        label="hydrolysate",
    )
    axes[0].set_ylabel("mass (kg)")
    axes[0].legend()
    axes[1].plot(time_seconds, result.species["E"].to("mole / liter").magnitude, label="active enzyme")
    axes[1].set_ylabel("enzyme (mol/L)")
    axes[1].legend()
    axes[2].plot(time_seconds, result.species["B_active"].to("kilogram").magnitude, label="active biomass")
    axes[2].plot(time_seconds, result.species["B_dead"].to("kilogram").magnitude, label="dead biomass")
    axes[2].set_xlabel("time (s)")
    axes[2].set_ylabel("biomass (kg)")
    axes[2].legend()
    fig.suptitle("Stage 12 example 4: enzyme secretion without product-driven growth")
    fig.tight_layout()
    fig.savefig(output_dir / "fungal_enzyme_secretion_no_growth.png", dpi=200)
    plt.close(fig)

    print(f"Saved example outputs to {output_dir}")


if __name__ == "__main__":
    run()
