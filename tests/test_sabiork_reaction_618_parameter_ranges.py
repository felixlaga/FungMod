from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest

from fungal_model.data.sabiork import (
    curate_reaction_618_parameter_ranges,
    load_sabiork_kinlaw_export,
    write_sabiork_parameter_range_report,
)
from fungal_model.registry import load_registry
from fungal_model.screening import assess_modelability


ROOT = Path(__file__).resolve().parents[1]
RAW_EXPORT = (
    ROOT
    / "data"
    / "kinetic_records"
    / "sabiork"
    / "case_001_reaction_618_beta_glucosidase"
    / "raw"
    / "kinlaw_entries_reaction_618.json"
)
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"

FUNGUS_ID = "sabiork_beta_glucosidase_source"
SUBSTRATE_ID = "cellobiose"
ENVIRONMENT_ID = "sabiork_reaction_618_selected_conditions"
PROCESS_TYPE = "homogeneous_michaelis_menten"
SELECTED_ENTRY_ID = "35622"
ENZYME_CONCENTRATION_SYMBOL = "enzyme_concentration_beta_glucosidase"


def test_local_raw_sabiork_export_loads_without_live_api_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_network_is_used(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("DATA-002 curation must use the local SABIO-RK snapshot.")

    monkeypatch.setattr("urllib.request.urlopen", fail_if_network_is_used)

    export = load_sabiork_kinlaw_export(RAW_EXPORT)

    assert export.meta["total_count"] == 29
    assert len(export.entries) == 29


def test_reaction_618_curation_writes_eligible_and_excluded_tables(tmp_path: Path) -> None:
    report = _curated_report()

    report_path = write_sabiork_parameter_range_report(report, tmp_path)
    eligible_rows = _csv_rows(tmp_path / "reaction_618_eligible_entries.csv")
    excluded_rows = _csv_rows(tmp_path / "reaction_618_excluded_entries.csv")
    payload = json.loads(report_path.read_text(encoding="utf-8"))

    assert report_path.name == "parameter_range_summary.json"
    assert (tmp_path / "parameter_range_summary.md").exists()
    assert len(eligible_rows) == 15
    assert len(excluded_rows) == 14
    assert all(row["reason"] for row in excluded_rows)
    assert set(_required_eligible_columns()) <= set(eligible_rows[0])
    assert set(_required_excluded_columns()) <= set(excluded_rows[0])
    assert "observations" in payload
    assert "limitations" in payload


def test_included_entries_satisfy_reaction_618_kinetic_criteria() -> None:
    report = _curated_report()

    for entry in report.eligible_entries:
        assert entry["ec_number"] == "3.2.1.21"
        assert "beta-glucosidase" in str(entry["enzyme_name"]).lower()
        assert entry["kinetic_law_type"] == "Michaelis-Menten"
        assert entry["Km_cellobiose_units"] == "mM"
        assert entry["kcat_cellobiose_units"] == "s^(-1)"
        assert entry["source_field_Km"] == "kineticlaw.parameter[].start_value"
        assert entry["source_field_kcat"] == "kineticlaw.parameter[].start_value"


def test_reaction_618_scoped_ranges_preserve_units_and_sparse_statuses() -> None:
    report = _curated_report()
    ranges = report.ranges
    all_eligible = ranges["all_eligible"]["all_eligible"]

    km_range = all_eligible["Km_cellobiose"]
    kcat_range = all_eligible["kcat_cellobiose"]
    assert km_range.count == 15
    assert km_range.status == "ok"
    assert km_range.units == "mM"
    assert km_range.lower == pytest.approx(0.68)
    assert km_range.upper == pytest.approx(114.0)
    assert km_range.min_entry_id
    assert km_range.max_entry_id
    assert km_range.p50 == pytest.approx(km_range.median)
    assert kcat_range.count == 15
    assert kcat_range.units == "s^(-1)"
    assert kcat_range.lower == pytest.approx(0.13)
    assert kcat_range.upper == pytest.approx(7.17)

    assert ranges["by_organism"]["Oryza sativa"]["Km_cellobiose"].count == 8
    assert ranges["by_pH_exact"]["pH 5"]["Km_cellobiose"].count == 7
    assert any(
        group["Km_cellobiose"].count == 13
        for group in ranges["by_temperature_exact"].values()
    )
    assert ranges["wildtype_only"]["wildtype_only"]["Km_cellobiose"].count == 6
    assert ranges["mutant_only"]["mutant_only"]["Km_cellobiose"].count == 9
    assert any(
        group["Km_cellobiose"].status == "insufficient_n"
        for group in ranges["by_organism"].values()
    )


def test_registry_keeps_selected_exact_unknown_and_exploratory_records_distinct() -> None:
    registry = load_registry(REGISTRY_INDEX)

    exact_km = _parameter_record(registry, symbol="Km_cellobiose", maturity="literature_processed")
    exact_kcat = _parameter_record(registry, symbol="kcat_cellobiose", maturity="literature_processed")
    range_km = _parameter_record(registry, symbol="Km_cellobiose", maturity="literature_range")
    unknown_enzyme = _parameter_record(
        registry,
        symbol=ENZYME_CONCENTRATION_SYMBOL,
        maturity="literature_processed",
    )
    exploratory_enzyme = _parameter_record(
        registry,
        symbol=ENZYME_CONCENTRATION_SYMBOL,
        maturity="exploratory_prior",
    )

    assert exact_km.record_id == "sabiork_reaction_618_Km_cellobiose"
    assert exact_km.value.kind == "exact"
    assert exact_km.provenance["selected_kinlaw_entry_id"] == SELECTED_ENTRY_ID
    assert exact_kcat.value.kind == "exact"
    assert exact_kcat.provenance["selected_kinlaw_entry_id"] == SELECTED_ENTRY_ID
    assert range_km.value.kind == "range"
    assert range_km.value.source == "SABIO-RK Reaction 618 multi-entry curation"
    assert range_km.provenance["curation_file"].endswith("parameter_range_summary.json")
    assert unknown_enzyme.value.kind == "unknown"
    assert exploratory_enzyme.value.kind == "distribution"
    assert exploratory_enzyme.provenance["exploratory_prior"] is True


def test_scientific_modelability_does_not_use_broad_literature_ranges_as_exact_values() -> None:
    registry = load_registry(REGISTRY_INDEX)

    report = assess_modelability(
        fungus_id=FUNGUS_ID,
        substrate_id=SUBSTRATE_ID,
        environment_id=ENVIRONMENT_ID,
        registry=registry,
        mode="scientific",
    )

    km_item = _known_item(report, "Km_cellobiose")
    kcat_item = _known_item(report, "kcat_cellobiose")
    assert report.status == "underparameterized"
    assert km_item.details["record_id"] == "sabiork_reaction_618_Km_cellobiose"
    assert kcat_item.details["record_id"] == "sabiork_reaction_618_kcat_cellobiose"
    assert "literature_range" not in km_item.details["record_id"]
    assert "literature_range" not in kcat_item.details["record_id"]


def _curated_report():
    return curate_reaction_618_parameter_ranges(load_sabiork_kinlaw_export(RAW_EXPORT))


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _required_eligible_columns() -> tuple[str, ...]:
    return (
        "entry_id",
        "organism",
        "enzyme_name",
        "ec_number",
        "enzyme_type",
        "kinetic_law_type",
        "Km_cellobiose_value",
        "Km_cellobiose_units",
        "kcat_cellobiose_value",
        "kcat_cellobiose_units",
        "ph",
        "temperature",
        "temperature_units",
        "buffer",
        "pubmed_id",
        "title",
        "journal",
        "year",
        "source_field_Km",
        "source_field_kcat",
    )


def _required_excluded_columns() -> tuple[str, ...]:
    return (
        "entry_id",
        "reason",
        "organism",
        "enzyme_name",
        "ec_number",
        "kinetic_law_type",
        "available_parameter_types",
        "notes",
    )


def _parameter_record(registry, *, symbol: str, maturity: str):
    for record in registry.get_parameter_records(
        parameter_symbol=symbol,
        process_type=PROCESS_TYPE,
    ):
        if record.maturity == maturity:
            return record
    raise AssertionError(f"Missing {maturity} record for {symbol}.")


def _known_item(report: Any, item_id: str):
    for item in report.known:
        if item.item_type == "parameter" and item.item_id == item_id:
            return item
    raise AssertionError(f"Missing known item {item_id}.")
