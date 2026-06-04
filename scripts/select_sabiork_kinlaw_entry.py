#!/usr/bin/env python3
"""Select one SABIO-RK Reaction 618 kinetic-law entry from a saved export."""

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
    load_sabiork_kinlaw_export,
    select_reaction_618_candidate,
    write_sabiork_selection_outputs,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Select a REAL-001B SABIO-RK Reaction 618 candidate from a local raw export."
    )
    parser.add_argument("--input", required=True, type=Path, help="Path to kinlaw_entries_reaction_618.json.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for selected_kinlaw_entry_<EntryID>.json and selection_report.json. Defaults to input parent.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = args.output_dir or args.input.parent
    try:
        export = load_sabiork_kinlaw_export(args.input)
        selection = select_reaction_618_candidate(export)
        selected_path, report_path = write_sabiork_selection_outputs(selection, output_dir)
    except (OSError, SabioRKParseError) as exc:
        print(f"SABIO-RK selection failed: {exc}", file=sys.stderr)
        return 1
    print(f"Selected SABIO-RK EntryID: {selection.selected_entry_id}")
    print(f"Saved selected raw entry: {selected_path}")
    print(f"Saved selection report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
