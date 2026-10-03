"""Offline protein-data holdouts and exploratory, conserved fungal digestion."""
from __future__ import annotations

import argparse
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
from fungal_model.core.units import Q_
from fungal_model.research.degrading_culture_example import ASSUMPTION, illustrative_culture, illustrative_initial_state
from fungal_model.research.secretion_benchmark import DATA_PATH, load_secretion_data, strain_holdouts

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = SolverSettings(method="BDF", rtol=1e-9, atol=1e-13, max_step=Q_(.5, "h"))
TIMES = Q_(np.linspace(0, 120, 481), "h")
COLORS = ["#168b83", "#dd8a25", "#8c5c9d", "#718397"]


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def finish(fig, path: Path, note: str) -> None:
    fig.text(.5, .014, note, ha="center", va="bottom", fontsize=9, color="#475569")
    fig.tight_layout(rect=(0, .05, 1, .93))
    fig.savefig(path, dpi=170, facecolor="white")
    plt.close(fig)


def data_figure(result, output: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11.8, 4.9), sharey=True)
    fig.suptitle("New primary data: secretion depends on carbon source", fontsize=17, weight="bold")
    for ax, strain in zip(axes, ("AB94-85", "ABGT1026"), strict=True):
        for i, carbon in enumerate(("xylose", "maltose")):
            rows = [r for r in result["predictions"] if r["strain"] == strain and r["carbon_source"] == carbon]
            ax.errorbar(i-.15, rows[0]["observed_mg_gDW_h"], yerr=rows[0]["observed_sd_mg_gDW_h"],
                        fmt="o", color="#172f3d", capsize=5, markersize=8, label="Measured mean ± SD" if i == 0 else None)
            for shift, mode, marker, color, label in ((0, "pooled", "s", COLORS[3], "Pooled ratio"),
                (.15, "carbon_source_conditioned", "D", COLORS[0], "Carbon-source ratio")):
                row = next(r for r in rows if r["mode"] == mode)
                ax.plot(i+shift, row["predicted_mg_gDW_h"], marker, color=color, markersize=8, label=label if i == 0 else None)
        ax.set(title=f"Held-out strain: {strain}", xticks=[0, 1], xticklabels=["Xylose", "Maltose"], xlim=(-.5, 1.5), ylim=(0, 2.6))
        ax.grid(axis="y", alpha=.2)
        ax.legend(loc="upper left", fontsize=9)
    axes[0].set_ylabel("Extracellular protein [mg / (g dry biomass · h)]")
    finish(fig, output / "secretion_data_holdouts.png",
        "Jørgensen et al. 2009, Table 1 • Each prediction excludes the entire target strain • Growth rate supplied: 0.16/h\n"
        "Four means, three steady-state replicates per mean; sequential carbon conditions • Component test, not whole-fungus validation")


def trajectory_dict(result):
    return {"time_h": result.time.to("h").magnitude.tolist(),
            "pools_mol_L": {n: q.to("mol/L").magnitude.tolist() for n, q in result.concentrations.items()},
            "process_rates_mol_L_h": {n: q.to("mol/L/h").magnitude.tolist() for n, q in result.process_rates.items()},
            "cumulative_reaction_exchange_mol_L": {n: q.to("mol/L").magnitude.tolist() for n, q in result.cumulative_reaction_exchange.items()},
            "cumulative_boundary_exchange_mol_L": {n: q.to("mol/L").magnitude.tolist() for n, q in result.cumulative_boundary_exchange.items()},
            "unmet_maintenance_per_h": result.unmet_maintenance_rate.to("1/h").magnitude.tolist(),
            "degradation": result.batch_degradation("polymer"), "diagnostics": result.diagnostics,
            "provenance": result.provenance}


def demonstration(output: Path):
    definitions = [("Coupled, aerated", .1, 20., .02), ("Low oxygen transfer", .1, .2, .02),
                   ("Low nitrogen", .1, 20., .0005), ("No secretion", 0., 20., .02)]
    runs = []
    for label, allocation, transfer, nitrogen in definitions:
        model = illustrative_culture(allocation=allocation, gas_transfer_per_h=transfer, catalytic_per_h=100, inactivation_per_h=.01)
        initial = illustrative_initial_state(nitrogen_mol_L=nitrogen)
        result = model.simulate(initial_state=initial, times=TIMES, solver_settings=SETTINGS)
        runs.append((label, result))
    fig, axes = plt.subplots(2, 3, figsize=(13, 7.9))
    fig.suptitle("A living degradation loop with an explicit resource budget", fontsize=17, weight="bold")
    panels = [("polymer", "Degradable polymer", "mmol repeat / L"), ("sugar", "Released, usable sugar", "mmol / L"),
              ("biomass", "Biomass pool", "Cmmol / L"), ("active_protein", "Active extracellular protein", "Cmmol / L"),
              ("oxygen", "Dissolved oxygen", "mmol / L"), ("carbon_dioxide", "Cumulative respiratory CO₂", "mmol / L")]
    for ax, (name, title, units) in zip(axes.flat, panels, strict=True):
        for (label, result), color in zip(runs, COLORS, strict=True):
            series = (result.cumulative_reaction_exchange[name] if name == "carbon_dioxide" else result.concentrations[name])
            ax.plot(result.time.magnitude, series.to("mmol/L").magnitude, color=color, lw=2, label=label)
        ax.set(title=title, xlabel="Time [h]", ylabel=units)
        ax.grid(alpha=.2)
    axes[0, 0].legend(fontsize=8)
    finish(fig, output / "coupled_degradation.png",
        "Illustrative parameters and empirical formulas; no measured trajectories are shown\n"
        "Enzyme production pays carbon, nitrogen and oxygen costs; inactive protein remains in the material ledger")
    reference = illustrative_culture(allocation=.1, gas_transfer_per_h=20, catalytic_per_h=100, inactivation_per_h=.01)
    radau = reference.simulate(initial_state=illustrative_initial_state(nitrogen_mol_L=.02), times=TIMES,
                              solver_settings=SolverSettings(method="Radau", rtol=1e-10, atol=1e-14, max_step=Q_(.25, "h")))
    disagreement = max(float(np.max(np.abs(radau.concentrations[n].magnitude-runs[0][1].concentrations[n].magnitude)))
                       for n in reference.names)
    return {"runs": {name: trajectory_dict(result) for name, result in runs},
            "maximum_BDF_Radau_pool_difference_mol_L": disagreement,
            "maximum_balance_residual_mol_L": max(max(r.diagnostics["maximum_absolute_balance_residual_mol_L"].values())
                                                  for _, r in runs),
            "reference_Radau_diagnostics": radau.diagnostics}


def allocation_sweep(output: Path):
    rows = []
    for fraction in np.linspace(0, .8, 33):
        model = illustrative_culture(allocation=float(fraction), gas_transfer_per_h=20, catalytic_per_h=100, inactivation_per_h=.01)
        result = model.simulate(initial_state=illustrative_initial_state(nitrogen_mol_L=.02), times=TIMES, solver_settings=SETTINGS)
        rows.append({"allocation_fraction": float(fraction), **result.batch_degradation("polymer"),
                     "final_biomass_Cmmol_L": float(result.concentrations["biomass"].magnitude[-1]*1000),
                     "final_total_protein_Cmmol_L": float((result.concentrations["active_protein"].magnitude[-1]
                                                          + result.concentrations["inactive_protein"].magnitude[-1])*1000),
                     "diagnostics": result.diagnostics})
    fig, axes = plt.subplots(1, 3, figsize=(12.4, 4.7))
    fig.suptitle("Secretion helps digestion, but consumes the growth budget", fontsize=17, weight="bold")
    fractions = [r["allocation_fraction"]*100 for r in rows]
    axes[0].plot(fractions, [r["final_fraction_removed"]*100 for r in rows], color=COLORS[0], lw=2)
    axes[0].set(title="Polymer removed by 120 h", ylabel="Degradation [%]", ylim=(-3, 103))
    for threshold, color in (("0.5", COLORS[0]), ("0.9", COLORS[1])):
        values = [r["threshold_times_hour"][threshold] if r["threshold_times_hour"][threshold] is not None else np.nan for r in rows]
        axes[1].plot(fractions, values, color=color, lw=2, label=f"{float(threshold)*100:.0f}% removal")
    axes[1].set(title="Time to degradation thresholds", ylabel="Time [h]")
    axes[1].legend(fontsize=9)
    axes[2].plot(fractions, [r["final_biomass_Cmmol_L"] for r in rows], color=COLORS[0], label="Biomass", lw=2)
    axes[2].plot(fractions, [r["final_total_protein_Cmmol_L"] for r in rows], color=COLORS[2], label="Secreted protein (active + inactive)", lw=2)
    axes[2].set(title="Material allocation at 120 h", ylabel="Pool [Cmmol / L]")
    axes[2].legend(fontsize=8)
    for ax in axes:
        ax.set_xlabel("Post-maintenance substrate sent to secretion [%]")
        ax.grid(alpha=.2)
    finish(fig, output / "allocation_tradeoff.png",
        "Illustrative parameter sweep, not an experimentally established optimum • Missing threshold segments mean unreached by 120 h\n"
        "Biomass and protein use explicit, different elemental formulas; curves are not universal fungal predictions")
    return {"points": rows, "maturity": "exploratory_software_tested", "uncertainty": "Not a confidence interval or inferred optimum",
            "fixed_parameters": illustrative_culture(allocation=.1, gas_transfer_per_h=20, catalytic_per_h=100, inactivation_per_h=.01).to_dict()}


def sensitivity(output: Path):
    # Deliberately supplied assumption ranges, not sampled parameter posteriors.
    results = []
    for catalytic, decay in product((1., 10., 100.), (.001, .01, .1)):
        model = illustrative_culture(allocation=.1, gas_transfer_per_h=20, catalytic_per_h=catalytic, inactivation_per_h=decay)
        result = model.simulate(initial_state=illustrative_initial_state(nitrogen_mol_L=.02), times=TIMES, solver_settings=SETTINGS)
        results.append({"catalytic_per_h": catalytic, "inactivation_per_h": decay, **trajectory_dict(result)})
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.8))
    fig.suptitle("Missing enzyme kinetics leave substantial predictive uncertainty", fontsize=16, weight="bold")
    time = TIMES.magnitude
    for ax, name, title, unit in zip(axes, ("polymer", "biomass"), ("Remaining polymer", "Biomass pool"),
                                   ("mmol repeat / L", "Cmmol / L"), strict=True):
        curves = np.array([r["pools_mol_L"][name] for r in results])*1000
        ax.fill_between(time, curves.min(axis=0), curves.max(axis=0), color=COLORS[0], alpha=.18, label="Nine assumed parameter combinations")
        for r, curve in zip(results, curves, strict=True):
            if r["inactivation_per_h"] == .01:
                ax.plot(time, curve, lw=2, label=f"Catalytic capacity {r['catalytic_per_h']:g}/h; inactivation 0.01/h")
        ax.set(title=title, xlabel="Time [h]", ylabel=unit)
        ax.grid(alpha=.2)
    axes[0].legend(fontsize=8)
    finish(fig, output / "kinetic_uncertainty.png",
        "Sensitivity envelope only, not a confidence or credible interval • Assumed catalytic capacity 1–100/h; inactivation 0.001–0.1/h\n"
        "Measure active enzyme abundance, specific catalytic capacity and inactivation before making organism-level forecasts")
    return {"assumption": ASSUMPTION, "range_source": "Explicit illustration only; ranges are not inferred from the protein-output data",
            "results": results}


def run(output: Path):
    output.mkdir(parents=True, exist_ok=False)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    data = load_secretion_data(ROOT)
    empirical = strain_holdouts(data)
    data_figure(empirical, output)
    write_json(output / "secretion_holdouts.json", empirical)
    dynamic = demonstration(output)
    write_json(output / "coupled_degradation.json", dynamic)
    sweep = allocation_sweep(output)
    write_json(output / "allocation_tradeoff.json", sweep)
    sensitivity_result = sensitivity(output)
    write_json(output / "kinetic_uncertainty.json", sensitivity_result)
    source_paths = sorted((ROOT / "src").rglob("*.py")) + [Path(__file__).resolve(), ROOT / "scripts/prepare_secretion_data.py"]
    summary = {"schema_version": 1, "empirical": {k: v for k, v in empirical.items() if k != "predictions"},
        "dynamic_balance_max_mol_L": dynamic["maximum_balance_residual_mol_L"],
        "dynamic_BDF_Radau_difference_max_mol_L": dynamic["maximum_BDF_Radau_pool_difference_mol_L"],
        "dynamic_scenarios": {n: r["degradation"] for n, r in dynamic["runs"].items()},
        "software": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__, "matplotlib": matplotlib.__version__},
        "data_manifest": json.loads((ROOT / DATA_PATH / "manifest.json").read_text()),
        "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths},
        "claim_boundary": "Measured protein-output component challenge and illustrative coupled culture simulations; neither perfect nor whole-fungus validated.",
        "remaining_gaps": ["Active enzyme fraction, composition, synthesis cost and substrate-specific activity measured together",
            "Dynamic induction/repression and intracellular storage", "Hyphal tips, branching, geometry and spatial nutrient transport",
            "Viability, death, recycling, pH, excreted organic products and species interactions",
            "Complete common-state chemical potentials and activity models for a physiological free-energy/entropy budget"]}
    write_json(output / "summary.json", summary)
    write_json(output / "artifact_manifest.json", {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                                   for p in sorted(output.iterdir()) if p.is_file()})
    print(json.dumps({k: summary[k] for k in ("empirical", "dynamic_balance_max_mol_L", "dynamic_BDF_Radau_difference_max_mol_L", "dynamic_scenarios")}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New directory; existing results are never overwritten")
    run(parser.parse_args().output.resolve())
