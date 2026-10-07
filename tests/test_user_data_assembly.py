"""One reviewable user dataset for "fungus X on substrate Y at conditions Z" (ASSEMBLE-001).

Inputs are existing repository data only: the frozen SABIO-RK Reaction 618
export in ``data/kinetic_records/sabiork/case_001_reaction_618_beta_glucosidase``
(real entries), the hand-written dbCAN format fixture of
``tests/fixtures/user_data/genome_case`` (synthetic gene identifiers, not a
real genome), and the illustrative ``oxidase_case``, ``esterase_case`` and
``literature_reentry`` user datasets. Review fields are filled by the tests
with text that says so; the one in-memory registry extension (a glucoamylase
class) is test-only, as in ``tests/test_user_data_genome.py``.
"""

from __future__ import annotations

import csv
import itertools
import shutil
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml

import fungal_model
import fungal_model.api as fungal_model_api
from fungal_model import (
    AssembledTablesDraft,
    UserDataError,
    UserTablesAssemblyError,
    UserTablesDraft,
    UserTablesSourceError,
    assemble_user_tables,
    environment_grid,
    load_user_dataset,
    source_proposal,
    virtual_experiment,
)
from fungal_model.api import VirtualExperimentError
from fungal_model.api.user_data import REVIEW_MARKER, enzyme_class_acts_on
from fungal_model.api.user_data_assembly import ASSEMBLY_STATUSES
from fungal_model.registry import FungModRegistry, load_registry
from fungal_model.registry.loaders import load_parameter_record_mapping, load_registry_record_mapping
from fungal_model.registry.records import EnzymeClassRecord
from fungal_model.sources.sabiork import fetch as sabiork_fetch

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"
FIXTURES = ROOT / "tests" / "fixtures" / "user_data"
GENOME = FIXTURES / "genome_case"
OXIDASE = FIXTURES / "oxidase_case"
ESTERASE = FIXTURES / "esterase_case"
LITERATURE = FIXTURES / "literature_reentry"
ANNOTATION = GENOME / "annotations" / "strain_g1_overview.txt"
EXPORT = (
    ROOT
    / "data"
    / "kinetic_records"
    / "sabiork"
    / "case_001_reaction_618_beta_glucosidase"
    / "raw"
    / "kinlaw_entries_reaction_618.json"
)
CACHE = ROOT / "data" / "source_snapshots" / "sabiork"
TOOL = "dbCAN 3 overview format (hand-written fixture; no dbCAN run)"
ANNOTATION_SOURCE = "FungMod genome-route format fixture; synthetic gene identifiers, not a real genome"
G1 = "Genome-annotated strain G1"
DESIGN = {
    # The literature_reentry fixture's virtual assay design.
    "substrate_initial_concentration": {"value": 10, "units": "mM"},
    "enzyme_concentration": {"value": 1e-3, "units": "mM"},
}
TIME_GRID = {"duration": 10, "units": "hour", "points": 61}
C30_PH5 = {"temperature": 30, "temperature_units": "degC", "ph": 5}
C40_PH5 = {"temperature": 40, "temperature_units": "degC", "ph": 5}
C30_PH6_5 = {"temperature": 30, "temperature_units": "degC", "ph": 6.5}
REVIEW_VALUES = {
    # Test-only review answers: an enzyme concentration for the virtual assay and an annotation source.
    ("kinetics.csv", "value"): "0.001",
    ("kinetics.csv", "units"): "mM",
    ("kinetics.csv", "source"): "Virtual assay design chosen by the test reviewer",
    ("genomes.csv", "source"): ANNOTATION_SOURCE,
    ("substrates.csv", "product_yield"): "2",
    ("substrates.csv", "source"): "Reaction equation cellobiose + H2O = 2 beta-D-glucose, stated by the test reviewer",
}
T_MIN, T_OPT, T_MAX = 10.0, 50.0, 70.0  # the oxidase fixture's illustrative cardinal temperatures


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_network_is_used(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Assembling user tables must not touch the network.")

    monkeypatch.setattr(urllib.request, "urlopen", fail_if_network_is_used)
    monkeypatch.setattr(sabiork_fetch, "urlopen", fail_if_network_is_used)


@pytest.fixture(scope="module")
def base_registry() -> FungModRegistry:
    return load_registry(REGISTRY_INDEX)


def _g1(**overrides: Any) -> AssembledTablesDraft:
    arguments: dict[str, Any] = {
        "dataset_id": "g1_assembly",
        "fungus": G1,
        "substrates": ["cellobiose"],
        "conditions": [C30_PH5],
        "annotation": ANNOTATION,
        "annotation_tool": TOOL,
        "kinetics_sources": [EXPORT],
        "entry_ids": ["35622"],
        "registry": REGISTRY_INDEX,
        "cache_dir": CACHE,
    }
    arguments.update(overrides)
    return assemble_user_tables(**arguments)


# ---------------------------------------------------------------------------
# Rule 3c: a cross-organism transfer is an estimate, visible and reviewable


def test_kinetics_of_another_organism_are_transferred_estimates(tmp_path: Path) -> None:
    draft = _g1()
    assert isinstance(draft, UserTablesDraft)
    (case,) = draft.assembly["cases"]
    assert (case["fungus"], case["enzyme_class"], case["substrate_id"], case["condition"]) == (
        G1,
        "beta_glucosidase",
        "cellobiose",
        "c30_ph5",
    )
    assert case["kinetics_status"] == "transferred_estimate"
    assert case["condition_route"] == "same_condition"
    assert case["source_ids"] == ["SABIO-RK EntryID 35622"]
    assert case["reason"].startswith("transferred from Oryza sativa enzyme, SABIO-RK entry 35622")
    assert any("genome annotation" in text for text in case["class_evidence"])
    assert draft.assembly["transferred_entry_ids"] == ["35622"]

    rows = {row["quantity"]: row for row in draft.kinetics}
    for quantity in ("km", "kcat", "substrate_initial_concentration"):
        assert rows[quantity]["evidence_type"] == "estimate", quantity
        assert rows[quantity]["method"].startswith("transferred from Oryza sativa enzyme, SABIO-RK entry 35622")
        assert rows[quantity]["source"] == "SABIO-RK EntryID 35622 (Seshadri S et al. 2009, PMID 19587102)"
    assert (rows["km"]["value"], rows["km"]["units"], rows["km"]["sd"]) == ("15.3", "mM", "1.2")
    assert not any(row["evidence_type"] in {"literature", "measured"} for row in draft.kinetics)
    # The enzyme concentration of the kcat form is the user's decision.
    assert rows["enzyme_concentration"]["value"].startswith(REVIEW_MARKER)
    assert rows["enzyme_concentration"]["evidence_type"] == "design"

    review_fields = {(item["file"], item["column"]) for item in draft.review_fields}
    assert review_fields == {
        ("user_dataset.yml", "contributor"),
        ("user_dataset.yml", "simulation.duration"),
        ("user_dataset.yml", "simulation.units"),
        ("user_dataset.yml", "simulation.points"),
        ("kinetics.csv", "value"),
        ("kinetics.csv", "units"),
        ("kinetics.csv", "source"),
        ("genomes.csv", "source"),
    }
    transfers = draft.review.split("## Transferred kinetics", 1)[1].split("\n## ", 1)[0]
    assert "transferred from Oryza sativa enzyme, SABIO-RK entry 35622" in transfers
    assert "only by editing kinetics.csv yourself" in transfers
    assert "never labels a transferred value as literature or measured" in transfers

    directory = tmp_path / "draft"
    draft.write(directory)
    with pytest.raises(UserDataError, match="unfilled review fields"):
        load_user_dataset(directory)
    _fill(directory)
    dataset = load_user_dataset(directory, registry=REGISTRY_INDEX)
    km = _parameter(dataset, "g1_assembly__genome_annotated_strain_g1__beta_glucosidase__cellobiose__c30_ph5__km")
    assert km.maturity == "exploratory_prior"
    assert km.provenance["exploratory_prior"] is True
    assert "transferred from Oryza sativa enzyme, SABIO-RK entry 35622" in km.provenance["measurement_method"]

    study = virtual_experiment(fungi=G1, substrates="cellobiose", environments="c30_ph5", user_data=dataset)
    # The substrate concentration is the other assay's tested range, so the case is an exploratory screen.
    assert study.preflight(mode="exploratory")[0].status in {"modelable", "exploratory"}
    assert study.preflight(mode="scientific")[0].status != "modelable"
    with pytest.raises(VirtualExperimentError, match="Scientific simulation requires exact"):
        study.simulate(mode="scientific", output_dir=tmp_path / "scientific", quicklook=False)
    result = study.simulate(mode="exploratory", n_samples=2, seed=5, output_dir=tmp_path / "run", quicklook=False)
    _assert_substrate_degrades(result.time_series())


def test_other_genome_classes_are_reported_as_the_genome_route_reports_them() -> None:
    draft = _g1()
    classes = {item["enzyme_class"]: item for item in draft.assembly["enzyme_classes"]}
    # USERDATA-008: GH7 resolves to the registry's cellobiohydrolase record, which does not act on cellobiose.
    assert set(classes) == {"beta_glucosidase", "cellobiohydrolase", "cellulase_generic"}
    assert classes["beta_glucosidase"]["declared_in"] == "genomes.csv"
    (evidence,) = classes["beta_glucosidase"]["evidence"]
    assert evidence["kind"] == "genome_annotation"
    assert evidence["families"] == ["GH1", "GH3"]
    assert evidence["gene_ids"] == ["synthetic_g001", "synthetic_g002", "synthetic_g003"]
    assert {item["enzyme_class"] for item in draft.assembly["unmodellable_enzyme_classes"]} == {
        "endo_xylanase",
        "glucoamylase",
        "laccase",
    }
    assert {item["family"] for item in draft.assembly["unmapped_families"]} == {"CBM1", "GT2"}
    (compatibility,) = draft.assembly["substrate_compatibility"]
    assert [item["enzyme_class"] for item in compatibility["acting"]] == ["beta_glucosidase"]
    not_acting = {item["enzyme_class"]: item for item in compatibility["not_acting"]}
    assert set(not_acting) == {"cellobiohydrolase", "cellulase_generic"}
    assert all("substrate class 'cellobiose'" in item["reason"] for item in not_acting.values())
    # The annotation is copied and listed in genomes.csv, so the loader resolves the same classes.
    assert draft.annotation_files == {"annotations/strain_g1_overview.txt": ANNOTATION.read_bytes()}
    (genome_row,) = draft.genomes
    assert (genome_row["annotation_file"], genome_row["annotation_tool"]) == (
        "annotations/strain_g1_overview.txt",
        TOOL,
    )
    assert draft.enzymes == ()  # every class comes from the annotation alone
    assert "Does not act on it: cellulase_generic" in draft.review
    assert "Does not act on it: cellobiohydrolase" in draft.review


# ---------------------------------------------------------------------------
# Rule 3b: the fungus's own species is literature, and scientific mode is reachable


def test_an_entry_of_the_fungus_species_is_literature_and_reaches_scientific_mode(tmp_path: Path) -> None:
    draft = _g1(
        dataset_id="pc_assembly",
        fungus="Phanerochaete chrysosporium",
        conditions=[C30_PH6_5],
        entry_ids=None,
        design=DESIGN,
        time_grid=TIME_GRID,
        annotation_source=ANNOTATION_SOURCE,
    )
    fungus = draft.assembly["fungus"]
    assert (fungus["resolved_as"], fungus["registry_fungus_id"]) == (
        "registry_fungus",
        "phanerochaete_chrysosporium_k3",
    )
    assert fungus["species_for_sabiork"] == ["Phanerochaete chrysosporium"]
    (strain,) = draft.strains
    assert strain["strain_id"] == "phanerochaete_chrysosporium_k3_assembled"
    assert strain["scientific_name"] == "Phanerochaete chrysosporium"

    (case,) = draft.assembly["cases"]
    assert (case["kinetics_status"], case["source_ids"]) == ("literature_same_organism", ["SABIO-RK EntryID 38521"])
    rows = {row["quantity"]: row for row in draft.kinetics}
    # Converted exactly as user_tables_from_sabiork converts EntryID 38521, with the stated design amounts.
    assert (rows["km"]["value"], rows["km"]["units"], rows["km"]["evidence_type"]) == ("6.8", "mM", "literature")
    assert rows["kcat"]["method"] == "SABIO-RK kinetic law 38521, Michaelis-Menten"
    assert {rows[q]["evidence_type"] for q in ("substrate_initial_concentration", "enzyme_concentration")} == {"design"}
    assert "transferred" not in "".join(row["method"] for row in draft.kinetics)
    # The registry record also gives the class; both pieces of evidence are kept.
    (enzyme_row,) = draft.enzymes
    assert enzyme_row["enzyme_class"] == "beta_glucosidase"
    assert "registry fungus record phanerochaete_chrysosporium_k3" in enzyme_row["evidence"]
    evidence_kinds = {item["kind"] for item in draft.assembly["enzyme_classes"][0]["evidence"]}
    assert evidence_kinds == {"registry_record", "genome_annotation"}
    (stored,) = draft.assembly["stored_registry_cases"]
    assert stored["process_compatibility"] == "phanerochaete_bgl1a_cellobiose_ph_ionization_mm"
    assert "not copied into the draft" in stored["note"]
    # Entries at other conditions or over a pH range are listed with the reason, not converted.
    entries = {item["entry_id"]: item for item in draft.assembly["entries"]}
    assert entries["38522"]["use"] == "not used" and "not at a single condition" in entries["38522"]["reason"]
    assert entries["38523"]["use"] == "not convertible" and entries["38523"]["reason"].startswith("mutant enzyme")
    assert draft.converted_entry_ids == ("38521",)

    directory = tmp_path / "draft"
    draft.write(directory)
    _fill(directory)
    dataset = load_user_dataset(directory)
    study = virtual_experiment(
        fungi=strain["name"], substrates="cellobiose", environments="c30_ph6_5", user_data=dataset
    )
    assert study.preflight(mode="scientific")[0].status == "modelable"
    result = study.simulate(mode="scientific", output_dir=tmp_path / "scientific", quicklook=False)
    _assert_substrate_degrades(result.time_series())


def test_an_explicitly_mapped_species_counts_as_the_fungus_own() -> None:
    mapped = _g1(conditions=[C30_PH6_5], entry_ids=None, same_species=["Phanerochaete chrysosporium"])
    (case,) = mapped.assembly["cases"]
    assert case["kinetics_status"] == "literature_same_organism"
    unmapped = _g1(conditions=[C30_PH6_5], entry_ids=None)
    (case,) = unmapped.assembly["cases"]
    assert case["kinetics_status"] == "transferred_estimate"
    assert case["reason"].startswith("transferred from Phanerochaete chrysosporium enzyme, SABIO-RK entry 38521")
    with pytest.raises(UserTablesAssemblyError, match="that no SABIO-RK entry has"):
        _g1(same_species=["Trametes versicolor"])


# ---------------------------------------------------------------------------
# Rule 4: no reuse across conditions without a response law


def test_a_condition_without_a_response_law_is_a_gap_naming_the_measured_condition(tmp_path: Path) -> None:
    draft = _g1(conditions=[C30_PH5, C40_PH5], design=DESIGN, time_grid=TIME_GRID, annotation_source=ANNOTATION_SOURCE)
    cases = {case["condition"]: case for case in draft.assembly["cases"]}
    assert cases["c30_ph5"]["kinetics_status"] == "transferred_estimate"
    gap = cases["c40_ph5"]
    assert (gap["kinetics_status"], gap["condition_route"]) == ("gap", "none")
    assert gap["measured_condition"] == {"condition_id": "c30_ph5", "condition": "30 degC, pH 5"}
    assert "stated only at c30_ph5" in gap["reason"] and "without a temperature response law" in gap["reason"]
    assert gap["design_rows"] == ["substrate_initial_concentration", "enzyme_concentration"]
    assert [row["condition_id"] for row in draft.conditions] == ["c30_ph5", "c40_ph5"]
    assert {row["quantity"] for row in draft.kinetics if row["condition_id"] == "c40_ph5"} == {
        "substrate_initial_concentration",
        "enzyme_concentration",
    }
    gaps = draft.review.split("## Gaps and measurement requests", 1)[1].split("\n## ", 1)[0]
    assert "c40_ph5 (40 degC, pH 5), gap: measure km and kcat of beta-glucosidase" in gaps
    assert "stated only at c30_ph5 (30 degC, pH 5)" in gaps

    directory = tmp_path / "draft"
    draft.write(directory)
    _fill(directory)
    dataset = load_user_dataset(directory)
    prefix = "g1_assembly__genome_annotated_strain_g1__beta_glucosidase__cellobiose__c40_ph5__"
    for quantity in ("km", "kcat"):
        request = _parameter(dataset, f"{prefix}{quantity}__gap").provenance["measurement_request"]
        assert f"Measure {quantity} of beta-glucosidase from {G1} on Cellobiose at 40 degC, pH 5" in request
        assert (
            "only at c30_ph5 (30 degC, pH 5), and FungMod does not reuse kinetics measured at another condition"
            in request
        )
    report = virtual_experiment(
        fungi=G1, substrates="cellobiose", environments="c40_ph5", user_data=dataset
    ).preflight()[0]
    assert report.status == "underparameterized"
    assert len(report.suggested_experiments) == 2
    assert all("only at c30_ph5" in text for text in report.suggested_experiments)


def test_a_response_law_carries_measured_kinetics_to_an_environment_grid_condition(tmp_path: Path) -> None:
    draft = assemble_user_tables(
        dataset_id="oxidase_assembly",
        fungus="Oxidase source strain L1",
        substrates=["syringaldazine_like"],
        conditions=[{**C40_PH5, "temperature": 50}, C40_PH5],
        user_data=OXIDASE,
    )
    cases = {case["condition"]: case for case in draft.assembly["cases"]}
    assert (cases["c50_ph5"]["kinetics_status"], cases["c50_ph5"]["condition_route"]) == ("user_data", "same_condition")
    carried = cases["c40_ph5"]
    assert (carried["kinetics_status"], carried["condition_route"]) == ("user_data", "response_law")
    assert carried["measured_condition"]["condition_id"] == "c50_ph5"
    assert carried["in_conditions_csv"] is False
    requested = {item["condition_id"]: item for item in draft.assembly["requested_conditions"]}
    assert requested["c40_ph5"]["environment_grid"] == {"temperature_C": [40.0], "ph": [5.0]}
    assert [row["condition_id"] for row in draft.conditions] == ["c50_ph5"]
    # The user's rows are kept unchanged.
    for name in ("kinetics.csv", "responses.csv", "strains.csv", "enzymes.csv", "enzyme_classes.csv", "substrates.csv"):
        assert [dict(row) for row in draft.tables()[name]] == _csv_rows(OXIDASE / name), name
    assert "environment_grid(temperature_C=[40.0], ph=[5.0])" in draft.review

    directory = tmp_path / "draft"
    draft.write(directory)
    _fill(directory)
    _run_both_temperatures(load_user_dataset(directory), tmp_path / "run")


def test_a_response_law_given_as_an_argument_works_like_responses_csv(tmp_path: Path) -> None:
    without_law = tmp_path / "oxidase_without_law"
    shutil.copytree(OXIDASE, without_law)
    (without_law / "responses.csv").unlink()
    gap_draft = assemble_user_tables(
        dataset_id="oxidase_assembly",
        fungus="strain_l1",
        substrates=["syringaldazine_like"],
        conditions=[{**C40_PH5, "temperature": 50}, C40_PH5],
        user_data=without_law,
    )
    gap = {case["condition"]: case for case in gap_draft.assembly["cases"]}["c40_ph5"]
    assert (gap["kinetics_status"], gap["measured_condition"]["condition_id"]) == ("gap", "c50_ph5")
    assert [row["condition_id"] for row in gap_draft.conditions] == ["c50_ph5", "c40_ph5"]

    law_rows = [
        {"substrate": row.pop("substrate_id"), **{k: v for k, v in row.items() if k != "strain_id"}}
        for row in _csv_rows(OXIDASE / "responses.csv")
    ]
    law_draft = assemble_user_tables(
        dataset_id="oxidase_assembly",
        fungus="strain_l1",
        substrates=["syringaldazine_like"],
        conditions=[{**C40_PH5, "temperature": 50}, C40_PH5],
        user_data=without_law,
        responses=law_rows,
    )
    carried = {case["condition"]: case for case in law_draft.assembly["cases"]}["c40_ph5"]
    assert carried["condition_route"] == "response_law"
    assert "the responses argument" in carried["reason"]
    assert [dict(row) for row in law_draft.responses] == _csv_rows(OXIDASE / "responses.csv")
    directory = tmp_path / "draft"
    law_draft.write(directory)
    _fill(directory)
    _run_both_temperatures(load_user_dataset(directory), tmp_path / "run")


def test_a_law_carries_kinetics_only_while_the_measured_condition_is_the_only_row(tmp_path: Path) -> None:
    without_law = tmp_path / "oxidase_without_law"
    shutil.copytree(OXIDASE, without_law)
    (without_law / "responses.csv").unlink()
    temperature_law = [
        {"substrate": row.pop("substrate_id"), **{k: v for k, v in row.items() if k != "strain_id"}}
        for row in _csv_rows(OXIDASE / "responses.csv")
        if row["law"] == "temperature_cardinal_rosso"
    ]
    draft = assemble_user_tables(
        dataset_id="oxidase_assembly",
        fungus="strain_l1",
        substrates=["syringaldazine_like"],
        conditions=[{**C40_PH5, "temperature": 50}, C40_PH5, {**C40_PH5, "temperature": 50, "ph": 6}],
        user_data=without_law,
        responses=temperature_law,
    )
    cases = {case["condition"]: case for case in draft.assembly["cases"]}
    # pH 6 needs a pH law, which is not given: a gap row naming the measured condition.
    assert (cases["c50_ph6"]["kinetics_status"], cases["c50_ph6"]["measured_condition"]["condition_id"]) == (
        "gap",
        "c50_ph5",
    )
    # That row would hold gap records of the same pair, so a grid run could not tell which value to reuse.
    assert (cases["c40_ph5"]["kinetics_status"], cases["c40_ph5"]["condition_route"]) == ("gap", "none")
    assert "the draft also has conditions.csv rows at c50_ph6" in cases["c40_ph5"]["reason"]
    assert [row["condition_id"] for row in draft.conditions] == ["c50_ph5", "c40_ph5", "c50_ph6"]
    assert all(item["in_conditions_csv"] for item in draft.assembly["requested_conditions"])
    directory = tmp_path / "draft"
    draft.write(directory)
    _fill(directory)
    load_user_dataset(directory)


# ---------------------------------------------------------------------------
# Rules 1 and 2: repertoire evidence and which classes act on the substrate


def test_a_class_acting_on_the_substrate_without_evidence_is_reported_and_not_added(tmp_path: Path) -> None:
    draft = assemble_user_tables(
        dataset_id="asserted_assembly",
        fungus="Asserted strain A1",
        substrates=["cellobiose"],
        conditions=[C30_PH5],
        enzyme_classes=[
            {
                "enzyme_class": "generic cellulase class",
                "evidence": "test-only assertion, not a measurement",
                "source": "tests/test_user_data_assembly.py",
            }
        ],
        kinetics_sources=[EXPORT],
        time_grid=TIME_GRID,
        registry=REGISTRY_INDEX,
    )
    (compatibility,) = draft.assembly["substrate_compatibility"]
    assert compatibility["acting"] == []
    assert [item["enzyme_class"] for item in compatibility["not_acting"]] == ["cellulase_generic"]
    (missing,) = compatibility["acting_without_evidence"]
    assert missing["enzyme_class"] == "beta_glucosidase"
    assert missing["reason"].startswith("no annotated gene and no user assertion for class beta_glucosidase")
    assert set(missing["unused_entry_ids"]) == {
        "35622",
        "38521",
        "38522",
        "38534",
        "39245",
        "39780",
        "44879",
        "44888",
        "60725",
    }
    assert draft.assembly["cases"] == []
    assert draft.kinetics == ()
    assert [row["enzyme_class"] for row in draft.enzymes] == ["cellulase_generic"]
    # No converted entry settles the stoichiometry, so the yield is the reviewer's to state.
    (substrate,) = draft.substrates
    assert substrate["product"] == "beta_D_glucose"
    assert substrate["product_yield"].startswith(REVIEW_MARKER)
    entries = {item["entry_id"]: item for item in draft.assembly["entries"]}
    assert "has no evidence for enzyme class 'beta_glucosidase'" in entries["35622"]["reason"]
    assert "Acts on it without evidence in the fungus: beta_glucosidase" in draft.review

    directory = tmp_path / "draft"
    draft.write(directory)
    _fill(directory)
    dataset = load_user_dataset(directory)
    (fungus,) = dataset.records["fungi"]
    assert fungus["enzyme_classes"] == ["asserted_assembly__cellulase_generic"]
    assert dataset.records["parameter_records"] == ()


def test_the_repertoire_never_comes_from_the_name() -> None:
    with pytest.raises(UserTablesAssemblyError, match="never takes a repertoire from a name"):
        assemble_user_tables(
            dataset_id="nameless",
            fungus="beta-glucosidase producing strain",
            substrates=["cellobiose"],
            conditions=[C30_PH5],
            kinetics_sources=[EXPORT],
            registry=REGISTRY_INDEX,
        )
    asserted = assemble_user_tables(
        dataset_id="asserted",
        fungus="Asserted strain A2",
        substrates=["cellobiose"],
        conditions=[C30_PH5],
        enzyme_classes=["EC 3.2.1.21"],
        registry=REGISTRY_INDEX,
    )
    (row,) = asserted.enzymes
    assert row["enzyme_class"] == "beta_glucosidase"
    assert row["evidence"].startswith(REVIEW_MARKER) and row["source"].startswith(REVIEW_MARKER)
    (case,) = asserted.assembly["cases"]
    assert case["kinetics_status"] == "gap"
    assert case["reason"].startswith("no source gives kinetics for beta-glucosidase on Cellobiose")


def test_loader_gap_requests_name_the_conditions_where_kinetics_were_stated(tmp_path: Path) -> None:
    directory = tmp_path / "esterase_two_conditions"
    shutil.copytree(ESTERASE, directory)
    with (directory / "conditions.csv").open("a", encoding="utf-8") as handle:
        handle.write("c45_ph7_5,45,degC,7.5,Second condition added by this test; no kinetics stated there\n")
    dataset = load_user_dataset(directory)
    prefix = "esterase_demo__strain_e1__carboxylesterase__p_nitrophenyl_butyrate__"
    request = _parameter(dataset, f"{prefix}c45_ph7_5__km__gap").provenance["measurement_request"]
    assert request == (
        "Measure km of carboxylesterase from Esterase source strain E1 on p-nitrophenyl butyrate at 45 degC, pH 7.5 "
        "(concentration units); kinetics.csv states kinetic constants of this strain, enzyme class and substrate only "
        "at c37_ph7_5 (37 degC, pH 7.5), and FungMod does not reuse kinetics measured at another condition."
    )
    # The original condition keeps its values; without other conditions nothing changes.
    km = _parameter(dataset, f"{prefix}c37_ph7_5__km")
    assert km.value.value == 150.0
    original = load_user_dataset(ESTERASE)
    assert not any(mapping["record_id"].endswith("__gap") for mapping in original.records["parameter_records"])


def test_enzyme_class_acts_on_is_the_loader_rule() -> None:
    assert enzyme_class_acts_on(
        target_bond_classes=("b", "a"),
        compatible_substrate_classes=("s",),
        substrate_class="s",
        bond_classes=("a", "c"),
    ) == ("a",)
    assert (
        enzyme_class_acts_on(
            target_bond_classes=("a",), compatible_substrate_classes=("t",), substrate_class="s", bond_classes=("a",)
        )
        == ()
    )
    assert (
        enzyme_class_acts_on(
            target_bond_classes=("a",), compatible_substrate_classes=("s",), substrate_class="s", bond_classes=("b",)
        )
        == ()
    )


# ---------------------------------------------------------------------------
# Rule 3a, 3d: the user's own data wins; several candidates are a conflict


def test_the_user_dataset_is_kept_unchanged_and_wins_over_literature() -> None:
    draft = assemble_user_tables(
        dataset_id="reentry_assembly",
        fungus="Os3BGlu6 source",
        substrates=["cellobiose"],
        conditions=[C30_PH5],
        user_data=LITERATURE,
        kinetics_sources=[EXPORT],
    )
    (case,) = draft.assembly["cases"]
    assert case["kinetics_status"] == "user_data"
    assert case["source_ids"] == ["user dataset reaction_618_reentry kinetics.csv rows 2, 3, 4, 5"]
    # The strain's species is Oryza sativa: the rice entries at the same condition are weaker evidence.
    assert "35622" in case["reason"] and "weaker evidence" in case["reason"]
    for name in ("strains.csv", "enzymes.csv", "substrates.csv", "conditions.csv", "kinetics.csv"):
        assert [dict(row) for row in draft.tables()[name]] == _csv_rows(LITERATURE / name), name
    assert draft.converted_entry_ids == ()
    assert draft.manifest["simulation"] == {"duration": 10, "units": "hour", "points": 61}


def test_a_loaded_user_dataset_assembles_like_its_directory() -> None:
    arguments: dict[str, Any] = {
        "dataset_id": "esterase_assembly",
        "fungus": "E1 esterase strain",
        "substrates": ["p_nitrophenyl_butyrate"],
        "conditions": [{"temperature": 37, "temperature_units": "degC", "ph": 7.5}],
    }
    from_directory = assemble_user_tables(user_data=ESTERASE, **arguments)
    from_dataset = assemble_user_tables(user_data=load_user_dataset(ESTERASE), **arguments)
    assert from_directory.file_texts() == from_dataset.file_texts()
    (case,) = from_dataset.assembly["cases"]
    assert (case["strain_id"], case["kinetics_status"]) == ("strain_e1", "user_data")


def test_several_candidates_for_one_case_are_a_conflict_until_entry_ids_chooses() -> None:
    conflict = _g1(entry_ids=None)
    (case,) = conflict.assembly["cases"]
    assert case["kinetics_status"] == "conflict"
    assert set(case["source_ids"]) == {"SABIO-RK EntryID 35622", "SABIO-RK EntryID 39780", "SABIO-RK EntryID 44879"}
    assert "does not choose between them (select one with entry_ids)" in case["reason"]
    assert conflict.kinetics == ()
    entries = {item["entry_id"]: item for item in conflict.assembly["entries"]}
    assert {entries[entry_id]["use"] for entry_id in ("35622", "39780", "44879")} == {"listed"}

    chosen = _g1(entry_ids=["44879"])
    (case,) = chosen.assembly["cases"]
    assert (case["kinetics_status"], case["source_ids"]) == ("transferred_estimate", ["SABIO-RK EntryID 44879"])

    elsewhere = _g1(entry_ids=None, conditions=[{**C30_PH5, "temperature": 45}])
    (case,) = elsewhere.assembly["cases"]
    assert case["kinetics_status"] == "gap"
    assert "kinetics are stated only at other conditions" in case["reason"]
    assert {"SABIO-RK EntryID 38521", "SABIO-RK EntryID 60725"} <= set(case["source_ids"])
    assert elsewhere.kinetics == ()


# ---------------------------------------------------------------------------
# A materially different, non-cellulose case


def test_a_new_substrate_and_a_non_cellulose_class_follow_the_same_rules(
    base_registry: FungModRegistry,
    tmp_path: Path,
) -> None:
    extended = _with_test_only_glucoamylase(base_registry)
    maltose = _csv_rows(GENOME / "substrates.csv")[1]
    described = {key: value for key, value in maltose.items() if key not in {"registry_substrate", "yield_basis"}}
    described["substrate"] = described.pop("name")
    draft = _g1(
        dataset_id="maltose_assembly",
        substrates=[described],
        kinetics_sources=(),
        entry_ids=None,
        registry=extended,
        design={"substrate_initial_concentration": {"value": 5, "units": "mM"}},
        time_grid=TIME_GRID,
        annotation_source=ANNOTATION_SOURCE,
    )
    (compatibility,) = draft.assembly["substrate_compatibility"]
    assert [item["enzyme_class"] for item in compatibility["acting"]] == ["glucoamylase"]
    (case,) = draft.assembly["cases"]
    assert (case["enzyme_class"], case["substrate_id"], case["kinetics_status"]) == ("glucoamylase", "maltose", "gap")
    assert case["design_rows"] == ["substrate_initial_concentration"]
    (row,) = draft.substrates
    assert {
        key: row[key] for key in ("substrate_class", "physical_state", "bond_classes", "product", "product_yield")
    } == {
        "substrate_class": "maltose",
        "physical_state": "dissolved",
        "bond_classes": "alpha_1_4_glycosidic",
        "product": "D_glucose",
        "product_yield": "2",
    }
    directory = tmp_path / "draft"
    draft.write(directory)
    _fill(directory)
    dataset = load_user_dataset(directory, registry=extended)
    request = _parameter(
        dataset, "maltose_assembly__genome_annotated_strain_g1__glucoamylase__maltose__c30_ph5__km__gap"
    )
    assert request.provenance["measurement_request"].startswith(
        f"Measure km of glucoamylase from {G1} on maltose at 30 degC, pH 5 (mM)"
    )

    undescribed = _g1(
        dataset_id="maltose_assembly", substrates=["maltose"], kinetics_sources=(), entry_ids=None, registry=extended
    )
    (compatibility,) = undescribed.assembly["substrate_compatibility"]
    assert "REVIEW fields" in compatibility["undetermined"]
    assert undescribed.assembly["cases"] == []
    review_columns = {item["column"] for item in undescribed.review_fields if item["file"] == "substrates.csv"}
    assert review_columns == {"substrate_class", "physical_state", "bond_classes", "product", "product_yield", "source"}


# ---------------------------------------------------------------------------
# Determinism, routes, arguments and exports


def test_the_same_inputs_give_byte_identical_files(tmp_path: Path) -> None:
    first = _g1(conditions=[C30_PH5, C40_PH5]).write(tmp_path / "first")
    second = _g1(conditions=[C30_PH5, C40_PH5]).write(tmp_path / "second")
    assert sorted(first) == sorted(second)
    assert "annotations/strain_g1_overview.txt" in first
    for name, path in first.items():
        assert path.read_bytes() == second[name].read_bytes(), name
    assert (tmp_path / "first" / "annotations" / "strain_g1_overview.txt").read_bytes() == ANNOTATION.read_bytes()
    assert _g1().to_dict() == _g1().to_dict()
    with pytest.raises(UserTablesAssemblyError, match="overwrite=True"):
        _g1().write(tmp_path / "first")


def test_explicit_condition_ids_name_the_rows() -> None:
    draft = _g1(
        conditions=[
            {**C30_PH5, "condition_id": "assay_a", "notes": "first assay"},
            {**C40_PH5, "condition_id": "assay_b"},
        ]
    )
    assert [(row["condition_id"], row["notes"]) for row in draft.conditions] == [
        ("assay_a", "first assay; SABIO-RK assay buffer (EntryID 35622: 100 mM sodium acetate)"),
        ("assay_b", "Requested condition"),
    ]
    assert {row["condition_id"] for row in draft.kinetics} == {"assay_a"}
    assert [case["condition"] for case in draft.assembly["cases"]] == ["assay_a", "assay_b"]
    assert draft.assembly["cases"][1]["measured_condition"]["condition_id"] == "assay_a"


def test_proposal_reaction_id_and_export_routes_assemble_the_same_tables() -> None:
    proposal = source_proposal(provider="sabiork", reaction_id="618")
    tables = [_g1(kinetics_sources=[source]).tables() for source in (proposal, "618", EXPORT)]
    assert tables[0] == tables[1] == tables[2]


def test_every_case_carries_the_report_fields() -> None:
    draft = _g1(conditions=[C30_PH5, C40_PH5])
    as_dict = draft.to_dict()
    assert as_dict["kind"] == "fungmod_assembled_user_tables_draft"
    assert as_dict["assembly"]["cases"] == [dict(case) for case in draft.assembly["cases"]]
    for case in draft.assembly["cases"]:
        for key in (
            "fungus",
            "enzyme_class",
            "substrate",
            "condition",
            "class_evidence",
            "kinetics_status",
            "source_ids",
            "reason",
        ):
            assert case[key] not in (None, ""), key
        assert case["kinetics_status"] in ASSEMBLY_STATUSES
        assert f"| {case['enzyme_class']} | {case['substrate_id']} | {case['condition']} " in draft.review
    assert as_dict["annotation_files"] == {"annotations/strain_g1_overview.txt": draft.assembly["annotation"]["sha256"]}


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"dataset_id": "Bad-Id"}, "lowercase snake_case"),
        ({"fungus": " "}, "nonblank name"),
        ({"conditions": []}, "does not invent conditions"),
        ({"conditions": [{"temperature": 30, "ph": 5}]}, "needs temperature_units"),
        ({"conditions": [C30_PH5, {**C30_PH5, "notes": "again"}]}, "repeats the condition"),
        ({"conditions": [{**C30_PH5, "ph": 15}]}, "between 0 and 14"),
        ({"substrates": ["cellulose film"]}, "dissolved substrates only"),
        ({"substrates": [{"substrate": "cellobiose", "bond_classes": "x"}]}, "referenced, not copied"),
        ({"entry_ids": ["99999999"]}, "are not in the kinetics sources"),
        ({"entry_ids": "35622"}, "not one string"),
        ({"annotation_tool": None}, "are given together"),
        ({"annotation_tool": "dbCAN"}, "without a version"),
        ({"design": {"km": {"value": 1, "units": "mM"}}}, "kinetic constants come from the source"),
        ({"time_grid": {"duration": 0, "units": "hour", "points": 61}}, "positive number"),
        ({"responses": [{"law": "ph_gaussian"}]}, "needs enzyme_class"),
        ({"user_data": ESTERASE}, "names no strain of the user dataset"),
    ],
)
def test_invalid_arguments_are_refused(overrides: Mapping[str, Any], message: str) -> None:
    with pytest.raises(UserTablesAssemblyError, match=message):
        _g1(**overrides)


def test_assembly_errors_are_source_errors() -> None:
    assert issubclass(UserTablesAssemblyError, UserTablesSourceError)


def test_write_refuses_the_registry_directory(tmp_path: Path) -> None:
    with pytest.raises(UserTablesAssemblyError, match="data_registry"):
        _g1().write(tmp_path / "data_registry" / "draft")


def test_public_names_are_exported() -> None:
    for name in ("assemble_user_tables", "AssembledTablesDraft", "UserTablesAssemblyError"):
        assert name in fungal_model.__all__
        assert getattr(fungal_model, name) is getattr(fungal_model_api, name)


# ---------------------------------------------------------------------------
# Helpers


def _fill(directory: Path) -> None:
    """Fill every REVIEW field of a written draft with the test reviewer's answers."""

    path = directory / "user_dataset.yml"
    manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    manifest["contributor"] = "Test reviewer"
    if isinstance(manifest["simulation"]["duration"], str):
        manifest["simulation"] = dict(TIME_GRID)
    path.write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8")
    for table in sorted(directory.glob("*.csv")):
        with table.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = list(reader.fieldnames or [])
            rows = list(reader)
        changed = False
        for row in rows:
            for column in columns:
                if row[column].startswith(REVIEW_MARKER):
                    row[column] = REVIEW_VALUES[(table.name, column)]
                    changed = True
        if changed:
            with table.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
    assert REVIEW_MARKER not in "".join(p.read_text(encoding="utf-8") for p in directory.glob("*.csv"))


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [{key: (value or "").strip() for key, value in row.items()} for row in csv.DictReader(handle)]


def _parameter(dataset: Any, record_id: str) -> Any:
    mapping = next(item for item in dataset.records["parameter_records"] if item["record_id"] == record_id)
    return load_parameter_record_mapping(mapping)


def _assert_substrate_degrades(rows: list[dict[str, Any]]) -> None:
    samples = {row["sample_id"] for row in rows}
    assert samples
    for sample_id in samples:
        substrate = [
            float(row["value"]) for row in rows if row["sample_id"] == sample_id and row["state_role"] == "substrate"
        ]
        assert substrate[-1] < substrate[0]
        assert all(later <= earlier + 1e-12 for earlier, later in itertools.pairwise(substrate))


def _run_both_temperatures(dataset: Any, output: Path) -> None:
    study = virtual_experiment(
        fungi="strain_l1",
        substrates="syringaldazine_like",
        environments=environment_grid(temperature_C=[40, 50], ph=[5.0]),
        user_data=dataset,
    )
    assert [report.status for report in study.preflight(mode="exploratory")] == ["modelable", "modelable"]
    result = study.simulate(mode="exploratory", n_samples=1, seed=7, output_dir=output, quicklook=False)
    rates: dict[float, float] = {}
    for row in result.time_series():
        assert row["environment_effect_status"] == "active_response_model"
        if row["state_role"] == "process_rate" and int(row["time_index"]) == 0:
            rates[float(row["temperature_C"])] = float(row["value"])
    assert set(rates) == {40.0, 50.0}
    assert rates[40.0] / rates[50.0] == pytest.approx(_ctmi(40.0, T_MIN, T_OPT, T_MAX), rel=1e-9)


def _ctmi(temperature: float, minimum: float, optimum: float, maximum: float) -> float:
    """Rosso et al. (1993) cardinal temperature model with inflection (independent of the implementation)."""

    numerator = (temperature - maximum) * (temperature - minimum) ** 2
    denominator = (optimum - minimum) * (
        (optimum - minimum) * (temperature - optimum) - (optimum - maximum) * (optimum + minimum - 2.0 * temperature)
    )
    return numerator / denominator


def _with_test_only_glucoamylase(base: FungModRegistry) -> FungModRegistry:
    """The shipped registry plus a test-only glucoamylase class record (not shipped, no kinetics)."""

    record = load_registry_record_mapping(
        "enzyme_classes",
        {
            "record_id": "glucoamylase",
            "name": "glucoamylase",
            "ec_number": "3.2.1.3",
            "maturity": "exploratory_metadata",
            "provenance": {
                "source": "In-memory registry extension of tests/test_user_data_assembly.py; not a shipped record",
                "confidence_level": "exploratory_assumption",
            },
            "target_bond_classes": ["alpha_1_4_glycosidic"],
            "compatible_substrate_classes": ["maltose"],
            "compatible_processes": ["homogeneous_michaelis_menten"],
            "notes": "Exists only in this test module to exercise a resolved class on a non-cellulose substrate.",
        },
    )
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
