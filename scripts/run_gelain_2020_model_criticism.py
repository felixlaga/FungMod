"""Run the preregistered Gelain 2020 model-criticism study. Retrospective; never validation.

Stage A (least-squares whole-condition holdouts, screen and profiles):

    python scripts/run_gelain_2020_model_criticism.py stage-a --output data/benchmarks/gelain_2020_criticism/results

Stage B (posterior sampling of one model, centred on its stage A all-condition fit):

    python scripts/run_gelain_2020_model_criticism.py stage-b --model M1_induction_state \\
        --output data/benchmarks/gelain_2020_criticism/results --processes 4

Stage B checkpoints its chain in ``<output>/stage_b/<model>/`` and resumes
from it when restarted with the same plan.

Refreshing recorded stage B verdicts after stage A was re-run under an amendment:

    python scripts/run_gelain_2020_model_criticism.py refresh-verdicts --output data/benchmarks/gelain_2020_criticism/results
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import sys
import time
from pathlib import Path
from typing import Any

for _variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_variable, "1")

import numpy as np  # noqa: E402

from fungal_model.research import gelain_criticism  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
_STUDY: gelain_criticism.PosteriorStudy | None = None


def _log_posterior(vector: np.ndarray) -> float:
    assert _STUDY is not None
    return _STUDY.problem.log_posterior(vector)


def _stage_a(args: argparse.Namespace, log: Any) -> int:
    comparison = gelain_criticism.run_stage_a(
        ROOT,
        output_dir=args.output,
        models=args.models,
        scenarios=args.scenarios,
        starts=args.starts,
        max_nfev=args.max_nfev,
        profiles=not args.skip_profiles,
        log=log,
    )
    for model_id, summary in comparison["models"].items():
        for scenario, item in summary["scenarios"].items():
            log(f"{model_id} / {scenario}: mean normalized held-out MSE {item['mean_normalized_mse']:.4g}; screen {'passed' if item['screen']['passed'] else 'failed'}")
    return 0


def _stage_b(args: argparse.Namespace, log: Any) -> int:
    global _STUDY
    fit_path = args.output / "stage_a" / args.model / "full_fit_primary.json"
    if not fit_path.exists():
        raise SystemExit(f"Stage A all-condition fit not found at {fit_path}; run stage-a first.")
    fit = json.loads(fit_path.read_text(encoding="utf-8"))
    if not fit.get("success"):
        raise SystemExit(f"Stage A all-condition fit for {args.model} did not succeed; stage B needs a centre.")
    center = {entry["symbol"]: float(entry["value"]) for entry in fit["parameters"]}
    _STUDY = gelain_criticism.build_posterior_study(
        ROOT, args.model, center, n_steps=args.steps, burn_in=args.burn_in, n_walkers=args.walkers
    )
    study = _STUDY
    log(
        f"{args.model}: {study.problem.dimension} coordinates, {len(study.problem.conditions)} conditions, "
        f"{study.settings.n_walkers} walkers x {study.settings.n_steps} steps"
    )
    output = args.output / "stage_b" / args.model
    if args.processes > 1:
        context = multiprocessing.get_context("fork")
        with context.Pool(args.processes) as pool:
            run = gelain_criticism.sample_posterior_study(
                study, output, map_function=pool.map, checkpoint_every=args.checkpoint_every,
                resume=not args.no_resume, log=log, log_posterior=_log_posterior,
            )
    else:
        run = gelain_criticism.sample_posterior_study(
            study, output, checkpoint_every=args.checkpoint_every, resume=not args.no_resume, log=log
        )
    log(f"sampling finished: {run.evaluations} evaluations, {run.failed_evaluations} failed")
    result, coverage = gelain_criticism.analyze_posterior_study(study, run, with_predictive=not args.skip_predictive)
    paths = gelain_criticism.write_posterior_outputs(study, result, coverage, output, root=ROOT)
    log(f"converged={result.converged}; identified={result.identified_parameters()}")
    for symbol, verdict in result.identifiability.items():
        log(f"  {symbol}: {verdict['class']} {verdict['credible_interval']}")
    if coverage is not None:
        log(f"coverage: {coverage['overall']['all_observables']['fraction']:.0%} of observations inside the band")
    log(f"wrote {sorted(str(path.relative_to(output)) for path in paths.values())}")
    return 0


def _refresh_verdicts(args: argparse.Namespace, log: Any) -> int:
    stage_b = args.output / "stage_b"
    folders = sorted(path for path in stage_b.glob("*/verdicts.json")) if stage_b.exists() else []
    if not folders:
        raise SystemExit(f"No recorded stage B verdicts under {stage_b}.")
    for verdicts_path in folders:
        verdicts = gelain_criticism.refresh_stage_b_verdicts(ROOT, verdicts_path.parent)
        log(f"{verdicts_path.parent.name}: R1 {verdicts['R1_holdout_support']}; outcome {verdicts['outcome']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="stage", required=True)
    stage_a = subparsers.add_parser("stage-a", help="least-squares holdouts, screen and profiles")
    stage_a.add_argument("--output", type=Path, default=ROOT / gelain_criticism.RESULTS_PATH)
    stage_a.add_argument("--models", nargs="*", default=None, help="Model identifiers (default: every declared model).")
    stage_a.add_argument("--scenarios", nargs="*", default=None, help="Scenario names (default: both).")
    stage_a.add_argument("--starts", type=int, default=None, help="Override the planned start count (development only).")
    stage_a.add_argument("--max-nfev", type=int, default=None, help="Override the planned evaluation cap (development only).")
    stage_a.add_argument("--skip-profiles", action="store_true")
    stage_b = subparsers.add_parser("stage-b", help="posterior sampling of one model")
    stage_b.add_argument("--model", required=True)
    stage_b.add_argument("--output", type=Path, default=ROOT / gelain_criticism.RESULTS_PATH)
    stage_b.add_argument("--processes", type=int, default=1)
    stage_b.add_argument("--steps", type=int, default=None, help="Override the planned step count (development only).")
    stage_b.add_argument("--burn-in", type=int, default=None)
    stage_b.add_argument("--walkers", type=int, default=None)
    stage_b.add_argument("--checkpoint-every", type=int, default=250)
    stage_b.add_argument("--no-resume", action="store_true")
    stage_b.add_argument("--skip-predictive", action="store_true")
    refresh = subparsers.add_parser(
        "refresh-verdicts", help="recompute every recorded stage B verdict against the stage A comparison on disk"
    )
    refresh.add_argument("--output", type=Path, default=ROOT / gelain_criticism.RESULTS_PATH)
    args = parser.parse_args(argv)
    started = time.perf_counter()

    def log(message: str) -> None:
        print(f"[{time.perf_counter() - started:8.1f} s] {message}", flush=True)

    if args.stage == "stage-a":
        return _stage_a(args, log)
    if args.stage == "refresh-verdicts":
        return _refresh_verdicts(args, log)
    return _stage_b(args, log)


if __name__ == "__main__":
    sys.exit(main())
