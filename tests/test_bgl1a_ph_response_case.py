"""P. chrysosporium BGL1A on cellobiose: the first registry case with an active pH response law.

The case binds the SABIO-RK entry 38522 pH-dependent Michaelis-Menten
constants (Tsukada et al. 2008) to the generic ``ph_ionization_michaelis_menten``
law. These tests pin the records to the raw export bit for bit, check the
honest mode gating (exploratory only, because the assay loadings are explicit
assumptions), and verify that virtual experiments over pH report
``active_response_model`` while a temperature-varying grid is still blocked.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import yaml
from scipy.integrate import solve_ivp

from fungal_model.api import EnvironmentGrid, VirtualExperiment, VirtualExperimentError
from fungal_model.kinetics import EnvironmentalValidityWarning
from fungal_model.registry import load_registry
from fungal_model.screening import assess_modelability, simulate_screen

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"
RAW_EXPORT = (
    ROOT
    / "data"
    / "kinetic_records"
    / "sabiork"
    / "case_001_reaction_618_beta_glucosidase"
    / "raw"
    / "kinlaw_entries_reaction_618.json"
)
FUNGUS_ID = "phanerochaete_chrysosporium_k3"
SUBSTRATE_ID = "cellobiose"
ENTRY_ID = 38522
PH_ENVIRONMENTS = tuple(f"tsukada_2008_bgl1a_assay_30c_ph{ph}" for ph in (4, 5, 6, 7, 8))
CONSTANT_RECORDS = {
    "tsukada_2008_bgl1a_k0_cellobiose": ("k0", 1.81, "1 / second"),
    "tsukada_2008_bgl1a_Km0_cellobiose": ("Km0", 6.8, "millimolar"),
    "tsukada_2008_bgl1a_pKe1": ("pKe1", 4.4, "dimensionless"),
    "tsukada_2008_bgl1a_pKe2": ("pKe2", 7.7, "dimensionless"),
    "tsukada_2008_bgl1a_pKes1": ("pKes1", 4.1, "dimensionless"),
    "tsukada_2008_bgl1a_pKes2": ("pKes2", 7.6, "dimensionless"),
}
ASSUMPTION_SYMBOLS = {"bgl1a_assay_initial_cellobiose_concentration", "bgl1a_assay_enzyme_concentration"}


def _raw_entry() -> dict:
    data = json.loads(RAW_EXPORT.read_text(encoding="utf-8"))["data"]
    return next(entry for entry in data if entry["id"] == ENTRY_ID)


def _raw_parameters(entry: dict) -> dict[str, dict]:
    return {item["name"]: item for item in entry["kineticlaw"]["parameter"]}


def _deposited_law(E: float, S: float, pH: float) -> float:
    """Verbatim transcription of the SABIO-RK formula with the entry 38522 constants."""

    k0, Km0, pKe1, pKe2, pKes1, pKes2 = 1.81, 6.8, 4.4, 7.7, 4.1, 7.6
    return (
        E
        * ((k0) / ((10 ** (pKes1 - pH) + 1) * (10 ** (pH - pKes2) + 1)))
        * S
        / (
            ((k0) / ((10 ** (pKes1 - pH) + 1) * (10 ** (pH - pKes2) + 1)))
            / (((k0) / (Km0)) / ((10 ** (pKe1 - pH) + 1) * (10 ** (pH - pKe2) + 1)))
            + S
        )
    )


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_registry_constants_equal_the_raw_sabio_export_and_record_its_hash() -> None:
    registry = load_registry(REGISTRY_INDEX)
    entry = _raw_entry()
    raw = _raw_parameters(entry)
    # Exact bytes: data/kinetic_records/** is checked out without line-ending
    # conversion (.gitattributes), like the other checksummed source snapshots.
    digest = hashlib.sha256(RAW_EXPORT.read_bytes()).hexdigest()
    assert entry["kineticlaw"]["kinlaw_type"]["name"] == "Michaelis-Menten (pH-dependent)"
    assert entry["general"]["organism"]["name"] == "Phanerochaete chrysosporium"
    assert entry["publication"]["pubmed_id"] == "18023045"
    for record_id, (raw_name, value, units) in CONSTANT_RECORDS.items():
        record = registry.parameters[record_id]
        assert record.value.kind == "exact"
        assert record.value.value == raw[raw_name]["start_value"] == value
        assert record.value.units == units
        assert record.maturity == "literature_processed"
        assert record.fungus_id == FUNGUS_ID and record.substrate_id == SUBSTRATE_ID
        assert record.environment_id is None
        assert record.process_type == "ph_ionization_michaelis_menten"
        assert record.provenance["selected_kinlaw_entry_id"] == str(ENTRY_ID)
        assert record.provenance["raw_export_sha256"] == digest
        assert "PMID 18023045" in record.provenance["publication"]
        deviation = raw[raw_name]["standard_deviation"]
        if deviation is not None:
            assert str(deviation) in record.value.notes
    ph_variable = raw["pH"]
    assert registry.parameters["tsukada_2008_bgl1a_ph_series_minimum"].value.value == ph_variable["start_value"] == 4.0
    assert registry.parameters["tsukada_2008_bgl1a_ph_series_maximum"].value.value == ph_variable["end_value"] == 8.0
    assert raw["S"]["start_value"] is None and raw["E"]["start_value"] is None
    for record_id in (
        "bgl1a_assay_initial_cellobiose_concentration_exploratory",
        "bgl1a_assay_enzyme_concentration_exploratory",
    ):
        record = registry.parameters[record_id]
        assert record.maturity == "exploratory_prior"
        assert record.provenance["exploratory_prior"] is True
        assert "assumption" in record.value.source
    fungus = registry.get_fungus(FUNGUS_ID)
    assert fungus.provenance["raw_export_sha256"] == digest
    assert fungus.enzyme_classes == ("beta_glucosidase",)
    assert entry["experimental_conditions"]["envvar_temperature"]["start_value"] == 30
    for ph, environment_id in zip((4.0, 5.0, 6.0, 7.0, 8.0), PH_ENVIRONMENTS, strict=True):
        environment = registry.get_environment(environment_id)
        assert environment.conditions["temperature"].value == pytest.approx(303.15)
        assert environment.conditions["ph"].value == ph
        assert "environment_effect_status" not in environment.provenance


def test_modelability_allows_exploratory_screens_and_blocks_scientific_mode_on_the_assumptions() -> None:
    registry = load_registry(REGISTRY_INDEX)
    exploratory = assess_modelability(
        fungus_id=FUNGUS_ID, substrate_id=SUBSTRATE_ID, environment_id=PH_ENVIRONMENTS[1], registry=registry, mode="exploratory"
    )
    assert exploratory.status == "modelable"
    assert exploratory.required_processes == ("ph_ionization_michaelis_menten",)
    scientific = assess_modelability(
        fungus_id=FUNGUS_ID, substrate_id=SUBSTRATE_ID, environment_id=PH_ENVIRONMENTS[1], registry=registry, mode="scientific"
    )
    assert scientific.status == "underparameterized"
    assert {item.item_id for item in scientific.missing} == ASSUMPTION_SYMBOLS
    assert all("Measure or curate" in suggestion for suggestion in scientific.suggested_experiments)
    sibling = assess_modelability(
        fungus_id="sabiork_beta_glucosidase_source",
        substrate_id=SUBSTRATE_ID,
        environment_id="sabiork_reaction_618_selected_conditions",
        registry=registry,
        mode="exploratory",
    )
    assert sibling.required_processes == ("homogeneous_michaelis_menten",)


def test_assembled_case_binds_the_ph_law_and_records_the_environment_response(tmp_path: Path) -> None:
    registry = load_registry(REGISTRY_INDEX)
    screen = simulate_screen(
        fungus_ids=[FUNGUS_ID],
        substrate_ids=[SUBSTRATE_ID],
        environment_ids=[PH_ENVIRONMENTS[2]],
        registry=registry,
        n_samples=1,
        seed=3,
        output_dir=tmp_path / "screen",
        mode="exploratory",
    )
    case = screen.case_results[0]
    assert case.process_type == "ph_ionization_michaelis_menten"
    assert case.environment_response["status"] == "active_response_model"
    assert set(case.environment_response["conditions"]) == {"ph"}
    assert case.environment_response["conditions"]["ph"]["laws"] == [
        {"process_id": "phanerochaete_bgl1a_ph_ionization_mm", "law": "ph_ionization_michaelis_menten", "binding": "process_law"}
    ]
    config = yaml.safe_load(Path(case.samples[0].config_path).read_text(encoding="utf-8"))
    assert set(config["entities"]["environment"]["data"]["conditions"]) == {"ph"}
    assert config["entities"]["environment"]["data"]["conditions"]["ph"]["value"] == 6.0
    process = config["processes"][0]
    assert process["process_type"] == "ph_ionization_michaelis_menten"
    assert process["parameters"] == {
        "turnover": "bgl1a_k0_cellobiose",
        "michaelis_constant": "bgl1a_Km0_cellobiose",
        "free_enzyme_lower_pk": "bgl1a_pKe1",
        "free_enzyme_upper_pk": "bgl1a_pKe2",
        "complex_lower_pk": "bgl1a_pKes1",
        "complex_upper_pk": "bgl1a_pKes2",
        "minimum_ph": "bgl1a_ph_series_minimum",
        "maximum_ph": "bgl1a_ph_series_maximum",
        "rate_units": "millimolar / second",
    }
    assert config["provenance"]["environment_response"] == case.environment_response
    assert all(sample.validation_passed for sample in case.samples)


def test_virtual_experiment_over_the_ph_series_reports_an_active_response_and_matches_the_deposited_law(
    tmp_path: Path,
) -> None:
    study = VirtualExperiment.from_names(
        fungi="P. chrysosporium",
        substrates="cellobiose",
        environments=PH_ENVIRONMENTS,
        registry=REGISTRY_INDEX,
    )
    result = study.simulate(mode="exploratory", n_samples=1, seed=1, output_dir=tmp_path / "ph_series", quicklook=False)
    output_dir = Path(result.output_directory)
    summary = {row["environment_id"]: row for row in _csv_rows(output_dir / "environment_summary.csv")}
    assert set(summary) == set(PH_ENVIRONMENTS)
    assert {row["environment_effect_status"] for row in summary.values()} == {"active_response_model"}
    assert {row["environment_response_model"] for row in summary.values()} == {"ph:ph_ionization_michaelis_menten"}
    assert {row["environment_comparison_allowed"] for row in summary.values()} == {"true"}
    assert {row["environment_ranking_allowed"] for row in summary.values()} == {"true"}
    assert {row["environment_response_metric_status"] for row in summary.values()} == {"computed"}
    half_times = {
        environment_id: float(row["median_time_to_50_percent_degradation"]) for environment_id, row in summary.items()
    }
    assert min(half_times, key=half_times.get) == PH_ENVIRONMENTS[2]
    assert max(half_times, key=half_times.get) == PH_ENVIRONMENTS[4]
    assert len(set(half_times.values())) == len(PH_ENVIRONMENTS)
    comparison_rows = _csv_rows(output_dir / "comparison_summary.csv")
    assert {row["ranking_allowed"] for row in comparison_rows} == {"true"}
    limitation_rows = _csv_rows(output_dir / "limitations_table.csv")
    assert any(
        row["category"] == "environment_effect" and "Environment response is active for ph" in row["limitation"]
        for row in limitation_rows
    )
    assert any(row["category"] == "ph_response" for row in limitation_rows)
    assert not any("Do not rank or plot these cases" in row["limitation"] for row in limitation_rows)

    series = [
        row
        for row in _csv_rows(output_dir / "time_series_long.csv")
        if row["environment_id"] == PH_ENVIRONMENTS[1] and row["state_role"] == "substrate"
    ]
    times = np.array([float(row["time"]) for row in series])
    substrate = np.array([float(row["value"]) for row in series])
    assert {row["units"] for row in series} == {"millimolar"} and {row["time_units"] for row in series} == {"second"}
    reference = solve_ivp(
        lambda t, y: [-_deposited_law(1.0e-3, y[0], 5.0)],
        (times[0], times[-1]),
        [5.0],
        t_eval=times,
        rtol=1e-10,
        atol=1e-12,
    )
    np.testing.assert_allclose(substrate, reference.y[0], rtol=1e-4, atol=1e-6)


def test_runtime_grid_blocks_ranking_when_temperature_varies_without_a_law_and_warns_outside_the_ph_range(
    tmp_path: Path,
) -> None:
    study = VirtualExperiment.from_registry(
        fungi=FUNGUS_ID,
        substrates=SUBSTRATE_ID,
        environments=EnvironmentGrid(temperature_C=[30.0, 40.0], ph=[5.0]),
        registry=REGISTRY_INDEX,
    )
    result = study.simulate(mode="exploratory", n_samples=1, seed=1, output_dir=tmp_path / "temperature_grid", quicklook=False)
    summary = _csv_rows(Path(result.output_directory) / "environment_summary.csv")
    assert {row["environment_effect_status"] for row in summary} == {"active_response_model"}
    assert {row["environment_response_model"] for row in summary} == {"ph:ph_ionization_michaelis_menten"}
    assert {row["environment_comparison_allowed"] for row in summary} == {"false"}
    assert {row["environment_ranking_allowed"] for row in summary} == {"false"}
    assert all("varies temperature without a response law" in row["environment_guardrail"] for row in summary)
    assert {row["environment_response_metric_status"] for row in summary} == {"not_applicable_metadata_only"}
    comparison_rows = _csv_rows(Path(result.output_directory) / "comparison_summary.csv")
    assert {row["ranking_allowed"] for row in comparison_rows} == {"false"}
    assert all("varies temperature" in row["ranking_blocking_reason"] for row in comparison_rows)

    out_of_range = VirtualExperiment.from_registry(
        fungi=FUNGUS_ID,
        substrates=SUBSTRATE_ID,
        environments=EnvironmentGrid(temperature_C=[30.0], ph=[9.0]),
        registry=REGISTRY_INDEX,
    )
    with pytest.warns(EnvironmentalValidityWarning, match="above pH 8.0"):
        out_of_range.simulate(mode="exploratory", n_samples=1, seed=1, output_dir=tmp_path / "ph_9", quicklook=False)

    in_range = VirtualExperiment.from_registry(
        fungi=FUNGUS_ID,
        substrates=SUBSTRATE_ID,
        environments=EnvironmentGrid(temperature_C=[30.0], ph=[4.5, 6.5]),
        registry=REGISTRY_INDEX,
    )
    grid_result = in_range.simulate(mode="exploratory", n_samples=1, seed=1, output_dir=tmp_path / "ph_grid", quicklook=False)
    grid_summary = _csv_rows(Path(grid_result.output_directory) / "environment_summary.csv")
    assert {row["environment_comparison_allowed"] for row in grid_summary} == {"true"}
    assert {row["environment_source"] for row in grid_summary} == {"runtime_environment_grid"}


def test_scientific_mode_is_blocked_by_the_explicit_loading_assumptions(tmp_path: Path) -> None:
    study = VirtualExperiment.from_registry(
        fungi=FUNGUS_ID, substrates=SUBSTRATE_ID, environments=PH_ENVIRONMENTS[:1], registry=REGISTRY_INDEX
    )
    reports = study.preflight(mode="scientific")
    assert reports[0].status == "underparameterized"
    assert {item.item_id for item in reports[0].missing} == ASSUMPTION_SYMBOLS
    with pytest.raises(VirtualExperimentError):
        study.simulate(mode="scientific", output_dir=tmp_path / "scientific", quicklook=False)
