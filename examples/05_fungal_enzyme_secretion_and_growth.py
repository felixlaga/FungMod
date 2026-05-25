"""Stage 6 benchmark: fungal enzyme secretion coupled to PET hydrolysis.

This example is a minimal living-system benchmark. A toy fungus secretes a
PET-active enzyme, pays an active-biomass cost for secretion, loses active
biomass to maintenance, and can grow only from explicitly assimilable lumped
hydrolysate.

All numerical values are artificial software-validation values. They are not
literature-calibrated fungal or PET degradation parameters.
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
from fungal_model.fungi import (
    BiomassMaintenanceRateLaw,
    EnzymeCapability,
    EnzymeDecayRateLaw,
    EnzymeProductionCostRateLaw,
    EnzymeProfile,
    EnzymeSecretionRateLaw,
    Fungus,
    ProductAssimilation,
    ProductUptakeRateLaw,
    biomass_yield_coefficient,
    make_fungal_parameter_set,
)
from fungal_model.kinetics.surface_kinetics import PETSurfaceHydrolysisRateLaw
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
        source="Artificial Stage 6 benchmark value; no physical or literature-calibrated claim.",
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
                    notes="Artificial film area for Stage 6 benchmark.",
                ),
                benchmark_parameter(
                    name="toy PET roughness factor",
                    symbol="r_rough",
                    value=1.2,
                    units="dimensionless",
                    notes="Artificial roughness factor for accessible-area calculation.",
                ),
                benchmark_parameter(
                    name="toy PET crystallinity fraction",
                    symbol="chi_c",
                    value=0.35,
                    units="dimensionless",
                    notes="Artificial crystallinity for accessible-area calculation.",
                ),
            ]
        ),
        notes="Artificial Stage 6 fungal PET benchmark substrate.",
    )


def build_fungus() -> Fungus:
    profile = EnzymeProfile(
        capabilities=(
            EnzymeCapability(
                name="toy secreted PET-active hydrolase",
                enzyme_class="PETase-like hydrolase",
                target_substrate="polyethylene terephthalate",
                target_bond_type="ester",
                evidence="Artificial Stage 6 benchmark capability.",
                source="Artificial Stage 6 benchmark metadata.",
                notes="No species-specific claim.",
            ),
        ),
        source="Artificial Stage 6 benchmark metadata.",
        notes="No genome, transcriptome, or secretome claim.",
    )
    parameters = make_fungal_parameter_set(
        [
            benchmark_parameter(
                name="toy minimum growth temperature",
                symbol="T_growth_min",
                value=290.0,
                units="kelvin",
                notes="Artificial growth-range lower bound.",
            ),
            benchmark_parameter(
                name="toy maximum growth temperature",
                symbol="T_growth_max",
                value=320.0,
                units="kelvin",
                notes="Artificial growth-range upper bound.",
            ),
            benchmark_parameter(
                name="toy minimum growth pH",
                symbol="pH_growth_min",
                value=5.0,
                units="dimensionless",
                notes="Artificial pH lower bound.",
            ),
            benchmark_parameter(
                name="toy maximum growth pH",
                symbol="pH_growth_max",
                value=8.0,
                units="dimensionless",
                notes="Artificial pH upper bound.",
            ),
            benchmark_parameter(
                name="toy minimum water activity",
                symbol="a_w_min",
                value=0.9,
                units="dimensionless",
                notes="Artificial water activity lower bound.",
            ),
            benchmark_parameter(
                name="toy enzyme secretion coefficient",
                symbol="alpha_E",
                value=1.0e-3,
                units="mole / liter / kilogram / second",
                notes="Artificial active-biomass secretion coefficient.",
            ),
            benchmark_parameter(
                name="toy extracellular enzyme decay constant",
                symbol="delta_E",
                value=1.0e-3,
                units="1 / second",
                notes="Artificial enzyme decay constant.",
            ),
            benchmark_parameter(
                name="toy enzyme secretion active biomass cost",
                symbol="c_E",
                value=1.0e-4,
                units="kilogram / (mole / liter)",
                notes="Artificial cost per secreted enzyme concentration.",
            ),
            benchmark_parameter(
                name="toy active biomass maintenance constant",
                symbol="m_B",
                value=1.0e-6,
                units="1 / second",
                notes="Artificial maintenance loss constant.",
            ),
            benchmark_parameter(
                name="toy hydrolysate uptake coefficient",
                symbol="q_product",
                value=100.0,
                units="1 / kilogram / second",
                notes="Artificial lumped product uptake coefficient.",
            ),
            benchmark_parameter(
                name="toy biomass yield on hydrolysate",
                symbol="Y_B",
                value=0.5,
                units="dimensionless",
                notes="Artificial biomass yield; remaining mass is untracked open-system flux.",
            ),
        ]
    )
    fungus = Fungus(
        species_name="Toy PET-active fungus",
        enzyme_profile=profile,
        parameters=parameters,
        known_substrates=("polyethylene terephthalate",),
        oxygen_requirement="aerobic assumed but oxygen is not modelled in Stage 6",
        moisture_requirement="requires sufficient water activity; water field is not modelled in Stage 6",
        notes="Artificial metadata for Stage 6 benchmark.",
        references=("Artificial Stage 6 benchmark metadata.",),
    )
    fungus.validate(require_parameter_values=True)
    return fungus


def build_engine(pet: PETSubstrate, fungus: Fungus) -> SimulationEngine:
    surface_parameters = ParameterSet(
        [
            benchmark_parameter(
                name="toy PET adsorption equilibrium constant",
                symbol="K_ads",
                value=1.0e6,
                units="liter / mole",
                notes="Artificial adsorption constant to make the benchmark visible.",
            ),
            benchmark_parameter(
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
    assimilation = ProductAssimilation(
        product="hydrolysate",
        assimilable=True,
        source="Artificial Stage 6 benchmark assumption.",
        notes="The lumped hydrolysate is assumed assimilable only for this benchmark.",
    )
    uptake = ProductUptakeRateLaw(
        product="hydrolysate",
        active_biomass="B_active",
        uptake_symbol="q_product",
        assimilation=assimilation,
        rate_units="kilogram / second",
    )
    yield_value = biomass_yield_coefficient(parameters=parameters, yield_symbol="Y_B")
    reactions = [
        Reaction(
            name="PET hydrolysis by secreted enzyme",
            reactants={"PET": 1.0},
            products={"hydrolysate": 1.0},
            rate_law=pet_hydrolysis,
            rate_units="kilogram / second",
            assumptions=pet_hydrolysis.assumptions,
            source="Stage 6 benchmark coupling PET surface hydrolysis to fungal enzyme.",
        ),
        Reaction(
            name="active biomass enzyme secretion",
            reactants={},
            products={"E": 1.0},
            rate_law=secretion,
            rate_units="mole / liter / second",
            assumptions=secretion.assumptions,
            source="Stage 6 benchmark enzyme secretion.",
        ),
        Reaction(
            name="enzyme secretion active biomass cost",
            reactants={"B_active": 1.0},
            products={"B_dead": 1.0},
            rate_law=secretion_cost,
            rate_units="kilogram / second",
            assumptions=secretion_cost.assumptions,
            source="Stage 6 benchmark enzyme cost.",
        ),
        Reaction(
            name="extracellular enzyme decay",
            reactants={"E": 1.0},
            products={},
            rate_law=decay,
            rate_units="mole / liter / second",
            assumptions=decay.assumptions,
            source="Stage 6 benchmark enzyme decay.",
        ),
        Reaction(
            name="active biomass maintenance",
            reactants={"B_active": 1.0},
            products={"B_dead": 1.0},
            rate_law=maintenance,
            rate_units="kilogram / second",
            assumptions=maintenance.assumptions,
            source="Stage 6 benchmark maintenance.",
        ),
        Reaction(
            name="assimilable hydrolysate uptake",
            reactants={"hydrolysate": 1.0},
            products={"B_active": yield_value},
            rate_law=uptake,
            rate_units="kilogram / second",
            assumptions=uptake.assumptions,
            source="Stage 6 benchmark product assimilation.",
            notes="Unassimilated mass is an untracked open-system flux at this stage.",
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


def run(output_dir: Path = ROOT / "outputs" / "example_05_fungal_enzyme_secretion_and_growth") -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    pet = build_pet()
    fungus = build_fungus()
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
    axes[2].plot(time_seconds, result.species["B_dormant"].to("kilogram").magnitude, label="dormant biomass")
    axes[2].set_xlabel("time (s)")
    axes[2].set_ylabel("biomass (kg)")
    axes[2].legend()
    fig.suptitle("Stage 6 fungal enzyme secretion and product-coupled growth benchmark")
    fig.tight_layout()
    fig.savefig(output_dir / "fungal_dynamics.png", dpi=200)
    plt.close(fig)

    print(f"Saved example outputs to {output_dir}")


if __name__ == "__main__":
    run()

