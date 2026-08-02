"""Single-command, deterministic reproduction of FungMod's headline artifacts.

Running this script from a repository checkout regenerates, with fixed seeds and
fixed configurations, the three artifacts that most directly demonstrate the
package:

1. The SABIO-RK Reaction 618 beta-glucosidase virtual experiment (report bundle).
2. The configured dynamic-thermodynamics showcase model run.
3. The Alvarez-Gonzalez 2022 same-source, no-calibration literature comparison.

Everything is written under a single output directory (default
``outputs/reproduction``). The run is deterministic: identical inputs and seeds
produce identical numerical results across machines.

Usage::

    python scripts/reproduce.py                 # full reproduction
    python scripts/reproduce.py --quick         # fast smoke (few samples)
    python scripts/reproduce.py --output-dir DIR

This is the script behind ``make reproduce``.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "outputs" / "reproduction"
REACTION_618_SEED = 618


def _load_literature_comparison():
    """Import ``run_comparison`` from the sibling literature script by path."""

    module_path = ROOT / "scripts" / "run_literature_time_course_comparison.py"
    spec = importlib.util.spec_from_file_location("_fungmod_literature_comparison", module_path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError(f"Could not load {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run_comparison


def reproduce(*, output_dir: Path, n_samples: int) -> dict[str, object]:
    """Run the full deterministic reproduction and return a summary dict."""

    # Force a non-interactive plotting backend so the run is headless and stable.
    os.environ.setdefault("MPLBACKEND", "Agg")

    import fungmod as fm

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary: dict[str, object] = {"fungmod_version": fm.__version__, "steps": {}}
    steps: dict[str, object] = summary["steps"]  # type: ignore[assignment]

    # --- Step 1: Reaction 618 virtual experiment -----------------------------
    print(f"[1/3] Reaction 618 virtual experiment (n_samples={n_samples}, seed={REACTION_618_SEED})")
    study = fm.virtual_experiment(
        fungi="beta-glucosidase source",
        substrates="cellobiose",
        environments="SABIO-RK Reaction 618 selected assay conditions",
    )
    reaction_618_dir = output_dir / "reaction_618"
    result = study.simulate(
        mode="exploratory",
        n_samples=n_samples,
        seed=REACTION_618_SEED,
        output_dir=reaction_618_dir,
        quicklook=False,
    )
    result.write_report(reaction_618_dir / "report", include_html=True, include_index=True)
    steps["reaction_618"] = {
        "output_dir": str(reaction_618_dir),
        "final_metrics": result.final_metrics(),
    }

    # --- Step 2: Configured dynamic-thermodynamics showcase ------------------
    print("[2/3] Configured dynamic-thermodynamics showcase model")
    configured_dir = output_dir / "configured_showcase"
    configured = fm.run_configured_model(
        fm.example_data_path("model_configs/showcase_dynamic_thermodynamics.yml"),
        output_dir=configured_dir,
    )
    steps["configured_showcase"] = {
        "output_dir": str(configured_dir),
        "solver_success": bool(configured.solver_metadata["success"]),
    }

    # --- Step 3: Literature same-source comparison ---------------------------
    print("[3/3] Alvarez-Gonzalez 2022 no-calibration literature comparison")
    run_comparison = _load_literature_comparison()
    comparison_dir = output_dir / "literature_comparison"
    comparison = run_comparison(output_dir=comparison_dir)
    steps["literature_comparison"] = {
        "output_dir": str(comparison_dir),
        "metrics": comparison.metrics,
    }

    summary_path = output_dir / "reproduction_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    summary["summary_path"] = str(summary_path)
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Fast smoke reproduction with a small number of samples.",
    )
    parser.add_argument(
        "--n-samples",
        type=int,
        default=None,
        help="Override the number of Monte Carlo samples (default 32, or 4 with --quick).",
    )
    args = parser.parse_args(argv)

    n_samples = args.n_samples if args.n_samples is not None else (4 if args.quick else 32)
    summary = reproduce(output_dir=args.output_dir, n_samples=n_samples)

    print("\nReproduction complete.")
    print(f"  fungmod version : {summary['fungmod_version']}")
    print(f"  summary written : {summary['summary_path']}")
    print(f"  artifacts under : {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
