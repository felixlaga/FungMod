"""Minimal Stage 1 benchmark: closed first-order A -> B reaction.

This example is not a fungal or PET model. It exists to verify that the ODE
engine, unit handling, simulation record, and validators work on a known
closed reaction system before more complex biology is added.
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
from fungal_model.core.assumptions import Assumption
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.simulation import SimulationEngine, SimulationRecord
from fungal_model.core.units import Q_
from fungal_model.core.validators import validate_mass_balance, validate_non_negative


def build_engine() -> SimulationEngine:
    parameters = ParameterSet(
        [
            Parameter(
                name="first-order benchmark rate constant",
                symbol="k",
                value=0.1,
                units="1 / second",
                uncertainty=0.0,
                source="Analytical first-order benchmark selected for software validation; no physical claim.",
                confidence_level="testing",
                notes="This value is a defined numerical benchmark, not an experimentally measured fungal parameter.",
                measurement_method="defined benchmark value",
            )
        ]
    )
    assumption = Assumption(
        name="closed well-mixed first-order benchmark",
        description="A converts irreversibly to B with rate k[A] in a closed homogeneous system.",
        justification="Minimal model for testing ODE integration, dimensional consistency, and mass conservation.",
        known_limitations="Not a PET, enzyme, or fungal mechanism; should not be interpreted biologically.",
        source="Canonical first-order kinetics derivation.",
    )

    def rate_law(state, time, parameter_set):
        del time
        return parameter_set.require_quantity("k", "1 / second") * state["A"]

    reaction = Reaction(
        name="A to B first-order benchmark",
        reactants={"A": 1.0},
        products={"B": 1.0},
        rate_law=rate_law,
        rate_units="mole / liter / second",
        assumptions=[assumption],
        source="Canonical first-order kinetics derivation.",
        notes="Benchmark reaction for Stage 1 only.",
    )
    return SimulationEngine(
        reactions=[reaction],
        parameters=parameters,
        species_units={"A": "mole / liter", "B": "mole / liter"},
        assumptions=[assumption],
    )


def run(output_dir: Path = ROOT / "outputs" / "example_01_first_order") -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    engine = build_engine()
    result = engine.simulate(
        initial_state={"A": Q_(1.0, "mole / liter"), "B": Q_(0.0, "mole / liter")},
        t_span=(Q_(0, "second"), Q_(60, "second")),
        t_eval=Q_(np.linspace(0, 60, 241), "second"),
    )
    validations = [
        validate_non_negative(result),
        validate_mass_balance(result, conserved_weights={"A": 1.0, "B": 1.0}),
    ]
    validation_data = [validation.to_dict() for validation in validations]

    record = SimulationRecord.from_result(result, validation_summary=validation_data)
    record.to_json(output_dir / "simulation_record.json")
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
    plt.plot(time_seconds, result.species["A"].to("mole / liter").magnitude, label="A")
    plt.plot(time_seconds, result.species["B"].to("mole / liter").magnitude, label="B")
    plt.xlabel("time (s)")
    plt.ylabel("concentration (mol/L)")
    plt.title("Closed first-order benchmark: A -> B")
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / "concentrations.png", dpi=200)
    plt.close()

    print(f"Saved example outputs to {output_dir}")


if __name__ == "__main__":
    run()
