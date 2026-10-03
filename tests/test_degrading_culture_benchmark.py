"""Exercise the complete offline experiment and retained evidence contract."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("degrading_runner", ROOT / "scripts/run_degrading_culture_benchmark.py")
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def test_offline_full_sweep_closes_balances_and_preserves_existing_results(tmp_path):
    destination = tmp_path / "new"
    runner.run(destination)
    summary = json.loads((destination / "summary.json").read_text())
    assert summary["dynamic_balance_max_mol_L"] < 1e-10
    assert summary["dynamic_BDF_Radau_difference_max_mol_L"] < 1e-8
    assert summary["dynamic_scenarios"]["No secretion"]["final_fraction_removed"] == 0
    assert summary["dynamic_scenarios"]["Coupled, aerated"]["threshold_times_hour"]["0.9"] < 120
    sweep = json.loads((destination / "allocation_tradeoff.json").read_text())
    assert len(sweep["points"]) == 33
    for row in sweep["points"]:
        assert max(row["diagnostics"]["maximum_absolute_balance_residual_mol_L"].values()) < 1e-10
        assert row["diagnostics"]["minimum_pool_mol_L"] >= -1e-12
    sensitivity = json.loads((destination / "kinetic_uncertainty.json").read_text())
    assert len(sensitivity["results"]) == 9
    for row in sensitivity["results"]:
        assert max(row["diagnostics"]["maximum_absolute_balance_residual_mol_L"].values()) < 1e-10
    artifacts = json.loads((destination / "artifact_manifest.json").read_text())
    for name, digest in artifacts.items():
        assert hashlib.sha256((destination / name).read_bytes()).hexdigest() == digest
    assert len(list(destination.glob("*.png"))) == 4
    with pytest.raises(FileExistsError):
        runner.run(destination)
    assert json.loads((destination / "artifact_manifest.json").read_text()) == artifacts
