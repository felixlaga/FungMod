from __future__ import annotations

import json
from pathlib import Path

from fungal_model import run_configured_model


ROOT = Path(__file__).resolve().parents[1]
MODEL_CONFIGS = ROOT / "data" / "model_configs"


def test_configured_output_manifest_lists_existing_reproducibility_files(tmp_path: Path) -> None:
    output_dir = tmp_path / "dummy_surface"

    result = run_configured_model(
        MODEL_CONFIGS / "toy_surface_dummy_non_pet.yml",
        output_dir=output_dir,
    )

    manifest = _json(output_dir / "output_manifest.json")
    assert manifest["mode"] == "toy"
    assert manifest["maturity"] == "framework_benchmark"
    assert "output_manifest.json" in manifest["files"]
    for relative_path in manifest["files"]:
        assert (output_dir / relative_path).is_file(), relative_path

    for required_file in (
        "run_environment.json",
        "package_versions.json",
        "source_revision.json",
        "solver_settings.json",
        "process_build_decisions.json",
    ):
        assert required_file in manifest["files"]

    configured_run = _json(output_dir / "configured_model_run.json")
    assert configured_run["solver_metadata"]["backend"] == "scipy.solve_ivp"

    solver = _json(output_dir / "solver_settings.json")
    assert solver["solver_settings"]["method"] == result.solver_settings.method
    assert solver["solver_metadata"]["backend"] == "scipy.solve_ivp"

    packages = _json(output_dir / "package_versions.json")
    assert packages["fungal_model"]["version"] == result.model_version
    assert packages["distributions"]["fungal-model"] is not None
    assert "numpy" in packages["distributions"]

    revision = _json(output_dir / "source_revision.json")
    assert set(revision) == {"available", "root", "commit", "branch", "dirty", "error"}
    if revision["available"]:
        assert revision["commit"]
        assert revision["root"]
        assert isinstance(revision["dirty"], bool)
    else:
        assert revision["commit"] is None

    decisions = _json(output_dir / "process_build_decisions.json")
    assert decisions["decisions"][0]["can_build"] is True


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
