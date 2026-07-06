from __future__ import annotations

from fnmatch import fnmatchcase
import subprocess
from pathlib import Path
from pathlib import PurePosixPath
from typing import Callable

import pytest


ROOT = Path(__file__).resolve().parents[1]
FINAL_GOAL_HTML_PLAN = "foundation_progress/FUNGMOD_FINAL_GOAL_PR_PLAN_2026_06_20.html"


ArtifactCheck = tuple[str, Callable[[str, tuple[str, ...]], bool]]


def _has_directory(parts: tuple[str, ...], directory: str) -> bool:
    return directory in parts


def _has_case_insensitive_directory(parts: tuple[str, ...], directory: str) -> bool:
    return any(part.lower() == directory for part in parts)


GENERATED_ARTIFACT_CHECKS: tuple[ArtifactCheck, ...] = (
    ("pytest cache", lambda _path, parts: _has_directory(parts, ".pytest_cache")),
    ("ruff cache", lambda _path, parts: _has_directory(parts, ".ruff_cache")),
    ("mypy cache", lambda _path, parts: _has_directory(parts, ".mypy_cache")),
    ("coverage html", lambda _path, parts: _has_directory(parts, "htmlcov")),
    ("build directory", lambda _path, parts: _has_directory(parts, "build")),
    ("dist directory", lambda _path, parts: _has_directory(parts, "dist")),
    ("outputs directory", lambda _path, parts: _has_case_insensitive_directory(parts, "outputs")),
    ("egg-info metadata", lambda _path, parts: any(part.endswith(".egg-info") for part in parts)),
    ("coverage data", lambda path, _parts: path in {".coverage", "coverage.xml"}),
    ("python bytecode", lambda path, _parts: path.endswith((".pyc", ".pyo"))),
    ("log file", lambda path, _parts: path.endswith(".log")),
    ("temporary file", lambda path, _parts: path.endswith(".tmp")),
    ("macOS metadata", lambda _path, parts: parts[-1:] == (".DS_Store",)),
    ("python cache directory", lambda _path, parts: _has_directory(parts, "__pycache__")),
    (
        "notebook checkpoint",
        lambda _path, parts: _has_directory(parts, ".ipynb_checkpoints"),
    ),
    (
        "generated progress-report html snapshot",
        lambda path, _parts: fnmatchcase(
            path,
            "foundation_progress/FUNGMOD_PROGRESS_REPORT_*.html",
        ),
    ),
)


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


def _git_check_ignore(path: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", "--quiet", path],
            cwd=ROOT,
            check=False,
            capture_output=True,
        )
    except FileNotFoundError:
        pytest.fail("git executable is unavailable; repository hygiene test requires git check-ignore")

    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False

    stderr = result.stderr.decode("utf-8", errors="replace").strip()
    pytest.fail(f"git check-ignore failed for {path!r}: {stderr}")


def test_no_generated_artifacts_covered_by_gitignore_are_tracked() -> None:
    forbidden: list[str] = []
    for path in _tracked_files():
        parts = PurePosixPath(path).parts
        for label, matches in GENERATED_ARTIFACT_CHECKS:
            if matches(path, parts):
                forbidden.append(f"{label}: {path}")
                break

    assert forbidden == []


def test_generated_progress_report_html_snapshots_are_ignored() -> None:
    assert _git_check_ignore("foundation_progress/FUNGMOD_PROGRESS_REPORT_2026_06_29.html")
    assert _git_check_ignore("foundation_progress/FUNGMOD_PROGRESS_REPORT_draft.html")


def test_final_goal_html_plan_remains_tracked_and_allowed() -> None:
    assert FINAL_GOAL_HTML_PLAN in _tracked_files()
    assert not _git_check_ignore(FINAL_GOAL_HTML_PLAN)
