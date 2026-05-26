"""Stage 2 benchmark: homogeneous Michaelis-Menten degradation of a toy substrate.

This is a dissolved-substrate benchmark for the kinetics layer. It is not a PET
model and should not be interpreted as surface-limited polymer hydrolysis.
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

from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.simulation import SimulationEngine, SimulationRecord
from fungal_model.core.units import Q_
from fungal_model.core.validators import validate_mass_balance, validate_non_negative
from fungal_model.processes import HomogeneousMichaelisMentenProcess
from fungal_model.results import SimulationResult as StandardSimulationResult


def build_engine() -> SimulationEngine:
    parameters = ParameterSet(
        [
            Parameter(
                name="toy dissolved-substrate Michaelis constant",
                symbol="Km",
                value=0.5,
                units="mole / liter",
                uncertainty=0.0,
                source="Artificial Stage 2 benchmark value; no physical or PET claim.",
                confidence_level="testing",
                notes="Chosen only to exercise the homogeneous Michaelis-Menten solver path.",
                measurement_method="defined benchmark value",
            ),
            Parameter(
                name="toy dissolved-substrate maximum rate",
                symbol="Vmax",
                value=0.02,
                units="mole / liter / second",
                uncertainty=0.0,
                source="Artificial Stage 2 benchmark value; no physical or PET claim.",
                confidence_level="testing",
                notes="Chosen only to exercise the homogeneous Michaelis-Menten solver path.",
                measurement_method="defined benchmark value",
            ),
        ]
    )
    process = HomogeneousMichaelisMentenProcess(
        name="toy dissolved substrate hydrolysis benchmark",
        substrate_state="S",
        product_state="P",
        vmax_symbol="Vmax",
        km_symbol="Km",
        rate_units="mole / liter / second",
        substrate_units="mole / liter",
        source="Canonical Michaelis-Menten dissolved-substrate benchmark.",
        notes="Not a PET surface model.",
    )
    return SimulationEngine(
        reactions=[process.as_reaction()],
        parameters=parameters,
        species_units={"S": "mole / liter", "P": "mole / liter"},
        assumptions=list(process.assumptions),
    )


def run(output_dir: Path = ROOT / "outputs" / "example_02_homogeneous_michaelis_menten") -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    engine = build_engine()
    result = engine.simulate(
        initial_state={"S": Q_(2.0, "mole / liter"), "P": Q_(0.0, "mole / liter")},
        t_span=(Q_(0.0, "second"), Q_(180.0, "second")),
        t_eval=Q_(np.linspace(0.0, 180.0, 361), "second"),
    )
    validations = [
        validate_non_negative(result),
        validate_mass_balance(result, conserved_weights={"S": 1.0, "P": 1.0}),
    ]
    validation_data = [validation.to_dict() for validation in validations]

    SimulationRecord.from_result(result, validation_summary=validation_data).to_json(
        output_dir / "simulation_record.json"
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
        name="example_02_homogeneous_michaelis_menten",
        label="toy",
    ).save(output_dir, mass_balance_weights={"S": 1.0, "P": 1.0})

    time_seconds = result.time.to("second").magnitude
    plt.figure(figsize=(7, 4))
    plt.plot(time_seconds, result.species["S"].to("mole / liter").magnitude, label="S")
    plt.plot(time_seconds, result.species["P"].to("mole / liter").magnitude, label="P")
    plt.xlabel("time (s)")
    plt.ylabel("concentration (mol/L)")
    plt.title("Homogeneous Michaelis-Menten toy benchmark")
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / "concentrations.png", dpi=200)
    plt.close()

    print(f"Saved example outputs to {output_dir}")


if __name__ == "__main__":
    run()
