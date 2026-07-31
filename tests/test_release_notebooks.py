from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = (
    ROOT / "notebooks" / "examples" / "20_zero_to_complete_virtual_experiment.ipynb",
    ROOT / "notebooks" / "examples" / "21_advanced_capabilities.ipynb",
    ROOT / "notebooks" / "examples" / "22_five_fungal_beta_glucosidases.ipynb",
)

ENSEMBLE_NOTEBOOKS = frozenset(NOTEBOOKS[:2])


def test_release_notebooks_are_deterministically_generated() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/build_release_notebooks.py", "--check"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.mark.parametrize("notebook_path", NOTEBOOKS, ids=lambda path: path.stem)
def test_release_notebook_contract(notebook_path: Path) -> None:
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    code = "\n".join(
        "".join(cell.get("source", []))
        for cell in notebook["cells"]
        if cell.get("cell_type") == "code"
    )
    markdown = "\n".join(
        "".join(cell.get("source", []))
        for cell in notebook["cells"]
        if cell.get("cell_type") == "markdown"
    )

    assert notebook["nbformat"] == 4
    assert "import fungmod as fm" in code
    assert "FUNGMOD_NOTEBOOK_OUTPUT_ROOT" in code
    if notebook_path in ENSEMBLE_NOTEBOOKS:
        assert "FUNGMOD_NOTEBOOK_SAMPLES" in code
    assert "SimulationEngine" not in code
    assert "ReactionDiffusionEngine" not in code
    assert "solve_ivp" not in code
    assert "class " not in code
    assert "not empirical validation" in markdown.lower()
    assert "not whole-fungus" in markdown.lower() or "whole-fungus physiology" in markdown.lower()


def test_fungal_beta_glucosidase_showcase_contract() -> None:
    notebook_path = ROOT / "notebooks" / "examples" / "22_five_fungal_beta_glucosidases.ipynb"
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    code = "\n".join(
        "".join(cell.get("source", []))
        for cell in notebook["cells"]
        if cell.get("cell_type") == "code"
    )
    markdown = "\n".join(
        "".join(cell.get("source", []))
        for cell in notebook["cells"]
        if cell.get("cell_type") == "markdown"
    ).lower()

    assert "five_fungal_beta_glucosidases.yml" in code
    assert "fm.run_configured_model(" in code
    assert "competitive_inhibition" in code
    assert "cellobiose_to_two_glucose" in code
    assert "with_glucose_inhibition" in code
    assert "without_glucose_inhibition" in code
    assert "scenario_summary.csv" in code
    assert "ranking_allowed" in code
    assert "10.1002/bit.22885" in markdown
    assert "purified enzymes" in markdown
    assert "not a whole-fungus capability model" in code
    assert "transglycosylation" in markdown


@pytest.mark.parametrize("notebook_path", NOTEBOOKS, ids=lambda path: path.stem)
def test_release_notebook_executes(
    notebook_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("FUNGMOD_NOTEBOOK_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("FUNGMOD_NOTEBOOK_SAMPLES", "2")
    monkeypatch.setenv("MPLBACKEND", "Agg")
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    namespace: dict[str, object] = {"__name__": f"__{notebook_path.stem}_smoke__"}

    for cell in notebook["cells"]:
        if cell.get("cell_type") != "code":
            continue
        source = "".join(cell.get("source", []))
        exec(compile(source, str(notebook_path), "exec"), namespace)

    generated_files = tuple(path for path in tmp_path.rglob("*") if path.is_file())
    assert generated_files
    assert any(path.name == "output_manifest.json" for path in generated_files)
