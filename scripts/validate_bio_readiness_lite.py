#!/usr/bin/env python
"""Validate BIO-READINESS-LITE mechanism proposals."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from fungal_model.validation.bio_readiness import validate_bio_mechanism_proposal_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate BIO-* mechanism proposals against the BIO-READINESS-LITE gate."
    )
    parser.add_argument("proposal", nargs="+", help="Path to a BIO mechanism proposal YAML file.")
    parser.add_argument(
        "--allow-template",
        action="store_true",
        help="Allow placeholder template values while still checking BIO/CASE/DATA structure.",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON reports.")
    args = parser.parse_args(argv)

    reports = [
        validate_bio_mechanism_proposal_file(Path(path), allow_template=args.allow_template)
        for path in args.proposal
    ]
    if args.json:
        print(json.dumps([report.to_dict() for report in reports], indent=2, sort_keys=True))
    else:
        for report in reports:
            status = "PASS" if report.passed else "FAIL"
            print(f"{status} {report.proposal_path}")
            for issue in report.issues:
                print(f"  [{issue.severity}] {issue.field}: {issue.message}")
    return 0 if all(report.passed for report in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
