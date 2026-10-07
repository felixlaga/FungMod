"""Enzyme repertoire from a genome annotation in user data (USERDATA-003).

The fixture ``tests/fixtures/user_data/genome_case/`` holds a hand-written dbCAN
overview in the documented format (synthetic gene identifiers; not a real
genome). A genome states which enzyme classes a strain can encode; these tests
pin that the route adds only classes with a registry record, reports the rest,
takes no rate from the genome, and turns every resolved class without kinetics
into explicit gaps whose measurement requests name the annotation.
"""

from __future__ import annotations

import itertools
import json
import os
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from fungal_model import UserDataError, UserDataset, VirtualExperiment, load_user_dataset, virtual_experiment
from fungal_model.api import VirtualExperimentError
from fungal_model.api.user_data import GENOME_TABLE, USER_DATASET_MATURITY_GAP
from fungal_model.capability import (
    DIAGNOSTIC,
    POLYSPECIFIC,
    CapabilityResolutionError,
    CazymeFamilyMap,
    families_from_overview,
    parse_overview,
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

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"
FIXTURES = ROOT / "tests" / "fixtures" / "user_data"
GENOME = FIXTURES / "genome_case"
ANNOTATION = "annotations/strain_g1_overview.txt"

DATASET_ID = "genome_demo"
FUNGUS = "genome_demo__strain_g1"
STRAIN_NAME = "Genome-annotated strain G1"
ENVIRONMENT = "genome_demo__c30_ph5"
BGL = "genome_demo__beta_glucosidase"
# USERDATA-008: the registry has a cellobiohydrolase record, so the GH7 gene now gives a modellable class.
CBH = "genome_demo__cellobiohydrolase"
CELLULASE = "genome_demo__cellulase_generic"
GLUCOAMYLASE = "genome_demo__glucoamylase"
BGL_PREFIX = "genome_demo__strain_g1__beta_glucosidase__cellobiose__c30_ph5__"
SOURCE = "FungMod genome-route format fixture; synthetic gene identifiers, not a real genome"
KINETICS_SOURCE = "FungMod genome-route fixture; illustrative values, not measurements"
BGL_NOTE = (
    "; the class was inferred from the dbCAN annotation (families GH1, GH3; family membership is polyspecific, "
    "so the activity itself needs confirming)."
)
GLUCOAMYLASE_NOTE = "; the class was inferred from the dbCAN annotation (families GH15)."
GENOMES_HEADER = "strain_id,annotation_file,annotation_tool,source"
GENOMES_HEADER_WITH_THRESHOLD = f"{GENOMES_HEADER},min_tools_agreeing"
TOOL = "dbCAN 3 overview format (hand-written fixture; no dbCAN run)"


@pytest.fixture(scope="module")
def base_registry() -> FungModRegistry:
    return load_registry(REGISTRY_INDEX)


@pytest.fixture(scope="module")
def genome(base_registry: FungModRegistry) -> UserDataset:
    return load_user_dataset(GENOME, registry=base_registry)


@pytest.fixture(scope="module")
def extended_registry(base_registry: FungModRegistry) -> FungModRegistry:
    """The shipped registry plus one test-only enzyme-class record (not shipped, no kinetics).

    It makes the family map's glucoamylase class (GH15) modellable, so the
    route can be exercised on a resolved class acting on a non-cellulose
    substrate; the shipped registry has no such record.
    """

    record = load_registry_record_mapping(
        "enzyme_classes",
        {
            "record_id": "glucoamylase",
            "name": "glucoamylase",
            "ec_number": "3.2.1.3",
            "maturity": "exploratory_metadata",
            "provenance": {
                "source": "In-memory registry extension of tests/test_user_data_genome.py; not a shipped record",
                "confidence_level": "exploratory_assumption",
            },
            "target_bond_classes": ["alpha_1_4_glycosidic"],
            "compatible_substrate_classes": ["maltose"],
            "compatible_processes": ["homogeneous_michaelis_menten"],
            "notes": "Exists only in this test module to show that modellability follows the base registry.",
        },
    )
    assert isinstance(record, EnzymeClassRecord)
    return FungModRegistry.build(
        registry_id=base_registry.registry_id,
        version=base_registry.version,
        maturity=base_registry.maturity,
        provenance=base_registry.provenance,
        fungi=base_registry.fungi.values(),
        enzyme_classes=(*base_registry.enzyme_classes.values(), record),
        substrates=base_registry.substrates.values(),
        environments=base_registry.environments.values(),
        process_compatibility=base_registry.process_compatibility.values(),
        parameters=base_registry.parameters.values(),
        case_templates=base_registry.case_templates.values(),
        product_maps=base_registry.product_maps.values(),
    )


# ---------------------------------------------------------------------------
# Resolution and evidence


def test_resolved_registry_classes_join_the_strain_with_genome_evidence(genome: UserDataset) -> None:
    fungus = _records(genome, "fungi")[FUNGUS]
    assert fungus["enzyme_classes"] == [BGL, CBH, CELLULASE]
    assert "genomes.csv row 2" in fungus["notes"]

    evidence = fungus["provenance"]["enzyme_class_evidence"][BGL]
    assert evidence["evidence"] == "genome annotation (dbCAN, 3 genes, families GH1, GH3)"
    assert evidence["source"] == SOURCE
    assert (evidence["file"], evidence["row"], evidence["declared_by"]) == (GENOME_TABLE, 2, GENOME_TABLE)
    annotation = evidence["genome_annotation"]
    assert annotation["annotation_file"] == ANNOTATION
    assert annotation["annotation_tool"] == "dbCAN"
    assert annotation["annotation_tool_version"] == "3 overview format (hand-written fixture; no dbCAN run)"
    assert annotation["gene_ids"] == ["synthetic_g001", "synthetic_g002", "synthetic_g003"]
    assert annotation["specificity"] == POLYSPECIFIC
    assert "not what it expresses" in annotation["claim_boundary"]
    assert fungus["provenance"]["enzyme_class_evidence"][CELLULASE]["evidence"] == (
        "genome annotation (dbCAN, 1 gene, families GH5)"
    )
    assert fungus["provenance"]["enzyme_class_evidence"][CBH]["evidence"] == (
        "genome annotation (dbCAN, 1 gene, families GH7)"
    )

    enzyme_class = _records(genome, "enzyme_classes")[BGL]
    assert enzyme_class["provenance"]["registry_parent_enzyme_class"] == "beta_glucosidase"
    assert enzyme_class["compatible_processes"] == ["homogeneous_michaelis_menten"]
    assert _records(genome, "enzyme_classes")[CBH]["provenance"]["registry_parent_enzyme_class"] == "cellobiohydrolase"

    resolved = {item["enzyme_class"]: item for item in genome.genome_resolved_classes}
    assert set(resolved) == {"beta_glucosidase", "cellobiohydrolase", "cellulase_generic"}
    assert resolved["beta_glucosidase"]["families"] == ["GH1", "GH3"]
    assert resolved["beta_glucosidase"]["gene_count"] == 3
    assert resolved["beta_glucosidase"]["record_id"] == BGL
    assert (resolved["beta_glucosidase"]["declared_by"], resolved["beta_glucosidase"]["enzymes_row"]) == (
        GENOME_TABLE,
        None,
    )

    (read,) = genome.genome_annotations
    assert read["annotation_sha256"] == genome.file_digests[ANNOTATION]
    assert read["tool_columns"] == ["HMMER", "dbCAN_sub", "DIAMOND"]
    assert read["min_tools_agreeing"] is None
    assert "families_from_overview" in read["consensus_rule"]
    assert read["gene_rows"] == 10
    assert read["family_map"]["sha256"]
    assert read["family_map"]["sources"] == list(CazymeFamilyMap.load().sources)
    # The default consensus rule is the existing one: the same families as families_from_overview.
    assert sorted(read["family_gene_counts"]) == list(families_from_overview(GENOME / ANNOTATION))


def test_explicit_enzymes_row_wins_and_both_pieces_of_evidence_are_recorded(tmp_path: Path) -> None:
    enzymes = "strain_id,enzyme_class,evidence,source\nstrain_g1,EC 3.2.1.21,activity assay on cellobiose,LN-9 p. 2\n"
    dataset = _load(tmp_path, {"enzymes.csv": enzymes})

    fungus = _records(dataset, "fungi")[FUNGUS]
    assert fungus["enzyme_classes"] == [BGL, CBH, CELLULASE]
    evidence = fungus["provenance"]["enzyme_class_evidence"][BGL]
    assert (evidence["evidence"], evidence["source"]) == ("activity assay on cellobiose", "LN-9 p. 2")
    assert (evidence["file"], evidence["row"], evidence["declared_by"]) == ("enzymes.csv", 2, "enzymes.csv")
    assert evidence["genome_annotation"]["evidence"] == "genome annotation (dbCAN, 3 genes, families GH1, GH3)"
    assert evidence["genome_annotation"]["row"] == 2

    resolved = {item["enzyme_class"]: item for item in dataset.genome_resolved_classes}
    assert (resolved["beta_glucosidase"]["declared_by"], resolved["beta_glucosidase"]["enzymes_row"]) == (
        "enzymes.csv",
        2,
    )
    assert resolved["cellulase_generic"]["declared_by"] == GENOME_TABLE
    # The explicit row declares the class, so its gap requests do not cite the annotation.
    gap = _parameter(dataset, f"{BGL_PREFIX}km__gap")
    assert "inferred from" not in gap.provenance["measurement_request"]
    assert "genome_annotation" not in gap.provenance[USER_DATASET_PROVENANCE_KEY]


def test_resolved_classes_without_a_registry_record_are_listed_not_fabricated(
    genome: UserDataset,
    base_registry: FungModRegistry,
) -> None:
    unmodellable = {item["enzyme_class"]: item for item in genome.unmodellable_enzyme_classes}
    # USERDATA-008: cellobiohydrolase has a registry record now and is no longer listed here.
    assert set(unmodellable) == {"endo_xylanase", "glucoamylase", "laccase"}
    assert unmodellable["endo_xylanase"]["families"] == ["GH10"]
    assert unmodellable["endo_xylanase"]["gene_count"] == 1
    assert unmodellable["endo_xylanase"]["specificity"] == DIAGNOSTIC
    assert unmodellable["laccase"]["families"] == ["AA1"]
    assert all("no enzyme-class record" in item["reason"] for item in unmodellable.values())

    generated = json.dumps(genome.to_dict()["records"])
    overlaid = genome.overlay(base_registry)
    for enzyme_class in unmodellable:
        assert enzyme_class not in base_registry.enzyme_classes
        assert f"{DATASET_ID}__{enzyme_class}" not in generated
        assert not any(record_id.endswith(enzyme_class) for record_id in overlaid.enzyme_classes)
    summary = genome.summary()
    assert summary["unmodellable_enzyme_classes"] == [dict(item) for item in genome.unmodellable_enzyme_classes]
    assert summary["record_counts"]["enzyme_classes"] == 3


def test_unmapped_families_are_listed(genome: UserDataset) -> None:
    unmapped = {item["family"]: item for item in genome.unmapped_families}
    assert set(unmapped) == {"CBM1", "GT2"}
    assert unmapped["CBM1"]["gene_count"] == 1
    assert unmapped["GT2"]["genomes_row"] == 2
    assert "assigns no enzyme class" in unmapped["GT2"]["reason"]
    assert genome.to_dict()["unmapped_families"] == [dict(item) for item in genome.unmapped_families]


def test_gap_records_carry_genome_aware_measurement_requests(genome: UserDataset) -> None:
    parameters = [load_parameter_record_mapping(mapping) for mapping in genome.records["parameter_records"]]
    assert {record.record_id for record in parameters} == {
        f"{BGL_PREFIX}{quantity}__gap"
        for quantity in ("km", "kcat", "substrate_initial_concentration", "enzyme_concentration")
    }
    for record in parameters:
        assert record.maturity == USER_DATASET_MATURITY_GAP
        assert record.allowed_use == PARAMETER_ALLOWED_USE_GAP_ANALYSIS_ONLY
        assert record.value.is_unknown
        assert record.value.units is None
        assert record.provenance["measurement_request"].endswith(BGL_NOTE)
        user = record.provenance[USER_DATASET_PROVENANCE_KEY]
        assert user["class_evidence"] == "genome_annotation"
        assert user["genome_annotation"]["families"] == ["GH1", "GH3"]

    kcat = _parameter(genome, f"{BGL_PREFIX}kcat__gap")
    assert kcat.provenance["measurement_request"] == (
        f"Measure kcat and the enzyme concentration of beta-glucosidase from {STRAIN_NAME} on Cellobiose at "
        f"30 degC, pH 5.0, or Vmax (or a specific activity and enzyme loading){BGL_NOTE}"
    )
    km = _parameter(genome, f"{BGL_PREFIX}km__gap")
    assert km.provenance["measurement_request"] == (
        f"Measure km of beta-glucosidase from {STRAIN_NAME} on Cellobiose at 30 degC, pH 5.0 "
        f"(concentration units){BGL_NOTE}"
    )
    template = _records(genome, "case_templates")["genome_demo__beta_glucosidase__cellobiose__homogeneous_mm_template"]
    assert template["process_state_metadata"]["config_mode"] == "exploratory"


def test_preflight_is_underparameterized_with_the_requests_as_suggested_experiments(
    genome: UserDataset,
    tmp_path: Path,
) -> None:
    study = virtual_experiment(fungi=STRAIN_NAME, substrates="cellobiose", environments="c30_ph5", user_data=genome)
    report = study.preflight(mode="exploratory")[0]

    assert report.status == "underparameterized"
    assert {item.item_id for item in report.missing} == {
        f"{DATASET_ID}__{quantity}__beta_glucosidase__cellobiose"
        for quantity in ("km", "kcat", "substrate_initial_concentration", "enzyme_concentration")
    }
    requests = {item.details["measurement_request"] for item in report.missing}
    assert set(report.suggested_experiments) == requests
    assert all(text.endswith(BGL_NOTE) for text in report.suggested_experiments)

    written = study.write_preflight_report(mode="exploratory", output_dir=tmp_path / "preflight")
    preflight_csv = Path(written.paths["modelability_preflight"]).read_text(encoding="utf-8")
    assert all(text in preflight_csv for text in requests)
    resolution = json.loads(Path(written.paths["user_dataset_genome_resolution"]).read_text(encoding="utf-8"))
    assert resolution["user_dataset_digest"] == genome.digest
    assert {item["enzyme_class"] for item in resolution["unmodellable_enzyme_classes"]} == {
        "endo_xylanase",
        "glucoamylase",
        "laccase",
    }
    assert {item["family"] for item in resolution["unmapped_families"]} == {"CBM1", "GT2"}
    assert resolution["genome_annotations"][0]["annotation_file"] == ANNOTATION

    experiment = study.to_dict()
    assert experiment["user_dataset_id"] == DATASET_ID
    assert [item["enzyme_class"] for item in experiment["genome_resolved_classes"]] == [
        "beta_glucosidase",
        "cellobiohydrolase",
        "cellulase_generic",
    ]
    assert len(experiment["unmodellable_enzyme_classes"]) == 3
    assert len(experiment["unmapped_families"]) == 2


def test_scientific_mode_never_runs_on_a_genome_only_class(genome: UserDataset, tmp_path: Path) -> None:
    study = virtual_experiment(fungi="strain_g1", substrates="cellobiose", environments="c30_ph5", user_data=genome)

    for mode in ("scientific", "exploratory"):
        assert study.preflight(mode=mode)[0].status == "underparameterized"
    for mapping in genome.records["parameter_records"]:
        record = load_parameter_record_mapping(mapping)
        assert parameter_record_mode_eligibility_blocker(record, mode="scientific") is not None
    with pytest.raises(VirtualExperimentError, match="Scientific simulation requires exact"):
        study.simulate(mode="scientific", output_dir=tmp_path / "scientific", quicklook=False)
    with pytest.raises(VirtualExperimentError, match="only modelable or exploratory"):
        study.simulate(mode="exploratory", output_dir=tmp_path / "exploratory", quicklook=False)


# ---------------------------------------------------------------------------
# A non-cellulose class with a registry record, and genome plus user kinetics


def test_a_resolved_class_on_a_non_cellulose_substrate_follows_the_base_registry(
    extended_registry: FungModRegistry,
) -> None:
    dataset = load_user_dataset(GENOME, registry=extended_registry)

    assert _records(dataset, "fungi")[FUNGUS]["enzyme_classes"] == [BGL, CBH, CELLULASE, GLUCOAMYLASE]
    assert "glucoamylase" in {item["enzyme_class"] for item in dataset.genome_resolved_classes}
    assert "glucoamylase" not in {item["enzyme_class"] for item in dataset.unmodellable_enzyme_classes}
    gap = _parameter(dataset, "genome_demo__strain_g1__glucoamylase__maltose__c30_ph5__km__gap")
    assert gap.substrate_id == "genome_demo__maltose"
    assert gap.provenance["measurement_request"] == (
        f"Measure km of glucoamylase from {STRAIN_NAME} on maltose at 30 degC, pH 5.0 "
        f"(concentration units){GLUCOAMYLASE_NOTE}"
    )
    assert gap.provenance[USER_DATASET_PROVENANCE_KEY]["genome_annotation"]["specificity"] == DIAGNOSTIC


def test_genome_plus_user_kinetics_runs_one_class_while_the_other_stays_a_gap(
    extended_registry: FungModRegistry,
    tmp_path: Path,
) -> None:
    case = "strain_g1,beta_glucosidase,cellobiose,c30_ph5"
    kinetics = (GENOME / "kinetics.csv").read_text(encoding="utf-8") + "".join(
        f'{case},{quantity},{value},,,{units},estimate,,"{KINETICS_SOURCE}",,\n'
        for quantity, value, units in (
            ("km", "15", "mM"),
            ("kcat", "0.1", "1/s"),
            ("substrate_initial_concentration", "10", "mM"),
            ("enzyme_concentration", "0.001", "mM"),
        )
    )
    dataset = load_user_dataset(
        _copy_fixture(tmp_path, GENOME, edits={"kinetics.csv": kinetics}),
        registry=extended_registry,
    )
    kcat = _parameter(dataset, f"{BGL_PREFIX}kcat")
    assert kcat.value.is_exact
    assert "inferred from" not in json.dumps(kcat.provenance)

    runnable = virtual_experiment(
        fungi="strain_g1",
        substrates="cellobiose",
        environments="c30_ph5",
        registry=extended_registry,
        user_data=dataset,
    )
    assert runnable.preflight(mode="exploratory")[0].status == "modelable"
    assert runnable.preflight(mode="scientific")[0].status != "modelable"
    result = runnable.simulate(mode="exploratory", n_samples=2, seed=3, output_dir=tmp_path / "run", quicklook=False)
    rows = result.time_series()
    for sample_id in {row["sample_id"] for row in rows}:
        substrate = [float(row["value"]) for row in rows if row["sample_id"] == sample_id and row["state_role"] == "substrate"]
        product = [float(row["value"]) for row in rows if row["sample_id"] == sample_id and row["state_role"] == "product"]
        assert substrate[0] == pytest.approx(10.0)
        assert substrate[-1] < substrate[0]
        assert all(later <= earlier + 1e-12 for earlier, later in itertools.pairwise(substrate))
        assert product[-1] == pytest.approx(2.0 * (substrate[0] - substrate[-1]), rel=1e-6)
    summary = json.loads((Path(result.output_directory) / "virtual_experiment_summary.json").read_text())
    assert summary["experiment"]["user_dataset_digest"] == dataset.digest
    assert {item["enzyme_class"] for item in summary["experiment"]["genome_resolved_classes"]} == {
        "beta_glucosidase",
        "cellobiohydrolase",
        "cellulase_generic",
        "glucoamylase",
    }
    assert {item["family"] for item in summary["experiment"]["unmapped_families"]} == {"CBM1", "GT2"}

    gap_study = virtual_experiment(
        fungi="strain_g1",
        substrates="maltose",
        environments="c30_ph5",
        registry=extended_registry,
        user_data=dataset,
    )
    report = gap_study.preflight(mode="exploratory")[0]
    assert report.status == "underparameterized"
    assert len(report.missing) == 4
    assert all(text.endswith(GLUCOAMYLASE_NOTE) for text in report.suggested_experiments)


# ---------------------------------------------------------------------------
# Consensus rule


def test_min_tools_agreeing_applies_the_users_threshold(tmp_path: Path) -> None:
    two = _load(tmp_path / "two", {GENOME_TABLE: _genomes_row(min_tools="2")})
    resolved = {item["enzyme_class"]: item for item in two.genome_resolved_classes}
    # synthetic_g003 (GH3 by DIAMOND only) and synthetic_g007 (GH5 by HMMER only) drop out;
    # synthetic_g004 (GH7 by three tools) gives the cellobiohydrolase record (USERDATA-008).
    assert set(resolved) == {"beta_glucosidase", "cellobiohydrolase"}
    assert resolved["beta_glucosidase"]["gene_count"] == 2
    assert _records(two, "fungi")[FUNGUS]["enzyme_classes"] == [BGL, CBH]
    (read,) = two.genome_annotations
    assert read["min_tools_agreeing"] == 2
    assert "at least 2 of the tool columns present (HMMER, dbCAN_sub, DIAMOND)" in read["consensus_rule"]
    assert "GH5" not in read["family_gene_counts"]
    assert {item["family"] for item in two.unmapped_families} == {"CBM1", "GT2"}

    three = _load(tmp_path / "three", {GENOME_TABLE: _genomes_row(min_tools="3")})
    by_class = {item["enzyme_class"]: item for item in three.genome_resolved_classes}
    assert set(by_class) == {"beta_glucosidase", "cellobiohydrolase"}
    bgl = by_class["beta_glucosidase"]
    assert (bgl["families"], bgl["gene_count"]) == (["GH3"], 1)
    assert (by_class["cellobiohydrolase"]["families"], by_class["cellobiohydrolase"]["gene_count"]) == (["GH7"], 1)
    assert three.unmapped_families == ()


@pytest.mark.parametrize(
    ("min_tools", "message"),
    [
        ("4", "exceeds the 3 tool column(s) present"),
        ("0", "must be a positive integer"),
        ("two", "must be a positive integer"),
    ],
)
def test_min_tools_agreeing_is_refused_outside_its_range(tmp_path: Path, min_tools: str, message: str) -> None:
    issues = _issues(tmp_path, {GENOME_TABLE: _genomes_row(min_tools=min_tools)})
    assert _has_issue(issues, GENOME_TABLE, 2, "min_tools_agreeing", message), issues


# ---------------------------------------------------------------------------
# Refusals


def _overview_lines() -> list[str]:
    return (GENOME / ANNOTATION).read_text(encoding="utf-8").splitlines(keepends=True)


REFUSALS: dict[str, tuple[dict[str, str | None], tuple[str, int | None, str | None, str]]] = {
    "absolute_path": (
        {GENOME_TABLE: None},
        (GENOME_TABLE, 2, "annotation_file", "is an absolute path"),
    ),
    "escaping_path": (
        {GENOME_TABLE: None},
        (GENOME_TABLE, 2, "annotation_file", "leaves the dataset directory"),
    ),
    "missing_file": (
        {GENOME_TABLE: None},
        (GENOME_TABLE, 2, "annotation_file", "does not exist in the dataset directory"),
    ),
    "unknown_tool": (
        {GENOME_TABLE: None},
        (GENOME_TABLE, 2, "annotation_tool", "is not a supported annotation tool"),
    ),
    "tool_without_version": (
        {GENOME_TABLE: None},
        (GENOME_TABLE, 2, "annotation_tool", "without a version"),
    ),
    "undeclared_strain": (
        {GENOME_TABLE: None},
        (GENOME_TABLE, 2, "strain_id", "not declared in strains.csv"),
    ),
    "malformed_overview_header": (
        {ANNOTATION: "Gene ID,EC#,HMMER,dbCAN_sub,DIAMOND,#ofTools\nsynthetic_g001,-,GH3,GH3_e41,GH3,3\n"},
        (GENOME_TABLE, 2, "annotation_file", "does not have a dbCAN overview header"),
    ),
    "duplicate_gene": (
        {ANNOTATION: "".join(_overview_lines()[:3]) + _overview_lines()[1]},
        (GENOME_TABLE, 2, "annotation_file", "repeats gene 'synthetic_g001'"),
    ),
    "second_annotation_for_a_strain": (
        {GENOME_TABLE: None},
        (GENOME_TABLE, 3, "strain_id", "already has a genome annotation in row 2"),
    ),
}


def _refusal_edits(case: str) -> dict[str, str | None]:
    edits, _ = REFUSALS[case]
    if GENOME_TABLE not in edits:
        return edits
    rows = {
        "absolute_path": _genomes_row(path=str((GENOME / ANNOTATION).resolve())),
        "escaping_path": _genomes_row(path=f"../{GENOME.name}/{ANNOTATION}"),
        "missing_file": _genomes_row(path="annotations/absent_overview.txt"),
        "unknown_tool": _genomes_row(tool="eggNOG-mapper 2.1.12"),
        "tool_without_version": _genomes_row(tool="dbCAN"),
        "undeclared_strain": _genomes_row(strain="strain_x"),
        "second_annotation_for_a_strain": _genomes_row() + _genomes_row().splitlines()[1] + "\n",
    }
    return {**edits, GENOME_TABLE: rows[case]}


@pytest.mark.parametrize("case", sorted(REFUSALS))
def test_invalid_genome_rows_are_refused_with_file_row_and_column(tmp_path: Path, case: str) -> None:
    _, (file, row, column, message) = REFUSALS[case]
    issues = _issues(tmp_path, _refusal_edits(case))
    assert _has_issue(issues, file, row, column, message), issues


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symbolic links are not available")
def test_annotation_reached_through_a_symbolic_link_outside_the_directory_is_refused(tmp_path: Path) -> None:
    outside = tmp_path / "outside_overview.txt"
    shutil.copyfile(GENOME / ANNOTATION, outside)
    dataset_dir = _copy_fixture(tmp_path, GENOME)
    link = dataset_dir / "annotations" / "linked_overview.txt"
    try:
        link.symlink_to(outside)
    except OSError as exc:  # pragma: no cover - platforms without symlink permission
        pytest.skip(f"cannot create a symbolic link: {exc}")
    (dataset_dir / GENOME_TABLE).write_text(_genomes_row(path="annotations/linked_overview.txt"), encoding="utf-8")

    with pytest.raises(UserDataError) as excinfo:
        load_user_dataset(dataset_dir, registry=REGISTRY_INDEX)
    assert _has_issue(excinfo.value.issues, GENOME_TABLE, 2, "annotation_file", "resolves outside the dataset directory")


def test_strain_whose_annotation_resolves_no_registry_class_is_refused(tmp_path: Path) -> None:
    # USERDATA-008: GH7 resolves to the cellobiohydrolase record now, so the annotation keeps GH10 only.
    overview = "".join(line for line in _overview_lines() if line.startswith("Gene ID") or "GH10" in line)
    issues = _issues(tmp_path, {ANNOTATION: overview})

    assert _has_issue(issues, "strains.csv", 2, "strain_id", "resolved no enzyme class with a registry record"), issues
    message = next(issue["message"] for issue in issues if issue["file"] == "strains.csv")
    assert "endo_xylanase" in message
    assert "FungMod does not create enzyme classes from a genome annotation" in message


def test_genome_table_lets_enzymes_csv_hold_only_its_header_but_not_without_it(tmp_path: Path) -> None:
    issues = _issues(tmp_path, {GENOME_TABLE: None})
    assert _has_issue(issues, "enzymes.csv", None, None, "at least one data row"), issues


# ---------------------------------------------------------------------------
# Digest and datasets without a genome


def test_digest_covers_the_annotation_file_bytes(genome: UserDataset, tmp_path: Path) -> None:
    again = load_user_dataset(GENOME, registry=REGISTRY_INDEX)
    assert again.digest == genome.digest
    assert ANNOTATION in genome.file_digests

    changed_text = (GENOME / ANNOTATION).read_text(encoding="utf-8").replace("GH7(20-455)", "GH7(21-455)")
    changed = _load(tmp_path, {ANNOTATION: changed_text})
    assert changed.digest != genome.digest
    assert changed.file_digests[ANNOTATION] != genome.file_digests[ANNOTATION]
    assert changed.file_digests["genomes.csv"] == genome.file_digests["genomes.csv"]
    assert changed.genome_resolved_classes == genome.genome_resolved_classes
    record = _parameter(changed, f"{BGL_PREFIX}km__gap")
    assert record.provenance[USER_DATASET_PROVENANCE_KEY]["digest"] == changed.digest


def test_datasets_and_experiments_without_a_genome_report_empty_or_null_lists(base_registry: FungModRegistry) -> None:
    esterase = load_user_dataset(FIXTURES / "esterase_case", registry=base_registry)
    for key in ("genome_annotations", "genome_resolved_classes", "unmodellable_enzyme_classes", "unmapped_families"):
        assert esterase.to_dict()[key] == []
        assert esterase.summary()[key] == []
    with_user_data = virtual_experiment(
        fungi="strain_e1", substrates="p_nitrophenyl_butyrate", environments="c37_ph7_5", user_data=esterase
    ).to_dict()
    registry_only = VirtualExperiment.from_registry(
        fungi="sabiork_beta_glucosidase_source",
        substrates="cellobiose",
        environments="sabiork_reaction_618_selected_conditions",
        registry=REGISTRY_INDEX,
    ).to_dict()
    for key in ("genome_resolved_classes", "unmodellable_enzyme_classes", "unmapped_families"):
        assert with_user_data[key] == []
        assert registry_only[key] is None


def test_genome_route_takes_no_rate_from_the_annotation(genome: UserDataset) -> None:
    for mapping in genome.records["parameter_records"]:
        assert mapping["value"]["kind"] == "unknown"
    keys = {
        key.lower()
        for name in ("genome_annotations", "genome_resolved_classes", "unmodellable_enzyme_classes", "unmapped_families")
        for entry in genome.to_dict()[name]
        for key in entry
    }
    for forbidden in ("kcat", "vmax", "km", "rate", "value", "units", "turnover", "activity", "expression"):
        assert not any(forbidden in key for key in keys), forbidden


# ---------------------------------------------------------------------------
# dbCAN per-gene parsing


def test_parse_overview_counts_genes_and_keeps_the_existing_family_rule() -> None:
    overview = parse_overview((GENOME / ANNOTATION).read_text(encoding="utf-8"), source="fixture")

    assert overview.tool_columns == ("HMMER", "dbCAN_sub", "DIAMOND")
    assert len(overview.genes) == 10
    families = overview.family_genes()
    assert tuple(families) == families_from_overview(GENOME / ANNOTATION)
    assert families["GH3"] == ("synthetic_g001", "synthetic_g003")
    assert families["AA1"] == ("synthetic_g006",)
    assert overview.family_genes(min_tools_agreeing=2)["GH3"] == ("synthetic_g001",)
    with pytest.raises(CapabilityResolutionError, match="exceeds"):
        overview.family_genes(min_tools_agreeing=4)
    with pytest.raises(CapabilityResolutionError, match="no gene identifier"):
        parse_overview("Gene ID\tHMMER\n\tGH3\n", source="fixture")
    with pytest.raises(CapabilityResolutionError, match="no CAZy family calls"):
        parse_overview("Gene ID\tHMMER\tDIAMOND\ng1\t-\t-\n", source="fixture")
    with pytest.raises(CapabilityResolutionError, match="more cells than the header"):
        parse_overview("Gene ID\tHMMER\ng1\tGH3\textra\n", source="fixture")


def test_family_map_sources_are_complete_citations() -> None:
    for source in CazymeFamilyMap.load().sources:
        assert not source.startswith("{"), source
        assert "doi:" in source


# ---------------------------------------------------------------------------
# Helpers


def _genomes_row(
    *,
    strain: str = "strain_g1",
    path: str = ANNOTATION,
    tool: str = TOOL,
    min_tools: str | None = None,
) -> str:
    header = GENOMES_HEADER if min_tools is None else GENOMES_HEADER_WITH_THRESHOLD
    row = f'{strain},{path},{tool},"{SOURCE}"'
    if min_tools is not None:
        row = f"{row},{min_tools}"
    return f"{header}\n{row}\n"


def _copy_fixture(tmp_path: Path, source: Path, *, edits: Mapping[str, str | None] | None = None) -> Path:
    target = tmp_path / source.name
    shutil.copytree(source, target)
    for name, text in (edits or {}).items():
        path = target / name
        if text is None:
            path.unlink()
        else:
            path.write_text(text, encoding="utf-8")
    return target


def _load(tmp_path: Path, edits: Mapping[str, str | None]) -> UserDataset:
    return load_user_dataset(_copy_fixture(tmp_path, GENOME, edits=edits), registry=REGISTRY_INDEX)


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

