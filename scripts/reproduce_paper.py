"""One command for the software paper's tables and figures and their reproduction, in tiers of cost.

    python scripts/reproduce_paper.py tables     # regenerate paper/tables (Markdown, LaTeX) and paper/figures (SVG, PDF) from the recorded results (seconds)
    python scripts/reproduce_paper.py check      # the committed tables, figures and manifests match the recorded results (seconds)
    python scripts/reproduce_paper.py verify     # recompute cheap checks from the recorded artifacts (about a minute)
    python scripts/reproduce_paper.py stage-a    # re-run stage A and the cross-solver reproduction, compare (about two hours)
    python scripts/reproduce_paper.py full       # also re-run the posterior chains, compare their verdicts (a day of compute)

Every tier is honest about what it recomputes. ``tables`` and ``check`` touch
no science: they format and plot the recorded result files. ``verify`` recomputes the
compiled-core objective at the recorded cross-solver optimum and the
stationarity of the recorded baseline fit and checks every digest chain.
``stage-a`` re-runs the least-squares stage of the model-criticism study and
the COPASI reproduction into an output directory and compares their summary
numbers with the recorded ones. ``full`` also re-runs the Bayesian study and
the three stage B chains through their own scripts and compares verdict-level
fields (convergence flag, identifiability classes, outcomes), because chains
are seeded but platform floating-point differences can move individual
samples. Nothing in this script changes the recorded results under
``data/benchmarks``; re-runs go to ``--output`` (default
``outputs/paper_reproduction``). ``make paper-tables``, ``make paper-check``
and ``make paper-verify`` wrap the cheap tiers.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

for _variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    import os

    os.environ.setdefault(_variable, "1")

from fungal_model.research import gelain_criticism, gelain_petab, paper_figures, paper_tables  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "outputs" / "paper_reproduction"
STAGE_A_TOLERANCE = 1e-6
CROSS_SOLVER_TOLERANCE = 1e-6


def _log(message: str) -> None:
    print(message, flush=True)


def _tables(args: argparse.Namespace) -> int:
    manifest = paper_tables.write_tables(ROOT, args.directory)
    for name, entry in manifest["tables"].items():
        _log(f"{entry['file']}: {len(entry['sources'])} sources")
    figures = paper_figures.write_figures(ROOT, args.figures_directory)
    for name, entry in figures["figures"].items():
        _log(f"{entry['file']} (+ {entry['data_file']}): {len(entry['sources'])} sources")
    return 0


def _check(args: argparse.Namespace) -> int:
    problems = paper_tables.check_tables(ROOT, args.directory) + paper_figures.check_figures(ROOT, args.figures_directory)
    for problem in problems:
        _log(f"MISMATCH: {problem}")
    _log("paper tables and figures consistent with the recorded results" if not problems else f"{len(problems)} problem(s)")
    return 0 if not problems else 1


def _verify(args: argparse.Namespace) -> int:
    started = time.perf_counter()
    checks = paper_tables.verify_recorded_results(ROOT)
    failed = [check for check in checks if not check.passed]
    for check in checks:
        _log(f"[{'ok' if check.passed else 'FAIL'}] {check.name}: {check.detail}")
    _log(f"{len(checks) - len(failed)} of {len(checks)} checks passed in {time.perf_counter() - started:.0f} s")
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps([{"name": c.name, "passed": c.passed, "detail": c.detail} for c in checks], indent=2) + "\n", encoding="utf-8"
        )
    return 0 if not failed else 1


def _compare_stage_a(recorded: dict[str, Any], fresh: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    for model_id, summary in recorded["models"].items():
        for scenario, item in summary["scenarios"].items():
            new = fresh["models"].get(model_id, {}).get("scenarios", {}).get(scenario)
            if new is None:
                problems.append(f"{model_id}/{scenario}: missing from the re-run")
                continue
            old_mse, new_mse = float(item["mean_normalized_mse"]), float(new["mean_normalized_mse"])
            if abs(old_mse - new_mse) > STAGE_A_TOLERANCE * max(abs(old_mse), 1e-12):
                problems.append(f"{model_id}/{scenario}: mean normalized held-out MSE {new_mse:.8g} against recorded {old_mse:.8g}")
            if bool(new["screen"]["passed"]) != bool(item["screen"]["passed"]):
                problems.append(f"{model_id}/{scenario}: screen {new['screen']['passed']} against recorded {item['screen']['passed']}")
    return problems


def _stage_a(args: argparse.Namespace) -> int:
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    _log("stage A of the model-criticism study (every model and scenario, profiles for models that pass the screen)")
    fresh = gelain_criticism.run_stage_a(ROOT, output_dir=output / "criticism", reuse_existing=False, log=_log)
    recorded = json.loads((ROOT / paper_tables.CRITICISM_STAGE_A).read_text(encoding="utf-8"))
    problems = _compare_stage_a(recorded, fresh)
    _log("cross-solver reproduction in COPASI")
    try:
        reproduction = gelain_petab.run_reproduction(ROOT, output_dir=output / "petab", log=_log)
    except Exception as exc:  # noqa: BLE001 - reported, not hidden
        problems.append(f"cross-solver reproduction did not run: {exc}")
    else:
        recorded_cross = json.loads((ROOT / paper_tables.CROSS_SOLVER).read_text(encoding="utf-8"))
        if reproduction["outcome"] != recorded_cross["outcome"]:
            problems.append(f"cross-solver outcome {reproduction['outcome']} against recorded {recorded_cross['outcome']}")
        for key in ("reference_objective", "copasi_best_objective"):
            old, new = float(recorded_cross["optimum_gate"][key]), float(reproduction["optimum_gate"][key])
            if abs(old - new) > CROSS_SOLVER_TOLERANCE * abs(old):
                problems.append(f"cross-solver {key} {new:.9g} against recorded {old:.9g}")
    for problem in problems:
        _log(f"MISMATCH: {problem}")
    _log(f"stage A tier finished in {(time.perf_counter() - started) / 60:.0f} min; {len(problems)} mismatch(es)")
    (output / "stage_a_comparison.json").write_text(json.dumps({"problems": problems}, indent=2) + "\n", encoding="utf-8")
    return 0 if not problems else 1


def _run(command: list[str]) -> None:
    _log("$ " + " ".join(command))
    subprocess.run(command, check=True, cwd=ROOT)


def _full(args: argparse.Namespace) -> int:
    code = _stage_a(args)
    output = args.output
    python = sys.executable
    processes = str(args.processes)
    _log("Bayesian study of the registry case (hours)")
    _run([python, "scripts/run_gelain_2020_bayesian_calibration.py", "--output", str(output / "bayesian"), "--processes", processes])
    recorded = json.loads((ROOT / paper_tables.BAYESIAN_RESULT).read_text(encoding="utf-8"))
    fresh = json.loads((output / "bayesian" / "bayesian_calibration.json").read_text(encoding="utf-8"))
    problems: list[str] = []
    if fresh["converged"] != recorded["converged"]:
        problems.append(f"Bayesian study converged={fresh['converged']} against recorded {recorded['converged']}")
    for symbol, verdict in recorded["identifiability"].items():
        new = fresh["identifiability"].get(symbol, {}).get("class")
        if new != verdict["class"]:
            problems.append(f"Bayesian study {symbol}: class {new} against recorded {verdict['class']}")
    for model_id in gelain_criticism.model_variants(gelain_criticism.load_plan(ROOT)):
        if model_id == gelain_criticism.BASELINE_MODEL:
            continue
        _log(f"stage B chain for {model_id} (hours)")
        _run([
            python, "scripts/run_gelain_2020_model_criticism.py", "stage-b", "--model", model_id,
            "--output", str(output / "criticism"), "--processes", processes,
        ])
        recorded_verdicts = json.loads((ROOT / paper_tables.CRITICISM_STAGE_B / model_id / "verdicts.json").read_text(encoding="utf-8"))
        fresh_verdicts = json.loads((output / "criticism" / "stage_b" / model_id / "verdicts.json").read_text(encoding="utf-8"))
        for key in ("R1_holdout_support", "R2_adequacy", "R3_identification", "outcome", "provisional"):
            if fresh_verdicts.get(key) != recorded_verdicts.get(key):
                problems.append(f"{model_id}: {key} {fresh_verdicts.get(key)} against recorded {recorded_verdicts.get(key)}")
    for problem in problems:
        _log(f"MISMATCH: {problem}")
    (output / "full_comparison.json").write_text(json.dumps({"problems": problems}, indent=2) + "\n", encoding="utf-8")
    return 0 if not problems and code == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="tier", required=True)
    tables = subparsers.add_parser("tables", help="regenerate paper/tables (Markdown and LaTeX) and paper/figures (SVG and PDF) with their manifests from the recorded results")
    tables.add_argument("--directory", type=Path, default=None, help="write the tables elsewhere than paper/tables")
    tables.add_argument("--figures-directory", type=Path, default=None, help="write the figures elsewhere than paper/figures")
    check = subparsers.add_parser("check", help="the committed tables, figures and manifests match the recorded results")
    check.add_argument("--directory", type=Path, default=None)
    check.add_argument("--figures-directory", type=Path, default=None)
    verify = subparsers.add_parser("verify", help="recompute cheap checks from the recorded artifacts")
    verify.add_argument("--report", type=Path, default=None, help="write the check list as JSON")
    stage_a = subparsers.add_parser("stage-a", help="re-run stage A and the cross-solver reproduction and compare")
    stage_a.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    full = subparsers.add_parser("full", help="stage-a plus the Bayesian study and the stage B chains")
    full.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    full.add_argument("--processes", type=int, default=4)
    args = parser.parse_args(argv)
    handlers = {"tables": _tables, "check": _check, "verify": _verify, "stage-a": _stage_a, "full": _full}
    return handlers[args.tier](args)


if __name__ == "__main__":
    sys.exit(main())
