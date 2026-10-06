"""Run the De Ligne 2019 colony comparison (COLONY-001) under its frozen plan.

Stage 0 (software checks, no fit)::

    python scripts/run_de_ligne_2019_colony_comparison.py stage-0 \\
        --output data/benchmarks/de_ligne_2019_colony/results

Stage 0 fits the plan's error model to the committed observations, times one
condition on the radial calibration grid, and records the grid, solver and
symmetry checks the plan requires before any fit. ``--skip-cartesian`` records
the symmetry check as not run; ``--cartesian-cells`` sets the reference grid.
Every output cites the plan's SHA-256.

Checking recorded stage 0 outputs against the current code and plan::

    python scripts/run_de_ligne_2019_colony_comparison.py check

``check`` recomputes the error models and compares them with the recorded
ones exactly, verifies that the recorded inputs cite the current plan digest,
and reports the recorded check verdicts; it does not repeat the solves.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from fungal_model.research import colony_comparison

ROOT = Path(__file__).resolve().parents[1]


def _log(message: str) -> None:
    print(message, flush=True)


def _stage_0(args: argparse.Namespace) -> int:
    colony_comparison.run_stage_0(
        ROOT,
        Path(args.output) if args.output else None,
        cartesian_cells=None if args.skip_cartesian else int(args.cartesian_cells),
        log=_log,
    )
    return 0


def _check(args: argparse.Namespace) -> int:
    output = ROOT / (Path(args.output) if args.output else colony_comparison.RESULTS_PATH) / "stage_0"
    plan = colony_comparison.load_plan(ROOT)
    problems: list[str] = []
    inputs = json.loads((output / "inputs.json").read_text(encoding="utf-8"))
    chain = {plan["_sha256"], *(entry["previous_sha256"] for entry in plan["amendments"])}
    if inputs["plan_sha256"] not in chain:
        problems.append(f"inputs.json cites plan digest {inputs['plan_sha256']}, not in the amendment chain")
    recorded = json.loads((output / "error_models.json").read_text(encoding="utf-8"))
    for species in plan["data"]["species_order"]:
        observations = colony_comparison.load_observations(ROOT, plan, species)
        fitted = colony_comparison.fit_error_models(observations, plan)
        for (quantity, temperature, humidity), model in fitted.items():
            name = f"{quantity}_{temperature}c_{humidity}rh"
            stored = recorded["series"][species].get(name)
            if stored is None:
                problems.append(f"{species} {name}: missing from the recorded error models")
                continue
            for field in ("s0", "s1", "readable_rows", "pooled", "pooled_rows"):
                if stored[field] != getattr(model, field):
                    problems.append(f"{species} {name}: {field} recorded {stored[field]}, recomputed {getattr(model, field)}")
    checks = json.loads((output / "checks.json").read_text(encoding="utf-8"))
    for name in ("grid", "solver", "symmetry"):
        entry = checks.get(name, {})
        status = entry.get("status", "run")
        verdict = entry.get("passed") if status == "run" else status
        _log(f"{name}: {verdict}")
    if problems:
        _log("\n".join(problems))
        return 1
    _log(f"check passed: stage 0 outputs under {output} are consistent with the plan and the data")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    subparsers = parser.add_subparsers(dest="command", required=True)
    stage_0 = subparsers.add_parser("stage-0", help="record the plan's software checks and error models")
    stage_0.add_argument("--output", default=None, help="results directory (default: the plan's)")
    stage_0.add_argument("--cartesian-cells", default=80, type=int, help="cells per axis of the cartesian reference grid")
    stage_0.add_argument("--skip-cartesian", action="store_true", help="record the symmetry check as not run")
    stage_0.set_defaults(handler=_stage_0)
    check = subparsers.add_parser("check", help="verify recorded stage 0 outputs against the plan and the data")
    check.add_argument("--output", default=None)
    check.set_defaults(handler=_check)
    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except colony_comparison.ColonyComparisonError as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(2)
