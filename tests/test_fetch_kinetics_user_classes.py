"""Kinetics of the enzyme classes a user dataset defines, looked up by their EC numbers (FETCH-003).

A class of a user dataset's ``enzyme_classes.csv`` carries an ``ec_number``.
FETCH-002 listed such classes as "not queried", because the SABIO-RK
conversion resolved an entry's EC number against the registry only. Now the
conversion (``user_tables_from_sabiork(user_enzyme_classes=...)``) also
resolves it to a user-defined class of the dataset being assembled, by exact
match of complete EC numbers, and ``assemble_user_tables(fetch_kinetics=True)``
(``fungmod assemble --fetch-kinetics``) queries those classes by their own EC
number and the substrate's name, under the FETCH-002 snapshot, status and
reporting rules. An EC number two classes share (two user-defined classes, or
a registry and a user-defined class) is listed with the reason and never
chosen, and nothing is matched by a name.

Every SABIO-RK answer here is a SYNTHETIC TEST RESPONSE written by hand in the
format of SABIO-RK's export API (``tests/fixtures/sabiork_kinetics_queries/``,
see its README); none is SABIO-RK data, and no organism stands behind any
entry. The user dataset ``tests/fixtures/user_data/lab_classes_case/`` holds
illustrative estimates only. Every test runs with ``urlopen`` and socket
connections patched to fail; a test that fetches serves its responses through
``_FakeSabio``.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import socket
import urllib.request
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

from fungal_model import assemble_user_tables, load_user_dataset, user_tables_from_sabiork, virtual_experiment
from fungal_model.api.user_data import REVIEW_MARKER
from fungal_model.api.user_data_assembly import _LOOKUP_LIMITATIONS, NETWORK_BLOCKED, AssembledTablesDraft
from fungal_model.api.user_data_sources import ENZYME_CLASS_COLUMNS, UserTablesSourceError, _csv_text
from fungal_model.cli import EXIT_OK
from fungal_model.registry import load_registry
from fungal_model.sources.sabiork import fetch as sabiork_fetch
from fungal_model.sources.sabiork.query_snapshots import ec_number_query
from tests.test_assemble_network import (
    CHAIN,
    TEST_OLIGOMER,
    TEST_OLIGOMER_CLASS,
    _draft_digest,
    _registry_chain_draft,
    _with_registry_chain,
    _without_network_block,
)
from tests.test_fetch_kinetics import (
    ANNOTATION,
    ANNOTATION_SOURCE,
    ANNOTATION_TOOL,
    BODY_A,
    BODY_NONE,
    C30_PH5,
    ESTERASE,
    EXPORT_618,
    G1,
    K1,
    QUERIES_OLIGOMER,
    QUERY_A,
    REGISTRY_INDEX,
    RESPONSES,
    _cli,
    _csv_rows,
    _FakeSabio,
    _files,
    _forbidden,
    _k1,
    _offline,
    _query,
    _url,
    _uses,
)

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "tests" / "fixtures" / "user_data" / "lab_classes_case"
ESTER_NAME = "4-Nitrophenyl butyrate"
PHOSPHATE_NAME = "4-Nitrophenyl phosphate"
# The classes' own ec_number cells and the substrates' names in substrates.csv make the queries.
QUERY_ESTER = 'ECNumber:"3.1.1.1" AND Substrate:"4-Nitrophenyl butyrate"'
QUERY_PHOSPHATE = 'ECNumber:"3.1.3.2" AND Substrate:"4-Nitrophenyl phosphate"'
QUERY_ESTERASE_FIXTURE = 'ECNumber:"3.1.1.1" AND Substrate:"p-nitrophenyl butyrate"'
BODY_ESTER_PATH = RESPONSES / "ecnumber_3_1_1_1_nitrophenyl_butyrate.json"
BODY_PHOSPHATE_PATH = RESPONSES / "ecnumber_3_1_3_2_nitrophenyl_phosphate.json"
BODY_ESTER = BODY_ESTER_PATH.read_bytes()
BODY_PHOSPHATE = BODY_PHOSPHATE_PATH.read_bytes()
K6 = "Synthetic kinetics organism K6"
K7 = "Synthetic kinetics organism K7"
K8 = "Synthetic kinetics organism K8"
ESTER_CLASS = "lab_ester_hydrolase"
PHOSPHATE_CLASS = "lab_phosphomonoesterase"
ESTER_DEFINED_IN = "enzyme_classes.csv row 2 of user dataset lab_classes_demo"
C25_PH7 = {"temperature": 25, "temperature_units": "degC", "ph": 7}
C30_PH7 = {"temperature": 30, "temperature_units": "degC", "ph": 7}
C37_PH7_5 = {"temperature": 37, "temperature_units": "degC", "ph": 7.5}
C40_PH5 = {"temperature": 40, "temperature_units": "degC", "ph": 5}
DESIGN = {
    "substrate_initial_concentration": {"value": 1, "units": "mM"},
    "enzyme_concentration": {"value": 0.05, "units": "uM"},
}

# Digests computed at e97e8e6 (the base of FETCH-003) with the same calls: drafts that involve no user-defined class
# in a SABIO-RK conversion, which FETCH-003 leaves byte for byte. _draft_digest for assembled drafts; for drafts of
# user_tables_from_sabiork, SHA-256 over their file texts and to_dict().
DIGESTS_E97E8E6 = {
    "esterase_user_data": "8b3b812c2c9f129bae7444875506eb5b2df4f7fd5962245616fa0beb555a52c9",
    "sabiork_618_draft": "d097ad3c8d7adf5ccc689ad417827ebd69a7a204f33d03ad1eddb7671f60969a",
    "sabiork_618_draft_proposed": "ce9604ee46bd206e7f1d43133db0bc3a9ac6606d23d30a05181b66db0859dc0d",
    "sabiork_maltose_response_draft": "f87eb21b9f68fd16a7bb28018333a0a137196981a6fdc056684c7d1c6f144b2a",
}
# Digests at e97e8e6 of FETCH-002 lookups of registry classes, with the fetch clock fixed (_fixed_clock). FETCH-003
# changes one sentence of their limitations (the lookup no longer leaves out classes a user dataset defines); with
# that sentence put back, the drafts are byte-identical.
LOOKUP_DIGESTS_E97E8E6 = {
    "k1_lookup_registry": "7fca33a05b2e6227f6d34f0b0935c100d227d25dbf83dbfff1344ace3b50e458",
    "g1_lookup_transfer": "59ea5e0bab96d0ab98d39b62c3be1022270e3ec5c1c2bf33021962e909fe0dff",
    "network_registry_chain_lookup": "2f8945019370a2d3f4ce694f57e305485d9f6ad341ba507ac1534ae5badaf9a6",
}
LOOKUP_LIMITATION_E97E8E6 = (
    "Kinetics looked up by EC number: one SABIO-RK query per complete EC number of a registry enzyme class of the "
    "fungus (its EC number and the EC numbers among its aliases that resolve to it) and substrate name, "
    'ECNumber:"<EC number>" AND Substrate:"<substrate name>". Entries filed under another name of the substrate are '
    "not found, and classes without an EC number or defined in a user dataset are not looked up (each is listed "
    "with the reason)."
)


# ---------------------------------------------------------------------------
# No network in the default test run


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(urllib.request, "urlopen", _forbidden)
    monkeypatch.setattr(sabiork_fetch, "urlopen", _forbidden)
    monkeypatch.setattr(socket.socket, "connect", _forbidden)
    monkeypatch.setattr(sabiork_fetch, "MIN_REQUEST_INTERVAL_SECONDS", 0.0)
    yield


@pytest.fixture
def sabio(monkeypatch: pytest.MonkeyPatch) -> _FakeSabio:
    fake = _FakeSabio()
    monkeypatch.setattr(sabiork_fetch, "urlopen", fake)
    return fake


@pytest.fixture
def cache(tmp_path_factory: pytest.TempPathFactory) -> Path:
    # The substrates' names make long snapshot directory names; a short root keeps Windows paths short.
    return tmp_path_factory.mktemp("k")


def _fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Freeze the snapshot id and retrieval time a fetch records, so a looked-up draft has one digest."""

    monkeypatch.setattr(sabiork_fetch, "_snapshot_id", lambda: "20261008T000000000000Z-" + "0" * 32)
    monkeypatch.setattr(sabiork_fetch, "_utc_now", lambda: "2026-10-08T00:00:00Z")


def _lab(cache_dir: Path, **overrides: Any) -> AssembledTablesDraft:
    """Strain K6 of the lab dataset, whose species is the organism of entries 9900021 and 9900024."""

    arguments: dict[str, Any] = {
        "dataset_id": "lab_lookup",
        "fungus": "strain_k6",
        "substrates": ["pnp_butyrate"],
        "conditions": [C25_PH7, C30_PH7, C37_PH7_5],
        "user_data": LAB,
        "design": DESIGN,
        "registry": REGISTRY_INDEX,
        "cache_dir": cache_dir,
        "fetch_kinetics": True,
    }
    arguments.update(overrides)
    return assemble_user_tables(**arguments)


def _lab_copy(tmp_path: Path, edit: Callable[[list[dict[str, str]]], list[dict[str, str]]]) -> Path:
    """A copy of the lab dataset whose enzyme_classes.csv rows ``edit`` changes."""

    target = tmp_path / "lab"
    shutil.copytree(LAB, target)
    rows = edit(_csv_rows(LAB / "enzyme_classes.csv"))
    (target / "enzyme_classes.csv").write_bytes(_csv_text(ENZYME_CLASS_COLUMNS, rows).encode("utf-8"))
    load_user_dataset(target, registry=load_registry(REGISTRY_INDEX))
    return target


def _with_ec(class_id: str, ec_number: str) -> Callable[[list[dict[str, str]]], list[dict[str, str]]]:
    def edit(rows: list[dict[str, str]]) -> list[dict[str, str]]:
        return [{**row, "ec_number": ec_number} if row["class_id"] == class_id else row for row in rows]

    return edit


def _reviewed(draft: AssembledTablesDraft, directory: Path) -> Path:
    draft.write(directory)
    manifest = yaml.safe_load((directory / "user_dataset.yml").read_text(encoding="utf-8"))
    manifest["contributor"] = "Test reviewer"
    (directory / "user_dataset.yml").write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    assert REVIEW_MARKER not in "".join(path.read_text(encoding="utf-8") for path in directory.glob("*.csv"))
    return directory


# ---------------------------------------------------------------------------
# A lab's own class gets literature and transferred kinetics


def test_a_lab_class_gets_same_species_literature_and_a_transfer_and_reruns_offline_byte_identical(
    sabio: _FakeSabio, monkeypatch: pytest.MonkeyPatch, cache: Path, tmp_path: Path
) -> None:
    assert ec_number_query("3.1.1.1", substrate=ESTER_NAME) == QUERY_ESTER
    sabio.serve(QUERY_ESTER, BODY_ESTER)

    draft = _lab(cache, refresh=True)

    # One query: the class's own ec_number from enzyme_classes.csv and the substrate's name from substrates.csv. The
    # second lab class does not act on the substrate and is not queried.
    assert sabio.requested == [_url(QUERY_ESTER)]
    cases = {case["condition"]: case for case in draft.assembly["cases"]}
    assert {condition: case["kinetics_status"] for condition, case in cases.items()} == {
        "c25_ph7": "user_data",
        "c30_ph7": "literature_same_organism",
        "c37_ph7_5": "transferred_estimate",
    }
    assert cases["c30_ph7"]["source_ids"] == ["SABIO-RK EntryID 9900021"]
    assert cases["c37_ph7_5"]["source_ids"] == ["SABIO-RK EntryID 9900022"]
    assert {case["enzyme_class"] for case in cases.values()} == {ESTER_CLASS}

    rows = {(row["condition_id"], row["quantity"]): row for row in draft.kinetics}
    # Same species: literature, as the conversion writes it, with sd and the entry as source.
    assert {key: rows["c30_ph7", "km"][key] for key in ("enzyme_class", "value", "units", "sd", "evidence_type")} == {
        "enzyme_class": ESTER_CLASS,
        "value": "0.35",
        "units": "mM",
        "sd": "0.04",
        "evidence_type": "literature",
    }
    assert rows["c30_ph7", "kcat"]["value"] == "45" and rows["c30_ph7", "kcat"]["evidence_type"] == "literature"
    assert rows["c30_ph7", "km"]["source"] == "SABIO-RK EntryID 9900021 (FungMod test fixture)"
    # Another organism: an estimate whose method says where it was transferred from.
    for quantity, value in (("km", "0.52"), ("kcat", "60")):
        assert rows["c37_ph7_5", quantity]["value"] == value
        assert rows["c37_ph7_5", quantity]["evidence_type"] == "estimate"
        assert rows["c37_ph7_5", quantity]["method"].startswith(f"transferred from {K7} enzyme, SABIO-RK entry 9900022")
    # The design amounts, and the lab's own rows at 25 degC unchanged.
    assert rows["c30_ph7", "enzyme_concentration"]["evidence_type"] == "design"
    own = [row for row in draft.kinetics if row["condition_id"] == "c25_ph7"]
    assert own == _csv_rows(LAB / "kinetics.csv")
    # The draft's enzyme_classes.csv holds the lab's rows unchanged.
    assert [dict(row) for row in draft.enzyme_classes] == _csv_rows(LAB / "enzyme_classes.csv")

    lookup = draft.assembly["kinetics_lookup"]
    assert lookup["not_queried"] == []
    item = _query(draft, QUERY_ESTER)
    assert (item["enzyme_class"], item["class_defined_in"], item["ec_number"], item["substrate_id"]) == (
        ESTER_CLASS,
        ESTER_DEFINED_IN,
        "3.1.1.1",
        "pnp_butyrate",
    )
    assert item["substrate"] == ESTER_NAME and item["entries"] == 4 and item["http_status"] == 200
    assert item["counts"] == {"converted": 2, "listed": 1, "not convertible": 1}
    assert _uses(item) == {"9900021": "converted", "9900022": "converted", "9900023": "not convertible", "9900024": "listed"}
    reasons = {entry["entry_id"]: entry["reason"] for entry in item["not_converted"]}
    assert reasons["9900023"].startswith("mutant enzyme (synthetic variant V2)")
    # The lab's own rows at 25 degC precede the same species's entry there.
    assert "not used at this condition (weaker evidence): SABIO-RK EntryID 9900024" in reasons["9900024"]

    # The decision names the class and its EC number; the conversion's substrates.csv row is not claimed, since the
    # draft keeps the dataset's own row.
    assert any(
        text.startswith(f"EC 3.1.1.1 (carboxylesterase) resolves to user-defined enzyme class `{ESTER_CLASS}`")
        for text in draft.decisions
    )
    assert (
        f"SABIO-RK entries on '{ESTER_NAME}' are matched to substrate `pnp_butyrate` of user dataset lab_classes_demo "
        "by its name; its substrates.csv row, with its product and yield, is kept unchanged."
    ) in draft.decisions
    assert not any(text.startswith(("Substrate ", "Product of ")) for text in draft.decisions)
    assert [dict(row) for row in draft.substrates] == [_csv_rows(LAB / "substrates.csv")[0]]
    assert f"| {ESTER_CLASS} (user-defined, {ESTER_DEFINED_IN}) | 3.1.1.1 |" in draft.review
    assert "or the ec_number of a user-defined class in enzyme_classes.csv) and substrate it acts on" in draft.review
    assert _LOOKUP_LIMITATIONS[1] in draft.assembly["limitations"]

    # Offline, the frozen snapshot gives the same draft, byte for byte.
    _offline(monkeypatch)
    offline = _lab(cache)
    assert _draft_digest(offline) == _draft_digest(draft)
    assert offline.file_texts() == draft.file_texts()

    # The reviewed draft loads; the same-species case runs in scientific mode, the transfer only in exploratory mode.
    directory = _reviewed(draft, tmp_path / "draft")
    registry = load_registry(REGISTRY_INDEX)
    dataset = load_user_dataset(directory, registry=registry)
    for condition, scientific in (("c30_ph7", "modelable"), ("c37_ph7_5", "underparameterized")):
        study = virtual_experiment(
            fungi="strain_k6", substrates="pnp_butyrate", environments=condition, user_data=dataset, registry=registry
        )
        (exploratory,) = study.preflight(mode="exploratory")
        (strict,) = study.preflight(mode="scientific")
        assert (exploratory.status, strict.status) == ("modelable", scientific), condition


def test_a_second_lab_class_gets_a_vmax_form_transfer_and_an_export_gives_the_same_rows(
    sabio: _FakeSabio, cache: Path, tmp_path: Path
) -> None:
    """Another EC number and substrate, the Vmax form in micromolar units, and both classes in one request."""

    sabio.serve(QUERY_ESTER, BODY_ESTER)
    sabio.serve(QUERY_PHOSPHATE, BODY_PHOSPHATE)
    request: dict[str, Any] = {
        "fungus": "Lab strain K6",
        "substrates": ["pnp_butyrate", "pnp_phosphate"],
        "conditions": [C40_PH5],
        "design": {"substrate_initial_concentration": {"value": 0.5, "units": "mM"}},
    }

    draft = _lab(cache, refresh=True, dataset_id="lab_vmax", **request)

    # Each class is queried on the substrate it acts on only.
    assert sabio.requested == [_url(QUERY_ESTER), _url(QUERY_PHOSPHATE)]
    cases = {case["enzyme_class"]: case for case in draft.assembly["cases"]}
    assert cases[PHOSPHATE_CLASS]["kinetics_status"] == "transferred_estimate"
    assert cases[PHOSPHATE_CLASS]["source_ids"] == ["SABIO-RK EntryID 9900031"]
    # Nothing was measured at 40 degC, pH 5 for the ester class, and nothing is reused from another condition.
    assert cases[ESTER_CLASS]["kinetics_status"] == "gap"
    rows = {row["quantity"]: row for row in draft.kinetics if row["enzyme_class"] == PHOSPHATE_CLASS}
    assert set(rows) == {"km", "vmax", "substrate_initial_concentration"}
    assert {key: rows["vmax"][key] for key in ("value", "units", "sd", "evidence_type")} == {
        "value": "85",
        "units": "µM*min^(-1)",
        "sd": "5",
        "evidence_type": "estimate",
    }
    assert {key: rows["km"][key] for key in ("value", "units", "evidence_type")} == {
        "value": "210",
        "units": "µM",
        "evidence_type": "estimate",
    }
    assert rows["km"]["method"].startswith(f"transferred from {K8} enzyme, SABIO-RK entry 9900031")
    item = _query(draft, QUERY_PHOSPHATE)
    assert (item["enzyme_class"], item["ec_number"], item["substrate_id"]) == (PHOSPHATE_CLASS, "3.1.3.2", "pnp_phosphate")
    assert item["class_defined_in"] == "enzyme_classes.csv row 3 of user dataset lab_classes_demo"
    assert _uses(item) == {"9900031": "converted", "9900032": "not used"}
    assert _uses(_query(draft, QUERY_ESTER)) == {
        "9900021": "not used",
        "9900022": "not used",
        "9900023": "not convertible",
        "9900024": "not used",
    }

    # The reviewed draft loads; the Vmax-form transfer runs in exploratory mode only.
    directory = _reviewed(draft, tmp_path / "draft")
    registry = load_registry(REGISTRY_INDEX)
    dataset = load_user_dataset(directory, registry=registry)
    (condition,) = draft.assembly["requested_conditions"]
    study = virtual_experiment(
        fungi="strain_k6", substrates="pnp_phosphate", environments=condition["condition_id"], user_data=dataset,
        registry=registry,
    )
    (exploratory,) = study.preflight(mode="exploratory")
    assert exploratory.status == "modelable"
    (scientific,) = study.preflight(mode="scientific")
    assert scientific.status == "underparameterized"

    # The same answer downloaded by hand as an export (kinetics_sources, no lookup) gives the same kinetics rows.
    exported = _lab(
        cache,
        dataset_id="lab_vmax",
        **request,
        fetch_kinetics=False,
        kinetics_sources=[BODY_ESTER_PATH, BODY_PHOSPHATE_PATH],
    )
    assert exported.kinetics == draft.kinetics
    assert "kinetics_lookup" not in exported.assembly


# ---------------------------------------------------------------------------
# An EC number two classes share is listed, never chosen


def test_two_user_classes_with_one_ec_number_are_listed_and_neither_gets_entries(
    sabio: _FakeSabio, cache: Path, tmp_path: Path
) -> None:
    def add_twin(rows: list[dict[str, str]]) -> list[dict[str, str]]:
        # Defined in enzyme_classes.csv only; the strain does not have it, and the EC number is still shared.
        return [*rows, {**rows[0], "class_id": "lab_ester_hydrolase_twin", "name": "Lab ester hydrolase twin"}]

    twin = _lab_copy(tmp_path, add_twin)

    looked_up = _lab(cache, user_data=twin, refresh=True)

    assert sabio.requested == []
    (item,) = looked_up.assembly["kinetics_lookup"]["not_queried"]
    assert (item["enzyme_class"], item["substrate_id"]) == (ESTER_CLASS, "pnp_butyrate")
    assert item["reason"] == (
        "EC 3.1.1.1 is also the ec_number of user-defined enzyme class lab_ester_hydrolase_twin (enzyme_classes.csv), "
        f"so its SABIO-RK entries would not become kinetics of {ESTER_CLASS}; nothing was queried"
    )
    assert looked_up.assembly["kinetics_lookup"]["queries"] == []

    # The same entries from an export: refused for both classes, never decided by a name.
    exported = _lab(cache, user_data=twin, fetch_kinetics=False, kinetics_sources=[BODY_ESTER_PATH])
    reasons = {item["entry_id"]: item["reason"] for item in exported.not_converted}
    expected = (
        "EC 3.1.1.1 (carboxylesterase) is the ec_number of user-defined enzyme classes 'lab_ester_hydrolase', "
        "'lab_ester_hydrolase_twin' of enzyme_classes.csv; FungMod does not choose between classes that share an EC "
        "number, and never by the enzyme name"
    )
    assert {entry: reason for entry, reason in reasons.items() if entry != "9900023"} == {
        "9900021": expected,
        "9900022": expected,
        "9900024": expected,
    }
    assert [case["kinetics_status"] for case in exported.assembly["cases"]] == ["user_data", "gap", "gap"]


def test_an_ec_number_of_a_registry_class_and_a_user_class_is_listed_on_both_sides(
    sabio: _FakeSabio, cache: Path, tmp_path: Path
) -> None:
    # The lab gives its own class the EC number of the registry's beta_glucosidase record.
    shared = _lab_copy(tmp_path, _with_ec(ESTER_CLASS, "3.2.1.21"))
    request: dict[str, Any] = {
        "user_data": shared,
        "substrates": ["pnp_butyrate", "cellobiose"],
        "conditions": [C30_PH5],
        "enzyme_classes": [
            {"enzyme_class": "beta_glucosidase", "evidence": "test-only assertion", "source": "tests"}
        ],
    }

    looked_up = _lab(cache, refresh=True, **request)

    # Neither class is queried by the shared EC number: no entry with it could become kinetics of either.
    assert sabio.requested == []
    reasons = {item["enzyme_class"]: item["reason"] for item in looked_up.assembly["kinetics_lookup"]["not_queried"]}
    assert reasons == {
        ESTER_CLASS: (
            f"EC 3.2.1.21 of {ESTER_CLASS} also resolves to registry enzyme class beta_glucosidase, so its SABIO-RK "
            f"entries would not become kinetics of {ESTER_CLASS}; nothing was queried"
        ),
        "beta_glucosidase": (
            f"EC 3.2.1.21 is also the ec_number of user-defined enzyme class {ESTER_CLASS} (enzyme_classes.csv), so "
            "its SABIO-RK entries would not become kinetics of beta_glucosidase; nothing was queried"
        ),
    }

    # The registry class's own entries from an export are refused too, with both classes named.
    exported = _lab(cache, fetch_kinetics=False, kinetics_sources=[EXPORT_618], entry_ids=["35622"], **request)
    refused = {item["entry_id"]: item["reason"] for item in exported.not_converted}
    assert exported.converted_entry_ids == ()
    assert refused["35622"].startswith(
        "EC 3.2.1.21 (beta-glucosidase) resolves both to registry enzyme class 'beta_glucosidase' and to "
        f"user-defined enzyme class '{ESTER_CLASS}' of enzyme_classes.csv; FungMod does not choose"
    )
    statuses = {case["enzyme_class"]: case["kinetics_status"] for case in exported.assembly["cases"]}
    assert statuses == {ESTER_CLASS: "gap", "beta_glucosidase": "gap"}


def test_a_registry_class_keeps_its_other_ec_numbers_when_one_is_shared(
    sabio: _FakeSabio, cache: Path, tmp_path: Path
) -> None:
    """cellobiohydrolase states 3.2.1.91 and 3.2.1.176; a lab class with 3.2.1.176 leaves it only 3.2.1.91."""

    def add_cleaver(rows: list[dict[str, str]]) -> list[dict[str, str]]:
        return [
            *rows,
            {
                "class_id": "lab_exo_cleaver",
                "name": "Lab exo cleaver",
                "ec_number": "3.2.1.176",
                "target_bond_classes": "beta_1_4_glycosidic",
                "compatible_substrate_classes": TEST_OLIGOMER_CLASS,
                "source": "test-only class of tests/test_fetch_kinetics_user_classes.py",
            },
        ]

    shared = _lab_copy(tmp_path, add_cleaver)
    enzymes = (shared / "enzymes.csv").read_bytes()
    (shared / "enzymes.csv").write_bytes(enzymes + b"strain_k6,lab_exo_cleaver,test-only assertion,tests\n")
    (query_91, query_176) = QUERIES_OLIGOMER
    sabio.serve(query_91, BODY_NONE)

    draft = _lab(
        cache,
        user_data=shared,
        substrates=[TEST_OLIGOMER],
        conditions=[C30_PH5],
        enzyme_classes=[{"enzyme_class": "cellobiohydrolase", "evidence": "test-only assertion", "source": "tests"}],
        registry=_with_registry_chain(load_registry(REGISTRY_INDEX)),
        refresh=True,
    )

    assert sabio.requested == [_url(query_91)] and _url(query_176) not in sabio.requested
    (item,) = draft.assembly["kinetics_lookup"]["queries"]
    assert (item["enzyme_class"], item["ec_number"], item["entries"]) == ("cellobiohydrolase", "3.2.1.91", 0)
    assert "class_defined_in" not in item
    reasons = {entry["enzyme_class"]: entry["reason"] for entry in draft.assembly["kinetics_lookup"]["not_queried"]}
    assert reasons == {
        "cellobiohydrolase": (
            "EC 3.2.1.176 is also the ec_number of user-defined enzyme class lab_exo_cleaver (enzyme_classes.csv), so "
            "SABIO-RK entries with that EC number would not become kinetics of cellobiohydrolase and that EC number "
            "was not queried; EC 3.2.1.91 was queried"
        ),
        "lab_exo_cleaver": (
            "EC 3.2.1.176 of lab_exo_cleaver also resolves to registry enzyme class cellobiohydrolase, so its SABIO-RK "
            "entries would not become kinetics of lab_exo_cleaver; nothing was queried"
        ),
    }


def test_a_lab_class_of_an_enzyme_network_is_queried_on_its_intermediate_pool(
    sabio: _FakeSabio, cache: Path, tmp_path: Path
) -> None:
    """The network_chain fixture with an ec_number given to its second class; SABIO-RK answers with no entries."""

    chain = _without_network_block(tmp_path, CHAIN)
    classes = _csv_rows(chain / "enzyme_classes.csv")
    classes = [{**row, "ec_number": "3.2.1.74"} if row["class_id"] == "oligomer_hydrolase_like" else row for row in classes]
    (chain / "enzyme_classes.csv").write_bytes(_csv_text(ENZYME_CLASS_COLUMNS, classes).encode("utf-8"))
    query = ec_number_query("3.2.1.74", substrate="Oligomer-like pool O1")
    sabio.serve(query, BODY_NONE)

    draft = assemble_user_tables(
        dataset_id="chain_lookup",
        fungus="strain_n1",
        substrates=["polymer_p1"],
        conditions=[C30_PH5, C40_PH5],
        user_data=chain,
        network=True,
        registry=REGISTRY_INDEX,
        cache_dir=cache,
        fetch_kinetics=True,
        refresh=True,
    )

    # The intermediate pool is queried by the class's own EC number; the class without one is listed.
    assert sabio.requested == [_url(query)]
    (item,) = draft.assembly["kinetics_lookup"]["queries"]
    assert (item["enzyme_class"], item["substrate_id"], item["entries"]) == ("oligomer_hydrolase_like", "oligomer_o1", 0)
    assert item["class_defined_in"] == "enzyme_classes.csv row 3 of user dataset network_chain"
    (listed,) = draft.assembly["kinetics_lookup"]["not_queried"]
    assert listed["enzyme_class"] == "depolymerase_like" and "no EC number" in listed["reason"]
    # An empty answer changes nothing: the user's rows at 30 degC, a gap at 40 degC that blocks the network there.
    (network,) = draft.assembly["network"]["networks"]
    members = {member["enzyme_class"]: member["kinetics_status"] for member in network["members"]}
    assert members["oligomer_hydrolase_like"] == {"c30_ph5": "user_data", "c40_ph5": "gap"}
    assert {condition["condition"]: condition["status"] for condition in network["conditions"]}["c40_ph5"] == NETWORK_BLOCKED


def test_a_partial_ec_number_is_not_queried_and_matches_no_entry(sabio: _FakeSabio, cache: Path, tmp_path: Path) -> None:
    partial = _lab_copy(tmp_path, _with_ec(ESTER_CLASS, "3.1.1.-"))

    looked_up = _lab(cache, user_data=partial, refresh=True)

    assert sabio.requested == []
    (item,) = looked_up.assembly["kinetics_lookup"]["not_queried"]
    assert item["reason"] == (
        f"{ESTER_CLASS} is an enzyme class of the user dataset (enzyme_classes.csv, EC 3.1.1.-, not a complete EC "
        "number); SABIO-RK is queried by complete EC number only, never by a class or enzyme name; nothing was queried"
    )
    # Exact match of complete EC numbers only: 3.1.1.1 is not "in" 3.1.1.-.
    exported = _lab(cache, user_data=partial, fetch_kinetics=False, kinetics_sources=[BODY_ESTER_PATH])
    reasons = {item["entry_id"]: item["reason"] for item in exported.not_converted}
    assert reasons["9900021"].startswith(
        "EC 3.1.1.1 (carboxylesterase) does not resolve to a registry enzyme class or to the ec_number of a "
        "user-defined class; no class is invented"
    )


def test_the_esterase_fixture_class_is_now_looked_up_by_its_ec_number(sabio: _FakeSabio, cache: Path) -> None:
    """FETCH-002 listed this class as not queried; its EC number now makes a query, here answered with no entries."""

    sabio.serve(QUERY_ESTERASE_FIXTURE, BODY_NONE)

    draft = assemble_user_tables(
        dataset_id="esterase_lookup",
        fungus="strain_e1",
        substrates=["p_nitrophenyl_butyrate"],
        conditions=[{"temperature": 37, "temperature_units": "degC", "ph": 7.5}],
        user_data=ESTERASE,
        registry=REGISTRY_INDEX,
        cache_dir=cache,
        fetch_kinetics=True,
        refresh=True,
    )

    assert sabio.requested == [_url(QUERY_ESTERASE_FIXTURE)]
    lookup = draft.assembly["kinetics_lookup"]
    assert lookup["not_queried"] == []
    (item,) = lookup["queries"]
    assert (item["enzyme_class"], item["class_defined_in"], item["entries"]) == (
        "carboxylesterase",
        "enzyme_classes.csv row 2 of user dataset esterase_demo",
        0,
    )
    assert [case["kinetics_status"] for case in draft.assembly["cases"]] == ["user_data"]


# ---------------------------------------------------------------------------
# The conversion on its own


def test_user_tables_from_sabiork_resolves_an_ec_number_to_a_given_user_class() -> None:
    classes = _csv_rows(LAB / "enzyme_classes.csv")

    draft = user_tables_from_sabiork(BODY_ESTER_PATH, dataset_id="lab_entries", user_enzyme_classes=classes)

    assert draft.converted_entry_ids == ("9900021", "9900022", "9900024")
    assert {row["enzyme_class"] for row in draft.enzymes} == {ESTER_CLASS}
    # Only the class the entries resolve to, as the user wrote it.
    assert [dict(row) for row in draft.enzyme_classes] == [classes[0]]
    assert "an exact match; no registry class and no other user-defined class has that EC number" in draft.review
    assert "and against the ec_number of the user-defined classes given (user_enzyme_classes" in draft.review

    # Without the user's classes nothing resolves, with the message of e97e8e6.
    with pytest.raises(
        UserTablesSourceError,
        match=r"EntryID 9900022: EC 3\.1\.1\.1 \(carboxylesterase\) does not resolve to a registry enzyme class; no "
        "class is invented",
    ):
        user_tables_from_sabiork(BODY_ESTER_PATH, dataset_id="lab_entries", entry_ids=["9900022", "9900024"])


def test_user_tables_from_sabiork_never_takes_a_user_class_by_name(tmp_path: Path) -> None:
    payload = json.loads(BODY_ESTER)
    (entry,) = [item for item in payload["data"] if item["id"] == 9900021]
    entry["enzyme_description"]["ec_number"] = "3.1.1.99"
    entry["enzyme_description"]["enzyme_name"] = "Lab ester hydrolase"
    payload["data"] = [entry]
    payload["meta"]["total_count"] = 1
    derived = tmp_path / "derived_export.json"
    derived.write_text(json.dumps(payload), encoding="utf-8")
    classes = _csv_rows(LAB / "enzyme_classes.csv")

    with pytest.raises(UserTablesSourceError, match="does not resolve to a registry enzyme class or to the ec_number"):
        user_tables_from_sabiork(derived, dataset_id="by_name", user_enzyme_classes=classes)
    with pytest.raises(
        UserTablesSourceError,
        match="names user-defined enzyme class 'lab_ester_hydrolase', whose ec_number is 3.1.1.1; the EC number and "
        "the name disagree, so no class is proposed",
    ):
        user_tables_from_sabiork(
            derived, dataset_id="by_name", user_enzyme_classes=classes, propose_enzyme_classes=True
        )


@pytest.mark.parametrize(
    ("classes", "message"),
    [
        ("lab_ester_hydrolase", "a sequence of enzyme_classes.csv rows"),
        ({"class_id": "x"}, "a sequence of enzyme_classes.csv rows"),
        (["lab_ester_hydrolase"], r"user_enzyme_classes\[0\] must be an enzyme_classes.csv row"),
        ([{"class_id": "x", "ec": "3.1.1.1"}], r"has key\(s\) ec, which are not enzyme_classes.csv columns"),
        ([{"class_id": "bad id"}], "needs a class_id of letters and digits"),
        ([{"class_id": "a_b"}, {"class_id": "a_b"}], "repeats class_id 'a_b'"),
        ([{"class_id": "beta_glucosidase"}], "names a registry enzyme class"),
    ],
)
def test_user_enzyme_classes_are_checked(classes: Any, message: str) -> None:
    with pytest.raises(UserTablesSourceError, match=message):
        user_tables_from_sabiork(BODY_ESTER_PATH, dataset_id="checked", user_enzyme_classes=classes)


# ---------------------------------------------------------------------------
# Without a user-defined class nothing changes


def _baseline(name: str) -> str:
    if name == "esterase_user_data":
        return _draft_digest(
            assemble_user_tables(
                dataset_id="esterase_draft",
                fungus="strain_e1",
                substrates=["p_nitrophenyl_butyrate"],
                conditions=[{"temperature": 37, "temperature_units": "degC", "ph": 7.5}],
                user_data=ESTERASE,
                registry=REGISTRY_INDEX,
            )
        )
    drafts = {
        "sabiork_618_draft": lambda: user_tables_from_sabiork(EXPORT_618, dataset_id="draft_618"),
        "sabiork_618_draft_proposed": lambda: user_tables_from_sabiork(
            EXPORT_618, dataset_id="draft_618", propose_enzyme_classes=True
        ),
        "sabiork_maltose_response_draft": lambda: user_tables_from_sabiork(
            RESPONSES / "ecnumber_3_2_1_3_maltose.json",
            dataset_id="maltose_draft",
            propose_enzyme_classes=True,
            design={"substrate_initial_concentration": {"value": 5, "units": "mM"}},
        ),
    }
    draft = drafts[name]()
    payload = {"files": draft.file_texts(), "dict": draft.to_dict()}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


@pytest.mark.parametrize("name", sorted(DIGESTS_E97E8E6))
def test_drafts_without_a_user_class_in_a_conversion_are_byte_identical_to_the_base_commit(name: str) -> None:
    assert _baseline(name) == DIGESTS_E97E8E6[name]


@pytest.mark.parametrize("name", sorted(LOOKUP_DIGESTS_E97E8E6))
def test_lookups_of_registry_classes_change_only_the_lookup_limitation(
    name: str, sabio: _FakeSabio, monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    _fixed_clock(monkeypatch)
    sabio.serve(QUERY_A, BODY_A)
    for query in QUERIES_OLIGOMER:
        sabio.serve(query, BODY_NONE)
    root = tmp_path_factory.mktemp("r")
    drafts = {
        "k1_lookup_registry": lambda: _k1(root, refresh=True),
        "g1_lookup_transfer": lambda: assemble_user_tables(
            dataset_id="g1_lookup",
            fungus=G1,
            substrates=["cellobiose"],
            conditions=[C30_PH5],
            annotation=ANNOTATION,
            annotation_tool=ANNOTATION_TOOL,
            annotation_source=ANNOTATION_SOURCE,
            registry=REGISTRY_INDEX,
            cache_dir=root,
            fetch_kinetics=True,
            refresh=True,
            entry_ids=["9900002"],
        ),
        "network_registry_chain_lookup": lambda: _registry_chain_draft(
            _with_registry_chain(load_registry(REGISTRY_INDEX)),
            kinetics_sources=(),
            entry_ids=None,
            same_species=[K1],
            cache_dir=root,
            fetch_kinetics=True,
            refresh=True,
        ),
    }
    draft = drafts[name]()

    assert all("class_defined_in" not in item for item in draft.assembly["kinetics_lookup"]["queries"])
    payload = {
        "files": draft.file_texts(),
        "annotations": {item: hashlib.sha256(data).hexdigest() for item, data in sorted(draft.annotation_files.items())},
        "dict": draft.to_dict(),
    }
    text = json.dumps(payload, sort_keys=True)
    new, old = json.dumps(_LOOKUP_LIMITATIONS[1])[1:-1], json.dumps(LOOKUP_LIMITATION_E97E8E6)[1:-1]
    # The sentence is in review.md and in assembly["limitations"], nowhere else.
    assert text.count(new) == 2 and old not in text
    assert hashlib.sha256(text.replace(new, old).encode("utf-8")).hexdigest() == LOOKUP_DIGESTS_E97E8E6[name]


def test_a_stored_lookup_has_the_same_bytes_on_every_platform(
    sabio: _FakeSabio, monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """The derived export and the fetch metadata are written with LF line endings on every platform, so the
    export SHA-256 a draft quotes (and the digests pinned above) do not depend on where the lookup ran."""

    _fixed_clock(monkeypatch)
    sabio.serve(QUERY_A, BODY_A)
    root = tmp_path_factory.mktemp("lf")
    draft = _k1(root, refresh=True)
    written = sorted(root.rglob("combined_export.json")) + sorted(root.rglob("fetch_metadata.json"))
    assert len(written) >= 2
    for path in written:
        assert b"\r\n" not in path.read_bytes(), path
    (query,) = [item for item in draft.assembly["kinetics_lookup"]["queries"] if item["query"] == QUERY_A]
    assert query["export_sha256"] == hashlib.sha256(next(root.rglob("combined_export.json")).read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# fungmod assemble --user-data ... --fetch-kinetics --fetch, check-data, run


def _assemble_lab(cache_dir: Path, *extra: str | Path) -> list[str]:
    return [
        str(argument)
        for argument in (
            "assemble",
            "--fungus",
            "strain_k6",
            "--user-data",
            LAB,
            "--substrate",
            "pnp_butyrate",
            "--temperature-c",
            "30",
            "--ph",
            "7",
            "--design",
            "substrate_initial_concentration=1",
            "mM",
            "--design",
            "enzyme_concentration=0.05",
            "uM",
            "--registry",
            REGISTRY_INDEX,
            "--cache-dir",
            cache_dir,
            "--dataset-id",
            "lab_lookup",
            "--fetch-kinetics",
            *extra,
        )
    ]


def test_fungmod_assemble_looks_up_a_lab_class_and_the_draft_checks_and_runs(
    sabio: _FakeSabio, monkeypatch: pytest.MonkeyPatch, cache: Path, tmp_path: Path
) -> None:
    sabio.serve(QUERY_ESTER, BODY_ESTER)
    draft_dir = tmp_path / "draft"

    code, out, err = _cli(*_assemble_lab(cache, "--fetch", "--output", draft_dir))

    assert code == EXIT_OK, err
    assert sabio.requested == [_url(QUERY_ESTER)]
    assert f"  {ESTER_CLASS} (user-defined, {ESTER_DEFINED_IN}) on pnp_butyrate, EC 3.1.1.1: {QUERY_ESTER}" in out
    assert "4 entries; 1 converted, 2 not used, 1 not convertible" in out
    assert (
        f"converted 9900021 ({K6}) -> {ESTER_CLASS} on pnp_butyrate at c30_ph7 (literature_same_organism)"
    ) in out
    assert "not convertible 9900023 (Synthetic kinetics organism K7): mutant enzyme (synthetic variant V2)" in out
    assert "not queried" not in out
    first = _files(draft_dir)

    # Offline, without --fetch: the frozen snapshot gives the same draft, byte for byte.
    _offline(monkeypatch)
    rerun = tmp_path / "rerun"
    code, out_offline, err = _cli(*_assemble_lab(cache, "--output", rerun))
    assert code == EXIT_OK, err
    assert f"network: not used; frozen snapshots under {cache} (--fetch queries the database)" in out_offline
    assert _files(rerun) == first

    # The reviewed draft is checked and run in scientific mode: the lab class with the same species's literature.
    manifest = yaml.safe_load((draft_dir / "user_dataset.yml").read_text(encoding="utf-8"))
    manifest["contributor"] = "Test reviewer"
    (draft_dir / "user_dataset.yml").write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    code, out_check, err_check = _cli("check-data", draft_dir, "--registry", REGISTRY_INDEX)
    assert code == EXIT_OK, err_check
    assert "User dataset: lab_lookup" in out_check
    code, out_run, err_run = _cli(
        "run",
        "--user-data",
        draft_dir,
        "--fungus",
        "strain_k6",
        "--substrate",
        "pnp_butyrate",
        "--condition",
        "c30_ph7",
        "--registry",
        REGISTRY_INDEX,
        "--mode",
        "scientific",
        "--output",
        tmp_path / "run",
        "--no-plots",
    )
    assert code == EXIT_OK, err_run
    assert "lab_lookup__strain_k6  lab_lookup__pnp_butyrate  lab_lookup__c30_ph7  modelable  yes" in out_run
    assert "Run label: scientific_exact_unvalidated" in out_run
