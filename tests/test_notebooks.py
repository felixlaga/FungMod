from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


NOTEBOOKS = [
    "00_quickstart.ipynb",
    "01_config_entity_inspection.ipynb",
    "02_failure_report.ipynb",
    "03_configured_outputs.ipynb",
]

PRODUCT_NOTEBOOKS = [
    "10_virtual_experiment_product_tour.ipynb",
]


NOTEBOOK_DIR = Path(__file__).resolve().parents[1] / "notebooks" / "examples"

PUBLIC_API_PATTERNS = (
    re.compile(r"(^|\n)\s*(from\s+fungal_model\s+import|import\s+fungal_model)\b"),
    re.compile(r"\brun_configured_model\s*\("),
)

HIDDEN_IMPLEMENTATION_PATTERNS = {
    "process class": re.compile(r"(^|\n)\s*class\s+\w*Process\b"),
    "solver class": re.compile(r"(^|\n)\s*class\s+\w*Solver\b"),
    "process factory class": re.compile(r"(^|\n)\s*class\s+\w*Factory\b"),
    "rate-law function": re.compile(r"(^|\n)\s*def\s+\w*rate\w*\s*\("),
    "solver function": re.compile(r"(^|\n)\s*def\s+\w*solver\w*\s*\("),
    "low-level solver import": re.compile(r"(^|\n)\s*(from\s+fungal_model\.solvers|from\s+scipy\.integrate)"),
    "core engine import": re.compile(r"(^|\n)\s*from\s+fungal_model\.core\.simulation\b"),
    "process internals import": re.compile(r"(^|\n)\s*from\s+fungal_model\.processes\b"),
    "direct scipy solver call": re.compile(r"\bsolve_ivp\s*\("),
    "legacy rate-law class": re.compile(r"\bRateLaw\s*="),
    "legacy PET rate law": re.compile(r"\bPETSurfaceHydrolysisRateLaw\b"),
    "reaction-diffusion engine": re.compile(r"\bReactionDiffusionEngine\b"),
    "simulation engine": re.compile(r"\bSimulationEngine\b"),
}


def load_notebook(name: str) -> dict:
    path = NOTEBOOK_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


def code_cells(notebook: dict) -> list[str]:
    return [
        "".join(cell.get("source", []))
        for cell in notebook["cells"]
        if cell.get("cell_type") == "code"
    ]


def markdown_cells(notebook: dict) -> list[str]:
    return [
        "".join(cell.get("source", []))
        for cell in notebook["cells"]
        if cell.get("cell_type") == "markdown"
    ]


def test_required_notebooks_exist_and_import_package_code() -> None:
    for name in NOTEBOOKS:
        notebook = load_notebook(name)
        assert notebook["nbformat"] == 4
        source = "\n".join(code_cells(notebook))
        for pattern in PUBLIC_API_PATTERNS:
            assert pattern.search(source), f"{name} does not demonstrate required public API pattern {pattern.pattern!r}"
        assert "FUNGMOD_NOTEBOOK_OUTPUT_ROOT" in source


def test_foundation_notebooks_are_labelled_software_test_only() -> None:
    for name in NOTEBOOKS:
        markdown = "\n".join(markdown_cells(load_notebook(name))).lower()

        assert "software-test fixture only" in markdown
        assert "not a researcher-facing scientific example" in markdown


def test_notebooks_do_not_define_core_classes_or_rate_laws() -> None:
    for name in [*NOTEBOOKS, *PRODUCT_NOTEBOOKS]:
        source = "\n".join(code_cells(load_notebook(name)))
        for label, pattern in HIDDEN_IMPLEMENTATION_PATTERNS.items():
            assert not pattern.search(source), f"{name} contains hidden implementation pattern {label!r}"


def test_product_tour_notebook_is_researcher_facing_but_unvalidated() -> None:
    notebook = load_notebook("10_virtual_experiment_product_tour.ipynb")
    markdown = "\n".join(markdown_cells(notebook)).lower()
    source = "\n".join(code_cells(notebook))

    assert "researcher-facing exploratory tour" in markdown
    assert "not an empirical validation" in markdown
    assert "virtual_experiment(" in source
    assert "mechanism_summary()" in source
    assert "FUNGMOD_NOTEBOOK_OUTPUT_ROOT" in source


def test_quickstart_notebook_executes_smoke_path_with_temp_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "notebook_outputs"
    monkeypatch.setenv("FUNGMOD_NOTEBOOK_OUTPUT_ROOT", str(output_root))
    _execute_notebook("00_quickstart.ipynb")

    output = output_root / "00_quickstart"
    assert (output / "record.json").exists()
    assert (output / "figures" / "state_trajectories.png").exists()
    assert (output / "output_manifest.json").exists()


def test_foundation_notebooks_execute_smoke_paths_with_temp_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "notebook_outputs"
    monkeypatch.setenv("FUNGMOD_NOTEBOOK_OUTPUT_ROOT", str(output_root))

    for name in NOTEBOOKS:
        _execute_notebook(name)

    output = output_root / "00_quickstart"
    assert (output / "record.json").exists()
    assert (output / "figures" / "state_trajectories.png").exists()
    assert (output / "output_manifest.json").exists()

    failure_output = output_root / "02_failure_report"
    assert (failure_output / "failure_report.json").exists()

    inspection_output = output_root / "03_configured_outputs"
    assert (inspection_output / "configured_metadata.json").exists()


def test_product_tour_notebook_executes_smoke_path_with_temp_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "notebook_outputs"
    monkeypatch.setenv("FUNGMOD_NOTEBOOK_OUTPUT_ROOT", str(output_root))
    _execute_notebook("10_virtual_experiment_product_tour.ipynb")

    output = output_root / "10_virtual_experiment_product_tour"
    assert (output / "mechanism_summary.csv").exists()
    assert (output / "assumption_summary.csv").exists()
    assert (output / "limitations_table.csv").exists()
    assert (output / "output_manifest.json").exists()


def _execute_notebook(name: str) -> None:
    namespace: dict[str, object] = {"__name__": "__notebook_smoke__"}
    for source in code_cells(load_notebook(name)):
        exec(compile(source, f"notebooks/{name}", "exec"), namespace)
