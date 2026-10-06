"""Reproduce the Gelain 2020 registry-case fit in COPASI through PEtab. Retrospective; never validation.

    python scripts/run_gelain_2020_petab_reproduction.py --output data/benchmarks/gelain_2020_petab/results

Exports the PEtab problem the frozen plan describes, imports it into COPASI,
simulates it at FungMod's optimum, fits it from that optimum and from the
planned random starts, and writes ``comparison.json`` and ``report.md``.
Requires the ``copasi`` extra (``pip install fungmod[copasi]``).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from fungal_model.research import gelain_petab

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, default=ROOT / gelain_petab.RESULTS_PATH)
    parser.add_argument("--starts", type=int, default=None, help="override the planned number of random starts (recorded as a deviation)")
    parser.add_argument("--seed", type=int, default=None, help="override the planned seed (recorded as a deviation)")
    args = parser.parse_args(argv)
    started = time.monotonic()

    def log(message: str) -> None:
        print(f"[{time.monotonic() - started:8.1f} s] {message}", flush=True)

    comparison = gelain_petab.run_reproduction(ROOT, output_dir=args.output, starts=args.starts, seed=args.seed, log=log)
    gate = comparison["optimum_gate"]
    log(
        f"COPASI best objective {gate['copasi_best_objective']:.10g} vs FungMod {gate['reference_objective']:.10g}; "
        f"outcome {comparison['outcome']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
