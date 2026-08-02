from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import NoReturn

import pytest
import yaml

from fungal_model.sources.sabiork import (
    PROPOSAL_STATUS,
    REVIEW_ONLY_ALLOWED_USE,
    RegistryProposal,
    SabioRKSource,
    SabioRKSourceError,
    SourceDiscoveryResult,
    stable_registry_proposal_id,
    stable_sabiork_token,
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
DATA_REGISTRY = ROOT / "data_registry"


def test_discover_for_virtual_experiment_uses_frozen_snapshot_without_network() -> None:
    def forbidden_fetcher(_query: str, _output_dir: Path) -> NoReturn:
        raise AssertionError("SOURCE-002 tests must not call live SABIO-RK")

    source = SabioRKSource(cache_dir=RAW_DIR, live_fetcher=forbidden_fetcher)

    discovery = source.discover_for_virtual_experiment(
        fungus="Oryza sativa",
        substrate="cellobiose",
        enzyme="beta-glucosidase",
        ec_number="3.2.1.21",
        reaction_id="618",
        entry_id="35622",
    )

    assert isinstance(discovery, SourceDiscoveryResult)
    assert discovery.source_query == "SabioReactionID:618"
    assert discovery.source_snapshot_path == str(REACTION_618_EXPORT)
    assert [record.entry_id for record in discovery.reaction_records] == ["35622"]


def test_discovery_default_cache_finds_repo_frozen_snapshot() -> None:
    discovery = SabioRKSource().discover_for_virtual_experiment(
        reaction_id="618",
        entry_id="35622",
        substrate="cellobiose",
    )

    assert discovery.reaction_records[0].entry_id == "35622"
    assert "data/kinetic_records/sabiork" in Path(discovery.source_snapshot_path).as_posix()


def test_discovery_filters_by_human_names_and_reports_source_content() -> None:
    discovery = SabioRKSource(cache_dir=RAW_DIR).discover_for_virtual_experiment(
        fungus="Oryza sativa",
        substrate="cellobiose",
        enzyme="beta-glucosidase",
        ec_number="3.2.1.21",
        reaction="H2O + Cellobiose",
        reaction_id="618",
        entry_id="35622",
    )

    assert discovery.organism_names == ("Oryza sativa",)
    assert discovery.enzyme_names == ("beta-glucosidase",)
    assert discovery.ec_numbers == ("3.2.1.21",)
    assert "Cellobiose" in discovery.substrates
    assert discovery.products == ("beta-D-Glucose",)
    product_rows = discovery.show_products()
    assert [(row["role"], row["compound_name"], row["stoichiometry"]) for row in product_rows] == [
        ("substrate", "H2O", "1"),
        ("substrate", "Cellobiose", "1"),
        ("product", "beta-D-Glucose", "2"),
    ]
    assert all(row["external_identifiers"] for row in product_rows)


def test_discovery_surfaces_kinetic_parameters_and_missing_fields() -> None:
    discovery = SabioRKSource(cache_dir=RAW_DIR).discover_for_virtual_experiment(
        reaction_id="618",
        entry_id="35622",
    )

    parameters = {row["proposed_symbol"]: row for row in discovery.show_kinetic_parameters()}
    missing = {row["field"] for row in discovery.show_missing_fields()}

    assert parameters["Km_cellobiose"]["start_value"] == 15.3
    assert parameters["kcat_cellobiose"]["units"] == "s^(-1)"
    assert "parameter.enzyme_concentration.start_value" in missing
    assert "parameter.enzyme_concentration.units" in missing


def test_unknown_discovery_query_fails_clearly() -> None:
    with pytest.raises(SabioRKSourceError, match="No SABIO-RK entries matched discovery filters"):
        SabioRKSource(cache_dir=RAW_DIR).discover_for_virtual_experiment(
            fungus="Aspergillus niger",
            substrate="cellobiose",
            reaction_id="618",
        )


def test_refresh_requires_explicit_live_fetcher_for_discovery(tmp_path: Path) -> None:
    with pytest.raises(SabioRKSourceError, match="explicit live_fetcher"):
        SabioRKSource(cache_dir=tmp_path).discover_for_virtual_experiment(
            reaction_id="618",
            refresh=True,
        )


def test_registry_proposal_has_deterministic_review_only_ids() -> None:
    discovery = SabioRKSource(cache_dir=RAW_DIR).discover_for_virtual_experiment(
        reaction_id="618",
        entry_id="35622",
    )

    proposal = discovery.to_registry_proposal(
        process_type="homogeneous_michaelis_menten",
        product_map="auto_from_stoichiometry",
    )
    proposal_again = discovery.to_registry_proposal(
        process_type="homogeneous_michaelis_menten",
        product_map="auto_from_stoichiometry",
    )

    assert isinstance(proposal, RegistryProposal)
    assert stable_sabiork_token("beta-D-Glucose") == "beta_d_glucose"
    assert (
        stable_registry_proposal_id("parameter", "618", "35622", "Km_cellobiose")
        == "proposed_sabiork_parameter_618_35622_km_cellobiose"
    )
    assert proposal.to_dict() == proposal_again.to_dict()
    records = proposal.proposed_records()
    parameter_ids = {record["record_id"] for record in records["parameter_records"]}
    product_map = records["product_maps"][0]

    assert proposal.proposal_status == PROPOSAL_STATUS
    assert "proposed_sabiork_parameter_618_35622_km_cellobiose" in parameter_ids
    assert product_map["proposal_status"] == PROPOSAL_STATUS
    assert product_map["stoichiometric_yields"] == {"beta_d_glucose": 2.0}
    assert all(record["allowed_use"] == REVIEW_ONLY_ALLOWED_USE for record in records["parameter_records"])


def test_registry_proposal_writes_review_only_bundle(tmp_path: Path) -> None:
    discovery = SabioRKSource(cache_dir=RAW_DIR).discover_for_virtual_experiment(
        reaction_id="618",
        entry_id="35622",
    )
    proposal = discovery.to_registry_proposal()

    result = proposal.write(tmp_path / "proposed_records" / "sabiork" / "reaction_618")

    expected = {
        "proposal_manifest",
        "source_discovery_result",
        "proposed_fungi",
        "proposed_substrates",
        "proposed_enzyme_classes",
        "proposed_product_maps",
        "proposed_parameter_records",
        "proposed_process_compatibility",
        "proposed_case_templates",
        "source_adapter_report",
    }
    assert set(result.paths) == expected
    assert all(path.exists() for path in result.paths.values())

    manifest = json.loads(result.paths["proposal_manifest"].read_text(encoding="utf-8"))
    parameters = yaml.safe_load(result.paths["proposed_parameter_records"].read_text(encoding="utf-8"))
    templates = yaml.safe_load(result.paths["proposed_case_templates"].read_text(encoding="utf-8"))

    assert manifest["proposal_status"] == PROPOSAL_STATUS
    assert parameters["proposal_status"] == PROPOSAL_STATUS
    assert any(
        record["record_id"] == "proposed_sabiork_parameter_618_35622_km_cellobiose"
        and record["allowed_use"] == REVIEW_ONLY_ALLOWED_USE
        for record in parameters["records"]
    )
    assert templates["records"][0]["proposal_status"] == PROPOSAL_STATUS
    assert "not production registry records" in result.paths["source_adapter_report"].read_text(encoding="utf-8")


def test_registry_proposal_refuses_to_write_inside_data_registry() -> None:
    discovery = SabioRKSource(cache_dir=RAW_DIR).discover_for_virtual_experiment(
        reaction_id="618",
        entry_id="35622",
    )

    with pytest.raises(SabioRKSourceError, match="refuses to write inside data_registry"):
        discovery.to_registry_proposal().write(DATA_REGISTRY / "source_002_should_not_exist")

    assert not (DATA_REGISTRY / "source_002_should_not_exist").exists()


def test_registry_proposal_does_not_mutate_production_registry(tmp_path: Path) -> None:
    before = _data_registry_snapshot()
    discovery = SabioRKSource(cache_dir=RAW_DIR).discover_for_virtual_experiment(
        reaction_id="618",
        entry_id="35622",
    )

    discovery.to_registry_proposal().write(tmp_path / "review_only_proposal")

    assert _data_registry_snapshot() == before


def test_discovery_workflow_makes_no_socket_connection(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def forbidden_connect(*_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("SOURCE-002 discovery tests must not open network sockets")

    monkeypatch.setattr(socket.socket, "connect", forbidden_connect)

    discovery = SabioRKSource(cache_dir=RAW_DIR).discover_for_virtual_experiment(
        reaction_id="618",
        entry_id="35622",
    )
    discovery.to_registry_proposal().write(tmp_path / "proposal")

    assert discovery.reaction_records[0].entry_id == "35622"


def test_source_002_notebook_exists_and_uses_review_only_workflow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    notebook_path = ROOT / "notebooks" / "09_sabiork_discovery_to_registry_proposal.ipynb"
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    source = "\n".join(
        "".join(cell.get("source", []))
        for cell in notebook["cells"]
        if cell.get("cell_type") == "code"
    )
    markdown = "\n".join(
        "".join(cell.get("source", []))
        for cell in notebook["cells"]
        if cell.get("cell_type") == "markdown"
    )

    assert notebook["nbformat"] == 4
    assert "discover_for_virtual_experiment" in source
    assert "to_registry_proposal" in source
    assert "data_registry" not in source
    assert "not production registry records" in markdown
    assert "review required" in markdown.lower()

    monkeypatch.setenv("FUNGMOD_NOTEBOOK_OUTPUT_ROOT", str(tmp_path))
    namespace: dict[str, object] = {"__name__": "__source_002_notebook_smoke__"}
    for cell in notebook["cells"]:
        if cell.get("cell_type") != "code":
            continue
        cell_source = "".join(cell.get("source", []))
        exec(compile(cell_source, str(notebook_path), "exec"), namespace)

    proposal_output_dir = Path(namespace["proposal_output_dir"])  # type: ignore[arg-type]
    assert (proposal_output_dir / "proposal_manifest.json").exists()
    assert (proposal_output_dir / "proposed_parameter_records.yml").exists()


def _data_registry_snapshot() -> dict[str, str]:
    return {
        str(path.relative_to(DATA_REGISTRY)): path.read_text(encoding="utf-8")
        for path in sorted(DATA_REGISTRY.rglob("*"))
        if path.is_file()
    }
