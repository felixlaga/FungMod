"""Offline joint assay benchmark. Retrospective comparison, never independent validation."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import scipy

from fungal_model.calibration.model_validation import ModelScope, ScopeRange, model_identity, validation_readiness
from fungal_model.core.units import Q_
from fungal_model.research.gelain_culture import CultureBenchmarkError, CultureDesign, parameters_from_records
from fungal_model.research.gelain_joint import (conditional_bootstrap, fit_joint, load_joint_cultures,
                                             predict_joint, profile_joint, score_joint)
from fungal_model.research.gelain_models import DISPLAY_UNITS, OBSERVABLE_UNITS, simulate_candidate

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = Path("data/benchmarks/gelain_2020_v2")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+"\n")


def source_comparison(root: Path) -> list[dict]:
    with (root/BENCHMARK/"source_simulations.csv").open() as handle:
        rows = list(csv.DictReader(handle))
    parameters = parameters_from_records(json.loads((root/BENCHMARK/"source_parameters.json").read_text())["parameters"])
    reports = []
    for dose in (10, 20, 30):
        selected = [r for r in rows if float(r["initial_substrate_g_l"]) == dose]
        design = CultureDesign(f"source_cellulose_{dose}", "cellulose", Q_([float(r["time_h"]) for r in selected], "hour"),
                               Q_(0.4, "g/L"), Q_(dose, "g/L"), "Deposited source simulation only")
        reference = np.array([[float(r[k]) for k in ("biomass_g_l", "substrate_g_l", "cellulase_fpu_l", "beta_u_l")]
                              for r in selected])
        predicted = simulate_candidate(design, {k:Q_(0,u) for k,u in list(OBSERVABLE_UNITS.items())[2:]}, parameters,
            model="published", hypothesis_source="Gelain 2020 Eqs 2-10", method="DOP853", rtol=1e-11, atol=1e-13)
        reports.append({"dose_g_l": dose, "role": "source_simulation_not_measurement",
            "max_absolute_difference": dict(zip(OBSERVABLE_UNITS, np.max(abs(predicted.values-reference), axis=0).tolist(), strict=True)),
            "units": OBSERVABLE_UNITS, "activity_exact_parity_established": False,
            "interpretation": "Activity discrepancy is retained. Discontinuous inhibition switches and the deposited fixed 1 h solver may contribute; exact source activity parity is not established."})
    return reports


def fit_job(root, training_ids, plan, model, scenario):
    # Pint quantities reconstruct against a process-global application registry
    # when pickled. Load assay quantities locally instead of crossing registries.
    training = [c for c in load_joint_cultures(root) if c.design.condition_id in training_ids]
    return fit_joint(training, plan, model=model, scenario=scenario)


def freeze_and_score(output: Path, condition, fit: dict, plan: dict, binding: dict) -> dict:
    """Only the training fit and held-out design are used before the freeze."""
    record = {"family": condition.design.family, "condition": condition.design.condition_id,
              "model": fit["model"], "scenario": fit["scenario"], "fit": fit, "success": False}
    if not fit["success"]:
        return record
    predicted = predict_joint(condition, fit, plan)
    alternate = predict_joint(condition, fit, plan, solver_key="solver_check")
    tighter_plan = dict(plan, solver=dict(plan["solver"], rtol=plan["solver_check"]["rtol"], atol=plan["solver_check"]["atol"]))
    tighter = predict_joint(condition, fit, tighter_plan)
    scales = np.asarray(fit["normalization"])
    difference = float(np.max(abs(predicted.values-alternate.values)/scales))
    convergence = float(np.max(abs(predicted.values-tighter.values)/scales))
    path = output/"frozen_predictions"/f"{condition.design.condition_id}_{fit['model']}_{fit['scenario']}.json"
    write_json(path, {"condition": condition.design.condition_id, "fit": fit, **binding,
        "times_h": predicted.times.magnitude.tolist(), "observables": list(condition.names),
        "units": [OBSERVABLE_UNITS[k] for k in condition.names], "predictions": predicted.values.tolist(),
        "solver": predicted.solver, "alternate_scaled_difference": difference, "tighter_scaled_difference": convergence})
    record.update(frozen_prediction_file=str(path.relative_to(output)), frozen_prediction_sha256=digest(path),
                  alternate_scaled_difference=difference, tighter_scaled_difference=convergence)
    record["success"] = max(difference, convergence) <= plan["solver_check"]["maximum_scaled_difference"]
    record["score"] = score_joint(predicted.values, condition, scales.tolist())
    baseline = np.tile([condition.design.initial_biomass.to("g/L").magnitude,
                       condition.design.initial_substrate.to("g/L").magnitude]+
                      [condition.initial_activities[k].to(OBSERVABLE_UNITS[k]).magnitude for k in condition.names[2:]],
                      (len(condition.values), 1))
    record["constant_initial_score"] = score_joint(baseline, condition, scales.tolist())
    return record


def comparisons(folds: list[dict], full: list[dict], plan: dict) -> list[dict]:
    rows = []
    for family, models in plan["models"].items():
        scenarios = ["primary", "correlated_assumption"] if family == "cellulose" else ["primary"]
        for scenario in scenarios:
            group_rows = []
            for model in models:
                group = [f for f in folds if (f["family"],f["model"],f["scenario"]) == (family,model,scenario)]
                complete = len(group) == 3 and all(f["success"] for f in group)
                scores = [f["score"] for f in group if f["success"]]
                fit = next(f for f in full if (f["family"],f["model"],f["scenario"]) == (family,model,scenario))
                names = fit["observables"]
                rmse = {k:float(np.sqrt(np.mean([s["rmse"][k]**2 for s in scores]))) for k in names} if complete else None
                nmse = {k:float(np.mean([s["normalized_mse"][k] for s in scores])) for k in names} if complete else None
                group_rows.append({"family":family, "model":model, "scenario":scenario, "complete":complete,
                    "pooled_rmse":rmse, "pooled_normalized_mse":nmse, "mean_normalized_mse":float(np.mean(list(nmse.values()))) if nmse else None,
                    "parameter_count":fit["parameter_count"], "practical_rank":fit.get("practical_rank"),
                    "all_fits_full_local_rank":fit["success"] and all(f["fit"].get("practical_rank")==fit["parameter_count"] for f in group+[{'fit':fit}]),
                    "near_bounds_full_fit":fit.get("near_bounds"), "validated":False})
            baseline = next(r for r in group_rows if r["model"] == "effective")
            for row in group_rows:
                reasons = []
                if not row["complete"] or not baseline["complete"]:
                    reasons.append("Incomplete successful holdouts or numerical checks")
                elif row["model"] != "effective":
                    if row["mean_normalized_mse"] > baseline["mean_normalized_mse"]*(1-plan["complexity_screen"]["minimum_relative_cv_improvement"]):
                        reasons.append("Insufficient held-condition improvement over effective null")
                    if any(row["pooled_normalized_mse"][k] > baseline["pooled_normalized_mse"][k]*(1+plan["complexity_screen"]["maximum_observable_worsening"]) for k in row["pooled_normalized_mse"]):
                        reasons.append("At least one observable worsens beyond the predefined allowance")
                    if not row["all_fits_full_local_rank"]:
                        reasons.append("Local sensitivity rank does not support all free parameters")
                row.update(complexity_screen_passed=not reasons, complexity_screen_reasons=reasons,
                           screen_is_biological_validation=False)
            rows.extend(group_rows)
    return rows


def readiness(root: Path, fit: dict, conditions, plan: dict) -> dict:
    family = fit["family"]
    identity = model_identity(model_id=f"gelain_2020_{family}_{fit['model']}", model_version="culture-v2",
        equation_source=fit["hypothesis_source"], equation_sha256=digest(root/"src/fungal_model/research/gelain_models.py"),
        parameter_records=fit["parameters"], training_experiment_ids=fit["training_conditions"],
        observation_model={"biomass":"X+R dry mass" if "retained" in fit["model"] else "X dry mass",
            "activity":"assay activity state, never enzyme concentration", "units":dict(zip(fit["observables"],fit["observable_units"],strict=True)),
            "initial_retained_mass":"Explicit fixed initialization, not a viability measurement",
            "error_model":fit["noise"], "measurement_uncertainty":fit["measurement_uncertainty"],
            "implementation_dependencies_sha256":{str(p.relative_to(root)):digest(p) for p in
                 [root/"src/fungal_model/research/gelain_culture.py",root/"src/fungal_model/research/gelain_joint.py"]}})
    doses = [float(c.design.initial_substrate.to("g/L").magnitude) for c in conditions]
    scope = ModelScope({"strain":plan["validation_scope"]["strain"], "substrate":family,
                       "reactor":plan["validation_scope"]["reactor"], "medium":plan["validation_scope"]["medium"],
                       "oxygen":plan["validation_scope"]["oxygen"]},
        {"initial_substrate":ScopeRange(Q_(min(doses),"g/L"),Q_(max(doses),"g/L")),
         "temperature":ScopeRange(Q_(302.15,"kelvin"),Q_(302.15,"kelvin")),
         "pH":ScopeRange(Q_(4.5,"dimensionless"),Q_(5.5,"dimensionless"))},
        {k:OBSERVABLE_UNITS[k] for k in fit["observables"]}, "Proposed Gelain culture domain, not a validated range",
        observation_time=ScopeRange(Q_(0,"hour"),Q_(96,"hour")))
    return validation_readiness(identity,scope,criteria_source=plan["acceptance_criteria"],
        independent_data_source=plan["independent_validation_data"], measurement_error_source=plan["empirical_measurement_error"],
        domain_review_source=plan["independent_domain_review"])


def plot_holdouts(output: Path, folds: list[dict], conditions) -> None:
    for family in ("glycerol","cellulose"):
        group = [c for c in conditions if c.design.family == family]
        fig, axes = plt.subplots(len(group[0].names),3,figsize=(13,3*len(group[0].names)),squeeze=False)
        for j,c in enumerate(group):
            for i,k in enumerate(c.names):
                ax = axes[i,j]
                ax.scatter(c.design.times.magnitude,c.values[:,i],color="black",s=18,label="published means",zorder=5)
                for fold in folds:
                    if fold["condition"] == c.design.condition_id and fold["scenario"] == "primary" and fold["fit"]["success"]:
                        frozen = json.loads((output/fold["frozen_prediction_file"]).read_text())
                        ax.plot(frozen["times_h"],np.asarray(frozen["predictions"])[:,i],label=fold["model"])
                ax.set(xlabel="Time (h)",ylabel=f"{k.replace('_',' ')} ({DISPLAY_UNITS[k]})")
                if i == 0:
                    ax.set_title(f"Held out: {c.design.initial_substrate.to('g/L').magnitude:g} g/L {family}")
        axes[0,0].legend(fontsize=8)
        fig.suptitle("Retrospective whole-condition holdouts; measurement error unknown",fontsize=13)
        fig.tight_layout()
        fig.savefig(output/f"{family}_holdouts.png",dpi=150)
        plt.close(fig)


def run(root: Path, output: Path, workers: int = 2) -> dict:
    output.mkdir(parents=True,exist_ok=True)
    if any(output.iterdir()):
        raise CultureBenchmarkError("Output must be empty; existing benchmark evidence is never overwritten.")
    subprocess.run([sys.executable,str(root/"scripts/prepare_public_experimental_data.py"),"--check"],check=True,cwd=root)
    plan = json.loads((root/BENCHMARK/"plan.json").read_text())
    conditions = load_joint_cultures(root)
    files = [root/BENCHMARK/n for n in ("plan.json","observations.json","source_parameters.json","source_simulations.csv")]
    files += [root/"data/experiments/source_intake/manifest.json",root/"scripts/prepare_public_experimental_data.py",root/"pyproject.toml",Path(__file__).resolve()]
    manifest = {str(p.relative_to(root)):digest(p) for p in files}
    software = {str(p.relative_to(root)):digest(p) for p in sorted((root/"src").rglob("*.py"))}
    for name,value in (("plan",plan),("inputs",manifest),("software",software),("source_comparison",source_comparison(root))):
        write_json(output/f"{name}.json",value)
    dependencies = {name:version(name) for name in ("numpy","scipy","pint","matplotlib","PyYAML","cryptography")}
    (output/"requirements.txt").write_text("# Direct runtime dependencies; install the source revision separately.\n"+
                                          "\n".join(f"{name}=={v}" for name,v in dependencies.items())+"\n")
    binding = {"plan_sha256":digest(output/"plan.json"),"input_manifest_sha256":digest(output/"inputs.json"),
               "software_manifest_sha256":digest(output/"software.json")}
    (output/"frozen_predictions").mkdir()
    (output/"full_fits").mkdir()
    (output/"validation_readiness").mkdir()
    folds, full = [], []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        jobs = {}
        for family,models in plan["models"].items():
            group = [c for c in conditions if c.design.family == family]
            for scenario in (["primary","correlated_assumption"] if family == "cellulose" else ["primary"]):
                for model in models:
                    for holdout in [None]+group:
                        training = [c for c in group if holdout is None or c.design.condition_id != holdout.design.condition_id]
                        jobs[pool.submit(fit_job,root,[c.design.condition_id for c in training],plan,model,scenario)] = holdout
        for future in as_completed(jobs):
            heldout,fit = jobs[future],future.result()
            print(f"{fit['family']} {fit['model']} {fit['scenario']} {heldout.design.condition_id if heldout else 'all'}: success={fit['success']}",flush=True)
            if heldout is None:
                full.append(fit)
                stem = f"{fit['family']}_{fit['model']}_{fit['scenario']}"
                write_json(output/"full_fits"/f"{stem}.json",fit)
                if fit["success"]:
                    write_json(output/"validation_readiness"/f"{stem}.json",readiness(root,fit,[c for c in conditions if c.design.family==fit['family']],plan))
            else:
                folds.append(freeze_and_score(output,heldout,fit,plan,binding))
    folds.sort(key=lambda f:(f["family"],f["model"],f["scenario"],f["condition"]))
    full.sort(key=lambda f:(f["family"],f["model"],f["scenario"]))
    comparison = comparisons(folds,full,plan)
    # Save expensive fit results before diagnostics; partial output is not a completed benchmark.
    write_json(output/"folds.json",folds)
    write_json(output/"comparison.json",comparison)
    with (output/"residuals.csv").open("w",newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["condition","model","scenario","time_h","observable","units","observed","predicted","residual","numerical_checks_passed"])
        for fold in folds:
            if not fold["fit"]["success"]:
                continue
            condition = next(c for c in conditions if c.design.condition_id==fold["condition"])
            frozen = json.loads((output/fold["frozen_prediction_file"]).read_text())
            for i,time in enumerate(frozen["times_h"]):
                for j,name in enumerate(condition.names):
                    actual,predicted = float(condition.values[i,j]), frozen["predictions"][i][j]
                    writer.writerow([fold["condition"],fold["model"],fold["scenario"],time,name,
                                     OBSERVABLE_UNITS[name],actual,predicted,predicted-actual,fold["success"]])
    diagnostics = {}
    for family in plan["models"]:
        candidates = [r for r in comparison if r["family"]==family and r["scenario"]=="primary" and r["complete"]]
        if not candidates:
            diagnostics[family] = {"failure":"No complete primary candidate"}
            continue
        chosen = min(candidates,key=lambda r:r["mean_normalized_mse"])
        fit = next(f for f in full if (f["family"],f["model"],f["scenario"])==(family,chosen["model"],"primary"))
        if not fit["success"]:
            diagnostics[family] = {"failure":"Selected descriptive all-condition fit failed"}
            continue
        print(f"Profiling and conditional bootstrap: {family} {fit['model']}",flush=True)
        group = [c for c in conditions if c.design.family==family]
        profiles = profile_joint(group,fit,plan)
        bootstrap = conditional_bootstrap(group,fit,plan)
        write_json(output/f"{family}_profiles.json",profiles)
        write_json(output/f"{family}_bootstrap.json",bootstrap)
        diagnostics[family] = {"model":fit["model"], "selection":"Lowest primary held-condition loss, for diagnosis only",
            "complexity_screen_passed":chosen["complexity_screen_passed"],"profile_complete":profiles["complete"],
            "reference_improved_during_profiles":profiles["reference_improved"],
            "bootstrap_successful":bootstrap["successful"],"bootstrap_requested":bootstrap["requested"]}
    plot_holdouts(output,folds,conditions)
    if any(digest(root/path)!=sha for path,sha in manifest.items()) or any(digest(root/path)!=sha for path,sha in software.items()):
        raise CultureBenchmarkError("Inputs or implementation changed during this run; do not publish mixed-version results.")
    attempts = [s for f in full+[f['fit'] for f in folds] for s in f['starts']]
    report = {"schema_version":2,"benchmark_id":plan["benchmark_id"],"completed":True,"validated":False,
        "design_status":plan["design_status"],"observed_values":sum(c.values.size for c in conditions),
        "folds":len(folds),"successful_numerically_checked_folds":sum(f["success"] for f in folds),
        "full_fits":len(full),"optimizer_starts":len(attempts),"failed_starts":sum(not s["success"] for s in attempts),
        "comparison":comparison,"diagnostics":diagnostics,"source_activity_exact_parity_established":False,
        "environment":{"python":platform.python_version(),"numpy":np.__version__,"scipy":scipy.__version__,"direct_dependencies":dependencies},
        "limitations":["No matched independent experiment, replicate uncertainty, detection limits or independent domain review",
                       "Condition holdouts share the publication and study-informed model development",
                       "Apparent yield and activity-driven hydrolysis do not resolve medium co-substrates or soluble products",
                       "Bootstrap bands are conditional on assumed noise; not empirically validated intervals"]}
    write_json(output/"report.json",report)
    lines = ["# Gelain joint culture benchmark v2", "", plan["design_status"], "", "| Family | Model | Scenario | Mean normalized held-out MSE | Complexity screen |", "|---|---|---|---:|---|"]
    for row in comparison:
        value = f"{row['mean_normalized_mse']:.6g}" if row['complete'] else 'incomplete'
        lines.append(f"| {row['family']} | {row['model']} | {row['scenario']} | {value} | {row['complexity_screen_passed']} |")
    lines += ["",f"{report['successful_numerically_checked_folds']}/{len(folds)} folds passed numerical checks; {report['failed_starts']}/{len(attempts)} starts failed.","",
              "No model is promoted to validated. See validation_readiness/ for exact identities and missing evidence.","",
              "Full diagnostics, failures, profiles, conditional bootstrap and source activity discrepancies are retained in adjacent JSON files."]
    (output/"report.md").write_text("\n".join(lines)+"\n")
    write_json(output/"artifacts.json",{str(p.relative_to(output)):digest(p) for p in sorted(output.rglob("*")) if p.is_file()})
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--workers",type=int,default=2)
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("workers must be positive")
    run(ROOT,args.output.resolve(),args.workers)
