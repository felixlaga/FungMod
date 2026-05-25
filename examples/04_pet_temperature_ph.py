"""Stage 5 benchmark: PET surface hydrolysis with temperature and pH modifiers.

This example composes the Stage 4 PET surface model with Arrhenius temperature
scaling and a Gaussian pH activity profile. All values are artificial benchmark
values for software validation; they are not literature-calibrated PET
degradation parameters.
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
from fungal_model.kinetics.arrhenius import ArrheniusReferenceTemperatureScaler
from fungal_model.kinetics.ph import GaussianPHActivityProfile
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
        source="Artificial Stage 5 benchmark value; no physical or literature-calibrated claim.",
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
                    notes="Artificial film area for Stage 5 benchmark.",
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
        notes="Artificial Stage 5 PET temperature/pH benchmark substrate.",
    )


def build_parameters() -> ParameterSet:
    return ParameterSet(
        [
            benchmark_parameter(
                name="toy PET adsorption equilibrium constant",
                symbol="K_ads",
                value=1.0,
                units="liter / mole",
                notes="Artificial Langmuir adsorption constant.",
            ),
            benchmark_parameter(
                name="toy PET reference surface hydrolysis constant",
                symbol="k_surface",
                value=2.0e-7,
                units="kilogram / meter ** 2 / second",
                notes="Artificial surface rate constant at T_ref.",
            ),
            benchmark_parameter(
                name="toy activation energy",
                symbol="Ea",
                value=40.0,
                units="kilojoule / mole",
                notes="Artificial activation energy for Arrhenius benchmark.",
            ),
            benchmark_parameter(
                name="toy reference temperature",
                symbol="T_ref",
                value=300.0,
                units="kelvin",
                notes="Reference temperature for k_surface.",
            ),
            benchmark_parameter(
                name="toy environmental temperature",
                symbol="T",
                value=315.0,
                units="kelvin",
                notes="Benchmark simulation temperature inside the artificial validity range.",
            ),
            benchmark_parameter(
                name="toy minimum measured temperature",
                symbol="T_min",
                value=290.0,
                units="kelvin",
                notes="Lower artificial validity bound for Arrhenius benchmark.",
            ),
            benchmark_parameter(
                name="toy maximum measured temperature",
                symbol="T_max",
                value=330.0,
                units="kelvin",
                notes="Upper artificial validity bound for Arrhenius benchmark.",
            ),
            benchmark_parameter(
                name="toy environmental pH",
                symbol="pH",
                value=7.5,
                units="dimensionless",
                notes="Benchmark pH inside the artificial validity range.",
            ),
            benchmark_parameter(
                name="toy optimum pH",
                symbol="pH_opt",
                value=7.0,
                units="dimensionless",
                notes="Artificial optimum pH for Gaussian activity benchmark.",
            ),
            benchmark_parameter(
                name="toy pH Gaussian width",
                symbol="pH_sigma",
                value=1.0,
                units="dimensionless",
                notes="Artificial width for Gaussian pH activity benchmark.",
            ),
            benchmark_parameter(
                name="toy minimum measured pH",
                symbol="pH_min",
                value=5.0,
                units="dimensionless",
                notes="Lower artificial pH validity bound.",
            ),
            benchmark_parameter(
                name="toy maximum measured pH",
                symbol="pH_max",
                value=9.0,
                units="dimensionless",
                notes="Upper artificial pH validity bound.",
            ),
        ]
    )


def build_engine(pet: PETSubstrate, parameters: ParameterSet) -> SimulationEngine:
    temperature_scaler = ArrheniusReferenceTemperatureScaler(
        activation_energy_symbol="Ea",
        reference_temperature_symbol="T_ref",
        temperature_symbol="T",
        minimum_temperature_symbol="T_min",
        maximum_temperature_symbol="T_max",
        source="Artificial Stage 5 temperature validity range.",
    )
    ph_profile = GaussianPHActivityProfile(
        ph_symbol="pH",
        optimum_symbol="pH_opt",
        width_symbol="pH_sigma",
        minimum_ph_symbol="pH_min",
        maximum_ph_symbol="pH_max",
        source="Artificial Stage 5 pH validity range.",
    )
    rate_law = PETSurfaceHydrolysisRateLaw(
        pet=pet,
        enzyme="E",
        pet_mass="PET",
        adsorption_symbol="K_ads",
        surface_rate_symbol="k_surface",
        rate_units="kilogram / second",
        enzyme_units="mole / liter",
        temperature_scaler=temperature_scaler,
        ph_profile=ph_profile,
    )
    reaction = Reaction(
        name="temperature and pH scaled PET surface hydrolysis",
        reactants={"PET": 1.0},
        products={"hydrolysate": 1.0},
        rate_law=rate_law,
        rate_units="kilogram / second",
        assumptions=rate_law.assumptions,
        source="Stage 5 modelling assumption: Arrhenius and pH modifiers applied to PET surface hydrolysis.",
        notes="The product state is a mass-equivalent lump, not resolved PET hydrolysis chemistry.",
    )
    return SimulationEngine(
        reactions=[reaction],
        parameters=parameters,
        species_units={
            "PET": "kilogram",
            "hydrolysate": "kilogram",
            "E": "mole / liter",
        },
        assumptions=rate_law.assumptions,
    )


def run(output_dir: Path = ROOT / "outputs" / "example_04_pet_temperature_ph") -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    pet = build_pet()
    parameters = build_parameters()
    engine = build_engine(pet, parameters)
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
    plt.title("Stage 5 PET hydrolysis with temperature and pH modifiers")
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / "masses.png", dpi=200)
    plt.close()

    print(f"Saved example outputs to {output_dir}")


if __name__ == "__main__":
    run()
