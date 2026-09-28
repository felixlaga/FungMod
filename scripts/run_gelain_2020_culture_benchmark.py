"""Reproduce the bounded, retrospective Gelain culture benchmark offline.

Run after ``python scripts/prepare_public_experimental_data.py --check``.
Output directories must be empty: a failed rerun cannot inherit old success.
The source simulations are software parity references, never measurements.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import platform
import subprocess
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import scipy

from fungal_model.core.units import Q_
from fungal_model.research.gelain_culture import (
    CultureBenchmarkError, CultureDesign, fit_effective_culture, load_culture_conditions,
    parameters_from_records, predict_effective_culture, score_predictions, simulate_culture,
)

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = Path("data/benchmarks/gelain_2020")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def source_parity(root: Path, plan: dict, source_parameters: dict) -> list[dict]:
    with (root / BENCHMARK / "source_simulations.csv").open() as handle:
        rows = list(csv.DictReader(handle))
    results = []
    for family, doses in (("glycerol", (5, 10, 20)), ("cellulose", (10, 20, 30))):
        parameters = parameters_from_records(source_parameters[family])
        for dose in doses:
            selected = [r for r in rows if r["family"] == family and float(r["initial_substrate_g_l"]) == dose]
            design = CultureDesign(f"source_{family}_{dose}", family,
                                   Q_([float(r["time_h"]) for r in selected], "hour"),
                                   Q_(float(selected[0]["biomass_g_l"]), "gram/liter"),
                                   Q_(float(selected[0]["substrate_g_l"]), "gram/liter"),
                                   "doi:10.17632/shd3wcczsr.2; deposited simulation reference")
            reference = np.array([[float(r["biomass_g_l"]), float(r["substrate_g_l"])] for r in selected])
            if family == "cellulose":
                reference = np.column_stack([reference, [float(r["induced_proxy_g_l"]) for r in selected]])
            prediction = simulate_culture(design, parameters, model="source_deposited_v1",
                                           hypothesis_source=plan["article_doi"], rtol=1e-10,
                                           atol=Q_(1e-12, "gram/liter"))
            projected = prediction.observations_g_l
            if prediction.induced_proxy is not None:
                projected = np.column_stack([projected, prediction.induced_proxy.magnitude])
            error = float(np.max(abs(projected - reference)))
            # Keep the paper/code discrepancy visible rather than quietly modifying Eq 5.
            paper = simulate_culture(design, parameters, model="source_paper_v1",
                                     hypothesis_source=plan["article_doi"], rtol=1e-10,
                                     atol=Q_(1e-12, "gram/liter"))
            results.append({"family": family, "initial_substrate_g_l": dose,
                            "initial_biomass_g_l": float(design.initial_biomass.magnitude),
                            "role": "software_parity_only", "max_abs_difference_g_l": error,
                            "passed": error <= plan["source_parity_max_abs_difference_g_l"],
                            "paper_vs_deposited_max_biomass_difference_g_l":
                                float(np.max(abs(paper.biomass.magnitude - prediction.biomass.magnitude)))})
    return results


def run(root: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise CultureBenchmarkError(f"Output directory must be empty: {output}")
    # Verify both original sources and all deterministic extracts before modelling.
    subprocess.run([__import__("sys").executable, str(root / "scripts/prepare_public_experimental_data.py"),
                    "--check"], check=True, cwd=root)
    plan_path = root / BENCHMARK / "plan.json"
    plan = json.loads(plan_path.read_text())
    source_parameters = json.loads((root / BENCHMARK / "source_parameters.json").read_text())
    conditions = load_culture_conditions(root)
    input_files = [plan_path, root / BENCHMARK / "source_parameters.json", root / BENCHMARK / "source_simulations.csv",
                   root / "data/experiments/source_intake/manifest.json",
                   root / "scripts/prepare_public_experimental_data.py", Path(__file__).resolve(),
                   root / "src/fungal_model/research/gelain_culture.py"]
    input_files += sorted((root / "data/experiments/literature/gelain_2020_t_harzianum").glob("*"))
    manifest = {str(p.relative_to(root)): digest(p) for p in input_files if p.is_file()}
    software = {str(p.relative_to(root)): digest(p) for p in sorted((root / "src").rglob("*.py"))}
    software["pyproject.toml"] = digest(root / "pyproject.toml")
    write_json(output / "software.json", software)
    write_json(output / "plan.json", plan)
    write_json(output / "inputs.json", manifest)
    parity = source_parity(root, plan, source_parameters)
    write_json(output / "source_parity.json", parity)
    if not all(r["passed"] for r in parity):
        raise CultureBenchmarkError("Source simulation parity failed; see source_parity.json.")
    frozen_dir = output / "frozen_predictions"
    frozen_dir.mkdir()
    folds, full_fits, residual_rows = [], [], []
    for family in ("glycerol", "cellulose"):
        group = [c for c in conditions if c.design.family == family]
        for heldout in group:
            training = [c for c in group if c.design.condition_id != heldout.design.condition_id]
            for weighting in (plan["primary_weighting"], plan["sensitivity_weighting"]):
                print(f"Fitting {family}; holdout={heldout.design.condition_id}; weights={weighting}", flush=True)
                fit = fit_effective_culture(training, plan, weighting=weighting)
                predicted = predict_effective_culture(heldout.design, fit, plan)
                alternate = predict_effective_culture(heldout.design, fit, plan, solver_key="solver_check")
                solver_difference = float(np.max(abs(predicted.observations_g_l - alternate.observations_g_l)))
                tighter = simulate_culture(
                    heldout.design, parameters_from_records(fit["parameters"], source=fit["parameter_source"]),
                    model=plan["model"], hypothesis_source=plan["hypothesis"], method=plan["solver"]["method"],
                    rtol=plan["solver_check"]["rtol"], atol=Q_(plan["solver_check"]["atol_g_l"], "gram/liter"))
                convergence = float(np.max(abs(predicted.observations_g_l - tighter.observations_g_l)))
                frozen = {"heldout_condition": heldout.design.condition_id, "fit": fit,
                          "plan_sha256": digest(output / "plan.json"), "input_hashes": manifest,
                          "software_manifest_sha256": digest(output / "software.json"),
                          "times_h": predicted.time.magnitude.tolist(),
                          "predicted_biomass_substrate_g_l": predicted.observations_g_l.tolist(),
                          "solver": dict(predicted.solver), "alternate_solver": dict(alternate.solver),
                          "alternate_solver_max_abs_difference_g_l": solver_difference,
                          "tolerance_convergence_max_abs_difference_g_l": convergence}
                frozen_path = frozen_dir / f"{heldout.design.condition_id}_{weighting}.json"
                write_json(frozen_path, frozen)  # Written BEFORE responses are scored; no response values in this file.
                if max(solver_difference, convergence) > plan["solver_check"]["max_abs_difference_g_l"]:
                    raise CultureBenchmarkError("Solver verification failed; frozen prediction retained for diagnosis.")
                scores = score_predictions(predicted.observations_g_l, heldout.values, fit["normalization_g_l"])
                baseline = np.tile([float(heldout.design.initial_biomass.to("gram/liter").magnitude),
                                    float(heldout.design.initial_substrate.to("gram/liter").magnitude)],
                                   (len(heldout.design.times.magnitude), 1))
                training_scores = [{"condition": c.design.condition_id, **score_predictions(
                    predict_effective_culture(c.design, fit, plan).observations_g_l, c.values, fit["normalization_g_l"])}
                    for c in training]
                fold = {"condition": heldout.design.condition_id, "family": family, "weighting": weighting,
                        "frozen_prediction_file": str(frozen_path.relative_to(output)),
                        "frozen_prediction_sha256": digest(frozen_path), "fit": fit,
                        "heldout_score": scores, "training_scores": training_scores,
                        "constant_initial_state_score": score_predictions(baseline, heldout.values, fit["normalization_g_l"]),
                        "solver_max_abs_difference_g_l": solver_difference,
                        "tolerance_max_abs_difference_g_l": convergence}
                folds.append(fold)
                for i, time in enumerate(predicted.time.magnitude):
                    for j, observable in enumerate(("biomass", "substrate")):
                        residual_rows.append({"condition": heldout.design.condition_id, "weighting": weighting,
                                              "role": "retrospective_condition_holdout", "time_h": float(time),
                                              "observable": observable, "observed_g_l": float(heldout.values.magnitude[i, j]),
                                              "predicted_g_l": float(predicted.observations_g_l[i, j]),
                                              "residual_g_l": float(predicted.observations_g_l[i, j] - heldout.values.magnitude[i, j])})
        print(f"Fitting {family}; all conditions; descriptive calibration only", flush=True)
        full_fits.append({"family": family, "role": "all_conditions_calibration_not_holdout",
                          "fit": fit_effective_culture(group, plan, weighting=plan["primary_weighting"])})

    published = []
    for condition in conditions:
        # Reproduce the source convention 0.4, rather than silently replacing it
        # with the workbook's 0.399067... initial measurement used in new fits.
        source_initial = next(r for r in parity if r["family"] == condition.design.family
                              and r["initial_substrate_g_l"] == float(condition.design.initial_substrate.magnitude))
        design = replace(condition.design, initial_biomass=Q_(source_initial["initial_biomass_g_l"], "gram/liter"))
        prediction = simulate_culture(design, parameters_from_records(source_parameters[design.family]),
                                      model="source_deposited_v1", hypothesis_source=plan["article_doi"])
        published.append({"condition": design.condition_id, "role": "published_all_conditions_fit_descriptive_only",
                          "score": score_predictions(prediction.observations_g_l, condition.values, [1, 1])})
    report = {"schema_version": 1, "benchmark_id": plan["benchmark_id"], "maturity": plan["maturity"],
              "scope": plan["scope"], "biological_validation": False, "measurement_uncertainty": None,
              "design_status": plan["design_status"], "environment": {"python": platform.python_version(),
                                                                        "numpy": np.__version__, "scipy": scipy.__version__},
              "inputs": manifest, "software_manifest_sha256": digest(output / "software.json"),
              "source_parity": parity, "folds": folds, "full_data_fits": full_fits,
              "published_source_descriptive_scores": published}
    write_json(output / "report.json", report)
    with (output / "residuals.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(residual_rows[0]))
        writer.writeheader()
        writer.writerows(residual_rows)
    primary = [r for r in folds if r["weighting"] == plan["primary_weighting"]]
    lines = ["# Gelain culture benchmark", "", "Exploratory retrospective condition holdouts; no empirical uncertainty or independent validation.",
             "", "RMSE in g/L. Published source scores use all-condition fitted parameters and are descriptive only.", "",
             "| Held-out condition | Biomass | Substrate | Constant-state biomass | Constant-state substrate |",
             "| --- | ---: | ---: | ---: | ---: |"]
    for row in primary:
        errors = row["heldout_score"]["rmse_g_l"] + row["constant_initial_state_score"]["rmse_g_l"]
        lines.append(f"| {row['condition']} | " + " | ".join(f"{v:.4f}" for v in errors) + " |")
    lines += ["", "See report.json for every optimizer start, bound contact, Jacobian diagnostic, weighting sensitivity,",
              "solver/tolerance check, training score and source reproduction result.",
              "No post-holdout model selection is performed. Means are retained as reported, including reversals and zeros."]
    (output / "report.md").write_text("\n".join(lines) + "\n")
    fig, axes = plt.subplots(2, 3, figsize=(12, 7), sharex=True, layout="constrained")
    for ax, condition in zip(axes.flat, conditions, strict=True):
        row = next(r for r in primary if r["condition"] == condition.design.condition_id)
        curve = predict_effective_culture(replace(condition.design, times=Q_(np.linspace(0, 96, 193), "hour")),
                                          row["fit"], plan)
        for j, (label, color) in enumerate((("Biomass", "#245b8a"), ("Substrate", "#c16221"))):
            ax.plot(curve.time.magnitude, curve.observations_g_l[:, j], color=color, label=f"{label} holdout prediction")
            ax.scatter(condition.design.times.magnitude, condition.values.magnitude[:, j], color=color,
                       marker="o" if j == 0 else "s", s=22, label=f"{label} published mean")
        ax.set_title(condition.design.condition_id.replace("gelain_2020_", "").replace("_", " "))
        ax.set(xlabel="Time (h)", ylabel="Concentration (g/L)", ylim=(0, None))
        ax.grid(alpha=0.15)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside lower center", ncol=2, fontsize=9)
    fig.suptitle("T. harzianum P49P11 • Retrospective condition holdouts\nEffective growth/loss hypothesis; measurement uncertainty unavailable", fontsize=12)
    fig.savefig(output / "holdouts.png", dpi=160)
    fig.savefig(output / "holdouts.svg")
    plt.close(fig)
    write_json(output / "artifacts.json", {str(p.relative_to(output)): digest(p)
                                          for p in sorted(output.rglob("*")) if p.is_file()})
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/gelain-culture-benchmark")
    args = parser.parse_args()
    report = run(ROOT, args.output.resolve())
    print(f"Completed {len(report['folds'])} retrospective folds; outputs: {args.output}")


if __name__ == "__main__":
    main()
