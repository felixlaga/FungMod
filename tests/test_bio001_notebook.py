from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_PATH = ROOT / "notebooks" / "07_bio001_cellulose_surface_virtual_experiment.ipynb"

WARNING_TEXT = (
    "This is an enzyme-mediated insoluble cellulose surface-degradation pilot. "
    "It is not a whole-fungus growth model. It does not include fungal secretion, "
    "uptake, biomass growth, oxygen limitation, or full lignocellulose structure. "
    "Any exploratory parameter ranges are user-supplied unless explicitly sourced."
)

HIDDEN_IMPLEMENTATION_PATTERNS = {
    "process class": re.compile(r"(^|\n)\s*class\s+\w*Process\b"),
    "process factory class": re.compile(r"(^|\n)\s*class\s+\w*Factory\b"),
    "rate-law function": re.compile(r"(^|\n)\s*def\s+\w*rate\w*\s*\("),
    "low-level solver import": re.compile(r"(^|\n)\s*(from\s+fungal_model\.solvers|from\s+scipy\.integrate)"),
    "process internals import": re.compile(r"(^|\n)\s*from\s+fungal_model\.processes\b"),
    "direct scipy solver call": re.compile(r"\bsolve_ivp\s*\("),
}


def test_bio001_notebook_exists_and_uses_public_virtual_experiment_api() -> None:
    notebook = _load_notebook()
    source = "\n".join(_code_cells(notebook))
    markdown = _markdown_source(notebook)

    assert notebook["nbformat"] == 4
    assert "BIO-001 cellulose surface virtual experiment" in markdown
    assert WARNING_TEXT in markdown
    assert "from fungal_model.api import VirtualExperiment" in source
    assert "from fungal_model.registry import load_registry" in source
    assert "simulate_screen" not in source
    assert "build_model_config_from_registry_case" not in source
    assert "run_configured_model" not in source


def test_bio001_notebook_does_not_define_core_model_logic() -> None:
    source = "\n".join(_code_cells(_load_notebook()))

    for label, pattern in HIDDEN_IMPLEMENTATION_PATTERNS.items():
        assert not pattern.search(source), f"Notebook contains hidden implementation pattern {label!r}"


def test_bio001_notebook_executes_surface_virtual_experiment(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("FUNGMOD_NOTEBOOK_OUTPUT_ROOT", str(tmp_path / "outputs"))
    namespace: dict[str, object] = {"__name__": "__bio001_notebook_smoke__"}
    for source in _code_cells(_load_notebook()):
        exec(compile(source, str(NOTEBOOK_PATH), "exec"), namespace)

    scientific_preflight = namespace["scientific_preflight"]
    exploratory_preflight = namespace["exploratory_preflight"]
    screen = namespace["screen"]
    screen_output_dir = Path(namespace["screen_output_dir"])  # type: ignore[arg-type]

    assert scientific_preflight.status == "underparameterized"
    assert exploratory_preflight.status == "exploratory"
    assert screen.case_results[0].modelability_report.status == "exploratory"
    assert len(screen.case_results[0].samples) == 8
    assert (screen_output_dir / "time_series_long.csv").exists()
    assert (screen_output_dir / "final_metrics.csv").exists()
    assert (screen_output_dir / "threshold_times.csv").exists()
    assert (screen_output_dir / "sampled_parameters.csv").exists()
    assert (screen_output_dir / "summary_metrics.csv").exists()
    assert (screen_output_dir / "provenance_table.csv").exists()
    assert (screen_output_dir / "limitations_table.csv").exists()
    assert Path(namespace["uncertainty_plot_path"]).exists()  # type: ignore[arg-type]


def _load_notebook() -> dict:
    return json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))


def _code_cells(notebook: dict) -> list[str]:
    return [
        "".join(cell.get("source", []))
        for cell in notebook["cells"]
        if cell.get("cell_type") == "code"
    ]


def _markdown_source(notebook: dict) -> str:
    return "\n".join(
        "".join(cell.get("source", []))
        for cell in notebook["cells"]
        if cell.get("cell_type") == "markdown"
    )
