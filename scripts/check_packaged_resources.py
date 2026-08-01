"""Verify deterministic package-data staging from the canonical data roots."""

from __future__ import annotations

import tempfile
from pathlib import Path

from stage_packaged_resources import resource_mismatches, stage_packaged_resources


ROOT = Path(__file__).resolve().parents[1]
TRACKED_MIRROR_ROOT = ROOT / "src" / "fungal_model" / "_resources"


def main() -> int:
    """Run the drift check."""

    if TRACKED_MIRROR_ROOT.is_dir() and any(path.is_file() for path in TRACKED_MIRROR_ROOT.rglob("*")):
        print(f"Tracked package-resource mirror still exists: {TRACKED_MIRROR_ROOT}")
        return 1
    with tempfile.TemporaryDirectory(prefix="fungmod-resource-stage-") as temporary:
        staged_root = Path(temporary) / "_resources"
        stage_packaged_resources(ROOT, staged_root)
        mismatches = resource_mismatches(ROOT, staged_root)
        if mismatches:
            print("Staged FungMod resources are not synchronized:")
            for mismatch in mismatches:
                print(f"- {mismatch}")
            return 1
    print("Canonical data/ and data_registry/ resources stage exactly once without a tracked mirror.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
