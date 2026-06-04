from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_PATH = ROOT / "notebooks" / "06_sabiork_reaction_618_beta_glucosidase.ipynb"

HIDDEN_IMPLEMENTATION_PATTERNS = {
    "process class": re.compile(r"(^|\n)\s*class\s+\w*Process\b"),
    "process factory class": re.compile(r"(^|\n)\s*class\s+\w*Factory\b"),
    "rate-law function": re.compile(r"(^|\n)\s*def\s+\w*rate\w*\s*\("),
    "low-level solver import": re.compile(r"(^|\n)\s*(from\s+fungal_model\.solvers|from\s+scipy\.integrate)"),
    "process internals import": re.compile(r"(^|\n)\s*from\s+fungal_model\.processes\b"),
    "direct scipy solver call": re.compile(r"\bsolve_ivp\s*\("),
}


def test_sabiork_reaction_618_notebook_exists_and_imports_package_code() -> None:
    notebook = _load_notebook()
    source = "\n".join(_code_cells(notebook))

    assert notebook["nbformat"] == 4
    assert "SABIO-RK Reaction 618 beta-glucosidase pilot" in _markdown_source(notebook)
    assert "from fungal_model.registry import load_registry" in source
    assert "from fungal_model.data import load_kinetic_record" in source
    assert "from fungal_model.screening import assess_modelability" in source
    assert "simulate_screen" in source
    assert "build_model_config_from_registry_case" not in source
    assert "run_configured_model" not in source


def test_sabiork_reaction_618_notebook_uses_local_fixtures_only() -> None:
    source = "\n".join(_code_cells(_load_notebook()))

    assert "fetch_sabiork" not in source
    assert "requests" not in source
    assert "kinlaw-entry/json" not in source
    assert "shutil" not in source
    assert "copytree" not in source
    assert "manual_homogeneous" not in source
    assert "\"data\"" in source
    assert "\"kinetic_records\"" in source
    assert "\"sabiork\"" in source
    assert "case_001_reaction_618_beta_glucosidase" in source
    assert "data_registry" in source


def test_sabiork_reaction_618_notebook_does_not_define_core_classes_or_rate_laws() -> None:
    source = "\n".join(_code_cells(_load_notebook()))

    for label, pattern in HIDDEN_IMPLEMENTATION_PATTERNS.items():
        assert not pattern.search(source), f"Notebook contains hidden implementation pattern {label!r}"


def test_sabiork_reaction_618_notebook_executes_native_exploratory_screen(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FUNGMOD_NOTEBOOK_OUTPUT_ROOT", str(tmp_path / "outputs"))
    namespace: dict[str, object] = {"__name__": "__sabiork_notebook_smoke__"}
    for source in _code_cells(_load_notebook()):
        exec(compile(source, str(NOTEBOOK_PATH), "exec"), namespace)

    report = namespace["report"]
    record = namespace["record"]
    screen = namespace["screen"]
    screen_output_dir = Path(namespace["screen_output_dir"])  # type: ignore[arg-type]

    assert report.status == "underparameterized"
    assert record.source_database == "SABIO-RK"
    assert record.source_reaction_id == "618"
    assert record.source_kinetic_law_id == "35622"
    assert screen.case_results[0].modelability_report.status == "exploratory"
    assert len(screen.case_results[0].samples) == 32
    assert (screen_output_dir / "sampled_parameters.csv").exists()
    assert (screen_output_dir / "final_states.csv").exists()


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
