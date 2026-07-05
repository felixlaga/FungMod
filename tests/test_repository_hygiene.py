from __future__ import annotations

import subprocess
from pathlib import Path
from pathlib import PurePosixPath

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _tracked_files() -> list[str]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            check=False,
            capture_output=True,
        )
    except FileNotFoundError:
        pytest.fail("git executable is unavailable; repository hygiene test requires git ls-files")

    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        pytest.fail(f"git ls-files failed for repository hygiene test: {stderr}")

    return [
        path.decode("utf-8", errors="replace")
        for path in result.stdout.split(b"\0")
        if path
    ]


def test_no_generated_metadata_files_are_tracked() -> None:
    forbidden: list[str] = []

    for path in _tracked_files():
        parts = PurePosixPath(path).parts
        if (
            path == ".DS_Store"
            or path.endswith("/.DS_Store")
            or path.endswith(".pyc")
            or "__pycache__" in parts
            or ".ipynb_checkpoints" in parts
        ):
            forbidden.append(path)

    assert forbidden == []
