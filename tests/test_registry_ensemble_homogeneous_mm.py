from __future__ import annotations

import csv
import shutil
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from fungal_model.registry import load_registry
from fungal_model.screening import EnsembleSample, RegistryScreenSimulationError, simulate_screen


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"

FUNGUS_ID = "sabiork_beta_glucosidase_source"
SUBSTRATE_ID = "cellobiose"
ENVIRONMENT_ID = "sabiork_reaction_618_selected_conditions"
PROCESS_TYPE = "homogeneous_michaelis_menten"
ENZYME_SYMBOL = "enzyme_concentration_beta_glucosidase"
ENZYME_LOWER = 1.0e-6
ENZYME_UPPER = 1.0e-3


def test_simulate_screen_runs_reaction_618_homogeneous_mm_exploratory_ensemble(
    tmp_path: Path,
) -> None:
    result = simulate_screen(
        fungus_ids=[FUNGUS_ID],
        substrate_ids=[SUBSTRATE_ID],
        environment_ids=[ENVIRONMENT_ID],
        registry=load_registry(REGISTRY_INDEX),
        n_samples=32,
        seed=1,
        output_dir=tmp_path / "screen",
    )

    case = result.case_results[0]
    enzyme_values = _enzyme_values(case.samples)
    final_rows = _csv_rows(tmp_path / "screen" / "final_states.csv")
    sampled_rows = _csv_rows(tmp_path / "screen" / "sampled_parameters.csv")

    assert case.process_type == PROCESS_TYPE
    assert case.modelability_report.status == "exploratory"
    assert len(case.samples) == 32
    assert not case.sample_failures
    assert all(ENZYME_LOWER <= value <= ENZYME_UPPER for value in enzyme_values)
    assert len(final_rows) == 32
    assert len(sampled_rows) == 32
    assert _csv_rows(tmp_path / "screen" / "sample_failures.csv") == []
    assert (tmp_path / "screen" / "screen_summary.json").exists()
    assert (tmp_path / "screen" / "sampled_parameter_summary.csv").exists()
    assert (tmp_path / "screen" / "final_state_summary.csv").exists()
    assert all(Path(sample.trajectory_path or "").exists() for sample in case.samples)
    _assert_final_state_rows_are_scalar(final_rows)


def test_simulate_screen_homogeneous_mm_fixed_seed_is_reproducible(tmp_path: Path) -> None:
    first = simulate_screen(
        fungus_ids=[FUNGUS_ID],
        substrate_ids=[SUBSTRATE_ID],
        environment_ids=[ENVIRONMENT_ID],
        registry=load_registry(REGISTRY_INDEX),
        n_samples=5,
        seed=17,
        output_dir=tmp_path / "first",
    )
    second = simulate_screen(
        fungus_ids=[FUNGUS_ID],
        substrate_ids=[SUBSTRATE_ID],
        environment_ids=[ENVIRONMENT_ID],
        registry=load_registry(REGISTRY_INDEX),
        n_samples=5,
        seed=17,
        output_dir=tmp_path / "second",
    )

    assert _enzyme_values(first.case_results[0].samples) == _enzyme_values(
        second.case_results[0].samples
    )


def test_simulate_screen_homogeneous_mm_requires_exploratory_enzyme_prior(
    tmp_path: Path,
) -> None:
    registry = _registry_without_exploratory_prior(tmp_path)

    with pytest.raises(RegistryScreenSimulationError, match="modelability status"):
        simulate_screen(
            fungus_ids=[FUNGUS_ID],
            substrate_ids=[SUBSTRATE_ID],
            environment_ids=[ENVIRONMENT_ID],
            registry=registry,
            n_samples=2,
            seed=1,
            output_dir=tmp_path / "screen",
        )


def _enzyme_values(samples: tuple[EnsembleSample, ...]) -> list[float]:
    return [
        float(sample.parameters["enzyme_initial_concentration"]["value"])
        for sample in samples
    ]


def _assert_final_state_rows_are_scalar(rows: list[dict[str, str]]) -> None:
    expected_columns = (
        "final_cellobiose_concentration",
        "final_beta_glucosidase_concentration",
        "final_beta_D_glucose_concentration",
    )
    for row in rows:
        for column in expected_columns:
            value = row[column]
            assert not value.startswith("[")
            assert not value.endswith("]")
            float(value)


def _registry_without_exploratory_prior(tmp_path: Path):
    registry_dir = _copy_registry(tmp_path)
    parameters_path = registry_dir / "parameters" / "parameter_records.yml"
    data = _yaml_mapping(parameters_path)
    records = cast(list[dict[str, Any]], data["records"])
    data["records"] = [
        record
        for record in records
        if not (
            record.get("maturity") == "exploratory_prior"
            or cast(dict[str, Any], record.get("provenance", {})).get("exploratory_prior")
        )
    ]
    parameters_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return load_registry(registry_dir / "registry_index.yml")


def _copy_registry(tmp_path: Path) -> Path:
    destination = tmp_path / "data_registry"
    shutil.copytree(ROOT / "data_registry", destination)
    return destination


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _yaml_mapping(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return cast(dict[str, Any], data)
