"""Verify that a built FungMod wheel contains every canonical resource exactly once."""

from __future__ import annotations

import argparse
import hashlib
import zipfile
from pathlib import Path

from stage_packaged_resources import SOURCE_DIRECTORIES, tree_hashes


ROOT = Path(__file__).resolve().parents[1]
WHEEL_PREFIX = "fungal_model/_resources/"


def canonical_resource_hashes(root: Path = ROOT) -> dict[str, str]:
    """Return canonical resource hashes keyed by their staged relative paths."""

    return {
        f"{directory_name}/{relative_path}": digest
        for directory_name in SOURCE_DIRECTORIES
        for relative_path, digest in tree_hashes(root / directory_name).items()
    }


def wheel_resource_hashes(wheel_path: Path) -> tuple[dict[str, str], list[str]]:
    """Return resource hashes and duplicate resource member names from a wheel."""

    with zipfile.ZipFile(wheel_path) as wheel:
        members = [name for name in wheel.namelist() if name.startswith(WHEEL_PREFIX) and not name.endswith("/")]
        duplicates = sorted({name for name in members if members.count(name) > 1})
        hashes = {
            name.removeprefix(WHEEL_PREFIX): hashlib.sha256(wheel.read(name)).hexdigest()
            for name in members
        }
    return hashes, duplicates


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()

    canonical = canonical_resource_hashes()
    built, duplicates = wheel_resource_hashes(args.wheel)
    if duplicates:
        print("Wheel contains duplicate packaged resource members:")
        for duplicate in duplicates:
            print(f"- {duplicate}")
        return 1
    if canonical != built:
        print("Wheel resources differ from the canonical repository roots:")
        for relative_path in sorted(canonical.keys() | built.keys()):
            if canonical.get(relative_path) == built.get(relative_path):
                continue
            if relative_path not in canonical:
                status = "extra wheel resource"
            elif relative_path not in built:
                status = "missing wheel resource"
            else:
                status = "content differs"
            print(f"- {relative_path}: {status}")
        return 1
    print(f"Wheel contains {len(canonical)} canonical resources exactly once with identical bytes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
