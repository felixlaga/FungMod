from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import fungmod
import fungal_model

from fungal_model import (
    default_registry_path,
    example_data_path,
    package_data_path,
    run_configured_model,
    source_proposal,
    virtual_experiment,
)
from fungal_model.registry import load_registry


ROOT = Path(__file__).resolve().parents[1]


def test_distribution_alias_and_version_are_public() -> None:
    assert fungmod.__version__ == fungal_model.__version__ == "0.1.0"
    assert fungmod.virtual_experiment is fungal_model.virtual_experiment
    assert fungmod.default_registry_path is fungal_model.default_registry_path


def test_packaged_resources_match_repository_sources() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/check_packaged_resources.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_packaged_resource_paths_are_bounded() -> None:
    assert default_registry_path().is_file()
    assert example_data_path("model_configs/toy_homogeneous_ab.yml").is_file()
    assert package_data_path("data_registry").is_dir()

    for invalid in ("/tmp/outside", "../data_registry"):
        try:
            package_data_path(invalid)
        except ValueError:
            pass
        else:  # pragma: no cover - failure branch
            raise AssertionError(f"Expected packaged path {invalid!r} to be rejected.")


def test_default_virtual_experiment_runs_outside_checkout(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    registry = load_registry(default_registry_path())
    assert registry.registry_id == "toy_registry"

    study = virtual_experiment(
        fungi="beta-glucosidase source",
        substrates="cellobiose",
        environments="SABIO-RK Reaction 618 selected assay conditions",
    )
    result = study.simulate(
        mode="exploratory",
        n_samples=2,
        seed=7,
        output_dir=tmp_path / "virtual_experiment",
        quicklook=False,
    )

    assert result.experiment.registry_source == str(default_registry_path())
    assert result.final_metrics()
    assert result.provenance()


def test_packaged_configured_model_runs_outside_checkout(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    output_dir = tmp_path / "configured"
    result = run_configured_model(
        example_data_path("model_configs/showcase_dynamic_thermodynamics.yml"),
        output_dir=output_dir,
    )

    assert result.solver_metadata["success"] is True
    assert (output_dir / "thermodynamic_summary.json").is_file()
    assert (output_dir / "entropy_production_rate_timeseries.csv").is_file()
    summary = json.loads((output_dir / "thermodynamic_summary.json").read_text(encoding="utf-8"))
    assert summary["has_dynamic_reaction_quotient"] is True
    assert summary["has_solver_time_enforcement"] is True


def test_frozen_source_proposal_uses_packaged_snapshot_outside_checkout(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    proposal = source_proposal(provider="sabiork", reaction_id="618")

    assert proposal.source_query == "SabioReactionID:618"
    assert proposal.reaction_records
    allowed_snapshot_roots = {
        ROOT / "data" / "kinetic_records" / "sabiork",
        example_data_path("kinetic_records/sabiork"),
    }
    snapshot_path = Path(proposal.source_snapshot_path)
    assert any(root in snapshot_path.parents for root in allowed_snapshot_roots)
