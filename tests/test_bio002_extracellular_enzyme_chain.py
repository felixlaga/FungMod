from __future__ import annotations

import csv
import shutil
from pathlib import Path

import numpy as np
import pytest
import yaml

from fungal_model.registry import load_registry
from fungal_model.screening import (
    BIO002_ENZYME_CHAIN_TEMPLATE_ID,
    EnzymeChainAssemblyError,
    EXTRACELLULAR_ENZYME_CHAIN_PROCESS_TYPE,
    build_extracellular_enzyme_chain_config,
    run_extracellular_enzyme_chain_demo,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"


def test_bio002_registry_template_defines_reusable_chain_without_organism_process_code() -> None:
    registry = load_registry(REGISTRY_INDEX)

    template = registry.get_case_template(BIO002_ENZYME_CHAIN_TEMPLATE_ID)

    assert template.validate().passed
    assert template.process_type == EXTRACELLULAR_ENZYME_CHAIN_PROCESS_TYPE
    assert template.state_roles == {
        "substrate": "solid_cellulose_equivalent_concentration",
        "intermediate": "cellobiose_concentration",
        "product": "beta_D_glucose_concentration",
        "surface_catalyst": "cellulase_concentration",
        "homogeneous_catalyst": "beta_glucosidase_concentration",
    }
    assert template.product_map["product_map_type"] == "stoichiometric"
    assert template.stoichiometric_yields["intermediate"] == pytest.approx(1.0)
    assert template.stoichiometric_yields["product"] == pytest.approx(2.0)
    assert "whole-fungus growth" in " ".join(template.limitations)
    assert "organism-specific" in " ".join(template.limitations)
    assert "PET" in " ".join(template.limitations)


def test_bio002_chain_config_assembles_two_generic_processes_from_template() -> None:
    registry = load_registry(REGISTRY_INDEX)

    config = build_extracellular_enzyme_chain_config(registry=registry)

    assert config.validate().passed
    assert config.mode == "exploratory"
    assert [process.process_type for process in config.processes] == [
        "surface_catalysis",
        "homogeneous_michaelis_menten",
    ]
    assert [process.id for process in config.processes] == [
        "bio002_surface_cellulose_to_cellobiose",
        "bio002_cellobiose_to_glucose_mm",
    ]
    assert config.to_dict()["case_template"]["chain_topology"] == {
        "topology_type": "linear",
        "process_ids": [
            "bio002_surface_cellulose_to_cellobiose",
            "bio002_cellobiose_to_glucose_mm",
        ],
        "product_map_ids": [
            "bio002_cellulose_to_cellobiose_map",
            "bio002_cellobiose_to_glucose_map",
        ],
        "state_roles": ["substrate", "intermediate", "product"],
        "state_names": [
            "solid_cellulose_equivalent_concentration",
            "cellobiose_concentration",
            "beta_D_glucose_concentration",
        ],
        "edges": [
            {
                "process_id": "bio002_surface_cellulose_to_cellobiose",
                "product_map_id": "bio002_cellulose_to_cellobiose_map",
                "reactant_role": "substrate",
                "product_role": "intermediate",
            },
            {
                "process_id": "bio002_cellobiose_to_glucose_mm",
                "product_map_id": "bio002_cellobiose_to_glucose_map",
                "reactant_role": "intermediate",
                "product_role": "product",
            },
        ],
        "entry_state_roles": ["substrate"],
        "terminal_state_roles": ["product"],
        "branching_supported": False,
        "cycles_supported": False,
    }
    assert {reference.id for reference in config.entities.product_maps} == {
        "bio002_cellulose_to_cellobiose_map",
        "bio002_cellobiose_to_glucose_map",
    }
    product_maps = {reference.id: reference.data for reference in config.entities.product_maps}
    assert product_maps["bio002_cellulose_to_cellobiose_map"]["products"] == {
        "cellobiose_concentration": 1.0
    }
    assert product_maps["bio002_cellobiose_to_glucose_map"]["products"] == {
        "beta_D_glucose_concentration": 2.0
    }
    forbidden = {"fungal_biomass", "biomass", "uptake", "secretion", "pet", "lignin"}
    model_surface = " ".join(
        [
            *config.initial_state.states,
            *(process.id for process in config.processes),
            *(process.process_type for process in config.processes),
        ]
    ).casefold()
    assert not any(token in model_surface for token in forbidden)


def test_direct_chain_resolver_rejects_storage_only_parameter(tmp_path: Path) -> None:
    registry_root = tmp_path / "data_registry"
    shutil.copytree(ROOT / "data_registry", registry_root)
    parameters_path = registry_root / "parameters" / "parameter_records.yml"
    payload = yaml.safe_load(parameters_path.read_text(encoding="utf-8"))
    target = next(
        item
        for item in payload["records"]
        if item["record_id"] == "bio002_cellulose_to_cellobiose_surface_rate"
    )
    target["allowed_use"] = "registry_storage_only_no_simulation_authorization"
    parameters_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    registry = load_registry(registry_root / "registry_index.yml")

    with pytest.raises(EnzymeChainAssemblyError, match="storage-only"):
        build_extracellular_enzyme_chain_config(registry=registry)


def test_bio002_demo_runs_with_stoichiometric_chain_dynamics_and_standard_tables(tmp_path: Path) -> None:
    registry = load_registry(REGISTRY_INDEX)
    output_dir = tmp_path / "bio002_chain"

    run = run_extracellular_enzyme_chain_demo(registry=registry, output_dir=output_dir)

    result = run.result
    substrate = result.state("solid_cellulose_equivalent_concentration").to("mM").magnitude
    cellobiose = result.state("cellobiose_concentration").to("mM").magnitude
    glucose = result.state("beta_D_glucose_concentration").to("mM").magnitude
    conserved = substrate + cellobiose + 0.5 * glucose

    assert result.solver_metadata["success"] is True
    assert substrate[-1] < substrate[0]
    assert cellobiose[-1] > 0.0
    assert glucose[-1] > 0.0
    assert np.max(cellobiose) > cellobiose[0]
    assert conserved[-1] == pytest.approx(conserved[0], rel=1e-6, abs=1e-6)
    assert set(result.process_rates) == {
        "bio002_surface_cellulose_to_cellobiose",
        "bio002_cellobiose_to_glucose_mm",
    }
    assert (output_dir / "bundle" / "state_trajectories.csv").exists()
    for table_name in (
        "time_series_long.csv",
        "final_metrics.csv",
        "threshold_times.csv",
        "summary_metrics.csv",
        "limitations_table.csv",
        "suggested_experiments.csv",
    ):
        assert (output_dir / table_name).exists(), table_name

    final_metrics = _csv_rows(output_dir / "final_metrics.csv")
    thresholds = _csv_rows(output_dir / "threshold_times.csv")
    time_series = _csv_rows(output_dir / "time_series_long.csv")
    limitations = _csv_rows(output_dir / "limitations_table.csv")
    suggestions = _csv_rows(output_dir / "suggested_experiments.csv")

    metrics = {row["metric"]: row for row in final_metrics}
    assert float(metrics["solid_substrate_degraded_fraction"]["value"]) > 0.9
    assert float(metrics["final_glucose_yield"]["value"]) > 0.0
    assert metrics["final_glucose_yield"]["status"] == "derived_from_chain_stoichiometry"
    assert {row["threshold_fraction"] for row in thresholds} == {"0.1", "0.5", "0.9"}
    assert all(row["status"] == "computed" for row in thresholds)
    assert {
        "solid_substrate_degraded_fraction",
        "glucose_yield",
        "bio002_surface_cellulose_to_cellobiose",
        "bio002_cellobiose_to_glucose_mm",
    }.issubset({row["state"] for row in time_series})
    assert any("not whole-fungus growth" in row["limitation"] for row in limitations)
    assert any("No PET, lignin" in row["limitation"] for row in limitations)
    assert {row["experiment_id"] for row in suggestions} == {
        "bio002_timecourse_cellobiose_glucose",
        "bio002_accessible_surface_area",
    }


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
