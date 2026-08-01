"""Deterministically stage canonical repository data for a built distribution."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path


SOURCE_DIRECTORIES = ("data", "data_registry")


def tree_hashes(root: Path) -> dict[str, str]:
    """Return SHA-256 hashes for every regular file below ``root``."""

    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def stage_packaged_resources(source_root: Path, destination_root: Path) -> None:
    """Copy the two canonical resource roots into a clean ``_resources`` tree."""

    source_root = source_root.resolve()
    destination_root = destination_root.resolve(strict=False)
    if destination_root.name != "_resources":
        raise ValueError("Packaged resource staging destination must be named '_resources'.")
    canonical_directories = tuple((source_root / name).resolve() for name in SOURCE_DIRECTORIES)
    if destination_root == source_root or any(
        destination_root == directory or directory in destination_root.parents
        for directory in canonical_directories
    ):
        raise ValueError("Packaged resource staging must not write inside a canonical resource directory.")

    missing = [name for name in SOURCE_DIRECTORIES if not (source_root / name).is_dir()]
    if missing:
        raise FileNotFoundError(f"Missing canonical resource directories: {', '.join(missing)}")

    if destination_root.exists():
        shutil.rmtree(destination_root)
    destination_root.mkdir(parents=True)
    for directory_name in SOURCE_DIRECTORIES:
        shutil.copytree(source_root / directory_name, destination_root / directory_name)


def resource_mismatches(source_root: Path, packaged_root: Path) -> list[str]:
    """Describe missing, extra, or byte-different staged resource files."""

    messages: list[str] = []
    for directory_name in SOURCE_DIRECTORIES:
        source_hashes = tree_hashes(source_root / directory_name)
        packaged_hashes = tree_hashes(packaged_root / directory_name)
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


__all__ = ["SOURCE_DIRECTORIES", "resource_mismatches", "stage_packaged_resources", "tree_hashes"]
