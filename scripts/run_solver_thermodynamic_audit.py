"""Reproducible solver/data comparison plus explicitly artificial thermodynamic verification."""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import platform

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import scipy

from fungal_model.chemistry import (DetailedBalanceNetwork, DetailedBalanceReaction, ElementalComposition,
                                    MacrochemicalBalance, MacrochemicalSpecies)
from fungal_model.core.numerics import SolverSettings
from fungal_model.core.parameters import Parameter
from fungal_model.core.units import Q_
from fungal_model.research.gelain_culture import CultureBenchmarkError, parameters_from_records
from fungal_model.research.gelain_joint import load_joint_cultures
from fungal_model.research.gelain_models import DISPLAY_UNITS, OBSERVABLE_UNITS, simulate_candidate

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = Path("data/benchmarks/gelain_2020_v2")
ARTIFICIAL = "Artificial thermodynamic verification coefficients; not measurements or fungal predictions."
METHODS = ("LSODA", "BDF", "Radau", "DOP853")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+"\n")


def artificial_network():
    """Three artificial isomers, including a closed cycle; no organism claim."""
    def p(name, value, units):
        return Parameter(name=name, symbol=name, value=value, units=units, uncertainty=None,
                         source=ARTIFICIAL, confidence_level="testing", notes=ARTIFICIAL)
    species = tuple(MacrochemicalSpecies(name, ElementalComposition.from_formula("C2H4", source=ARTIFICIAL),
        0, ARTIFICIAL, formation_gibbs=p(f"mu_{name}", energy, "J/mol"))
        for name, energy in (("A", 0), ("B", -1000), ("C", -2000)))
    reactions = tuple(DetailedBalanceReaction(f"{a}_to_{b}", {a: 1}, {b: 1}, p(f"k{i}", rate, "mol/L/s"), ARTIFICIAL)
                      for i, (a, b, rate) in enumerate((("A", "B", .3), ("B", "C", .1), ("C", "A", .2))))
    return DetailedBalanceNetwork(balance=MacrochemicalBalance("artificial cycle", species, ARTIFICIAL,
        thermodynamic_conditions="Artificial ideal-dilute common standard state at 300 K; no experimental claim"),
        reactions=reactions, temperature=p("T", 300, "K"), gas_constant=p("R", 8.31446261815324, "J/mol/K"),
        standard_concentration=p("c_standard", 1, "mol/L"))


def plot_thermodynamics(output):
    model = artificial_network()
    initial = {"A": Q_(.8, "mol/L"), "B": Q_(.15, "mol/L"), "C": Q_(.05, "mol/L")}
    equilibrium = model.equilibrium(initial)
    result = model.simulate(initial_state=initial, times=Q_(np.linspace(0, 30, 401), "s"),
        solver_settings=SolverSettings(method="Radau", rtol=1e-10, atol={n: Q_(1e-12, "mol/L") for n in model.names}))
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.6), layout="constrained")
    for name, value in result.concentrations.items():
        line, = axes[0].plot(result.time.magnitude, value.magnitude, label=name)
        axes[0].axhline(equilibrium["concentrations"][name].magnitude, color=line.get_color(), ls=":", alpha=.5)
    axes[0].set(title="Closed cycle → independently solved equilibrium", ylabel="Concentration (mol/L)")
    axes[0].legend()
    axes[1].plot(result.time.magnitude, result.free_energy_density.magnitude-equilibrium["free_energy_density"].magnitude)
    axes[1].set(title="Available chemical free energy decreases", ylabel="f − f equilibrium (J/L)")
    entropy = result.entropy_production_density
    assert entropy is not None
    axes[2].plot(result.time.magnitude, entropy.magnitude)
    axes[2].set(title="Entropy production remains nonnegative", ylabel="Entropy production (J/L/K/s)")
    for ax in axes:
        ax.set_xlabel("Time (s)")
        ax.grid(alpha=.2)
    fig.suptitle("Physical-law verification · artificial coefficients · NOT biological data", fontsize=13)
    fig.savefig(output/"thermodynamic_relaxation.png", dpi=170)
    plt.close(fig)
    summary = dict(result.diagnostics, equilibrium={n: float(v.magnitude) for n, v in equilibrium["concentrations"].items()},
                   equilibrium_residual=equilibrium["maximum_scaled_residual"], provenance=result.provenance,
                   empirical_validation=False)
    write_json(output/"thermodynamic_verification.json", summary)
    columns = np.column_stack([result.time.magnitude, *[v.magnitude for v in result.concentrations.values()],
                               result.free_energy_density.magnitude, entropy.magnitude])
    np.savetxt(output/"thermodynamic_trajectory.csv", columns, delimiter=",",
               header="time_s,A_mol_L,B_mol_L,C_mol_L,free_energy_J_L,entropy_production_J_L_K_s", comments="")
    return summary


def refined_controls(condition, model, method):
    units = {name: OBSERVABLE_UNITS[name] for name in condition.names}
    if model in {"retained", "hydrolysis_retained"}:
        units["retained_mass"] = "g/L"
    elif model == "published" and condition.design.family == "cellulose":
        units["induction"] = "dimensionless"
    return SolverSettings(method=method, rtol=1e-10,
        atol={n: Q_(1e-14 if n == "substrate" else 1e-12, u) for n, u in units.items()}, max_step=Q_(.1, "hour"))


def replay_record(condition, frozen):
    """Freeze training-only parameters; score all solvers on the same held-out observations."""
    fit = frozen["fit"]
    if condition.design.condition_id in fit["training_conditions"] or not fit["success"]:
        raise ValueError("Invalid held-out fit binding.")
    if frozen["observables"] != list(condition.names) or frozen["times_h"] != condition.design.times.to("hour").magnitude.tolist():
        raise ValueError("Frozen prediction observations/times changed; review evidence before replay.")
    parameters = parameters_from_records(fit["parameters"])
    results, attempts = {}, {}
    for method in METHODS:
        # Preserve the initial outcome; refinement is explicit, never a hidden retry.
        try:
            original = simulate_candidate(condition.design, condition.initial_activities, parameters,
                model=fit["model"], hypothesis_source=fit["hypothesis_source"], method=method, rtol=1e-10, atol=1e-12)
            attempts[method] = {"success": True, "solver": original.solver}
        except CultureBenchmarkError as error:
            attempts[method] = {"success": False, "error": str(error), "method": method, "rtol": 1e-10, "atol": 1e-12}
        result = simulate_candidate(condition.design, condition.initial_activities, parameters,
            model=fit["model"], hypothesis_source=fit["hypothesis_source"],
            solver_settings=refined_controls(condition, fit["model"], method))
        results[method] = result
    reference = results["DOP853"].values
    scale = np.asarray(fit["normalization"])
    rows = []
    for method, result in results.items():
        error = result.values-condition.values
        rows.append({"condition": condition.design.condition_id, "model": fit["model"], "family": fit["family"],
            "scenario": fit["scenario"], "method": method, "solver": result.solver, "initial_attempt": attempts[method],
            "max_scaled_difference_from_DOP853": float(np.max(abs(result.values-reference)/scale)),
            "max_scaled_difference_from_frozen": float(np.max(abs(result.values-np.asarray(frozen["predictions"]))/scale)),
            "scaled_data_rmse": float(np.sqrt(np.mean((error/scale)**2))),
            "rmse": dict(zip(condition.names, np.sqrt(np.mean(error**2, axis=0)).tolist(), strict=True)),
            "predictions": result.values.tolist(), "times_h": result.times.magnitude.tolist(),
            "training_conditions": fit["training_conditions"], "empirical_validation": False})
    return rows, parameters


def run(root: Path, output: Path):
    if output.exists() and any(output.iterdir()):
        raise ValueError("Choose an empty output directory; prior evidence is not overwritten.")
    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False, "font.size": 10})
    conditions = {c.design.condition_id: c for c in load_joint_cultures(root)}
    rows, inputs, selected = [], {}, {}
    for path in sorted((root/BENCHMARK/"results/frozen_predictions").glob("*.json")):
        frozen = json.loads(path.read_text())
        condition = conditions[frozen["condition"]]
        replayed, parameters = replay_record(condition, frozen)
        rows.extend(replayed)
        inputs[str(path.relative_to(root))] = digest(path)
        if frozen["fit"]["model"] == "published" and frozen["fit"]["scenario"] == "primary":
            selected[condition.design.condition_id] = (frozen, parameters)
    for family in ("glycerol", "cellulose"):
        group = [c for c in conditions.values() if c.design.family == family]
        fig, axes = plt.subplots(len(group[0].names), 3, figsize=(14, 3*len(group[0].names)),
                                 squeeze=False, layout="constrained")
        for column, condition in enumerate(group):
            frozen, parameters = selected[condition.design.condition_id]
            design = replace(condition.design, times=Q_(np.linspace(0, float(condition.design.times.magnitude[-1]), 401), "h"))
            for method, style in (("LSODA", "-"), ("DOP853", "--")):
                prediction = simulate_candidate(design, condition.initial_activities, parameters, model="published",
                    hypothesis_source=frozen["fit"]["hypothesis_source"],
                    solver_settings=refined_controls(condition, "published", method))
                for row, name in enumerate(condition.names):
                    ax = axes[row, column]
                    ax.plot(prediction.times.magnitude, prediction.values[:, row], style, label=f"Held-out {method}")
            for row, name in enumerate(condition.names):
                ax = axes[row, column]
                ax.scatter(condition.design.times.magnitude, condition.values[:, row], color="black", s=25, zorder=5,
                           label="Published means")
                ax.set(title=f"{float(condition.design.initial_substrate.magnitude):g} g/L initial · {name.replace('_', ' ')}",
                       xlabel="Time (h)", ylabel=DISPLAY_UNITS[name])
                ax.grid(alpha=.2)
                if row == column == 0:
                    ax.legend(fontsize=8)
        fig.suptitle(f"Gelain 2020 · {family} · predictions trained on the other two conditions\n"
                     "Retrospective holdout; measured SD and raw replicates unavailable; solver curves overlap", fontsize=13)
        fig.savefig(output/f"{family}_data_comparison.png", dpi=160)
        plt.close(fig)
    fig, ax = plt.subplots(figsize=(10, 4.8), layout="constrained")
    data = [r["scaled_data_rmse"] for r in rows if r["method"] == "DOP853"]
    differences = [r["max_scaled_difference_from_DOP853"] for r in rows if r["method"] != "DOP853"]
    ax.scatter(np.arange(len(data)), data, label="Data RMSE / training scale", marker="o", s=24)
    maximum_by_fold = [max(r["max_scaled_difference_from_DOP853"] for r in rows[i:i+4]) for i in range(0,len(rows),4)]
    ax.scatter(np.arange(len(data)), maximum_by_fold, label="Maximum solver difference / training scale", marker="x", s=28)
    ax.set(yscale="log", xlabel="Frozen held-out model/condition/scenario", ylabel="Dimensionless error",
           title="Model–data discrepancies versus numerical disagreement")
    ax.legend()
    ax.grid(alpha=.2)
    fig.savefig(output/"numerical_vs_data_error.png", dpi=170)
    plt.close(fig)
    thermo = plot_thermodynamics(output)
    pooled = []
    for family, model, scenario in sorted({(r["family"], r["model"], r["scenario"]) for r in rows}):
        group = [r for r in rows if (r["family"],r["model"],r["scenario"],r["method"]) == (family,model,scenario,"DOP853")]
        pooled.append({"family": family, "model": model, "scenario": scenario,
                       "pooled_rmse": {name: float(np.sqrt(np.mean([r["rmse"][name]**2 for r in group]))) for name in group[0]["rmse"]}})
    for path in (root/BENCHMARK/"observations.json", root/BENCHMARK/"plan.json"):
        inputs[str(path.relative_to(root))] = digest(path)
    implementation = {str(p.relative_to(root)): digest(p) for p in [Path(__file__),
        *sorted((root/"src/fungal_model").rglob("*.py"))]}
    summary = {"schema_version": "1.0.0", "frozen_holdouts": len(rows)//4, "integrations": len(rows)*2,
        "initial_failed_integrations": sum(not r["initial_attempt"]["success"] for r in rows),
        "refined_successful_integrations": len(rows),
        "refinement": "All methods: explicit state tolerances (substrate 1e-14 g/L; others 1e-12 canonical units), max step 0.1 h. No clipping.",
        "unique_observations": sum(c.values.size for c in conditions.values()),
        "max_scaled_solver_difference": max(differences), "pooled_rmse": pooled,
        "max_scaled_difference_from_frozen": max(r["max_scaled_difference_from_frozen"] for r in rows),
        "new_parameters_fitted": 0, "new_empirical_data_added": False, "empirical_validation": False,
        "thermodynamic_culture_predictions": "unavailable: no matched formation energies, gas exchange or calorimetry",
        "source": "https://doi.org/10.17632/shd3wcczsr.2", "input_sha256": inputs,
        "implementation_sha256": implementation, "software": {"python": platform.python_version(),
            "numpy": np.__version__, "scipy": scipy.__version__, "matplotlib": matplotlib.__version__},
        "artificial_thermodynamic_verification": {k: v for k,v in thermo.items() if k != "provenance"}}
    write_json(output/"solver_replays.json", rows)
    write_json(output/"summary.json", summary)
    write_json(output/"artifact_sha256.json", {p.name: digest(p) for p in sorted(output.iterdir()) if p.is_file()})
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(ROOT, args.output)
    print(json.dumps({k: report[k] for k in ("frozen_holdouts", "integrations", "unique_observations",
        "max_scaled_solver_difference", "max_scaled_difference_from_frozen", "pooled_rmse")}, indent=2))
