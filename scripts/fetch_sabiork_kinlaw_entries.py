#!/usr/bin/env python3
"""Fetch and freeze a SABIO-RK kinetic-law JSON export."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from urllib.error import HTTPError, URLError


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fungal_model.sources.sabiork.fetch import (  # noqa: E402
    BASE_URL,
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    ENDPOINT,
    EXPECTED_REACTION_618_TOTAL_COUNT,
    HTTPResponseSnapshot,
    SabioRKFetchError,
    build_fetch_metadata,
    build_kinlaw_url,
    fetch_and_save_export,
    validate_kinlaw_export,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch a SABIO-RK kinlaw-entry JSON export and freeze it locally."
    )
    parser.add_argument("--query", required=True, help="SABIO-RK Solr query string, e.g. SabioReactionID:618.")
    parser.add_argument("--output-dir", required=True, type=Path, help="Directory where raw JSON files are saved.")
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--endpoint", default=ENDPOINT)
    parser.add_argument("--page", default=DEFAULT_PAGE, type=int)
    parser.add_argument("--pageSize", default=DEFAULT_PAGE_SIZE, type=int)
    parser.add_argument("--timeout-seconds", default=30.0, type=float)
    parser.add_argument(
        "--expected-total-count",
        default=EXPECTED_REACTION_618_TOTAL_COUNT,
        type=int,
        help="Expected total_count for warning-only drift detection. Use -1 to disable.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    expected_total_count = None if args.expected_total_count < 0 else args.expected_total_count
    try:
        export_path, metadata_path = fetch_and_save_export(
            query=args.query,
            output_dir=args.output_dir,
            base_url=args.base_url,
            endpoint=args.endpoint,
            page=args.page,
            page_size=args.pageSize,
            expected_total_count=expected_total_count,
            timeout_seconds=args.timeout_seconds,
        )
    except (SabioRKFetchError, HTTPError, URLError, OSError) as exc:
        print(f"SABIO-RK fetch failed: {exc}", file=sys.stderr)
        return 1
    print(f"Saved raw export: {export_path}")
    print(f"Saved fetch metadata: {metadata_path}")
    return 0


__all__ = [
    "BASE_URL",
    "DEFAULT_PAGE",
    "DEFAULT_PAGE_SIZE",
    "ENDPOINT",
    "EXPECTED_REACTION_618_TOTAL_COUNT",
    "HTTPResponseSnapshot",
    "SabioRKFetchError",
    "build_fetch_metadata",
    "build_kinlaw_url",
    "fetch_and_save_export",
    "main",
    "parse_args",
    "validate_kinlaw_export",
]


if __name__ == "__main__":
    raise SystemExit(main())
