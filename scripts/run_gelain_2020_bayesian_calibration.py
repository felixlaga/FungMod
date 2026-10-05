"""Posterior sampling of the T. harzianum cellulose registry case. Retrospective; never validation.

Run from the repository root after installation:

    python scripts/run_gelain_2020_bayesian_calibration.py --output outputs/gelain-bayesian --processes 4

The run checkpoints its chain in the output directory and resumes from it
when restarted with the same plan.
"""

from __future__ import annotations

import argparse
import multiprocessing
import os
import sys
import time
from pathlib import Path
from typing import Any

for _variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    # One BLAS thread per worker process: the likelihood is a scalar ODE integration, not a matrix workload.
    os.environ.setdefault(_variable, "1")

import numpy as np  # noqa: E402

from fungal_model.research import gelain_bayesian  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
_STUDY: gelain_bayesian.StudyProblem | None = None


def _log_posterior(vector: np.ndarray) -> float:
    assert _STUDY is not None
    return _STUDY.problem.log_posterior(vector)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Output directory (created if missing).")
    parser.add_argument(
        "--plan",
        type=Path,
        default=None,
        help="Plan file relative to the repository root (default: the primary plan).",
    )
    parser.add_argument("--processes", type=int, default=1, help="Worker processes for likelihood evaluation.")
    parser.add_argument("--steps", type=int, default=None, help="Override the planned step count (development only).")
    parser.add_argument("--burn-in", type=int, default=None, help="Override the planned burn-in (development only).")
    parser.add_argument("--walkers", type=int, default=None, help="Override the planned walker count (development only).")
    parser.add_argument("--checkpoint-every", type=int, default=250)
    parser.add_argument("--no-resume", action="store_true", help="Ignore an existing checkpoint.")
    parser.add_argument("--skip-predictive", action="store_true", help="Skip the posterior predictive bands.")
    args = parser.parse_args(argv)

    global _STUDY
    started = time.perf_counter()
    _STUDY = gelain_bayesian.build_study(
        ROOT, n_steps=args.steps, burn_in=args.burn_in, n_walkers=args.walkers, plan_path=args.plan
    )
    study = _STUDY

    def log(message: str) -> None:
        print(f"[{time.perf_counter() - started:8.1f} s] {message}", flush=True)

    log(
        f"study built: {study.problem.dimension} coordinates, {len(study.problem.conditions)} conditions, "
        f"{study.settings.n_walkers} walkers x {study.settings.n_steps} steps"
    )
    output = args.output
    overrides: dict[str, Any] = {k: v for k, v in (("steps", args.steps), ("burn_in", args.burn_in), ("walkers", args.walkers)) if v is not None}
    if overrides:
        log(f"development overrides active: {overrides}")
    if args.processes > 1:
        context = multiprocessing.get_context("fork")
        with context.Pool(args.processes) as pool:
            run = gelain_bayesian.sample_study(
                study,
                output,
                map_function=pool.map,
                checkpoint_every=args.checkpoint_every,
                resume=not args.no_resume,
                log=log,
                log_posterior=_log_posterior,
            )
    else:
        run = gelain_bayesian.sample_study(
            study, output, checkpoint_every=args.checkpoint_every, resume=not args.no_resume, log=log
        )
    log(f"sampling finished: {run.evaluations} evaluations, {run.failed_evaluations} failed")
    result = gelain_bayesian.analyze_study(study, run, with_predictive=not args.skip_predictive)
    paths = gelain_bayesian.write_study_outputs(study, result, output, root=ROOT)
    log(f"converged={result.converged}; identified={result.identified_parameters()}")
    for symbol, verdict in result.identifiability.items():
        log(f"  {symbol}: {verdict['class']} {verdict['credible_interval']}")
    log(f"wrote {sorted(str(path.relative_to(output)) for path in paths.values())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
