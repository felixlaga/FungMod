from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from fungal_model.core.errors import InvalidMechanismError, MissingParameterError
from fungal_model.plugins.pet import PETSurfaceWorkflowConfig, run_pet_surface_integration


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def test_pet_surface_integration_workflow_saves_full_output_folder(tmp_path) -> None:
    with pytest.warns(DeprecationWarning):
        result = run_pet_surface_integration(tmp_path / "run")

    assert result.assembly_report is not None
    assert result.assembly_report.success
    assert result.state("solid_polymer_amount").magnitude[-1] < result.state("solid_polymer_amount").magnitude[0]
    assert result.rate("plugin_surface_catalysis").magnitude[0] > 0.0

    expected = [
        "record.json",
        "model_assembly_report.json",
        "assumptions.json",
        "parameters.csv",
        "validation_report.json",
        "solver_report.json",
        "state_trajectories.csv",
        "process_rates.csv",
        "figures/state_trajectories.png",
        "figures/process_rates.png",
        "figures/mass_balance.png",
        "logs/provenance_report.md",
        "input_model_config.json",
        "configured_model_run.json",
        "resolved_model_config.yml",
    ]
    for relative_path in expected:
        assert (tmp_path / "run" / relative_path).exists(), relative_path

    report = json.loads((tmp_path / "run" / "model_assembly_report.json").read_text(encoding="utf-8"))
    assert report["success"] is True
    assert report["matched_processes"][0]["process_type"] == "surface_catalysis"


def test_missing_pet_accessible_surface_fails_honestly(tmp_path) -> None:
    data = yaml.safe_load((DATA / "substrates" / "pet_film.yml").read_text(encoding="utf-8"))
    for parameter in data["parameters"]:
        if parameter["symbol"] == "A_accessible":
            parameter["value"] = None
            parameter["uncertainty"] = None
    bad_path = tmp_path / "pet_missing_area.yml"
    bad_path.write_text(yaml.safe_dump(data), encoding="utf-8")

    config = PETSurfaceWorkflowConfig.default()
    config = PETSurfaceWorkflowConfig(
        substrate_path=bad_path,
        enzyme_path=config.enzyme_path,
        fungus_path=config.fungus_path,
        environment_path=config.environment_path,
        geometry_path=config.geometry_path,
        parameters_path=config.parameters_path,
    )

    with pytest.warns(DeprecationWarning), pytest.raises(MissingParameterError) as exc_info:
        run_pet_surface_integration(tmp_path / "bad_run", config=config)

    issue = exc_info.value.report.missing_parameters[0]
    assert issue.symbol == "A_accessible"
    assert issue.reason == "unknown_value"


def test_changing_enzyme_config_changes_model_assembly(tmp_path) -> None:
    data = yaml.safe_load((DATA / "enzymes" / "petase_like.yml").read_text(encoding="utf-8"))
    data["name"] = "toy incompatible cellulase"
    data["enzyme_class"] = "cellulase"
    data["target_bond_types"] = ["beta-1,4-glycosidic"]
    data["target_substrate_names"] = ["cellulose"]
    bad_enzyme = tmp_path / "bad_enzyme.yml"
    bad_enzyme.write_text(yaml.safe_dump(data), encoding="utf-8")

    default = PETSurfaceWorkflowConfig.default()
    config = PETSurfaceWorkflowConfig(
        substrate_path=default.substrate_path,
        enzyme_path=bad_enzyme,
        fungus_path=default.fungus_path,
        environment_path=default.environment_path,
        geometry_path=default.geometry_path,
        parameters_path=default.parameters_path,
    )

    with pytest.warns(DeprecationWarning), pytest.raises(InvalidMechanismError) as exc_info:
        run_pet_surface_integration(tmp_path / "bad_enzyme_run", config=config)

    reasons = {issue.reason for issue in exc_info.value.report.incompatible_mechanisms}
    assert "enzyme_substrate_mismatch" in reasons
