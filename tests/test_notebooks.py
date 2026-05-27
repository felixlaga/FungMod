from __future__ import annotations

import json
from pathlib import Path


NOTEBOOKS = [
    "00_quickstart.ipynb",
    "01_process_library_demo.ipynb",
    "02_surface_hydrolysis_demo.ipynb",
    "03_fungus_on_pet_demo.ipynb",
    "04_reaction_diffusion_demo.ipynb",
    "05_calibration_and_uncertainty_demo.ipynb",
]


NOTEBOOK_DIR = Path(__file__).resolve().parents[1] / "notebooks" / "examples"


def load_notebook(name: str) -> dict:
    path = NOTEBOOK_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


def code_cells(notebook: dict) -> list[str]:
    return [
        "".join(cell.get("source", []))
        for cell in notebook["cells"]
        if cell.get("cell_type") == "code"
    ]


def test_required_notebooks_exist_and_import_package_code() -> None:
    for name in NOTEBOOKS:
        notebook = load_notebook(name)
        assert notebook["nbformat"] == 4
        source = "\n".join(code_cells(notebook))
        assert "fungal_model" in source


def test_notebooks_do_not_define_core_classes_or_rate_laws() -> None:
    forbidden = (
        "\nclass ",
        "RateLaw =",
        "def surface_catalysis_rate",
        "def michaelis_menten_rate",
        "def arrhenius_rate_constant",
    )
    for name in NOTEBOOKS:
        source = "\n".join(code_cells(load_notebook(name)))
        for pattern in forbidden:
            assert pattern not in source, f"{name} contains implementation pattern {pattern!r}"


def test_quickstart_notebook_executes_smoke_path() -> None:
    namespace: dict[str, object] = {"__name__": "__notebook_smoke__"}
    for source in code_cells(load_notebook("00_quickstart.ipynb")):
        exec(compile(source, "notebooks/00_quickstart.ipynb", "exec"), namespace)

    output = Path(__file__).resolve().parents[1] / "outputs" / "notebook_00_quickstart"
    assert (output / "record.json").exists()
    assert (output / "figures" / "state_trajectories.png").exists()
