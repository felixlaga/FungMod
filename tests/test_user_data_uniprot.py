"""Enzyme repertoire from a UniProt proteome export in user data (USERDATA-007).

The fixture ``tests/fixtures/user_data/uniprot_case/`` holds a hand-written
UniProtKB TSV export in UniProt's column format (a format fixture with
synthetic accessions; not a real proteome). These tests pin that the route
resolves CAZy cross-references through the existing family map and EC numbers
through the registry's EC lookup, reports a protein whose two annotations
disagree without choosing, adds only classes with a registry record, takes no
rate from the proteome, and turns every resolved class without kinetics into
explicit gaps whose measurement requests name the proteome and accessions.
The fetch client is tested with a patched ``urllib.request.urlopen`` only;
every test runs with ``urlopen`` patched to fail.
"""

from __future__ import annotations

import csv
import email.message
import hashlib
import inspect
import io
import itertools
import json
import os
import shutil
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from fungal_model import UserDataError, UserDataset, load_user_dataset, virtual_experiment
from fungal_model.api import VirtualExperimentError
from fungal_model.api.user_data import GENOME_TABLE, UNIPROT_SOURCE_TYPE, USER_DATASET_MATURITY_GAP
from fungal_model.capability import (
    DIAGNOSTIC,
    POLYSPECIFIC,
    CapabilityResolutionError,
    CapabilityResolver,
    CazymeFamilyMap,
    decode_uniprot_tsv,
    parse_uniprot_tsv,
    resolve_uniprot_proteome,
)
from fungal_model.provenance import USER_DATASET_PROVENANCE_KEY
from fungal_model.registry import FungModRegistry, load_registry
from fungal_model.registry.loaders import load_parameter_record_mapping, load_registry_record_mapping
from fungal_model.registry.records import (
    PARAMETER_ALLOWED_USE_GAP_ANALYSIS_ONLY,
    EnzymeClassRecord,
    ParameterRecord,
    parameter_record_mode_eligibility_blocker,
)
from fungal_model.sources import uniprot as uniprot_source
from fungal_model.sources.uniprot import (
    SNAPSHOT_METADATA_FILENAME,
    SNAPSHOT_TSV_FILENAME,
    UniprotFetchError,
    build_stream_url,
    fetch_proteome_snapshot,
    load_proteome_snapshot,
    organism_query,
    proteome_query,
    write_snapshot_to_user_dataset,
)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"
FIXTURES = ROOT / "tests" / "fixtures" / "user_data"
UNIPROT = FIXTURES / "uniprot_case"
GENOME = FIXTURES / "genome_case"
ANNOTATION = "annotations/strain_u1_uniprot.tsv"

DATASET_ID = "uniprot_demo"
FUNGUS = "uniprot_demo__strain_u1"
STRAIN_NAME = "Proteome-annotated strain U1"
BGL = "uniprot_demo__beta_glucosidase"
# USERDATA-008: the registry has a cellobiohydrolase record (EC 3.2.1.91), so X0TEST05 now supports it.
CBH = "uniprot_demo__cellobiohydrolase"
CELLULASE = "uniprot_demo__cellulase_generic"
# REGISTRY-002: the registry has a glucoamylase record (EC 3.2.1.3), so X0TEST09 (GH15, EC 3.2.1.3) now supports it.
GLUCOAMYLASE = "uniprot_demo__glucoamylase"
BGL_PREFIX = "uniprot_demo__strain_u1__beta_glucosidase__cellobiose__c30_ph5__"
SOURCE = (
    "FungMod UniProt-route format fixture standing in for UniProt proteome UP000000000 (a placeholder id); "
    "synthetic accessions, not a real proteome"
)
TOOL = "UniProt format fixture (hand-written; no UniProt release)"
KINETICS_SOURCE = "FungMod UniProt-route fixture; illustrative values, not measurements"
BGL_NOTE = (
    "; the class was inferred from UniProt proteome UP000000000 (accessions X0TEST01, X0TEST02, X0TEST03; CAZy "
    "families GH1, GH3; EC 3.2.1.21; 1 of 3 reviewed in Swiss-Prot; family membership is polyspecific, so the "
    "activity itself needs confirming)."
)
GLUCOAMYLASE_NOTE = (
    "; the class was inferred from UniProt proteome UP000000000 (accessions X0TEST09; CAZy families GH15; "
    "EC 3.2.1.3; 0 of 1 reviewed in Swiss-Prot)."
)
GENOMES_HEADER = "strain_id,annotation_file,annotation_tool,source"
STREAM_URL = (
    "https://rest.uniprot.org/uniprotkb/stream?query=(proteome:UP000000000)"
    "&fields=accession,id,protein_name,gene_names,organism_name,organism_id,ec,xref_cazy,reviewed&format=tsv"
)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test runs with urlopen patched to fail; a fetch test patches in its own fake response."""

    def forbidden_urlopen(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("the UniProt route must not reach the network in tests")

    monkeypatch.setattr(urllib.request, "urlopen", forbidden_urlopen)


@pytest.fixture(scope="module")
def base_registry() -> FungModRegistry:
    return load_registry(REGISTRY_INDEX)


@pytest.fixture(scope="module")
def proteome(base_registry: FungModRegistry) -> UserDataset:
    return load_user_dataset(UNIPROT, registry=base_registry)


@pytest.fixture(scope="module")
def extended_registry(base_registry: FungModRegistry) -> FungModRegistry:
    """The shipped registry with its glucoamylase record widened in memory to the fixture's maltose class.

    REGISTRY-002 ships ``glucoamylase`` (EC 3.2.1.3, GH15) as categorical
    metadata acting on the solid starch class only. This test-only copy also
    lists the user-defined dissolved ``maltose`` class (not shipped, no
    kinetics), so the route is exercised on a class acting on a dissolved
    non-cellulose substrate, with CAZy and EC evidence agreeing; with the
    shipped record the class acts on no substrate of the fixture.
    """

    shipped = base_registry.enzyme_classes["glucoamylase"]
    widened = replace(
        shipped,
        maturity="exploratory_metadata",
        compatible_substrate_classes=(*shipped.compatible_substrate_classes, "maltose"),
        provenance={
            **shipped.provenance,
            "test_only_change": "maltose added in memory by tests/test_user_data_uniprot.py; not a shipped record",
        },
    )
    return FungModRegistry.build(
        registry_id=base_registry.registry_id,
        version=base_registry.version,
        maturity=base_registry.maturity,
        provenance=base_registry.provenance,
        fungi=base_registry.fungi.values(),
        enzyme_classes=(
            *(record for record in base_registry.enzyme_classes.values() if record.record_id != "glucoamylase"),
            widened,
        ),
        substrates=base_registry.substrates.values(),
        environments=base_registry.environments.values(),
        process_compatibility=base_registry.process_compatibility.values(),
        parameters=base_registry.parameters.values(),
        case_templates=base_registry.case_templates.values(),
        product_maps=base_registry.product_maps.values(),
    )


# ---------------------------------------------------------------------------
# Resolution: every protein kind of the fixture


def test_classes_with_a_record_join_the_strain_with_the_accessions_behind_them(proteome: UserDataset) -> None:
    fungus = _records(proteome, "fungi")[FUNGUS]
    assert fungus["enzyme_classes"] == [BGL, CBH, CELLULASE, GLUCOAMYLASE]

    evidence = fungus["provenance"]["enzyme_class_evidence"][BGL]
    assert evidence["evidence"] == "UniProt proteome UP000000000 (3 proteins, CAZy families GH1, GH3, EC 3.2.1.21)"
    assert (evidence["file"], evidence["row"], evidence["declared_by"]) == (GENOME_TABLE, 2, GENOME_TABLE)
    annotation = evidence["genome_annotation"]
    assert annotation["source_type"] == UNIPROT_SOURCE_TYPE
    assert annotation["proteome_id"] == "UP000000000"
    assert annotation["organism_id"] == "0"
    assert annotation["annotation_tool"] == "UniProt"
    assert annotation["annotation_tool_version"] == "format fixture (hand-written; no UniProt release)"
    assert annotation["annotation_sha256"] == proteome.file_digests[ANNOTATION]
    assert annotation["accessions"] == ["X0TEST01", "X0TEST02", "X0TEST03"]
    # One protein with agreeing CAZy and EC annotations, one CAZy-only row, one EC-only row.
    assert annotation["accessions_by_basis"] == {"cazy_and_ec": ["X0TEST01"], "cazy": ["X0TEST02"], "ec": ["X0TEST03"]}
    assert annotation["reviewed_accessions"] == ["X0TEST01"]
    assert annotation["specificity"] == POLYSPECIFIC
    assert "not what it expresses" in annotation["claim_boundary"]
    assert "unreviewed" in annotation["claim_boundary"]

    resolved = {item["enzyme_class"]: item for item in proteome.genome_resolved_classes}
    assert set(resolved) == {"beta_glucosidase", "cellobiohydrolase", "cellulase_generic", "glucoamylase"}
    assert resolved["beta_glucosidase"]["source_type"] == UNIPROT_SOURCE_TYPE
    assert resolved["beta_glucosidase"]["accession_count"] == 3
    assert resolved["beta_glucosidase"]["ec_numbers"] == ["3.2.1.21"]
    assert resolved["beta_glucosidase"]["record_id"] == BGL
    # GH5 resolves to cellulase_generic; the protein's EC 3.2.1.4 resolves to no class and cannot be compared.
    assert resolved["cellulase_generic"]["accessions_by_basis"]["cazy"] == ["X0TEST06"]
    assert resolved["cellulase_generic"]["ec_numbers"] == []
    # GH7 and EC 3.2.1.91 both name the cellobiohydrolase record: the reviewed X0TEST05 agrees.
    assert resolved["cellobiohydrolase"]["accessions_by_basis"] == {"cazy_and_ec": ["X0TEST05"], "cazy": [], "ec": []}
    assert resolved["cellobiohydrolase"]["ec_numbers"] == ["3.2.1.91"]
    assert resolved["cellobiohydrolase"]["specificity"] == DIAGNOSTIC
    assert fungus["provenance"]["enzyme_class_evidence"][CBH]["evidence"] == (
        "UniProt proteome UP000000000 (1 protein, CAZy families GH7, EC 3.2.1.91)"
    )
    # REGISTRY-002: GH15 and EC 3.2.1.3 both name the glucoamylase record: X0TEST09 agrees.
    assert resolved["glucoamylase"]["accessions_by_basis"] == {"cazy_and_ec": ["X0TEST09"], "cazy": [], "ec": []}
    assert resolved["glucoamylase"]["ec_numbers"] == ["3.2.1.3"]
    assert resolved["glucoamylase"]["specificity"] == DIAGNOSTIC
    assert fungus["provenance"]["enzyme_class_evidence"][GLUCOAMYLASE]["evidence"] == (
        "UniProt proteome UP000000000 (1 protein, CAZy families GH15, EC 3.2.1.3)"
    )


def test_annotation_entry_reports_columns_counts_and_every_ec_outcome(proteome: UserDataset) -> None:
    (read,) = proteome.genome_annotations
    assert read["source_type"] == UNIPROT_SOURCE_TYPE
    assert read["annotation_file"] == ANNOTATION
    assert read["organism"] == "Synthetic format-fixture organism"
    assert read["ignored_columns"] == ["Length"]
    assert "Reviewed" in read["read_columns"]
    # REGISTRY-002: the fixture gains X0TEST13 (AA1, EC 1.10.3.2), whose laccase class has no registry record.
    assert read["entry_rows"] == 13
    assert read["review_counts"] == {"reviewed": 2, "unreviewed": 11, "not_stated": 0}
    # USERDATA-008: X0TEST05 (GH7, EC 3.2.1.91) moved from CAZy-only to agreeing CAZy and EC evidence;
    # REGISTRY-002: X0TEST09 (GH15, EC 3.2.1.3) too, and X0TEST13 is CAZy-only.
    assert read["protein_counts"] == {"cazy_and_ec": 3, "cazy": 3, "ec": 1, "disagreement": 2, "no_class": 3}
    assert read["family_map"]["sources"] == list(CazymeFamilyMap.load().sources)
    assert read["ec_comparable_classes"] == [
        "beta_glucosidase",
        "cellobiohydrolase",
        "chitinase",
        "endo_xylanase",
        "glucoamylase",
    ]

    unresolved = {item["ec_number"]: item for item in read["unresolved_ec_numbers"]}
    assert set(unresolved) == {"1.10.3.2", "3.1.1.73", "3.2.1.37", "3.2.1.4"}
    assert unresolved["1.10.3.2"]["accessions"] == ["X0TEST13"]
    assert unresolved["3.2.1.4"]["accessions"] == ["X0TEST06"]
    assert all(item["reason"] == "no registry enzyme class carries this EC number" for item in unresolved.values())
    # A partial EC number is kept as written and never resolved, also beside a complete one.
    assert read["partial_ec_numbers"] == [
        {"ec_number": "3.2.1.-", "accessions": ["X0TEST07", "X0TEST11"], "accession_count": 2}
    ]


def test_disagreeing_proteins_are_reported_with_both_sides_and_support_no_class(proteome: UserDataset) -> None:
    (read,) = proteome.genome_annotations
    disagreements = {item["accession"]: item for item in read["ec_cazy_disagreements"]}
    assert set(disagreements) == {"X0TEST04", "X0TEST10"}

    # GH7 names cellobiohydrolase, EC 3.2.1.21 names beta_glucosidase.
    gh7 = disagreements["X0TEST04"]
    assert (gh7["cazy_families"], gh7["cazy_classes"]) == (["CBM1", "GH7"], ["cellobiohydrolase"])
    assert (gh7["ec_numbers"], gh7["ec_classes"]) == (["3.2.1.21"], ["beta_glucosidase"])
    # Both classes carry a registry EC number now, so both are contested (USERDATA-008).
    assert gh7["contested_classes"] == ["beta_glucosidase", "cellobiohydrolase"]
    # GH3 names beta_glucosidase, whose registry record carries an EC number the protein's EC does not match.
    gh3 = disagreements["X0TEST10"]
    assert (gh3["cazy_classes"], gh3["ec_numbers"], gh3["ec_classes"]) == (["beta_glucosidase"], ["3.2.1.37"], [])
    assert "neither is chosen" in gh3["outcome"]

    supporting = {accession for item in proteome.genome_resolved_classes for accession in item["accessions"]}
    supporting |= {accession for item in proteome.unmodellable_enzyme_classes for accession in item["accessions"]}
    assert not supporting & set(disagreements)


def test_classes_without_a_registry_record_are_listed_not_fabricated(
    proteome: UserDataset,
    base_registry: FungModRegistry,
) -> None:
    unmodellable = {item["enzyme_class"]: item for item in proteome.unmodellable_enzyme_classes}
    # USERDATA-008 (cellobiohydrolase) and REGISTRY-002 (glucoamylase): these classes have registry records now
    # and are no longer listed here; the fixture's X0TEST13 (AA1) names laccase, which still has none.
    assert set(unmodellable) == {"laccase"}
    assert unmodellable["laccase"]["accessions"] == ["X0TEST13"]
    assert unmodellable["laccase"]["specificity"] == POLYSPECIFIC
    assert unmodellable["laccase"]["families"] == ["AA1"]
    assert all(item["source_type"] == UNIPROT_SOURCE_TYPE for item in unmodellable.values())
    assert all("from a proteome annotation" in item["reason"] for item in unmodellable.values())

    generated = json.dumps(proteome.to_dict()["records"])
    overlaid = proteome.overlay(base_registry)
    for enzyme_class in unmodellable:
        assert f"{DATASET_ID}__{enzyme_class}" not in generated
        assert not any(record_id.endswith(enzyme_class) for record_id in overlaid.enzyme_classes)
    assert proteome.summary()["record_counts"]["enzyme_classes"] == 4


def test_unmapped_families_are_listed_with_their_accessions(proteome: UserDataset) -> None:
    unmapped = {item["family"]: item for item in proteome.unmapped_families}
    assert set(unmapped) == {"CBM1", "GT2"}
    assert unmapped["CBM1"]["accessions"] == ["X0TEST04", "X0TEST05"]
    assert unmapped["GT2"]["accession_count"] == 1
    assert unmapped["GT2"]["source_type"] == UNIPROT_SOURCE_TYPE
    assert "assigns no enzyme class" in unmapped["GT2"]["reason"]


def test_gap_records_name_the_proteome_and_accessions(proteome: UserDataset) -> None:
    parameters = [load_parameter_record_mapping(mapping) for mapping in proteome.records["parameter_records"]]
    assert {record.record_id for record in parameters} == {
        f"{BGL_PREFIX}{quantity}__gap"
        for quantity in ("km", "kcat", "substrate_initial_concentration", "enzyme_concentration")
    }
    for record in parameters:
        assert record.maturity == USER_DATASET_MATURITY_GAP
        assert record.allowed_use == PARAMETER_ALLOWED_USE_GAP_ANALYSIS_ONLY
        assert record.value.is_unknown
        assert record.provenance["measurement_request"].endswith(BGL_NOTE)
        user = record.provenance[USER_DATASET_PROVENANCE_KEY]
        assert user["class_evidence"] == "genome_annotation"
        assert user["genome_annotation"]["source_type"] == UNIPROT_SOURCE_TYPE
        assert user["genome_annotation"]["accessions"] == ["X0TEST01", "X0TEST02", "X0TEST03"]

    km = _parameter(proteome, f"{BGL_PREFIX}km__gap")
    assert km.provenance["measurement_request"] == (
        f"Measure km of beta-glucosidase from {STRAIN_NAME} on Cellobiose at 30 degC, pH 5.0 "
        f"(concentration units){BGL_NOTE}"
    )


def test_preflight_is_underparameterized_and_simulation_is_refused(proteome: UserDataset, tmp_path: Path) -> None:
    study = virtual_experiment(fungi=STRAIN_NAME, substrates="cellobiose", environments="c30_ph5", user_data=proteome)
    for mode in ("exploratory", "scientific"):
        report = study.preflight(mode=mode)[0]
        assert report.status == "underparameterized"
        assert all(text.endswith(BGL_NOTE) for text in report.suggested_experiments)
    for mapping in proteome.records["parameter_records"]:
        assert parameter_record_mode_eligibility_blocker(load_parameter_record_mapping(mapping), mode="scientific")
    with pytest.raises(VirtualExperimentError, match="Scientific simulation requires exact"):
        study.simulate(mode="scientific", output_dir=tmp_path / "scientific", quicklook=False)
    with pytest.raises(VirtualExperimentError, match="only modelable or exploratory"):
        study.simulate(mode="exploratory", output_dir=tmp_path / "exploratory", quicklook=False)

    written = study.write_preflight_report(mode="exploratory", output_dir=tmp_path / "preflight")
    resolution = json.loads(Path(written.paths["user_dataset_genome_resolution"]).read_text(encoding="utf-8"))
    assert resolution["user_dataset_digest"] == proteome.digest
    (annotation,) = resolution["genome_annotations"]
    assert annotation["source_type"] == UNIPROT_SOURCE_TYPE
    assert {item["accession"] for item in annotation["ec_cazy_disagreements"]} == {"X0TEST04", "X0TEST10"}
    assert {item["enzyme_class"]: item["accessions"] for item in resolution["unmodellable_enzyme_classes"]} == {
        "laccase": ["X0TEST13"],
    }
    assert all(item["source_type"] == UNIPROT_SOURCE_TYPE for item in resolution["genome_resolved_classes"])
    assert {item["family"] for item in resolution["unmapped_families"]} == {"CBM1", "GT2"}


def test_user_kinetics_estimates_make_the_proteome_class_run_in_exploratory_mode(
    base_registry: FungModRegistry,
    tmp_path: Path,
) -> None:
    case = "strain_u1,beta_glucosidase,cellobiose,c30_ph5"
    kinetics = (UNIPROT / "kinetics.csv").read_text(encoding="utf-8") + "".join(
        f'{case},{quantity},{value},,,{units},estimate,,"{KINETICS_SOURCE}",,\n'
        for quantity, value, units in (
            ("km", "15", "mM"),
            ("kcat", "0.1", "1/s"),
            ("substrate_initial_concentration", "10", "mM"),
            ("enzyme_concentration", "0.001", "mM"),
        )
    )
    dataset = load_user_dataset(_copy(tmp_path, UNIPROT, {"kinetics.csv": kinetics}), registry=base_registry)
    assert "inferred from" not in json.dumps(_parameter(dataset, f"{BGL_PREFIX}kcat").provenance)

    study = virtual_experiment(fungi="strain_u1", substrates="cellobiose", environments="c30_ph5", user_data=dataset)
    assert study.preflight(mode="exploratory")[0].status == "modelable"
    assert study.preflight(mode="scientific")[0].status != "modelable"
    result = study.simulate(mode="exploratory", n_samples=2, seed=5, output_dir=tmp_path / "run", quicklook=False)
    rows = result.time_series()
    for sample_id in {row["sample_id"] for row in rows}:
        substrate = [float(r["value"]) for r in rows if r["sample_id"] == sample_id and r["state_role"] == "substrate"]
        product = [float(r["value"]) for r in rows if r["sample_id"] == sample_id and r["state_role"] == "product"]
        assert substrate[0] == pytest.approx(10.0)
        assert substrate[-1] < substrate[0]
        assert all(later <= earlier + 1e-12 for earlier, later in itertools.pairwise(substrate))
        assert product[-1] == pytest.approx(2.0 * (substrate[0] - substrate[-1]), rel=1e-6)
    summary = json.loads((Path(result.output_directory) / "virtual_experiment_summary.json").read_text())
    assert summary["experiment"]["user_dataset_digest"] == dataset.digest
    assert {item["source_type"] for item in summary["experiment"]["genome_resolved_classes"]} == {UNIPROT_SOURCE_TYPE}


def test_explicit_enzymes_row_wins_and_keeps_the_proteome_evidence(tmp_path: Path) -> None:
    enzymes = "strain_id,enzyme_class,evidence,source\nstrain_u1,EC 3.2.1.21,activity assay on cellobiose,LN-9 p. 2\n"
    dataset = _load(tmp_path, {"enzymes.csv": enzymes})

    evidence = _records(dataset, "fungi")[FUNGUS]["provenance"]["enzyme_class_evidence"][BGL]
    assert (evidence["evidence"], evidence["file"], evidence["declared_by"]) == (
        "activity assay on cellobiose",
        "enzymes.csv",
        "enzymes.csv",
    )
    assert evidence["genome_annotation"]["source_type"] == UNIPROT_SOURCE_TYPE
    resolved = {item["enzyme_class"]: item for item in dataset.genome_resolved_classes}
    assert (resolved["beta_glucosidase"]["declared_by"], resolved["beta_glucosidase"]["enzymes_row"]) == (
        "enzymes.csv",
        2,
    )
    assert "inferred from" not in _parameter(dataset, f"{BGL_PREFIX}km__gap").provenance["measurement_request"]


# ---------------------------------------------------------------------------
# A non-cellulose class (shipped record widened in memory), exports with one evidence column


def test_a_proteome_class_on_a_non_cellulose_substrate_follows_the_base_registry(
    proteome: UserDataset,
    extended_registry: FungModRegistry,
) -> None:
    gap_id = "uniprot_demo__strain_u1__glucoamylase__maltose__c30_ph5__km__gap"
    # With the shipped record (solid starch only) the class joins the strain but acts on no fixture substrate.
    assert _records(proteome, "fungi")[FUNGUS]["enzyme_classes"] == [BGL, CBH, CELLULASE, GLUCOAMYLASE]
    assert gap_id not in _records(proteome, "parameter_records")

    dataset = load_user_dataset(UNIPROT, registry=extended_registry)

    assert _records(dataset, "fungi")[FUNGUS]["enzyme_classes"] == [BGL, CBH, CELLULASE, GLUCOAMYLASE]
    resolved = {item["enzyme_class"]: item for item in dataset.genome_resolved_classes}
    # With an EC number on the class, GH15 and EC 3.2.1.3 of X0TEST09 agree.
    assert resolved["glucoamylase"]["accessions_by_basis"]["cazy_and_ec"] == ["X0TEST09"]
    assert "glucoamylase" not in {item["enzyme_class"] for item in dataset.unmodellable_enzyme_classes}
    (read,) = dataset.genome_annotations
    assert "3.2.1.3" not in {item["ec_number"] for item in read["unresolved_ec_numbers"]}
    assert read["ec_comparable_classes"] == [
        "beta_glucosidase",
        "cellobiohydrolase",
        "chitinase",
        "endo_xylanase",
        "glucoamylase",
    ]

    gap = _parameter(dataset, gap_id)
    assert gap.substrate_id == "uniprot_demo__maltose"
    assert gap.provenance["measurement_request"] == (
        f"Measure km of Glucoamylase from {STRAIN_NAME} on maltose at 30 degC, pH 5.0 "
        f"(concentration units){GLUCOAMYLASE_NOTE}"
    )
    report = virtual_experiment(
        fungi="strain_u1", substrates="maltose", environments="c30_ph5", registry=extended_registry, user_data=dataset
    ).preflight(mode="exploratory")[0]
    assert report.status == "underparameterized"
    assert all(text.endswith(GLUCOAMYLASE_NOTE) for text in report.suggested_experiments)


def test_an_ec_only_export_without_a_proteome_id_or_review_column(tmp_path: Path) -> None:
    tsv = "Entry\tEC number\nX0TEST01\t3.2.1.21\nX0TEST02\t3.2.1.-\nX0TEST03\t3.2.1.4; 3.2.1.21\n"
    row = f'{GENOMES_HEADER}\nstrain_u1,{ANNOTATION},UniProt downloaded 2026-10-06,"hand-written EC-only export"\n'
    dataset = _load(tmp_path, {ANNOTATION: tsv, GENOME_TABLE: row})

    (resolved,) = [item for item in dataset.genome_resolved_classes if item["enzyme_class"] == "beta_glucosidase"]
    assert resolved["accessions_by_basis"] == {"cazy_and_ec": [], "cazy": [], "ec": ["X0TEST01", "X0TEST03"]}
    assert resolved["specificity"] is None
    (read,) = dataset.genome_annotations
    assert read["proteome_id"] is None
    assert read["review_counts"] == {"reviewed": 0, "unreviewed": 0, "not_stated": 3}
    assert read["annotation_tool_version"] == "downloaded 2026-10-06"
    assert _parameter(dataset, f"{BGL_PREFIX}km__gap").provenance["measurement_request"].endswith(
        f"; the class was inferred from UniProt export {ANNOTATION} (accessions X0TEST01, X0TEST03; EC 3.2.1.21; "
        "review status not in the export)."
    )


def test_a_cazy_only_export(tmp_path: Path) -> None:
    tsv = "Entry\tCAZy\tReviewed\nX0TEST01\tGH3;\tunreviewed\nX0TEST02\tGH5_5;CBM1;\treviewed\n"
    dataset = _load(tmp_path, {ANNOTATION: tsv})

    resolved = {item["enzyme_class"]: item for item in dataset.genome_resolved_classes}
    assert resolved["beta_glucosidase"]["accessions_by_basis"]["cazy"] == ["X0TEST01"]
    # The subfamily suffix is dropped: GH5_5 counts as GH5.
    assert resolved["cellulase_generic"]["families"] == ["GH5"]
    assert dataset.genome_annotations[0]["ec_cazy_disagreements"] == []


def test_dbcan_and_uniprot_rows_coexist_and_dbcan_entries_keep_their_keys(tmp_path: Path) -> None:
    target = _copy(tmp_path, GENOME, {})
    (target / ANNOTATION).write_bytes((UNIPROT / ANNOTATION).read_bytes())
    strains = (GENOME / "strains.csv").read_text(encoding="utf-8") + "strain_u1,Proteome-annotated strain U1,,\n"
    genomes = (GENOME / GENOME_TABLE).read_text(encoding="utf-8") + f'strain_u1,{ANNOTATION},{TOOL},"{SOURCE}"\n'
    (target / "strains.csv").write_text(strains, encoding="utf-8")
    (target / GENOME_TABLE).write_text(genomes, encoding="utf-8")
    dataset = load_user_dataset(target, registry=REGISTRY_INDEX)

    dbcan, uniprot = dataset.genome_annotations
    assert set(dbcan) == DBCAN_ANNOTATION_KEYS
    assert uniprot["source_type"] == UNIPROT_SOURCE_TYPE
    for name, keys in (
        ("genome_resolved_classes", DBCAN_RESOLVED_KEYS),
        ("unmodellable_enzyme_classes", DBCAN_UNMODELLABLE_KEYS),
        ("unmapped_families", DBCAN_UNMAPPED_KEYS),
    ):
        entries = getattr(dataset, name)
        assert {item["strain_id"] for item in entries} == {"strain_g1", "strain_u1"}, name
        assert all(set(item) == keys for item in entries if item["strain_id"] == "strain_g1"), name
        assert all(item["source_type"] == UNIPROT_SOURCE_TYPE for item in entries if item["strain_id"] == "strain_u1")


def test_the_dbcan_route_is_unchanged(base_registry: FungModRegistry) -> None:
    genome = load_user_dataset(GENOME, registry=base_registry)
    (read,) = genome.genome_annotations
    assert set(read) == DBCAN_ANNOTATION_KEYS
    assert all(set(item) == DBCAN_RESOLVED_KEYS for item in genome.genome_resolved_classes)
    assert all(set(item) == DBCAN_UNMODELLABLE_KEYS for item in genome.unmodellable_enzyme_classes)
    assert all(set(item) == DBCAN_UNMAPPED_KEYS for item in genome.unmapped_families)
    assert "source_type" not in json.dumps(genome.to_dict())
    km = _parameter(genome, "genome_demo__strain_g1__beta_glucosidase__cellobiose__c30_ph5__km__gap")
    assert set(km.provenance[USER_DATASET_PROVENANCE_KEY]["genome_annotation"]) == DBCAN_EVIDENCE_KEYS
    assert km.provenance["measurement_request"].endswith(
        "; the class was inferred from the dbCAN annotation (families GH1, GH3; family membership is polyspecific, "
        "so the activity itself needs confirming)."
    )


# ---------------------------------------------------------------------------
# Refusals in genomes.csv


def _genomes_row(*, path: str = ANNOTATION, tool: str = TOOL, source: str = SOURCE, extra: str = "") -> str:
    header = GENOMES_HEADER + (",min_tools_agreeing" if extra else "")
    row = f'strain_u1,{path},{tool},"{source}"' + (f",{extra}" if extra else "")
    return f"{header}\n{row}\n"


def _tsv_lines() -> list[str]:
    return (UNIPROT / ANNOTATION).read_text(encoding="utf-8").splitlines(keepends=True)


REFUSALS: dict[str, tuple[dict[str, str], tuple[str, int | None, str | None, str]]] = {
    "absolute_path": (
        {GENOME_TABLE: _genomes_row(path=str((UNIPROT / ANNOTATION).resolve()))},
        (GENOME_TABLE, 2, "annotation_file", "is an absolute path"),
    ),
    "escaping_path": (
        {GENOME_TABLE: _genomes_row(path=f"../{UNIPROT.name}/{ANNOTATION}")},
        (GENOME_TABLE, 2, "annotation_file", "leaves the dataset directory"),
    ),
    "missing_file": (
        {GENOME_TABLE: _genomes_row(path="annotations/absent.tsv")},
        (GENOME_TABLE, 2, "annotation_file", "does not exist in the dataset directory"),
    ),
    "missing_version": (
        {GENOME_TABLE: _genomes_row(tool="UniProt")},
        (GENOME_TABLE, 2, "annotation_tool", "names UniProt without a version"),
    ),
    "min_tools_agreeing": (
        {GENOME_TABLE: _genomes_row(extra="2")},
        (GENOME_TABLE, 2, "min_tools_agreeing", "a UniProt export has none"),
    ),
    "two_proteome_ids_in_source": (
        {GENOME_TABLE: _genomes_row(source="UniProt proteomes UP000000000 and UP000000001")},
        (GENOME_TABLE, 2, "source", "several UniProt proteome identifiers"),
    ),
    "mixed_organisms": (
        {ANNOTATION: "".join(_tsv_lines()[:3]) + _tsv_lines()[3].replace("\t0\t", "\t1\t")},
        (GENOME_TABLE, 2, "annotation_file", "mixed sets are not supported"),
    ),
    "duplicate_accession": (
        {ANNOTATION: "".join(_tsv_lines()[:3]) + _tsv_lines()[1]},
        (GENOME_TABLE, 2, "annotation_file", "repeats accession 'X0TEST01'"),
    ),
    "missing_entry_column": (
        {ANNOTATION: "Accession\tEC number\nX0TEST01\t3.2.1.21\n"},
        (GENOME_TABLE, 2, "annotation_file", "needs the column 'Entry'"),
    ),
    "a_dbcan_overview_under_a_uniprot_row": (
        {ANNOTATION: (GENOME / "annotations" / "strain_g1_overview.txt").read_text(encoding="utf-8")},
        (GENOME_TABLE, 2, "annotation_file", "does not have a UniProt TSV header"),
    ),
}


@pytest.mark.parametrize("case", sorted(REFUSALS))
def test_invalid_uniprot_rows_are_refused_with_file_row_and_column(tmp_path: Path, case: str) -> None:
    edits, (file, row, column, message) = REFUSALS[case]
    issues = _issues(tmp_path, edits)
    assert _has_issue(issues, file, row, column, message), issues


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symbolic links are not available")
def test_export_reached_through_a_symbolic_link_outside_the_directory_is_refused(tmp_path: Path) -> None:
    outside = tmp_path / "outside.tsv"
    shutil.copyfile(UNIPROT / ANNOTATION, outside)
    dataset_dir = _copy(tmp_path, UNIPROT, {})
    try:
        (dataset_dir / "annotations" / "linked.tsv").symlink_to(outside)
    except OSError as exc:  # pragma: no cover - platforms without symlink permission
        pytest.skip(f"cannot create a symbolic link: {exc}")
    (dataset_dir / GENOME_TABLE).write_text(_genomes_row(path="annotations/linked.tsv"), encoding="utf-8")

    with pytest.raises(UserDataError) as excinfo:
        load_user_dataset(dataset_dir, registry=REGISTRY_INDEX)
    assert _has_issue(excinfo.value.issues, GENOME_TABLE, 2, "annotation_file", "resolves outside the dataset directory")


def test_strain_whose_proteome_resolves_no_registry_class_is_refused(tmp_path: Path) -> None:
    lines = _tsv_lines()
    # USERDATA-008 and REGISTRY-002: X0TEST05 (GH7) and X0TEST09 (GH15) resolve to registry records now, so the
    # export keeps X0TEST13 (AA1, EC 1.10.3.2), whose laccase class has no registry record.
    tsv = lines[0] + "".join(line for line in lines if line.startswith(("X0TEST04", "X0TEST13", "X0TEST07")))
    issues = _issues(tmp_path, {ANNOTATION: tsv})

    message = next(issue["message"] for issue in issues if issue["file"] == "strains.csv")
    assert "its UniProt export (genomes.csv row 2) resolved no enzyme class with a registry record" in message
    assert "laccase" in message
    assert "1.10.3.2" in message
    assert "disagree: X0TEST04" in message
    assert "FungMod does not create enzyme classes from a proteome" in message


def test_an_unknown_tool_is_refused_naming_both_supported_routes(tmp_path: Path) -> None:
    issues = _issues(tmp_path, {GENOME_TABLE: _genomes_row(tool="InterProScan 5.66")})
    assert _has_issue(issues, GENOME_TABLE, 2, "annotation_tool", "is not a supported annotation tool"), issues
    message = next(issue["message"] for issue in issues if issue["column"] == "annotation_tool")
    assert "dbCAN" in message and "UniProt" in message


# ---------------------------------------------------------------------------
# Determinism, digest, no rate


def test_loading_is_deterministic_and_the_digest_covers_the_export_bytes(
    proteome: UserDataset,
    tmp_path: Path,
) -> None:
    again = load_user_dataset(UNIPROT, registry=REGISTRY_INDEX)
    assert again.to_dict() == proteome.to_dict()
    assert again.digest == proteome.digest
    assert proteome.file_digests[ANNOTATION] == hashlib.sha256((UNIPROT / ANNOTATION).read_bytes()).hexdigest()

    # One byte of an ignored column changes the digest but not the resolution.
    changed = _load(tmp_path, {ANNOTATION: (UNIPROT / ANNOTATION).read_text(encoding="utf-8").replace("\t812\n", "\t813\n")})
    assert changed.digest != proteome.digest
    assert changed.file_digests[ANNOTATION] != proteome.file_digests[ANNOTATION]
    assert changed.genome_resolved_classes == proteome.genome_resolved_classes
    record = _parameter(changed, f"{BGL_PREFIX}km__gap")
    assert record.provenance[USER_DATASET_PROVENANCE_KEY]["digest"] == changed.digest


def test_the_proteome_route_takes_no_rate(proteome: UserDataset) -> None:
    for mapping in proteome.records["parameter_records"]:
        assert mapping["value"]["kind"] == "unknown"
    keys = {
        key.lower()
        for name in ("genome_annotations", "genome_resolved_classes", "unmodellable_enzyme_classes", "unmapped_families")
        for entry in proteome.to_dict()[name]
        for key in entry
    }
    for forbidden in ("kcat", "vmax", "km", "rate", "value", "units", "turnover", "activity", "expression"):
        assert not any(forbidden in key for key in keys), forbidden


# ---------------------------------------------------------------------------
# Parser and resolver


def test_parser_reads_uniprot_cell_formats_and_ignores_unknown_columns() -> None:
    text = (
        "Entry\tLength\tEC number\tCAZy\tReviewed\tOrganism (ID)\n"
        "X0TEST01\t100\t3.2.1.4; 3.2.1.91; 3.2.1.4\tGH5_5;CBM1;\treviewed\t0\n"
        "X0TEST02\t200\t3.2.1.-\t\tunreviewed\t\n"
        "X0TEST03\t300\t\t\t\t0\n"
    )
    proteome = parse_uniprot_tsv(text, source="fixture")
    first, second, third = proteome.entries
    assert first.ec_numbers == ("3.2.1.4", "3.2.1.91")
    assert first.cazy_families == ("CBM1", "GH5")
    assert (second.ec_numbers, second.partial_ec_numbers) == ((), ("3.2.1.-",))
    assert (third.reviewed, third.has_evidence) == ("not_stated", False)
    assert proteome.ignored_columns == ("Length",)
    assert proteome.organism_id == "0"
    assert proteome.partial_ec_accessions() == {"3.2.1.-": ("X0TEST02",)}


PARSER_REFUSALS = {
    "no header": ("", "has no header row"),
    "missing entry": ("Entry Name\tEC number\nSYN\t3.2.1.4\n", "needs the column 'Entry'"),
    "no evidence column": ("Entry\tOrganism\nX0TEST01\tx\n", "neither the 'EC number' nor the 'CAZy' column"),
    "repeated header": ("Entry\tCAZy\tCAZy\nX0TEST01\tGH3;\tGH3;\n", "repeats the header column"),
    "duplicate accession": ("Entry\tCAZy\nX0TEST01\tGH3;\nX0TEST01\tGH1;\n", "repeats accession 'X0TEST01'"),
    "blank accession": ("Entry\tCAZy\n\tGH3;\n", "has no accession"),
    "wider row": ("Entry\tCAZy\nX0TEST01\tGH3;\textra\n", "more cells than the header"),
    "malformed EC": ("Entry\tEC number\nX0TEST01\t3.2.1\n", "is not an EC number"),
    "comma-separated EC": ("Entry\tEC number\nX0TEST01\t3.2.1.4, 3.2.1.91\n", "is not an EC number"),
    "malformed CAZy": ("Entry\tCAZy\nX0TEST01\tGH7 (glycoside hydrolase family 7)\n", "is not a CAZy identifier"),
    "reviewed value": ("Entry\tCAZy\tReviewed\nX0TEST01\tGH3;\tyes\n", "UniProt writes 'reviewed'"),
    "taxonomy id": ("Entry\tCAZy\tOrganism (ID)\nX0TEST01\tGH3;\tNCBI:0\n", "not an NCBI taxonomy id"),
    "mixed organism ids": (
        "Entry\tCAZy\tOrganism (ID)\nX0TEST01\tGH3;\t0\nX0TEST02\tGH1;\t1\n",
        "mixed sets are not supported",
    ),
    "mixed organism names": (
        "Entry\tCAZy\tOrganism\nX0TEST01\tGH3;\tOrganism A\nX0TEST02\tGH1;\tOrganism B\n",
        "mixed sets are not supported",
    ),
    "nothing to resolve": ("Entry\tEC number\tCAZy\nX0TEST01\t\t\n", "has no entry with an EC number or a CAZy family"),
}


@pytest.mark.parametrize("case", sorted(PARSER_REFUSALS))
def test_parser_refusals(case: str) -> None:
    text, message = PARSER_REFUSALS[case]
    with pytest.raises(CapabilityResolutionError, match=message.replace("(", r"\(").replace(")", r"\)")):
        parse_uniprot_tsv(text, source="fixture")


def test_compressed_or_non_utf8_exports_are_refused() -> None:
    with pytest.raises(CapabilityResolutionError, match="gzip-compressed"):
        decode_uniprot_tsv(b"\x1f\x8b\x08\x00rest", source="fixture")
    with pytest.raises(CapabilityResolutionError, match="not UTF-8"):
        decode_uniprot_tsv(b"Entry\tCAZy\n\xff\xfe\n", source="fixture")


def test_an_ec_number_ambiguous_in_the_registry_resolves_to_no_class(base_registry: FungModRegistry) -> None:
    """Two test-only classes carrying one EC number: the EC resolves to neither and FungMod does not choose."""

    registry = _registry_with(
        base_registry,
        {
            "record_id": "test_only_second_ec_holder",
            "name": "test-only second EC holder",
            "ec_number": "3.2.1.21",
            "maturity": "exploratory_metadata",
            "provenance": {"source": "tests/test_user_data_uniprot.py only", "confidence_level": "exploratory_assumption"},
            "target_bond_classes": ["test_only_bond"],
            "compatible_substrate_classes": ["test_only_substrate"],
            "compatible_processes": ["homogeneous_michaelis_menten"],
            "notes": "Exists only to make one EC number ambiguous.",
        },
    )
    resolution = resolve_uniprot_proteome(
        parse_uniprot_tsv("Entry\tEC number\nX0TEST01\t3.2.1.21\n", source="fixture"),
        capability_resolver=CapabilityResolver(
            family_map=CazymeFamilyMap.load(), registry_enzyme_classes=tuple(sorted(registry.enzyme_classes))
        ),
        registry=registry,
        organism="test organism",
        proteome_source="fixture",
        annotation_tool="UniProt",
        annotation_tool_version="fixture",
        annotation_date="not recorded",
    )
    assert resolution.capabilities == ()
    assert resolution.unresolved_ec_numbers == {"3.2.1.21": ("X0TEST01",)}
    reason = resolution.unresolved_ec_reasons["3.2.1.21"]
    assert "ambiguous" in reason and "beta_glucosidase" in reason and "test_only_second_ec_holder" in reason


# ---------------------------------------------------------------------------
# Fetch client (patched urlopen only)


class _FakeResponse:
    def __init__(self, body: bytes, *, status: int = 200, headers: Mapping[str, str] | None = None) -> None:
        self._body = body
        self._status = status
        self.headers = email.message.Message()
        for key, value in (headers or {}).items():
            self.headers[key] = value

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False

    def getcode(self) -> int:
        return self._status

    def read(self) -> bytes:
        return self._body


def _serve(monkeypatch: pytest.MonkeyPatch, body: bytes, **kwargs: Any) -> list[str]:
    requested: list[str] = []

    def fake_urlopen(request: urllib.request.Request, *, timeout: float) -> _FakeResponse:
        assert timeout > 0
        requested.append(request.full_url)
        return _FakeResponse(body, **kwargs)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return requested


RELEASE_HEADERS = {"X-UniProt-Release": "fixture_release", "X-UniProt-Release-Date": "06-October-2026"}


def test_stream_urls_are_built_from_a_proteome_or_taxonomy_id() -> None:
    assert build_stream_url(proteome_query("UP000000000")) == STREAM_URL
    assert organism_query(12345) == "(organism_id:12345)"
    assert build_stream_url(organism_query("12345")).startswith(
        "https://rest.uniprot.org/uniprotkb/stream?query=(organism_id:12345)&fields=accession,"
    )
    for bad in ("UP", "up000000000", "UP0000 1", "Trichoderma reesei"):
        with pytest.raises(UniprotFetchError, match="not a UniProt proteome identifier"):
            proteome_query(bad)
    for bad_id in ("0", "-5", "abc", True):
        with pytest.raises(UniprotFetchError, match="not an NCBI taxonomy id"):
            organism_query(bad_id)  # type: ignore[arg-type]
    with pytest.raises(UniprotFetchError, match="exactly one"):
        fetch_proteome_snapshot(proteome_id="UP000000000", taxonomy_id="12345", snapshot_dir="unused")


def test_without_refresh_a_missing_snapshot_is_refused_and_nothing_is_fetched(tmp_path: Path) -> None:
    with pytest.raises(UniprotFetchError, match="pass refresh=True"):
        fetch_proteome_snapshot(proteome_id="UP000000000", snapshot_dir=tmp_path)
    assert not any(tmp_path.iterdir())


def test_refresh_fetches_the_stream_url_and_stores_a_verified_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    body = (UNIPROT / ANNOTATION).read_bytes()
    requested = _serve(monkeypatch, body, headers=RELEASE_HEADERS)
    snapshot = fetch_proteome_snapshot(proteome_id="UP000000000", snapshot_dir=tmp_path, refresh=True)

    assert requested == [STREAM_URL]
    assert snapshot.directory == tmp_path / "proteome_UP000000000"
    assert snapshot.tsv_path == snapshot.directory / SNAPSHOT_TSV_FILENAME
    assert snapshot.read_bytes() == body
    assert snapshot.sha256 == hashlib.sha256(body).hexdigest()
    metadata = json.loads((snapshot.directory / SNAPSHOT_METADATA_FILENAME).read_text(encoding="utf-8"))
    assert metadata["url"] == STREAM_URL
    assert metadata["query"] == "(proteome:UP000000000)"
    assert metadata["uniprot_release"] == "fixture_release"
    assert metadata["uniprot_release_date"] == "06-October-2026"
    assert metadata["http_status"] == 200
    assert metadata["retrieved_at"].endswith("Z")
    assert metadata["entry_rows"] == 13  # REGISTRY-002 added X0TEST13 to the fixture export
    assert "not checked against a live response" in metadata["field_names_note"]

    # Later reads use the frozen snapshot, with urlopen failing again.
    monkeypatch.setattr(urllib.request, "urlopen", _forbidden)
    assert fetch_proteome_snapshot(proteome_id="UP000000000", snapshot_dir=tmp_path).metadata == metadata


def test_a_snapshot_with_a_different_digest_is_kept_unless_overwrite(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    body = (UNIPROT / ANNOTATION).read_bytes()
    _serve(monkeypatch, body)
    first = fetch_proteome_snapshot(proteome_id="UP000000000", snapshot_dir=tmp_path, refresh=True)

    # The same bytes again: the stored snapshot is returned unchanged.
    assert fetch_proteome_snapshot(proteome_id="UP000000000", snapshot_dir=tmp_path, refresh=True).metadata == (
        first.metadata
    )

    shorter = b"".join(body.splitlines(keepends=True)[:4])
    _serve(monkeypatch, shorter)
    with pytest.raises(UniprotFetchError, match="pass overwrite=True"):
        fetch_proteome_snapshot(proteome_id="UP000000000", snapshot_dir=tmp_path, refresh=True)
    assert first.tsv_path.read_bytes() == body
    replaced = fetch_proteome_snapshot(proteome_id="UP000000000", snapshot_dir=tmp_path, refresh=True, overwrite=True)
    assert replaced.sha256 == hashlib.sha256(shorter).hexdigest() != first.sha256


def test_a_changed_snapshot_file_fails_its_digest_check(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _serve(monkeypatch, (UNIPROT / ANNOTATION).read_bytes())
    snapshot = fetch_proteome_snapshot(taxonomy_id=12345, snapshot_dir=tmp_path, refresh=True)
    assert snapshot.directory.name == "organism_id_12345"
    snapshot.tsv_path.write_bytes(snapshot.read_bytes().replace(b"GH3;", b"GH1;"))

    with pytest.raises(UniprotFetchError, match="changed after it was stored"):
        load_proteome_snapshot(snapshot.directory)
    with pytest.raises(UniprotFetchError, match="changed after it was stored"):
        fetch_proteome_snapshot(taxonomy_id=12345, snapshot_dir=tmp_path)


@pytest.mark.parametrize(
    ("body", "kwargs", "message"),
    [
        (b"<html>Service unavailable</html>\n", {}, "does not have a UniProt TSV header"),
        (b"Entry\tEntry Name\tEC number\tCAZy\n", {}, "has no entry with an EC number or a CAZy family"),
        (b"\x1f\x8b\x08\x00", {}, "gzip-compressed"),
        ((UNIPROT / ANNOTATION).read_bytes(), {"status": 204}, "HTTP 204"),
    ],
)
def test_unusable_responses_are_refused_and_nothing_is_stored(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    body: bytes,
    kwargs: dict[str, Any],
    message: str,
) -> None:
    _serve(monkeypatch, body, **kwargs)
    with pytest.raises(UniprotFetchError, match=message):
        fetch_proteome_snapshot(proteome_id="UP000000000", snapshot_dir=tmp_path, refresh=True)
    assert not any(tmp_path.iterdir())


def test_network_errors_become_fetch_errors(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def failing(request: urllib.request.Request, *, timeout: float) -> None:
        raise urllib.error.HTTPError(request.full_url, 503, "Service Unavailable", email.message.Message(), None)

    monkeypatch.setattr(urllib.request, "urlopen", failing)
    with pytest.raises(UniprotFetchError, match="HTTP 503"):
        fetch_proteome_snapshot(proteome_id="UP000000000", snapshot_dir=tmp_path, refresh=True)

    def unreachable(request: urllib.request.Request, *, timeout: float) -> None:
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr(urllib.request, "urlopen", unreachable)
    with pytest.raises(UniprotFetchError, match="could not be reached"):
        fetch_proteome_snapshot(proteome_id="UP000000000", snapshot_dir=tmp_path, refresh=True)
    assert not any(tmp_path.iterdir())


def test_a_fetched_snapshot_written_into_a_dataset_loads_with_the_suggested_row(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _serve(monkeypatch, (UNIPROT / ANNOTATION).read_bytes(), headers=RELEASE_HEADERS)
    snapshot = fetch_proteome_snapshot(proteome_id="UP000000000", snapshot_dir=tmp_path / "snapshots", refresh=True)
    monkeypatch.setattr(urllib.request, "urlopen", _forbidden)
    dataset_dir = _copy(tmp_path, UNIPROT, {ANNOTATION: None, GENOME_TABLE: None})

    row = write_snapshot_to_user_dataset(snapshot, dataset_dir, strain_id="strain_u1")
    assert row["annotation_file"] == "annotations/proteome_UP000000000.tsv"
    assert row["annotation_tool"] == "UniProt release fixture_release"
    assert (dataset_dir / row["annotation_file"]).read_bytes() == snapshot.read_bytes()
    assert not (dataset_dir / GENOME_TABLE).exists()

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(row), lineterminator="\n")
    writer.writeheader()
    writer.writerow(row)
    (dataset_dir / GENOME_TABLE).write_text(buffer.getvalue(), encoding="utf-8")
    dataset = load_user_dataset(dataset_dir, registry=REGISTRY_INDEX)
    (read,) = dataset.genome_annotations
    assert read["proteome_id"] == "UP000000000"
    assert read["annotation_tool_version"] == "release fixture_release"
    assert snapshot.sha256 in read["source"] and STREAM_URL in read["source"]
    assert read["annotation_sha256"] == snapshot.sha256
    assert {item["enzyme_class"] for item in dataset.genome_resolved_classes} == {
        "beta_glucosidase",
        "cellobiohydrolase",
        "cellulase_generic",
        "glucoamylase",
    }

    with pytest.raises(UniprotFetchError, match="different content"):
        (dataset_dir / row["annotation_file"]).write_bytes(b"Entry\tCAZy\nX0TEST01\tGH3;\n")
        write_snapshot_to_user_dataset(snapshot, dataset_dir, strain_id="strain_u1")
    assert write_snapshot_to_user_dataset(snapshot, dataset_dir, strain_id="strain_u1", overwrite=True) == row
    for bad in ("../outside.tsv", "/tmp/absolute.tsv", "annotations\\proteome.tsv"):
        with pytest.raises(UniprotFetchError, match="inside the dataset directory"):
            write_snapshot_to_user_dataset(snapshot, dataset_dir, strain_id="strain_u1", annotation_file=bad)


def test_the_fetch_client_is_complete_and_names_no_organism_lookup() -> None:
    for name in uniprot_source.__all__:
        candidate = getattr(uniprot_source, name)
        if callable(candidate) and not isinstance(candidate, type):
            source = inspect.getsource(candidate).lower()
            assert "notimplementederror" not in source and "todo" not in source, name
    assert "future work" in (uniprot_source.__doc__ or "")
    assert not hasattr(uniprot_source, "organism_name_query")


# ---------------------------------------------------------------------------
# Helpers

DBCAN_ANNOTATION_KEYS = {
    "strain_id",
    "file",
    "row",
    "annotation_file",
    "annotation_sha256",
    "annotation_tool",
    "annotation_tool_version",
    "source",
    "tool_columns",
    "min_tools_agreeing",
    "consensus_rule",
    "gene_rows",
    "family_gene_counts",
    "family_map",
    "claim_boundary",
}
DBCAN_RESOLVED_KEYS = {
    "strain_id",
    "enzyme_class",
    "families",
    "gene_count",
    "specificity",
    "genomes_row",
    "record_id",
    "declared_by",
    "enzymes_row",
    "evidence",
    "source",
}
DBCAN_UNMODELLABLE_KEYS = {"strain_id", "enzyme_class", "families", "gene_count", "specificity", "genomes_row", "reason"}
DBCAN_UNMAPPED_KEYS = {"strain_id", "family", "gene_count", "genomes_row", "reason"}
DBCAN_EVIDENCE_KEYS = {
    "file",
    "row",
    "evidence",
    "source",
    "annotation_file",
    "annotation_sha256",
    "annotation_tool",
    "annotation_tool_version",
    "families",
    "gene_count",
    "gene_ids",
    "specificity",
    "consensus_rule",
    "claim_boundary",
}


def _forbidden(*_args: Any, **_kwargs: Any) -> None:
    raise AssertionError("the UniProt route must not reach the network here")


def _registry_with(base: FungModRegistry, mapping: Mapping[str, Any]) -> FungModRegistry:
    record = load_registry_record_mapping("enzyme_classes", dict(mapping))
    assert isinstance(record, EnzymeClassRecord)
    return FungModRegistry.build(
        registry_id=base.registry_id,
        version=base.version,
        maturity=base.maturity,
        provenance=base.provenance,
        fungi=base.fungi.values(),
        enzyme_classes=(*base.enzyme_classes.values(), record),
        substrates=base.substrates.values(),
        environments=base.environments.values(),
        process_compatibility=base.process_compatibility.values(),
        parameters=base.parameters.values(),
        case_templates=base.case_templates.values(),
        product_maps=base.product_maps.values(),
    )


def _copy(tmp_path: Path, source: Path, edits: Mapping[str, str | None]) -> Path:
    target = tmp_path / source.name
    shutil.copytree(source, target)
    for name, text in edits.items():
        path = target / name
        if text is None:
            path.unlink()
        else:
            path.write_text(text, encoding="utf-8")
    return target


def _load(tmp_path: Path, edits: Mapping[str, str | None]) -> UserDataset:
    return load_user_dataset(_copy(tmp_path, UNIPROT, edits), registry=REGISTRY_INDEX)


def _issues(tmp_path: Path, edits: Mapping[str, str | None]) -> list[dict[str, Any]]:
    with pytest.raises(UserDataError) as excinfo:
        _load(tmp_path, edits)
    issues = excinfo.value.issues
    assert all(set(issue) == {"file", "row", "column", "message"} for issue in issues)
    return issues


def _has_issue(
    issues: list[dict[str, Any]],
    file: str,
    row: int | None,
    column: str | None,
    message: str,
) -> bool:
    return any(
        issue["file"] == file and issue["row"] == row and issue["column"] == column and message in issue["message"]
        for issue in issues
    )


def _records(dataset: UserDataset, record_type: str) -> dict[str, Mapping[str, Any]]:
    return {str(mapping["record_id"]): mapping for mapping in dataset.records[record_type]}


def _parameter(dataset: UserDataset, record_id: str) -> ParameterRecord:
    return load_parameter_record_mapping(_records(dataset, "parameter_records")[record_id])
