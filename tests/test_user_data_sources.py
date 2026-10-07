"""SABIO-RK kinetic-law entries drafted into user-dataset tables (USERDATA-005).

The conversions run on the real frozen SABIO-RK Reaction 618 snapshot in
``data/kinetic_records/sabiork/case_001_reaction_618_beta_glucosidase``. A few
format tests below derive a modified copy of one real entry in a temporary
directory (a Vmax in place of kcat, an unparseable unit); those copies test the
converter's routing only and are not presented as measurements.
"""

from __future__ import annotations

import copy
import csv
import json
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml

import fungal_model
from fungal_model import (
    UserDataError,
    UserTablesDraft,
    UserTablesSourceError,
    load_user_dataset,
    source_proposal,
    user_tables_from_sabiork,
    virtual_experiment,
)
from fungal_model.api import user_data_sources
from fungal_model.api.user_data import REVIEW_MARKER
from fungal_model.api.user_data_sources import SABIORK_TEMPERATURE_UNITS, SABIORK_UNIT_SPELLINGS
from fungal_model.core.units import Q_, units_are_compatible
from fungal_model.registry.loaders import load_parameter_record_mapping
from fungal_model.registry.records import ParameterRecord
from fungal_model.sources.sabiork import fetch as sabiork_fetch

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "data" / "kinetic_records" / "sabiork" / "case_001_reaction_618_beta_glucosidase" / "raw"
EXPORT = SNAPSHOT / "kinlaw_entries_reaction_618.json"
LITERATURE = ROOT / "tests" / "fixtures" / "user_data" / "literature_reentry"
REENTRY_DESIGN = {
    # The literature_reentry fixture's virtual assay design (its design rows), stated here as design values.
    "substrate_initial_concentration": {"value": 10, "units": "mM"},
    "enzyme_concentration": {"value": 1e-3, "units": "mM"},
}
PH_LAW_ENTRIES = ("38522", "38528", "38529", "38530", "38531", "38532", "38533", "38534")


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_network_is_used(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Drafting user tables from SABIO-RK must not touch the network.")

    monkeypatch.setattr(urllib.request, "urlopen", fail_if_network_is_used)
    monkeypatch.setattr(sabiork_fetch, "urlopen", fail_if_network_is_used)


@pytest.fixture(scope="module")
def all_618() -> UserTablesDraft:
    return user_tables_from_sabiork("618", dataset_id="reaction_618_draft")


def _fill_manifest(directory: Path) -> None:
    path = directory / "user_dataset.yml"
    manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    manifest["contributor"] = "Test reviewer"
    manifest["simulation"] = {"duration": 10, "units": "hour", "points": 61}
    path.write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _set_cell(directory: Path, table: str, row: int, column: str, value: str) -> None:
    path = directory / table
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[row - 2][column] = value
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _parameters(dataset: Any) -> dict[str, ParameterRecord]:
    return {
        str(mapping["record_id"]).split("__", 1)[1]: load_parameter_record_mapping(mapping)
        for mapping in dataset.records["parameter_records"]
    }


def _role(parameters: Mapping[str, ParameterRecord], quantity: str) -> ParameterRecord:
    matches = [record for key, record in parameters.items() if key.endswith(f"__{quantity}")]
    assert len(matches) == 1, (quantity, sorted(parameters))
    return matches[0]


# ---------------------------------------------------------------------------
# The selected entry reproduces the hand-entered literature re-entry


def test_entry_35622_reproduces_the_literature_reentry_fixture(tmp_path: Path) -> None:
    draft = user_tables_from_sabiork(
        "618",
        dataset_id="entry_35622_draft",
        entry_ids=["35622"],
        design=REENTRY_DESIGN,
    )
    assert draft.converted_entry_ids == ("35622",)
    # The product and its yield come from the reaction equation without review.
    assert draft.substrates[0]["product"] == "beta_D_glucose"
    assert draft.substrates[0]["product_yield"] == "2"
    review_columns = {(item["file"], item["column"]) for item in draft.review_fields}
    assert review_columns == {
        ("user_dataset.yml", "contributor"),
        ("user_dataset.yml", "simulation.duration"),
        ("user_dataset.yml", "simulation.units"),
        ("user_dataset.yml", "simulation.points"),
    }

    directory = tmp_path / "draft"
    draft.write(directory)
    _fill_manifest(directory)
    drafted = _parameters(load_user_dataset(directory))
    fixture = _parameters(load_user_dataset(LITERATURE))

    for quantity in ("km", "kcat"):
        mine, theirs = _role(drafted, quantity), _role(fixture, quantity)
        assert mine.value.kind == theirs.value.kind == "exact"
        assert mine.value.value == theirs.value.value
        assert mine.value.units == theirs.value.units
        assert mine.maturity == theirs.maturity == "user_reported_literature"
        mine_provenance = mine.provenance["fungmod_user_dataset"]
        theirs_provenance = theirs.provenance["fungmod_user_dataset"]
        assert mine_provenance["sd"] == theirs_provenance["sd"]
        assert mine_provenance["evidence_type"] == theirs_provenance["evidence_type"] == "literature"
        source = str(mine.value.source)
        assert source == "SABIO-RK EntryID 35622 (Seshadri S et al. 2009, PMID 19587102)"
        for citation in ("EntryID 35622", "Seshadri", "2009", "19587102"):
            assert citation in str(theirs.value.source)
        assert mine.provenance["measurement_method"] == "SABIO-RK kinetic law 35622, Michaelis-Menten"
    for quantity in ("substrate_initial_concentration", "enzyme_concentration"):
        mine, theirs = _role(drafted, quantity), _role(fixture, quantity)
        assert Q_(mine.value.value, mine.value.units) == Q_(theirs.value.value, theirs.value.units)
        assert mine.maturity == theirs.maturity == "user_design_value"


def test_drafted_entry_simulates_like_the_hand_entered_fixture(tmp_path: Path) -> None:
    draft = user_tables_from_sabiork("618", dataset_id="entry_35622_draft", entry_ids=["35622"], design=REENTRY_DESIGN)
    directory = tmp_path / "draft"
    draft.write(directory)
    _fill_manifest(directory)

    trajectories = []
    for fungi, user_data, label in (
        ("oryza_sativa_in_escherichia_coli_origami_de3", directory, "drafted"),
        ("Os3BGlu6 source", LITERATURE, "fixture"),
    ):
        study = virtual_experiment(fungi=fungi, substrates="cellobiose", environments="c30_ph5", user_data=user_data)
        assert study.preflight(mode="scientific")[0].status == "modelable"
        result = study.simulate(mode="scientific", output_dir=tmp_path / label, quicklook=False)
        trajectories.append(
            [
                (row["time"], float(row["value"]))
                for row in result.time_series()
                if row["state_role"] in {"substrate", "product"}
            ]
        )
    drafted, fixture = trajectories
    assert len(drafted) == len(fixture) == 2 * 61
    for (time_a, value_a), (time_b, value_b) in zip(drafted, fixture, strict=True):
        assert time_a == time_b
        assert value_a == pytest.approx(value_b, rel=1e-9, abs=1e-12)


# ---------------------------------------------------------------------------
# All of Reaction 618: every entry converted or listed with a reason


def test_every_entry_of_reaction_618_is_converted_or_listed(all_618: UserTablesDraft) -> None:
    export = json.loads(EXPORT.read_text(encoding="utf-8"))
    entry_ids = [str(entry["id"]) for entry in export["data"]]
    assert len(entry_ids) == 29
    listed = {item["entry_id"]: item["reason"] for item in all_618.not_converted}
    assert set(all_618.converted_entry_ids).isdisjoint(listed)
    assert set(all_618.converted_entry_ids) | set(listed) == set(entry_ids)
    assert all(reason.strip() for reason in listed.values())
    assert all_618.converted_entry_ids == ("38521", "39245", "44879", "44888", "60725")
    for entry_id, reason in listed.items():
        assert f"| {entry_id} |" in all_618.review, entry_id
        assert reason.split(";")[0].replace("|", "\\|") in all_618.review

    # Mutants, isoenzyme conflicts and unresolved EC numbers are the explicit reasons.
    assert listed["38523"].startswith("mutant enzyme (BGL1A V173C)")
    assert "conflict: EntryIDs 35622, 39780" in listed["35622"]
    assert "conflict: EntryIDs 38522, 38534" in listed["38534"]
    assert "EC 3.2.1.74" in listed["39470"] and "does not resolve" in listed["39470"]
    assert "no Km, kcat or Vmax could be converted" in listed["35633"]


def test_reaction_618_lists_the_ph_dependent_laws(all_618: UserTablesDraft) -> None:
    section = all_618.review.split("## pH-ionization laws", 1)[1].split("\n## ", 1)[0]
    assert "pH-ionization laws are not importable as user data yet" in section
    for entry_id in PH_LAW_ENTRIES:
        assert f"| {entry_id} | Michaelis-Menten (pH-dependent) |" in section
    assert "pKe1 = 4.4" in section


def test_reaction_618_units_are_kept_or_listed(all_618: UserTablesDraft) -> None:
    for row in all_618.kinetics:
        Q_(1.0, row["units"])  # every written unit parses with the unit registry
    written: dict[str, int] = {}
    for row in all_618.kinetics:
        entry_id = row["source"].split()[2]  # "SABIO-RK EntryID <id> (...)"
        written[entry_id] = written.get(entry_id, 0) + 1
    listed: dict[str, list[str]] = {}
    for item in all_618.not_converted_parameters:
        listed.setdefault(item["entry_id"], []).append(item["parameter"])
    export = json.loads(EXPORT.read_text(encoding="utf-8"))
    for entry in export["data"]:
        entry_id = str(entry["id"])
        if entry_id not in all_618.converted_entry_ids:
            continue
        names = [parameter["name"] for parameter in entry["kineticlaw"]["parameter"]]
        # Every parameter of a converted entry is one written row or one listed parameter.
        assert written[entry_id] + len(listed.get(entry_id, [])) == len(names), entry_id
        assert set(listed.get(entry_id, [])) <= set(names), entry_id


def test_reaction_618_draft_loads_once_reviewed(all_618: UserTablesDraft, tmp_path: Path) -> None:
    directory = tmp_path / "all"
    all_618.write(directory)
    _fill_manifest(directory)
    dataset = load_user_dataset(directory)
    parameters = _parameters(dataset)
    km = parameters[
        "phanerochaete_chrysosporium_in_escherichia_coli_rosetta_de3__beta_glucosidase__cellobiose__c30_ph6_5__km"
    ]
    assert km.value.value == 6.8 and km.value.units == "mM"
    concentration = parameters[
        "oryza_sativa_in_escherichia_coli_origami_de3_cell__beta_glucosidase__cellobiose__c30_ph5__enzyme_concentration"
    ]
    assert (concentration.value.kind, concentration.value.lower, concentration.value.upper) == ("range", 20.0, 100.0)
    assert concentration.value.units == "nM"
    conditions = {row["condition_id"]: row for row in all_618.conditions}
    assert conditions["c30_ph6_5"]["notes"] == "SABIO-RK assay buffer (EntryID 38521: 50 mM MES)"
    assert {row["temperature_units"] for row in all_618.conditions} == {"degC"}


# ---------------------------------------------------------------------------
# REVIEW fields, pH-dependent laws and enzyme classes


def test_an_unfilled_review_field_is_refused_by_name(tmp_path: Path) -> None:
    draft = user_tables_from_sabiork("618", dataset_id="ph_law_draft", entry_ids=["38522"])
    directory = tmp_path / "draft"
    draft.write(directory)

    with pytest.raises(UserDataError) as error:
        load_user_dataset(directory)
    named = {(issue["file"], issue["row"], issue["column"]) for issue in error.value.issues}
    assert named == {
        ("user_dataset.yml", None, "contributor"),
        ("user_dataset.yml", None, "simulation.duration"),
        ("user_dataset.yml", None, "simulation.units"),
        ("user_dataset.yml", None, "simulation.points"),
        ("conditions.csv", 2, "ph"),
    }
    assert "simulation.duration" in str(error.value)
    assert all(issue["message"].startswith("Unfilled review field") for issue in error.value.issues)

    _fill_manifest(directory)
    with pytest.raises(UserDataError) as error:
        load_user_dataset(directory)
    assert [(issue["file"], issue["row"], issue["column"]) for issue in error.value.issues] == [
        ("conditions.csv", 2, "ph")
    ]
    assert "Unfilled review field ph" in str(error.value)
    assert "SABIO-RK gives pH 4 to 8, a range" in str(error.value)

    _set_cell(directory, "conditions.csv", 2, "ph", "6.5")
    dataset = load_user_dataset(directory)
    assert dataset.dataset_id == "ph_law_draft"


def test_a_review_marker_in_free_text_is_refused_too(tmp_path: Path) -> None:
    draft = user_tables_from_sabiork("618", dataset_id="entry_35622_draft", entry_ids=["35622"])
    directory = tmp_path / "draft"
    draft.write(directory)
    _fill_manifest(directory)
    _set_cell(directory, "kinetics.csv", 2, "source", f"{REVIEW_MARKER} check the citation")
    with pytest.raises(UserDataError) as error:
        load_user_dataset(directory)
    assert [(issue["file"], issue["row"], issue["column"]) for issue in error.value.issues] == [
        ("kinetics.csv", 2, "source")
    ]


def test_loader_refuses_a_review_marker_in_any_manifest_value(tmp_path: Path) -> None:
    directory = tmp_path / "literature_reentry"
    directory.mkdir()
    for path in LITERATURE.iterdir():
        (directory / path.name).write_bytes(path.read_bytes())
    manifest = yaml.safe_load((directory / "user_dataset.yml").read_text(encoding="utf-8"))
    manifest["simulation"] = f"{REVIEW_MARKER} choose the time grid"
    (directory / "user_dataset.yml").write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    with pytest.raises(UserDataError) as error:
        load_user_dataset(directory)
    # Reported once, as unfilled; not also as a missing simulation mapping.
    assert [(issue["file"], issue["column"]) for issue in error.value.issues] == [("user_dataset.yml", "simulation")]


def test_ph_ionization_law_converts_only_km_and_kcat_at_the_entry_ph() -> None:
    draft = user_tables_from_sabiork("618", dataset_id="ph_law_draft", entry_ids=["38522"])
    quantities = {row["quantity"]: row for row in draft.kinetics}
    assert set(quantities) == {"km", "kcat"}
    assert (quantities["km"]["value"], quantities["km"]["units"]) == ("6.8", "mM")
    assert (quantities["kcat"]["value"], quantities["kcat"]["units"]) == ("1.81", "s^(-1)")
    assert "parameter Km0" in quantities["km"]["method"]
    assert quantities["kcat"]["method"].startswith("SABIO-RK kinetic law 38522, Michaelis-Menten (pH-dependent)")
    (condition,) = draft.conditions
    assert condition["condition_id"] == "c30_ph4_to_8"
    assert condition["ph"].startswith(REVIEW_MARKER)
    pka = [item for item in draft.not_converted_parameters if item["parameter_type"] == "pKa"]
    assert [item["parameter"] for item in pka] == ["pKe1", "pKe2", "pKes1", "pKes2"]
    assert all("pH-ionization law not importable as user data yet" in item["reason"] for item in pka)
    assert "| 38522 | Michaelis-Menten (pH-dependent) |" in draft.review
    assert not any("cardinal" in row["quantity"] for row in draft.kinetics)


def test_an_unresolved_ec_number_is_listed_and_not_invented(tmp_path: Path) -> None:
    draft = user_tables_from_sabiork("618", dataset_id="ec_draft", entry_ids=["35622", "39470"])
    assert draft.converted_entry_ids == ("35622",)
    (listed,) = draft.not_converted
    assert listed["entry_id"] == "39470"
    assert "EC 3.2.1.74 (glucan 1,4-beta-glucosidase) does not resolve to a registry enzyme class" in listed["reason"]
    assert draft.enzyme_classes == ()
    assert {row["enzyme_class"] for row in draft.enzymes} == {"beta_glucosidase"}
    assert "enzyme_classes.csv" not in draft.tables()
    paths = draft.write(tmp_path / "plain")
    assert "enzyme_classes.csv" not in paths
    assert "EC 3.2.1.74" in (tmp_path / "plain" / "review.md").read_text(encoding="utf-8")

    proposed = user_tables_from_sabiork(
        "618", dataset_id="ec_draft", entry_ids=["35622", "39470"], propose_enzyme_classes=True
    )
    assert proposed.converted_entry_ids == ("35622", "39470")
    (row,) = proposed.enzyme_classes
    assert (row["class_id"], row["ec_number"]) == ("glucan_1_4_beta_glucosidase", "3.2.1.74")
    assert row["target_bond_classes"].startswith(REVIEW_MARKER)
    assert row["compatible_substrate_classes"].startswith(REVIEW_MARKER)
    directory = tmp_path / "proposed"
    proposed.write(directory)
    _fill_manifest(directory)
    with pytest.raises(UserDataError) as error:
        load_user_dataset(directory)
    assert {(issue["file"], issue["column"]) for issue in error.value.issues} == {
        ("enzyme_classes.csv", "target_bond_classes"),
        ("enzyme_classes.csv", "compatible_substrate_classes"),
    }


# ---------------------------------------------------------------------------
# Input routes, mapping options and determinism


def test_proposal_export_file_and_reaction_id_give_the_same_tables() -> None:
    proposal = source_proposal(provider="sabiork", reaction_id="618")
    from_proposal = user_tables_from_sabiork(proposal, dataset_id="routes")
    from_file = user_tables_from_sabiork(EXPORT, dataset_id="routes")
    from_reaction = user_tables_from_sabiork("618", dataset_id="routes")
    assert from_proposal.tables() == from_file.tables() == from_reaction.tables()
    assert "query SabioReactionID:618" in from_proposal.manifest["source"]
    assert "the SABIO-RK export file kinlaw_entries_reaction_618.json" in from_file.manifest["source"]

    narrowed = source_proposal(provider="sabiork", reaction_id="618", entry_id="35622")
    assert user_tables_from_sabiork(narrowed, dataset_id="routes").converted_entry_ids == ("35622",)


def test_written_files_are_byte_identical_for_the_same_input(all_618: UserTablesDraft, tmp_path: Path) -> None:
    again = user_tables_from_sabiork("618", dataset_id="reaction_618_draft")
    first = all_618.write(tmp_path / "first")
    second = again.write(tmp_path / "second")
    assert sorted(first) == sorted(second) == sorted(
        ["user_dataset.yml", "strains.csv", "enzymes.csv", "substrates.csv", "conditions.csv", "kinetics.csv", "review.md"]
    )
    for name, path in first.items():
        assert path.read_bytes() == second[name].read_bytes(), name
    with pytest.raises(UserTablesSourceError, match="overwrite=True"):
        again.write(tmp_path / "first")
    again.write(tmp_path / "first", overwrite=True)
    assert (tmp_path / "first" / "kinetics.csv").read_bytes() == second["kinetics.csv"].read_bytes()


def test_strain_id_for_organism_names_the_strain() -> None:
    draft = user_tables_from_sabiork(
        "618",
        dataset_id="mapped",
        entry_ids=["35622"],
        strain_id_for_organism={"Oryza sativa": "os3bglu6_source"},
    )
    assert [row["strain_id"] for row in draft.strains] == ["os3bglu6_source"]
    assert {row["strain_id"] for row in draft.kinetics} == {"os3bglu6_source"}
    assert "mapped by strain_id_for_organism" in draft.review
    # A generated strain ID never coincides with an ID given to another organism.
    clash = user_tables_from_sabiork(
        "618",
        dataset_id="mapped",
        entry_ids=["35622", "39245"],
        strain_id_for_organism={"Oryza sativa": "hordeum_vulgare"},
    )
    assert [row["strain_id"] for row in clash.strains] == ["hordeum_vulgare", "hordeum_vulgare_2"]
    with pytest.raises(UserTablesSourceError, match="that no selected entry has"):
        user_tables_from_sabiork(
            "618", dataset_id="mapped", entry_ids=["35622"], strain_id_for_organism={"Hordeum vulgare": "barley"}
        )
    with pytest.raises(UserTablesSourceError, match="single underscores"):
        user_tables_from_sabiork("618", dataset_id="mapped", strain_id_for_organism={"Oryza sativa": "os source"})


def test_invalid_arguments_are_refused() -> None:
    with pytest.raises(UserTablesSourceError, match="not in the source"):
        user_tables_from_sabiork("618", dataset_id="bad", entry_ids=["99999999"])
    with pytest.raises(UserTablesSourceError, match="not one string"):
        user_tables_from_sabiork("618", dataset_id="bad", entry_ids="35622")
    with pytest.raises(UserTablesSourceError, match="lowercase snake_case"):
        user_tables_from_sabiork("618", dataset_id="Bad-Id")
    with pytest.raises(UserTablesSourceError, match="kinetic constants come from the source"):
        user_tables_from_sabiork("618", dataset_id="bad", design={"km": {"value": 1, "units": "mM"}})
    with pytest.raises(UserTablesSourceError, match="enzyme mass per volume"):
        user_tables_from_sabiork("618", dataset_id="bad", design={"enzyme_loading": {"value": 1, "units": "mM"}})
    with pytest.raises(UserTablesSourceError, match="Nothing is fetched"):
        user_tables_from_sabiork("4242424", dataset_id="bad", cache_dir=ROOT / "no_such_cache")
    with pytest.raises(UserTablesSourceError, match="No SABIO-RK entry could be converted"):
        user_tables_from_sabiork("618", dataset_id="bad", entry_ids=["38523"])


# ---------------------------------------------------------------------------
# Format tests on a derived copy of one real entry: Vmax routing and units


def _derived_export(tmp_path: Path, parameter_updates: Mapping[str, Mapping[str, Any]]) -> Path:
    """Copy the snapshot's EntryID 35622 and replace named parameters (format test input only)."""

    export = json.loads(EXPORT.read_text(encoding="utf-8"))
    entry = copy.deepcopy(next(item for item in export["data"] if item["id"] == 35622))
    parameters = []
    for parameter in entry["kineticlaw"]["parameter"]:
        update = parameter_updates.get(parameter["name"])
        if update is None:
            parameters.append(parameter)
        elif update:
            parameters.append({**parameter, **update})
    entry["kineticlaw"]["parameter"] = parameters
    path = tmp_path / "derived_export.json"
    path.write_text(json.dumps({"meta": {"total_count": 1}, "data": [entry]}), encoding="utf-8")
    return path


def _vmax(units: str, value: float = 12.0) -> dict[str, Any]:
    return {
        "name": "Vmax",
        "parameter_type": {"id": 1, "name": "Vmax", "sbo_term": "SBO:0000186"},
        "species": {"species_ref_type": "Species", "species_key": None, "ref_status_actual": None},
        "start_value": value,
        "end_value": None,
        "standard_deviation": None,
        "unit": {"id": 0, "name": units, "n_name": None},
        "comment": "-",
    }


def test_vmax_per_enzyme_mass_becomes_a_specific_activity_with_a_review_loading(tmp_path: Path) -> None:
    path = _derived_export(tmp_path, {"kcat": _vmax("µmol*min^(-1)*mg^(-1)")})
    draft = user_tables_from_sabiork(path, dataset_id="specific_activity_format")
    quantities = {row["quantity"]: row for row in draft.kinetics}
    assert quantities["specific_activity"]["value"] == "12"
    assert quantities["specific_activity"]["units"] == "µmol*min^(-1)*mg^(-1)"
    loading = quantities["enzyme_loading"]
    assert loading["value"].startswith(REVIEW_MARKER) and loading["units"].startswith(REVIEW_MARKER)
    assert ("kinetics.csv", "value") in {(item["file"], item["column"]) for item in draft.review_fields}

    designed = user_tables_from_sabiork(
        path,
        dataset_id="specific_activity_format",
        design={"enzyme_loading": {"value": 0.05, "units": "mg/L"}, "enzyme_concentration": {"value": 1, "units": "uM"}},
    )
    quantities = {row["quantity"]: row for row in designed.kinetics}
    assert (quantities["enzyme_loading"]["value"], quantities["enzyme_loading"]["units"]) == ("0.05", "mg/L")
    assert quantities["enzyme_loading"]["evidence_type"] == "design"
    assert "enzyme_concentration" not in quantities  # the Vmax form has no enzyme concentration
    assert "enzyme_concentration = 1 uM" in designed.review and "not used by any case" in designed.review
    directory = tmp_path / "designed"
    designed.write(directory)
    _fill_manifest(directory)
    vmax = _role(_parameters(load_user_dataset(directory)), "vmax")
    # 12 umol/min/mg x 0.05 mg/L = 0.6 umol/(L min), formed by the loader, not by the converter.
    assert Q_(vmax.value.value, vmax.value.units).to("uM/min").magnitude == pytest.approx(0.6)


def test_vmax_routes_by_dimension_and_unknown_units_are_listed(tmp_path: Path) -> None:
    molar = user_tables_from_sabiork(
        _derived_export(tmp_path, {"kcat": _vmax("µM*min^(-1)")}), dataset_id="vmax_format"
    )
    assert {row["quantity"] for row in molar.kinetics} >= {"km", "vmax"}
    assert not any(row["quantity"] == "enzyme_loading" for row in molar.kinetics)

    mass_rate = user_tables_from_sabiork(
        _derived_export(tmp_path, {"kcat": _vmax("mg*ml^(-1)*min^(-1)")}), dataset_id="vmax_format"
    )
    reasons = {item["parameter"]: item["reason"] for item in mass_rate.not_converted_parameters}
    assert "mass concentration per time" in reasons["Vmax"]

    unknown = user_tables_from_sabiork(
        _derived_export(tmp_path, {"kcat": _vmax("OD*min^(-1)")}), dataset_id="vmax_format"
    )
    reasons = {item["parameter"]: item["reason"] for item in unknown.not_converted_parameters}
    assert "not parsed by the unit registry and are not in the SABIO-RK unit table" in reasons["Vmax"]
    assert "| 35622 | Vmax | Vmax | 12.0 | OD*min^(-1) |" in unknown.review

    both = user_tables_from_sabiork(
        _derived_export(tmp_path, {"kcat_Km": _vmax("µM*min^(-1)")}), dataset_id="vmax_format"
    )
    assert "vmax" not in {row["quantity"] for row in both.kinetics}
    assert any("the kcat form is kept" in item["reason"] for item in both.not_converted_parameters)


def test_unit_table_maps_spellings_the_unit_registry_rejects(monkeypatch: pytest.MonkeyPatch) -> None:
    # Emulate a unit registry that does not read SABIO-RK's ``^(-1)`` spellings.
    monkeypatch.setattr(user_data_sources, "_parses", lambda units: "^" not in units)
    draft = user_tables_from_sabiork("618", dataset_id="unit_table", entry_ids=["35622"])
    kcat = next(row for row in draft.kinetics if row["quantity"] == "kcat")
    assert (kcat["value"], kcat["units"]) == ("0.13", "1/s")
    assert "'s^(-1)' is written as '1/s' (SABIO-RK unit table; the same unit)." in draft.review


def test_unit_table_entries_are_the_same_units() -> None:
    for spelling, target in SABIORK_UNIT_SPELLINGS.items():
        Q_(1.0, target)
        try:
            original = Q_(1.0, spelling)
        except Exception:  # a spelling this unit registry cannot read is exactly what the table is for
            continue
        assert original.to(target).magnitude == pytest.approx(1.0), spelling
    for spelling, target in SABIORK_TEMPERATURE_UNITS.items():
        assert target in {"degC", "kelvin"}
        assert units_are_compatible(target, "kelvin")


def test_public_names_are_exported() -> None:
    for name in ("user_tables_from_sabiork", "UserTablesDraft", "UserTablesSourceError"):
        assert name in fungal_model.__all__
