#!/usr/bin/env python3
"""Write review-only FungMod proposals from a frozen SABIO-RK snapshot."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fungal_model.sources.sabiork import SabioRKSource, SabioRKSourceError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse a frozen SABIO-RK kinetic-law snapshot and write review-only FungMod proposals."
    )
    parser.add_argument("--snapshot", required=True, type=Path, help="Frozen kinlaw_entries_*.json file.")
    parser.add_argument("--output-dir", required=True, type=Path, help="Proposal bundle output directory.")
    parser.add_argument("--query", default="", help="Original SABIO-RK query, if known.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = SabioRKSource(cache_dir=args.snapshot.parent)
    try:
        snapshot = source.load_kinlaw_entries(args.snapshot, query=args.query)
        records = source.parse_reaction_records(snapshot)
        proposal = source.propose_fungmod_records(
            records,
            source_query=snapshot.query,
            source_snapshot_path=str(snapshot.export_path),
        )
        result = proposal.write(args.output_dir)
    except (OSError, SabioRKSourceError, ValueError) as exc:
        print(f"SABIO-RK proposal generation failed: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote SABIO-RK proposal bundle: {result.output_directory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
