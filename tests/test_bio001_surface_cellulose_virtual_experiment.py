from __future__ import annotations

import csv
from pathlib import Path

import pytest

from fungal_model.api import VirtualExperiment
from fungal_model.api.metrics import threshold_crossing_time
from fungal_model.registry import load_registry
from fungal_model.screening import assess_modelability
from fungal_model.screening.case_builder import select_registry_case_compatibility


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"

FUNGUS_ID = "generic_cellulase_source"
SUBSTRATE_ID = "cellulose_film_generic"
ENVIRONMENT_ID = "bio001_cellulose_surface_pilot_environment"
PROCESS_TYPE = "surface_catalysis"


def test_bio001_registry_records_load_with_surface_metadata() -> None:
    registry = load_registry(REGISTRY_INDEX)

    fungus = registry.get_fungus(FUNGUS_ID)
    substrate = registry.get_substrate(SUBSTRATE_ID)
    enzyme = registry.get_enzyme_class("cellulase_generic")
    compatibility = registry.get_process_compatibility(
        enzyme_class="cellulase_generic",
        substrate_class="cellulose_film_generic",
        process_type=PROCESS_TYPE,
    )[0]

    assert fungus.enzyme_classes == ("cellulase_generic",)
    assert substrate.substrate_class == "cellulose_film_generic"
    assert substrate.physical_state == "solid_polymer"
    assert substrate.bond_classes == ("beta_1_4_glycosidic",)
    assert "accessible_surface_area" in substrate.properties
    assert "accessible_site_fraction" in substrate.properties
    assert enzyme.compatible_processes == (PROCESS_TYPE,)
    assert enzyme.target_bond_classes == ("beta_1_4_glycosidic",)
    assert compatibility.process_type == PROCESS_TYPE
    assert compatibility.parameter_roles["surface_rate_constant"] == "cellulose_surface_rate_constant"
    assert compatibility.parameter_roles["substrate_initial_amount"] == "initial_cellulose_film_mass"


def test_bio001_modelability_scientific_vs_exploratory_modes() -> None:
    registry = load_registry(REGISTRY_INDEX)

    scientific = assess_modelability(
        fungus_id=FUNGUS_ID,
        substrate_id=SUBSTRATE_ID,
        environment_id=ENVIRONMENT_ID,
        registry=registry,
        mode="scientific",
    )
    exploratory = assess_modelability(
        fungus_id=FUNGUS_ID,
        substrate_id=SUBSTRATE_ID,
        environment_id=ENVIRONMENT_ID,
        registry=registry,
        mode="exploratory",
    )

    assert scientific.status == "underparameterized"
    assert {item.item_id for item in scientific.missing} >= set(exploratory.required_parameters)
    assert exploratory.status == "exploratory"
    assert exploratory.required_processes == (PROCESS_TYPE,)
    assert {item.item_id for item in exploratory.uncertain} == set(exploratory.required_parameters)
    selected = select_registry_case_compatibility(
        registry=registry,
        fungus_id=FUNGUS_ID,
        substrate_id=SUBSTRATE_ID,
        report=exploratory,
    )
    assert selected.record_id == "bio001_cellulase_cellulose_film_surface_catalysis"


def test_bio001_virtual_experiment_writes_surface_degradation_tables(tmp_path: Path) -> None:
    output_dir = tmp_path / "bio001_cellulose_surface"
    study = VirtualExperiment.from_registry(
        fungi=FUNGUS_ID,
        substrates=SUBSTRATE_ID,
        environments=ENVIRONMENT_ID,
        registry=REGISTRY_INDEX,
    )

    result = study.simulate(
        mode="exploratory",
        n_samples=3,
        seed=21,
        output_dir=output_dir,
        quicklook=False,
    )

    assert result.screen_result.case_results[0].process_type == PROCESS_TYPE
    assert len(result.screen_result.case_results[0].samples) == 3
    for filename in (
        "time_series_long.csv",
        "final_metrics.csv",
        "threshold_times.csv",
        "summary_metrics.csv",
        "sampled_parameters.csv",
        "provenance_table.csv",
        "limitations_table.csv",
        "missing_parameters.csv",
        "suggested_experiments.csv",
        "virtual_experiment_output_data_dictionary.csv",
        "virtual_experiment_output_schema.json",
    ):
        assert (output_dir / filename).exists(), filename

    time_rows = _csv_rows(output_dir / "time_series_long.csv")
    final_rows = _csv_rows(output_dir / "final_metrics.csv")
    threshold_rows = _csv_rows(output_dir / "threshold_times.csv")
    sampled_rows = _csv_rows(output_dir / "sampled_parameters.csv")
    provenance_rows = _csv_rows(output_dir / "provenance_table.csv")
    limitation_rows = _csv_rows(output_dir / "limitations_table.csv")

    states = {row["state"] for row in time_rows}
    assert {
        "solid_substrate_remaining",
        "soluble_product_amount",
        "substrate_degraded_fraction",
        "solid_substrate_degraded_fraction",
        "accessible_site_fraction_remaining_proxy",
        "degradation_rate",
        "product_release_rate",
    } <= states
    assert "soluble_product_concentration" not in states
    assert not states.intersection({"fungal_biomass", "biomass", "uptake_flux", "respiration", "secretion_rate"})

    metrics = {row["metric"] for row in final_rows}
    assert {
        "solid_substrate_remaining",
        "solid_substrate_degraded_fraction",
        "accessible_site_fraction_remaining_proxy",
        "soluble_product_amount",
        "final_product_amount",
        "final_product_yield",
        "maximum_product_release_rate",
        "maximum_substrate_depletion_rate",
    } <= metrics
    assert "soluble_product_concentration" not in metrics
    assert not any(row["metric"] == "final_product_concentration" and row["units"] == "kilogram" for row in final_rows)
    assert any(
        row["metric"] == "accessible_site_fraction_remaining_proxy"
        and row["status"] == "derived_proxy"
        for row in final_rows
    )
    assert {row["threshold_fraction"] for row in threshold_rows} == {"0.1", "0.5", "0.9"}
    assert any(row["status"] == "computed" for row in threshold_rows)
    assert any(row["status"] == "not_reached" for row in threshold_rows)

    assert {row["role"] for row in sampled_rows} == {
        "surface_rate_constant",
        "adsorption_constant",
        "accessible_surface_area",
        "substrate_initial_amount",
        "enzyme_initial_concentration",
    }
    assert all(row["parameter_source_class"] == "user_supplied_exploratory_prior" for row in sampled_rows)
    assert all(row["exploratory_prior"] == "true" for row in sampled_rows)
    assert all(row["source"] == "user-supplied exploratory range" for row in sampled_rows)
    assert all(row["source_record_id"].startswith("bio001_") for row in sampled_rows)
    assert all(row["range_scope"] == "user_supplied_case_prior" for row in sampled_rows)
    assert all(
        row["range_interpretation"] == "user_supplied_exploratory_prior_not_literature_curated"
        for row in sampled_rows
    )
    assert all(row["allowed_use"] == "exploratory_simulation_only_not_literature_curated" for row in sampled_rows)

    assert any(
        row["record_type"] == "parameter"
        and row["maturity"] == "exploratory_prior"
        and row["exploratory_prior"] == "true"
        for row in provenance_rows
    )
    assert any("not a whole-fungus growth" in row["limitation"] for row in limitation_rows)
    assert any("derived proxies from remaining substrate" in row["limitation"] for row in limitation_rows)
    _assert_threshold_rows_match_trajectory(time_rows, threshold_rows)


def _assert_threshold_rows_match_trajectory(
    time_rows: list[dict[str, str]],
    threshold_rows: list[dict[str, str]],
) -> None:
    by_sample: dict[str, list[tuple[float, float]]] = {}
    for row in time_rows:
        if row["state"] != "substrate_degraded_fraction":
            continue
        by_sample.setdefault(row["sample_id"], []).append((float(row["time"]), float(row["value"])))
    for row in threshold_rows:
        values = sorted(by_sample[row["sample_id"]])
        expected = threshold_crossing_time(
            time_values=[time for time, _fraction in values],
            degraded_fraction=[fraction for _time, fraction in values],
            threshold=float(row["threshold_fraction"]),
        )
        if expected is None:
            assert row["status"] == "not_reached"
            assert row["value"] == ""
        else:
            assert row["status"] == "computed"
            assert float(row["value"]) == pytest.approx(expected)


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
