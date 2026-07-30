"""Fail when wheel-packaged data assets drift from repository source assets."""

from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESOURCE_ROOT = ROOT / "src" / "fungal_model" / "_resources"
SOURCE_DIRECTORIES = ("data", "data_registry")


def tree_hashes(root: Path) -> dict[str, str]:
    """Return SHA-256 hashes for every regular file below ``root``."""

    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def resource_mismatches() -> list[str]:
    """Describe missing, extra, or byte-different packaged resource files."""

    messages: list[str] = []
    for directory_name in SOURCE_DIRECTORIES:
        source_hashes = tree_hashes(ROOT / directory_name)
        packaged_hashes = tree_hashes(RESOURCE_ROOT / directory_name)
        for relative_path in sorted(source_hashes.keys() | packaged_hashes.keys()):
            source_hash = source_hashes.get(relative_path)
            packaged_hash = packaged_hashes.get(relative_path)
            if source_hash == packaged_hash:
                continue
            if source_hash is None:
                status = "extra packaged file"
            elif packaged_hash is None:
                status = "missing packaged file"
            else:
                status = "content differs"
            messages.append(f"{directory_name}/{relative_path}: {status}")
    return messages


def main() -> int:
    """Run the drift check."""

    mismatches = resource_mismatches()
    if mismatches:
        print("Packaged FungMod resources are not synchronized:")
        for mismatch in mismatches:
            print(f"- {mismatch}")
        return 1
    print("Packaged FungMod resources match data/ and data_registry/.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
