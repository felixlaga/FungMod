#!/usr/bin/env python3
"""Curate Km/kcat ranges from a saved SABIO-RK Reaction 618 export."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fungal_model.data.sabiork import (  # noqa: E402
    SabioRKParseError,
    curate_reaction_618_parameter_ranges,
    load_sabiork_kinlaw_export,
    write_sabiork_parameter_range_report,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Curate literature-derived Km/kcat ranges from a local saved "
            "SABIO-RK Reaction 618 kinetic-law export."
        )
    )
    parser.add_argument("--input", required=True, type=Path, help="Path to kinlaw_entries_reaction_618.json.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for curated outputs. Defaults to sibling curated/ for raw snapshots.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = args.output_dir or _default_output_dir(args.input)
    try:
        export = load_sabiork_kinlaw_export(args.input)
        report = curate_reaction_618_parameter_ranges(export)
        report_path = write_sabiork_parameter_range_report(report, output_dir)
    except (OSError, SabioRKParseError) as exc:
        print(f"SABIO-RK parameter range curation failed: {exc}", file=sys.stderr)
        return 1
    print(f"Included SABIO-RK EntryIDs: {', '.join(report.included_entry_ids)}")
    print(f"Saved parameter range report: {report_path}")
    return 0


def _default_output_dir(input_path: Path) -> Path:
    if input_path.parent.name == "raw":
        return input_path.parent.parent / "curated"
    return input_path.parent


if __name__ == "__main__":
    raise SystemExit(main())
