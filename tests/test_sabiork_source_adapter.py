from __future__ import annotations

import csv
from pathlib import Path
from typing import NoReturn

import pytest
import yaml

from fungal_model.sources.sabiork import (
    SabioRKReactionRecord,
    SabioRKSource,
    SabioRKSourceError,
)


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = (
    ROOT
    / "data"
    / "kinetic_records"
    / "sabiork"
    / "case_001_reaction_618_beta_glucosidase"
    / "raw"
)
REACTION_618_EXPORT = RAW_DIR / "kinlaw_entries_reaction_618.json"
MINIMAL_EXPORT = ROOT / "tests" / "fixtures" / "sabiork_reaction_618_export_minimal.json"
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"


def test_source_adapter_loads_frozen_snapshot_without_network() -> None:
    def forbidden_fetcher(_query: str, _output_dir: Path) -> NoReturn:
        raise AssertionError("tests must not call live SABIO-RK")

    source = SabioRKSource(cache_dir=RAW_DIR, live_fetcher=forbidden_fetcher)

    snapshot = source.fetch_kinlaw_entries("SabioReactionID:618")

    assert snapshot.export_path == REACTION_618_EXPORT
    assert snapshot.metadata_path == RAW_DIR / "fetch_metadata.json"
    assert snapshot.export.meta["total_count"] == 29
    assert len(snapshot.export.entries) == 29


def test_source_adapter_refresh_requires_explicit_fetcher(tmp_path: Path) -> None:
    source = SabioRKSource(cache_dir=tmp_path)

    with pytest.raises(SabioRKSourceError, match="explicit live_fetcher"):
        source.fetch_kinlaw_entries("SabioReactionID:618", refresh=True)


def test_source_adapter_extracts_reaction_products_and_stoichiometry() -> None:
    source = SabioRKSource(cache_dir=RAW_DIR)
    snapshot = source.fetch_kinlaw_entries("SabioReactionID:618")

    record = _record_by_entry(source.parse_reaction_records(snapshot), "35622")

    assert record.reaction_id == "618"
    assert record.equation == "H2O + Cellobiose = 2 beta-D-Glucose"
    assert {participant.compound_name for participant in record.substrates} == {"H2O", "Cellobiose"}
    assert [(participant.compound_name, participant.stoichiometry) for participant in record.products] == [
        ("beta-D-Glucose", "2")
    ]
    assert record.products[0].external_identifiers["ChebiID"]


def test_source_adapter_extracts_enzyme_conditions_publication_and_parameters() -> None:
    source = SabioRKSource(cache_dir=RAW_DIR)
    snapshot = source.fetch_kinlaw_entries("SabioReactionID:618")

    record = _record_by_entry(source.parse_reaction_records(snapshot), "35622")
    parameters = {parameter.proposed_symbol: parameter for parameter in record.parameters}

    assert record.enzyme_name == "beta-glucosidase"
    assert record.ec_number == "3.2.1.21"
    assert record.organism == "Oryza sativa"
    assert record.ph == 5
    assert record.temperature == 30
    assert record.temperature_units == "°C"
    assert record.publication["pubmed_id"] == "19587102"
    assert parameters["Km_cellobiose"].start_value == 15.3
    assert parameters["Km_cellobiose"].units == "mM"
    assert parameters["kcat_cellobiose"].start_value == 0.13
    assert parameters["kcat_cellobiose"].units == "s^(-1)"
    assert parameters["enzyme_concentration"].start_value is None
    assert parameters["enzyme_concentration"].units == "-"


def test_source_adapter_writes_review_only_proposed_records(tmp_path: Path) -> None:
    source = SabioRKSource(cache_dir=RAW_DIR)
    snapshot = source.fetch_kinlaw_entries("SabioReactionID:618")
    records = source.parse_reaction_records(snapshot)
    proposal = source.propose_fungmod_records(
        records,
        source_query=snapshot.query,
        source_snapshot_path=str(snapshot.export_path),
    )

    result = proposal.write(tmp_path / "reaction_618_proposals")

    required = {
        "reaction_records",
        "compound_roles",
        "kinetic_law_entries",
        "parameters",
        "publications",
        "proposed_product_maps",
        "proposed_parameter_records",
        "proposed_process_compatibility",
        "source_adapter_report",
    }
    assert set(result.paths) == required
    assert all(path.exists() for path in result.paths.values())

    compound_rows = _csv_rows(result.paths["compound_roles"])
    parameter_rows = _csv_rows(result.paths["parameters"])
    product_maps = yaml.safe_load(result.paths["proposed_product_maps"].read_text(encoding="utf-8"))
    parameter_proposals = yaml.safe_load(result.paths["proposed_parameter_records"].read_text(encoding="utf-8"))

    assert any(
        row["entry_id"] == "35622"
        and row["role"] == "product"
        and row["compound_name"] == "beta-D-Glucose"
        and row["stoichiometry"] == "2"
        for row in compound_rows
    )
    assert any(row["entry_id"] == "35622" and row["proposed_symbol"] == "Km_cellobiose" for row in parameter_rows)
    assert product_maps["proposal_status"] == "proposed_review_required"
    assert product_maps["records"][0]["review_required"] is True
    assert parameter_proposals["proposal_status"] == "proposed_review_required"
    assert any(
        record["record_id"] == "proposed_sabiork_35622_Km_cellobiose"
        and record["value"]["kind"] == "exact"
        and record["source_units"] == "mM"
        and record["allowed_use"] == "review_only_not_simulation_registry"
        for record in parameter_proposals["records"]
    )


def test_source_adapter_does_not_mutate_simulation_registry(tmp_path: Path) -> None:
    registry_before = REGISTRY_INDEX.read_text(encoding="utf-8")
    source = SabioRKSource(cache_dir=RAW_DIR)
    snapshot = source.fetch_kinlaw_entries("SabioReactionID:618")
    records = source.parse_reaction_records(snapshot)

    source.propose_fungmod_records(records).write(tmp_path / "proposals")

    assert REGISTRY_INDEX.read_text(encoding="utf-8") == registry_before
    assert not (ROOT / "data_registry" / "proposed_parameter_records.yml").exists()
    assert not (ROOT / "data_registry" / "proposed_product_maps.yml").exists()


def test_source_adapter_reports_missing_fields_without_guessing() -> None:
    source = SabioRKSource(cache_dir=MINIMAL_EXPORT.parent)
    snapshot = source.load_kinlaw_entries(MINIMAL_EXPORT, query="SabioReactionID:618")

    records = source.parse_reaction_records(snapshot)

    assert records[0].participants == ()
    assert records[0].parameters == ()
    assert "missing_reaction_species; no participants were guessed from the equation." in records[0].warnings
    assert "missing_kinetic_law_parameters" in records[0].warnings


def _record_by_entry(records: tuple[SabioRKReactionRecord, ...], entry_id: str) -> SabioRKReactionRecord:
    for record in records:
        if record.entry_id == entry_id:
            return record
    raise AssertionError(f"Missing parsed entry {entry_id}")


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
