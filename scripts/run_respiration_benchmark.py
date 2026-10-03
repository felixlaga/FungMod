"""Offline new-data challenge and explicit exploratory culture demonstrations."""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
from itertools import product
import json
from pathlib import Path
import platform

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import scipy

from fungal_model.core.numerics import SolverSettings
from fungal_model.core.parameters import Parameter
from fungal_model.core.units import Q_
from fungal_model.fungi import ResourceLimitedCulture
from fungal_model.research.respiration_benchmark import fit_pirt, lameiras_glucose_model, load_respiration_data

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "Lameiras et al. 2015, doi:10.1007/s11306-015-0781-z, Table 2 UNRECONCILED rates."
ASSUMPTION = "Explicit illustrative kinetic/operating assumption, not measured or fitted. No empirical trajectory claim."
OBSERVABLES = {"substrate_uptake": ("glucose", -1, "Glucose uptake"),
               "oxygen_uptake": ("oxygen", -1, "Oxygen uptake"),
               "carbon_dioxide_release": ("carbon_dioxide", 1, "Carbon dioxide release")}
COLORS = {"growth_only": "#8795a3", "growth_maintenance": "#007f86"}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def fit_records(records, maintenance):
    return fit_pirt(growth_rates=Q_([r["dilution_per_h"] for r in records], "1/h"),
                    substrate_uptake=Q_([r["unreconciled"]["substrate_uptake"]["value"] for r in records], "1/h"),
                    condition_ids=[r["id"] for r in records], source=SOURCE, include_maintenance=maintenance)


def holdouts(data):
    records = data["lameiras_2015"]["records"]
    predictions = []
    for i, target in enumerate(records):
        training = [r for j, r in enumerate(records) if j != i]
        for name, maintenance in (("growth_only", False), ("growth_maintenance", True)):
            fit = fit_records(training, maintenance)
            if target["id"] in fit.training_conditions:
                raise ValueError("Held-out condition leaked into training.")
            model = lameiras_glucose_model(fit, data)
            exchange = model.specific_exchange(Q_(target["dilution_per_h"], "1/h"))
            predictions.append({"condition": target["id"], "dilution_per_h": target["dilution_per_h"],
                "model": name, "fit": fit.to_dict(), "metabolism": model.to_dict(),
                "prediction": {key: float(sign * exchange[species].magnitude)
                    for key, (species, sign, _) in OBSERVABLES.items()},
                "observation": {key: target["unreconciled"][key] for key in OBSERVABLES},
                "prediction_units": "mol species/(Cmol biomass h)", "growth_input": "Nominal dilution, mu = D; no biomass retention/death."})
    metrics = {name: {key: float(np.sqrt(np.mean([(p["prediction"][key] - p["observation"][key]["value"])**2
                for p in predictions if p["model"] == name]))) for key in OBSERVABLES} for name in COLORS}
    return predictions, metrics


def plot_holdouts(output, predictions, metrics):
    fig, axes = plt.subplots(2, 3, figsize=(14, 8), layout="constrained", gridspec_kw={"height_ratios": [2.2, 1]})
    for column, (key, (_, _, title)) in enumerate(OBSERVABLES.items()):
        records = [p for p in predictions if p["model"] == "growth_maintenance"]
        x = np.array([p["dilution_per_h"] for p in records])
        y = 1000 * np.array([p["observation"][key]["value"] for p in records])
        err = 1000 * np.array([p["observation"][key]["reported_error"] for p in records])
        axes[0, column].errorbar(x, y, yerr=err, fmt="o", color="#202831", capsize=4, label="Published unreconciled data", zorder=3)
        for name, color in COLORS.items():
            model_records = [p for p in predictions if p["model"] == name]
            predicted = np.array([1000 * p["prediction"][key] for p in model_records])
            label = "Growth + maintenance" if name == "growth_maintenance" else "Growth only"
            axes[0, column].plot(x, predicted, "D--" if name == "growth_only" else "s-", color=color,
                                 label=f"{label} · LOO RMSE {metrics[name][key]*1000:.2f}")
            axes[1, column].plot(x, predicted-y, "o-", color=color)
        axes[0, column].set_title(title, loc="left", fontweight="bold")
        axes[0, column].set_ylabel("mmol / (Cmol biomass · h)")
        axes[0, column].legend(fontsize=8, loc="upper left")
        axes[1, column].axhline(0, color="#333333", lw=.8)
        axes[1, column].set(xlabel="Dilution rate (1/h)", ylabel="Prediction − data")
        for ax in axes[:, column]:
            ax.grid(alpha=.18)
    fig.suptitle("New data test · A. niger NW185 · four chemostat conditions\nEach prediction excludes that condition from fitting; oxygen and CO₂ are never fitted", fontsize=14)
    fig.supxlabel("Lameiras et al. (2015), Table 2. Bars are quoted source errors; covariance/statistical interpretation unresolved.", fontsize=9)
    fig.savefig(output / "new_data_holdouts.png", dpi=180)
    plt.close(fig)


def sensitivity(data):
    records = data["lameiras_2015"]["records"]
    values = []
    for signs in product((-1, 1), repeat=8):
        mu = np.array([r["dilution_per_h"] + signs[i] * r["dilution"]["reported_error"] for i, r in enumerate(records)])
        uptake = np.array([r["unreconciled"]["substrate_uptake"]["value"] + signs[i+4] *
                           r["unreconciled"]["substrate_uptake"]["reported_error"] for i, r in enumerate(records)])
        fit = fit_pirt(growth_rates=Q_(mu, "1/h"), substrate_uptake=Q_(uptake, "1/h"),
                       condition_ids=[r["id"] for r in records], source=SOURCE+" Explicit error-corner perturbation.",
                       include_maintenance=True)
        model = lameiras_glucose_model(fit, data)
        coefficients = model.growth_reaction.coefficients
        admissible = coefficients["oxygen"] < 0 and coefficients["carbon_dioxide"] >= 0
        assert fit.true_yield.value is not None and fit.maintenance_demand.value is not None
        values.append([float(fit.true_yield.value), float(fit.maintenance_demand.value), admissible])
    array = np.array(values)
    aerobic = array[array[:, 2] == 1]
    return {"scenario_count": len(array), "true_yield_range": [float(array[:, 0].min()), float(array[:, 0].max())],
            "maintenance_range_per_h": [float(array[:, 1].min()), float(array[:, 1].max())],
            "zero_maintenance_scenarios": int(np.count_nonzero(array[:, 1] == 0)),
            "incompatible_with_aerobic_no_carbon_fixation_scenarios": int(np.count_nonzero(array[:, 2] == 0)),
            "aerobic_true_yield_range": [float(aerobic[:, 0].min()), float(aerobic[:, 0].max())],
            "aerobic_maintenance_range_per_h": [float(aerobic[:, 1].min()), float(aerobic[:, 1].max())],
            "interpretation": "All 256 plus/minus reported-error corners for dilution and glucose uptake. "
                "An assumption sensitivity envelope, NOT a statistical confidence interval or probability distribution. "
                "Source errors are correlated/poorly characterized. Zero-maintenance possibilities remain. "
                "Unconstrained fits that produce O2 or consume CO2 in growth are flagged and excluded only from "
                "the explicitly labelled aerobic envelope; this is not a Gibbs feasibility test.",
            "sample_columns": ["true_yield", "maintenance_per_h", "oxygen_consuming_without_carbon_fixation"],
            "samples": values}


def external_challenge(data, fit, output):
    row = next(r for r in data["lameiras_2017"]["single_substrate_batch"] if r["substrate"] == "Glucose")
    model = lameiras_glucose_model(fit, data)
    exchange = model.specific_exchange(Q_(row["growth_rate"]["value"], "1/h"))
    values = {key: {"prediction": float(sign * exchange[species].magnitude), "observation": row[key],
                   "relative_error": float(sign * exchange[species].magnitude / row[key]["value"] - 1)}
              for key, (species, sign, _) in OBSERVABLES.items()}
    fig, ax = plt.subplots(figsize=(9, 5), layout="constrained")
    x = np.arange(3)
    ax.bar(x-.18, [values[k]["observation"]["value"] * 1000 for k in OBSERVABLES], .36, color="#354654",
           yerr=[values[k]["observation"]["reported_error"] * 1000 for k in OBSERVABLES], capsize=4, label="2017 batch reference (reconciled)")
    ax.bar(x+.18, [values[k]["prediction"] * 1000 for k in OBSERVABLES], .36, color=COLORS["growth_maintenance"],
           label="2015 model frozen; no 2017 refitting")
    ax.set_xticks(x, [v[2] for v in OBSERVABLES.values()])
    ax.set(ylabel="mmol / (Cmol biomass · h)", title="External regime challenge reveals a remaining gap")
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(axis="y", alpha=.15)
    fig.supxlabel("Same strain/laboratory, different cultivation regime and pH (3.0 → 2.5).\nReconciled reference rates do not independently validate the conservation law.", fontsize=9)
    fig.savefig(output / "external_regime_challenge.png", dpi=180)
    plt.close(fig)
    return {"doi": data["lameiras_2017"]["doi"], "growth_rate_per_h": row["growth_rate"]["value"],
            "rates": values, "fit": fit.to_dict(), "claim_boundary": data["lameiras_2017"]["role"],
            "composition_assumption": "2015 mean biomass composition frozen; 2017 substrate-specific composition not retrieved."}


def plot_mixed(data, output):
    records = data["lameiras_2017"]["mixed_substrate_chemostat"]
    x = [r["dilution_per_h"] for r in records]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), layout="constrained")
    axes[0].errorbar(x, [r["biomass_gDW_L"]["value"] for r in records],
                     yerr=[r["biomass_gDW_L"]["reported_error"] for r in records], fmt="o-", capsize=3, color="#354654")
    axes[0].set(ylabel="Measured biomass (g dry weight/L)", title="Biomass falls at the fastest dilutions")
    for name in ("glucose", "xylose", "arabinose", "galacturonic_acid", "mannose", "rhamnose"):
        axes[1].plot(x, [1000 * r["reconciled"][name+"_uptake"]["value"] for r in records], "o-", ms=3,
                     label=name.replace("_", " "))
    axes[1].set(ylabel="Reconciled uptake (mmol / Cmol biomass / h)", title="Substrate use changes with growth conditions")
    axes[1].legend(fontsize=8)
    for ax in axes:
        ax.set_xlabel("Dilution rate (1/h)")
        ax.grid(alpha=.18)
    fig.suptitle("Remaining target · six-substrate physiology and regulation", fontsize=14)
    fig.supxlabel("Lameiras et al. (2017), Table 2. Observations/reference rates only; no simulated curve.\nSequential conditions are not independent replicates. Suspect CO₂/TOC cells are quarantined.", fontsize=9)
    fig.savefig(output / "mixed_substrate_gap.png", dpi=180)
    plt.close(fig)


def dynamic_demo(data, fit, output):
    def p(name, value, units):
        return Parameter(name, name, value, units, None, ASSUMPTION, "testing", ASSUMPTION)
    culture = ResourceLimitedCulture(lameiras_glucose_model(fit, data), "ammonium", "oxygen",
        ("carbon_dioxide", "water", "proton"), p("qmax", .08, "1/h"), p("Ks", .001, "mol/L"),
        p("Kn", .0001, "mol/L"), p("Ko", .00001, "mol/L"), p("D", 0, "1/h"),
        p("kla", 20, "1/h"), p("Osat", .00025, "mol/L"),
        {n: Q_(0, "mol/L") for n in ("glucose", "ammonium", "oxygen")}, ASSUMPTION)
    cases = {"Aerated batch": (culture, .01),
             "Low oxygen transfer": (replace(culture, gas_transfer_rate=p("kla", .5, "1/h")), .01),
             "Nitrogen limited": (culture, .0002)}
    t = Q_(np.linspace(0, 160, 321), "h")
    fig, axes = plt.subplots(2, 3, figsize=(14, 8), layout="constrained")
    columns = {"time_h": t.magnitude.tolist()}
    audits = {}
    for label, (case, nitrogen) in cases.items():
        initial = {"glucose": Q_(.02, "mol/L"), "biomass": Q_(.001, "mol/L"),
                   "ammonium": Q_(nitrogen, "mol/L"), "oxygen": Q_(.00025, "mol/L")}
        # Exact names include numerical ledgers; tolerances are explicit units.
        names = (*case.names, "extent:growth", "extent:maintenance", *(f"boundary:{n}" for n in case.names))
        settings = SolverSettings(method="Radau", rtol=1e-9,
            atol={n: Q_(1e-13, "mol/L") for n in names}, max_step=Q_(.5, "h"))
        trajectory = case.simulate(initial_state=initial, times=t, solver_settings=settings)
        alternate = case.simulate(initial_state=initial, times=t, solver_settings=replace(settings, method="BDF"))
        differences = {n: float(np.max(np.abs(trajectory.concentrations[n].magnitude - alternate.concentrations[n].magnitude)))
                       for n in case.names}
        audits[label] = {"primary": trajectory.diagnostics, "alternate": alternate.diagnostics,
                        "maximum_solver_difference_mol_L": differences, "provenance": trajectory.provenance,
                        "initial_state_mol_L": {n: float(v.magnitude) for n, v in initial.items()}}
        arrays = [trajectory.concentrations["biomass"].magnitude * 1000,
                  trajectory.concentrations["glucose"].magnitude * 1000,
                  trajectory.concentrations["ammonium"].magnitude * 1000,
                  trajectory.concentrations["oxygen"].magnitude * 1e6,
                  trajectory.cumulative_reaction_exchange["carbon_dioxide"].magnitude * 1000,
                  trajectory.unmet_maintenance_rate.magnitude * 1000]
        for ax, array, name in zip(axes.flat, arrays, ("biomass", "glucose", "ammonium", "oxygen", "CO2", "unmet"), strict=True):
            ax.plot(t.magnitude, array, label=label)
            columns[f"{label}:{name}"] = array.tolist()
    for ax, title, unit in zip(axes.flat,
        ("Biomass", "Glucose", "Ammonium", "Dissolved oxygen", "Cumulative CO₂ export", "Unmet maintenance demand"),
        ("Cmmol/L", "mmol/L", "mmol/L", "µmol/L", "mmol/L", "mmol substrate / Cmol biomass / h"), strict=True):
        ax.set(title=title, ylabel=unit, xlabel="Time (h)")
        ax.grid(alpha=.18)
    axes[0, 0].legend(fontsize=8)
    fig.suptitle("New dynamic capability · exploratory scenarios, NOT experimental trajectories", fontsize=14)
    fig.supxlabel("Yield/maintenance calibrated to 2015 means; capacities, affinities, transfer and initial states are explicit illustrative assumptions.\nUnmet maintenance does not predict survival or death. Gas, solvent and buffered-proton exchanges close the open-system balance.", fontsize=9)
    fig.savefig(output / "resource_limited_cultures.png", dpi=180)
    plt.close(fig)
    write_json(output / "dynamic_audit.json", audits)
    np.savetxt(output / "exploratory_trajectories.csv", np.array(list(columns.values())).T, delimiter=",",
               header=",".join(columns), comments="")
    return audits


def run(root, output):
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output directory must be empty; preserve previous evidence.")
    output.mkdir(parents=True, exist_ok=True)
    data = load_respiration_data(root)
    predictions, metrics = holdouts(data)
    plot_holdouts(output, predictions, metrics)
    fit = fit_records(data["lameiras_2015"]["records"], True)
    external = external_challenge(data, fit, output)
    plot_mixed(data, output)
    dynamic_demo(data, fit, output)
    envelope = sensitivity(data)
    write_json(output / "held_out_predictions.json", predictions)
    write_json(output / "parameter_sensitivity.json", envelope)
    write_json(output / "external_challenge.json", external)
    sources = ("scripts/run_respiration_benchmark.py", "scripts/prepare_respiration_data.py",
               "src/fungal_model/fungi/respiration.py", "src/fungal_model/research/respiration_benchmark.py",
               "src/fungal_model/chemistry/macrochemistry.py", "src/fungal_model/core/numerics.py",
               "data/benchmarks/lameiras_respiration/manifest.json")
    summary = {"maturity": "exploratory_software_tested", "primary_conditions": 4,
        "holdout_predictions_per_model": 12, "rmse_mol_per_Cmol_h": metrics, "all_condition_calibration": fit.to_dict(),
        "glucose_holdout_rmse_reduction_fraction": 1-metrics["growth_maintenance"]["substrate_uptake"]/metrics["growth_only"]["substrate_uptake"],
        "sensitivity": {k: v for k, v in envelope.items() if k != "samples"},
        "external_challenge_relative_errors": {k: v["relative_error"] for k, v in external["rates"].items()},
        "limitations": ["Four nominal growth rates; predictors have uncertainty. Holdouts are not an independent laboratory.",
            "Gas predictions omit chemically unresolved excreted TOC; cannot assign oxygen demand/energy to an unidentified pool.",
            "2017 rates are reconciled and measured at different pH/regime; transfer does not establish validation.",
            "Dynamic kinetics/initial conditions are explicit assumptions, not experimentally identified.",
            "No fungal formation-energy dataset: entropy/heat production unavailable for these empirical cultures.",
            "No morphology, mixed-substrate regulation, storage, viability, death, or integrated enzyme secretion in this module."],
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__},
        "source_hashes": {str(p): hashlib.sha256((root / p).read_bytes()).hexdigest() for p in sources},
        "artifact_hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir())}}
    write_json(output / "summary.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = run(ROOT, args.output)
    print(json.dumps({k: summary[k] for k in ("primary_conditions", "rmse_mol_per_Cmol_h",
        "glucose_holdout_rmse_reduction_fraction", "external_challenge_relative_errors", "sensitivity")}, indent=2))
